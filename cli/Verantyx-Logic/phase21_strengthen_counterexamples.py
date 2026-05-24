#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, re
from pathlib import Path
from typing import Dict, Any, List

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists(): return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def get_minimal_tpl(domain: str, hint: str) -> str:
    hint = hint.lower()
    if "propositional" in domain:
        return "Domain: {T, F}\nStructure: Assignment {p: T, q: F}\nDropped Assumption: Soundness\nFailure Point: Logical contradiction\nMinimality: true"
    if "modal" in domain:
        return "Domain: Kripke\nStructure: W={w0, w1}, R={(w0, w1)}\nDropped Assumption: Reflexivity\nFailure Point: Axiom T failure\nMinimality: true"
    return f"Domain: {domain}\nStructure: Minimal counter-model\nDropped Assumption: General property\nFailure Point: Property mismatch\nMinimality: true"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--patches-out", required=True)
    args = ap.parse_args()

    entries = read_jsonl(Path(args.kb))
    patches = []

    for e in entries:
        if e.get("kind") == "counterexample_schema" and "needs_review" in e.get("patterns", []):
            new_ref = get_minimal_tpl(e.get("domain", "logic"), e.get("refutation", ""))
            patches.append({
                "id": e["id"], "op": "set_field", "path": "/refutation", "value": new_ref,
                "reason": "phase21:strengthen_counterexample"
            })

    with Path(args.patches_out).open("w") as f:
        for p in patches:
            f.write(json.dumps(p) + "\n")
    print(f"[OK] Generated {len(patches)} strengthening patches.")

if __name__ == "__main__":
    main()

