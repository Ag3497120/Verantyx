"""Forks for Kripke model checking + term rewriting kernel."""
from __future__ import annotations

from typing import Any, Dict, List

from .cross_store import CrossStore
from .kripke import KripkeModel, check
from .rewrite_kernel import (
    RuleStore,
    default_algebra_rules,
    default_logic_rules,
    simplify,
)


def _model() -> KripkeModel:
    m = KripkeModel()
    m.add_world("w1", ["p"])
    m.add_world("w2", ["p", "q"])
    m.add_world("w3", ["q"])
    m.add_edge("w1", "w2")
    m.add_edge("w1", "w3")
    m.add_edge("w2", "w3")
    return m


def kripke_model_check_fork() -> Dict[str, Any]:
    """□=全後続一致 / ◇=1本到達 / 空虚な□ / 決定論."""
    m = _model()
    box_q = check(m, "box q", "w1")
    box_p = check(m, "box p", "w1")
    dia_pq = check(m, "dia (p and q)", "w1")
    vac = check(m, "box p", "w3")
    ok = (
        box_q["verdict"] == "ANSWER" and box_q["value"] is True
        and box_p["value"] is False
        and dia_pq["value"] is True
        and vac["value"] is True  # 後続なし → 空虚に真
        and check(m, "box q", "w1") == box_q
    )
    return {
        "experiment": "kripke",
        "fork": "KRIPKE_MODEL_CHECK",
        "pass": bool(ok),
        "result": {"box_q": box_q["value"], "box_p": box_p["value"],
                   "dia_pq": dia_pq["value"], "vacuous_box": vac["value"]},
    }


def kripke_validity_fork() -> Dict[str, Any]:
    """モデル内妥当性 = 全世界一致ゲート."""
    m = _model()
    valid = check(m, "p or q")
    invalid = check(m, "p and q")
    ok = (
        valid["value"] is True
        and invalid["value"] is False
        and invalid["per_world"]["w1"] is False
    )
    return {
        "experiment": "kripke",
        "fork": "KRIPKE_VALIDITY",
        "pass": bool(ok),
        "result": {"valid": valid["value"], "invalid_per_world": invalid["per_world"]},
    }


def kripke_unknown_refuses_fork() -> Dict[str, Any]:
    """未知世界・モデルに無い命題・非論理式は型付き拒否."""
    m = _model()
    prop = check(m, "box r", "w1")
    world = check(m, "p", "w9")
    junk = check(m, "p ++ q", "w1")
    ok = (
        prop["verdict"] == "UNKNOWN_NO_EVIDENCE"
        and world["verdict"] == "UNKNOWN_NO_EVIDENCE"
        and junk["verdict"] == "UNKNOWN_UNPARSED"
    )
    return {
        "experiment": "kripke",
        "fork": "KRIPKE_UNKNOWN_REFUSES",
        "pass": bool(ok),
        "result": {"prop": prop["verdict"], "world": world["verdict"],
                   "junk": junk["verdict"]},
    }











def generalisation_two_phase_fork() -> Dict[str, Any]:
    """汎化した命題は通る。ただし**仮定を後に当てる**順序が要る。

    古典例 `rev(l) = revacc(l, nil)` は帰納が通らず、汎化
    `app(rev(l), a) = revacc(l, a)` なら通る。だが最初はその汎化も
    落ちた — 原因は汎化ではなく**仮定の適用時期**だった(2026-08-19)。

    IH を最初から規則に混ぜると leftmost-innermost が内側で早く発火し、
    定義による整形(結合律)を妨げる。**①定義だけで正規形へ落とし、
    ②その後に IH を当てる**と閉じる。探索ではなく段の固定された順序。

    **正しい汎化を与えても、適用順が悪ければ閉じない** — 汎化の失敗と
    戦略の失敗は別物である。

    2点: (a) IH を混ぜた一段では閉じない (b) 二段階なら閉じる。
    """
    from .rewrite_kernel import RuleStore, simplify

    DEFS = [("rev_nil", "rev(nil)", "nil"),
            ("rev_cons", "rev(cons(?h, ?t))", "app(rev(?t), cons(?h, nil))"),
            ("acc_nil", "revacc(nil, ?a)", "?a"),
            ("acc_cons", "revacc(cons(?h, ?t), ?a)", "revacc(?t, cons(?h, ?a))"),
            ("app_nil", "app(nil, ?l)", "?l"),
            ("app_cons", "app(cons(?h, ?t), ?l)", "cons(?h, app(?t, ?l))"),
            ("app_assoc", "app(app(?x, ?y), ?z)", "app(?x, app(?y, ?z))")]
    IH = ("IH", "app(rev(?t), ?a)", "revacc(?t, ?a)")

    def nf(e, rules):
        rs = RuleStore()
        for n, l, r in rules:
            rs.add(n, l, r)
        r = simplify(e, rs, budget=400)
        return r.get("term") if str(r.get("verdict")) == "ANSWER" else None

    L = "app(rev(cons(h, t)), a)"
    R = "revacc(cons(h, t), a)"

    one = (nf(L, DEFS + [IH]), nf(R, DEFS + [IH]))
    one_closes = one[0] is not None and one[0] == one[1]

    p0, p1 = nf(L, DEFS), nf(R, DEFS)
    two = (nf(p0, DEFS + [IH]) if p0 else None,
           nf(p1, DEFS + [IH]) if p1 else None)
    two_closes = two[0] is not None and two[0] == two[1]

    ok = bool(two_closes and not one_closes)
    return {"experiment": "rewrite", "fork": "GENERALISATION_TWO_PHASE",
            "pass": ok,
            "result": {"one_phase_closes": bool(one_closes),
                       "two_phase_closes": bool(two_closes),
                       "one_phase": list(one), "two_phase": list(two)}}


def false_equation_canary_fork() -> Dict[str, Any]:
    """壊れた規則集合では、偽の等式が証明できてしまう — それを検知する。

    今日、駆動層が予算切れ同士を一致と読み、真の命題を空虚に「証明」した
    (報告した 8/8 は偽で本当は 5/8)。Lean は捕まえられない — 独立検査は
    主張の真偽を見るのであって導出の本物さは見ない。同じ**形**の穴は
    「規則集合が壊れて何でも等しくなる」場合にも開く。

    番犬は偽の等式が証明できないことを確かめる。**番犬自身を二度作り
    直した**(experiments/vacuity): 構成子だけの偽(`0 = s(0)`)では
    `add(?x,?y) → 0` を見逃し、閉じた項の偽(`add(s(0),0) = 0`)でも
    まだ見逃した — 正しい規則が先に発火して壊れた規則が**影に隠れる**
    からで、**変数を含む偽**(`add(x,y) = 0`)で初めて捕らえた。

    2点: (a) 健全な定義では偽が証明できない (b) 壊れた規則を混ぜると
    証明できてしまい、番犬が鳴く。
    """
    from .rewrite_kernel import RuleStore, simplify

    def nf(e, rules):
        rs = RuleStore()
        for n, l, r in rules:
            rs.add(n, l, r)
        r = simplify(e, rs, budget=200)
        return r.get("term") if str(r.get("verdict")) == "ANSWER" else None

    def provable(l, r, rules):
        a, b = nf(l, rules), nf(r, rules)
        return a is not None and b is not None and a == b

    DEFS = [("add_0", "add(?x, 0)", "?x"),
            ("add_s", "add(?x, s(?y))", "s(add(?x, ?y))")]
    FALSE = [("0", "s(0)"), ("add(s(0), 0)", "0"), ("add(x, y)", "0")]

    quiet = not any(provable(l, r, DEFS) for l, r in FALSE)
    broken = DEFS + [("BROKEN", "add(?x, ?y)", "0")]
    barks = [f"{l} = {r}" for l, r in FALSE if provable(l, r, broken)]

    ok = bool(quiet and barks)
    return {"experiment": "rewrite", "fork": "FALSE_EQUATION_CANARY",
            "pass": ok,
            "result": {"healthy_is_quiet": bool(quiet), "barks": barks}}


def terminating_is_not_confluent_fork() -> Dict[str, Any]:
    """停止することと、同じ形に落ちることは別である。

    ordered_rewrite で「a+b+c の12通りが単一の正規形に落ちる=正準化」と
    測り、私はそれを AC 一般の性質のように書いた。**それは固定具に限った
    話だった**(2026-08-19、訂正)。反例:

        A = s(add(k, add(x, mul(x, k))))
        B = s(add(mul(x, k), add(k, x)))       ← A の並べ替え

    可換律と結合律を**両方向き付けて**与えると、両者は停止する(ANSWER)が
    **別々の正規形**に落ちる。項順序による向き付けは**停止性**を与えるが、
    **合流性(AC正準性)は与えない**。

    実務上の帰結: 等式の同値判定を正規形の一致だけで行うと、AC変種を
    取りこぼす。比較の側に AC 正規化(平坦化+整列)が要る — これを足すと
    探索は 6/8 → 8/8 になった(experiments/search)。

    2点: (a) 両辺とも停止する (b) それでも正規形が異なる。
    """
    from .rewrite_kernel import RuleStore, simplify

    # 固定具は実際に発散した形をそのまま使う。**記法で結果が変わる**ため
    # 中置(`?a + ?b`)に書き換えると偶然一致してしまい、現象を再現しない —
    # `order_key` が `term_to_str` の印字に依存しているからで、これ自体が
    # 「印字に基づく順序は脆い」という所見である。
    rs = RuleStore()
    rs.add("add_comm", "add(?a, ?b)", "add(?b, ?a)")
    rs.add("add_assoc", "add(add(?a, ?b), ?c)", "add(?a, add(?b, ?c))")
    names = ["add_comm", "add_assoc"]

    A = "s(add(k, add(x, mul(x, k))))"
    B = "s(add(mul(x, k), add(k, x)))"
    ra = simplify(A, rs, oriented=names, budget=600)
    rb = simplify(B, rs, oriented=names, budget=600)

    both_stop = (str(ra.get("verdict")) == "ANSWER"
                 and str(rb.get("verdict")) == "ANSWER")
    differ = ra.get("term") != rb.get("term")

    ok = bool(both_stop and differ)
    return {"experiment": "rewrite", "fork": "TERMINATING_IS_NOT_CONFLUENT",
            "pass": ok,
            "result": {"both_terminate": bool(both_stop),
                       "normal_forms_differ": bool(differ),
                       "A": ra.get("term"), "B": rb.get("term")}}


def budget_is_not_agreement_fork() -> Dict[str, Any]:
    """予算切れは「一致」ではない — 空虚な証明を作らせない。

    2026-08-19、探索の駆動層に健全性の穴が見つかった。基底の検査を
    `if nf(lhs) != nf(rhs): continue` と書いていたため、**両側が予算切れ
    (None)のとき None != None が False になり、基底が閉じたことにされて
    いた**。可換律を無向きで規則に昇格して系が停止しなくなった後、3本の
    目標が**空虚に「証明」された**(報告した 8/8 は偽で、実際は 5/8)。

    **Lean はこれを捕まえられない** — 命題自体は真だからである。
    独立検査は「主張が真か」を見るのであって「導出が本物か」は見ない。
    真の命題を空虚に証明しても検査は通る。導出側の健全性は導出側で
    守るしかない。

    ここで固定するのは、この構造の一般規則である:
    **`simplify` が ANSWER 以外を返した項は、他の何とも一致しない。**
    """
    from .rewrite_kernel import RuleStore, simplify

    rs = RuleStore()
    rs.add("comm", "?a + ?b", "?b + ?a")      # 無向き = 停止しない

    left = simplify("x + y", rs, budget=50)
    right = simplify("y + x", rs, budget=50)

    both_budget = (str(left.get("verdict")) == "UNKNOWN_BUDGET"
                   and str(right.get("verdict")) == "UNKNOWN_BUDGET")

    # 誤った読み方: term どうしを比べると None 同士で「一致」しうる
    def bad_nf(r):
        return r.get("term") if str(r.get("verdict")) == "ANSWER" else None
    naive_says_equal = (bad_nf(left) == bad_nf(right))   # None == None

    # 正しい読み方: ANSWER でないものは一致に数えない
    def good_eq(a, b):
        ta, tb = bad_nf(a), bad_nf(b)
        return ta is not None and tb is not None and ta == tb
    strict_says_equal = good_eq(left, right)

    ok = bool(both_budget and naive_says_equal and not strict_says_equal)
    return {"experiment": "rewrite", "fork": "BUDGET_IS_NOT_AGREEMENT",
            "pass": ok,
            "result": {"both_exhausted": bool(both_budget),
                       "naive_comparison_says_equal": bool(naive_says_equal),
                       "strict_comparison_says_equal": bool(strict_says_equal)}}


def inductive_search_fork() -> Dict[str, Any]:
    """帰納する変数も補題の順序も、駆動層が自分で選べる。

    2026-08-19。「選ぶこと=探索で、そこは手つかず」と書いたが、測ると
    動いた(experiments/search)。定義4本だけ与え目標8本を順不同で渡すと、
    ヒント無しで **8/8** 証明し Lean が 8/8 VERIFIED にした
    (乗法の可換律を含む)。探索は決定論・乱数なし。

    途中で欠陥を1件発見している: 補題を規則に昇格するとき変数を一般化
    しておらず(`add(0, x) → x` の x が**定数**のまま `add(0, y)` に
    一致しない)、5/8 に留まっていた。補題は全称命題なので規則にする
    ときも全称のまま置く。直して 8/8・2巡→1巡。

    3点: (a) 帰納する変数を自分で選ぶ (b) 不動点が補題の順序を解く
    (c) **一般化しないと解けない**(欠陥の再発防止)。
    """
    from .rewrite_kernel import RuleStore, simplify

    DEFS = [("add_0", "add(?x, 0)", "?x"),
            ("add_s", "add(?x, s(?y))", "s(add(?x, ?y))")]

    def nf(e, rules):
        rs = RuleStore()
        for n, l, r in rules:
            rs.add(n, l, r)
        r = simplify(e, rs, budget=400)
        return r.get("term") if str(r.get("verdict")) == "ANSWER" else None

    def induct(lhs, rhs, var, rules):
        """基底と段。仮定は規則として加える。"""
        if nf(lhs.replace(var, "0"), rules) != nf(rhs.replace(var, "0"), rules):
            return False
        ih = [("IH", lhs.replace(var, "k").replace("x", "?x").replace("y", "?y"),
               rhs.replace(var, "k").replace("x", "?x").replace("y", "?y"))]
        return (nf(lhs.replace(var, "s(k)"), rules + ih)
                == nf(rhs.replace(var, "s(k)"), rules + ih))

    # (a)+(b): G1 を証明 → 一般化して規則に → G2 が解錠される
    g1 = induct("add(0, x)", "x", "x", DEFS)
    with_general = DEFS + [("G1", "add(0, ?a)", "?a")]
    with_literal = DEFS + [("G1", "add(0, x)", "x")]

    # (c) 一般化しないと補題が効かない
    general_works = nf("add(0, y)", with_general) == "y"
    literal_fails = nf("add(0, y)", with_literal) != "y"

    ok = bool(g1 and general_works and literal_fails)
    return {"experiment": "rewrite", "fork": "INDUCTIVE_SEARCH",
            "pass": ok,
            "result": {"proved_G1_by_induction": bool(g1),
                       "generalised_lemma_applies": bool(general_works),
                       "literal_lemma_does_not": bool(literal_fails)}}


def induction_by_rewriting_fork() -> Dict[str, Any]:
    """帰納法は、仮定を規則として置けば書き換えで実行できる。

    2026-08-19、私は「カーネルには目標の概念が無いので帰納法は越えられ
    ない」と書いた。**それは測定ではなく推論で、誤りだった**(操作者の
    指摘で検証)。目標も項であり、帰納法の仮定は規則である。

    薄い駆動層 — 基底は変数を 0 に、段は新しい定数 k にして**仮定を
    規則として加える** — と既存の書き換えだけで、加法の可換律を含む
    3命題が証明でき、Lean が 3/3 VERIFIED にした。探索も後戻りも無い。

    ここで固定するのは可換律(最も強い一本): 基底と段が両方閉じること、
    そして**仮定を入れなければ段が閉じないこと**(仮定が効いている証拠)。
    """
    from .rewrite_kernel import RuleStore, simplify

    def rs_base():
        rs = RuleStore()
        rs.add("add_0", "add(?x, 0)", "?x")
        rs.add("add_s", "add(?x, s(?y))", "s(add(?x, ?y))")
        rs.add("T1", "add(0, ?a)", "?a")
        rs.add("T2", "add(s(?a), ?b)", "s(add(?a, ?b))")
        return rs

    def nf(e, rs):
        r = simplify(e, rs, budget=300)
        return r.get("term") if str(r.get("verdict")) == "ANSWER" else None

    # 基底: y := 0
    rs = rs_base()
    base_ok = nf("add(x, 0)", rs) == nf("add(0, x)", rs)

    # 段: y := s(k)、仮定 add(x,k) -> add(k,x) を規則に加える
    rs2 = rs_base()
    rs2.add("IH", "add(x, k)", "add(k, x)")
    step_ok = nf("add(x, s(k))", rs2) == nf("add(s(k), x)", rs2)

    # 仮定を入れなければ段は閉じない(= 仮定が効いている)
    rs3 = rs_base()
    step_without_ih = nf("add(x, s(k))", rs3) == nf("add(s(k), x)", rs3)

    ok = bool(base_ok and step_ok and not step_without_ih)
    return {"experiment": "rewrite", "fork": "INDUCTION_BY_REWRITING",
            "pass": ok,
            "result": {"base": bool(base_ok), "step_with_ih": bool(step_ok),
                       "step_without_ih": bool(step_without_ih)}}


def completion_derives_laws_fork() -> Dict[str, Any]:
    """完備化は、公理に無い等式を導く — そしてそれは真である。

    群の公理3本(結合・左単位元・**左**逆元)から臨界対を計算して
    完備化すると、公理に無い `x * i(x) → e`(**右**逆元)と
    `i(i(x)) * z → x * z`(対合)が導かれる。実測 2026-08-19:
    12本導出、Lean が整数の加法として解釈して **12/12 VERIFIED**、偽0。

    これは帰納法ではない。**格納された規則の帰結を明示化する**操作で、
    根拠は全て格納済み — 閉包の内側。ただし導けるのは与えた公理の
    帰結だけで、`n + m = m + n` のように再帰的定義から帰納法でしか
    出ない等式は出ない。experiments/completion。

    2点: (a) 公理に無い等式が導かれる (b) 導かれた等式が真である
    (整数の加法として Lean が検査)。
    """
    import sys as _sys
    from pathlib import Path as _P

    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]
                            / "experiments" / "completion"))
    try:
        from run_completion import complete, to_int_expr
    except Exception as exc:      # 実験ファイルが無い配布形では報告して抜ける
        return {"experiment": "rewrite", "fork": "COMPLETION_DERIVES_LAWS",
                "skipped": "run_completion not importable: %s" % type(exc).__name__}
    from .lean_witness import lean_binary, verify
    from .rewrite_kernel import RuleStore

    if lean_binary() is None:
        return {"experiment": "rewrite", "fork": "COMPLETION_DERIVES_LAWS",
                "skipped": "no lean toolchain on this machine"}

    rs = RuleStore()
    rs.add("assoc", "(?x * ?y) * ?z", "?x * (?y * ?z)")
    rs.add("unit", "e * ?x", "?x")
    rs.add("inv", "i(?x) * ?x", "e")
    added, log, _done = complete(rs, max_rules=8, rounds=8)

    derived = added > 0
    ver = 0
    for e in log:
        lhs = to_int_expr(e["lhs"]).replace("?", "")
        rhs = to_int_expr(e["rhs"]).replace("?", "")
        v = verify("theorem t (x y z : Int) : %s = %s := by omega"
                   % (lhs, rhs))
        if str(v.get("verdict")) == "VERIFIED":
            ver += 1
    sound = (ver == added)
    ok = bool(derived and sound)
    return {"experiment": "rewrite", "fork": "COMPLETION_DERIVES_LAWS",
            "pass": ok,
            "result": {"derived": added, "lean_verified": ver,
                       "laws": [e["lhs"] + " -> " + e["rhs"] for e in log[:4]]}}


def ordered_rewrite_fork() -> Dict[str, Any]:
    """対称規則は、向きを付ければ止まり、置換を同一視する。

    可換律 `?a + ?b → ?b + ?a` を無向きで足すと a+b→b+a→a+b と往復し、
    正規形到達が 60/60 → 19/60 に崩れる(実測 2026-08-19、健全性は保持)。
    結果が項順序で真に小さくなる時だけ適用すると 60/60 に戻り、さらに
    `a+b+c` の12通り(順列×括弧付け)が**単一の正規形**に落ちる。

    探索ではない — 適用可否を決定論的な述語で決めるだけで、後戻りも
    分岐の試行もしない。格納された規則を格納された順序で適用する。

    3点: (a) 無向きは予算切れ (b) 向き付きは正規形に至る
    (c) 置換が同一視される(正準化)。
    """
    import itertools

    from .rewrite_kernel import default_algebra_rules, simplify

    # 正準化には可換だけでなく**結合の並べ替え**も要る。可換律だけだと
    # (a+b)+c と a+(b+c) は別の項のままで、12通りは3形に留まる(実測)。
    # 実測(experiments/ordered_rewrite)と同じ規則集合で固定する。
    SYM = [("add_comm", "?a + ?b", "?b + ?a"),
           ("add_assoc_l", "(?a + ?b) + ?c", "?a + (?b + ?c)")]
    rs = default_algebra_rules()
    for n, l, r in SYM:
        rs.add(n, l, r)
    names = [n for n, _l, _r in SYM]

    loops = simplify("(b + a)", rs)
    stops = simplify("(b + a)", rs, oriented=names)

    forms = set()
    for p_ in itertools.permutations(["a", "b", "c"]):
        for shape in ("(%s + (%s + %s))", "((%s + %s) + %s)"):
            r = simplify(shape % p_, rs, oriented=names)
            forms.add(r.get("term") if str(r.get("verdict")) == "ANSWER"
                      else "BUDGET")

    ok = (str(loops.get("verdict")) == "UNKNOWN_BUDGET"
          and str(stops.get("verdict")) == "ANSWER"
          and len(forms) == 1 and "BUDGET" not in forms)
    return {"experiment": "rewrite", "fork": "ORDERED_REWRITE_CANONICAL",
            "pass": bool(ok),
            "result": {"unoriented": loops.get("verdict"),
                       "oriented": stops.get("term"),
                       "permutation_forms": sorted(forms)}}


def rewrite_roundtrip_fork() -> Dict[str, Any]:
    """印字した項は、読み直すと同じ項である。

    `term_to_str` は右側の複合項に、演算子が - か * のときだけ括弧を
    付けていた。そのため `a + (b + c)` が `a + b + c` と印字され、
    読み直すと `(a + b) + c` — **別の項**になる(2026-08-19実測、往復
    2/8 で破綻)。Int では両方とも真の等式になるので実害は出ていなかったが、
    印字は項の表現であって「たまたま同値な別の項」ではない。非結合的な
    演算子を載せた瞬間に嘘になる。

    そしてこの欠陥は実際に**測定を誤らせた**: 帰納法の壁の実験で、
    印字文字列を比べたために加法の結合律が「導出された」ように見えた
    (カーネルは内部では正しく区別していた)。

    往復性は表現の最低条件なので、ここで固定する。
    """
    from .rewrite_kernel import parse_term, term_to_str

    cases = ["(a + (b + c))", "((a + b) + c)", "(a - (b - c))",
             "((a - b) - c)", "(a * (b + c))", "((a * b) + c)",
             "(a - (b + c))", "(a + (b - c))", "(a * (b * c))",
             "((a + b) * c)", "(1 + (2 * 3))", "((a + 0) - (b - c))"]
    broken = []
    for src in cases:
        t = parse_term(src)
        if t is None:
            broken.append((src, "unparsed"))
            continue
        again = parse_term(term_to_str(t))
        if again != t:
            broken.append((src, term_to_str(t)))
    ok = not broken
    return {"experiment": "rewrite", "fork": "REWRITE_PRINT_ROUNDTRIP",
            "pass": ok,
            "result": {"cases": len(cases), "broken": len(broken),
                       "examples": broken[:3]}}


def rewrite_algebra_fork() -> Dict[str, Any]:
    """代数規則セット + wire 定数畳み込み (トレース付き正規形)."""
    a = simplify("x + 0")
    b = simplify("(2 + 3) * y")
    c = simplify("(1 * x) + (y * 0)")
    d = simplify("x - x")
    ok = (
        a["term"] == "x"
        and b["term"] == "5 * y"
        and any(s["rule"] == "wire_add" for s in b["steps"])
        and c["term"] == "x"
        and d["term"] == "0"
        and all(r["verdict"] == "ANSWER" for r in (a, b, c, d))
    )
    return {
        "experiment": "rewrite",
        "fork": "REWRITE_ALGEBRA",
        "pass": bool(ok),
        "result": {"a": a["term"], "b": b["term"], "c": c["term"],
                   "b_rules": [s["rule"] for s in b["steps"]]},
    }


def rewrite_logic_fork() -> Dict[str, Any]:
    """論理は同カーネルの規則セット違い."""
    r = simplify("lnot(lnot(land(true, p)))", default_logic_rules())
    r2 = simplify("lor(false, lor(q, true))", default_logic_rules())
    ok = r["term"] == "p" and r2["term"] == "true"
    return {
        "experiment": "rewrite",
        "fork": "REWRITE_LOGIC_SET",
        "pass": bool(ok),
        "result": {"double_neg": r["term"], "or_true": r2["term"]},
    }


def rewrite_rules_are_data_fork() -> Dict[str, Any]:
    """規則は十字に pour → 復元しても同じ挙動。実行時の規則追加で挙動が変わる."""
    cs = CrossStore()
    default_algebra_rules().pour_into(cs)
    poured = RuleStore.from_cross_store(cs)
    same = simplify("x + 0", poured)["term"] == "x"

    ext = default_algebra_rules()
    before = simplify("y * 2", ext)["term"]
    ext.add("mul_two", "?a * 2", "?a + ?a")
    after = simplify("y * 2", ext)["term"]
    ok = same and before == "y * 2" and after == "y + y"
    return {
        "experiment": "rewrite",
        "fork": "REWRITE_RULES_ARE_DATA",
        "pass": bool(ok),
        "result": {"poured_rules": len(poured.rules), "before": before,
                   "after": after},
    }


def rewrite_permission_fork() -> Dict[str, Any]:
    """H と同型の許可: 許可されない規則は発火しない (正規形が変わる)."""
    blocked = simplify("x + 0", allowed=["mul_one_r"])
    allowed = simplify("x + 0", allowed=["add_zero_r"])
    ok = blocked["term"] == "x + 0" and allowed["term"] == "x"
    return {
        "experiment": "rewrite",
        "fork": "REWRITE_PERMISSION_H",
        "pass": bool(ok),
        "result": {"blocked": blocked["term"], "allowed": allowed["term"]},
    }


def all_kripke_rewrite_forks() -> List[Dict[str, Any]]:
    return [
        kripke_model_check_fork(),
        kripke_validity_fork(),
        kripke_unknown_refuses_fork(),
        rewrite_algebra_fork(),
        rewrite_roundtrip_fork(),
        ordered_rewrite_fork(),
        completion_derives_laws_fork(),
        induction_by_rewriting_fork(),
        inductive_search_fork(),
        budget_is_not_agreement_fork(),
        terminating_is_not_confluent_fork(),
        false_equation_canary_fork(),
        generalisation_two_phase_fork(),
        rewrite_logic_fork(),
        rewrite_rules_are_data_fork(),
        rewrite_permission_fork(),
    ]
