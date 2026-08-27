# -*- coding: utf-8 -*-
"""輪郭合わせ (silhouette matching)。**写真1枚の輪郭を制約に、密着ベースを変形する。**

コーパスから型紙を引かず幾何だけで導く経路の最後の一段。人台
(``mannequin`` / ``mannequin_spline``)、密着ベース(``base_garment``、
身体の表面 + 一定オフセット)ときて、ここでは写真に写った服の輪郭に
密着ベースを合わせる ── 服は密着ベースそのものではなく、その先に写真
という証拠がある。

**画像処理はしない。** このモジュールに画像は入ってこない。入力は輪郭
── 誰か・何かが既に作った2次元の閉じた点列 ── で、写真から輪郭を
取り出す仕事はこれとは別の問題であり、別の答えを持つ。ここはその境目を
守るために多角形しか受け取らない。このリポジトリは第三者ライブラリを
一切importしない(``no_dependencies``で検査される)ので、画像デコード
自体がここでは原理的にできない。

**正直な定式化。** 正面から撮った輪郭が拘束するのは、各高さでの
「投影幅」(左右方向、x軸)だけ。奥行(z軸、カメラの光軸方向)は1視点
からは求まらない ── これは弱点ではなく、情報の形そのもの。だから、
ここでの変形は幅からだけ解く: 密着ベースの半径オフセット
(``base_garment``と同じ、半径方向へ一定量を足す近似)を、高さ方向に
「一定」ではなく「高さの関数」に一般化し、その関数(``ease(y)``)を
輪郭の幅だけから一意に決める:

    ease(y) = 輪郭の半幅(y) − 身体の半幅(y, θ=0)

全周(全θ)へ同じ ``ease(y)`` を足すので奥行も動くが、それは輪郭が
定めたのではなく、この半径オフセット・モデルの副作用 ──
``single_view_limits`` に、コメントではなく答えの一部として明記する。

**1視点でできないこと、出力自身が名乗る。** 1枚の輪郭が定める形は
visual hull の意味で上界でしかない。内側に折れたプリーツと平らな
パネルは、輪郭の上では区別がつかない ── 高さごとの走査で輪郭が2点
より多く交わっても、外側の最小・最大だけを幅として使い、内側の交点
(凹みの証拠)は捨てる。視点を増やせば(2視点・4視点)この上界は
狭まるが、ここは1視点しか受け取っていない。

**両方向で測る。** 密着ベース自身の輪郭を渡せば、リングより細かい
高さで測った残差はほぼゼロで一致するはず ── 一致しない変形は何も
一致させていない。逆に、身体より狭い輪郭(身体が入らない)や、この
オフセット・モデルの範囲を遥かに超えて広い輪郭は、
``UNKNOWN_SILHOUETTE_UNREACHABLE`` として、どの高さで・どれだけ
外れたかを名指しして拒否する ── 沈黙で諦めの悪い適合をしない。

**この先の面が要る側への接続。** ``radius_at_for()`` がこの結果から
``base_garment.build``/``flatten.build`` がそのまま ``radius_at=`` へ
渡せる関数を作る。メッシュを組む・平らにする処理はここでは複製しない
── 既にある側へ渡すだけ。``to_surface()`` はその配線の一例
(``base_garment.build`` を直接呼ぶ)。
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import base_garment as _bg
from . import mannequin as _mq

Vec2 = Tuple[float, float]
RadiusFn = Callable[[Dict[str, Any], float, float], Optional[float]]

NO_MANNEQUIN = "UNKNOWN_NO_MANNEQUIN"
BAD_RESOLUTION = "UNKNOWN_RESOLUTION_TOO_COARSE"
NO_COVERAGE = "UNKNOWN_NO_BODY_IN_REQUESTED_RANGE"
BAD_OUTLINE = "UNKNOWN_OUTLINE_DEGENERATE"
OUTLINE_GAP = "UNKNOWN_OUTLINE_NO_COVERAGE"
UNREACHABLE = "UNKNOWN_SILHOUETTE_UNREACHABLE"

#: これを割ると格子が閉じない、または三角形が1枚も作れない
#: (``base_garment``/``flatten`` と同じ下限 ── ``to_surface`` が同じ
#: ``segments``/``height_steps`` でメッシュを組むので、ここで先に断る)。
MIN_SEGMENTS = 3
MIN_HEIGHT_STEPS = 1
#: 身体はこれより狭い服を着られない ── 布は伸縮しない前提
#: (base_garment / mannequin と同じ、布の物理は計算しない)なので、
#: ease が負になる要求は拒否する。わずかな数値誤差の余地だけ許す。
MIN_EASE_CM = 0.0
#: この半径オフセット・モデル(全周へ一定量を足す)が正直に表せる
#: ゆるみの上限。**仮定。** これを超える要求(桁違いのオーバーサイズ)
#: は、この土台の平行移動では作れない ── 存在し得ないのではなく、
#: この式では届かない、という拒否。
MAX_EASE_CM = 25.0
_EPS = 1e-6
#: 残差を測る高さの密度。解いたリングの間で目標の幅がどれだけ非線形
#: でも見逃さないよう、リング数よりも細かく走査する。
PROBE_MULTIPLIER = 5


def _scan_x(outline: Sequence[Vec2], y: float) -> List[float]:
    """輪郭(閉多角形、``outline[-1]``→``outline[0]``で閉じる)を高さyで
    水平に走査し、交差するxをすべて返す(昇順)。

    区間は閉じている(``min(y0,y1) <= y <= max(y0,y1)``)。半開区間だと
    輪郭の頂点がちょうどyに乗ったとき(たとえば輪郭の一番上そのものを
    走査するとき)両側の辺のどちらからも数えられず、そこだけ幅が消える
    ── 実測でこれに当たった(``a_silhouette_constrains_only_the_
    projected_width`` の「自分自身の輪郭」テストが、リングの最上段で
    まさにここを踏む)。閉区間は共有頂点を二重に数えることがあるが、
    ``outline_width_at`` は最小・最大しか使わないので同じ値の重複は
    無害。水平な辺は無視する(幅に寄与しない)。
    """
    xs: List[float] = []
    n = len(outline)
    for i in range(n):
        x0, y0 = outline[i]
        x1, y1 = outline[(i + 1) % n]
        if y0 == y1:
            continue
        lo, hi = (y0, y1) if y0 < y1 else (y1, y0)
        if lo <= y <= hi:
            t = (y - y0) / (y1 - y0)
            xs.append(x0 + t * (x1 - x0))
    xs.sort()
    return xs


def outline_width_at(outline: Sequence[Vec2], y: float
                     ) -> Optional[Tuple[float, float]]:
    """高さyでの輪郭の幅を ``(left_x, right_x)`` で返す。交点が2点未満
    なら None(その高さに輪郭が無い)。

    **外側の交点だけを使う。** 3点以上交わっても(凹みがあっても)、
    ここでは最小と最大だけを見る ── 内側の交点は凹みの証拠であって、
    幅からは捨てる。これは visual hull が上界でしかないことの、この
    モジュールでの具体的な現れ: 凹みは幅の測定からして既に見えない。
    """
    xs = _scan_x(outline, y)
    if len(xs) < 2:
        return None
    return xs[0], xs[-1]


def _ease_interp(ring_ys: Sequence[float], ring_g: Sequence[float],
                 y: float) -> float:
    """解いたリング間を線形補間する。範囲外は最寄りの端の値で平坦に
    延長する ── 輪郭から求めた情報の外側で新しい形を発明しないための、
    base_garment/mannequinと同じ規律。"""
    if y <= ring_ys[0]:
        return ring_g[0]
    if y >= ring_ys[-1]:
        return ring_g[-1]
    for j in range(len(ring_ys) - 1):
        y0, y1 = ring_ys[j], ring_ys[j + 1]
        if y0 <= y <= y1:
            u = 0.0 if y1 == y0 else (y - y0) / (y1 - y0)
            return ring_g[j] + (ring_g[j + 1] - ring_g[j]) * u
    return ring_g[-1]


def match(man: Dict[str, Any], outline: Sequence[Vec2], *,
         radius_at: Optional[RadiusFn] = None,
         segments: int = _mq.SEGMENTS,
         height_steps: int = 16,
         y_top: Optional[float] = None,
         y_bottom: Optional[float] = None) -> Dict[str, Any]:
    """密着ベースの半径オフセットを高さの関数にし、輪郭の投影幅だけから解く。

    ``radius_at``(既定 ``mannequin.radius_at``)が身体の半径。各高さ
    リングで ``ease(y) = 輪郭の半幅 − 身体の半幅(θ=0)`` を解き、それを
    全周へ一様に足す ── ``base_garment.build`` の定数 ``gap`` を高さの
    関数に一般化したもの。

    輪郭がリングの高さを覆っていなければ ``OUTLINE_GAP``、解いた
    ``ease`` が ``[MIN_EASE_CM, MAX_EASE_CM]`` を外れれば
    ``UNREACHABLE`` ── どちらも、どの高さで・どれだけ外れたかを
    名指しして拒否する。
    """
    if man.get("verdict") != "ANSWER":
        return {"verdict": NO_MANNEQUIN,
                "why": "人台が立っていないので輪郭合わせはできません",
                "upstream_verdict": man.get("verdict")}
    if segments < MIN_SEGMENTS or height_steps < MIN_HEIGHT_STEPS:
        return {"verdict": BAD_RESOLUTION,
                "segments": segments, "height_steps": height_steps,
                "minimum_segments": MIN_SEGMENTS,
                "minimum_height_steps": MIN_HEIGHT_STEPS,
                "how_to_close": f"周方向は{MIN_SEGMENTS}以上、高さ方向は"
                                f"{MIN_HEIGHT_STEPS}以上でなければ三角形が"
                                f"1枚も作れません"}
    if (len(outline) < 3
            or any(not math.isfinite(v) for p in outline for v in p)):
        return {"verdict": BAD_OUTLINE,
                "points": len(outline),
                "why": "輪郭は少なくとも3点の有限な座標が必要です",
                "how_to_close": "3点以上の有限座標からなる閉多角形を渡して"
                                "ください"}
    ys = [p[1] for p in outline]
    if max(ys) - min(ys) <= _EPS:
        return {"verdict": BAD_OUTLINE,
                "y_extent": round(max(ys) - min(ys), 6),
                "why": "輪郭の高さがゼロで、水平に走査できません",
                "how_to_close": "高さ方向に広がりのある輪郭を渡してくださ"
                                "い"}

    rf: RadiusFn = radius_at or _mq.radius_at
    levels = man["_levels"]
    body_lo, body_hi = levels[0][0], levels[-1][0]
    want_lo = body_lo if y_bottom is None else float(y_bottom)
    want_hi = body_hi if y_top is None else float(y_top)
    lo = max(want_lo, body_lo)
    hi = min(want_hi, body_hi)
    if hi <= lo:
        return {"verdict": NO_COVERAGE,
                "requested": [want_lo, want_hi],
                "body_range": [body_lo, body_hi],
                "how_to_close": "狙った範囲に人台の身体がありません。"
                                f"人台の範囲は{body_lo:.2f}〜{body_hi:.2f}"
                                f"cmです"}

    ring_ys = [lo + (hi - lo) * j / height_steps
              for j in range(height_steps + 1)]
    missing_outline: List[float] = []
    missing_body: List[float] = []
    half_widths: List[Optional[float]] = []
    body_halfs: List[Optional[float]] = []
    for y in ring_ys:
        w = outline_width_at(outline, y)
        a = rf(man, y, 0.0)
        if w is None:
            missing_outline.append(round(y, 4))
        if a is None:
            missing_body.append(round(y, 4))
        half_widths.append(None if w is None else (w[1] - w[0]) / 2.0)
        body_halfs.append(a)

    if missing_body:
        return {"verdict": NO_COVERAGE,
                "requested": [round(lo, 4), round(hi, 4)],
                "body_range": [body_lo, body_hi],
                "missing_heights": missing_body,
                "how_to_close": "この高さ域には radius_at が身体を返しませ"
                                "ん。人台の範囲を狭めてください"}
    if missing_outline:
        return {"verdict": OUTLINE_GAP,
                "requested": [round(lo, 4), round(hi, 4)],
                "missing_heights": missing_outline,
                "ring_count": len(ring_ys),
                "why": f"{len(missing_outline)}/{len(ring_ys)} 本のリングで"
                       f"輪郭が水平走査に交わりませんでした",
                "how_to_close": "密着ベースが覆う高さ全体([{:.2f}, "
                                "{:.2f}])を覆う輪郭を渡すか、y_top/"
                                "y_bottomで範囲を絞ってください"
                                .format(lo, hi)}

    eases = [hw - a for hw, a in zip(half_widths, body_halfs)]
    violations = []
    for y, e, a, hw in zip(ring_ys, eases, body_halfs, half_widths):
        if e < MIN_EASE_CM - _EPS:
            violations.append({"y": round(y, 4), "ease_cm": round(e, 4),
                               "bound": "min", "bound_cm": MIN_EASE_CM,
                               "over_by_cm": round(MIN_EASE_CM - e, 4),
                               "target_half_width_cm": round(hw, 4),
                               "body_half_width_cm": round(a, 4)})
        elif e > MAX_EASE_CM + _EPS:
            violations.append({"y": round(y, 4), "ease_cm": round(e, 4),
                               "bound": "max", "bound_cm": MAX_EASE_CM,
                               "over_by_cm": round(e - MAX_EASE_CM, 4),
                               "target_half_width_cm": round(hw, 4),
                               "body_half_width_cm": round(a, 4)})
    if violations:
        worst = max(violations, key=lambda v: v["over_by_cm"])
        return {"verdict": UNREACHABLE,
                "violations": violations,
                "worst": worst,
                "min_ease_cm": MIN_EASE_CM, "max_ease_cm": MAX_EASE_CM,
                "why": f"{len(violations)}/{len(ring_ys)} 本のリングで、幅"
                       f"だけから解いた ease が [{MIN_EASE_CM}, "
                       f"{MAX_EASE_CM}]cm を外れました。最悪は y="
                       f"{worst['y']}cm で {worst['bound']} を "
                       f"{worst['over_by_cm']}cm 超過(ease="
                       f"{worst['ease_cm']}cm)",
                "how_to_close": (
                    "min側の超過は、身体よりこの高さで狭い輪郭を渡してい"
                    "ます ── 身体は入りません。max側の超過は、この一定"
                    "半径オフセット・モデルが正直に表せるゆるみを超えて"
                    "います ── ダーツやタックなど別の構造が必要な形です")}

    # ---- 残差: リングより細かい高さで、輪郭の実測幅と比較する --------
    probe_n = height_steps * PROBE_MULTIPLIER
    probe_ys = [lo + (hi - lo) * k / probe_n for k in range(probe_n + 1)]
    devs: List[float] = []
    probe_gaps = 0
    for y in probe_ys:
        w = outline_width_at(outline, y)
        a = rf(man, y, 0.0)
        if w is None or a is None:
            probe_gaps += 1
            continue
        true_width = w[1] - w[0]
        model_width = 2.0 * (a + _ease_interp(ring_ys, eases, y))
        devs.append(abs(model_width - true_width))
    max_dev = max(devs) if devs else 0.0
    mean_dev = (sum(devs) / len(devs)) if devs else 0.0

    return {
        "verdict": "ANSWER",
        "what": ("skin-tight base garment deformed so its projected width "
                 "matches a front-view silhouette outline; depth follows "
                 "the same radial ease as a byproduct, not a measurement"),
        "segments": segments, "height_steps": height_steps,
        "y_range_used": [round(lo, 4), round(hi, 4)],
        "ease_by_height_cm": [[round(y, 4), round(e, 4)]
                              for y, e in zip(ring_ys, eases)],
        "ease_range_cm": [round(min(eases), 4), round(max(eases), 4)],
        "min_ease_cm": MIN_EASE_CM, "max_ease_cm": MAX_EASE_CM,
        "width_residual_cm": {
            "max": round(max_dev, 6), "mean": round(mean_dev, 6),
            "probe_count": len(devs), "probe_total": probe_n + 1,
            "probe_gaps": probe_gaps,
        },
        "single_view_limits": {
            "depth_unconstrained_by_this_view": (
                "正面の輪郭1枚が拘束するのは各高さの投影幅(左右)だけで"
                "す。奥行(カメラの光軸方向)はここからは求まりません。"
                "ease(y)は幅だけから解き、それを全周へ一様に足すので奥行"
                "も動きますが、それは輪郭が定めた値ではなく、この半径オ"
                "フセット・モデルの副作用です"),
            "visual_hull_is_an_upper_bound": (
                "1視点の輪郭が定める形は visual hull の意味で上界でしか"
                "ありません。内側に折れたプリーツと平らなパネルは輪郭の"
                "上で区別がつきません。視点を増やせば(2視点・4視点)こ"
                "の上界は狭まりますが、ここは1視点しか受け取っていませ"
                "ん"),
            "outline_scan_keeps_only_the_outer_extent": (
                "高さごとの水平走査で交点が2点より多くても、外側の最小"
                "・最大だけを幅として使い、内側の交点(凹みの証拠)は捨"
                "てています ── upper boundの具体的な現れです"),
        },
        "no_image_processing": (
            "入力は輪郭(2次元点列)そのものです。写真からこの輪郭を取"
            "り出す仕事はここには含まれません ── 別の問題、別の答えで"
            "す。このリポジトリは第三者ライブラリを一切importしません"),
        "generated_not_evidence": (
            "この ease(y) と残差は生成物です。観測の出典にはなりませ"
            "ん。布の挙動(伸縮・張り・重なり)は計算していません"),
    }


def radius_at_for(result: Dict[str, Any], *,
                  base_radius_at: Optional[RadiusFn] = None) -> RadiusFn:
    """``match`` のANSWERから、``base_garment.build``/``flatten.build``が
    そのまま ``radius_at=`` へ渡せる関数を作る。メッシュを組む処理はここ
    では複製しない ── 既にある側(``base_garment``/``flatten``)へ渡す
    だけ。

    ``result`` が ``ANSWER`` でなければ ``ValueError``。呼ぶ側は
    ``match`` の verdict を先に見ているはずで、拒否された結果から面を
    作ろうとするのはこの関数の責任ではなく呼ぶ側の誤り ── 他の ``_at``
    関数群と違い typed な UNKNOWN を返さないのは、これは幾何の答えでは
    なく配線の道具だから。
    """
    if result.get("verdict") != "ANSWER":
        raise ValueError("cannot build a radius_at from a non-ANSWER match "
                         f"result: {result.get('verdict')}")
    rf: RadiusFn = base_radius_at or _mq.radius_at
    pairs = result["ease_by_height_cm"]
    ring_ys = [p[0] for p in pairs]
    ring_g = [p[1] for p in pairs]

    def _fn(man: Dict[str, Any], y: float, theta: float) -> Optional[float]:
        r = rf(man, y, theta)
        if r is None:
            return None
        return r + _ease_interp(ring_ys, ring_g, y)
    return _fn


def to_surface(result: Dict[str, Any], man: Dict[str, Any], *,
              base_radius_at: Optional[RadiusFn] = None,
              gap: float = 0.0) -> Dict[str, Any]:
    """輪郭合わせの結果を実際のメッシュにする便宜関数。**新しいメッシュ
    構築は書かない** ── ``radius_at_for`` で作った関数を
    ``base_garment.build`` へそのまま渡すだけの配線。パネル側
    (``flatten.build``)が要るのも同じ関数なので、そちらへ渡してもよい
    ── ここは一例。
    """
    if result.get("verdict") != "ANSWER":
        return dict(result)
    rf = radius_at_for(result, base_radius_at=base_radius_at)
    y_lo, y_hi = result["y_range_used"]
    return _bg.build(man, gap=gap, segments=result["segments"],
                     height_steps=result["height_steps"],
                     y_top=y_hi, y_bottom=y_lo, radius_at=rf)
