from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def build_cross(entry: Dict[str, Any], idx: int) -> Dict[str, Any]:
    raw_text = entry.get("raw_text", "")
    tokens = entry.get("tokens") or []
    shapes = entry.get("shapes") or []
    signature = entry.get("structure_signature") or []
    notes = entry.get("notes") or []

    cross_id = f"text_cross_{idx:07d}"
    core_id = f"{cross_id}::core"

    core_node = {
        "id": core_id,
        "axis": "core",
        "title": "raw_text",
        "content": {"raw_text": raw_text},
        "links": [],
    }

    syntax_nodes = []
    edges = []

    for i, tok in enumerate(tokens):
        tok_id = f"{cross_id}::tok::{i}"
        syntax_nodes.append(
            {
                "id": tok_id,
                "axis": "syntax",
                "title": "token",
                "content": {"token": tok, "position": i},
                "links": [],
            }
        )
        edges.append(
            {"source": core_id, "target": tok_id, "rel": "mentions", "weight": 1.0}
        )

    evidence_nodes = [
        {
            "id": f"{cross_id}::shapes",
            "axis": "evidence",
            "title": "shapes",
            "content": {"shapes": shapes},
            "links": [],
        },
        {
            "id": f"{cross_id}::signature",
            "axis": "evidence",
            "title": "structure_signature",
            "content": {"structure_signature": signature},
            "links": [],
        },
    ]

    if notes:
        evidence_nodes.append(
            {
                "id": f"{cross_id}::notes",
                "axis": "evidence",
                "title": "notes",
                "content": {"notes": notes},
                "links": [],
            }
        )

    for node in evidence_nodes:
        edges.append(
            {"source": node["id"], "target": core_id, "rel": "supports", "weight": 0.7}
        )

    return {
        "cross_id": cross_id,
        "domain": "text_cross",
        "task": "decomposition",
        "core_formula": raw_text,
        "core_node": core_node,
        "syntax_nodes": syntax_nodes,
        "semantic_nodes": [],
        "assumption_nodes": [],
        "counterexample_nodes": [],
        "evidence_nodes": evidence_nodes,
        "edges": edges,
        "meta": {
            "tokens": tokens,
            "structure_signature": signature,
            "notes": notes,
            "source": "text_cross_kb.jsonl",
        },
    }


def main() -> None:
    in_path = Path("avh_math/db/text_cross_kb.jsonl")
    out_path = Path("avh_math/db/text_cross_kb_cross.jsonl")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for idx, entry in enumerate(iter_jsonl(in_path), start=1):
            cross = build_cross(entry, idx)
            handle.write(json.dumps(cross, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
