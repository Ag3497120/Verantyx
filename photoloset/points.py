# -*- coding: utf-8 -*-
"""型紙の点に、**改訂をまたいで動かない番号**を振る。

「30番から35番をもう少しゆとりを」が成り立つには、35番が次の周回でも
同じ場所でなければならない。番号が動けば指示の意味が変わり、**エージェント
ループは原理的に収束しない** — 直す前と直した後で違う場所を指すから。

だから番号は**並び順から採らない**。住所から導く::

    番号 = 辺の基底 + round(t * (STRIDE - 1))

``t`` は辺に沿った 0..1 の位置で、これは発明ではない — ``garment_marks``
のノッチが既に ``{"edge": "袖ぐり", "t": 0.361, "role": "肩点"}`` の形で
同じ住所を使っている。ここはそれを型紙全体に広げるだけ。

**辺の基底は追記専用の登録簿から来る。** 現在の型紙の辺を数えて割り当てる
と、辺が1本増えた瞬間に後続の基底が全部ずれ、既存の番号が別の場所を指す。
それはこの模組が防ぐためだけに存在する故障そのもの。登録簿は
``Registry.of`` で辺を**見つけたら足す**が、**一度振った基底は二度と
動かさない**。

**番号は位置を指すのであって、点を指すのではない。** 一つの番号は辺の
1/STRIDE の区間に対応する。裁片の頂点も、ノッチも、ユーザーが後から足した
指示も、同じ番号空間に落ちる。だから「35番」は「35番の点」ではなく
「35番の場所」で、そこに何が居るかは別の問い。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: 1辺あたりの番号数。辺の長さの 1/100 の位置まで指せる。92cm の脇線なら
#: 約 0.92cm 刻み。**細かさはここだけで決まる**ので、上げるときは
#: 既存の番号が動かないことを ``renumber_check`` で測ってから上げる。
STRIDE = 100

NO_NUMBER = "UNKNOWN_NO_SUCH_NUMBER"
NOT_REGISTERED = "UNKNOWN_EDGE_NOT_REGISTERED"
BAD_T = "UNKNOWN_T_OUT_OF_RANGE"
MOVED = "UNKNOWN_NUMBERING_MOVED"
RESHAPED = "UNKNOWN_OUTLINE_RESHAPED"


class Registry:
    """裁片と辺に基底番号を配る。**追記専用。**

    ``of`` は知らない辺を見つけたら末尾に足す。**既に振った基底は、辺が
    増えても、裁片が増えても、順序が変わっても、二度と動かない** — これが
    この模組の存在理由で、``renumber_check`` が測るのもそこ。
    """

    def __init__(self, bases: Optional[Dict[str, int]] = None,
                 shape: Optional[Dict[str, int]] = None) -> None:
        #: "裁片/辺" -> 基底。挿入順が採番順で、dict は 3.7+ で順序を保つ。
        self._bases: Dict[str, int] = dict(bases or {})
        #: 裁片 -> 輪郭の頂点数。**辺の名前 ``eN`` は頂点順から作るので、
        #: 頂点が1つ挿入されると ``e1`` は別の線分になる。基底は動かない
        #: ので ``renumber_check`` は「異常なし」と答え、番号は動いていない
        #: のに場所が変わる。** 実測でそうなることを確かめた上で、ここに
        #: 頂点数を覚えさせて ``label`` が断るようにしてある。
        self._shape: Dict[str, int] = dict(shape or {})
        self._next = (max(self._bases.values()) + STRIDE
                      if self._bases else 0)

    @staticmethod
    def key(piece: str, edge: str) -> str:
        return f"{piece}/{edge}"

    def of(self, piece: str, edge: str) -> int:
        """基底を返す。知らない辺なら**足してから**返す。"""
        k = self.key(piece, edge)
        if k not in self._bases:
            self._bases[k] = self._next
            self._next += STRIDE
        return self._bases[k]

    def known(self, piece: str, edge: str) -> bool:
        return self.key(piece, edge) in self._bases

    def edges(self) -> List[str]:
        return list(self._bases)

    def to_json(self) -> Dict[str, Any]:
        return {"stride": STRIDE, "bases": dict(self._bases),
                "shape": dict(self._shape)}

    @classmethod
    def from_json(cls, o: Dict[str, Any]) -> "Registry":
        """保存した登録簿を読む。**STRIDE が変わっていたら断る** — 同じ
        基底でも刻みが違えば番号は別の場所を指す。黙って読むと、保存した
        ときの「35番」と今の「35番」が違う場所になる。
        """
        if int(o.get("stride", STRIDE)) != STRIDE:
            raise ValueError(
                f"{MOVED}: saved stride {o.get('stride')} != {STRIDE}. "
                "Every number saved under the old stride points somewhere "
                "else now. Re-register, or put STRIDE back.")
        return cls(o.get("bases") or {}, o.get("shape") or {})


def number(reg: Registry, piece: str, edge: str, t: float) -> int:
    """住所 → 番号。**同じ住所は常に同じ番号**（登録簿が同じなら）。"""
    if not (0.0 <= t <= 1.0):
        raise ValueError(f"{BAD_T}: t={t} outside 0..1 on {piece}/{edge}")
    return reg.of(piece, edge) + int(round(t * (STRIDE - 1)))


def resolve(reg: Registry, n: int) -> Dict[str, Any]:
    """番号 → 住所。知らない番号は**型付きで断る**。

    返すのは点ではなく**区間**。一つの番号は辺の 1/STRIDE を覆うので、
    そこに頂点があるとは限らない。「35番に点がある」と「35番の場所」は
    別の主張で、後者しか言えない。
    """
    for k, base in reg._bases.items():
        if base <= n < base + STRIDE:
            slot = n - base
            piece, _, edge = k.partition("/")
            lo = slot / (STRIDE - 1)
            hi = (slot + 1) / (STRIDE - 1)
            return {"verdict": "ANSWER", "piece": piece, "edge": edge,
                    "t": lo, "t_lo": lo, "t_hi": min(hi, 1.0),
                    "number": n,
                    "covers": f"{100.0 / (STRIDE - 1):.2f}% of {k}"}
    return {"verdict": NO_NUMBER, "number": n,
            "how_to_close": ("番号は登録済みの辺の基底から STRIDE 個ずつ。"
                             f"登録済み: {len(reg._bases)} 辺 "
                             f"({reg._next} まで)。register the edge first."),
            "registered": reg.edges()}


def span(reg: Registry, lo: int, hi: int) -> Dict[str, Any]:
    """「30番から35番」を住所の範囲にする。

    **辺をまたぐ範囲は断る。** 30 と 35 が別の辺なら、その間の番号は
    どちらの辺にも属さない場所を含みうるし、「そこをゆるめる」が何を
    意味するか誰も言えない。
    """
    if lo > hi:
        lo, hi = hi, lo
    a, b = resolve(reg, lo), resolve(reg, hi)
    for r in (a, b):
        if r["verdict"] != "ANSWER":
            return r
    if (a["piece"], a["edge"]) != (b["piece"], b["edge"]):
        return {"verdict": "UNKNOWN_SPAN_CROSSES_EDGES",
                "from": a, "to": b,
                "how_to_close": ("一つの辺の中で指してください。"
                                 f"{lo} は {a['piece']}/{a['edge']}、"
                                 f"{hi} は {b['piece']}/{b['edge']} です")}
    return {"verdict": "ANSWER", "piece": a["piece"], "edge": a["edge"],
            "t_lo": a["t_lo"], "t_hi": b["t_hi"],
            "from": lo, "to": hi, "numbers": list(range(lo, hi + 1))}


def _edges_of(piece: Dict[str, Any]) -> List[Tuple[str, int, int]]:
    """裁片の輪郭を辺に割る。**閉じた多角形として最後の点から先頭へ戻る。**

    辺の名前は輪郭の頂点番号から作る（``e0``, ``e1``, ...）。``draft`` が
    辺に名前を持っていればそちらが優先されるべきだが、今の ``pieces`` は
    ``outline`` しか持たないので、**持っていないものを持っているふりは
    しない**。名前が付いたらここが読み替わる。
    """
    out = piece.get("outline") or []
    n = len(out)
    if n < 2:
        return []
    return [(f"e{i}", i, (i + 1) % n) for i in range(n)]


def label(draft: Dict[str, Any], reg: Optional[Registry] = None
          ) -> Dict[str, Any]:
    """型紙の全裁片に番号を振る。**元の draft は変えない。**

    返すのは ``{"verdict", "registry", "pieces": [{name, edges: [...]}]}``。
    各辺は基底と、頂点が乗る番号を持つ。
    """
    reg = Registry() if reg is None else reg
    if draft.get("verdict") != "OK" and "pieces" not in draft:
        return {"verdict": draft.get("verdict", "UNKNOWN_NO_PIECES"),
                "how_to_close": draft.get("how_to_close", ""),
                "note": "番号は型紙が引けてから振る"}
    # **辺の同一性を先に確かめる。** ``eN`` は輪郭の頂点順から作る名前
    # なので、頂点が1つ増減した裁片では同じ名前が別の線分を指す。基底は
    # 動かないから ``renumber_check`` は通る — 通りながら壊れている。
    # 実測: 後身頃の輪郭に1点挿入すると、100/150/250/300 は同じ辺名を
    # 返し続けたが、その辺が結ぶ頂点は変わっていた。
    reshaped = [{"piece": (p.get("name") or "?"),
                 "was": reg._shape.get(p.get("name") or "?"),
                 "now": len(p.get("outline") or [])}
                for p in (draft.get("pieces") or [])
                if (p.get("name") or "?") in reg._shape
                and reg._shape[p.get("name") or "?"]
                != len(p.get("outline") or [])]
    if reshaped:
        return {
            "verdict": RESHAPED, "pieces": reshaped,
            "how_to_close": (
                "この裁片の番号は使えません。辺の名前を輪郭の頂点順ではなく"
                "製図の系譜（肩線・脇線・袖ぐり）から採れば頂点の増減で"
                "壊れなくなります。``seam_checks`` は既にその名前を持って"
                "いるので、``draft`` の ``pieces`` が辺に名前を持つように"
                "なった日にここが読み替わります。それまでは、形が変わった"
                "裁片は採番し直してください"),
            "why": ("番号が動かないことと、番号の指す場所が動かないことは"
                    "別。基底は動いていないので renumber_check は通る"),
        }

    rows: List[Dict[str, Any]] = []
    for p in draft.get("pieces") or []:
        name = p.get("name") or "?"
        out = p.get("outline") or []
        reg._shape[name] = len(out)
        es: List[Dict[str, Any]] = []
        for edge, i, j in _edges_of(p):
            base = reg.of(name, edge)
            es.append({
                "edge": edge, "base": base,
                "last": base + STRIDE - 1,
                "from_vertex": i, "to_vertex": j,
                "from_xy": out[i], "to_xy": out[j],
                # 頂点は必ず t=0 と t=1 に居るので、両端の番号は決め打ちで
                # 言える。**間に何が居るかはここでは言わない** — 言えば
                # それは測っていない主張になる。
                "vertex_numbers": [base, base + STRIDE - 1],
            })
        rows.append({"piece": name, "vertices": len(out), "edges": es})
    return {"verdict": "ANSWER", "registry": reg.to_json(),
            "stride": STRIDE, "pieces": rows,
            "total_numbers": len(reg.edges()) * STRIDE,
            "not_a_point": ("番号は辺上の位置を指す。そこに頂点があるとは"
                            "限らない")}


def renumber_check(before: Registry, after: Registry) -> Dict[str, Any]:
    """**改訂の前後で番号が動いていないか。**

    これがこの模組の反証子。``before`` にあった辺の基底が ``after`` で
    一つでも変わっていたら、その辺の番号は全部別の場所を指している。
    新しい辺が増えているのは正常 — 増えても既存が動かないことが主張。
    """
    moved = []
    for k, base in before._bases.items():
        now = after._bases.get(k)
        if now is None:
            moved.append({"edge": k, "was": base, "now": "GONE"})
        elif now != base:
            moved.append({"edge": k, "was": base, "now": now})
    added = [k for k in after._bases if k not in before._bases]
    return {
        "verdict": "ANSWER" if not moved else MOVED,
        "checked": len(before._bases),
        "moved": moved,
        "added": added,
        "stable": not moved,
        "why": ("既存の辺の基底が動くと、ユーザーが前の周回で言った"
                "「30番から35番」が別の場所を指す。ループは収束しない"),
    }
