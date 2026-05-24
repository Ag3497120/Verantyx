import json
import random
import re
from pathlib import Path

# Target Path
KB_PATH = Path("/Users/motonishikoudai/avh_math/avh_math/db/foundation_kb.jsonl")

def load_statement_hashes():
    seen = set()
    if not KB_PATH.exists():
        return seen
    with KB_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            stmt = (obj.get("statement") or "").strip()
            if stmt:
                seen.add(stmt)
    return seen

def get_next_indices():
    counts = {"definition": 1, "axiom": 1, "theorem": 1, "rule": 1, "counterexample_schema": 1}
    if not KB_PATH.exists():
        return counts
    
    with KB_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                if obj.get("domain") != "propositional_logic":
                    continue
                # ID format: prop.kind.index
                parts = obj["id"].split(".")
                if len(parts) == 3:
                    k = parts[1]
                    idx = int(parts[2])
                    if k in counts:
                        counts[k] = max(counts[k], idx + 1)
            except:
                continue
    return counts

# Logic Components
VARS = ["p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z"] + [f"p{i}" for i in range(1, 50)] + [f"q{i}" for i in range(1, 50)]
OPS = [r"\land", r"\lor", r"\to", r"\leftrightarrow", r"\oplus"]
CONSTANTS = [r"\top", r"\bot"]

def gen_formula(depth=0):
    if depth > 2 or random.random() < 0.3:
        if random.random() < 0.1:
            return random.choice(CONSTANTS)
        return random.choice(VARS)
    
    r = random.random()
    if r < 0.2:
        return f"\\neg {gen_formula(depth + 1)}"
    else:
        op = random.choice(OPS)
        return f"({gen_formula(depth + 1)} {op} {gen_formula(depth + 1)})"

def generate_batch():
    indices = get_next_indices()
    results = []
    seen_statements = load_statement_hashes()
    
    # Kind and Counts
    target_counts = {
        "definition": 2000,
        "axiom": 1000,
        "theorem": 3500,
        "rule": 2000,
        "counterexample_schema": 1500
    }
    
    # 1. Definitions
    def_terms = [
        "Polarity of {} in {}", "Main Connective of {}", "Subformula structure of {}", 
        "Truth assignment for {}", "Valuation mapping of {}", "Satisfiability of {}", 
        "Tautological status of {}", "Contradiction form of {}", "Contingent formula {}",
        "Literal component of {}", "Clause in {}", "Dual of {}", "Normal form of {}",
        "CNF conversion of {}", "DNF decomposition of {}", "Tseytin variable for {}",
        "Interpolant of {} and {}", "Definability of {} using {}", "Complexity of {}",
        "Formula depth of {}", "Variable set of {}", "Recursive step for {}",
        "Boolean function represented by {}", "Semantic consequence under {}",
        "Consistency check for {}", "Compactness property of {}", "Decidability of {}",
        "Validity of {} in L3 logic", "Kripke model world for {}", "Polarity shift in {}"
    ]
    
    added = 0
    while added < target_counts["definition"]:
        f_in = gen_formula(1)
        f_context = gen_formula(1)
        term = random.choice(def_terms).format(f_in, f_context)
        stmt = f"In propositional logic, {term} refers to the property where {gen_formula(1)} is evaluated within the context of {gen_formula(1)}."
        if stmt in seen_statements:
            continue
        seen_statements.add(stmt)
        results.append({
            "id": f"prop.definition.{indices['definition']:05d}",
            "domain": "propositional_logic",
            "kind": "definition",
            "title": f"Definition: {term}",
            "statement": stmt,
            "prerequisites": ["prop:syntax"],
            "yields": [f"tag:{indices['definition']}"],
            "refutation": None,
            "patterns": [f"Explain {term}", f"What is {term}?"] ,
            "links": []
        })
        indices["definition"] += 1
        added += 1

    # 2. Axioms
    added = 0
    while added < target_counts["axiom"]:
        a, b, c = gen_formula(0), gen_formula(0), gen_formula(0)
        types = [
            (f"({a} \\to ({b} \\to {a}))", "Hilbert K"),
            (f"((({a} \\to ({b} \\to {c})) \\to (({a} \\to {b}) \\to ({a} \\to {c}))))", "Hilbert S"),
            (f"(((\\neg {b} \\to \\neg {a}) \\to ((\\neg {b} \\to {a}) \\to {b})))", "Hilbert Neg"),
            (f"(({a} \\land {b}) \\to {a})", "Conjunction Ax"),
            (f"({a} \\to ({a} \\lor {b}))", "Disjunction Ax")
        ]
        stmt, tname = random.choice(types)
        if stmt in seen_statements:
            continue
        seen_statements.add(stmt)
        results.append({
            "id": f"prop.axiom.{indices['axiom']:05d}",
            "domain": "propositional_logic",
            "kind": "axiom",
            "title": f"Axiom {tname} Instance",
            "statement": stmt,
            "prerequisites": ["prop:axiom_schema"],
            "yields": ["tag:axiom"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["axiom"] += 1
        added += 1

    # 3. Theorems
    added = 0
    while added < target_counts["theorem"]:
        a, b, c = gen_formula(0), gen_formula(0), gen_formula(0)
        stmts = [
            f"\\neg ({a} \\land {b}) \\leftrightarrow (\\neg {a} \\lor \\neg {b})",
            f"\\neg ({a} \\lor {b}) \\leftrightarrow (\\neg {a} \\land \\neg {b})",
            f"({a} \\to {b}) \\leftrightarrow (\\neg {a} \\lor {b})",
            f"{a} \\leftrightarrow \\neg \\neg {a}",
            f"((({a} \\to {b}) \\land ({b} \\to {c})) \\to ({a} \\to {c}))"
        ]
        stmt = random.choice(stmts)
        if stmt in seen_statements:
            continue
        seen_statements.add(stmt)
        results.append({
            "id": f"prop.theorem.{indices['theorem']:05d}",
            "domain": "propositional_logic",
            "kind": "theorem",
            "title": f"Theorem: {stmt[:40]}",
            "statement": stmt,
            "prerequisites": ["prop:semantics"],
            "yields": ["tag:tautology"],
            "refutation": None,
            "patterns": [stmt],
            "links": []
        })
        indices["theorem"] += 1
        added += 1

    # 4. Rules
    added = 0
    while added < target_counts["rule"]:
        a, b = gen_formula(0), gen_formula(0)
        stmt = f"\\{{ {a}, {a} \\to {b} \\}} \\vdash {b}"
        if stmt in seen_statements:
            continue
        seen_statements.add(stmt)
        results.append({
            "id": f"prop.rule.{indices['rule']:05d}",
            "domain": "propositional_logic",
            "kind": "rule",
            "title": f"Inference Rule {indices['rule']}",
            "statement": stmt,
            "prerequisites": ["prop:proof_theory"],
            "yields": ["tag:mp"],
            "refutation": None,
            "patterns": [f"Derive {b} from {a}"],
            "links": []
        })
        indices["rule"] += 1
        added += 1

    # 5. Counterexamples
    added = 0
    while added < target_counts["counterexample_schema"]:
        a, b = gen_formula(0), gen_formula(0)
        stmt = f"((({a} \\to {b}) \\land {b}) \\to {a})"
        if stmt in seen_statements:
            continue
        seen_statements.add(stmt)
        results.append({
            "id": f"prop.counterexample_schema.{indices['counterexample_schema']:05d}",
            "domain": "propositional_logic",
            "kind": "counterexample_schema",
            "title": f"Fallacy instance {indices['counterexample_schema']}",
            "statement": stmt,
            "prerequisites": ["prop:fallacy"],
            "yields": ["tag:invalid"],
            "refutation": f"v({a})=F, v({b})=T",
            "patterns": [f"Why is {stmt} invalid?"],
            "links": []
        })
        indices["counterexample_schema"] += 1

    # Shuffling to avoid large Kind blocks
    random.shuffle(results)
    
    # Write to target
    with KB_PATH.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    
    print(f"Added {len(results)} items.")

if __name__ == "__main__":
    generate_batch()
