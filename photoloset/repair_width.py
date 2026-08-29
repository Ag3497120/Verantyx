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
辺そのものは消える。旧形式では ``dropped_edges`` に出すだけだが、
``garment.compiled-pattern.v1`` では、その辺を参照していた seam / layer /
transform / feature を削除も推測もしない。片われへ一意に移せる参照だけを
新しい安定 ``piece_id`` へ再配線し、一意に移せない参照は ``REVIEW`` /
``UNKNOWN_EDGE_REWIRE_REQUIRED`` として残す。この状態を製造可能とは扱わない。
"""
from __future__ import annotations

import copy
import hashlib
import json
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


def _digest(value: Any) -> str:
    """Return a stable digest without trusting a stale artifact digest."""
    payload = copy.deepcopy(value)
    if isinstance(payload, dict):
        payload.pop("digest", None)
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _piece_identity(piece: Dict[str, Any]) -> str:
    return str(piece.get("piece_id") or piece.get("name") or "?")


def _child_piece_id(piece: Dict[str, Any], side: str) -> str:
    """A deterministic id: independent of list position, locale and runtime."""
    return f"{_piece_identity(piece)}::width-split:{side}"


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


def _clip_named_edge(points: Sequence[Sequence[float]], cx: float,
                     keep_right: bool
                     ) -> Optional[Tuple[List[List[float]], List[float]]]:
    """Clip one named edge while preserving its parametric source span.

    Compiled garment edges are currently simple polylines.  Width repair may
    cut such an edge once.  In that case the child still owns a real fragment
    of the named sewing edge; losing that address would unnecessarily destroy
    an otherwise deterministic waist/hem/gather seam.  If clipping would make
    more than one disconnected fragment, return ``None`` and keep the strict
    REVIEW behaviour.
    """
    raw = [[float(p[0]), float(p[1])] for p in points]
    if len(raw) < 2:
        return None
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(raw, raw[1:])]
    total = sum(lengths)
    if total <= _EPS:
        return None

    def inside(p: Sequence[float]) -> bool:
        return (p[0] >= cx - _EPS) if keep_right else (p[0] <= cx + _EPS)

    fragments: List[Tuple[List[List[float]], float, float]] = []
    travelled = 0.0
    for a, b, segment_length in zip(raw, raw[1:], lengths):
        a_in, b_in = inside(a), inside(b)
        if a_in and b_in:
            segment = [a, b]
            t0, t1 = 0.0, 1.0
        elif a_in == b_in:
            travelled += segment_length
            continue
        else:
            dx = b[0] - a[0]
            if abs(dx) <= _EPS:
                travelled += segment_length
                continue
            crossing_t = (cx - a[0]) / dx
            crossing = [cx, a[1] + crossing_t * (b[1] - a[1])]
            if a_in:
                segment, t0, t1 = [a, crossing], 0.0, crossing_t
            else:
                segment, t0, t1 = [crossing, b], crossing_t, 1.0
        start = (travelled + t0 * segment_length) / total
        end = (travelled + t1 * segment_length) / total
        if fragments and math.hypot(
                fragments[-1][0][-1][0] - segment[0][0],
                fragments[-1][0][-1][1] - segment[0][1]) <= 1e-6:
            fragments[-1][0].append(segment[1])
            fragments[-1] = (fragments[-1][0], fragments[-1][1], end)
        else:
            fragments.append((segment, start, end))
        travelled += segment_length
    if len(fragments) != 1 or len(fragments[0][0]) < 2:
        return None
    fragment, start, end = fragments[0]
    return fragment, [round(start, 9), round(end, 9)]


def _split_edge_fragment(points: Sequence[Sequence[float]], cx: float,
                         keep_right: bool
                         ) -> Optional[Tuple[List[List[float]], float, float]]:
    """Return the geometrically exact half of a two-point named edge.

    Compiled pattern edges are straight two-point segments.  Longer or
    self-crossing polylines need an explicit topology operation and therefore
    remain UNKNOWN rather than being silently joined across a clipped gap.
    """
    if len(points) != 2:
        return None
    p0 = [float(points[0][0]), float(points[0][1])]
    p1 = [float(points[1][0]), float(points[1][1])]
    x0, x1 = p0[0], p1[0]
    if abs(x1 - x0) < _EPS:
        return None
    t = (cx - x0) / (x1 - x0)
    if not _EPS < t < 1.0 - _EPS:
        return None
    crossing = [cx, p0[1] + t * (p1[1] - p0[1])]
    p0_right = p0[0] >= cx
    if keep_right:
        fragment = [p0, crossing] if p0_right else [crossing, p1]
        t_range = (0.0, t) if p0_right else (t, 1.0)
    else:
        fragment = [crossing, p1] if p0_right else [p0, crossing]
        t_range = (t, 1.0) if p0_right else (0.0, t)
    return fragment, min(t_range), max(t_range)


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
            # Preserve real edge fragments for compiled-pattern parametric
            # seam expansion.  They are not silently treated as the whole old
            # edge: ``source_span`` records exactly which interval survived.
            for target, keep_right in ((right_edges, True),
                                       (left_edges, False)):
                clipped = _clip_named_edge(pts, cx, keep_right)
                if clipped is None:
                    continue
                fragment, span = clipped
                target[edge_name] = {
                    "points": fragment,
                    "length": _length(fragment),
                    "fragment_of_edge": edge_name,
                    "source_span": span,
                    "state": "PROPOSED",
                }
            # The complete old address no longer exists, but for a straight
            # edge both clipped subsegments are exact geometry.  Give those
            # fragments stable addresses so a relation can later fan out only
            # when its opposite edge can be partitioned consistently.
            for keep_right, target, side_name in (
                    (True, right_edges, "right"),
                    (False, left_edges, "left")):
                fragment = _split_edge_fragment(pts, cx, keep_right)
                if fragment is None:
                    continue
                fragment_points, t0, t1 = fragment
                fragment_name = f"{edge_name}::width-split:{side_name}"
                target[fragment_name] = {
                    "points": fragment_points,
                    "length": _length(fragment_points),
                    "source_edge": edge_name,
                    "source_t_range": [round(t0, 9), round(t1, 9)],
                    "state": "INFERRED",
                    "kind": "WIDTH_SPLIT_EDGE_FRAGMENT",
                }

    right_edges[SPLIT_EDGE] = {"points": right_cut, "length": _length(right_cut)}
    left_edges[SPLIT_EDGE] = {"points": left_cut, "length": _length(left_cut)}

    # Keep all compiled-pattern metadata (cut_count, grain, layer, role,
    # provenance, construction hints, ...).  The former implementation built
    # three-field replacement dictionaries here, which silently erased that
    # data and left every structured reference pointing at the removed id.
    right_piece = copy.deepcopy(piece)
    left_piece = copy.deepcopy(piece)
    source_id = _piece_identity(piece)
    right_id = _child_piece_id(piece, "right")
    left_id = _child_piece_id(piece, "left")
    for child, child_id, side, child_name, child_outline, child_edges in (
            (right_piece, right_id, "right", f"{name} (右)",
             right_outline, right_edges),
            (left_piece, left_id, "left", f"{name} (左)",
             left_outline, left_edges)):
        child["name"] = child_name
        if "piece_id" in piece:
            child["piece_id"] = child_id
        if "node_id" in piece:
            child["node_id"] = child_id
            child["source_node_id"] = piece.get("node_id")
        child["outline"] = child_outline
        child["edges"] = child_edges
        child["area_cm2"] = _area(child_outline)
        child["split_from_piece_id"] = source_id
        child["width_split"] = {
            "state": "PROPOSED",
            "side": side,
            "source_piece_id": source_id,
            "rule": "vertical line through source bounding-box centre",
        }
        provenance = child.get("provenance")
        if isinstance(provenance, dict):
            provenance["width_repair"] = copy.deepcopy(child["width_split"])

        # A transform addressed to an edge is valid only on the child that
        # retained that complete named edge.  Do not duplicate a transform
        # onto a child where its address was cut in half.
        kept_transforms: List[Dict[str, Any]] = []
        transform_reviews: List[Dict[str, Any]] = []
        for transform in child.get("transforms") or []:
            record = copy.deepcopy(transform)
            address = record.get("edge", record.get("address"))
            if isinstance(address, str) and address in child_edges:
                if "piece_id" in piece:
                    record["piece_id"] = child_id
                kept_transforms.append(record)
            elif (record.get("kind") == "GATHER"
                  and isinstance(address, str)):
                fragment_name = next((edge_name for edge_name, edge in
                                      child_edges.items()
                                      if edge.get("source_edge") == address),
                                     None)
                ratio = record.get("ratio")
                if (fragment_name is not None and isinstance(ratio, (int, float))
                        and not isinstance(ratio, bool) and float(ratio) > 1.0):
                    fragment_length = float(
                        child_edges[fragment_name]["length"])
                    record.update({
                        "address": fragment_name,
                        "piece_id": child_id,
                        "cut_length_cm": fragment_length,
                        "finished_length_cm": round(
                            fragment_length / float(ratio), 6),
                        "parent_address": address,
                        "rewire_status": "ANSWER_SEGMENTED",
                    })
                    kept_transforms.append(record)
                else:
                    record.update({
                        "state": "UNKNOWN",
                        "rewire_status": "UNKNOWN_EDGE_REWIRE_REQUIRED",
                        "source_piece_id": source_id,
                        "candidate_piece_id": child_id,
                    })
                    transform_reviews.append(record)
            elif address is None:
                record.update({
                    "state": "REVIEW",
                    "rewire_status": "REVIEW_TRANSFORM_SCOPE_AFTER_SPLIT",
                    "source_piece_id": source_id,
                    "candidate_piece_id": child_id,
                })
                transform_reviews.append(record)
            else:
                record.update({
                    "state": "UNKNOWN",
                    "rewire_status": "UNKNOWN_EDGE_REWIRE_REQUIRED",
                    "source_piece_id": source_id,
                    "candidate_piece_id": child_id,
                })
                transform_reviews.append(record)
        if "transforms" in child:
            child["transforms"] = kept_transforms
        if transform_reviews:
            child["transform_reviews"] = transform_reviews
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
# garment.compiled-pattern.v1 の構造化参照の再配線
# --------------------------------------------------------------------

def _split_reference_map(
        split_results: Dict[str, Tuple[Dict[str, Any], Dict[str, Any],
                                      List[str]]],
        original_pieces: Sequence[Dict[str, Any]],
        ) -> Dict[str, Dict[str, Any]]:
    originals = {str(piece.get("name") or "?"): piece
                 for piece in original_pieces}
    mapping: Dict[str, Dict[str, Any]] = {}
    for name, (right, left, dropped) in split_results.items():
        original = originals[name]
        info = {
            "source_piece_id": _piece_identity(original),
            "right": right,
            "left": left,
            "dropped_edges": list(dropped),
        }
        for alias in {name, str(original.get("piece_id") or ""),
                      str(original.get("node_id") or "")}:
            if alias:
                mapping[alias] = info
    return mapping


def _child_id(piece: Dict[str, Any]) -> str:
    return str(piece.get("piece_id") or piece.get("name") or "?")


def _piece_for(pieces: Sequence[Dict[str, Any]], identity: Any
               ) -> Optional[Dict[str, Any]]:
    text = str(identity)
    return next((piece for piece in pieces
                 if text in (_child_id(piece), str(piece.get("name") or ""))),
                None)


def _edge_from_record(record: Dict[str, Any]) -> Optional[str]:
    edge = record.get("edge", record.get("address"))
    if isinstance(edge, str) and edge:
        return edge.rsplit("/", 1)[-1]
    return None


def _fragment_options(endpoint: Dict[str, Any],
                      reference_map: Dict[str, Dict[str, Any]]
                      ) -> List[Dict[str, Any]]:
    identity = endpoint.get("piece_id", endpoint.get("name"))
    edge_name = _edge_from_record(endpoint)
    info = reference_map.get(str(identity)) if identity is not None else None
    if info is None or edge_name is None:
        return []
    options: List[Dict[str, Any]] = []
    for child in (info["right"], info["left"]):
        for child_edge_name, child_edge in (child.get("edges") or {}).items():
            if child_edge.get("source_edge") != edge_name:
                continue
            options.append({
                "endpoint": {
                    "piece_id": _child_id(child),
                    "edge": child_edge_name,
                    "rewired_from_piece_id": info["source_piece_id"],
                    "source_edge": edge_name,
                    "rewire_status": "ANSWER_SEGMENTED",
                },
                "length": float(child_edge["length"]),
                "t_range": list(child_edge.get("source_t_range") or []),
            })
    return sorted(options, key=lambda item: tuple(item["t_range"]) or (0.0, 1.0))


def _full_endpoint(endpoint: Dict[str, Any],
                   pieces: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    identity = endpoint.get("piece_id", endpoint.get("name"))
    edge_name = _edge_from_record(endpoint)
    piece = _piece_for(pieces, identity)
    if piece is None or edge_name not in (piece.get("edges") or {}):
        return None
    return {"piece": piece, "edge": edge_name,
            "length": float(piece["edges"][edge_name]["length"])}


def _partition_straight_edge(piece: Dict[str, Any], edge_name: str,
                             fractions: Sequence[float], token: str,
                             side: str) -> Optional[List[Dict[str, Any]]]:
    edge = (piece.get("edges") or {}).get(edge_name)
    points = edge.get("points") if isinstance(edge, dict) else None
    if not isinstance(points, list) or len(points) != 2:
        return None
    try:
        p0 = (float(points[0][0]), float(points[0][1]))
        p1 = (float(points[1][0]), float(points[1][1]))
    except (TypeError, ValueError, IndexError):
        return None
    total = sum(float(value) for value in fractions)
    if total <= _EPS or any(float(value) <= _EPS for value in fractions):
        return None
    result: List[Dict[str, Any]] = []
    cursor = 0.0
    for index, value in enumerate(fractions, 1):
        start = cursor / total
        cursor += float(value)
        end = cursor / total
        a = [p0[0] + (p1[0] - p0[0]) * start,
             p0[1] + (p1[1] - p0[1]) * start]
        b = [p0[0] + (p1[0] - p0[0]) * end,
             p0[1] + (p1[1] - p0[1]) * end]
        alias = f"{edge_name}::width-peer:{token}:{side}:{index}"
        piece["edges"][alias] = {
            "points": [a, b], "length": _length([a, b]),
            "source_edge": edge_name,
            "source_t_range": [round(start, 9), round(end, 9)],
            "state": "INFERRED", "kind": "WIDTH_SPLIT_PEER_SEGMENT",
        }
        result.append({
            "endpoint": {"piece_id": _child_id(piece), "edge": alias,
                         "source_edge": edge_name,
                         "rewire_status": "ANSWER_SEGMENTED"},
            "length": float(piece["edges"][alias]["length"]),
            "t_range": [start, end],
        })
    return result


def _segment_relation(row: Dict[str, Any],
                      reference_map: Dict[str, Dict[str, Any]],
                      pieces: Sequence[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Fan a relation out only when both complete edge lengths reconcile."""
    a, b = row.get("a"), row.get("b")
    if not isinstance(a, dict) or not isinstance(b, dict):
        return None
    a_parts = _fragment_options(a, reference_map)
    b_parts = _fragment_options(b, reference_map)
    if not a_parts and not b_parts:
        return None
    operation_id = str(row.get("operation_id") or "relation")
    token = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:10]

    full_a = _full_endpoint(a, pieces) if not a_parts else None
    full_b = _full_endpoint(b, pieces) if not b_parts else None
    if (not a_parts and full_a is None) or (not b_parts and full_b is None):
        return None
    raw_total_a = (sum(part["length"] for part in a_parts)
                   if a_parts else float(full_a["length"]))
    raw_total_b = (sum(part["length"] for part in b_parts)
                   if b_parts else float(full_b["length"]))
    kind = str(row.get("kind") or "")
    if kind == "GATHER":
        if raw_total_a <= raw_total_b + _EPS:
            return None
        declared_ratio = row.get("ratio")
        if (declared_ratio is not None
                and abs(float(declared_ratio)
                        - raw_total_a / raw_total_b) > 1e-6):
            return None
    elif kind != "LAYER" and abs(raw_total_a - raw_total_b) > 0.3:
        return None

    if not a_parts:
        a_parts = _partition_straight_edge(
            full_a["piece"], full_a["edge"],
            [part["length"] for part in b_parts], token, "a") or []
    if not b_parts:
        b_parts = _partition_straight_edge(
            full_b["piece"], full_b["edge"],
            [part["length"] for part in a_parts], token, "b") or []
    if not a_parts or len(a_parts) != len(b_parts):
        return None

    total_a = sum(part["length"] for part in a_parts)
    total_b = sum(part["length"] for part in b_parts)
    if kind == "GATHER":
        if total_a <= total_b + _EPS:
            return None
        expected_ratio = total_a / total_b
        declared_ratio = row.get("ratio")
        if (declared_ratio is not None
                and abs(float(declared_ratio) - expected_ratio) > 1e-6):
            return None
    elif kind != "LAYER" and abs(total_a - total_b) > 0.3:
        # This is the important fail-closed boundary: geometry can split the
        # edge, but it cannot make a 120 cm seam truthfully join a 30 cm edge.
        return None

    expanded: List[Dict[str, Any]] = []
    for index, (part_a, part_b) in enumerate(zip(a_parts, b_parts), 1):
        if (kind != "GATHER" and kind != "LAYER"
                and abs(part_a["length"] - part_b["length"]) > 0.3):
            return None
        if kind == "GATHER" and part_a["length"] <= part_b["length"] + _EPS:
            return None
        child = copy.deepcopy(row)
        child.update({
            "operation_id": f"{operation_id}::width-segment:{index}",
            "parent_operation_id": operation_id,
            "a": part_a["endpoint"], "b": part_b["endpoint"],
            "declared_a_cm": round(part_a["length"], 6),
            "declared_b_cm": round(part_b["length"], 6),
            "topology_status": "ANSWER_SEGMENTED",
            "active": True,
            "manufacturing_validated": False,
        })
        if kind == "GATHER":
            child["ratio"] = round(part_a["length"] / part_b["length"], 9)
        expanded.append(child)
    return expanded


def _expand_segmentable_relations(
        rows: Sequence[Dict[str, Any]],
        reference_map: Dict[str, Dict[str, Any]],
        pieces: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for source in rows:
        expanded = _segment_relation(source, reference_map, pieces)
        out.extend(expanded if expanded is not None else [copy.deepcopy(source)])
    return out


def _resolve_structured_endpoint(
        endpoint: Dict[str, Any],
        reference_map: Dict[str, Dict[str, Any]],
        ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Resolve one ``{piece_id, edge}`` address without inventing an edge.

    An edge retained in exactly one child is safe to rewire.  A crossing edge
    was deliberately removed by ``_split_piece``; such an endpoint is kept as
    a typed unresolved address, with no dangling ``piece_id`` pretending that
    the removed parent still exists.
    """
    out = copy.deepcopy(endpoint)
    identity = out.get("piece_id", out.get("name"))
    info = reference_map.get(str(identity)) if identity is not None else None
    if info is None:
        return out, None
    edge = _edge_from_record(out)
    candidates = [child for child in (info["right"], info["left"])
                  if edge is not None and edge in (child.get("edges") or {})]
    if len(candidates) == 1:
        child = candidates[0]
        out.pop("name", None)
        out["piece_id"] = _child_id(child)
        out["rewired_from_piece_id"] = info["source_piece_id"]
        out["rewire_status"] = "ANSWER"
        return out, None

    out.pop("piece_id", None)
    out.pop("name", None)
    out.update({
        "source_piece_id": info["source_piece_id"],
        "candidate_piece_ids": [_child_id(info["right"]),
                                _child_id(info["left"])],
        "resolution": "UNKNOWN_EDGE_REWIRE_REQUIRED",
    })
    issue = {
        "code": "UNKNOWN_EDGE_REWIRE_REQUIRED",
        "source_piece_id": info["source_piece_id"],
        "edge": edge,
        "candidate_piece_ids": copy.deepcopy(out["candidate_piece_ids"]),
        "why": ("the named edge crossed the width split or the reference did "
                "not name an edge; choosing one child would invent topology"),
    }
    return out, issue


def _parametric_split_options(
        endpoint: Dict[str, Any],
        reference_map: Dict[str, Dict[str, Any]],
        ) -> Optional[List[Dict[str, Any]]]:
    """Return the two real child-edge fragments for a crossing address."""
    identity = endpoint.get("piece_id", endpoint.get("name"))
    info = reference_map.get(str(identity)) if identity is not None else None
    edge = _edge_from_record(endpoint)
    if info is None or edge is None or edge not in info["dropped_edges"]:
        return None
    options: List[Dict[str, Any]] = []
    for child in (info["right"], info["left"]):
        fragment = (child.get("edges") or {}).get(edge)
        if not isinstance(fragment, dict) or not fragment.get("source_span"):
            return None
        row = copy.deepcopy(endpoint)
        row.pop("name", None)
        row.update({
            "piece_id": _child_id(child),
            "edge": edge,
            "source_span": copy.deepcopy(fragment["source_span"]),
            "rewired_from_piece_id": info["source_piece_id"],
            "rewire_status": "ANSWER_PARAMETRIC_FRAGMENT",
        })
        options.append(row)
    return sorted(options, key=lambda row: tuple(row["source_span"]))


def _expand_parametric_relation(
        source: Dict[str, Any], reference_map: Dict[str, Dict[str, Any]],
        ) -> Optional[List[Dict[str, Any]]]:
    """Expand a compiler-authored seam over a deterministic width split.

    Expansion is permitted only when both declared endpoint lengths exist.
    Those values are emitted by ``structure_to_pattern`` and provide the
    parametric correspondence needed to split the opposite, unsplit edge.
    Arbitrary imported patterns without that evidence remain REVIEW.
    """
    if not all(isinstance(source.get(key), (int, float))
               for key in ("declared_a_cm", "declared_b_cm")):
        return None
    if not isinstance(source.get("a"), dict) or not isinstance(source.get("b"), dict):
        return None
    a_options = _parametric_split_options(source["a"], reference_map)
    b_options = _parametric_split_options(source["b"], reference_map)
    if a_options is None and b_options is None:
        return None

    def resolved(endpoint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        value, issue = _resolve_structured_endpoint(endpoint, reference_map)
        return value if issue is None else None

    if a_options is None:
        one = resolved(source["a"])
        if one is None:
            return None
        a_options = [one for _ in b_options or []]
    if b_options is None:
        one = resolved(source["b"])
        if one is None:
            return None
        b_options = [one for _ in a_options]
    if len(a_options) != len(b_options) or not a_options:
        return None

    expanded: List[Dict[str, Any]] = []
    parent_id = str(source.get("operation_id") or "relation")
    for index, (a, b) in enumerate(zip(a_options, b_options), start=1):
        split_endpoint = a if a.get("source_span") else b
        span = list(split_endpoint.get("source_span") or [0.0, 1.0])
        fraction = abs(float(span[1]) - float(span[0]))
        a_row, b_row = copy.deepcopy(a), copy.deepcopy(b)
        # The fragment owns its full child edge.  The opposite unsplit edge is
        # addressed by a parametric interval, so two operations do not claim
        # to sew the same complete edge twice.
        for endpoint in (a_row, b_row):
            if not endpoint.get("source_span"):
                endpoint["span"] = copy.deepcopy(span)
                endpoint["span_state"] = "PROPOSED_WIDTH_REPAIR"
        row = copy.deepcopy(source)
        row.update({
            "operation_id": f"{parent_id}:width-segment:{index}",
            "split_from_operation_id": parent_id,
            "a": a_row,
            "b": b_row,
            "declared_a_cm": round(float(source["declared_a_cm"]) * fraction, 6),
            "declared_b_cm": round(float(source["declared_b_cm"]) * fraction, 6),
            "state": "PROPOSED",
            "active": True,
            "manufacturing_validated": False,
            "topology_status": "ANSWER_PARAMETRIC_SPLIT",
            "orientation_state": "PROPOSED",
        })
        expanded.append(row)
    return expanded


def _rewire_relations(
        rows: Sequence[Dict[str, Any]], collection: str,
        reference_map: Dict[str, Dict[str, Any]],
        ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rewired: List[Dict[str, Any]] = []
    reviews: List[Dict[str, Any]] = []
    for index, source in enumerate(rows):
        expanded = _expand_parametric_relation(source, reference_map)
        if expanded is not None:
            rewired.extend(expanded)
            continue
        row = copy.deepcopy(source)
        issues: List[Dict[str, Any]] = []
        for key in ("a", "b", "source", "target"):
            if isinstance(row.get(key), dict):
                row[key], issue = _resolve_structured_endpoint(
                    row[key], reference_map)
                if issue is not None:
                    issues.append({"endpoint": key, **issue})
        if issues:
            row.update({
                "state": "REVIEW",
                "active": False,
                "manufacturing_validated": False,
                "topology_status": "UNKNOWN_EDGE_REWIRE_REQUIRED",
                "rewire_issues": copy.deepcopy(issues),
            })
            reviews.append({
                "collection": collection,
                "index": index,
                "operation_id": row.get("operation_id"),
                "state": "REVIEW",
                "issues": issues,
            })
        rewired.append(row)
    return rewired, reviews


def _transform_owner(pattern: Dict[str, Any], record: Dict[str, Any]
                     ) -> Optional[str]:
    explicit = record.get("piece_id")
    if explicit is not None:
        return str(explicit)
    needle = {key: value for key, value in record.items()
              if key not in ("operation_id", "piece_id", "state")}
    owners: List[str] = []
    for piece in pattern.get("pieces") or []:
        for candidate in piece.get("transforms") or []:
            if all(candidate.get(key) == value for key, value in needle.items()):
                owners.append(_piece_identity(piece))
                break
    unique = sorted(set(owners))
    return unique[0] if len(unique) == 1 else None


def _rewire_direct_records(
        rows: Sequence[Dict[str, Any]], collection: str,
        reference_map: Dict[str, Dict[str, Any]],
        *, source_pattern: Optional[Dict[str, Any]] = None,
        expand_piece_scope: bool = False,
        ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Rewire records carrying a direct piece id (features/transforms/layers)."""
    rewired: List[Dict[str, Any]] = []
    reviews: List[Dict[str, Any]] = []
    for index, source in enumerate(rows):
        row = copy.deepcopy(source)
        nested_issues: List[Dict[str, Any]] = []
        for key in ("attach_to", "source", "target", "a", "b"):
            if isinstance(row.get(key), dict):
                row[key], issue = _resolve_structured_endpoint(
                    row[key], reference_map)
                if issue is not None:
                    nested_issues.append({"endpoint": key, **issue})
        identity = row.get("piece_id", row.get("target_piece_id"))
        qualified_address = row.get("address")
        if (identity is None and isinstance(qualified_address, str)
                and "/" in qualified_address):
            identity = qualified_address.rsplit("/", 1)[0]
        if identity is None and collection == "transforms" and source_pattern:
            identity = _transform_owner(source_pattern, row)
            if identity is not None:
                row["piece_id"] = identity
                row["piece_owner_inferred_from_piece_history"] = True
        info = reference_map.get(str(identity)) if identity is not None else None
        if info is None:
            if nested_issues:
                row.update({
                    "state": "REVIEW", "active": False,
                    "manufacturing_validated": False,
                    "rewire_status": "UNKNOWN_EDGE_REWIRE_REQUIRED",
                    "rewire_issues": copy.deepcopy(nested_issues),
                })
                reviews.append({
                    "collection": collection, "index": index,
                    "operation_id": row.get("operation_id"),
                    "state": "REVIEW", "issues": nested_issues,
                })
            rewired.append(row)
            continue
        edge = _edge_from_record(row)
        candidates = [child for child in (info["right"], info["left"])
                      if edge is not None and edge in (child.get("edges") or {})]
        id_key = "target_piece_id" if "target_piece_id" in row \
            and "piece_id" not in row else "piece_id"
        if len(candidates) == 1:
            child_identity = _child_id(candidates[0])
            row[id_key] = child_identity
            if (isinstance(qualified_address, str)
                    and "/" in qualified_address):
                row["address"] = f"{child_identity}/{edge}"
            row["rewired_from_piece_id"] = info["source_piece_id"]
            row["rewire_status"] = "ANSWER"
            if nested_issues:
                row.update({
                    "state": "REVIEW", "active": False,
                    "manufacturing_validated": False,
                    "rewire_status": "UNKNOWN_EDGE_REWIRE_REQUIRED",
                    "rewire_issues": copy.deepcopy(nested_issues),
                })
                reviews.append({
                    "collection": collection, "index": index,
                    "operation_id": row.get("operation_id"),
                    "state": "REVIEW", "issues": nested_issues,
                })
            rewired.append(row)
            continue
        if (collection == "transforms" and row.get("kind") == "GATHER"
                and edge is not None):
            fragments = _fragment_options(
                {"piece_id": identity, "edge": edge}, reference_map)
            ratio = row.get("ratio")
            if (fragments and isinstance(ratio, (int, float))
                    and not isinstance(ratio, bool) and float(ratio) > 1.0):
                parent_operation = str(row.get("operation_id") or "gather")
                for part_index, part in enumerate(fragments, 1):
                    expanded = copy.deepcopy(row)
                    fragment_length = float(part["length"])
                    expanded.update({
                        "operation_id": (f"{parent_operation}::"
                                         f"width-segment:{part_index}"),
                        "parent_operation_id": parent_operation,
                        "piece_id": part["endpoint"]["piece_id"],
                        "address": part["endpoint"]["edge"],
                        "cut_length_cm": fragment_length,
                        "finished_length_cm": round(
                            fragment_length / float(ratio), 6),
                        "parent_address": edge,
                        "rewire_status": "ANSWER_SEGMENTED",
                    })
                    rewired.append(expanded)
                continue
        if edge is None and expand_piece_scope:
            for child in (info["right"], info["left"]):
                expanded = copy.deepcopy(row)
                expanded[id_key] = _child_id(child)
                expanded["rewired_from_piece_id"] = info["source_piece_id"]
                expanded["rewire_status"] = "ANSWER_SPLIT_SCOPE_EXPANDED"
                if nested_issues:
                    expanded.update({
                        "state": "REVIEW", "active": False,
                        "manufacturing_validated": False,
                        "rewire_status": "UNKNOWN_EDGE_REWIRE_REQUIRED",
                        "rewire_issues": copy.deepcopy(nested_issues),
                    })
                rewired.append(expanded)
            if nested_issues:
                reviews.append({
                    "collection": collection, "index": index,
                    "operation_id": row.get("operation_id"),
                    "state": "REVIEW", "issues": nested_issues,
                })
            continue

        row.pop("piece_id", None)
        row.pop("target_piece_id", None)
        row.update({
            "state": "REVIEW",
            "active": False,
            "manufacturing_validated": False,
            "source_piece_id": info["source_piece_id"],
            "candidate_piece_ids": [_child_id(info["right"]),
                                    _child_id(info["left"])],
            "rewire_status": ("REVIEW_PIECE_SCOPE_AFTER_SPLIT" if edge is None
                              else "UNKNOWN_EDGE_REWIRE_REQUIRED"),
        })
        rewired.append(row)
        reviews.append({
            "collection": collection,
            "index": index,
            "operation_id": row.get("operation_id"),
            "state": "REVIEW",
            "code": row["rewire_status"],
            "source_piece_id": info["source_piece_id"],
            "edge": edge,
            "candidate_piece_ids": copy.deepcopy(row["candidate_piece_ids"]),
            "nested_issues": nested_issues,
        })
    return rewired, reviews


def _seam_checks(pattern: Dict[str, Any], prior: Sequence[Dict[str, Any]]
                 ) -> List[Dict[str, Any]]:
    """Recompute checks from rewired endpoints; unresolved rows stay REVIEW."""
    by_piece = {_child_id(piece): piece for piece in pattern.get("pieces") or []}
    prior_by_operation = {row.get("operation_id"): row for row in prior
                          if row.get("operation_id") is not None}
    checks: List[Dict[str, Any]] = []
    for seam in pattern.get("seams") or []:
        operation_id = seam.get("operation_id")
        check = copy.deepcopy(prior_by_operation.get(operation_id, {}))
        check["operation_id"] = operation_id
        a, b = seam.get("a"), seam.get("b")
        if (seam.get("active") is False or not isinstance(a, dict)
                or not isinstance(b, dict) or "piece_id" not in a
                or "piece_id" not in b):
            check.update({
                "state": "REVIEW", "sewable": False,
                "geometrically_sewable": False,
                "topology_status": "UNKNOWN_EDGE_REWIRE_REQUIRED",
                "why": "a seam endpoint could not be rewired after width split",
            })
            checks.append(check)
            continue
        pa, pb = by_piece.get(str(a["piece_id"])), by_piece.get(str(b["piece_id"]))
        ea, eb = a.get("edge"), b.get("edge")
        if (pa is None or pb is None or ea not in (pa.get("edges") or {})
                or eb not in (pb.get("edges") or {})):
            check.update({
                "state": "REVIEW", "sewable": False,
                "geometrically_sewable": False,
                "topology_status": "UNKNOWN_EDGE_REWIRE_REQUIRED",
                "why": "rewired seam address does not resolve to generated geometry",
            })
            checks.append(check)
            continue
        # Compiler-authored parametric splits retain the declared sewing
        # lengths.  Geometry lengths can differ from finished seam lengths
        # after gathers/ease and must not overwrite that construction intent.
        la = float(seam.get("declared_a_cm",
                            pa["edges"][ea]["length"]))
        lb = float(seam.get("declared_b_cm",
                            pb["edges"][eb]["length"]))
        gathered = seam.get("kind") == "GATHER"
        difference = round(la - lb, 6)
        sewable = gathered or abs(difference) <= 0.3
        def address(endpoint: Dict[str, Any], edge: str) -> str:
            suffix = ""
            if endpoint.get("span"):
                suffix = f"@{endpoint['span'][0]}:{endpoint['span'][1]}"
            return f"{endpoint['piece_id']}/{edge}{suffix}"

        aa, bb = address(a, ea), address(b, eb)
        check.update({
            "label": f"{aa} <-> {bb}", "a": aa, "b": bb,
            "length_a": la, "length_b": lb,
            "length_a_cm": la, "length_b_cm": lb,
            "difference": difference, "difference_cm": difference,
            "tolerance": 0.3, "sewable": sewable,
            "geometrically_sewable": sewable,
            "state": seam.get("state", "PROPOSED"),
            "topology_status": "ANSWER",
        })
        checks.append(check)
    return checks


def _rewire_compiled_pattern(
        source_pattern: Dict[str, Any], new_pattern: Dict[str, Any],
        split_results: Dict[str, Tuple[Dict[str, Any], Dict[str, Any],
                                      List[str]]],
        ) -> Dict[str, Any]:
    reference_map = _split_reference_map(
        split_results, source_pattern.get("pieces") or [])
    reviews: List[Dict[str, Any]] = []

    expanded_seams = _expand_segmentable_relations(
        source_pattern.get("seams") or [], reference_map,
        new_pattern.get("pieces") or [])
    seams, found = _rewire_relations(expanded_seams,
                                     "seams", reference_map)
    reviews.extend(found)
    expanded_layers = _expand_segmentable_relations(
        source_pattern.get("layers") or [], reference_map,
        new_pattern.get("pieces") or [])
    layers, found = _rewire_relations(expanded_layers,
                                      "layers", reference_map)
    reviews.extend(found)
    # Some layer schemas use one direct piece_id rather than relation endpoints.
    layers, found = _rewire_direct_records(
        layers, "layers", reference_map, expand_piece_scope=True)
    reviews.extend(found)
    transforms, found = _rewire_direct_records(
        source_pattern.get("transforms") or [], "transforms", reference_map,
        source_pattern=source_pattern)
    reviews.extend(found)
    features, found = _rewire_direct_records(
        source_pattern.get("features") or [], "features", reference_map)
    reviews.extend(found)

    for _name, (right, left, _dropped) in sorted(split_results.items()):
        source_id = str(right.get("split_from_piece_id") or "?")
        seams.append({
            "operation_id": f"repair-width:{source_id}",
            "kind": "WIDTH_SPLIT_JOIN",
            "a": {"piece_id": _child_id(right), "edge": SPLIT_EDGE},
            "b": {"piece_id": _child_id(left), "edge": SPLIT_EDGE},
            "state": "PROPOSED",
            "active": True,
            "manufacturing_validated": False,
            "basis": "deterministic centre split for fabric-width repair",
        })

    new_pattern["seams"] = seams
    new_pattern["layers"] = layers
    new_pattern["transforms"] = transforms
    new_pattern["features"] = features
    new_pattern["seam_checks"] = _seam_checks(
        {**new_pattern, "seams": seams}, source_pattern.get("seam_checks") or [])
    new_pattern["unresolved_topology"] = reviews
    new_pattern["topology_status"] = "REVIEW" if reviews else "PROPOSED"
    explicit_map: Dict[str, Any] = {}
    originals = {str(piece.get("name") or "?"): piece
                 for piece in source_pattern.get("pieces") or []}
    for name, (right, left, _dropped) in sorted(split_results.items()):
        original = originals[name]
        source_id = _piece_identity(original)
        edge_map: Dict[str, Any] = {}
        for edge in original.get("edges") or {}:
            candidates = [child for child in (right, left)
                          if edge in (child.get("edges") or {})]
            if len(candidates) == 1:
                edge_map[edge] = {
                    "status": "ANSWER",
                    "piece_id": _child_id(candidates[0]),
                    "edge": edge,
                }
            else:
                edge_map[edge] = {
                    "status": "UNKNOWN_EDGE_REWIRE_REQUIRED",
                    "candidate_piece_ids": [_child_id(right), _child_id(left)],
                }
        explicit_map[source_id] = {
            "state": "PROPOSED",
            "children": [_child_id(right), _child_id(left)],
            "edge_rewire": edge_map,
        }
    new_pattern["piece_id_rewire"] = explicit_map
    new_pattern["manufacturing_ready"] = False
    gates = list(new_pattern.get("remaining_gates") or [])
    gate = "review width-split seam placement and every unresolved topology reference"
    if gate not in gates:
        gates.append(gate)
    new_pattern["remaining_gates"] = gates
    old_digest = source_pattern.get("digest")
    if old_digest is not None:
        new_pattern["input_pattern_digest"] = old_digest
    provenance = copy.deepcopy(new_pattern.get("provenance") or {})
    provenance["width_repair"] = {
        "method": "deterministic bounding-box centre split",
        "authority": "PROPOSED",
        "manufacturing_validated": False,
        "unresolved_reference_count": len(reviews),
    }
    new_pattern["provenance"] = provenance
    new_pattern["total_area_cm2"] = round(sum(
        float(piece.get("area_cm2") or 0.0)
        * int(piece.get("cut_count", 1))
        for piece in new_pattern.get("pieces") or []), 6)
    new_pattern["digest"] = _digest(new_pattern)
    return new_pattern


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
    is_compiled_pattern = (
        pattern.get("schema") == "garment.compiled-pattern.v1"
        or any("piece_id" in piece for piece in pattern.get("pieces") or [])
    )
    if is_compiled_pattern:
        new_pattern = _rewire_compiled_pattern(
            pattern, new_pattern, split_results)

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
    if is_compiled_pattern:
        result["topology_rewire"] = {
            "status": new_pattern.get("topology_status"),
            "piece_id_rewire": copy.deepcopy(
                new_pattern.get("piece_id_rewire") or {}),
            "unresolved": copy.deepcopy(
                new_pattern.get("unresolved_topology") or []),
            "manufacturing_ready": False,
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
