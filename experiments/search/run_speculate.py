# -*- coding: utf-8 -*-
"""補題の発見 — 失敗した基底/段の等式を、補題として推測し再帰的に証明する。

事前登録は PREREG.md の続き(判定は同じ: 健全性が崩れたら失格)。
探索は決定論・乱数なし・深さ制限つき。
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_search import DEFS, GOALS, LEAN, generalise, store, sub, vars_of
from verantyx.rewrite_kernel import parse_term, simplify

# 対称な補題(両辺が互いの置換 — 可換律の類)は、規則に昇格するとき
# **向き付き**にする。無向きのまま入れると a+b→b+a→a+b の往復で系が
# 停止しなくなる(branching_rewrite の実測)。実際 G3 を証明して昇格した
# 直後に `add(a, b)` が UNKNOWN_BUDGET になることを確認している —
# **自分で証明した定理が、自分の書き換え系を壊していた**。
ORIENTED = []

def is_symmetric(l, r):
    tl, tr = parse_term(l), parse_term(r)
    if tl is None or tr is None or l == r:
        return False
    if not (isinstance(tl, tuple) and isinstance(tr, tuple)):
        return False
    return (tl[0] == tr[0] and len(tl) == len(tr)
            and sorted(map(str, tl[1:])) == sorted(map(str, tr[1:])))

def nf(e, rs):
    r = simplify(e, rs, oriented=ORIENTED or None, budget=400)
    return r.get("term") if str(r.get("verdict")) == "ANSWER" else None
from verantyx.lean_witness import lean_binary, verify

def prove(lhs, rhs, rules, stats, depth=0, max_depth=3, seen=None):
    """直接 → 帰納 → **失敗した等式を補題として推測**(再帰)。"""
    seen = seen if seen is not None else set()
    key = (lhs, rhs)
    if key in seen or depth > max_depth:
        return False, None, rules
    seen = seen | {key}
    stats["nodes"] += 1
    rs = store(rules)
    a, b = nf(lhs, rs), nf(rhs, rs)
    if a is not None and a == b:
        return True, "direct", rules
    for v in vars_of(lhs, rhs):
        stats["nodes"] += 1
        rs0 = store(rules)
        b0, b1 = nf(sub(lhs, v, "0"), rs0), nf(sub(rhs, v, "0"), rs0)
        base_ok = (b0 is not None and b0 == b1)
        if not base_ok:
            # 基底が閉じない → その等式を補題として推測して再帰
            if b0 is not None and b1 is not None:
                stats["speculated"] += 1
                ok, _how, rules = prove(b0, b1, rules, stats, depth + 1,
                                        max_depth, seen)
                if ok:
                    stats["discovered"].append("%s = %s" % (b0, b1))
                    _n = "L%d" % len(rules)
                    _gl, _gr = generalise(b0), generalise(b1)
                    rules = rules + [(_n, _gl, _gr)]
                    if is_symmetric(_gl, _gr):
                        ORIENTED.append(_n)
                    rs0 = store(rules)
                    base_ok = (nf(sub(lhs, v, "0"), rs0)
                               == nf(sub(rhs, v, "0"), rs0))
            if not base_ok:
                continue
        rs1 = store(rules)
        rs1.add("IH", generalise(sub(lhs, v, "k")),
                generalise(sub(rhs, v, "k")))
        s0, s1 = nf(sub(lhs, v, "s(k)"), rs1), nf(sub(rhs, v, "s(k)"), rs1)
        if s0 is not None and s0 == s1:
            return True, "induction on %s (depth %d)" % (v, depth), rules
        # 段が閉じない → その等式を補題として推測して再帰
        if s0 is not None and s1 is not None:
            stats["speculated"] += 1
            ok, _how, rules = prove(s0, s1, rules, stats, depth + 1,
                                    max_depth, seen)
            if ok:
                stats["discovered"].append("%s = %s" % (s0, s1))
                _n = "L%d" % len(rules)
                _gl, _gr = generalise(s0), generalise(s1)
                rules = rules + [(_n, _gl, _gr)]
                if is_symmetric(_gl, _gr):
                    ORIENTED.append(_n)
                rs1 = store(rules)
                rs1.add("IH", generalise(sub(lhs, v, "k")),
                        generalise(sub(rhs, v, "k")))
                if nf(sub(lhs, v, "s(k)"), rs1) == nf(sub(rhs, v, "s(k)"), rs1):
                    return True, "induction on %s + 推測補題" % v, rules
    return False, None, rules

def run(names, label):
    del ORIENTED[:]                      # 腕ごとに初期化(独立に測る)
    goals = [g for g in GOALS if g[0] in names]
    rules = list(DEFS)
    stats = {"nodes": 0, "speculated": 0, "discovered": []}
    proven, how = [], {}
    for name, l, r in goals:
        ok, method, rules = prove(l, r, rules, stats)
        if ok:
            proven.append(name); how[name] = method
            gl, gr = generalise(l), generalise(r)
            rules = rules + [(name, gl, gr)]
            if is_symmetric(gl, gr):
                ORIENTED.append(name)
    return {"label": label, "proved": proven, "how": how,
            "oriented": list(ORIENTED),
            "unproved": [g[0] for g in goals if g[0] not in proven],
            "nodes": stats["nodes"], "speculated": stats["speculated"],
            "discovered": stats["discovered"][:6]}

def main():
    if lean_binary() is None:
        print(json.dumps({"skipped": "no lean toolchain"})); return
    t0 = time.time()
    out = {"arms": []}
    for names, label in (({"G3"}, "G3単独(加法可換のみ)"),
                         ({"G8"}, "G8単独(乗法可換のみ)"),
                         ({"G3", "G8"}, "可換律2本のみ"),
                         ({g[0] for g in GOALS}, "全8本")):
        out["arms"].append(run(names, label))
    # 健全性: 証明したと主張した goal を Lean で検査
    ver, uns = 0, []
    for arm in out["arms"]:
        for n in arm["proved"]:
            v = verify(LEAN[n])
            if str(v.get("verdict")) == "VERIFIED":
                ver += 1
            else:
                uns.append({"arm": arm["label"], "goal": n,
                            "lean": v.get("verdict")})
    out["lean_verified"] = ver
    out["unsound"] = len(uns)
    out["unsound_detail"] = uns
    out["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    Path(__file__).with_name("results_speculate.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
