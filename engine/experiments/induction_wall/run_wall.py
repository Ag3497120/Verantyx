# -*- coding: utf-8 -*-
"""帰納法の壁 — PREREG.md が事前登録。決定論・読み取り専用。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.lean_witness import lean_binary, verify
from verantyx.rewrite_kernel import (default_algebra_rules, parse_term,
                                     simplify)

# A群: 等式恒等式(変数つき・帰納法不要)。左右を独立に正規形へ落とし、
# 一致すれば「導出できた」とみなす — これが等式理論での全称証明。
A = [("(a + 0)", "a"), ("(0 + a)", "a"), ("(a * 1)", "a"), ("(1 * a)", "a"),
     ("(a * 0)", "0"), ("(0 * a)", "0"), ("(a - 0)", "a"), ("(a - a)", "0"),
     ("((a + 0) * 1)", "a"), ("((a - a) + b)", "b"),
     ("((a * 0) + (b * 1))", "b"), ("(((a + 0) - a) + c)", "c"),
     ("((1 * a) - (a * 1))", "0"), ("(((a * 1) + 0) * 1)", "a"),
     ("((0 + (b - b)) + a)", "a"), ("(((a - a) * c) + b)", "b"),
     ("((a + 0) + (0 + b))", "(a + b)"), ("(((0 * c) + a) - 0)", "a"),
     ("((b * 1) - (b - b))", "b"), ("(((a - a) + (b * 1)) * 1)", "b")]

# B群: 帰納法を要する自然数の命題(等式の書き換えでは到達しない)
B = [("n + m = m + n", "加法の可換律"),
     ("n + (m + k) = (n + m) + k", "加法の結合律"),
     ("n * m = m * n", "乗法の可換律"),
     ("n * (m + k) = n * m + n * k", "分配律"),
     ("n + 0 = n", "右単位元"),
     ("0 + n = n", "左単位元"),
     ("n * 1 = n", "乗法の単位元"),
     ("n * 0 = 0", "乗法の零元"),
     ("(n + m) * k = n * k + m * k", "右分配"),
     ("n * (m * k) = (n * m) * k", "乗法の結合律")]

def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"})); return
    rules = default_algebra_rules()
    t0 = time.time()
    out = {"A": {"n": len(A), "derived": 0, "verified": 0, "unsound": 0},
           "B": {"n": len(B), "derived": 0, "omega_ok": 0, "induction_needed": 0}}
    bad = []
    for expr, want in A:
        r = simplify(expr, rules)
        if str(r.get("verdict")) != "ANSWER":
            continue
        got = r.get("term")
        # 期待側も同じカーネルで正規形にしてから比べる(公平に)。
        # **項どうし**で比べる — 印字文字列の比較は括弧を落とし、
        # 結合律が「導出された」ように見せる(2026-08-19、この実験自身が
        # 踏んだ誤り。term_to_str の往復欠陥として別途修理・fork 化した)。
        w = simplify(want, rules)
        same = (parse_term(got) == parse_term(w.get("term")))
        if not same:
            continue
        out["A"]["derived"] += 1
        v = verify("theorem t (a b c : Int) : %s = %s := by omega" % (expr, got))
        if str(v.get("verdict")) == "VERIFIED":
            out["A"]["verified"] += 1
        else:
            out["A"]["unsound"] += 1
            bad.append({"expr": expr, "got": got, "lean": v.get("verdict")})
    for stmt, label in B:
        lhs, rhs = stmt.split(" = ")
        rl, rr = simplify(lhs, rules), simplify(rhs, rules)
        if (str(rl.get("verdict")) == "ANSWER"
                and str(rr.get("verdict")) == "ANSWER"
                and parse_term(rl.get("term")) == parse_term(rr.get("term"))):
            out["B"]["derived"] += 1
        # Lean 側: omega で通るか / induction が要るか
        v1 = verify("theorem t (n m k : Nat) : %s := by omega" % stmt)
        if str(v1.get("verdict")) == "VERIFIED":
            out["B"]["omega_ok"] += 1
        else:
            v2 = verify("theorem t (n m k : Nat) : %s := by induction n <;> simp <;> omega"
                        % stmt)
            if str(v2.get("verdict")) == "VERIFIED":
                out["B"]["induction_needed"] += 1
    out["seconds"] = round(time.time() - t0, 1)
    out["unsound_examples"] = bad
    print(json.dumps(out, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
