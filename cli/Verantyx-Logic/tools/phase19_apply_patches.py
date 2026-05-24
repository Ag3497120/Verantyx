#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple Patch Applier for Phase 19/27
Supports: add_unique, set, append_text
"""

import argparse
import json
import shutil
import os
from pathlib import Path

def apply_patches(kb_path: Path, patches_path: Path, backup: bool = False):
    print(f"Applying patches from {patches_path} to {kb_path}...")
    
    # Load patches
    patches = {}
    with patches_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    p = json.loads(line)
                    patches[p["target_id"]] = p
                except json.JSONDecodeError:
                    continue

    if not patches:
        print("No patches found.")
        return

    # Backup KB
    if backup:
        backup_path = kb_path.with_suffix(".jsonl.bak")
        shutil.copy(kb_path, backup_path)
        print(f"Backup created at {backup_path}")

    applied_count = 0
    new_lines = []
    
    with kb_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            eid = entry.get("id")
            
            if eid in patches:
                patch = patches[eid]
                for op in patch["ops"]:
                    op_type = op["op"]
                    path_key = op["path"].lstrip("/")
                    
                    if op_type == "add_unique":
                        current = set(entry.get(path_key, []))
                        for v in op["values"]:
                            current.add(v)
                        entry[path_key] = list(current)
                    
                    elif op_type == "set":
                        entry[path_key] = op["value"]
                        
                    elif op_type == "append_text":
                        current_val = entry.get(path_key, "")
                        if not isinstance(current_val, str):
                             current_val = str(current_val)
                        entry[path_key] = current_val + op["value"]
                        
                applied_count += 1
            
            new_lines.append(json.dumps(entry, ensure_ascii=False))

    with kb_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")

    print(f"Applied patches to {applied_count} entries.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--patches", required=True)
    ap.add_argument("--backup", action="store_true")
    args = ap.parse_args()
    
    apply_patches(Path(args.kb), Path(args.patches), args.backup)

if __name__ == "__main__":
    main()
