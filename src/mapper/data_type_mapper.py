import tucana.generated.shared.data_type_pb2 as data_type_pb2

from src.schema.data_type_schema import DataType


def map_to_data_type_schema(grpc_value: data_type_pb2.DefinitionDataType) -> DataType:
    return DataType(
        identifier=grpc_value.identifier,
        type=grpc_value.type,
        genericKeys=grpc_value.generic_keys,
    )

def map_to_grpc_data_type(data_type: DataType) -> data_type_pb2.DefinitionDataType:
    return data_type_pb2.DefinitionDataType(
        identifier=data_type.identifier,
        type=data_type.type,
        generic_keys=data_type.generic_keys,
    )
