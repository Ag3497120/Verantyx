from __future__ import annotations

from dataclasses import dataclass
from typing import Union, Dict, Any


@dataclass
class Var:
    name: str


@dataclass
class Not:
    child: "Expr"


@dataclass
class And:
    left: "Expr"
    right: "Expr"


@dataclass
class Or:
    left: "Expr"
    right: "Expr"


@dataclass
class Imp:
    left: "Expr"
    right: "Expr"


@dataclass
class Box:
    child: "Expr"


@dataclass
class Dia:
    child: "Expr"


@dataclass
class Iff:
    left: "Expr"
    right: "Expr"

Expr = Union[Var, Not, And, Or, Imp, Box, Dia, Iff]


def ast_to_dict(expr: Expr) -> Dict[str, Any]:
    if isinstance(expr, Var):
        return {"type": "var", "name": expr.name}
    if isinstance(expr, Not):
        return {"type": "not", "child": ast_to_dict(expr.child)}
    if isinstance(expr, And):
        return {"type": "and", "left": ast_to_dict(expr.left), "right": ast_to_dict(expr.right)}
    if isinstance(expr, Or):
        return {"type": "or", "left": ast_to_dict(expr.left), "right": ast_to_dict(expr.right)}
    if isinstance(expr, Imp):
        return {"type": "imp", "left": ast_to_dict(expr.left), "right": ast_to_dict(expr.right)}
    if isinstance(expr, Box):
        return {"type": "box", "child": ast_to_dict(expr.child)}
    if isinstance(expr, Dia):
        return {"type": "dia", "child": ast_to_dict(expr.child)}
    if isinstance(expr, Iff):
        return {"type": "iff", "left": ast_to_dict(expr.left), "right": ast_to_dict(expr.right)}
    return {"type": "unknown"}
