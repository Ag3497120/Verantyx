# -*- coding: utf-8 -*-
"""確認測定 — PREREG.md が事前登録。自分のハーネスを自分で測る。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cross_energy_prover"))
import verantyx.prover as P
from verantyx.prover import (Prover, load_list_context, load_mathlib_context,
                             parse_term)
from verantyx.self_harness import (DEFAULT_KNOBS, apply_knobs, classify,
                                   lift_all, variations)
from run_confirm import CONFIRM, REGRESS, LEAN, lean_lemma
from run_confirm3 import BATTERY
from run_confirm7 import POLY, LEAN_POLY
from run_confirm11 import FALSE, LEAN_L, LISTS
from run_confirm12 import Q, QF, LEAN_Q
from verantyx.lean_witness import lean_binary, verify

GOALS = CONFIRM + REGRESS + BATTERY + POLY + LISTS + Q          # 真の目標
FALSE_GOALS = FALSE + QF                                        # 偽の目標
BATTERY_ID = "prover_goals48@2026-08-21"


def run_battery(ctx, knobs, order="forward"):
    """1つの設定で目標集合を回し、(証明数, 反駁数, how一覧) を返す。"""
    goals = GOALS if order == "forward" else list(reversed(GOALS))
    falses = FALSE_GOALS if order == "forward" else list(reversed(FALSE_GOALS))
    proved, hows = 0, []
    for name, l, r in goals:
        p = Prover(mathlib_context=ctx)
        apply_knobs(p, knobs)
        if not knobs.get("energy", True):
            _orig = P.energy
            P.energy = lambda cand, syms, led: 0.0
            try:
                ok, how = p.prove(parse_term(l), parse_term(r))
            finally:
                P.energy = _orig
        else:
            ok, how = p.prove(parse_term(l), parse_term(r))
        proved += bool(ok)
        if ok:
            hows.append(how)
    refuted = 0
    for name, l, r in falses:
        p = Prover(mathlib_context=ctx)
        apply_knobs(p, knobs)
        ok, how = p.prove(parse_term(l), parse_term(r))
        refuted += (not ok and how.startswith("REFUTED"))
    return proved, refuted, hows


def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"}))
        return
    t0 = time.time()
    nat, lst = load_mathlib_context(), load_list_context()
    ctx = (nat[0] + lst[0], nat[1] + lst[1])
    res = {"battery": BATTERY_ID, "n_goals": len(GOALS),
           "n_false": len(FALSE_GOALS), "parent_knobs": DEFAULT_KNOBS}

    # 親(現在の設定)
    base_p, base_r, base_hows = run_battery(ctx, DEFAULT_KNOBS)
    res["parent"] = {"proved": base_p, "refuted": base_r}

    # Q1: 作業ログ → ハーネス項
    res["lift"] = lift_all(base_hows)

    # 変分(単一変更のみ)
    rows = []
    for v in variations():
        pr, rf, _h = run_battery(ctx, v["knobs"])
        delta = pr - base_p
        rows.append({"name": v["name"], "changed": v["changed"],
                     "from": v["from"], "to": v["to"],
                     "establishes": v["establishes"],
                     "proved": pr, "delta": delta,
                     "refuted": rf,
                     "verdict": classify(delta),
                     "witness": f"verified:run:prover@{BATTERY_ID}"})
    res["variations"] = rows

    # Q4: 目標順を反転しても採否が一致
    mismatches = []
    base_rev, _br, _bh = run_battery(ctx, DEFAULT_KNOBS, order="reverse")
    for v in variations():
        pr, _rf, _h = run_battery(ctx, v["knobs"], order="reverse")
        vd = classify(pr - base_rev)
        got = next(r["verdict"] for r in rows if r["name"] == v["name"])
        if vd != got:
            mismatches.append({"name": v["name"], "forward": got,
                               "reversed": vd})
    res["order_mismatch"] = mismatches

    # Q5: 採択された変分でも健全性(Lean 全通・不健全0)
    unsound = []
    adopted = [r for r in rows if r["verdict"] == "adopted"]
    for a in adopted:
        knobs = next(v["knobs"] for v in variations() if v["name"] == a["name"])
        for name, l, r in GOALS:
            p = Prover(mathlib_context=ctx)
            apply_knobs(p, knobs)
            ok, _how = p.prove(parse_term(l), parse_term(r))
            if not ok:
                continue
            fix = (LEAN.get(name) or LEAN_POLY.get(name)
                   or LEAN_L.get(name) or LEAN_Q.get(name))
            v_ = (str(verify(fix).get("verdict")) if fix
                  else lean_lemma(parse_term(l), parse_term(r))["verdict"])
            if v_ != "VERIFIED":
                unsound.append({"variation": a["name"], "goal": name,
                                "lean": v_})
    res["adopted"] = [a["name"] for a in adopted]
    res["unsound_in_adopted"] = unsound

    res["Q1_ok"] = res["lift"]["n_lifted"] > 0
    res["Q2_ok"] = any(r["verdict"] == "harmful" for r in rows)
    res["Q3_ok"] = all(r["verdict"] in ("adopted", "abstain", "harmful")
                       for r in rows)
    res["Q4_ok"] = not mismatches
    res["Q5_ok"] = not unsound
    res["all_pass"] = all([res["Q1_ok"], res["Q3_ok"], res["Q4_ok"],
                           res["Q5_ok"]])
    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")


if __name__ == "__main__":
    main()
