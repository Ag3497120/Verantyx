# -*- coding: utf-8 -*-
"""部品の幾何。**1部品 = 1手続き。ports が辺に写像される。**

ここにあるのは部品の製図だけ。服としての組立て(接続・開portの列挙)
は ``compose`` の仕事。種類(ワンピース等)はこの層に存在しない —
種類は組合せに付ける名前であって、手続きを増やさない限り能力は増えない。

正直な限界: 上身頃と袖はコートの製図と同じ骨格です(半身・わ裁ち)。
統合は、コート自体をこの部品の組合せに移し替える段で行う — 今ここで
触ると、動いているもののビット一致を危くする。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .garment_pattern import _length, _area

# 共通の既定値。**全部式として出力に載る。**
BODICE_EASE = 1.5          # 胸のゆとり(1枚あたり)
WAIST_SEAM_EASE = 1.0      # ウエストの楽(1枚あたり)
CAPE_SECTOR = 0.75         # ケープの扇の開き(全円=1.0)
CAPE_ARC_STEPS = 24        # 弧を何点で結ぶか(決定的)


def _piece(name: str, outline: List[Tuple[float, float]],
           edges: Dict[str, List[Tuple[float, float]]],
           ports: Dict[str, str]) -> Dict[str, Any]:
    return {
        "name": name,
        "outline": [[round(x, 2), round(y, 2)] for x, y in outline],
        "edges": {k: {"points": [[round(x, 2), round(y, 2)] for x, y in v],
                      "length": _length(v)} for k, v in edges.items()},
        "area_cm2": _area(outline),
        "ports": ports,           # **接続口 → 辺の名前。** 組立てはここで
                                  # 辺を探す。近さで探さない
    }


# ---------------------------------------------------------------- 上身頃
def draft_bodice(measures_get, params: Dict[str, float]
                 ) -> Dict[str, Any]:
    """上身頃。**半身・わ裁ち**(前後の2枚)。コートと同じ骨格。

    下端は裾でなくウエスト。ここにスカートが繋がる。
    """
    chest = measures_get("chest")
    shoulder = measures_get("shoulder")
    waist = measures_get("waist")
    L = measures_get("bodice_length")

    # 設計パラメータは **ゾーン調整で上書きされ得る**。既定はこの
    # モジュールの定数。
    chest_ease = params.get("chest_ease", BODICE_EASE)
    waist_ease = params.get("waist_ease", WAIST_SEAM_EASE)
    ah_add = params.get("armhole_depth_add", 6.5)

    half_c = chest / 4.0 + chest_ease
    half_w = max(waist / 4.0 + waist_ease, half_c * 0.6)
    armhole_depth = chest / 8.0 + ah_add
    shoulder_drop = shoulder / 10.0
    neck_w = chest / 12.0 + 1.5
    neck_d = chest / 12.0 + 2.0

    formulas = [
        ("身頃幅 (胸, 1枚)", f"chest / 4 + {chest_ease}"),
        ("身頃幅 (ウエスト, 1枚)", f"waist / 4 + {waist_ease}"),
        ("袖ぐり深さ", f"chest / 8 + {ah_add}"),
        ("肩線の下がり", "shoulder / 10"),
        ("襟ぐり幅", "chest / 12 + 1.5"),
        ("襟ぐり深さ", "chest / 12 + 2.0"),
    ]

    out = {"formulas": formulas, "pieces": [], "seams": []}
    for name, is_front in (("前身頃", True), ("後身頃", False)):
        neck_depth = neck_d if is_front else 2.0
        sh_end = (shoulder / 2.0, shoulder_drop)
        armhole = [sh_end,
                   (half_c - (1.6 if is_front else 1.0),
                    armhole_depth * 0.55),
                   (half_c, armhole_depth)]
        outline = [(0.0, neck_depth), (neck_w, 0.0), sh_end,
                   (half_c, armhole_depth), (half_w, L), (0.0, L)]
        edges = {
            "襟ぐり": [(0.0, neck_depth), (neck_w, 0.0)],
            "肩線": [(neck_w, 0.0), sh_end],
            "袖ぐり": armhole,
            "脇線": [(half_c, armhole_depth), (half_w, L)],
            "ウエスト": [(half_w, L), (0.0, L)],
            "中心線": [(0.0, L), (0.0, neck_depth)],
        }
        # **半身は左側を描く**(わ裁ちの規約)。右側は鏡像で2枚取る。
        # 肩線は部品の内部縫い目であって接続口ではない。
        ports = {"neck": "襟ぐり",
                 "armhole_l": "袖ぐり", "waist": "ウエスト",
                 "center_front" if is_front else "center_back": "中心線"}
        out["pieces"].append(_piece(name, outline, edges, ports))

    out["seams"] = [
        {"a": ("前身頃", "肩線"), "b": ("後身頃", "肩線"),
         "label": "肩線: 前 ↔ 後"},
        {"a": ("前身頃", "脇線"), "b": ("後身頃", "脇線"),
         "label": "脇線: 前 ↔ 後"},
    ]
    return out


# ---------------------------------------------------------------- 袖
def draft_sleeve(measures_get, params: Dict[str, float],
                 armhole_total: float) -> Dict[str, Any]:
    """袖。**袖ぐりの合計は接続先(上身頃)から来る** — 単独では出ない。

    side は 左/右。2本の袖は別インスタンスで、辺名に側が入る。
    """
    chest = measures_get("chest")
    sl = measures_get("sleeve_length")
    side = params.get("side", "左")
    ease = params.get("ease_in", 2.0)
    cuff_add = params.get("cuff_add", 2.0)

    armhole_depth = chest / 8.0 + 6.5
    cap_h = armhole_depth * 0.78
    cuff_half = chest / 8.0 + cuff_add
    target = armhole_total + ease

    def cap_points(w):
        return [(-w, cap_h), (-w * 0.5, cap_h * 0.22), (0.0, 0.0),
                (w * 0.5, cap_h * 0.22), (w, cap_h)]

    lo, hi = 0.1, armhole_total
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _length(cap_points(mid)) < target:
            lo = mid
        else:
            hi = mid
    w = round((lo + hi) / 2.0, 4)
    cap = cap_points(w)
    name = f"袖({side})"
    outline = [*cap, (cuff_half, cap_h + sl), (-cuff_half, cap_h + sl)]
    # **袖山は肩点で前後に分かれる。** 上身頃の袖ぐりは前後の2枚に載る
    # ので、受け側も2辺に分けて 1↔1 のペアで縫む(鎖は縫えない)。
    edges = {
        "袖山(前半)": [cap[0], cap[1], cap[2]],
        "袖山(後半)": [cap[2], cap[3], cap[4]],
        "袖下線(前)": [(w, cap_h), (cuff_half, cap_h + sl)],
        "袖口": [(cuff_half, cap_h + sl), (-cuff_half, cap_h + sl)],
        "袖下線(後)": [(-cuff_half, cap_h + sl), (-w, cap_h)],
    }
    port_armhole = "armhole_l" if side == "左" else "armhole_r"
    port_cuff = "cuff_l" if side == "左" else "cuff_r"
    out = {
        "formulas": [
            ("袖山の高さ", "袖ぐり深さ × 0.78"),
            ("袖山の幅", f"bisect 60 iters to armhole "
                         f"{armhole_total:.1f} + ease {ease}"),
            ("袖幅 (袖口側)", f"chest / 8 + {cuff_add}"),
        ],
        "pieces": [_piece(name, outline, edges,
                          {port_armhole: ["袖山(前半)", "袖山(後半)"],
                           port_cuff: "袖口"})],
        "seams": [{"a": (name, "袖下線(前)"), "b": (name, "袖下線(後)"),
                   "label": f"袖下線: {name} の筒"}],
    }
    return out


# ---------------------------------------------------------------- ケープ
def draft_cape(measures_get, params: Dict[str, float]) -> Dict[str, Any]:
    """ケープ。**半身・わ裁ち**(前中心・後中心はわ)。

    内弧は肩点で二つに分かれる — 衿ぐり(前) と 衿ぐり(後)。**port neck
    はこの両辺を指す**(port は辺のリストを持ち得る)。扇の開き f は
    半身としての全円に対する割りで、内弧の合計が 襟ぐり周囲 に一致する
    よう半径を解く。
    """
    neck = measures_get("neck")
    cape_len = measures_get("cape_length")
    f = params.get("sector", 0.375)      # 半身の扇の開き(全円=1.0)

    r_in = neck / (2.0 * math.pi * f)
    r_out = r_in + cape_len
    steps = CAPE_ARC_STEPS
    a0, a1 = -math.pi * f, math.pi * f   # 後中心 → 前中心
    mid = steps // 2

    inner = [(r_in * math.cos(-math.pi * f + math.pi * f * 2 * i / steps),
              r_in * math.sin(-math.pi * f + math.pi * f * 2 * i / steps))
             for i in range(steps + 1)]
    outer = [(r_out * math.cos(-math.pi * f + math.pi * f * 2 * i / steps),
              r_out * math.sin(-math.pi * f + math.pi * f * 2 * i / steps))
             for i in range(steps + 1)]
    outline = inner + outer[::-1]
    edges = {
        "衿ぐり (前)": inner[mid:],
        "衿ぐり (後)": inner[:mid + 1],
        "裾": outer[::-1],
        "中心線 (前)": [inner[-1], outer[-1]],
        "中心線 (後)": [outer[0], inner[0]],
    }
    out = {
        "formulas": [
            ("ケープの内半径", f"neck / (2pi x sector {f})"),
            ("ケープの外半径", "inner radius + cape length"),
            ("扇の開き", f"{f} (half piece; full circle = 1.0; default)"),
            ("弧の分割", f"{steps} points (deterministic)"),
        ],
        "pieces": [_piece("ケープ", outline, edges,
                          {"neck": ["衿ぐり (前)", "衿ぐり (後)"],
                           "hem": "裾",
                           "center_front": "中心線 (前)",
                           "center_back": "中心線 (後)"})],
        "seams": [],
    }
    return out


# ---------------------------------------------------------- スカート(半身)
def draft_skirt_panel(measures_get, params: Dict[str, float]) -> Dict[str, Any]:
    """スカートの半身(前後の2枚・わ裁ち)。

    単体スカート(garment_skirt)の全身版とは別。**こちらは部品として
    上身頃のウエストに繋がる。** ハイローは 後身頃だけ丈を落とす。
    """
    waist = measures_get("waist")
    hip = measures_get("hip")
    L = measures_get("skirt_length")
    drop = params.get("hi_lo_drop", 0.0)
    flare = params.get("flare_ratio", 1.35)
    waist_ease = params.get("waist_ease", 2.0)
    hip_ease = params.get("hip_ease", 2.0)

    w_waist = waist / 4.0 + waist_ease
    w_hip = max(hip / 4.0 + hip_ease, w_waist)
    hem_w = w_hip * flare
    # **脇の長さは前後同長** — ハイローは中心の裾が落ちるのであって、
    # 脇が違うのではない。脇が違うと縫い合わせの検査が正しく落ちる。
    side_len = L + drop / 2.0

    out = {"formulas": [
        ("ウエスト幅 (1/4)", f"waist / 4 + {waist_ease}"),
        ("ヒップ幅 (1/4)", f"max(hip / 4 + {hip_ease}, ウエスト幅)"),
        ("裾幅", "ヒップ幅 × flare_ratio"),
        ("flare_ratio", f"{flare} (A-line; tool default)"),
        ("ハイローの落ち差", f"back hem +{drop} cm, side +{drop / 2.0} cm"
         if drop else "none (same length)"),
    ], "pieces": [], "seams": []}

    for name, center_len in (("スカート前", L), ("スカート後", L + drop)):
        hw, hh = w_waist, hem_w
        # 半身なので幅は 1/4 規格のそのまま(中心線を0に置く)。
        outline = [(0.0, 0.0), (hw, 0.0), (hh, side_len), (0.0, center_len)]
        edges = {
            "ウエスト(カーシング)": [(0.0, 0.0), (hw, 0.0)],
            "脇線": [(hw, 0.0), (hh, side_len)],
            "裾": [(hh, side_len), (0.0, center_len)],
            "中心線": [(0.0, center_len), (0.0, 0.0)],
        }
        out["pieces"].append(_piece(name, outline, edges,
                                    {"waist": "ウエスト(カーシング)",
                                     ("center_front" if name == "スカート前"
                                      else "center_back"): "中心線"}))
    out["seams"] = [
        {"a": ("スカート前", "脇線"), "b": ("スカート後", "脇線"),
         "label": "脇線: スカート前 ↔ スカート後"},
    ]
    return out
