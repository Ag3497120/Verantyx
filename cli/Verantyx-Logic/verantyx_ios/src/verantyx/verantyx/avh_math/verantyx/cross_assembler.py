from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from avh_math.verantyx.cross_pieces import extract_pieces, assemble_candidates, CrossPieces
from avh_math.verantyx.shape_parser import parse_formula
from avh_math.verantyx.shape_ast import Var, Not, And, Or, Imp, Iff, Box, Dia, Expr


def enrich_cross_with_pieces(cross: Dict[str, Any]) -> Dict[str, Any]:
    pieces = extract_pieces(cross)
    assembled = assemble_candidates(pieces)
    cross.setdefault("meta", {})
    cross["meta"]["assembled"] = assembled
    return cross


@dataclass
class AssembledTask:
    task_id: str
    domain: str
    formula: str
    assumptions: List[str]
    atoms: List[str]
    notes: List[str]


def _mk(task_prefix: str, i: int) -> str:
    return f"{task_prefix}_{i:03d}"

def _ast_to_surface(expr: Expr) -> str:
    if isinstance(expr, Var):
        return expr.name
    if isinstance(expr, Not):
        return f"~{_ast_to_surface(expr.child)}"
    if isinstance(expr, Box):
        return f"[]{_ast_to_surface(expr.child)}"
    if isinstance(expr, Dia):
        return f"<>{_ast_to_surface(expr.child)}"
    if isinstance(expr, And):
        return f"({_ast_to_surface(expr.left)}&{_ast_to_surface(expr.right)})"
    if isinstance(expr, Or):
        return f"({_ast_to_surface(expr.left)}|{_ast_to_surface(expr.right)})"
    if isinstance(expr, Imp):
        return f"({_ast_to_surface(expr.left)}->{_ast_to_surface(expr.right)})"
    if isinstance(expr, Iff):
        return f"({_ast_to_surface(expr.left)}<->{_ast_to_surface(expr.right)})"
    return ""


def assemble_tasks(p: CrossPieces, max_tasks: int = 24) -> List[AssembledTask]:
    tasks: List[AssembledTask] = []
    base_assumptions = list(p.assumptions)
    base_atoms = list(p.atoms)

    if p.core_formula:
        tasks.append(
            AssembledTask(
                task_id=_mk("core", 0),
                domain=p.domain,
                formula=p.core_formula,
                assumptions=base_assumptions,
                atoms=base_atoms,
                notes=["core_formula"],
            )
        )

    for i, f in enumerate(p.syntax_formulas[: max_tasks - 1], start=1):
        tasks.append(
            AssembledTask(
                task_id=_mk("syn", i),
                domain=p.domain,
                formula=f,
                assumptions=base_assumptions,
                atoms=base_atoms,
                notes=["syntax_candidate"],
            )
        )

    if p.domain == "modal_logic":
        normalized: List[AssembledTask] = []
        for t in tasks:
            f = t.formula
            f2 = f.replace("□", "[]").replace("◇", "<>")
            f2 = f2.replace("box", "[]").replace("diamond", "<>")
            if f2 != f:
                normalized.append(
                    AssembledTask(
                        task_id=t.task_id + "_norm",
                        domain=t.domain,
                        formula=f2,
                        assumptions=t.assumptions,
                        atoms=t.atoms,
                        notes=t.notes + ["modal_normalized"],
                    )
                )
        tasks.extend(normalized)

    # AST-based canonicalization (robust candidate normalization)
    ast_cands: List[AssembledTask] = []
    for t in tasks:
        try:
            expr = parse_formula(t.formula)
        except Exception:
            continue
        canon = _ast_to_surface(expr)
        if canon and canon != t.formula:
            ast_cands.append(
                AssembledTask(
                    task_id=t.task_id + "_ast",
                    domain=t.domain,
                    formula=canon,
                    assumptions=t.assumptions,
                    atoms=t.atoms,
                    notes=t.notes + ["ast_canonical"],
                )
            )
    tasks.extend(ast_cands)

    return tasks[:max_tasks]
