import uuid

from .cross import TextDecompositionCross
from .node import TextCrossNode
from .tokenizer import tokenize_text
from .shape import classify_shape


def build_text_cross(text: str) -> TextDecompositionCross:
    cross = TextDecompositionCross(
        cross_id=f"text_cross_{uuid.uuid4().hex[:8]}",
        raw_text=text or "",
    )

    tokens = tokenize_text(text or "")

    for i, tok in enumerate(tokens):
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
