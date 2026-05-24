#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple Patch Applier for Phase 26
"""

import json
import shutil
from pathlib import Path

def apply_patches(kb_path: Path, patches_path: Path):
    print(f"Applying patches from {patches_path} to {kb_path}...")
    
    # Load patches
    patches = {}
    with patches_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                p = json.loads(line)
                patches[p["target_id"]] = p

    # Backup KB
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
                    if op["op"] == "add_unique":
                        current = set(entry.get("patterns", []))
                        for v in op["values"]:
                            current.add(v)
                        entry["patterns"] = list(current)
                    elif op["op"] == "set":
                        # Only handle top-level set for now as per Phase 26 spec
                        key = op["path"].lstrip("/")
                        entry[key] = op["value"]
                applied_count += 1
            
            new_lines.append(json.dumps(entry, ensure_ascii=False))

    with kb_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")

    print(f"Applied patches to {applied_count} entries.")

if __name__ == "__main__":
    kb = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")
    patches = Path("/Users/motonishikoudai/avh_math/avh_math/db/phase26_patches.jsonl")
    apply_patches(kb, patches)
