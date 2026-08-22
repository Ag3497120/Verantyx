# -*- coding: utf-8 -*-
"""確認測定3 — PREREG3.md が事前登録。台帳(proof_ledger)配線込み。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prover import Prover, parse_term, term_to_str
from run_confirm import CONFIRM, REGRESS, LEAN, lean_lemma, to_lean, TACTICS
from verantyx.lean_witness import lean_binary, verify
from verantyx.proof_ledger import ProofLedger
from prover import VAR_TYPES, t_vars

BATTERY = [
    ("B1", "len(app(x, y))", "len(app(y, x))"),
    ("B2", "rev(app(x, y))", "app(rev(y), rev(x))"),
    ("B3", "len(rev(x))", "len(x)"),
    ("B4", "app(rev(x), nil)", "rev(x)"),
    ("B5", "rev(app(rev(x), nil))", "x"),
    ("B6", "len(app(x, cons(a, nil)))", "s(len(x))"),
    ("B7", "mul(a, s(0))", "a"),
    ("B8", "mul(s(0), a)", "a"),
    ("B9", "mul(add(a, b), c)", "add(mul(a, c), mul(b, c))"),
    ("B10", "len(app(app(x, y), z))", "add(add(len(x), len(y)), len(z))"),
    ("B11", "rev(cons(a, nil))", "cons(a, nil)"),
    ("B12", "mul(a, mul(b, c))", "mul(mul(a, b), c)"),
]

LEDGER = Path(__file__).with_name("proof_ledger.json")


def lean_goal(lhs, rhs):
    """目標の Lean 検査(補題と同じ自動翻訳+戦術ポートフォリオ)。"""
    return lean_lemma(parse_term(lhs), parse_term(rhs))


def run_goals(goals, ledger):
    out = []
    for name, l, r in goals:
        p = Prover(proof_ledger=ledger)
        t0 = time.time()
        ok, how = p.prove(parse_term(l), parse_term(r))
        row = {"name": name, "goal": f"{l} = {r}", "proved": ok, "how": how,
               "lemmas": p.stats["lemmas"], "nodes": p.stats["nodes"],
               "seconds": round(time.time() - t0, 1)}
        if ok:
            ledger.close_goal(name, l, r, how=how)
            # 目標も台帳の補題席に(起源=自分自身)
            ledger.add_lemma(l, r, how=how, origin_goal=name,
                             ground_passed=-1)
        else:
            ledger.open_goal(name, l, r,
                             failure_type=how,
                             needs=["abstraction_redesign", "lpo_kbo",
                                    "general_ac"])
        out.append(row)
    return out


def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"}))
        return
    t0 = time.time()
    if LEDGER.exists():
        LEDGER.unlink()   # 確認は白紙の台帳から(再現性)
    gp = LEDGER.with_name(LEDGER.stem + ".gaps.json")
    if gp.exists():
        gp.unlink()
    ledger = ProofLedger(LEDGER)

    res = {"confirm": run_goals(CONFIRM, ledger),
           "regress": run_goals(REGRESS, ledger),
           "battery": run_goals(BATTERY, ledger)}

    # S1: 主張の Lean 検査(固定 fixture がある目標はそれ、無い目標は
    # 自動翻訳ポートフォリオ)
    unsound, ver = [], 0
    for grp in ("confirm", "regress", "battery"):
        for g in res[grp]:
            if not g["proved"]:
                continue
            name = g["name"]
            if name in LEAN:
                v = verify(LEAN[name])
                verdict = str(v.get("verdict"))
            else:
                l, r = g["goal"].split(" = ", 1)
                verdict = lean_goal(l, r)["verdict"]
            if verdict == "VERIFIED":
                ver += 1
            else:
                unsound.append({"goal": name, "lean": verdict})
    res["lean_verified_targets"] = ver
    res["unsound"] = len(unsound)
    res["unsound_detail"] = unsound

    # 台帳の補題に Lean 証人を刻む(検査できた分)
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
    Path(__file__).with_name("results_confirm4.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
