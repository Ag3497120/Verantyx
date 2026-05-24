import json
import random
from pathlib import Path

KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

# Current max indices based on grep output
# definition 3520, rule 3600, theorem 6160, axiom 1720, counterexample_schema 3000
indices = {
    "definition": 3521,
    "axiom": 1721,
    "theorem": 6161,
    "rule": 3601,
    "counterexample_schema": 3001
}

VARS = ["p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z"] + [f"p{i}" for i in range(1, 100)]
OPS = [r"\land", r"\lor", r"\to", r"\leftrightarrow", r"\oplus", r"\text{ NAND }", r"\text{ NOR } "]

def gen_f(d=0):
    if d > 2 or random.random() < 0.3: return random.choice(VARS)
    if random.random() < 0.2: return f"\\neg {gen_f(d+1)}"
    return f"({gen_f(d+1)} {random.choice(OPS)} {gen_f(d+1)})"

def generate_batch_10():
    results = []
    
    # 1. Definitions (2000) - Focus: Intuitionistic/Kripke Semantics
    int_terms = [
        "Kripke frame world {}", "Forcing relation for {}", "Intuitionistic valuation of {}",
        "Persistence property in {}", "Monotonicity condition for {}", "Strong negation of {}",
        "Modal translation of {}", "Glivenko translation for {}", "Dummett logic factor {}",
        "Intermediate logic property of {}", "Finite model property for {}", "Heyting algebra element {}"
    ]
    for _ in range(2000):
        f = gen_f(1)
        term = random.choice(int_terms).format(f)
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": f"In intuitionistic propositional logic, {term} is defined as the state where the forcing relation $\\Vdash$ satisfies the persistence constraint for the subformula {gen_f(1)}.",
            "prerequisites": ["prop:intuitionistic", "prop:kripke_semantics"],
            "yields": [f"tag:int_{indices['definition']}"],
            "refutation": None,
            "patterns": [f"Define {term}", f"What is the {term} in intuitionism?"],
            "links": []
        })
        indices["definition"] += 1

    # 2. Axioms (1000) - Focus: Constructive Axioms
    for _ in range(1000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"({a} \\to ({b} \\to ({a} \\land {b})))" # Constructive conjunction
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"Axiom: Constructive Conjunction Instance {indices['axiom']}",
            "statement": stmt,
            "prerequisites": ["prop:intuitionistic_axioms"],
            "yields": ["tag:constructive_axiom"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1

    # 3. Theorems (3500) - Focus: Constructive Theorems
    for _ in range(3500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"(\\neg {a} \\lor \\neg {b}) \\to \\neg ({a} \\land {b})" # One direction of De Morgan (valid intuitionistically)
        if random.random() < 0.5: stmt = f"({a} \\to \\neg \\neg {a})"
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Theorem: Constructive Valid {indices['theorem']}",
            "statement": stmt,
            "prerequisites": ["prop:intuitionistic_logic"],
            "yields": ["tag:intuitionistic_tautology"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1

    # 4. Rules (2000) - Focus: Natural Deduction
    for _ in range(2000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"\\{{ {a}, {b} \\}} \\vdash ({a} \\land {b})"
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Rule: Conjunction Introduction {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:natural_deduction"],
            "yields": ["tag:intro_rule"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["rule"] += 1

    # 5. Counterexamples (1500) - Focus: LEM/DNE failures
    for _ in range(1500):
        a = gen_f(0)
        stmt = f"{a} \\lor \\neg {a}"
        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"LEM Failure: {a}",
            "statement": stmt,
            "prerequisites": ["prop:intuitionistic_logic"],
            "yields": ["tag:non_constructive"],
            "refutation": f"In a Kripke model world w where w does not force {a} and w has a future world w' that forces {a}, w does not force not {a}, hence w does not force {a} v not {a}.",
            "patterns": [f"Why does {stmt} fail intuitionistically?"],
            "links": []
        })
        indices["counterexample_schema"] += 1

    random.shuffle(results)
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Batch 10 complete. Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch_10()
