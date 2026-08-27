# -*- coding: utf-8 -*-
"""密着ベース(skin-tight base garment)。**人台の表面 + 一定オフセット。**

コーパスから型紙を引く経路(``sewing_search`` / ``garment_pattern``)とは
別の、幾何だけで導く経路の第二段。第一段は人台(``mannequin`` /
``mannequin_spline``)、第三段はこれを平らにする ``flatten``。ここでは
その間 — 人台の表面を法線方向に一定量(空気層 ``gap``)だけ押し出した
面を作る。これがドレスやコートの「土台」で、この上にゆとり・ダーツ・
デザイン線が乗る(乗せる側はまだ無い — このモジュールは土台だけ)。

**押し出しは半径方向。** 法線ベクトルではなく ``mannequin`` と同じ
(x,y,z) = (r cosθ, y, r sinθ) の r に gap を足す。人台の断面は楕円なので
真の法線は半径方向とわずかにずれる — この単純化は
``mannequin.dress`` が既にしているものと同じで、ここで新しく持ち込んだ
近似ではない。

**身体が無い高さには広げない。** 半径関数(既定 ``mannequin.radius_at``)
は身体の無い高さで None を返す。ロングコートのように人台の範囲より
下まで作ろうとしても、その先には身体が無いので押し出す相手がいない —
外挿で形を発明せず、リングを作らずに落とす。落としたリングの数と、
実際に使われた範囲は出力に必ず載る。
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import mannequin as _mq

Vec3 = Tuple[float, float, float]
Face = Tuple[int, int, int, int]
RadiusFn = Callable[[Dict[str, Any], float, float], Optional[float]]

NO_MANNEQUIN = "UNKNOWN_NO_MANNEQUIN"
NO_COVERAGE = "UNKNOWN_NO_BODY_IN_REQUESTED_RANGE"
BAD_RESOLUTION = "UNKNOWN_RESOLUTION_TOO_COARSE"

#: これを割ると格子が閉じない、または三角形が1枚も作れない。
MIN_SEGMENTS = 3
MIN_HEIGHT_STEPS = 1


def build(man: Dict[str, Any], *,
          gap: float = _mq.GAP_CM,
          segments: int = _mq.SEGMENTS,
          height_steps: int = 16,
          y_top: Optional[float] = None,
          y_bottom: Optional[float] = None,
          radius_at: Optional[RadiusFn] = None) -> Dict[str, Any]:
    """人台の表面を ``gap`` だけ外に押し出した密着ベースの面を作る。

    ``y_top``/``y_bottom`` を渡すと、その範囲を狙う(既定は人台の全域
    ``levels[0][0]``〜``levels[-1][0]``)。狙った範囲が人台の範囲より
    外に出ていたら、**その分だけ切り詰める** — 身体の無い高さのリングは
    作らず、``clipped_top``/``clipped_bottom`` に切り詰めた量(cm)を
    載せる。これはロングコートの裾が人台の下に出る場合の、この関数の
    唯一の答え方: 発明ではなく境界。

    ``radius_at`` を渡すと、その半径関数(``mannequin_spline.radius_at``
    など)を使う人台の上にベースを作る。既定は ``mannequin.radius_at``。
    """
    if man.get("verdict") != "ANSWER":
        return {"verdict": NO_MANNEQUIN,
                "why": "人台が立っていないのでベースは作れません",
                "upstream_verdict": man.get("verdict")}
    if segments < MIN_SEGMENTS or height_steps < MIN_HEIGHT_STEPS:
        return {"verdict": BAD_RESOLUTION,
                "segments": segments, "height_steps": height_steps,
                "minimum_segments": MIN_SEGMENTS,
                "minimum_height_steps": MIN_HEIGHT_STEPS,
                "how_to_close": f"周方向は{MIN_SEGMENTS}以上、高さ方向は"
                                f"{MIN_HEIGHT_STEPS}以上でなければ三角形が"
                                f"1枚も作れません"}
    rf: RadiusFn = radius_at or _mq.radius_at
    levels = man["_levels"]
    body_lo, body_hi = levels[0][0], levels[-1][0]

    want_lo = body_lo if y_bottom is None else float(y_bottom)
    want_hi = body_hi if y_top is None else float(y_top)
    lo = max(want_lo, body_lo)
    hi = min(want_hi, body_hi)
    clipped_bottom = round(max(0.0, lo - want_lo), 4)
    clipped_top = round(max(0.0, want_hi - hi), 4)
    if hi <= lo:
        return {"verdict": NO_COVERAGE,
                "requested": [want_lo, want_hi],
                "body_range": [body_lo, body_hi],
                "how_to_close": "狙った範囲に人台の身体がありません。"
                                f"人台の範囲は{body_lo:.2f}〜{body_hi:.2f}"
                                f"cmです"}

    rings_y = [lo + (hi - lo) * j / height_steps for j in range(height_steps + 1)]
    verts: List[Vec3] = []
    faces: List[Face] = []
    ring_base: List[Optional[int]] = []
    dropped = 0
    for y in rings_y:
        ring: List[Vec3] = []
        ok = True
        for i in range(segments):
            theta = 2.0 * math.pi * i / segments
            r = rf(man, y, theta)
            if r is None:
                ok = False
                break
            surface = r + gap
            ring.append((surface * math.cos(theta), y, surface * math.sin(theta)))
        if not ok:
            dropped += 1
            ring_base.append(None)
            continue
        ring_base.append(len(verts))
        verts.extend(ring)

    for j in range(len(rings_y) - 1):
        b0, b1 = ring_base[j], ring_base[j + 1]
        if b0 is None or b1 is None:
            continue
        for i in range(segments):
            k = (i + 1) % segments
            faces.append((b0 + i, b0 + k, b1 + k, b1 + i))

    present_ys = [y for y, b in zip(rings_y, ring_base) if b is not None]
    if not present_ys:
        return {"verdict": NO_COVERAGE,
                "requested": [want_lo, want_hi],
                "body_range": [body_lo, body_hi],
                "how_to_close": "求めた解像度では身体のあるリングが1本も"
                                "取れませんでした"}

    return {
        "verdict": "ANSWER",
        "what": "skin-tight base garment (body surface + constant offset)",
        "gap_cm": gap,
        "segments": segments, "height_steps": height_steps,
        "verts": verts, "faces": faces,
        "vertices": len(verts), "faces_count": len(faces),
        "y_range_requested": [round(want_lo, 4), round(want_hi, 4)],
        "y_range_used": [round(min(present_ys), 4), round(max(present_ys), 4)],
        "body_range": [round(body_lo, 4), round(body_hi, 4)],
        "clipped_bottom_cm": clipped_bottom,
        "clipped_top_cm": clipped_top,
        "rings_dropped_for_no_body": dropped,
        "ends_where_the_body_ends": (
            "要求した範囲が人台の範囲を超えていたら、その先へ押し出さず"
            "リングを作りません。clipped_bottom_cm / clipped_top_cm が"
            "0より大きいのは、コートの裾のように身体の無い高さまで"
            "狙ったとき — 発明した形ではなく、要求のうち作れなかった"
            "量です"),
        "offset_is_radial_not_normal": (
            "押し出しは(x,y,z)=(r cosθ, y, r sinθ)のrにgapを足す半径"
            "方向で、楕円断面の真の法線とはわずかにずれます。"
            "mannequin.dress と同じ簡略化で、ここで新しく持ち込んだ"
            "ものではありません"),
        "generated_not_evidence": (
            "この面は生成物です。観測の出典にはなりません。布の厚み・"
            "張り・重なりは計算していません"),
    }


def to_obj(verts: Sequence[Vec3], faces: Sequence[Face]) -> str:
    """``mannequin.to_obj`` と同じ書式(OBJ, quad面)。密着ベース単体を
    見るための書き出しで、ここにも物理の主張はない。"""
    out = ["# skin-tight base garment (generated)", "o base_garment"]
    for v in verts:
        out.append(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}")
    for f in faces:
        out.append(f"f {f[0]+1} {f[1]+1} {f[2]+1} {f[3]+1}")
    return "\n".join(out) + "\n"
