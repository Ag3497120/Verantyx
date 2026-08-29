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
#: 人台より上/下には身体が無い。**これは異常ではなく事実。** 人台は胴で、
#: ロングコートの裾がその下に垂れるのは実際にそうなる。以前ここは例外を
#: 投げていて、すべての服で ``dress`` が落ちていた — 「この高さに身体は
#: 無い」という真で有用な答えを、拒否ではなく故障として表していた。
NO_BODY = "UNKNOWN_NO_BODY_AT_THIS_HEIGHT"


def _ellipse_radius(a: float, b: float, theta: float) -> float:
    """楕円の θ 方向半径。a=幅の半分, b=奥行の半分。"""
    # A closed garment outline can legitimately end in a single apex (for
    # example the point of a triangular train).  At that exact height both
    # semi-axes are zero.  The polar ellipse formula is then 0/0, while the
    # geometric cross-section is unambiguously the origin itself.
    if abs(a) <= 1e-12 and abs(b) <= 1e-12:
        return 0.0
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


def radius_at(man: Dict[str, Any], y: float,
              theta: float) -> Optional[float]:
    """高さ y・方向 θ での人台の表面半径。**身体が無ければ None。**

    人台は胴体で、上端は襟ぐり、下端は腰。その外側に身体は無い。裾が
    人台より下に垂れるロングコートは正常で、そこでの正しい答えは
    「この高さに身体は無い」であって例外ではない。呼ぶ側は None を
    受けなければならない。
    """
    levels = man["_levels"]
    if y < levels[0][0] - 1e-9 or y > levels[-1][0] + 1e-9:
        return None
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
    al = align(man, points)
    if al["verdict"] != "ANSWER":
        return al
    worn: List[Tuple[float, float, float]] = []
    min_clear = float("inf")
    below = 0
    for (x, y, z) in al["points"]:
        theta = math.atan2(z, x) if (x or z) else 0.0
        surface = radius_at(man, y, theta)
        if surface is None:
            # 身体が無い高さ。押し出す相手がいないので、布は自分の半径の
            # まま。**裾の広がりはここでは作らない** — 以前あった
            # ``-y * 0.35`` は仮定で、身体の無い場所の形を発明していた。
            below += 1
            worn.append((x, y, z))
            continue
        target = surface + gap
        r = math.hypot(x, z)
        if r < 1e-9:
            worn.append((target, y, 0.0))
        else:
            worn.append((x / r * target, y, z / r * target))
        min_clear = min(min_clear, gap)
    return {
        "verdict": "ANSWER",
        "what": "garment placed on the dress form",
        "points": [(round(p[0], 4), round(p[1], 4), round(p[2], 4))
                   for p in worn],
        "gap_cm": gap,
        "alignment": al["rule"],
        "points_below_the_form": below,
        "min_clearance_cm": (None if min_clear == float("inf")
                             else round(min_clear, 3)),
        "clearance_is_by_construction":
            "身体のある高さでは、この配置は全点を表面+空気層へ押し出すので"
            "隙間は必ず gap と等しくなります。**この形から着心地は読めません。**"
            "落ちたままの服と身体の距離は clearance() で測ってください",
        "generated_not_evidence":
            "着せた形は生成物です。観測の出典にはなりません。"
            "布の挙動(衝突・摩擦)は計算していません",
    }


def align(man: Dict[str, Any],
          points: List[Tuple[float, float, float]]) -> Dict[str, Any]:
    """服を人台の座標系へ移す。**規則を出力に載せる。**

    二つの座標系は原点も向きも違う。実測（参照コート・着丈112cm）::

        服   y -130.92 .. -5.89   x 1.0 .. 40.4 (中心 20.7)
        人台 y    0.00 .. 69.44   軸 x=0, z=0

    合わせ方は解剖学的な基準点で決める。**服は肩から吊るもの**なので、
    服の上端を人台の上端（襟ぐり）に合わせ、左右は軸に載せる。裾が人台の
    下に出るのは正常で、そこには身体が無いだけ。

    **服の幾何は動かしていない** — 剛体移動だけで、形は不変。
    """
    if man.get("verdict") != "ANSWER":
        return dict(man)
    if not points:
        return {"verdict": "UNKNOWN_NO_POINTS",
                "how_to_close": "落とした服の頂点が要ります"}
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    top = man["_levels"][-1][0]
    dy = top - max(ys)
    dx = -(min(xs) + max(xs)) / 2.0
    dz = -(min(zs) + max(zs)) / 2.0
    moved = [(x + dx, y + dy, z + dz) for (x, y, z) in points]
    return {
        "verdict": "ANSWER",
        "points": moved,
        "rule": {
            "anchor": "服の上端 → 人台の上端(襟ぐり)",
            "why": "服は肩から吊る。上端どうしが解剖学的に対応する",
            "dy_cm": round(dy, 4), "dx_cm": round(dx, 4),
            "dz_cm": round(dz, 4),
            "garment_was": [round(min(ys), 2), round(max(ys), 2)],
            "form_is": [round(man["_levels"][0][0], 2), round(top, 2)],
            "rigid": "平行移動のみ。服の形は変えていない",
        },
    }


#: 「密着」とみなす隙間(cm)。**閾値であって事実ではない。**
CLING_CM = 1.5


def clearance(man: Dict[str, Any],
              points: List[Tuple[float, float, float]],
              cling_cm: float = CLING_CM) -> Dict[str, Any]:
    """**落ちたままの服**と人台の距離。最初の誠実なフィット評価。

    ``dress`` の出力を測ってはいけない — あれは全点を表面+空気層へ押し出す
    ので、隙間は構成上どこでも空気層と等しくなる。落ちようのない検査。

    測るのはソルバが出した形そのもの。値の意味::

        正       布は身体から離れている(隙間)
        0..cling 密着
        負       **布が身体の中にある**

    負が出るのは欠陥の報告ではなく、**この企画が衝突を計算していないという
    事実の測定**。ドレープは身体を知らないので、身体のある場所へ落ちる。
    どこでどれだけ食い込むかが、衝突を入れる前に分かる唯一の数字。
    """
    if man.get("verdict") != "ANSWER":
        return dict(man)
    al = align(man, points)
    if al["verdict"] != "ANSWER":
        return al
    rows: List[Dict[str, Any]] = []
    inside = free = clinging = apart = 0
    lo = hi = None
    worst: Optional[Dict[str, Any]] = None
    for i, (x, y, z) in enumerate(al["points"]):
        theta = math.atan2(z, x) if (x or z) else 0.0
        surface = radius_at(man, y, theta)
        if surface is None:
            free += 1
            rows.append({"i": i, "y": round(y, 3), "state": NO_BODY})
            continue
        c = math.hypot(x, z) - surface
        lo = c if lo is None else min(lo, c)
        hi = c if hi is None else max(hi, c)
        if c < 0.0:
            inside += 1
            st = "INSIDE_THE_BODY"
        elif c <= cling_cm:
            clinging += 1
            st = "CLINGING"
        else:
            apart += 1
            st = "APART"
        row = {"i": i, "y": round(y, 3), "clearance_cm": round(c, 4),
               "state": st}
        rows.append(row)
        if worst is None or c < worst["clearance_cm"]:
            worst = row
    return {
        "verdict": "ANSWER",
        "what": "distance from the garment AS IT FELL to the dress form",
        "per_point": rows,
        "points": len(rows),
        "inside_the_body": inside,
        "clinging": clinging,
        "apart": apart,
        "no_body_at_that_height": free,
        "cling_threshold_cm": cling_cm,
        "min_clearance_cm": None if lo is None else round(lo, 4),
        "max_clearance_cm": None if hi is None else round(hi, 4),
        "worst": worst,
        "alignment": al["rule"],
        "negative_means": (
            "布が身体の中にあります。ドレープは衝突を計算していないので、"
            "身体のある場所へ落ちます。これはこの企画の既知の限界の測定で"
            "あって、型紙の欠陥の主張ではありません"),
        "not_a_fit_verdict": (
            "距離であって着心地ではありません。圧迫・伸び・シワには接触の"
            "物理が要り、曲げ剛性も摩擦もまだありません"),
    }

def to_obj(verts: List[Tuple[float, float, float]],
           faces: List[Tuple[int, int, int, int]]) -> str:
    out = ["# dress form (generated)", "o mannequin"]
    for v in verts:
        out.append(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}")
    for f in faces:
        out.append(f"f {f[0]+1} {f[1]+1} {f[2]+1} {f[3]+1}")
    return "\n".join(out) + "\n"
