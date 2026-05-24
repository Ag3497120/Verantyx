import json
from pathlib import Path

kb_path = Path("avh_math/db/foundation_kb.jsonl")

new_entries = [
    {
        "id": "modal_axiom_k",
        "kind": "axiom",
        "statement": "[](p -> q) -> ([]p -> []q)",
        "domain": "modal_logic",
        "logic_system": ["K"],
        "applicable_query_types": ["SINGLE", "SET_ALL"],
        "solve_level": "DB_DIRECT",
        "tags": ["modal", "distribution"],
        "patterns": ["distribution axiom", "K axiom"]
    },
    {
        "id": "modal_axiom_t",
        "kind": "axiom",
        "statement": "[]p -> p",
        "domain": "modal_logic",
        "prerequisites": ["assume:reflexive"],
        "logic_system": ["T", "S4", "S5"],
        "applicable_query_types": ["SINGLE", "SET_ALL"],
        "solve_level": "DB_DIRECT",
        "tags": ["modal", "reflexivity"],
        "patterns": ["reflexivity axiom", "T axiom"]
    },
    {
        "id": "modal_axiom_4",
        "kind": "axiom",
        "statement": "[]p -> [][]p",
        "domain": "modal_logic",
        "prerequisites": ["assume:transitive"],
        "logic_system": ["K4", "S4", "S5"],
        "applicable_query_types": ["SINGLE", "SET_ALL"],
        "solve_level": "DB_DIRECT",
        "tags": ["modal", "transitivity"],
        "patterns": ["transitivity axiom", "4 axiom"]
    },
    {
        "id": "modal_axiom_b",
        "kind": "axiom",
        "statement": "p -> []<>p",
        "domain": "modal_logic",
        "prerequisites": ["assume:symmetric"],
        "logic_system": ["B", "S5"],
        "applicable_query_types": ["SINGLE", "SET_ALL"],
        "solve_level": "DB_DIRECT",
        "tags": ["modal", "symmetry"],
        "patterns": ["symmetry axiom", "B axiom"]
    },
    {
        "id": "modal_axiom_5",
        "kind": "axiom",
        "statement": "<>p -> []<>p",
        "domain": "modal_logic",
        "prerequisites": ["assume:euclidean"],
        "logic_system": ["S5"],
        "applicable_query_types": ["SINGLE", "SET_ALL"],
        "solve_level": "DB_DIRECT",
        "tags": ["modal", "euclidean"],
        "patterns": ["euclidean axiom", "5 axiom"]
    },
    {
        "id": "modal_invalid_p_boxp",
        "kind": "counterexample_schema",
        "statement": "p -> []p",
        "domain": "modal_logic",
        "invalid_if": ["assume:general"], # 一般的なフレームでは無効
        "applicable_query_types": ["SINGLE", "SET_ALL"],
        "solve_level": "AXIOM_DERIVED",
        "tags": ["modal", "invalid"],
        "patterns": ["p implies box p", "truth implies necessity"],
        "refutation": "World w: p=True, w->v, v: p=False. Then w |= p but w |/= []p."
    }
]

with kb_path.open("a", encoding="utf-8") as f:
    for entry in new_entries:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

print(f"Appended {len(new_entries)} entries to {kb_path}")
