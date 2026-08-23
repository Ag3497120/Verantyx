# -*- coding: utf-8 -*-
"""型紙を引く。**この道具の簡易製図であって、既存の製図法ではない。**

事前登録: experiments/garment/PREREG11_PATTERN.md

文化式・ドレメ式は公表された体系で、正しく実装したと私は検証できない。
名乗れば検証できない主張になる。ここは**全ての式を書き出して監査可能に
する** — 式が見えれば服飾の人が「この式は違う」と言える。名前だけ借りると
それができない。

型紙は観測ではない。実物の型紙を誰も見ていない。引いた型紙は寸法からの
派生であって、「この一着の型紙」ではない。

**足りない寸法を既定で埋めない。** 立体(見るもの)は既定で補ってよいが、
型紙は裁つものなので、無い寸法は無いと言って引かない。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

#: 製図に要る寸法。**一つでも欠ければ引かない。**
REQUIRED = ("body_length", "chest", "shoulder")

#: 袖に要る寸法。袖だけ引けないことはある。
SLEEVE_REQUIRED = ("sleeve_length",)

#: この道具の式。**全部書き出す。** 監査できない式は使わない。
#: 単位は cm。chest は仕上がり周囲(ゆとり込み)として扱う。
FORMULAS = {
    "身頃幅 (前後それぞれ)": "chest / 4",
    "袖ぐり深さ": "chest / 8 + 6.5",
    "肩線の下がり": "shoulder / 10",
    "衿ぐり幅 (前後共通)": "chest / 12 + 1.5",
    "前衿ぐり深さ": "chest / 12 + 2.0",
    "後衿ぐり深さ": "2.0（固定）",
    "袖山の高さ": "袖ぐり深さ × 0.78",
    "袖幅 (袖口側)": "chest / 8 + 2.0",
    "袖山の幅": "袖山の長さが「袖ぐりの合計 + いせ込み」になるよう解く",
    "いせ込み": "2.0cm（この道具の既定）",
}

#: 袖山を袖ぐりより長くする分(cm)。**この道具が決めた値**で、
#: 服飾の標準ではない。いせ込みは生地と縫い手で変わる。
EASE_IN = 2.0


def _need(measures: Any, spots: Tuple[str, ...]) -> Tuple[Dict[str, float],
                                                          List[str]]:
    """必要な寸法を集める。**既定で埋めない。**"""
    have: Dict[str, float] = {}
    if measures is not None:
        sheet = measures.sheet()
        for row in sheet["measured"] + sheet["derived"]:
            have[row["spot"]] = float(row["value"])
    missing = [s for s in spots if s not in have]
    return have, missing


def _length(points: List[Tuple[float, float]]) -> float:
    """折れ線の長さ。縫い合わせの検算に使う。"""
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    return round(total, 2)


def _area(points: List[Tuple[float, float]]) -> float:
    """多角形の面積(靴紐公式)。生地量の見積もりに使う。"""
    n = len(points)
    s = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return round(abs(s) / 2.0, 1)


def draft(measures: Any) -> Dict[str, Any]:
    """型紙を引く。返すのはピースと、**縫い合わせの検算**。"""
    have, missing = _need(measures, REQUIRED)
    if missing:
        return {
            "verdict": "UNKNOWN_MISSING_MEASUREMENTS",
            "missing": list(missing),
            "how_to_close": "、".join(missing) + " を実測すれば引ける",
            "formulas": dict(FORMULAS),
            "note": "型紙は裁つものなので、足りない寸法を既定で埋めません。"
                    "立体(見るもの)とはここが違います",
        }

    L = have["body_length"]
    chest = have["chest"]
    shoulder = have["shoulder"]

    half = chest / 4.0                    # 身頃幅
    armhole_depth = chest / 8.0 + 6.5     # 袖ぐり深さ
    shoulder_drop = shoulder / 10.0       # 肩線の下がり
    neck_w = chest / 12.0 + 1.5           # 衿ぐり幅
    front_neck_d = chest / 12.0 + 2.0     # 前衿ぐり深さ
    back_neck_d = 2.0                     # 後衿ぐり深さ

    pieces: List[Dict[str, Any]] = []

    def piece(name: str, outline: List[Tuple[float, float]],
              edges: Dict[str, List[Tuple[float, float]]]):
        pieces.append({
            "name": name,
            "outline": [[round(x, 2), round(y, 2)] for x, y in outline],
            "edges": {k: {"points": [[round(x, 2), round(y, 2)]
                                     for x, y in v],
                          "length": _length(v)}
                      for k, v in edges.items()},
            "area_cm2": _area(outline),
        })

    # ---- 後身頃 ----------------------------------------------------
    # 原点は中心・衿ぐり位置。x は外向き、y は下向き。
    back_shoulder_end = (shoulder / 2.0, shoulder_drop)
    back_armhole = [
        back_shoulder_end,
        (half - 1.0, armhole_depth * 0.55),
        (half, armhole_depth),
    ]
    back_outline = [
        (0.0, back_neck_d),
        (neck_w, 0.0),
        back_shoulder_end,
        *back_armhole[1:],
        (half, L),
        (0.0, L),
    ]
    piece("後身頃", back_outline, {
        "袖ぐり": back_armhole,
        "肩線": [(neck_w, 0.0), back_shoulder_end],
        "脇線": [(half, armhole_depth), (half, L)],
    })

    # ---- 前身頃 ----------------------------------------------------
    front_shoulder_end = (shoulder / 2.0, shoulder_drop)
    front_armhole = [
        front_shoulder_end,
        (half - 1.6, armhole_depth * 0.55),
        (half, armhole_depth),
    ]
    front_outline = [
        (0.0, front_neck_d),
        (neck_w, 0.0),
        front_shoulder_end,
        *front_armhole[1:],
        (half, L),
        (0.0, L),
    ]
    piece("前身頃", front_outline, {
        "袖ぐり": front_armhole,
        "肩線": [(neck_w, 0.0), front_shoulder_end],
        "脇線": [(half, armhole_depth), (half, L)],
    })

    # ---- 袖 --------------------------------------------------------
    sleeve_missing: List[str] = []
    _, sleeve_missing = _need(measures, SLEEVE_REQUIRED)
    if not sleeve_missing:
        sl = have["sleeve_length"]
        cap_h = armhole_depth * 0.78
        cuff_half = chest / 8.0 + 2.0
        armhole_total = (_length(back_armhole) + _length(front_armhole))
        # 袖山は袖ぐりに合わせて引く。**合わせるのが目的**で、
        # 合ったことを主張するのではなく、後で差を出して確かめる。
        # **袖山は袖ぐりに合わせて解く。** 比で出すと合わない
        # (実測: 差 +4.28cm で「縫えない」と検算が出した)。
        # 幅を二分探索して、袖山の長さが「袖ぐり + いせ込み」になる
        # ところを取る。決定的で、式も回数も書いてある。
        target = armhole_total + EASE_IN

        def cap_points(w: float):
            return [(-w, cap_h), (-w * 0.5, cap_h * 0.22), (0.0, 0.0),
                    (w * 0.5, cap_h * 0.22), (w, cap_h)]

        lo, hi = 0.1, armhole_total
        for _ in range(60):        # 60回で十分に収束する
            mid = (lo + hi) / 2.0
            if _length(cap_points(mid)) < target:
                lo = mid
            else:
                hi = mid
        w = round((lo + hi) / 2.0, 4)
        cap = cap_points(w)
        sleeve_outline = [
            *cap,
            (cuff_half, cap_h + sl),
            (-cuff_half, cap_h + sl),
        ]
        piece("袖", sleeve_outline, {
            "袖山": cap,
            "袖下線 (右)": [(w, cap_h), (cuff_half, cap_h + sl)],
            "袖下線 (左)": [(-w, cap_h), (-cuff_half, cap_h + sl)],
        })

    # ---- 縫い合わせの検算 -------------------------------------------
    checks = _seam_checks(pieces)

    return {
        "verdict": "ANSWER",
        "pieces": pieces,
        "seam_checks": checks,
        "used": {k: round(v, 2) for k, v in have.items()
                 if k in REQUIRED + SLEEVE_REQUIRED},
        "sleeve_missing": sleeve_missing,
        "formulas": dict(FORMULAS),
        "total_area_cm2": round(sum(p["area_cm2"] for p in pieces), 1),
        "seam_allowance":
            "縫い代は入っていません。引いたのは出来上がり線です。",
        "not_a_published_system":
            "これはこの道具の簡易製図で、文化式・ドレメ式などの公表された"
            "製図法ではありません。式は全て出しているので、違うと思ったら"
            "式を見てください。",
        "note": "型紙は寸法からの派生で、実物の型紙を見たものではありません",
    }


def _seam_checks(pieces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """縫い合わせる辺の長さが合うか。**差を必ず出す。**

    合っていることを主張するのではなく、差を出す。合わなければ、
    その型紙は縫えない — 裁ってから分かるより先に言う。
    """
    by_name = {p["name"]: p for p in pieces}
    out: List[Dict[str, Any]] = []

    def compare(label: str, a: Tuple[str, str], b: Tuple[str, str],
                tolerance: float, why: str):
        pa, ea = a
        pb, eb = b
        if pa not in by_name or pb not in by_name:
            return
        la = by_name[pa]["edges"][ea]["length"]
        lb = by_name[pb]["edges"][eb]["length"]
        diff = round(la - lb, 2)
        out.append({
            "label": label, "a": f"{pa}/{ea}", "b": f"{pb}/{eb}",
            "length_a": la, "length_b": lb, "difference": diff,
            "tolerance": tolerance,
            "sewable": abs(diff) <= tolerance,
            "why": why,
        })

    compare("肩線", ("前身頃", "肩線"), ("後身頃", "肩線"), 0.3,
            "前後の肩線が合わないと肩が縫えない")
    compare("脇線", ("前身頃", "脇線"), ("後身頃", "脇線"), 0.3,
            "前後の脇線が合わないと脇が縫えない")
    if "袖" in by_name:
        cap = by_name["袖"]["edges"]["袖山"]["length"]
        armhole = (by_name["前身頃"]["edges"]["袖ぐり"]["length"]
                   + by_name["後身頃"]["edges"]["袖ぐり"]["length"])
        diff = round(cap - armhole, 2)
        out.append({
            "label": "袖山と袖ぐり",
            "a": "袖/袖山", "b": "前後身頃/袖ぐり の合計",
            "length_a": cap, "length_b": round(armhole, 2),
            "difference": diff,
            # 袖山は袖ぐりよりわずかに長いのが普通(いせ込み)。
            # ただし**それを既定で正しいとしない** — 範囲を出して人が見る。
            "tolerance": 4.0,
            "sewable": -0.5 <= diff <= 4.0,
            "why": "袖山は袖ぐりよりやや長いのが普通(いせ込み)。"
                   "短ければ入らず、長すぎれば縫い込めない",
        })
    return out


def to_svg(draft_out: Dict[str, Any]) -> str:
    """型紙を SVG にする。**注記を図の中に残す。**"""
    if draft_out.get("verdict") != "ANSWER":
        return ""
    pad, gap = 30.0, 20.0
    x_cursor = pad
    parts: List[str] = []
    max_y = 0.0
    for p in draft_out["pieces"]:
        xs = [pt[0] for pt in p["outline"]]
        ys = [pt[1] for pt in p["outline"]]
        w = max(xs) - min(xs)
        shift = x_cursor - min(xs)
        pts = " ".join(f"{x + shift:.1f},{y + pad:.1f}"
                       for x, y in p["outline"])
        parts.append(f'<polygon points="{pts}" fill="none" stroke="#111" '
                     f'stroke-width="0.8" data-piece="{p["name"]}"/>')
        parts.append(f'<text x="{x_cursor:.1f}" y="{pad - 8:.1f}" '
                     f'font-size="9" fill="#111">{p["name"]} '
                     f'{p["area_cm2"]}cm²</text>')
        x_cursor += w + gap
        max_y = max(max_y, max(ys))
    width = int(x_cursor + pad)
    height = int(max_y + pad * 2 + 60)
    head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#fff"/>']
    y = max_y + pad + 20
    foot = [
        f'<text x="{pad}" y="{y:.1f}" font-size="9" fill="#b04">'
        f'{draft_out["seam_allowance"]}</text>',
        f'<text x="{pad}" y="{y + 14:.1f}" font-size="9" fill="#666">'
        f'{draft_out["not_a_published_system"]}</text>',
        f'<text x="{pad}" y="{y + 28:.1f}" font-size="9" fill="#666">'
        f'{draft_out["note"]}</text>',
        "</svg>",
    ]
    return "\n".join(head + parts + foot)


def save(measures: Any, path: Any) -> Dict[str, Any]:
    """型紙を書き出し、**生成物の印を付ける**。"""
    from pathlib import Path

    from .garment import mark_generated

    out = draft(measures)
    if out.get("verdict") != "ANSWER":
        return out
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(to_svg(out), encoding="utf-8")
    stamp = mark_generated(p)
    return {k: v for k, v in out.items() if k != "pieces"} | {
        "path": str(p), "stamp": str(stamp),
        "pieces": [{"name": x["name"], "area_cm2": x["area_cm2"]}
                   for x in out["pieces"]]}
