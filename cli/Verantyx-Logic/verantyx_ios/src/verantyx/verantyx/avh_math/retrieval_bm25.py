# avh_math/retrieval_bm25.py
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Iterable, Any, Optional

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|[\u3040-\u30ff\u4e00-\u9fff]+|[0-9]+")

def tokenize(text: str) -> List[str]:
    if not text:
        return []
    # Lowercase for latin tokens; keep japanese chunks as-is
    toks = TOKEN_RE.findall(text)
    out = []
    for t in toks:
        if re.match(r"^[A-Za-z_]", t):
            out.append(t.lower())
        else:
            out.append(t)
    return out

@dataclass
class BM25Config:
    k1: float = 1.2
    b: float = 0.75
    min_token_len: int = 1
    max_tokens_per_doc: int = 2000

class KBIndex:
    """
    Lightweight BM25 index for foundation_kb.jsonl.
    Stores:
      - postings: token -> list[(doc_id, tf)]
      - doc_len: doc_id -> length
      - doc_meta: doc_id -> {domain, kind, title}
      - N, avgdl
    """

    def __init__(self, cfg: BM25Config | None = None):
        self.cfg = cfg or BM25Config()
        self.postings: Dict[str, List[Tuple[str, int]]] = {}
        self.doc_len: Dict[str, int] = {}
        self.doc_meta: Dict[str, Dict[str, Any]] = {}
        self.N: int = 0
        self.avgdl: float = 0.0

    def add_doc(self, doc_id: str, text: str, meta: Dict[str, Any]) -> None:
        toks = tokenize(text)[: self.cfg.max_tokens_per_doc]
        toks = [t for t in toks if len(t) >= self.cfg.min_token_len]
        if not toks:
            # still register doc
            self.doc_len[doc_id] = 0
            self.doc_meta[doc_id] = meta
            self.N += 1
            return

        tf_map: Dict[str, int] = {}
        for t in toks:
            tf_map[t] = tf_map.get(t, 0) + 1

        for tok, tf in tf_map.items():
            self.postings.setdefault(tok, []).append((doc_id, tf))

        self.doc_len[doc_id] = len(toks)
        self.doc_meta[doc_id] = meta
        self.N += 1

    def finalize(self) -> None:
        if self.N == 0:
            self.avgdl = 0.0
        else:
            self.avgdl = sum(self.doc_len.values()) / float(self.N)

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "cfg": self.cfg.__dict__,
            "N": self.N,
            "avgdl": self.avgdl,
            "doc_len": self.doc_len,
            "doc_meta": self.doc_meta,
            # postings can be big; store as dict[token] -> list[[doc_id, tf],...]
            "postings": {k: [[d, tf] for (d, tf) in v] for k, v in self.postings.items()},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    @staticmethod
    def load(path: str) -> "KBIndex":
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        idx = KBIndex(BM25Config(**payload.get("cfg", {})))
        idx.N = int(payload["N"])
        idx.avgdl = float(payload["avgdl"])
        idx.doc_len = {k: int(v) for k, v in payload["doc_len"].items()}
        idx.doc_meta = payload["doc_meta"]
        idx.postings = {k: [(d, int(tf)) for d, tf in v] for k, v in payload["postings"].items()}
        return idx

    def _idf(self, df: int) -> float:
        # BM25 IDF with +1 guard
        # idf = log( (N - df + 0.5) / (df + 0.5) + 1 )
        return math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)

    def search(self, query: str, topk: int = 10) -> List[Tuple[str, float]]:
        q_toks = tokenize(query)
        if not q_toks or self.N == 0:
            return []

        # accumulate scores
        scores: Dict[str, float] = {}
        k1, b = self.cfg.k1, self.cfg.b
        avgdl = self.avgdl if self.avgdl > 0 else 1.0

        # per token postings
        for tok in set(q_toks):
            plist = self.postings.get(tok)
            if not plist:
                continue
            df = len(plist)
            idf = self._idf(df)
            for doc_id, tf in plist:
                dl = self.doc_len.get(doc_id, 0)
                denom = tf + k1 * (1.0 - b + b * (dl / avgdl))
                score = idf * ((tf * (k1 + 1.0)) / (denom if denom != 0 else 1.0))
                scores[doc_id] = scores.get(doc_id, 0.0) + score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:topk]
        return ranked


def build_kb_index_from_jsonl(kb_jsonl_path: str, out_index_path: str) -> None:
    idx = KBIndex()
    with open(kb_jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)

            doc_id = obj.get("id")
            if not doc_id:
                continue

            # searchable text (Verantyxっぽい：patterns/title/statement/refutation を全部混ぜる)
            parts: List[str] = []
            for k in ("domain", "kind", "title", "statement", "refutation"):
                v = obj.get(k)
                if isinstance(v, str):
                    parts.append(v)
            pats = obj.get("patterns")
            if isinstance(pats, list):
                parts.extend([str(x) for x in pats if x is not None])

            text = "\n".join(parts)

            meta = {
                "domain": obj.get("domain"),
                "kind": obj.get("kind"),
                "title": obj.get("title"),
            }
            idx.add_doc(doc_id, text, meta)

    idx.finalize()
    idx.save(out_index_path)
