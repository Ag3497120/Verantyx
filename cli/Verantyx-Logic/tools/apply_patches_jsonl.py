#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, shutil, os
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
    ap.add_argument("--backup", action="store_true")
    args = ap.parse_args()

    kb = read_jsonl(args.kb)
    patches = read_jsonl(args.patches)

    if args.backup:
        shutil.copy2(args.kb, args.kb + ".bak")

    index = {e.get("id"): e for e in kb}

    applied = 0
    for p in patches:
        if p.get("op") != "patch":
            continue
        eid = p.get("id")
        if eid not in index:
            continue
        e = index[eid]
        patch = p.get("patch", {})

        # patterns_add
        add = patch.get("patterns_add", [])
        if add:
            pats = e.get("patterns") or []
            for a in add:
                if a not in pats:
                    pats.append(a)
            e["patterns"] = pats

        # patch_note
        note = patch.get("patch_note")
        if note:
            # Append if existing
            current_note = e.get("patch_note", "")
            if current_note:
                e["patch_note"] = current_note + " | " + note
            else:
                e["patch_note"] = note

        # allow updating refutation_candidate, etc.
        for k, v in patch.items():
            if k in ("patterns_add", "patch_note"):
                continue
            e[k] = v
        
        applied += 1

    write_jsonl(args.kb, kb)
    print(f"[OK] applied patches={applied}")

if __name__ == "__main__":
    main()
