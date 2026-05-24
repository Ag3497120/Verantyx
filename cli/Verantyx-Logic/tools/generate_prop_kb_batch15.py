import json
import random
from pathlib import Path

KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

indices = {
    "definition": 13521,
    "axiom": 6721,
    "theorem": 23661,
    "rule": 13601,
    "counterexample_schema": 10501
}

VARS = ["p", "q", "r", "s", "t"] + [f"p{i}" for i in range(1, 500)]
OPS = [r"\\land", r"\\lor", r"\\to", r"\\leftrightarrow"]

def gen_f(d=0):
    if d > 2 or random.random() < 0.3: return random.choice(VARS)
    op = random.choice(OPS)
    return f"({gen_f(d+1)} {op} {gen_f(d+1)})"

def generate_batch_15():
    results = []
    
    # 1. Definitions
    para_terms = [
        "Dialetheic truth value for {}", "Evaluation Both in logic LP for {}", 
        "Evaluation Neither in FDE for {}", "Glut of truth in {}", "Gap of truth in {}",
        "Designated value set in para-consistent {}", "Consequence relation in logic RM",
        "Negation fixed point in {}", "Hyper-valuation of {}", "Constructive negation of {}",
        "De Morgan monoid element {}", "Kleene 4-valued state for {}", "Information state in {}"
    ]
    for _ in range(2000):
        f1 = gen_f(1)
        term = random.choice(para_terms).format(f1)
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": f"In paraconsistent logic or FDE, {term} is defined as the semantic state where {gen_f(1)} evaluates to a non-classical value designated as inconsistent or incomplete.",
            "prerequisites": ["prop:paraconsistent", "prop:semantics"],
            "yields": [f"tag:para_{indices['definition']}"],
            "refutation": None,
            "patterns": [f"What is {term}?", f"Define {term} in logic LP"],
            "links": []
        })
        indices["definition"] += 1

    # 2. Axioms
    for _ in range(1000):
        a = gen_f(0)
        stmt = f"({a} \\lor \\neg {a})"
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"Axiom Instance: LP {indices['axiom']}",
            "statement": stmt,
            "prerequisites": ["prop:lp_logic"],
            "yields": ["tag:lp_axiom"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1

    # 3. Theorems
    for _ in range(3500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"\\neg ({a} \\land {b}) \\leftrightarrow (\\neg {a} \\lor \\neg {b})"
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Theorem Instance: FDE {indices['theorem']}",
            "statement": stmt,
            "prerequisites": ["prop:fde_logic"],
            "yields": ["tag:fde_tautology"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1

    # 4. Rules
    for _ in range(2000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"\\{{ {a} \\land \\neg {a} \\}} \\nvdash {b}"
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Paraconsistent Rule {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:explosion_failure"],
            "yields": ["tag:non_explosive"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["rule"] += 1

    # 5. Counterexamples
    for _ in range(1500):
        a, b, c = gen_f(0), gen_f(0), gen_f(0)
        r_type = random.choice(["Ex Falso", "Disjunctive Syllogism", "Modus Ponens in RM"])
        if r_type == "Ex Falso":
            stmt = f"({a} \\land \\neg {a}) \\to {b}"
            ref = f"LP/FDE valuation v({a})=Both, v({b})=F."
        elif r_type == "Disjunctive Syllogism":
            stmt = f"(({a} \\lor {b}) \\land \\neg {a}) \\to {b}"
            ref = f"LP valuation v({a})=Both, v({b})=F."
        else:
            stmt = f"({a} \\to {b}) \\to (({a} \\land {c}) \\to {b})"
            ref = "Failure of strengthening in relevance contexts."

        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"Paraconsistent Failure: {r_type}",
            "statement": stmt,
            "prerequisites": ["prop:non_classical"],
            "yields": ["tag:invalid_inference"],
            "refutation": ref,
            "patterns": [f"Why does {stmt} fail?"],
            "links": []
        })
        indices["counterexample_schema"] += 1

    random.shuffle(results)
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Batch 15 complete. Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch_15()