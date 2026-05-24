from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CexTemplate:
    template_id: str
    formula_pattern: str          # regex on normalized formula
    missing_assumption: str       # e.g., "assume:reflexive"
    minimal_model_hint: Dict[str, Any]  # hints for human explanation
    explanation_steps: List[str]  # text steps
    used_knowledge: List[str]


def _norm(s: str) -> str:
    return " ".join(s.strip().split())


def synth_cex_templates_from_kb(knowledge_db: Dict[str, Any]) -> List[CexTemplate]:
    """
    KB(correspondence) から「この仮定が無いとこの形の式は壊れる」を合成。
    まずは様相論理の対応（T/4/5など）で強くなる。
    """
    out: List[CexTemplate] = []
    corr = knowledge_db.get("correspondence") or {}

    # --- Template: T axiom requires reflexive ---
    # If NOT reflexive, □P -> P can fail with 1-world model without self-loop.
    # Pattern: []p -> p
    if "assume:reflexive" in corr:
        out.append(CexTemplate(
            template_id="cex.modal.not_reflexive.breaks_T",
            # Normalized: []p -> p
            formula_pattern=r"^\[\](?P<P>.+?)\s*->\s*(?P=P)$",
            missing_assumption="assume:reflexive",
            minimal_model_hint={
                "worlds": ["w"],
                "edges": [],  # no wRw
                "valuation": "Set P false at w; □P holds vacuously if w has no successors."
            },
            explanation_steps=[
                "反射性（reflexive）が無いと、wRw が成り立たない世界 w を作れる。",
                "到達先が無い（後続世界が0）なら □P は“全ての到達先でP”が空集合上で真（真 vacuously true）になり得る。",
                "そこで w で P を偽にすれば、□P は真だが P は偽になり、□P→P が壊れる。"
            ],
            used_knowledge=["correspondence.assume:reflexive"]
        ))

    # --- Template: 4 axiom requires transitive ---
    # If NOT transitive, □P -> □□P can fail with wRv, vRu, but not wRu.
    # Pattern: []p -> [][]p
    if "assume:transitive" in corr:
        out.append(CexTemplate(
            template_id="cex.modal.not_transitive.breaks_4",
            formula_pattern=r"^\[\](?P<P>.+?)\s*->\s*\[\]\[\](?P=P)$",
            missing_assumption="assume:transitive",
            minimal_model_hint={
                "worlds": ["w", "v", "u"],
                "edges": [["w", "v"], ["v", "u"]],  # but NOT w->u
                "valuation": "Make P true at v; make P false at u."
            },
            explanation_steps=[
                "推移性（transitive）が無いと、wRv かつ vRu だが wRu ではない構造が作れる。",
                "w から見ると到達先は v だけなので、v で P を真にしておけば □P は真になり得る。",
                "しかし v からは u に到達でき、u で P を偽にすると、v で □P が偽になり、結果として w で □□P が偽になる。",
                "よって □P→□□P は推移性なしでは壊れる。"
            ],
            used_knowledge=["correspondence.assume:transitive"]
        ))

    # --- Template: 5 axiom requires euclidean (if you have it) ---
    # ◊P -> □◊P breaks without euclidean; classic fork counterexample
    # Pattern: <>p -> []<>p
    if "assume:euclidean" in corr:
        out.append(CexTemplate(
            template_id="cex.modal.not_euclidean.breaks_5_diamond",
            formula_pattern=r"^<>\s*(?P<P>.+?)\s*->\s*\[\]<>\s*(?P=P)$",
            missing_assumption="assume:euclidean",
            minimal_model_hint={
                "worlds": ["w", "v", "u"],
                "edges": [["w", "v"], ["w", "u"]], # fork
                "valuation": "Make P true at v; make P false at u; and ensure u has no P-successor."
            },
            explanation_steps=[
                "ユークリッド性（euclidean）が無いと、w から v と u へ分岐するが、v と u が互いに見えない構造が作れる（分岐）。",
                "w->v で v で P が真なら w で ◊P は真。",
                "しかし w->u で u から P が見える世界に行けなければ、u で ◊P は偽。",
                "よって w から見た到達先 u で ◊P が偽になるため、w で □◊P は偽となり、式が壊れる。"
            ],
            used_knowledge=["correspondence.assume:euclidean"]
        ))

    return out

def match_cex_template(
    formula: str,
    assumptions: List[str],
    templates: List[CexTemplate],
) -> Optional[CexTemplate]:
    f = _norm(formula)
    aset = set(assumptions)
    for t in templates:
        # Check if the REQUIRED assumption is MISSING
        if t.missing_assumption in aset:
            continue # assumption is present, so this CEX template doesn't apply (it shouldn't fail due to this reason)
        
        # Check if formula matches
        m = re.match(t.formula_pattern, f)
        if m:
            return t
    return None