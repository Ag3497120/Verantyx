from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
import re


@dataclass
class PuzzlePiece:
    kind: str
    name: str
    payload: Dict[str, Any] = field(default_factory=dict)


def pieces_for_domain(domain: str, core_formula: str, text_norm: str) -> List[PuzzlePiece]:
    pieces: List[PuzzlePiece] = []
    d = domain or "unknown"

    if d == "propositional_logic":
        pieces.append(PuzzlePiece(kind="solver", name="prop_truth_table"))
    elif d == "modal_logic":
        pieces.append(PuzzlePiece(kind="solver", name="modal_kripke"))
        if re.search(r"\b(k|system\s*k|任意のkripke|どんな\s+frame)\b", text_norm.lower()):
            pieces.append(PuzzlePiece(kind="assumption", name="assume:K", payload={"frame": "any"}))
        if "推移" in text_norm or "transitive" in text_norm.lower():
            pieces.append(PuzzlePiece(kind="assumption", name="assume:transitive"))
        if "反射" in text_norm or "reflexive" in text_norm.lower():
            pieces.append(PuzzlePiece(kind="assumption", name="assume:reflexive"))
    elif d == "linear_algebra":
        pieces.append(PuzzlePiece(kind="solver", name="linear_algebra_rules"))
    else:
        pieces.append(PuzzlePiece(kind="solver", name="backoff"))

    pieces.append(PuzzlePiece(kind="explainer", name="clean_explainer"))
    return pieces
