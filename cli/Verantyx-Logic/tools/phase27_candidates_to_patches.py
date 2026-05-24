#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase 27-B: Convert candidates to non-destructive patches.
"""

from __future__ import annotations
import argparse, json, os
from typing import Any, Dict, Iterable, Tuple


def iter_jsonl(path: str) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            yield i, json.loads(line)


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for obj in rows:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def make_patch(target_id: str, candidate: Dict[str, Any], note: str) -> Dict[str, Any]:
    return {
        "target_id": target_id,
        "phase": 27,
        "ops": [
            {"op": "add_unique", "path": "/patterns", "values": ["min_candidate:true"]},
            {"op": "set", "path": "/refutation_candidate", "value": candidate},
            {"op": "append_text", "path": "/patch_note", "value": note},
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max", type=int, default=0)
    args = ap.parse_args()
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    
    # Clear output file
    if os.path.exists(args.out):
        os.remove(args.out)

    n = 0
    for _, rec in iter_jsonl(args.candidates):
        tid = rec.get("target_id")
        cand = rec.get("candidate")
        if not isinstance(tid, str) or not isinstance(cand, dict):
            continue
        note = "Phase27: generated refutation_candidate (non-destructive). Use Phase25 to re-verify minimality.\n"
        write_jsonl(args.out, [make_patch(tid, cand, note)])
        n += 1
        if args.max and n >= args.max:
            break

    print(f"[OK] phase27 patches written: {n} -> {args.out}")


if __name__ == "__main__":
    main()
