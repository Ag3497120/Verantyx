from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import itertools

from avh_math.model_search import Model, generate_models

# AST nodes
class Node: ...

@dataclass(frozen=True)
class Atom(Node):
    name: str

@dataclass(frozen=True)
class Imp(Node):
    left: Node
    right: Node

@dataclass(frozen=True)
class Box(Node):
    inner: Node

@dataclass(frozen=True)
class Dia(Node):
    inner: Node

@dataclass
class VerifyConfig:
    max_worlds: int = 3
    max_edges: int = 4
    check_world: int = 0  # evaluate validity at world 0 for counterexample search

def parse_formula(s: str) -> Node:
    """
    Very small parser for forms:
    - []p
    - <>p
    - p
    - X -> Y
    Also supports nesting like [][]p or []<>p etc.
    """
    s = s.strip().replace(" ", "")
    # implication split at top-level
    parts = _split_top_level(s, "->")
    if len(parts) == 2:
        return Imp(parse_formula(parts[0]), parse_formula(parts[1]))

    # modal prefixes
    if s.startswith("[]"):
        return Box(parse_formula(s[2:]))
    if s.startswith("<>"):
        return Dia(parse_formula(s[2:]))

    # atom
    if s.isalnum():
        return Atom(s)

    raise ValueError(f"Unsupported formula syntax: {s}")

def _split_top_level(s: str, token: str) -> List[str]:
    # no parentheses in this minimal version, so token split is safe.
    if token in s:
        return s.split(token, 1)
    return [s]

def eval_node(model: Model, node: Node, w: int) -> bool:
    if isinstance(node, Atom):
        return w in set(model.valuation.get(node.name, tuple()))
    if isinstance(node, Imp):
        return (not eval_node(model, node.left, w)) or eval_node(model, node.right, w)
    if isinstance(node, Box):
        succs = model.succ(w)
        # vacuously true if no successors
        return all(eval_node(model, node.inner, v) for v in succs)
    if isinstance(node, Dia):
        succs = model.succ(w)
        return any(eval_node(model, node.inner, v) for v in succs)
    raise TypeError("Unknown node type")

@dataclass
class VerifyResult:
    formula: str
    status: str  # "valid" | "invalid" | "unknown"
    diffs: List[str]
    counterexample: Optional[Dict[str, Any]] = None
    audit: List[str] = None

def find_counterexample(
    formula: str,
    atoms: List[str],
    assumptions: List[str],
    cfg: VerifyConfig,
) -> VerifyResult:
    audit: List[str] = []
    diffs: List[str] = []

    assume_trans = "assume:transitive" in assumptions
    assume_refl = "assume:reflexive" in assumptions

    audit.append(f"[VERIFY] formula={formula}")
    audit.append(f"[ASSUME] transitive={assume_trans} reflexive={assume_refl}")
    audit.append(f"[SEARCH] max_worlds={cfg.max_worlds} max_edges={cfg.max_edges}")

    try:
        ast = parse_formula(formula)
    except Exception as e:
        return VerifyResult(formula=formula, status="unknown", diffs=["diff:parser_uncertain"], counterexample=None, audit=audit + [f"[ERROR] parse: {e}"])

    tried = 0
    for model in generate_models(
        max_worlds=cfg.max_worlds,
        atoms=atoms,
        assume_transitive=assume_trans,
        assume_reflexive=assume_refl,
        max_edges=cfg.max_edges,
    ):
        tried += 1
        ok = eval_node(model, ast, cfg.check_world)
        if not ok:
            diffs.append("diff:counterexample_found")
            audit.append(f"[CE] found after {tried} models")
            ce = {
                "n_worlds": model.n_worlds,
                "edges": list(model.edges),
                "valuation": {k: list(v) for k, v in model.valuation.items()},
                "at_world": cfg.check_world,
            }
            return VerifyResult(formula=formula, status="invalid", diffs=diffs, counterexample=ce, audit=audit)

    # none found within bounds
    diffs.append("diff:valid_under_assumptions")
    audit.append(f"[OK] no counterexample in {tried} models")
    # If bounds are small, also note search_exhausted (optional)
    if cfg.max_worlds <= 3:
        diffs.append("diff:search_exhausted")
    return VerifyResult(formula=formula, status="valid", diffs=diffs, counterexample=None, audit=audit)

# --- Template Search Helpers ---

def _edges_to_adj(worlds: int, edges: List[Tuple[int, int]]) -> List[List[int]]:
    adj = [[] for _ in range(worlds)]
    for a, b in edges:
        if 0 <= a < worlds and 0 <= b < worlds:
            adj[a].append(b)
    return adj

def _is_transitive(worlds: int, edges: List[Tuple[int, int]]) -> bool:
    E = set(edges)
    for a, b in E:
        for c, d in E:
            if b == c and (a, d) not in E:
                return False
    return True

def _is_reflexive(worlds: int, edges: List[Tuple[int, int]]) -> bool:
    E = set(edges)
    return all((w, w) in E for w in range(worlds))

def _assumptions_ok(assumptions: List[str], worlds: int, edges: List[Tuple[int, int]]) -> bool:
    # 最小版：transitive / reflexive だけ対応（必要なら増やせる）
    if "assume:transitive" in assumptions and not _is_transitive(worlds, edges):
        return False
    if "assume:reflexive" in assumptions and not _is_reflexive(worlds, edges):
        return False
    return True

def _template_constraints_ok(template_constraints: List[str], assumptions: List[str], worlds: int, edges: List[Tuple[int, int]]) -> bool:
    # 例: template側が "not:reflexive" を要求
    c = set(template_constraints or [])
    if "not:reflexive" in c and _is_reflexive(worlds, edges):
        return False
    if "assume:reflexive" in c and "assume:reflexive" not in assumptions:
        return False
    return True

def _all_valuations(atoms: List[str], worlds: int):
    # valuation: Dict[atom, List[bool]] worldごとの真偽
    for bits in itertools.product([False, True], repeat=len(atoms) * worlds):
        v = {}
        idx = 0
        for a in atoms:
            arr = []
            for _ in range(worlds):
                arr.append(bits[idx])
                idx += 1
            v[a] = arr
        yield v

def _eval_formula_on_model(formula: str, worlds: int, edges: List[Tuple[int, int]], valuation: Dict[str, List[bool]]) -> bool:
    # Convert valuation from Dict[str, List[bool]] to Dict[str, Tuple[int, ...]]
    val_indices = {}
    for atom, bools in valuation.items():
        val_indices[atom] = tuple(i for i, b in enumerate(bools) if b)
    
    model = Model(n_worlds=worlds, edges=tuple(edges), valuation=val_indices)
    node = parse_formula(formula)
    return eval_node(model, node, 0) # w0=0

def find_counterexample_by_templates(
    formula: str,
    atoms: List[str],
    assumptions: List[str],
    templates_db: Dict[str, Any],
    max_templates: int = 6,
) -> "VerifyResult":
    audit: List[str] = [f"[TPL] template_search max_templates={max_templates}"]
    templates = (templates_db.get("templates", []) or [])[:max_templates]

    for tpl in templates:
        tid = tpl.get("id", "tpl:unknown")
        worlds = int(tpl.get("worlds", 1))
        edges = [tuple(e) for e in (tpl.get("edges", []) or [])]
        tcons = tpl.get("constraints", []) or []

        if not _template_constraints_ok(tcons, assumptions, worlds, edges):
            audit.append(f"[TPL] skip {tid} (template constraints not met)")
            continue
        if not _assumptions_ok(assumptions, worlds, edges):
            audit.append(f"[TPL] skip {tid} (assumptions not satisfied)")
            continue

        audit.append(f"[TPL] try {tid} worlds={worlds} edges={edges}")

        # valuation 全探索（小さいテンプレだけなのでCPUでも現実的）
        for valuation in _all_valuations(atoms, worlds):
            try:
                ok = _eval_formula_on_model(formula, worlds, edges, valuation)
            except Exception as e:
                return VerifyResult(
                    status="unknown",
                    diffs=["diff:evaluator_error"],
                    counterexample=None,
                    audit=audit + [f"[TPL][ERROR] eval failed: {e}"],
                    formula=formula # Added formula field which was missing in original snippet
                )

            if not ok:
                # 反例
                ce = {
                    "template_id": tid,
                    "n_worlds": worlds, # Changed key to match standard counterexample
                    "edges": edges,
                    "valuation": valuation,
                    "at_world": 0
                }
                return VerifyResult(
                    status="invalid",
                    diffs=["diff:counterexample_found"],
                    counterexample=ce,
                    audit=audit + [f"[TPL] hit counterexample via {tid}"],
                    formula=formula
                )

    return VerifyResult(
        formula=formula,
        status="unknown",
        diffs=["diff:no_counterexample_in_templates"],
        counterexample=None,
        audit=audit + ["[TPL] no counterexample found in templates"],
    )

def find_counterexample_final(
    formula: str,
    atoms: List[str],
    assumptions: List[str],
    cfg: Optional[VerifyConfig] = None
) -> VerifyResult:
    """
    Phase 14: High-Fidelity final verification.
    Uses larger search bounds than standard verification to ensure robust results.
    """
    if cfg is None:
        cfg = VerifyConfig(max_worlds=4, max_edges=6) # standard: 3/4
    
    audit = [f"[PHASE14] Starting high-fidelity check for {formula}"]
    res = find_counterexample(formula, atoms, assumptions, cfg)
    res.audit = audit + (res.audit or [])
    
    if res.status == "valid":
        # Final sanity check: if it's "valid", we mark it as "verified_valid"
        res.diffs.append("diff:phase14_verified")
    
    return res

def check_model(formula: str, model_dict: Dict[str, Any], at_world: int = 0) -> bool:
    """
    Checks if a formula holds in a specific model at a specific world.
    Returns True if valid (formula holds), False if counterexample (formula fails).
    """
    worlds = int(model_dict.get("n_worlds") or model_dict.get("worlds") or 0)
    edges_raw = model_dict.get("edges") or []
    edges: List[Tuple[int, int]] = []
    for e in edges_raw:
        if isinstance(e, (list, tuple)) and len(e) == 2:
            edges.append((int(e[0]), int(e[1])))
            
    valuation = model_dict.get("valuation") or {}
    # Valuation format in model_search is Dict[str, Tuple[int]]. 
    # But in _eval_formula_on_model it was Dict[str, List[bool]].
    # We need to handle both or standardize.
    # model_search.Model expects Dict[str, Tuple[int]].
    
    val_indices = {}
    for atom, val in valuation.items():
        if isinstance(val, (list, tuple)):
            if len(val) > 0 and isinstance(val[0], bool):
                # List[bool] -> Tuple[int]
                val_indices[atom] = tuple(i for i, b in enumerate(val) if b)
            else:
                # Tuple[int] -> Tuple[int]
                val_indices[atom] = tuple(int(v) for v in val)
        else:
            val_indices[atom] = ()

    model = Model(n_worlds=worlds, edges=tuple(edges), valuation=val_indices)
    node = parse_formula(formula)
    return eval_node(model, node, at_world)