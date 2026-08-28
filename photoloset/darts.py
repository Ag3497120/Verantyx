# -*- coding: utf-8 -*-
"""ダーツ。**平らな布を立体にする唯一の道具。**

裁片は今まで全部平面の展開だった。ダーツは楔を抜いて両脚を縫い合わせる
ことで、布に円錐を作る — 胸、肩甲骨、腰。これが入らないと服は筒のままで、
体に沿わない。

**輪郭には焼き込まない。** ダーツを ``outline`` に頂点として挿入すると、
``points`` の採番が壊れる（``UNKNOWN_OUTLINE_RESHAPED``）。挿入した瞬間に
``e1`` が別の線分になり、ユーザーが前の周回で言った「30番から35番」が別の
場所を指す。だからダーツは**別の層**に置き、住所は ``points`` と同じ
``(裁片, 辺, t)`` で持つ。輪郭は動かない。楔は引くときに開く。

**抜いた布は戻らない。** ダーツを入れると裁片は展開可能でなくなる —
これは欠陥ではなく目的で、平らなまま留まる布は立体にならない。ただし
「型紙を平らに戻せる」という主張はここで終わるので、それを黙って越えない
ように ``developable`` を False で名乗る。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

Vec = Tuple[float, float]

#: 脚の長さの許容差(cm)。これを超えると縫い合わせたとき片方が余る。
LEG_TOLERANCE_CM = 0.05
#: 頂点が裁片の内側にどれだけ入っていなければならないか(cm)。
APEX_MARGIN_CM = 0.5

NO_EDGE = "UNKNOWN_NO_SUCH_EDGE"
APEX_OUT = "UNKNOWN_APEX_OUTSIDE_PANEL"
OVERLAP = "UNKNOWN_DARTS_OVERLAP"
TOO_WIDE = "UNKNOWN_INTAKE_EXCEEDS_EDGE"
BAD_INTAKE = "UNKNOWN_INTAKE_NOT_POSITIVE"
LEGS_UNEQUAL = "UNKNOWN_LEGS_UNEQUAL"


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k)


def _len(a: Vec) -> float:
    return math.hypot(a[0], a[1])


def _unit(a: Vec) -> Vec:
    n = _len(a)
    return (0.0, 0.0) if n == 0.0 else (a[0] / n, a[1] / n)


def _at(out: Sequence[Vec], i: int, j: int, t: float) -> Vec:
    """辺 i->j の t の位置。``points`` と同じパラメータ化。"""
    a, b = out[i], out[j]
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _inside(poly: Sequence[Vec], p: Vec) -> bool:
    """点が多角形の内側か（交差数法）。**境界上は外とみなす** — 頂点が
    縁に乗ったダーツは縫い代を食う。"""
    n = len(poly)
    hit = False
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x > p[0]:
                hit = not hit
    return hit


def _dist_to_boundary(poly: Sequence[Vec], p: Vec) -> float:
    """点から輪郭までの最短距離。"""
    best = float("inf")
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        ab = _sub(b, a)
        L2 = ab[0] ** 2 + ab[1] ** 2
        if L2 == 0.0:
            best = min(best, _len(_sub(p, a)))
            continue
        u = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0]
                               + (p[1] - a[1]) * ab[1]) / L2))
        best = min(best, _len(_sub(p, _add(a, _mul(ab, u)))))
    return best


#: ``_feasible_apex_search`` の粗いサンプリング数と、その後の二分の
#: 回数。この探索は受理条件を**変えない**（呼ばれるのは既に断った後）
#: ので回数はチューニング対象ではないが、断った理由の説明に数字として
#: 出すので名前を付けておく。
_APEX_SEARCH_SAMPLES = 200
_APEX_SEARCH_BISECT_ITERS = 40


def _feasible_apex_search(out: Sequence[Vec], mid: Vec, apex: Vec,
                          required: float,
                          samples: int = _APEX_SEARCH_SAMPLES,
                          iters: int = _APEX_SEARCH_BISECT_ITERS
                          ) -> Optional[Tuple[float, Vec, float]]:
    """底辺の中点から要求された頂点までの線分の上で、``required`` cm の
    余白（``_dist_to_boundary``）を保てる一番深い点を探す。

    **受理条件はここでは変えない** — 呼ばれるのは ``open_one`` が既に
    断ると決めた後で、断りに添える代案の値を測るためだけ。粗く
    ``samples`` 点走査してから最後の実行可能点と最初の不可能点の間を
    ``iters`` 回二分する — この探索自身は margin が線分上で一度だけ
    山になって降りる（unimodal）ことを仮定している。真ん中の頂点候補
    (``apex1``/``apex2``)を選ぶときと同じ「内側かどうかを実際に測って
    決める」流儀で、線分上の各点でも ``_inside`` を測り直す。見つからな
    ければ ``None`` — 呼び出し側はその場合 ``assumed`` を出さない。
    """
    def at(f: float) -> Vec:
        return _add(mid, _mul(_sub(apex, mid), f))

    def ok(f: float) -> bool:
        p = at(f)
        return _inside(out, p) and _dist_to_boundary(out, p) >= required

    best_f: Optional[float] = None
    for k in range(1, samples + 1):
        f = k / samples
        if ok(f):
            best_f = f
    if best_f is None:
        return None
    lo, hi = best_f, min(best_f + 1.0 / samples, 1.0)
    if not ok(hi):
        for _ in range(iters):
            m = (lo + hi) / 2.0
            if ok(m):
                lo = m
            else:
                hi = m
        best_f = lo
    p = at(best_f)
    return best_f, p, _dist_to_boundary(out, p)


def dart(piece: str, edge: str, t: float, intake_cm: float,
         length_cm: float = 0.0, role: str = "",
         toward: Optional[Vec] = None) -> Dict[str, Any]:
    """一本のダーツの宣言。**幾何はまだ引かない。**

    住所は ``points`` と同じ ``(裁片, 辺, t)``。``t`` はダーツの中心で、
    ``intake_cm`` は辺の上で抜く幅。

    頂点の決め方は二つある。``length_cm`` だけ渡すと辺の**垂直**に深さを
    取る。この場合**両脚は構成上必ず等しくなる** — 頂点が底辺の垂直二等分線
    に乗るので。だから ``UNKNOWN_LEGS_UNEQUAL`` はその経路では絶対に出ない。

    ``toward`` を渡すと頂点はその点そのものになる。実際の製図はこちらで、
    肩ダーツはバストポイントを指し、垂直ではない。**このときだけ脚は
    不揃いになりうる**ので、脚の検査が意味を持つのもこの経路だけ。
    """
    return {"piece": piece, "edge": edge, "t": float(t),
            "intake_cm": float(intake_cm), "length_cm": float(length_cm),
            "role": role,
            "toward": None if toward is None
            else (float(toward[0]), float(toward[1]))}


def _edges_of(out: Sequence[Vec]) -> List[Tuple[str, int, int]]:
    n = len(out)
    return [(f"e{i}", i, (i + 1) % n) for i in range(n)]


def open_one(outline: Sequence[Vec], d: Dict[str, Any]) -> Dict[str, Any]:
    """一本のダーツを開く。**輪郭は変えない** — 楔と検算を返すだけ。

    返すのは頂点、両脚の付け根、脚の長さ、抜いた面積、そして縫い合わせた
    ときに辺が何cm縮むか。
    """
    out = [tuple(map(float, p)) for p in outline]
    es = {name: (i, j) for name, i, j in _edges_of(out)}
    if d["edge"] not in es:
        # **代案を出さない。** 存在しない辺名の「一番近い」辺は幾何が
        # 決めるものではなく、綴りの近さで推測するだけになる — それは
        # この裁片の測定値ではなく、呼び出し側が何を言いたかったかの
        # 憶測で、外れたときに壊れる数を持てない(basisが検算できない)。
        return {"verdict": NO_EDGE, "edge": d["edge"],
                "known": sorted(es), "how_to_close": "辺の名前が違います"}
    i, j = es[d["edge"]]
    a, b = out[i], out[j]
    edge_len = _len(_sub(b, a))
    w = float(d["intake_cm"])
    if w <= 0.0:
        # **代案を出さない。** 0の上のどこかが「一番近い正の値」という
        # 主張はできない — 連続量には最小の刻みが無く、この裁片にも
        # このファイルにも「これ以上小さいと縫えない」という測定済みの
        # 下限が無い(下限があるのは TOO_WIDE の側の edge_len だけ)。
        return {"verdict": BAD_INTAKE, "intake_cm": w,
                "how_to_close": "抜く幅は正でなければ楔になりません"}
    if w >= edge_len:
        entry: Dict[str, Any] = {
            "verdict": TOO_WIDE, "intake_cm": w,
            "edge_cm": round(edge_len, 4),
            "how_to_close": f"{d['edge']} は {edge_len:.2f}cm しか"
                            f"ありません"}
        # **辺の長さは既にここで測ってある。** 使えるのはそれ未満のどこ
        # かで、丁度そこは脚の付け根が辺の両端と重なる縮退点。「あと
        # どれだけ」に単位を与える定数がこのファイルには他にないので、
        # 脚の長さの許容差(LEG_TOLERANCE_CM)を余白として流用する —
        # 発明した値ではなく、この裁片に対してこの意味で既に使われて
        # いる値。
        assumed_intake = edge_len - LEG_TOLERANCE_CM
        if assumed_intake > 0.0:
            entry.update({
                "assumed": round(assumed_intake, 4),
                "kind": "INFERRED",
                "basis": (
                    f"edge_cm ({edge_len:.4f}) is the exact length this "
                    f"refusal already measured and compared {w:.4f} "
                    f"against; intake must stay strictly under it or the "
                    f"two leg base points coincide with the edge's own "
                    f"endpoints, so this backs off by LEG_TOLERANCE_CM "
                    f"({LEG_TOLERANCE_CM}cm), the leg-length-agreement "
                    f"tolerance this same file already uses for truing"),
                "breaks_when": (
                    f"on an edge shorter than 2x LEG_TOLERANCE_CM "
                    f"({2 * LEG_TOLERANCE_CM}cm) this floors at or below "
                    f"zero and is withheld below; even where it is "
                    f"offered, an intake this close to the full edge "
                    f"leaves no seam allowance at either corner, which "
                    f"this file does not model"),
                "alternatives": [{
                    "value": round(edge_len, 4),
                    "basis": ("the exact measured edge length being "
                              "compared against; usable only if the "
                              "caller independently keeps the two leg "
                              "base points off the edge's endpoints")}],
            })
        return entry

    along = _unit(_sub(b, a))
    mid = _at(out, i, j, float(d["t"]))
    toward = d.get("toward")
    if toward is not None:
        # 実際の製図。頂点は解剖学的な点で、辺の垂直とは限らない。
        apex = (float(toward[0]), float(toward[1]))
        inward = _unit(_sub(apex, mid))
    else:
        # 内向き法線。**符号は多角形の向きではなく、実際に内側かで決める**
        # — 向きを仮定すると、時計回りの裁片でダーツが外へ飛び出す。
        n1 = (-along[1], along[0])
        apex1 = _add(mid, _mul(n1, float(d["length_cm"])))
        apex2 = _add(mid, _mul(n1, -float(d["length_cm"])))
        apex = apex1 if _inside(out, apex1) else apex2
        inward = n1 if apex is apex1 else (-n1[0], -n1[1])

    half = _mul(along, w / 2.0)

    def legs_at(centre: Vec) -> Tuple[Vec, Vec, float, float]:
        p1, p2 = _sub(centre, half), _add(centre, half)
        return p1, p2, _len(_sub(apex, p1)), _len(_sub(apex, p2))

    leg_a, leg_b, la, lb = legs_at(mid)

    # **真度をとる (truing).** 頂点を解剖学的な点に置くと両脚は揃わない。
    # 製図ではダーツの中心を辺に沿ってずらして揃える — 抜く幅は変えずに。
    # ``la - lb`` は中心の位置について単調なので二分で一意に決まる。
    # 垂直に取ったダーツは最初から揃っているのでここは動かない。
    trued_from = None
    if abs(la - lb) > LEG_TOLERANCE_CM:
        lo_u = w / 2.0 / edge_len
        hi_u = 1.0 - lo_u
        if lo_u < hi_u:
            f_lo = (lambda u: (lambda r: r[2] - r[3])(legs_at(_at(out, i, j, u))))
            if f_lo(lo_u) * f_lo(hi_u) < 0.0:
                a_u, b_u = lo_u, hi_u
                for _ in range(60):
                    m_u = (a_u + b_u) / 2.0
                    if f_lo(a_u) * f_lo(m_u) <= 0.0:
                        b_u = m_u
                    else:
                        a_u = m_u
                trued_from = float(d["t"])
                mid = _at(out, i, j, (a_u + b_u) / 2.0)
                leg_a, leg_b, la, lb = legs_at(mid)
                d = dict(d, t=(a_u + b_u) / 2.0)

    margin = _dist_to_boundary(out, apex)
    if not _inside(out, apex) or margin < APEX_MARGIN_CM:
        entry = {
            "verdict": APEX_OUT, "apex": [round(x, 4) for x in apex],
            "margin_cm": round(margin, 4),
            "required_cm": APEX_MARGIN_CM,
            "how_to_close": (f"深さ {d['length_cm']}cm では頂点が裁片の"
                             f"外か縁に近すぎます（余白 {margin:.2f}cm）")}
        # **この判定の境界(0.5cm)はここでは動かさない。** 探すのは断った
        #「後」の代案 — 同じ底辺の中点から要求された頂点への線分の上で、
        # 余白を保てる一番深い点。この境界を動かさないことは
        # ``tests/run_checks.py`` の "a dart whose apex leaves the panel
        # is refused" が26.5/27.0/27.5cmの3点で実測して縛っている。
        depth_before = _len(_sub(apex, mid))
        found = _feasible_apex_search(out, mid, apex, APEX_MARGIN_CM)
        if found is not None:
            f_star, apex_star, margin_star = found
            entry.update({
                "assumed": round(f_star * depth_before, 4),
                "kind": "INFERRED",
                "assumed_apex": [round(x, 4) for x in apex_star],
                "basis": (
                    f"scanned {_APEX_SEARCH_SAMPLES} points then "
                    f"bisected {_APEX_SEARCH_BISECT_ITERS} steps (the "
                    f"same coarse-scan-then-bisect idiom this file's own "
                    f"leg-truing already uses above) along the segment "
                    f"from this dart's base midpoint to the requested "
                    f"apex, for the deepest point still inside the panel "
                    f"with >= {APEX_MARGIN_CM}cm to every edge; found at "
                    f"depth {f_star * depth_before:.4f}cm of the "
                    f"requested {depth_before:.4f}cm, margin "
                    f"{margin_star:.4f}cm"),
                "breaks_when": (
                    "this line search only samples the ONE straight "
                    "line from base to the requested apex, and assumes "
                    "margin rises then falls at most once along it — "
                    "true on this piece's e2, where 26.5cm keeps "
                    "0.5053cm and 27.0cm only 0.0526cm, margin already "
                    "falling by then. A panel with a concave notch "
                    "crossing this line could open a second feasible "
                    "band narrower than "
                    f"{depth_before / _APEX_SEARCH_SAMPLES:.4f}cm "
                    "(this scan's own sample spacing), which would be "
                    "stepped over and reported as no room when there is "
                    "some, or vice versa"),
                "alternatives": [],
            })
        return entry
    if abs(la - lb) > LEG_TOLERANCE_CM:
        # 真度が取れなかった。辺の上に両脚が揃う中心が存在しない — 頂点が
        # 辺の延長線の側に寄りすぎている。**ずらして誤魔化さない。**
        entry = {
            "verdict": LEGS_UNEQUAL, "leg_a_cm": round(la, 4),
            "leg_b_cm": round(lb, 4),
            "difference_cm": round(abs(la - lb), 4),
            "tolerance_cm": LEG_TOLERANCE_CM,
            "how_to_close": ("この辺の上に両脚が揃う中心がありません。"
                             "頂点を動かすか、別の辺から取ってください")}
        # **どちらの端がマシか、測って言う。** 上の二分探索自身が
        # ``la - lb`` は中心位置について単調と仮定している(コメント
        # 参照)。単調で符号が変わらないなら、区間の中を探すまでもなく
        # 食い違いの最小は区間の**どちらかの端**にある。
        lo_u = w / 2.0 / edge_len
        hi_u = 1.0 - lo_u
        if lo_u < hi_u:
            _, _, la_lo, lb_lo = legs_at(_at(out, i, j, lo_u))
            _, _, la_hi, lb_hi = legs_at(_at(out, i, j, hi_u))
            diff_lo, diff_hi = abs(la_lo - lb_lo), abs(la_hi - lb_hi)
            if diff_lo <= diff_hi:
                best_u, best_diff = lo_u, diff_lo
                other_u, other_diff = hi_u, diff_hi
            else:
                best_u, best_diff = hi_u, diff_hi
                other_u, other_diff = lo_u, diff_lo
            entry.update({
                "assumed": round(best_u, 6),
                "kind": "PROPOSED",
                "assumed_difference_cm": round(best_diff, 4),
                "basis": (
                    f"la(u)-lb(u) is assumed monotonic along this edge "
                    f"— the same assumption this file's own truing "
                    f"bisection above already relies on — so with no "
                    f"sign change across the valid range u in "
                    f"[{lo_u:.4f}, {hi_u:.4f}], the smallest "
                    f"|leg_a-leg_b| sits at one of its two ends; "
                    f"measured {diff_lo:.4f}cm at u={lo_u:.4f} and "
                    f"{diff_hi:.4f}cm at u={hi_u:.4f}, so u={best_u:.4f} "
                    f"is kept"),
                "breaks_when": (
                    "if la(u)-lb(u) is not actually monotonic here — a "
                    "concave bite in the panel near this edge can make "
                    "the apex-to-base distance dip and rise — the true "
                    "minimum could sit at an interior u neither endpoint "
                    f"reaches, and this reports a gap ({best_diff:.4f}cm) "
                    "worse than achievable. Either way this gap "
                    f"({best_diff:.4f}cm) still exceeds the "
                    f"{LEG_TOLERANCE_CM}cm tolerance, so this is a "
                    "description of the least-bad option, not a fix — a "
                    "person should still move the apex or the edge"),
                "alternatives": [{
                    "value": round(other_u, 6),
                    "basis": (f"the other end of the same interval; "
                             f"|leg_a-leg_b|={other_diff:.4f}cm there, "
                             f"worse than the kept end")}],
            })
        return entry

    # 面積は楔の三頂点から靴紐公式で。**真度を取った後は二等辺なので
    # 0.5*w*depth と一致する** — ここで公式との差は捕まらない。それでも
    # 頂点から計算するのは、真度が取れなかった経路（LEGS_UNEQUAL で
    # 返る前）や、将来ダーツが三角でなくなったときに、式のほうが先に
    # 嘘になるから。
    area = abs((leg_a[0] * (leg_b[1] - apex[1])
                + leg_b[0] * (apex[1] - leg_a[1])
                + apex[0] * (leg_a[1] - leg_b[1])) / 2.0)
    depth = _len(_sub(apex, mid))
    return {
        "verdict": "ANSWER",
        "piece": d["piece"], "edge": d["edge"], "t": d["t"],
        "role": d.get("role", ""),
        "apex": [round(x, 6) for x in apex],
        "leg_a": [round(x, 6) for x in leg_a],
        "leg_b": [round(x, 6) for x in leg_b],
        "inward": [round(x, 6) for x in inward],
        "leg_a_cm": round(la, 6), "leg_b_cm": round(lb, 6),
        "intake_cm": w, "length_cm": float(d["length_cm"]),
        "depth_cm": round(depth, 6),
        "perpendicular": toward is None,
        "trued_from_t": trued_from,
        "trued": trued_from is not None,
        "removed_area_cm2": round(area, 6),
        "edge_cm_before": round(edge_len, 6),
        # **縫い合わせると辺は intake だけ縮む。** 展開と立体の関係が数字
        # として出るのはここだけなので、後で必ず測る。
        "edge_cm_after_closing": round(edge_len - w, 6),
        "apex_margin_cm": round(margin, 6),
        "developable": False,
        "not_flat_anymore": ("ダーツを閉じるとこの裁片は展開可能ではなく"
                             "なります。立体にするとはそういうことで、"
                             "「平らに戻せる」はここで終わります"),
    }


def apply(draft: Dict[str, Any], darts: Sequence[Dict[str, Any]]
          ) -> Dict[str, Any]:
    """型紙にダーツの層を足す。**``draft`` は変えない。**

    重なりも見る — 同じ辺で範囲が重なる二本は、縫うと互いの脚を食う。
    """
    if draft.get("verdict") != "ANSWER":
        return {"verdict": draft.get("verdict", "UNKNOWN_NO_PIECES"),
                "note": "ダーツは型紙が引けてから"}
    by_piece = {(p.get("name") or "?"): p for p in draft.get("pieces") or []}
    opened: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    spans: Dict[Tuple[str, str], List[Tuple[float, float, str]]] = {}

    for d in darts:
        p = by_piece.get(d["piece"])
        if p is None:
            refused.append({"verdict": "UNKNOWN_NO_SUCH_PIECE",
                            "piece": d["piece"], "known": sorted(by_piece)})
            continue
        out = [tuple(map(float, q)) for q in (p.get("outline") or [])]
        es = {n: (i, j) for n, i, j in _edges_of(out)}
        if d["edge"] in es:
            i, j = es[d["edge"]]
            L = _len(_sub(out[j], out[i]))
            if L > 0:
                halfT = (d["intake_cm"] / 2.0) / L
                lo, hi = d["t"] - halfT, d["t"] + halfT
                key = (d["piece"], d["edge"])
                clash = [o for o in spans.get(key, [])
                         if not (hi <= o[0] or lo >= o[1])]
                if clash:
                    entry = {
                        "verdict": OVERLAP, "piece": d["piece"],
                        "edge": d["edge"], "t": d["t"],
                        "clashes_with": [c[2] for c in clash],
                        "how_to_close": ("同じ辺で範囲が重なる二本は、縫うと"
                                         "互いの脚を食います")}
                    # **既に置いてある span の隙間を測る。** 「重ならない
                    # 最寄りの場所」を、今置いてある全部の span に対して
                    # 実際に検算してから選ぶ — 衝突した相手だけでなく。
                    all_spans = spans.get(key, [])

                    def _clashes(c_lo: float, c_hi: float) -> bool:
                        return any(not (c_hi <= s_lo or c_lo >= s_hi)
                                  for s_lo, s_hi, _ in all_spans)

                    candidates: List[Tuple[float, float]] = []
                    for (o_lo, o_hi, _label) in all_spans:
                        for cand_t in (o_hi + halfT, o_lo - halfT):
                            c_lo, c_hi = cand_t - halfT, cand_t + halfT
                            if c_lo < 0.0 or c_hi > 1.0:
                                continue
                            if _clashes(c_lo, c_hi):
                                continue
                            candidates.append((abs(cand_t - d["t"]), cand_t))
                    if candidates:
                        candidates.sort(key=lambda c: c[0])
                        _best_dt, best_t = candidates[0]
                        entry.update({
                            "assumed": round(best_t, 6),
                            "kind": "PROPOSED",
                            "basis": (
                                f"the nearest open slot on this edge "
                                f"next to the {len(all_spans)} dart(s) "
                                f"already placed there, found by pushing "
                                f"this span flush against the nearest "
                                f"clashing span's boundary and checking "
                                f"the result against every span already "
                                f"placed on this edge, not only the one "
                                f"it clashed with; moved by "
                                f"{_best_dt:.4f} in t (this edge's own "
                                f"0..1 parameter, the same one "
                                f"'points'/this dart's own address use)"),
                            "breaks_when": (
                                "this only guarantees no numeric "
                                "overlap — this file has no minimum gap "
                                "between two darts on the same edge, so "
                                "the nudged dart can end up with its "
                                "base touching its neighbour's exactly "
                                "at t, reading as one wide dart to a "
                                "sewer even though the two spans do not "
                                "overlap"),
                            "alternatives": (
                                [{"value": round(candidates[1][1], 6),
                                  "basis": ("the next-nearest open slot, "
                                           "on the other side")}]
                                if len(candidates) > 1 else []),
                        })
                    refused.append(entry)
                    continue
                spans.setdefault(key, []).append(
                    (lo, hi, d.get("role") or f"{d['edge']}@{d['t']}"))
        r = open_one(out, d)
        (opened if r["verdict"] == "ANSWER" else refused).append(r)

    total = sum(o["removed_area_cm2"] for o in opened)
    return {
        "verdict": "ANSWER",
        "darts": opened,
        "refused": refused,
        "count": len(opened),
        "removed_area_cm2": round(total, 6),
        "pieces_no_longer_developable": sorted(
            {o["piece"] for o in opened}),
        "shape_note": ("ダーツを持つ裁片は円錐になります。平面の展開として"
                       "の面積はダーツの分だけ減り、その差が立体の分です"),
    }
