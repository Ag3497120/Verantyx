# avh_math/solvers/prop_truth_table.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
import itertools
import re

# Very small propositional parser:
# Supports: ¬, ~, !  (NOT)
#           ∧, &, and (AND)
#           ∨, |, or  (OR)
#           →, ->     (IMPLIES)
#           ↔, <->    (IFF)
#
# Atoms: A, B, P, Q, R, ... (single letter) or identifiers like p1, q_2

TOKEN_RE = re.compile(
    r"\s+|"
    r"(<->|↔|->|→|[()])|"
    r"(¬|~|!)|"
    r"(∧|&|\band\b)|"
    r"(∨|\||\bor\b)|"
    r"([A-Za-z_][A-Za-z0-9_]*)"
)

@dataclass
class Node:
    kind: str
    value: str | None = None
    left: "Node | None" = None
    right: "Node | None" = None

def _tokenize(s: str) -> List[str]:
    out: List[str] = []
    for m in TOKEN_RE.finditer(s):
        if m.group(0).isspace():
            continue
        tok = m.group(1) or m.group(2) or m.group(3) or m.group(4) or m.group(5)
        if tok is None:
            continue
        out.append(tok)
    return out

def _normalize_tokens(toks: List[str]) -> List[str]:
    norm = []
    for t in toks:
        tl = t.lower()
        if tl in ("and", "∧", "&"):
            norm.append("AND")
        elif tl in ("or", "∨", "|"):
            norm.append("OR")
        elif t in ("¬", "~", "!"):
            norm.append("NOT")
        elif t in ("->", "→"):
            norm.append("IMP")
        elif t in ("<->", "↔"):
            norm.append("IFF")
        elif t in ("(", ")"):
            norm.append(t)
        else:
            norm.append(t)  # atom
    return norm

class ParseError(Exception):
    pass

# Pratt parser precedence
PREC = {
    "IFF": 1,
    "IMP": 2,
    "OR": 3,
    "AND": 4,
}
RIGHT_ASSOC = {"IMP", "IFF"}

def parse_prop(expr: str) -> Tuple[Node, List[str]]:
    toks = _normalize_tokens(_tokenize(expr))
    if not toks:
        raise ParseError("empty")
    i = 0

    def peek() -> str | None:
        return toks[i] if i < len(toks) else None

    def consume(expected: str | None = None) -> str:
        nonlocal i
        if i >= len(toks):
            raise ParseError("unexpected EOF")
        t = toks[i]
        if expected is not None and t != expected:
            raise ParseError(f"expected {expected}, got {t}")
        i += 1
        return t

    def parse_primary() -> Node:
        t = peek()
        if t is None:
            raise ParseError("EOF in primary")
        if t == "NOT":
            consume("NOT")
            return Node(kind="NOT", left=parse_primary())
        if t == "(":
            consume("(")
            n = parse_expr(0)
            consume(")")
            return n
        if t in ("AND","OR","IMP","IFF",")"):
            raise ParseError(f"bad primary token: {t}")
        # atom
        consume()
        return Node(kind="ATOM", value=t)

    def parse_expr(min_prec: int) -> Node:
        left = parse_primary()
        while True:
            op = peek()
            if op not in PREC:
                break
            prec = PREC[op]
            if prec < min_prec:
                break
            consume()
            next_min = prec + (0 if op in RIGHT_ASSOC else 1)
            right = parse_expr(next_min)
            left = Node(kind=op, left=left, right=right)
        return left

    ast = parse_expr(0)
    if i != len(toks):
        raise ParseError(f"trailing tokens: {toks[i:]}")
    atoms = sorted({a for a in _collect_atoms(ast)})
    return ast, atoms

def _collect_atoms(n: Node):
    if n.kind == "ATOM" and n.value is not None:
        yield n.value
    if n.left:
        yield from _collect_atoms(n.left)
    if n.right:
        yield from _collect_atoms(n.right)

def eval_ast(n: Node, env: Dict[str, bool]) -> bool:
    k = n.kind
    if k == "ATOM":
        return bool(env[n.value])  # type: ignore[index]
    if k == "NOT":
        return not eval_ast(n.left, env)  # type: ignore[arg-type]
    if k == "AND":
        return eval_ast(n.left, env) and eval_ast(n.right, env)  # type: ignore[arg-type]
    if k == "OR":
        return eval_ast(n.left, env) or eval_ast(n.right, env)  # type: ignore[arg-type]
    if k == "IMP":
        a = eval_ast(n.left, env)   # type: ignore[arg-type]
        b = eval_ast(n.right, env)  # type: ignore[arg-type]
        return (not a) or b
    if k == "IFF":
        a = eval_ast(n.left, env)   # type: ignore[arg-type]
        b = eval_ast(n.right, env)  # type: ignore[arg-type]
        return a == b
    raise ValueError(k)

def is_tautology(expr: str) -> Dict[str, Any]:
    try:
        ast, atoms = parse_prop(expr)
        if len(atoms) == 0:
            v = eval_ast(ast, {})
            return {
                "is_tautology": bool(v),
                "atoms": [],
                "counterexample": None if v else {},
            }

        for bits in itertools.product([False, True], repeat=len(atoms)):
            env = dict(zip(atoms, bits))
            val = eval_ast(ast, env)
            if not val:
                return {
                    "is_tautology": False,
                    "atoms": atoms,
                    "counterexample": env,
                }
        return {
            "is_tautology": True,
            "atoms": atoms,
            "counterexample": None,
        }
    except Exception as e:
        return {
            "is_tautology": False,
            "error": str(e),
            "status": "parse_error"
        }
