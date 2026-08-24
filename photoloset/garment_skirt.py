# -*- coding: utf-8 -*-
"""スカートの製図。**組立器が組み立てた宣言を解釈して幾何を作る。**

これは2つ目のBlockであり、**抽象の証明**です:

- 製図定数は BlockView(十字)から読む。このファイルに服の数字は
  一つも書かない
- 出力はコートと同じ形(pieces/edges/seam_checks)なので、合印・縫い代・
  SVG の既存エンジンがそのまま使える
- 縫い目と吊り方は宣言(settings)が決める。脇を縫い、ウエストの左右端
  で吊る — 肩の無い服は肩で吊れない

まだ足りないもの(正直に): 開き(ファスナー)のある後ろ中心は、ライブラリ
に候補として在るが draftable=False。引けないものを引けると言わないため。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .garment_pattern import _length, _area, _need


def _half(x: float) -> float:
    return x / 2.0


def draft(measures: Any, view: Any) -> Dict[str, Any]:
    """宣言(view)を読んでスカートを引く。

    必要な寸法は宣言(measures の腕)が持ち、一つでも欠ければ引かない
    — コートと同じ門です。
    """
    spots = tuple(view.required())
    have, missing, units = _need(measures, spots)
    if missing:
        return {
            "verdict": "UNKNOWN_MISSING_MEASUREMENTS",
            "missing": list(missing),
            "how_to_close": "、".join(missing) + " を実測すれば引ける",
            "units": units,
            "formulas": view.formulas(),
            "note": "型紙は裁つものなので、足りない寸法を既定で埋めません",
        }

    P = view.param
    waist = have["waist"]
    hip = have["hip"]
    L = have["skirt_length"]

    # ---- 式(全部宣言から) ------------------------------------------
    hip_depth = P("hip_depth")          # ウエストからヒップまでの下がり
    waist_ease = P("waist_ease_per_panel")
    hip_ease = P("hip_ease")
    flare = P("flare_ratio")

    w_waist = _half(waist) + waist_ease           # 1枚のウエスト幅
    w_hip = max(_half(hip) + hip_ease, w_waist)   # ヒップが細い服はない
    hem_w = w_hip * flare                         # 裾幅

    hw = _half(w_waist)
    hh = _half(hem_w)

    def panel(name: str) -> Tuple[List[Tuple[float, float]],
                                  Dict[str, List[Tuple[float, float]]]]:
        """1枚分。原点は中心線上のウエスト。x は外向き、y は下向き。

        前後とも中心線は折り(わ)なので輪郭には現れない。輪郭にあるのは
        ウエスト・両脇・裾の4辺だけ。
        """
        outline = [
            (-hw, 0.0), (hw, 0.0),
            (hh, L), (-hh, L),
        ]
        edges = {
            "ウエスト(カーシング)": [(-hw, 0.0), (hw, 0.0)],
            "脇線 (右)": [(hw, 0.0), (hh, L)],
            "裾": [(hh, L), (-hh, L)],
            "脇線 (左)": [(-hh, L), (-hw, 0.0)],
        }
        return outline, edges

    pieces: List[Dict[str, Any]] = []
    for name in view.pieces():
        outline, edges = panel(name)
        pieces.append({
            "name": name,
            "outline": [[round(x, 2), round(y, 2)] for x, y in outline],
            "edges": {k: {"points": [[round(x, 2), round(y, 2)]
                                     for x, y in v],
                          "length": _length(v)}
                      for k, v in edges.items()},
            "area_cm2": _area(outline),
        })

    # ---- 縫い合わせの検算 -------------------------------------------
    checks = _seam_checks(pieces, view.seams())

    return {
        "verdict": "ANSWER",
        "block_kind": "skirt",
        "block_root": view.root,
        "pieces": pieces,
        "seam_checks": checks,
        "used": {k: round(v, 2) for k, v in have.items()},
        "units": units,
        "formulas": view.formulas(),
        "total_area_cm2": round(sum(p["area_cm2"] for p in pieces), 1),
        "seam_allowance":
            "縫い代は入っていません。引いたのは出来上がり線です。",
        "not_a_published_system":
            "これはこの道具の簡易製図です。式は全て出しているので、"
            "違うと思ったら式を見てください。",
        "note": "型紙は寸法からの派生で、実物の型紙を見たものではありません",
        # ---- 下流(合印・縫製)への手渡し。束ねず、宣言が運ぶ -------------
        "settings": {
            "pins_policy": _setting(view, "pins_policy"),
            "grain_angle_deg": _setting(view, "grain_angle_deg"),
        },
        "placement": view.placement(),
        "seam_specs": view.seams(),
        "notch_plan": _setting(view, "notch_plan") or [],
    }


def _setting(view: Any, key: str) -> Any:
    try:
        return view.setting(key)
    except ValueError:
        return None


def _seam_checks(pieces: List[Dict[str, Any]],
                 seams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """縫い合わせる辺の長さ差。**差を出すのが目的で、合格ではない。**

    前後で同じ点から引いた辺どうしは構成上ゼロになるので structural
    札が付く — 点を比べて自動判定される(コートと同じ規律)。
    """
    by_name = {p["name"]: p for p in pieces}
    out: List[Dict[str, Any]] = []
    for spec in seams:
        (pa, ea), (pb, eb) = spec["a"], spec["b"]
        label = spec.get("label", f"{pa}/{ea} ↔ {pb}/{eb}")
        if pa not in by_name or pb not in by_name:
            continue
        ra = by_name[pa]["edges"].get(ea)
        rb = by_name[pb]["edges"].get(eb)
        if ra is None or rb is None:
            continue
        same_points = ra["points"] == rb["points"]
        diff = round(ra["length"] - rb["length"], 2)
        out.append({
            "label": label,
            "a": f"{pa}/{ea}", "b": f"{pb}/{eb}",
            "length_a": ra["length"], "length_b": rb["length"],
            "difference": diff,
            "tolerance": 0.3,
            "sewable": abs(diff) <= 0.3,
            "structural": same_points,
            "not_a_test": ("前後で同じ点から引いているので、差は構成上"
                           "ゼロです。通っても何も確かめていません"
                           if same_points else None),
            "why": "脇が合わないと脇が縫えない",
        })
    return out
