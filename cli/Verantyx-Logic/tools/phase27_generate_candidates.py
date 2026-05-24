#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase 27-A: Generate refutation replacement candidates for entries with
min_verified:unknown or min_verified:false.
"""

from __future__ import annotations
import argparse, json
from typing import Any, Dict, Iterable, List, Tuple, Optional


def iter_jsonl(path: str) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            yield i, json.loads(line)


def has_pattern(entry: Dict[str, Any], p: str) -> bool:
    pats = entry.get("patterns")
    return isinstance(pats, list) and p in pats

def get_domain(entry: Dict[str, Any]) -> str:
    d = entry.get("domain")
    return d if isinstance(d, str) else ""


# ---- Heuristic candidate generators (purely symbolic, GPU-free) ----

def candidate_prop_logic(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "format": "BoundaryRefutationV1",
        "Domain": "propositional_logic",
        "Structure": "Valuation v over atoms; v: {p,q,r,...} -> {T,F}",
        "DroppedAssumption": "none (classical truth tables)",
        "FailurePoint": "Provide v such that premise(s)=T but conclusion=F",
        "MinimalityHint": "Use smallest atom set appearing in statement; 1-2 atoms if possible",
        "Witness": {
            "atoms": ["p", "q"],
            "valuation": {"p": "T", "q": "F"},
            "note": "Adjust atoms/values to falsify the target formula; keep atoms minimal."
        }
    }

def candidate_fol(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "format": "BoundaryRefutationV1",
        "Domain": "first_order_logic",
        "Structure": "Finite structure M with small domain (size 1..3), explicit interpretations",
        "DroppedAssumption": "none (standard FOL semantics)",
        "FailurePoint": "Quantifier order / Skolemization / satisfiable vs valid mismatch",
        "MinimalityHint": "Try |D|=1 then 2 then 3; prefer unary predicates / one binary relation",
        "Witness": {
            "domain": [0, 1],
            "predicates": {"P": [0], "Q": []},
            "relations": {"R": [[0, 1]]},
            "functions": {},
            "assignment": {"x": 0, "y": 1},
            "note": "Tune predicate/relations to make \u2200\u2203 true but \u2203\u2200 false, or vice versa."
        }
    }

def candidate_model_theory(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "format": "BoundaryRefutationV1",
        "Domain": "model_theory",
        "Structure": "Pair of elementarily equivalent but non-isomorphic structures, or finite-vs-infinite split",
        "DroppedAssumption": "categoricity / saturation / compactness misuse (identify which)",
        "FailurePoint": "Non-categoricity / non-standard model / LS theorem boundary",
        "MinimalityHint": "Use canonical examples: (Q,<) vs (R,<), non-standard PA, dense orders without endpoints",
        "Witness": {
            "example": "Dense linear orders: (Q,<) and (R,<) are elementarily equivalent but not isomorphic",
            "note": "Swap in standard counterexample family matching the statement tags/patterns."
        }
    }

def candidate_modal(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "format": "BoundaryRefutationV1",
        "Domain": "modal_logic",
        "Structure": "Small Kripke frame (W,R) with 1..3 worlds; valuation V",
        "DroppedAssumption": "toggle one frame property (reflexive/transitive/symmetric/euclidean/serial)",
        "FailurePoint": "Axiom schema fails on minimal frame when property is absent",
        "MinimalityHint": "Start with 2-world chain w0->w1; add edge for transitivity violations if needed",
        "Witness": {
            "worlds": ["w0", "w1"],
            "R": [["w0", "w1"]],
            "V": {"p": ["w1"]},
            "note": "Typical: falsify \u25E2p\u2192p with non-reflexive frame, etc."
        }
    }

def candidate_generic(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "format": "BoundaryRefutationV1",
        "Domain": get_domain(entry) or "unknown_domain",
        "Structure": "Provide the smallest explicit structure that violates the claim",
        "DroppedAssumption": "identify the missing assumption that makes the claim fail",
        "FailurePoint": "state the exact sub-claim that fails under the structure",
        "MinimalityHint": "minimize domain/size/parameters; keep witness fully explicit",
        "Witness": {"note": "Fill explicit small structure; avoid placeholders."}
    }

def build_candidate(entry: Dict[str, Any]) -> Dict[str, Any]:
    d = get_domain(entry)
    if d == "propositional_logic":
        return candidate_prop_logic(entry)
    if d == "first_order_logic":
        return candidate_fol(entry)
    if d == "model_theory":
        return candidate_model_theory(entry)
    if d == "modal_logic":
        return candidate_modal(entry)
    return candidate_generic(entry)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="0=all, else limit for testing")
    args = ap.parse_args()

    # Create output directory if it doesn't exist
    import os
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    
    # Clear output file
    if os.path.exists(args.out):
        os.remove(args.out)

    written = 0
    with open(args.out, "a", encoding="utf-8") as fo:
        for _, e in iter_jsonl(args.kb):
            eid = e.get("id")
            if not isinstance(eid, str):
                continue

            # target: unknown or false (from Phase26 tagging)
            if not (has_pattern(e, "min_verified:unknown") or has_pattern(e, "min_verified:false")):
                continue

            # We focus on counterexample_schema first, but allow others if you want
            kind = e.get("kind")
            if kind not in ("counterexample_schema", "theorem", "axiom", "rule", "definition"):
                continue

            cand = build_candidate(e)
            rec = {
                "target_id": eid,
                "domain": get_domain(e),
                "kind": kind,
                "candidate": cand
            }
            fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
            if args.limit and written >= args.limit:
                break

    print(f"[OK] phase27 candidates written: {written} -> {args.out}")


if __name__ == "__main__":
    main()
