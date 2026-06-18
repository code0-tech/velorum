from typing import List, Optional

from pydantic import BaseModel, Field


class Model(BaseModel):
    identifier: str
    name: str
    capabilities: List[str] = Field(default=[])
    provider: str
    api: Optional[str] = Field(default=None)
    auth: str
    token_cost: Optional[float] = Field(default=1.0)
