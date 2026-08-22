# -*- coding: utf-8 -*-
"""番犬 — PREREG.md が事前登録。決定論・読み取り専用。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "search"))
from run_search import DEFS, GOALS, generalise, store, sub, vars_of
from run_ac import ac, nf_ac, try_prove
from verantyx.lean_witness import lean_binary, verify

#: 偽であることが分かっている等式。健全な規則集合では証明できない。
#:
#: **構成子だけの等式では足りない**(2026-08-19実測): `add(?x,?y) → 0` の
#: ような、演算子を潰すが構成子には触れない壊れ方を見逃した。番犬は
#: **使っている演算子を実際に通る**偽の等式を持たねばならない。
FALSE_EQUATIONS = [
    # 構成子(0 と s(n) は異なる)
    ("0", "s(0)"), ("s(0)", "s(s(0))"), ("0", "s(s(0))"), ("s(0)", "0"),
    # add を通る偽(add(s(0),0)=s(0) なので 0 とは異なる)
    ("add(s(0), 0)", "0"), ("add(0, s(0))", "0"),
    ("add(s(0), s(0))", "s(0)"),
    # mul を通る偽(mul(s(0),s(0))=s(0) なので 0 とは異なる)
    ("mul(s(0), s(0))", "0"), ("mul(s(s(0)), s(0))", "0"),
    # **変数を含む偽**。閉じた項だけでは足りない(2026-08-19実測):
    # `add(?x,?y) → 0` のような壊れ方は、正しい規則(add(?x,0)→?x /
    # add(?x,s(?y))→…)が先に発火して**影に隠れ**、閉じた項では
    # 一度も噛まない。変数を含む項でだけ表に出る。
    ("add(x, y)", "0"), ("mul(x, y)", "0"),
    ("add(x, y)", "x"), ("s(x)", "x"), ("s(x)", "0"),
]

def canary(rules, oriented):
    """偽の等式が証明できてしまわないか。鳴いた等式を返す。"""
    barked = []
    for l, r in FALSE_EQUATIONS:
        ok, _how = try_prove(l, r, rules, oriented, {"nodes": 0})
        if ok:
            barked.append("%s = %s" % (l, r))
    return barked

def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"})); return
    t0 = time.time()
    out = {"checks": []}

    # ① 正常系: 探索の全行程で番犬が鳴かないか
    rules, oriented, proven = list(DEFS), [], []
    out["checks"].append({"stage": "定義のみ", "barked": canary(rules, oriented)})
    pending = list(GOALS)
    rounds = 0
    while True:
        rounds += 1
        got = []
        for name, l, r in pending:
            ok, _ = try_prove(l, r, rules, oriented, {"nodes": 0})
            if ok:
                proven.append(name)
                gl, gr = generalise(l), generalise(r)
                rules.append((name, gl, gr))
                if name in ("G3", "G4", "G8"):
                    oriented.append(name)
                got.append(name)
                out["checks"].append({"stage": "%s 昇格後" % name,
                                      "barked": canary(rules, oriented)})
        pending = [g for g in pending if g[0] not in proven]
        if not got or not pending:
            break
    out["proved"] = proven
    out["normal_barks"] = sum(len(c["barked"]) for c in out["checks"])

    # ② 番犬は本当に働くか: 故意に壊れた規則を混ぜる
    broken = list(rules) + [("BROKEN", "add(?x, ?y)", "0")]
    out["broken_barks"] = canary(broken, oriented)
    mulbroken = list(rules) + [("BROKEN2", "mul(?x, ?y)", "0")]
    out["mul_broken_barks"] = canary(mulbroken, oriented)
    # ③ もっと露骨に壊す
    collapse = list(DEFS) + [("COLLAPSE", "s(?x)", "0")]
    out["collapse_barks"] = canary(collapse, [])

    out["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
