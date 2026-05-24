#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase 26: Apply Phase25 minimality results as non-destructive patches.
Modified to handle the output format of phase25_runner.py.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple


def iter_jsonl(path: str) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line)
            except Exception as e:
                raise RuntimeError(f"[JSONL parse error] {path} line={i} err={e}")


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for obj in rows:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def build_patch(
    entry_id: str,
    add_patterns: List[str],
    patch_note: Optional[str] = None,
) -> Dict[str, Any]:
    ops: List[Dict[str, Any]] = []
    if add_patterns:
        ops.append({
            "op": "add_unique",
            "path": "/patterns",
            "values": add_patterns
        })
    if patch_note:
        ops.append({
            "op": "set",
            "path": "/patch_note",
            "value": patch_note
        })

    return {
        "target_id": entry_id,
        "phase": 26,
        "ops": ops
    }

def verdict_to_patterns(verdict: str, include_unknown: bool) -> List[str]:
    verdict = str(verdict).lower().strip()
    if verdict in ("verified", "true", "min_true", "minimal_true"):
        return ["min_verified:true"]
    if verdict in ("refuted", "false", "min_false", "minimal_false"):
        return ["min_verified:false", "needs_review:true"]
    if verdict in ("unknown", "undecided") and include_unknown:
        return ["min_verified:unknown"]
    return []

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase25", required=True, help="phase25_results.jsonl")
    ap.add_argument("--out", required=True, help="phase26_patches.jsonl")
    ap.add_argument("--include_unknown", action="store_true", help="also tag unknown with min_verified:unknown")
    ap.add_argument("--max_patches", type=int, default=0, help="0=all, else limit for testing")
    args = ap.parse_args()

    out_path = args.out
    
    # Clear output file if it exists to avoid appending to old runs in this session
    if os.path.exists(out_path):
        os.remove(out_path)

    patches_written = 0

    for i, rec in iter_jsonl(args.phase25):
        # Determine entry_id
        entry_id = rec.get("id") or rec.get("target_id") or rec.get("canonical_id")
        if not entry_id or not isinstance(entry_id, str):
            continue

        # Determine status and details based on structure
        result_obj = rec.get("result")
        if isinstance(result_obj, dict):
            # phase25_runner.py format
            status = result_obj.get("verdict")
            details = result_obj.get("details", {})
            reason = details.get("note")
            witness = details.get("witness")
            checked = details.get("checked_smaller")
        else:
            # flat format fallback
            status = rec.get("status") or rec.get("verdict") or rec.get("minimality")
            reason = rec.get("reason")
            witness = rec.get("witness")
            checked = rec.get("checked_smaller")

        if not status:
            continue

        add_patterns = verdict_to_patterns(status, include_unknown=bool(args.include_unknown))
        if not add_patterns:
            continue

        note_parts: List[str] = []
        if isinstance(reason, str) and reason.strip():
            note_parts.append(f"Phase26 minimality note: {reason.strip()}")
        if checked is not None:
            note_parts.append(f"checked_smaller={checked}")
        if witness is not None:
            try:
                note_parts.append("witness=" + json.dumps(witness, ensure_ascii=False))
            except Exception:
                note_parts.append("witness=<unserializable>")

        patch_note = "\n".join(note_parts) if note_parts else None

        patch = build_patch(entry_id=entry_id, add_patterns=add_patterns, patch_note=patch_note)
        write_jsonl(out_path, [patch])
        patches_written += 1

        if args.max_patches and patches_written >= args.max_patches:
            break

    print(f"[OK] wrote patches: {patches_written} -> {out_path}")


if __name__ == "__main__":
    main()
