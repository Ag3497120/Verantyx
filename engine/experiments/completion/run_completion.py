# -*- coding: utf-8 -*-
"""Knuth-Bendix 完備化 — PREREG.md が事前登録。決定論・カーネルは無改造。

臨界対: 規則 l1→r1 の部分項が規則 l2→r2 の左辺と単一化するとき、
同じ項から2通りの書き換えが生じる。両者を正規形に落として一致しなければ、
その等式を項順序で向き付けて新しい規則に加える。
根拠は全て格納済みの規則 — 閉包の内側。
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verantyx.lean_witness import lean_binary, verify
from verantyx.rewrite_kernel import (Rule, RuleStore, order_key, parse_term,
                                     simplify, subst, term_to_str)

def rename(t, suffix):
    """変数を衝突しないよう改名。"""
    if isinstance(t, str) and t.startswith("?"):
        return t + suffix
    if isinstance(t, tuple):
        return (t[0],) + tuple(rename(x, suffix) for x in t[1:])
    return t

def unify(a, b, s=None):
    """一階の単一化(出現検査つき)。"""
    s = dict(s or {})
    def walk(t):
        while isinstance(t, str) and t.startswith("?") and t in s:
            t = s[t]
        return t
    def occurs(v, t):
        t = walk(t)
        if t == v: return True
        if isinstance(t, tuple): return any(occurs(v, x) for x in t[1:])
        return False
    def go(x, y):
        x, y = walk(x), walk(y)
        if x == y: return True
        if isinstance(x, str) and x.startswith("?"):
            if occurs(x, y): return False
            s[x] = y; return True
        if isinstance(y, str) and y.startswith("?"):
            if occurs(y, x): return False
            s[y] = x; return True
        if isinstance(x, tuple) and isinstance(y, tuple):
            if x[0] != y[0] or len(x) != len(y): return False
            return all(go(p, q) for p, q in zip(x[1:], y[1:]))
        return False
    return s if go(a, b) else None

def apply_sub(t, s):
    if isinstance(t, str) and t.startswith("?"):
        return apply_sub(s[t], s) if t in s else t
    if isinstance(t, tuple):
        return (t[0],) + tuple(apply_sub(x, s) for x in t[1:])
    return t

def positions(t):
    """非変数の部分項の位置。"""
    out = [()]
    if isinstance(t, tuple):
        for i, sub in enumerate(t[1:], start=1):
            if isinstance(sub, str) and sub.startswith("?"):
                continue
            for p in positions(sub):
                out.append((i,) + p)
    return out

def at(t, p):
    for i in p: t = t[i]
    return t

def replace(t, p, new):
    if not p: return new
    i = p[0]
    return t[:i] + (replace(t[i], p[1:], new),) + t[i+1:]

def critical_pairs(r1, r2):
    """r1 の部分項に r2 を重ねた臨界対 (両方の書き換え結果)。"""
    out = []
    l1, rr1 = rename(r1.lhs, "1"), rename(r1.rhs, "1")
    l2, rr2 = rename(r2.lhs, "2"), rename(r2.rhs, "2")
    for p in positions(l1):
        sub = at(l1, p)
        if isinstance(sub, str) and sub.startswith("?"): continue
        s = unify(sub, l2)
        if s is None: continue
        a = apply_sub(rr1, s)                       # r1 で書き換えた側
        b = apply_sub(replace(l1, p, rr2), s)       # r2 で書き換えた側
        if a != b: out.append((a, b))
    return out

def norm(t, rs, names):
    r = simplify(term_to_str(t), rs, oriented=names, budget=300)
    return parse_term(r.get("term")) if str(r.get("verdict")) == "ANSWER" else None

def complete(rs, max_rules=40, rounds=12):
    names = [r.name for r in rs.rules]
    added, log = 0, []
    for _ in range(rounds):
        new = None
        rules = list(rs.rules)
        for r1 in rules:
            for r2 in rules:
                for a, b in critical_pairs(r1, r2):
                    na, nb = norm(a, rs, names), norm(b, rs, names)
                    if na is None or nb is None or na == nb: continue
                    lo, hi = (na, nb) if order_key(na) < order_key(nb) else (nb, na)
                    new = (hi, lo, r1.name, r2.name)
                    break
                if new: break
            if new: break
        if not new: return added, log, True      # 完備
        hi, lo, n1, n2 = new
        nm = "kb%d" % (added + 1)
        rs.add(nm, term_to_str(hi), term_to_str(lo))
        names.append(nm)
        added += 1
        log.append({"rule": nm, "lhs": term_to_str(hi), "rhs": term_to_str(lo),
                    "from": [n1, n2]})
        if added >= max_rules: return added, log, False
    return added, log, False

# 群を整数の加法として読む: * → +, e → 0, i(x) → -x
def to_int_expr(s):
    s = s.replace("i(", "NEG(").replace("*", "+").replace("e", "0")
    out, i = [], 0
    while i < len(s):
        if s.startswith("NEG(", i):
            depth, j = 1, i + 4
            while j < len(s) and depth:
                if s[j] == "(": depth += 1
                elif s[j] == ")": depth -= 1
                j += 1
            out.append("(-(" + to_int_expr(s[i+4:j-1]) + "))")
            i = j
        else:
            out.append(s[i]); i += 1
    return "".join(out)

def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"})); return
    rs = RuleStore()
    rs.add("assoc", "(?x * ?y) * ?z", "?x * (?y * ?z)")
    rs.add("unit",  "e * ?x", "?x")
    rs.add("inv",   "i(?x) * ?x", "e")
    t0 = time.time()
    added, log, complete_ok = complete(rs)
    res = {"start_rules": 3, "derived": added, "completed": complete_ok,
           "verified": 0, "unproven": 0, "seconds": 0}
    bad = []
    for entry in log:
        lhs = to_int_expr(entry["lhs"]).replace("?", "")
        rhs = to_int_expr(entry["rhs"]).replace("?", "")
        src = "theorem t (x y z : Int) : %s = %s := by omega" % (lhs, rhs)
        v = verify(src)
        entry["int_form"] = "%s = %s" % (lhs, rhs)
        entry["lean"] = v.get("verdict")
        if str(v.get("verdict")) == "VERIFIED": res["verified"] += 1
        else:
            res["unproven"] += 1
            bad.append(entry)
    res["seconds"] = round(time.time() - t0, 1)
    res["derived_rules"] = log
    res["unproven_examples"] = bad[:5]
    print(json.dumps(res, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
