from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class Trace:
    lines: List[str] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def add(self, msg: str) -> None:
        self.lines.append(msg)

    def attach(self, key: str, value: Any) -> None:
        self.artifacts[key] = value