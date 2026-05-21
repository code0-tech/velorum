from abc import ABC
from typing import Any, List


class Store(ABC):
    def __init__(
            self,
            payload_identifier: str,
    ):
        self.payload_identifier = payload_identifier
        self.data = []

    def insert(self, data: Any):
        self.data.append(data)

    def find(self, identifier: str) -> Any:
        for entry in self.data:
            if getattr(entry, self.payload_identifier) == identifier:
                return entry
        return None

    def find_all(self, identifier: List[str]) -> List[Any]:
        return [entry for entry in self.data if getattr(entry, self.payload_identifier) in identifier]

    def get_all(self) -> List[Any]:
        return self.data if self.data else []
