from dataclasses import dataclass
from typing import List, Optional

@dataclass
class PuzzlePiece:
    kind: str  # formula / assumption / syntax / shape
    content: str
    confidence: float
    source: str  # text_cross / kb / inferred
    metadata: Optional[dict] = None
