import tucana.generated.shared.flow_type_pb2 as flow_type_pb2

from src.schema.flow_type_schema import FlowType, FlowTypeSetting


def map_to_flow_type_schema(grpc_value: flow_type_pb2.FlowType) -> FlowType:
    return FlowType(
        identifier=grpc_value.identifier,
        signature=grpc_value.signature,
        descriptions=grpc_value.description[0].content if grpc_value.description else "",
        names=grpc_value.name[0].content if grpc_value.name else "",
        aliases=grpc_value.alias[0].content if grpc_value.alias else "",
        flowTypeSettings=[
            FlowTypeSetting(
                names=setting.name[0].content if setting.name else "",
                descriptions=setting.description[0].content if setting.name else "",
            )
            for setting in grpc_value.settings
        ]
    )


def map_to_grpc_flow_type(flow_type: FlowType) -> flow_type_pb2.FlowType:
    return flow_type_pb2.FlowType(
        identifier=flow_type.identifier,
        signature=flow_type.signature,
        description=[
            {
                "code": "en-US",
                "content": flow_type.descriptions if flow_type.descriptions else ""
            }
        ],
        name=[
            {
                "code": "en-US",
                "content": flow_type.names if flow_type.names else ""
            }
        ],
        alias=[
            {
                "code": "en-US",
                "content": flow_type.aliases if flow_type.aliases else ""
            }
        ],
        settings=[
            {
                "name": [
                    {
                        "code": "en-US",
                        "content": setting.names if setting.names else ""
                    }
                ],
                "description": [
                    {
                        "code": "en-US",
                        "content": setting.names if setting.names else ""
                    }
                ],
                "default_value": setting.default_value
            }
            for setting in (flow_type.flow_type_settings or [])
        ]
    )
