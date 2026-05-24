#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", required=True)
    ap.add_argument("--patches", required=True)
    ap.add_argument("--threshold", type=float, default=35.0)
    args = ap.parse_args()

    patches = []
    with Path(args.scores).open("r") as f:
        for line in f:
            r = json.loads(line)
            if r["trust"] < args.threshold:
                patches.append({
                    "id": r["id"],
                    "op": "set_field", # Simplified for now, using set_field to add review tag in logic
                    "path": "/patterns",
                    "value": ["needs_review"], # In a real scenario, we'd append to existing patterns
                    "reason": f"Trust score {r['trust']} is below threshold {args.threshold}"
                })

    with Path(args.patches).open("w") as f:
        for p in patches:
            f.write(json.dumps(p) + "\n")
    print(f"[OK] Generated {len(patches)} review patches.")

if __name__ == "__main__":
    main()

