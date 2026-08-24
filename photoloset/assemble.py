# -*- coding: utf-8 -*-
"""Block 組立器 — 承認された部品断片から服の宣言を組み立てる。

今日まで、コートの宣言は人間が1ファイルに手書きだった。目標は
「検索→候補→承認」で**宣言が組み上がる**こと。このモジュールはその
背骨で、まず選択(人が決めたこと)を入力にして宣言を出す:

    selections = {"silhouette": "Aライン",
                  "closure": "ゴムウエスト（開き無し）",
                  "waist_finish": "シャーリング"}

守る門(全部型付きで断る):

- 家族(スロット)が無い → ``UNKNOWN_NO_SUCH_SLOT``
- 候補が無い → ``UNKNOWN_NO_SUCH_VARIANT``
- 引けない候補を選んだ → ``UNKNOWN_PART_NOT_DRAFTABLE`` + why_not
  (黙って別の候補に読み替えない)

出すものは ``block.ingest`` にそのまま載る形の宣言。**組立器自身は
幾何を一つも計算しない** — 計算は製図エンジンの仕事、ここは承認済み
データの束ね役です。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import parts as _parts

NO_SLOT = "UNKNOWN_NO_SUCH_SLOT"
NO_VARIANT = "UNKNOWN_NO_SUCH_VARIANT"
NOT_DRAFTABLE = "UNKNOWN_PART_NOT_DRAFTABLE"

#: スカートとして引くために要る実測。**これも宣言の一部。**
SKIRT_MEASURES = ("waist", "hip", "skirt_length")

#: スカート共通の縫い目(ゴムウエスト・前後とも折りのとき)。
#: **型紙の名前付き辺で書く。近さでは決めない。**
SKIRT_SEAMS = [
    {"a": ("前身頃", "脇線 (右)"), "b": ("後身頃", "脇線 (右)"),
     "label": "脇線(右): 前 ↔ 後"},
    {"a": ("前身頃", "脇線 (左)"), "b": ("後身頃", "脇線 (左)"),
     "label": "脇線(左): 前 ↔ 後"},
]

#: 合印の方針。**釣り合わせの式は marks 側の手続き**に名前で委ねる。
SKIRT_NOTCH_PLAN = [
    {"piece": "前身頃", "edge": "脇線 (右)", "rule": "midpoint_balance"},
    {"piece": "前身頃", "edge": "脇線 (左)", "rule": "midpoint_balance"},
    {"piece": "後身頃", "edge": "脇線 (右)", "rule": "midpoint_balance"},
    {"piece": "後身頃", "edge": "脇線 (左)", "rule": "midpoint_balance"},
]


def assemble(selections: Dict[str, str],
             library: Optional[_parts.Library] = None
             ) -> Dict[str, Any]:
    """選択から宣言を組み立てる。戻り値は verdict 付き。"""
    lib = library or _parts.Library()

    for family, key in selections.items():
        if family not in _parts.FAMILIES:
            return {
                "verdict": NO_SLOT,
                "why": f"{family} という家族(スロット)はライブラリに無い",
                "families": list(_parts.FAMILIES),
                "how_to_close": f"{family} の家族をライブラリに足すか、"
                                "既存の家族から選ぶ",
            }
        try:
            v = lib.variant(family, key)
        except ValueError:
            known = [x["key"] for x in lib.variants(family)]
            return {
                "verdict": NO_VARIANT,
                "why": f"{family}/{key} という候補は無い",
                "known": known,
                "how_to_close": "既知の候補から選ぶ",
            }
        if not v.get("draftable", False):
            return {
                "verdict": NOT_DRAFTABLE,
                "which": f'{family}/{key}',
                "why": v.get("why_not", "製図手続きが未登録"),
                # **黙って別の候補に読み替えない。**
                "alternatives": [x["key"] for x in lib.variants(family)
                                 if x.get("draftable")],
                "how_to_close": "draftable な候補を選ぶか、製図手続きを"
                                "登録する",
            }

    chosen: Dict[str, Dict[str, Any]] = {
        fam: lib.variant(fam, selections[fam])
        for fam in selections
    }
    sil = chosen["silhouette"]

    params: List[Tuple[str, float]] = list(_parts.SHARED_PARAMS)
    formulas: List[Tuple[str, str]] = []
    for v in chosen.values():
        params += [(k, float(val)) for k, val in v.get("params", [])]
        formulas += [(n, t) for n, t in v.get("formulas", [])]
    formulas = list(_parts.SHARED_FORMULAS) + formulas

    label_bits = [chosen[f]["label"] for f in
                  ("silhouette", "closure", "waist_finish") if f in chosen]
    decl: Dict[str, Any] = {
        "name": "skirt",
        "label": "スカート（" + "・".join(label_bits) + "）",
        "required": SKIRT_MEASURES,
        "pieces": [("前身頃", True), ("後身頃", True)],
        "params": [(k, v, None) for k, v in params],
        "formulas": formulas,
        "seams": [dict(s) for s in SKIRT_SEAMS],
        "placement": {
            "前身頃": ((0.0, 0.0, 12.0), "前は手前"),
            "後身頃": ((0.0, 0.0, -12.0), "後ろは奥"),
        },
        "settings": {
            "grain_angle_deg": (90.0, "たて地。中心線と平行"),
            "pins_policy": ("waist_extremes",
                            "ウエスト線の左右の端を吊る。肩の無い服は"
                            "肩で吊れない"),
            # 合印の方針も宣言として載せる。**式は marks 側の手続き**に
            # 名前で委ねる — 組立器は手続きを持たない。
            "notch_plan": ([dict(n) for n in SKIRT_NOTCH_PLAN],
                           "脇の中間に単合印。前後で対になる"),
        },
        # Block の ingest は知らない拡張。組立以降の段(製図)が読む。
        "kind": "skirt",
    }
    return {
        "verdict": "ANSWER",
        "declaration": decl,
        "chosen": {k: v["key"] for k, v in chosen.items()},
        "library_census": lib.census(),
    }
