# -*- coding: utf-8 -*-
"""寸法 — **推定しない。持つのは実測と比率と、欠けの名前だけ。**

事前登録: experiments/garment/PREREG6_MEASURE.md

一枚の絵に長さの基準が映っていなければ、袖丈は出ない。「肘下12cm相当」は
観測ではなく比率の読みで、基準が入って初めて長さになる。ここを曖昧にすると、
比率から出した数字が実寸の顔をして型紙に乗り、裁った後に気付く。

三つを混ぜない:

    measured   実物・資料から入った長さ。出典と単位が要る
    ratio      基準に掛ける値。基準が無ければ長さにならない
    derived    比率×基準で計算された長さ。**実測と同じ欄には入らない**
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

def _number(value: Any) -> float:
    """**数でないものと、保存できない数を、書き口で断る。**

    ``float(value)`` は ``"nan"`` も ``"inf"`` も受け取る。受け取ると
    ``measures.json`` に素の ``NaN`` が書かれ (JSON ではない)、MCP の
    返事も**一行まるごと**読めなくなる — 実測: ``measure_taken`` に
    ``value="nan"`` を渡すと ``{"verdict": "ANSWER", "entry": {…
    "value": NaN …}}`` が stdout に出て、Python 以外の読み手はその返事
    ごと落ちた。数でない文字列も、素の ``ValueError`` の文面が verdict に
    化けていた (「could not convert string to float」という名前の断り)。
    どちらもここで型の付いた断りにする。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{NOT_A_NUMBER}: {value!r} は数ではない。"
                         "寸法は数で書く")
    if not math.isfinite(v):
        raise ValueError(f"{NOT_A_NUMBER}: {v!r} は JSON で往復しない "
                         "(NaN と ±Infinity は JSON の数ではない)")
    return v


UNITS = ("cm", "mm", "inch")

#: cm に直す係数。製図は cm。
TO_CM = {"cm": 1.0, "mm": 0.1, "inch": 2.54}

#: 同じ場所の実測が食い違っている。**どちらも捨てない。**
CONTESTED = "CONTESTED_MEASUREMENT"

#: 一着について決めるべき寸法(閉じた表)。閉じているから欠けを数えられる。
SPOTS: Dict[str, str] = {
    "body_length": "着丈",
    "chest": "胸囲",
    "waist": "胴囲",
    "hip": "腰囲",
    "shoulder": "肩幅",
    "sleeve_length": "袖丈",
    "cuff_width": "袖口幅",
    "collar_height": "襟の高さ",
    "pocket_position": "ポケット位置(肩からの距離)",
    "hem_width": "裾幅",
    "skirt_length": "スカート丈",
    "neck": "襟ぐり周囲",
    "bodice_length": "上身頃丈",
    "cape_length": "ケープ丈",
}

#: 比率が掛かる基準。ここに無いものを基準にはできない。
BASES = ("body_length", "chest", "shoulder")

NOT_A_NUMBER = "UNKNOWN_NOT_A_NUMBER"
NO_UNIT = "UNKNOWN_NO_UNIT"
NO_BASIS = "UNKNOWN_NO_BASIS"
NOT_TAKEN = "UNKNOWN_NOT_TAKEN"


@dataclass
class Measure:
    spot: str
    kind: str                # measured / ratio
    value: float
    unit: str = ""           # measured のとき必須
    basis: str = ""          # ratio のとき、掛ける先
    source: str = ""
    by: str = ""


@dataclass
class Measures:
    entries: List[Measure] = field(default_factory=list)

    def measured(self, spot: str, value: float, unit: str, source: str,
                 by: str = "") -> Measure:
        """実測を置く。**単位の無い数字は受け取らない。**

        cm と inch が混じった表は、裁った後にしか気付けない。
        """
        if unit not in UNITS:
            raise ValueError(
                f"{NO_UNIT}: 単位が要る ({'/'.join(UNITS)})。"
                "単位の無い数字は、型紙の上で意味を持たない")
        return self._add(Measure(spot=spot, kind="measured",
                                 value=_number(value), unit=unit,
                                 source=source, by=by))

    def ratio(self, spot: str, value: float, basis: str,
              source: str = "") -> Measure:
        """比率を置く。**これは長さではない。** 基準が入るまで長さにならない。"""
        if basis not in BASES:
            raise ValueError(
                f"{NO_BASIS}: 基準は {'/'.join(BASES)} のいずれか。"
                "基準の無い比率は、掛ける先が無い")
        return self._add(Measure(spot=spot, kind="ratio",
                                 value=_number(value),
                                 basis=basis, source=source))

    def _add(self, m: Measure) -> Measure:
        if m.spot not in SPOTS:
            raise ValueError(f"UNKNOWN_SPOT: {m.spot} は寸法の表にない")
        self.entries.append(m)
        return m

    # -- 読む ------------------------------------------------------------
    #: 同じ場所を二度測ったとき、これ以内なら同じ測定とみなす(cm 換算)。
    #: **選んだ数字ではなく実務の公差**: POM の一般的な許容は身幅で ±1cm、
    #: 襟などの細部で ±0.5cm。ここは細部側の 0.5cm を採る。
    SAME_MEASUREMENT_CM = 0.5

    def _measured_rows(self, spot: str) -> List[Measure]:
        return [e for e in self.entries
                if e.spot == spot and e.kind == "measured"]

    def _measured_of(self, spot: str) -> Optional[Measure]:
        rows = self._measured_rows(spot)
        return rows[0] if rows else None

    def _conflict(self, spot: str) -> Optional[List[Measure]]:
        """同じ場所の実測が食い違っているか。

        2026-08-23 の欠陥: `rows[0]` だけを読んでいたので、後から入れた
        違う値は **台帳に残ったまま画面に出ませんでした**。観測の側は
        矛盾を検出するのに、寸法の側は最初の一件を黙って使っていた。
        裁つのは寸法のほうなので、こちらが黙るのは重い。

        **どちらが正しいかは決めません。** 両方出して人が選びます。
        """
        rows = self._measured_rows(spot)
        if len(rows) < 2:
            return None
        cm = [r.value * TO_CM.get(r.unit, 1.0) for r in rows]
        if max(cm) - min(cm) <= self.SAME_MEASUREMENT_CM:
            return None
        return rows

    def state(self, spot: str) -> Dict[str, Any]:
        clash = self._conflict(spot)
        if clash:
            return {"spot": spot, "name": SPOTS[spot], "state": CONTESTED,
                    "sides": [{"value": r.value, "unit": r.unit,
                               "source": r.source, "by": r.by}
                              for r in clash],
                    "tolerance_cm": self.SAME_MEASUREMENT_CM,
                    "how_to_close": f"{SPOTS[spot]}をもう一度測って、"
                                    "どちらが正しいか決める",
                    "why": "同じ場所の実測が食い違っています。"
                           "どちらかを勝手に採りません"}
        m = self._measured_of(spot)
        if m:
            return {"spot": spot, "name": SPOTS[spot], "state": "MEASURED",
                    "value": m.value, "unit": m.unit, "source": m.source,
                    "by": m.by}
        ratios = [e for e in self.entries
                  if e.spot == spot and e.kind == "ratio"]
        if ratios:
            r = ratios[0]
            base = self._measured_of(r.basis)
            if base is None:
                return {"spot": spot, "name": SPOTS[spot], "state": NO_BASIS,
                        "ratio": r.value, "basis": r.basis,
                        "how_to_close": f"{SPOTS[r.basis]}を実測すれば"
                                        f"長さになる"}
            # **計算した長さは実測と同じ欄に入らない。**
            return {"spot": spot, "name": SPOTS[spot], "state": "DERIVED",
                    "value": round(r.value * base.value, 1),
                    "unit": base.unit, "ratio": r.value, "basis": r.basis,
                    "from": f"{SPOTS[r.basis]} {base.value}{base.unit}"
                            f" × {r.value}",
                    "note": "計算値。実測ではない"}
        return {"spot": spot, "name": SPOTS[spot], "state": NOT_TAKEN,
                "how_to_close": f"{SPOTS[spot]}を実物か資料から測る"}

    def sheet(self) -> Dict[str, Any]:
        """寸法表。**欠けを空欄で消さない。**"""
        rows = [self.state(s) for s in SPOTS]
        return {
            "verdict": "ANSWER",
            "measured": [r for r in rows if r["state"] == "MEASURED"],
            "derived": [r for r in rows if r["state"] == "DERIVED"],
            "contested": [r for r in rows if r["state"] == CONTESTED],
            # 食い違いは open に入れる — **裁つ根拠にならないから。**
            "open": [r for r in rows
                     if r["state"] in (NOT_TAKEN, NO_BASIS, CONTESTED)],
            "counts": {
                "measured": sum(1 for r in rows if r["state"] == "MEASURED"),
                "derived": sum(1 for r in rows if r["state"] == "DERIVED"),
                "contested": sum(1 for r in rows
                                 if r["state"] == CONTESTED),
                "open": sum(1 for r in rows
                            if r["state"] in (NOT_TAKEN, NO_BASIS,
                                              CONTESTED)),
            },
            "note": "derived は比率×基準の計算値で、実測ではない。"
                    "裁つ前に実測で確かめる",
        }

    def save(self, path: Any) -> Dict[str, Any]:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"entries": [asdict(e) for e in self.entries]},
                                ensure_ascii=False, indent=1),
                     encoding="utf-8")
        return {"verdict": "ANSWER", "path": str(p)}

    @classmethod
    def load(cls, path: Any) -> "Measures":
        p = Path(path)
        if not p.is_file():
            return cls()
        d = json.loads(p.read_text(encoding="utf-8"))
        out = cls()
        out.entries = [Measure(**row) for row in d.get("entries", [])]
        return out
