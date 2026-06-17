import json
from pathlib import Path
from typing import Any, List

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from src.logger import get_logger
from src.schema.few_shot_schema import FewShot
from src.store.vector_store import Store

log = get_logger("few_shots_store")


class FewShotsStore(Store):
    def __init__(self, memory_client: QdrantClient, vector_model: SentenceTransformer):
        super().__init__(
            memory_client,
            vector_model,
            'few_shots',
            "identifier",
            "identifier"
        )
        self._load_models_from_json()

    def _load_models_from_json(self):
        filepath = Path(__file__).parent.parent.parent / "few_shots.configuration.json"

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        if not isinstance(raw_data, list):
            raw_data = [raw_data]

        for item in raw_data:
            shot = FewShot(**item)
            self.insert("global", shot)
            prompt_preview = shot.prompt[:50].replace("\n", " ") + ("…" if len(shot.prompt) > 50 else "")
            log.debug(f"Loaded few-shot: \"{prompt_preview}\" ({len(shot.flow.nodes)} nodes)")

        log.success(f"FewShotsStore ready — {len(raw_data)} example(s) loaded")  # type: ignore[attr-defined]

    def insert(self, group_identifier: str, payload: FewShot) -> None:
        super().insert(group_identifier, payload)

    def validate(self, payload: Any) -> FewShot:
        return FewShot.model_validate(payload)

    def search(self, group_identifier: str, prompt: str, limit=5) -> List[FewShot]:
        return super().search(prompt, group_identifier, limit)

    def find(self, group_identifier: str, identifier: str) -> FewShot | None:
        return super().find(group_identifier, identifier)

    def find_all(self, group_identifier: str, identifiers: List[str]) -> List[FewShot]:
        return super().find_all(group_identifier, identifiers)

    def get_all(self, group_identifier: str) -> List[FewShot]:
        return super().get_all(group_identifier)

    def combine(
            self,
            first_list: List[FewShot],
            second_list: List[FewShot]
    ) -> List[FewShot]:
        return super().combine(first_list, second_list)
