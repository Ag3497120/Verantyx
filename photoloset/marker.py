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
        # **この道具自身の文面から借りる。** how_to_close が挙げる二つの
        # 例(110、150)は、日本の生地流通でよく見る反物幅の例として
        # ここに書かれている — それ自体が確かめられる出典(このファイル
        # を読めば同じ二つの数字が出典)。広い方を assumed に、狭い方を
        # alternatives に。**どちらも実測ではなく例なので PROPOSED。**
        return {"verdict": NO_WIDTH,
                "how_to_close": "生地幅(cm)を渡してください。110、150 など",
                "assumed": 150.0,
                "kind": "PROPOSED",
                "basis": ("この関数自身の how_to_close が挙げる二例"
                          "(110cm・150cm)のうち広い方。広い方を選ぶのは、"
                          "狭く仮定して実際の反物が広いと利用率の見積もり"
                          "が悪化する側より、広く仮定して実際が狭いと "
                          "TOO_WIDE で早く止まる側の方が、無言で失敗する"
                          "危険が小さいため"),
                "assumption_breaks_when": (
                    "実際の反物が110・150のどちらでもない場合は的外れ。"
                    "薄手のコットン等は110cm前後、コート地・毛織物は"
                    "137〜152cm、レースや一部の特殊生地は90cm以下も"
                    "珍しくない"),
                "alternatives": [
                    {"value": 110.0,
                     "basis": "この関数自身の how_to_close が挙げるもう"
                              "一つの例"}]}
    if seam_allowance_cm is None or seam_allowance_cm < 0:
        # **garment_marks.SEAM_ALLOWANCE の最頻値を借りる。** 度数は
        # 毎回数え直す(定数を書かない) — テーブルに行が足されても
        # ここを直さなくて済む。
        from . import garment_marks as _marks
        from collections import Counter as _Counter
        _counts = _Counter(v[0] for v in _marks.SEAM_ALLOWANCE.values()
                           if v[0] > 0.0)
        _mode_cm, _mode_n = max(_counts.items(),
                                key=lambda kv: (kv[1], -kv[0]))
        _total = sum(_counts.values())
        return {"verdict": NO_SA,
                "how_to_close": ("縫い代(cm)を渡してください。型紙は"
                                 "出来上がり線なので、裁ち線はその外側です"),
                "assumed": _mode_cm,
                "kind": "PROPOSED",
                "basis": (f"garment_marks.SEAM_ALLOWANCE で最も多い幅 "
                          f"({_mode_n}/{_total} 辺、直線の縫い目"
                          "「肩線・脇線」向け)。ここは裁片1枚に一律の幅を"
                          "使うので、辺ごとの正しい値ではなく製図全体の"
                          "代表値を選んでいる"),
                "assumption_breaks_when": (
                    "この製図が曲線(袖ぐり・衿ぐり、0.64〜0.95cm)や裾"
                    "(2.54cm)を多く含むほど外れる。マーカーは辺ごとの"
                    "幅を持たず1枚に1つの数しか使えないので、たとえ"
                    "garment_marks側の正しい辺別の値が分かっていても"
                    "ここでは一律の代表値に潰れる — この関数自身の限界"
                    "であって、値の選び方だけの問題ではない"),
                "alternatives": _marks.catalog_alternatives(_mode_cm)}

    pieces = draft.get("pieces") or []
    missing = [(p.get("name") or "?") for p in pieces
               if int(cut.get(p.get("name") or "?", 0)) < 1]
    if missing:
        return {"verdict": NO_COUNT, "pieces": missing,
                "how_to_close": ("それぞれ何枚裁つか言ってください。"
                                 "後身頃1枚と2枚では要る生地が倍違います"),
                # **ここは値を仮定しません。** 裁片が「わ」で1枚裁つのか、
                # 左右で鏡合わせにして2枚裁つのかは、輪郭からは分から
                # ない製作側の決定(port_finish 等、この関数の入力に無い
                # 情報)です。1を既定にすると鏡合わせが要る裁片(実際に
                # 袖は2枚)で静かに半分の生地しか見積もらず、逆に2を既定
                # にすると、わ裁ちの裁片(後身頃など)で無駄に多く見積もり
                # ます。どちらの既定も「確かめられる基準」を持たないので、
                # 置きません。
                "no_assumption": (
                    "1枚か2枚(以上)かは輪郭からは分からない製作側の"
                    "決定で、この関数の入力にその手がかりがありません。"
                    "1を既定にすると鏡合わせが要る裁片で生地が足りなく"
                    "なり、2を既定にするとわ裁ちの裁片で無駄が出ます。"
                    "どちらにも確かめられる基準がないので仮定しません")}

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
        widest = round(max(it["w"] for it in over), 2)
        # **既に計算済みの値を運ぶ。** widest_cm はこの拒否のために新しく
        # 仮定した数ではなく、直前で実測した「この注文で一番幅の要る
        # 裁片」そのもの。だから INFERRED — 何かを測った結果から来ている。
        # 110・150 は NO_WIDTH と同じ、この関数自身の how_to_close の例。
        wider_catalog = [w for w in (110.0, 150.0) if w >= widest]
        return {"verdict": TOO_WIDE,
                "pieces": sorted({it["piece"] for it in over}),
                "widest_cm": widest,
                "fabric_width_cm": fabric_width_cm,
                "how_to_close": ("生地幅を広げるか、その裁片を分割して"
                                 "縫い目を増やしてください。布目を90度回す"
                                 "のは、この裁片のたて地を横に使うことなので"
                                 "落ち方が変わります — 幅を稼ぐ手ではありま"
                                 "せん"),
                "assumed": widest,
                "kind": "INFERRED",
                "basis": ("この注文で一番幅の要る裁片、widest_cm として"
                          "上ですでに実測した値そのもの(新しく仮定した"
                          "数ではない)。これが収まる最小の反物幅"),
                "assumption_breaks_when": (
                    "widest_cm ぴったりでは、裁片と反物の耳の間に余白が"
                    "無い。実際の裁断はピン打ち・耳の織り乱れの分の余白"
                    "が要るので、これは『最低これ以上』の下限であって、"
                    "そのまま注文してよい実用幅ではない"),
                "alternatives": [
                    {"value": w,
                     "basis": ("NO_WIDTH と同じ、この関数自身の "
                               "how_to_close が挙げる例のうち widest_cm "
                               "以上のもの")}
                    for w in wider_catalog]}

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
