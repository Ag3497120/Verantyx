from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import itertools

from avh_math.verantyx.shape_ast import Var, Not, And, Or, Imp, Iff, Box, Dia, Expr


@dataclass
class KripkeFrame:
    worlds: List[int]
    R: Set[Tuple[int, int]]
    V: Dict[str, Set[int]]


@dataclass
class KripkeResult:
    status: str  # valid | invalid | unknown
    counterexample: Optional[Dict[str, object]] = None
    audit: List[str] = None


def _succ(R: Set[Tuple[int, int]], w: int) -> List[int]:
    return [v for (x, v) in R if x == w]


def eval_modal(expr: Expr, w: int, frame: KripkeFrame) -> bool:
    if isinstance(expr, Var):
        return w in frame.V.get(expr.name, set())
    if isinstance(expr, Not):
        return not eval_modal(expr.child, w, frame)
    if isinstance(expr, And):
        return eval_modal(expr.left, w, frame) and eval_modal(expr.right, w, frame)
    if isinstance(expr, Or):
        return eval_modal(expr.left, w, frame) or eval_modal(expr.right, w, frame)
    if isinstance(expr, Imp):
        a = eval_modal(expr.left, w, frame)
        b = eval_modal(expr.right, w, frame)
        return (not a) or b
    if isinstance(expr, Iff):
        a = eval_modal(expr.left, w, frame)
        b = eval_modal(expr.right, w, frame)
        return a == b
    if isinstance(expr, Box):
        succs = _succ(frame.R, w)
        return all(eval_modal(expr.child, v, frame) for v in succs)
    if isinstance(expr, Dia):
        succs = _succ(frame.R, w)
        return any(eval_modal(expr.child, v, frame) for v in succs)
    return False


def _is_reflexive(worlds: List[int], R: Set[Tuple[int, int]]) -> bool:
    return all((w, w) in R for w in worlds)


def _is_symmetric(R: Set[Tuple[int, int]]) -> bool:
    return all((b, a) in R for (a, b) in R)


def _is_transitive(R: Set[Tuple[int, int]]) -> bool:
    for (a, b) in R:
        for (c, d) in R:
            if b == c and (a, d) not in R:
                return False
    return True


def _is_serial(worlds: List[int], R: Set[Tuple[int, int]]) -> bool:
    for w in worlds:
        if not any(x == w for (x, _) in R):
            return False
    return True


def _assumptions_ok(worlds: List[int], R: Set[Tuple[int, int]], assumptions: List[str]) -> bool:
    if "reflexive" in assumptions and not _is_reflexive(worlds, R):
        return False
    if "symmetric" in assumptions and not _is_symmetric(R):
        return False
    if "transitive" in assumptions and not _is_transitive(R):
        return False
    if "serial" in assumptions and not _is_serial(worlds, R):
        return False
    return True


def find_counterexample(
    expr: Expr,
    atoms: List[str],
    assumptions: List[str],
    max_worlds: int = 3,
    max_edges: int = 6,
) -> KripkeResult:
    audit: List[str] = []
    atoms = [a for a in atoms if a.isalpha()]
    if not atoms:
        atoms = ["p"]
    
    # 決定打：仮定の正規化（assume: プレフィックスを剥離し、実質的な制約のみにする）
    effective_assumptions = []
    for a in assumptions:
        clean_a = a.replace("assume:", "").strip().lower()
        # frame:K4 などの特殊指定も吸収
        if clean_a.startswith("frame:"):
            kind = clean_a.split(":")[1]
            if kind == "k4": effective_assumptions.append("transitive")
            elif kind == "s4": effective_assumptions.extend(["reflexive", "transitive"])
            elif kind == "s5": effective_assumptions.extend(["reflexive", "transitive", "euclidean"])
        else:
            effective_assumptions.append(clean_a)
    
    # 重複排除
    effective_assumptions = list(set(effective_assumptions))

    for n in range(1, max_worlds + 1):
        worlds = list(range(n))
        all_pairs = list(itertools.product(worlds, worlds))

        for edges_bits in range(1 << len(all_pairs)):
            R: Set[Tuple[int, int]] = set()
            for i, pair in enumerate(all_pairs):
                if (edges_bits >> i) & 1:
                    R.add(pair)
            
            # 決定打：制約の強制適用 (Constraint Enforcement)
            if "transitive" in effective_assumptions:
                # 推移的閉包の計算
                while True:
                    new_edges = {(a, d) for (a, b) in R for (c, d) in R if b == c and (a, d) not in R}
                    if not new_edges: break
                    R.update(new_edges)
            
            if "reflexive" in effective_assumptions:
                for w in worlds: R.add((w, w))

            if len(R) > max_edges:
                continue
            
            # 最終チェック（対称性や直列性など他の制約）
            if not _assumptions_ok(worlds, R, effective_assumptions):
                continue

            # valuation: 2^(n*|atoms|)
            for bits in range(1 << (n * len(atoms))):
                V: Dict[str, Set[int]] = {a: set() for a in atoms}
                bit = 0
                for a in atoms:
                    for w in worlds:
                        if (bits >> bit) & 1:
                            V[a].add(w)
                        bit += 1
                frame = KripkeFrame(worlds=worlds, R=R, V=V)
                for w in worlds:
                    if not eval_modal(expr, w, frame):
                        audit.append("[CE] counterexample_found")
                        # 決定打：UIが解釈可能な形式で反例を詳細化
                        return KripkeResult(
                            status="invalid",
                            counterexample={
                                "type": "kripke_model",
                                "worlds": worlds,
                                "relation": sorted(list(R)),
                                "valuation": {k: sorted(list(v)) for k, v in V.items()},
                                "falsifying_world": w,
                                "assumptions_applied": effective_assumptions
                            },
                            audit=audit,
                        )

    audit.append("[OK] no_counterexample_in_bounds")
    return KripkeResult(status="valid", counterexample=None, audit=audit)
