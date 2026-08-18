import tucana.generated.shared.flow_pb2 as flow_pb2

from src.mapper.flow_literal_value_mapper import map_to_grpc_literal_value, map_to_literal_value_schema
from src.schema.flow_schema import NodeParameterValue, LiteralValue, ReferencePath, TriggerReferenceValue, \
    SubFlowReferenceValue, NodeReferenceValue, SubFlowValue, InlineReferenceValue


def map_to_value_schema(grpc_value: flow_pb2.NodeValue) -> NodeParameterValue:
    if grpc_value.HasField('literal_value'):
        literal = map_to_literal_value_schema(grpc_value.literal_value.value)
        if grpc_value.literal_value.references:
            literal.references = [
                InlineReferenceValue(
                    signature=ref.signature,
                    value=map_to_value_schema(ref.value),
                )
                for ref in grpc_value.literal_value.references
            ]
        return literal
    elif grpc_value.HasField('reference_value'):
        ref_paths = None
        if len(grpc_value.reference_value.paths) > 0:
            ref_paths = [ReferencePath(path=p.path) for p in grpc_value.reference_value.paths]

        if grpc_value.reference_value.HasField("flow_input"):
            return TriggerReferenceValue(referencePath=ref_paths)
        elif grpc_value.reference_value.HasField("input_type"):
            return SubFlowReferenceValue(
                nodeFunctionId=grpc_value.reference_value.input_type.node_id,
                inputIndex=grpc_value.reference_value.input_type.input_index,
                parameterIndex=grpc_value.reference_value.input_type.parameter_index,
                referencePath=ref_paths
            )
        elif grpc_value.reference_value.HasField("node_id"):
            return NodeReferenceValue(
                nodeFunctionId=grpc_value.reference_value.node_id,
                referencePath=ref_paths
            )
    elif grpc_value.HasField('sub_flow') and grpc_value.sub_flow.HasField("starting_node_id"):
        return SubFlowValue(
            startingNodeId=grpc_value.sub_flow.starting_node_id
        )

    return LiteralValue(value=None)


def map_to_grpc_value(value: NodeParameterValue) -> flow_pb2.NodeValue:
    grpc_val = flow_pb2.NodeValue()
    if hasattr(value, 'value'):
        grpc_val.literal_value.value.CopyFrom(map_to_grpc_literal_value(value))
        for ref in (getattr(value, 'references', None) or []):
            grpc_ref = flow_pb2.InlineReferenceValue()
            grpc_ref.signature = ref.signature
            grpc_ref.value.CopyFrom(map_to_grpc_value(ref.value))
            grpc_val.literal_value.references.append(grpc_ref)
    elif hasattr(value, 'starting_node_id') and value.starting_node_id is not None:
        grpc_sub_flow = flow_pb2.SubFlow()
        grpc_sub_flow.starting_node_id = value.starting_node_id
        grpc_val.sub_flow.CopyFrom(grpc_sub_flow)
    elif hasattr(value, 'node_id') and hasattr(value, 'input_index') and hasattr(value, 'parameter_index'):
        if value.node_id is not None:
            grpc_val.reference_value.input_type.node_id = value.node_id
        if value.parameter_index is not None:
            grpc_val.reference_value.input_type.parameter_index = value.parameter_index
        if value.input_index is not None:
            grpc_val.reference_value.input_type.input_index = value.input_index
    elif hasattr(value, 'node_id') and value.node_id is not None:
        grpc_val.reference_value.node_id = value.node_id
    elif hasattr(value, 'reference_path'):
        grpc_val.reference_value.flow_input.CopyFrom(flow_pb2.FlowInput())

    if hasattr(value, 'reference_path') and value.reference_path:
        for p in value.reference_path:
            grpc_path = flow_pb2.ReferencePath()
            if p.path:
                grpc_path.path = p.path
            grpc_val.reference_value.paths.append(grpc_path)

    return grpc_val
