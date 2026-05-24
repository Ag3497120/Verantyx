#!/usr/bin/env python3
# tools/phase28_3_run_verifier.py

import argparse, json, time, os
from typing import Any, Dict, Optional

def has_pattern(entry: Dict[str, Any], pat: str) -> bool:
    pats = entry.get("patterns", [])
    return isinstance(pats, list) and pat in pats

def get_candidate(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c = entry.get("refutation_candidate")
    return c if isinstance(c, dict) else None

# -------------------------
# Verifier stub (replaceable)
# -------------------------
def verify_candidate(entry: Dict[str, Any], cand: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns:
      status: "verified" | "refuted" | "unknown"
      reason: short string
      evidence: optional dict
    """
    # Check Phase 28 format
    # Note: Phase 28 uses "domain", "dropped_assumption", "failure_point", "structure" (lowercase)
    required = {"domain", "dropped_assumption", "failure_point", "structure"}
    if not required.issubset(set(cand.keys())):
        return {"status": "unknown", "reason": "candidate_missing_required_fields", "evidence": {"missing": sorted(list(required - set(cand.keys())))}}

    if not isinstance(cand.get("structure"), dict):
        return {"status": "unknown", "reason": "candidate_structure_not_object", "evidence": None}

    # Heuristic: domain check
    ed = entry.get("domain")
    cd = cand.get("domain")
    if ed and cd and ed != cd:
        return {"status": "unknown", "reason": "domain_mismatch", "evidence": {"entry_domain": ed, "cand_domain": cd}}

    # For Phase 28.3 demo: If candidate is from phase28_template, we simulate verification success.
    if cand.get("source") == "phase28_template" or cand.get("source") == "phase28.2_template":
        return {"status": "verified", "reason": "template_driven_verified_stub", "evidence": {"template_sig": cand.get("template_sig")}} 

    return {"status": "unknown", "reason": "no_template_match_and_no_real_checker", "evidence": None}

# -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=12000)
    ap.add_argument("--only_pattern", default="targeted_by:phase28.2")
    args = ap.parse_args()

    processed = 0
    verified = 0
    refuted = 0
    unknown = 0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    with open(args.kb, "r", encoding="utf-8") as f, open(args.out, "w", encoding="utf-8") as w:
        for line in f:
            if processed >= args.limit:
                break
            if not line.strip():
                continue
            e = json.loads(line)

            if e.get("kind") != "counterexample_schema":
                continue
            if not has_pattern(e, args.only_pattern):
                continue

            cand = get_candidate(e)
            if not cand:
                result = {
                    "id": e.get("id"),
                    "status": "unknown",
                    "reason": "no_refutation_candidate",
                    "ts": time.time(),
                }
                w.write(json.dumps(result, ensure_ascii=False) + "\n")
                processed += 1
                unknown += 1
                continue

            vr = verify_candidate(e, cand)
            status = vr["status"]
            if status == "verified":
                verified += 1
            elif status == "refuted":
                refuted += 1
            else:
                unknown += 1

            result = {
                "id": e.get("id"),
                "status": status,
                "reason": vr.get("reason"),
                "evidence": vr.get("evidence"),
                "ts": time.time(),
            }
            w.write(json.dumps(result, ensure_ascii=False) + "\n")
            processed += 1

    print(f"[OK] wrote={args.out}")
    print(f"[STATS] processed={processed} verified={verified} refuted={refuted} unknown={unknown}")

if __name__ == "__main__":
    main()
