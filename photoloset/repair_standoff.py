# -*- coding: utf-8 -*-
"""輪郭の ease 分類を、修復カタログが読める構造問題へ翻訳する。

``silhouette.match`` は、一定半径オフセットで表せない輪郭をもう
「存在しない服」として拒否しない。身体より狭い高さを ``compression``、
身体から大きく離れる高さを ``standoff`` として ``structure_hints`` に
残し、型紙生成を続ける。このモジュールはその記録を ``repairs.py`` の
``detect/repair`` 契約へ繋ぐ。

ここでは構造を勝手に選ばない。ギャザー、タック、別裁片、芯地、ボーン、
伸縮素材は互いに見た目も材料も違い、正面輪郭一枚から一意には決まらない。
したがって ``repair`` は数値根拠つきの ``PROPOSED`` 選択肢を返すが、点を
動かしたり ``ANSWER`` を名乗ったりしない。高さ範囲を持つ裁片化と、人の
選択を受け取る経路が揃うまでは、それが正直な境界である。
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


STANDOFF = "standoff"
COMPRESSION = "compression"

STRUCTURE_REQUIRED = "STRUCTURE_HINT_REQUIRES_CONSTRUCTION"
CHOICE_REQUIRED = "UNKNOWN_STRUCTURE_CHOICE_REQUIRED"


def _hints(pattern: Any) -> List[Dict[str, Any]]:
    """生の silhouette 結果と photo_to_pattern の要約の両方を読む。"""
    if not isinstance(pattern, dict):
        return []
    raw = pattern.get("structure_hints")
    if raw is None:
        summary = pattern.get("silhouette_match_summary")
        if isinstance(summary, dict):
            raw = summary.get("structure_hints")
    if not isinstance(raw, list):
        return []
    return [h for h in raw
            if isinstance(h, dict)
            and h.get("classification") in (STANDOFF, COMPRESSION)]


def _measured(hints: List[Dict[str, Any]]) -> Dict[str, Any]:
    ys = [float(h["y"]) for h in hints
          if isinstance(h.get("y"), (int, float))
          and not isinstance(h.get("y"), bool)]
    standoff = [h for h in hints if h.get("classification") == STANDOFF]
    compression = [h for h in hints
                   if h.get("classification") == COMPRESSION]
    stand_values = [float(h["standoff_by_cm"]) for h in standoff
                    if isinstance(h.get("standoff_by_cm"), (int, float))
                    and not isinstance(h.get("standoff_by_cm"), bool)]
    comp_values = [float(h["compress_by_cm"]) for h in compression
                   if isinstance(h.get("compress_by_cm"), (int, float))
                   and not isinstance(h.get("compress_by_cm"), bool)]
    return {
        "hint_count": len(hints),
        "standoff_count": len(standoff),
        "compression_count": len(compression),
        "y_range_cm": ([round(min(ys), 4), round(max(ys), 4)]
                       if ys else None),
        "max_standoff_by_cm": (round(max(stand_values), 4)
                                if stand_values else None),
        "max_compress_by_cm": (round(max(comp_values), 4)
                                if comp_values else None),
    }


def detect(pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """未解決の standoff/compression を一件の構造問題として返す。"""
    hints = _hints(pattern)
    if not hints:
        return None
    measured = _measured(hints)
    classes = [name for name, count in (
        (STANDOFF, measured["standoff_count"]),
        (COMPRESSION, measured["compression_count"])) if count]
    return {
        "problem": STRUCTURE_REQUIRED,
        "where": measured["y_range_cm"],
        "measured": measured,
        "classifications": classes,
        "hints": copy.deepcopy(hints),
    }


def _alternatives(problem: Dict[str, Any]) -> List[Dict[str, Any]]:
    measured = problem["measured"]
    y_range = measured["y_range_cm"]
    out: List[Dict[str, Any]] = []
    if measured["standoff_count"]:
        amount = measured["max_standoff_by_cm"]
        basis = (f"silhouette.match が y={y_range}cm の "
                 f"{measured['standoff_count']}リングで、一定半径オフセット"
                 f"の上限を最大{amount}cm超えると実測した")
        out += [
            {"value": "gather_or_tuck", "kind": "PROPOSED",
             "basis": basis,
             "requires": "寄せる辺、分量、向きを人が選ぶ"},
            {"value": "separate_supported_piece", "kind": "PROPOSED",
             "basis": basis,
             "requires": "別裁片の高さ範囲と支持方法を人が選ぶ"},
            {"value": "stiffened_panel", "kind": "PROPOSED",
             "basis": basis,
             "requires": "芯地・骨・素材の曲げ剛性を人が指定する"},
        ]
    if measured["compression_count"]:
        amount = measured["max_compress_by_cm"]
        basis = (f"silhouette.match が y={y_range}cm の "
                 f"{measured['compression_count']}リングで、輪郭が身体を"
                 f"最大{amount}cm締めると実測した")
        out += [
            {"value": "boned_or_interfaced_structure", "kind": "PROPOSED",
             "basis": basis,
             "requires": "身体を締める許可と支持材を人が指定する"},
            {"value": "stretch_material", "kind": "PROPOSED",
             "basis": basis,
             "requires": "素材の伸長率と回復率を実測して指定する"},
            {"value": "release_the_silhouette", "kind": "PROPOSED",
             "basis": basis,
             "requires": "輪郭を身体幅まで広げる設計変更を人が承認する"},
        ]
    return out


def repair(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """根拠つき選択肢を返す。未選択のまま形を変えたとは言わない。"""
    problem = detect(pattern)
    if problem is None:
        return {
            "verdict": "ANSWER",
            "changed": "nothing — no standoff/compression hint was present",
            "cost": {}, "kind": "OBSERVED", "pattern": pattern,
            "before": {}, "after": {},
        }
    measured = problem["measured"]
    return {
        "verdict": CHOICE_REQUIRED,
        "changed": ("nothing — the front-view outline measured a structure "
                    "outside the constant-offset surface model, but it does "
                    "not determine which construction should realize it"),
        "cost": {"pieces_added": 0, "seams_added": 0,
                 "unresolved_hint_count": measured["hint_count"]},
        "kind": "PROPOSED",
        "pattern": pattern,
        "before": measured,
        "after": measured,
        "alternatives": _alternatives(problem),
        "cannot_fix_because": (
            "gathers, tucks, separate supported pieces, stiffening, boning, "
            "stretch material and releasing the silhouette are physically "
            "different constructions. One front-view outline measures the "
            "width departure but cannot choose among them. A human choice "
            "and height-ranged piece construction are still required"),
        "how_to_close": (
            "choose one proposed construction for each affected height "
            "range; then pass that choice to height-ranged flatten/panel "
            "construction and re-run the same structure and sewability "
            "measurements"),
    }
