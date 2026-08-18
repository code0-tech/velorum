from typing import Optional, Any, List

from pydantic import BaseModel, ConfigDict, Field


class ParameterDefinition(BaseModel):
    default_value: Optional[Any] = Field(None, alias="defaultValue")
    descriptions: Optional[str] = Field(None)
    names: Optional[str] = Field(None)

    model_config = ConfigDict(populate_by_name=True)


class FunctionDefinition(BaseModel):
    aliases: Optional[str] = Field(None)
    descriptions: Optional[str] = Field(None)
    identifier: Optional[str] = Field(None)
    names: Optional[str] = Field(None)
    parameter_definitions: Optional[List[ParameterDefinition]] = Field(None, alias="parameterDefinitions")
    signature: Optional[str] = Field(None)

    model_config = ConfigDict(populate_by_name=True)
