from abc import ABC, abstractmethod
from typing import Any, Dict
from avh_math.puzzle.status_types import ReasoningStatus

class BaseVerifier(ABC):
    @abstractmethod
    def verify(self, reasoning_cross: Any) -> Dict[str, Any]:
        """
        Reasoning Crossを受け取り、検証結果を返す。
        戻り値には 'status' (ReasoningStatus) を含むこと。
        """
        pass
