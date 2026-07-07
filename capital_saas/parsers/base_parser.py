from abc import ABC, abstractmethod
from pathlib import Path


class BaseParser(ABC):
    parser_type = "base"

    @abstractmethod
    def parse(self, file_path: Path) -> dict:
        raise NotImplementedError

    @staticmethod
    def result(**kwargs) -> dict:
        return {"parser_type": "base", "status": "success", **kwargs}
