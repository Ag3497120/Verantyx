# -*- coding: utf-8 -*-
"""縫う順序。**「人が縫えるか」への、コーパスを要らない答え。**

型紙が正しくても、縫える順序が無ければ服にならない。既に閉じた筒の内側の
縫い目には針が入らないので、実際の縫製には順序があり、**その順序が存在する
かどうかは計算できる**。

    人が縫える  ⟸  妥当な縫製順序が存在する（＋局所の幾何が成立する）

順序が見つかれば、それが**構成可能性の証明であると同時に縫製指示書**になる。

**平ら(FLAT)と輪(IN_THE_ROUND)。** 縫う時点で両側がまだ別の塊なら、布は
平らに開いたまま縫える。既に同じ塊なら、その一本は輪を閉じる。

**輪で縫う本数には下限がある。** 頂点=裁片・辺=縫い目のグラフで、全域森を
張る辺は必ず平らに縫えて、残りは必ず輪になる::

    β = 辺 − 頂点 + 連結成分

これは**順序の選び方によらない**。参照コートなら 5 − 3 + 1 = 3 本。「輪が
3本ある」は服の性質であって、下手な順序のせいではない。**だから 3 本より
多く輪にする順序は下手で、それは検出できる。**

**言えないこと。** ここが持っているのは裁片と縫い目の繋がりだけで、どちらが
内側か、開きがどこにあるか、立体としてどう配置されるかは持っていない。だから
「この縫い目には物理的に手が入らない」は**一般には言えない**。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

FLAT = "FLAT"
ROUND = "IN_THE_ROUND"

NO_ORDER = "UNKNOWN_NO_SEWING_ORDER"
NO_SEAMS = "UNKNOWN_NO_SEAMS"
BAD_SEAM = "UNKNOWN_SEAM_NAMES_NO_PIECES"


def _sides(label: str) -> Optional[Tuple[str, str]]:
    """``前身頃/肩線 ↔ 後身頃/肩線`` から裁片の対を取る。"""
    if "↔" not in label:
        return None
    a, _, b = label.partition("↔")

    def piece(s: str) -> str:
        s = s.strip()
        return s.split("/", 1)[0].strip() if "/" in s else s

    pa, pb = piece(a), piece(b)
    return (pa, pb) if pa and pb else None


class _Union:
    def __init__(self) -> None:
        self.up: Dict[str, str] = {}

    def find(self, x: str) -> str:
        self.up.setdefault(x, x)
        while self.up[x] != x:
            self.up[x] = self.up[self.up[x]]
            x = self.up[x]
        return x

    def join(self, a: str, b: str) -> bool:
        """繋いだら True、既に同じ塊なら False（＝この一本が輪を閉じる）。"""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.up[ra] = rb
        return True


def plan(built: Dict[str, Any]) -> Dict[str, Any]:
    """縫う順序を出す。**平らに縫える分を先に、輪は後に。**

    ``built`` は ``garment_sew.build`` の返り値。
    """
    if built.get("verdict") not in (None, "ANSWER"):
        return {"verdict": built.get("verdict"),
                "note": "順序は縫い目が引けてから"}
    seams = built.get("seams") or []
    if not seams:
        return {"verdict": NO_SEAMS,
                "how_to_close": "縫い目が一本もありません"}

    rows: List[Dict[str, Any]] = []
    bad: List[str] = []
    for s in seams:
        label = s.get("seam") or "?"
        pair = _sides(label)
        if pair is None:
            bad.append(label)
            continue
        rows.append({"seam": label, "a": pair[0], "b": pair[1],
                     "length_cm": s.get("length_a")})
    if bad:
        return {"verdict": BAD_SEAM, "seams": bad,
                "how_to_close": ("縫い目の名前から裁片が読めません。"
                                 "『裁片/辺 ↔ 裁片/辺』の形が要ります")}

    pieces = sorted({r["a"] for r in rows} | {r["b"] for r in rows})

    # **平らに縫えるものを先に。** 貪欲で足りる — 全域森を張る辺を先に取れば
    # 平らな本数は最大(頂点 − 成分数)になり、輪は必ず β 本になる。順序を
    # 工夫してこれ以上減らすことはできない。
    u = _Union()
    for p in pieces:
        u.find(p)
    order: List[Dict[str, Any]] = []
    later: List[Dict[str, Any]] = []
    for r in rows:
        if u.join(r["a"], r["b"]):
            order.append(dict(r, how=FLAT,
                              why="両側がまだ別の塊なので、平らに開いて縫える"))
        else:
            later.append(r)
    for r in later:
        order.append(dict(r, how=ROUND,
                          why="両側は既に繋がっている。この一本は輪を閉じる"))

    comps = len({u.find(p) for p in pieces})
    beta = len(rows) - len(pieces) + comps
    rounds = sum(1 for o in order if o["how"] == ROUND)
    for i, o in enumerate(order, 1):
        o["step"] = i

    return {
        "verdict": "ANSWER",
        "order": order,
        "steps": len(order),
        "pieces": pieces,
        "flat": len(order) - rounds,
        "in_the_round": rounds,
        # **下限は順序に依らない。** 達していれば、これ以上平らにはできない。
        "in_the_round_minimum": beta,
        "at_the_minimum": rounds == beta,
        "components": comps,
        "formula": "β = 縫い目 − 裁片 + 連結成分 "
                   f"= {len(rows)} − {len(pieces)} + {comps} = {beta}",
        "constructible": True,
        "what_this_does_not_say": (
            "順序が在ることは示しましたが、**針が物理的に届くかは別**です。"
            "ここが持っているのは裁片と縫い目の繋がりだけで、どちらが内側か、"
            "開きがどこにあるか、立体としてどう置かれるかを持っていません。"
            "「輪になる／ならない」までが言えることの端です"),
        "not_a_published_system": (
            "工業の縫製仕様書に準拠していません"),
    }
