#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict, Counter

def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s: yield json.loads(s)

def write_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def get_tag_value(patterns: List[str], prefix: str) -> Optional[str]:
    for p in patterns or []:
        if isinstance(p, str) and p.startswith(prefix):
            return p[len(prefix):].strip()
    return None

def extract_field(text: str, key: str) -> str:
    # Use simpler regex to avoid nested parenthesis issues
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(key):
            content = line[len(key):].strip()
            # Capture following lines that don't start with a key
            for next_line in lines[i+1:]:
                if re.match(r"^[A-Z][A-Za-z ]+:", next_line):
                    break
                content += " " + next_line.strip()
            return content.strip()
    return ""

def canonical_score(entry: Dict[str, Any]) -> Tuple[int, int, int]:
    ref = str(entry.get("refutation", ""))
    verified = 1 if "Verified Minimality: true" in ref else 0
    wc_str = get_tag_value(entry.get("patterns", []), "wc:")
    wc = int(wc_str) if wc_str and wc_str.isdigit() else 999
    return (verified, -wc, len(entry.get("patterns", [])))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--clusters-out", required=True)
    ap.add_argument("--cards-out", required=True)
    ap.add_argument("--report-out", required=True)
    args = ap.parse_args()

    clusters = defaultdict(list)
    for e in iter_jsonl(Path(args.kb)):
        if e.get("kind") == "counterexample_schema":
            sig = get_tag_value(e.get("patterns", []), "sig:")
            if sig: clusters[sig].append(e)

    cards = []
    cluster_meta = []
    for sig, members in clusters.items():
        canon = sorted(members, key=canonical_score, reverse=True)[0]
        ref = str(canon.get("refutation", ""))
        
        card = {
            "signature": sig,
            "domain": canon.get("domain"),
            "canonical_id": canon["id"],
            "member_count": len(members),
            "dropped_assumption": extract_field(ref, "Dropped Assumption:"),
            "failure_point": extract_field(ref, "Failure Point:"),
            "suggested_actions": ["validate_minimality", "check_isomorphic_variants"]
        }
        cards.append(card)
        cluster_meta.append({"signature": sig, "canonical_id": canon["id"], "member_ids": [m["id"] for m in members]})

    write_json(Path(args.cards_out), cards)
    write_json(Path(args.clusters_out), cluster_meta)
    
    report = {"total_clusters": len(cards), "total_members": sum(len(m) for m in clusters.values())}
    write_json(Path(args.report_out), report)
    print(f"[OK] Generated {len(cards)} boundary cards.")

if __name__ == "__main__":
    main()