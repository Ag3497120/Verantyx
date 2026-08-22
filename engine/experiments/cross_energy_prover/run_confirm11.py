# -*- coding: utf-8 -*-
"""確認測定11 — PREREG11.md が事前登録。List断片 + 完了基準5点。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prover import (DEFS, Prover, load_list_context, load_mathlib_context,
                    parse_term)
from run_confirm import CONFIRM, REGRESS, LEAN, lean_lemma
from run_confirm3 import BATTERY
from run_confirm7 import POLY, LEAN_POLY
from verantyx.lean_witness import lean_binary, verify
from verantyx.proof_ledger import ProofLedger

LISTS = [
    ("L1", "rev(app(app(x, y), z))", "app(rev(z), app(rev(y), rev(x)))"),
    ("L2", "len(app(x, app(y, z)))", "add(len(x), add(len(y), len(z)))"),
    ("L3", "len(rev(app(x, y)))", "add(len(y), len(x))"),
    ("L4", "rev(rev(app(x, y)))", "app(x, y)"),
]
FALSE = [
    ("F1", "app(x, y)", "app(y, x)"),
    ("F2", "rev(x)", "x"),
    ("F3", "len(app(x, y))", "len(x)"),
    ("F4", "rev(app(x, y))", "app(rev(x), rev(y))"),
]
LEAN_L = {
    "L1": "theorem t (x y z : List Nat) : ((x ++ y) ++ z).reverse = z.reverse ++ (y.reverse ++ x.reverse) := by simp",
    "L2": "theorem t (x y z : List Nat) : (x ++ (y ++ z)).length = x.length + (y.length + z.length) := by simp [Nat.add_assoc]",
    "L3": "theorem t (x y : List Nat) : (x ++ y).reverse.length = y.length + x.length := by simp",
    "L4": "theorem t (x y : List Nat) : (x ++ y).reverse.reverse = x ++ y := by simp",
    "B1": "theorem t (x y : List Nat) : (x ++ y).length = (y ++ x).length := by simp <;> omega",
    "B10": "theorem t (x y z : List Nat) : ((x ++ y) ++ z).length = (x.length + y.length) + z.length := by simp [Nat.add_assoc]",
}
LEDGER = Path(__file__).with_name("proof_ledger11.json")
ALL = [("confirm", CONFIRM), ("regress", REGRESS), ("battery", BATTERY),
       ("poly", POLY), ("lists", LISTS), ("false", FALSE)]


def verdict_of(ok, how):
    if ok:
        return "proved"
    return "refuted" if how.startswith("REFUTED") else "refused"


def run_goals(goals, ledger, ml_ctx):
    out = []
    for name, l, r in goals:
        p = Prover(proof_ledger=ledger, mathlib_context=ml_ctx)
        t0 = time.time()
        ok, how = p.prove(parse_term(l), parse_term(r))
        v = verdict_of(ok, how)
        row = {"name": name, "goal": f"{l} = {r}", "verdict": v, "how": how,
               "lemmas": p.stats["lemmas"], "cited": p.stats["cited"],
               "nodes": p.stats["nodes"],
               "seconds": round(time.time() - t0, 1)}
        if ledger is not None:
            if v == "proved":
                ledger.close_goal(name, l, r, how=how)
                ledger.add_lemma(l, r, how=how, origin_goal=name,
                                 ground_passed=-1, cited=p.stats["cited"])
            elif v == "refuted":
                ledger.open_goal(name, l, r, failure_type="REFUTED",
                                 needs=["none:false_proposition"])
            else:
                ledger.open_goal(name, l, r, failure_type=how,
                                 needs=["signature_extension"])
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
    nat = load_mathlib_context()
    lst = load_list_context()
    ml = (nat[0] + lst[0], nat[1] + lst[1])

    res = {"handed_rules": len(ml[0])}
    for gname, goals in ALL:
        res[gname] = run_goals(goals, ledger, ml)

    # ⑤ 独立検証: proved は全て Lean
    unsound, ver = [], 0
    for gname, _ in ALL:
        for g in res[gname]:
            if g["verdict"] != "proved":
                continue
            fix = LEAN.get(g["name"]) or LEAN_POLY.get(g["name"]) \
                or LEAN_L.get(g["name"])
            if fix:
                v = str(verify(fix).get("verdict"))
            else:
                l, r = g["goal"].split(" = ", 1)
                v = lean_lemma(parse_term(l), parse_term(r))["verdict"]
            if v == "VERIFIED":
                ver += 1
            else:
                unsound.append({"goal": g["name"], "lean": v})
    res["lean_verified_targets"] = ver
    res["unsound"] = len(unsound)
    res["unsound_detail"] = unsound

    # ④ 順序の不変: ml と DEFS を反転した第二走(台帳なし)で verdict 一致
    ml_rev = (list(reversed(ml[0])), ml[1])
    mismatches = []
    for gname, goals in ALL:
        second = run_goals(goals, None, ml_rev)
        for g1, g2 in zip(res[gname], second):
            if g1["verdict"] != g2["verdict"]:
                mismatches.append({"goal": g1["name"],
                                   "first": g1["verdict"],
                                   "second": g2["verdict"]})
    # DEFS 反転も(第三走)
    third_mismatch = []
    for gname, goals in ALL:
        out3 = []
        for name, l, r in goals:
            p = Prover(rules=list(reversed(DEFS)), mathlib_context=ml)
            ok, how = p.prove(parse_term(l), parse_term(r))
            out3.append(verdict_of(ok, how))
        for g1, v3 in zip(res[gname], out3):
            if g1["verdict"] != v3:
                third_mismatch.append({"goal": g1["name"],
                                       "first": g1["verdict"], "defs_rev": v3})
    res["order_invariance"] = {"ml_reversed_mismatch": mismatches,
                               "defs_reversed_mismatch": third_mismatch}
    ledger.save()
    res["ledger_summary"] = ledger.summary()
    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results_confirm11.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
