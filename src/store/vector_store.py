import time
from abc import ABC, abstractmethod
from typing import List, Any

from apscheduler.schedulers.background import BackgroundScheduler
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, MatchAny, Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer


class Store(ABC):
    def __init__(
            self,
            client: QdrantClient,
            model: SentenceTransformer,
            collection_name: str,
            payload_identifier: str,
            group_identifier: str,
            time_to_live: int = 60 * 5

    ):
        self.client = client
        self.model = model
        self.collection_name = collection_name
        self.payload_identifier = payload_identifier
        self.group_identifier = group_identifier
        self.time_to_live = time_to_live
        self._id_counter = 0
        self._scheduler = None
        self._setup_collection()
        self._start_garbage_collector()

    def _setup_collection(self):
        if not self.client.collection_exists(collection_name=self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=384,
                    distance=Distance.COSINE
                ),
            )

    def _start_garbage_collector(self):
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(
            self._garbage_collect_all,
            'interval',
            minutes=1,  # Jede Minute
            id='garbage_collector'
        )
        self._scheduler.start()

    def _garbage_collect_all(self):
        try:
            all_points = self.client.scroll(
                collection_name=self.collection_name,
                limit=1000,
                with_payload=True
            )[0]

            now = time.time()
            points_to_delete = []

            for point in all_points:
                if point.payload and "created_at" in point.payload:
                    age = now - point.payload["created_at"]
                    if age > self.time_to_live:
                        points_to_delete.append(point.id)

            if points_to_delete:
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=points_to_delete
                )
                print(f"[GC] {len(points_to_delete)} abgelaufene Einträge gelöscht")
        except Exception as e:
            print(f"[GC Error] {e}")

    def _reset_time_to_live(self, group_identifier: str):
        items = self.get_all(group_identifier)
        current_time = time.time()

        for item in items:
            item_dict = item.model_dump() if hasattr(item, 'model_dump') else item
            item_dict["created_at"] = current_time
            self.insert(group_identifier, item_dict)

    @abstractmethod
    def validate(self, payload: Any) -> Any:
        pass

    def insert(self, group_identifier: str, payload: Any) -> None:

        if not isinstance(payload, dict):
            payload = payload.model_dump() if hasattr(payload, 'model_dump') else dict(payload)

        if "created_at" not in payload:
            payload["created_at"] = time.time()

        payload_str = str(payload)
        vector = self.model.encode(payload_str).tolist()

        payload[self.group_identifier] = group_identifier

        point = PointStruct(
            id=self._id_counter,
            vector=vector,
            payload=payload
        )

        self._id_counter += 1

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )

    def search(self, group_identifier: str, prompt: str, limit=5) -> List[Any]:
        self._reset_time_to_live(group_identifier)

        query_vector = self.model.encode(prompt).tolist()

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key=self.group_identifier,
                        match=MatchValue(value=group_identifier)
                    )
                ]
            ),
            limit=limit,
            with_payload=True
        )

        return [
            self.validate(hit.payload)
            for hit in response.points
        ]

    def find(self, group_identifier: str, identifier: str) -> Any | None:
        self._reset_time_to_live(group_identifier)

        response = self.client.query_points(
            collection_name=self.collection_name,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key=self.payload_identifier,
                        match=MatchValue(value=identifier)
                    ),
                    FieldCondition(
                        key=self.group_identifier,
                        match=MatchValue(value=group_identifier)
                    )
                ]
            ),
            limit=1,
            with_payload=True
        )

        if response.points:
            return self.validate(response.points[0].payload)

        return None

    def find_all(self, group_identifier: str, identifiers: List[str]) -> List[Any]:
        self._reset_time_to_live(group_identifier)

        if not identifiers:
            return []

        response = self.client.query_points(
            collection_name=self.collection_name,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key=self.payload_identifier,
                        match=MatchAny(any=identifiers)
                    ),
                    FieldCondition(
                        key=self.group_identifier,
                        match=MatchValue(value=group_identifier)
                    )
                ]
            ),
            limit=len(identifiers),
            with_payload=True
        )

        return [
            self.validate(hit.payload)
            for hit in response.points
        ]

    def get_all(self, group_identifier: str) -> List[Any]:
        functions: List[Any] = []
        offset = None

        while True:
            points, next_page_offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=256,
                with_payload=True,
                offset=offset,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key=self.group_identifier,
                            match=MatchValue(value=group_identifier)
                        )
                    ]
                ),
            )

            if not points:
                break

            functions.extend(
                self.validate(point.payload)
                for point in points
                if point.payload is not None
            )

            if next_page_offset is None:
                break

            offset = next_page_offset

        return functions

    def combine(
            self,
            first_list: List[Any],
            second_list: List[Any]
    ) -> List[Any]:
        seen_identifiers = set()
        combined = []

        for fn in first_list + second_list:
            if isinstance(fn, dict):
                identifier_value = fn.get(self.payload_identifier)
            else:
                identifier_value = getattr(fn, self.payload_identifier, None)

            if identifier_value not in seen_identifiers:
                combined.append(fn)
                seen_identifiers.add(identifier_value)

        return combined

    def __del__(self):
        if self._scheduler:
            self._scheduler.shutdown()
