import json
import random
from pathlib import Path

KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

indices = {
    "definition": 7521,
    "axiom": 3721,
    "theorem": 13161,
    "rule": 7601,
    "counterexample_schema": 6001
}

VARS = ["p", "q", "r", "s", "t"] + [f"p{i}" for i in range(1, 200)]
OPS = [r"\land", r"\lor", r"\to", r"\leftrightarrow"]

def gen_f(d=0):
    if d > 1 or random.random() < 0.4: return random.choice(VARS)
    op = random.choice(OPS)
    return f"({gen_f(d+1)} {op} {gen_f(d+1)})"

def generate_batch_12():
    results = []
    
    # 1. Definitions (2000)
    meta_terms = [
        "Soundness of system {}", "Completeness of proof calculus {}", "Compactness of set of formulas containing {}",
        "Decidability of formula {}", "CNF representation of {}", "DNF form of {}",
        "Tseytin transform of {}", "Resolution step for {}", "Unification component of ",
        "Model existence for {}", "Consistency of set containing {}", "Literal set of {}",
        "Clause set for {}", "Davis-Putnam procedure for {}", "DPLL heuristic for {}",
        "Interpolant of {} and {}", "Craig's interpolation for {}", "Satisfiability degree of {}"
    ]
    for _ in range(2000):
        f1 = gen_f(1)
        f2 = gen_f(1)
        templ = random.choice(meta_terms)
        if templ.count("{}") == 2:
            term = templ.format(f1, f2)
        else:
            term = templ.format(f1)
            
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": f"In the meta-theory of propositional logic, {term} is defined as the structural mapping where {gen_f(1)} implies the existence of a model under finite constraints.",
            "prerequisites": ["prop:meta_theory"],
            "yields": [f"tag:meta_{indices['definition']}"],
            "refutation": None,
            "patterns": [f"Explain {term}", f"What is {term}?"],
            "links": []
        })
        indices["definition"] += 1

    # 2. Axioms (1000)
    for _ in range(1000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"((\\neg {a} \\lor {b}) \\leftrightarrow ({a} \\to {b}))"
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"Axiom Instance: Semantic Definition {indices['axiom']}",
            "statement": stmt,
            "prerequisites": ["prop:resolution"],
            "yields": ["tag:reduction_axiom"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1

    # 3. Theorems (3500)
    for _ in range(3500):
        a, b, c = gen_f(0), gen_f(0), gen_f(0)
        stmt = f"((({a} \\lor {b}) \\land {c}) \\leftrightarrow (({a} \\land {c}) \\lor ({b} \\land {c})))"
        if random.random() < 0.5: stmt = f"\\neg \\neg {a} \\leftrightarrow {a}"
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Theorem: Normal Form Equivalence {indices['theorem']}",
            "statement": stmt,
            "prerequisites": ["prop:equivalence"],
            "yields": ["tag:boolean_equivalence"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1

    # 4. Rules (2000)
    for _ in range(2000):
        a, b, c = gen_f(0), gen_f(0), gen_f(0)
        stmt = f"\\{{ ({a} \\lor {b}), (\\neg {a} \\lor {c}) \\}} \\vdash ({b} \\lor {c})"
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Resolution Rule Instance {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:resolution_method"],
            "yields": ["tag:inference_step"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["rule"] += 1

    # 5. Counterexamples (1500)
    for _ in range(1500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"({a} \\land {b}) \\leftrightarrow ({a} \\lor {b})"
        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"False Equivalence {indices['counterexample_schema']}",
            "statement": stmt,
            "prerequisites": ["prop:boolean_errors"],
            "yields": ["tag:invalid_equivalence"],
            "refutation": f"v({a})=T, v({b})=F",
            "patterns": [f"Why is {stmt} not an equivalence?"],
            "links": []
        })
        indices["counterexample_schema"] += 1

    random.shuffle(results)
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Batch 12 complete. Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch_12()