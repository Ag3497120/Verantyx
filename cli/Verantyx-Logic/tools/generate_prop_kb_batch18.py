import json
import random
from pathlib import Path

KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

# Current max indices based on grep
indices = {
    "definition": 17521,
    "axiom": 8721,
    "theorem": 30661,
    "rule": 17601,
    "counterexample_schema": 13501
}

VARS = ["p", "q", "r", "s", "t"] + [f"p{i}" for i in range(1, 800)]
MODAL = [r"\square", r"\Diamond", r"[! \psi]", r"< ! \psi >", r"[\alpha]", r"< \alpha >"]
OPS = [r"\land", r"\lor", r"\to", r"\leftrightarrow"]

def gen_f(d=0):
    if d > 2 or random.random() < 0.3: return random.choice(VARS)
    r = random.random()
    if r < 0.15: return f"\\neg {gen_f(d+1)}"
    if r < 0.35: 
        m = random.choice(MODAL)
        return f"{m} {gen_f(d+1)}"
    op = random.choice(OPS)
    return f"({gen_f(d+1)} {op} {gen_f(d+1)})"

def generate_batch_18():
    results = []
    
    # 1. Definitions (2000) - Focus: Epistemic / Dynamic / PAL
    terms = [
        "Public announcement of {}", "Knowledge agent i knowing {}", "Group knowledge of {}",
        "Common knowledge of {}", "Dynamic program alpha executing {}", "Program composition alpha;beta",
        "Non-deterministic choice alpha U beta", "Kleene star alpha* in {}", "Atomic program pi affecting {}",
        "World transition under {}", "PAL reduction for {}", "Epistemic accessibility for world {}",
        "Bisimulation between frame W and W' for {}", "Modal depth of dynamic formula {}",
        "Resource bound in linear proof of {}", "Proof net component for {}"
    ]
    for _ in range(2000):
        f = gen_f(1)
        term = random.choice(terms).format(f)
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": f"In the extension of propositional logic (Dynamic/Epistemic), {term} is defined as the structural operation where the evaluation of {gen_f(1)} is constrained by the transition or knowledge state of the agent/program.",
            "prerequisites": ["prop:epistemic", "prop:dynamic"],
            "yields": [f"tag:dyn_{indices['definition']}"],
            "refutation": None,
            "patterns": [f"Define {term}", f"What is the semantic of {term}?"]
        })
        indices["definition"] += 1

    # 2. Axioms (1000) - Focus: Epistemic/PAL Axioms
    for _ in range(1000):
        a, b = gen_f(0), gen_f(0)
        # PAL reduction axioms
        stmt = f"([! {a}] {b} \\leftrightarrow ({a} \\to [! {a}] {b}))"
        if random.random() < 0.5: stmt = f"(\\square ({a} \\to {b}) \\to (\\square {a} \\to \\square {b}))" # K axiom for epistemic
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"Dynamic/Epistemic Axiom Instance {indices['axiom']}",
            "statement": stmt,
            "prerequisites": ["prop:modal_axioms", "prop:pal"],
            "yields": ["tag:dynamic_axiom"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1

    # 3. Theorems (3500) - Focus: Common Knowledge / Iteration
    for _ in range(3500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"(\\square {a} \\land \\square {b}) \\leftrightarrow \\square ({a} \\land {b})"
        if random.random() < 0.5: stmt = f"([! {a}] \\neg {b} \\leftrightarrow ({a} \\to \\neg [! {a}] {b}))"
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Epistemic Theorem {indices['theorem']}",
            "statement": stmt,
            "prerequisites": ["prop:epistemic_logic"],
            "yields": ["tag:epistemic_tautology"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1

    # 4. Rules (2000) - Focus: Modal / Sequent
    for _ in range(2000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"\\{{ \\vdash {a} \\}} \\implies \\{{ \\vdash [! {b}] {a} \\}}" # PAL rule
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Dynamic Inference Rule {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:proof_theory"],
            "yields": ["tag:dynamic_step"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["rule"] += 1

    # 5. Counterexamples (1500) - Focus: Knowledge failure / PAL paradox
    for _ in range(1500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"\\neg {a} \\to \\square \\neg {a}" # Negative introspection failure in non-S5
        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"Epistemic Fallacy in {indices['counterexample_schema']}",
            "statement": stmt,
            "prerequisites": ["prop:epistemic_logic"],
            "yields": ["tag:invalid_modal"],
            "refutation": f"Kripke model world w where {a} is false, but w sees w' where {a} is true. Then world w does not know not {a}.",
            "patterns": [f"Why does {stmt} fail in K4 logic?"]
        })
        indices["counterexample_schema"] += 1

    random.shuffle(results)
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Batch 18 complete. Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch_18()
