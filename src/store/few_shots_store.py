import json
from pathlib import Path
from typing import Any, List

from model2vec import StaticModel
from qdrant_client import QdrantClient

from src.logger import get_logger
from src.schema.few_shot_schema import FewShot
from src.store.vector_store import Store

log = get_logger("few_shots_store")


class FewShotsStore(Store):
    def __init__(self, memory_client: QdrantClient, vector_model: StaticModel):
        super().__init__(
            memory_client,
            vector_model,
            'few_shots',
            "identifier",
            "identifier",
            time_to_live=None,
        )
        self._load_models_from_json()

    def _load_models_from_json(self):
        project_root = Path(__file__).parent.parent.parent
        internal_path = project_root / "few_shots.configuration.json"
        external_path = project_root / "few_shots_external.configuration.json"

        raw_data: List[dict] = []
        raw_data.extend(self._read_few_shots_file(internal_path, required=True))
        raw_data.extend(self._read_few_shots_file(external_path, required=False))

        for item in raw_data:
            shot = FewShot(**item)
            self.insert("global", shot)
            prompt_preview = shot.prompt[:50].replace("\n", " ") + ("…" if len(shot.prompt) > 50 else "")
            log.debug(f"Loaded few-shot: \"{prompt_preview}\" ({len(shot.flow.nodes)} nodes)")

        log.success(f"FewShotsStore ready — {len(raw_data)} example(s) loaded")  # type: ignore[attr-defined]

    @staticmethod
    def _read_few_shots_file(filepath: Path, required: bool) -> List[dict]:
        if not filepath.exists():
            if required:
                raise FileNotFoundError(f"File not found: {filepath}")
            log.info(f"No external few-shots file at {filepath} — skipping")
            return []

        if not filepath.is_file():
            if required:
                raise IsADirectoryError(f"Expected a file but found a directory: {filepath}")
            log.warning(f"External few-shots path {filepath} is not a file — skipping")
            return []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if not content:
                if required:
                    raise ValueError(f"File is empty: {filepath}")
                log.info(f"External few-shots file {filepath} is empty — skipping")
                return []
            data = json.loads(content)
        except json.JSONDecodeError as e:
            if required:
                raise
            log.warning(f"External few-shots file {filepath} is not valid JSON ({e}) — skipping")
            return []

        if not isinstance(data, list):
            data = [data]
        return data

    def insert(self, group_identifier: str, payload: FewShot) -> None:
        super().insert(group_identifier, payload)

    def validate(self, payload: Any) -> FewShot:
        return FewShot.model_validate(payload)

    def search(self, group_identifier: str, prompt: str, limit=5) -> List[FewShot]:
        return super().search(group_identifier, prompt, limit)

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
