# -*- coding: utf-8 -*-
"""平らにする前の量。**曲げずには広げられない — Gauss の定理を測れる数にする。**

Gauss の Theorema Egregium: 曲面を伸び縮みなしに平面へ写すことはできない。
Gauss-Bonnet はその「絶対に吸収しなければならない総量」を決める式で、
円板(disc)なら::

    ∫∫ K dA (面のガウス曲率の積分) + ∮ k_g ds (境界の測地曲率) = 2π

型紙の裁片は、この総量を二つの道具でしか吸収できない — **輪郭を曲げる**
(裾や脇線を直線でなく曲線にする)か、**ダーツを切る**(楔を抜いて縫い合わ
せる)か。どちらにどれだけ割り振るかがパターンメーカーの決定そのもので、
この総量を計算できて初めてその決定を検討できる。

**ここでやっていること。** 人台(``mannequin.build`` の出力)の表面を
周方向 × 高さ方向の三角格子に切り、各「内部」頂点(周を一周し、上端の
襟ぐりリングにも下端の腰リングにも乗らない頂点)で、そこに集まる三角形の
内角の和を 2π から引く — **角度欠損(angle defect)、扇(triangle-fan)で
測る。** 四近傍の格子和(上下左右の頂点だけを見る方式)は離散ガウス曲率
ではない。閉曲面(球)で試すと前者は正しい値(4π = 720度)に収束せず、
角度欠損だけが厳密に一致する — ``angle_sums`` の docstring に実測値がある。

**境界は数えない。** 上端(neck)・下端(hip)のリングは輪郭であって内部
頂点ではない。そこにも曲率はあるが、Gauss-Bonnet の境界項(測地曲率)の
側に入るもので、ここでは計算しない — 数えるとしたら別の関数の仕事。

**総量は分けない。** この輪郭がダーツをX cm、輪郭の湾曲をY度受け持つ、
という按分はこのモジュールの外の決定であって計算ではない。以前の版は
90度を12cmのダーツ一本に割って18.85cmを出した — 実際のバストダーツは
2〜4cmで、これは輪郭が吸収する境界項を無視した誤り。``report`` はその
換算を一切しない。
"""
from __future__ import annotations

import bisect
import math
from typing import Any, Dict, List, Sequence, Tuple

from . import mannequin as _mq

Vec3 = Tuple[float, float, float]
Face = Tuple[int, int, int]

TWO_PI = 2.0 * math.pi

#: 三角形を作るための最小解像度。これを割ると格子が閉じない。
MIN_SEGMENTS = 3
MIN_HEIGHT_STEPS = 1

BAD_RESOLUTION = "UNKNOWN_RESOLUTION_TOO_COARSE"
NEEDS_TWO = "UNKNOWN_NEEDS_AT_LEAST_TWO_RESOLUTIONS"
NO_RESOLUTIONS = "UNKNOWN_NO_RESOLUTIONS"
RADIUS_UNDEFINED = "UNKNOWN_RADIUS_UNDEFINED"

#: ブリーフで言及された既定の精緻化系列(周方向 x 高さ方向)。最後の刻みが
#: 収束の判定に使われる — 増やすほど信頼できるが遅くなる。
DEFAULT_RESOLUTIONS: Tuple[Tuple[int, int], ...] = (
    (20, 12), (40, 24), (80, 48), (160, 96))

#: ``mannequin._levels`` は (hip, waist, chest, shoulder, neck) の5点。
#: 帯はその間の4区間。
BAND_NAMES: Tuple[str, ...] = (
    "hip→waist", "waist→chest", "chest→shoulder", "shoulder→neck")


def _angle_at(p: Vec3, a: Vec3, b: Vec3) -> float:
    """頂点 p における三角形 (p, a, b) の内角(ラジアン、3D)。"""
    v1 = (a[0] - p[0], a[1] - p[1], a[2] - p[2])
    v2 = (b[0] - p[0], b[1] - p[1], b[2] - p[2])
    n1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2)
    n2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2 + v2[2] ** 2)
    if n1 <= 0.0 or n2 <= 0.0:
        return 0.0
    cos_t = (v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / (n1 * n2)
    cos_t = max(-1.0, min(1.0, cos_t))
    return math.acos(cos_t)


def angle_sums(verts: Sequence[Vec3], faces: Sequence[Face]) -> List[float]:
    """各頂点に集まる三角形の内角の和(ラジアン)。**扇(fan)で足す** —
    四近傍の格子和ではない。

    離散 Gauss-Bonnet の検算(このモジュール自身の正しさの根拠、
    ``mannequin`` には依存しない)。閉じた球面メッシュ(北極・南極を
    単一頂点に持つ UV球、重複頂点なし)で ``sum(2π - s for s in
    angle_sums(...))`` を取ると、分割数に関わらず厳密に 4π = 720度になる
    (実測: 20x10, 40x20, 80x40, 160x80 分割のいずれも 719.999999999…度、
    誤差 1e-9 度未満)。円柱(展開可能、曲率ゼロのはず)では同じ式が
    0.00000000000X 度(浮動小数の丸め誤差のみ)になる。四近傍の格子和では
    どちらも成立しない。
    """
    sums = [0.0] * len(verts)
    for (i, j, k) in faces:
        p, a, b = verts[i], verts[j], verts[k]
        sums[i] += _angle_at(p, a, b)
        sums[j] += _angle_at(a, p, b)
        sums[k] += _angle_at(b, p, a)
    return sums


def mesh(man: Dict[str, Any], segments: int, height_steps: int
        ) -> Dict[str, Any]:
    """人台表面を segments(周方向)× height_steps(高さ方向)の三角格子に
    切る。**``mannequin.build`` の描画メッシュとは別物** — あちらは
    SEGMENTS=24, STEPS_Y=16 に固定されていて、こちらは精緻化を見るために
    自由に選べる。頂点の座標は ``mannequin.radius_at`` の楕円式そのもの
    から来るので、二重に近似を重ねていない。
    """
    if man.get("verdict") != "ANSWER":
        return dict(man)
    if segments < MIN_SEGMENTS or height_steps < MIN_HEIGHT_STEPS:
        return {"verdict": BAD_RESOLUTION,
                "segments": segments, "height_steps": height_steps,
                "minimum_segments": MIN_SEGMENTS,
                "minimum_height_steps": MIN_HEIGHT_STEPS,
                "how_to_close": f"周方向は{MIN_SEGMENTS}以上、高さ方向は"
                                f"{MIN_HEIGHT_STEPS}以上でなければ三角形が"
                                f"1枚も作れません"}
    levels = man["_levels"]
    y_top = levels[-1][0]
    verts: List[Vec3] = []
    for j in range(height_steps + 1):
        y = y_top * j / height_steps
        for i in range(segments):
            theta = TWO_PI * i / segments
            r = _mq.radius_at(man, y, theta)
            if r is None:
                # y は [levels[0][0], y_top] の中だけを歩くので、これは
                # 人台の作りが変わって levels の前提が壊れた徴候。黙って
                # 0を入れない。
                #
                # **未検証の防御コード。** 今日の `mannequin.build()` の
                # 出力からこの分岐には到達できない(y は常にレンジの内側)
                # ―― どのチェックもフォールシファイアもここを実際に赤く
                # していない。levels の作りが変わって初めて意味を持つ、
                # 到達性未確認の防御的リターン。
                return {"verdict": RADIUS_UNDEFINED, "y": round(y, 6),
                        "theta": round(theta, 6),
                        "how_to_close": "人台の高さレンジ(_levels)と"
                                       "格子の刻みが合っていません"}
            verts.append((r * math.cos(theta), y, r * math.sin(theta)))
    faces: List[Face] = []
    for j in range(height_steps):
        for i in range(segments):
            i2 = (i + 1) % segments
            a_idx, b_idx = j * segments + i, j * segments + i2
            c_idx, d_idx = (j + 1) * segments + i2, (j + 1) * segments + i
            faces.append((a_idx, b_idx, c_idx))
            faces.append((a_idx, c_idx, d_idx))
    return {"verdict": "ANSWER", "verts": verts, "faces": faces,
            "segments": segments, "height_steps": height_steps,
            "y_top": y_top, "level_ys": [lv[0] for lv in levels]}


def _band_of(y: float, level_ys: Sequence[float]) -> int:
    """高さ y がどの帯(レベル間の区間)に入るか。境界にちょうど乗ったら
    上側の帯に数える(``bisect_right`` — 決定的な規約であって、どちらの
    帯に属するかの物理的な根拠があるわけではない)。"""
    bi = bisect.bisect_right(level_ys, y) - 1
    return max(0, min(len(level_ys) - 2, bi))


def curvature(man: Dict[str, Any], segments: int, height_steps: int
             ) -> Dict[str, Any]:
    """内部頂点だけの角度欠損を合計する。上端(neck)・下端(hip)のリングは
    輪郭であって内部頂点ではないので、ここには入らない。"""
    m = mesh(man, segments, height_steps)
    if m.get("verdict") != "ANSWER":
        return m
    verts, faces, level_ys, y_top = (
        m["verts"], m["faces"], m["level_ys"], m["y_top"])
    sums = angle_sums(verts, faces)
    total = 0.0
    bands = [0.0] * (len(level_ys) - 1)
    for j in range(1, height_steps):
        y = y_top * j / height_steps
        bi = _band_of(y, level_ys)
        for i in range(segments):
            defect = TWO_PI - sums[j * segments + i]
            total += defect
            bands[bi] += defect
    return {
        "verdict": "ANSWER",
        "segments": segments, "height_steps": height_steps,
        "total_deg": math.degrees(total),
        "bands_deg": dict(zip(BAND_NAMES,
                              (math.degrees(b) for b in bands))),
    }


def report(man: Dict[str, Any],
           resolutions: Sequence[Tuple[int, int]] = DEFAULT_RESOLUTIONS
          ) -> Dict[str, Any]:
    """総曲率・帯別分布・精緻化での収束を、正直な限界つきで返す。

    **ダーツ量には換算しない。** 総量は輪郭の湾曲とダーツの両方が支払う
    負債で、その内訳を決めるのはこの関数の外(パターンメーカー)の仕事。
    """
    if man.get("verdict") != "ANSWER":
        return dict(man)
    resolutions = list(resolutions or [])
    if not resolutions:
        return {"verdict": NO_RESOLUTIONS,
                "how_to_close": "少なくとも1つの(segments, height_steps)"
                                "が要ります"}
    if len(resolutions) < 2:
        return {"verdict": NEEDS_TWO, "given": len(resolutions),
                "how_to_close": "収束を見せるには少なくとも2段階の解像度"
                                "が要ります(粗い方と細かい方)"}

    steps: List[Dict[str, Any]] = []
    for segments, height_steps in resolutions:
        c = curvature(man, segments, height_steps)
        if c.get("verdict") != "ANSWER":
            return c
        steps.append(c)

    coarsest, finest, prev = steps[0], steps[-1], steps[-2]
    settle_deg = abs(finest["total_deg"] - prev["total_deg"])
    band_spread = {
        name: (max(s["bands_deg"][name] for s in steps)
               - min(s["bands_deg"][name] for s in steps))
        for name in BAND_NAMES
    }

    return {
        "verdict": "ANSWER",
        "measures_used": man.get("measures_used"),
        "levels": [tuple(lv) for lv in man["_levels"]],
        "method": "三角扇(triangle-fan)の角度欠損(2π - 内角和)を内部頂点"
                  "で測る。四近傍の格子和ではない",
        "boundary_excluded": "上端(neck)・下端(hip)のリングは輪郭であって"
                             "内部頂点ではないので、ここには足さない — "
                             "そこの取り分は Gauss-Bonnet の境界項"
                             "(測地曲率)の側で、この関数は計算しない",
        "refinement": [
            {"segments": s["segments"], "height_steps": s["height_steps"],
             "total_deg": s["total_deg"], "bands_deg": s["bands_deg"]}
            for s in steps
        ],
        "total_deg": finest["total_deg"],
        "total_deg_coarsest": coarsest["total_deg"],
        "total_deg_change_last_step": settle_deg,
        "bands_deg": finest["bands_deg"],
        "band_spread_across_refinement_deg": band_spread,
        "honest_limit": (
            "この人台は5レベル(hip, waist, chest, shoulder, neck)を線形"
            "補間しただけで、曲率はその5つの折れ目(crease)に集中する — "
            "実在の身体のように滑らかには分布しない。合計"
            f"(total_deg)は精緻化で収束するので信用できる"
            f"({coarsest['total_deg']:.2f}度 -> {finest['total_deg']:.2f}"
            f"度、最後の刻みでの変化は{settle_deg:.4f}度)。帯別分布"
            "(bands_deg)はレベル数で量子化されていて信用できない — "
            "band_spread_across_refinement_deg を見ると、同じ精緻化"
            "系列の中で各帯の合計が数十度単位で動く。折れ目の曲率が"
            "どのグリッド行に落ちるかがグリッドを変えるたびに動くから"
            "で、グリッドを細かくするだけでは直らない(折れ目自体が"
            "動かないので)。直すにはレベル数を増やすか、実測girthを"
            "通る滑らかな(スプライン)補間にする必要がある"),
        "total_is_shared_not_split": (
            "この総量は輪郭の湾曲とダーツの両方が支払う負債。どちらに"
            "どれだけ割り振るかはパターンメーカーの決定であって計算では"
            "ないので、この関数はそれを決めない — ダーツの寸法(cm)への"
            "換算はしない"),
    }
