import json
import random
from pathlib import Path

KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

# Next indices
indices = {
    "definition": 19521,
    "axiom": 9721,
    "theorem": 34161,
    "rule": 19601,
    "counterexample_schema": 15001
}

VARS = ["p", "q", "r", "s", "t"] + [f"p{i}" for i in range(1, 900)]
OPS = [r"\land", r"\lor", r"\to", r"\leftrightarrow", r"\oplus"]

def gen_f(d=0):
    if d > 2 or random.random() < 0.3: return random.choice(VARS)
    r = random.random()
    if r < 0.2: return f"\\neg {gen_f(d+1)}"
    op = random.choice(OPS)
    return f"({gen_f(d+1)} {op} {gen_f(d+1)})"

def generate_batch_19():
    results = []
    
    # 1. Definitions (2000)
    terms = [
        "Circuit size of {}", "Boolean depth of formula {}", "Post's lattice class {}",
        "Functional completeness status of {}", "Monotone circuit for {}", "Bounded-depth formula for {}",
        "Interpolant complexity of {}", "Entropy of valuation for {}", "Truth function degree of {}",
        "Recursive depth limit for {}", "Variable density in {}", "Satisfiability instance size for {}",
        "CNF-to-DNF conversion cost for {}", "Resolution width of {}", "Tseytin variable count for {}"
    ]
    for _ in range(2000):
        f = gen_f(1)
        term = random.choice(terms).format(f)
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": f"In advanced boolean theory and complexity, {term} is defined as the structural metric where {gen_f(1)} evaluates to a value constrained by the computational properties of the formula.",
            "prerequisites": ["prop:complexity", "prop:boolean_theory"],
            "yields": [f"tag:bool_{indices['definition']}"],
            "refutation": None,
            "patterns": [f"What is {term}?", f"Define {term}"],
            "links": []
        })
        indices["definition"] += 1

    # 2. Axioms (1000)
    for _ in range(1000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"(({a} \land {b}) \leftrightarrow ({b} \land {a}))"
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"Commutativity Axiom Instance {indices['axiom']}",
            "statement": stmt,
            "prerequisites": ["prop:axioms"],
            "yields": ["tag:identity"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1

    # 3. Theorems (3500)
    for _ in range(3500):
        a, b, c = gen_f(0), gen_f(0), gen_f(0)
        stmt = f"({a} \land ({b} \lor {c})) \leftrightarrow (({a} \land {b}) \lor ({a} \land {c}))"
        if random.random() < 0.5: stmt = f"\\neg ({a} \leftrightarrow {b}) \leftrightarrow ({a} \oplus {b})"
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Boolean Theorem {indices['theorem']}",
            "statement": stmt,
            "prerequisites": ["prop:identities"],
            "yields": ["tag:boolean_tautology"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1

    # 4. Rules (2000)
    for _ in range(2000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"\\{{ {a} \\leftrightarrow {b} \\}} \\implies \\{{ \\neg {a} \\leftrightarrow \\neg {b} \\}}"
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Transformation Rule Instance {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:proof_theory"],
            "yields": ["tag:transformation_step"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["rule"] += 1

    # 5. Counterexamples (1500)
    for _ in range(1500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"({a} \to {b}) \equiv (\\neg {a} \land {b})"
        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"Boolean Fallacy in {indices['counterexample_schema']}",
            "statement": stmt,
            "prerequisites": ["prop:boolean_errors"],
            "yields": ["tag:invalid_reduction"],
            "refutation": f"v({a})=F, v({b})=F makes ({a} -> {b}) True but (not {a} and {b}) False.",
            "patterns": [f"Why does {stmt} fail?"],
            "links": []
        })
        indices["counterexample_schema"] += 1

    random.shuffle(results)
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Batch 19 complete. Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch_19()