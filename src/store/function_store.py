import json
import re
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, MatchAny, Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

from src.schema.function_schema import FunctionDefinition, ParameterDefinition


def resolve_ts_signature(signature, type_defs):
    # 1. Typ-Datenbank aufbauen
    # Wir extrahieren: Name, Generics (falls vorhanden) und den Body
    type_db = {}
    # Regex erkennt: type NAME<OPTIONAL_GENERIC> = BODY
    type_pattern = re.compile(r"type\s+(\w+)(?:<([^>]+)>)?\s*=\s*(.+)")

    for td in type_defs:
        match = type_pattern.search(td)
        if match:
            name, generics, body = match.groups()
            params = [p.strip() for p in generics.split(",")] if generics else []
            type_db[name] = {"params": params, "body": body.strip()}

    def smart_split(s):
        """Teilt Kommas nur auf der obersten Ebene (ignoriert Kommas in <...>)"""
        parts = []
        bracket_level = 0
        current = []
        for char in s:
            if char == '<':
                bracket_level += 1
            elif char == '>':
                bracket_level -= 1
            if char == ',' and bracket_level == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        parts.append("".join(current).strip())
        return [p for p in parts if p]

    def resolve(target):
        # Finde den am weitesten links stehenden Typ-Namen, der evtl. <...> folgt
        # Wir suchen nach Wörtern, die nicht gefolgt werden von ( oder : (um Funktionsnamen zu schützen)
        pattern = r"\b(\w+)\b(?:<([^<>]+(?:<[^<>]+>)*)>)?"

        def replacement(match):
            name = match.group(1)
            args_raw = match.group(2)

            # Wenn der Name nicht in der DB ist, ist es ein Primitiv oder ein nacktes Generic
            if name not in type_db:
                if args_raw:
                    resolved_args = ", ".join([resolve(a) for a in smart_split(args_raw)])
                    return f"{name}<{resolved_args}>"
                return name

            entry = type_db[name]
            resolved_body = entry["body"]

            # Falls Generics im Spiel sind, ersetze diese im Body
            if args_raw and entry["params"]:
                args = smart_split(args_raw)
                for param, arg in zip(entry["params"], args):
                    # Wichtig: Nur ganze Wörter ersetzen (\b)
                    resolved_body = re.sub(rf"\b{param}\b", arg, resolved_body)

            # Rekursiv weiter auflösen, falls der Body selbst Custom Types enthält
            return resolve(resolved_body)

        # Wir wenden die Ersetzung so lange an, bis sich nichts mehr ändert
        previous = ""
        while previous != target:
            previous = target
            target = re.sub(pattern, replacement, target)
        return target

    return resolve(signature)


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

    def insert_from_json(self, functions_file_path: str, datatype_file_path: str):
        with open(functions_file_path, 'r') as f:
            functions = json.load(f)

        with open(datatype_file_path, 'r') as f:
            datatypes = [
                f"type {d['identifier']}{'<' + ','.join(d['genericKeys']) + '>' if d['genericKeys'] else ''} = {d['type']}"
                for d in json.load(f)
            ]

        points = []

        for idx, item in enumerate(functions):
            fn = FunctionDefinition(
                names=item.get("names")[0]["content"],
                aliases=item.get("aliases")[0]["content"],
                descriptions=item.get("descriptions")[0]["content"],
                identifier=item.get("identifier"),
                signature=resolve_ts_signature(item.get("signature"), datatypes),
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

    def find(self, identifier: str) -> FunctionDefinition | None:

        response = self.client.query_points(
            collection_name=self.collection_name,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="identifier",
                        match=MatchValue(value=identifier)
                    )
                ]
            ),
            limit=1,
            with_payload=True
        )

        if response.points:
            return FunctionDefinition.model_validate(response.points[0].payload)

        return None

    def find_all(self, identifiers: List[str]) -> List[FunctionDefinition]:

        if not identifiers:
            return []

        response = self.client.query_points(
            collection_name=self.collection_name,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="identifier",
                        match=MatchAny(any=identifiers)
                    )
                ]
            ),
            limit=len(identifiers),
            with_payload=True
        )

        return [
            FunctionDefinition.model_validate(hit.payload)
            for hit in response.points
        ]

    def get_all(self) -> List[FunctionDefinition]:
        functions: List[FunctionDefinition] = []
        offset = None

        while True:
            points, next_page_offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=256,
                with_payload=True,
                offset=offset,
            )

            if not points:
                break

            functions.extend(
                FunctionDefinition.model_validate(point.payload)
                for point in points
                if point.payload is not None
            )

            if next_page_offset is None:
                break

            offset = next_page_offset

        return functions

    def combine(
            self,
            first_list: List[FunctionDefinition],
            second_list: List[FunctionDefinition]
    ) -> List[FunctionDefinition]:
        seen_identifiers = set()
        combined = []

        for fn in first_list + second_list:
            if fn.identifier not in seen_identifiers:
                combined.append(fn)
                seen_identifiers.add(fn.identifier)

        return combined
