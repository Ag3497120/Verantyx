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
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .garment_drape import (LOCAL_MINIMUM, NO_MATERIAL, ORDER_DEPENDENT,
                            _energy, _stiffness, _vertex_diff, solve)

Vec = Tuple[float, float, float]

#: 縫う辺の対応。**型紙の名前で書く。** 近さでは決めない。
#:
#: span は辺Aを刻む向きと範囲 (始点の割合, 終点の割合)。省略は (0.0, 1.0)。
#: **袖山は前後の袖ぐりに半分ずつ付く** — 片方だけに付けると、袖山の
#: 半分が何にも繋がらないまま袖ぐりに引き寄せられ、縫い目が永久に開く。
#: (2026-08-23 実測: 反復を32倍にしても隙間 6.06→5.96cm で止まった)
#:
#: 向きは端点で決まります。袖ぐりは肩線と共有する端から脇線と共有する端
#: へ走り、袖山は脇の下から肩を通ってもう一方の脇の下へ走ります。だから
#: 前半は (0.5, 0.0) と逆に刻んで、肩どうし・脇どうしを合わせます。
#: どちらの半分を前にするかは**この道具が決めた**ことで、測ったもので
#: はありません(左右対称なので長さは変わりません)。
SEAMS: List[Dict[str, Any]] = [
    {"a": ("前身頃", "肩線"), "b": ("後身頃", "肩線")},
    {"a": ("前身頃", "脇線"), "b": ("後身頃", "脇線")},
    {"a": ("袖", "袖山"), "b": ("前身頃", "袖ぐり"), "span": (0.5, 0.0),
     "label": "袖/袖山(前半) ↔ 前身頃/袖ぐり"},
    {"a": ("袖", "袖山"), "b": ("後身頃", "袖ぐり"), "span": (0.5, 1.0),
     "label": "袖/袖山(後半) ↔ 後身頃/袖ぐり"},
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


def _sample(points: Sequence[Sequence[float]], n: int,
            span: Tuple[float, float] = (0.0, 1.0)
            ) -> List[Tuple[float, float]]:
    """折れ線を n 点に等間隔で刻む。縫い目の対応に使う。

    span は刻む範囲と**向き**を弧長の割合で言います。(0.5, 0.0) なら
    真ん中から始点へ、逆向きに刻みます。袖山のように一本の辺が二枚に
    分かれて付くとき、これが無いと片側が繋がりません。
    """
    if n < 2 or len(points) < 2:
        return [(points[0][0], points[0][1])] if points else []
    segs = []
    total = 0.0
    for a, b in zip(points, points[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        segs.append((a, b, d))
        total += d
    t0, t1 = span
    out = []
    for k in range(n):
        want = total * (t0 + (t1 - t0) * k / (n - 1))
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
          stitches: int = 0,
          marks: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """型紙から縫い合わせたメッシュを組む。

    返すのは頂点・辺・縫い目の対・**どの頂点がどのピース由来か**。

    `marks` に合印(`garment_marks.apply` の出力)を渡すと、縫い目の対応を
    **合印で区切って**作ります。渡さないと弧長に比例して割ります。

    この違いは小さくありません。比例配分は「いせを全長に均等に配る」と
    黙って決めているのと同じで、テーラードの袖では間違いです
    (脇の下にいせは要らない)。どちらを使ったかは `seams[].correspondence`
    に残します。
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
    seen_pairs: set = set()
    seam_rows: List[Dict[str, Any]] = []
    for spec in SEAMS:
        (pa, ea), (pb, eb) = spec["a"], spec["b"]
        span = spec.get("span", (0.0, 1.0))
        name = spec.get("label", f"{pa}/{ea} ↔ {pb}/{eb}")
        if pa not in pieces or pb not in pieces:
            seam_rows.append({"seam": name,
                              "state": "UNKNOWN_PIECE_MISSING"})
            continue
        ra = pieces[pa]["edges"].get(ea)
        rb = pieces[pb]["edges"].get(eb)
        if ra is None or rb is None:
            seam_rows.append({"seam": name,
                              "state": "UNKNOWN_EDGE_MISSING"})
            continue
        # **目の数はメッシュから出す。** 固定の 7 本だと、短い辺では
        # 7 本が同じ格子点に潰れます (2026-08-23 実測: 28本が19対に潰れ、
        # 袖山の7本が頂点1つに乗っていた)。一つの点は一箇所にしか居ら
        # れないので、潰れた分は必ず開いたままになります。
        span_len = abs(span[1] - span[0]) * ra["length"]
        n_st = stitches or max(2, int(round(min(span_len, rb["length"])
                                            / cell)) + 1)
        here = [p for p in (marks or {}).get("notch_pairs", [])
                if p["seam"] == name]
        if len(here) >= 2:
            sa, sb = _sample_by_notches(ra["points"], rb["points"],
                                        here, cell)
            mode = "notched"
        else:
            sa = _sample(ra["points"], n_st, span=span)
            sb = _sample(rb["points"], n_st)
            mode = "proportional"
        made = 0
        for ta, tb in zip(sa, sb):
            ia = piece_base[pa] + _nearest(piece_flat[pa], ta)
            ib = piece_base[pb] + _nearest(piece_flat[pb], tb)
            if ia != ib and (ia, ib) not in seen_pairs:
                seen_pairs.add((ia, ib))
                seam_pairs.append((ia, ib))
                made += 1
        span_share = abs(span[1] - span[0])
        seam_rows.append({"seam": name,
                          "state": "SEWN", "stitches": made,
                          "correspondence": mode,
                          "notches_used": len(here),
                          "length_a": round(ra["length"] * span_share, 2),
                          "length_b": rb["length"]})

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


def _sample_by_notches(pts_a: Sequence[Sequence[float]],
                       pts_b: Sequence[Sequence[float]],
                       pairs: Sequence[Dict[str, Any]],
                       cell: float
                       ) -> Tuple[List[Tuple[float, float]],
                                  List[Tuple[float, float]]]:
    """**合印で区切って対応を作る。** 区間の中だけを比例で割る。

    合印は二枚の間の約束なので、区間の端は必ず合印どうしで合います。
    区間の中まで型紙が指定していないので、そこは比例で割る — これは
    「決めていないことは決めない」であって、全長を比例で割るのとは違い
    ます。全長を比例で割ると、脇の下にもいせが入ります。
    """
    from .garment_marks import at_arc

    order = sorted(pairs, key=lambda p: p["a"]["arc_cm"])
    out_a: List[Tuple[float, float]] = []
    out_b: List[Tuple[float, float]] = []
    for x, y in zip(order, order[1:]):
        a0, a1 = x["a"]["arc_cm"], y["a"]["arc_cm"]
        b0, b1 = x["b"]["arc_cm"], y["b"]["arc_cm"]
        span = min(abs(a1 - a0), abs(b1 - b0))
        n = max(2, int(round(span / cell)) + 1)
        for k in range(n):
            t = k / (n - 1)
            pa = at_arc(pts_a, a0 + (a1 - a0) * t)
            pb = at_arc(pts_b, b0 + (b1 - b0) * t)
            if out_a and abs(out_a[-1][0] - pa[0]) < 1e-9 \
                    and abs(out_a[-1][1] - pa[1]) < 1e-9:
                continue
            out_a.append(pa)
            out_b.append(pb)
    return out_a, out_b


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
                  start: Optional[Sequence[Vec]] = None,
                  pinned: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    """縫って落とす。縫い目は**距離ゼロに引く拘束**として効く。

    刻みは落とす側と同じ規則で剛性から決める。固定にしていたら、
    剛性を桁で直した瞬間に nan で発散した(実測)。**同じ物理を解く
    二箇所が別の刻みを持つと、片方だけ壊れる。**

    `start` は**解き始める位置**で、布そのものではありません。
    自然長は必ず `built["points"]`(型紙を置いた平らな状態)から取ります。

    2026-08-23 に直した欠陥: 以前は初期位置と自然長の両方を
    `built["points"]` から取っていたので、多点始動の検査が
    `built["points"]` を差し替えて**別の布**を作ってしまっていました。
    「始点を変えたら形が変わる」ではなく「違う服を三着比べていた」。
    """
    points = built["points"]
    edges = built["edges"]
    pairs = built["seam_pairs"]
    gap_tol = built.get("cell", DEFAULT_CELL) / 2.0
    n = len(points)
    pos = [list(p) for p in (start if start is not None else points)]
    stiff = _stiffness(material)
    # **自然長は平らな型紙から。** ここを start から取ると布が変わる。
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
        # **「縮んだ」を「閉じた」と呼ばない。** 前は gaps[-1] < gaps[0]
        # を closed としていて、6cm 開いたままの縫い目が合格していました
        # (2026-08-23 実測)。許容は選ばずメッシュから出します — 目は各
        # ピースの最寄り格子点に付くので、cell の半分は原理的な下限です。
        "seam_gap": {"first": gaps[0], "last": gaps[-1],
                     "tolerance": round(gap_tol, 4),
                     "tolerance_from": "メッシュ格子の半分 (cell/2)",
                     "decreased": gaps[-1] < gaps[0],
                     "closed": gaps[-1] <= gap_tol},
        "energy": {"first": energies[0], "last": energies[-1]},
        "iterations": iterations,
        "step": round(step, 6), "stitch_k": round(stitch_k, 3),
    }


def _shoulder_pins(built: Dict[str, Any]) -> List[int]:
    """肩の一番高い点を吊る。**決定的に選ぶ** — 乱数で吊ると再現しない。

    吊るのは**前身頃だけ**です。前と後ろを別々に吊ると、肩の縫い目は
    動けない点どうしを結ぶことになり、初期の前後間隔 (24cm) がそのまま
    残ります (2026-08-23 実測: 最大隙間がちょうど 24.0cm だった)。
    後ろは肩の縫い目を通して前にぶら下がります — 服はそう吊れています。

    目の付いた点は吊りません。**吊った点は動けないので、そこに付いた
    目は原理的に閉じません。**
    """
    owner = built["owner"]
    points = built["points"]
    sewn = {i for pair in built.get("seam_pairs", []) for i in pair}
    idx = [i for i, o in enumerate(owner) if o == "前身頃"]
    if not idx:
        return []
    top = max(points[i][1] for i in idx)
    row = sorted(i for i in idx if abs(points[i][1] - top) < 1e-6)
    del row
    # 縫っていない点だけを候補にし、上から帯を広げて**左右に離れた二点**
    # を取ります。一点で吊ると回ってしまい、初期配置ごとに別の形に落ち
    # ます — 多点始動の検査が落ちる原因になります。
    cand = sorted((i for i in idx if i not in sewn),
                  key=lambda i: -points[i][1])
    if not cand:
        return []
    band = 0.0
    while True:
        band += 6.0
        here = [i for i in cand if points[i][1] >= top - band]
        xs = {round(points[i][0], 3) for i in here}
        if len(xs) >= 2 or band > 60.0:
            break
    lo = min(here, key=lambda i: (points[i][0], -points[i][1]))
    hi = max(here, key=lambda i: (points[i][0], points[i][1]))
    return sorted({lo, hi})


def _internal_diff(a: Sequence[Sequence[float]],
                   b: Sequence[Sequence[float]], *, samples: int = 4000
                   ) -> float:
    """**形の中の距離**の食い違い。置き方(平行移動・回転)に依らない。

    座標の差だけを見ると、同じ形が揺れただけなのか本当に別の形に落ちた
    のかが分かりません。合同なら中の距離は変わりません。
    抽出は種を固定します — 乱数で変わる検査は検査になりません。
    """
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    rng = random.Random(20260823)
    worst = 0.0
    for _ in range(samples):
        i, j = rng.randrange(n), rng.randrange(n)
        if i == j:
            continue
        worst = max(worst, abs(math.dist(a[i], a[j]) - math.dist(b[i], b[j])))
    return round(worst, 4)


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
    from .garment_marks import apply as _marks
    drafted = draft(measures)
    built = build(drafted, cell=cell, marks=_marks(drafted))
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
        # **布は同じ。置き始める場所だけ動かす。**
        begin = [(p[0], p[1] + k * math.sin(i * 0.7), p[2] + k * 0.4)
                 for i, p in enumerate(built["points"])]
        starts.append(sew_and_drape(built, material, start=begin,
                                    iterations=iterations)["points"])
    start_diffs = [_vertex_diff(starts[0], s) for s in starts]
    # **同じ形が向きだけ違うのか、違う形なのか**を分ける。
    # 形の中の距離は置き方に依らないので、これが合っていれば揺れている
    # だけ、合っていなければ別の畳まれ方に落ちています。
    shape_diffs = [_internal_diff(starts[0], s) for s in starts]
    by_piece = {}
    for name in set(built["owner"]):
        idx = [i for i, o in enumerate(built["owner"]) if o == name]
        by_piece[name] = round(max(
            max((math.dist(starts[0][i], s[i]) for i in idx), default=0.0)
            for s in starts), 3)

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
            "shape_difference": max(shape_diffs),
            "same_shape_moved": max(shape_diffs) <= tol["starts"],
            "by_piece": by_piece,
            "shapes": len(starts)},
    }
    failed = [k for k, v in checks.items() if v["verdict"] != "ANSWER"]
    out = {
        "verdict": "ANSWER" if not failed else checks[failed[0]]["verdict"],
        "checks": checks, "failed": failed,
        "seams": built["seams"],
        "pieces": built["pieces"],
        # **辺も返す。** 点だけ描くと、どこが布でどこが空きなのか
        # 読めません。辺は測ったものではなくメッシュの構造です。
        "edges": [[a, b] for a, b, _ in built["edges"]],
        "seam_pairs": [[a, b] for a, b in built["seam_pairs"]],
        "owner": built["owner"],
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
    return out
