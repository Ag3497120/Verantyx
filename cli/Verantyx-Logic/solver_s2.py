#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase S2: Propositional Logic Resolution Solver (Proof Synthesizer)

Capabilities:
1. Parse propositional formula (using existing parser logic)
2. Convert to Negation Normal Form (NNF) -> CNF
3. Perform Resolution to find contradiction (refutation of negation = proof of validity)
4. Return structured proof trace
"""

from __future__ import annotations
import re
from typing import List, Set, Dict, Optional, Tuple, Any
from dataclasses import dataclass

# --- 1. Parser (Reuse/Adapt from Phase 28.4) ---

TOKEN_RE = re.compile(r"\s+")
VAR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

class PropNode:
    def __init__(self, kind: str, value: Any = None, left: Optional["PropNode"] = None, right: Optional["PropNode"] = None):
        self.kind = kind
        self.value = value
        self.left = left
        self.right = right

    def __repr__(self):
        if self.kind == "atom": return str(self.value)
        if self.kind == "const": return str(self.value)
        if self.kind == "not": return f"~{self.left}"
        return f"({self.left} {self.value} {self.right})"

def prop_tokenize(s: str) -> List[str]:
    s = s.replace("¬", "~").replace("∧", "&").replace("∨", "|").replace("→", "->").replace("↔", "<->")
    s = s.replace("(", " ( ").replace(")", " ) ")
    s = s.replace("<->", " <-> ").replace("->", " -> ")
    s = s.replace("&", " & ").replace("|", " | ").replace("~", " ~ ")
    s = TOKEN_RE.sub(" ", s).strip()
    return s.split(" ") if s else []

class PropParser:
    PRECEDENCE = {"<->": 1, "->": 2, "|": 3, "&": 4}
    def __init__(self, tokens: List[str]):
        self.toks = tokens
        self.i = 0
    def peek(self) -> Optional[str]:
        return self.toks[self.i] if self.i < len(self.toks) else None
    def pop(self) -> str:
        t = self.toks[self.i]; self.i += 1; return t
    def parse(self) -> PropNode:
        return self.parse_expr(0)
    def parse_expr(self, min_prec: int) -> PropNode:
        node = self.parse_prefix()
        while True:
            op = self.peek()
            if op not in self.PRECEDENCE or self.PRECEDENCE[op] < min_prec: break
            self.pop()
            rhs = self.parse_expr(self.PRECEDENCE[op] + (0 if op == "->" else 1))
            node = PropNode(kind="binop", value=op, left=node, right=rhs)
        return node
    def parse_prefix(self) -> PropNode:
        t = self.peek()
        if t == "~": self.pop(); return PropNode(kind="not", left=self.parse_prefix())
        if t == "(": self.pop(); n = self.parse_expr(0); self.pop(); return n
        self.pop()
        if t in ("T", "1"): return PropNode(kind="const", value=True)
        if t in ("F", "0"): return PropNode(kind="const", value=False)
        return PropNode(kind="atom", value=t)

# --- 2. CNF Converter ---

def to_nnf(node: PropNode) -> PropNode:
    # Eliminate <->, ->
    if node.kind == "binop":
        if node.value == "<->":
            # a <-> b  ===  (a -> b) & (b -> a)
            l, r = node.left, node.right
            return to_nnf(PropNode("binop", "&", 
                PropNode("binop", "->", l, r),
                PropNode("binop", "->", r, l)))
        if node.value == "->":
            # a -> b  ===  ~a | b
            return to_nnf(PropNode("binop", "|", 
                PropNode("not", left=node.left), 
                node.right))
        # Recurse for & / |
        return PropNode("binop", node.value, to_nnf(node.left), to_nnf(node.right))
    
    if node.kind == "not":
        # Push negation down
        child = node.left
        if child.kind == "not": return to_nnf(child.left) # ~~a -> a
        if child.kind == "binop":
            if child.value == "&": # ~(a & b) -> ~a | ~b
                return to_nnf(PropNode("binop", "|", 
                    PropNode("not", left=child.left), 
                    PropNode("not", left=child.right)))
            if child.value == "|": # ~(a | b) -> ~a & ~b
                return to_nnf(PropNode("binop", "&", 
                    PropNode("not", left=child.left), 
                    PropNode("not", left=child.right)))
            if child.value == "->": # ~(a -> b) -> a & ~b
                return to_nnf(PropNode("binop", "&", 
                    child.left, 
                    PropNode("not", left=child.right)))
        return PropNode("not", left=to_nnf(child)) # Literal negation
        
    return node # Atom or Const

def distribute_or_over_and(node: PropNode) -> PropNode:
    if node.kind == "binop":
        l = distribute_or_over_and(node.left)
        r = distribute_or_over_and(node.right)
        if node.value == "|":
            # (A & B) | C -> (A | C) & (B | C)
            if l.kind == "binop" and l.value == "&":
                return PropNode("binop", "&",
                    distribute_or_over_and(PropNode("binop", "|", l.left, r)),
                    distribute_or_over_and(PropNode("binop", "|", l.right, r)))
            # A | (B & C) -> (A | B) & (A | C)
            if r.kind == "binop" and r.value == "&":
                return PropNode("binop", "&",
                    distribute_or_over_and(PropNode("binop", "|", l, r.left)),
                    distribute_or_over_and(PropNode("binop", "|", l, r.right)))
        return PropNode("binop", node.value, l, r)
    return node

def flatten_cnf(node: PropNode) -> List[Set[str]]:
    # Returns list of clauses (set of literals). Literal: "p" or "~p"
    if node.kind == "binop" and node.value == "&":
        return flatten_cnf(node.left) + flatten_cnf(node.right)
    # Clause level (ORs)
    literals = set()
    def collect_lits(n):
        if n.kind == "binop" and n.value == "|":
            collect_lits(n.left); collect_lits(n.right)
        elif n.kind == "not":
            literals.add(f"~{n.left.value}")
        elif n.kind == "atom":
            literals.add(str(n.value))
        elif n.kind == "const":
            if n.value is False: pass # False in OR is identity
            else: literals.add("TRUE") # Tautology clause
    collect_lits(node)
    return [literals]

# --- 3. Resolution Engine ---

@dataclass
class ResolutionStep:
    id: int
    clause: Set[str]
    rule: str # "axiom", "resolvent"
    parents: List[int] # ids

def solve_resolution(clauses: List[Set[str]]) -> Optional[List[ResolutionStep]]:
    steps = []
    pool = [] # (clause_set, step_index)
    
    # Init
    for c in clauses:
        if "TRUE" in c: continue # Skip tautologies
        steps.append(ResolutionStep(len(steps)+1, c, "axiom", []))
        pool.append((c, len(steps)))

    # Simple BFS
    seen = set()
    
    # Add initial clauses to seen
    for c, _ in pool:
        seen.add(tuple(sorted(list(c))))

    new_gen = list(pool)
    
    while True:
        next_gen = []
        progress = False
        
        # Resolve new_gen against pool (including itself)
        for i in range(len(new_gen)):
            c1, id1 = new_gen[i]
            # Try against all existing
            for j in range(len(pool)):
                c2, id2 = pool[j]
                
                # Try to resolve c1 and c2
                res = try_resolve(c1, c2)
                if res is not None:
                    # Found resolvent
                    if not res: # Empty clause -> Contradiction!
                        final = ResolutionStep(len(steps)+1, set(), "resolvent", [id1, id2])
                        steps.append(final)
                        return trace_proof(steps, final)
                    
                    res_tuple = tuple(sorted(list(res)))
                    if res_tuple not in seen:
                        seen.add(res_tuple)
                        step = ResolutionStep(len(steps)+1, res, "resolvent", [id1, id2])
                        steps.append(step)
                        pool.append((res, step.id))
                        next_gen.append((res, step.id))
                        progress = True
                        if "TRUE" in res: continue # Optimization
        
        if not progress:
            return None # Satisfiable (no proof of negation)
        
        new_gen = next_gen

def try_resolve(c1: Set[str], c2: Set[str]) -> Optional[Set[str]]:
    # Look for complimentary literals p, ~p
    resolvable_vars = []
    for l1 in c1:
        var = l1[1:] if l1.startswith("~") else l1
        neg = l1[1:] if l1.startswith("~") else f"~{l1}"
        if neg in c2:
            resolvable_vars.append(l1)
    
    if len(resolvable_vars) == 1:
        # Resolve on this single variable
        pivot = resolvable_vars[0]
        neg_pivot = pivot[1:] if pivot.startswith("~") else f"~{pivot}"
        
        new_c = (c1 - {pivot}) | (c2 - {neg_pivot})
        
        # Check if tautology (contains a and ~a)
        for l in new_c:
            neg = l[1:] if l.startswith("~") else f"~{l}"
            if neg in new_c:
                return None # Tautology, ignore
        
        return new_c
    return None

def trace_proof(all_steps: List[ResolutionStep], final: ResolutionStep) -> List[ResolutionStep]:
    # Backtrack from empty clause
    needed = {final.id}
    q = [final]
    used_steps = []
    
    while q:
        curr = q.pop(0)
        used_steps.append(curr)
        for p_id in curr.parents:
            if p_id not in needed:
                needed.add(p_id)
                # Find parent obj
                parent = next(s for s in all_steps if s.id == p_id)
                q.append(parent)
    
    used_steps.sort(key=lambda s: s.id)
    return used_steps

def prove_prop_formula(formula_str: str) -> Dict[str, Any]:
    """
    To prove P, we refute ~P.
    1. Negate formula
    2. Convert to CNF
    3. Run Resolution
    4. If empty clause found -> Valid (Proof returned)
    5. If saturated without empty -> Invalid (Counterexample exists)
    """
    try:
        # Parse
        ast = PropParser(prop_tokenize(formula_str)).parse()
        # Negate
        neg_ast = PropNode("not", left=ast)
        # NNF -> CNF
        nnf = to_nnf(neg_ast)
        cnf_ast = distribute_or_over_and(nnf)
        clauses = flatten_cnf(cnf_ast)
        
        proof = solve_resolution(clauses)
        
        if proof:
            # Found contradiction in ~P -> P is Valid
            formatted_proof = []
            for s in proof:
                c_str = " v ".join(sorted(list(s.clause))) if s.clause else "⊥ (Contradiction)"
                if s.rule == "axiom":
                    formatted_proof.append(f"{s.id}. {c_str} [CNF Axiom]")
                else:
                    formatted_proof.append(f"{s.id}. {c_str} [Res {s.parents[0]}, {s.parents[1]}]")
            
            return {
                "verdict": "Valid",
                "proof": formatted_proof,
                "clauses": [list(c) for c in clauses]
            }
        else:
            return {
                "verdict": "Invalid", # or Unknown if timeout
                "proof": None
            }
            
    except Exception as e:
        return {"verdict": "Error", "error": str(e)}

if __name__ == "__main__":
    # Test
    fs = [
        "p -> p",
        "p -> (q -> p)",
        "(p -> q) -> (~q -> ~p)",
        "p -> q" # Invalid
    ]
    for f in fs:
        print(f"--- Proving: {f} ---")
        res = prove_prop_formula(f)
        if res["verdict"] == "Valid":
            print("Valid! Proof:")
            for line in res["proof"]: print(line)
        else:
            print(f"Not Valid ({res['verdict']})")
