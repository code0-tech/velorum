from typing import Union, Literal, Optional, List, Any

from pydantic import BaseModel, ConfigDict, Field


class ReferencePath(BaseModel):
    path: str = None
    model_config = ConfigDict(populate_by_name=True)


class ReferenceValue(BaseModel):
    typename: Literal["LiteralValue"] = Field("ReferenceValue", alias="__typename")
    input_index: Optional[int] = Field(None, alias="inputIndex")
    node_function_id: Optional[int] = Field(None, alias="nodeFunctionId")
    parameter_index: Optional[int] = Field(None, alias="parameterIndex")
    reference_path: Optional[List[ReferencePath]] = Field(None, alias="referencePath")
    model_config = ConfigDict(populate_by_name=True)


class NodeFunctionIdWrapper(BaseModel):
    typename: Literal["LiteralValue"] = Field("NodeFunctionIdWrapper", alias="__typename")
    id: int
    model_config = ConfigDict(populate_by_name=True)


class LiteralValue(BaseModel):
    typename: Literal["LiteralValue"] = Field("LiteralValue", alias="__typename")
    value: Any
    model_config = ConfigDict(populate_by_name=True)


NodeParameterValue = Union[LiteralValue, NodeFunctionIdWrapper, ReferenceValue]


class NodeParameter(BaseModel):
    value: NodeParameterValue
    model_config = ConfigDict(populate_by_name=True)


class NodeFunction(BaseModel):
    function_definition: str = Field(alias="functionDefinition")
    id: int
    next_node_id: Optional[int] = Field(None, alias="nextNodeId")
    parameters: Optional[List[NodeParameter]] = Field(None)
    model_config = ConfigDict(populate_by_name=True)


class FlowSetting(BaseModel):
    value: Any
    model_config = ConfigDict(populate_by_name=True)


class Flow(BaseModel):
    name: str
    nodes: List[NodeFunction]
    settings: Optional[List[FlowSetting]] = None
    starting_node_id: int = Field(alias="startingNodeId")
    type: str

    model_config = ConfigDict(populate_by_name=True)
