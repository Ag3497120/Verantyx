# -*- coding: utf-8 -*-
"""平面化(flattening)。**3次元の面を2次元の裁片に写し、歪みを測る。**

コーパスから型紙を引かず幾何だけで導く経路の第三段。第一段は人台
(``mannequin`` / ``mannequin_spline``)、第二段は密着ベース
(``base_garment``)、ここはその面を平らな裁片に写す。

**展開可能でない面は、必ず歪む。** 人台は楕円断面が高さで変わる面で、
円錐(展開可能)ではない — Gauss の Theorema Egregium により、伸び縮み
なしに平面へ写すことはできない(``curvature`` の docstring 参照)。
だからここは「良い平面化」を主張しない。**どれだけ歪むかを、三角形
ごとに面積と角度で測って返すだけ。**

**やっていること。**

1. 密着ベースの面を、子午線1本(θ=0)で切り開く。円筒状のトポロジーを
   円板(境界のある面)にしないと、平面に写す先の座標系が矛盾する
   ―― 切った位置の頂点は複製し、2次元では別々の点として扱う。
2. 初期レイアウトを弧長の累積で作る(各行は行内の3次元距離を積んだ
   横位置、各列の高さは列ごとの3次元距離の平均)。これは等長写像の
   近似で、対角線(bias)の長さまでは合わせていない。
3. 格子の全辺(縦・横・両対角線)を、3次元での距離を自然長とする
   ばねとして張り、Jacobi 緩和でエネルギーを下げる。これは
   ``garment_sew.sew_and_drape`` とは別の実装 — あちらは3次元・重力
   ありの縫製ドレープで、ここは2次元・重力なしの平面化。**定式化は
   どの緩和法を使うかに依らない**: エネルギーは「各辺の現在の2D長さと
   3D自然長の差の二乗和」で、ここに同梱した Jacobi 緩和はその一つの
   実装にすぎない。``converge`` が別の緩和法(たとえば曲げ剛性つき)を
   持ち込んでも、エネルギーの定義と、その先の歪み測定(手順4)は
   変わらない。
4. 緩和後の2次元位置と元の3次元位置を、同じ三角形分割で比べる ——
   面積比・角度差を三角形ごとに測る。**「良い平面化」とは言わない。**
   どれだけ悪いかを報告するだけ。

**このモジュールが仮定していること(歪みの数字はこれに依存する)。**

- 対応する縫い目は子午線1本の切り開きだけ。実際の型紙のように前身頃・
  後身頃・脇線へ分割してはいない ―― 分割すれば各裁片は小さくなり、
  歪みは一般に小さくなる。ここが測るのは分割前の、円周全体を1枚とした
  最悪に近いケースの歪み。
- 格子辺(縦・横・対角線)の自然長だけを保とうとする緩和は、真の測地線
  距離の近似であって厳密な等長写像の探索ではない。
- 初期レイアウトは弧長の累積で、対角線までは合わせていない ―― 緩和が
  対角線のずれを事後的に減らす。
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import mannequin as _mq

Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]
RadiusFn = Callable[[Dict[str, Any], float, float], Optional[float]]

NO_MANNEQUIN = "UNKNOWN_NO_MANNEQUIN"
BAD_RESOLUTION = "UNKNOWN_RESOLUTION_TOO_COARSE"
BODY_MISSING_IN_GRID = "UNKNOWN_NO_BODY_AT_THIS_HEIGHT"

MIN_SEGMENTS = 3
MIN_HEIGHT_STEPS = 1

#: 緩和の既定反復数。24x16 格子(425頂点)で約6秒 —実測(2026-08-27)。
DEFAULT_ITERATIONS = 3000
#: 勾配降下の刻み幅。ばね定数を1とみなした単純なエネルギーなので、
#: この値自体に単位の意味は無い ―― 大きくすると発散し、
#: 小さくすると収束が遅くなる。0.15 は 24x16 格子で発散しない上限に
#: 実測で近い値。
DEFAULT_STEP = 0.15
#: この相対変化を下回ったら「落ち着いた」とみなす(sew_and_drape の
#: seams_settled と同じ発想 ―― 収束の判定を出力に出す)。
SETTLE_TOLERANCE = 1e-4
CHECK_EVERY = 200


def _dist3(a: Vec3, b: Vec3) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
                     + (a[2] - b[2]) ** 2)


def _grid3d(man: Dict[str, Any], segments: int, height_steps: int,
           radius_at: RadiusFn, gap: float
           ) -> Optional[Dict[Tuple[int, int], Vec3]]:
    """人台の子午線1本(θ=0)で切り開いた格子。i は 0..segments
    (segments列目はi=0と同じ3次元位置 — 切り口の複製)、j は 0..height_steps。

    ``radius_at`` が範囲内で None を返したら(=このモジュールが対応する
    範囲の中で身体が消えたら)None を返す ―― 呼ぶ側が
    BODY_MISSING_IN_GRID として断る。
    """
    levels = man["_levels"]
    y0, y1 = levels[0][0], levels[-1][0]
    out: Dict[Tuple[int, int], Vec3] = {}
    for j in range(height_steps + 1):
        y = y0 + (y1 - y0) * j / height_steps
        for i in range(segments + 1):
            theta = 2.0 * math.pi * (i % segments) / segments
            r = radius_at(man, y, theta)
            if r is None:
                return None
            surface = r + gap
            out[(i, j)] = (surface * math.cos(theta), y,
                           surface * math.sin(theta))
    return out


def _build_edges(V3: Dict[Tuple[int, int], Vec3], segments: int,
                 height_steps: int
                 ) -> List[Tuple[Tuple[int, int], Tuple[int, int], float, str]]:
    """縦(warp)・横(weft)・両対角線(bias)。自然長は3次元の距離。"""
    edges: List[Tuple[Tuple[int, int], Tuple[int, int], float, str]] = []
    for j in range(height_steps + 1):
        for i in range(segments):
            a, b = (i, j), (i + 1, j)
            edges.append((a, b, _dist3(V3[a], V3[b]), "weft"))
    for j in range(height_steps):
        for i in range(segments + 1):
            a, b = (i, j), (i, j + 1)
            edges.append((a, b, _dist3(V3[a], V3[b]), "warp"))
    for j in range(height_steps):
        for i in range(segments):
            a, b = (i, j), (i + 1, j + 1)
            edges.append((a, b, _dist3(V3[a], V3[b]), "bias"))
            c, d = (i + 1, j), (i, j + 1)
            edges.append((c, d, _dist3(V3[c], V3[d]), "bias"))
    return edges


def _initial_layout(V3: Dict[Tuple[int, int], Vec3], segments: int,
                    height_steps: int) -> Dict[Tuple[int, int], List[float]]:
    """弧長の累積によるレイアウト。**等長写像の近似**であって解ではない
    ―― 緩和の出発点として十分な近さがあればよい。各行の横位置は行内の
    3次元距離を積む(その行自身の円周に忠実)。各行の高さは、列ごとの
    3次元距離を平均したものを積む(全周で高さが一致するとは限らないので
    平均を選ぶ ―― この選択自体が仮定で、docstring の通り明記する)。
    """
    pos: Dict[Tuple[int, int], List[float]] = {}
    for j in range(height_steps + 1):
        x = 0.0
        pos[(0, j)] = [0.0, 0.0]
        for i in range(1, segments + 1):
            x += _dist3(V3[(i - 1, j)], V3[(i, j)])
            pos[(i, j)] = [x, 0.0]
    y = 0.0
    for j in range(height_steps + 1):
        if j > 0:
            ds = [_dist3(V3[(i, j - 1)], V3[(i, j)])
                 for i in range(segments + 1)]
            y += sum(ds) / len(ds)
        for i in range(segments + 1):
            pos[(i, j)][1] = y
    return pos


def _energy(pos: Dict[Tuple[int, int], List[float]],
           edges: Sequence[Tuple[Tuple[int, int], Tuple[int, int], float, str]]
           ) -> float:
    e = 0.0
    for a, b, rest, _kind in edges:
        pa, pb = pos[a], pos[b]
        d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
        e += 0.5 * (d - rest) ** 2
    return e


def relax(pos: Dict[Tuple[int, int], List[float]],
         edges: Sequence[Tuple[Tuple[int, int], Tuple[int, int], float, str]],
         pinned: Sequence[Tuple[int, int]], *,
         iterations: int = DEFAULT_ITERATIONS,
         step: float = DEFAULT_STEP) -> Dict[str, Any]:
    """**参照実装の一つ。** 縦・横・対角線ぜんぶを自然長=3D距離のばねと
    見て、Jacobi(同期更新、``garment_sew.sew_and_drape`` と同じ規律)で
    エネルギーを下げる。定式化(エネルギーの定義)はこの関数の外
    ―― ``_energy`` を下げる別の緩和法に差し替えても、この関数のあとの
    歪み測定は変わらない。

    停止は「エネルギーがこれ以上動かない」で判定し、反復の上限に達した
    だけなら ``converged`` を False で報告する ―― 打ち切りを収束と
    偽らない、``garment_sew`` と同じ規律。
    """
    touching: Dict[Tuple[int, int], List[Tuple[Tuple[int, int], float]]] = {}
    for a, b, rest, _kind in edges:
        touching.setdefault(a, []).append((b, rest))
        touching.setdefault(b, []).append((a, rest))
    pin = set(pinned)
    e_history = [_energy(pos, edges)]
    prev_check = e_history[0]
    converged = False
    used = 0
    for it in range(iterations):
        grad: Dict[Tuple[int, int], Tuple[float, float]] = {}
        for v, nbrs in touching.items():
            if v in pin:
                continue
            px, py = pos[v]
            gx = gy = 0.0
            for o, rest in nbrs:
                ox, oy = pos[o]
                dx, dy = px - ox, py - oy
                length = math.hypot(dx, dy)
                if length < 1e-9:
                    continue
                c = (length - rest) / length
                gx += c * dx
                gy += c * dy
            grad[v] = (gx, gy)
        for v, (gx, gy) in grad.items():
            pos[v][0] -= step * gx
            pos[v][1] -= step * gy
        used += 1
        if used % CHECK_EVERY == 0:
            e_now = _energy(pos, edges)
            e_history.append(e_now)
            if prev_check > 0 and abs(e_now - prev_check) / prev_check < SETTLE_TOLERANCE:
                converged = True
                prev_check = e_now
                break
            prev_check = e_now
    return {"pos": pos, "energy_first": e_history[0],
           "energy_last": e_history[-1], "energy_history": e_history,
           "converged": converged, "iterations_used": used,
           "iterations_cap": iterations}


def _tri_area2(p0: Vec2, p1: Vec2, p2: Vec2) -> float:
    return abs((p1[0] - p0[0]) * (p2[1] - p0[1])
              - (p2[0] - p0[0]) * (p1[1] - p0[1])) / 2.0


def _tri_area3(p0: Vec3, p1: Vec3, p2: Vec3) -> float:
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
    cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def _angle(p0: Sequence[float], p1: Sequence[float],
          p2: Sequence[float]) -> float:
    """p0 の内角(度)。2次元・3次元どちらの座標でも使う。"""
    v1 = [p1[k] - p0[k] for k in range(len(p0))]
    v2 = [p2[k] - p0[k] for k in range(len(p0))]
    n1 = math.sqrt(sum(x * x for x in v1))
    n2 = math.sqrt(sum(x * x for x in v2))
    if n1 <= 0.0 or n2 <= 0.0:
        return 0.0
    cos_t = sum(a * b for a, b in zip(v1, v2)) / (n1 * n2)
    cos_t = max(-1.0, min(1.0, cos_t))
    return math.degrees(math.acos(cos_t))


def _triangles(segments: int, height_steps: int
              ) -> List[Tuple[Tuple[int, int], Tuple[int, int],
                              Tuple[int, int]]]:
    """格子の各セルを対角線1本で2枚の三角形に切る。切り方はどちらの
    対角線でもよいが、``_build_edges`` の bias 辺(``(i,j)-(i+1,j+1)``)
    と同じ側を使う ―― 三角形の辺がすべて緩和で扱った辺と一致する。"""
    out = []
    for j in range(height_steps):
        for i in range(segments):
            a, b, c, d = (i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)
            out.append((a, b, c))
            out.append((a, c, d))
    return out


def build(man: Dict[str, Any], *,
          gap: float = _mq.GAP_CM,
          segments: int = _mq.SEGMENTS,
          height_steps: int = 16,
          radius_at: Optional[RadiusFn] = None,
          iterations: int = DEFAULT_ITERATIONS,
          step: float = DEFAULT_STEP) -> Dict[str, Any]:
    """密着ベースの面(既定 gap=``mannequin.GAP_CM``)を切り開いて緩和し、
    三角形ごとの歪み(面積比・角度差)を測って返す。

    **良い/悪いの判定はしない。** 数字を出すだけ ―― 面積比が1から
    離れているほど、その三角形は伸ばされたか縮められた。角度差が
    大きいほど、その三角形はせん断された。
    """
    if man.get("verdict") != "ANSWER":
        return {"verdict": NO_MANNEQUIN,
                "why": "人台が立っていないので平面化できません",
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
    V3 = _grid3d(man, segments, height_steps, rf, gap)
    if V3 is None:
        return {"verdict": BODY_MISSING_IN_GRID,
                "how_to_close": "この人台とこの範囲では、格子の途中で"
                                "身体が無い高さに当たりました。人台の"
                                "範囲内(levels[0][0]〜levels[-1][0])"
                                "だけを平面化してください"}

    edges = _build_edges(V3, segments, height_steps)
    pos = _initial_layout(V3, segments, height_steps)
    pinned = [(0, 0), (segments, 0)]
    solved = relax(pos, edges, pinned, iterations=iterations, step=step)
    pos = solved["pos"]

    tris = _triangles(segments, height_steps)
    area_ratios: List[float] = []
    angle_errors: List[float] = []
    per_triangle: List[Dict[str, Any]] = []
    for t in tris:
        p2 = [tuple(pos[v]) for v in t]
        p3 = [V3[v] for v in t]
        a3 = _tri_area3(*p3)
        a2 = _tri_area2(*p2)
        ratio = None if a3 <= 1e-9 else a2 / a3
        angs2 = [_angle(p2[0], p2[1], p2[2]), _angle(p2[1], p2[2], p2[0]),
                _angle(p2[2], p2[0], p2[1])]
        angs3 = [_angle(p3[0], p3[1], p3[2]), _angle(p3[1], p3[2], p3[0]),
                _angle(p3[2], p3[0], p3[1])]
        worst_angle = max(abs(a - b) for a, b in zip(angs2, angs3))
        if ratio is not None:
            area_ratios.append(ratio)
        angle_errors.append(worst_angle)
        per_triangle.append({
            "grid": [list(v) for v in t],
            "area_3d_cm2": round(a3, 6), "area_2d_cm2": round(a2, 6),
            "area_ratio": None if ratio is None else round(ratio, 4),
            "max_angle_error_deg": round(worst_angle, 4),
        })

    n_tri = len(tris)
    n_area = len(area_ratios)
    worst_area_idx = (max(range(n_area), key=lambda k: abs(area_ratios[k] - 1.0))
                      if area_ratios else None)
    worst_angle_idx = max(range(n_tri), key=lambda k: angle_errors[k])
    over_area = sum(1 for r in area_ratios if r < 0.9 or r > 1.1)
    over_angle = sum(1 for a in angle_errors if a > 5.0)

    return {
        "verdict": "ANSWER",
        "what": "flattened panel (single meridian cut) and its distortion",
        "segments": segments, "height_steps": height_steps,
        "gap_cm": gap,
        "triangles": n_tri,
        "relaxation": {"converged": solved["converged"],
                      "iterations_used": solved["iterations_used"],
                      "iterations_cap": solved["iterations_cap"],
                      "energy_first": round(solved["energy_first"], 4),
                      "energy_last": round(solved["energy_last"], 4),
                      "stopped_because": ("エネルギーの相対変化が"
                                          f"{SETTLE_TOLERANCE}を下回った"
                                          if solved["converged"] else
                                          "反復の上限に達した")},
        "area_ratio": {
            "min": round(min(area_ratios), 4) if area_ratios else None,
            "max": round(max(area_ratios), 4) if area_ratios else None,
            "mean": (round(sum(area_ratios) / n_area, 4)
                    if area_ratios else None),
            "triangles_outside_0.9_1.1": over_area,
            "worst_triangle": (per_triangle[worst_area_idx]
                               if worst_area_idx is not None else None),
        },
        "angle_error_deg": {
            "min": round(min(angle_errors), 4),
            "max": round(max(angle_errors), 4),
            "mean": round(sum(angle_errors) / n_tri, 4),
            "triangles_over_5deg": over_angle,
            "worst_triangle": per_triangle[worst_angle_idx],
        },
        "per_triangle": per_triangle,
        "assumed": (
            "単一の子午線(θ=0)での切り開き1本だけ。前身頃・後身頃・"
            "脇線への分割はしていない ―― この数字は分割前、円周全体を"
            "1枚とした場合の歪み。格子辺(縦・横・両対角線)の自然長=3D"
            "距離を保つ緩和は測地線距離の近似で、厳密な等長写像の探索"
            "ではない。初期レイアウトは弧長の累積(行の横位置は行内距離"
            "の和、行の高さは列距離の平均)"),
        "distortion_always_present": (
            "展開可能でない面(人台は円錐ではない)を平面へ写せば必ず"
            "歪む — Theorema Egregium。この関数は歪みを0にする方法を"
            "探していません。三角形ごとの面積比・角度差を測って、どこに"
            "どれだけ歪みがあるかを報告するだけです"),
        "solver_is_swappable": (
            "ここに同梱した緩和(Jacobiのばね降下)は、辺の自然長=3D"
            "距離を保つエネルギーを下げる実装の一つです。別の緩和法が"
            "同じエネルギーをより低く下げれば、area_ratio/angle_error_deg"
            "の数字は変わりえますが、歪みの定義(2Dの面積・角度と3Dの"
            "面積・角度の差)は変わりません"),
        "generated_not_evidence": (
            "平面化した位置は生成物です。観測の出典にはなりません。"
            "布の厚み・張り・裁ち代は計算していません"),
    }
