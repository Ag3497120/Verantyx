# -*- coding: utf-8 -*-
"""ハーネス項のインタプリタ — 構造則が**構成で**真になるように書く。

wire_add の線(「学習した数学ではなく構成上正確な計算」): A1..A5 は
測って当てるものではなく、この実行器の作りが保証する。保証していない
等式(交換則など)は接地検査に裁かせ、反例が無くても昇格しない。

観測 = (成功, 消費した試行数, 出力)。等式の意味は「全ての接地割り当て
と入力で観測が一致」。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx.prover import parse_term, term_to_str


def _nat(t: Any) -> int:
    """予算項を整数へ。演算(mul/min/add/max/monus)は N 側の意味で評価
    — 予算代数は数学側の署名をそのまま使う(A2/A3 の右辺)。"""
    if isinstance(t, int):
        return t
    if t == "0":
        return 0
    if isinstance(t, tuple):
        if t[0] == "s":
            return 1 + _nat(t[1])
        if t[0] == "add":
            return _nat(t[1]) + _nat(t[2])
        if t[0] == "mul":
            return _nat(t[1]) * _nat(t[2])
        if t[0] == "min":
            return min(_nat(t[1]), _nat(t[2]))
        if t[0] == "max":
            return max(_nat(t[1]), _nat(t[2]))
        if t[0] == "monus":
            return max(0, _nat(t[1]) - _nat(t[2]))
    raise ValueError(f"not a numeral: {t!r}")


class Model:
    """決定論のモック。attempt(action, input, state) -> (成功, 出力)。

    状態(行為ごとの実行回数)は実行系列に沿って糸を通す — hretry の
    入れ子が「同じ実行系列」になるのは、この糸のおかげ(A2 の構成保証)。
    """

    name = "base"

    def attempt(self, action: int, text: str,
                counts: Dict[int, int]) -> Tuple[bool, str]:
        raise NotImplementedError


class MockA(Model):
    """不安定型: 各行為の最初の1回は必ず失敗、2回目から成功。"""

    name = "mockA"

    def attempt(self, action, text, counts):
        counts[action] = counts.get(action, 0) + 1
        if counts[action] == 1:
            return False, ""
        return True, f"o{action}({text})"


class MockB(Model):
    """長文弱者型: 入力が長さ6を超えると必ず失敗。再試行は救えない。"""

    name = "mockB"

    def attempt(self, action, text, counts):
        counts[action] = counts.get(action, 0) + 1
        if len(text) > 6:
            return False, ""
        return True, f"o{action}({text})"


def run(term: Any, text: str, model: Model,
        counts: Optional[Dict[int, int]] = None) -> Tuple[bool, int, str]:
    """(成功, 試行数, 出力)。構造則を構成で保証する実行。"""
    counts = counts if counts is not None else {}
    if isinstance(term, str):
        term = parse_term(term)
    op = term[0] if isinstance(term, tuple) else term
    if op == "hact":
        ok, out = model.attempt(_nat(term[1]), text, counts)
        return ok, 1, out
    if op == "hseq":
        ok1, n1, out1 = run(term[1], text, model, counts)
        if not ok1:
            return False, n1, ""
        ok2, n2, out2 = run(term[2], out1, model, counts)
        return ok2, n1 + n2, out2
    if op == "hretry":
        budget = _nat(term[2])
        total = 0
        for _ in range(max(1, budget)):
            ok, n, out = run(term[1], text, model, counts)
            total += n
            if ok:
                return True, total, out
        return False, total, ""
    if op == "htrunc":
        cap = _nat(term[2])
        return run(term[1], text[:cap], model, counts)
    if op == "hjudge":
        ok, n, out = run(term[1], text, model, counts)
        if ok and not out:          # 検証: 空出力は不合格
            return False, n, ""
        return ok, n, out
    raise ValueError(f"unknown harness op: {op!r}")


# ---------------------------------------------------------------------------
# 接地検査 — 等式の審判
# ---------------------------------------------------------------------------
def _nat_term(n: int) -> Any:
    t: Any = "0"
    for _ in range(n):
        t = ("s", t)
    return t


def ground_harnesses(max_depth: int = 2) -> List[Any]:
    """小さい接地ハーネス項の列挙(決定論順)。"""
    atoms: List[Any] = [("hact", _nat_term(0)), ("hact", _nat_term(1))]
    budgets = [_nat_term(1), _nat_term(2), _nat_term(3)]
    caps = [_nat_term(0), _nat_term(4), _nat_term(6), _nat_term(8)]
    level = list(atoms)
    all_terms = list(atoms)
    for _ in range(max_depth):
        nxt: List[Any] = []
        for f in level:
            for b in budgets[1:]:
                nxt.append(("hretry", f, b))
            for c in caps:
                nxt.append(("htrunc", f, c))
            nxt.append(("hjudge", f))
            for g in atoms:
                nxt.append(("hseq", f, g))
        seen = {term_to_str(t) for t in all_terms}
        nxt = [t for t in nxt if term_to_str(t) not in seen][:80]
        all_terms += nxt
        level = nxt
    return all_terms


INPUTS = ["", "xx", "xxxx", "xxxxxx", "xxxxxxxx", "xxxxxxxxxx"]


def observe(term: Any, model_cls) -> Tuple:
    """全入力での観測列(モデル状態は入力ごとに新品)。"""
    return tuple(run(term, s, model_cls()) for s in INPUTS)


def check_law(lhs_pat: str, rhs_pat: str, *, models=(MockA, MockB),
              max_assign: int = 400) -> Dict[str, Any]:
    """H変数 f,g,h と N変数 a,b への接地割り当てを列挙して観測を比較。

    返り値: PASSED(検査数) / REFUTED(割り当て・入力・両観測)。
    """
    import itertools

    from verantyx.prover import t_subst

    tl, tr = parse_term(lhs_pat), parse_term(rhs_pat)
    hs = ground_harnesses(1)[:8]
    ns = [_nat_term(1), _nat_term(2), _nat_term(3)]
    import re as _re

    def _has(v: str) -> bool:
        # 単語境界つき — "h" が "hseq" に部分一致しないように
        pat = r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % v
        return bool(_re.search(pat, lhs_pat) or _re.search(pat, rhs_pat))

    vs: List[str] = [v for v in ("f", "g", "h") if _has(v)]
    nvs = [v for v in ("a", "b") if _has(v)]
    passed = 0
    combos = itertools.product(*([hs] * len(vs) + [ns] * len(nvs)))
    for combo in itertools.islice(combos, max_assign):
        env = dict(zip(vs + nvs, combo))
        l = t_subst(tl, env)
        r = t_subst(tr, env)
        for model in models:
            ol, orr = observe(l, model), observe(r, model)
            if ol != orr:
                bad = next(i for i in range(len(INPUTS)) if ol[i] != orr[i])
                return {"verdict": "REFUTED", "passed": passed,
                        "model": model.name,
                        "assignment": {k: term_to_str(v)
                                       for k, v in env.items()},
                        "input": INPUTS[bad],
                        "lhs_obs": ol[bad], "rhs_obs": orr[bad]}
            passed += 1
    return {"verdict": "PASSED", "passed": passed}
