from __future__ import annotations
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cross import TextDecompositionCross

def build_text_cross(text: str) -> TextDecompositionCross:
    from .cross import TextDecompositionCross
    
    cross = TextDecompositionCross(
        cross_id=f"text_cross_{uuid.uuid4().hex[:8]}",
        raw_text=text or "",
    )

    from .tokenizer import tokenize_text
    from .shape import classify_shape
    tokens = tokenize_text(text or "")

    for i, tok in enumerate(tokens):
        from .node import TextCrossNode
        cross.add_node(
            f"tok_{i}",
            TextCrossNode(
                axis="token",
                content={
                    "surface": tok,
                    "position": i,
                    "shape": classify_shape(tok),
                },
            ),
        )

    return cross