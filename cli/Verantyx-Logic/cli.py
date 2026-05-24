from __future__ import annotations
import argparse
import json
from engine import AVHEngine
from verifier import VerifyConfig

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="default", choices=["default", "strict"])
    ap.add_argument("--max_worlds", type=int, default=3)
    ap.add_argument("--max_edges", type=int, default=4)
    ap.add_argument("--text", type=str, default="")
    args = ap.parse_args()

    text = args.text.strip()
    if not text:
        text = """クリプキ・フレーム ⟨W, R⟩ において、到達関係 R は 推移的（transitive）である。
このとき常に妥当な式はどれか。
A. □A → A
B. ◊A → □◊A
C. □A → □□A
D. A → □◊A
"""

    eng = AVHEngine(profile=args.profile)
    # Phase3 uses internal tactics.json for configuration
    # cfg = VerifyConfig(max_worlds=args.max_worlds, max_edges=args.max_edges)

    res = eng.solve(text)

    print("=== TRACE ===")
    for line in res.trace:
        print(line)

    print("\n=== RANKED ===")
    for i, c in enumerate(res.ranked, 1):
        print(f"#{i} {c.formula} | status={c.status} | energy={c.energy} | breakdown={c.energy_breakdown}")
        if c.counterexample:
            print(f"   counterexample={c.counterexample}")
        if c.cex_explain and c.cex_explain.get("status") == "template_hit":
            print(f"   [CEX EXPLAIN] {c.cex_explain.get('template_id')} (Missing: {c.cex_explain.get('missing_assumption')})")
            for step in c.cex_explain.get('steps', []):
                print(f"     - {step}")
        if c.proof_sketch and c.proof_sketch.get("status") == "sketch_available":
            print(f"   [PROOF SKETCH] {c.proof_sketch.get('claim')}")
        if c.explanation:
            print(f"   [EXPLANATION] {c.explanation.get('summary')}")
            if c.explanation.get('notes'):
                print(f"     Note: {c.explanation.get('notes')[0]}")
        if c.repair_suggestions:
            for rs in c.repair_suggestions:
                print(f"   [REPAIR SUGGESTION] Add: {rs.get('add')} | Why: {rs.get('because')}")
        if c.counterexample_delta:
            for d in c.counterexample_delta:
                print(f"   [CEX DELTA] If add {d.get('add_assumption')}: {d.get('required_change')} edge={d.get('edge')}")
                print(f"     Why: {d.get('why_breaks')}")
        if c.counterexample_patch_proof:
            for p in c.counterexample_patch_proof:
                print(f"   [PATCH PROOF] Add {p.get('add_assumption')} => Still CEX? {p.get('still_counterexample_after_patch')}")
                print(f"     Note: {p.get('proof_note')}")
        if c.minimal_patches:
            for mp in c.minimal_patches:
                print(f"   [MINIMAL PATCH] Goal: {mp.get('goal')} | Size: {mp.get('patch_size')} | Still CEX? {mp.get('still_counterexample')}")
                print(f"     Patch: +{mp.get('patch',{}).get('add_edges')} -{mp.get('patch',{}).get('remove_edges')}")
        if c.minimal_assumption_sets:
            for mas in c.minimal_assumption_sets:
                print(f"   [MINIMAL ASSUMPTION SET] Add: {mas.get('add')} | Valid? {mas.get('valid')}")
    print("\n=== BEST VALID ===")
    print(res.best_valid)

if __name__ == "__main__":
    main()