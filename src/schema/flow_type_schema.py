from typing import Optional, Any, List

from pydantic import BaseModel, Field, ConfigDict


class FlowTypeSetting(BaseModel):
    default_value: Optional[Any] = Field(None, alias="defaultValue")
    descriptions: Optional[str] = Field(None)
    names: Optional[str] = Field(None)

    class Config:
        populate_by_name = True


class FlowType(BaseModel):
    aliases: Optional[str] = Field(None)
    descriptions: Optional[str] = Field(None)
    flow_type_settings: Optional[List[FlowTypeSetting]] = Field(None, alias="flowTypeSettings")
    identifier: Optional[str] = Field(None)
    names: Optional[str] = Field(None)
    signature: Optional[str] = Field(None)

    class Config:
        populate_by_name = True
