import tucana.generated.shared.flow_pb2 as flow_pb2

from src.mapper.flow_literal_value_mapper import map_to_grpc_literal_value, map_to_literal_value_schema
from src.mapper.flow_value_mapper import map_to_grpc_value, map_to_value_schema
from src.schema.flow_schema import LiteralValue, Flow, NodeFunction, FlowSetting


def map_to_flow_schema(grpc_flow: flow_pb2.GenerationFlow) -> Flow:
    return Flow(
        name=grpc_flow.name,
        type=grpc_flow.type,
        startingNodeId=grpc_flow.starting_node_id,
        nodes=[
            NodeFunction(
                functionIdentifier=node.runtime_function_id,
                id=node.database_id,
                nextNodeId=node.next_node_id if node.next_node_id else None,
                parameters=[map_to_value_schema(param.value) for param in node.parameters]
            )
            for node in grpc_flow.node_functions
        ],
        settings=[
            FlowSetting(
                value=map_to_literal_value_schema(setting.value).value
            )
            for setting in grpc_flow.settings
        ]
    )


def map_to_grpc_flow(flow: Flow) -> flow_pb2.GenerationFlow:
    grpc_flow = flow_pb2.GenerationFlow()

    grpc_flow.name = flow.name
    grpc_flow.type = flow.type
    grpc_flow.starting_node_id = str(flow.starting_node_id)

    if flow.nodes:
        for node in flow.nodes:
            grpc_node = flow_pb2.NodeFunction()
            grpc_node.database_id = node.id
            grpc_node.runtime_function_id = node.function_identifier

            if node.next_node_id is not None:
                grpc_node.next_node_id = node.next_node_id

            if node.parameters:
                for idx, param in node.parameters:
                    grpc_param = flow_pb2.NodeParameter()
                    grpc_param.runtime_parameter_id = f"param_{idx}"
                    grpc_param.value = map_to_grpc_value(param)
                    grpc_node.parameters.append(grpc_param)

            grpc_flow.node_functions.append(grpc_node)

    if flow.settings:
        for idx, setting in flow.settings:
            grpc_setting = flow_pb2.FlowSetting()
            grpc_setting.flow_setting_id = f"setting_{idx}"
            grpc_setting.value.CopyFrom(map_to_grpc_literal_value(LiteralValue(value=setting.value)))
            grpc_flow.settings.append(grpc_setting)

    return grpc_flow
