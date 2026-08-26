# -*- coding: utf-8 -*-
"""マーカー（配置）と生地使用量。**縫う人に直接届く数字。**

型紙が正しくても、生地が何メートル要るか言えなければ買えない。ここはその
一つの数を出す。ただし**その数を出すには、型紙が持っていない情報が三つ要る**
ので、無いまま計算しない。

1. **裁断枚数。** 裁片は「何枚裁つか」を持っていない。後身頃1枚と2枚では
   必要量が倍違う。``UNKNOWN_CUT_COUNT_NOT_STATED``。
2. **毛並み。** ``garment_marks`` の布目線は既に
   ``UNKNOWN_NAP_NOT_RECORDED`` と言っている。毛並みが分からないなら
   180°回転は使えない — 使えば逆毛になり、光の当たり方が変わる。
   **ただしここでは、毛並みを言っても長さは変わらない。** 裁片を外接矩形
   として置いているので、矩形の180°回転は同じ矩形になる。毛並みが効き始め
   るのは、裁片を多角形として噛み合わせるようになってから。**効かない自由度
   を「使えます」と報告しない。**
3. **縫い代。** ``garment_pattern`` は出来上がり線を引く。裁ち線はその外側。
   出来上がり線で数えた生地量は**必ず足りない**。

**この配置は最適ではない。** 裁片を外接矩形として棚に並べるだけで、実際の
マーカーは凹んだ形を噛み合わせる。だから出る長さは**上界**で、利用率は
**下界**。生地を買う向きとしてはそれが安全な側だが、「これが最小」とは
言わない。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

NO_COUNT = "UNKNOWN_CUT_COUNT_NOT_STATED"
TOO_WIDE = "UNKNOWN_PIECE_WIDER_THAN_FABRIC"
NO_WIDTH = "UNKNOWN_FABRIC_WIDTH_NOT_STATED"
NO_SA = "UNKNOWN_SEAM_ALLOWANCE_NOT_STATED"
NAP_UNKNOWN = "UNKNOWN_NAP_NOT_RECORDED"


def _box(outline: Sequence[Sequence[float]]) -> Tuple[float, float]:
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    return max(xs) - min(xs), max(ys) - min(ys)


def lay(draft: Dict[str, Any], fabric_width_cm: float,
        cut: Dict[str, int], seam_allowance_cm: float,
        nap: Optional[str] = None) -> Dict[str, Any]:
    """裁片を生地幅に並べ、要る長さを出す。

    ``nap`` は ``"none"``（毛並み無し）か、向きのある生地の名前、または
    ``None``（不明）。**今の配置では長さに影響しない** — 理由は模組の
    docstring に。記録はする。効くようになる日に、ここが読み替わる。
    """
    if draft.get("verdict") != "ANSWER":
        return {"verdict": draft.get("verdict", "UNKNOWN_NO_PIECES"),
                "note": "マーカーは型紙が引けてから"}
    if not fabric_width_cm or fabric_width_cm <= 0:
        return {"verdict": NO_WIDTH,
                "how_to_close": "生地幅(cm)を渡してください。110、150 など"}
    if seam_allowance_cm is None or seam_allowance_cm < 0:
        return {"verdict": NO_SA,
                "how_to_close": ("縫い代(cm)を渡してください。型紙は"
                                 "出来上がり線なので、裁ち線はその外側です")}

    pieces = draft.get("pieces") or []
    missing = [(p.get("name") or "?") for p in pieces
               if int(cut.get(p.get("name") or "?", 0)) < 1]
    if missing:
        return {"verdict": NO_COUNT, "pieces": missing,
                "how_to_close": ("それぞれ何枚裁つか言ってください。"
                                 "後身頃1枚と2枚では要る生地が倍違います")}

    sa = float(seam_allowance_cm)
    items: List[Dict[str, Any]] = []
    for p in pieces:
        name = p.get("name") or "?"
        w, h = _box(p.get("outline") or [])
        # 裁ち線は出来上がり線の外側。**外接矩形を両側に広げる** — 正確な
        # 平行曲線ではないので、これは多めに出る。多めに出るのは生地を
        # 買う側では安全だが、最小だとは言わない。
        cw, ch = w + 2.0 * sa, h + 2.0 * sa
        for k in range(int(cut[name])):
            items.append({"piece": name, "copy": k + 1,
                          "w": cw, "h": ch,
                          "sewing_line_cm2": p.get("area_cm2")})

    over = [it for it in items if it["w"] > fabric_width_cm]
    if over:
        return {"verdict": TOO_WIDE,
                "pieces": sorted({it["piece"] for it in over}),
                "widest_cm": round(max(it["w"] for it in over), 2),
                "fabric_width_cm": fabric_width_cm,
                "how_to_close": ("生地幅を広げるか、その裁片を分割して"
                                 "縫い目を増やしてください。布目を90度回す"
                                 "のは、この裁片のたて地を横に使うことなので"
                                 "落ち方が変わります — 幅を稼ぐ手ではありま"
                                 "せん")}

    # **決定的な棚詰め。** 高い順、同高は名前順、同名は複製番号順。乱数も
    # 時刻も使わない — 同じ入力から同じマーカーが出ないと、注文した生地量と
    # 裁つマーカーが一致しない。
    items.sort(key=lambda it: (-it["h"], it["piece"], it["copy"]))
    placed: List[Dict[str, Any]] = []
    shelf_y = 0.0
    shelf_h = 0.0
    x = 0.0
    for it in items:
        if x + it["w"] > fabric_width_cm + 1e-9:
            shelf_y += shelf_h
            shelf_h = 0.0
            x = 0.0
        placed.append({"piece": it["piece"], "copy": it["copy"],
                       "x_cm": round(x, 3), "y_cm": round(shelf_y, 3),
                       "w_cm": round(it["w"], 3), "h_cm": round(it["h"], 3),
                       })
        x += it["w"]
        shelf_h = max(shelf_h, it["h"])
    length = shelf_y + shelf_h

    cut_area = sum(it["w"] * it["h"] for it in items)
    sewing_area = sum(float(it["sewing_line_cm2"] or 0.0) for it in items)
    lay_area = fabric_width_cm * length
    return {
        "verdict": "ANSWER",
        "fabric_width_cm": fabric_width_cm,
        "length_cm": round(length, 2),
        "length_m": round(length / 100.0, 3),
        "pieces_laid": len(placed),
        "placement": placed,
        "seam_allowance_cm": sa,
        # 三つの面積。**混ぜない。**
        "sewing_line_area_cm2": round(sewing_area, 2),
        "cut_rectangle_area_cm2": round(cut_area, 2),
        "fabric_area_cm2": round(lay_area, 2),
        "utilisation_pct": round(100.0 * cut_area / lay_area, 2)
        if lay_area else None,
        "nap": nap or NAP_UNKNOWN,
        "nap_changes_nothing_here": (
            "毛並みを言っても、言わなくても、この長さは同じです。裁片を外接"
            "矩形として置いているので、矩形の180°回転は同じ矩形になります。"
            "毛並みが効くのは多角形として噛み合わせるようになってから。"
            "使えない自由度を「使えます」とは報告しません"),
        "this_is_an_upper_bound": (
            "裁片を外接矩形として棚に並べただけです。実際のマーカーは凹んだ"
            "形を噛み合わせるので、これより短くなります。**最小ではありま"
            "せん。** 生地を買う向きとしては多めに出る側で安全です"),
        "not_a_published_system": (
            "AAMA/ASTM のマーカー規格に準拠していません。準拠を名乗るには"
            "その規格で検証した誰かが要ります"),
    }
