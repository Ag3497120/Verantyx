from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ShapeSig:
    domain_hint: str
    features: Dict[str, int]
    tags: List[str]


def shape_signature(text: str, core_formula: str | None = None) -> ShapeSig:
    t = text or ""
    f = core_formula or ""

    features: Dict[str, int] = {
        "has_modal_box": int("[]" in t or "□" in t or "[]" in f),
        "has_modal_diamond": int("<>" in t or "◇" in t or "<>" in f),
        "has_imp": int("->" in t or "→" in t or "->" in f),
        "has_and": int("&" in t or "∧" in t or "&" in f),
        "has_or": int("|" in t or "∨" in t or "|" in f),
        "has_not": int("~" in t or "¬" in t or "~" in f),
        "has_quantifier": int(bool(re.search(r"[∀∃]|\\forall|\\exists", t))),
        "has_matrix_words": int(bool(re.search(r"(行列|matrix|symmetric|対称|rank|det|trace|eigen)", t, re.I))),
        "has_dim_words": int(bool(re.search(r"(次元|dimension|dim)", t, re.I))),
        "has_group_words": int(bool(re.search(r"(群|group|abelian|normal|subgroup)", t, re.I))),
        "has_topology_words": int(bool(re.search(r"(位相|topology|open set|compact|hausdorff|連結)", t, re.I))),
        "has_complexity_words": int(bool(re.search(r"(P\\s*=\\s*NP|NP|reduction|多項式|計算量)", t, re.I))),
    }

    domain_hint = "unknown"
    if features["has_modal_box"] or features["has_modal_diamond"]:
        domain_hint = "modal_logic"
    elif features["has_quantifier"]:
        domain_hint = "first_order_logic"
    elif features["has_matrix_words"] or features["has_dim_words"]:
        domain_hint = "linear_algebra"
    elif features["has_group_words"]:
        domain_hint = "group_theory"
    elif features["has_topology_words"]:
        domain_hint = "topology"
    elif features["has_complexity_words"]:
        domain_hint = "computational_complexity"
    elif features["has_imp"] or features["has_and"] or features["has_or"] or features["has_not"]:
        domain_hint = "propositional_logic"

    tags: List[str] = []
    for k, v in features.items():
        if v:
            tags.append(f"shape:{k}")

    return ShapeSig(domain_hint=domain_hint, features=features, tags=tags)
