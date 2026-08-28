# -*- coding: utf-8 -*-
"""生地幅より広い裁片を、縫える形に直す。**直した服は INFERRED のまま。**

``marker.lay`` は ``UNKNOWN_PIECE_WIDER_THAN_FABRIC`` で止まる。裁片が
反物の幅を超えていれば、輪郭がどれだけ正しくても裁てない。この壁は
``marker.py`` の docstring が言う通り**この道具の限界ではなく物理の限界**
だが、限界の手前で止まるだけでは服にならない。ここは三つの出口を出す。

1. **分割して縫い目を足す。** 型紙の見た目の外接矩形の中心で縦に割り、
   新しい裁片を2枚にする。**選んだ規則は「中心で割る」というだけ**で、
   これは実在の縫製規則(見返し線・脇線・共衿の位置)を知って選んだ
   ものではない。中心を選ぶ理由は二つ: (a) 中心割りは残り幅の最大値を
   最小化する — 端に寄せて割ると、広い方の片われが元のまま残ってしまう。
   (b) 中心線には前中心・後中心という**衣服の言葉が既にある**ので、
   任意の場所に割るより人が受け入れやすい。**ただしこれは私が選んだ
   規則であって、実物の型紙にその線があるかどうかをこの関数は知らない。**
2. **回す。** ``marker.lay`` 自身の docstring がすでに実測している通り、
   裁片は外接矩形として置かれているので、**180度回転は同じ矩形になり
   長さを一切変えない**。かつて ``rotation_used`` フラグがあり、それが
   同じ理由で消された(このファイルが継ぐ教訓)。90度回転(たてよこを
   入れ替える)は矩形の寸法を変える ── が、それは布目線を横流れにする
   ことでもある。布目線はこのデータ構造に無い(``nap`` は毛並みだけを
   言い、たて地は別の情報)。**確かめられない安全を「安全です」とは
   言わない** ので、90度回転は計算だけして、適用はしない。
3. **広い生地を頼む。** 型紙を一切変えない、唯一「型紙側の直し」ではない
   出口。``marker.lay`` が ``TOO_WIDE`` のときに既に出している
   ``widest_cm`` と ``alternatives`` をそのまま運ぶ ── 新しく仮定した
   数ではない。

この三つのうち、この module が実際に**適用する**のは1だけ。2は計算して
断り、3は数字を運ぶだけで型紙を変えない。

**言えないこと。** 分割線が輪郭の名前付き辺(肩線・脇線・袖ぐり…)を
横切ったら、その辺はどちらの片われにも渡さない ── 部分的に切れた辺を
「元の名前のまま」渡すと、縫い代・合印など下流の道具が辺の全長を前提に
壊れる。横切られた辺は消える。消えたことは ``dropped_edges`` に出す。
辺が消えた裁片は、消えた分だけ「縫えるか」を再検査していない ──
この module はそこまで測っていない。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import marker as _marker
from . import sewing_order as _sewing_order

#: marker.py が定義した拒否名をそのまま使う。**ここで新しく作らない**
#: ── 二つのモジュールが同じ問題に別の名前を持つと、呼び出し側が
#: 両方を知らないといけなくなる。
PROBLEM = _marker.TOO_WIDE

#: 中心で割っても、片われの一方が反物幅に収まらない。分割は1本しか
#: 足さないので、この場合はこの module では直せない。
CANNOT_FIX = "UNKNOWN_SPLIT_STILL_TOO_WIDE"

#: detect が問題を見なかった、または repair に渡された型紙が
#: そもそも TOO_WIDE ではなかった。
NOT_APPLICABLE = "UNKNOWN_NOT_PIECE_WIDTH_PROBLEM"

#: 新しく足す縫い目の辺名。``marker.py`` / ``garment_marks.py`` の
#: ``中心線`` は「わ(縫わない折り線、縫い代0)」の意味で既に使われて
#: いるので、それとは**別の名前**を使う ── 同じ名前を使うと、縫い代を
#: 0にする処理がこの新しい実在の縫い目にも効いてしまう。
SPLIT_EDGE = "分割線"

_EPS = 1e-9


# --------------------------------------------------------------------
# 幾何: 外接矩形・面積・折れ線長・半平面クリップ
# --------------------------------------------------------------------

def _bbox(outline: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    return min(xs), max(xs), min(ys), max(ys)


def _area(outline: Sequence[Sequence[float]]) -> float:
    """多角形の面積(靴紐公式)。``garment_pattern._area`` と同じ式を、
    この module 側でも独立に持つ ── 分割で作った新しい輪郭の面積は、
    型紙モジュールを経由せずここで直接測る。"""
    n = len(outline)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = outline[i]
        x2, y2 = outline[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return round(abs(s) / 2.0, 1)


def _length(points: Sequence[Sequence[float]]) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    return round(total, 2)


def _clip_polygon(outline: Sequence[Sequence[float]], cx: float,
                   keep_right: bool) -> List[List[float]]:
    """閉じた輪郭を、垂直線 ``x = cx`` の片側だけに切る。

    Sutherland–Hodgman の一本clip。半平面は凸なので、輪郭が凹んで
    いても正しく切れる ── 裁片の輪郭が凸だと仮定していない。
    """
    def inside(p: Sequence[float]) -> bool:
        return (p[0] >= cx - _EPS) if keep_right else (p[0] <= cx + _EPS)

    def crossing(p1: Sequence[float], p2: Sequence[float]) -> List[float]:
        x1, y1 = p1
        x2, y2 = p2
        if abs(x2 - x1) < _EPS:
            return [cx, y1]
        t = (cx - x1) / (x2 - x1)
        return [cx, y1 + t * (y2 - y1)]

    n = len(outline)
    out: List[List[float]] = []
    for i in range(n):
        cur = outline[i]
        prev = outline[i - 1]
        cur_in = inside(cur)
        prev_in = inside(prev)
        if cur_in != prev_in:
            out.append(crossing(prev, cur))
        if cur_in:
            out.append([cur[0], cur[1]])
    # 連続する重複点(交点がちょうど頂点に乗った場合)を潰す。
    cleaned: List[List[float]] = []
    for p in out:
        if not cleaned or math.hypot(p[0] - cleaned[-1][0],
                                     p[1] - cleaned[-1][1]) > 1e-6:
            cleaned.append(p)
    if len(cleaned) > 1 and math.hypot(cleaned[0][0] - cleaned[-1][0],
                                       cleaned[0][1] - cleaned[-1][1]) < 1e-6:
        cleaned.pop()
    return cleaned


def _edge_side(points: Sequence[Sequence[float]], cx: float
               ) -> Optional[str]:
    """名前付き辺が分割線のどちら側に**完全に**収まっているか。

    ``"right"`` / ``"left"`` / 跨いでいれば ``None``。跨いだ辺は
    どちらの片われにも渡さない(モジュール docstring の
    「言えないこと」を参照)。
    """
    xs = [p[0] for p in points]
    if all(x >= cx - _EPS for x in xs):
        return "right"
    if all(x <= cx + _EPS for x in xs):
        return "left"
    return None


def _cut_segment(clipped: Sequence[Sequence[float]], cx: float
                  ) -> Optional[List[List[float]]]:
    """クリップ後の輪郭から、``x = cx`` に乗っている点だけを、
    y の並びで取り出す。分割線そのものの2点(両端)。"""
    on_line = [p for p in clipped if abs(p[0] - cx) < 1e-6]
    if len(on_line) < 2:
        return None
    ys = sorted({round(p[1], 6) for p in on_line})
    lo, hi = ys[0], ys[-1]
    return [[cx, lo], [cx, hi]]


def _split_piece(piece: Dict[str, Any]
                  ) -> Optional[Tuple[Dict[str, Any], Dict[str, Any],
                                      List[str]]]:
    """1枚の裁片を、外接矩形の中心の縦線で2枚に割る。

    戻り値は ``(右の裁片, 左の裁片, 消えた辺名のリスト)``。輪郭が
    退化していて割れない場合は ``None``。
    """
    name = piece.get("name") or "?"
    outline = [[float(x), float(y)] for x, y in (piece.get("outline") or [])]
    if len(outline) < 3:
        return None
    x0, x1, _y0, _y1 = _bbox(outline)
    cx = (x0 + x1) / 2.0
    if x1 - x0 < 1e-6:
        return None

    right_outline = _clip_polygon(outline, cx, keep_right=True)
    left_outline = _clip_polygon(outline, cx, keep_right=False)
    if len(right_outline) < 3 or len(left_outline) < 3:
        return None

    right_cut = _cut_segment(right_outline, cx)
    left_cut = _cut_segment(left_outline, cx)
    if not right_cut or not left_cut:
        return None

    old_edges = piece.get("edges") or {}
    dropped: List[str] = []
    right_edges: Dict[str, Any] = {}
    left_edges: Dict[str, Any] = {}
    for edge_name, edge in old_edges.items():
        pts = edge.get("points") or []
        side = _edge_side(pts, cx)
        if side == "right":
            right_edges[edge_name] = {"points": pts, "length": edge.get("length")}
        elif side == "left":
            left_edges[edge_name] = {"points": pts, "length": edge.get("length")}
        else:
            dropped.append(edge_name)

    right_edges[SPLIT_EDGE] = {"points": right_cut, "length": _length(right_cut)}
    left_edges[SPLIT_EDGE] = {"points": left_cut, "length": _length(left_cut)}

    right_piece = {"name": f"{name} (右)", "outline": right_outline,
                   "edges": right_edges, "area_cm2": _area(right_outline)}
    left_piece = {"name": f"{name} (左)", "outline": left_outline,
                  "edges": left_edges, "area_cm2": _area(left_outline)}
    return right_piece, left_piece, dropped


# --------------------------------------------------------------------
# 縫い目ラベルの読み書き(sewing_order.plan と同じ書式)
# --------------------------------------------------------------------

def _parse_endpoint(text: str) -> Tuple[str, Optional[str]]:
    text = text.strip()
    if "/" in text:
        p, e = text.split("/", 1)
        return p.strip(), e.strip()
    return text, None


def _parse_seam(label: str) -> Optional[Tuple[Tuple[str, Optional[str]],
                                              Tuple[str, Optional[str]]]]:
    if "↔" not in label:
        return None
    a, _, b = label.partition("↔")
    return _parse_endpoint(a), _parse_endpoint(b)


def _rebuild_seam_graph(seam_graph: Sequence[Dict[str, Any]],
                         split_name: str,
                         right_piece: Dict[str, Any],
                         left_piece: Dict[str, Any],
                         cut_length: float
                         ) -> Tuple[List[Dict[str, Any]], List[str]]:
    """分割前の縫い目一覧を、分割後の裁片名に合わせて書き換える。

    分割された裁片を指していた行は、その辺を実際に持つ片われの名前へ
    差し替える。どちらの片われもその辺を持たない(=分割線が横切った)
    行は、**消して** ``broken`` に積む ── 誤った名前のまま残さない。
    """
    right_edges = set(right_piece["edges"])
    left_edges = set(left_piece["edges"])
    out: List[Dict[str, Any]] = []
    broken: List[str] = []
    for row in seam_graph:
        label = row.get("seam") or "?"
        parsed = _parse_seam(label)
        if parsed is None:
            out.append(dict(row))
            continue
        (pa, ea), (pb, eb) = parsed

        def resolve(p: str, e: Optional[str]) -> Optional[str]:
            if p != split_name:
                return p
            if e is not None and e in right_edges:
                return right_piece["name"]
            if e is not None and e in left_edges:
                return left_piece["name"]
            return None

        ra = resolve(pa, ea)
        rb = resolve(pb, eb)
        if ra is None or rb is None:
            broken.append(label)
            continue
        new_label = f"{ra}/{ea} ↔ {rb}/{eb}" if (ea and eb) else label
        out.append(dict(row, seam=new_label))

    out.append({"seam": f"{right_piece['name']}/{SPLIT_EDGE} ↔ "
                        f"{left_piece['name']}/{SPLIT_EDGE}",
               "length_a": cut_length})
    return out, broken


# --------------------------------------------------------------------
# 契約: detect / repair
# --------------------------------------------------------------------

def detect(pattern: Dict[str, Any], fabric_width_cm: float,
           cut: Dict[str, int], seam_allowance_cm: float,
           nap: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """``marker.lay`` を呼び、``TOO_WIDE`` だけを拾う。

    ここで独自の判定はしない ── **既に測る道具がある問題を、
    自分で測り直さない。**
    """
    result = _marker.lay(pattern, fabric_width_cm, cut, seam_allowance_cm, nap)
    if result.get("verdict") != PROBLEM:
        return None
    return {"problem": PROBLEM,
            "where": list(result.get("pieces") or []),
            "measured": {"widest_cm": result.get("widest_cm"),
                         "fabric_width_cm": result.get("fabric_width_cm")}}


def repair(pattern: Dict[str, Any], fabric_width_cm: float,
           cut: Dict[str, int], seam_allowance_cm: float,
           nap: Optional[str] = None,
           seam_graph: Optional[Sequence[Dict[str, Any]]] = None
           ) -> Dict[str, Any]:
    """広すぎる裁片を中心で割り、``marker.lay`` に測り直させる。

    ``seam_graph`` は、この型紙の縫い目一覧(``garment_sew.build`` の
    ``seams`` と同じ形: ``[{"seam": "A/辺 ↔ B/辺", "length_a": ...}]``)。
    渡せば、分割前後で ``sewing_order.plan`` に通し、輪(IN_THE_ROUND)
    の本数が変わったかを実測する。渡さなければ、その部分は
    「測っていない」とだけ言う ── 測らずに「変わらない」とは言わない。
    """
    before = _marker.lay(pattern, fabric_width_cm, cut, seam_allowance_cm, nap)
    if before.get("verdict") != PROBLEM:
        return {"verdict": NOT_APPLICABLE,
                "changed": "何もしていません。この型紙は"
                          f"{PROBLEM} ではありません",
                "cost": {}, "kind": None, "pattern": pattern,
                "before": before, "after": before}

    over_names = list(before.get("pieces") or [])
    pieces_by_name = {p["name"]: p for p in pattern.get("pieces") or []}
    sa = float(seam_allowance_cm)

    # ---- 3. 広い生地を頼む(型紙は変えない、数字だけ運ぶ) ----------
    ask_for_wider_cloth = {
        "fabric_width_cm_needed": before.get("widest_cm"),
        "alternatives": before.get("alternatives"),
        "note": ("これは marker.lay が TOO_WIDE の時点で既に実測した "
                 "widest_cm・alternatives をそのまま運んだもので、"
                 "ここで新しく仮定した数ではありません。型紙は"
                 "一切変えていません")}

    # ---- 2. 回転(計算するが、適用しない) ---------------------------
    rotation: Dict[str, Any] = {}
    for name in over_names:
        piece = pieces_by_name.get(name)
        if piece is None:
            continue
        x0, x1, y0, y1 = _bbox(piece["outline"])
        cw, ch = (x1 - x0) + 2 * sa, (y1 - y0) + 2 * sa
        rotation[name] = {
            "180_deg": {
                "changes_bounding_box": False,
                "why": ("外接矩形の180度回転は同じ矩形になる"
                        "(marker.py が既に実測して rotation_used "
                        "フラグを消した理由と同じ)。毛並みの有無に"
                        "関わらず、この配置方式では効かない")},
            "90_deg": {
                "changes_bounding_box": abs(cw - ch) > 1e-9,
                "would_fit_if_applied": ch <= fabric_width_cm,
                "applied": False,
                "why_not_applied": (
                    "縦横を入れ替えると数値上は幅が変わり得るが"
                    "(この裁片は横倒しにすると "
                    f"{round(ch, 2)}cm)、それは布目線を横流れに"
                    "することでもある。このデータには輪郭とは別の"
                    "たて地情報が無いので、横流れが許される裁片かを"
                    "確かめられない。確かめられない安全は適用しない"
                    "ので、幅はここでは変わっていない")},
        }

    # ---- 1. 中心で分割 -----------------------------------------------
    still_too_wide: List[str] = []
    split_results: Dict[str, Tuple[Dict[str, Any], Dict[str, Any],
                                   List[str]]] = {}
    for name in over_names:
        piece = pieces_by_name.get(name)
        if piece is None:
            still_too_wide.append(name)
            continue
        split = _split_piece(piece)
        if split is None:
            still_too_wide.append(name)
            continue
        right_piece, left_piece, dropped = split
        for child in (right_piece, left_piece):
            x0, x1, _y0, _y1 = _bbox(child["outline"])
            if (x1 - x0) + 2 * sa > fabric_width_cm:
                still_too_wide.append(name)
                break
        else:
            split_results[name] = split

    if still_too_wide:
        return {
            "verdict": CANNOT_FIX,
            "changed": "何も変えていません。中心で割っても直りません",
            "cannot_fix": sorted(set(still_too_wide)),
            "cost": {},
            "kind": None,
            "pattern": pattern,
            "before": before,
            "after": before,
            "why": ("分割は1本しか縫い目を足さないので、片われの一方が"
                    "それでも生地幅を超えるなら、この module では"
                    "直せません。もっと幅を必要とする本数に割るのは、"
                    "この repair の外です。半分だけ直して ANSWER を"
                    "返すことはしません"),
            "ask_for_wider_cloth": ask_for_wider_cloth,
            "rotation_considered": rotation,
        }

    # ---- 新しい pieces / cut を組む ------------------------------------
    new_pieces: List[Dict[str, Any]] = []
    new_cut: Dict[str, int] = dict(cut)
    dropped_edges: Dict[str, List[str]] = {}
    seams_added = 0
    seam_length_added_cm = 0.0
    split_names: Dict[str, Tuple[str, str]] = {}
    for p in pattern.get("pieces") or []:
        name = p.get("name") or "?"
        if name in split_results:
            right_piece, left_piece, dropped = split_results[name]
            new_pieces.append(right_piece)
            new_pieces.append(left_piece)
            n = int(cut.get(name, 1))
            new_cut[right_piece["name"]] = n
            new_cut[left_piece["name"]] = n
            new_cut.pop(name, None)
            if dropped:
                dropped_edges[name] = dropped
            seams_added += 1
            seam_length_added_cm += right_piece["edges"][SPLIT_EDGE]["length"]
            split_names[name] = (right_piece["name"], left_piece["name"])
        else:
            new_pieces.append(p)

    new_pattern = dict(pattern)
    new_pattern["pieces"] = new_pieces

    after = _marker.lay(new_pattern, fabric_width_cm, new_cut,
                        seam_allowance_cm, nap)

    result: Dict[str, Any] = {
        "verdict": "ANSWER",
        "changed": (f"{len(split_results)}枚の裁片"
                    f"({'、'.join(sorted(split_results))})を、"
                    f"それぞれ外接矩形の中心の縦線で2枚に割り、"
                    f"新しい縫い目「{SPLIT_EDGE}」を{seams_added}本足した"),
        "cost": {
            "pieces_added": seams_added,
            "seams_added": seams_added,
            "seam_length_added_cm": round(seam_length_added_cm, 2),
            "dropped_edges": dropped_edges,
            "note": ("足した縫い目の長さの合計。分割線が輪郭の名前付き辺"
                     "(肩線・脇線・袖ぐり等)を横切った裁片は"
                     "dropped_edges に出す ── その辺は片われのどちらにも"
                     "渡していない"),
        },
        "kind": "INFERRED",
        "pattern": new_pattern,
        "before": before,
        "after": after,
        "ask_for_wider_cloth": ask_for_wider_cloth,
        "rotation_considered": rotation,
        "split_rule": (
            "外接矩形の x 方向の中心(最小と最大の中点)に縦線を引いて"
            "割った。これは私が選んだ規則で、実物の型紙にその線が"
            "あるかを確かめてはいない。選んだ理由: 中心割りは片われの"
            "最大幅を最小化する(端に寄せると広い方がそのまま残る)。"
            "また前中心・後中心はこの分野で既に受け入れられている"
            "線の名前で、任意の場所より人が受け入れやすい"),
    }

    if seam_graph is not None:
        right_name, left_name = None, None
        # 分割した裁片が複数あっても、seam_graph の書き換えは
        # 1枚ずつ順番に適用すれば足りる(裁片名は互いに独立)。
        rows = list(seam_graph)
        broken_all: List[str] = []
        for name, (right_piece, left_piece, _dropped) in split_results.items():
            rows, broken = _rebuild_seam_graph(
                rows, name, right_piece, left_piece,
                right_piece["edges"][SPLIT_EDGE]["length"])
            broken_all.extend(broken)
        plan_before = _sewing_order.plan({"verdict": "ANSWER",
                                          "seams": list(seam_graph)})
        plan_after = _sewing_order.plan({"verdict": "ANSWER", "seams": rows})
        beta_before = plan_before.get("in_the_round_minimum")
        beta_after = plan_after.get("in_the_round_minimum")
        result["sewing_order_before"] = plan_before
        result["sewing_order_after"] = plan_after
        result["beta_before"] = beta_before
        result["beta_after"] = beta_after
        result["beta_went_up"] = (None if beta_before is None
                                  or beta_after is None
                                  else beta_after > beta_before)
        result["beta_note"] = (
            "予想: 分割は縫い目を1本・裁片を1枚足し、二つの片われは"
            "新しい縫い目で互いに繋がったままなので連結成分数は変わらない"
            " ── β = 縫い目 − 裁片 + 連結成分 の増分は "
            "(+1) − (+1) + 0 = 0。実測でもそうなっているかは "
            "beta_before/beta_after を見て判断すること(この module は"
            "『上がるはず』と決め打ちしない)")
        if broken_all:
            result["broken_seam_rows"] = broken_all
    else:
        result["sewing_order_before"] = None
        result["sewing_order_after"] = None
        result["beta_before"] = None
        result["beta_after"] = None
        result["beta_went_up"] = None
        result["beta_note"] = ("seam_graph を渡されなかったので測って"
                               "いません。測らずに『変わらない』とは"
                               "言いません")

    return result
