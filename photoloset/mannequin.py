# -*- coding: utf-8 -*-
"""人台(マネキン)。**ユーザーの実測から、着せる先を出す。**

- 断面は楕円(幅×奥行)。**奥行の比は仮定**で、式と値を出力に載せる —
  胸囲は周囲であって幅ではない。分けるには誰かが測るしかない
- ``dress`` は縫って落とした服を人台の周りに**再配置する**。これは
  物理ではなく可視化のための写像で、**生成物であることを出力自身が
  名乗る** — 落ちた形が観測ではないのと同じで、着せた形も観測ではない
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

#: 奥行/幅 の比。**この道具の仮定。** 実測が入ったら書き換わるべき。
DEPTH_RATIO = 0.70
#: 断面の分割数(決定的)。
SEGMENTS = 24
#: 人台と布の間の空気層(既定 cm)。
GAP_CM = 1.0

NO_MEASURE = "UNKNOWN_MISSING_MEASUREMENTS"


def _ellipse_radius(a: float, b: float, theta: float) -> float:
    """楕円の θ 方向半径。a=幅の半分, b=奥行の半分。"""
    return (a * b) / math.sqrt((b * math.cos(theta)) ** 2
                               + (a * math.sin(theta)) ** 2)


def build(measures: Any) -> Dict[str, Any]:
    """実測(胸囲・胴囲・腰囲・着丈)から人台のメッシュを作る。"""
    have: Dict[str, float] = {}
    missing = []
    for spot in ("chest", "waist", "hip", "body_length"):
        rows = [e for e in measures.entries
                if e.spot == spot and e.kind == "measured"]
        if not rows:
            missing.append(spot)
            continue
        k = {"cm": 1.0, "mm": 0.1, "inch": 2.54}.get(
            (rows[0].unit or "").lower())
        if k is None:
            missing.append(spot)
            continue
        have[spot] = float(rows[0].value) * k
    if missing:
        return {"verdict": NO_MEASURE, "missing": missing,
                "how_to_close": "、".join(missing) + " を実測すれば立つ"}

    # 周囲 → 半径(円換算)。幅の半分 = r、奥行の半分 = r × 比。
    def dims(circ: float) -> Tuple[float, float]:
        r = circ / (2.0 * math.pi)
        return r, r * DEPTH_RATIO

    hip_a, hip_b = dims(have["hip"])
    waist_a, waist_b = dims(have["waist"])
    chest_a, chest_b = dims(have["chest"])
    L = have["body_length"]

    # レベル: y=0 を腰、上へ胸、襟ぐり。腰下はスカートが回るので
    # 円錐に落とす(裾線まで)。
    levels = [
        (0.0, hip_a, hip_b),
        (L * 0.25, waist_a, waist_b),
        (L * 0.45, chest_a, chest_b),
        (L * 0.55, chest_a * 0.82, chest_b * 0.82),   # 肩まわり。**仮定**
        (L * 0.62, chest_a * 0.45, chest_b * 0.45),   # 襟ぐり。**仮定**
    ]
    formulas = [
        ("断面の幅の半分", "周囲 / 2π"),
        ("断面の奥行の半分", "幅の半分 × 0.70 (**仮定**。実測が要る)"),
        ("胸の高さ", "着丈 × 0.45 (**仮定**)"),
        ("肩の縮み", "胸幅 × 0.82 (**仮定**)"),
        ("襟ぐりの縮み", "胸幅 × 0.45 (**仮定**)"),
    ]
    assumed = [k for k in ("胸の高さ", "肩の縮み", "襟ぐりの縮み",
                           "断面の奥行の半分")]

    rings: List[List[Tuple[float, float, float]]] = []
    STEPS_Y = 16
    for j in range(STEPS_Y + 1):
        t = j / STEPS_Y
        y = t * levels[-1][0]
        # 上下のレベルの間を線形補間(決定的)。
        lo = max(i for i in range(len(levels)) if levels[i][0] <= y + 1e-9)
        hi = min(lo + 1, len(levels) - 1)
        y0, a0, b0 = levels[lo]
        y1, a1, b1 = levels[hi]
        u = 0.0 if y1 == y0 else (y - y0) / (y1 - y0)
        a, b = a0 + (a1 - a0) * u, b0 + (b1 - b0) * u
        ring = []
        for i in range(SEGMENTS):
            th = 2.0 * math.pi * i / SEGMENTS
            r = _ellipse_radius(a, b, th)
            ring.append((r * math.cos(th), y, r * math.sin(th)))
        rings.append(ring)

    verts: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int, int]] = []
    for ring in rings:
        for v in ring:
            verts.append(v)
    for j in range(len(rings) - 1):
        for i in range(SEGMENTS):
            k = (i + 1) % SEGMENTS
            faces.append((j * SEGMENTS + i, j * SEGMENTS + k,
                          (j + 1) * SEGMENTS + k, (j + 1) * SEGMENTS + i))

    return {
        "verdict": "ANSWER",
        "what": "dress form (mannequin)",
        "vertices": len(verts), "faces": len(faces),
        "verts": verts, "faces": faces,
        "_levels": levels,
        "measures_used": have,
        "formulas": formulas,
        "assumed": assumed,
        "not_a_body": "これは人台です。あなたの身体ではありません。"
                      "奥行の比は仮定です",
        "segments": SEGMENTS,
    }


def radius_at(man: Dict[str, Any], y: float, theta: float) -> float:
    """高さ y・方向 θ での人台の表面半径。"""
    levels = man["_levels"]
    lo = max(i for i in range(len(levels)) if levels[i][0] <= y + 1e-9)
    hi = min(lo + 1, len(levels) - 1)
    y0, a0, b0 = levels[lo]
    y1, a1, b1 = levels[hi]
    u = 0.0 if y1 == y0 else max(0.0, min(1.0, (y - y0) / (y1 - y0)))
    return _ellipse_radius(a0 + (a1 - a0) * u, b0 + (b1 - b0) * u, theta)


def dress(man: Dict[str, Any], points: List[Tuple[float, float, float]],
          gap: float = GAP_CM) -> Dict[str, Any]:
    """落とした服を人台の周りへ**再配置する**。

    各頂点を、高さはそのままに角度方向へ人台表面+空気層へ押し出す。
    腰より下は裾に向かって広がる(スカートの落ち方の代用。**物理では
    ない** — 生成物)。
    """
    if man.get("verdict") != "ANSWER":
        return dict(man)
    worn: List[Tuple[float, float, float]] = []
    min_clear = float("inf")
    for (x, y, z) in points:
        theta = math.atan2(z, x) if (x or z) else 0.0
        surface = radius_at(man, y, theta)
        # 腰(y=0)より下は、裾へ向かって直線で広げる。
        extra = 0.0
        if y < 0:
            extra = -y * 0.35          # 広がり率。**仮定**
        target = surface + gap + extra
        r = math.hypot(x, z)
        if r < 1e-9:
            worn.append((target, y, 0.0))
            min_clear = min(min_clear, target - surface)
            continue
        worn.append((x / r * target, y, z / r * target))
        min_clear = min(min_clear, target - surface)
    return {
        "verdict": "ANSWER",
        "what": "garment placed on the dress form",
        "points": [(round(p[0], 4), round(p[1], 4), round(p[2], 4))
                   for p in worn],
        "gap_cm": gap,
        "min_clearance_cm": round(min_clear, 3),
        "generated_not_evidence":
            "着せた形は生成物です。観測の出典にはなりません。"
            "布の挙動(衝突・摩擦)は計算していません",
    }


def to_obj(verts: List[Tuple[float, float, float]],
           faces: List[Tuple[int, int, int, int]]) -> str:
    out = ["# dress form (generated)", "o mannequin"]
    for v in verts:
        out.append(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}")
    for f in faces:
        out.append(f"f {f[0]+1} {f[1]+1} {f[2]+1} {f[3]+1}")
    return "\n".join(out) + "\n"
