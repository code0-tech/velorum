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
                defaultValue=parameter.default_value,
                names=parameter.name[0].content if parameter.name else "",
                descriptions=parameter.description[0].content if parameter.description else "",
            ) for parameter in grpc_value.parameter_definitions
        ]
    )
