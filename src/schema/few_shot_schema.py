from pydantic import BaseModel

from src.schema.flow_schema import Flow


class FewShot(BaseModel):
    prompt: str
    flow: Flow
