# -*- coding: utf-8 -*-
"""確認測定7 — PREREG8.md が事前登録。mathlib断片の手渡し(票なし・昇格なし)。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prover import Prover, load_mathlib_context, parse_term
from run_confirm import CONFIRM, REGRESS, LEAN, lean_lemma
from run_confirm3 import BATTERY
from verantyx.lean_witness import lean_binary, verify
from verantyx.proof_ledger import ProofLedger

POLY = [
    ("P1", "add(mul(a, b), mul(a, c))", "mul(a, add(b, c))"),
    ("P2", "mul(add(a, b), c)", "add(mul(a, c), mul(b, c))"),
    ("P3", "mul(add(a, b), add(a, b))",
     "add(mul(a, a), add(mul(a, b), add(mul(b, a), mul(b, b))))"),
    ("P4", "mul(a, add(b, add(c, d)))",
     "add(mul(a, b), add(mul(a, c), mul(a, d)))"),
    ("P5", "mul(mul(a, add(b, c)), d)",
     "add(mul(mul(a, b), d), mul(mul(a, c), d))"),
    ("P6", "add(mul(add(a, b), c), mul(add(a, b), d))",
     "mul(add(a, b), add(c, d))"),
]
# 事前検証済み治具(6/6 VERIFIED を測定前に確認済み)
LEAN_POLY = {
    "P1": "theorem t (a b c : Nat) : a * b + a * c = a * (b + c) := by simp [Nat.mul_add]",
    "P2": "theorem t (a b c : Nat) : (a + b) * c = a * c + b * c := by simp [Nat.add_mul]",
    "P3": "theorem t (a b : Nat) : (a + b) * (a + b) = a * a + (a * b + (b * a + b * b)) := by simp [Nat.add_mul, Nat.mul_add] <;> ac_rfl",
    "P4": "theorem t (a b c d : Nat) : a * (b + (c + d)) = a * b + (a * c + a * d) := by simp [Nat.mul_add]",
    "P5": "theorem t (a b c d : Nat) : (a * (b + c)) * d = (a * b) * d + (a * c) * d := by simp [Nat.mul_add, Nat.add_mul]",
    "P6": "theorem t (a b c d : Nat) : (a + b) * c + (a + b) * d = (a + b) * (c + d) := by simp [Nat.mul_add]",
}

# P4 は変数 d を使う — VAR_TYPES に d が無いので n を使う形に直す
POLY = [(n, l.replace(", d)", ", n)").replace("(d,", "(n,").replace(" d)", " n)"),
         r.replace(", d)", ", n)").replace("(d,", "(n,").replace(" d)", " n)"))
        for n, l, r in POLY]

LEDGER = Path(__file__).with_name("proof_ledger8.json")


def run_goals(goals, ledger, ml_ctx, lean_fixtures):
    out = []
    for name, l, r in goals:
        p = Prover(proof_ledger=ledger, mathlib_context=ml_ctx)
        t0 = time.time()
        ok, how = p.prove(parse_term(l), parse_term(r))
        row = {"name": name, "goal": f"{l} = {r}", "proved": ok, "how": how,
               "lemmas": p.stats["lemmas"], "cited": p.stats["cited"],
               "nodes": p.stats["nodes"],
               "seconds": round(time.time() - t0, 1)}
        if ok:
            ledger.close_goal(name, l, r, how=how)
            ledger.add_lemma(l, r, how=how, origin_goal=name,
                             ground_passed=-1, cited=p.stats["cited"])
        else:
            ledger.open_goal(name, l, r, failure_type=how,
                             needs=["signature_extension", "lpo_kbo"])
        out.append(row)
    return out


def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"}))
        return
    t0 = time.time()
    for p in (LEDGER, LEDGER.with_name(LEDGER.stem + ".gaps.json")):
        if p.exists():
            p.unlink()
    ledger = ProofLedger(LEDGER)
    ml_ctx = load_mathlib_context()

    res = {"ml_rules": len(ml_ctx[0]),
           "confirm": run_goals(CONFIRM, ledger, ml_ctx, LEAN),
           "regress": run_goals(REGRESS, ledger, ml_ctx, LEAN),
           "battery": run_goals(BATTERY, ledger, ml_ctx, LEAN),
           "poly": run_goals(POLY, ledger, ml_ctx, LEAN_POLY)}

    unsound, ver = [], 0
    for grp in ("confirm", "regress", "battery", "poly"):
        for g in res[grp]:
            if not g["proved"]:
                continue
            name = g["name"]
            fix = LEAN.get(name) or LEAN_POLY.get(name)
            if fix:
                verdict = str(verify(fix).get("verdict"))
            else:
                l, r = g["goal"].split(" = ", 1)
                verdict = lean_lemma(parse_term(l), parse_term(r))["verdict"]
            if verdict == "VERIFIED":
                ver += 1
            else:
                unsound.append({"goal": name, "lean": verdict})
    res["lean_verified_targets"] = ver
    res["unsound"] = len(unsound)
    res["unsound_detail"] = unsound
    for row in ledger.lemmas:
        if row.get("lean_verdict"):
            continue
        lv = lean_lemma(parse_term(row["lhs"]), parse_term(row["rhs"]))
        row["lean_verdict"] = lv["verdict"]
        row["lean_tactic"] = lv.get("tactic")
    ledger.save()
    res["ledger_summary"] = ledger.summary()
    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results_confirm8.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
