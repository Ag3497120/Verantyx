# -*- coding: utf-8 -*-
"""合印・縫い代・布目線。**型紙に「どう組むか」を書き込む。**

事前登録: experiments/garment/PREREG14_MARKS.md

辺の長さが合っていても、**どこをどこに合わせるか**が無ければ組み方は
決まらない。`garment_sew` はこれまで縫い目の対応を弧長に比例して割って
いたが、それは「いせを全長に均等に配る」と黙って決めているのと同じ。

実務は逆で、テーラードの袖山では脇の下にいせを入れない。合印は、その
配分を**型紙の側から**決めるためにある。飾りではない。

## 層番号について

ASTM D6673-10 は **2019年1月に廃止され、後継がない**。実務の交換形式は
「DXF-ASTM」のままだが、生きた規格としては引用できない。ここで持つ層
番号は**内部の呼び名**であって、DXF を書き出すわけでも「対応」を名乗る
わけでもない。

  1 = 裁ち切り線 / 4 = 合印 / 7 = 布目線 / 14 = 出来上がり線

**縫い代は値として保存しない。** 層1と層14の差が縫い代。だから両方持つ。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

Pt = Tuple[float, float]

LAYER_CUT = 1
LAYER_NOTCH = 4
LAYER_GRAIN = 7
LAYER_SEW = 14

UNPAIRED = "UNKNOWN_NOTCH_UNPAIRED"
SELF_INTERSECT = "UNKNOWN_SEAM_ALLOWANCE_SELF_INTERSECTS"
TOO_DEEP = "UNKNOWN_NOTCH_DEEPER_THAN_ALLOWANCE"
NO_NAP = "UNKNOWN_NAP_NOT_RECORDED"
INWARD = "UNKNOWN_SEAM_ALLOWANCE_WENT_INWARD"

#: 留め継ぎの上限。角が尖ると交点が遠くへ飛ぶので、これを超えたら
#: 角を落とす。縫い代の何倍まで許すか。
MITRE_LIMIT = 4.0

#: 縫い代。**インチの原典を併記する** — cm の数字だけ出すと、どこから
#: 来た値か分からなくなる。出典: Laurel Hoffmann, Threads (2018/10-11),
#: "based on industry standards"。家庭用の既定 5/8in より狭い。
SEAM_ALLOWANCE = {
    "肩線":       (1.27, '1/2"', "肩線・脇線"),
    "脇線":       (1.27, '1/2"', "肩線・脇線"),
    "袖下線 (右)": (1.27, '1/2"', "肩線・脇線に準じる"),
    "袖下線 (左)": (1.27, '1/2"', "肩線・脇線に準じる"),
    "袖ぐり":     (0.95, '3/8"', "力のかかる曲線 (armscye)"),
    "袖山":       (0.95, '3/8"', "力のかかる曲線 (armscye)"),
    "衿ぐり":     (0.64, '1/4"', "力のかからない曲線 (neckline)"),
    "裾":         (2.54, '1"',   "並価格帯の裾。**裾は減らさない**"),
    "袖口":       (2.54, '1"',   "並価格帯の裾に準じる"),
    "中心線":     (0.0,  "—",    "**わ**（中心）なので縫い代を付けない"),
}

#: 合印の深さ(cm)。実物は 2-3mm の切り込み。
#: **縫い代の半分を超えてはいけない** — 超えると弱点になる。
NOTCH_DEPTH_CM = 0.25

#: 袖山のいせ込みを、脇の下側に入れない。
#: 出典: テーラリングの通説 "most if not all of the ease is on the outer
#: part of the sleeve. The armpit area does not need any ease at all."
EASE_FREE_TO_PITCH = True


# ------------------------------------------------------------------ 幾何
def _seg_len(a: Pt, b: Pt) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def arc_lengths(pts: Sequence[Sequence[float]]) -> List[float]:
    """折れ線の累積弧長。"""
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + _seg_len(a, b))
    return out


def at_arc(pts: Sequence[Sequence[float]], s: float) -> Pt:
    """始点から弧長 s の位置。"""
    cum = arc_lengths(pts)
    total = cum[-1]
    s = min(max(s, 0.0), total)
    for i in range(len(cum) - 1):
        if cum[i + 1] >= s or i == len(cum) - 2:
            span = cum[i + 1] - cum[i]
            t = 0.0 if span == 0 else (s - cum[i]) / span
            a, b = pts[i], pts[i + 1]
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return (pts[-1][0], pts[-1][1])


def arc_at_point(pts: Sequence[Sequence[float]], p: Pt) -> float:
    """点にいちばん近い位置の弧長。合印を高さで置くときに使う。"""
    cum = arc_lengths(pts)
    best, best_d = 0.0, float("inf")
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(
            1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
        q = (a[0] + vx * t, a[1] + vy * t)
        d = _seg_len(p, q)
        if d < best_d:
            best_d, best = d, cum[i] + _seg_len(a, q)
    return best


def arc_at_height(pts: Sequence[Sequence[float]], y: float) -> Optional[float]:
    """指定の高さ y を横切るところの弧長。**製図の水平線で合印を置く。**"""
    cum = arc_lengths(pts)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if (a[1] - y) * (b[1] - y) <= 0 and a[1] != b[1]:
            t = (y - a[1]) / (b[1] - a[1])
            return cum[i] + _seg_len(a, (a[0] + (b[0] - a[0]) * t, y))
    return None


# ------------------------------------------------------------------ 合印
def _notch(edge: str, s: float, total: float, kind: str, role: str,
           basis: str) -> Dict[str, Any]:
    return {
        "edge": edge,
        "arc_cm": round(s, 3),
        "t": round(s / total, 5) if total else 0.0,
        "kind": kind,                       # single(前) / double(後)
        "role": role,
        "depth_cm": NOTCH_DEPTH_CM,
        "layer": LAYER_NOTCH,
        "basis": basis,                     # **どの式で置いたか**
    }


def armhole_notches(piece_name: str, armhole: Sequence[Sequence[float]],
                    armhole_depth: float) -> List[Dict[str, Any]]:
    """袖ぐりの釣り合い合印。

    袖ぐりは**肩点から脇の下へ**走る(draft の作り)。だから弧長 0 が肩点、
    弧長 total が脇。

    - 肩点 / 脇: 端点そのもの
    - 振り(pitch): 伝統的な後ろの規則「襟ぐりから袖ぐり深さの半分の高さ」。
      **前は本来「前ゴージから2cm上」だが、この製図に衿とゴージが無い。**
      規則が使えないので、後ろと同じ高さで代用し、そう明記する。
    - 胸 / 肩甲: 振りと肩点の弧長の中点。いせを配る区間を割るために置く。
    """
    is_back = piece_name == "後身頃"
    total = arc_lengths(armhole)[-1]
    out = [
        _notch(("袖ぐり"), 0.0, total, "single", "肩点",
               "袖ぐりの肩側の端点"),
        _notch(("袖ぐり"), total, total, "single", "脇",
               "袖ぐりの脇側の端点"),
    ]
    pitch_y = armhole_depth / 2.0
    s_pitch = arc_at_height(armhole, pitch_y)
    if s_pitch is None:
        s_pitch = total * 0.6
        basis = "袖ぐり深さの半分の高さを横切らなかったので弧長 0.6 で代用"
    elif is_back:
        basis = ("後振り: 襟ぐりから袖ぐり深さの半分の高さ "
                 f"(y={pitch_y:.2f}cm)。テーラリングの通則")
    else:
        basis = ("前振り: 本来は前ゴージから2cm上だが、**この製図には衿と"
                 "ゴージが無い**。規則が使えないので後振りと同じ高さ "
                 f"(y={pitch_y:.2f}cm) で代用している。実測ではなく代用")
    # 後ろの釣り合い合印は伝統的に双。前は単。
    out.append(_notch("袖ぐり", s_pitch, total,
                      "double" if is_back else "single",
                      "後振り" if is_back else "前振り", basis))
    s_mid = s_pitch / 2.0
    out.append(_notch("袖ぐり", s_mid, total, "single",
                      "後肩甲" if is_back else "前胸",
                      "振りと肩点の弧長の中点。いせを配る区間を割るため"))
    return out


def cap_notches(cap: Sequence[Sequence[float]],
                front_arm: Sequence[Sequence[float]],
                back_arm: Sequence[Sequence[float]],
                front_notches: List[Dict[str, Any]],
                back_notches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """袖山の合印。**袖ぐり側の合印から、いせの配分で決める。**

    袖山は 脇(左) → 肩 → 脇(右) と走る。前半・後半それぞれが片方の
    袖ぐりと組む(`garment_sew.SEAMS` と同じ約束)。

    配分の規則:
      - 脇 〜 振り: **いせを入れない**(袖山側の弧長 = 袖ぐり側の弧長)
      - 振り 〜 肩: 残りのいせを全部ここに入れ、区間の長さに比例して割る

    これが「脇の下にいせは要らない」を数字にしたもの。均等配分なら
    この関数は要らない。
    """
    cum = arc_lengths(cap)
    total = cum[-1]
    half = total / 2.0
    out: List[Dict[str, Any]] = []

    def by_role(ns, role):
        for n in ns:
            if n["role"] == role:
                return n
        return None

    if not cap or not front_arm or not back_arm:
        return out
    for side, arm, notches, sign in (
            ("前", front_arm, front_notches, -1),
            ("後", back_arm, back_notches, +1)):
        arm_total = arc_lengths(arm)[-1]
        cap_half = half                      # この半分が受け持つ袖山長
        ease = cap_half - arm_total          # 半分あたりのいせ
        pitch = by_role(notches, "前振り" if side == "前" else "後振り")
        mid = by_role(notches, "前胸" if side == "前" else "後肩甲")
        if pitch is None or mid is None:
            continue
        # 袖ぐり側は肩点=0・脇=arm_total。脇から測り直す。
        a_pitch = arm_total - pitch["arc_cm"]      # 脇→振り
        a_mid = arm_total - mid["arc_cm"]          # 脇→胸/肩甲
        upper = arm_total - a_pitch                # 振り→肩
        # 脇からの袖山側の弧長
        c_pitch = a_pitch if EASE_FREE_TO_PITCH else a_pitch + ease * (
            a_pitch / arm_total)
        share = 0.0 if upper == 0 else (a_mid - a_pitch) / upper
        c_mid = c_pitch + (a_mid - a_pitch) + ease * share
        c_shoulder = cap_half

        # 袖山の弧長に直す。前半は 0→half が 脇(左)→肩。
        def to_cap(s_from_underarm: float) -> float:
            return (s_from_underarm if sign < 0
                    else total - s_from_underarm)

        base = ("袖ぐり側の合印から、脇〜振りはいせ0・振り〜肩に"
                f"いせ{ease:.2f}cmを区間長で配って決めた")
        out.append(_notch("袖山", to_cap(0.0), total, "single",
                          f"脇({side})", "袖山の端点。袖ぐりの脇と組む"))
        out.append(_notch("袖山", to_cap(c_pitch), total,
                          "double" if side == "後" else "single",
                          f"{side}振り", base))
        out.append(_notch("袖山", to_cap(c_mid), total, "single",
                          "前胸" if side == "前" else "後肩甲", base))
        out.append(_notch("袖山", to_cap(c_shoulder), total, "single",
                          f"肩点({side})", "袖山の頂点。袖ぐりの肩点と組む"))
    return out


def pair_notches(pieces: Dict[str, Any],
                 notches: Dict[str, List[Dict[str, Any]]]
                 ) -> Dict[str, Any]:
    """合印を対にする。**相手のいない合印は返さない。**

    合印は一枚の上の印ではなく、二枚の間の約束。片側にしか無い印は
    組み方を決められないので、印として通さない。
    """
    from .garment_sew import SEAMS

    pairs: List[Dict[str, Any]] = []
    unpaired: List[Dict[str, Any]] = []
    used = set()
    for spec in SEAMS:
        (pa, ea), (pb, eb) = spec["a"], spec["b"]
        label = spec.get("label", f"{pa}/{ea} ↔ {pb}/{eb}")
        side = "前" if pb == "前身頃" else "後"
        na = [n for n in notches.get(pa, []) if n["edge"] == ea]
        nb = [n for n in notches.get(pb, []) if n["edge"] == eb]
        for a in na:
            role = a["role"].replace(f"({side})", "")
            match = [b for b in nb if b["role"] == role]
            if ea == "袖山" and f"({side})" not in a["role"] \
                    and a["role"] not in ("前振り", "後振り",
                                          "前胸", "後肩甲"):
                continue
            if ea == "袖山" and a["role"] in ("前振り", "前胸") \
                    and side != "前":
                continue
            if ea == "袖山" and a["role"] in ("後振り", "後肩甲") \
                    and side != "後":
                continue
            if not match:
                continue
            b = match[0]
            key = (pa, ea, a["arc_cm"], pb, eb, b["arc_cm"])
            if key in used:
                continue
            used.add(key)
            pairs.append({
                "seam": label, "role": role,
                "a": {"piece": pa, "edge": ea, "arc_cm": a["arc_cm"],
                      "kind": a["kind"]},
                "b": {"piece": pb, "edge": eb, "arc_cm": b["arc_cm"],
                      "kind": b["kind"]},
                "kinds_agree": a["kind"] == b["kind"],
            })
    for piece, ns in notches.items():
        for n in ns:
            hit = any((p["a"]["piece"] == piece
                       and p["a"]["arc_cm"] == n["arc_cm"]
                       and p["a"]["edge"] == n["edge"])
                      or (p["b"]["piece"] == piece
                          and p["b"]["arc_cm"] == n["arc_cm"]
                          and p["b"]["edge"] == n["edge"])
                      for p in pairs)
            if not hit:
                unpaired.append({"piece": piece, **n})
    return {"pairs": pairs, "unpaired": unpaired}


def ease_by_segment(pairs: List[Dict[str, Any]],
                    pieces: Dict[str, Any]) -> List[Dict[str, Any]]:
    """合印で区切った区間ごとのいせ。**脇の下が 0 に寄ることを見る。**"""
    rows: List[Dict[str, Any]] = []
    by_seam: Dict[str, List[Dict[str, Any]]] = {}
    for p in pairs:
        by_seam.setdefault(p["seam"], []).append(p)
    for seam, ps in by_seam.items():
        ps = sorted(ps, key=lambda p: p["a"]["arc_cm"])
        for x, y in zip(ps, ps[1:]):
            da = abs(y["a"]["arc_cm"] - x["a"]["arc_cm"])
            db = abs(y["b"]["arc_cm"] - x["b"]["arc_cm"])
            rows.append({
                "seam": seam,
                "from": x["role"], "to": y["role"],
                "cap_cm": round(da, 3), "armhole_cm": round(db, 3),
                "ease_cm": round(da - db, 3),
                "ease_pct": round((da - db) / db * 100, 2) if db else None,
            })
    return rows


# --------------------------------------------------------------- 縫い代
def _label_segment(a: Pt, b: Pt, edges: Dict[str, Any],
                   hem_y: Optional[float], piece_name: str = "") -> str:
    """輪郭の一区間が、どの名前付き辺か。**近さではなく一致で決める。**"""
    for name, rec in edges.items():
        pts = rec["points"]
        for p, q in zip(pts, pts[1:]):
            if ((abs(p[0] - a[0]) < 1e-6 and abs(p[1] - a[1]) < 1e-6
                 and abs(q[0] - b[0]) < 1e-6 and abs(q[1] - b[1]) < 1e-6)
                or (abs(p[0] - b[0]) < 1e-6 and abs(p[1] - b[1]) < 1e-6
                    and abs(q[0] - a[0]) < 1e-6 and abs(q[1] - a[1]) < 1e-6)):
                return name
    if abs(a[0]) < 1e-6 and abs(b[0]) < 1e-6:
        return "中心線"
    if hem_y is not None and abs(a[1] - hem_y) < 1e-6 \
            and abs(b[1] - hem_y) < 1e-6:
        # 袖の下端は裾ではなく袖口。値は同じでも名前が違えば読み手が迷う。
        return "袖口" if piece_name == "袖" else "裾"
    return "衿ぐり"


def _signed_area(poly: Sequence[Sequence[float]]) -> float:
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i][0], poly[i][1]
        x2, y2 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def _segments_cross(p1, p2, p3, p4) -> bool:
    def d(a, b, c):
        return ((b[0] - a[0]) * (c[1] - a[1])
                - (b[1] - a[1]) * (c[0] - a[0]))
    d1, d2 = d(p3, p4, p1), d(p3, p4, p2)
    d3, d4 = d(p1, p2, p3), d(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def offset_outline(outline: Sequence[Sequence[float]],
                   edges: Dict[str, Any],
                   allowance: Optional[Dict[str, float]] = None,
                   piece_name: str = "") -> Dict[str, Any]:
    """出来上がり線から**外へ**縫い代を出し、裁ち切り線を作る。

    辺ごとに縫い代が違うので、区間ごとに直線をずらして、隣どうしの
    交点を新しい頂点にする(留め継ぎ)。

    **出来上がり線は返り値でも動かさない。** 層14と層1を両方持つのが
    この関数の目的で、片方を上書きしたら縫い代は復元できない。
    """
    sa = dict(allowance or {})
    poly = [(float(p[0]), float(p[1])) for p in outline]
    n = len(poly)
    if n < 3:
        return {"verdict": "UNKNOWN_OUTLINE_TOO_SHORT"}
    ys = [p[1] for p in poly]
    hem_y = max(ys)
    # **向きは推論せず、後で面積で確かめる。** ここを取り違えると縫い代が
    # 内側に付き、図を描くまで気付かない(2026-08-23 実測: 三枚とも内側に
    # 付いていて、VN5-VN8/VN11 は全部通っていた)。
    outward = 1.0 if _signed_area(poly) > 0 else -1.0

    labels, offs, normals = [], [], []
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        name = _label_segment(a, b, edges, hem_y, piece_name)
        labels.append(name)
        width = sa.get(name, SEAM_ALLOWANCE.get(name, (0.0,))[0])
        offs.append(width)
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-9
        normals.append((outward * dy / L, -outward * dx / L))

    cut: List[Pt] = []
    bevelled = 0
    for i in range(n):
        j = (i - 1) % n
        a1 = (poly[j][0] + normals[j][0] * offs[j],
              poly[j][1] + normals[j][1] * offs[j])
        b1 = (poly[i][0] + normals[j][0] * offs[j],
              poly[i][1] + normals[j][1] * offs[j])
        a2 = (poly[i][0] + normals[i][0] * offs[i],
              poly[i][1] + normals[i][1] * offs[i])
        b2 = (poly[(i + 1) % n][0] + normals[i][0] * offs[i],
              poly[(i + 1) % n][1] + normals[i][1] * offs[i])
        d1 = (b1[0] - a1[0], b1[1] - a1[1])
        d2 = (b2[0] - a2[0], b2[1] - a2[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        limit = MITRE_LIMIT * max(offs[j], offs[i], 1e-9)
        if abs(den) < 1e-9:
            cut.append(((b1[0] + a2[0]) / 2.0, (b1[1] + a2[1]) / 2.0))
            continue
        t = ((a2[0] - a1[0]) * d2[1] - (a2[1] - a1[1]) * d2[0]) / den
        q = (a1[0] + d1[0] * t, a1[1] + d1[1] * t)
        if _seg_len(q, poly[i]) > limit:
            # **尖った角で留め継ぎが飛ぶ。** 袖山の先で裁ち切り線が
            # 243cm まで伸びていた(実測)。角を落として二点にする。
            cut.append(b1)
            cut.append(a2)
            bevelled += 1
        else:
            cut.append(q)

    bad = []
    m = len(cut)
    for i in range(m):
        for j in range(i + 2, m):
            if i == 0 and j == m - 1:
                continue
            if _segments_cross(cut[i], cut[(i + 1) % m],
                               cut[j], cut[(j + 1) % m]):
                bad.append([i, j])
    if bad:
        return {"verdict": SELF_INTERSECT,
                "crossing_segments": bad[:8],
                "how_to_close": "縫い代を狭めるか、輪郭の角を丸める",
                "why": "外にずらした線が自分と交わりました。この型紙は"
                       "この縫い代では裁てません"}

    # **外に付いたことを面積で確かめる。** 向きの取り違えは、図を描くまで
    # 他のどの検査にも掛からない。
    if abs(_signed_area(cut)) <= abs(_signed_area(poly)):
        return {"verdict": INWARD,
                "sew_area_cm2": round(abs(_signed_area(poly)), 2),
                "cut_area_cm2": round(abs(_signed_area(cut)), 2),
                "why": "縫い代が内側に付きました。裁ち切り線は必ず"
                       "出来上がり線を囲みます"}

    return {
        "verdict": "ANSWER",
        "sew_line": [[round(x, 3), round(y, 3)] for x, y in poly],
        "bevelled_corners": bevelled,
        "mitre_limit": MITRE_LIMIT,
        "sew_area_cm2": round(abs(_signed_area(poly)), 2),
        "cut_area_cm2": round(abs(_signed_area(cut)), 2),
        "cut_line": [[round(x, 3), round(y, 3)] for x, y in cut],
        "segment_allowance": [
            {"from": i, "edge": labels[i], "cm": round(offs[i], 3),
             "imperial": SEAM_ALLOWANCE.get(labels[i], (0, "—", ""))[1],
             "why": SEAM_ALLOWANCE.get(labels[i], (0, "—", ""))[2]}
            for i in range(n)],
        "layers": {"sew_line": LAYER_SEW, "cut_line": LAYER_CUT},
        "not_stored_as_a_value":
            "縫い代は値として持ちません。出来上がり線と裁ち切り線の差が"
            "縫い代です。片方だけ持つと復元できません",
    }


def check_notch_depth(notches: Sequence[Dict[str, Any]],
                      allowance: Dict[str, float]) -> Dict[str, Any]:
    """合印の深さは縫い代の半分まで。**超えたら通さない。**"""
    bad = []
    for n in notches:
        w = allowance.get(n["edge"], SEAM_ALLOWANCE.get(
            n["edge"], (0.0,))[0])
        if w <= 0:
            continue
        if n["depth_cm"] > w / 2.0 + 1e-9:
            bad.append({"edge": n["edge"], "role": n["role"],
                        "depth_cm": n["depth_cm"], "max_cm": round(w / 2, 3)})
    return {"verdict": TOO_DEEP if bad else "ANSWER", "violations": bad,
            "rule": "切り込みが縫い代の半分を超えると弱点になる"}


# ------------------------------------------------------------- 布目線
def grain_line(piece: Dict[str, Any], angle_deg: float = 90.0,
               nap: Optional[str] = None) -> Dict[str, Any]:
    """布目線。**一本の直線で、意味を持つのは向きだけ。**

    位置は輪郭の内側なら自由(規格もそう言っている)。だから重心に置く。
    角度は x 軸から反時計回り。90 度 = 中心線と平行 = たて地。

    向きの扱い(一方向/二方向/四方向)は**生地の性質**であって型紙の性質
    ではない。毛並みが台帳に無ければ `UNKNOWN_NAP_NOT_RECORDED` を返す
    — 「毛並みが無い」ではなく「記録されていない」。
    """
    xs = [p[0] for p in piece["outline"]]
    ys = [p[1] for p in piece["outline"]]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    half = (max(ys) - min(ys)) * 0.3
    r = math.radians(angle_deg)
    a = (cx - math.cos(r) * half, cy - math.sin(r) * half)
    b = (cx + math.cos(r) * half, cy + math.sin(r) * half)
    return {
        "piece": piece["name"],
        "line": [[round(a[0], 3), round(a[1], 3)],
                 [round(b[0], 3), round(b[1], 3)]],
        "angle_deg": round(angle_deg % 180.0, 3),
        "orientation": nap or NO_NAP,
        "layer": LAYER_GRAIN,
        "means": "たて地の向き。耳(selvage)と平行に置く",
        "position_is_free":
            "線の位置に意味はありません。意味を持つのは向きだけです",
    }


def rotate_piece(piece: Dict[str, Any], grain: Dict[str, Any],
                 notches: Sequence[Dict[str, Any]],
                 deg: float) -> Dict[str, Any]:
    """型紙を回す。**布目線も一緒に回す。**

    型入れで型紙を傾けたとき、布目線が付いて回らなければバイアス裁ちを
    表現できない。回した後も「布目に対する角度」は保存される。
    """
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)

    def rot(p):
        return [round(p[0] * c - p[1] * s, 4), round(p[0] * s + p[1] * c, 4)]

    return {
        "name": piece["name"],
        "outline": [rot(p) for p in piece["outline"]],
        "grain": {**grain,
                  "line": [rot(p) for p in grain["line"]],
                  "angle_deg": round((grain["angle_deg"] + deg) % 180.0, 3)},
        # 合印は弧長で持っているので、回しても値は変わらない。
        # **これが弧長で持つ理由。**
        "notches": [dict(n) for n in notches],
        "rotated_deg": deg,
    }


# ------------------------------------------------------------------ 統合
def apply(draft_out: Dict[str, Any],
          fabrics: Any = None) -> Dict[str, Any]:
    """型紙に合印・縫い代・布目線を付ける。"""
    if draft_out.get("verdict") != "ANSWER":
        return dict(draft_out)

    by_name = {p["name"]: p for p in draft_out["pieces"]}
    chest = draft_out["used"].get("chest")
    armhole_depth = (chest / 8.0 + 6.5) if chest else None

    notches: Dict[str, List[Dict[str, Any]]] = {}
    for name in ("前身頃", "後身頃"):
        p = by_name.get(name)
        if not p or armhole_depth is None:
            continue
        notches[name] = armhole_notches(
            name, p["edges"]["袖ぐり"]["points"], armhole_depth)

    if "袖" in by_name and "前身頃" in notches and "後身頃" in notches:
        notches["袖"] = cap_notches(
            by_name["袖"]["edges"]["袖山"]["points"],
            by_name["前身頃"]["edges"]["袖ぐり"]["points"],
            by_name["後身頃"]["edges"]["袖ぐり"]["points"],
            notches["前身頃"], notches["後身頃"])

    paired = pair_notches(by_name, notches)
    ease = ease_by_segment(paired["pairs"], by_name)

    allowances, grains, depth_checks = {}, [], []
    for name, p in by_name.items():
        off = offset_outline(p["outline"], p["edges"],
                             piece_name=name)
        allowances[name] = off
        grains.append(grain_line(p, 90.0, _nap_of(fabrics)))
        depth_checks.append({
            "piece": name,
            **check_notch_depth(notches.get(name, []), {})})

    out = dict(draft_out)
    out["notches"] = notches
    out["notch_pairs"] = paired["pairs"]
    out["notch_unpaired"] = paired["unpaired"]
    out["ease_by_segment"] = ease
    out["seam_allowance"] = allowances
    out["grain"] = grains
    out["notch_depth_checks"] = depth_checks
    out["marks_note"] = (
        "合印は二枚の間の約束です。相手のいない印は通していません。"
        "いせは合印で区切った区間ごとに配っていて、脇の下には入れません")
    out["standard_note"] = (
        "層番号は内部の呼び名です。ASTM D6673-10 は 2019年1月に廃止され"
        "後継がないので、規格対応は名乗りません")
    return out


def _nap_of(fabrics: Any) -> Optional[str]:
    """生地台帳に毛並みの記録があるか。無ければ None(=未記録)。"""
    if fabrics is None:
        return None
    try:
        for e in getattr(fabrics, "entries", []):
            if getattr(e, "prop", "") in ("nap", "毛並み", "direction"):
                return str(getattr(e, "value", "")) or None
    except Exception:
        return None
    return None
