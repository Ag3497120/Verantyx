#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Dict, Any, List

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists(): return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--patches", required=True)
    ap.add_argument("--backup", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()

    kb_path, patches_path = Path(args.kb), Path(args.patches)
    backup_path, log_path = Path(args.backup), Path(args.log)

    patches = read_jsonl(patches_path)
    if not patches:
        print("No patches to apply.")
        return

    # Backup
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(kb_path, backup_path)
    print(f"Backup created: {backup_path}")

    # Load and Patch
    kb_data = {}
    ids_order = []
    with kb_path.open("r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            eid = obj["id"]
            kb_data[eid] = obj
            ids_order.append(eid)

    applied = 0
    for p in patches:
        eid = p["id"]
        if eid in kb_data:
            if p["op"] == "set_field":
                key = p["path"].lstrip("/")
                kb_data[eid][key] = p["value"]
                applied += 1

    # Save
    with kb_path.open("w", encoding="utf-8") as f:
        for eid in ids_order:
            f.write(json.dumps(kb_data[eid], ensure_ascii=False) + "\n")

    log = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "applied": applied, "total": len(patches)}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log) + "\n")

    print(f"[OK] Applied {applied} patches to {kb_path}")

if __name__ == "__main__":
    main()
