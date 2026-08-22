"""自分のハーネスを自分で測る — 作業ログ→ハーネス項→単一変更の変分。

構想「行動の蓄積で覚えて発明する」の完結点。実在の行動ログと安い審判の
両方が要るが、LLM の作業ログは審判が高く騒がしい。証明器**自身**の
作業ログなら:

    実在する        proof_ledger の how / trials(構成した治具ではない)
    審判が無料      Lean + 目標集合
    把手が本物      波の幅・深さ・予算・手渡し在庫・エネルギー

procedure_vary の規律をそのまま持ち込む: **単一変更のみ**。二つ変えて
失敗したら結果は原因を名指さない(解釈できない測定は失敗より悪い)。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

#: 作業ログ(how)→ ハーネス項。**閉じた表**。読めない how は未写像で
#: 数え、腕を推測しない(未タグは一級市民、の系譜)。
_LIFT = [
    (re.compile(r"^ledger$"), "hact(0)"),
    (re.compile(r"^direct$"), "hact(0)"),
    (re.compile(r"^direct\+cond"), "hseq(hact(0), hact(4))"),
    (re.compile(r"^mathlib_context$"), "hact(5)"),
    (re.compile(r"^induction on \w+ \+ cond$"),
     "hseq(hseq(hact(1), hact(2)), hact(4))"),
    (re.compile(r"^induction on \w+ \+ .+$"),
     "hseq(hseq(hact(1), hact(2)), hact(3))"),
    (re.compile(r"^induction on \w+$"), "hseq(hact(1), hact(2))"),
]

#: 原子行為の読み(台帳の読者のため — 番号だけでは何も言っていない)
ACTS = {0: "直接検査", 1: "基底", 2: "段", 3: "発明した補題の適用",
        4: "条件の放電", 5: "手渡し在庫の参照"}


def lift(how: str) -> Optional[str]:
    """作業ログの一行をハーネス項へ。写せなければ None(推測しない)。"""
    h = (how or "").strip()
    for rx, term in _LIFT:
        if rx.match(h):
            return term
    return None


def lift_all(hows: List[str]) -> Dict[str, Any]:
    """写った項の分布と、未写像の内訳。"""
    terms: Dict[str, int] = {}
    unmapped: Dict[str, int] = {}
    for h in hows:
        t = lift(h)
        if t is None:
            unmapped[h] = unmapped.get(h, 0) + 1
        else:
            terms[t] = terms.get(t, 0) + 1
    return {"terms": terms, "unmapped": unmapped,
            "n_lifted": sum(terms.values()),
            "n_unmapped": sum(unmapped.values())}


#: 実在する把手だけ。既定値は現在の器の設定。
DEFAULT_KNOBS: Dict[str, Any] = {
    "wave": 6,                 # 1つの詰まりで試す候補数(十字の腕数)
    "max_depth": 3,            # 補題の再帰証明の深さ
    "invention_budget": 4000,  # 接地検査の予算
    "handoff": True,           # mathlib/core 断片の手渡し
    "energy": True,            # エネルギーによる試行順
}


def variations(parent: Optional[Dict[str, Any]] = None
               ) -> List[Dict[str, Any]]:
    """親から**単一変更**の変分だけを列挙(決定論)。

    それぞれ「この変分の成功が何を立証するか」を持つ — procedure_vary が
    「各変分は自分の成功が何を establish するかを述べる」としたのと同じ。
    """
    p = dict(parent or DEFAULT_KNOBS)
    out: List[Dict[str, Any]] = []

    def add(name: str, key: str, value: Any, establishes: str) -> None:
        k = dict(p)
        k[key] = value
        out.append({"name": name, "knobs": k, "changed": key,
                    "from": p[key], "to": value,
                    "establishes": establishes})

    add("wave1", "wave", 1,
        "十字の腕を1本に絞っても足りる(=6本は過剰)")
    add("wave12", "wave", 12,
        "腕を増やすと届く詰まりがある(=6本は不足)")
    add("depth2", "max_depth", 2, "補題の再帰は2段で足りる")
    add("depth4", "max_depth", 4, "3段では届かない補題の梯子がある")
    add("budget500", "invention_budget", 500,
        "発明の予算を絞っても証明数が落ちない")
    add("no_handoff", "handoff", False,
        "手渡し在庫が無くても証明数が落ちない(=参照は効いていない)")
    add("no_energy", "energy", False,
        "エネルギーの順序づけは証明数に効いていない")
    return out


def apply_knobs(prover: Any, knobs: Dict[str, Any]) -> None:
    """把手を1つの Prover に適用する(器の側は変更しない)。"""
    prover.wave = knobs.get("wave", DEFAULT_KNOBS["wave"])
    prover.max_depth = knobs.get("max_depth", DEFAULT_KNOBS["max_depth"])
    prover.invention_budget = knobs.get("invention_budget",
                                        DEFAULT_KNOBS["invention_budget"])
    if not knobs.get("handoff", True):
        prover.ml_rules, prover.ml_oriented = [], []


def classify(delta: int, line: int = 2) -> str:
    """採択 / 棄権 / 害。±(line-1) 以内は棄権 — ノイズから勝者を選ばない。"""
    if delta >= line:
        return "adopted"
    if delta <= -line:
        return "harmful"
    return "abstain"
