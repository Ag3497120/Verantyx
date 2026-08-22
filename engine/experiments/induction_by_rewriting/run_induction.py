# -*- coding: utf-8 -*-
"""帰納法を書き換えで — PREREG.md が事前登録。カーネルは無改造。

駆動層は薄い: 基底と段に割り、段では**帰納法の仮定を規則として加える**。
実際の証明作業はすべてカーネルの書き換えが行う。
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.lean_witness import lean_binary, verify
from verantyx.rewrite_kernel import (RuleStore, parse_term, simplify,
                                     term_to_str)

def base_rules():
    rs = RuleStore()
    rs.add("add_0", "add(?x, 0)", "?x")
    rs.add("add_s", "add(?x, s(?y))", "s(add(?x, ?y))")
    return rs

def subst_var(s, var, val):
    """文字列レベルの単純置換(変数は1文字なので安全)。"""
    out, i = [], 0
    while i < len(s):
        if s[i] == var and (i == 0 or not s[i-1].isalnum()) and \
           (i+1 >= len(s) or not s[i+1].isalnum()):
            out.append(val)
        else:
            out.append(s[i])
        i += 1
    return "".join(out)

def nf(expr, rs):
    r = simplify(expr, rs, budget=300)
    return r.get("term") if str(r.get("verdict")) == "ANSWER" else None

def prove_by_induction(lhs, rhs, var, extra_rules=()):
    """var についての帰納法。閉じた手順・探索なし。"""
    trace = {}
    # 基底: var := 0
    rs = base_rules()
    for n, l, r in extra_rules:
        rs.add(n, l, r)
    b_l, b_r = nf(subst_var(lhs, var, "0"), rs), nf(subst_var(rhs, var, "0"), rs)
    trace["base"] = {"lhs": b_l, "rhs": b_r, "ok": b_l is not None and b_l == b_r}
    if not trace["base"]["ok"]:
        return False, trace
    # 段: var := k(新しい定数)、帰納法の仮定を**規則として**加える
    rs2 = base_rules()
    for n, l, r in extra_rules:
        rs2.add(n, l, r)
    ih_l, ih_r = subst_var(lhs, var, "k"), subst_var(rhs, var, "k")
    rs2.add("IH", ih_l, ih_r)                      # ← 仮定を規則に
    s_l = nf(subst_var(lhs, var, "s(k)"), rs2)
    s_r = nf(subst_var(rhs, var, "s(k)"), rs2)
    trace["step"] = {"ih": "%s -> %s" % (ih_l, ih_r), "lhs": s_l, "rhs": s_r,
                     "ok": s_l is not None and s_l == s_r}
    return trace["step"]["ok"], trace

def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"})); return
    t0 = time.time()
    out = {"theorems": []}

    # T1: add(0, x) = x  — x について帰納
    ok1, tr1 = prove_by_induction("add(0, x)", "x", "x")
    # T2: add(s(x), y) = s(add(x, y)) — y について帰納
    ok2, tr2 = prove_by_induction("add(s(x), y)", "s(add(x, y))", "y")
    # T3: 可換律 — T1,T2 を規則として与えた上で y について帰納
    extra = [("T1", "add(0, ?a)", "?a"),
             ("T2", "add(s(?a), ?b)", "s(add(?a, ?b))")]
    ok3, tr3 = prove_by_induction("add(x, y)", "add(y, x)", "y",
                                  extra_rules=extra)

    # 検査の戦術は omega に統一する。最初は `induction y <;> simp <;> omega`
    # と書いたが、simp が全目標を閉じた後に omega が「目標が無い」で失敗し、
    # T2/T3 が UNPROVEN になった — **命題は真で、私の戦術が壊れていた**。
    # 独立検査の道具が壊れていると、健全な導出を不健全と誤報する。
    LEAN = {
        "T1": "theorem t (x : Nat) : 0 + x = x := by omega",
        "T2": "theorem t (x y : Nat) : (x + 1) + y = (x + y) + 1 := by omega",
        "T3": "theorem t (x y : Nat) : x + y = y + x := by omega",
    }
    for name, ok, tr in (("T1", ok1, tr1), ("T2", ok2, tr2), ("T3", ok3, tr3)):
        v = verify(LEAN[name])
        out["theorems"].append({
            "name": name, "kernel_proved": bool(ok),
            "lean_on_statement": v.get("verdict"), "trace": tr})
    out["seconds"] = round(time.time() - t0, 1)
    # 不健全の検査: カーネルが証明したと言い、Lean が偽と言うものは無いか
    out["unsound"] = sum(1 for t in out["theorems"]
                         if t["kernel_proved"] and
                         t["lean_on_statement"] != "VERIFIED")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
