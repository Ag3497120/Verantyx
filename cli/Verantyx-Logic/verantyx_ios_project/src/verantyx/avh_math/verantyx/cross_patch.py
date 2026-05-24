from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def make_kb_patch(entry_id: str, add_patterns: List[str], patch_note: str) -> Dict[str, Any]:
    return {
        "id": entry_id,
        "add_patterns": add_patterns,
        "patch_note": patch_note,
    }


def write_patches_jsonl(out_path: str, patches: List[Dict[str, Any]]) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for rec in patches:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def apply_task_results_to_cross(cross: Dict[str, Any], results: List[Dict[str, Any]]) -> Dict[str, Any]:
    cross = dict(cross)
    meta = dict(cross.get("meta") or {})
    meta["puzzle_assembler"] = {
        "tasks": len(results),
        "best_status": results[0]["status"] if results else "unknown",
    }
    cross["meta"] = meta

    solver_nodes = list(cross.get("solver_nodes") or [])
    cross_id = cross.get("cross_id") or "cross"
    for r in results[:12]:
        solver_nodes.append(
            {
                "axis": "solver",
                "node_id": f"{cross_id}__solve_{r.get('task_id')}",
                "links": [],
                "content": {
                    "task_id": r.get("task_id"),
                    "formula": r.get("formula"),
                    "status": r.get("status"),
                    "answer_text": r.get("answer_text"),
                    "payload": r.get("payload", {}),
                },
            }
        )
    cross["solver_nodes"] = solver_nodes

    pn = list(cross.get("patch_note") or [])
    pn.append(f"PuzzleAssembler: attached {min(len(results), 12)} results")
    cross["patch_note"] = pn
    return cross
