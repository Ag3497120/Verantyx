from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class TextCrossNode:
    axis: str
    content: Dict
    links: List[str] = field(default_factory=list)
