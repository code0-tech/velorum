import tucana.generated.shared.struct_pb2 as shared_struct_pb2
import tucana.generated.shared.flow_pb2 as flow_pb2

def map_pydantic_value_to_grpc(py_value):
    grpc_val = shared_struct_pb2.Value()

    if py_value is None:
        grpc_val.null_value = shared_struct_pb2.NULL_VALUE
    elif isinstance(py_value, bool):
        grpc_val.bool_value = py_value
    elif isinstance(py_value, int):
        # Erst auf das Feld zugreifen, dann die Unter-Zahl setzen
        grpc_val.number_value.integer = py_value
    elif isinstance(py_value, float):
        # Erst auf das Feld zugreifen, dann das Unter-Float setzen
        grpc_val.number_value.float = py_value
    elif isinstance(py_value, str):
        grpc_val.string_value = py_value
    elif isinstance(py_value, list):
        list_val = shared_struct_pb2.ListValue()
        for v in py_value:
            list_val.values.append(map_pydantic_value_to_grpc(v))
        grpc_val.list_value.CopyFrom(list_val)
    elif isinstance(py_value, dict):
        struct_val = shared_struct_pb2.Struct()
        for k, v in py_value.items():
            struct_val.fields[k].CopyFrom(map_pydantic_value_to_grpc(v))
        grpc_val.struct_value.CopyFrom(struct_val)

    return grpc_val

def map_node_value(py_param) -> flow_pb2.NodeValue:
    grpc_node_value = flow_pb2.NodeValue()

    if hasattr(py_param, 'value') and not hasattr(py_param, 'node_id') and not hasattr(py_param, 'starting_node_id'):
        grpc_node_value.literal_value.CopyFrom(map_pydantic_value_to_grpc(py_param.value))

    elif hasattr(py_param, 'starting_node_id'):
        grpc_sub_flow = flow_pb2.SubFlow()
        grpc_sub_flow.starting_node_id = py_param.starting_node_id
        grpc_node_value.sub_flow.CopyFrom(grpc_sub_flow)

    elif hasattr(py_param, 'node_id') and py_param.node_id is not None:
        grpc_ref = flow_pb2.ReferenceValue()

        if hasattr(py_param, 'input_index') and py_param.input_index is not None:
            grpc_ref.input_type.node_id = py_param.node_id
            grpc_ref.input_type.parameter_index = py_param.parameter_index or 0
            grpc_ref.input_type.input_index = py_param.input_index
        else:
            grpc_ref.node_id = py_param.node_id

        if py_param.reference_path:
            for p in py_param.reference_path:
                grpc_path = flow_pb2.ReferencePath()
                if p.path:
                    grpc_path.path = p.path
                grpc_ref.paths.append(grpc_path)

        grpc_node_value.reference_value.CopyFrom(grpc_ref)

    return grpc_node_value

def map_pydantic_flow_to_grpc(pydantic_flow) -> flow_pb2.GenerationFlow:
    grpc_flow = flow_pb2.GenerationFlow()
    grpc_flow.name = pydantic_flow.name
    grpc_flow.type = pydantic_flow.type
    grpc_flow.starting_node_id = str(pydantic_flow.starting_node_id)

    if pydantic_flow.nodes:
        for py_node in pydantic_flow.nodes:
            grpc_node = flow_pb2.NodeFunction()
            grpc_node.runtime_function_id = py_node.function_identifier

            if py_node.next_node_id is not None:
                grpc_node.next_node_id = py_node.next_node_id

            if py_node.parameters:
                for idx, py_param in enumerate(py_node.parameters):
                    grpc_param = flow_pb2.NodeParameter()
                    grpc_param.runtime_parameter_id = f"param_{idx}"
                    grpc_param.value.CopyFrom(map_node_value(py_param))
                    grpc_node.parameters.append(grpc_param)

            grpc_flow.node_functions.append(grpc_node)

    if pydantic_flow.settings:
        for idx, py_setting in enumerate(pydantic_flow.settings):
            grpc_setting = flow_pb2.FlowSetting()
            grpc_setting.flow_setting_id = f"setting_{idx}"
            grpc_setting.value.CopyFrom(map_pydantic_value_to_grpc(py_setting.value))
            grpc_flow.settings.append(grpc_setting)

    return grpc_flow