# -*- coding: utf-8 -*-
"""確認測定12 — PREREG12.md が事前登録。条件付き書き換えと不等式、5点基準。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prover import (DEFS, Prover, load_list_context, load_mathlib_context,
                    parse_term, term_to_str)
from run_confirm import CONFIRM, REGRESS, LEAN
from run_confirm3 import BATTERY
from run_confirm7 import POLY, LEAN_POLY
from run_confirm11 import FALSE, LEAN_L, LISTS, run_goals, verdict_of
from verantyx.lean_witness import lean_binary, verify
from verantyx.proof_ledger import ProofLedger

Q = [
    ("Q1", "le(0, a)", "true"),
    ("Q2", "le(a, a)", "true"),
    ("Q3", "le(a, add(a, b))", "true"),
    ("Q4", "le(a, s(a))", "true"),
    ("Q5", "monus(a, a)", "0"),
    ("Q6", "monus(a, add(a, b))", "0"),
    ("Q7", "monus(add(a, b), b)", "a"),
]
QF = [
    ("QF1", "le(s(a), a)", "true"),
    ("QF2", "monus(a, b)", "0"),
    ("QF3", "le(add(a, b), a)", "true"),
]
LEAN_Q = {
    "Q1": "theorem t (a : Nat) : Nat.ble 0 a = true := by simp [Nat.ble_eq]",
    "Q2": "theorem t (a : Nat) : Nat.ble a a = true := by simp [Nat.ble_eq]",
    "Q3": "theorem t (a b : Nat) : Nat.ble a (a+b) = true := by simp [Nat.ble_eq] <;> omega",
    "Q4": "theorem t (a : Nat) : Nat.ble a (a+1) = true := by simp [Nat.ble_eq] <;> omega",
    "Q5": "theorem t (a : Nat) : a - a = 0 := by omega",
    "Q6": "theorem t (a b : Nat) : a - (a+b) = 0 := by omega",
    "Q7": "theorem t (a b : Nat) : (a+b) - b = a := by omega",
}
LEDGER = Path(__file__).with_name("proof_ledger12.json")
GROUPS = [("confirm", CONFIRM), ("regress", REGRESS), ("battery", BATTERY),
          ("poly", POLY), ("lists", LISTS), ("false", FALSE),
          ("ineq", Q), ("ineq_false", QF)]


def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"}))
        return
    t0 = time.time()
    for p in (LEDGER, LEDGER.with_name(LEDGER.stem + ".gaps.json")):
        if p.exists():
            p.unlink()
    ledger = ProofLedger(LEDGER)
    nat = load_mathlib_context()
    lst = load_list_context()
    ml = (nat[0] + lst[0], nat[1] + lst[1])

    res = {}
    cond_fired_total, cond_refused_total = [], 0
    for gname, goals in GROUPS:
        rows = []
        for name, l, r in goals:
            p = Prover(proof_ledger=ledger, mathlib_context=ml)
            t1 = time.time()
            ok, how = p.prove(parse_term(l), parse_term(r))
            v = verdict_of(ok, how)
            rows.append({"name": name, "goal": f"{l} = {r}", "verdict": v,
                         "how": how[:120], "cited": p.stats["cited"],
                         "cond_fired": p.stats["cond_fired"],
                         "nodes": p.stats["nodes"],
                         "seconds": round(time.time() - t1, 1)})
            cond_fired_total += p.stats["cond_fired"]
            cond_refused_total += p.stats["cond_refused"]
            if v == "proved":
                ledger.close_goal(name, l, r, how=how)
                ledger.add_lemma(l, r, how=how, origin_goal=name,
                                 ground_passed=-1, cited=p.stats["cited"])
            elif v == "refuted":
                ledger.open_goal(name, l, r, failure_type="REFUTED",
                                 needs=["none:false_proposition"])
            else:
                ledger.open_goal(name, l, r, failure_type=how[:60],
                                 needs=["conditional_or_lemma"])
        res[gname] = rows

    # ③(i) 安全プローブ: 放電不能な条件で発火してはならない
    p = Prover(mathlib_context=ml)
    probe = parse_term("monus(add(a, s(0)), a)")
    fired: list = []
    out = p._cond_try(probe, 0, set(), fired)
    res["safety_probe"] = {
        "term": "monus(add(a, s(0)), a)",
        "fired": out is not None,
        "cond_refused": p.stats["cond_refused"],
        "note": "発火したら即失格(条件 le(a+1,a)=true は偽)"}

    # ⑤ 独立検証
    unsound, ver = [], 0
    for gname, _ in GROUPS:
        for g in res[gname]:
            if g["verdict"] != "proved":
                continue
            fix = (LEAN.get(g["name"]) or LEAN_POLY.get(g["name"])
                   or LEAN_L.get(g["name"]) or LEAN_Q.get(g["name"]))
            v = str(verify(fix).get("verdict")) if fix else "NO_FIXTURE"
            if v == "VERIFIED":
                ver += 1
            else:
                unsound.append({"goal": g["name"], "lean": v})
    res["lean_verified_targets"] = ver
    res["unsound"] = len(unsound)
    res["unsound_detail"] = unsound

    # ④ 順序の不変(DEFS+ml 反転)
    mismatches = []
    ml_rev = (list(reversed(ml[0])), ml[1])
    for gname, goals in GROUPS:
        for (name, l, r), g1 in zip(goals, res[gname]):
            p = Prover(rules=list(reversed(DEFS)), mathlib_context=ml_rev)
            ok, how = p.prove(parse_term(l), parse_term(r))
            if verdict_of(ok, how) != g1["verdict"]:
                mismatches.append({"goal": name, "first": g1["verdict"],
                                   "reversed": verdict_of(ok, how)})
    res["order_invariance_mismatch"] = mismatches
    res["cond"] = {"fired": cond_fired_total,
                   "refused": cond_refused_total}
    ledger.save()
    res["ledger_summary"] = ledger.summary()
    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results_confirm12.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
