#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import Any, Dict, Iterable, List, Tuple, Set

def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line: continue
            try:
                obj = json.loads(line)
            except Exception as e:
                raise ValueError(f"JSON parse error at line {i}: {e}") from e
            yield obj

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-龥ぁ-んァ-ヴー]+")

def tokenize(text: str) -> List[str]:
    if not text: return []
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    toks = _TOKEN_RE.findall(text)
    stop = {"the","a","an","of","and","or","in","on","to","is","are","for","with"}
    return [t for t in toks if t not in stop and len(t) >= 2]

def add_tokens(index: Dict[str, Set[str]], entry_id: str, tokens: Iterable[str]):
    for t in tokens: index[t].add(entry_id)

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

def max_numeric_suffix(entry_id: str) -> Tuple[str, int]:
    m = re.match(r"^(.*\D)(\d+)$", entry_id)
    if not m: return ("", -1)
    return (m.group(1), int(m.group(2)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--include-text", action="store_true")
    args = ap.parse_args()

    kb_path = Path(args.kb)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    inv: Dict[str, Set[str]] = defaultdict(set)
    meta_counter = Counter()
    domain_counter = Counter()
    kind_counter = Counter()
    last_ids: Dict[str, int] = defaultdict(lambda: -1)

    for obj in iter_jsonl(kb_path):
        eid = str(obj.get("id", "")).strip()
        if not eid: continue

        domain = str(obj.get("domain", "")).strip()
        kind = str(obj.get("kind", "")).strip()

        domain_counter[domain] += 1
        kind_counter[kind] += 1
        meta_counter["entries"] += 1

        prefix, num = max_numeric_suffix(eid)
        if num >= 0 and num > last_ids[prefix]: last_ids[prefix] = num

        add_tokens(inv, eid, [f"domain:{domain}", f"kind:{kind}"])

        for key in ("patterns", "yields", "prerequisites"):
            val = obj.get(key, [])
            if isinstance(val, list):
                for it in val:
                    s = str(it).strip()
                    if s:
                        add_tokens(inv, eid, [f"{key}:{s.lower()}"])
                        add_tokens(inv, eid, tokenize(s))
            elif isinstance(val, str):
                add_tokens(inv, eid, [f"{key}:{val.lower()}"])
                add_tokens(inv, eid, tokenize(val))

        if args.include_text:
            add_tokens(inv, eid, tokenize(str(obj.get("title", ""))))
            add_tokens(inv, eid, tokenize(str(obj.get("statement", ""))))

        if kind == "counterexample_schema":
            fields = parse_refutation_fields(obj.get("refutation", None))
            for k, v in fields.items():
                if "dropped" in k:
                    add_tokens(inv, eid, [f"dropped:{v.lower()}"])
                    add_tokens(inv, eid, tokenize(v))
                if "failure" in k:
                    add_tokens(inv, eid, [f"failure:{v.lower()}"])
                    add_tokens(inv, eid, tokenize(v))

    inv_out = {tok: sorted(list(ids)) for tok, ids in inv.items()}
    (out_dir / "kb_index.json").write_text(json.dumps(inv_out, ensure_ascii=False), encoding="utf-8")

    meta = {
        "kb_path": str(kb_path),
        "entries": meta_counter["entries"],
        "domains": domain_counter.most_common(),
        "kinds": kind_counter.most_common(),
        "last_ids_by_prefix": dict(last_ids),
        "index_tokens": len(inv_out),
        "include_text": bool(args.include_text),
    }
    (out_dir / "kb_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
