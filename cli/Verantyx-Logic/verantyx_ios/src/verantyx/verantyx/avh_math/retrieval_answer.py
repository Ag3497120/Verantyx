# avh_math/retrieval_answer.py
from __future__ import annotations
import json
from typing import Any, Dict, List, Optional, Tuple

from avh_math.retrieval_bm25 import KBIndex

def load_kb_entry_by_id(kb_jsonl_path: str, target_id: str) -> Optional[Dict[str, Any]]:
    # 86,000+ 行だと線形は重いので、本当は Phase17 のオフセット索引を使うのが理想。
    # まずは “確実に動く” 版として線形読み取り。
    with open(kb_jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("id") == target_id:
                return obj
    return None

def retrieve_similar_entries(
    index: KBIndex,
    kb_jsonl_path: str,
    query: str,
    topk: int = 8
) -> List[Dict[str, Any]]:
    ranked = index.search(query, topk=topk)
    out: List[Dict[str, Any]] = []
    for doc_id, score in ranked:
        entry = load_kb_entry_by_id(kb_jsonl_path, doc_id)
        if not entry:
            continue
        entry["_score"] = float(score)
        out.append(entry)
    return out

def synthesize_answer_from_similars(
    query: str,
    similars: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Verantyx系の “DB照合→答え”。
    - 最も近い entry を中心に「結論候補」を作る
    - refutation が強いなら disproved 寄り、theorem/definition が多ければ proved/unknown 寄り
    """
    if not similars:
        return {
            "status_hint": "unknown",
            "answer_text": "DB内に十分近いエントリが見つかりませんでした。",
            "used_kb_ids": [],
            "explain": "no_similar_entries",
        }

    used_ids = [e.get("id") for e in similars if e.get("id")]
    # heuristics
    kinds = [str(e.get("kind") or "") for e in similars]
    has_counterexample = any(k == "counterexample_schema" for k in kinds)
    top = similars[0]

    # まず top の statement を短く提示
    title = top.get("title") or top.get("id")
    domain = top.get("domain") or "unknown"
    top_statement = (top.get("statement") or "").strip()
    top_refutation = top.get("refutation")

    # 返答テンプレ
    if has_counterexample:
        # 「同型の破綻境界」系
        msg = [
            f"DBの類似反例（{domain}）に基づく推定:",
            f"- 最類似: {title}",
        ]
        if top_statement:
            msg.append(f"- 近い主張: {top_statement}")
        if isinstance(top_refutation, str) and top_refutation.strip():
            msg.append(f"- 反例/破綻点: {top_refutation.strip()}")
        msg.append("→ このクエリは **反例が出るタイプ（disproved寄り）** の可能性が高いです。")
        return {
            "status_hint": "disproved",
            "answer_text": "\n".join(msg),
            "used_kb_ids": used_ids,
            "explain": "counterexample_dominant",
        }

    # theorem/definition が優勢なら「成立しそう」だが確証ではない
    msg = [
        f"DBの類似定義/定理（{domain}）に基づく推定:",
        f"- 最類似: {title}",
    ]
    if top_statement:
        msg.append(f"- 近い主張: {top_statement}")
    msg.append("→ 探索・証明が未実行なら **unknown（成立寄り）** として扱います。")
    return {
        "status_hint": "unknown",
        "answer_text": "\n".join(msg),
        "used_kb_ids": used_ids,
        "explain": "theorem_definition_dominant",
    }
