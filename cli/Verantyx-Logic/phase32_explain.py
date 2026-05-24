# phase32_explain.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json
import re

# ---- Paths (あなたの構成に合わせてOK) ----
KB_PATH = Path("avh_math/db/foundation_kb.jsonl")
OFFSETS_PATH = Path("avh_math/db/kb_offsets.json")
META_PATH = Path("avh_math/db/kb_meta.json")
GRAPH_PATH = Path("avh_math/db/boundary_graph.json")

# -----------------------------
# Low-level: fast JSONL lookup
# -----------------------------
class KBReader:
    """
    foundation_kb.jsonl を id->file offset でランダムアクセス。
    """
    def __init__(self, kb_path: Path = KB_PATH, offsets_path: Path = OFFSETS_PATH):
        self.kb_path = kb_path
        self.offsets_path = offsets_path
        self.offsets: Dict[str, int] = {}
        if self.offsets_path.exists():
            self.offsets = json.loads(self.offsets_path.read_text(encoding="utf-8"))

    def get(self, entry_id: str) -> Optional[Dict[str, Any]]:
        off = self.offsets.get(entry_id)
        if off is None:
            return None
        with self.kb_path.open("rb") as f:
            f.seek(off)
            line = f.readline()
        if not line:
            return None
        try:
            return json.loads(line.decode("utf-8"))
        except Exception:
            return None

# -----------------------------
# Explain builder (no LLM)
# -----------------------------
@dataclass
class ExplainResult:
    query: str
    lang: str
    domain_guess: str
    summary: str
    why_steps: List[str]
    evidence: List[Dict[str, Any]]
    next_actions: List[str]

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def _safe(s: Any) -> str:
    return "" if s is None else str(s)

def _parse_refutation(ref: Any) -> Dict[str, str]:
    if ref is None:
        return {}
    if isinstance(ref, dict):
        return {k: _safe(v) for k, v in ref.items()}

    text = _safe(ref)
    out = {}
    keys = ["Domain", "Structure", "Dropped Assumption", "Failure Point", "Minimality"]
    for k in keys:
        marker = k + ":"
        if marker in text:
            seg = text.split(marker, 1)[1]
            seg = seg.split("\n", 1)[0]
            seg = seg.split(";", 1)[0]
            out[k] = seg.strip()
    return out

def _choose_best_counterexample(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    # 1. min_verified:real_true
    # 2. kind=counterexample_schema
    # 3. has structured refutation
    candidates = [e for e in entries if e.get("kind") == "counterexample_schema"]
    if not candidates:
        return entries[0] if entries else None
        
    def score(e):
        s = 0
        pats = e.get("patterns", [])
        if "min_verified:real_true" in pats: s += 10
        if "min_verified:true" in pats: s += 5
        ref = e.get("refutation")
        if isinstance(ref, dict): s += 3
        elif isinstance(ref, str) and "Failure Point:" in ref: s += 2
        return s

    candidates.sort(key=score, reverse=True)
    return candidates[0]

def build_explanation(
    query: str,
    domain_guess: str,
    candidate_ids: List[str],
    lang: str = "ja",
    max_evidence: int = 8,
) -> ExplainResult:
    reader = KBReader()
    graph = _load_json(GRAPH_PATH)

    # KBから候補を引く
    entries: List[Dict[str, Any]] = []
    for _id in candidate_ids[:200]:
        e = reader.get(_id)
        if e:
            entries.append(e)

    best = _choose_best_counterexample(entries)
    best_ref = _parse_refutation(best.get("refutation") if best else None)

    # hotspots / clusters
    hotspots = graph.get("hotspots", [])[:10]
    clusters = graph.get("clusters", {})

    # 類似クラスタ
    cset = set(candidate_ids)
    cluster_scores = []
    for cid, ids in (clusters or {}).items():
        ov = len(set(ids) & cset)
        if ov > 0:
            cluster_scores.append((cid, ov))
    cluster_scores.sort(key=lambda x: -x[1])
    top_cluster_id = cluster_scores[0][0] if cluster_scores else None

    # evidence
    evidence: List[Dict[str, Any]] = []
    used = set()

    def push(ev: Optional[Dict[str, Any]]):
        if not ev: return
        _id = ev.get("id")
        if not _id or _id in used: return
        used.add(_id)
        evidence.append({
            "id": _id,
            "domain": ev.get("domain"),
            "kind": ev.get("kind"),
            "title": ev.get("title"),
            "statement": ev.get("statement"),
            "refutation": ev.get("refutation"),
            "patterns": ev.get("patterns", [])[:12],
            "links": ev.get("links", [])[:12],
        })

    push(best)
    if best:
        for lid in (best.get("links") or [])[:20]:
            push(reader.get(lid))
            if len(evidence) >= max_evidence: break

    # 足りなければ同ドメインから補う
    if len(evidence) < max_evidence:
        for ev in entries:
            if ev.get("domain") == domain_guess:
                push(ev)
                if len(evidence) >= max_evidence: break

    # ---- Template (no LLM) ----
    if lang == "en":
        summary = f"Boundary-based explanation for '{query}' (domain≈{domain_guess})."
        steps = []
        if best_ref:
            steps.append(f"Detected boundary signature from a counterexample schema: {best.get('id') if best else 'N/A'}.")
            if "Dropped Assumption" in best_ref:
                steps.append(f"Dropped assumption: {best_ref['Dropped Assumption']}.")
            if "Failure Point" in best_ref:
                steps.append(f"Failure point: {best_ref['Failure Point']}.")
            if "Structure" in best_ref:
                steps.append(f"Minimal structure: {best_ref['Structure']}.")
        else:
            steps.append("No structured refutation format was found in the top candidates.")
        if top_cluster_id:
            steps.append(f"Similar boundary cluster: {top_cluster_id} (overlap with candidates).")
        if hotspots:
            steps.append(f"Hotspots (risky assumptions): " + ", ".join([_safe(h.get("name") or h.get("assumption") or "hotspot") for h in hotspots[:5]]))
        next_actions = [
            "Increase model search depth (max_worlds / domain size) for verification.",
            "Toggle the suspected dropped assumption ON/OFF and re-run verification.",
            "Compare with other examples in the same boundary cluster."
        ]
    else:
        summary = f"クエリ「{query}」を、境界（反例）ベースで説明します（推定ドメイン：{domain_guess}）。"
        steps = []
        if best_ref:
            steps.append(f"最有力の根拠は counterexample_schema: {best.get('id') if best else 'N/A'} です。")
            if "Dropped Assumption" in best_ref:
                steps.append(f"落とした仮定：{best_ref['Dropped Assumption']}。")
            if "Failure Point" in best_ref:
                steps.append(f"破綻点：{best_ref['Failure Point']}。")
            if "Structure" in best_ref:
                steps.append(f"最小構造（反例の指紋）：{best_ref['Structure']}。")
            if "Minimality" in best_ref:
                steps.append(f"最小性：{best_ref['Minimality']}。")
        else:
            steps.append("上位候補に、構造化された反例フォーマットが見つかりませんでした（refutationが未整備の可能性）。")
        if top_cluster_id:
            steps.append(f"類似境界クラスタ：{top_cluster_id}（同型・同質な破綻が集約）。")
        if hotspots:
            steps.append("ホットスポット（落とすと危険な仮定）：" \
                         + " / ".join([_safe(h.get('name') or h.get('assumption') or 'hotspot') for h in hotspots[:5]]))
        next_actions = [
            "検証強度を上げる（max_worlds/ドメインサイズ拡張）→ unknown を確定へ寄せる",
            "落とした仮定を ON/OFF して再検証し、破綻境界が一致するか確認",
            "同じクラスタ内の反例を比較し、共通の破綻点（Failure Point）を抽出"
        ]

    return ExplainResult(
        query=query,
        lang=lang,
        domain_guess=domain_guess,
        summary=summary,
        why_steps=steps,
        evidence=evidence,
        next_actions=next_actions,
    )
