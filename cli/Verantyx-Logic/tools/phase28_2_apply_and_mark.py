#!/usr/bin/env python3
# tools/phase28_2_apply_and_mark.py

import argparse, json, shutil, time

def load_patches(path):
    patches = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    patches.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return patches

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--patches", required=True)
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--out", default=None, help="output kb path; default overwrite")
    args = ap.parse_args()

    kb_in = args.kb
    kb_out = args.out or args.kb

    if args.backup and kb_in == kb_out:
        ts = time.strftime("%Y%m%d-%H%M%S")
        bak = kb_in + f".bak.{ts}"
        shutil.copy2(kb_in, bak)
        print("[OK] backup:", bak)

    patches = load_patches(args.patches)
    patch_map = {}
    for p in patches:
        # Phase 28.2 patches use "id" (merge format) or "target_id" (ops format)
        # The generator uses "id" and "merge". We'll handle both basic cases if needed,
        # but primarily support the generator's output.
        pid = p.get("id") or p.get("target_id")
        if pid:
            patch_map[pid] = p

    applied = 0

    import os
    temp_out = kb_out + ".tmp"

    with open(kb_in, "r", encoding="utf-8") as f, open(temp_out, "w", encoding="utf-8") as w:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            pid = e.get("id")
            if pid in patch_map:
                p = patch_map[pid]
                
                # Handle "merge" op
                if p.get("op") == "merge":
                    fields = p.get("fields", {})
                    for k, v in fields.items():
                        e[k] = v
                
                # Handle "ops" list (legacy/generic support)
                elif "ops" in p:
                     for op in p["ops"]:
                        path_key = op["path"].lstrip("/")
                        if op["op"] == "add_unique":
                             curr = set(e.get(path_key, []))
                             for val in op["values"]:
                                 curr.add(val)
                             e[path_key] = list(curr)
                        elif op["op"] == "set":
                             e[path_key] = op["value"]
                        elif op["op"] == "append_text":
                             e[path_key] = str(e.get(path_key, "")) + op["value"]

                # Mark target
                pats = e.get("patterns", [])
                if not isinstance(pats, list):
                    pats = []
                if "targeted_by:phase28.2" not in pats:
                    pats.append("targeted_by:phase28.2")
                e["patterns"] = pats
                
                applied += 1
            w.write(json.dumps(e, ensure_ascii=False) + "\n")

    os.replace(temp_out, kb_out)
    print(f"[OK] applied={applied} -> {kb_out}")

if __name__ == "__main__":
    main()
