#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase15: Boundary Navigation (integrates Phase14 "compression + boundary graphization")
"""

from __future__ import annotations
import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from collections import defaultdict, Counter

# ----------------------------
# Phase14 format assumptions
# ----------------------------

_FIELD_ALIASES = {
    "domain": ["domain"],
    "structure": ["structure"],
    "dropped_assumption": ["dropped assumption", "dropped_assumption", "droppedassumption", "assumption dropped"],
    "failure_point": ["failure point", "failure_point", "failurepoint"],
    "minimality": ["minimality", "minimal"],
}

def _normalize_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.strip().lower()).strip()

def parse_refutation_phase14(refutation: str) -> Dict[str, str]:
    if not refutation or not isinstance(refutation, str):
        return {}
    lines = [ln.strip() for ln in refutation.splitlines() if ln.strip()]
    kv = {}
    for ln in lines:
        m = re.match(r"^([A-Za-z _-]+)\s*:\s*(.+)$", ln)
        if m:
            k = _normalize_key(m.group(1))
            v = m.group(2).strip()
            kv[k] = v
    out = {}
    for canonical, aliases in _FIELD_ALIASES.items():
        for a in aliases:
            ak = _normalize_key(a)
            for k, v in kv.items():
                if ak == k or ak in k:
                    out[canonical] = v
                    break
            if canonical in out:
                break
    return out

@dataclass(frozen=True)
class BoundarySignature:
    domain: str
    dropped_assumption: str
    failure_point: str
    structure_fingerprint: str

    def key(self) -> str:
        return f"{self.domain}||{self.dropped_assumption}||{self.failure_point}||{self.structure_fingerprint}"

def fingerprint_structure(structure_text: str) -> str:
    if not structure_text:
        return "structure:unknown"
    s = structure_text.lower()
    s = re.sub(r"\s+", " ", s).strip()
    tokens = re.findall(r"[a-z0-9_]+|[∈⊨¬∧∨→↔∀∃=<>≤≥]", s)
    stop = {"the", "a", "an", "of", "and", "or", "in", "on", "with", "for", "to", "is", "are"}
    tokens = [t for t in tokens if t not in stop]
    tokens = tokens[:60]
    return " ".join(tokens) if tokens else "structure:unknown"

@dataclass
class KBEntry:
    id: str
    domain: str
    kind: str
    title: str
    statement: str
    prerequisites: List[str]
    yields: List[str]
    refutation: Optional[str]
    patterns: List[str]
    links: List[str]

def load_jsonl(path: Path) -> List[KBEntry]:
    entries: List[KBEntry] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line: continue
            obj = json.loads(line)
            def _get_list(key: str) -> List[str]:
                v = obj.get(key, [])
                if v is None: return []
                return v if isinstance(v, list) else [str(v)]
            entries.append(KBEntry(
                id=str(obj.get("id", "")), domain=str(obj.get("domain", "")),
                kind=str(obj.get("kind", "")), title=str(obj.get("title", "")),
                statement=str(obj.get("statement", "")), prerequisites=_get_list("prerequisites"),
                yields=_get_list("yields"), refutation=obj.get("refutation", None),
                patterns=_get_list("patterns"), links=_get_list("links"),
            ))
    return entries

def build_boundary_signatures(entries: List[KBEntry]) -> Dict[str, BoundarySignature]:
    sigs: Dict[str, BoundarySignature] = {}
    for e in entries:
        if e.kind != "counterexample_schema": continue
        fields = parse_refutation_phase14(e.refutation or "")
        sigs[e.id] = BoundarySignature(
            domain=fields.get("domain", e.domain or "unknown"),
            dropped_assumption=fields.get("dropped_assumption", "unknown"),
            failure_point=fields.get("failure_point", "unknown"),
            structure_fingerprint=fingerprint_structure(fields.get("structure", ""))
        )
    return sigs

def build_graph(entries: List[KBEntry], sigs: Dict[str, BoundarySignature]) -> Dict[str, Any]:
    cex_ids = set(sigs.keys())
    canonical_of: Dict[str, str] = {}
    for eid in cex_ids:
        e = next((x for x in entries if x.id == eid), None)
        canon = next((lk for lk in e.links if lk in cex_ids), None) if e else None
        canonical_of[eid] = canon or eid

    clusters = defaultdict(list)
    for eid, canon in canonical_of.items():
        clusters[canon].append(eid)

    return {
        "meta": {"num_entries": len(entries), "num_counterexamples": len(cex_ids), "num_canonical": len(clusters)},
        "canonical_clusters": {k: {"members": v, "signature": asdict(sigs[k]) if k in sigs else None} for k, v in clusters.items()}
    }

def score_entry_against_query(e: KBEntry, query: str) -> float:
    q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not q_tokens: return 0.0
    def token_overlap(text: str) -> int:
        t_tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
        return len(q_tokens.intersection(t_tokens))
    
    score = 0.0
    score += 1.5 * min(5, token_overlap(e.title))
    score += 1.0 * min(8, token_overlap(e.statement))
    for t in (e.yields + e.prerequisites):
        if token_overlap(t) > 0: score += 1.2
    return score

def navigate_boundaries(entries: List[KBEntry], sigs: Dict[str, BoundarySignature], query: str, topk: int = 20, candidate_ids: Optional[Set[str]] = None) -> Dict[str, Any]:
    scored_list: List[Tuple[float, KBEntry]] = []
    for e in entries:
        if candidate_ids is not None and e.id not in candidate_ids:
            continue
        s = score_entry_against_query(e, query)
        if s > 0:
            scored_list.append((s, e))
    
    scored_list.sort(key=lambda x: x[0], reverse=True)
    top = scored_list[:topk]
    
    nearby_cex = []
    for _, e in top:
        if e.kind == "counterexample_schema" and e.id in sigs: nearby_cex.append(e.id)
        for lk in e.links:
            if lk in sigs: nearby_cex.append(lk)
            
    dropped_counter = Counter()
    failure_counter = Counter()
    for eid in nearby_cex:
        sig = sigs.get(eid)
        if sig:
            dropped_counter[sig.dropped_assumption] += 1
            failure_counter[sig.failure_point] += 1

    return {
        "query": query,
        "top_hits": [{"score": s, "id": e.id, "kind": e.kind, "title": e.title} for s, e in top],
        "boundary_risks": {
            "dropped_assumption_hotspots": dropped_counter.most_common(15),
            "failure_point_hotspots": failure_counter.most_common(15),
        },
        "recommendation": [
            "Dropped Assumption上位から反例探索を優先",
            "Failure Point上位がcategoricityならモデル理論クラスタをチェック"
        ]
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--build-graph", action="store_true")
    ap.add_argument("--graph-out", default=None)
    ap.add_argument("--query", default=None)
    ap.add_argument("--topk", type=int, default=20)
    ap.add_argument("--report-out", default=None)
    args = ap.parse_args()

    kb_path = Path(args.kb)
    entries = load_jsonl(kb_path)
    sigs = build_boundary_signatures(entries)

    if args.build_graph:
        graph = build_graph(entries, sigs)
        if args.graph_out: Path(args.graph_out).write_text(json.dumps(graph, ensure_ascii=False, indent=2))
        else: print(json.dumps(graph, ensure_ascii=False, indent=2))

    if args.query:
        report = navigate_boundaries(entries, sigs, args.query, topk=args.topk)
        if args.report_out: Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        else: print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()