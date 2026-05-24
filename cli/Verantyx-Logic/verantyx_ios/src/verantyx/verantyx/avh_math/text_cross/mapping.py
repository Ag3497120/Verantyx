from __future__ import annotations

from typing import Any, Dict, List


def _detect_domain_from_text(text: str, tokens: List[str], shapes: List[str]) -> str:
    text_l = (text or "").lower()
    tokens_l = [t.lower() for t in tokens]
    shapes_set = set(shapes)

    # modal cues
    if "[]" in tokens or "□" in tokens or "<>" in tokens or "◇" in tokens:
        return "modal_logic"
    if "kripke" in text_l or "様相" in text or "modal" in text_l:
        return "modal_logic"
    if "modal" in shapes_set:
        return "modal_logic"

    # linear algebra cues
    if "dim" in text_l or "sym" in text_l or "matrix" in text_l:
        return "linear_algebra"
    if "行列" in text or "次元" in text:
        return "linear_algebra"

    # propositional cues
    if "->" in tokens or "→" in tokens or "&" in tokens or "|" in tokens or "~" in tokens:
        return "propositional_logic"
    if "tautology" in text_l or "命題" in text:
        return "propositional_logic"

    return "unknown"


def _detect_assumptions(text: str) -> List[str]:
    text_l = (text or "").lower()
    out: List[str] = []
    if "推移" in text or "transitive" in text_l:
        out.append("assume:transitive")
    if "反射" in text or "reflexive" in text_l:
        out.append("assume:reflexive")
    if "対称" in text or "symmetric" in text_l:
        out.append("assume:symmetric")
    if "ユークリッド" in text or "euclidean" in text_l:
        out.append("assume:euclidean")
    return sorted(set(out))


def derive_mapping(similars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract lightweight mapping hints from similar text-cross entries.
    This does not decide domain; it suggests hints based on surface shapes.
    """
    domain_votes: Dict[str, int] = {}
    assumptions: List[str] = []
    samples: List[Dict[str, Any]] = []

    for s in similars:
        core_text = s.get("core_formula") or ""
        meta = s.get("meta") or {}
        tokens = meta.get("tokens") or []
        shapes = meta.get("structure_signature") or []

        domain = _detect_domain_from_text(core_text, tokens, shapes)
        domain_votes[domain] = domain_votes.get(domain, 0) + 1
        assumptions.extend(_detect_assumptions(core_text))
        samples.append(
            {
                "cross_id": s.get("cross_id"),
                "domain_hint": domain,
                "assumptions": _detect_assumptions(core_text),
            }
        )

    domain_hint = "unknown"
    if domain_votes:
        domain_hint = sorted(domain_votes.items(), key=lambda x: x[1], reverse=True)[0][0]

    return {
        "domain_hint": domain_hint,
        "assumptions": sorted(set(assumptions)),
        "samples": samples[:3],
    }
