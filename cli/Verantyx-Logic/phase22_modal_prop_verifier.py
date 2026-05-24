#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Set
from itertools import product

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s: out.append(json.loads(s))
    return out

def write_jsonl(path: Path, rows: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

def extract_field(text: str, key: str) -> str:
    # Escape the key and use a more stable boundary pattern
    pattern = rf"(?m)^{re.escape(key)}\s*(.*?)(?=\n\w[\w\s-]*:|\Z)"
    m = re.search(pattern, text, flags=re.DOTALL)
    return (m.group(1).strip() if m else "").strip()

def count_modal_worlds(structure: str) -> Optional[int]:
    m = re.search(r"W\s*=\s*\{([^}]*)\}", structure)
    if not m: m = re.search(r"W=\{([^}]*)\}", structure)
    if not m: return None
    return len([x.strip() for x in m.group(1).split(",") if x.strip()])

def infer_modal_witness(dropped: str) -> Optional[str]:
    d = dropped.lower()
    if "reflex" in d: return "([]p -> p)"
    if "transit" in d: return "([]p -> [][]p)"
    if "euclid" in d: return "(<>p -> []<>p)"
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--patches-out", required=True)
    ap.add_argument("--report-out", required=True)
    args = ap.parse_args()

    kb = read_jsonl(Path(args.kb))
    patches = []
    stats = {"processed": 0, "verified_true": 0, "verified_false": 0, "unverified": 0}

    for e in kb:
        if e.get("kind") != "counterexample_schema": continue
        
        ref = str(e.get("refutation", ""))
        dropped = extract_field(ref, "Dropped Assumption:")
        domain = e.get("domain", "")
        
        status = "unverified"
        if domain == "modal_logic":
            witness = infer_modal_witness(dropped)
            n_worlds = count_modal_worlds(extract_field(ref, "Structure:"))
            if witness and n_worlds is not None:
                # 簡易的な最小性判定（n_worlds=1でAxiom T失敗などは最小）
                if n_worlds == 1: 
                    status = "true"
                    stats["verified_true"] += 1
                else:
                    status = "unverified" # 本来はここでbrute-force
                    stats["unverified"] += 1
            else:
                stats["unverified"] += 1
        else:
            stats["unverified"] += 1

        new_ref = ref.rstrip() + f"\nVerified Minimality: {status}"
        patches.append({
            "id": e["id"], "op": "set_field", "path": "/refutation", "value": new_ref,
            "reason": "phase22:verified_minimality"
        })
        stats["processed"] += 1

    write_jsonl(Path(args.patches_out), patches)
    Path(args.report_out).write_text(json.dumps(stats, indent=2))
    print(f"[OK] Processed {stats['processed']} entries.")

if __name__ == "__main__":
    main()
