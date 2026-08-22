# -*- coding: utf-8 -*-
"""基準体・ゆとり・サイズ展開。**着せない。比べる。**

事前登録: experiments/garment/PREREG9_BODY.md

本当の着装は、型紙を裁って縫い、生地の重さと曲げ剛性で落とす計算である。
台帳には型紙が無く、`fabric/weight` は未取得のままである。この状態で
人台に巻きつけた絵を出せば、それは**生成された見た目**で、「こう着られる」
と読まれる。誰も知らないことを、立体の説得力で言うことになる。

代わりに比べる。**ゆとり = 服の周囲 − 体の周囲。** 算術であり、作り手が
実際に見る数字であり、布の挙動を一切主張しない。

人台は**寸法を比べる相手**であって、この服を着る人ではない。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

#: 基準体の寸法表(cm)。**日本工業規格の成人男子の目安**を出発点にした
#: 参照値で、この服を着る誰かを測ったものではない。
#: 出典を持たない数字を実測の顔で置かないため、必ず reference と明示する。
BODY_SIZES: Dict[str, Dict[str, float]] = {
    "S":  {"height": 165, "chest": 88,  "waist": 76, "shoulder": 43,
           "arm_length": 56},
    "M":  {"height": 170, "chest": 92,  "waist": 80, "shoulder": 44.5,
           "arm_length": 58},
    "L":  {"height": 175, "chest": 96,  "waist": 84, "shoulder": 46,
           "arm_length": 60},
    "XL": {"height": 180, "chest": 100, "waist": 88, "shoulder": 47.5,
           "arm_length": 62},
}

#: 服の寸法 → 比べる体の寸法。**対応が付かないものは比べない。**
COMPARE = {
    "chest": "chest",
    "waist": "waist",
    "shoulder": "shoulder",
    "sleeve_length": "arm_length",
}

#: 一段あたりの標準的な振り分け(cm)。**これは業界の目安であって、
#: この一着について誰かが決めたものではない。** 使ったことを必ず残す。
GRADE_STEP = {
    "chest": 4.0, "waist": 4.0, "shoulder": 1.5,
    "sleeve_length": 2.0, "body_length": 2.0,
    "hem_width": 4.0, "collar_height": 0.0,
    "cuff_width": 0.5, "pocket_position": 1.0,
}

NO_BASIS = "UNKNOWN_NO_BASIS"


def body(size: str) -> Dict[str, Any]:
    """基準体を返す。**これは着用者ではない。**"""
    if size not in BODY_SIZES:
        raise ValueError(
            f"UNKNOWN_SIZE: {size} は基準体の表にない "
            f"({'/'.join(BODY_SIZES)})")
    return {
        "verdict": "ANSWER",
        "size": size,
        "measurements": dict(BODY_SIZES[size]),
        "kind": "reference_body",
        "note": "寸法を比べる相手であって、この服を着る人ではありません。"
                "誰も観測していない体です",
    }


def ease(measures: Any, size: str) -> Dict[str, Any]:
    """ゆとり = 服 − 体。**引き算であって着装計算ではない。**

    どちらかが未取得ならゆとりも出ない。片方だけで出した差は、
    もう片方を勝手に決めたことになる。
    """
    ref = BODY_SIZES.get(size)
    if ref is None:
        raise ValueError(f"UNKNOWN_SIZE: {size} は基準体の表にない")

    sheet = measures.sheet() if measures is not None else {
        "measured": [], "derived": [], "open": []}
    have: Dict[str, Dict[str, Any]] = {}
    for row in sheet["measured"] + sheet["derived"]:
        have[row["spot"]] = row

    rows: List[Dict[str, Any]] = []
    for spot, body_spot in COMPARE.items():
        got = have.get(spot)
        if got is None:
            rows.append({"spot": spot, "state": NO_BASIS,
                         "body": ref[body_spot],
                         "how_to_close": f"{spot} を実測すればゆとりが出る"})
            continue
        value = float(got["value"])
        rows.append({
            "spot": spot,
            "garment": value,
            "body": ref[body_spot],
            # **負でも丸めない。** 入らない服は入らないと言う。
            "ease": round(value - ref[body_spot], 1),
            "unit": got.get("unit", "cm"),
            # 服の値が計算値なら、ゆとりも計算値の上に立っている。
            "from_derived": got.get("state") == "DERIVED",
            "state": "EASE",
        })
    tight = [r for r in rows if r.get("ease") is not None and r["ease"] < 0]
    return {
        "verdict": "ANSWER",
        "size": size,
        "rows": rows,
        "negative": [r["spot"] for r in tight],
        "counts": {"computed": sum(1 for r in rows if "ease" in r),
                   "no_basis": sum(1 for r in rows
                                   if r["state"] == NO_BASIS)},
        "not_a_fit_calculation":
            "これは引き算です。型紙による着装計算ではなく、生地の落ち方も"
            "着心地も計算していません。型紙と生地の物性が要ります。",
        "reference_body": "比べた体は基準体で、この服を着る人ではありません",
    }


def grade(measures: Any, base_size: str,
          sizes: Optional[List[str]] = None) -> Dict[str, Any]:
    """サイズ展開。**振り分けで出た寸法は実測ではない。**

    基準の実測は一つも変わらない。展開は読み出しであって書き込みでは
    ない — 何サイズ作っても台帳は同じ。
    """
    order = list(BODY_SIZES)
    if base_size not in order:
        raise ValueError(f"UNKNOWN_SIZE: {base_size} は基準体の表にない")
    wanted = sizes or order
    for s_ in wanted:
        if s_ not in order:
            raise ValueError(f"UNKNOWN_SIZE: {s_} は基準体の表にない")

    sheet = measures.sheet() if measures is not None else {
        "measured": [], "derived": [], "open": []}
    base_rows = {r["spot"]: r for r in sheet["measured"]}

    table: Dict[str, List[Dict[str, Any]]] = {}
    for s_ in wanted:
        steps = order.index(s_) - order.index(base_size)
        out: List[Dict[str, Any]] = []
        for spot, row in sorted(base_rows.items()):
            step = GRADE_STEP.get(spot)
            if step is None:
                out.append({"spot": spot, "state": NO_BASIS,
                            "how_to_close": f"{spot} の振り分け量が表に無い"})
                continue
            value = round(float(row["value"]) + step * steps, 1)
            out.append({
                "spot": spot, "name": row.get("name", spot),
                "value": value, "unit": row.get("unit", "cm"),
                # 基準サイズ以外は**派生**。実測欄には立てない。
                "state": "MEASURED" if steps == 0 else "GRADED",
                "from": (f"{base_size} の {row['value']}{row.get('unit','cm')}"
                         f" {'+' if steps >= 0 else '−'} "
                         f"{abs(step * steps)}" if steps else ""),
                "step": step,
            })
        table[s_] = out

    return {
        "verdict": "ANSWER",
        "base_size": base_size,
        "sizes": wanted,
        "table": table,
        "grade_step": dict(GRADE_STEP),
        "note": "GRADED は振り分けで出した寸法で、実測ではありません。"
                "振り分け量は業界の目安であって、この一着について誰かが"
                "決めたものではありません",
    }
