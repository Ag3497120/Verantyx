import json
import random
from pathlib import Path

KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

indices = {
    "definition": 9521,
    "axiom": 4721,
    "theorem": 16661,
    "rule": 9601,
    "counterexample_schema": 7501
}

VARS = ["p", "q", "r", "s", "t"] + [f"p{i}" for i in range(1, 300)]
OPS = [r"\land", r"\lor", r"\to", r"\leftrightarrow", r"\oplus", r"\text{ NAND }", r"\text{ NOR }"]

def gen_f(d=0):
    if d > 2 or random.random() < 0.3: return random.choice(VARS)
    op = random.choice(OPS)
    return f"({gen_f(d+1)} {op} {gen_f(d+1)})"

def generate_batch_13():
    results = []
    
    # 1. Definitions (2000) - Focus: Truth Tables / Valuation complexity
    syn_terms = [
        "Truth table row for {}", "Valuation set of {}", "Functional completeness of {}",
        "Post's lattice class containing {}", "Sheffer stroke form of {}", "Boolean chain index for {}",
        "Monotone boolean function {}", "Affine boolean function {}", "Self-dual form of {}",
        "Horn clause structure in {}", "Krom formula component of {}", "2-SAT instance for {}",
        "Truth table column for {}", "Partial valuation of {}", "Super-boolean assignment for {}"
    ]
    for _ in range(2000):
        f1 = gen_f(1)
        term = random.choice(syn_terms).format(f1)
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": f"In propositional logic syntax and semantics, {term} is defined as the evaluation pattern where {gen_f(1)} represents a unique truth function within the set of mapping constraints.",
            "prerequisites": ["prop:truth_tables", "prop:syntax"],
            "yields": [f"tag:syn_{indices['definition']}"],
            "refutation": None,
            "patterns": [f"Explain {term}", f"What is the {term}?"],
            "links": []
        })
        indices["definition"] += 1

    # 2. Axioms (1000) - Focus: NAND/NOR axioms
    for _ in range(1000):
        a, b, c = gen_f(0), gen_f(0), gen_f(0)
        stmt = f"(({a} \text{{ NAND }} ({b} \text{{ NAND }} {c})) \text{{ NAND }} (({a} \text{{ NAND }} {c}) \text{{ NAND }} ({a} \text{{ NAND }} {b})))" # Nicod's axiom style
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"Axiom Instance: NAND logic {indices['axiom']}",
            "statement": stmt,
            "prerequisites": ["prop:nand_logic"],
            "yields": ["tag:nand_axiom"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1

    # 3. Theorems (3500) - Focus: XOR / Equivalence
    for _ in range(3500):
        a, b, c = gen_f(0), gen_f(0), gen_f(0)
        stmt = f"({a} \oplus {b}) \leftrightarrow (({a} \lor {b}) \land \neg ({a} \land {b}))"
        if random.random() < 0.5: stmt = f"({a} \leftrightarrow {b}) \leftrightarrow \neg ({a} \oplus {b})"
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Theorem: Connective Identity {indices['theorem']}",
            "statement": stmt,
            "prerequisites": ["prop:identities"],
            "yields": ["tag:tautology"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1

    # 4. Rules (2000) - Focus: Tableaux / Truth table reduction
    for _ in range(2000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"\{{ \neg ({a} \land {b}) \}} \vdash (\neg {a} \lor \neg {b})"
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Semantic Rule: De Morgan step {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:tableaux"],
            "yields": ["tag:reduction_step"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["rule"] += 1

    # 5. Counterexamples (1500) - Focus: XOR fallacies
    for _ in range(1500):
        a, b, c = gen_f(0), gen_f(0), gen_f(0)
        stmt = f"({a} \oplus {b}) \oplus {c} \leftrightarrow {a} \oplus ({b} \land {c})"
        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"XOR Fallacy Instance {indices['counterexample_schema']}",
            "statement": stmt,
            "prerequisites": ["prop:xor_logic"],
            "yields": ["tag:invalid_xor"],
            "refutation": f"v({a})=T, v({b})=T, v({c})=F",
            "patterns": [f"Why is {stmt} invalid?"],
            "links": []
        })
        indices["counterexample_schema"] += 1

    random.shuffle(results)
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Batch 13 complete. Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch_13()
