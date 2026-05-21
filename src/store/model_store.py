import json
from pathlib import Path
from typing import List

from src.schema.model_schema import Model
from src.store.data_store import Store


class ModelStore(Store):
    def __init__(self):
        super().__init__("identifier")
        self._load_models_from_json()

    def _load_models_from_json(self):
        filepath = Path(__file__).parent.parent.parent / "models.configuration.json"

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        if not isinstance(raw_data, list):
            raw_data = [raw_data]

        for item in raw_data:
            self.insert(Model(
                **item
            ))

    def insert(self, data: Model):
        super().insert(data)

    def find(self, identifier: str) -> Model | None:
        return super().find(identifier)

    def find_all(self, identifiers: List[str]) -> List[Model]:
        return super().find_all(identifiers)

    def get_all(self) -> List[Model] | None:
        return super().get_all()
