from typing import List, Any

from model2vec import StaticModel
from qdrant_client import QdrantClient

from src.schema.data_type_schema import DataType
from src.schema.function_schema import FunctionDefinition
from src.store.ts_resolver import resolve_ts_signature
from src.store.vector_store import Store


class FunctionStore(Store):
    def __init__(self, memory_client: QdrantClient, vector_model: StaticModel):
        super().__init__(
            memory_client,
            vector_model,
            'functions',
            "identifier",
            "project_id"
        )

    def insert_from_definition(self, group_identifier: str, payload: FunctionDefinition,
                               data_types: List[DataType]) -> None:
        datatypes = [
            f"type {d.identifier}{'<' + ','.join(d.generic_keys) + '>' if d.generic_keys else ''} = {d.type}"
            for d in data_types
        ]

        payload.signature = resolve_ts_signature(payload.signature, datatypes)

        self.insert(group_identifier, payload)

    def validate(self, payload: Any) -> FunctionDefinition:
        return FunctionDefinition.model_validate(payload)

    def search(self, group_identifier: str, prompt: str, limit=5) -> List[FunctionDefinition]:
        return super().search(group_identifier, prompt, limit)

    def find(self, group_identifier: str, identifier: str) -> FunctionDefinition | None:
        return super().find(group_identifier, identifier)

    def find_all(self, group_identifier: str, identifiers: List[str]) -> List[FunctionDefinition]:
        return super().find_all(group_identifier, identifiers)

    def get_all(self, group_identifier: str) -> List[FunctionDefinition]:
        return super().get_all(group_identifier)

    def combine(
            self,
            first_list: List[FunctionDefinition],
            second_list: List[FunctionDefinition]
    ) -> List[FunctionDefinition]:
        return super().combine(first_list, second_list)
