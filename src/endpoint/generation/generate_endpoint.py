import time

import grpc
import tucana.generated.velorum.generate_pb2 as pb2
import tucana.generated.velorum.generate_pb2_grpc as pb2_grpc
from litellm.types.completion import ChatCompletionUserMessageParam
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from src.mapper.data_type_mapper import map_to_data_type_schema
from src.mapper.flow_mapper import map_pydantic_flow_to_grpc
from src.mapper.flow_types_mapper import map_to_flow_type_schema
from src.mapper.function_mapper import map_to_function_schema
from src.orchestrator.prompt_orchestrator import PromptOrchestrator
from src.postprocessing.flow_post import flow_postprocessing
from src.schema.flow_schema import Flow
from src.store.flow_type_store import FlowTypeStore
from src.store.function_store import FunctionStore


class GenerateService(pb2_grpc.GenerateServiceServicer):

    def __init__(self):
        self.memory_client = QdrantClient(":memory:")
        self.vector_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.function_store = FunctionStore(self.memory_client, self.vector_model)
        self.flow_type_store = FlowTypeStore(self.memory_client, self.vector_model)
        self.prompt_orchestrator = PromptOrchestrator()
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

        print("1")

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

        few_shots = [
            ChatCompletionUserMessageParam(role="user",
                                           content="Erstelle einen Webhook flow, welche4 ein user objekt speichert und anschließend die mail als response zurückgibt."),
            {
                "role": "assistant",
                "content": Flow(**{
                    "name": "User email webhook",
                    "nodes": [
                        {
                            "functionIdentifier": "std::control::value",
                            "id": 1,
                            "nextNodeId": 2,
                            "parameters": [
                                {
                                    "value": {
                                        "email": "test@test.com",
                                        "username": "test",
                                    }
                                }
                            ],
                        },
                        {
                            "functionIdentifier": "http::response::create",
                            "id": 2,
                            "nextNodeId": 3,
                            "parameters": [
                                {
                                    "value": 200
                                },
                                {
                                    "value": {}
                                },
                                {
                                    "nodeFunctionId": 1,
                                    "referencePath": [{
                                        "path": "email"
                                    }]
                                }
                            ],
                        },
                        {
                            "functionIdentifier": "rest::control::respond",
                            "id": 3,
                            "parameters": [
                                {
                                    "nodeFunctionId": 2,
                                }
                            ],
                        }
                    ],
                    "startingNodeId": 1,
                    "type": "REST"
                }).model_dump_json()
            },
            ChatCompletionUserMessageParam(role="user",
                                           content="Erstelle einen Webhook flow, welcher über die Liste [1,2,3] iteriert und jede Zahl mal zwei rechnet und das Eregbnis zurückgibt."),
            {
                "role": "assistant",
                "content": Flow(**{
                    "name": "Map list webhook flow",
                    "nodes": [
                        {
                            "functionIdentifier": "std::list::map",
                            "id": 1,
                            "nextNodeId": 4,
                            "parameters": [
                                {
                                    "value": [1, 2, 3]
                                },
                                {
                                    "startingNodeId": 2
                                }
                            ],
                        },
                        {
                            "functionIdentifier": "std::number::multiply",
                            "id": 2,
                            "nextNodeId": 3,
                            "parameters": [
                                {
                                    "nodeFunctionId": 1,
                                    "parameterIndex": 1,
                                    "input_index": 0
                                },
                                {
                                    "value": 2
                                }
                            ],
                        },
                        {
                            "functionIdentifier": "std::control::return",
                            "id": 3,
                            "parameters": [
                                {
                                    "nodeFunctionId": 2,
                                }
                            ],
                        },
                        {
                            "functionIdentifier": "http::response::create",
                            "id": 4,
                            "nextNodeId": 5,
                            "parameters": [
                                {
                                    "value": 200
                                },
                                {
                                    "value": {}
                                },
                                {
                                    "nodeFunctionId": 1,
                                }
                            ],
                        },
                        {
                            "functionIdentifier": "rest::control::respond",
                            "id": 5,
                            "parameters": [
                                {
                                    "nodeFunctionId": 4,
                                }
                            ],
                        }
                    ],
                    "startingNodeId": 1,
                    "type": "REST"
                }).model_dump_json()
            },
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
                prompt=request.prompt,
                few_shots=few_shots,
                available_functions=self.function_store.combine(prompt_functions, few_shot_functions),
                available_flow_types=self.flow_type_store.combine(prompt_flow_types, few_shots_flow_types)
            )

            current_time_ms = int(time.time() * 1000)
            return pb2.FlowResponse(
                flow=map_pydantic_flow_to_grpc(
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
            context.abort(
                code=grpc.StatusCode.INTERNAL,
                details="An unexpected error occurred during flow generation."
            )

    def Flow(self, request: pb2.FlowRequest, context) -> pb2.FlowResponse:
        return context.abort(
            code=grpc.StatusCode.UNIMPLEMENTED
        )
