from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseRecognizer(ABC):
    @abstractmethod
    def recognize(self, text: str) -> Dict[str, Any]:
        """
        テキストを解析し、構造化された結果を返す。
        """
        pass

    @abstractmethod
    def can_handle(self, text: str) -> float:
        """
        このRecognizerがテキストを処理できる可能性（0.0 - 1.0）を返す。
        """
        pass
