# -*- coding: utf-8 -*-
"""向き付き書き換え — PREREG.md が事前登録。決定論・読み取り専用。

カーネルは変更しない。向き付けは `simplify` の外側で、規則の適用可否を
項順序で決める薄い層として実装する(閉包の内側 — 探索も後戻りもしない)。
"""
import json, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.lean_witness import lean_binary, verify
from verantyx.rewrite_kernel import (Rule, RuleStore, default_algebra_rules,
                                     match, parse_term, subst, term_to_str)

def tsize(t):
    if isinstance(t, tuple):
        return 1 + sum(tsize(x) for x in t[1:])
    return 1

def key(t):
    return (tsize(t), term_to_str(t))

def step_ordered(t, rules, comm_names):
    """leftmost-innermost で1回。可換規則は**真に小さくなる時だけ**適用。"""
    if isinstance(t, tuple):
        for i, sub in enumerate(t[1:], start=1):
            r = step_ordered(sub, rules, comm_names)
            if r is not None:
                new_sub, name = r
                return (t[:i] + (new_sub,) + t[i + 1:]), name
    for rule in rules.rules:
        b = match(rule.lhs, t, {})
        if b is None:
            continue
        out = subst(rule.rhs, b)
        if rule.name in comm_names and not (key(out) < key(t)):
            continue          # 向き: 小さくならない適用は行わない
        return out, rule.name
    return None

def simplify_ordered(expr, rules, comm_names, budget=200):
    t = parse_term(expr)
    if t is None:
        return {"verdict": "UNKNOWN_UNPARSED"}
    for _ in range(budget):
        r = step_ordered(t, rules, comm_names)
        if r is None:
            return {"verdict": "ANSWER", "term": term_to_str(t), "t": t}
        t = r[0]
    return {"verdict": "UNKNOWN_BUDGET", "term": term_to_str(t), "t": t}

VARS = ["a", "b", "c"]
def gen(rng, d=0):
    if d >= 3 or rng.random() < 0.3:
        return rng.choice(VARS + ["0", "1"])
    op = rng.choice(["+", "-", "*", "+", "-"]); l = gen(rng, d + 1)
    if op == "*":
        return "(%s * %s)" % (l, rng.choice(["0", "1"]))
    return "(%s %s %s)" % (l, op, gen(rng, d + 1))

def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"})); return
    rng = random.Random(20260819)
    exprs, seen = [], set()
    while len(exprs) < 60:
        e = gen(rng)
        if e not in seen and sum(1 for c in e if c not in "() ") >= 4:
            seen.add(e); exprs.append(e)

    def arm(label, extra, comm):
        rs = default_algebra_rules()
        for n, l, r in extra:
            rs.add(n, l, r)
        res = {"answer": 0, "budget": 0, "verified": 0, "unsound": 0}
        t0 = time.time()
        for e in exprs:
            r = simplify_ordered(e, rs, comm)
            if str(r.get("verdict")) == "UNKNOWN_BUDGET":
                res["budget"] += 1; continue
            if str(r.get("verdict")) != "ANSWER":
                continue
            res["answer"] += 1
            v = verify("theorem t (a b c : Int) : %s = %s := by omega"
                       % (e, r["term"]))
            if str(v.get("verdict")) == "VERIFIED":
                res["verified"] += 1
            else:
                res["unsound"] += 1
        res["seconds"] = round(time.time() - t0, 1)
        return res

    COMM = [("add_comm", "?a + ?b", "?b + ?a")]
    out = {"n": len(exprs),
           "A_shrinking_only": arm("A", [], set()),
           "B_comm_unoriented": arm("B", COMM, set()),
           "C_comm_ordered": arm("C", COMM, {"add_comm"})}
    # C は b+a と a+b を同じ正規形へ落とすか
    rs = default_algebra_rules(); rs.add("add_comm", "?a + ?b", "?b + ?a")
    p1 = simplify_ordered("(b + a)", rs, {"add_comm"})
    p2 = simplify_ordered("(a + b)", rs, {"add_comm"})
    out["C_normalises_permutations"] = (p1.get("term") == p2.get("term"))
    out["C_example"] = {"(b + a)": p1.get("term"), "(a + b)": p2.get("term")}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
