# -*- coding: utf-8 -*-
"""探索 — PREREG.md が事前登録。カーネル無改造・決定論・乱数なし。"""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.lean_witness import lean_binary, verify
from verantyx.rewrite_kernel import RuleStore, simplify

DEFS = [("add_0", "add(?x, 0)", "?x"),
        ("add_s", "add(?x, s(?y))", "s(add(?x, ?y))"),
        ("mul_0", "mul(?x, 0)", "0"),
        ("mul_s", "mul(?x, s(?y))", "add(mul(?x, ?y), ?x)")]

GOALS = [("G1", "add(0, x)", "x"),
         ("G2", "add(s(x), y)", "s(add(x, y))"),
         ("G3", "add(x, y)", "add(y, x)"),
         ("G4", "add(add(x, y), z)", "add(x, add(y, z))"),
         ("G5", "mul(0, x)", "0"),
         ("G6", "mul(x, 0)", "0"),
         ("G7", "mul(s(x), y)", "add(mul(x, y), y)"),
         ("G8", "mul(x, y)", "mul(y, x)")]

LEAN = {"G1": "theorem t (x : Nat) : 0 + x = x := by omega",
        "G2": "theorem t (x y : Nat) : (x+1) + y = (x + y) + 1 := by omega",
        "G3": "theorem t (x y : Nat) : x + y = y + x := by omega",
        "G4": "theorem t (x y z : Nat) : (x + y) + z = x + (y + z) := by omega",
        "G5": "theorem t (x : Nat) : 0 * x = 0 := by simp",
        "G6": "theorem t (x : Nat) : x * 0 = 0 := by simp",
        "G7": "theorem t (x y : Nat) : (x+1) * y = x * y + y := by "
              "induction y with | zero => simp | succ n ih => simp [Nat.mul_succ] at * <;> omega",
        "G8": "theorem t (x y : Nat) : x * y = y * x := by "
              "exact Nat.mul_comm x y"}

VAR = re.compile(r"(?<![A-Za-z0-9_])([xyz])(?![A-Za-z0-9_])")

def vars_of(*exprs):
    seen = []
    for e in exprs:
        for m in VAR.finditer(e):
            if m.group(1) not in seen:
                seen.append(m.group(1))
    return seen

def sub(e, v, val):
    return VAR.sub(lambda m: val if m.group(1) == v else m.group(1), e)

def generalise(e):
    """素の変数をパターン変数へ(x → ?x)。

    証明済みの補題を規則に昇格するとき、これをしないと変数が**定数**の
    ままで、ほぼ何にも一致しない(実測: G1 を `add(0, x)→x` で足しても
    `add(0, y)` は書き換わらない)。補題は全称命題なので、規則にする
    ときは全称のまま置く。IH も同様 — 帰納する変数以外は全称。
    """
    return VAR.sub(lambda m: "?" + m.group(1), e)

def store(rules):
    rs = RuleStore()
    for n, l, r in rules:
        rs.add(n, l, r)
    return rs

def nf(e, rs):
    r = simplify(e, rs, budget=400)
    return r.get("term") if str(r.get("verdict")) == "ANSWER" else None

def try_prove(lhs, rhs, rules, stats):
    """直接 → 各変数への帰納。閉じた手順。決めるのは駆動層。"""
    rs = store(rules)
    stats["nodes"] += 1
    a, b = nf(lhs, rs), nf(rhs, rs)
    if a is not None and a == b:
        return True, "direct"
    for v in vars_of(lhs, rhs):
        stats["nodes"] += 1
        rs0 = store(rules)
        # **None は「予算切れ」であって「一致」ではない。**
        # `nf(a) != nf(b)` と書くと、両側が予算切れ(None)のとき
        # None != None が False になり、**基底が閉じたことにされる**。
        # 実測 2026-08-19: 可換律を規則に昇格した後の系では add(a,b) が
        # 予算切れになり、G4/G7/G8 が**空虚に「証明」されていた**。
        # Lean は命題自体が真なので捕まえられなかった —
        # 独立検査は「主張が真か」を見るのであって
        # 「導出が本物か」は見ない。
        b0, b1 = nf(sub(lhs, v, "0"), rs0), nf(sub(rhs, v, "0"), rs0)
        if b0 is None or b1 is None or b0 != b1:
            continue                                  # 基底が閉じない
        rs1 = store(rules)
        rs1.add("IH", generalise(sub(lhs, v, "k")),
                generalise(sub(rhs, v, "k")))
        s0 = nf(sub(lhs, v, "s(k)"), rs1)
        s1 = nf(sub(rhs, v, "s(k)"), rs1)
        if s0 is not None and s1 is not None and s0 == s1:
            return True, "induction on %s" % v
    return False, None

def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"})); return
    t0 = time.time()
    rules = list(DEFS)
    proven, how, stats = {}, {}, {"nodes": 0}
    rounds = 0
    pending = list(GOALS)
    while True:
        rounds += 1
        got = []
        for name, lhs, rhs in pending:
            ok, method = try_prove(lhs, rhs, rules, stats)
            if ok:
                proven[name] = (lhs, rhs)
                how[name] = "%s (round %d)" % (method, rounds)
                # 証明できたら規則に昇格 — **全称のまま**(パターン変数へ)
                rules.append((name, generalise(lhs), generalise(rhs)))
                got.append(name)
        pending = [g for g in pending if g[0] not in proven]
        if not got or not pending:
            break
    res = {"rounds": rounds, "nodes_explored": stats["nodes"],
           "proved": sorted(proven), "unproved": [g[0] for g in pending],
           "how": how, "verified": 0, "unsound": 0,
           "seconds_search": round(time.time() - t0, 1)}
    bad = []
    for name in sorted(proven):
        v = verify(LEAN[name])
        if str(v.get("verdict")) == "VERIFIED":
            res["verified"] += 1
        else:
            res["unsound"] += 1
            bad.append({"goal": name, "lean": v.get("verdict")})
    res["lean_failures"] = bad
    res["seconds_total"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
