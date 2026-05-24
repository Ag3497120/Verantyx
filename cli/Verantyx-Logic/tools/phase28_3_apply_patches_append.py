#!/usr/bin/env python3
# tools/phase28_3_apply_patches_append.py

import argparse, json, shutil, time, os

def load_patch_map(path):
    m = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    p = json.loads(line)
                    m[p["id"]] = p
                except json.JSONDecodeError:
                    continue
    return m

def ensure_list(x):
    return x if isinstance(x, list) else []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--patches", required=True)
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    kb_in = args.kb
    kb_out = args.out or args.kb

    if args.backup and kb_in == kb_out:
        ts = time.strftime("%Y%m%d-%H%M%S")
        bak = kb_in + f".bak.{ts}"
        shutil.copy2(kb_in, bak)
        print("[OK] backup:", bak)

    patch_map = load_patch_map(args.patches)
    applied = 0

    temp_out = kb_out + ".tmp"
    with open(kb_in, "r", encoding="utf-8") as f, open(temp_out, "w", encoding="utf-8") as w:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            pid = e.get("id")
            p = patch_map.get(pid)
            if not p:
                w.write(json.dumps(e, ensure_ascii=False) + "\n")
                continue

            fields = p.get("fields", {})
            
            # 1. Handle patterns__append
            if "patterns__append" in fields:
                pats = ensure_list(e.get("patterns", []))
                # Remove existing min_verified:* if we are appending a new one
                pats = [x for x in pats if not (isinstance(x, str) and x.startswith("min_verified:"))]
                add_pats = fields["patterns__append"]
                for x in add_pats:
                    if x not in pats:
                        pats.append(x)
                e["patterns"] = pats

            # 2. Handle patch_note__append
            if "patch_note__append" in fields:
                pn = e.get("patch_note", "")
                if pn is None: pn = ""
                add_note = fields["patch_note__append"]
                if pn:
                    pn = pn + " | " + add_note
                else:
                    pn = add_note
                e["patch_note"] = pn

            # 3. Merge normal fields
            for k, v in fields.items():
                if k in ("patterns__append", "patch_note__append"):
                    continue
                e[k] = v

            applied += 1
            w.write(json.dumps(e, ensure_ascii=False) + "\n")

    os.replace(temp_out, kb_out)
    print(f"[OK] applied={applied} -> {kb_out}")

if __name__ == "__main__":
    main()
