from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from avh_math.logic.prop_parse import Node, Not, And, Or, Imp, Iff

Literal = Tuple[str, bool]     # (var, True)=var, (var, False)=¬var
Clause = Set[Literal]
CNF = List[Clause]

def _neg(lit: Literal) -> Literal:
    v, pos = lit
    return (v, not pos)

@dataclass
class Tseytin:
    clauses: CNF
    mapping: Dict[Node, str]
    counter: int

def _new_var(t: Tseytin) -> str:
    t.counter += 1
    return f"t{t.counter}"

def _add_clause(t: Tseytin, lits: List[Literal]) -> None:
    t.clauses.append(set(lits))

def tseytin_cnf(root: Node) -> Tuple[CNF, str]:
    """
    Returns (CNF, top_var) such that CNF is satisfiable iff root is satisfiable,
    and top_var is the variable representing root's truth.
    """
    t = Tseytin(clauses=[], mapping={}, counter=0)

    def enc(n: Node) -> str:
        if n in t.mapping:
            return t.mapping[n]
        if n.op == "var":
            t.mapping[n] = n.name  # use original variable name
            return n.name

        v = _new_var(t)
        t.mapping[n] = v

        if n.op == "not":
            a = enc(n.a)
            # v <-> ¬a  => (v ∨ a) ∧ (¬v ∨ ¬a)
            _add_clause(t, [(v, True), (a, True)])
            _add_clause(t, [(v, False), (a, False)])
            return v
        
        # Binary ops
        a = enc(n.a)
        b = enc(n.b)

        if n.op == "and":
            # v <-> (a ∧ b)
            # (¬v ∨ a) ∧ (¬v ∨ b) ∧ (v ∨ ¬a ∨ ¬b)
            _add_clause(t, [(v, False), (a, True)])
            _add_clause(t, [(v, False), (b, True)])
            _add_clause(t, [(v, True), (a, False), (b, False)])
            return v

        if n.op == "or":
            # v <-> (a ∨ b)
            # (v ∨ ¬a) ∧ (v ∨ ¬b) ∧ (¬v ∨ a ∨ b)
            _add_clause(t, [(v, True), (a, False)])
            _add_clause(t, [(v, True), (b, False)])
            _add_clause(t, [(v, False), (a, True), (b, True)])
            return v

        if n.op == "imp":
            # (a -> b) == (¬a ∨ b)
            # v <-> (¬a ∨ b)
            # (v ∨ a) ∧ (v ∨ ¬b) ∧ (¬v ∨ ¬a ∨ b)
            _add_clause(t, [(v, True), (a, True)])
            _add_clause(t, [(v, True), (b, False)])
            _add_clause(t, [(v, False), (a, False), (b, True)])
            return v

        if n.op == "iff":
            # (a <-> b) == (a->b) ∧ (b->a)
            # Encode via v <-> ((¬a ∨ b) ∧ (¬b ∨ a))
            # But we can encode directly with 4 clauses:
            # v -> (a->b) and v -> (b->a) and (a->b & b->a) -> v
            # CNF for v <-> (a==b):
            # (¬v ∨ ¬a ∨ b) ∧ (¬v ∨ ¬b ∨ a) ∧ (v ∨ a ∨ b) ∧ (v ∨ ¬a ∨ ¬b)
            _add_clause(t, [(v, False), (a, False), (b, True)])
            _add_clause(t, [(v, False), (b, False), (a, True)])
            _add_clause(t, [(v, True), (a, True), (b, True)])
            _add_clause(t, [(v, True), (a, False), (b, False)])
            return v

        raise ValueError(f"Unknown op: {n.op}")

    top = enc(root)
    return (t.clauses, top)

def cnf_for_formula(root: Node) -> CNF:
    cnf, top = tseytin_cnf(root)
    # enforce top == True
    cnf.append({(top, True)})
    return cnf

def cnf_for_negation(root: Node) -> CNF:
    cnf, top = tseytin_cnf(root)
    # enforce top == False  (i.e., ¬root)
    cnf.append({(top, False)})
    return cnf
