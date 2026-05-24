#!/usr/bin/env python3
# tools/phase28_2_coverage_report.py

import argparse, json
from collections import Counter

def has_pattern(entry, pat: str) -> bool:
    pats = entry.get("patterns", [])
    return isinstance(pats, list) and pat in pats

def any_prefix(entry, prefix: str) -> bool:
    pats = entry.get("patterns", [])
    if not isinstance(pats, list):
        return False
    return any(p.startswith(prefix) for p in pats)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    c = Counter()

    with open(args.kb, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)

            kind = e.get("kind", "")
            if kind != "counterexample_schema":
                continue

            c["cex_total"] += 1

            if any_prefix(e, "min_verified:"):
                c["cex_has_min_verified_tag"] += 1
                if has_pattern(e, "min_verified:true"):
                    c["cex_min_true"] += 1
                elif has_pattern(e, "min_verified:false"):
                    c["cex_min_false"] += 1
                elif has_pattern(e, "min_verified:unknown"):
                    c["cex_min_unknown"] += 1
            else:
                c["cex_no_min_verified_tag"] += 1

            if has_pattern(e, "needs_review"):
                c["cex_needs_review"] += 1

            if "refutation_candidate" in e:
                c["cex_has_candidate"] += 1
            else:
                c["cex_no_candidate"] += 1

            ref = e.get("refutation")
            if ref is None:
                c["cex_refutation_null"] += 1
            elif isinstance(ref, dict):
                # check minimal required keys of your Phase D/E format
                keys = set(ref.keys())
                req = {"domain", "structure", "dropped_assumption", "failure_point"}
                if req.issubset(keys):
                    c["cex_refutation_struct_ok"] += 1
                else:
                    c["cex_refutation_struct_weak"] += 1
            else:
                c["cex_refutation_non_struct"] += 1

    import os
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out = dict(c)
    with open(args.out, "w", encoding="utf-8") as w:
        json.dump(out, w, ensure_ascii=False, indent=2)

    print("[OK] wrote", args.out)
    for k, v in c.most_common():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()
