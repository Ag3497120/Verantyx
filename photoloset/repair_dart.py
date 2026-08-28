# -*- coding: utf-8 -*-
"""ダーツの修理。**辺に合わないダーツを、``darts.py`` を通して直す。**

``darts.py`` は二つの理由でダーツを断る — ``UNKNOWN_INTAKE_EXCEEDS_EDGE``
(抜く幅が辺より広い)と ``UNKNOWN_DARTS_OVERLAP``(二本の範囲が重なる)。
どちらも直せることがある。ここはその「直し方」で、断りそのものではない。

**この裁片修理は幾何を持たない。** 頂点を内側かどうか測る、脚を揃える、
辺の長さを測る — 全部 ``darts.py`` の ``open_one``/``apply`` を呼んで
やらせる。理由は単純で、この裁片が「本当に縫えるか」を知っているのは
darts.py の中の二分探索と交差数法だけで、ここでその判定をもう一度書けば
二つの実装が食い違ったときにどちらが正しいか誰にも分からなくなる。
だから修理案を作ったら、必ず ``open_one``/``apply`` に投げ返して
その答えをそのまま採用する — 通った案だけを ANSWER にする。

**「入っている」パターンの形。** 一本のダーツを ``pattern["darts"]`` に
必ず1個だけ入れる。既に置いてあって動かさない他のダーツは
``pattern["other_darts"]``。修理が成功すると ``pattern["darts"]`` は
1個のまま(deepen・move)か、2個に増える(split)。**個数が変わること
自体がこの修理の代償の一つ** — 「同じ形」を「同じキー構成の入れ物」の
意味で保つので、1本が2本になっても壊れない。

**代償は必ず数字で言う。** 幅を削った分・深さを足した分・どの辺に
移したか。「直った」だけでは何を失ったか分からない。

**直せない場合がある。** この裁片のどの辺にも、深めても頂点が収まらず、
分けても隙間がなく、長い辺に移しても届かない — そのときは押し通さずに
断る。断りの名前は ``darts.py`` 自身が使う名前をそのまま借りる
(``TOO_WIDE``/``OVERLAP``)か、この修理固有の理由を新しい
``UNKNOWN_*`` として名乗る。
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import darts as _dt

Vec = Tuple[float, float]

#: darts.py 自身の断り名をそのまま使う — 「同じ問題」に二つの名前を
#: 付けない。
TOO_WIDE = _dt.TOO_WIDE
OVERLAP = _dt.OVERLAP

#: このファイル固有の断り。深めても分けても移しても直らないときに出す。
CANNOT_REPAIR = "UNKNOWN_DART_CANNOT_BE_MADE_TO_FIT"
#: このファイルが扱う問題ではないとき(頂点が最初から外/脚が最初から
#: 不揃い/辺名が違う/幅が0以下)。他の修理か人が要る。
OUT_OF_SCOPE = "UNKNOWN_NOT_A_DART_FIT_PROBLEM"
#: pattern["darts"] が1本でないとき — この修理は「1本を直す」契約で、
#: 複数本の同時修理は範囲外(組み合わせ爆発を持ち込まない)。
BAD_SHAPE = "UNKNOWN_PATTERN_MUST_HOLD_ONE_DART"


def _draft(outline: Sequence[Vec], piece: str) -> Dict[str, Any]:
    return {"verdict": "ANSWER",
            "pieces": [{"name": piece, "outline": list(outline)}]}


def _edge_ij(outline: Sequence[Vec], edge: str) -> Optional[Tuple[int, int]]:
    es = {n: (i, j) for n, i, j in _dt._edges_of(outline)}
    return es.get(edge)


def _edge_len(outline: Sequence[Vec], edge: str) -> Optional[float]:
    ij = _edge_ij(outline, edge)
    if ij is None:
        return None
    i, j = ij
    return _dt._len(_dt._sub(outline[j], outline[i]))


def _spans_on(other: Sequence[Dict[str, Any]], outline: Sequence[Vec],
              edge: str) -> List[Tuple[float, float]]:
    """``other_darts`` のうち、この辺の上にある分だけ (lo, hi) の t 範囲で
    返す。``apply`` が重なりを見るのと同じ式(intake の半分を辺長で割って
    t 単位にする)を使う — ここだけ独自の単位系を持つと、後で
    ``_dt.apply`` に投げ返した答えと食い違う。
    """
    L = _edge_len(outline, edge)
    out: List[Tuple[float, float]] = []
    if not L:
        return out
    for d in other:
        if d.get("edge") != edge:
            continue
        half_t = (float(d["intake_cm"]) / 2.0) / L
        out.append((float(d["t"]) - half_t, float(d["t"]) + half_t))
    return sorted(out)


def _free_gaps(spans: Sequence[Tuple[float, float]]
               ) -> List[Tuple[float, float]]:
    """占有区間の外側、``[0, 1]`` の中の空き区間。既に置いた ``other_darts``
    だけを塞ぎとして見る — 修理対象の元の場所は空き扱いになる(そこを
    今から作り直すのだから)。
    """
    gaps: List[Tuple[float, float]] = []
    cur = 0.0
    for lo, hi in spans:
        if lo > cur:
            gaps.append((cur, lo))
        cur = max(cur, hi)
    if cur < 1.0:
        gaps.append((cur, 1.0))
    return gaps


def detect(pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """今のダーツがこの裁片に本当に入るかを測る。**測るのは darts.py。**

    ``pattern`` は ``{"outline", "piece", "darts": [一本], "other_darts":
    [既に置いてある分, 省略可]}``。問題が無ければ ``None``。あれば
    ``{"problem", "where", "measured"}``。
    """
    darts_in = list(pattern.get("darts") or [])
    if len(darts_in) != 1:
        return {"problem": BAD_SHAPE, "where": {"piece": pattern.get("piece")},
                "measured": {"dart_count": len(darts_in)}}
    target = darts_in[0]
    outline = [tuple(map(float, p)) for p in pattern["outline"]]
    piece = pattern["piece"]
    other = list(pattern.get("other_darts") or [])

    # 単体の幾何(辺・幅・頂点・脚)は open_one 一本で全部わかる。他の
    # ダーツとの重なりはここではまだ見ない — 単体が壊れているのに重なり
    # の話をしても、どちらの問題か混ざる。
    solo = _dt.open_one(outline, target)
    where = {"piece": piece, "edge": target.get("edge"), "t": target.get("t")}
    if solo["verdict"] == TOO_WIDE:
        return {"problem": TOO_WIDE, "where": where,
                "measured": {"intake_cm": solo["intake_cm"],
                             "edge_cm": solo["edge_cm"]}}
    if solo["verdict"] != "ANSWER":
        # APEX_OUT・LEGS_UNEQUAL・NO_EDGE・BAD_INTAKE — このファイルの
        # 契約はTOO_WIDE/OVERLAPだけ。範囲外だと**名乗って**返す。
        return {"problem": solo["verdict"], "where": where,
                "measured": {k: v for k, v in solo.items()
                             if k not in ("verdict", "how_to_close")}}

    # 単体は入る。他のダーツと重なるかは apply() に聞く — 同じ辺の上の
    # span 判定をここでもう一度書かない。
    r = _dt.apply(_draft(outline, piece), other + [target])
    clashes = [ref for ref in r["refused"] if ref.get("verdict") == OVERLAP]
    if not clashes:
        return None
    ov = clashes[0]
    return {"problem": OVERLAP, "where": where,
            "measured": {"clashes_with": ov.get("clashes_with"),
                         "intake_cm": target["intake_cm"]}}


#: ``apply`` は toward 式のダーツを真度取りで動かすので、返ってくる
#: ``t`` は渡した ``t`` と一致しない — それで候補を探し当てようとすると
#: 見失う。だから候補だけに一時的な役目名を付けて、それで見分ける。
_PROBE_ROLE = "__repair_dart_probe__"


def _try_candidate(outline: Sequence[Vec], piece: str,
                    other: Sequence[Dict[str, Any]],
                    candidate: Dict[str, Any]
                    ) -> Optional[Dict[str, Any]]:
    """候補ダーツ1本を実際に ``open_one``→``apply`` の両方に通す。**両方
    を ANSWER で通った案しか使わない** — open_one だけ見ると他のダーツと
    の重なりを見落とす。通れば開いた形を返す(元の役目名を付け直して)、
    通らなければ None。
    """
    probe = dict(candidate, role=_PROBE_ROLE)
    r = _dt.apply(_draft(outline, piece), list(other) + [probe])
    if r["refused"]:
        return None
    for opened in r["darts"]:
        if opened.get("role") == _PROBE_ROLE:
            return dict(opened, role=candidate.get("role", ""))
    return None


def _repair_too_wide(outline: Sequence[Vec], piece: str,
                      target: Dict[str, Any],
                      other: Sequence[Dict[str, Any]]
                      ) -> Dict[str, Any]:
    edge = target["edge"]
    edge_len = _edge_len(outline, edge)
    w0 = float(target["intake_cm"])
    solo_before = _dt.open_one(outline, target)  # TOO_WIDE を測った本人
    before = {"verdict": solo_before["verdict"],
              "intake_cm": solo_before["intake_cm"],
              "edge_cm": solo_before["edge_cm"]}
    attempts: List[Dict[str, Any]] = []

    ij = _edge_ij(outline, edge)
    mid = _dt._at(outline, ij[0], ij[1], float(target["t"]))
    toward = target.get("toward")
    depth0 = (_dt._len(_dt._sub(tuple(toward), mid)) if toward is not None
              else float(target["length_cm"]))

    # --- 戦略1: 深める。幅を edge_cm - LEG_TOLERANCE_CM(darts.py 自身が
    # 同じ断りの中で既に計算している値)まで狭め、面積 0.5*w*depth を
    # 保つように深さを足す。「同じ抜き量を、長く狭い楔で取る」。
    if depth0 > 0.0 and "assumed" in solo_before:
        w1 = float(solo_before["assumed"])
        depth1 = w0 * depth0 / w1
        if toward is not None:
            direction = _dt._unit(_dt._sub(tuple(toward), mid))
            new_toward = _dt._add(mid, _dt._mul(direction, depth1))
            cand = _dt.dart(piece, edge, target["t"], w1, 0.0,
                            role=target.get("role", ""), toward=new_toward)
        else:
            cand = _dt.dart(piece, edge, target["t"], w1, depth1,
                            role=target.get("role", ""))
        opened = _try_candidate(outline, piece, other, cand)
        if opened is not None:
            after = {"verdict": "ANSWER", "intake_cm": opened["intake_cm"],
                     "edge_cm": opened["edge_cm_before"]}
            area0 = 0.5 * w0 * depth0
            return {
                "verdict": "ANSWER", "strategy": "deepen",
                "changed": (f"{edge} の抜き幅を {w0:.4f}cm から "
                           f"{w1:.4f}cm に狭め、深さを {depth0:.4f}cm から "
                           f"{depth1:.4f}cm に伸ばして同じ抜き面積を保った"),
                "cost": {"intake_reduced_cm": round(w0 - w1, 4),
                         "depth_added_cm": round(depth1 - depth0, 4),
                         "area_preserved_cm2": round(area0, 6),
                         "note": ("辺1本の中でシェイピングが浅く広くから"
                                  "深く狭くに変わる。裁片のこの場所だけ"
                                  "布が急に立ち上がる")},
                "kind": "INFERRED",
                "pattern": {"outline": list(outline), "piece": piece,
                           "darts": [cand], "other_darts": list(other)},
                "before": before, "after": after,
            }
        r1 = _dt.open_one(outline, cand)
        attempts.append({"strategy": "deepen", "verdict": r1["verdict"],
                         "detail": r1.get("how_to_close", "")})
    else:
        attempts.append({"strategy": "deepen",
                         "verdict": "UNKNOWN_EDGE_TOO_SHORT_TO_BACK_OFF",
                         "detail": (f"edge_cm {edge_len} は "
                                   f"2x LEG_TOLERANCE_CM "
                                   f"({2*_dt.LEG_TOLERANCE_CM}) 以下、"
                                   f"または元の深さが0"
                                   if depth0 <= 0.0 else "")})

    # --- 戦略2: もっと長い辺に移す。抜き幅・深さ(または toward の
    # 絶対座標)はそのまま、住所だけ変える。t は 0.5(辺の中心)から
    # 始める — 元の t はこの新しい辺の上では意味を持たない。
    moved = _repair_move_to_longer_edge(outline, piece, target, other,
                                        skip_edge=edge, w0=w0,
                                        depth0=depth0, toward=toward)
    if moved is not None:
        opened, new_edge = moved
        after = {"verdict": "ANSWER", "intake_cm": opened["intake_cm"],
                 "edge_cm": opened["edge_cm_before"]}
        return {
            "verdict": "ANSWER", "strategy": "move_to_longer_edge",
            "changed": (f"{edge}({edge_len:.4f}cm)には入らないので、"
                       f"{new_edge}({_edge_len(outline, new_edge):.4f}cm)"
                       f"へダーツごと移した。幅・深さは変えていない"),
            "cost": {"moved_from": edge, "moved_to": new_edge,
                     "note": "体のどこでシェイピングが起きるかが変わる — "
                             "元の辺の分は取れないまま残る"},
            "kind": "INFERRED",
            "pattern": {"outline": list(outline), "piece": piece,
                       "darts": [opened_to_dart(opened)],
                       "other_darts": list(other)},
            "before": before,
            "after": {"verdict": "ANSWER", "intake_cm": opened["intake_cm"],
                      "edge_cm": opened["edge_cm_before"]},
        }
    attempts.append({"strategy": "move_to_longer_edge",
                     "verdict": "UNKNOWN_NO_EDGE_LONG_ENOUGH", "detail": ""})

    return {
        "verdict": CANNOT_REPAIR, "kind": "INFERRED",
        "how_to_close": (f"{edge} は {edge_len:.4f}cm しかなく、抜き幅 "
                         f"{w0:.4f}cm を狭めても頂点が収まらず、この裁片の"
                         f"どの辺に移しても足りません"),
        "before": before, "attempts": attempts,
    }


def opened_to_dart(opened: Dict[str, Any]) -> Dict[str, Any]:
    """``open_one``/``apply`` が返す開いた形から、もう一度渡せる
    ダーツ宣言に戻す。往復させても中身は変わらない(perpendicular の場合
    ``length_cm`` を、そうでなければ ``toward`` を復元する)。
    """
    if opened.get("perpendicular"):
        return _dt.dart(opened["piece"], opened["edge"], opened["t"],
                        opened["intake_cm"], opened["depth_cm"],
                        role=opened.get("role", ""))
    return _dt.dart(opened["piece"], opened["edge"], opened["t"],
                    opened["intake_cm"], 0.0, role=opened.get("role", ""),
                    toward=tuple(opened["apex"]))


def _repair_move_to_longer_edge(outline: Sequence[Vec], piece: str,
                                 target: Dict[str, Any],
                                 other: Sequence[Dict[str, Any]],
                                 skip_edge: str, w0: float, depth0: float,
                                 toward: Optional[Sequence[float]]
                                 ) -> Optional[Tuple[Dict[str, Any], str]]:
    """他の辺のどれかに、幅を変えずにこのダーツごと移せないか試す。
    候補は短い順に試す — 移すことそのものが代償(その辺のその場所の
    シェイピングを失う)なので、間に合う中で一番近い(短い)辺を選ぶ。
    """
    edges = [n for n, _, _ in _dt._edges_of(outline) if n != skip_edge]
    edges.sort(key=lambda e: _edge_len(outline, e) or 0.0)
    for e in edges:
        L = _edge_len(outline, e)
        if not L or w0 >= L:
            continue
        if toward is not None:
            cand = _dt.dart(piece, e, 0.5, w0, 0.0, role=target.get("role", ""),
                            toward=tuple(toward))
        else:
            cand = _dt.dart(piece, e, 0.5, w0, depth0,
                            role=target.get("role", ""))
        opened = _try_candidate(outline, piece, other, cand)
        if opened is not None:
            return opened, e
    return None


def _repair_overlap(outline: Sequence[Vec], piece: str,
                     target: Dict[str, Any],
                     other: Sequence[Dict[str, Any]]
                     ) -> Dict[str, Any]:
    edge = target["edge"]
    edge_len = _edge_len(outline, edge)
    w0 = float(target["intake_cm"])
    before_apply = _dt.apply(_draft(outline, piece), list(other) + [target])
    before = {"verdict": ("ANSWER" if not before_apply["refused"]
                          else before_apply["refused"][0]["verdict"]),
              "clashes_with": (before_apply["refused"][0].get("clashes_with")
                               if before_apply["refused"] else [])}
    attempts: List[Dict[str, Any]] = []

    # --- 戦略1: 半分ずつの二本に分ける。合計の抜き量は変えない。それぞれ
    # の半幅が収まる空き区間を、既に置いてある other_darts の隙間から
    # 直接探す — 全幅で探して見つからない場所でも、半幅なら入ることが
    # ある(全幅の候補探しを流用すると、この場合を取りこぼす)。
    w_half = w0 / 2.0
    if edge_len and w_half > 0.0:
        half_t = (w_half / 2.0) / edge_len
        spans = _spans_on(other, outline, edge)
        gaps = _free_gaps(spans)
        placed = _place_two_halves(gaps, float(target["t"]), half_t)
        if placed is not None:
            t1, t2 = placed
            half1 = _dt.dart(piece, edge, t1, w_half,
                             float(target.get("length_cm", 0.0)) or 0.0,
                             role=(target.get("role") or "dart") + "-a",
                             toward=target.get("toward"))
            half2 = _dt.dart(piece, edge, t2, w_half,
                             float(target.get("length_cm", 0.0)) or 0.0,
                             role=(target.get("role") or "dart") + "-b",
                             toward=target.get("toward"))
            r = _dt.apply(_draft(outline, piece), list(other) + [half1, half2])
            if not r["refused"] and len(r["darts"]) == len(other) + 2:
                after = {"verdict": "ANSWER", "clashes_with": []}
                return {
                    "verdict": "ANSWER", "strategy": "split",
                    "changed": (f"{edge} の抜き {w0:.4f}cm の一本を、"
                               f"{w_half:.4f}cm ずつの二本(t={t1:.4f} と "
                               f"t={t2:.4f})に分けた。合計の抜き量は変え"
                               f"ていない"),
                    "cost": {"darts_to_sew": 2,
                             "intake_each_cm": round(w_half, 4),
                             "total_intake_cm": round(w_half * 2, 6),
                             "note": ("同じシェイピングが一箇所に集中せず、"
                                      "辺の上の二箇所に分散する。縫う手間は"
                                      "一本から二本に増える")},
                    "kind": "INFERRED",
                    "pattern": {"outline": list(outline), "piece": piece,
                               "darts": [half1, half2],
                               "other_darts": list(other)},
                    "before": before, "after": after,
                }
        attempts.append({"strategy": "split",
                         "verdict": "UNKNOWN_NO_ROOM_FOR_EITHER_HALF",
                         "detail": f"free gaps on {edge}: {gaps}"})

    # --- 戦略2: もっと長い辺に丸ごと移す。
    ij = _edge_ij(outline, edge)
    mid = _dt._at(outline, ij[0], ij[1], float(target["t"]))
    toward = target.get("toward")
    depth0 = (_dt._len(_dt._sub(tuple(toward), mid)) if toward is not None
              else float(target.get("length_cm", 0.0)))
    moved = _repair_move_to_longer_edge(outline, piece, target, other,
                                        skip_edge=edge, w0=w0,
                                        depth0=depth0, toward=toward)
    if moved is not None:
        opened, new_edge = moved
        return {
            "verdict": "ANSWER", "strategy": "move_to_longer_edge",
            "changed": (f"{edge} は既に埋まっているので、ダーツごと "
                       f"{new_edge} へ移した。抜き幅は変えていない"),
            "cost": {"moved_from": edge, "moved_to": new_edge,
                     "note": "シェイピングが体の別の場所に移る"},
            "kind": "INFERRED",
            "pattern": {"outline": list(outline), "piece": piece,
                       "darts": [opened_to_dart(opened)],
                       "other_darts": list(other)},
            "before": before,
            "after": {"verdict": "ANSWER", "clashes_with": []},
        }
    attempts.append({"strategy": "move_to_longer_edge",
                     "verdict": "UNKNOWN_NO_EDGE_WITH_ROOM", "detail": ""})

    return {
        "verdict": CANNOT_REPAIR, "kind": "INFERRED",
        "how_to_close": (f"{edge} の上に半幅 {w_half:.4f}cm 二本分の空きが"
                         f"なく、この裁片の他のどの辺にも幅 {w0:.4f}cm 分"
                         f"の空きがありません"),
        "before": before, "attempts": attempts,
    }


#: 空き区間の端ぴったりに置くと、境界を挟んだ相手側の span と浮動小数点
#: の丸め差(1e-16 桁)だけ食い込んで、``apply`` の重なり判定が「触れて
#: いるだけ」のはずを「重なっている」と読むことがある — 実測して踏んだ
#: 罠(t=0.532608695652174 が隣の span の端 0.5217391304347826 と、算出
#: 経路の違いだけで最後の桁がずれて重なり扱いになった)。cm 単位の辺の
#: 上では無視できる幅(1e-6 は 92cm 辺で 0.0001cm 未満)だけ内側に控える。
_GAP_MARGIN_T = 1e-6


def _place_one(gaps: Sequence[Tuple[float, float]], target_t: float,
               half_t: float) -> Optional[float]:
    """半幅ダーツ一本を、空き区間のうち元の位置に一番近く置ける場所へ。
    置けなければ ``None``。
    """
    slot = 2.0 * half_t + 2.0 * _GAP_MARGIN_T
    best: Optional[Tuple[float, float]] = None
    for lo, hi in gaps:
        if hi - lo < slot:
            continue
        lo_b, hi_b = lo + half_t + _GAP_MARGIN_T, hi - half_t - _GAP_MARGIN_T
        c = min(max(target_t, lo_b), hi_b)
        d = abs(c - target_t)
        if best is None or d < best[0]:
            best = (d, c)
    return None if best is None else best[1]


def _subtract_span(gaps: Sequence[Tuple[float, float]], centre: float,
                    half_t: float) -> List[Tuple[float, float]]:
    """置いた半幅ダーツの分(余白込み)を空き区間から削る。**二本目を
    探すときは一本目が占めた場所を二度と提案しない**ための引き算。
    """
    lo = centre - half_t - _GAP_MARGIN_T
    hi = centre + half_t + _GAP_MARGIN_T
    out: List[Tuple[float, float]] = []
    for g_lo, g_hi in gaps:
        if hi <= g_lo or lo >= g_hi:
            out.append((g_lo, g_hi))
            continue
        if g_lo < lo:
            out.append((g_lo, lo))
        if hi < g_hi:
            out.append((hi, g_hi))
    return out


def _place_two_halves(gaps: Sequence[Tuple[float, float]], target_t: float,
                       half_t: float) -> Optional[Tuple[float, float]]:
    """半幅ダーツ二本を、既にある空き区間の中に置く。**一本ずつ、その
    時点で元の位置に一番近い場所へ** — 一本目を置いたら、その場所を
    引いた残りの空きから二本目を探す。二本纏めて置く特別扱いをしない分、
    境界がぴったり揃う浮動小数点の罠(1e-16桁の丸め差だけで「重なって
    いる」と読まれる)を作らない。置けなければ ``None``。
    """
    t1 = _place_one(gaps, target_t, half_t)
    if t1 is None:
        return None
    remaining = _subtract_span(gaps, t1, half_t)
    t2 = _place_one(remaining, target_t, half_t)
    if t2 is None:
        return None
    return t1, t2


def repair(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """``pattern`` のダーツ1本を、辺に合うように直す。

    直せたら ``verdict: ANSWER`` と、変えた内容・代償・修理後の
    ``pattern`` を返す。直せなければ ``UNKNOWN_*`` で、何を試して
    どれも通らなかったかを ``attempts`` に残す。
    """
    d = detect(pattern)
    if d is None:
        return {"verdict": "ANSWER", "strategy": "none",
                "changed": "変えていない — 測ってみたが問題がなかった",
                "cost": {}, "kind": "OBSERVED",
                "pattern": copy.deepcopy(pattern),
                "before": {"verdict": "ANSWER"}, "after": {"verdict": "ANSWER"}}

    outline = [tuple(map(float, p)) for p in pattern["outline"]]
    piece = pattern["piece"]
    other = list(pattern.get("other_darts") or [])
    problem = d["problem"]

    if problem == TOO_WIDE:
        target = pattern["darts"][0]
        return _repair_too_wide(outline, piece, target, other)
    if problem == OVERLAP:
        target = pattern["darts"][0]
        return _repair_overlap(outline, piece, target, other)

    # BAD_SHAPE や、単体幾何そのものが壊れている(APEX_OUT/LEGS_UNEQUAL/
    # NO_EDGE/BAD_INTAKE)場合はこのファイルの契約の外。**半端に手を出して
    # ANSWER を返さない** — 名乗って断る。
    return {"verdict": OUT_OF_SCOPE, "kind": "INFERRED",
            "how_to_close": (f"repair_dart は {TOO_WIDE} と {OVERLAP} しか"
                             f"扱わない。検出されたのは {problem}"),
            "detected": d}
