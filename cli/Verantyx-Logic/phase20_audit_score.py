#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import math
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict, Counter

BOUNDARY_KEYS = ["Domain:", "Structure:", "Dropped Assumption:", "Failure Point:", "Minimality:"]

def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists(): return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def simhash64(text: str) -> int:
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    v = [0]*64
    for t in tokens:
        h = hash(t) & ((1<<64)-1)
        for i in range(64):
            v[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if v[i] > 0: out |= (1<<i)
    return out

def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()

def calculate_trust(entry: Dict[str, Any], fb_stats: Dict[str, Counter], in_deg: Dict[str, int]) -> Tuple[float, Dict[str, float]]:
    eid = entry["id"]
    kind = entry.get("kind", "")
    
    # 1. Placeholder Risk
    placeholder = 1.0 if "formal definition of" in entry.get("statement", "").lower() else 0.0
    
    # 2. Robustness
    ref = str(entry.get("refutation", ""))
    robustness = sum(1 for k in BOUNDARY_KEYS if k in ref) / len(BOUNDARY_KEYS) if kind == "counterexample_schema" else 0.5
    
    # 3. Connectivity
    conn = 1.0 - math.exp(-in_deg.get(eid, 0) / 5.0)
    
    # 4. Feedback
    fb_c = fb_stats.get(eid, Counter())
    total_fb = sum(fb_c.values())
    fb_val = (fb_c["good"] - fb_c["bad"]*1.5) / total_fb if total_fb > 0 else 0.0
    fb_score = 1.0 / (1.0 + math.exp(-fb_val)) # sigmoid
    
    # Weights
    score = (robustness * 0.4 + conn * 0.3 + fb_score * 0.3) * (1.0 - placeholder * 0.5)
    return round(score * 100, 2), {"robustness": robustness, "connectivity": conn, "feedback": fb_score, "placeholder": placeholder}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--feedback", default="")
    ap.add_argument("--scores", required=True)
    ap.add_argument("--dups", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    kb_path = Path(args.kb)
    entries = read_jsonl(kb_path)
    fb_rows = read_jsonl(Path(args.feedback)) if args.feedback else []
    
    fb_stats = defaultdict(Counter)
    for r in fb_rows: fb_stats[r["id"]][r["verdict"]] += 1
    
    in_deg = Counter()
    for e in entries:
        for link in e.get("links", []): in_deg[link] += 1
    
    # Audit and Duplicate Detection
    scores = []
    hashes = defaultdict(list)
    for e in entries:
        trust, signals = calculate_trust(e, fb_stats, in_deg)
        scores.append({"id": e["id"], "trust": trust, "signals": signals})
        
        h = simhash64(e.get("statement", "") + str(e.get("refutation", "")))
        hashes[h >> 48].append((e["id"], h)) # Group by prefix for speed

    dups = []
    for bucket in hashes.values():
        for i in range(len(bucket)):
            for j in range(i+1, len(bucket)):
                if hamming(bucket[i][1], bucket[j][1]) < 5:
                    dups.append([bucket[i][0], bucket[j][0]])

    with Path(args.scores).open("w") as f:
        for s in scores: f.write(json.dumps(s) + "\n")
    
    report = {
        "ts": now_ts(),
        "total_entries": len(entries),
        "duplicate_clusters": len(dups),
        "low_trust_count": sum(1 for s in scores if s["trust"] < 35),
        "avg_trust": round(sum(s["trust"] for s in scores) / len(scores), 2)
    }
    Path(args.dups).write_text(json.dumps(dups, indent=2))
    Path(args.report).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
