import tucana.generated.shared.struct_pb2 as struct_pb2

from src.schema.flow_schema import LiteralValue


def map_to_literal_value_schema(grpc_value: struct_pb2.Value) -> LiteralValue:
    if grpc_value.null_value:
        return LiteralValue(value=None)
    elif grpc_value.bool_value:
        return LiteralValue(value=grpc_value.bool_value)
    elif grpc_value.number_value.integer:
        return LiteralValue(value=grpc_value.number_value.integer)
    elif grpc_value.number_value.float:
        return LiteralValue(value=grpc_value.number_value.float)
    elif grpc_value.string_value:
        return LiteralValue(value=grpc_value.string_value)
    elif grpc_value.list_value:
        return LiteralValue(value=[map_to_literal_value_schema(v).value for v in grpc_value.list_value.values])
    elif grpc_value.struct_value:
        return LiteralValue(
            value={k: map_to_literal_value_schema(v).value for k, v in grpc_value.struct_value.fields.items()})

    return LiteralValue(value=None)


def map_to_grpc_literal_value(literal_value: LiteralValue) -> struct_pb2.Value:
    grpc_val = struct_pb2.Value()

    if literal_value.value is None:
        grpc_val.null_value = struct_pb2.NullValue.NULL_VALUE
    elif isinstance(literal_value.value, bool):
        grpc_val.bool_value = literal_value.value
    elif isinstance(literal_value.value, int):
        grpc_val.number_value.integer = literal_value.value
    elif isinstance(literal_value.value, float):
        grpc_val.number_value.float = literal_value.value
    elif isinstance(literal_value.value, str):
        grpc_val.string_value = literal_value.value
    elif isinstance(literal_value.value, list):
        list_val = struct_pb2.ListValue()
        for v in literal_value.value:
            list_val.values.append(map_to_grpc_literal_value(LiteralValue(value=v)))
        grpc_val.list_value.CopyFrom(list_val)
    elif isinstance(literal_value.value, dict):
        struct_val = struct_pb2.Struct()
        for k, v in literal_value.value.items():
            struct_val.fields[k].CopyFrom(map_to_grpc_literal_value(LiteralValue(value=v)))
        grpc_val.struct_value.CopyFrom(struct_val)

    return grpc_val
