"""経験十字 — 経験のコンパイルを立体十字の上に置く(PREREG: experience_cross)。

十字の三双対(arm_schema)が9状態型の家:

    x軸 支持/反論   WITNESS(支持+) / COUNTEREXAMPLE(反論 = support−)
    y軸 原因/結果   FAILURE の敗因 / verdict の遷移(結果:proved 等)
    z軸 一般/実例   RULE の一般形 / モデル縛りの実測・実走

経験行は構造化された出所を持つので、腕の割り当ては**構成で決定**する
(表層手掛かりも推測も不要)。写像の無い行は未タグ = 一級。矛盾は
CrossStore.contradictions(結果:proved vs 結果:refuted)が構造の事件と
して出す — 検出器を新造しない。履歴は provenance(初出・最新・出所)が
持ち、上書きはしない。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .cross_store import CrossStore
from .experience import compile_view

#: 状態型 → (腕, 面キー)。構成で決まる写像 — ここに無い型は未タグ。
_ARM_OF = {
    "WITNESS": ("support+", "支持"),
    "COUNTEREXAMPLE": ("support-", "反論"),
    "FAILURE": ("cause+", "敗因"),
    "RULE": ("kind+", "一般"),
    "TRANSFER": ("kind-", "転移"),
    "GAP": ("cause-", "需要"),
    # CLAIM / EVIDENCE / PROCEDURE は v1 では面(結果/条件)のみで腕なし
}


def _facets_for(row: Dict[str, Any]) -> Tuple[List[str], Optional[str]]:
    """1行 → (facet列, 腕)。写像できなければ ([], None) = 未タグ。"""
    st = row.get("state")
    d = row.get("detail") or {}
    facets: List[str] = []
    arm = _ARM_OF.get(st, (None, None))[0]
    if st == "RULE":
        facets.append("結果:proved")
        w = d.get("witness")
        if w:
            facets.append(f"支持:{w}")
        if d.get("model"):
            facets.append(f"条件:model={d['model']}")
        if d.get("kind"):
            facets.append(f"一般:{d['kind']}")
    elif st == "COUNTEREXAMPLE":
        facets.append("結果:refuted")
        why = d.get("why") or d.get("kind") or "refuted"
        facets.append(f"反論:{why}")
        if d.get("witness"):
            facets.append(f"反論:{d['witness']}")
        if d.get("model"):
            facets.append(f"条件:model={d['model']}")
    elif st == "FAILURE":
        facets.append("結果:refused")
        why = d.get("failure_type") or d.get("kind") or d.get("verdict")
        if why:
            facets.append(f"敗因:{why}")
    elif st == "GAP":
        facets.append("状態:open")
        if d.get("failure_type"):
            facets.append(f"敗因:{d['failure_type']}")
        for n in (d.get("needs") or [])[:3]:
            facets.append(f"需要:{n}")
    elif st == "TRANSFER":
        facets.append("転移:記録")
    elif st in ("CLAIM", "EVIDENCE"):
        v = d.get("witness") or d.get("verdict") or d.get("status")
        if v:
            facets.append(f"条件:{v}")
        if d.get("model"):
            facets.append(f"条件:model={d['model']}")
    else:
        return [], None
    return facets, arm


def pour(view: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """compile_view → 経験十字。元の在庫は不動。

    返り値: {"store": CrossStore, "arms": 並行索引(core→腕→facet列),
             "untagged": 写像の無かった行数, "poured": 行数}
    """
    v = view or compile_view()
    st = CrossStore(track_provenance=True)
    arms: Dict[str, Dict[str, List[str]]] = {}
    untagged = 0
    poured = 0
    for row in v["rows"]:
        subject = str(row.get("subject") or "").strip()
        if not subject:
            untagged += 1
            continue
        facets, arm = _facets_for(row)
        if not facets:
            untagged += 1          # 推測で腕を当てない — 未タグは一級
            continue
        st.add(subject, facets, source=row.get("source"))
        if arm:
            slot = arms.setdefault(subject.casefold(), {})
            slot.setdefault(arm, []).extend(facets)
        poured += 1
    return {"store": st, "arms": arms, "untagged": untagged,
            "poured": poured}


def contested(store: CrossStore, arms: Dict[str, Dict[str, List[str]]]
              ) -> List[Dict[str, Any]]:
    """支持と反論が同居する核 + 結果面の構造矛盾(既存検出器)。"""
    out = []
    for core, slot in arms.items():
        if slot.get("support+") and slot.get("support-"):
            out.append({"core": core, "kind": "contested",
                        "support": slot["support+"][:3],
                        "oppose": slot["support-"][:3]})
    for core in store.crosses:
        for c in store.contradictions(core):
            if c["key"] == "結果" and len(c["values"]) > 1:
                out.append({"core": core, "kind": "結果の矛盾", **c})
    return out


def reevaluate_math_gaps(store: CrossStore, gap_rows: List[Dict[str, Any]],
                         ) -> List[Dict[str, Any]]:
    """GAP再評価ループ v1: 主題が等式の open Gap を現在の在庫で再証明。

    閉じたら 結果:proved + 支持:証人 + 状態:closed を**追記**(履歴は
    provenance が保持 — 上書きしない)。閉じなければ open のまま。
    """
    from .prover import prove_equation

    out = []
    seen = set()
    for row in gap_rows:
        subj = str(row.get("subject") or "")
        if " = " not in subj or subj in seen:
            continue
        seen.add(subj)
        lhs, rhs = subj.split(" = ", 1)
        r = prove_equation(lhs, rhs, lean=True)
        if r.get("verdict") == "PROVED":
            w = (r.get("lean") or {}).get("witness") or "kernel"
            store.add(subj, ["状態:closed", "結果:proved", f"支持:{w}"],
                      source="reevaluation@2026-08-20")
            out.append({"subject": subj, "reevaluated": "CLOSED",
                        "witness": w, "cited": r.get("cited")})
        else:
            out.append({"subject": subj,
                        "reevaluated": "STILL_" + str(r.get("verdict")),
                        "reason": r.get("reason")})
    return out
