# -*- coding: utf-8 -*-
"""立体十字ストア。**Block の置き場所であって、辞書の代用品ではない。**

1核 = 6本の腕 × 4つの面 = **24席**。この上限は測定に由来する
(ノードの識別能力は 6腕×4面=24語、それを超える語は到達不能 0/60)。
だからこの店は**容量を超えた要求を黙って拡張しない** — 子コアに分れる
(マトリョーシカは選択ではなく幾何が要求すること)。

守っている性質と、その根拠:

- **同点は棄権。** 同じ住所に値が違い複数立ったら、どちらも捨てずに
  CONTESTED を返す。多数決もアルファベット順も使わない — 恣意的な
  同点崩しは一致を捏造した (実測: 辞書順タイブレークで全一致の精度が
  73.3% → 23.7% に落ちた)。
- **配置は情報を増やさない。** 取り出し答えが格納順に依ってよい理由は
  ない。`placement_check()` が店じゅうを二つの決定的な順で歩き、
  答えが一つでも動いたら ORDER_DEPENDENT を返す。
- **辺は関係の席。** 面(facet)は「何が在るか」、辺(edge)は「何と何が
  約束しているか」。縫い目のように二枚の間でしか成立しないものは、
  面に置かず辺で結ぶ。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

#: 幾何。**この数は測定から来ている。** 変えるなら測定し直すこと。
ARMS = ("pieces", "measures", "seams", "params", "settings", "rules")
FACES_PER_ARM = 4
CAPACITY_PER_CORE = len(ARMS) * FACES_PER_ARM      # 24

NOT_IN_CROSS = "UNKNOWN_NOT_IN_CROSS"
CONTESTED_IN_CROSS = "CONTESTED_IN_CROSS"
ARM_FULL = "UNKNOWN_CROSS_ARM_FULL"
ORDER_DEPENDENT = "UNKNOWN_ORDER_DEPENDENT"

Addr = Tuple[str, str, str]          # (core, arm, key)


class CrossFullError(ValueError):
    """腕の4面が埋まった。**黙って拡張しない** — 子コアに分ける。"""


class CrossStore:
    """核の集まりと、核どうしを結ぶ辺。"""

    def __init__(self) -> None:
        self.cores: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        # 面は挿入順を保つ。**並べ替えで答えが変わってはいけない**ので、
        # 順序は保持しつつ、依存していないことを placement_check が確かめる。
        self.edges: List[Dict[str, Any]] = []

    # ------------------------------------------------------------ 格納
    def _core(self, name: str) -> Dict[str, List[Dict[str, Any]]]:
        if name not in self.cores:
            self.cores[name] = {arm: [] for arm in ARMS}
        return self.cores[name]

    def put(self, core: str, arm: str, key: str, value: Any,
            source: str = "") -> Dict[str, Any]:
        """面に載せる。同じ主張の再掲は増えない(同じ絵を9回見ても1件)。"""
        if arm not in ARMS:
            raise ValueError(f"UNKNOWN_NO_SUCH_ARM: {arm} — arms are {ARMS}")
        c = self._core(core)
        slots = c[arm]
        for i, f in enumerate(slots):
            if f["key"] == key and f["value"] == value \
                    and f["source"] == source:
                return {"core": core, "arm": arm, "face": i,
                        "state": "already"}
        if len(slots) >= FACES_PER_ARM:
            raise CrossFullError(
                f"{ARM_FULL}: {core}/{arm} は4面とも埋まっています。"
                "黙って拡張せず、子コアに分けてください "
                "(マトリョーシカは幾何が要求すること)")
        slots.append({"key": key, "value": value, "source": source})
        return {"core": core, "arm": arm, "face": len(slots) - 1,
                "state": "placed"}

    def get(self, core: str, arm: str, key: str) -> Dict[str, Any]:
        """取り出す。**同点は棄権する。**

        - 無い → UNKNOWN_NOT_IN_CROSS(「無い」は「0件の検索結果」と別)
        - 一意 → ANSWER
        - 値が違うものが複数 → CONTESTED_IN_CROSS。両方を出し、
          **どちらも選ばない**
        """
        for f in self._core(core)[arm]:
            if f["key"] != key:
                continue
            sides = [f]
            for g in self._core(core)[arm]:
                if g is not f and g["key"] == key:
                    sides.append(g)
            values = [s["value"] for s in sides]
            if all(v == values[0] for v in values[1:]):
                return {"verdict": "ANSWER", "value": values[0],
                        "sources": [s["source"] for s in sides],
                        "agreed": len(sides),
                        "where": {"core": core, "arm": arm}}
            return {"verdict": CONTESTED_IN_CROSS,
                    "sides": [{"value": s["value"], "source": s["source"]}
                              for s in sides],
                    "how_to_close":
                        "宣言を確かめて、正しい方だけを残す",
                    "where": {"core": core, "arm": arm}}
        return {"verdict": NOT_IN_CROSS,
                "why": f"{core}/{arm} に {key} は載っていない",
                "how_to_close": "Block の宣言に足す"}

    def require(self, core: str, arm: str, key: str) -> Any:
        """値を必須で取る。断られたら例外で止まる(**埋めない**)。"""
        r = self.get(core, arm, key)
        if r["verdict"] == "ANSWER":
            return r["value"]
        raise ValueError(f'{r["verdict"]}: {core}/{arm}/{key}')

    def contested(self) -> List[Dict[str, Any]]:
        """店じゅうの割れの一覧。**片方は選ばれていない。**"""
        out: List[Dict[str, Any]] = []
        for cname, c in self.cores.items():
            for arm, slots in c.items():
                seen: Dict[str, List[Dict[str, Any]]] = {}
                for f in slots:
                    seen.setdefault(f["key"], []).append(f)
                for key, fs in seen.items():
                    vals = [f["value"] for f in fs]
                    if any(v != vals[0] for v in vals[1:]):
                        out.append({"core": cname, "arm": arm, "key": key,
                                    "sides": len(fs)})
        return out

    # ------------------------------------------------------------ 辺
    def link(self, a: Addr, b: Addr, label: str,
             value: Any = None) -> int:
        """辺を結ぶ。面を消費しない — **関係は席を要らない。**"""
        self.edges.append({"a": a, "b": b, "label": label, "value": value})
        return len(self.edges) - 1

    def put_all(self, root: str, arm: str, items: List[Tuple[str, Any]],
                source: str) -> List[str]:
        """腕に順に載せる。**満杯になったら子コアに分れ、辺で繋ぐ。**

        黙って席を増やさない。分割は店の幾何(4面)が決めることで、
        どこに何が行ったかは nest 辺が覚えている。戻り値は載った核の列。
        """
        cores = [root]
        cur = root
        no = 0
        for key, value in items:
            try:
                self.put(cur, arm, key, value, source)
            except CrossFullError:
                no += 1
                cur = f"{root}·{arm}{no}"
                cores.append(cur)
                self.link((cores[-2], arm, ""), (cur, arm, ""), "nest")
                self.put(cur, arm, key, value, source)
        return cores

    def edges_labeled(self, label_prefix: str) -> List[Dict[str, Any]]:
        out = []
        for e in self.edges:
            if e["label"].startswith(label_prefix):
                out.append(e)
        return out

    def edges_from(self, core: str) -> List[Dict[str, Any]]:
        return [e for e in self.edges
                if e["a"][0] == core or e["b"][0] == core]

    # ------------------------------------------------------------ 配置不変性
    def placement_check(self) -> Dict[str, Any]:
        """店じゅうを二つの決定的な順で歩き、**答えが一つでも動いたら落とす**。

        配置は情報を増やさない。格納順を変えたからといって、取り出せる
        事実が変わるなら、それは事実ではなく順序の産物です。逆順は
        決定的でなければならないので reversed(乱数禁止)。これは通っても
        何かを証明したことにはならない構成上の確認なので structural。
        """
        addresses: List[Tuple[str, str, str]] = []
        for cname in self.cores:
            for arm in ARMS:
                for f in self.cores[cname][arm]:
                    addresses.append((cname, arm, f["key"]))

        def walk(order: List[int]) -> Dict[Any, Any]:
            out: Dict[Any, Any] = {}
            for i in order:
                core, arm, key = addresses[i]
                out[(core, arm, key)] = self.get(core, arm, key)
            return out

        fwd = walk(list(range(len(addresses))))
        rev = walk(list(reversed(range(len(addresses)))))
        same = fwd == rev
        return {
            "verdict": "ANSWER" if same else ORDER_DEPENDENT,
            "structural": True,
            "not_a_test": ("配置を変えても答えは動いてはいけない、という"
                           "確認です。通っても情報は増えません"),
            "addresses_checked": len(addresses),
            "why_it_matters":
                "配置が答えを決めているなら、それは宣言ではなく並びの産物",
        }

    # ------------------------------------------------------------ 出し入れ
    def to_dict(self) -> Dict[str, Any]:
        return {"cores": {n: {a: [dict(f) for f in slots]
                              for a, slots in c.items()}
                          for n, c in self.cores.items()},
                "edges": [dict(e) for e in self.edges]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrossStore":
        st = cls()
        st.cores = {n: {a: [dict(f) for f in slots]
                        for a, slots in c.items()}
                    for n, c in data["cores"].items()}
        st.edges = [dict(e) for e in data["edges"]]
        return st

    # ------------------------------------------------------------ 観測
    def census(self) -> Dict[str, Any]:
        """店の在り方の集計。**席の数は幾どおりに収まっているか。**"""
        facets = sum(len(s) for c in self.cores.values()
                     for s in c.values())
        over = [(n, a, len(s)) for n, c in self.cores.items()
                for a, s in c.items() if len(s) > FACES_PER_ARM]
        return {"cores": len(self.cores), "facets": facets,
                "capacity_per_core": CAPACITY_PER_CORE,
                "over_capacity": over,
                "edges": len(self.edges),
                "contested": len(self.contested())}
