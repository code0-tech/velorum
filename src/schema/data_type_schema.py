from typing import List

from pydantic import BaseModel, Field


class DataType(BaseModel):
    identifier: str
    type: str
    generic_keys: List[str] = Field(alias="genericKeys", default=None)
