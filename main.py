from litellm.types.completion import ChatCompletionUserMessageParam

from src.orchestrator.prompt_orchestrator import PromptOrchestrator
from src.postprocessing.flow_post import flow_postprocessing
from src.schema.flow_type_schema import FlowType
from src.schema.flow_schema import Flow
from src.store.function_store import FunctionStore

if __name__ == '__main__':
    # function store
    function_store = FunctionStore()
    function_store.insert_from_json("./test/functions.json", "./test/datatypes.json")

    # orchestrator
    prompt_orchestrator = PromptOrchestrator()

    prompt = "Erstelle einen HTTP Event Flow, der zuerst den Request loggt und dann 'Event empfangen' an Slack sendet."
    prompt_functions = function_store.search(
        prompt=prompt,
        limit=10
    )

    few_shots = [
        ChatCompletionUserMessageParam(role="user", content="Erstelle einen Webhook flow, welche4 ein user objekt speichert und anschließend die mail als response zurückgibt."),
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
                "type": "http_event_flow"
            }).model_dump_json()
        },
        ChatCompletionUserMessageParam(role="user", content="Erstelle einen Webhook flow, welcher über die Liste [1,2,3] iteriert und jede Zahl mal zwei rechnet und das Eregbnis zurückgibt."),
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
                "type": "http_event_flow"
            }).model_dump_json()
        },
    ]
    few_shot_functions = function_store.find_all(["std::control::value", "http::response::create", "rest::control::respond", "std::list::map", "std::control::return", "std::number::multiply"])

    generated_flow = prompt_orchestrator.generate(
        prompt=prompt,
        few_shots=few_shots,
        available_functions=function_store.combine(prompt_functions, few_shot_functions),
        available_flow_types=[
            FlowType(
                identifier="http_event_flow",
                names="HTTP Event Flow",
                descriptions="Ein Flow, der durch HTTP-Events ausgelöst wird.",
                signature="(): void",
            )
        ],
    )

    print(flow_postprocessing(generated_flow, [FlowType(
        identifier="http_event_flow",
        names="HTTP Event Flow",
        descriptions="Ein Flow, der durch HTTP-Events ausgelöst wird.",
        signature="(): void",
    )], function_store.get_all()).model_dump_json(indent=2, by_alias=True, exclude_none=True))
