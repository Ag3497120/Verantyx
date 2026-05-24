import json
import random
from pathlib import Path

KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

indices = {
    "definition": 17521,
    "axiom": 8721,
    "theorem": 30661,
    "rule": 17601,
    "counterexample_schema": 13501
}

VARS = ["p", "q", "r", "s", "t"] + [f"p{i}" for i in range(1, 700)]
TEMP = [r"\bigcirc", r"\square", r"\Diamond", r"\mathcal{U}"]
OPS = [r"\land", r"\lor", r"\to", r"\leftrightarrow"]

def gen_f(d=0):
    if d > 2 or random.random() < 0.3: return random.choice(VARS)
    r = random.random()
    if r < 0.2: return f"\\neg {gen_f(d+1)}"
    if r < 0.4: 
        op = random.choice(TEMP)
        if op == r"\\mathcal{U}": return f"({gen_f(d+1)} {op} {gen_f(d+1)})")
        return f"{op} {gen_f(d+1)}"
    op = random.choice(OPS)
    return f"({gen_f(d+1)} {op} {gen_f(d+1)})"

def generate_batch_17():
    results = []
    
    # 1. Definitions
    temp_terms = [
        "Temporal next state for {}", "Future reachability of {}", "Global invariance of {}",
        "Until constraint between {} and {}", "LTL trace valuation for {}", "PDL program state for {}",
        "Execution path of program {}", "Test operator ?{} in PDL", "Star operator * iteration for {}",
        "Safety property of formula {}", "Liveness condition for {}", "Fairness constraint in {}"
    ]
    for _ in range(2000):
        f1 = gen_f(1)
        term = random.choice(temp_terms).format(f1)
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": f"In temporal or dynamic propositional logic, {term} is defined as the behavioral mapping where {gen_f(1)} describes a transition system property over discrete time or program execution.",
            "prerequisites": ["prop:ltl", "prop:pdl"],
            "yields": [f"tag:temp_{indices['definition']}"],
            "refutation": None,
            "patterns": [f"What is {term}?", f"Define {term} in temporal logic"],
            "links": []
        })
        indices["definition"] += 1

    # 2. Axioms
    for _ in range(1000):
        a = gen_f(0)
        stmt = f"(\square {a} \leftrightarrow ({a} \land \bigcirc \square {a}))"
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"LTL Expansion Axiom Instance",
            "statement": stmt,
            "prerequisites": ["prop:ltl_axioms"],
            "yields": ["tag:ltl_axiom"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1

    # 3. Theorems
    for _ in range(3500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"(\bigcirc ({a} \land {b}) \leftrightarrow (\bigcirc {a} \land \bigcirc {b}))"
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Theorem Instance: Temporal logic {indices['theorem']}",
            "statement": stmt,
            "prerequisites": ["prop:ltl"],
            "yields": ["tag:temporal_tautology"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1

    # 4. Rules
    for _ in range(2000):
        a = gen_f(0)
        stmt = f"\\{{ {a} \\to \\bigcirc {a} \\}} \\implies \\{{ {a} \\to \\square {a} \\}}"
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Temporal Induction Rule {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:proof_theory"],
            "yields": ["tag:ltl_step"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["rule"] += 1

    # 5. Counterexamples
    for _ in range(1500):
        a = gen_f(0)
        stmt = f"\\Diamond {a} \\to \\square {a}"
        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"Temporal Fallacy {indices['counterexample_schema']}",
            "statement": stmt,
            "prerequisites": ["prop:ltl"],
            "yields": ["tag:ltl_invalid"],
            "refutation": f"Trace where {a} holds at t=1 but not t=2.",
            "patterns": [f"Why does {stmt} fail?"],
            "links": []
        })
        indices["counterexample_schema"] += 1

    random.shuffle(results)
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Batch 17 complete. Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch_17()
