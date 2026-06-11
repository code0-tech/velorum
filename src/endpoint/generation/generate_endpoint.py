import time

import grpc
import tucana.generated.velorum.generate_pb2 as pb2
import tucana.generated.velorum.generate_pb2_grpc as pb2_grpc
from litellm.types.completion import ChatCompletionUserMessageParam
from pydantic import ValidationError
from qdrant_client import QdrantClient

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


class GenerateService(pb2_grpc.GenerateServiceServicer):

    def __init__(self):
        self.memory_client = QdrantClient(":memory:")
        self.vector_model = load_vector_model()
        self.function_store = FunctionStore(self.memory_client, self.vector_model)
        self.flow_type_store = FlowTypeStore(self.memory_client, self.vector_model)
        self.few_shots_store = FewShotsStore(self.memory_client, self.vector_model)
        self.model_store = ModelStore()
        self.prompt_orchestrator = PromptOrchestrator()
        self.flow_orchestrator = FlowOrchestrator()
        pass

    def Prompt(self, request: pb2.PromptRequest, context) -> pb2.FlowResponse:

        if not request.project_id:
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'project_id' field cannot be empty. Please provide a valid project_id for flow generation."
            )

        if not request.prompt or not request.prompt.strip():
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'prompt' field cannot be empty. Please provide a valid prompt for flow generation."
            )

        if not request.model_identifier or not request.model_identifier.strip():
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'model_identifier' field cannot be empty. Please provide a valid model_identifier for flow generation."
            )

        if self.model_store.find(identifier=request.model_identifier) is None:
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details=f"The specified model_identifier '{request.model_identifier}' does not exist. Please provide a valid model_identifier for flow generation."
            )

        if len(
                self.function_store.get_all(
                    group_identifier=str(request.project_id)
                )
        ) <= 0 and (len(request.functions) <= 0):
            context.abort(
                code=grpc.StatusCode.ABORTED,
                details="No functions found for the given project_id. Please add functions before requesting a prompt generation."
            )

        if len(
                self.flow_type_store.get_all(
                    group_identifier=str(request.project_id)
                )
        ) <= 0 and (len(request.flow_types) <= 0):
            context.abort(
                code=grpc.StatusCode.ABORTED,
                details="No flow types found for the given project_id. Please add flow_types before requesting a prompt generation."
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

        few_shots = [
            (
                ChatCompletionUserMessageParam(role="user", content=fS.prompt),
                {
                    "role": "assistant",
                    "content": fS.flow.model_dump_json()
                },
            )
            for fS in prompt_few_shots
        ]

        few_shot_functions = self.function_store.find_all(
            group_identifier=str(request.project_id),
            identifiers=[
                "std::control::value",
                "http::response::create",
                "rest::control::respond",
                "std::list::map",
                "std::control::return",
                "std::number::multiply"
            ]
        )
        few_shots_flow_types = self.flow_type_store.find_all(
            group_identifier=str(request.project_id),
            identifiers=[
                "REST"
            ]
        )

        try:
            generated_flow, completion = self.prompt_orchestrator.generate(
                model=self.model_store.find(identifier=request.model_identifier),
                prompt=request.prompt,
                few_shots=few_shots,
                available_functions=self.function_store.combine(prompt_functions, few_shot_functions),
                available_flow_types=self.flow_type_store.combine(prompt_flow_types, few_shots_flow_types)
            )

            current_time_ms = int(time.time() * 1000)
            return pb2.FlowResponse(
                flow=map_to_grpc_flow(
                    flow_postprocessing(
                        generated_flow,
                        self.flow_type_store.combine(prompt_flow_types,
                                                     few_shots_flow_types),
                        self.function_store.combine(prompt_functions,
                                                    few_shot_functions)
                    )
                ),
                cached_until=current_time_ms + 300000,
                usage=completion.usage.total_tokens
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            context.abort(
                code=grpc.StatusCode.INTERNAL,
                details="An unexpected error occurred during flow generation."
            )

    def Flow(self, request: pb2.FlowRequest, context) -> pb2.FlowResponse:
        if not request.project_id:
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'project_id' field cannot be empty. Please provide a valid project_id for flow generation."
            )

        if not request.prompt or not request.prompt.strip():
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'prompt' field cannot be empty. Please provide a valid prompt for flow generation."
            )

        if not request.flow:
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'flow' field is invalid. Please provide a valid flow for flow generation."
            )

        try:
            Flow.model_validate(map_to_flow_schema(request.flow))
        except ValidationError as e:
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details=f"The 'flow' field is invalid. Please provide a valid flow for flow generation."
            )

        if not request.model_identifier or not request.model_identifier.strip():
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="The 'model_identifier' field cannot be empty. Please provide a valid model_identifier for flow generation."
            )

        if self.model_store.find(identifier=request.model_identifier) is None:
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details=f"The specified model_identifier '{request.model_identifier}' does not exist. Please provide a valid model_identifier for flow generation."
            )

        if len(
                self.function_store.get_all(
                    group_identifier=str(request.project_id)
                )
        ) <= 0 and (len(request.functions) <= 0):
            context.abort(
                code=grpc.StatusCode.ABORTED,
                details="No functions found for the given project_id. Please add functions before requesting a prompt generation."
            )

        if len(
                self.flow_type_store.get_all(
                    group_identifier=str(request.project_id)
                )
        ) <= 0 and (len(request.flow_types) <= 0):
            context.abort(
                code=grpc.StatusCode.ABORTED,
                details="No flow types found for the given project_id. Please add flow_types before requesting a prompt generation."
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

        try:
            generated_flow, completion = self.flow_orchestrator.generate(
                model=self.model_store.find(identifier=request.model_identifier),
                prompt=request.prompt,
                flow=map_to_flow_schema(request.flow),
                few_shots=[],
                available_functions=prompt_functions,
                available_flow_types=prompt_flow_types
            )

            current_time_ms = int(time.time() * 1000)
            return pb2.FlowResponse(
                flow=map_to_grpc_flow(
                    flow_postprocessing(
                        generated_flow,
                        prompt_flow_types,
                        prompt_functions
                    )
                ),
                cached_until=current_time_ms + 300000,
                usage=completion.usage.total_tokens
            )
        except Exception as e:
            context.abort(
                code=grpc.StatusCode.INTERNAL,
                details="An unexpected error occurred during flow generation."
            )
