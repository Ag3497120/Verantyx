from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Union
import re

# -----------------------------
# AST
# -----------------------------
@dataclass
class Expr:
    pass

@dataclass
class Var(Expr):
    name: str

@dataclass
class Not(Expr):
    a: Expr

@dataclass
class And(Expr):
    a: Expr
    b: Expr

@dataclass
class Or(Expr):
    a: Expr
    b: Expr

@dataclass
class Imp(Expr):
    a: Expr
    b: Expr

@dataclass
class Iff(Expr):
    a: Expr
    b: Expr

# -----------------------------
# Parser
# -----------------------------
def _tokenize(s: str) -> List[str]:
    # Normalize
    s = s.replace("¬", "~").replace("∧", "&").replace("∨", "|").replace("→", "->").replace("↔", "<->")
    tokens = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "()~&|":
            tokens.append(ch)
            i += 1
            continue
        # multi-char ops
        if s.startswith("->", i):
            tokens.append("->")
            i += 2
            continue
        if s.startswith("<->", i):
            tokens.append("<->")
            i += 3
            continue
        # variable: [A-Za-z0-9_]+
        if ch.isalnum() or ch == "_":
            j = i
            while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                j += 1
            tokens.append(s[i:j])
            i = j
            continue
        raise ValueError(f"Unexpected char at {i}: {s[i:i+10]}")
    return tokens

class _Parser:
    def __init__(self, tokens: List[str]):
        self.toks = tokens
        self.i = 0

    def _peek(self) -> Optional[str]:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _eat(self, t: str) -> None:
        if self._peek() != t:
            raise ValueError(f"Expected {t}, got {self._peek()}")
        self.i += 1

    def parse(self) -> Expr:
        e = self._parse_iff()
        if self._peek() is not None:
            raise ValueError(f"Trailing tokens: {self.toks[self.i:]}")
        return e

    def _parse_iff(self) -> Expr:
        e = self._parse_imp()
        while self._peek() == "<->":
            self._eat("<->")
            r = self._parse_imp()
            e = Iff(e, r)
        return e

    def _parse_imp(self) -> Expr:
        e = self._parse_or()
        # right associative
        if self._peek() == "->":
            self._eat("->")
            r = self._parse_imp()
            return Imp(e, r)
        return e

    def _parse_or(self) -> Expr:
        e = self._parse_and()
        while self._peek() == "|":
            self._eat("|")
            r = self._parse_and()
            e = Or(e, r)
        return e

    def _parse_and(self) -> Expr:
        e = self._parse_not()
        while self._peek() == "&":
            self._eat("&")
            r = self._parse_not()
            e = And(e, r)
        return e

    def _parse_not(self) -> Expr:
        if self._peek() == "~":
            self._eat("~")
            return Not(self._parse_not())
        return self._parse_atom()

    def _parse_atom(self) -> Expr:
        t = self._peek()
        if t is None:
            raise ValueError("Unexpected EOF")
        if t == "(":
            self._eat("(")
            e = self._parse_iff()
            self._eat(")")
            return e
        # variable
        self.i += 1
        return Var(t)

def parse_expr(s: str) -> Expr:
    return _Parser(_tokenize(s)).parse()

# -----------------------------
# Tseitin CNF
# CNF = list of clauses, clause = list of ints
# var id: positive int, neg = -id
# -----------------------------
class _Tseitin:
    def __init__(self):
        self.var2id: Dict[str, int] = {}
        self.next_id = 1
        self.clauses: List[List[int]] = []
        self.aux_names: List[str] = []

    def _new_var(self, name: str) -> int:
        if name in self.var2id:
            return self.var2id[name]
        vid = self.next_id
        self.next_id += 1
        self.var2id[name] = vid
        return vid

    def _new_aux(self) -> int:
        name = f"__t{len(self.aux_names)+1}"
        self.aux_names.append(name)
        return self._new_var(name)

    def encode(self, e: Expr) -> int:
        if isinstance(e, Var):
            return self._new_var(e.name)

        if isinstance(e, Not):
            a = self.encode(e.a)
            v = self._new_aux()
            # v <-> ~a
            # (v -> ~a) and (~a -> v)
            self.clauses.append([-v, -a])
            self.clauses.append([a, v])
            return v

        if isinstance(e, And):
            a = self.encode(e.a)
            b = self.encode(e.b)
            v = self._new_aux()
            # v <-> (a & b)
            # v -> a, v -> b, (a & b) -> v
            self.clauses.append([-v, a])
            self.clauses.append([-v, b])
            self.clauses.append([-a, -b, v])
            return v

        if isinstance(e, Or):
            a = self.encode(e.a)
            b = self.encode(e.b)
            v = self._new_aux()
            # v <-> (a | b)
            self.clauses.append([-a, v])
            self.clauses.append([-b, v])
            self.clauses.append([-v, a, b])
            return v

        if isinstance(e, Imp):
            # (a -> b) is (~a | b)
            a = self.encode(e.a)
            b = self.encode(e.b)
            v = self._new_aux()
            # v <-> (~a | b)
            self.clauses.append([a, v])
            self.clauses.append([-b, v])
            self.clauses.append([-v, -a, b])
            return v

        if isinstance(e, Iff):
            # (a <-> b) is (a -> b) & (b -> a)
            # v <-> (a <-> b)
            # v -> (a -> b) => v -> (~a | b) => -v | -a | b
            # v -> (b -> a) => v -> (~b | a) => -v | -b | a
            # (a <-> b) -> v => (~a | b) & (~b | a) -> v 
            # ... simpler: v <-> (a=b)
            a = self.encode(e.a)
            b = self.encode(e.b)
            v = self._new_aux()
            # v -> (a=b) => (v & a -> b) & (v & b -> a)
            # -v | -a | b
            self.clauses.append([-v, -a, b])
            # -v | -b | a
            self.clauses.append([-v, -b, a])
            # (a=b) -> v => (a & b -> v) & (-a & -b -> v)
            # -a | -b | v
            self.clauses.append([-a, -b, v])
            # a | b | v
            self.clauses.append([a, b, v])
            return v
        
        raise TypeError(e)

def to_cnf(e: Expr) -> Tuple[List[List[int]], Dict[str, int]]:
    t = _Tseitin()
    root = t.encode(e)
    # enforce root true
    t.clauses.append([root])
    return t.clauses, t.var2id

# -----------------------------
# DPLL SAT Solver (small but works)
# -----------------------------
def _simplify(clauses: List[List[int]], lit: int) -> Optional[List[List[int]]]:
    new_cs: List[List[int]] = []
    for c in clauses:
        if lit in c:
            continue  # satisfied
        if -lit in c:
            nc = [x for x in c if x != -lit]
            if len(nc) == 0:
                return None
            new_cs.append(nc)
        else:
            new_cs.append(c)
    return new_cs

def _unit_propagate(clauses: List[List[int]], asn: Dict[int, bool]) -> Optional[Tuple[List[List[int]], Dict[int, bool]]]:
    changed = True
    while changed:
        changed = False
        unit = None
        for c in clauses:
            if len(c) == 1:
                unit = c[0]
                break
        if unit is None:
            break
        v = abs(unit)
        val = unit > 0
        if v in asn:
            if asn[v] != val:
                return None
        else:
            asn[v] = val
            changed = True
        out = _simplify(clauses, unit)
        if out is None:
            return None
        clauses = out
    return clauses, asn

def _choose_var(clauses: List[List[int]], asn: Dict[int, bool]) -> Optional[int]:
    for c in clauses:
        for lit in c:
            v = abs(lit)
            if v not in asn:
                return v
    return None

def dpll(clauses: List[List[int]], asn: Optional[Dict[int, bool]] = None) -> Optional[Dict[int, bool]]:
    if asn is None:
        asn = {}
    up = _unit_propagate(clauses, dict(asn))
    if up is None:
        return None
    clauses, asn = up
    if not clauses:
        return asn  # SAT
    v = _choose_var(clauses, asn)
    if v is None:
        return asn
    # try True then False
    for val in (True, False):
        lit = v if val else -v
        out = _simplify(clauses, lit)
        if out is None:
            continue
        asn2 = dict(asn)
        asn2[v] = val
        sat = dpll(out, asn2)
        if sat is not None:
            return sat
    return None

def solve_sat(formula: str) -> Tuple[bool, Optional[Dict[str, bool]]]:
    """
    Returns (is_satisfiable, valuation_for_original_vars or None)
    """
    expr = parse_expr(formula)
    cnf, var2id = to_cnf(expr)
    model = dpll(cnf)
    if model is None:
        return False, None
    # keep only original vars (exclude __t*)
    inv = {vid: name for name, vid in var2id.items()}
    valuation: Dict[str, bool] = {}
    for vid, val in model.items():
        name = inv.get(vid)
        if name and not name.startswith("__t"):
            valuation[name] = val
    return True, valuation

def solve_validity(formula: str) -> Tuple[bool, Optional[Dict[str, bool]]]:
    """
    Validity: formula is valid iff negation is UNSAT.
    Returns (is_valid, counterexample_valuation_if_invalid else None)
    """
    sat, val = solve_sat(f"~({formula})")
    if sat:
        # counterexample valuation makes ~formula true => formula false
        return False, val
    return True, None
