from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional, Iterable
import itertools

# Kripke model: worlds 0..n-1, relation R (edges), valuation V(atom)->set(worlds)

@dataclass(frozen=True)
class Model:
    n_worlds: int
    edges: Tuple[Tuple[int, int], ...]
    valuation: Dict[str, Tuple[int, ...]]  # atom -> worlds where true

    def succ(self, w: int) -> List[int]:
        return [v for (x, v) in self.edges if x == w]

def generate_models(
    max_worlds: int,
    atoms: List[str],
    assume_transitive: bool = False,
    assume_reflexive: bool = False,
    max_edges: Optional[int] = None,
) -> Iterable[Model]:
    """
    Brute-force small models up to max_worlds. For each n, enumerate edge sets (optionally bounded),
    then enumerate valuations for atoms.
    """
    for n in range(1, max_worlds + 1):
        world_pairs = [(i, j) for i in range(n) for j in range(n)]
        # edge subsets
        all_edge_subsets = _edge_subsets(world_pairs, max_edges=max_edges)
        for edges in all_edge_subsets:
            if assume_reflexive and not all((i, i) in edges for i in range(n)):
                continue
            if assume_transitive and not _is_transitive(n, edges):
                continue

            edges_t = tuple(sorted(edges))
            # valuations: each atom can be true in any subset of worlds
            for valuation in _valuations(n, atoms):
                yield Model(n_worlds=n, edges=edges_t, valuation=valuation)

def _edge_subsets(pairs: List[Tuple[int, int]], max_edges: Optional[int]) -> Iterable[Set[Tuple[int, int]]]:
    # If max_edges is set, enumerate combinations up to that size.
    # 決定打：反例探索のため、エッジがあるモデル（非自明な構造）を優先的に探索する。
    # 空のモデル（エッジ数0）は []p が常に真になりやすく反例になりにくいため、順序を工夫する。
    
    limit = len(pairs) + 1 if max_edges is None else min(max_edges, len(pairs)) + 1
    
    # まずエッジ数 1 以上を探索
    for r in range(1, limit):
        for comb in itertools.combinations(pairs, r):
            yield set(comb)
            
    # 最後にエッジ数 0 を探索（必要なら）
    yield set()

def _valuations(n: int, atoms: List[str]) -> Iterable[Dict[str, Tuple[int, ...]]]:
    world_indices = list(range(n))
    # each atom -> subset of worlds
    for assigns in itertools.product([0, 1], repeat=n * len(atoms)):
        valuation: Dict[str, List[int]] = {a: [] for a in atoms}
        idx = 0
        for a in atoms:
            for w in world_indices:
                if assigns[idx] == 1:
                    valuation[a].append(w)
                idx += 1
        yield {a: tuple(ws) for a, ws in valuation.items()}

def _is_transitive(n: int, edges: Set[Tuple[int, int]]) -> bool:
    # if (a,b) and (b,c) then (a,c)
    for a in range(n):
        for b in range(n):
            if (a, b) not in edges:
                continue
            for c in range(n):
                if (b, c) in edges and (a, c) not in edges:
                    return False
    return True

def falsify(statement: str, domain: str, assumptions: list[str], max_worlds: int = 4, max_depth: int = 3, timeout_s: float = 1.5) -> dict:
    """
    Return:
      {"status": "falsified", "counterexample": "<PhaseE-format text>", "meta": {...}}
      {"status": "not_found", "counterexample": None, "meta": {...}}
    """
    # TODO: Replace with real solvers per domain.
    # Currently a stub that claims 'not_found' (provisionally verified) for demonstration.
    return {"status": "not_found", "counterexample": None, "meta": {"note": "placeholder falsify() - implement real search"}}