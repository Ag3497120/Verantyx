# -*- coding: utf-8 -*-
"""型紙を縫い合わせて落とす。

事前登録: experiments/garment/PREREG13_SEW.md

ここまで、立体・型紙・布シミュは**それぞれ別に寸法から生えていて、
互いを見ていなかった**。立体は寸法から作る塊、型紙は寸法から引く平面、
布シミュは平らな正方形を落とすだけ。どれも動くが、「この一着がどう
落ちるか」にはなっていない。

**縫い目は型紙が決める。** どの辺とどの辺を縫うかは、型紙の名前付き辺
(`肩線`・`脇線`・`袖ぐり`・`袖山`)から決まる。近いから縫う、をやると
型紙を無視して形を作ることになる。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .garment_drape import (LOCAL_MINIMUM, NO_MATERIAL, ORDER_DEPENDENT,
                            _energy, _stiffness, _vertex_diff, solve)

Vec = Tuple[float, float, float]

#: 縫う辺の対応。**型紙の名前で書く。** 近さでは決めない。
#: (ピースA, 辺A, ピースB, 辺B, 反転するか)
SEAMS: List[Tuple[str, str, str, str, bool]] = [
    ("前身頃", "肩線", "後身頃", "肩線", False),
    ("前身頃", "脇線", "後身頃", "脇線", False),
    ("袖", "袖山", "前身頃", "袖ぐり", False),
]

#: 型紙を3次元に置く初期位置。前は手前、後ろは奥、袖は横。
#: **これは初期配置であって形ではない** — 落とした結果が形。
PLACEMENT = {
    "前身頃": (0.0, 0.0, 12.0),
    "後身頃": (0.0, 0.0, -12.0),
    "袖": (34.0, 0.0, 0.0),
}

#: メッシュの粗さ (cm)。段を上げるときはここを下げる。
DEFAULT_CELL = 6.0

NO_PATTERN = "UNKNOWN_NO_PATTERN"
NOT_SEWN = "UNKNOWN_SEAM_DID_NOT_CLOSE"


def _inside(poly: Sequence[Sequence[float]], x: float, y: float) -> bool:
    """多角形の内側か(交差数)。境界は含めない側に倒す。"""
    n = len(poly)
    hit = False
    for i in range(n):
        x1, y1 = poly[i][0], poly[i][1]
        x2, y2 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            t = (y - y1) / (y2 - y1)
            if x < x1 + t * (x2 - x1):
                hit = not hit
    return hit


def _mesh_piece(piece: Dict[str, Any], cell: float
                ) -> Tuple[List[Tuple[float, float]],
                           List[Tuple[int, int, str]]]:
    """ピースを格子に切る。**輪郭の中だけを取る。**

    格子は決定的で、cell と輪郭から一意に決まる。
    """
    poly = piece["outline"]
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    nx = max(2, int(math.ceil((x1 - x0) / cell)) + 1)
    ny = max(2, int(math.ceil((y1 - y0) / cell)) + 1)

    index: Dict[Tuple[int, int], int] = {}
    pts: List[Tuple[float, float]] = []
    for j in range(ny):
        for i in range(nx):
            x = x0 + (x1 - x0) * i / (nx - 1)
            y = y0 + (y1 - y0) * j / (ny - 1)
            if _inside(poly, x, y):
                index[(i, j)] = len(pts)
                pts.append((x, y))

    edges: List[Tuple[int, int, str]] = []
    for (i, j), a in index.items():
        for di, dj, kind in ((1, 0, "weft"), (0, 1, "warp"),
                             (1, 1, "bias"), (1, -1, "bias")):
            b = index.get((i + di, j + dj))
            if b is not None:
                edges.append((a, b, kind))
    return pts, edges


def _sample(points: Sequence[Sequence[float]], n: int
            ) -> List[Tuple[float, float]]:
    """折れ線を n 点に等間隔で刻む。縫い目の対応に使う。"""
    if n < 2 or len(points) < 2:
        return [(points[0][0], points[0][1])] if points else []
    segs = []
    total = 0.0
    for a, b in zip(points, points[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        segs.append((a, b, d))
        total += d
    out = []
    for k in range(n):
        want = total * k / (n - 1)
        run = 0.0
        for a, b, d in segs:
            if run + d >= want or (a, b, d) is segs[-1]:
                t = 0.0 if d == 0 else (want - run) / d
                t = min(max(t, 0.0), 1.0)
                out.append((a[0] + (b[0] - a[0]) * t,
                            a[1] + (b[1] - a[1]) * t))
                break
            run += d
    return out


def _nearest(pts: Sequence[Tuple[float, float]],
             target: Tuple[float, float]) -> int:
    best, bi = float("inf"), 0
    for i, p in enumerate(pts):
        d = (p[0] - target[0]) ** 2 + (p[1] - target[1]) ** 2
        if d < best:
            best, bi = d, i
    return bi


def build(draft_out: Dict[str, Any], *, cell: float = DEFAULT_CELL,
          stitches: int = 7) -> Dict[str, Any]:
    """型紙から縫い合わせたメッシュを組む。

    返すのは頂点・辺・縫い目の対・**どの頂点がどのピース由来か**。
    """
    if draft_out.get("verdict") != "ANSWER":
        return {"verdict": NO_PATTERN,
                "why": "型紙が引けていないので縫えません",
                "missing": draft_out.get("missing", []),
                "how_to_close": draft_out.get("how_to_close", "")}

    pieces = {p["name"]: p for p in draft_out["pieces"]}
    points: List[Vec] = []
    edges: List[Tuple[int, int, str]] = []
    # **出身を残す。** 混ざると、直すときにどの型紙を触ればよいか
    # 分からなくなる。
    owner: List[str] = []
    piece_base: Dict[str, int] = {}
    piece_flat: Dict[str, List[Tuple[float, float]]] = {}

    for name, piece in pieces.items():
        flat, local_edges = _mesh_piece(piece, cell)
        base = len(points)
        piece_base[name] = base
        piece_flat[name] = flat
        ox, oy, oz = PLACEMENT.get(name, (0.0, 0.0, 0.0))
        for x, y in flat:
            points.append((x + ox, -y + oy, oz))
            owner.append(name)
        for a, b, kind in local_edges:
            edges.append((base + a, base + b, kind))

    # 縫い目。**型紙の名前付き辺から決める。**
    seam_pairs: List[Tuple[int, int]] = []
    seam_rows: List[Dict[str, Any]] = []
    for pa, ea, pb, eb, flip in SEAMS:
        if pa not in pieces or pb not in pieces:
            seam_rows.append({"seam": f"{pa}/{ea} ↔ {pb}/{eb}",
                              "state": "UNKNOWN_PIECE_MISSING"})
            continue
        ra = pieces[pa]["edges"].get(ea)
        rb = pieces[pb]["edges"].get(eb)
        if ra is None or rb is None:
            seam_rows.append({"seam": f"{pa}/{ea} ↔ {pb}/{eb}",
                              "state": "UNKNOWN_EDGE_MISSING"})
            continue
        sa = _sample(ra["points"], stitches)
        sb = _sample(rb["points"], stitches)
        if flip:
            sb = list(reversed(sb))
        made = 0
        for ta, tb in zip(sa, sb):
            ia = piece_base[pa] + _nearest(piece_flat[pa], ta)
            ib = piece_base[pb] + _nearest(piece_flat[pb], tb)
            if ia != ib:
                seam_pairs.append((ia, ib))
                made += 1
        seam_rows.append({"seam": f"{pa}/{ea} ↔ {pb}/{eb}",
                          "state": "SEWN", "stitches": made,
                          "length_a": ra["length"], "length_b": rb["length"]})

    return {
        "verdict": "ANSWER",
        "points": points, "edges": edges, "owner": owner,
        "seam_pairs": seam_pairs, "seams": seam_rows,
        "pieces": {k: {"vertices": len(v), "base": piece_base[k]}
                   for k, v in piece_flat.items()},
        "cell": cell,
        "note": "縫い目は型紙の名前付き辺から決めています。"
                "近さで勝手に繋いでいません",
    }


def _seam_gap(pos: Sequence[Sequence[float]],
              pairs: Sequence[Tuple[int, int]]) -> float:
    """縫い合わせた点同士の平均距離。**下がらなければ縫えていない。**"""
    if not pairs:
        return 0.0
    total = 0.0
    for a, b in pairs:
        total += math.dist(pos[a], pos[b])
    return round(total / len(pairs), 4)


def sew_and_drape(built: Dict[str, Any], material: Dict[str, Any], *,
                  iterations: int = 300, order: Optional[Sequence[int]] = None,
                  step: Optional[float] = None,
                  stitch_k: Optional[float] = None,
                  pinned: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    """縫って落とす。縫い目は**距離ゼロに引く拘束**として効く。

    刻みは落とす側と同じ規則で剛性から決める。固定にしていたら、
    剛性を桁で直した瞬間に nan で発散した(実測)。**同じ物理を解く
    二箇所が別の刻みを持つと、片方だけ壊れる。**
    """
    points = built["points"]
    edges = built["edges"]
    pairs = built["seam_pairs"]
    n = len(points)
    pos = [list(p) for p in points]
    stiff = _stiffness(material)
    rest = [math.dist(points[a], points[b]) for a, b, _ in edges]
    touching: List[List[int]] = [[] for _ in range(n)]
    for e, (a, b, _) in enumerate(edges):
        touching[a].append(e)
        touching[b].append(e)
    stitched: List[List[int]] = [[] for _ in range(n)]
    for s, (a, b) in enumerate(pairs):
        stitched[a].append(s)
        stitched[b].append(s)
    pin = set(pinned or _shoulder_pins(built))
    seq = list(order) if order is not None else list(range(n))
    mass = material["gsm"] / 10000.0
    # 縫合は布より弱くする。強すぎると縫い目が布を引き裂く向きに効く。
    if stitch_k is None:
        stitch_k = max(stiff.values()) * 0.25
    if step is None:
        step = 0.4 / max(max(stiff.values()), stitch_k, 1e-6)
    from .garment_drape import GRAVITY

    gaps = [_seam_gap(pos, pairs)]
    energies = [_energy(pos, edges, rest, stiff, mass, pin)]
    for _ in range(iterations):
        for i in seq:
            if i in pin:
                continue
            g = [0.0, 0.0, 0.0]
            for e in touching[i]:
                a, b, kind = edges[e]
                other = b if a == i else a
                d = [pos[i][t] - pos[other][t] for t in range(3)]
                length = math.sqrt(sum(x * x for x in d))
                if length < 1e-9:
                    continue
                c = stiff[kind] * (length - rest[e]) / length
                for t in range(3):
                    g[t] += c * d[t]
            for s in stitched[i]:
                a, b = pairs[s]
                other = b if a == i else a
                for t in range(3):
                    g[t] += stitch_k * (pos[i][t] - pos[other][t])
            g[1] += -mass * GRAVITY
            for t in range(3):
                pos[i][t] -= step * g[t]
        gaps.append(_seam_gap(pos, pairs))
        energies.append(_energy(pos, edges, rest, stiff, mass, pin))

    return {
        "verdict": "ANSWER",
        "points": [(round(p[0], 4), round(p[1], 4), round(p[2], 4))
                   for p in pos],
        "owner": built["owner"],
        "seam_gap": {"first": gaps[0], "last": gaps[-1],
                     "closed": gaps[-1] < gaps[0]},
        "energy": {"first": energies[0], "last": energies[-1]},
        "iterations": iterations,
        "step": round(step, 6), "stitch_k": round(stitch_k, 3),
    }


def _shoulder_pins(built: Dict[str, Any]) -> List[int]:
    """肩の一番高い点を吊る。**決定的に選ぶ** — 乱数で吊ると再現しない。"""
    owner = built["owner"]
    points = built["points"]
    pins = []
    for name in ("前身頃", "後身頃"):
        idx = [i for i, o in enumerate(owner) if o == name]
        if not idx:
            continue
        top = max(points[i][1] for i in idx)
        row = [i for i in idx if abs(points[i][1] - top) < 1e-6]
        pins.append(min(row))
        pins.append(max(row))
    return sorted(set(pins))


def validate(measures: Any, material: Dict[str, Any], *,
             cell: float = DEFAULT_CELL, iterations: int = 300,
             tolerances: Optional[Dict[str, float]] = None
             ) -> Dict[str, Any]:
    """縫って落とし、**検査に通ったときだけ形を返す。**

    PREREG12 の検証器は解法に依存しないので、平らな布から縫った服に
    替えても同じように効く。
    """
    from .garment_pattern import draft

    if material.get("verdict") != "ANSWER":
        return {"verdict": NO_MATERIAL,
                "why": "生地の物性が無ければ落としません"}
    built = build(draft(measures), cell=cell)
    if built["verdict"] != "ANSWER":
        return built

    tol = {"order": 1.5, "starts": 3.0}
    tol.update(tolerances or {})
    base = sew_and_drape(built, material, iterations=iterations)

    n = len(built["points"])
    orders = [list(reversed(range(n))), list(range(1, n)) + [0]]
    order_diffs = [
        _vertex_diff(base["points"],
                     sew_and_drape(built, material, iterations=iterations,
                                   order=o)["points"])
        for o in orders]

    starts = []
    for k in (0.0, 0.8, -0.8):
        moved = dict(built)
        moved["points"] = [(p[0], p[1] + k * math.sin(i * 0.7),
                            p[2] + k * 0.4)
                           for i, p in enumerate(built["points"])]
        starts.append(sew_and_drape(moved, material,
                                    iterations=iterations)["points"])
    start_diffs = [_vertex_diff(starts[0], s) for s in starts]

    checks = {
        "seam_closed": {
            "verdict": "ANSWER" if base["seam_gap"]["closed"] else NOT_SEWN,
            **base["seam_gap"]},
        "order": {
            "verdict": ("ANSWER" if max(order_diffs) <= tol["order"]
                        else ORDER_DEPENDENT),
            "worst_difference": max(order_diffs), "tolerance": tol["order"]},
        "starts": {
            "verdict": ("ANSWER" if max(start_diffs) <= tol["starts"]
                        else LOCAL_MINIMUM),
            "worst_difference": max(start_diffs), "tolerance": tol["starts"],
            "shapes": len(starts)},
    }
    failed = [k for k, v in checks.items() if v["verdict"] != "ANSWER"]
    out = {
        "verdict": "ANSWER" if not failed else checks[failed[0]]["verdict"],
        "checks": checks, "failed": failed,
        "seams": built["seams"],
        "pieces": built["pieces"],
        "owner_counts": {name: built["owner"].count(name)
                         for name in built["pieces"]},
        "assumed": material.get("assumed"),
        "not_a_measurement":
            "縫って落とした形は生成物です。観測の出典にはできません。",
    }
    if failed:
        out["why_no_shape"] = ("検査が通らなかったので形を返していません。"
                               "順序や初期配置が決めた皺を、物理として"
                               "見せないためです")
        if "starts" in failed:
            out["shapes"] = starts
    else:
        out["points"] = base["points"]
        out["owner"] = built["owner"]
    return out
