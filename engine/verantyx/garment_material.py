# -*- coding: utf-8 -*-
"""生地の性質と重ね着。**立体十字を生地に使う。**

事前登録: experiments/garment/PREREG10_LAYERS.md

生地の性質は出典が食い違う典型である。同じ「メルトン」でも一社が
420g/m²、別の資料が 450g/m² と書く。どちらかが嘘なのではなく、別のものを
指している可能性がある。片方を選んで一つの数字にすると、**選んだことが
消える。**

`CrossStore` はこれをそのまま扱える。`core = fabric:メルトン`、
`facet = weight:450` を出典付きで積み、同じ key に別の値が立てば矛盾として
拾う。服飾台帳で観測が割れたときと同じ扱いで、片方を勝たせない。

## 重ねて入るかは引き算

外側の内周 − 内側の外周 − 層の厚みの合計。作り手が実際に確かめることで、
布の解法は要らない。**布の落ち方・皺・動きやすさは計算しない。**
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cross_store import CrossStore

#: 生地について持つ性質。閉じた表 — 何を聞かれていないかを数えるため。
PROPERTIES = {
    "weight": "目付 (g/m²)",
    "thickness": "厚み (mm)",
    "width": "生地幅 (cm)",
    "composition": "組成",
}

#: 数として扱う性質。ここに無いものは文字列として比べる。
NUMERIC = ("weight", "thickness", "width")

NO_SOURCE = "UNKNOWN_NO_SOURCE"
SPLIT = "CONTESTED"
UNKNOWN = "UNKNOWN_NOT_RECORDED"


@dataclass
class Property:
    """生地の性質ひとつ。**出典の無い性質は受け付けない。**"""

    fabric: str
    prop: str
    value: str
    source: str
    note: str = ""


@dataclass
class Fabrics:
    """生地台帳。十字はこの像であって、これ自体ではない。"""

    entries: List[Property] = field(default_factory=list)

    def record(self, fabric: str, prop: str, value: Any,
               source: str, note: str = "") -> Property:
        if prop not in PROPERTIES:
            raise ValueError(
                f"UNKNOWN_PROPERTY: {prop} は性質の表にない "
                f"({'/'.join(PROPERTIES)})")
        if not str(source).strip():
            raise ValueError(
                f"{NO_SOURCE}: 生地の性質には出典が要る。"
                "出典の無い目付は、誰かが言った数字ですらない")
        p = Property(fabric=str(fabric).strip(), prop=prop,
                     value=str(value).strip(), source=str(source).strip(),
                     note=str(note))
        self.entries.append(p)
        return p

    # -- 十字に載せる --------------------------------------------------
    def cross(self) -> CrossStore:
        """生地台帳を十字に写す。**元は触らない。**"""
        store = CrossStore()
        for e in self.entries:
            store.add(f"fabric:{e.fabric}", [f"{e.prop}:{e.value}"],
                      source=e.source)
        return store

    def state(self, fabric: str, prop: str) -> Dict[str, Any]:
        """ある生地のある性質。**割れたら片方を勝たせない。**"""
        rows = [e for e in self.entries
                if e.fabric == fabric and e.prop == prop]
        if not rows:
            return {"fabric": fabric, "prop": prop, "state": UNKNOWN,
                    "how_to_close": f"{fabric} の{PROPERTIES[prop]}を"
                                    "資料か実測で入れる"}
        values = sorted({e.value for e in rows})
        if len(values) > 1:
            # **同じ資料を二度読んでも証拠は一つ。** 出典を畳む。
            # 畳まないと、同じ仕様書を二回入れただけで片方が重く見える。
            return {"fabric": fabric, "prop": prop, "state": SPLIT,
                    "sides": [{"value": v,
                               "sources": sorted({e.source for e in rows
                                                  if e.value == v})}
                              for v in values],
                    "how_to_close": "出典が食い違っている。別のものを指して"
                                    "いる可能性がある / 人が確かめる"}
        return {"fabric": fabric, "prop": prop, "state": "RECORDED",
                "value": values[0],
                "sources": sorted({e.source for e in rows}),
                "agreed": len({e.source for e in rows})}

    def number(self, fabric: str, prop: str) -> Optional[float]:
        """数として使える値。**割れているものは数にしない。**"""
        s = self.state(fabric, prop)
        if s["state"] != "RECORDED" or prop not in NUMERIC:
            return None
        try:
            return float(str(s["value"]).replace(",", ""))
        except ValueError:
            return None

    def report(self, fabrics: Optional[List[str]] = None) -> Dict[str, Any]:
        names = fabrics or sorted({e.fabric for e in self.entries})
        rows = [self.state(f, p) for f in names for p in PROPERTIES]
        return {
            "verdict": "ANSWER",
            "fabrics": names,
            "rows": rows,
            "counts": {
                "recorded": sum(1 for r in rows if r["state"] == "RECORDED"),
                "contested": sum(1 for r in rows if r["state"] == SPLIT),
                "unknown": sum(1 for r in rows if r["state"] == UNKNOWN),
            },
            "note": "出典が食い違うものは片方を勝たせません。"
                    "別のものを指している可能性があります",
        }

    def save(self, path: Any) -> Dict[str, Any]:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"entries": [asdict(e) for e in self.entries]},
                                ensure_ascii=False, indent=1),
                     encoding="utf-8")
        return {"verdict": "ANSWER", "path": str(p)}

    @classmethod
    def load(cls, path: Any) -> "Fabrics":
        p = Path(path)
        if not p.is_file():
            return cls()
        d = json.loads(p.read_text(encoding="utf-8"))
        out = cls()
        out.entries = [Property(**row) for row in d.get("entries", [])]
        return out


# ---------------------------------------------------------------------
#  面積と重さ
# ---------------------------------------------------------------------

def surface_area(solid: Dict[str, Any]) -> float:
    """立体の表面積 (cm²)。三角形の面積を足すだけ。"""
    verts = solid.get("vertices", [])
    total = 0.0
    for f in solid.get("faces", []):
        if len(f) != 3:
            continue
        try:
            a, b, c = (verts[i] for i in f)
        except IndexError:
            continue
        ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cx = uy * vz - uz * vy
        cy = uz * vx - ux * vz
        cz = ux * vy - uy * vx
        total += 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
    return round(total, 1)


def cloth_estimate(solid: Dict[str, Any], fabrics: Fabrics,
                   fabric: str) -> Dict[str, Any]:
    """面積から重さを見積もる。**必要量ではなく下限の目安。**

    立体は型紙ではない。縫い代も、裁ち都合も、重なりも入っていない。
    """
    area_cm2 = surface_area(solid)
    gsm = fabrics.number(fabric, "weight")
    out: Dict[str, Any] = {
        "verdict": "ANSWER",
        "fabric": fabric,
        "surface_area_cm2": area_cm2,
        "surface_area_m2": round(area_cm2 / 10000.0, 3),
        "not_a_yardage":
            "立体は型紙ではありません。縫い代も裁ち都合も重なりも"
            "入っていないので、これは**下限の目安**であって必要な"
            "生地量ではありません。",
    }
    if gsm is None:
        s = fabrics.state(fabric, "weight")
        out["state"] = s["state"]
        out["how_to_close"] = s.get(
            "how_to_close", "目付が割れています。人が確かめてください")
        return out
    out["state"] = "DERIVED"
    out["gsm"] = gsm
    # **書いた式を掛けたら、書いた数になること。** 内部の精度で計算して
    # 表示だけ丸めると、読み手が式を検算したときに合わない
    # (実測 VL3 で 520.2 と 520.3 に割れた)。派生値は由来を示すのが
    # 規律なので、示した由来から計算する。
    out["weight_g"] = round(out["surface_area_m2"] * gsm, 1)
    out["from"] = f"{out['surface_area_m2']}m² × {gsm}g/m²"
    out["note"] = "計算値です。実測ではありません"
    return out


# ---------------------------------------------------------------------
#  重ね着
# ---------------------------------------------------------------------

def layer_fit(inner_girth: Optional[float], outer_girth: Optional[float],
              thicknesses: List[Optional[float]]) -> Dict[str, Any]:
    """外側が内側の上に入るか。**引き算であって着装計算ではない。**

    余り = 外の内周 − 内の外周 − 厚みの合計 × 2π
    (厚みは半径方向に効くので周には 2π 倍で乗る)
    """
    missing: List[str] = []
    if inner_girth is None:
        missing.append("内側の外周")
    if outer_girth is None:
        missing.append("外側の内周")
    if any(t is None for t in thicknesses):
        missing.append("層の厚み")
    if missing:
        return {"verdict": "UNKNOWN_NO_BASIS",
                "missing": missing,
                "how_to_close": "、".join(missing) + " を入れると余りが出る"}
    # mm → cm
    added = sum(float(t) for t in thicknesses) / 10.0 * 2.0 * math.pi
    slack = round(float(outer_girth) - float(inner_girth) - added, 1)
    return {
        "verdict": "ANSWER",
        "inner_girth": inner_girth,
        "outer_girth": outer_girth,
        "thickness_adds_cm": round(added, 1),
        # **負を丸めない。** 入らないものは入らない。
        "slack_cm": slack,
        "fits": slack >= 0,
        "not_a_drape":
            "これは引き算です。布の落ち方・皺・動きやすさは計算して"
            "いません。型紙と生地の解法が要ります。",
    }
