from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Explanation:
    summary: str
    correspondence: List[str]          # e.g. ["axiom:4"]
    missing_assumptions: List[str]     # e.g. ["assume:reflexive"]
    notes: List[str]                  # extra details
    evidence_refs: List[str]          # NEW: e.g. ["assume:transitive"]
    repair_suggestion: Optional[List[str]] = None # NEW: e.g. ["assume:reflexive"]

def _normalize_formula(formula: str) -> str:
    # Normalize to match DB keys: strip spaces, standard arrow
    # The DB keys currently have spaces (e.g. "[]p -> [][]p"), but engine output has none ("[]p->[][]p").
    # We should normalize both to a canonical form (e.g. no spaces) for lookup.
    # But since I can't change DB loading logic easily to re-key, I will try to match robustly.
    # Actually, simplest is to strip spaces from formula and also strip spaces from DB keys during lookup?
    # No, that's slow.
    # I'll normalize formula to have spaces if possible? No.
    # I'll strip spaces here and assume DB keys should be space-stripped or I'll try both.
    
    # Let's try removing all spaces.
    return formula.strip().replace(" ", "").replace("→", "->")

def _kb_get(kb: Dict[str, Any], path: List[str], default=None):
    cur: Any = kb
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def explain_formula(
    *,
    formula: str,
    assumptions: List[str],
    verdict: str,  # "valid" | "invalid" | "unknown"
    kb: Dict[str, Any],
) -> Explanation:
    """
    Phase 7.5:
    - If the formula matches a known schema, attach correspondence axioms from KB.
    - If invalid, mention missing assumptions when known.
    """
    f = _normalize_formula(formula)
    corr = _kb_get(kb, ["correspondence"], {}) or {}
    schema_map = (corr.get("schemas") or {})
    
    # Create a normalized map for lookup (robustness hack)
    norm_schema_map = {k.replace(" ", ""): v for k, v in schema_map.items()}
    
    axioms = (corr.get("axioms") or {})
    missing_hints = (corr.get("missing_assumption_hints") or {})
    norm_missing_hints = {k.replace(" ", ""): v for k, v in missing_hints.items()}

    notes: List[str] = []
    correspondence_ids: List[str] = []
    missing: List[str] = []

    # 1) Schema match
    schema_entry = norm_schema_map.get(f)
    if schema_entry:
        supports = schema_entry.get("supports") or []
        for ax_id in supports:
            if ax_id in axioms:
                correspondence_ids.append(ax_id)
        notes.append(schema_entry.get("explain") or "Matches a known modal axiom schema.")
    else:
        notes.append("No direct correspondence schema match in knowledge DB.")

    # 2) Missing assumptions (helpful when invalid)
    hinted = norm_missing_hints.get(f) or []
    if verdict == "invalid" and hinted:
        # missing = hinted - assumptions
        for need in hinted:
            if need not in assumptions:
                missing.append(need)

    # 3) Build summary
    if verdict == "valid":
        if correspondence_ids:
            # show the first one primarily
            ax0 = axioms.get(correspondence_ids[0], {})
            reqs = ax0.get("requires") or []
            ok = all(r in assumptions for r in reqs)
            if ok:
                summary = f"Valid: under assumptions {assumptions}, this matches {correspondence_ids[0]} ({ax0.get('schema')})."
            else:
                summary = f"Valid (by model search): matches {correspondence_ids[0]} but required assumptions {reqs} are not fully present in Spec."
        else:
            summary = f"Valid: no counterexample found under assumptions {assumptions}."
    elif verdict == "invalid":
        if missing:
            summary = f"Invalid: counterexample exists; typically this schema needs {missing}."
        else:
            summary = "Invalid: counterexample exists under the given assumptions."
    else:
        summary = "Unknown: insufficient evidence."

    # Phase 8: Collect evidence refs
    refs: List[str] = []
    for ax_id in correspondence_ids:
        ax = axioms.get(ax_id, {}) or {}
        for req in (ax.get("requires") or []):
            if isinstance(req, str) and req.startswith("assume:"):
                refs.append(req)
    refs.extend(missing)
    refs = sorted(set(refs))

    return Explanation(
        summary=summary,
        correspondence=correspondence_ids,
        missing_assumptions=missing,
        notes=notes,
        evidence_refs=refs,
        repair_suggestion=missing if verdict == "invalid" and missing else None
    )