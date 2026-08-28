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
オフセット・モデルの範囲を遥かに超えて広い輪郭は、**止めない。**
``structure_hints`` にどの高さで・どれだけ・どちら側(締める/離れて
立つ)かを名指しして、``ANSWER`` のまま返す。以前はここで
``UNKNOWN_SILHOUETTE_UNREACHABLE`` を返して止めていたが、それは
「作れない」という嘘だった ── コルセットもケープも実在し、縫える。
この一定半径オフセット・モデルが表せないのは面の形であって、服の
存在ではない。沈黙で諦めの悪い適合をしないのは変わらない: 一致しない
高さを黙って一致したことにはしない。ただし「一致しない」の返し方が
拒否から分類に変わった。

**身体が無い高さでも、幅は写真に写っている。** ``mannequin.radius_at``
は人台の腰〜襟ぐりの外で ``None`` を返す ── そこには身体が無いから、
というのが ``mannequin`` にとっての正直な答え。だが輪郭という証拠は
そこにも写っている: スカートのフレア・裾は腰より下、襟や高い衿は
襟ぐりより上にあり、投影幅(x方向)は依然として輪郭が測っている。
無いのは奥行(z方向)だけ。``y_top``/``y_bottom`` で人台の範囲より
広い範囲を明示的に要求すると、身体が無い高さでは ``ease`` モデル
(身体の半径 + 一定量)を使わず、代わりに ── その高さの輪郭の半幅を
そのまま断面の幅半径(``a``)にし、奥行半径(``b``)は最寄りの実在する
断面の前後比を運んで ``b = a × ratio`` で作る楕円を置く。「最寄り」
とは、腰より下では ``_levels[0]``(腰)、襟ぐりより上では
``_levels[-1]``(襟ぐり)── **どちらも ``_levels`` から読む値であって、
``mannequin.DEPTH_RATIO`` という定数を書き写したものではない**(今の
``mannequin.build`` ではその定数から作られた値と一致するが、比を
高さごとに測る実装に変わっても、ここは読み直すだけで追随する)。

**この仮定が壊れる場所を測った。** 前後比0.700を裾までそのまま運ぶ
のは、裾の断面が実際には円に近づく(サーキュラースカートなら
比→1.0)ときに最悪になる。実測: 合成の裾(半幅46.04cm、前後比が
1.0に近づくと仮定)に0.700を運ぶと、奥行半径は32.23cmと出る ──
真の値46.04cmに対して13.81cm・**30%の過小評価**。腰に近い高さほど
比0.700は妥当に近づき(そこでの実測はそもそも0.700そのもの)、裾に
近づくほど誤差は増える。この誤差そのものは輪郭に写っていない ──
1視点の限界の、もう一つの具体的な現れ。襟ぐりより上(衿・立ち衿など)
は比の値は同じ式で読めるが、その先が本当に胴の延長(楕円が滑らかに
続く)である保証はもっと弱い ── 衿は骨格が違う。読める、という
チェック可能性はあるが、この高さでの物理的な妥当性は腰下より弱いと
ここで明記しておく。

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
#: **2026-08-28 に判定から分類へ変えた。** 服がこの二つの境界を跨ぐのは
#: 失敗ではなく、そこにある構造の名前だった ── ease が負なら、服は
#: 身体を締めている(コルセット・補整)。ease が MAX_EASE_CM を超えるなら、
#: 服は身体から離れて立っている(ケープ・マント・パフスリーブ)。どちらも
#: 実在し、縫える。この一定半径オフセット・モデル(全周へ一様な量を足す
#: だけ)では**面としては**まだ書けない、というだけで、それは服について
#: 何も言っていない ── この式の表現力についての事実。
#:
#: 以前はここで ``UNKNOWN_SILHOUETTE_UNREACHABLE`` を返して止まっていた。
#: 「作れません」は嘘だった: ``docs/`` のアニメ服の実測で、肩ケープが
#: y=47.74cmで ease 46.76cm(上限25を21.76cm超過)を要求した。ケープは
#: 実在する。作れないのは面の表し方の方で、服の方ではない。
#:
#: 境界そのものは変えていない。MIN=0.0(身体はこれより負のeaseを
#: 力学的には保持できない ── 締める場合は身体が変形する側の話で、
#: 面のオフセットの話ではない)、MAX=25.0(依然として根拠のない**仮定**
#: だが、判定の敷居ではなく分類の敷居になったので、外れても止まらない)。
MIN_EASE_CM = 0.0
MAX_EASE_CM = 25.0
#: 分類の名前。負のease、範囲内、上限超過の三つ。
COMPRESSION = "compression"
FITTED = "fitted"
STANDOFF = "standoff"
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

    輪郭がリングの高さを覆っていなければ ``OUTLINE_GAP`` で拒否する。
    解いた ``ease`` が ``[MIN_EASE_CM, MAX_EASE_CM]`` を外れても、
    もう拒否はしない ── ``structure_hints`` にどの高さで・どれだけ
    ``compression``(締める)か ``standoff``(離れて立つ)かを名指しして
    ``ANSWER`` を返す。境界内は ``fitted``。``ring_class_counts`` が
    3分類それぞれの本数を持つ。

    ``y_top``/``y_bottom`` が人台の範囲(``_levels[0][0]``〜
    ``_levels[-1][0]``)より外へ出ると、その分は ``ease`` モデルではなく
    モジュールdocstringの「身体が無い高さでも、幅は写真に写っている」
    節の楕円モデルで解く ── 輪郭の半幅と、最寄りの実在する断面
    (腰 or 襟ぐり)から読んだ前後比だけを使う。この拡張ゾーンで輪郭が
    足りなければ、身体ゾーンと同じ ``OUTLINE_GAP``。比が定義できない
    (``_levels`` の該当する幅がゼロ)なら ``NO_COVERAGE`` ── どちらも
    どの高さで足りないかを名指しする。``y_top``/``y_bottom`` を省略
    した既定呼び出しは今までと完全に同じ(人台の範囲だけ)で、この
    拡張は一切働かない。
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
    #: **分類、拒否ではない。** 各リングの ease がどちらの境界の外にある
    #: かを名指しするだけで、ここでは何も止めない。止めていた頃の
    #: ``UNREACHABLE``/``violations`` という名前は、実在する構造(締める・
    #: 離れて立つ)を「届かない」と誤って呼んでいた。
    ring_classes: List[str] = []
    structure_hints: List[Dict[str, Any]] = []
    for y, e, a, hw in zip(ring_ys, eases, body_halfs, half_widths):
        if e < MIN_EASE_CM - _EPS:
            ring_classes.append(COMPRESSION)
            structure_hints.append({
                "y": round(y, 4), "ease_cm": round(e, 4),
                "classification": COMPRESSION,
                "compress_by_cm": round(MIN_EASE_CM - e, 4),
                "target_half_width_cm": round(hw, 4),
                "body_half_width_cm": round(a, 4),
                "why": "この高さで輪郭は身体より狭い。服が身体を締めてい"
                       "ます ── コルセット・補整・タイトな伸縮素材といっ"
                       "た、身体側を変形させる構造が要ります。この土台は"
                       "剛体の人台なので、締める側の変形はここでは表現し"
                       "ません: 圧縮量を記録するところまでがこの関数の仕"
                       "事です",
            })
        elif e > MAX_EASE_CM + _EPS:
            ring_classes.append(STANDOFF)
            structure_hints.append({
                "y": round(y, 4), "ease_cm": round(e, 4),
                "classification": STANDOFF,
                "standoff_by_cm": round(e - MAX_EASE_CM, 4),
                "target_half_width_cm": round(hw, 4),
                "body_half_width_cm": round(a, 4),
                "why": "この高さで輪郭は、一定半径オフセット・モデルが正"
                       "直に表せるゆるみを超えて身体から離れています ──"
                       "ケープ・マント・パフスリーブといった、身体から離"
                       "れて別の支持を持つ構造です。この面モデル(全周へ"
                       "一様な量を足すだけ)ではこの高さの面を書けません"
                       "── 服が存在しないのではなく、この式の表現力の外"
                       "です",
            })
        else:
            ring_classes.append(FITTED)

    # ---- 拡張ゾーン: 要求範囲が人台の範囲より外に出ている分 -----------
    # ``want_lo``/``want_hi`` は既定では ``body_lo``/``body_hi`` そのもの
    # なので、y_top/y_bottomを渡さない既存の呼び出しはここを一切通らな
    # い(下の2つの ``if`` がどちらも False のまま) ── 動作は今までと
    # 完全に同じ。
    ring_spacing = (hi - lo) / height_steps
    ext_below_ys: List[float] = []
    ext_above_ys: List[float] = []
    ext_below_ratio: Optional[float] = None
    ext_above_ratio: Optional[float] = None
    ext_below_ratio_basis = ext_above_ratio_basis = ""
    ext_missing: List[float] = []

    if want_lo < lo - _EPS:
        n = max(1, math.ceil((lo - want_lo) / ring_spacing))
        ext_below_ys = [want_lo + (lo - want_lo) * k / n for k in range(n)]
        y0, a0, b0 = levels[0]
        ext_below_ratio = None if a0 <= _EPS else b0 / a0
        ext_below_ratio_basis = (
            f"levels[0] = ({y0:.4f}, {a0:.4f}, {b0:.4f}) -> "
            f"b/a = {ext_below_ratio:.4f}" if ext_below_ratio is not None
            else "levels[0] の幅(a)がゼロで前後比が定義できません")
        if ext_below_ratio is None:
            return {"verdict": NO_COVERAGE,
                    "requested": [round(want_lo, 4), round(want_hi, 4)],
                    "body_range": [body_lo, body_hi],
                    "why": "腰(levels[0])の幅がゼロで、身体の外へ運べる"
                           "前後比の根拠がありません",
                    "how_to_close": "腰の半径が正になるように人台を立て"
                                    "直すか、y_bottomを人台の範囲内に絞っ"
                                    "てください"}
        ext_missing += [round(y, 4) for y in ext_below_ys
                        if outline_width_at(outline, y) is None]

    if want_hi > hi + _EPS:
        n = max(1, math.ceil((want_hi - hi) / ring_spacing))
        ext_above_ys = [hi + (want_hi - hi) * (k + 1) / n for k in range(n)]
        y0, a0, b0 = levels[-1]
        ext_above_ratio = None if a0 <= _EPS else b0 / a0
        ext_above_ratio_basis = (
            f"levels[-1] = ({y0:.4f}, {a0:.4f}, {b0:.4f}) -> "
            f"b/a = {ext_above_ratio:.4f}" if ext_above_ratio is not None
            else "levels[-1] の幅(a)がゼロで前後比が定義できません")
        if ext_above_ratio is None:
            return {"verdict": NO_COVERAGE,
                    "requested": [round(want_lo, 4), round(want_hi, 4)],
                    "body_range": [body_lo, body_hi],
                    "why": "襟ぐり(levels[-1])の幅がゼロで、身体の外へ運"
                           "べる前後比の根拠がありません",
                    "how_to_close": "襟ぐりの半径が正になるように人台を立"
                                    "て直すか、y_topを人台の範囲内に絞っ"
                                    "てください"}
        ext_missing += [round(y, 4) for y in ext_above_ys
                        if outline_width_at(outline, y) is None]

    if ext_missing:
        ext_missing.sort()
        return {"verdict": OUTLINE_GAP,
                "requested": [round(want_lo, 4), round(want_hi, 4)],
                "missing_heights": ext_missing,
                "ring_count": len(ext_below_ys) + len(ext_above_ys),
                "why": f"{len(ext_missing)} 本の拡張リング(身体の外、"
                       f"輪郭だけが根拠)で輪郭が水平走査に交わりません"
                       f"でした",
                "how_to_close": "要求した範囲([{:.2f}, {:.2f}])の全体を"
                                "覆う輪郭を渡すか、y_top/y_bottomを輪郭が"
                                "実際に覆う範囲へ絞ってください"
                                .format(want_lo, want_hi)}

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

    extrapolation: Optional[Dict[str, Any]] = None
    extrap_internal: Optional[Dict[str, Any]] = None
    if ext_below_ys or ext_above_ys:
        extrapolation = {}
        if ext_below_ys:
            extrapolation["below_body"] = {
                "y_range_cm": [round(want_lo, 4), round(lo, 4)],
                "ring_count": len(ext_below_ys),
                "front_back_ratio": round(ext_below_ratio, 6),
                "ratio_basis": ext_below_ratio_basis,
                "kind": "INFERRED",
                "breaks_when": (
                    "断面が真円に近づく(比→1.0)ほど過小評価になりま"
                    "す。実測(合成の裾、半幅46.04cm・真の比1.0を仮定): "
                    "この比を運ぶと奥行半径32.23cm、真値46.04cmに対し"
                    "13.81cm・30%の過小評価"),
            }
        if ext_above_ys:
            extrapolation["above_body"] = {
                "y_range_cm": [round(hi, 4), round(want_hi, 4)],
                "ring_count": len(ext_above_ys),
                "front_back_ratio": round(ext_above_ratio, 6),
                "ratio_basis": ext_above_ratio_basis,
                "kind": "INFERRED",
                "breaks_when": (
                    "襟ぐりから上は衿・立ち衿など骨格の違う構造になりや"
                    "すく、胴の楕円がそのまま続くという前提自体が腰下よ"
                    "り弱くなります。比の値そのものは腰下と同じ式で読め"
                    "ますが、この高さでの物理的な妥当性はここでは測って"
                    "いません"),
            }
        extrap_internal = {
            "outline": list(outline),
            "body_lo": body_lo, "body_hi": body_hi,
            "ratio_below": ext_below_ratio, "ratio_above": ext_above_ratio,
        }

    lo_used = want_lo if ext_below_ys else lo
    hi_used = want_hi if ext_above_ys else hi

    out = {
        "verdict": "ANSWER",
        "what": ("skin-tight base garment deformed so its projected width "
                 "matches a front-view silhouette outline; depth follows "
                 "the same radial ease as a byproduct, not a measurement"),
        "segments": segments, "height_steps": height_steps,
        "y_range_used": [round(lo_used, 4), round(hi_used, 4)],
        "ease_by_height_cm": [[round(y, 4), round(e, 4)]
                              for y, e in zip(ring_ys, eases)],
        "ease_range_cm": [round(min(eases), 4), round(max(eases), 4)],
        "min_ease_cm": MIN_EASE_CM, "max_ease_cm": MAX_EASE_CM,
        #: **分類、構成する ANSWER の一部として。** どの高さがどちらの
        #: 面モデルの限界を超えるかを名指しする。空リストは「境界内」で
        #: はなく「この服はこの高さで身体を締めても離れて立ってもいな
        #: い」の測定 ── ring_class_counts の fitted 件数と一致する。
        "structure_hints": structure_hints,
        "ring_classes": ring_classes,
        "ring_class_counts": {
            COMPRESSION: ring_classes.count(COMPRESSION),
            FITTED: ring_classes.count(FITTED),
            STANDOFF: ring_classes.count(STANDOFF),
        },
        "extrapolation": extrapolation,
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
    if extrap_internal is not None:
        # ``radius_at_for`` だけが読む配線用の内部データ。拡張ゾーンが
        # 無い呼び出し(既定)では作らない ── 輪郭全体を複製して結果に
        # 抱え込むのは、実際に使う呼び出しだけにしたい。
        out["_extrap"] = extrap_internal
    return out


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

    ``rf(man, y, theta)`` が ``None`` を返す高さ(身体ゾーンの外)では、
    ``result["_extrap"]`` があれば ── ``match`` が ``y_top``/
    ``y_bottom`` で身体の外まで解いたときだけ載る ── そこに保存した
    輪郭と前後比から、その場で ``outline_width_at`` を呼び直して楕円
    半径を作る。リング間の線形補間ではなく輪郭そのものを毎回読むので、
    ``base_garment.build`` が要求する任意のyで誤差なく再現する。
    """
    if result.get("verdict") != "ANSWER":
        raise ValueError("cannot build a radius_at from a non-ANSWER match "
                         f"result: {result.get('verdict')}")
    rf: RadiusFn = base_radius_at or _mq.radius_at
    pairs = result["ease_by_height_cm"]
    ring_ys = [p[0] for p in pairs]
    ring_g = [p[1] for p in pairs]
    extrap = result.get("_extrap")

    def _fn(man: Dict[str, Any], y: float, theta: float) -> Optional[float]:
        r = rf(man, y, theta)
        if r is not None:
            return r + _ease_interp(ring_ys, ring_g, y)
        if extrap is None:
            return None
        if y < extrap["body_lo"] - _EPS:
            ratio = extrap["ratio_below"]
        elif y > extrap["body_hi"] + _EPS:
            ratio = extrap["ratio_above"]
        else:
            return None
        if ratio is None:
            return None
        w = outline_width_at(extrap["outline"], y)
        if w is None:
            return None
        a = (w[1] - w[0]) / 2.0
        return _mq._ellipse_radius(a, a * ratio, theta)
    return _fn


def to_surface(result: Dict[str, Any], man: Dict[str, Any], *,
              base_radius_at: Optional[RadiusFn] = None,
              gap: float = 0.0) -> Dict[str, Any]:
    """輪郭合わせの結果を実際のメッシュにする便宜関数。**新しいメッシュ
    構築は書かない** ── ``radius_at_for`` で作った関数を
    ``base_garment.build`` へそのまま渡すだけの配線。パネル側
    (``flatten.build``)が要るのも同じ関数なので、そちらへ渡してもよい
    ── ここは一例。

    ``result`` が拡張ゾーン(``_extrap``)を持つとき ── ``match`` が
    ``y_top``/``y_bottom`` で身体の外まで解いていたとき ── でも、
    ``base_garment.build`` 自身は要求範囲を人台の ``_levels`` の範囲へ
    黙って切り詰める(``base_garment.py`` 自身の設計、ここでは変えない)。
    ``radius_at`` は拡張ゾーンでも答えられるが、``base_garment.build``
    はそこまで要求しない ── その分は返り値の ``clipped_bottom_cm``/
    ``clipped_top_cm``/``y_range_used`` に、``base_garment.build`` 自身
    の言葉で載る。ここで隠しはしない。"""
    if result.get("verdict") != "ANSWER":
        return dict(result)
    rf = radius_at_for(result, base_radius_at=base_radius_at)
    y_lo, y_hi = result["y_range_used"]
    return _bg.build(man, gap=gap, segments=result["segments"],
                     height_steps=result["height_steps"],
                     y_top=y_hi, y_bottom=y_lo, radius_at=rf)
