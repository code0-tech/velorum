from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Model(BaseModel):
    identifier: str
    name: str
    capabilities: List[str] = Field(default=[])
    provider: str
    api: Optional[str] = Field(default=None)
    auth: str
    token_cost: Optional[float] = Field(default=1.0)

    @field_validator("token_cost")
    @classmethod
    def token_cost_min_one(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 1:
            raise ValueError("token_cost must be >= 1")
        return v
