# -*- coding: utf-8 -*-
"""確認測定 — PREREG.md が事前登録。ハーネス代数 v0。"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from interpreter import (MockA, MockB, check_law, ground_harnesses, run,
                        INPUTS, _nat_term)
from verantyx.prover import (DEFS, nf, parse_term, term_to_str,
                             lean_witness_for)

LAWS = [
    ("A1", "hseq(hseq(f, g), h)", "hseq(f, hseq(g, h))"),
    ("A2", "hretry(hretry(f, a), b)", "hretry(f, mul(a, b))"),
    ("A3", "htrunc(htrunc(f, a), b)", "htrunc(f, min(a, b))"),
    ("A4", "hretry(f, s(0))", "f"),
    ("A5", "hjudge(hjudge(f))", "hjudge(f)"),
]
FALSE_LAWS = [
    ("F1", "hseq(f, g)", "hseq(g, f)"),
    ("F2", "hretry(f, s(s(0)))", "f"),
    ("F3", "htrunc(f, s(s(s(s(0)))))", "f"),
]
UNDECIDED = [
    ("X1", "htrunc(hretry(f, a), b)", "hretry(htrunc(f, b), a)"),
]
#: 書き換え規則(構造則の畳む向き)。budget は接地なので min/mul は
#: N側の定義規則で数まで落ちる。
HRULES = [
    ("A1", "hseq(hseq(?f, ?g), ?h)", "hseq(?f, hseq(?g, ?h))"),
    ("A2", "hretry(hretry(?f, ?a), ?b)", "hretry(?f, mul(?a, ?b))"),
    ("A3", "htrunc(htrunc(?f, ?a), ?b)", "htrunc(?f, min(?a, ?b))"),
    ("A4", "hretry(?f, s(0))", "?f"),
    ("A5", "hjudge(hjudge(?f))", "hjudge(?f)"),
]


def main():
    t0 = time.time()
    res = {}

    # ① 構造則(接地検査)+ ② 偽法則 + ③ 判定保留
    for group, laws in (("laws", LAWS), ("false_laws", FALSE_LAWS),
                        ("undecided", UNDECIDED)):
        rows = []
        for name, l, r in laws:
            c = check_law(l, r, max_assign=400)
            verdict = c["verdict"]
            if group == "undecided" and verdict == "PASSED":
                verdict = "UNTESTED"     # 昇格しない — 構成で保証していない
            rows.append({"name": name, "law": f"{l} = {r}",
                         "verdict": verdict, **{k: v for k, v in c.items()
                                                if k != "verdict"}})
        res[group] = rows

    # ⑤ 予算側の恒等式は Lean でも(既存経路)
    res["lean_budget"] = {
        "min_idem": lean_witness_for(parse_term("min(a, a)"),
                                     parse_term("a")),
        "mul_one": lean_witness_for(parse_term("mul(a, s(0))"),
                                    parse_term("a")),
    }

    # 圧縮: 深さ≤3 の全項 → 構造則で正準形へ
    terms = ground_harnesses(3)
    rules = HRULES + DEFS
    canon = {}
    for t in terms:
        n = nf(t, rules)
        key = term_to_str(n) if n is not None else "(budget)"
        canon.setdefault(key, []).append(term_to_str(t))
    res["compression"] = {
        "terms": len(terms), "canonical_forms": len(canon),
        "sample_collapse": sorted(
            ({"canonical": k, "collapsed": len(v)}
             for k, v in canon.items()), key=lambda x: -x["collapsed"])[:5]}

    # ④ 順序: 規則列反転で正準形集合が不変
    canon_rev = set()
    rules_rev = list(reversed(HRULES)) + list(reversed(DEFS))
    for t in terms:
        n = nf(t, rules_rev)
        canon_rev.add(term_to_str(n) if n is not None else "(budget)")
    res["order_invariance"] = {
        "forward_forms": len(canon), "reversed_forms": len(canon_rev),
        "identical": set(canon) == canon_rev}

    # 経験則: モデル別に実行が earn する事実(証人つき・転移の実測)
    def success_rate(term_s):
        out = {}
        for model in (MockA, MockB):
            ok = sum(1 for s in INPUTS if run(parse_term(term_s), s,
                                              model())[0])
            out[model.name] = f"{ok}/{len(INPUTS)}"
        return out

    plain = success_rate("hact(0)")
    retry2 = success_rate("hretry(hact(0), s(s(0)))")
    trunc6 = success_rate("htrunc(hact(0), s(s(s(s(s(s(0)))))))")
    facts = []
    for label, base, var in (("retry2_helps", plain, retry2),
                             ("trunc6_helps", plain, trunc6)):
        for m in ("mockA", "mockB"):
            b = int(base[m].split("/")[0])
            v = int(var[m].split("/")[0])
            facts.append({"fact": label, "model": m,
                          "base": base[m], "variant": var[m],
                          "adopted": v > b,
                          "witness": f"verified:run:{m}@2026-08-20"})
    res["empirical"] = {"rates": {"plain": plain, "retry2": retry2,
                                  "trunc6": trunc6},
                        "facts": facts,
                        "model_specific": any(
                            f1["adopted"] != f2["adopted"]
                            for f1 in facts for f2 in facts
                            if f1["fact"] == f2["fact"]
                            and f1["model"] != f2["model"])}
    # 転移の実測: mockA で採択された事実を mockB に適用したら
    transfer = []
    for f1 in facts:
        if f1["model"] == "mockA" and f1["adopted"]:
            f2 = next(x for x in facts if x["fact"] == f1["fact"]
                      and x["model"] == "mockB")
            transfer.append({"fact": f1["fact"],
                             "mockA": "adopted",
                             "mockB": ("adopted" if f2["adopted"]
                                       else "NOT_TRANSFERRED")})
    res["transfer"] = transfer

    res["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")


if __name__ == "__main__":
    main()
