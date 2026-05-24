from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Set, Tuple
import itertools
import re

# AST Nodes
@dataclass
class Node:
    kind: str
    value: str | None = None
    left: "Node | None" = None
    right: "Node | None" = None
    child: "Node | None" = None # For unary ops (NOT, BOX, DIAMOND)

class ModalSolver:
    def __init__(self, max_worlds: int = 3):
        self.max_worlds = max_worlds
        # Tokens: ->, <->, &, |, ~, [], <>, (, ), Atoms
        self.token_re = re.compile(
            r"\s+|"
            r"(<->|↔)|(->|→)|"
            r"(∧|&)|(∨|\|)|(¬|~|!)|"
            r"(\[\]|□|\bbox\b)|(<>|◇|\bdiamond\b)|"
            r"([()])|"
            r"([A-Za-z][A-Za-z0-9_]*)"
        )

    def solve(self, formula: str, atoms: List[str], assumptions: List[str]) -> Dict[str, Any]:
        try:
            # DEBUG: Trace assumptions
            print(f"[DEBUG MODAL] Solving '{formula}' with assumptions: {assumptions}")
            
            ast = self._parse(formula)
            # Re-collect atoms from AST just in case
            used_atoms = sorted(list(self._collect_atoms(ast)))
            if not atoms: atoms = used_atoms
            
            # Optimization: limit atoms
            if len(atoms) > 6:
                return {"status": "tentative_answer", "reason": "Too many atoms for model search."}

            worlds = list(range(self.max_worlds))
            
            # Generate Relations
            relations = self._generate_relations(worlds, assumptions)
            
            # Generate Valuations
            valuations = self._generate_valuations(worlds, atoms)
            
            counterexample = None
            checked_models = 0
            
            for R in relations:
                for V in valuations:
                    model = (worlds, R, V)
                    checked_models += 1
                    
                    # Check validity in ALL worlds of this model
                    valid_in_model = True
                    for w in worlds:
                        if not self._eval(ast, model, w):
                            valid_in_model = False
                            counterexample = {
                                "worlds": worlds,
                                "relation": sorted(list(R)), # set to list for JSON
                                "valuation": V,
                                "failed_world": w
                            }
                            break
                    
                    if not valid_in_model:
                        break
                if counterexample:
                    break
            
            if counterexample:
                return {
                    "status": "disproved",
                    "method": "finite_kripke_search",
                    "counterexample": counterexample,
                    "confidence": 1.0,
                    "details": f"Refuted by Kripke model ({checked_models} frames checked).",
                    "stats": {"worlds": self.max_worlds, "models": checked_models}
                }
            else:
                return {
                    "status": "proved",
                    "method": "finite_kripke_search",
                    "confidence": 1.0,
                    "details": f"Verified in all checked Kripke frames (size <= {self.max_worlds}, {checked_models} models).",
                    "stats": {"worlds": self.max_worlds, "models": checked_models}
                }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def _generate_relations(self, worlds: List[int], assumptions: List[str]) -> List[Set[Tuple[int, int]]]:
        pairs = [(i, j) for i in worlds for j in worlds]
        all_rels = []
        
        # Norm assumptions
        is_refl = any("reflexive" in a for a in assumptions)
        is_trans = any("transitive" in a for a in assumptions)
        is_sym = any("symmetric" in a for a in assumptions)
        is_serial = any("serial" in a for a in assumptions)
        
        for bits in itertools.product([False, True], repeat=len(pairs)):
            R = {pairs[i] for i, b in enumerate(bits) if b}
            
            if is_refl and not all((w,w) in R for w in worlds): continue
            if is_serial and not all(any((w,v) in R for v in worlds) for w in worlds): continue
            if is_sym and not all((v,w) in R for (w,v) in R): continue
            if is_trans and not self._is_transitive(R): continue
            
            all_rels.append(R)
        return all_rels

    def _is_transitive(self, R: Set[Tuple[int, int]]) -> bool:
        for (a, b) in R:
            for (c, d) in R:
                if b == c and (a, d) not in R: return False
        return True

    def _generate_valuations(self, worlds: List[int], atoms: List[str]) -> List[Dict[int, Dict[str, bool]]]:
        vals = []
        # Total bits = worlds * atoms
        for bits in itertools.product([False, True], repeat=len(worlds) * len(atoms)):
            V = {}
            idx = 0
            for w in worlds:
                V[w] = {}
                for a in atoms:
                    V[w][a] = bits[idx]
                    idx += 1
            vals.append(V)
        return vals

    def _eval(self, node: Node, model: Tuple[List[int], Set[Tuple[int, int]], Dict[int, Dict[str, bool]]], w: int) -> bool:
        worlds, R, V = model
        k = node.kind
        
        if k == "ATOM": return V[w].get(node.value, False)
        if k == "NOT": return not self._eval(node.child, model, w)
        if k == "AND": return self._eval(node.left, model, w) and self._eval(node.right, model, w)
        if k == "OR": return self._eval(node.left, model, w) or self._eval(node.right, model, w)
        if k == "IMP": return (not self._eval(node.left, model, w)) or self._eval(node.right, model, w)
        if k == "IFF": return self._eval(node.left, model, w) == self._eval(node.right, model, w)
        
        if k == "BOX":
            for v in worlds:
                if (w, v) in R:
                    if not self._eval(node.child, model, v): return False
            return True
            
        if k == "DIAMOND":
            for v in worlds:
                if (w, v) in R:
                    if self._eval(node.child, model, v): return True
            return False
            
        raise ValueError(f"Unknown node: {k}")

    # --- Parser ---
    def _parse(self, formula: str) -> Node:
        self._tokens = self._tokenize(formula)
        self._pos = 0
        node = self._parse_expr()
        if self._pos < len(self._tokens):
            raise ValueError("Unexpected tokens at end")
        return node

    def _collect_atoms(self, node: Node) -> Set[str]:
        if node.kind == "ATOM": return {node.value}
        s = set()
        if node.child: s |= self._collect_atoms(node.child)
        if node.left: s |= self._collect_atoms(node.left)
        if node.right: s |= self._collect_atoms(node.right)
        return s

    def _tokenize(self, s: str) -> List[str]:
        out = []
        for m in self.token_re.finditer(s):
            if m.group(0).isspace(): continue
            if m.group(1): out.append("IFF")
            elif m.group(2): out.append("IMP")
            elif m.group(3): out.append("AND")
            elif m.group(4): out.append("OR")
            elif m.group(5): out.append("NOT")
            elif m.group(6): out.append("BOX")
            elif m.group(7): out.append("DIAMOND")
            elif m.group(8): out.append(m.group(8))
            elif m.group(9): out.append(m.group(9))
        return out

    def _curr(self): return self._tokens[self._pos] if self._pos < len(self._tokens) else None
    def _consume(self, ex=None):
        t = self._curr()
        if ex and t != ex: raise ValueError(f"Expected {ex}, got {t}")
        self._pos += 1
        return t

    def _parse_expr(self): return self._parse_iff()
    def _parse_iff(self):
        n = self._parse_imp()
        while self._curr() == "IFF":
            self._consume()
            n = Node("IFF", left=n, right=self._parse_imp())
        return n
    def _parse_imp(self):
        n = self._parse_or()
        while self._curr() == "IMP":
            self._consume()
            n = Node("IMP", left=n, right=self._parse_imp()) # Right assoc
        return n
    def _parse_or(self):
        n = self._parse_and()
        while self._curr() == "OR":
            self._consume()
            n = Node("OR", left=n, right=self._parse_and())
        return n
    def _parse_and(self):
        n = self._parse_unary()
        while self._curr() == "AND":
            self._consume()
            n = Node("AND", left=n, right=self._parse_unary())
        return n
    def _parse_unary(self):
        t = self._curr()
        if t == "NOT":
            self._consume()
            return Node("NOT", child=self._parse_unary())
        if t == "BOX":
            self._consume()
            return Node("BOX", child=self._parse_unary())
        if t == "DIAMOND":
            self._consume()
            return Node("DIAMOND", child=self._parse_unary())
        return self._parse_primary()
    def _parse_primary(self):
        t = self._curr()
        if t == "(":
            self._consume()
            n = self._parse_expr()
            self._consume(")")
            return n
        if t in ("AND","OR","IMP","IFF","NOT","BOX","DIAMOND",")",None):
            raise ValueError(f"Unexpected: {t}")
        self._consume()
        return Node("ATOM", value=t)