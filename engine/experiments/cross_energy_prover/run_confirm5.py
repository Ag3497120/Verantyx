# -*- coding: utf-8 -*-
"""確認測定5 — PREREG5.md が事前登録。目標集合の不動点 + 規則の持ち越し。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prover import DEFS, Prover, generalise_str, is_symmetric, parse_term
from run_confirm import CONFIRM, REGRESS, LEAN, lean_lemma
from run_confirm3 import BATTERY
from verantyx.lean_witness import lean_binary, verify
from verantyx.proof_ledger import ProofLedger

LEDGER = Path(__file__).with_name("proof_ledger5.json")
ALL = CONFIRM + REGRESS + BATTERY


def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"}))
        return
    t0 = time.time()
    for p in (LEDGER, LEDGER.with_name(LEDGER.stem + ".gaps.json")):
        if p.exists():
            p.unlink()
    ledger = ProofLedger(LEDGER)

    rules = list(DEFS)
    oriented: list = []
    pending = list(ALL)
    results = {}
    rounds = 0
    while True:
        rounds += 1
        got = []
        for name, l, r in pending:
            p = Prover(rules=rules, proof_ledger=ledger)
            p.oriented = list(oriented)
            t1 = time.time()
            ok, how = p.prove(parse_term(l), parse_term(r))
            results[name] = {"name": name, "goal": f"{l} = {r}",
                             "proved": ok, "how": how, "round": rounds,
                             "lemmas": p.stats["lemmas"],
                             "nodes": p.stats["nodes"],
                             "seconds": round(time.time() - t1, 1)}
            if ok:
                got.append(name)
                ledger.close_goal(name, l, r, how=how)
                ledger.add_lemma(l, r, how=how, origin_goal=name,
                                 ground_passed=-1)
                # このプロセスで核が証明した規則だけを持ち越す
                rules = p.rules
                oriented = list(p.oriented)
                tl, tr = parse_term(l), parse_term(r)
                gname = name
                rules = rules + [(gname, generalise_str(tl),
                                  generalise_str(tr))]
                if is_symmetric(tl, tr):
                    oriented.append(gname)
        pending = [g for g in pending if g[0] not in {n for n in got}]
        if not got or not pending:
            break
    for name, l, r in pending:
        ledger.open_goal(name, l, r, failure_type=results[name]["how"],
                         needs=["lpo_kbo", "general_ac"])

    res = {"rounds": rounds,
           "goals": [results[n] for n, _l, _r in ALL]}
    unsound, ver = [], 0
    for g in res["goals"]:
        if not g["proved"]:
            continue
        if g["name"] in LEAN:
            verdict = str(verify(LEAN[g["name"]]).get("verdict"))
        else:
            l, r = g["goal"].split(" = ", 1)
            verdict = lean_lemma(parse_term(l), parse_term(r))["verdict"]
        if verdict == "VERIFIED":
            ver += 1
        else:
            unsound.append({"goal": g["name"], "lean": verdict})
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
    Path(__file__).with_name("results_confirm5.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
