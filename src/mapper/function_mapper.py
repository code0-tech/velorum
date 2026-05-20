import tucana.generated.shared.function_pb2 as function_pb2

from src.schema.function_schema import FunctionDefinition, ParameterDefinition


def map_to_function_schema(grpc_value: function_pb2.FunctionDefinition) -> FunctionDefinition:
    return FunctionDefinition(
        identifier=grpc_value.runtime_name,
        signature=grpc_value.signature,
        names=grpc_value.name[0].content if grpc_value.name else "",
        aliases=grpc_value.alias[0].content if grpc_value.alias else "",
        descriptions=grpc_value.description[0].content if grpc_value.description else "",
        parameterDefinitions=[
            ParameterDefinition(
                names=parameter.name[0].content if parameter.name else "",
                descriptions=parameter.description[0].content if parameter.description else "",
            ) for parameter in grpc_value.parameter_definitions
        ]
    )

def map_to_grpc_function(function: FunctionDefinition) -> function_pb2.FunctionDefinition:
    return function_pb2.FunctionDefinition(
        runtime_name=function.identifier,
        signature=function.signature,
        name=[
            {
                "code": "en-US",
                "content": function.names if function.names else ""
            }
        ],
        alias=[
            {
                "code": "en-US",
                "content": function.aliases if function.aliases else ""
            }
        ],
        description=[
            {
                "code": "en-US",
                "content": function.descriptions if function.descriptions else ""
            }
        ],
        parameter_definitions=[
            {
                "default_value": parameter.default_value,
                "name": [
                    {
                        "code": "en-US",
                        "content": parameter.names if parameter.names else ""
                    }
                ],
                "description": [
                    {
                        "code": "en-US",
                        "content": parameter.descriptions if parameter.descriptions else ""
                    }
                ]
            } for parameter in (function.parameter_definitions or [])
        ]
    )