import json
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from src.schema.Function_schema import FunctionDefinition, ParameterDefinition


class FunctionStore:
    def __init__(self, collection_name="functions"):
        self.client = QdrantClient(":memory:")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.collection_name = collection_name
        self._setup_collection()

    def _setup_collection(self):
        if not self.client.collection_exists(collection_name=self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=384,
                    distance=Distance.COSINE
                ),
            )

    def insert_from_json(self, file_path: str):
        with open(file_path, 'r') as f:
            data = json.load(f)

        points = []
        for idx, item in enumerate(data):
            fn = FunctionDefinition(
                names=item.get("names")[0]["content"],
                aliases=item.get("aliases")[0]["content"],
                descriptions=item.get("descriptions")[0]["content"],
                identifier=item.get("identifier"),
                signature=item.get("signature"),
                parameterDefinitions=[
                    ParameterDefinition(
                        descriptions=pd["descriptions"][0]["content"],
                        names=pd["names"][0]["content"],
                    )
                    for pd in item.get("parameterDefinitions")["nodes"]
                ]
            )

            name_val = fn.names or ""
            desc_val = fn.descriptions or ""
            text_to_embed = f"{name_val}: {desc_val}"

            vector = self.model.encode(text_to_embed).tolist()

            points.append(PointStruct(
                id=idx,
                vector=vector,
                payload=fn.model_dump(by_alias=True)
            ))

        self.client.upsert(collection_name=self.collection_name, points=points)

    def search(self, prompt: str, limit=5) -> List[FunctionDefinition]:
        query_vector = self.model.encode(prompt).tolist()


        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            with_payload=True
        )

        return [
            FunctionDefinition.model_validate(hit.payload)
            for hit in response.points
        ]
