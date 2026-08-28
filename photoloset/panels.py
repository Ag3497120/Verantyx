# -*- coding: utf-8 -*-
"""パネル分割(paneling)。**平面化した1枚の筒を、歪みが最悪の場所で切って
実際の型紙にする第四段。**

``flatten`` が返すのは子午線1本(θ=0)で切り開いた筒 1 枚と、その歪み
(三角形ごとの面積比・角度差)。それは型紙ではない — 型紙は複数の裁片が
縫い目で繋がったもので、縫い目をどこに置くかがまだ決まっていない。

**ここでやっていること。**

1. 歪みが最悪の場所を、既に測ってある数字(``flatten`` の面積比・角度差)
   から選び、そこで切る。切ったら両側を**別々に平面化し直し**、歪みが
   実際にどれだけ減ったかを測る — 「たぶん減る」ではなく数字で。
2. Gauss-Bonnet はパネル1枚(円板)あたりの総量を固定する: 内部の頂点
   一つひとつの角度欠損(``curvature.py`` と同じ扇の式)の合計と、境界の
   頂点の「π からの不足」の合計が、**厳密に** 360° になる ―― これは
   幾何ではなく組合せ的な恒等式で、このモジュールは主張するだけでなく
   両方の項を独立に計算して、足して 360° になることを検算する
   (``gauss_bonnet_residual_deg``)。内部側がダーツの取り分、境界側が
   輪郭が「タダで」持って行く取り分 ――以前の版はこの境界側を無視して
   総量をまるごとダーツに変換し、90° を12cmのダーツ一本に押し込んで
   実測18.85cmという誤った値を出した(``curvature.py`` の docstring
   参照)。ここでは内部側**だけ**をダーツに渡す。
3. ダーツは ``darts.py`` をそのまま呼ぶ ―― 新しいダーツの定式化は作らない。
   角度から抜き幅への変換は円錐の頂角の公式(``intake = 2·depth·sin(θ/2)``)
   一つだけで、それ以外は ``darts.dart`` / ``darts.open_one`` に任せる。

**この経路が仮定していること。**

- 切る場所は「歪みが一番悪い列を、貪欲に一つずつ割る」という一つの基準
  だけで選ぶ。パターンメーカーが選ぶ場所(バストポイント、ウエストの
  絞り位置)とは無関係で、そちらの基準が良いとも悪いとも言わない。
- ダーツの深さ(``dart_depth_ratio``)はパネルの外接矩形の短辺に対する
  比で決め打ちしている。解剖学的な位置(バストポイントなど)ではない。
- 円錐の頂角公式は「基準辺の垂直二等分線上に頂点を置いた、単純な
  二等辺三角形のダーツ」を仮定する ―― ``darts.dart`` の
  ``perpendicular`` 経路と同じ前提。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import darts as _darts
from . import flatten as _flat
from . import mannequin as _mq

Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]
RadiusFn = _flat.RadiusFn

NO_MANNEQUIN = "UNKNOWN_NO_MANNEQUIN"
BAD_RESOLUTION = "UNKNOWN_RESOLUTION_TOO_COARSE"
BODY_MISSING_IN_GRID = "UNKNOWN_NO_BODY_AT_THIS_HEIGHT"
BAD_PANEL_COUNT = "UNKNOWN_PANEL_COUNT_NOT_POSITIVE"
TOO_MANY_PANELS = "UNKNOWN_MORE_PANELS_THAN_COLUMNS"

#: 歪みスコアで面積比の偏差と角度誤差を足し合わせる際の正規化。角度誤差は
#: 度なので、45度を「面積比が1からの偏差1.0(=2倍か0倍)」と同じ重みに
#: 揃える ―― この定数自体が選択で、比較の基準はこれ一つだけと明記する。
ANGLE_NORMALIZER_DEG = 45.0

#: ダーツの深さを、パネルの外接矩形(2D)の短辺の何倍に取るか。
#: **解剖学的根拠はない。** 布が実際に足りるための単純な既定値。
DEFAULT_DART_DEPTH_RATIO = 0.30


def _slice_v3(v3: Dict[Tuple[int, int], Vec3], i_lo: int, i_hi: int,
             height_steps: int) -> Dict[Tuple[int, int], Vec3]:
    """``flatten._grid3d`` の全周格子から [i_lo, i_hi] の帯を切り出し、
    列番号をローカル(0..width)に振り直す。"""
    return {(i - i_lo, j): v3[(i, j)]
            for i in range(i_lo, i_hi + 1)
            for j in range(height_steps + 1)}


def _panel_flatten(v3_full: Dict[Tuple[int, int], Vec3], i_lo: int, i_hi: int,
                   height_steps: int, iterations: int, step: float
                   ) -> Dict[str, Any]:
    """帯 [i_lo, i_hi] を単独で平面化する。**``flatten.build`` と同じ緩和
    (``_build_edges`` / ``relax``)を、全周ではなく帯だけに使い回す。**"""
    width = i_hi - i_lo
    v3 = _slice_v3(v3_full, i_lo, i_hi, height_steps)
    edges = _flat._build_edges(v3, width, height_steps)
    pos = _flat._initial_layout(v3, width, height_steps)
    pinned = [(0, 0), (width, 0)]
    solved = _flat.relax(pos, edges, pinned, iterations=iterations, step=step)
    pos = solved["pos"]

    tris = _flat._triangles(width, height_steps)
    area_ratios: List[float] = []
    angle_errors: List[float] = []
    # 列(セル)ごとの歪みスコア。セルの列番号は三角形の3頂点の最小i。
    column_score = [0.0] * max(width, 1)
    for t in tris:
        p2 = [tuple(pos[v]) for v in t]
        p3 = [v3[v] for v in t]
        a3 = _flat._tri_area3(*p3)
        a2 = _flat._tri_area2(*p2)
        ratio = None if a3 <= 1e-9 else a2 / a3
        angs2 = [_flat._angle(p2[0], p2[1], p2[2]),
                _flat._angle(p2[1], p2[2], p2[0]),
                _flat._angle(p2[2], p2[0], p2[1])]
        angs3 = [_flat._angle(p3[0], p3[1], p3[2]),
                _flat._angle(p3[1], p3[2], p3[0]),
                _flat._angle(p3[2], p3[0], p3[1])]
        worst_angle = max(abs(a - b) for a, b in zip(angs2, angs3))
        if ratio is not None:
            area_ratios.append(ratio)
        angle_errors.append(worst_angle)
        li = min(v[0] for v in t)
        score = (0.0 if ratio is None else abs(ratio - 1.0)) \
            + worst_angle / ANGLE_NORMALIZER_DEG
        column_score[li] += score

    n_tri = len(tris)
    area_mad_mean = (sum(abs(r - 1.0) for r in area_ratios) / len(area_ratios)
                     if area_ratios else 0.0)
    angle_mean = sum(angle_errors) / n_tri if n_tri else 0.0
    return {
        "width": width, "height_steps": height_steps,
        "pos": pos, "v3": v3, "triangles": n_tri,
        "area_ratio_mean": (sum(area_ratios) / len(area_ratios)
                            if area_ratios else None),
        "area_ratio_min": min(area_ratios) if area_ratios else None,
        "area_ratio_max": max(area_ratios) if area_ratios else None,
        "area_ratio_abs_dev_mean": round(area_mad_mean, 6),
        "angle_error_mean_deg": round(angle_mean, 6),
        "angle_error_max_deg": (round(max(angle_errors), 6)
                               if angle_errors else 0.0),
        "column_score": column_score,
        "energy_first": solved["energy_first"],
        "energy_last": solved["energy_last"],
        "converged": solved["converged"],
        "distortion_index": round(
            area_mad_mean + angle_mean / ANGLE_NORMALIZER_DEG, 6),
    }


def _best_cut_line(column_score: Sequence[float], width: int) -> Optional[int]:
    """幅 width の帯の中で、内部の格子線(境界ではない)のうち、両側の
    セルの歪みスコアの和が最大の場所を返す。幅が2未満なら内部の線が
    無いので None。"""
    if width < 2:
        return None
    best_c, best_s = None, -1.0
    for c in range(1, width):
        s = column_score[c - 1] + column_score[c]
        if s > best_s:
            best_c, best_s = c, s
    return best_c


def _panel_curvature(pf: Dict[str, Any]) -> Dict[str, Any]:
    """このパネル自身の三角形分割(``flatten._triangles`` と同じ辺)で、
    内部頂点の角度欠損(2π − 内角和)と境界頂点の π からの不足を、
    どちらも「このパネルだけの局所的な扇」で計算して足す。

    disc(単連結、境界1本)の組合せ的 Gauss-Bonnet は
    Σ_内部(2π−Σθ) + Σ_境界(π−Σθ) = 2π を**三角形数・頂点数の数え上げ
    だけから**厳密に満たす(このモジュールの docstring に導出はないが、
    ``tests/run_checks.py`` の対応する検査が360°との残差を実測する)。
    """
    width, height_steps = pf["width"], pf["height_steps"]
    v3 = pf["v3"]
    tris = _flat._triangles(width, height_steps)
    angle_sum: Dict[Tuple[int, int], float] = {}
    for t in tris:
        p = [v3[v] for v in t]
        for k in range(3):
            v = t[k]
            a, b = p[(k + 1) % 3], p[(k + 2) % 3]
            angle_sum[v] = angle_sum.get(v, 0.0) + _flat._angle(p[k], a, b)

    interior_deg = 0.0
    boundary_deg = 0.0
    for (li, j), s in angle_sum.items():
        if 0 < li < width and 0 < j < height_steps:
            interior_deg += 360.0 - s
        else:
            boundary_deg += 180.0 - s
    total = interior_deg + boundary_deg
    return {
        "interior_deg": round(interior_deg, 6),
        "boundary_deg": round(boundary_deg, 6),
        "gauss_bonnet_total_deg": round(total, 6),
        "gauss_bonnet_residual_deg": round(abs(360.0 - total), 9),
        "method": "このパネル自身の三角形分割で、内部頂点は2π-Σθ、境界"
                  "頂点はπ-Σθを足す。組合せ的な恒等式で、幾何に依らず"
                  "厳密に360°になるはず(残差は浮動小数の丸め誤差のみ)",
    }


def _length(points: Sequence[Vec2]) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    return round(total, 4)


def _poly_area(poly: Sequence[Vec2]) -> float:
    n = len(poly)
    s = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _panel_boundary(pf: Dict[str, Any]
                    ) -> Tuple[List[Vec2], Dict[str, List[Vec2]]]:
    """緩和済みの2D位置から、パネルの輪郭(閉多角形)と、名前付き4辺
    (下辺・右辺・上辺・左辺)を作る。右辺・左辺が実際の縫い目(新しく
    切った子午線、または元々のθ=0の切り口)。"""
    width, height_steps = pf["width"], pf["height_steps"]
    pos = pf["pos"]
    bottom = [tuple(pos[(li, 0)]) for li in range(width + 1)]
    right = [tuple(pos[(width, j)]) for j in range(height_steps + 1)]
    top = [tuple(pos[(li, height_steps)]) for li in range(width + 1)]
    left = [tuple(pos[(0, j)]) for j in range(height_steps + 1)]
    outline = (bottom + right[1:] + list(reversed(top))[1:]
              + list(reversed(left))[1:-1])
    # ``garment_pattern.draft`` と同じ形({"points":..., "length":...}) —
    # ``garment_marks.apply`` / ``dxf.to_dxf`` がこの形を読む。
    edges = {name: {"points": pts, "length": _length(pts)}
            for name, pts in (("下辺", bottom), ("右辺", right),
                              ("上辺", top), ("左辺", left))}
    return outline, edges


def _place_dart(panel_name: str, pf: Dict[str, Any], outline: Sequence[Vec2],
                interior_deg: float, dart_depth_ratio: float) -> Dict[str, Any]:
    """このパネルの内部曲率の取り分を、円錐の頂角公式で抜き幅に変え、
    ``darts.dart`` / ``darts.open_one`` にそのまま渡す。**新しいダーツの
    式は作らない** — 変換は角度から intake_cm への一行だけ。

    ``_panel_boundary`` が返す、格子密度そのままの**実際の**輪郭
    (``outline``。簡略化した4隅の輪郭ではない)の右辺に置く。右辺は
    ``height_steps`` 本の線分に分かれている(``e{width}``〜
    ``e{width+height_steps-1}``、``width`` はこのパネルの列幅)ので、
    縦方向の真ん中に一番近い線分から順に試し、抜き幅が収まった最初の
    1本を使う。垂直(perpendicular)経路を使うので両脚は構成上必ず揃う
    (``darts.py`` の docstring参照) —— ここで LEGS_UNEQUAL は出ない。

    **以前の版はここで4隅だけの簡略輪郭に置いていた。** 右辺全体を1本の
    線分として ``e1`` で扱えたのはその簡略輪郭でだけ通用する数え方で、
    ``to_pieces()`` が返す実際の(細かく分割された)輪郭では ``e1`` は
    右辺ではなく下辺の一部を指してしまう ―― 番号の食い違いで、実際の
    縫い目の長さを測ったことには一度もなっていなかった。
    """
    width, height_steps = pf["width"], pf["height_steps"]
    pos = pf["pos"]
    xs = [pos[k][0] for k in pos]
    ys = [pos[k][1] for k in pos]
    dx, dy = max(xs) - min(xs), max(ys) - min(ys)
    depth_cm = round(dart_depth_ratio * min(dx, dy), 4)

    if interior_deg <= 1e-9:
        if width < 2:
            reason, why = "WIDTH_ONE_NO_INTERIOR", (
                "このパネルは列幅1(内部の頂点が構成上ゼロ)なので、"
                "interior_degは必ず0になります — 曲率が実際に0だという"
                "測定ではありません。曲率の取り分はこのパネルの境界"
                "(boundary_deg)に丸ごと乗っています")
        elif interior_deg > -1e-9:
            reason, why = "NO_SURPLUS", (
                "内部曲率がほぼ0でした。このパネルの取り分の大半を輪郭"
                "自身の形が既に持っている(boundary_degを見てください)"
                "ということで、ダーツで抜く余地がほぼありません")
        else:
            reason, why = "SADDLE_NOT_SUPPORTED", (
                "曲率の内部側が負(鞍型)です。負のときは布を抜くダーツ"
                "ではなく、逆に布を足す操作(ゴデーやギャザー)が要ります"
                "が、darts.pyにその操作はありません — 実装していない"
                "能力は名乗りません")
        return {"placed": False, "interior_deg": round(interior_deg, 4),
               "width_columns": width, "reason": reason, "why": why}

    theta = math.radians(min(interior_deg, 179.999))
    intake_cm = round(2.0 * depth_cm * math.sin(theta / 2.0), 4)

    out = [tuple(map(float, p)) for p in outline]
    # 右辺(縫い目)は境界の edge index [width, width+height_steps) の
    # 線分たち(``_panel_boundary`` の並べ方から導ける ── bottomがindex
    # 0..width、その次から right[1:] が続くので、rightの最初の線分は
    # 必ず e{width})。縦方向の真ん中に近い線分から順に試す。
    mid_offset = height_steps // 2
    order = sorted(range(height_steps), key=lambda k: abs(k - mid_offset))
    tried: List[Dict[str, Any]] = []
    chosen: Optional[Dict[str, Any]] = None
    for k in order:
        edge_name = f"e{width + k}"
        d = _darts.dart(panel_name, edge_name, 0.5, intake_cm,
                        length_cm=depth_cm, role="distortion-share")
        r = _darts.open_one(out, d)
        tried.append({"edge": edge_name, "verdict": r.get("verdict")})
        if r.get("verdict") == "ANSWER":
            chosen = r
            break
    if chosen is None:
        return {"placed": False, "interior_deg": round(interior_deg, 4),
               "width_columns": width, "reason": "NO_SEAM_SEGMENT_FITS",
               "why": (f"抜き幅{intake_cm}cmが右辺の{height_steps}本の"
                       f"線分のどれにも収まりませんでした"),
               "depth_cm": depth_cm, "intake_cm_requested": intake_cm,
               "tried": tried}
    return {
        "placed": True,
        "interior_deg": round(interior_deg, 4),
        "depth_cm": depth_cm,
        "intake_cm_requested": intake_cm,
        "formula": "intake_cm = 2 * depth_cm * sin(interior_deg/2) "
                   "(円錐の頂角。darts.py の perpendicular 経路と同じ"
                   "二等辺三角形を仮定)",
        "darts_result": chosen,
        "edge_selection": (
            f"右辺は{height_steps}本の線分(e{width}..e{width + height_steps - 1})"
            f"に分かれている。縦方向の真ん中に近い順に試し、"
            f"{chosen['edge']}で収まった(試した順: "
            f"{[t['edge'] for t in tried]})。この輪郭は簡略版ではなく、"
            f"``to_pieces()``が返すのと同じ細かい境界そのもの"),
    }


def cut(man: Dict[str, Any], *, n_panels: int = 4,
        segments: Optional[int] = None, height_steps: int = 16,
        gap: Optional[float] = None, radius_at: Optional[RadiusFn] = None,
        iterations: int = _flat.DEFAULT_ITERATIONS,
        step: float = _flat.DEFAULT_STEP,
        dart_depth_ratio: float = DEFAULT_DART_DEPTH_RATIO) -> Dict[str, Any]:
    """全周1枚の平面化を、歪みが最悪の場所から貪欲に切って
    ``n_panels`` 枚のパネルにする。

    各追加の切り口(seam)は、その時点でいちばん歪みがひどいパネルの
    中で、いちばん歪みがひどい内部の格子線に置く。切ったら両側を
    独立に緩め直し、切る前後の歪み指数(面積比の平均絶対偏差 +
    角度誤差平均/45)を **両方報告する** — 「減るはず」ではなく
    「減った」を数字で言う。

    Gauss-Bonnet の総量(円板1枚あたり360°)を、各パネルについて内部
    (``curvature``と同じ扇の式)と境界(π基準)に実際に割って、足すと
    360°に戻ることを検算する。内部側だけをダーツに渡す
    (``darts.dart``/``darts.open_one`` をそのまま使う)。

    ``radius_at`` に ``silhouette.radius_at_for()`` の返り値のような、
    既に身体の半径へオフセットを足し込み済みの関数を渡すときは
    ``gap=0.0`` も渡すこと。``flatten._grid3d`` は常に
    ``radius_at(...) + gap`` を使うので、既にオフセットを含む
    ``radius_at`` にこの関数の既定 ``gap``(``mannequin.GAP_CM``)を
    重ねると二重にゆるみを足してしまう ―― ``silhouette.to_surface`` が
    自分の呼び出しで ``gap=0.0`` を渡しているのと同じ理由。
    """
    if man.get("verdict") != "ANSWER":
        # **代案を出さない、ここは意図的に。** 人台がどう立てなかったかは
        # ``man["verdict"]`` の名の数だけあり得て、「たぶんこの寸法」を
        # 名乗れる幾何的な近傍がここには無い —— NO_MANNEQUIN は他の3つと
        # 違って「境界を超えた」のではなく「上流が何も返さなかった」の
        # で、比較していた測定値自体が存在しない。``flatten.build`` の
        # 同名の断りも同じ理由で代案を持たない。
        return {"verdict": NO_MANNEQUIN,
                "why": "人台が立っていないのでパネルに切れません",
                "how_to_close": "man['verdict'] が何と断っているかを見て、"
                                "人台の側を直してから呼び直してください",
                "upstream_verdict": man.get("verdict")}
    segments = _mq.SEGMENTS if segments is None else segments
    gap = _mq.GAP_CM if gap is None else gap
    if segments < _flat.MIN_SEGMENTS or height_steps < _flat.MIN_HEIGHT_STEPS:
        entry: Dict[str, Any] = {
            "verdict": BAD_RESOLUTION, "segments": segments,
            "height_steps": height_steps,
            "minimum_segments": _flat.MIN_SEGMENTS,
            "minimum_height_steps": _flat.MIN_HEIGHT_STEPS,
            "how_to_close": f"周方向は{_flat.MIN_SEGMENTS}以上、高さ"
                            f"方向は{_flat.MIN_HEIGHT_STEPS}以上でなけ"
                            f"れば三角形が1枚も作れません"}
        # **比較していた下限そのものが、答えられる最小の格子。** 判定は
        # 「<」なので下限自体は通る —— 発明ではなく、この断りが既に
        # 比べていた値をそのまま使う。
        assumed_segments = max(segments, _flat.MIN_SEGMENTS)
        assumed_height_steps = max(height_steps, _flat.MIN_HEIGHT_STEPS)
        if (assumed_segments, assumed_height_steps) != (segments,
                                                         height_steps):
            entry.update({
                "assumed": {"segments": assumed_segments,
                           "height_steps": assumed_height_steps},
                "kind": "INFERRED",
                "basis": (
                    "minimum_segments/minimum_height_steps are the "
                    "exact thresholds this refusal already compares "
                    "against (_flat.MIN_SEGMENTS, _flat."
                    "MIN_HEIGHT_STEPS); the comparison is strict '<', "
                    "so the minimum itself is the smallest grid this "
                    "module accepts — each axis clamped up "
                    "independently, the other left alone if it already "
                    "cleared its own floor"),
                "breaks_when": (
                    "clamping up silently coarsens or refines only the "
                    "axis that failed — a caller who asked for "
                    "segments=2 against a minimum of "
                    f"{_flat.MIN_SEGMENTS} gets a grid "
                    f"{_flat.MIN_SEGMENTS / 2:.2g}x finer than "
                    "requested on that axis alone, and every per-panel "
                    "distortion number downstream is measured on that "
                    "grid, not the one asked for"),
                "alternatives": [],
            })
        return entry
    if not isinstance(n_panels, int) or n_panels < 1:
        entry = {"verdict": BAD_PANEL_COUNT, "n_panels": n_panels,
                "how_to_close": "パネル数は1以上の整数にしてください"}
        # **整数でない、あるいは1未満。** 「1以上」の1はこの判定が既に
        # 比べている裸の下限で、発明した値ではない。数として解釈できる
        # 入力(bool は除く — 真偽値は枚数の意味を持たない)だけ丸めて
        # から床を当てる。数として解釈できない入力には代案を出さない。
        if (not isinstance(n_panels, bool)
                and isinstance(n_panels, (int, float))
                and not (isinstance(n_panels, float)
                        and math.isnan(n_panels))):
            rounded = int(round(n_panels))
            assumed_n = max(rounded, 1)
            entry.update({
                "assumed": assumed_n,
                "kind": "INFERRED",
                "basis": (
                    f"1 is the literal floor this check compares "
                    f"n_panels against ('n_panels < 1'); the given "
                    f"value ({n_panels!r}) rounds to {rounded}, then "
                    f"that floor is applied"),
                "breaks_when": (
                    "rounding a fractional request changes which "
                    "columns get chosen as cut lines outright — 2 vs 3 "
                    "panels are different seam placements, not a small "
                    "nudge on one — so a caller who meant a fraction "
                    "as 'about a quarter cut' should choose the "
                    "integer explicitly rather than trust this "
                    "rounding"),
                "alternatives": [{
                    "value": 1,
                    "basis": ("the bare floor this check compares "
                              "against, ignoring the given value "
                              "entirely")}],
            })
        return entry
    if n_panels > segments:
        return {
            "verdict": TOO_MANY_PANELS, "n_panels": n_panels,
            "segments": segments,
            "how_to_close": f"周方向の分割が{segments}列しかないので、"
                            f"パネルは最大{segments}枚までしか切れませ"
                            f"ん",
            # **segments はこの判定が既に比べている境界そのもの。**
            # 「>」なので segments 自体は通る —— この境界は動かさない
            # (``tests/falsifiers.py`` の "more panels than columns is
            # accepted anyway" が +5 する変異で赤くなることを縛って
            # いる)。ここは代案を添えるだけで判定式には触れていない。
            "assumed": segments,
            "kind": "INFERRED",
            "basis": (
                f"segments ({segments}) is the exact bound this "
                f"refusal already compares n_panels against; the "
                f"comparison is strict '>', so segments itself is the "
                f"largest panel count the grid can cut and remains "
                f"accepted"),
            "breaks_when": (
                "cutting into exactly `segments` panels leaves every "
                "column its own panel with zero interior grid lines "
                "inside any of them (cut()'s own candidates filter "
                "needs i_hi - i_lo >= 2 to find a line to split "
                "further), so every seam attempt beyond the first "
                "stops immediately via stop_reason — this value is "
                "feasible for THIS refusal but exhausts the panel-"
                "splitting margin exactly where the grid is thinnest"),
            "alternatives": [],
        }

    rf: RadiusFn = radius_at or _mq.radius_at
    v3 = _flat._grid3d(man, segments, height_steps, rf, gap)
    if v3 is None:
        return {"verdict": BODY_MISSING_IN_GRID,
                "how_to_close": "この人台とこの範囲では、格子の途中で"
                                "身体が無い高さに当たりました"}

    baseline = _panel_flatten(v3, 0, segments, height_steps, iterations, step)
    panels = [{"i_lo": 0, "i_hi": segments, "flat": baseline}]
    seam_log: List[Dict[str, Any]] = []
    stop_reason = None

    for k in range(1, n_panels):
        candidates = [p for p in panels if p["i_hi"] - p["i_lo"] >= 2]
        if not candidates:
            stop_reason = ("残っている全てのパネルの幅が2列未満で、これ"
                           "以上内部に切る線がありません")
            break
        worst = max(candidates, key=lambda p: p["flat"]["distortion_index"])
        c_local = _best_cut_line(worst["flat"]["column_score"],
                                 worst["flat"]["width"])
        if c_local is None:
            stop_reason = "切る場所が見つかりませんでした"
            break
        c_global = worst["i_lo"] + c_local
        a = _panel_flatten(v3, worst["i_lo"], c_global, height_steps,
                           iterations, step)
        b = _panel_flatten(v3, c_global, worst["i_hi"], height_steps,
                           iterations, step)
        before_idx = worst["flat"]["distortion_index"]
        na, nb = a["triangles"], b["triangles"]
        after_idx = ((a["distortion_index"] * na + b["distortion_index"] * nb)
                    / max(na + nb, 1))
        seam_log.append({
            "seam_number": k,
            "cut_at_theta_deg": round(360.0 * c_global / segments, 3),
            "split_panel_theta_range_deg": [
                round(360.0 * worst["i_lo"] / segments, 3),
                round(360.0 * worst["i_hi"] / segments, 3)],
            "distortion_index_before": round(before_idx, 6),
            "distortion_index_after": round(after_idx, 6),
            "distortion_bought": round(before_idx - after_idx, 6),
            "distortion_bought_pct": (
                round(100.0 * (before_idx - after_idx) / before_idx, 2)
                if before_idx > 1e-12 else None),
        })
        panels.remove(worst)
        panels.append({"i_lo": worst["i_lo"], "i_hi": c_global, "flat": a})
        panels.append({"i_lo": c_global, "i_hi": worst["i_hi"], "flat": b})
        panels.sort(key=lambda p: p["i_lo"])

    panels.sort(key=lambda p: p["i_lo"])
    n_reached = len(panels)

    out_panels: List[Dict[str, Any]] = []
    for idx, p in enumerate(panels, 1):
        pf = p["flat"]
        name = f"パネル{idx}"
        outline, edges = _panel_boundary(pf)
        area = round(_poly_area(outline), 2)
        curv = _panel_curvature(pf)
        dart_r = _place_dart(name, pf, outline, curv["interior_deg"],
                            dart_depth_ratio)
        out_panels.append({
            "name": name,
            "theta_range_deg": [round(360.0 * p["i_lo"] / segments, 3),
                                round(360.0 * p["i_hi"] / segments, 3)],
            "outline": [[round(x, 3), round(y, 3)] for x, y in outline],
            "edges": {k2: {"points": [[round(x, 3), round(y, 3)]
                                      for x, y in v2["points"]],
                          "length": v2["length"]}
                     for k2, v2 in edges.items()},
            "area_cm2": area,
            "triangles": pf["triangles"],
            "distortion": {
                "area_ratio_mean": pf["area_ratio_mean"],
                "area_ratio_abs_dev_mean": pf["area_ratio_abs_dev_mean"],
                "angle_error_mean_deg": pf["angle_error_mean_deg"],
                "angle_error_max_deg": pf["angle_error_max_deg"],
                "distortion_index": pf["distortion_index"],
            },
            "curvature": curv,
            "dart": dart_r,
        })

    total_before = baseline["distortion_index"]
    total_after = (sum(pp["distortion"]["distortion_index"] * pp["triangles"]
                       for pp in out_panels)
                  / max(sum(pp["triangles"] for pp in out_panels), 1))
    total_area = round(sum(pp["area_cm2"] for pp in out_panels), 2)
    curvature_check_deg = round(
        sum(pp["curvature"]["interior_deg"] for pp in out_panels)
        + sum(pp["curvature"]["boundary_deg"] for pp in out_panels), 4)

    return {
        "verdict": "ANSWER",
        "what": "flattened tube cut into pattern panels by distortion",
        "segments": segments, "height_steps": height_steps, "gap_cm": gap,
        "n_panels_requested": n_panels, "n_panels_reached": n_reached,
        "stopped_early_because": stop_reason,
        "seam_log": seam_log,
        "panels": out_panels,
        "total_area_cm2": total_area,
        "distortion_index_before_any_additional_cut": round(total_before, 6),
        "distortion_index_after_all_cuts": round(total_after, 6),
        "distortion_bought_total": round(total_before - total_after, 6),
        "distortion_bought_total_pct": (
            round(100.0 * (total_before - total_after) / total_before, 2)
            if total_before > 1e-12 else None),
        "gauss_bonnet_across_all_panels_deg": curvature_check_deg,
        "gauss_bonnet_expected_deg": round(360.0 * n_reached, 4),
        "cut_criterion": (
            "各追加の切り口は、その時点でいちばん歪み指数(面積比の平均"
            "絶対偏差 + 角度誤差平均/45度)が大きいパネルの中で、両側の"
            "セルのスコア和が最大の内部格子線に置く。歪みが最悪の場所を"
            "割る、という一つの基準であって、パターンメーカーが選ぶ場所"
            "(バストポイント等)ではない"),
        "allocation_is_not_a_choice_by_this_module": (
            "各パネルの内部曲率(interior_deg)と境界曲率(boundary_deg)"
            "の按分は、Gauss-Bonnetの組合せ的恒等式が決める — このパネル"
            "自身の三角形分割で内部頂点は2π-Σθ、境界頂点はπ-Σθを足すと"
            "厳密に360°になる。ダーツに渡すのはinterior_degだけで、"
            "boundary_degは輪郭の形そのものが既に持っている取り分"),
        "distortion_always_present": (
            "パネルに分けても歪みは0にならない — Theorema Egregiumは"
            "パネルがいくつであっても効く。distortion_bought_totalは"
            "『どれだけ減ったか』であって『0にしたか』ではない"),
        "generated_not_evidence": (
            "パネルの位置・面積・ダーツは生成物です。観測の出典には"
            "なりません。縫い代・布の厚み・張りは計算していません"),
    }


def to_pieces(cut_out: Dict[str, Any]) -> Dict[str, Any]:
    """``cut`` の結果を、``garment_pattern.draft`` と同じ ``pieces`` の形
    に直す。**輪の縫い目も自分で宣言する** — 隣どうしの右辺/左辺、
    そして最後のパネルの右辺と最初のパネルの左辺(元々の θ=0 の切り口、
    両側が同じ3次元の点なので、これも本物の縫い目)。"""
    if cut_out.get("verdict") != "ANSWER":
        return dict(cut_out)
    panels = cut_out["panels"]
    pieces = [{"name": p["name"], "outline": p["outline"],
              "edges": p["edges"], "area_cm2": p["area_cm2"]}
             for p in panels]
    n = len(panels)
    seam_specs = []
    for i in range(n):
        a = panels[i]["name"]
        b = panels[(i + 1) % n]["name"]
        label = (f"{a}/右辺 ↔ {b}/左辺" if i < n - 1
                 else f"{a}/右辺 ↔ {b}/左辺 (元のθ=0の切り口を閉じる)")
        seam_specs.append({"a": (a, "右辺"), "b": (b, "左辺"), "label": label})
    return {
        "verdict": "ANSWER", "pieces": pieces, "used": {},
        "seam_specs": seam_specs,
        "placement": {p["name"]: (i * 40.0, 0.0, 0.0)
                     for i, p in enumerate(panels)},
        "note": "cut() の出力から作った pieces。garment_pattern.draft の"
                "ようなダーツ・縫い代情報は乗っていない — 幾何と縫い目"
                "対応だけを、既存の型紙の形に翻訳したもの",
    }


def compare_to_draft(cut_out: Dict[str, Any], draft_out: Dict[str, Any]
                     ) -> Dict[str, Any]:
    """パネル分割と ``garment_pattern.draft`` の製図を並べる。**似せる
    ためではない** — どちらもコートの寸法から出発して、片方は公式、
    片方は幾何で、違う形になるのが期待どおりであることを数字で示す。"""
    if cut_out.get("verdict") != "ANSWER":
        return dict(cut_out)
    if draft_out.get("verdict") != "ANSWER":
        return dict(draft_out)
    panel_area = cut_out["total_area_cm2"]
    draft_area = draft_out["total_area_cm2"]
    return {
        "verdict": "ANSWER",
        "panel_count": len(cut_out["panels"]),
        "draft_piece_count": len(draft_out["pieces"]),
        "panel_names": [p["name"] for p in cut_out["panels"]],
        "draft_piece_names": [p["name"] for p in draft_out["pieces"]],
        "panel_total_area_cm2": panel_area,
        "draft_total_area_cm2": draft_area,
        "area_ratio_panels_over_draft": (
            round(panel_area / draft_area, 4) if draft_area else None),
        "seam_positions": {
            "panels": [s["cut_at_theta_deg"] for s in cut_out["seam_log"]],
            "panels_units": "度(θ, 全周に対する切り口の角度)",
            "draft": "肩線・脇線・袖ぐりという名前の辺 — 角度という座標系"
                    "を持たない",
        },
        "structural_difference": (
            "draftは前身頃・後身頃・袖という異なる形の3枚が、肩・脇・"
            "袖ぐりという別々の縫い目で繋がる。panelsは全周を輪切りに"
            "した同じ高さ範囲(腰〜衿ぐり)のゴア(gore)がN枚、全て同じ"
            "縦の縫い目の種類(右辺↔左辺)で輪に繋がる — 前後の区別も、"
            "袖の別ピースも、この経路には無い"),
        "why_they_differ_is_expected": (
            "draftは文化式的な製図知識(肩幅・袖ぐり深さの経験式)を式に"
            "持っている。panelsは形状の観測(距離場の歪み)だけから切って"
            "いて、『前』『後ろ』『袖』が何であるかを知らない。似ていたら"
            "むしろ疑うべき一致だった"),
        "not_a_claim_of_equivalence": (
            "面積比や枚数の近さ・遠さは、どちらが正しいパターンかを判定"
            "しない。draftは公表されていない簡易製図(garment_patternの"
            "docstring参照)、panelsは一つの距離歪み基準による分割 ――"
            "両方とも、実物の型紙そのものではない"),
    }
