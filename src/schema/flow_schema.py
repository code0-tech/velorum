from typing import Union, Optional, List, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReferencePath(BaseModel):
    path: str = None
    model_config = ConfigDict(populate_by_name=True)


class TriggerReferenceValue(BaseModel):
    reference_path: Optional[List[ReferencePath]] = Field(None, alias="referencePath")
    model_config = ConfigDict(populate_by_name=True)


class SubFlowReferenceValue(BaseModel):
    node_id: Optional[int] = Field(None, alias="nodeFunctionId")
    input_index: Optional[int] = Field(None, alias="inputIndex")
    parameter_index: Optional[int] = Field(None, alias="parameterIndex")
    reference_path: Optional[List[ReferencePath]] = Field(None, alias="referencePath")
    model_config = ConfigDict(populate_by_name=True)


class NodeReferenceValue(BaseModel):
    node_id: Optional[int] = Field(None, alias="nodeFunctionId")
    reference_path: Optional[List[ReferencePath]] = Field(None, alias="referencePath")
    model_config = ConfigDict(populate_by_name=True)


class SubFlowValue(BaseModel):
    starting_node_id: int = Field(alias="startingNodeId")
    model_config = ConfigDict(populate_by_name=True)


class InlineReferenceValue(BaseModel):
    # The signature is arbitrary free text; it is referenced inside `value`
    # via the exact placeholder ``${<signature>}``.
    signature: str
    value: "NodeParameterValue"
    model_config = ConfigDict(populate_by_name=True)


class LiteralValue(BaseModel):
    # `value` behaves like a template: any occurrence of ``${<signature>}`` inside
    # a (possibly nested) string — standalone as a whole value, embedded in a
    # string, as an object field value or as a list entry — is substituted with
    # the resolved value of the matching reference. velorum only carries the
    # template together with its references; the resolution happens downstream.
    value: Any
    references: Optional[List[InlineReferenceValue]] = None
    model_config = ConfigDict(populate_by_name=True, extra='forbid')


NodeParameterValue = Union[LiteralValue, SubFlowValue, NodeReferenceValue, SubFlowReferenceValue, TriggerReferenceValue]

InlineReferenceValue.model_rebuild()


class NodeFunction(BaseModel):
    function_identifier: str = Field(alias="functionIdentifier")
    id: int
    next_node_id: Optional[int] = Field(None, alias="nextNodeId")
    parameters: Optional[List[NodeParameterValue]] = Field(None)
    model_config = ConfigDict(populate_by_name=True)


class FlowSetting(BaseModel):
    value: Any = Field(None)
    model_config = ConfigDict(populate_by_name=True)


class Flow(BaseModel):
    name: str
    nodes: List[NodeFunction]
    settings: Optional[List[FlowSetting]] = None
    starting_node_id: Optional[int] = Field(None, alias="startingNodeId")
    type: str

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("starting_node_id", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value):
        if isinstance(value, str) and value.strip() == "":
            return None
        return value
