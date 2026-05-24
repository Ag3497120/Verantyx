#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict, Counter

def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists(): return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def kb_get_entry(kb_path: Path, offsets: Dict[str, int], eid: str) -> Dict[str, Any]:
    off = offsets.get(eid)
    if off is None: raise KeyError(eid)
    with kb_path.open("rb") as f:
        f.seek(off)
        return json.loads(f.readline().decode("utf-8").strip())

def normalize_refutation_format(refutation: str, domain: str) -> str:
    if not refutation: return refutation
    if "Domain:" in refutation and "Failure Point:" in refutation:
        return refutation.strip()
    return (
        f"Domain: {domain}\n"
        f"Structure: {refutation.strip()}\n"
        f"Dropped Assumption: (unspecified)\n"
        f"Failure Point: (unspecified)\n"
        f"Minimality: true"
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--offsets", required=True)
    ap.add_argument("--feedback", required=True)
    ap.add_argument("--patches", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    kb_path, offsets_path = Path(args.kb), Path(args.offsets)
    feedback_path, patches_path, report_path = Path(args.feedback), Path(args.patches), Path(args.report)

    offsets = load_json(offsets_path)
    feedback = read_jsonl(feedback_path)
    
    patches = []
    stats = Counter()

    for fb in feedback:
        eid = fb.get("id")
        verdict = fb.get("verdict")
        try:
            entry = kb_get_entry(kb_path, offsets, eid)
        except KeyError:
            continue

        if verdict == "wrong" or verdict == "bad":
            if entry.get("kind") in ("definition", "theorem"):
                patches.append({
                    "id": eid, "op": "set_field", "path": "/refutation", "value": None,
                    "reason": "feedback:wrong; definitions/theorems should not have refutations"
                })
                stats["refutation_nullified"] += 1
        elif verdict == "weak":
            if entry.get("kind") == "counterexample_schema":
                new_ref = normalize_refutation_format(entry.get("refutation", ""), entry.get("domain", "unknown"))
                patches.append({
                    "id": eid, "op": "set_field", "path": "/refutation", "value": new_ref,
                    "reason": "feedback:weak; normalized to boundary format"
                })
                stats["refutation_normalized"] += 1

    with patches_path.open("w", encoding="utf-8") as f:
        for p in patches:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    report = {"ts": now_ts(), "patches_generated": len(patches), "stats": dict(stats)}
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[OK] Generated {len(patches)} patches.")

if __name__ == "__main__":
    main()
