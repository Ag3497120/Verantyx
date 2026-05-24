#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import shutil
from typing import Any, Dict, List

def read_jsonl(path: str) -> List[Dict[str, Any]]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--patches", required=True)
    ap.add_argument("--backup", default="")
    args = ap.parse_args()

    kb = read_jsonl(args.kb)
    patches = read_jsonl(args.patches)

    by_id = {}
    for i, e in enumerate(kb):
        eid = e.get("id")
        if isinstance(eid, str):
            by_id[eid] = i

    if args.backup:
        os.makedirs(os.path.dirname(args.backup), exist_ok=True)
        write_jsonl(args.backup, kb)
        print(f"[OK] backup written: {args.backup}")

    applied = 0
    missing = 0

    for p in patches:
        if p.get("op") != "update":
            continue
        pid = p.get("id")
        if not isinstance(pid, str) or pid not in by_id:
            missing += 1
            continue
        idx = by_id[pid]
        sets = p.get("set", {})
        if isinstance(sets, dict):
            for k, v in sets.items():
                kb[idx][k] = v
            applied += 1

    write_jsonl(args.kb, kb)
    print(f"[OK] applied={applied} missing={missing} -> {args.kb}")

if __name__ == "__main__":
    main()
