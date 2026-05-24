#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phase 25-B: Execute Verification Jobs

Inputs:
- phase25_jobs.jsonl
- foundation_kb.jsonl (optional for canonical refutation lookup)

Outputs:
- phase25_results.jsonl (append)
"""

from __future__ import annotations
import argparse, json, time
from pathlib import Path
from typing import Dict, Any, Optional

def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                yield json.loads(s)

def append_jsonl(path: Path, obj: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def load_seen_job_ids(results_path: Path) -> set[str]:
    if not results_path.exists():
        return set()
    seen = set()
    for r in iter_jsonl(results_path):
        jid = r.get("job_id")
        if jid:
            seen.add(jid)
    return seen

def find_entry_by_id(kb_path: Path, target_id: str) -> Optional[Dict[str, Any]]:
    for e in iter_jsonl(kb_path):
        if e.get("id") == target_id:
            return e
    return None

# ----------------- PLUGGABLE CHECKER -----------------

def verify_with_checker(job: Dict[str, Any], canonical_entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Replace this with your real checker integration.

    Expected return keys:
    - status: "ok" | "fail"
    - verdict: "verified" | "refuted" | "unknown"
    - details: dict
    """

    kind = job["kind"]
    params = job.get("params", {})

    # --- STUB behavior (deterministic-ish) ---
    # This just returns "unknown" to avoid lying about verification.
    # You MUST plug in actual model_search / checker here.
    return {
        "status": "ok",
        "verdict": "unknown",
        "details": {
            "note": "stub_checker: replace verify_with_checker() with Phase14 model checker integration",
            "job_kind": kind,
            "params": params,
            "canonical_has_refutation": bool(canonical_entry and canonical_entry.get("refutation")),
        }
    }

# -----------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sleep", type=float, default=0.0)
    args = ap.parse_args()

    jobs_path = Path(args.jobs)
    kb_path = Path(args.kb)
    out_path = Path(args.out)

    seen = load_seen_job_ids(out_path)
    ran = 0
    skipped = 0

    for job in iter_jsonl(jobs_path):
        jid = job.get("job_id")
        if not jid:
            continue
        if jid in seen:
            skipped += 1
            continue

        canonical_id = job.get("canonical_id")
        canonical_entry = find_entry_by_id(kb_path, canonical_id) if canonical_id else None

        t0 = time.time()
        result = verify_with_checker(job, canonical_entry)
        dt = time.time() - t0

        row = {
            "job_id": jid,
            "kind": job.get("kind"),
            "canonical_id": canonical_id,
            "domain": job.get("domain"),
            "signature": job.get("signature"),
            "runtime_sec": round(dt, 6),
            "result": result,
        }
        append_jsonl(out_path, row)
        ran += 1

        if args.sleep > 0:
            time.sleep(args.sleep)

    print(json.dumps({
        "ok": True,
        "ran": ran,
        "skipped_already_done": skipped,
        "results_out": str(out_path)
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()