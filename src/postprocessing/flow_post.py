from difflib import SequenceMatcher
from typing import Any, Dict, Iterator, List, Optional, Set

from src.logger import get_logger
from src.schema.flow_schema import (
    Flow,
    FlowSetting,
    InlineReferenceValue,
    LiteralValue,
    NodeFunction,
    NodeParameterValue,
    NodeReferenceValue,
    SubFlowReferenceValue,
    SubFlowValue,
)
from src.schema.flow_type_schema import FlowType, FlowTypeSetting
from src.schema.function_schema import FunctionDefinition

log = get_logger("flow_post")


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
    elif isinstance(parameter, LiteralValue) and parameter.references:
        for reference in parameter.references:
            referenced_ids |= _extract_referenced_node_ids(reference.value)

    return referenced_ids


def _iter_strings(value: Any) -> Iterator[str]:
    """Yield every string in a (possibly nested) literal value tree."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)


def _clean_inline_references(parameter: NodeParameterValue) -> NodeParameterValue:
    """Drop declared inline references that are never used via ``${signature}``.

    The signature is arbitrary free text, so matching is done by literal
    substring (``${<signature>}``) against every string in the value tree —
    standalone, embedded, as an object value or as a list entry. Placeholders
    without a matching declared reference are logged but left untouched, since a
    free-text signature can itself contain ``}`` and cannot be repaired safely.
    """
    if not isinstance(parameter, LiteralValue) or not parameter.references:
        return parameter

    strings = list(_iter_strings(parameter.value))

    used: List[InlineReferenceValue] = []
    for reference in parameter.references:
        placeholder = "${" + reference.signature + "}"
        if any(placeholder in string for string in strings):
            used.append(reference.model_copy(update={"value": _clean_inline_references(reference.value)}))
        else:
            log.debug(f"Dropping unused inline reference '{reference.signature}'")

    declared_placeholders = {"${" + reference.signature + "}" for reference in parameter.references}
    for string in strings:
        index = string.find("${")
        while index != -1:
            if not any(string.startswith(placeholder, index) for placeholder in declared_placeholders):
                log.warning(f"Inline placeholder without matching reference near: {string[index:index + 40]!r}")
            index = string.find("${", index + 2)

    return parameter.model_copy(update={"references": used or None})


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


def _default_for(setting: FlowTypeSetting) -> object:
    """Fallback value for a setting: its default value if one was provided, else None."""
    return setting.default_value if setting.has_default_value else None


def _reconcile_settings(
    flow: Flow,
    flow_types: List[FlowType],
    original_flow: Optional[Flow],
) -> List[FlowSetting]:
    """Align the flow's settings with the definition of its flow type.

    Guarantees the resulting settings list has exactly one entry per flow type
    setting, in the same order. Hidden settings are never taken from the model's
    output — the model may generate a value, but it must be overwritten:

    * prompt -> Flow (no ``original_flow``): a hidden setting becomes its default
      value if one is defined, otherwise null.
    * Flow -> Flow (``original_flow`` given): a hidden setting keeps the value the
      incoming flow already had (even if that value is null); if the incoming flow
      is missing that setting, it falls back to the default value or null.

    Visible settings keep the generated value, falling back to the incoming flow's
    value and finally to the default when the model omitted them.
    """
    flow_type = next(
        (ft for ft in flow_types if ft.identifier and ft.identifier == flow.type),
        None,
    )
    if flow_type is None or flow_type.flow_type_settings is None:
        log.debug(f"No flow type '{flow.type}' with settings found — leaving settings untouched")
        return list(flow.settings or [])

    setting_definitions = flow_type.flow_type_settings
    generated = list(flow.settings or [])
    original = list(original_flow.settings) if original_flow and original_flow.settings else []

    reconciled: List[FlowSetting] = []
    for index, definition in enumerate(setting_definitions):
        has_generated = index < len(generated)
        has_original = index < len(original)

        if definition.hidden:
            if original_flow is not None:
                value = original[index].value if has_original else _default_for(definition)
            else:
                value = _default_for(definition)
        else:
            if has_generated:
                value = generated[index].value
            elif has_original:
                value = original[index].value
            else:
                value = _default_for(definition)

        reconciled.append(FlowSetting(value=value))

    if len(generated) != len(setting_definitions):
        log.debug(
            f"Flow type '{flow.type}': setting count {len(generated)} → {len(setting_definitions)}"
        )

    return reconciled


def flow_postprocessing(
    flow: Flow,
    flow_types: List[FlowType],
    functions: List[FunctionDefinition],
    original_flow: Optional[Flow] = None,
) -> Flow:
    log.debug(f"Postprocessing '{flow.name}' — {len(flow.nodes)} nodes")

    reconciled_settings = _reconcile_settings(flow, flow_types, original_flow)

    reachable_node_ids = _collect_reachable_node_ids(flow)

    pruned = [n.id for n in flow.nodes if n.id not in reachable_node_ids]
    if pruned:
        log.debug(f"Pruning {len(pruned)} unreachable node(s): {pruned}")

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

        if new_identifier != node.function_identifier:
            log.warning(
                f"Node {node.id}: unknown function '{node.function_identifier}' "
                f"→ corrected to '{new_identifier}'"
            )

        actual_count = len(node.parameters or [])
        if actual_count != expected_count:
            log.debug(
                f"Node {node.id} ({new_identifier}): "
                f"parameter count {actual_count} → {expected_count}"
            )

        normalized_parameters = [
            _clean_inline_references(parameter)
            for parameter in _normalize_parameters(node.parameters, expected_count)
        ]
        next_node_id = node.next_node_id if node.next_node_id in reachable_node_ids else None

        if node.next_node_id is not None and next_node_id is None:
            log.debug(f"Node {node.id}: next_node_id {node.next_node_id} is unreachable, cleared")

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
        log.warning(
            f"starting_node_id {flow.starting_node_id} is unreachable, "
            f"falling back to node {fallback_starting_node_id}"
        )
    else:
        fallback_starting_node_id = flow.starting_node_id

    log.debug(f"Postprocessing done — {len(processed_nodes)} nodes retained")

    return flow.model_copy(
        update={
            "nodes": processed_nodes,
            "starting_node_id": fallback_starting_node_id,
            "settings": reconciled_settings,
        }
    )
