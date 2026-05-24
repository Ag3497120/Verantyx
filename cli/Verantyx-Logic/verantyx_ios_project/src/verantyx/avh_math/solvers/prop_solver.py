from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import itertools
import re

# AST Nodes
@dataclass
class Node:
    kind: str
    value: str | None = None
    left: "Node | None" = None
    right: "Node | None" = None

class PropSolver:
    def __init__(self):
        # Tokens: ->, <->, &, |, ~, (, ), Atoms
        self.token_re = re.compile(
            r"\s+|"
            r"(<->|↔)|(->|→)|"
            r"(∧|&)|(∨|\|)|(¬|~|!)|"
            r"([()])|"
            r"([A-Za-z][A-Za-z0-9_]*)"
        )

    def solve(self, formula: str) -> Dict[str, Any]:
        try:
            ast, atoms = self._parse(formula)
            
            # Atomic Optimization: if atoms > 10, abort (too heavy)
            if len(atoms) > 10:
                return {
                    "status": "tentative_answer",
                    "reason": "Too many atoms for truth table."
                }

            counterexample = None
            
            # Exhaustive Search
            for bits in itertools.product([False, True], repeat=len(atoms)):
                valuation = dict(zip(atoms, bits))
                result = self._eval(ast, valuation)
                
                if not result:
                    counterexample = valuation
                    break
            
            if counterexample:
                return {
                    "status": "disproved",
                    "method": "truth_table",
                    "counterexample": counterexample,
                    "confidence": 1.0,
                    "details": f"Refuted by assignment: {counterexample}"
                }
            else:
                return {
                    "status": "proved",
                    "method": "truth_table",
                    "confidence": 1.0,
                    "details": f"Verified tautology ({2**len(atoms)} assignments checked)."
                }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def _parse(self, formula: str) -> tuple[Node, List[str]]:
        tokens = self._tokenize(formula)
        # Recursive Descent Parser (Simplified)
        self._pos = 0
        self._tokens = tokens
        
        ast = self._parse_expr()
        if self._pos < len(tokens):
            raise ValueError("Unexpected tokens at end")
            
        atoms = sorted(list(set(t for t in tokens if t not in ("AND", "OR", "NOT", "IMP", "IFF", "(", ")"))))
        return ast, atoms

    def _tokenize(self, s: str) -> List[str]:
        out = []
        for m in self.token_re.finditer(s):
            if m.group(0).isspace(): continue
            if m.group(1): out.append("IFF")
            elif m.group(2): out.append("IMP")
            elif m.group(3): out.append("AND")
            elif m.group(4): out.append("OR")
            elif m.group(5): out.append("NOT")
            elif m.group(6): out.append(m.group(6)) # ( )
            elif m.group(7): out.append(m.group(7)) # Atom
        return out

    def _curr(self):
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _consume(self, expected=None):
        t = self._curr()
        if expected and t != expected:
            raise ValueError(f"Expected {expected}, got {t}")
        self._pos += 1
        return t

    # Grammar:
    # Expr -> Iff
    # Iff  -> Imp { <-> Imp }
    # Imp  -> Or { -> Or }  (Right Associative for -> ?) Usually -> is right assoc: A->B->C = A->(B->C)
    # But here we use simple left assoc for simplicity or standard precedence
    # Let's use:
    # Expr -> Term { <-> Term }   (Low prec)
    # Term -> Factor { -> Factor } 
    # ...
    # Standard Precedence: (High) ~ > & > | > -> > <-> (Low)
    
    def _parse_expr(self): return self._parse_iff()

    def _parse_iff(self):
        node = self._parse_imp()
        while self._curr() == "IFF":
            self._consume()
            right = self._parse_imp()
            node = Node("IFF", left=node, right=right)
        return node

    def _parse_imp(self):
        node = self._parse_or()
        while self._curr() == "IMP":
            self._consume()
            right = self._parse_imp() # Right associative: A->(B->C)
            node = Node("IMP", left=node, right=right)
        return node

    def _parse_or(self):
        node = self._parse_and()
        while self._curr() == "OR":
            self._consume()
            right = self._parse_and()
            node = Node("OR", left=node, right=right)
        return node

    def _parse_and(self):
        node = self._parse_not()
        while self._curr() == "AND":
            self._consume()
            right = self._parse_not()
            node = Node("AND", left=node, right=right)
        return node

    def _parse_not(self):
        if self._curr() == "NOT":
            self._consume()
            return Node("NOT", left=self._parse_not())
        return self._parse_primary()

    def _parse_primary(self):
        t = self._curr()
        if t == "(":
            self._consume()
            n = self._parse_expr()
            self._consume(")")
            return n
        if t in ("AND", "OR", "IMP", "IFF", "NOT", ")", None):
            raise ValueError(f"Unexpected token: {t}")
        self._consume()
        return Node("ATOM", value=t)

    def _eval(self, node: Node, val: Dict[str, bool]) -> bool:
        if node.kind == "ATOM": return val[node.value]
        if node.kind == "NOT": return not self._eval(node.left, val)
        if node.kind == "AND": return self._eval(node.left, val) and self._eval(node.right, val)
        if node.kind == "OR": return self._eval(node.left, val) or self._eval(node.right, val)
        if node.kind == "IMP": return (not self._eval(node.left, val)) or self._eval(node.right, val)
        if node.kind == "IFF": return self._eval(node.left, val) == self._eval(node.right, val)
        return False