# -*- coding: utf-8 -*-
"""布を落とす — **解法より先に検証器がある。**

事前登録: experiments/garment/PREREG12_DRAPE.md

`これまで.pdf` に記録された立体十字の性質のうち、四つが布に直接当たる。

    配置は情報を増やさない  → 制約の処理順で形が変わらない
    24面の壁(段は幾何が強制) → 粗中細で収束する
    エネルギー系・断面の一致 → 複数の初期配置から同じ形に収束する
    同点は棄権              → 座屈方向が同点なら方向を言わない

**辺に性質を載せる。** 質点ばね系の布は頂点と辺でできていて、辺が剛性を
持つ。織物は経糸・緯糸・バイアスで固さが違う異方性で、3軸それぞれに
異なる性質を持つ構造である(**意味の三双対と対応するとは言わない** —
同じなのはデータ構造の形であって中身ではない)。

落とした形は生成物で、観測の出典にできない。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

Vec = Tuple[float, float, float]

#: 重力 (cm/s²)。寸法を cm で扱っているので合わせる。
GRAVITY = -980.0

#: 辺の種別。**織物の3方向**で、それぞれ別の剛性を持つ。
#: warp=経(縦)、weft=緯(横)、bias=斜(対角)。
EDGE_KINDS = ("warp", "weft", "bias")

NO_MATERIAL = "UNKNOWN_NO_MATERIAL"
ORDER_DEPENDENT = "UNKNOWN_ORDER_DEPENDENT"
NOT_CONVERGED = "UNKNOWN_NOT_CONVERGED"
LOCAL_MINIMUM = "UNKNOWN_LOCAL_MINIMUM"


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(a: Vec) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def grid(nx: int, ny: int, width: float, height: float
         ) -> Tuple[List[Vec], List[Tuple[int, int, str]]]:
    """布の格子を作る。**辺に種別を付ける** — 経・緯・斜。

    帰り値は決定的で、`nx`,`ny` から一意に決まる。
    """
    pts: List[Vec] = []
    for j in range(ny):
        for i in range(nx):
            pts.append((i * width / max(nx - 1, 1),
                        0.0,
                        -j * height / max(ny - 1, 1)))

    def idx(i: int, j: int) -> int:
        return j * nx + i

    edges: List[Tuple[int, int, str]] = []
    for j in range(ny):
        for i in range(nx):
            if i + 1 < nx:
                edges.append((idx(i, j), idx(i + 1, j), "weft"))
            if j + 1 < ny:
                edges.append((idx(i, j), idx(i, j + 1), "warp"))
            if i + 1 < nx and j + 1 < ny:
                edges.append((idx(i, j), idx(i + 1, j + 1), "bias"))
                edges.append((idx(i + 1, j), idx(i, j + 1), "bias"))
    return pts, edges


def _stiffness(material: Dict[str, float]) -> Dict[str, float]:
    """辺の種別ごとの剛性。**バイアスは柔らかい** — 織物の実際。"""
    base = material["stiffness"]
    return {"warp": base, "weft": base, "bias": base * 0.25}


def solve(points: Sequence[Vec], edges: Sequence[Tuple[int, int, str]],
          pinned: Sequence[int], material: Dict[str, float],
          *, iterations: int = 400, order: Optional[Sequence[int]] = None,
          step: Optional[float] = None) -> Dict[str, Any]:
    """落とす。**エネルギーの勾配を降りる。**

    最初は位置ベース(PBD 風)で書いたが、**PBD には減少するエネルギーが
    定義されない** — 制約の射影が任意にエネルギーを出し入れするので、
    エネルギー検査を当てても何も言っていない(実測 VE6 でエネルギーが
    上がって判明)。

    構想は「各ノードのエネルギー比率が変わり、一番安定状態で終了」
    だったので、素直にエネルギーを下る。頂点を**順に**更新する
    Gauss-Seidel なので順序依存は残り、順序不変の検査は効く。

    `order` は頂点の更新順。検証器がここを揺らす。
    """
    n = len(points)
    pos = [list(p) for p in points]
    pin = set(pinned)
    stiff = _stiffness(material)
    rest = [_norm(_sub(points[b], points[a])) for a, b, _ in edges]
    # 頂点 → その頂点に触れる辺
    touching: List[List[int]] = [[] for _ in range(n)]
    for e, (a, b, _) in enumerate(edges):
        touching[a].append(e)
        touching[b].append(e)
    seq = list(order) if order is not None else list(range(n))
    # 面密度(g/cm²) × 1頂点が受け持つ面積 ≒ 質量。相対値として使う。
    mass = material["gsm"] / 10000.0
    # **刻みは剛性に合わせる。** 固定の刻みだと、剛性を上げた瞬間に
    # 発散する。0.4/k は決定的で、出力にも出す。
    if step is None:
        step = 0.4 / max(max(stiff.values()), 1e-6)

    energies: List[float] = [_energy(pos, edges, rest, stiff, mass, pin)]
    for _ in range(iterations):
        for i in seq:
            if i in pin:
                continue
            gx = gy = gz = 0.0
            for e in touching[i]:
                a, b, kind = edges[e]
                other = b if a == i else a
                d = [pos[i][t] - pos[other][t] for t in range(3)]
                length = math.sqrt(sum(x * x for x in d))
                if length < 1e-9:
                    continue
                # d/dx  ½k(|d|-L)²  =  k(|d|-L) · d/|d|
                c = stiff[kind] * (length - rest[e]) / length
                gx += c * d[0]
                gy += c * d[1]
                gz += c * d[2]
            # 重力の勾配。位置エネルギー -m·g·y の y 微分。
            gy += -mass * GRAVITY
            pos[i][0] -= step * gx
            pos[i][1] -= step * gy
            pos[i][2] -= step * gz
        energies.append(_energy(pos, edges, rest, stiff, mass, pin))

    return {
        "points": [(round(p[0], 4), round(p[1], 4), round(p[2], 4))
                   for p in pos],
        "energy": energies,
        "iterations": iterations,
        "step": round(step, 6),
    }


def _energy(pos, edges, rest, stiff, mass, pin) -> float:
    """全エネルギー。ばねの伸び + 位置エネルギー。

    **両方を同じ単位で足す。** 最初は位置エネルギーだけ 1/1000 して
    いて、合計が意味を持たなかった(実測 VE6)。単位を揃えないと、
    「エネルギーが下がった」は何も言っていない。
    """
    e = 0.0
    for i, (a, b, kind) in enumerate(edges):
        d = [pos[b][t] - pos[a][t] for t in range(3)]
        length = math.sqrt(sum(x * x for x in d))
        e += 0.5 * stiff[kind] * (length - rest[i]) ** 2
    for i, p in enumerate(pos):
        if i not in pin:
            e += -mass * GRAVITY * p[1]
    return round(e, 6)


def material_from(fabrics: Any, fabric: str) -> Dict[str, Any]:
    """生地台帳から物性を取る。**無ければ落とさない。**

    型紙と同じで、これは裁つ側の話である。既定で埋めない。
    """
    gsm = fabrics.number(fabric, "weight") if fabrics else None
    thick = fabrics.number(fabric, "thickness") if fabrics else None
    missing = []
    if gsm is None:
        missing.append("weight")
    if thick is None:
        missing.append("thickness")
    if missing:
        return {"verdict": NO_MATERIAL, "fabric": fabric,
                "missing": missing,
                "how_to_close": f"{fabric} の "
                                + "、".join(missing)
                                + " を出典付きで入れる"}
    # 曲げ剛性の実測は台帳に無い。**厚みから当てない** — 当てた数字は
    # 実測の顔をする。ここでは「厚みに比例する係数」を仮定として明示する。
    #
    # 桁を合わせてある。最初は 0.05+厚み×0.12 と置いていて、重力荷重
    # (目付200なら 19.6) に対して剛性 0.11 — **500倍ずれていて、布では
    # なくゴムひもだった**。40cm の布が 156cm 落ちても、順序不変・段の
    # 収束・多点一致・エネルギー単調減少は**全部通った**。
    # 立体十字の性質は「恣意的な選択の産物か」を見分けるが、
    # **「モデルが間違っているか」は見分けない**。別の検査が要る
    # (`check_strain`)。
    #
    # 織物は自重で数%しか伸びない。**歪みから逆算する。**
    #
    # 一頂点にかかる荷重は m·g だが、吊られた布では上の方の辺が
    # 下の全部を支えるので、荷重は頂点数に比例して積み上がる。
    # 一列 N 頂点なら、最上段の辺が受けるのは概ね N·m·g。
    # k ≈ N·m·g / (歪み·L) で、N≈10、歪み 2%、L≈6cm を基準に置く。
    #
    # 最初は N を無視して k=65 と置き、収束後の歪みが 119% になった。
    # 40cm の布が 60cm 落ちる状態で、順序不変・段の収束・多点一致・
    # エネルギー単調減少は**全部通っていた**(実測)。
    load = gsm / 10000.0 * abs(GRAVITY)
    stacked = load * 10.0
    stiffness = round(max(200.0, stacked / (0.02 * 6.0))
                      * (0.6 + thick * 0.8), 2)
    return {"verdict": "ANSWER", "fabric": fabric,
            "gsm": gsm, "thickness": thick,
            "stiffness": stiffness,
            "assumed": {
                "stiffness": "自重で歪み5%に収まる剛性を目付から出し、"
                             "厚みで 0.6+厚み×0.8 倍する",
                "why": "曲げ剛性の実測が台帳に無いので置いた仮定です。"
                       "測った値ではありません。カンチレバー法などの"
                       "実測が入れば置き換わります",
            }}


# ======================================================================
#  検証器 — 立体十字の四つの性質を布に当てる
# ======================================================================
#
# **形が物理の産物か、恣意的な選択の産物かを見分ける。**
# 解法に依存しないので、後から解法を差し替えても効く。


def _silhouette(points: Sequence[Vec]) -> Tuple[float, float, float]:
    """形の指紋。頂点の並びに依らない量だけを使う — 順序を比べる道具が
    順序に依存していたら、何も測れない。"""
    ys = [p[1] for p in points]
    xs = [p[0] for p in points]
    zs = [p[2] for p in points]
    return (round(min(ys), 3),
            round(sum(ys) / len(ys), 3),
            round(max(xs) - min(xs) + max(zs) - min(zs), 3))


def _diff(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
    return round(max(abs(x - y) for x, y in zip(a, b)), 4)


def _vertex_diff(a: Sequence[Vec], b: Sequence[Vec]) -> float:
    """頂点ごとの最大ずれ (cm)。

    **同じメッシュなら頂点が対応するので、指紋を通さず直接比べる。**
    最初は指紋(最下点・平均・広がり)で比べていて、生座標が 0.17cm
    動いているのに差 0.000 と出ていた — 粗い物差しで測ると、検査が
    通ったことに意味が無くなる(実測で判明)。
    指紋が要るのは、頂点が対応しない**段の比較**だけ。
    """
    return round(max(max(abs(x - y) for x, y in zip(p, q))
                     for p, q in zip(a, b)), 4)


def check_order(points, edges, pinned, material, *, trials: int = 3,
                tolerance: float = 0.5, **kw) -> Dict[str, Any]:
    """**配置は情報を増やさない。** 頂点の更新順で形が変わってはいけない。

    変われば形を返さない。順序が決めた皺を物理として見せないため。
    """
    n = len(points)
    base = solve(points, edges, pinned, material, **kw)
    ref = base["points"]
    rows = []
    worst = 0.0
    for t in range(trials):
        # 決定的な並べ替え。乱数を使うと検査自体が再現しない。
        order = list(range(t, n)) + list(range(t))
        if t == 1:
            order = list(reversed(range(n)))
        got = solve(points, edges, pinned, material, order=order, **kw)
        # **頂点ごとに比べる。** 同じメッシュなので対応が付く。
        d = _vertex_diff(ref, got["points"])
        worst = max(worst, d)
        rows.append({"trial": t, "difference": d})
    ok = worst <= tolerance
    return {
        "verdict": "ANSWER" if ok else ORDER_DEPENDENT,
        "worst_difference": worst, "tolerance": tolerance,
        "trials": rows,
        "silhouette": _silhouette(ref),
        "why": "頂点の更新順で形が変わるなら、それは物理ではなく"
               "順序の産物です",
        **({} if ok else {"how_to_close":
                          "反復を増やすか、順序に依らない解法にする"}),
    }


def check_scales(width: float, height: float, pinned_corners: bool,
                 material, *, sizes: Sequence[int] = (5, 9, 13),
                 tolerance: float = 6.0, **kw) -> Dict[str, Any]:
    """**24面の壁と同じ形。** 段(解像度)を上げて収束するか。

    一つの解像度が表せる皺の波長には下限があり、一様に細かくすると
    連立系が悪条件になる。段は最適化ではなく必然である。
    """
    rows = []
    for nx in sizes:
        pts, edges = grid(nx, nx, width, height)
        pin = [0, nx - 1] if pinned_corners else [0]
        got = solve(pts, edges, pin, material, **kw)
        rows.append({"n": nx, "silhouette": _silhouette(got["points"])})
    # **段は頂点が対応しないので、ここだけ指紋で比べる。**
    diffs = [_diff(rows[i]["silhouette"], rows[i + 1]["silhouette"])
             for i in range(len(rows) - 1)]
    # 収束 = 段を上げるほど差が縮む、かつ最後の差が許容内
    shrinking = all(b <= a + 1e-9 for a, b in zip(diffs, diffs[1:]))
    ok = bool(diffs) and diffs[-1] <= tolerance and shrinking
    return {
        "verdict": "ANSWER" if ok else NOT_CONVERGED,
        "steps": rows, "differences": diffs, "tolerance": tolerance,
        "shrinking": shrinking,
        "why": "粗中細で同じ形に寄らないなら、見ているのは解像度の"
               "産物です",
        **({} if ok else {"how_to_close":
                          "段を増やすか、反復を増やす"}),
    }


def check_starts(points, edges, pinned, material, *,
                 nudges: Sequence[float] = (0.0, 0.7, -0.7),
                 tolerance: float = 1.5, **kw) -> Dict[str, Any]:
    """**エネルギー系・断面の一致。** 複数の初期配置から同じ形に収束するか。

    皺は局所最小に落ちる。初期配置を変えると別の皺になり、どちらも
    「収束した」と言う。割れたら**片方を選ばない。**
    """
    rows = []
    for k in nudges:
        start = [(p[0], p[1] + k * math.sin(i * 0.9), p[2] + k * 0.3)
                 for i, p in enumerate(points)]
        got = solve(start, edges, pinned, material, **kw)
        rows.append({"nudge": k,
                     "points": got["points"],
                     "silhouette": _silhouette(got["points"]),
                     "final_energy": got["energy"][-1]})
    # ここも同じメッシュなので頂点ごとに比べる。
    ref = rows[0]["points"]
    worst = max(_vertex_diff(ref, r["points"]) for r in rows)
    ok = worst <= tolerance
    return {
        "verdict": "ANSWER" if ok else LOCAL_MINIMUM,
        "worst_difference": worst, "tolerance": tolerance,
        "starts": [{k: v for k, v in r.items() if k != "points"}
                   for r in rows],
        "shapes": [r["points"] for r in rows],
        "why": "初期配置で形が変わるなら、それは局所最小で、"
               "どちらを見せても恣意的です",
        **({} if ok else {
            "how_to_close": "始点を増やして最小エネルギーのものを取るか、"
                            "割れたまま両方を人に見せる",
            "note": "**片方を選んでいません。** 両方の形を返しています"}),
    }


def check_strain(points, edges, pinned, material, *,
                 limit: float = 0.15, **kw) -> Dict[str, Any]:
    """**布が布らしく振る舞うか。** 歪みが限度を超えたら物性が違う。

    これは一貫性の検査ではなく**妥当性**の検査である。順序不変・段の
    収束・多点一致・エネルギー単調減少は、一貫して計算された不合理を
    全部通す(実測: 40cm の布が 156cm 落ちても四つとも緑だった)。
    立体十字の性質が見分けるのは「恣意的な選択の産物か」であって、
    「モデルが間違っているか」ではない。
    """
    got = solve(points, edges, pinned, material, **kw)
    pos = got["points"]
    worst = 0.0
    for i, (a, b, _) in enumerate(edges):
        rest = _norm(_sub(points[b], points[a]))
        if rest < 1e-9:
            continue
        now = math.dist(pos[a], pos[b])
        worst = max(worst, abs(now - rest) / rest)
    worst = round(worst, 4)
    ok = worst <= limit
    return {
        "verdict": "ANSWER" if ok else "UNKNOWN_IMPLAUSIBLE_STRAIN",
        "worst_strain": worst, "limit": limit,
        "why": "織物は自重で数%しか伸びません。大きく伸びるなら、"
               "計算ではなく物性の置き方が違います",
        **({} if ok else {
            "how_to_close": "生地の剛性を実測で入れるか、仮定の式を直す"}),
    }


def check_energy(points, edges, pinned, material, **kw) -> Dict[str, Any]:
    """エネルギーが単調に下がるか。上がるなら解法が壊れている。"""
    got = solve(points, edges, pinned, material, **kw)
    E = got["energy"]
    rises = [i for i, (a, b) in enumerate(zip(E, E[1:])) if b > a + 1e-6]
    return {
        "verdict": "ANSWER" if not rises else "UNKNOWN_ENERGY_ROSE",
        "first": E[0], "last": E[-1], "rises": len(rises),
        "steps": len(E) - 1,
        "why": "位置ベース(PBD)には減少するエネルギーが定義されないので、"
               "この検査は勾配を降りる解法にだけ意味があります",
    }


def validate(width: float = 40.0, height: float = 40.0,
             material: Optional[Dict[str, Any]] = None,
             *, tolerances: Optional[Dict[str, float]] = None,
             **kw) -> Dict[str, Any]:
    """四つの検査をまとめて回す。**一つでも落ちたら形を返さない。**

    許容値は検査ごとに別物なので、まとめて配らない。順序のずれ(cm)と
    段の差(cm)を同じ数で測ると、片方が必ず無意味になる。
    """
    tol = {"order": 0.5, "starts": 1.5, "scales": 6.0}
    tol.update(tolerances or {})
    if material is None or material.get("verdict") != "ANSWER":
        return {"verdict": NO_MATERIAL,
                "why": "生地の物性が無ければ落としません。型紙と同じで、"
                       "これは裁つ側の話です"}
    pts, edges = grid(9, 9, width, height)
    pin = [0, 8]
    checks = {
        "strain": check_strain(pts, edges, pin, material, **kw),
        "energy": check_energy(pts, edges, pin, material, **kw),
        "order": check_order(pts, edges, pin, material,
                             tolerance=tol["order"], **kw),
        "starts": check_starts(pts, edges, pin, material,
                               tolerance=tol["starts"], **kw),
        "scales": check_scales(width, height, True, material,
                               tolerance=tol["scales"], **kw),
    }
    failed = [k for k, v in checks.items() if v["verdict"] != "ANSWER"]
    out = {
        "verdict": "ANSWER" if not failed else checks[failed[0]]["verdict"],
        "checks": checks, "failed": failed,
        "material": {k: material[k] for k in ("fabric", "gsm", "thickness",
                                              "stiffness")},
        "assumed": material.get("assumed"),
        "tolerances": tol,
        "not_a_measurement":
            "落とした形は生成物です。観測の出典にはできません。",
    }
    if not failed:
        out["points"] = solve(pts, edges, pin, material, **kw)["points"]
    else:
        out["why_no_shape"] = ("検査が通らなかったので形を返していません。"
                               "順序や初期配置が決めた皺を、物理として"
                               "見せないためです")
    return out
