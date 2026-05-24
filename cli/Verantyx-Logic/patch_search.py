from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Callable

from patch_proof import (
    Patch,
    apply_patch_to_counterexample,
    check_assumption_satisfied,
    recheck_formula_with_model_search,
)

Edge = Tuple[int, int]


@dataclass
class PatchCandidate:
    patch: Patch
    patch_size: int
    assumption_satisfied: bool
    still_counterexample: Optional[bool]
    note: str


def _edges_of_worlds(worlds: int) -> List[Edge]:
    """世界数Nに対して取りうる全辺候補。MVPは全組み合わせ。"""
    return [(i, j) for i in range(worlds) for j in range(worlds)]


def _patch_size(p: Patch) -> int:
    return len(p.add_edges) + len(p.remove_edges)


def _merge_patch(a: Patch, b: Patch) -> Patch:
    # setで正規化して重複除去（順序は最後に整列）
    add = set(a.add_edges) | set(b.add_edges)
    rem = set(a.remove_edges) | set(b.remove_edges)
    # 同じ辺を add と remove の両方に入れない（remove優先）
    add = add - rem
    return Patch(add_edges=sorted(add), remove_edges=sorted(rem))


# -----------------------------
# Assumption -> Patch generator
# -----------------------------

def candidate_patches_for_assumption(worlds: int, assumption: str, max_extra: int = 2) -> List[Patch]:
    """
    「assumption を満たす方向」のパッチ候補を生成する。
    max_extra: “最小っぽい候補”を少しだけ増やすための緩さ。
    """
    all_edges = _edges_of_worlds(worlds)

    if assumption == "assume:reflexive":
        # 必須：全 i に (i,i)
        base = Patch(add_edges=[(i, i) for i in range(worlds)], remove_edges=[])
        # worlds=1ならadd 1本。worlds>1のときは多いが、reflexiveの定義上必要。
        return [base]

    if assumption == "assume:symmetric":
        # ある辺 (a,b) があれば (b,a) が必要
        # “追加だけで”対称性を満たす候補：全辺を対称化する
        # MVP: この1個を返す（removeを混ぜる最適化はPhase 13で）
        # engine側で「不足分だけ add」へ絞るので、生成は空でもOK
        return [Patch(add_edges=[], remove_edges=[])]  # engine側で不足分生成

    if assumption == "assume:transitive":
        # 推移性は “欠けている (x,z) を追加する” で満たせる
        # ただし欠けている辺は現モデル依存なので、ここでも空を返して engine側で生成
        return [Patch(add_edges=[], remove_edges=[])]

    if assumption == "assume:euclidean":
        # ユークリッド性も現モデル依存
        return [Patch(add_edges=[], remove_edges=[])]

    return []


def patch_to_satisfy_assumption_minimal(
    cex: Dict[str, Any],
    assumption: str,
    limit_k: int = 3,
) -> List[Patch]:
    """
    現反例モデル cex を、assumption を満たすように最小変更で修正する候補を返す。
    MVP:
      - reflexive: 必要な self-loop を全部追加（定義上それが最小）
      - symmetric/transitive/euclidean: “不足している辺だけ add” を greedily 作る
    """
    worlds = int(cex.get("n_worlds") or cex.get("worlds") or 0)
    # Ensure edges are tuples
    raw_edges = cex.get("edges") or []
    edges = set()
    for e in raw_edges:
        if len(e) >= 2:
            edges.add((int(e[0]), int(e[1])))

    if assumption == "assume:reflexive":
        add = [(i, i) for i in range(worlds) if (i, i) not in edges]
        return [Patch(add_edges=add, remove_edges=[])]

    if assumption == "assume:symmetric":
        add: List[Edge] = []
        for (a, b) in list(edges):
            if (b, a) not in edges:
                add.append((b, a))
        # 追加数が大きすぎたら切る（MVP）
        if len(add) > limit_k:
            add = add[:limit_k]
        return [Patch(add_edges=add, remove_edges=[])]

    if assumption == "assume:transitive":
        # 欠けてる (x,z) を列挙して少数返す
        missing: List[Edge] = []
        for (x, y) in edges:
            for (y2, z) in edges:
                if y2 == y and (x, z) not in edges:
                    missing.append((x, z))
        # できるだけ少なく
        missing = list(dict.fromkeys(missing))  # preserve order unique
        if not missing:
            return [Patch(add_edges=[], remove_edges=[])]
        # 最小っぽく 1本ずつ試す + まとめて試す
        out = [Patch(add_edges=[e], remove_edges=[]) for e in missing[:limit_k]]
        out.append(Patch(add_edges=missing[:limit_k], remove_edges=[]))
        return out

    if assumption == "assume:euclidean":
        missing: List[Edge] = []
        for (a, b) in edges:
            for (a2, c) in edges:
                if a2 == a and (b, c) not in edges:
                    missing.append((b, c))
        missing = list(dict.fromkeys(missing))
        if not missing:
            return [Patch(add_edges=[], remove_edges=[])]
        out = [Patch(add_edges=[e], remove_edges=[]) for e in missing[:limit_k]]
        out.append(Patch(add_edges=missing[:limit_k], remove_edges=[]))
        return out

    return []


# -----------------------------
# Main search API
# -----------------------------

def find_minimal_patches(
    model_checker_fn: Callable[[str, Dict[str, Any]], bool],
    formula: str,
    base_assumptions: List[str],
    cex: Dict[str, Any],
    goal_assumption: str,
    limit_k: int = 3,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """
    goal_assumption を満たしつつ、同じ反例モデルがもう反例でなくなるパッチを列挙。
    limit_k: transitive/euclidean の欠けedge候補の探索幅
    """
    # 1) goal_assumption を満たす候補 patch を作る（最小寄り）
    patches = patch_to_satisfy_assumption_minimal(cex, goal_assumption, limit_k=limit_k)

    results: List[PatchCandidate] = []

    for p in patches:
        patched = apply_patch_to_counterexample(cex, p)
        satisfied = check_assumption_satisfied(patched, goal_assumption)

        recheck = recheck_formula_with_model_search(
            model_checker_fn=model_checker_fn,
            formula=formula,
            assumptions=(base_assumptions + [goal_assumption]),
            patched_cex=patched,
        )

        results.append(PatchCandidate(
            patch=p,
            patch_size=_patch_size(p),
            assumption_satisfied=satisfied,
            still_counterexample=recheck.get("still_counterexample"),
            note=recheck.get("note", ""),
        ))

    # 2) ソート：小さいほど良い、反例が潰れているほど良い
    # Prioritize: Satisfied assumptions AND destroyed counterexample (still_cex=False)
    def key(pc: PatchCandidate):
        # Rank:
        # 0: Satisfied + Not Still CEX (Best)
        # 1: Satisfied + Still CEX (Intermediate)
        # 2: Not Satisfied (Worst)
        if not pc.assumption_satisfied:
            rank = 2
        elif pc.still_counterexample is False:
            rank = 0
        else:
            rank = 1
        return (rank, pc.patch_size)

    results.sort(key=key)

    out: List[Dict[str, Any]] = []
    for pc in results[:max_results]:
        out.append({
            "goal": f"make_assumption_true: {goal_assumption}",
            "patch": {
                "add_edges": [list(e) for e in pc.patch.add_edges],
                "remove_edges": [list(e) for e in pc.patch.remove_edges],
            },
            "patch_size": pc.patch_size,
            "assumption_satisfied": pc.assumption_satisfied,
            "still_counterexample": pc.still_counterexample,
            "note": pc.note,
        })
    return out