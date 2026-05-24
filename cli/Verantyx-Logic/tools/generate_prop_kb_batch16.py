import json
import random
from pathlib import Path

KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

indices = {
    "definition": 15521,
    "axiom": 7721,
    "theorem": 27161,
    "rule": 15601,
    "counterexample_schema": 12001
}

VARS = ["p", "q", "r", "s", "t"] + [f"p{i}" for i in range(1, 600)]
MODAL = [r"\square", r"\Diamond"]
OPS = [r"\land", r"\lor", r"\to", r"\leftrightarrow"]

def gen_f(d=0):
    if d > 2 or random.random() < 0.3: return random.choice(VARS)
    r = random.random()
    if r < 0.2: return f"\\neg {gen_f(d+1)}"
    if r < 0.4: return f"{random.choice(MODAL)} {gen_f(d+1)}"
    op = random.choice(OPS)
    return f"({gen_f(d+1)} {op} {gen_f(d+1)})"

def generate_batch_16():
    results = []
    
    # 1. Definitions (2000) - Focus: Modal / Kripke
    modal_terms = [
        "Modal accessibility world {}", "Necessity operator scope in {}", "Possibility valuation for {}",
        "Reflexivity of frame world {}", "Transitivity of modal relation in {}",
        "Euclidean property for world {}", "Seriality condition in frame {}",
        "Modal translation of propositional {}", "Boxed formula {} strength",
        "Diamond formula {} reachable set", "Normal modal system logic K",
        "Modal fixed point for {}", "Bisimulation component for {}"
    ]
    for _ in range(2000):
        f1 = gen_f(1)
        term = random.choice(modal_terms).format(f1)
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": f"In modal propositional logic, {term} is defined as the property where {gen_f(1)} evaluates within a Kripke frame world satisfying the given accessibility constraints.",
            "prerequisites": ["prop:modal_logic", "prop:kripke_semantics"],
            "yields": [f"tag:modal_{indices['definition']}"],
            "refutation": None,
            "patterns": [f"What is {term}?", f"Define {term}"],
            "links": []
        })
        indices["definition"] += 1

    # 2. Axioms (1000) - Focus: Modal Axioms (K, T, 4, 5)
    for _ in range(1000):
        a, b = gen_f(0), gen_f(0)
        a_type = random.choice(["K", "T", "4", "5", "D"])
        if a_type == "K": stmt = f"(\square ({a} \to {b}) \to (\square {a} \to \square {b}))"
        elif a_type == "T": stmt = f"(\square {a} \to {a})"
        elif a_type == "4": stmt = f"(\square {a} \to \square \square {a})"
        elif a_type == "5": stmt = f"(\Diamond {a} \to \square \Diamond {a})"
        else: stmt = f"(\square {a} \to \Diamond {a})"
        
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"Modal Axiom {a_type} Instance",
            "statement": stmt,
            "prerequisites": ["prop:modal_axioms"],
            "yields": [f"tag:modal_axiom_{a_type}"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1

    # 3. Theorems (3500) - Focus: Modal Tautologies
    for _ in range(3500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"(\square ({a} \land {b}) \leftrightarrow (\square {a} \land \square {b}))"
        if random.random() < 0.5: stmt = f"(\Diamond {a} \leftrightarrow \neg \square \neg {a})"
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Theorem Instance: Modal logic {indices['theorem']}",
            "statement": stmt,
            "prerequisites": ["prop:modal_logic"],
            "yields": ["tag:modal_tautology"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1

    # 4. Rules (2000) - Focus: Necessitation / Distributivity
    for _ in range(2000):
        a = gen_f(0)
        stmt = f"\\{{ \\vdash {a} \\}} \\implies \\{{ \\vdash \\square {a} \\}}" # Necessitation
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Modal Rule: Necessitation {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:modal_logic"],
            "yields": ["tag:modal_step"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["rule"] += 1

    # 5. Counterexamples (1500) - Focus: Modal failures (e.g. Diamond dist over land)
    for _ in range(1500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"\Diamond ({a} \land {b}) \leftrightarrow (\Diamond {a} \land \Diamond {b})"
        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"Modal Fallacy: Diamond over Land in {indices['counterexample_schema']}",
            "statement": stmt,
            "prerequisites": ["prop:modal_logic"],
            "yields": ["tag:modal_invalid"],
            "refutation": f"Frame world w sees w1 where {a} holds and w2 where {b} holds, but no world sees a world where both hold.",
            "patterns": [f"Why does {stmt} fail in modal logic?"],
            "links": []
        })
        indices["counterexample_schema"] += 1

    random.shuffle(results)
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Batch 16 complete. Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch_16()
