#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase 25-A: Build Verification Jobs from boundary_cards.json

Inputs:
- boundary_cards.json (Phase24 output)
- foundation_kb.jsonl (to get canonical entry details)

Outputs:
- phase25_jobs.jsonl (append-safe; overwrite by default)
"""

from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Dict, Any, Optional, List

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                yield json.loads(s)

def write_jsonl(path: Path, rows: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def find_entry_by_id(kb_path: Path, target_id: str) -> Optional[Dict[str, Any]]:
    # simple scan; Phase17 offsets can replace this later
    for e in iter_jsonl(kb_path):
        if e.get("id") == target_id:
            return e
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True)
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-cards", type=int, default=5000)
    ap.add_argument("--worlds-floor", type=int, default=1)
    ap.add_argument("--worlds-ceil", type=int, default=4)
    ap.add_argument("--jobs-per-card", type=int, default=6)
    args = ap.parse_args()

    cards_path = Path(args.cards)
    kb_path = Path(args.kb)
    out_path = Path(args.out)

    cards = read_json(cards_path)
    jobs: List[Dict[str, Any]] = []
    n = 0

    for card in cards:
        if n >= args.max_cards:
            break
        canonical_id = card.get("canonical_id")
        if not canonical_id:
            continue

        entry = find_entry_by_id(kb_path, canonical_id)
        if not entry:
            continue

        domain = entry.get("domain", "unknown")
        sig = card.get("signature", "")
        dropped = card.get("dropped_assumption", "")
        failure = card.get("failure_point", "")

        # Job 1: minimality verify (try smaller worlds)
        jobs.append({
            "job_id": f"mincheck::{canonical_id}",
            "kind": "verify_minimality",
            "domain": domain,
            "signature": sig,
            "canonical_id": canonical_id,
            "params": {
                "try_worlds": list(range(args.worlds_floor, args.worlds_ceil + 1)),
                "target_failure_point": failure,
                "dropped_assumption": dropped,
            }
        })

        # Job 2: adjacency toggle (dropped assumption neighborhood)
        jobs.append({
            "job_id": f"toggle::{canonical_id}",
            "kind": "assumption_toggle_probe",
            "domain": domain,
            "signature": sig,
            "canonical_id": canonical_id,
            "params": {
                "base_dropped_assumption": dropped,
                "toggle_radius": 2,
                "target_failure_point": failure,
            }
        })

        # Job 3: isomorphic variants probe (fingerprint neighbors)
        jobs.append({
            "job_id": f"isomorph::{canonical_id}",
            "kind": "isomorphic_variant_probe",
            "domain": domain,
            "signature": sig,
            "canonical_id": canonical_id,
            "params": {
                "fingerprints_top": card.get("fingerprints_top", []),
                "max_variants": 8,
            }
        })

        # Optional: up to jobs_per_card by adding repeats with different ceilings
        # (kept simple; runner can interpret multiple try_worlds bands)
        n += 1

    write_jsonl(out_path, jobs)
    print(json.dumps({
        "ok": True,
        "cards_used": n,
        "jobs_written": len(jobs),
        "out": str(out_path)
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()