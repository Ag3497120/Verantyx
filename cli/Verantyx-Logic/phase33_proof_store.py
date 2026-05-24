# phase33_proof_store.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import time
import hashlib

PROOF_PATH = Path("avh_math/db/proof_library.jsonl")

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

def make_problem_key(query: str) -> str:
    """
    query を安定キー化。将来、Spec/ASTがあるならそっちに置換推奨。
    """
    q = " ".join(query.strip().split())
    return f"q_{_hash(q)}"

def append_proof(entry: Dict[str, Any], path: Path = PROOF_PATH) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)

    # 必須キー補完
    entry = dict(entry)
    entry.setdefault("id", f"proof_{int(time.time()*1000)}_{_hash(json.dumps(entry, ensure_ascii=False))}")
    entry.setdefault("created_at", _now_iso())
    entry.setdefault("kind", "proof")  # proof | sketch | counterexample | note
    entry.setdefault("status", "user_added")  # user_added | verified | needs_review
    entry.setdefault("kb_links", [])   # KB entry ids (axiom/theorem/rule/cex...)
    entry.setdefault("text", "")
    entry.setdefault("lang", "ja")

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry

def read_all(path: Path = PROOF_PATH, limit: int = 2000) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out

def search_proofs(
    query: str,
    problem_key: Optional[str] = None,
    path: Path = PROOF_PATH,
    limit: int = 50
) -> List[Dict[str, Any]]:
    q = query.lower().strip()
    all_items = read_all(path=path, limit=100000)

    scored = []
    for p in all_items:
        if problem_key and p.get("problem_key") != problem_key:
            continue
        hay = " ".join([
            str(p.get("title", "")),
            str(p.get("text", "")),
            " ".join(p.get("kb_links") or []),
            str(p.get("domain", "")),
        ]).lower()
        if q and q not in hay:
            continue
        scored.append(p)

    # 新しい順
    scored.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return scored[:limit]

