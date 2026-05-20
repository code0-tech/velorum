import re
from typing import List, Any

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from src.schema.data_type_schema import DataType
from src.schema.function_schema import FunctionDefinition
from src.store.store import Store


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


class FunctionStore(Store):
    def __init__(self, memory_client: QdrantClient, vector_model: SentenceTransformer):
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

        self.insert(group_identifier, payload.model_dump())

    def validate(self, payload: Any) -> FunctionDefinition:
        return FunctionDefinition.model_validate(payload)

    def search(self, group_identifier: str, prompt: str, limit=5) -> List[FunctionDefinition]:
        return super().search(prompt, group_identifier, limit)

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
