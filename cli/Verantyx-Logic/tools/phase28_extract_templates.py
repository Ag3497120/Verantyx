#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# tools/phase28_extract_templates.py

import argparse, json
from collections import defaultdict, Counter

TAG_TRUE = "min_verified:true"

def has_tag(entry, tag: str) -> bool:
    pats = entry.get("patterns", [])
    return isinstance(pats, list) and tag in pats

def parse_refutation_struct(ref):
    """
    Refutation is expected to be a dict. If it's stored as a string, attempt to parse if JSON-like,
    or create a basic object if not.
    """
    if isinstance(ref, dict):
        return ref
    # If ref is a string, it might be a description or encoded JSON.
    # For Phase 28, we primarily rely on struct objects (like refutation_candidate).
    return None

def boundary_signature(entry, ref_obj):
    """
    A stable signature key for clustering.
    Prefer Dropped Assumption / Failure Point.
    """
    domain = entry.get("domain", "unknown")
    
    # Try multiple casing styles
    dropped = ref_obj.get("dropped_assumption") or ref_obj.get("DroppedAssumption") or ref_obj.get("Dropped Assumption")
    failure = ref_obj.get("failure_point") or ref_obj.get("FailurePoint") or ref_obj.get("Failure Point")

    dropped = str(dropped) if dropped else "unknown_dropped"
    failure = str(failure) if failure else "unknown_failure"

    # Use title prefix as a hint if generic
    title = entry.get("title", "")
    return f"{domain}||{dropped}||{failure}||{title[:40]}"

def normalize_template(ref_obj):
    """
    Turn a verified refutation into a reusable template.
    """
    t = {}
    
    # Normalize keys
    keys_map = {
        "domain": ["domain", "Domain"],
        "dropped_assumption": ["dropped_assumption", "DroppedAssumption", "Dropped Assumption"],
        "failure_point": ["failure_point", "FailurePoint", "Failure Point"]
    }
    
    for norm_k, alts in keys_map.items():
        for alt in alts:
            if alt in ref_obj:
                t[norm_k] = ref_obj[alt]
                break

    # Preserve structure sketch / Witness
    struct = None
    if "structure" in ref_obj and isinstance(ref_obj["structure"], dict):
        struct = ref_obj["structure"]
    elif "Witness" in ref_obj:
        struct = ref_obj["Witness"]
    elif "witness" in ref_obj:
        struct = ref_obj["witness"]
    elif "candidate" in ref_obj and isinstance(ref_obj["candidate"], dict):
         # Nested candidate case
         cand = ref_obj["candidate"]
         if "Witness" in cand: struct = cand["Witness"]
         elif "witness" in cand: struct = cand["witness"]

    if struct:
        t["structure_schema"] = struct
    else:
        t["structure_schema"] = {"note": "missing structure_schema", "original": str(ref_obj)[:100]}

    if "minimality" in ref_obj:
        t["minimality"] = ref_obj["minimality"]

    return t

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True, help="foundation_kb.jsonl")
    ap.add_argument("--out", required=True, help="boundary_templates.json")
    ap.add_argument("--max_per_sig", type=int, default=5)
    args = ap.parse_args()

    buckets = defaultdict(list)
    stats = Counter()

    with open(args.kb, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)

            if not has_tag(entry, TAG_TRUE):
                continue

            # Prioritize refutation_candidate as it's the verified struct from Phase 27
            ref = entry.get("refutation_candidate") or entry.get("refutation")
            ref_obj = parse_refutation_struct(ref)
            
            if not ref_obj:
                stats["skip_no_ref_obj"] += 1
                continue

            sig = boundary_signature(entry, ref_obj)
            if len(buckets[sig]) >= args.max_per_sig:
                stats["skip_bucket_full"] += 1
                continue

            buckets[sig].append({
                "id": entry.get("id"),
                "template": normalize_template(ref_obj),
            })
            stats["kept"] += 1

    # Build canonical template per signature
    templates = {}
    for sig, items in buckets.items():
        # Pick first as canonical
        canonical = items[0]["template"]
        templates[sig] = {
            "signature": sig,
            "count": len(items),
            "examples": [it["id"] for it in items],
            "template": canonical,
        }

    out_obj = {
        "tag": TAG_TRUE,
        "num_signatures": len(templates),
        "templates": templates,
        "stats": dict(stats),
    }

    import os
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as w:
        json.dump(out_obj, w, ensure_ascii=False, indent=2)

    print(f"[OK] wrote {args.out} signatures={len(templates)} kept={stats['kept']}")

if __name__ == "__main__":
    main()
