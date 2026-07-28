import time

import grpc
import tucana.generated.velorum.generate_pb2 as pb2
import tucana.generated.velorum.generate_pb2_grpc as pb2_grpc
from litellm.types.completion import ChatCompletionUserMessageParam
from pydantic import ValidationError
from qdrant_client import QdrantClient

from src.logger import get_logger
from src.mapper.data_type_mapper import map_to_data_type_schema
from src.mapper.flow_mapper import map_to_grpc_flow, map_to_flow_schema
from src.mapper.flow_types_mapper import map_to_flow_type_schema
from src.mapper.function_mapper import map_to_function_schema
from src.model import load_vector_model
from src.orchestrator.flow_orchestrator import FlowOrchestrator
from src.orchestrator.prompt_orchestrator import PromptOrchestrator
from src.postprocessing.flow_post import flow_postprocessing
from src.schema.flow_schema import Flow
from src.store.few_shots_store import FewShotsStore
from src.store.flow_type_store import FlowTypeStore
from src.store.function_store import FunctionStore
from src.store.model_store import ModelStore

log = get_logger("generate_endpoint")


class GenerateService(pb2_grpc.GenerateServiceServicer):

    def __init__(self):
        log.info("Initializing GenerateService...")
        self.memory_client = QdrantClient(":memory:")
        self.vector_model = load_vector_model()
        self.function_store = FunctionStore(self.memory_client, self.vector_model)
        self.flow_type_store = FlowTypeStore(self.memory_client, self.vector_model)
        self.few_shots_store = FewShotsStore(self.memory_client, self.vector_model)
        self.model_store = ModelStore()
        self.prompt_orchestrator = PromptOrchestrator()
        self.flow_orchestrator = FlowOrchestrator()
        log.success("GenerateService ready")  # type: ignore[attr-defined]

    def Prompt(self, request: pb2.PromptRequest, context) -> pb2.FlowResponse:
        prompt_preview = request.prompt[:60].replace("\n", " ") + ("…" if len(request.prompt) > 60 else "")
        log.info(f"[Prompt] project={request.project_id} model={request.model_identifier} prompt=\"{prompt_preview}\"")

        if not request.project_id:
            log.warning("[Prompt] Rejected — missing project_id")
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'project_id' field cannot be empty. Please provide a valid project_id for flow generation."
            )

        if not request.prompt or not request.prompt.strip():
            log.warning("[Prompt] Rejected — empty prompt")
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'prompt' field cannot be empty. Please provide a valid prompt for flow generation."
            )

        if not request.model_identifier or not request.model_identifier.strip():
            log.warning("[Prompt] Rejected — missing model_identifier")
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'model_identifier' field cannot be empty. Please provide a valid model_identifier for flow generation."
            )

        if self.model_store.find(identifier=request.model_identifier) is None:
            log.warning(f"[Prompt] Rejected — unknown model '{request.model_identifier}'")
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details=f"The specified model_identifier '{request.model_identifier}' does not exist. Please provide a valid model_identifier for flow generation."
            )

        functions = [
            map_to_function_schema(fn)
            for fn in request.functions
        ]

        data_types = [
            map_to_data_type_schema(dt)
            for dt in request.data_types
        ]

        flow_types = [
            map_to_flow_type_schema(ft)
            for ft in request.flow_types
        ]

        log.info(
            f"[Prompt] Storing definitions — project={request.project_id} "
            f"functions={len(functions)} flow_types={len(flow_types)} data_types={len(data_types)}"
        )
        try:
            for fn in functions:
                self.function_store.insert_from_definition(
                    group_identifier=str(request.project_id),
                    payload=fn,
                    data_types=data_types
                )

            for ft in flow_types:
                self.flow_type_store.insert_from_definition(
                    group_identifier=str(request.project_id),
                    payload=ft,
                    data_types=data_types
                )
        except Exception as e:
            log.error(f"[Prompt] Failed to store definitions: {e}", exc_info=True)
            context.abort(
                code=grpc.StatusCode.INTERNAL,
                details="An unexpected error occurred while storing function/flow_type definitions."
            )
        log.info(f"[Prompt] Stored definitions successfully")

        stored_functions_count = len(self.function_store.get_all(group_identifier=str(request.project_id)))
        stored_flow_types_count = len(self.flow_type_store.get_all(group_identifier=str(request.project_id)))
        stored_few_shots_count = len(self.few_shots_store.get_all(group_identifier="global"))
        log.info(
            f"[Prompt] Store state — project={request.project_id} "
            f"functions={stored_functions_count} "
            f"flow_types={stored_flow_types_count} "
            f"few_shots={stored_few_shots_count}"
        )

        if stored_functions_count <= 0:
            log.warning(f"[Prompt] Rejected — no functions for project={request.project_id}")
            context.abort(
                code=grpc.StatusCode.ABORTED,
                details="No functions found for the given project_id. Please add functions before requesting a prompt generation."
            )

        if stored_flow_types_count <= 0:
            log.warning(f"[Prompt] Rejected — no flow types for project={request.project_id}")
            context.abort(
                code=grpc.StatusCode.ABORTED,
                details="No flow types found for the given project_id. Please add flow_types before requesting a prompt generation."
            )

        prompt_functions = self.function_store.search(
            group_identifier=str(request.project_id),
            prompt=request.prompt,
            limit=10
        )

        prompt_flow_types = self.flow_type_store.search(
            group_identifier=str(request.project_id),
            prompt=request.prompt,
            limit=2
        )

        prompt_few_shots = self.few_shots_store.search(
            group_identifier="global",
            prompt=request.prompt,
            limit=2
        )

        log.debug(
            f"[Prompt] Context — functions={len(prompt_functions)} "
            f"flow_types={len(prompt_flow_types)} "
            f"few_shots={len(prompt_few_shots)}"
        )

        # Only keep few-shots whose referenced functions are ALL available in the
        # project's function store — otherwise the example would teach the model to
        # use functions that do not exist for this project.
        candidate_function_ids = list({
            node.function_identifier
            for fS in prompt_few_shots
            for node in fS.flow.nodes
        })
        available_function_definitions = self.function_store.find_all(
            group_identifier=str(request.project_id),
            identifiers=candidate_function_ids
        )
        available_function_ids = {fn.identifier for fn in available_function_definitions}

        filtered_few_shots = [
            fS for fS in prompt_few_shots
            if all(node.function_identifier in available_function_ids for node in fS.flow.nodes)
        ]
        dropped_few_shots = len(prompt_few_shots) - len(filtered_few_shots)
        if dropped_few_shots:
            log.debug(f"[Prompt] Dropped {dropped_few_shots} few-shot(s) referencing unavailable functions")
        prompt_few_shots = filtered_few_shots

        few_shot_function_ids = list({
            node.function_identifier
            for fS in prompt_few_shots
            for node in fS.flow.nodes
        })
        few_shot_flow_type_ids = list({
            fS.flow.type
            for fS in prompt_few_shots
            if fS.flow.type
        })

        if few_shot_function_ids:
            log.debug(f"[Prompt] Few-shot functions: {few_shot_function_ids}")
        if few_shot_flow_type_ids:
            log.debug(f"[Prompt] Few-shot flow types: {few_shot_flow_type_ids}")

        few_shot_functions = [
            fn for fn in available_function_definitions
            if fn.identifier in few_shot_function_ids
        ]
        few_shots_flow_types = self.flow_type_store.find_all(
            group_identifier=str(request.project_id),
            identifiers=few_shot_flow_type_ids
        )

        few_shots = [
            msg
            for fS in prompt_few_shots
            for msg in (
                ChatCompletionUserMessageParam(role="user", content=fS.prompt),
                {"role": "assistant", "content": fS.flow.model_dump_json()},
            )
        ]

        combined_functions = self.function_store.combine(prompt_functions, few_shot_functions)
        combined_flow_types = self.flow_type_store.combine(prompt_flow_types, few_shots_flow_types)

        log.debug(
            f"[Prompt] Combined — functions={len(combined_functions)} "
            f"flow_types={len(combined_flow_types)}"
        )
        log.info(f"[Prompt] Generating flow...")

        t0 = time.time()
        try:
            generated_flow, completion = self.prompt_orchestrator.generate(
                model=self.model_store.find(identifier=request.model_identifier),
                prompt=request.prompt,
                few_shots=few_shots,
                available_functions=combined_functions,
                available_flow_types=combined_flow_types
            )

            elapsed = time.time() - t0
            log.success(  # type: ignore[attr-defined]
                f"[Prompt] Generated '{generated_flow.name}' in {elapsed:.2f}s | tokens={completion.usage.total_tokens}"
            )
            log.info(f"[Prompt] Generated flow: {generated_flow.model_dump_json()}")

            final_flow = flow_postprocessing(
                generated_flow,
                combined_flow_types,
                combined_functions
            )
            log.info(f"[Prompt] Post-processed flow: {final_flow.model_dump_json()}")

            current_time_ms = int(time.time() * 1000)
            return pb2.FlowResponse(
                flow=map_to_grpc_flow(final_flow),
                cached_until=current_time_ms + 300000,
                usage=completion.usage.total_tokens
            )
        except Exception as e:
            elapsed = time.time() - t0
            log.error(f"[Prompt] Generation failed after {elapsed:.2f}s: {e}", exc_info=True)
            context.abort(
                code=grpc.StatusCode.INTERNAL,
                details="An unexpected error occurred during flow generation."
            )

    def Flow(self, request: pb2.FlowRequest, context) -> pb2.FlowResponse:
        prompt_preview = request.prompt[:60].replace("\n", " ") + ("…" if len(request.prompt) > 60 else "")
        log.info(f"[Flow] project={request.project_id} model={request.model_identifier} prompt=\"{prompt_preview}\"")

        if not request.project_id:
            log.warning("[Flow] Rejected — missing project_id")
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'project_id' field cannot be empty. Please provide a valid project_id for flow generation."
            )

        if not request.prompt or not request.prompt.strip():
            log.warning("[Flow] Rejected — empty prompt")
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'prompt' field cannot be empty. Please provide a valid prompt for flow generation."
            )

        if not request.flow:
            log.warning("[Flow] Rejected — missing flow")
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'flow' field is invalid. Please provide a valid flow for flow generation."
            )

        try:
            incoming_flow = Flow.model_validate(map_to_flow_schema(request.flow))
            log.info(f"[Flow] Incoming flow: {incoming_flow.model_dump_json()}")
        except ValidationError as e:
            log.warning(f"[Flow] Rejected — invalid flow schema: {e}")
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details=f"The 'flow' field is invalid. Please provide a valid flow for flow generation."
            )

        if not request.model_identifier or not request.model_identifier.strip():
            log.warning("[Flow] Rejected — missing model_identifier")
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'model_identifier' field cannot be empty. Please provide a valid model_identifier for flow generation."
            )

        if self.model_store.find(identifier=request.model_identifier) is None:
            log.warning(f"[Flow] Rejected — unknown model '{request.model_identifier}'")
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details=f"The specified model_identifier '{request.model_identifier}' does not exist. Please provide a valid model_identifier for flow generation."
            )

        functions = [
            map_to_function_schema(fn)
            for fn in request.functions
        ]

        data_types = [
            map_to_data_type_schema(dt)
            for dt in request.data_types
        ]

        flow_types = [
            map_to_flow_type_schema(ft)
            for ft in request.flow_types
        ]

        log.info(
            f"[Flow] Storing definitions — project={request.project_id} "
            f"functions={len(functions)} flow_types={len(flow_types)} data_types={len(data_types)}"
        )
        try:
            for fn in functions:
                self.function_store.insert_from_definition(
                    group_identifier=str(request.project_id),
                    payload=fn,
                    data_types=data_types
                )

            for ft in flow_types:
                self.flow_type_store.insert_from_definition(
                    group_identifier=str(request.project_id),
                    payload=ft,
                    data_types=data_types
                )
        except Exception as e:
            log.error(f"[Flow] Failed to store definitions: {e}", exc_info=True)
            context.abort(
                code=grpc.StatusCode.INTERNAL,
                details="An unexpected error occurred while storing function/flow_type definitions."
            )
        log.info(f"[Flow] Stored definitions successfully")

        stored_functions_count = len(self.function_store.get_all(group_identifier=str(request.project_id)))
        stored_flow_types_count = len(self.flow_type_store.get_all(group_identifier=str(request.project_id)))
        stored_few_shots_count = len(self.few_shots_store.get_all(group_identifier="global"))
        log.info(
            f"[Flow] Store state — project={request.project_id} "
            f"functions={stored_functions_count} "
            f"flow_types={stored_flow_types_count} "
            f"few_shots={stored_few_shots_count}"
        )

        if stored_functions_count <= 0:
            log.warning(f"[Flow] Rejected — no functions for project={request.project_id}")
            context.abort(
                code=grpc.StatusCode.ABORTED,
                details="No functions found for the given project_id. Please add functions before requesting a prompt generation."
            )

        if stored_flow_types_count <= 0:
            log.warning(f"[Flow] Rejected — no flow types for project={request.project_id}")
            context.abort(
                code=grpc.StatusCode.ABORTED,
                details="No flow types found for the given project_id. Please add flow_types before requesting a prompt generation."
            )

        prompt_functions = self.function_store.search(
            group_identifier=str(request.project_id),
            prompt=request.prompt,
            limit=10
        )

        prompt_flow_types = self.flow_type_store.search(
            group_identifier=str(request.project_id),
            prompt=request.prompt,
            limit=2
        )

        flow_few_shots = self.few_shots_store.search(
            group_identifier="global",
            prompt=request.prompt,
            limit=2
        )

        log.debug(
            f"[Flow] Context — functions={len(prompt_functions)} "
            f"flow_types={len(prompt_flow_types)} "
            f"few_shots={len(flow_few_shots)}"
        )

        # Only keep few-shots whose referenced functions are ALL available in the
        # project's function store — otherwise the example would teach the model to
        # use functions that do not exist for this project.
        flow_candidate_function_ids = list({
            node.function_identifier
            for fS in flow_few_shots
            for node in fS.flow.nodes
        })
        flow_available_function_definitions = self.function_store.find_all(
            group_identifier=str(request.project_id),
            identifiers=flow_candidate_function_ids
        )
        flow_available_function_ids = {fn.identifier for fn in flow_available_function_definitions}

        filtered_flow_few_shots = [
            fS for fS in flow_few_shots
            if all(node.function_identifier in flow_available_function_ids for node in fS.flow.nodes)
        ]
        dropped_flow_few_shots = len(flow_few_shots) - len(filtered_flow_few_shots)
        if dropped_flow_few_shots:
            log.debug(f"[Flow] Dropped {dropped_flow_few_shots} few-shot(s) referencing unavailable functions")
        flow_few_shots = filtered_flow_few_shots

        flow_few_shot_function_ids = list({
            node.function_identifier
            for fS in flow_few_shots
            for node in fS.flow.nodes
        })
        flow_few_shot_flow_type_ids = list({
            fS.flow.type
            for fS in flow_few_shots
            if fS.flow.type
        })

        if flow_few_shot_function_ids:
            log.debug(f"[Flow] Few-shot functions: {flow_few_shot_function_ids}")
        if flow_few_shot_flow_type_ids:
            log.debug(f"[Flow] Few-shot flow types: {flow_few_shot_flow_type_ids}")

        flow_few_shot_functions = [
            fn for fn in flow_available_function_definitions
            if fn.identifier in flow_few_shot_function_ids
        ]
        flow_few_shots_flow_types = self.flow_type_store.find_all(
            group_identifier=str(request.project_id),
            identifiers=flow_few_shot_flow_type_ids
        )

        incoming_flow_function_ids = list({
            node.function_identifier
            for node in incoming_flow.nodes
        })
        incoming_flow_flow_type_ids = [incoming_flow.type] if incoming_flow.type else []

        if incoming_flow_function_ids:
            log.debug(f"[Flow] Incoming-flow functions: {incoming_flow_function_ids}")
        if incoming_flow_flow_type_ids:
            log.debug(f"[Flow] Incoming-flow flow types: {incoming_flow_flow_type_ids}")

        incoming_flow_functions = self.function_store.find_all(
            group_identifier=str(request.project_id),
            identifiers=incoming_flow_function_ids
        )
        incoming_flow_flow_types = self.flow_type_store.find_all(
            group_identifier=str(request.project_id),
            identifiers=incoming_flow_flow_type_ids
        )

        few_shots = [
            msg
            for fS in flow_few_shots
            for msg in (
                ChatCompletionUserMessageParam(role="user", content=fS.prompt),
                {"role": "assistant", "content": fS.flow.model_dump_json()},
            )
        ]

        combined_functions = self.function_store.combine(
            self.function_store.combine(prompt_functions, flow_few_shot_functions),
            incoming_flow_functions
        )
        combined_flow_types = self.flow_type_store.combine(
            self.flow_type_store.combine(prompt_flow_types, flow_few_shots_flow_types),
            incoming_flow_flow_types
        )

        log.debug(
            f"[Flow] Combined — functions={len(combined_functions)} "
            f"flow_types={len(combined_flow_types)}"
        )
        log.info(f"[Flow] Modifying flow...")

        t0 = time.time()
        try:
            generated_flow, completion = self.flow_orchestrator.generate(
                model=self.model_store.find(identifier=request.model_identifier),
                prompt=request.prompt,
                flow=map_to_flow_schema(request.flow),
                few_shots=few_shots,
                available_functions=combined_functions,
                available_flow_types=combined_flow_types
            )

            elapsed = time.time() - t0
            log.success(  # type: ignore[attr-defined]
                f"[Flow] Modified '{generated_flow.name}' in {elapsed:.2f}s | tokens={completion.usage.total_tokens}"
            )
            log.info(f"[Flow] Generated flow: {generated_flow.model_dump_json()}")

            final_flow = flow_postprocessing(
                generated_flow,
                combined_flow_types,
                combined_functions
            )
            log.info(f"[Flow] Post-processed flow: {final_flow.model_dump_json()}")

            current_time_ms = int(time.time() * 1000)
            return pb2.FlowResponse(
                flow=map_to_grpc_flow(final_flow),
                cached_until=current_time_ms + 300000,
                usage=completion.usage.total_tokens
            )
        except Exception as e:
            elapsed = time.time() - t0
            log.error(f"[Flow] Generation failed after {elapsed:.2f}s: {e}", exc_info=True)
            context.abort(
                code=grpc.StatusCode.INTERNAL,
                details="An unexpected error occurred during flow generation."
            )
