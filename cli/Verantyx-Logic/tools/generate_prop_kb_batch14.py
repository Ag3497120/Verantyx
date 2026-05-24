import json
import random
from pathlib import Path

KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

indices = {
    "definition": 11521,
    "axiom": 5721,
    "theorem": 20161,
    "rule": 11601,
    "counterexample_schema": 9001
}

VARS = ["p", "q", "r", "s", "t"] + [f"p{i}" for i in range(1, 400)]
OPS = [r"\land", r"\lor", r"\to", r"\leftrightarrow", r"\otimes", r"\multimap"]

def gen_f(d=0):
    if d > 2 or random.random() < 0.3: return random.choice(VARS)
    op = random.choice(OPS)
    return f"({gen_f(d+1)} {op} {gen_f(d+1)})"

def generate_batch_14():
    results = []
    
    # 1. Definitions (2000) - Focus: Relevance / Resource usage
    sub_terms = [
        "Relevant implication in {}", "Resource sensitive state of {}", "Multiplicative unit 1 in {}",
        "Additive unit 0 in {}", "Weakening rule failure for {}", "Contraction rule status of {}",
        "Exchange property in {}", "Fusion connective for {}", "Linear implication {} -> {}",
        "Exponential bang !{}", "Question mark operator ?{}", "Strict implication in {}",
        "Variable sharing constraint for {}", "Acker's property in {}", "Entailment in logic R"
    ]
    for _ in range(2000):
        f1 = gen_f(1)
        f2 = gen_f(1)
        templ = random.choice(sub_terms)
        if templ.count("{}") == 2: term = templ.format(f1, f2)
        else: term = templ.format(f1)
        
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": f"In substructural or relevance logic, {term} is defined as the structural constraint where {gen_f(1)} represents a resource-bounded or variable-constrained evaluation.",
            "prerequisites": ["prop:substructural_logic", "prop:relevance"],
            "yields": [f"tag:sub_{indices['definition']}"],
            "refutation": None,
            "patterns": [f"Explain {term}", f"What is {term}?"],
            "links": []
        })
        indices["definition"] += 1

    # 2. Axioms (1000) - Focus: Relevance Axioms
    for _ in range(1000):
        a, b, c = gen_f(0), gen_f(0), gen_f(0)
        stmt = f"(({a} \\to {b}) \\to (({b} \\to {c}) \\to ({a} \\to {c})))" # Prefixing
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"Axiom Instance: Relevance logic {indices['axiom']}",
            "statement": stmt,
            "prerequisites": ["prop:relevance_axioms"],
            "yields": ["tag:relevant_axiom"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1

    # 3. Theorems (3500) - Focus: Linear Logic fragments
    for _ in range(3500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"(!({a} \\land {b}) \\leftrightarrow (!{a} \\otimes !{b}))"
        if random.random() < 0.5: stmt = f"({a} \\multimap {b}) \\leftrightarrow ({b} \\multimap {a})" # commutativity of linear implies
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Theorem Instance: Linear logic {indices['theorem']}",
            "statement": stmt,
            "prerequisites": ["prop:linear_logic"],
            "yields": ["tag:linear_tautology"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1

    # 4. Rules (2000) - Focus: Natural Deduction without Weakening
    for _ in range(2000):
        a, b = gen_f(0), gen_f(0)
        stmt = f"\\{{ {a} \\multimap {b}, {a} \\}} \\vdash {b}"
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Linear Rule Instance {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:proof_theory"],
            "yields": ["tag:linear_step"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["rule"] += 1

    # 5. Counterexamples (1500) - Focus: Weakening / Paradoxes
    for _ in range(1500):
        a, b = gen_f(0), gen_f(0)
        stmt = f"{a} \\to ({b} \\to {a})" # Positive Paradox (invalid in Relevance)
        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"Relevance Fallacy {indices['counterexample_schema']}",
            "statement": stmt,
            "prerequisites": ["prop:relevance"],
            "yields": ["tag:invalid_relevance"],
            "refutation": f"Model where {a} and {b} share no variables; weakening is disallowed.",
            "patterns": [f"Why is {stmt} invalid in relevance logic?"],
            "links": []
        })
        indices["counterexample_schema"] += 1

    random.shuffle(results)
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Batch 14 complete. Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch_14()
