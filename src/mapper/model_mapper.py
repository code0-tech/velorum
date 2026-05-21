import tucana.generated.velorum.info_pb2 as info_pb2

from src.schema.model_schema import Model


def map_to_grpc_model(model: Model) -> info_pb2.Model:
    model_types = []
    capabilities = model.capabilities if model.capabilities else []

    type_map = {
        "explain": info_pb2.Model.ModelType.EXPLAIN,
        "generate": info_pb2.Model.ModelType.GENERATE,
    }

    for capability in capabilities:
        if capability.lower() in type_map:
            model_types.append(type_map[capability.lower()])

    if not model_types:
        model_types = [info_pb2.Model.ModelType.UNKNOWN]

    return info_pb2.Model(
        identifier=model.identifier,
        name=model.name,
        token_cost=float(model.token_cost) if model.token_cost else 0.0,
        type=model_types
    )
