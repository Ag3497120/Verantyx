#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists(): return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def pick_canonical(cluster: List[str], scores: Dict[str, Dict[str, Any]]) -> str:
    best = None
    best_val = -1.0
    for eid in cluster:
        trust = scores.get(eid, {}).get("trust", 0.0)
        if trust > best_val:
            best = eid
            best_val = trust
    return best or cluster[0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dups", required=True)
    ap.add_argument("--scores", required=True)
    ap.add_argument("--plan-out", required=True)
    ap.add_argument("--patches-out", required=True)
    args = ap.parse_args()

    dups_raw = read_json(Path(args.dups))
    score_rows = read_jsonl(Path(args.scores))
    scores = {r["id"]: r for r in score_rows}

    # Simplify clusters from phase 20 list format
    clusters = dups_raw if isinstance(dups_raw, list) else []
    
    patches = []
    plan = []

    for cluster in clusters:
        if len(cluster) < 2: continue
        canon = pick_canonical(cluster, scores)
        for eid in cluster:
            if eid == canon:
                patches.append({"id": eid, "op": "set_field", "path": "/patterns", "value": ["has_duplicates"], "reason": "phase21:canonical"})
            else:
                patches.append({"id": eid, "op": "set_field", "path": "/patterns", "value": [f"duplicate_of:{canon}"], "reason": "phase21:duplicate"})
                patches.append({"id": eid, "op": "set_field", "path": "/links", "value": [canon], "reason": "phase21:link_to_canon"})
        plan.append({"canonical": canon, "duplicates": [e for e in cluster if e != canon]})

    with Path(args.patches_out).open("w") as f:
        for p in patches: f.write(json.dumps(p) + "\n")
    Path(args.plan_out).write_text(json.dumps(plan, indent=2))
    print(f"[OK] Generated {len(patches)} dedup patches.")

if __name__ == "__main__":
    main()
