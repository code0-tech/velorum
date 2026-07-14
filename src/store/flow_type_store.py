from typing import List, Any

from model2vec import StaticModel
from qdrant_client import QdrantClient

from src.schema.data_type_schema import DataType
from src.schema.flow_type_schema import FlowType
from src.store.ts_resolver import resolve_ts_signature
from src.store.vector_store import Store


class FlowTypeStore(Store):
    def __init__(self, memory_client: QdrantClient, vector_model: StaticModel):
        super().__init__(
            memory_client,
            vector_model,
            'flow_types',
            "identifier",
            "project_id"
        )

    def insert_from_definition(self, group_identifier: str, payload: FlowType,
                               data_types: List[DataType]) -> None:
        datatypes = [
            f"type {d.identifier}{'<' + ','.join(d.generic_keys) + '>' if d.generic_keys else ''} = {d.type}"
            for d in data_types
        ]

        payload.signature = resolve_ts_signature(payload.signature, datatypes)

        super().insert(group_identifier, payload)

    def validate(self, payload: Any) -> FlowType:
        return FlowType.model_validate(payload)

    def search(self, group_identifier: str, prompt: str, limit=5) -> List[FlowType]:
        return super().search(group_identifier, prompt, limit)

    def find(self, group_identifier: str, identifier: str) -> FlowType | None:
        return super().find(group_identifier, identifier)

    def find_all(self, group_identifier: str, identifiers: List[str]) -> List[FlowType]:
        return super().find_all(group_identifier, identifiers)

    def get_all(self, group_identifier: str) -> List[FlowType]:
        return super().get_all(group_identifier)

    def combine(
            self,
            first_list: List[FlowType],
            second_list: List[FlowType]
    ) -> List[FlowType]:
        return super().combine(first_list, second_list)
