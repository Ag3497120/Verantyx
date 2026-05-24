#!/usr/bin/env python3
# tools/phase28_3_make_patches.py

import argparse, json, os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out_patches", required=True)
    ap.add_argument("--note", default="Phase 28.3 verifier run")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out_patches), exist_ok=True)

    wrote = 0
    with open(args.results, "r", encoding="utf-8") as f, open(args.out_patches, "w", encoding="utf-8") as w:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            _id = r.get("id")
            status = r.get("status", "unknown")

            if status == "verified":
                tag = "min_verified:true"
            elif status == "refuted":
                tag = "min_verified:false"
            else:
                tag = "min_verified:unknown"

            patch = {
                "id": _id,
                "op": "merge",
                "fields": {
                    "patterns__append": [tag],
                    "patch_note__append": f"{args.note} => {tag} ({r.get('reason')})",
                },
            }
            w.write(json.dumps(patch, ensure_ascii=False) + "\n")
            wrote += 1

    print(f"[OK] patches={wrote} -> {args.out_patches}")

if __name__ == "__main__":
    main()

