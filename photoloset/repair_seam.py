# -*- coding: utf-8 -*-
"""縫い代の反物語 — 突き合わせる辺の長さが合わないとき、何を変えて縫える
ようにするか。**測るのは常に既存の検算 (``garment_pattern._seam_checks``)
と、辺の点から長さを出す既存の式 (``garment_pattern._length``)。ここで
二つ目の測定を書かない。**

型紙 (``garment_pattern.draft`` の返り値と同じ形の辞書) を受け取り、
``seam_checks`` のどれかが縫えない (``sewable`` が False) とき、四つの
直し方から一つを選んで実際に適用する:

  1. いせ込み (ease) — 長い方の辺に沿って余りを配る。**布は動かさない。**
     小さな余りだけ。
  2. ギャザー (gather) — もっと大きく配る。**仕上げが変わる** — ギャザー
     の寄せが見える。
  3. ダーツに取る (dart) — 余りをダーツへ逃がす。``darts.py`` を呼ぶだけで、
     ここでダーツの幾何を書き直さない。**ダーツが一つ増える。**
  4. 縫い目を動かす (move the seam) — 辺の点そのものを動かして長さを
     変える。**シルエットが動く** — 動いた距離を必ず数字で出す。

**直した型紙は OBSERVED に戻らない。** ``kind`` は常に ``"INFERRED"``。
写真から採った寸法ではなく、この道具が型紙を変えた結果だから。

**この装置が直せない場合:**
  - 差が短い方の辺の長さ以上 (``UNKNOWN_SURPLUS_EXCEEDS_SHORTER_EDGE``) —
    それだけ削ると辺が潰れるか負になる。半端な値を返さず断る。
  - 袖山と袖ぐりのように、比べている片方が単一の辺ではなく複数辺の合計
    (``UNKNOWN_COMBINED_EDGE``) — ダーツも移動も「どの一本の辺を」動かす
    のか決まらない。
  - 縫い目を動かそうとした辺で、記録された ``length`` と点から測った
    実際の長さが食い違っている (``UNKNOWN_EDGE_LENGTH_INCONSISTENT``) —
    ``garment_pattern._seam_checks`` は ``length`` 欄を無条件に信じて
    点を測り直さないので、ここで食い違いに気付かないと、動かした後の
    長さが目標からずれて出る(2026-08-28 の欠陥: 最初の実装は記録された
    ``length`` をそのまま倍率の分母に使っていて、点の実長と食い違う
    テスト用の型紙で動かした後の辺が目標の 20.3cm ではなく 14.13cm に
    なっていた。**倍率は動かす点自身の実測長に対してでなければならない**)。

いせ込みとギャザーは辺の点を一切変えない。だから「直す前」と「直した後」
を同じ ``_seam_checks`` に通すと、辺の長さは**同じ値のまま**返ってくる —
それは測定の誤りではなく、この二つの直し方の性質そのもの: 布の長さの
差自体は消さず、縫うときの扱い方だけを変える。ここではその事実を隠さず、
「厳密な検算 (``sewable``) はまだ False のまま」と正直に返す。ダーツと
縫い目移動は辺の点(または縫い閉じた後の実効長)を実際に変えるので、
直した後は同じ ``_seam_checks`` が違う ``difference`` を返す。
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional, Tuple

from . import darts as _darts
from . import garment_pattern as _gp

Vec = Tuple[float, float]

PROBLEM = "SEAM_LENGTH_MISMATCH"

NO_PATTERN = "UNKNOWN_NO_PATTERN"
NO_PROBLEM = "UNKNOWN_NO_PROBLEM"
NO_SUCH_SEAM = "UNKNOWN_NO_SUCH_SEAM"
STRUCTURAL_CHECK = "UNKNOWN_STRUCTURAL_CHECK"
COMBINED_EDGE = "UNKNOWN_COMBINED_EDGE"
SURPLUS_TOO_LARGE = "UNKNOWN_SURPLUS_EXCEEDS_SHORTER_EDGE"
NO_SUCH_PIECE = "UNKNOWN_NO_SUCH_PIECE"
EDGE_LENGTH_INCONSISTENT = "UNKNOWN_EDGE_LENGTH_INCONSISTENT"

#: いせ込みの上限(cm)。**この道具が選んだ値で、実測から出したもの
#: ではない。** 課題文にある「毛は肩で2〜3cm、安定した織りはほぼ無し」
#: という範囲の下端を採る — この型紙は生地の種類を持たないので、
#: 生地を知らないまま広い方(3cm)を仮定するのは危険側に倒れる。狭い方
#: を仮定して、後で生地が分かればここを引数で越えられるようにする。
EASE_LIMIT_CM = 2.0

#: ギャザーの上限(cm)。**選んだ値。** いせ込みより明らかに大きく持てる
#: が、無限には持てない — 際限なく配ると「ギャザーの意匠」ではなく
#: 「合わなかった辺の言い訳」になる。この境目をどこかに置く必要が
#: あるので、いせ込みの3倍を切りのよい数として選ぶ。
GATHER_LIMIT_CM = 6.0

#: ダーツの深さは、抜く幅(intake_cm = 余り)の何倍に取るか。**選んだ比。**
#: 実物のダーツは浅すぎると立体にならず、深すぎると裁片からはみ出す
#: (``darts.APEX_OUT``)。3倍は「浅すぎない」側を狙った値で、はみ出す
#: 場合は ``darts.py`` 自身が断る — その断りを、この関数が縫い目移動へ
#: 落ちる合図として使う。ここでは深さの上限を別に発明しない。
DART_DEPTH_RATIO = 3.0

#: 縫い目移動が達成する目標: 短い方の辺 + この余白ちょうどまで長い方を
#: 縮める。**ゼロぴったりに縮めない** — ``_seam_checks`` 自身が
#: 「縫える」と判定する境目 (``tolerance``) まで動かせば足りるので、
#: それ以上シルエットを動かすのは余計なコストになる。目標の余白は
#: その検査自身の ``tolerance`` を使う(ここで新しい数字を発明しない)。


def _length(points: Any) -> float:
    """辺の長さ。**``garment_pattern._length`` をそのまま呼ぶ** —
    二つ目の物差しを作らない。"""
    return _gp._length([tuple(p) for p in points])


def _seam_checks(pieces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """縫い合わせの検算。**``garment_pattern._seam_checks`` をそのまま
    呼ぶ。** 直す前も直した後も、同じこの関数で測る。"""
    return _gp._seam_checks(pieces)


def detect(pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """縫えない辺を探す。**``structural`` は候補から外す** — 前後が同じ
    点から引かれている検査は差が構成上ゼロで、直す対象がない。

    複数縫えない辺があれば、差が一番大きいものを返す。``None`` は
    「縫えない辺が無い」で、型紙が引けていない場合も ``None``。

    **いせ込み/ギャザーで既に扱った辺は、もう候補に挙げない。** その
    二つは辺の点を変えないので、``_seam_checks`` の ``sewable`` は
    直した後も ``False`` のまま——それをここで除外しなければ、直した
    直後にまた同じ辺を「まだ縫えない」と拾って**無限に発火し続ける**
    (実測: ``repairs.make_sewable`` に通したとき、budget を使い切るまで
    同じギャザー修理が毎回そのまま繰り返された)。``pattern[
    "construction_notes"]`` に載った辺は、幾何としては変わっていなくても
    この道具の中では**扱い済み**として数える。
    """
    if not isinstance(pattern, dict):
        return None
    if pattern.get("verdict") != "ANSWER" or not pattern.get("pieces"):
        return None
    checks = _seam_checks(pattern["pieces"])
    handled = {n["label"] for n in (pattern.get("construction_notes") or [])
              if isinstance(n, dict) and "label" in n}
    candidates = [c for c in checks
                  if not c.get("structural") and not c.get("sewable")
                  and c["label"] not in handled]
    if not candidates:
        return None
    worst = max(candidates, key=lambda c: abs(c["difference"]))
    return {
        "problem": PROBLEM,
        "where": {"label": worst["label"], "a": worst["a"], "b": worst["b"]},
        "measured": {
            "length_a": worst["length_a"], "length_b": worst["length_b"],
            "difference": worst["difference"],
            "tolerance": worst["tolerance"],
        },
    }


def _dart_outline_edge(piece: Dict[str, Any],
                       edge_name: str) -> Optional[str]:
    """検算の辺名 (例: ``肩線``) を ``darts.py`` の輪郭辺名 (``e0`` など)
    に対応させる。**対応できるのは、その辺が輪郭上の連続した2点、つまり
    直線1本ぴったりのときだけ。** 袖ぐりのように複数区間からなる辺は、
    ``darts.py`` の1本の ``e{i}`` に収まらないので ``None`` を返す —
    呼び出し側はこれをダーツが使えない合図として扱う。
    """
    pts = [tuple(p) for p in piece["edges"][edge_name]["points"]]
    if len(pts) != 2:
        return None
    outline = [tuple(p) for p in piece.get("outline") or []]
    for name, i, j in _darts._edges_of(outline):
        pair = (outline[i], outline[j])
        if pair == tuple(pts) or pair == (pts[1], pts[0]):
            return name
    return None


def _clone_pieces(pieces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return copy.deepcopy(pieces)


def _set_edge(pieces: List[Dict[str, Any]], piece_name: str,
             edge_name: str, points: Optional[List[Vec]],
             length: float) -> None:
    for p in pieces:
        if p["name"] == piece_name:
            if points is not None:
                p["edges"][edge_name]["points"] = [
                    [round(x, 2), round(y, 2)] for x, y in points]
            p["edges"][edge_name]["length"] = round(length, 2)
            return
    raise KeyError(piece_name)


def _entry_by_label(checks: List[Dict[str, Any]],
                    label: str) -> Optional[Dict[str, Any]]:
    for c in checks:
        if c["label"] == label:
            return c
    return None


def _before_of(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {"length_a": entry["length_a"], "length_b": entry["length_b"],
            "difference": entry["difference"],
            "tolerance": entry["tolerance"], "sewable": entry["sewable"]}


def _ease_or_gather(pattern: Dict[str, Any], entry: Dict[str, Any],
                    surplus: float, kind: str, limit: float
                    ) -> Dict[str, Any]:
    """いせ込み・ギャザー共通。**辺の点を一切変えない。**

    直す前と直した後を同じ ``_seam_checks`` にかけると、辺の長さも差も
    ``entry`` と一字一句同じ値が返る — それはこの関数が測定を誤魔化して
    いるのではなく、いせ込み/ギャザーが布そのものの長さの差を消さない
    ことをそのまま映している。厳密な検算 (``sewable``) は ``False`` の
    ままだと正直に返し、代わりにこの道具が選んだ許容 (``limit``) の中に
    収まったかを別の欄で言う。
    """
    before = _before_of(entry)
    # 「直した後」も同じ関数・同じ辺に同じ点でもう一度かける — 変えて
    # いないことを主張だけでなく実測で示す。
    after_checks = _seam_checks(pattern["pieces"])
    after_entry = _entry_by_label(after_checks, entry["label"])
    after = _before_of(after_entry) if after_entry else dict(before)
    verb = "いせ込み" if kind == "ease" else "ギャザー"
    changed = (f"{entry['a']} と {entry['b']} の間で {surplus}cm の余りを"
              f"{verb}として辺に配った。裁片の点は動かしていない")
    out_pattern = dict(pattern)
    notes = list(pattern.get("construction_notes") or [])
    notes.append({"label": entry["label"], "method": kind,
                  "surplus_cm": surplus, "limit_cm": limit})
    out_pattern["construction_notes"] = notes
    return {
        "verdict": "ANSWER",
        "changed": changed,
        "cost": {
            "method": kind,
            f"{kind}d_cm": surplus,
            "limit_cm": limit,
            "finish_changes": kind == "gather",
            "note": ("仕上げにギャザーの寄せが見える" if kind == "gather"
                     else "見た目の変化はほぼ無い"),
        },
        "kind": "INFERRED",
        "pattern": out_pattern,
        "before": before,
        "after": dict(after, **{
            f"{kind}_ok": surplus <= limit,
            f"{kind}_limit_cm": limit,
        }),
    }


def _repair_dart(pattern: Dict[str, Any], pieces_by_name: Dict[str, Any],
                 piece_name: str, edge_name: str, surplus: float,
                 entry: Dict[str, Any], before: Dict[str, Any]
                 ) -> Tuple[Optional[Dict[str, Any]], str]:
    """ダーツで余りを逃がす。失敗したら ``(None, 理由)`` を返し、
    呼び出し側は縫い目移動に落ちる。**ここでダーツの幾何は書かない** —
    ``darts.dart``/``darts.open_one`` を呼ぶだけ。
    """
    piece = pieces_by_name.get(piece_name)
    if piece is None:
        return None, f"裁片 {piece_name} が型紙に無い"
    outline_edge = _dart_outline_edge(piece, edge_name)
    if outline_edge is None:
        return None, (f"{edge_name} は輪郭上の直線1本に対応しないので、"
                      f"darts.py の1本の辺として扱えない(複数区間)")
    depth = round(DART_DEPTH_RATIO * surplus, 4)
    d = _darts.dart(piece_name, outline_edge, t=0.5, intake_cm=surplus,
                    length_cm=depth, role="seam-length repair")
    outline_pts = [tuple(p) for p in piece["outline"]]
    result = _darts.open_one(outline_pts, d)
    if result["verdict"] != "ANSWER":
        return None, (f"darts.py が断った ({result['verdict']}): "
                      f"{result.get('how_to_close', '')}")
    new_len = result["edge_cm_after_closing"]
    updated_pieces = _clone_pieces(pattern["pieces"])
    _set_edge(updated_pieces, piece_name, edge_name, None, new_len)
    after_checks = _seam_checks(updated_pieces)
    after_entry = _entry_by_label(after_checks, entry["label"])
    after = _before_of(after_entry) if after_entry else {}
    out_pattern = dict(pattern, pieces=updated_pieces,
                       seam_checks=after_checks)
    changed = (f"{piece_name}/{edge_name} ({outline_edge}) に {surplus}cm"
              f"のダーツを開いて、縫い閉じたときの実効長を"
              f"{result['edge_cm_before']}cm から {new_len}cm に落とした")
    return {
        "verdict": "ANSWER",
        "changed": changed,
        "cost": {
            "method": "dart",
            "removed_area_cm2": result["removed_area_cm2"],
            "depth_cm": result["depth_cm"],
            "intake_cm": surplus,
            "developable": False,
            "note": "ダーツがこの裁片に一つ増えた。展開可能ではなくなる",
        },
        "kind": "INFERRED",
        "pattern": out_pattern,
        "before": before,
        "after": after,
    }, ""


def _repair_move_seam(pattern: Dict[str, Any],
                      pieces_by_name: Dict[str, Any], piece_name: str,
                      edge_name: str, target_length: float,
                      entry: Dict[str, Any], before: Dict[str, Any],
                      dart_note: str) -> Dict[str, Any]:
    """縫い目そのものを動かす。**辺の点を実際に動かし、動いた距離を
    測って返す。** 起点(辺の最初の点)からの相似拡大/縮小で、多角線
    全体の長さが一意に目標へ動く — 相似の中心から測った距離が一律に
    ``target/current`` 倍されれば、線分の数によらず折れ線全体の長さも
    同じ倍率で動くため。

    **輪郭 (``outline``) には触れない** — ``darts.py`` が「ダーツは輪郭
    に焼き込まない」としているのと同じ理由で、ここでも辺の記録だけを
    変える。だから、この辺の端点を他の辺(例えば隣の袖ぐり)と共有して
    いる場合、その隣の辺は今回の変更を知らないまま — この関数が直せる
    のは、この一本の辺の長さだけ。
    """
    piece = pieces_by_name.get(piece_name)
    if piece is None:
        return {"verdict": NO_SUCH_PIECE, "piece": piece_name}
    pts = [tuple(p) for p in piece["edges"][edge_name]["points"]]
    # **点から測り直す。記録された ``length`` は信じない。** この関数は
    # ``pts`` そのものを相似拡大/縮小するので、倍率は ``pts`` の実際の
    # 幾何長に対してでなければならない。``_seam_checks`` は ``length``
    # 欄を無条件に信じる(点から測り直さない)ので、点と食い違った
    # ``length`` が入っていても検算はそれに気付かない — ここで気付く。
    current_len = _length(pts)
    recorded_len = piece["edges"][edge_name]["length"]
    if abs(current_len - recorded_len) > 0.01:
        return {"verdict": EDGE_LENGTH_INCONSISTENT, "label": entry["label"],
                "measured": {"recorded_cm": recorded_len,
                            "geometric_cm": current_len},
                "how_to_close": "この辺は記録された長さと点から測った実際"
                                "の長さが食い違っています。動かす前に"
                                "型紙そのものを直してください"}
    if current_len <= 0.0:
        return {"verdict": SURPLUS_TOO_LARGE, "label": entry["label"],
                "how_to_close": "辺の長さが0なので動かしようがない"}
    k = target_length / current_len
    anchor = pts[0]
    new_pts = [anchor] + [
        (anchor[0] + (x - anchor[0]) * k, anchor[1] + (y - anchor[1]) * k)
        for x, y in pts[1:]]
    displacement = max(
        math.hypot(nx - ox, ny - oy)
        for (ox, oy), (nx, ny) in zip(pts, new_pts))
    new_len = _length(new_pts)
    updated_pieces = _clone_pieces(pattern["pieces"])
    _set_edge(updated_pieces, piece_name, edge_name, new_pts, new_len)
    after_checks = _seam_checks(updated_pieces)
    after_entry = _entry_by_label(after_checks, entry["label"])
    after = _before_of(after_entry) if after_entry else {}
    out_pattern = dict(pattern, pieces=updated_pieces,
                       seam_checks=after_checks)
    note = ("裁片の輪郭 (outline) は連動して直していない。この辺の端点を"
           "他の辺と共有している場合、その辺の長さは今回の変更の外")
    if dart_note:
        note = f"ダーツは使えなかった({dart_note})ので縫い目移動に落ちた。{note}"
    changed = (f"{piece_name}/{edge_name} の点を動かして、辺の長さを"
              f"{round(current_len, 2)}cm から {round(new_len, 2)}cm に"
              f"変えた(縫えると判定される tolerance の内側まで)")
    return {
        "verdict": "ANSWER",
        "changed": changed,
        "cost": {
            "method": "move_seam",
            "max_point_displacement_cm": round(displacement, 4),
            "edge_before_cm": round(current_len, 2),
            "edge_after_cm": round(new_len, 2),
            "note": note,
        },
        "kind": "INFERRED",
        "pattern": out_pattern,
        "before": before,
        "after": after,
    }


def repair(pattern: Dict[str, Any], label: Optional[str] = None
          ) -> Dict[str, Any]:
    """縫えない辺を一本、直す。``label`` を渡すとその検算を狙う。渡さ
    なければ ``detect`` が選んだ一番差の大きい辺を直す。

    直し方の選び方は余りの大きさで決める(**選んだ境目で、実測から出した
    ものではない**、``EASE_LIMIT_CM``/``GATHER_LIMIT_CM`` を参照):
    余り <= EASE_LIMIT_CM ならいせ込み、<= GATHER_LIMIT_CM ならギャザー、
    それを超えたらダーツを試す。ダーツの深さの上限はここでは発明せず、
    ``darts.py`` 自身が断ったら(はみ出す・脚が揃わない・辺より広い等)
    縫い目移動に落ちる。
    """
    if not isinstance(pattern, dict) or pattern.get("verdict") != "ANSWER" \
            or not pattern.get("pieces"):
        return {"verdict": NO_PATTERN,
                "how_to_close": "先に garment_pattern.draft() で型紙を"
                                "引いてから渡してください"}

    checks = _seam_checks(pattern["pieces"])
    if label is None:
        problem = detect(pattern)
        if problem is None:
            return {"verdict": NO_PROBLEM,
                    "how_to_close": "縫えない辺が見つかりません"}
        label = problem["where"]["label"]

    entry = _entry_by_label(checks, label)
    if entry is None:
        return {"verdict": NO_SUCH_SEAM, "label": label,
                "known": sorted({c["label"] for c in checks})}
    if entry.get("structural"):
        return {"verdict": STRUCTURAL_CHECK, "label": label,
                "measured": _before_of(entry),
                "how_to_close": "この検査は前後が同じ点から引かれていて"
                                "差が構成上ゼロです。直す対象がありません"}
    if entry["sewable"]:
        return {"verdict": NO_PROBLEM, "label": label,
                "measured": _before_of(entry),
                "how_to_close": "この辺はもう縫える範囲です"}

    a_piece, a_edge = entry["a"].split("/", 1)
    b_piece, b_edge = entry["b"].split("/", 1)
    if "の合計" in b_edge or "の合計" in a_edge:
        # 袖山と袖ぐり: 片方が単一の辺ではなく前後身頃2辺の合計。
        # ダーツも縫い目移動も「どの一本の辺を」動かすかが決まらない。
        return {"verdict": COMBINED_EDGE, "label": label,
                "measured": _before_of(entry),
                "how_to_close": "比べている片方が単一の辺ではなく複数辺の"
                                "合計です。この装置は一本の辺しか動かせ"
                                "ません"}

    diff = entry["difference"]
    surplus = abs(diff)
    tolerance = entry["tolerance"]
    if diff > 0:
        longer_piece, longer_edge = a_piece, a_edge
        longer_len, shorter_len = entry["length_a"], entry["length_b"]
    else:
        longer_piece, longer_edge = b_piece, b_edge
        longer_len, shorter_len = entry["length_b"], entry["length_a"]

    if surplus >= shorter_len:
        return {"verdict": SURPLUS_TOO_LARGE, "label": label,
                "measured": {"surplus_cm": round(surplus, 4),
                            "shorter_edge_cm": round(shorter_len, 4)},
                "how_to_close": "短い方の辺の長さ以上を削ると辺が潰れる"
                                "か負になります。型紙そのものを引き"
                                "直してください"}

    pieces_by_name = {p["name"]: p for p in pattern["pieces"]}
    if longer_piece not in pieces_by_name:
        return {"verdict": NO_SUCH_PIECE, "piece": longer_piece}

    before = _before_of(entry)

    if surplus <= EASE_LIMIT_CM:
        return _ease_or_gather(pattern, entry, surplus, "ease",
                               EASE_LIMIT_CM)
    if surplus <= GATHER_LIMIT_CM:
        return _ease_or_gather(pattern, entry, surplus, "gather",
                               GATHER_LIMIT_CM)

    dart_result, dart_note = _repair_dart(
        pattern, pieces_by_name, longer_piece, longer_edge, surplus,
        entry, before)
    if dart_result is not None:
        return dart_result

    target_length = shorter_len + tolerance
    return _repair_move_seam(pattern, pieces_by_name, longer_piece,
                             longer_edge, target_length, entry, before,
                             dart_note)
