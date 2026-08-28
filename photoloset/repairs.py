# -*- coding: utf-8 -*-
"""修復のカタログ。**「縫えない」で止まらず、縫えるまで変える側。**

ここまでの道具(``darts`` / ``panels`` / ``garment_pattern`` / ``marker`` /
``sewing_order``)は、寸法や幾何が持ち込んだ問題を**測って断る**。それは
正しい――発明した代案で黙って埋めるより、止まって理由を言う方が誠実。

だが持ち主の設計はその先にある。**写真から始まった以上、どこかで「これは
縫えない」に当たる。当たった先で人間が毎回介入しなくても、機械が「変えて、
何を変えたか言う」ところまでは進めるはずだ。** このモジュールはその一段
上――個々の道具の断りを受け取り、**この道具の中で**変えられるだけ変えて、
変えたことを一件残らず書き出す。

**四つの修復、一つの契約。** ``repair_seam.py`` / ``repair_dart.py`` /
``repair_width.py`` (このファイルが書かれた時点でまだ存在しないかもしれ
ない――``_SIBLING_LOADERS`` の各ローダーは import に失敗しても静かに
抜ける) と、
``panels.cut`` をここで包んだ四本目。全員が同じ形を返す::

    detect(pattern, ...) -> None | {"problem": ..., "where": ..., "measured": {...}}
    repair(pattern, ...) -> {"verdict": "ANSWER" | "UNKNOWN_...", "changed": ...,
                             "cost": {...}, "kind": "INFERRED",
                             "pattern": <同じ形>, "before": {...}, "after": {...}}

**四本目は他の三本と生まれが違う。** ``repair_seam`` / ``repair_dart`` /
``repair_width`` は ``garment_pattern.draft`` が引く平面の型紙(``pieces``
の輪郭・辺)を直接見て直す。``panels.cut`` はそうではない――**寸法から
3次元の面を作り、切って、平面化し直す**側で、直す元の「平らな型紙」は
無く、代わりに人台(``mannequin.build`` の出力)と格子の粗さを持っている。
``panels.py`` は書き換えない――そちらは正しく動いている。ここでやるのは
**入出力の形を、他の三本と同じ ``pattern`` 辞書に揃える包み**で、それを
``surface`` という一つの追加の席に持たせる::

    pattern["surface"] = {
        "man": <mannequin.build の出力>,
        "segments": ..., "height_steps": ..., "gap_cm": ...,
        "n_panels": <今何枚に切ってあるか>,
        "dart_depth_ratio": ...,
    }

``surface`` を持たない pattern (``garment_pattern.draft`` がそのまま
返したもの等) には、この修復は**検知すらしない** ――measure し直す
3次元の面がここには無い。持っている情報を超えて「たぶんこう」を言わない、
という他のモジュール全部と同じ立場。

**この修復が測る「歪みすぎ」は、``panels.cut`` 自身がもう出している数字
そのもの。** 新しい歪み指標は作らない――``distortion_index_after_all_cuts``
(面積比の平均絶対偏差 + 角度誤差平均/45度。``panels.ANGLE_NORMALIZER_DEG``
参照)を、切る前と切った後で同じ関数(``panels.cut``)にもう一度測らせて
比べる。閾値(``SEWABLE_DISTORTION_INDEX_MAX``)だけはこのモジュールが
決めた値――``panels.py`` 自身は「どこまで歪めば縫えないか」を主張しない
ので、根拠は無い。この docstring に載せた実例(全周1枚 0.146 → 3回切って
0.061)が「切る前=引っかかる、切った後=通る」側に来るように選んだ、
この道具の判断だと明記する。

**カタログの二本柱。**

``diagnose(pattern)`` は登録済みの修復全部の ``detect`` を順に当てて、
見つかった問題を全部返す(直しはしない、見るだけ)。

``make_sewable(pattern, *, budget=...)`` は登録の優先順位で**一つずつ**
直す――全部同時にではない。優先順位は

    surface_split(``panels.cut`` のこの包み) → repair_dart → repair_seam → repair_width

の順で固定する。理由: パネルを割ると輪郭そのものが変わり、ダーツの深さ
(裁片の外接矩形基準)も、縫い目の長さも、生地の並べ方も全部その後に決まる
――ここが一番上流。ダーツは輪郭は変えないが辺の長さを変える(``抜き幅``
分)ので、縫い目の検算より先。生地の並べ方(``marker.lay``)は最終的な
輪郭・面積だけを見るので一番下流。**この順序を選んだ理由がこれで全部――
証明ではなく、依存の向きの読みで、直した後に diagnose を丸ごと再実行して
何が新しく出るかを ``problems_remaining`` として必ず一緒に返す**(rule 1
の「測る」)。

**止まる条件は二つ。** (1) ``budget`` 回で打ち切り――打ち切ったら
``stop_reason`` にそう書く。まだ縫えると言わない。(2) 発火する修復が
無くなった――全員が ``given_up``(直そうとして ``UNKNOWN_...`` を返した)
か、そもそも登録されていない。どちらで止まっても、最後にもう一度
``diagnose`` を回した結果を ``problems_remaining`` に残す。パターンが
戻ってきて「もう何も検出されない」と「まだ残っている」を混同させない。

**「縫える」はこのモジュールの自己申告ではない。** ``measure_sewable``
が使うのは四つの既存の検査――

  1. ``seam_checks``: ``garment_pattern.draft`` が既に付けていればそれを
     そのまま使う。付いていない pattern (``panels`` 由来の輪の型紙)には
     ``seam_specs`` から**同じ判定式・同じ 0.3cm 許容**(``garment_pattern.
     _seam_checks`` の ``compare()`` と同一)で作る――新しい基準ではない。
  2. ``sewing_order.plan``: 縫い目のラベルから ``built`` を組んで渡し、
     ``verdict == "ANSWER"`` を見る。
  3. ``marker.lay``: 生地幅・縫い代を、``marker.lay`` 自身が ``NO_WIDTH``
     / ``NO_SA`` で出す ``assumed`` を一度問い合わせてから渡す――このモジ
     ュールが独自の生地幅を仮定しない。
  4. ダーツが一つも「本物の」拒否(``SADDLE_NOT_SUPPORTED`` /
     ``NO_SEAM_SEGMENT_FITS`` / ``verdict`` が ``ANSWER`` 以外)をしていない
     こと。``WIDTH_ONE_NO_INTERIOR`` / ``NO_SURPLUS`` は「ダーツが要らない」
     という測定結果であって拒否ではない――``panels._place_dart`` 自身の
     docstring がそう言っている。

四つ全部が緑になって初めて ``sewable: True``。**このモジュールの登録済み
修復が全部発火しなくなっても、この四つのどれかが赤いままなら False の
まま返す** ――実測(下の transcript)がまさにこれを示す: ``surface_split``
は自分の問題(歪みすぎ)を2回で解消するが、生まれた輪の縫い目は
(``panels`` が各裁片を独立に平面化するせいで)長さが揃わず、
``seam_checks`` は赤いままになる。それを直すのは ``repair_seam`` の仕事で、
このファイルはそれを持っていない――**持っていないと言う**。
"""
from __future__ import annotations

import copy
import importlib
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import marker as _marker
from . import panels as _panels
from . import sewing_order as _sewing_order

#: このモジュール自身が持ち込む唯一の閾値。根拠は無い――``panels.cut`` は
#: どこからが「縫えないほど歪んでいるか」を主張しない。上の docstring に
#: 書いた実例(0.146→0.061、3回切って通る)で正しい側に来るように選んだ。
SEWABLE_DISTORTION_INDEX_MAX = 0.08

#: 縫い目の検算で許す長さの差(cm)。``garment_pattern._seam_checks`` の
#: ``肩線``/``脇線`` 比較がそのまま使っている値をここでも流用する――
#: 新しい許容を発明しない。
SEAM_LENGTH_TOLERANCE_CM = 0.3

#: ダーツの「本物の」拒否。この二つ以外(``WIDTH_ONE_NO_INTERIOR`` /
#: ``NO_SURPLUS``)は「ダーツが要らない」という測定結果で、拒否ではない
#: (``panels._place_dart`` の docstring 参照)。
_DART_NOT_NEEDED_REASONS = {"WIDTH_ONE_NO_INTERIOR", "NO_SURPLUS"}

SURFACE_TOO_DISTORTED = "SURFACE_DISTORTION_EXCEEDS_THRESHOLD"

_SIBLING_MODULES: Tuple[str, ...] = ("repair_seam", "repair_dart",
                                     "repair_width")

#: ``make_sewable`` が修復を試す優先順位。上流(パネル分割)から下流
#: (生地の並べ方)へ――このファイルの docstring に理由を書いた。
PRIORITY: Tuple[str, ...] = (
    "surface_split", "repair_dart", "repair_seam", "repair_width")


# ---------------------------------------------------------------------
# 四本目: panels.cut を detect/repair の形に包む。
# ---------------------------------------------------------------------

def _cut_from_surface(surface: Dict[str, Any], n_panels: int) -> Dict[str, Any]:
    """``surface`` に入っている粗さ・人台で ``panels.cut`` を呼ぶ。**毎回
    同じ関数で測り直す**――途中の値を信用しない(rule 1)。"""
    return _panels.cut(
        surface["man"], n_panels=n_panels,
        segments=surface.get("segments"),
        height_steps=surface.get("height_steps", 16),
        gap=surface.get("gap_cm"),
        dart_depth_ratio=surface.get("dart_depth_ratio",
                                     _panels.DEFAULT_DART_DEPTH_RATIO))


def _pattern_from_cut(man: Dict[str, Any], cut_out: Dict[str, Any],
                      prior_surface: Optional[Dict[str, Any]] = None
                      ) -> Dict[str, Any]:
    """``panels.cut`` の結果を、このカタログ共通の ``pattern`` 形に翻訳する。
    ``panels.to_pieces`` をそのまま呼ぶ――輪郭・辺の作り方はここでは
    作り直さない。"""
    tp = _panels.to_pieces(cut_out)
    surface = {
        "man": man,
        "segments": cut_out["segments"],
        "height_steps": cut_out["height_steps"],
        "gap_cm": cut_out["gap_cm"],
        "n_panels": cut_out["n_panels_reached"],
        "dart_depth_ratio": (prior_surface or {}).get(
            "dart_depth_ratio", _panels.DEFAULT_DART_DEPTH_RATIO),
        "distortion_index_after_all_cuts": cut_out[
            "distortion_index_after_all_cuts"],
    }
    # **ダーツの拒否も本物も両方積む。** placed=False を捨てると
    # 「一度も拒否していない」ことになってしまい、no-dart-refusing の
    # 検査が何も見ずに緑になる――それは測定ではなく見落とし。
    darts_list = [p["dart"] for p in cut_out["panels"]]
    return {
        "verdict": "ANSWER",
        "pieces": tp["pieces"],
        "seam_specs": tp["seam_specs"],
        "surface": surface,
        "darts": darts_list,
        "total_area_cm2": cut_out["total_area_cm2"],
        "seam_log": cut_out["seam_log"],
        "note": "panels.cut() の結果を repairs.py 共通の pattern 形に翻訳"
                "したもの。縫い代は入っていない(panels.to_pieces と同じ)",
    }


def detect(pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """``pattern["surface"]`` の人台・粗さで ``panels.cut`` を測り直し、
    ``distortion_index_after_all_cuts`` が閾値を超えていれば問題を返す。

    ``surface`` が無い pattern には検知しない――
    これは他の repair 由来の型紙(``garment_pattern.draft`` の平面製図)を
    見たとき、毎回起きる正常な no-op で、エラーではない。
    """
    if not isinstance(pattern, dict):
        return None
    surface = pattern.get("surface")
    if not surface or not surface.get("man"):
        return None
    cut_out = _cut_from_surface(surface, surface.get("n_panels", 1))
    if cut_out.get("verdict") != "ANSWER":
        # このdetectは「歪みすぎ」だけを見る。人台や格子そのものが
        # 立たない(NO_MANNEQUIN 等)のは別の問題で、ここでは名乗らない。
        return None
    idx = cut_out["distortion_index_after_all_cuts"]
    if idx <= SEWABLE_DISTORTION_INDEX_MAX:
        return None
    worst = sorted(cut_out["panels"],
                   key=lambda p: -p["distortion"]["distortion_index"])[:3]
    return {
        "problem": SURFACE_TOO_DISTORTED,
        "where": [p["name"] for p in worst],
        "measured": {
            "distortion_index_after_all_cuts": idx,
            "threshold": SEWABLE_DISTORTION_INDEX_MAX,
            "n_panels": cut_out["n_panels_reached"],
            "segments": cut_out["segments"],
            "worst_panels": {p["name"]: p["distortion"]["distortion_index"]
                             for p in worst},
        },
    }


def repair(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """``panels.cut`` の貪欲な基準で縫い目をもう一本足し、両側を測り直す。
    ``detect`` が使ったのと**同じ ``panels.cut`` を、同じ引数で**、切る前
    (今の枚数)と切った後(+1枚)の両方に呼んで、同じフィールド
    (``distortion_index_after_all_cuts``)を比べる。

    直せないときは ``ANSWER`` を返さない――半端に直して緑を名乗らない
    (rule 4)。二通り拒否する:

    * これ以上切る場所が無い/``segments`` を使い切っている
      (``panels.cut`` 自身が ``UNKNOWN_MORE_PANELS_THAN_COLUMNS`` 等で
      拒否) → ``UNKNOWN_CANNOT_ADD_SEAM``。
    * 切ったのに指数が下がらなかった(貪欲な分割がこれ以上の内部格子線
      を持たないパネルしか残っていない等) → ``UNKNOWN_SEAM_DID_NOT_HELP``。
    """
    problem = detect(pattern)
    surface = pattern.get("surface") if isinstance(pattern, dict) else None
    if problem is None or not surface:
        return {"verdict": "ANSWER", "changed": "nothing — no surface "
                "distortion problem was detected on this pattern",
                "cost": {"seams_added": 0}, "kind": pattern.get(
                    "kind", "OBSERVED") if isinstance(pattern, dict)
                    else "OBSERVED",
                "pattern": pattern, "before": {}, "after": {}}

    old_n = surface["n_panels"]
    before_cut = _cut_from_surface(surface, old_n)
    before_idx = before_cut["distortion_index_after_all_cuts"]
    new_n = old_n + 1
    after_cut = _cut_from_surface(surface, new_n)

    if after_cut.get("verdict") != "ANSWER":
        return {
            "verdict": "UNKNOWN_CANNOT_ADD_SEAM",
            "changed": ("nothing — one more seam was requested "
                       f"(n_panels {old_n} -> {new_n}) and panels.cut "
                       f"refused it: {after_cut.get('verdict')}"),
            "cost": {"seams_added": 0},
            "kind": "INFERRED",
            "pattern": pattern,
            "before": {"distortion_index_after_all_cuts": round(
                before_idx, 6), "n_panels": old_n},
            "after": {"distortion_index_after_all_cuts": round(
                before_idx, 6), "n_panels": old_n},
            "why_refused": {"upstream_verdict": after_cut.get("verdict"),
                            "segments": surface.get("segments"),
                            "how_to_close": after_cut.get("how_to_close")},
            "cannot_fix_because": (
                f"segments={surface.get('segments')} is already the most "
                f"circumferential columns this grid has (panels.cut "
                f"refuses n_panels > segments) — a curvature this "
                f"concentrated needs a finer grid (more segments) before "
                f"this repair can offer another seam, and this repair "
                f"does not change segments itself"),
        }

    after_idx = after_cut["distortion_index_after_all_cuts"]
    if after_idx >= before_idx - 1e-12:
        return {
            "verdict": "UNKNOWN_SEAM_DID_NOT_HELP",
            "changed": (f"attempted one more seam (n_panels {old_n} -> "
                       f"{after_cut['n_panels_reached']}) but the measured "
                       f"distortion did not drop "
                       f"({before_idx:.6f} -> {after_idx:.6f})"),
            "cost": {"seams_added": max(
                0, after_cut["n_panels_reached"] - old_n)},
            "kind": "INFERRED",
            "pattern": pattern,
            "before": {"distortion_index_after_all_cuts": round(
                before_idx, 6), "n_panels": old_n},
            "after": {"distortion_index_after_all_cuts": round(
                after_idx, 6), "n_panels": after_cut["n_panels_reached"]},
            "cannot_fix_because": (
                "panels.cut's own greedy split did not find a line that "
                "actually reduces the measured index further from this "
                "state"),
        }

    new_seam = after_cut["seam_log"][-1] if after_cut["seam_log"] else None
    new_pattern = _pattern_from_cut(surface["man"], after_cut, surface)
    return {
        "verdict": "ANSWER",
        "changed": (f"cut one more seam via panels.cut's own greedy "
                   f"worst-distortion rule (panel count {old_n} -> "
                   f"{after_cut['n_panels_reached']})"),
        "cost": {
            "seams_added": after_cut["n_panels_reached"] - old_n,
            "distortion_index_before": round(before_idx, 6),
            "distortion_index_after": round(after_idx, 6),
            "distortion_bought": round(before_idx - after_idx, 6),
            "distortion_bought_pct": (
                round(100.0 * (before_idx - after_idx) / before_idx, 2)
                if before_idx > 1e-12 else None),
            "new_seam": new_seam,
        },
        "kind": "INFERRED",
        "pattern": new_pattern,
        "before": {"distortion_index_after_all_cuts": round(before_idx, 6),
                  "n_panels": old_n},
        "after": {"distortion_index_after_all_cuts": round(after_idx, 6),
                 "n_panels": after_cut["n_panels_reached"]},
        "still_over_threshold": after_idx > SEWABLE_DISTORTION_INDEX_MAX,
    }


# ---------------------------------------------------------------------
# 「縫える」を測る四つの既存の検査。
# ---------------------------------------------------------------------

def _seam_checks_for(pattern: Dict[str, Any]
                     ) -> Tuple[List[Dict[str, Any]], str]:
    """pattern に ``seam_checks`` があればそれを使う(``garment_pattern.
    draft`` 由来)。無ければ ``seam_specs`` + ``pieces`` から、
    ``garment_pattern._seam_checks`` と同じ判定式・同じ許容(0.3cm)で
    作る――``panels`` 由来の輪の型紙用に、ここが埋める。"""
    existing = pattern.get("seam_checks")
    if existing is not None:
        return existing, ("pattern に既にある seam_checks "
                          "(garment_pattern.draft の検算をそのまま使用)")
    specs = pattern.get("seam_specs") or []
    pieces = {p["name"]: p for p in pattern.get("pieces") or []}
    out: List[Dict[str, Any]] = []
    for spec in specs:
        pa, ea = spec["a"]
        pb, eb = spec["b"]
        if pa not in pieces or pb not in pieces:
            continue
        edge_a = pieces[pa].get("edges", {}).get(ea)
        edge_b = pieces[pb].get("edges", {}).get(eb)
        if not edge_a or not edge_b:
            continue
        la, lb = edge_a["length"], edge_b["length"]
        diff = round(la - lb, 4)
        same_points = edge_a["points"] == edge_b["points"]
        out.append({
            "label": spec.get("label", f"{pa}/{ea} <-> {pb}/{eb}"),
            "a": f"{pa}/{ea}", "b": f"{pb}/{eb}",
            "length_a": la, "length_b": lb, "difference": diff,
            "tolerance": SEAM_LENGTH_TOLERANCE_CM,
            "sewable": abs(diff) <= SEAM_LENGTH_TOLERANCE_CM,
            "structural": same_points,
            "why": ("seam_specs から repairs.py が生成した検算。"
                   "garment_pattern._seam_checks の compare() と同じ"
                   "判定式・同じ0.3cm許容"),
        })
    return out, ("pattern に seam_checks が無いので seam_specs から生成 "
                "(garment_pattern._seam_checks の許容0.3cmを流用)")


def _seam_checks_ok(pattern: Dict[str, Any]
                    ) -> Tuple[bool, List[Dict[str, Any]],
                              List[Dict[str, Any]], str]:
    checks, source = _seam_checks_for(pattern)
    mismatches = [c for c in checks
                 if not c.get("sewable") and not c.get("structural")]
    return len(mismatches) == 0, checks, mismatches, source


def _sewing_order_ok(pattern: Dict[str, Any]
                     ) -> Tuple[bool, Dict[str, Any]]:
    checks, _ = _seam_checks_for(pattern)
    seams = [{"seam": f"{c['a']} <-> {c['b']}".replace("<->", "↔"),
             "length_a": c.get("length_a")} for c in checks]
    built = {"verdict": "ANSWER", "seams": seams}
    result = _sewing_order.plan(built)
    return result.get("verdict") == "ANSWER", result


def _marker_defaults(pattern: Dict[str, Any]) -> Tuple[float, float]:
    """生地幅・縫い代を、``marker.lay`` 自身が ``NO_WIDTH``/``NO_SA`` で
    出す ``assumed`` を問い合わせて決める――このモジュールが独自の
    生地幅を仮定しない。"""
    probe = _marker.lay(pattern, 0.0, {}, -1.0)
    width = (probe.get("assumed")
            if probe.get("verdict") == _marker.NO_WIDTH else None) or 150.0
    probe2 = _marker.lay(pattern, width, {}, -1.0)
    sa = (probe2.get("assumed")
         if probe2.get("verdict") == _marker.NO_SA else None) or 1.5
    return float(width), float(sa)


def _marker_ok(pattern: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    width, sa = _marker_defaults(pattern)
    cut = {p["name"]: 1 for p in pattern.get("pieces") or []}
    result = _marker.lay(pattern, width, cut, sa)
    return result.get("verdict") == "ANSWER", result


def _dart_entry_refusing(entry: Any) -> bool:
    """panels 由来(``placed`` キー)と darts.open_one 由来(``verdict``
    キー)の両方の形を見る。``WIDTH_ONE_NO_INTERIOR``/``NO_SURPLUS`` は
    「要らない」という測定結果で、拒否ではない。"""
    if not isinstance(entry, dict):
        return False
    if "placed" in entry:
        if entry.get("placed"):
            return False
        return entry.get("reason") not in _DART_NOT_NEEDED_REASONS
    return entry.get("verdict") not in (None, "ANSWER")


def _darts_ok(pattern: Dict[str, Any]
             ) -> Tuple[bool, List[Any], List[Any]]:
    darts_list = pattern.get("darts") or []
    refusing = [d for d in darts_list if _dart_entry_refusing(d)]
    return len(refusing) == 0, darts_list, refusing


def measure_sewable(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """「縫える」を、この四つの既存の検査で測る――このモジュール自身の
    verdict は無い。"""
    seam_ok, seam_checks, seam_mismatches, seam_source = \
        _seam_checks_ok(pattern)
    order_ok, order_result = _sewing_order_ok(pattern)
    marker_ok, marker_result = _marker_ok(pattern)
    darts_ok, darts_list, darts_refusing = _darts_ok(pattern)
    sewable = seam_ok and order_ok and marker_ok and darts_ok
    return {
        "sewable": sewable,
        "checks": {
            "seam_checks": {"ok": seam_ok, "source": seam_source,
                            "n_checks": len(seam_checks),
                            "mismatches": seam_mismatches},
            "sewing_order.plan": {"ok": order_ok,
                                  "verdict": order_result.get("verdict"),
                                  "detail": order_result},
            "marker.lay": {"ok": marker_ok,
                           "verdict": marker_result.get("verdict"),
                           "detail": marker_result},
            "no_dart_refusing": {"ok": darts_ok, "n_darts": len(darts_list),
                                 "refusing": darts_refusing},
        },
        "which_checks_used": (
            "seam_checks (pattern既存 or seam_specsから生成), "
            "sewing_order.plan, marker.lay, no genuine dart refusal"),
    }


# ---------------------------------------------------------------------
# カタログ本体。
# ---------------------------------------------------------------------

def _import_sibling(modname: str) -> Optional[Any]:
    """``repair_seam`` / ``repair_dart`` / ``repair_width`` を探す。無ければ
    (このファイルが書かれた時点ではまだ無い可能性がある)静かに抜ける――
    カタログは今揃っているものだけで動き、後で並んだ分は次の
    ``reload_registry()`` から自動で拾う(このファイルを直す必要はない)。"""
    try:
        return importlib.import_module(f".{modname}", __package__)
    except Exception:
        return None


def _load_repair_seam() -> Optional[Dict[str, Any]]:
    """``repair_seam`` の ``pattern`` は ``garment_pattern.draft`` と同じ
    形(``verdict``/``pieces``)――このカタログの ``pattern`` とそのまま
    互換なので、包まずそのまま登録する。"""
    mod = _import_sibling("repair_seam")
    if mod is None or not callable(getattr(mod, "detect", None)) \
            or not callable(getattr(mod, "repair", None)):
        return None
    return {"detect": mod.detect, "repair": mod.repair, "module": "repair_seam"}


def _load_repair_width() -> Optional[Dict[str, Any]]:
    """``repair_width`` の ``pattern`` 自体は互換だが、``detect``/``repair``
    は ``fabric_width_cm`` / ``cut`` / ``seam_allowance_cm`` を必須で取る
    (この module 自身が生地幅を仮定しないため)。このカタログもここでは
    仮定を作らない――``_marker_defaults`` が ``marker.lay`` 自身の
    ``NO_WIDTH``/``NO_SA`` から借りている、まさにその値を渡すだけ。"""
    mod = _import_sibling("repair_width")
    if mod is None or not callable(getattr(mod, "detect", None)) \
            or not callable(getattr(mod, "repair", None)):
        return None

    def _detect(pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(pattern, dict) or pattern.get("verdict") != \
                "ANSWER" or not pattern.get("pieces"):
            return None
        width, sa = _marker_defaults(pattern)
        cut = {p["name"]: 1 for p in pattern["pieces"]}
        return mod.detect(pattern, width, cut, sa)

    def _repair(pattern: Dict[str, Any]) -> Dict[str, Any]:
        width, sa = _marker_defaults(pattern)
        cut = {p["name"]: 1 for p in pattern.get("pieces") or []}
        return mod.repair(pattern, width, cut, sa)

    return {"detect": _detect, "repair": _repair, "module": "repair_width",
           "adapter": ("fabric_width_cm/cut/seam_allowance_cm は "
                      "marker.lay 自身の NO_WIDTH/NO_SA が出す assumed "
                      "から借りている(_marker_defaults)。cut は全裁片"
                      "1枚――このカタログは枚数の情報を持たない")}


def _load_repair_dart() -> Optional[Dict[str, Any]]:
    """``repair_dart`` の ``pattern`` は根本的に違う形:
    ``{"outline", "piece", "darts": [開く前のダーツ仕様を1本], "other_darts"}``
    ――**一枚の裁片・一本の候補ダーツ**を見る module で、このカタログが
    運ぶ全体の型紙(``pieces`` が複数枚)とは粒度が違う。

    このカタログの ``pattern`` は、開く前の候補ダーツ仕様をどこにも
    持っていない――``panels`` 由来の ``darts`` は既に開いた結果
    (``darts.open_one`` の返り値)で、``garment_pattern.draft`` 由来の
    pattern には ``darts`` キー自体が無い。無い情報から候補ダーツを
    作ることは、確かめようのない値を発明することになるので**しない**。

    だから、この module はカタログに登録は**する**(``REPAIRS`` に
    名前は出る)が、``detect`` は全体型紙のレベルでは常に ``None``――
    「検知しない」であって「検知して見逃した」ではない。裁片1枚・
    候補ダーツ1本の粒度で直接呼びたければ、
    ``photoloset.repair_dart.detect/repair`` をその形の ``pattern`` で
    直接呼ぶ。
    """
    mod = _import_sibling("repair_dart")
    if mod is None or not callable(getattr(mod, "detect", None)) \
            or not callable(getattr(mod, "repair", None)):
        return None

    def _detect(pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None

    def _repair(pattern: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "verdict": "UNKNOWN_INCOMPATIBLE_PATTERN_SHAPE",
            "changed": ("nothing — repairs.py never calls repair_dart at "
                       "the whole-garment level; its pattern shape is "
                       "{outline, piece, darts:[one unopened spec], "
                       "other_darts}, not this catalogue's multi-piece "
                       "pattern, and this catalogue has no source of "
                       "pending dart specs to synthesize one"),
            "cost": {}, "kind": "INFERRED", "pattern": pattern,
            "before": {}, "after": {},
            "cannot_fix_because": (
                "granularity mismatch: repair_dart validates/fixes one "
                "candidate dart on one piece; this catalogue only has "
                "either already-opened dart results (panels-origin) or "
                "no darts key at all (garment_pattern.draft-origin), "
                "never an unopened candidate to hand it"),
        }

    return {"detect": _detect, "repair": _repair, "module": "repair_dart",
           "adapter": ("granularity mismatch, documented above — detect "
                      "always returns None at the garment level")}


_SIBLING_LOADERS: Dict[str, Callable[[], Optional[Dict[str, Any]]]] = {
    "repair_seam": _load_repair_seam,
    "repair_dart": _load_repair_dart,
    "repair_width": _load_repair_width,
}


def _build_registry() -> Dict[str, Dict[str, Any]]:
    reg: Dict[str, Dict[str, Any]] = {
        "surface_split": {"detect": detect, "repair": repair,
                          "module": "repairs.py (panels.cut wrap)"},
    }
    for name in _SIBLING_MODULES:
        entry = _SIBLING_LOADERS[name]()
        if entry is not None:
            reg[name] = entry
    return reg


#: 起動時に一度だけ組む。欠けているモジュールが後から現れても拾えるよう
#: ``reload_registry()`` を用意する――プロセスを再起動しなくていい。
REPAIRS: Dict[str, Dict[str, Any]] = _build_registry()


def reload_registry() -> Dict[str, Dict[str, Any]]:
    """``REPAIRS`` を組み直す。``repair_seam.py`` 等が後から着地した
    テスト・対話セッションのために。"""
    global REPAIRS
    REPAIRS = _build_registry()
    return REPAIRS


def diagnose(pattern: Dict[str, Any]) -> List[Dict[str, Any]]:
    """登録済みの修復全部の ``detect`` を pattern に当てる。**直しはしない
    ――見るだけ。** 見つかった問題全部に、どの修復が名乗ったかを付けて
    返す。"""
    problems: List[Dict[str, Any]] = []
    for name, entry in REPAIRS.items():
        try:
            p = entry["detect"](pattern)
        except Exception as exc:  # noqa: BLE001 - 一本のdetectの例外で
            # 診断全体を止めない。壊れているのはそのdetectで、診断が
            # クラッシュしたことにはしない。
            p = {"problem": f"DETECT_RAISED_{type(exc).__name__}",
                "where": name, "measured": {"error": str(exc)}}
        if p is not None:
            p = dict(p)
            p["repair"] = name
            problems.append(p)
    return problems


def make_sewable(pattern: Dict[str, Any], *, budget: int = 8
                 ) -> Dict[str, Any]:
    """登録の優先順位(``PRIORITY``)で一つずつ直し、記録を残して返す。

    止まる条件は二つ――``budget`` 回で打ち切りか、発火する修復が無く
    なったか。どちらで止まっても、最後にもう一度 ``diagnose`` を回した
    結果を ``problems_remaining`` に残す(rule 1: 直した後も同じ関数で
    測る)。``sewable`` は ``measure_sewable`` の実測――このカタログの
    修復が全部止まっても、四つの既存検査のどれかが赤ければ False のまま
    (rule 3)。
    """
    current = copy.deepcopy(pattern)
    transcript: List[Dict[str, Any]] = []
    given_up: List[str] = []
    round_no = 0
    loop_stop = None

    while True:
        if round_no >= budget:
            loop_stop = "budget"
            break
        fired = None
        fired_name = None
        for name in PRIORITY:
            if name in given_up or name not in REPAIRS:
                continue
            entry = REPAIRS[name]
            try:
                problem = entry["detect"](current)
            except Exception as exc:  # noqa: BLE001
                problem = {"problem": f"DETECT_RAISED_{type(exc).__name__}"}
            if problem is not None:
                fired, fired_name = problem, name
                break
        if fired is None:
            loop_stop = "nothing_fires"
            break

        round_no += 1
        result = REPAIRS[fired_name]["repair"](current)
        step = {
            "round": round_no,
            "repair": fired_name,
            "problem": fired.get("problem"),
            "where": fired.get("where"),
            "measured_before": fired.get("measured"),
            "verdict": result.get("verdict"),
            "changed": result.get("changed"),
            "cost": result.get("cost"),
            "before": result.get("before"),
            "after": result.get("after"),
        }
        if result.get("verdict") == "ANSWER" and isinstance(
                result.get("pattern"), dict):
            current = result["pattern"]
            step["applied"] = True
        else:
            given_up.append(fired_name)
            step["applied"] = False
            step["cannot_fix_because"] = result.get("cannot_fix_because")
        transcript.append(step)

    remeasure = diagnose(current)
    if not remeasure:
        stop_reason = f"{round_no}回で、登録済み修復が検出する問題が0件になった"
    elif loop_stop == "budget":
        stop_reason = (f"上限{budget}回に達したので打ち切った。まだ"
                       f"{len(remeasure)}件の問題が残っている(縫えると"
                       f"言っていない)")
    else:
        stop_reason = (f"これ以上発火する修復が無い(諦めた: {given_up}"
                       f"、または未登録)。残り{len(remeasure)}件は登録"
                       f"済みのどの修復も直せない")

    sewable = measure_sewable(current)
    return {
        "rounds": round_no,
        "budget": budget,
        "stop_reason": stop_reason,
        "loop_stop": loop_stop,
        "given_up": given_up,
        "registered_repairs": sorted(REPAIRS),
        "transcript": transcript,
        "problems_remaining": remeasure,
        "pattern": current,
        **sewable,
    }
