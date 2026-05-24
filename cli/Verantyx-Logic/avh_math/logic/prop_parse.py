from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

# AST nodes
@dataclass(frozen=True)
class Node:
    op: str  # "var", "not", "and", "or", "imp", "iff"
    a: Optional[Node] = None
    b: Optional[Node] = None
    name: Optional[str] = None

def Var(name: str) -> Node:
    return Node(op="var", name=name)

def Not(x: Node) -> Node:
    return Node(op="not", a=x)

def And(a: Node, b: Node) -> Node:
    return Node(op="and", a=a, b=b)

def Or(a: Node, b: Node) -> Node:
    return Node(op="or", a=a, b=b)

def Imp(a: Node, b: Node) -> Node:
    return Node(op="imp", a=a, b=b)

def Iff(a: Node, b: Node) -> Node:
    return Node(op="iff", a=a, b=b)

# Tokenizer
OPS = {
    "¬": "NOT", "~": "NOT", "!": "NOT",
    "∧": "AND", "&": "AND",
    "∨": "OR",  "|": "OR",
    "→": "IMP", "->": "IMP",
    "↔": "IFF", "<->": "IFF",
    "(": "LP", ")": "RP",
}

def tokenize(s: str) -> List[str]:
    # multi-char operators first
    s = s.replace("<->", " ↔ ").replace("->", " → ")
    # space around single-char ops/parens
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch in ("(", ")"):
            out.append(ch); i += 1; continue
        # one-char operators
        if ch in OPS:
            out.append(OPS[ch]); i += 1; continue
        # variable/identifier (letters, digits, underscore)
        j = i
        while j < len(s) and (s[j].isalnum() or s[j] in ("_", ":")):
            j += 1
        if j == i:
            # Check for unicode operator that might be in OPS but not caught by single char check?
            # Actually above OPS check handles single char.
            # If we are here, it's an unexpected char
            raise ValueError(f"Unexpected char at {i}: {repr(ch)}")
        out.append("VAR:" + s[i:j])
        i = j
    return out

# Pratt parser
PRECEDENCE = {
    "IFF": 10,
    "IMP": 20,
    "OR":  30,
    "AND": 40,
    "NOT": 50,
}
RIGHT_ASSOC = {"IMP", "IFF"}  # treat as right-associative for parsing

class Parser:
    def __init__(self, tokens: List[str]):
        self.toks = tokens
        self.pos = 0

    def peek(self) -> Optional[str]:
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def take(self) -> str:
        t = self.peek()
        if t: self.pos += 1
        return t

    def parse_atom(self) -> Node:
        t = self.take()
        if not t: raise ValueError("Unexpected EOF")
        if t == "NOT":
            return Not(self.parse_expr(PRECEDENCE["NOT"]))
        if t == "LP":
            e = self.parse_expr(0)
            if self.take() != "RP":
                raise ValueError("Missing )")
            return e
        if t.startswith("VAR:"):
            return Var(t[4:])
        raise ValueError(f"Unexpected token: {t}")

    def parse_expr(self, min_prec: int) -> Node:
        left = self.parse_atom()
        while True:
            k = self.peek()
            if not k or k not in PRECEDENCE:
                break
            
            # Map token to precedence key if needed, but here tokens are already keys like AND, OR
            prec = PRECEDENCE[k]
            if prec < min_prec:
                break
            
            self.take() # consume op
            next_min = prec + (0 if k in RIGHT_ASSOC else 1)
            right = self.parse_expr(next_min)
            
            if k == "AND": left = And(left, right)
            elif k == "OR": left = Or(left, right)
            elif k == "IMP": left = Imp(left, right)
            elif k == "IFF": left = Iff(left, right)
            
        return left
    
    def parse(self) -> Node:
        return self.parse_expr(0)

def parse_prop(s: str) -> Node:
    toks = tokenize(s)
    return Parser(toks).parse()

def pretty(n: Node) -> str:
    if n.op == "var":
        return n.name or "?"
    if n.op == "not":
        return f"¬{pretty(n.a)}"
    a = pretty(n.a) if n.a else "?"
    b = pretty(n.b) if n.b else "?"
    sym = {"and":"∧","or":"∨","imp":"→","iff":"↔"}[n.op]
    return f"({a} {sym} {b})"