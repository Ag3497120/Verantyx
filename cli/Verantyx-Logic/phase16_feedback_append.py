#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Iterable

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-龥ぁ-んァ-ヴー]+")

def tokenize(text: str) -> List[str]:
    if not text: return []
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    toks = _TOKEN_RE.findall(text)
    stop = {"the","a","an","of","and","or","in","on","to","is","are","for","with"}
    return [t for t in toks if t not in stop and len(t) >= 2]

def parse_refutation_fields(refutation: Any) -> Dict[str, str]:
    if not isinstance(refutation, str) or not refutation.strip(): return {}
    fields = {}
    for ln in refutation.splitlines():
        ln = ln.strip()
        if not ln: continue
        m = re.match(r"^([A-Za-z _-]+)\s*:\s*(.+)$", ln)
        if m:
            k = m.group(1).strip().lower()
            v = m.group(2).strip()
            fields[k] = v
    return fields

def ensure_schema(e: Dict[str, Any]) -> Dict[str, Any]:
    required = ["domain","kind","title","statement","prerequisites","yields","refutation","patterns","links"]
    out = dict(e)
    for k in required:
        if k not in out:
            out[k] = [] if k in ("prerequisites","yields","patterns","links") else None
    for k in ("prerequisites","yields","patterns","links"):
        v = out.get(k, [])
        out[k] = [str(x) for x in v] if isinstance(v, list) else [str(v)] if v else []
    return out

def domain_prefix(domain: str) -> str:
    mapping = {
        "propositional_logic": "prop", "first_order_logic": "fol", "model_theory": "mt",
        "modal_logic": "modal", "complexity_theory": "comp", "group_theory": "group",
        "ring_theory": "ring", "topology": "topo", "graph_theory": "graph", "cross_domain": "cross",
    }
    return mapping.get(domain, domain[:5])

def kind_token(kind: str) -> str:
    mapping = {"definition": "def", "axiom": "axi", "theorem": "the", "rule": "rul", "counterexample_schema": "cex"}
    return mapping.get(kind, kind[:3])

def make_prefix(domain: str, kind: str) -> str:
    return f"{domain_prefix(domain)}.{kind_token(kind)}."

def assign_ids(new_entries: List[Dict[str, Any]], meta: Dict[str, Any], existing_ids: Set[str]) -> List[Dict[str, Any]]:
    last_ids = meta.get("last_ids_by_prefix", {})
    out = []
    for e in new_entries:
        e = ensure_schema(e)
        pref = make_prefix(e["domain"], e["kind"])
        n = last_ids.get(pref, 3000 if "cex" not in pref else 1000)
        while True:
            n += 1
            eid = f"{pref}{n:05d}"
            if eid not in existing_ids: break
        last_ids[pref] = n
        e["id"] = eid
        out.append(e)
    meta["last_ids_by_prefix"] = last_ids
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--new", required=True)
    args = ap.parse_args()

    kb_path = Path(args.kb)
    meta_path = Path(args.meta)
    idx_path = Path(args.index)
    new_path = Path(args.new)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    index = json.loads(idx_path.read_text(encoding="utf-8"))
    new_entries_raw = json.loads(new_path.read_text(encoding="utf-8"))

    # Load existing IDs to avoid collision
    existing_ids = set()
    with kb_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line: existing_ids.add(json.loads(line).get("id"))

    new_entries = assign_ids(new_entries_raw, meta, existing_ids)

    with kb_path.open("a", encoding="utf-8") as f:
        for e in new_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # Incremental update logic (omitted for brevity, full update suggested for metadata consistency)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"[OK] Appended {len(new_entries)} entries. Run indexer to sync.")

if __name__ == "__main__":
    main()
