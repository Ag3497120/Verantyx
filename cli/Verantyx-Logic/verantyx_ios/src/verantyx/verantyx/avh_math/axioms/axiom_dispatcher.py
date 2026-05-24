from __future__ import annotations

from typing import Dict, Optional, List
import re

def _strip(s: str) -> str:
    return (s or "").replace(" ", "").replace("(", "").replace(")", "").replace(",", "")

def _normalize_atoms(s: str) -> str:
    s = re.sub(r"\b[A-Z]\b", "p", s)
    s = re.sub(r"\b[qrs]\b", "q", s)
    return s

PROP_TAUTOLOGIES = {
    # Modus ponens / implication basics
    "((p->q)&p)->q",
    "(p&(p->q))->q",
    "p->(q->p)",
    "p->p",
    # And-elimination / introduction
    "(p&q)->p",
    "(p&q)->q",
    "p->(p&q)",
    "q->(p&q)",
    # Or-introduction
    "p->(p|q)",
    "q->(p|q)",
    # Double negation
    "p->~~p",
    "~~p->p",
    # Excluded middle / non-contradiction
    "p|~p",
    "~(p&~p)",
    # Implication to disjunction
    "(p->q)<->(~p|q)",
    # Or commutativity / and commutativity (schematic)
    "(p|q)<->(q|p)",
    "(p&q)<->(q&p)",
    "p->(p|(p&q))",
    "p->(p&(p|q))",
    "~(p&q)<->(~p|~q)",
    "~(p|q)<->(~p&~q)",
    "(p->q)->((q->r)->(p->r))",
    "(p->r)->((q->r)->((p|q)->r))",
    # Distributivity
    "p&(q|r)<->((p&q)|(p&r))",
    "p|(q&r)<->((p|q)&(p|r))",
    # Distribution of box over and (modal tautology in K)
    "[](p&q)->([]p&[]q)",
    # Absorption
    "p&(p|q)<->p",
    "p|(p&q)<->p",
    # Contraposition
    "(p->q)<->(~q->~p)",
    # Exportation
    "((p&q)->r)<->(p->(q->r))",
    # Peirce law
    "((p->q)->p)->p",
    # Reductio
    "(p->q)->((p->~q)->~p)",
    # Associativity
    "(p&q)&r<->p&(q&r)",
    "(p|q)|r<->p|(q|r)",
    # Idempotence
    "p&p<->p",
    "p|p<->p",
    # Or-elimination (other direction)
    "((p|q)->r)->((p->r)&(q->r))",
    # Implication from conjunction
    "p->(q->(p&q))",
    # Quantifier-like schemas (shallow, used only in FOL dispatcher)
    "forallxP(x)->P(c)",
    "P(c)->existsxP(x)",
    # Simplification / Addition variants
    "(p&q)->(q&p)",
    "(p|q)->(q|p)",
    "p->(q->p)",
    # Double negation for compound
    "~~(p&q)->(p&q)",
    "~~(p|q)->(p|q)",
    # Absorption (redundant but explicit)
    "p&(q|p)<->p",
    "p|(q&p)<->p",
    # Exportation (explicit direction)
    "((p&q)->r)->(p->(q->r))",
    # Importation (explicit direction)
    "(p->(q->r))->((p&q)->r)",
    # Hypothetical syllogism (schema)
    "(p->q)->((q->r)->(p->r))",
    # Resolution-style
    "((p|q)&(~p|r))->(q|r)",
    # Absorption variants
    "p|(p&q)<->p",
    "p&(p|q)<->p",
    # Exportation/importation with swapped order
    "((q&p)->r)->(q->(p->r))",
    "(q->(p->r))->((q&p)->r)",
    # Biconditional expansion
    "(p<->q)<->((p->q)&(q->p))",
    # Implication distribution over and/or (schemas)
    "(p->q)&(p->r)->(p->(q&r))",
    "(p->r)&(q->r)->((p|q)->r)",
    # De Morgan (one-way expansions)
    "~(p&q)->(~p|~q)",
    "~(p|q)->(~p&~q)",
    # Implication to contrapositive (directional)
    "(p->q)->(~q->~p)",
    # Weakening / strengthening
    "p->(q->p)",
    "p->(p|q)",
    # Disjunction commutes with implication (schema)
    "(p->r)->((p|q)->(r|q))",
    # Excluded middle for compound
    "(p&q)|~(p&q)",
    "(p|q)|~(p|q)",
    # Implication with truth/falsehood placeholders
    "p->(q|~q)",
    "(p&~p)->q",
    # Identities with constants (treated schematically)
    "p<->(p&true)",
    "p<->(p|false)",
    # Double implication chain
    "(p->q)->((q->p)->(p<->q))",
    # Curry/uncurry variants
    "(p->(q->r))<->((p&q)->r)",
    # Distributivity of -> over & (schema)
    "(p->(q&r))<->((p->q)&(p->r))",
    # Distributivity of -> over | (schema)
    "((p|q)->r)<->((p->r)&(q->r))",
    # De Morgan as biconditional
    "~(p&q)<->(~p|~q)",
    "~(p|q)<->(~p&~q)",
    # Absorption with implication
    "(p->q)->(p->(p&q))",
    "(p->q)->((p|q)->q)",
    # Or/and with implication
    "(p&q)->(p|q)",
    # Conditional proof schema
    "((p&q)->r)->(p->(q->r))",
    # Implication distribution with negation
    "(~p->~q)->(q->p)",
    # Exportation with swapped variables
    "((q&p)->r)<->(q->(p->r))",
    # Commutation of biconditional
    "(p<->q)<->(q<->p)",
    # Implication reflexivity with conjunction/disjunction
    "p->(p|p)",
    "p->(p&p)",
    # Tautological disjunction with implication
    "(p->q)|(q->p)",
}

PROP_CONTRADICTIONS = {
    "p&~p",
    "~(p|~p)",
    "(p&~p)|q",
    "p&~p&q",
    "~(p->p)",
    "p&~p&r",
    "~(p|~p)&q",
    "(p->q)&p&~q",
    "(p&~p)&(q|~q)",
    "p&~p&~(q|~q)",
    "p&~p&~p",
    "(p&~p)|(q&~q)",
}

MODAL_AXIOMS: Dict[str, Dict[str, List[str] | str]] = {
    "[](p->q)->([]p->[]q)": {"system": "K", "requires": []},
    "[]p->p": {"system": "T", "requires": ["reflexive"]},
    "[]p->[][]p": {"system": "4", "requires": ["transitive"]},
    "<>p->[]<>p": {"system": "5", "requires": ["euclidean"]},
    "<>p<->~[]~p": {"system": "K", "requires": []},
    "[]p<->~<>~p": {"system": "K", "requires": []},
    # B axiom (symmetry)
    "p->[]<>p": {"system": "B", "requires": ["symmetric"]},
    # D axiom (seriality)
    "[]p-><>p": {"system": "D", "requires": ["serial"]},
    # S4: T + 4 combined schema (pattern-only, requires both)
    "[]p->p&[]p->[][]p": {"system": "S4", "requires": ["reflexive", "transitive"]},
    # S5: T + 5 combined schema (pattern-only, requires both)
    "[]p->p&<>p->[]<>p": {"system": "S5", "requires": ["reflexive", "euclidean"]},
    # McKinsey (requires transitive + dense in some systems, keep as conditional)
    "[]<>p-><>[]p": {"system": "M", "requires": ["transitive"]},
    # Dual of D (seriality)
    "[]p<->~<>~p": {"system": "D", "requires": ["serial"]},
    # Converse Barcan (syntactic placeholder)
    "[]forallxP(x)->forallx[]P(x)": {"system": "CBF", "requires": []},
    # Barcan (syntactic placeholder)
    "forallx[]P(x)->[]forallxP(x)": {"system": "BF", "requires": []},
    # Necessitation-style schema (syntactic placeholder)
    "p->[]p": {"system": "N", "requires": []},
    # Symmetry equivalence (B alternative)
    "[]p-><>p": {"system": "D", "requires": ["serial"]},
    # 4 dual: <> <> p -> <> p (transitive)
    "<><>p-><>p": {"system": "4", "requires": ["transitive"]},
    # 5 dual: <>p -> <>[]p (euclidean)
    "<>p-><>[]p": {"system": "5", "requires": ["euclidean"]},
    # S4 duals
    "<>[]p->[]p": {"system": "S4", "requires": ["transitive", "reflexive"]},
    # S5 duals
    "[]<>p-><>p": {"system": "S5", "requires": ["euclidean", "reflexive"]},
    "<>[]p->[]p": {"system": "S5", "requires": ["euclidean", "reflexive"]},
    # Additional distribution (K)
    "[](p|q)->([]p|[]q)": {"system": "K", "requires": []},
    # Idempotence of box under transitivity/reflexivity (S4)
    "[][]p->[]p": {"system": "S4", "requires": ["transitive"]},
    # Euclidean equivalence forms (S5)
    "<>[]p-><>p": {"system": "S5", "requires": ["euclidean", "reflexive"]},
    # Modal excluded middle (schema, K)
    "[]p|~[]p": {"system": "K", "requires": []},
    # Modal tautologies (K, propositional lift)
    "[]p->[]p": {"system": "K", "requires": []},
    "([]p&[]q)->[]p": {"system": "K", "requires": []},
    "([]p&[]q)->[]q": {"system": "K", "requires": []},
    # Distribution consequences
    "[](p&q)->[]p": {"system": "K", "requires": []},
    "[](p&q)->[]q": {"system": "K", "requires": []},
}

LINEAR_ALGEBRA_FACTS: Dict[str, Dict[str, str]] = {
    "dimSym(n,R)": {
        "answer": "n(n+1)/2",
        "note": "Symmetric matrix has n diagonal + n(n-1)/2 off-diagonal",
    },
    "dimSkew(n,R)": {
        "answer": "n(n-1)/2",
        "note": "Skew-symmetric matrix has n(n-1)/2 degrees of freedom",
    },
    "dimSkew(n,C)": {
        "answer": "n(n-1)/2",
        "note": "Skew-symmetric complex matrices have n(n-1)/2 complex DOF",
    },
    "dimSym(n,C)": {
        "answer": "n(n+1)/2",
        "note": "Complex symmetric matrix has n(n+1)/2 degrees of freedom",
    },
    "dimHerm(n,C)": {
        "answer": "n^2",
        "note": "Hermitian matrices over C have n^2 real degrees of freedom",
    },
    "dimSkewHerm(n,C)": {
        "answer": "n^2",
        "note": "Skew-Hermitian matrices over C have n^2 real degrees of freedom",
    },
    "dimUpper(n,R)": {
        "answer": "n(n+1)/2",
        "note": "Upper triangular matrices have n(n+1)/2 entries",
    },
    "dimLower(n,R)": {
        "answer": "n(n+1)/2",
        "note": "Lower triangular matrices have n(n+1)/2 entries",
    },
    "dimStrictUpper(n,R)": {
        "answer": "n(n-1)/2",
        "note": "Strictly upper triangular matrices have n(n-1)/2 entries",
    },
    "dimStrictLower(n,R)": {
        "answer": "n(n-1)/2",
        "note": "Strictly lower triangular matrices have n(n-1)/2 entries",
    },
    "dimDiag(n,R)": {
        "answer": "n",
        "note": "Diagonal matrices have n degrees of freedom",
    },
    "dimTraceZero(n,R)": {
        "answer": "n^2-1",
        "note": "Trace-zero matrices form a codimension-1 subspace of M_n(R)",
    },
    "dimTraceZero(n,C)": {
        "answer": "n^2-1",
        "note": "Trace-zero matrices form a codimension-1 subspace of M_n(C)",
    },
    "dimGL(n,R)": {
        "answer": "n^2",
        "note": "GL(n,R) is open in M_n(R), dimension n^2",
    },
    "dimO(n,R)": {
        "answer": "n(n-1)/2",
        "note": "Orthogonal group O(n) has dimension n(n-1)/2",
    },
    "dimSO(n,R)": {
        "answer": "n(n-1)/2",
        "note": "Special orthogonal group SO(n) has dimension n(n-1)/2",
    },
    "dimU(n,C)": {
        "answer": "n^2",
        "note": "Unitary group U(n) has real dimension n^2",
    },
    "dimSU(n,C)": {
        "answer": "n^2-1",
        "note": "Special unitary group SU(n) has real dimension n^2-1",
    },
    "dimMat(m,n,R)": {
        "answer": "m*n",
        "note": "All m×n matrices over R have dimension m*n",
    },
    "dimMat(n,R)": {
        "answer": "n^2",
        "note": "All n×n matrices over R have n^2 entries",
    },
    "dimMat(m,n,C)": {
        "answer": "m*n",
        "note": "All m×n matrices over C have dimension m*n over C",
    },
    "dimMat(n,C)": {
        "answer": "n^2",
        "note": "All n×n matrices over C have dimension n^2 over C",
    },
    "dimSym(n,F)": {
        "answer": "n(n+1)/2",
        "note": "Symmetric matrices over any field have n(n+1)/2 entries",
    },
    "dimSkew(n,F)": {
        "answer": "n(n-1)/2",
        "note": "Skew-symmetric matrices over any field have n(n-1)/2 entries",
    },
    "dimMat(n,F)": {
        "answer": "n^2",
        "note": "All n×n matrices over a field have n^2 entries",
    },
    "dimNull(A:m×n)": {
        "answer": "n - rank(A)",
        "note": "Nullity formula for an m×n matrix",
    },
    "rankNullity(n)": {
        "answer": "rank(A)+nullity(A)=n",
        "note": "Rank–nullity theorem for linear maps to n-dimensional domain",
    },
    "dimSpan(v1,...,vk)": {
        "answer": "<=k",
        "note": "Dimension of span of k vectors is at most k",
    },
    "dimSum(U,V)": {
        "answer": "dim(U)+dim(V)-dim(U∩V)",
        "note": "Dimension formula for sum of subspaces",
    },
    "dimQuotient(V,W)": {
        "answer": "dim(V)-dim(W)",
        "note": "Dimension of quotient space V/W when W is a subspace of V",
    },
    "dimTensor(V,W)": {
        "answer": "dim(V)*dim(W)",
        "note": "Dimension of tensor product for finite-dimensional spaces",
    },
    "dimHom(V,W)": {
        "answer": "dim(V)*dim(W)",
        "note": "Dimension of Hom(V,W) for finite-dimensional spaces",
    },
    "dimEnd(V)": {
        "answer": "(dim V)^2",
        "note": "Dimension of End(V) for finite-dimensional spaces",
    },
    "dimKer(A)": {
        "answer": "nullity(A)",
        "note": "Kernel dimension equals nullity",
    },
    "dimIm(A)": {
        "answer": "rank(A)",
        "note": "Image dimension equals rank",
    },
    "dimRowSpace(A)": {
        "answer": "rank(A)",
        "note": "Row space dimension equals rank",
    },
    "dimColSpace(A)": {
        "answer": "rank(A)",
        "note": "Column space dimension equals rank",
    },
    "rankAT(A)": {
        "answer": "rank(A)",
        "note": "Rank of A equals rank of A^T",
    },
    "rankAAT(A)": {
        "answer": "rank(A)",
        "note": "Rank of A A^T equals rank of A",
    },
    "rankATA(A)": {
        "answer": "rank(A)",
        "note": "Rank of A^T A equals rank of A",
    },
    "dimOrthogonalComplement(U,n)": {
        "answer": "n - dim(U)",
        "note": "In R^n, dim(U⊥)=n-dim(U)",
    },
    "dimSum3(U,V,W)": {
        "answer": "dim(U)+dim(V)+dim(W)-dim(U∩V)-dim(U∩W)-dim(V∩W)+dim(U∩V∩W)",
        "note": "Inclusion-exclusion for three subspaces",
    },
    "rankI(A)": {
        "answer": "n",
        "note": "Identity matrix has full rank n",
    },
    "detI(A)": {
        "answer": "1",
        "note": "Identity matrix determinant is 1",
    },
    "detDiagonal(D)": {
        "answer": "product(diagonal entries)",
        "note": "Determinant of a diagonal matrix is the product of diagonal entries",
    },
    "detTriangular(T)": {
        "answer": "product(diagonal entries)",
        "note": "Determinant of triangular matrix is product of diagonal entries",
    },
    "traceDiagonal(D)": {
        "answer": "sum(diagonal entries)",
        "note": "Trace is sum of diagonal entries",
    },
    "traceAB(AB,BA)": {
        "answer": "tr(AB)=tr(BA)",
        "note": "Trace is invariant under cyclic permutation of product of two matrices",
    },
    "traceABC(ABC,BCA,CAB)": {
        "answer": "tr(ABC)=tr(BCA)=tr(CAB)",
        "note": "Trace is invariant under cyclic permutation of product",
    },
    "detAB(A,B)": {
        "answer": "det(AB)=det(A)det(B)",
        "note": "Determinant is multiplicative",
    },
    "detAT(A)": {
        "answer": "det(A^T)=det(A)",
        "note": "Determinant invariant under transpose",
    },
    "rankAT(A)": {
        "answer": "rank(A^T)=rank(A)",
        "note": "Rank invariant under transpose",
    },
    "rankI(A)": {
        "answer": "rank(I)=n",
        "note": "Identity matrix has full rank",
    },
    "traceLinear(aA,bB)": {
        "answer": "tr(aA+bB)=a tr(A)+b tr(B)",
        "note": "Trace is linear",
    },
    "detScalar(aA)": {
        "answer": "det(aA)=a^n det(A)",
        "note": "Scaling determinant by scalar for n×n matrix",
    },
    "rankScalar(aA)": {
        "answer": "rank(aA)=rank(A) (a≠0)",
        "note": "Nonzero scalar multiple does not change rank",
    },
    "rankProduct(AB)": {
        "answer": "rank(AB)≤min(rank(A),rank(B))",
        "note": "Rank inequality for product",
    },
    "rankSum(A,B)": {
        "answer": "rank(A+B)≤rank(A)+rank(B)",
        "note": "Subadditivity of rank",
    },
    "dimOrthogonalComplement(U,n)": {
        "answer": "n - dim(U)",
        "note": "Orthogonal complement in R^n",
    },
    "dimOrthogonalComplementC(U,n)": {
        "answer": "n - dim(U)",
        "note": "Orthogonal complement in C^n",
    },
    "dimImAT(A)": {
        "answer": "rank(A)",
        "note": "Image of A^T has dimension rank(A)",
    },
    "dimKerAT(A)": {
        "answer": "n - rank(A)",
        "note": "Kernel of A^T has dimension n-rank(A) for n columns",
    },
    "dimRowSpace(A)": {
        "answer": "rank(A)",
        "note": "Row space dimension equals rank",
    },
    "dimColSpace(A)": {
        "answer": "rank(A)",
        "note": "Column space dimension equals rank",
    },
    "rankSimilarity(PAPinv)": {
        "answer": "rank(PAP^{-1})=rank(A)",
        "note": "Rank invariant under similarity",
    },
    "detSimilarity(PAPinv)": {
        "answer": "det(PAP^{-1})=det(A)",
        "note": "Determinant invariant under similarity",
    },
    "traceSimilarity(PAPinv)": {
        "answer": "tr(PAP^{-1})=tr(A)",
        "note": "Trace invariant under similarity",
    },
    "dimInvertible(n)": {
        "answer": "n^2",
        "note": "Invertible matrices form an open dense subset of M_n(F)",
    },
    "dimSym(n,F)": {
        "answer": "n(n+1)/2",
        "note": "Symmetric matrices over any field have n(n+1)/2 entries",
    },
    "dimSkew(n,F)": {
        "answer": "n(n-1)/2",
        "note": "Skew-symmetric matrices over any field have n(n-1)/2 entries",
    },
    "dimUpper(n,F)": {
        "answer": "n(n+1)/2",
        "note": "Upper triangular matrices over a field have n(n+1)/2 entries",
    },
    "dimStrictUpper(n,F)": {
        "answer": "n(n-1)/2",
        "note": "Strictly upper triangular matrices have n(n-1)/2 entries",
    },
    "dimDiag(n,F)": {
        "answer": "n",
        "note": "Diagonal matrices have n degrees of freedom",
    },
    "detZeroRow(A)": {
        "answer": "det(A)=0",
        "note": "If a matrix has a zero row or column, determinant is 0",
    },
    "detRowSwap(A)": {
        "answer": "det(row_swap(A))=-det(A)",
        "note": "Row swap flips determinant sign",
    },
    "detRowScale(A)": {
        "answer": "det(scale_row(A, c))=c det(A)",
        "note": "Scaling a row scales determinant",
    },
    "detRowAdd(A)": {
        "answer": "det(row_add(A))=det(A)",
        "note": "Adding multiple of one row to another does not change determinant",
    },
    "detSingular(A)": {
        "answer": "det(A)=0",
        "note": "A is singular iff det(A)=0",
    },
    "detInvertible(A)": {
        "answer": "det(A)≠0",
        "note": "A is invertible iff det(A)≠0",
    },
    "rankInvertible(A)": {
        "answer": "rank(A)=n",
        "note": "A is invertible iff rank(A)=n",
    },
    "rankNullity(m,n)": {
        "answer": "rank(A)+nullity(A)=n",
        "note": "Rank–nullity for m×n matrix",
    },
    "dimSolutionAx0(n)": {
        "answer": "nullity(A)=n-rank(A)",
        "note": "Dimension of solution space of Ax=0 equals nullity",
    },
}

def _compact(s: str) -> str:
    return _normalize_atoms((s or "").replace(" ", "").replace("□", "[]").replace("◇", "<>").replace(",", ""))


def _compact_linear(s: str) -> str:
    f = _compact(s)
    f = f.replace("Sym", "Sym").replace("sym", "Sym")
    f = f.replace("Herm", "Herm").replace("herm", "Herm")
    f = f.replace("SkewHerm", "SkewHerm").replace("skewHerm", "SkewHerm")
    f = f.replace("Skew", "Skew").replace("skew", "Skew")
    f = f.replace("GL", "GL").replace("gl", "GL")
    f = f.replace("Mat", "Mat").replace("mat", "Mat")
    f = f.replace("Diag", "Diag").replace("diag", "Diag")
    f = f.replace("Upper", "Upper").replace("upper", "Upper")
    f = f.replace("StrictUpper", "StrictUpper").replace("strictUpper", "StrictUpper")
    f = f.replace("O", "O").replace("o", "O")
    f = f.replace("SO", "SO").replace("so", "SO")
    f = f.replace("U", "U").replace("u", "U")
    f = f.replace("SU", "SU").replace("su", "SU")
    return f


def dispatch_axiom(core_formula: str, domain: str, assumptions: Optional[List[str]] = None) -> Optional[Dict]:
    f = _compact(core_formula)
    assumptions = assumptions or []

    if domain == "propositional_logic":
        if f in PROP_TAUTOLOGIES:
            return {
                "status": "proved",
                "method": "axiom:propositional",
                "note": "Known tautology",
            }
        if f in PROP_CONTRADICTIONS:
            return {
                "status": "disproved",
                "method": "axiom:propositional",
                "note": "Known contradiction",
            }

    if domain == "modal_logic":
        if f in MODAL_AXIOMS:
            info = MODAL_AXIOMS[f]
            reqs = info.get("requires", [])
            if reqs and not all(f"assume:{r}" in assumptions or r in assumptions for r in reqs):
                return {
                    "status": "needs_assumptions",
                    "method": "axiom:modal",
                    "system": info.get("system"),
                    "note": f"Requires assumptions: {reqs}",
                    "missing_assumptions": reqs,
                }
            return {
                "status": "proved",
                "method": "axiom:modal",
                "system": info.get("system"),
            }
        # Distribution schema (if expressed in and-form)
        if f == _compact("[](p&q)->([]p&[]q)"):
            return {
                "status": "proved",
                "method": "axiom:modal",
                "system": "K",
                "note": "Distribution of □ over ∧",
            }

    if domain == "first_order_logic":
        f_q = _strip(f).replace("forall", "forall").replace("exists", "exists")
        if f_q in PROP_TAUTOLOGIES:
            return {
                "status": "proved",
                "method": "axiom:fol",
                "note": "Quantifier schema (intro/elim)",
            }
        if f_q in PROP_CONTRADICTIONS:
            return {
                "status": "disproved",
                "method": "axiom:fol",
                "note": "Quantifier schema contradiction",
            }

    if domain == "linear_algebra":
        key = _strip(_compact_linear(core_formula))
        if key in LINEAR_ALGEBRA_FACTS:
            info = LINEAR_ALGEBRA_FACTS[key]
            return {
                "status": "proved",
                "method": "axiom:linear_algebra",
                "answer": info["answer"],
                "note": info["note"],
            }

    return None
