#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-龥ぁ-んァ-ヴー]+")

def tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    toks = _TOKEN_RE.findall(text)
    stop = {"the","a","an","of","and","or","in","on","to","is","are","for","with"}
    return [t for t in toks if t not in stop and len(t) >= 2]

def load_index(path: Path) -> Dict[str, List[str]]:
    return json.loads(path.read_text(encoding="utf-8"))

def retrieve_candidates(index: Dict[str, List[str]], query: str, topk: int = 200) -> List[Tuple[str, int]]:
    toks = tokenize(query)
    freq: Dict[str, int] = {}
    for t in toks:
        ids = index.get(t, [])
        for eid in ids:
            freq[eid] = freq.get(eid, 0) + 1

    explicit = re.findall(r"(domain:[a-z0-9_]+|kind:[a-z_]+)", query.lower())
    if explicit:
        cand_set: Set[str] = set(freq.keys()) if freq else set()
        for ex in explicit:
            s = set(index.get(ex, []))
            cand_set = (cand_set & s) if cand_set else s
        freq = {eid: freq.get(eid, 0) for eid in cand_set}

    return sorted(freq.items(), key=lambda x: x[1], reverse=True)[:topk]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--topk", type=int, default=200)
    args = ap.parse_args()

    idx = load_index(Path(args.index))
    ranked = retrieve_candidates(idx, args.query, topk=args.topk)
    print(json.dumps({"query": args.query, "candidates": ranked}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
