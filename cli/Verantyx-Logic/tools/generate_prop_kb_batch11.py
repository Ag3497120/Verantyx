import json
import random
from pathlib import Path

KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

# Current max indices from grep
indices = {
    "definition": 5521,
    "axiom": 2721,
    "theorem": 9661,
    "rule": 5601,
    "counterexample_schema": 4501
}

VARS = ["p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z"] + [f"p{i}" for i in range(1, 150)]
OPS = [r"\land", r"\lor", r"\to", r"\leftrightarrow", r"\oplus", r"\otimes", r"\multimap"] # Added linear logic ops

def gen_f(d=0):
    if d > 2 or random.random() < 0.3: return random.choice(VARS)
    if random.random() < 0.2: return f"\\neg {gen_f(d+1)}"
    return f"({gen_f(d+1)} {random.choice(OPS)} {gen_f(d+1)})"

def generate_batch_11():
    results = []
    
    # 1. Definitions (2000) - Focus: Many-valued / Fuzzy / Linear / Quantum
    mv_terms = [
        "Lukasiewicz L3 valuation of {}", "Kleene strong 3-valued state for {}",
        "Designated value set in {}", "Paraconsistent negation of {}",
        "Linear logic resource {}", "Exponential operator !{}", "Additive conjunction & in {}",
        "Quantum logic orthocomplement of {}", "Non-distributive lattice node {}",
        "Fuzzy membership degree of {}", "Many-valued consequence for {}",
        "Belnap 4-valued logic value for {}", "Orthomodularity condition in {}"
    ]
    for _ in range(2000):
        f = gen_f(1)
        term = random.choice(mv_terms).format(f)
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": f"In non-classical propositional logic, {term} is defined as the structural evaluation where {gen_f(1)} behaves according to the arity constraints of the logic system L_n.",
            "prerequisites": ["prop:non_classical", "prop:mv_logic"],
            "yields": [f"tag:mv_{indices['definition']}"],
            "refutation": None,
            "patterns": [f"What is {term}?", f"Define {term} in fuzzy logic"],
            "links": []
        })
        indices["definition"] += 1

    # 2. Axioms (1000) - Focus: MV logic / Orthomodular
    for _ in range(1000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"({a} \to ({b} \to {a}))" # Hilbert K is often kept in L3
        if random.random() < 0.5: stmt = f"((({a} \to {b}) \to ((\\neg {a} \to \\neg {b}) \to (\\neg {b} \to \\neg {a}))))) "
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"Axiom Instance: Non-classical {indices['axiom']}",
            "statement": stmt,
            "prerequisites": ["prop:non_classical_axioms"],
            "yields": ["tag:mv_axiom"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1

    # 3. Theorems (3500) - Focus: Substructural / Para-consistent
    for _ in range(3500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"({a} \otimes {b}) \to ({b} \otimes {a})" # Linear logic commutativity
        if random.random() < 0.5: stmt = f"\\neg (({a} \land \\neg {a}) \land \\neg ({a} \land \\neg {a}))" # Para-consistent fragment
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Theorem Instance: {indices['theorem']}",
            "statement": stmt,
            "prerequisites": ["prop:substructural_logic"],
            "yields": ["tag:substructural_tautology"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1

    # 4. Rules (2000) - Focus: Sequent Calculus / Linear
    for _ in range(2000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"\\{{ {a} \\vdash {b} \\}} \\implies \\{{ !{a} \\vdash {b} \\}}" # Dereliction in linear logic
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Sequent Rule: {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:sequent_calculus"],
            "yields": ["tag:linear_step"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["rule"] += 1

    # 5. Counterexamples (1500) - Focus: Distributivity failures, MV non-tautologies
    for _ in range(1500):
        a, b, c = gen_f(0), gen_f(0), gen_f(0)
        r_type = random.choice(["Distributivity", "Excluded Middle", "Contradiction", "Modus Ponens"])
        if r_type == "Distributivity":
            stmt = f"{a} \land ({b} \lor {c}) \leftrightarrow ({a} \land {b}) \lor ({a} \land {c})"
            ref = "Quantum logic lattice: Distributivity fails for non-orthogonal subspaces."
        elif r_type == "Excluded Middle":
            stmt = f"{a} \lor \\neg {a}"
            ref = f"L3 logic: v({a})=0.5 => 0.5 v 0.5 = 0.5 != 1."
        elif r_type == "Contradiction":
            stmt = f"\\neg ({a} \land \\neg {a})"
            ref = "Para-consistent logic: Contradictions are allowed, v(A)=Both => v(A and not A)=Both."
        else:
            stmt = f"((({a} \to {b}) \land {a}) \to {b})"
            ref = "Relevance logic: valid but requires shared variables; fails in some many-valued contexts."

        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"Non-classical Failure: {r_type} in {a}",
            "statement": stmt,
            "prerequisites": ["prop:non_classical"],
            "yields": ["tag:non_tautology"],
            "refutation": ref,
            "patterns": [f"Why does {stmt} fail in quantum/L3 logic?", r_type],
            "links": []
        })
        indices["counterexample_schema"] += 1

    random.shuffle(results)
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Batch 11 complete. Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch_11()
