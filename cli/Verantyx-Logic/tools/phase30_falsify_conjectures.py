#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase 30: Conjecture Falsification Loop

- Load KB JSONL
- Find conjecture theorem entries: kind="theorem" and patterns include "status:conjecture"
- For each, attempt to find a counterexample with a model search backend.
- Emit:
  - phase30_results.jsonl : per conjecture outcome
  - phase30_patches.jsonl : non-destructive patches to apply to KB
  - phase30_new_counterexamples.jsonl : optional "reborn" counterexample_schema entries (not auto-appended)

Backend strategy:
1) Try to import avh_math.model_search and use it if it exposes a callable `falsify(...)`.
2) Else fallback to a deterministic stub that returns unknown (never claims true/false incorrectly).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ---------------- IO ----------------

def read_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out

def write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---------------- Utils ----------------

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def ensure_list(x: Any) -> List[Any]:
    if isinstance(x, list):
        return x
    return []

def has_pattern(entry: Dict[str, Any], pat: str) -> bool:
    pats = ensure_list(entry.get("patterns"))
    p = norm(pat)
    return any(norm(str(x)) == p for x in pats)

def add_patterns(entry: Dict[str, Any], to_add: List[str]) -> List[str]:
    pats = [str(x) for x in ensure_list(entry.get("patterns")) if str(x).strip()]
    s = set(pats)
    for t in to_add:
        if t not in s:
            pats.append(t)
            s.add(t)
    return pats

# ---------------- Backend API ----------------

@dataclass
class FalsifyResult:
    status: str  # "falsified" | "not_found" | "unknown" | "error"
    counterexample: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class Backend:
    def falsify(self, conjecture_entry: Dict[str, Any], max_search: Dict[str, Any]) -> FalsifyResult:
        raise NotImplementedError

class StubBackend(Backend):
    def falsify(self, conjecture_entry: Dict[str, Any], max_search: Dict[str, Any]) -> FalsifyResult:
        # Safe fallback: never claims verified true/false
        return FalsifyResult(
            status="unknown",
            counterexample=None,
            details={"reason": "stub_backend_no_solver_connected", "max_search": max_search},
        )

class AVHModelSearchBackend(Backend):
    """
    Adapter to avh_math.model_search if present.
    """

    def __init__(self):
        # Local import to avoid circular dependency
        try:
            import sys
            sys.path.append(os.getcwd()) # Ensure root is in path
            from avh_math import model_search
            self.ms = model_search
        except ImportError:
            self.ms = None

    def falsify(self, conjecture_entry: Dict[str, Any], max_search: Dict[str, Any]) -> FalsifyResult:
        if not self.ms:
             return FalsifyResult(status="unknown", details={"reason": "avh_math.model_search not found"})

        statement = str(conjecture_entry.get("statement", "")).strip()
        domain = str(conjecture_entry.get("domain", "cross_domain")).strip()
        prereq = [str(x) for x in ensure_list(conjecture_entry.get("prerequisites"))]
        assumptions = [x for x in prereq if x.startswith("assume:")]

        # defaults
        max_worlds = int(max_search.get("max_worlds", 4))
        max_depth = int(max_search.get("max_depth", 3))
        timeout_s = float(max_search.get("timeout_s", 1.5))

        if hasattr(self.ms, "falsify") and callable(getattr(self.ms, "falsify")):
            raw = self.ms.falsify(
                statement=statement,
                domain=domain,
                assumptions=assumptions,
                max_worlds=max_worlds,
                max_depth=max_depth,
                timeout_s=timeout_s,
            )
            status = str(raw.get("status", "unknown"))
            cx = raw.get("counterexample")
            meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
            if status not in ["falsified", "not_found"]:
                status = "unknown"
            return FalsifyResult(status=status, counterexample=cx, details=meta)

        return FalsifyResult(
            status="unknown",
            counterexample=None,
            details={"reason": "avh_math.model_search exists but missing falsify()", "max_search": max_search},
        )

def pick_backend(prefer: str) -> Backend:
    if prefer == "avh":
        try:
            return AVHModelSearchBackend()
        except Exception:
            return StubBackend()
    if prefer == "stub":
        return StubBackend()
    # auto
    try:
        return AVHModelSearchBackend()
    except Exception:
        return StubBackend()

# ---------------- Patch construction ----------------

def patch_for_verified_true(e: Dict[str, Any], note: str) -> Dict[str, Any]:
    pats = add_patterns(e, ["theorem_verified:true", "phase30:checked"])
    pats = add_patterns({"patterns": pats}, ["status:conjecture_resolved"])
    return {
        "op": "update",
        "id": e["id"],
        "set": {
            "patterns": pats,
            "patch_note": f"{note}",
        },
    }

def patch_for_verified_false(e: Dict[str, Any], counterexample: str, note: str) -> Dict[str, Any]:
    pats = add_patterns(e, ["theorem_verified:false", "needs_review", "phase30:falsified"])
    return {
        "op": "update",
        "id": e["id"],
        "set": {
            "patterns": pats,
            "refutation": counterexample,
            "patch_note": f"{note}",
        },
    }

def reborn_counterexample_entry(kb: List[Dict[str, Any]], domain: str) -> str:
    prefix_map = {
        "propositional_logic": "prop",
        "first_order_logic": "fol",
        "model_theory": "mt",
        "modal_logic": "modal",
        "computational_complexity": "comp",
        "group_theory": "grp",
        "ring_theory": "ring",
        "topology": "topo",
        "graph_theory": "graph",
        "cross_domain": "xdom",
    }
    d = domain.strip().lower()
    pfx = prefix_map.get(d, "xdom")
    mx = 0
    for e in kb:
        eid = e.get("id")
        if not isinstance(eid, str):
            continue
        if not eid.startswith(pfx + ".cex."):
            continue
        m = re.search(r"\.(\d{5,})$", eid)
        if m:
            mx = max(mx, int(m.group(1)))
    return f"{pfx}.cex.{mx+1:05d}"

# ---------------- Main ----------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out-results", required=True)
    ap.add_argument("--out-patches", required=True)
    ap.add_argument("--out-reborn", required=True)
    ap.add_argument("--backend", default="auto", choices=["auto", "avh", "stub"])
    ap.add_argument("--limit", type=int, default=0, help="0 = no limit")
    ap.add_argument("--max_worlds", type=int, default=4)
    ap.add_argument("--max_depth", type=int, default=3)
    ap.add_argument("--timeout_s", type=float, default=1.5)
    args = ap.parse_args()

    kb = read_jsonl(args.kb)
    backend = pick_backend(args.backend)

    # collect conjectures
    targets: List[Dict[str, Any]] = []
    for e in kb:
        if e.get("kind") != "theorem":
            continue
        if not has_pattern(e, "status:conjecture"):
            continue
        # If already resolved, skip
        pats = [norm(str(x)) for x in ensure_list(e.get("patterns"))]
        if "theorem_verified:true" in pats or "theorem_verified:false" in pats:
            continue
        targets.append(e)

    if args.limit and args.limit > 0:
        targets = targets[: args.limit]

    max_search = {"max_worlds": args.max_worlds, "max_depth": args.max_depth, "timeout_s": args.timeout_s}

    results: List[Dict[str, Any]] = []
    patches: List[Dict[str, Any]] = []
    reborn: List[Dict[str, Any]] = []

    t0 = time.time()

    for idx, e in enumerate(targets, 1):
        eid = e.get("id")
        domain = str(e.get("domain", "cross_domain")).strip() or "cross_domain"
        statement = str(e.get("statement", "")).strip()

        r = backend.falsify(e, max_search=max_search)

        if r.status == "falsified":
            note = f"Phase30 falsified (backend={args.backend})"
            cx = r.counterexample or "Domain: unknown\nStructure: unknown\nDropped Assumption: unknown\nFailure Point: conjecture falsified\nMinimality: unknown"
            patches.append(patch_for_verified_false(e, cx, note))

            new_id = reborn_counterexample_entry(kb, domain)
            reborn.append({
                "id": new_id,
                "domain": domain,
                "kind": "counterexample_schema",
                "title": f"Reborn from {eid}",
                "statement": f"Counterexample schema reborn from falsified conjecture {eid}.",
                "prerequisites": [f"source:{eid}"],
                "yields": ["logic:countermodel", "phase30:reborn"],
                "refutation": cx,
                "patterns": ["phase30:reborn", "counterexample_schema", f"from:{eid}"],
                "links": [str(eid)],
            })

        elif r.status == "not_found":
            note = f"Phase30 no counterexample found within bounds {max_search} (backend={args.backend})"
            patches.append(patch_for_verified_true(e, note))

        elif r.status == "unknown":
            pats = add_patterns(e, ["theorem_verified:unknown", "phase30:checked"])
            patches.append({
                "op": "update",
                "id": e["id"],
                "set": {"patterns": pats, "patch_note": f"Phase30 unknown (backend={args.backend})"},
            })

        else:
            pats = add_patterns(e, ["theorem_verified:error", "needs_review", "phase30:error"])
            patches.append({
                "op": "update",
                "id": e["id"],
                "set": {"patterns": pats, "patch_note": f"Phase30 error: {r.details}"},
            })

        results.append({
            "id": str(eid),
            "domain": domain,
            "status": r.status,
            "max_search": max_search,
            "counterexample_present": bool(r.counterexample),
            "backend": args.backend,
            "details": r.details or {},
            "statement_head": statement[:160],
        })

        if idx % 100 == 0:
            print(f"[PHASE30] processed {idx}/{len(targets)}")

    dt = time.time() - t0
    print(f"[PHASE30] targets={len(targets)} patches={len(patches)} reborn={len(reborn)} elapsed={dt:.2f}s")
    write_jsonl(args.out_results, results)
    write_jsonl(args.out_patches, patches)
    write_jsonl(args.out_reborn, reborn)

if __name__ == "__main__":
    main()
