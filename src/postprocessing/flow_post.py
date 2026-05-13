from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set

from src.schema.flow_schema import (
    Flow,
    LiteralValue,
    NodeFunction,
    NodeParameterValue,
    NodeReferenceValue,
    SubFlowReferenceValue,
    SubFlowValue,
)
from src.schema.flow_type_schema import FlowType
from src.schema.function_schema import FunctionDefinition


def _expected_parameter_count(function_definition: FunctionDefinition) -> int:
    return len(function_definition.parameter_definitions or [])


def _find_closest_function_definition(
    function_identifier: Optional[str],
    provided_parameter_count: int,
    function_definitions: List[FunctionDefinition],
) -> Optional[FunctionDefinition]:
    valid_definitions = [fd for fd in function_definitions if fd.identifier]
    if not valid_definitions:
        return None

    same_arity = [fd for fd in valid_definitions if _expected_parameter_count(fd) == provided_parameter_count]
    candidates = same_arity if same_arity else valid_definitions

    source_identifier = function_identifier or ""

    def score(fd: FunctionDefinition) -> float:
        identifier = fd.identifier or ""
        similarity = SequenceMatcher(None, source_identifier, identifier).ratio()
        arity_penalty = abs(_expected_parameter_count(fd) - provided_parameter_count)
        return similarity + (1.0 / (1 + arity_penalty))

    return max(candidates, key=score)


def _normalize_parameters(parameters: Optional[List[NodeParameterValue]], expected_count: int) -> List[NodeParameterValue]:
    current_parameters: List[NodeParameterValue] = list(parameters or [])
    if len(current_parameters) > expected_count:
        return current_parameters[:expected_count]

    if len(current_parameters) < expected_count:
        missing = expected_count - len(current_parameters)
        current_parameters.extend(LiteralValue(value=None) for _ in range(missing))

    return current_parameters


def _extract_referenced_node_ids(parameter: NodeParameterValue) -> Set[int]:
    referenced_ids: Set[int] = set()

    if isinstance(parameter, SubFlowValue):
        referenced_ids.add(parameter.starting_node_id)
    elif isinstance(parameter, (NodeReferenceValue, SubFlowReferenceValue)) and parameter.node_id is not None:
        referenced_ids.add(parameter.node_id)

    return referenced_ids


def _collect_reachable_node_ids(flow: Flow) -> Set[int]:
    nodes_by_id: Dict[int, NodeFunction] = {node.id: node for node in flow.nodes}
    if flow.starting_node_id not in nodes_by_id:
        return set()

    reachable_node_ids: Set[int] = set()
    stack: List[int] = [flow.starting_node_id]

    while stack:
        node_id = stack.pop()
        if node_id in reachable_node_ids:
            continue

        node = nodes_by_id.get(node_id)
        if node is None:
            continue

        reachable_node_ids.add(node_id)

        if node.next_node_id is not None and node.next_node_id in nodes_by_id:
            stack.append(node.next_node_id)

        for parameter in node.parameters or []:
            stack.extend(
                referenced_id
                for referenced_id in _extract_referenced_node_ids(parameter)
                if referenced_id in nodes_by_id
            )

    return reachable_node_ids


def flow_postprocessing(flow: Flow, flow_types: List[FlowType], functions: List[FunctionDefinition]) -> Flow:
    _ = flow_types

    reachable_node_ids = _collect_reachable_node_ids(flow)

    function_by_identifier: Dict[str, FunctionDefinition] = {
        fd.identifier: fd
        for fd in functions
        if fd.identifier
    }

    processed_nodes: List[NodeFunction] = []

    for node in flow.nodes:
        if node.id not in reachable_node_ids:
            continue

        function_definition = function_by_identifier.get(node.function_identifier)
        if function_definition is None:
            function_definition = _find_closest_function_definition(
                function_identifier=node.function_identifier,
                provided_parameter_count=len(node.parameters or []),
                function_definitions=functions,
            )

        new_identifier = node.function_identifier
        expected_count = len(node.parameters or [])

        if function_definition is not None:
            new_identifier = function_definition.identifier or node.function_identifier
            expected_count = _expected_parameter_count(function_definition)

        normalized_parameters = _normalize_parameters(node.parameters, expected_count)
        next_node_id = node.next_node_id if node.next_node_id in reachable_node_ids else None

        processed_nodes.append(
            node.model_copy(
                update={
                    "function_identifier": new_identifier,
                    "parameters": normalized_parameters,
                    "next_node_id": next_node_id,
                }
            )
        )

    if flow.starting_node_id not in reachable_node_ids and processed_nodes:
        fallback_starting_node_id = processed_nodes[0].id
    else:
        fallback_starting_node_id = flow.starting_node_id

    return flow.model_copy(
        update={
            "nodes": processed_nodes,
            "starting_node_id": fallback_starting_node_id,
        }
    )
