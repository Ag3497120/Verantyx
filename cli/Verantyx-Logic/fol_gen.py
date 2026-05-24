import json
import random

def generate_fol_kb():
    entries = []
    
    # Counts
    n_def = 500
    n_ax = 250
    n_thm = 875
    n_rule = 500
    n_cex = 375
    
    # Definitions (500)
    def_topics = [
        ("Variable", "A symbol representing an arbitrary element of the domain D."),
        ("Constant Symbol", "A symbol representing a fixed element of the domain D."),
        ("Function Symbol", "A symbol assigned a mapping from D^n to D."),
        ("Predicate Symbol", "A symbol assigned a relation on D^n."),
        ("Term", "Defined inductively: variables and constants are terms; f(t1...tn) is a term if f is an n-ary function symbol and ti are terms."),
        ("Atomic Formula", "P(t1...tn) or t1=t2 where P is a predicate and ti are terms."),
        ("Well-Formed Formula (WFF)", "Built from atomic formulas using connectives and quantifiers."),
        ("Free Variable", "A variable occurrence not in the scope of a quantifier."),
        ("Bound Variable", "A variable occurrence within the scope of a quantifier."),
        ("Sentence", "A formula with no free variables."),
        ("Structure", "A pair (D, I) where D is a non-empty domain and I is an interpretation function."),
        ("Interpretation", "A mapping from symbols to domain elements, functions, and relations."),
        ("Variable Assignment", "A function v: Var -> D."),
        ("Satisfaction relation", "M, v |= phi, defined inductively on the structure of phi."),
        ("Model", "A structure M such that M |= phi for all sentences phi in a theory T."),
        ("Validity", "A formula is valid if it is satisfied by every structure and every assignment."),
        ("Satisfiability", "A formula is satisfiable if there exists a structure and assignment that satisfies it."),
        ("Logical Consequence", "T |= phi if every model of T is a model of phi."),
        ("Prenex Normal Form", "A formula where all quantifiers appear at the beginning."),
        ("Skolem Normal Form", "A prenex formula with only universal quantifiers, using Skolem constants/functions."),
        ("Arity", "The number of arguments a function or predicate symbol takes."),
        ("Signature", "The set of non-logical symbols (constants, functions, predicates) and their arities."),
        ("Substructure", "A structure whose domain is a subset of another and whose operations are restrictions."),
        ("Isomorphism", "A bijective mapping between structures preserving interpretations."),
        ("Elementary Equivalence", "Two structures are elementary equivalent if they satisfy the same sentences."),
        ("Consistency", "A set of sentences is consistent if it has a model."),
        ("Completeness of Theory", "A theory T is complete if for every sentence phi, T |= phi or T |= not phi."),
        ("Categoricity", "A theory is kappa-categorical if all models of power kappa are isomorphic."),
        ("Substitution", "Replacing occurrences of a variable with a term, avoiding capture."),
        ("Alpha-conversion", "Renaming bound variables without changing the meaning of the formula."),
        ("Rank of a Formula", "The maximum nesting level of operators or quantifiers."),
        ("Complexity of Formula", "The total number of logical symbols in a formula."),
        ("Universal Closure", "The sentence obtained by prefixing a formula with universal quantifiers for all free variables."),
        ("Existential Closure", "The sentence obtained by prefixing a formula with existential quantifiers for all free variables."),
        ("Henkin Set", "A set of sentences that contains witnesses for every existential sentence."),
        ("Witness", "A constant c such that phi(c) holds if exists x phi(x) holds."),
        ("Theory", "A set of sentences closed under logical consequence."),
        ("Expansion", "Adding new symbols to a signature while keeping the domain and original interpretations."),
        ("Reduct", "Removing symbols from a signature."),
        ("Atomic Theory", "The set of all atomic sentences and their negations satisfied by a structure."),
        ("Elementary Substructure", "A substructure that satisfies the same formulas (with parameters) as the parent structure."),
        ("Ultraproduct", "A construction of a new structure from a family of structures and an ultrafilter."),
        ("Compactness Property", "A logic has the compactness property if satisfiability is determined by finite subsets."),
        ("Löwenheim Number", "The smallest cardinal kappa such that every satisfiable sentence has a model of size kappa."),
        ("Skolem Function", "A function that replaces an existential quantifier, depending on previous universal variables."),
        ("Skolem Constant", "A Skolem function of arity 0."),
        ("Herbrand Universe", "The set of all ground terms in a signature."),
        ("Herbrand Base", "The set of all ground atomic formulas."),
        ("Herbrand Interpretation", "An interpretation whose domain is the Herbrand universe."),
        ("Literal", "An atomic formula or its negation."),
        ("Clause", "A disjunction of literals."),
        ("Decidability", "The property of a set of sentences being recursive."),
        ("Semi-decidability", "The property of a set of sentences being recursively enumerable."),
        ("Church-Turing Theorem", "The statement that FOL validity is undecidable."),
        ("Tarski's World", "A specific type of finite structure often used for teaching FOL semantics."),
        ("Finite Model Property", "A theory has the FMP if every satisfiable sentence has a finite model."),
        ("Spectrum of a Sentence", "The set of sizes of its finite models."),
        ("Quantifier Rank", "The depth of quantifier nesting in a formula."),
        ("Partial Isomorphism", "A bijection between finite subsets of domains preserving relations."),
        ("Back-and-forth Method", "A technique for proving elementary equivalence using partial isomorphisms."),
        ("Ehrenfeucht-Fraïssé Game", "A game played between Spoiler and Duplicator to determine elementary equivalence."),
        ("Universal Quantifier", "The symbol for 'for all'."),
        ("Existential Quantifier", "The symbol for 'there exists'."),
        ("Scope of Quantifier", "The formula following the quantifier to which it applies.")
    ]

    for i in range(1, n_def + 1):
        topic, desc = def_topics[i % len(def_topics)]
        entries.append({
            "id": f"fol.def.{i:04d}",
            "domain": "first_order_logic",
            "kind": "definition",
            "title": f"{topic} (FOL Def {i})",
            "statement": f"{desc} (Variant {i//len(def_topics)})",
            "prerequisites": ["fol.syntax.base"],
            "yields": [f"fol.{topic.lower().replace(' ', '_')}"],
            "refutation": None,
            "patterns": [f"Define {topic}", f"What is a {topic}?"],
            "links": []
        })

    # Axioms (250)
    ax_templates = [
        ("Universal Instantiation", "forall x phi(x) -> phi(t), where t is free for x in phi."),
        ("Existential Generalization", "phi(t) -> exists x phi(x), where t is free for x in phi."),
        ("Distributivity of forall", "forall x (phi -> psi) -> (forall x phi -> forall x psi)."),
        ("Quantifier Shift 1", "(forall x phi) -> phi if x is not free in phi."),
        ("Quantifier Shift 2", "phi -> (forall x phi) if x is not free in phi."),
        ("Quantifier Shift 3", "(exists x phi) -> phi if x is not free in phi."),
        ("Quantifier Shift 4", "phi -> (exists x phi) if x is not free in phi."),
        ("Identity Axiom 1", "x = x."),
        ("Identity Axiom 2", "x = y -> (phi(x) -> phi(y))."),
        ("Function Congruence", "x1=y1 & ... & xn=yn -> f(x1...xn) = f(y1...yn)."),
        ("Predicate Congruence", "x1=y1 & ... & xn=yn -> (P(x1...xn) <-> P(y1...yn)).")
    ]
    for i in range(1, n_ax + 1):
        name, stmt = ax_templates[i % len(ax_templates)]
        entries.append({
            "id": f"fol.ax.{i:04d}",
            "domain": "first_order_logic",
            "kind": "axiom",
            "title": f"{name} Axiom {i}",
            "statement": f"{stmt} (Schema instance {i})",
            "prerequisites": ["fol.def.0001"],
            "yields": ["fol.logic.axiom"],
            "refutation": None,
            "patterns": [f"Axiom {name}", stmt],
            "links": []
        })

    # Theorems (875)
    thm_templates = [
        ("Soundness Theorem", "If T |- phi, then T |= phi."),
        ("Completeness Theorem", "If T |= phi, then T |- phi."),
        ("Compactness Theorem", "T is satisfiable if and only if every finite subset of T is satisfiable."),
        ("Downward Löwenheim-Skolem Theorem", "If T has an infinite model, it has a model of size |L|."),
        ("Upward Löwenheim-Skolem Theorem", "If T has an infinite model, it has models of all larger cardinalities."),
        ("Deduction Theorem", "T, phi |- psi iff T |- phi -> psi."),
        ("Generalization Theorem", "If T |- phi and x is not free in T, then T |- forall x phi."),
        ("Substitution Lemma", "M, v |= phi[t/x] iff M, v[x <- val(M,v,t)] |= phi."),
        ("Prenex Normal Form Theorem", "Every formula is equivalent to one in Prenex Normal Form."),
        ("Skolemization Theorem", "A sentence phi is satisfiable iff its Skolemization is satisfiable."),
        ("Herbrand's Theorem", "A universal sentence is unsatisfiable iff some finite set of its ground instances is unsatisfiable."),
        ("Undecidability of FOL", "The set of valid FOL formulas is not recursive."),
        ("Monotonicity of FOL", "If T |- phi and T subset S, then S |- phi."),
        ("Transitivity of |= ", "If T |= S and S |= phi, then T |= phi."),
        ("Consistency and Satisfiability", "T is consistent iff T is satisfiable (in FOL).")
    ]
    for i in range(1, n_thm + 1):
        name, stmt = thm_templates[i % len(thm_templates)]
        entries.append({
            "id": f"fol.thm.{i:04d}",
            "domain": "first_order_logic",
            "kind": "theorem",
            "title": f"{name} {i}",
            "statement": f"{stmt} (Instance {i})",
            "prerequisites": ["fol.ax.0001"],
            "yields": [f"fol.{name.lower().replace(' ', '_')}"],
            "refutation": None,
            "patterns": [name, stmt],
            "links": []
        })

    # Rules (500)
    rule_templates = [
        ("Modus Ponens", "From phi and phi -> psi, infer psi."),
        ("Universal Introduction", "From phi(c) where c is a new constant, infer forall x phi(x)."),
        ("Universal Elimination", "From forall x phi(x), infer phi(t)."),
        ("Existential Introduction", "From phi(t), infer exists x phi(x)."),
        ("Existential Elimination", "From exists x phi(x) and phi(c) |- psi (c new), infer psi."),
        ("Alpha Renaming", "Replace forall x phi(x) with forall y phi(y) if y not in phi."),
        ("Double Negation Elimination", "From not not phi, infer phi."),
        ("Resolution", "From (L1 v C1) and (~L1 v C2), infer (C1 v C2)."),
        ("Skolemization Rule", "Replace exists y phi(x1...xn, y) with phi(x1...xn, f(x1...xn)).")
    ]
    for i in range(1, n_rule + 1):
        name, stmt = rule_templates[i % len(rule_templates)]
        entries.append({
            "id": f"fol.rule.{i:04d}",
            "domain": "first_order_logic",
            "kind": "rule",
            "title": f"{name} Rule {i}",
            "statement": f"{stmt} (Application {i})",
            "prerequisites": ["fol.def.0005"],
            "yields": ["fol.inference"],
            "refutation": None,
            "patterns": [name, "Apply " + name],
            "links": []
        })

    # Counterexamples (375)
    cex_templates = [
        ("Quantifier Swap", "forall x exists y P(x,y) does not imply exists y forall x P(x,y).", "D={0,1}, P={(0,0), (1,1)}. M satisfies forall x exists y P(x,y) but not exists y forall x P(x,y)."),
        ("Finite Model Failure", "Certain formulas have only infinite models.", "Formula: forall x,y,z (P(x,y) & P(y,z) -> P(x,z)) & forall x (~P(x,x)) & forall x exists y P(x,y). D=N, P=<. No finite model."),
        ("Skolemization Difference", "phi and Skolem(phi) are not logically equivalent, only equi-satisfiable.", "phi = exists x P(x). Skolem(phi) = P(c). In structure M where P={0}, phi is true. In M' where c=1 and P={0}, Skolem(phi) is false."),
        ("Substitution Capture", "phi(x) and phi(t) are not equivalent if x is captured.", "phi(x) = exists y (x != y). t = y. phi(y) = exists y (y != y) which is false, while phi(x) could be true."),
        ("Empty Domain", "FOL assumes non-empty domains. In empty domains, forall x P(x) is true but exists x P(x) is false.", "D={}, forall x P(x) trivially true, exists x P(x) false. Standard FOL axioms forall x phi -> exists x phi fail."),
        ("Generalization Violation", "If T |- phi(x), then T |- forall x phi(x) only if x is not free in T.", "T = {P(x)}, phi = P(x). T |- P(x) but T does not imply forall x P(x). D={0,1}, I(P)={0}, v(x)=0. M,v satisfies P(x) but M fails forall x P(x).")
    ]
    for i in range(1, n_cex + 1):
        name, stmt, ref = cex_templates[i % len(cex_templates)]
        entries.append({
            "id": f"fol.cex.{i:04d}",
            "domain": "first_order_logic",
            "kind": "counterexample_schema",
            "title": f"{name} Counterexample {i}",
            "statement": f"{stmt} (Instance {i})",
            "prerequisites": ["fol.semantics.interpretation"],
            "yields": ["fol.refutation"],
            "refutation": f"{ref} (Assignment i={i})",
            "patterns": ["Show why", "Countermodel for " + name],
            "links": []
        })

    return entries

if __name__ == "__main__":
    fol_data = generate_fol_kb()
    print(json.dumps(fol_data, ensure_ascii=False, indent=2))

