from typing import Optional, Any, List

from pydantic import BaseModel, Field, ConfigDict


class FlowTypeSetting(BaseModel):
    identifier: Optional[str] = Field(None)
    default_value: Optional[Any] = Field(None, alias="defaultValue")
    # Whether a defaultValue was provided at all. Needed because a default value
    # may legitimately be null, which is indistinguishable from "no default" by
    # inspecting default_value alone.
    has_default_value: bool = Field(False, alias="hasDefaultValue")
    hidden: bool = Field(False)
    optional: bool = Field(False)
    descriptions: Optional[str] = Field(None)
    names: Optional[str] = Field(None)

    model_config = ConfigDict(populate_by_name=True)


class FlowType(BaseModel):
    aliases: Optional[str] = Field(None)
    descriptions: Optional[str] = Field(None)
    flow_type_settings: Optional[List[FlowTypeSetting]] = Field(None, alias="flowTypeSettings")
    identifier: Optional[str] = Field(None)
    names: Optional[str] = Field(None)
    signature: Optional[str] = Field(None)

    model_config = ConfigDict(populate_by_name=True)
