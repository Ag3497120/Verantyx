# -*- coding: utf-8 -*-
"""ゾーン — 服の調整点に番号を振り、差分で再製図できるようにする。

エージェントループの受け皿。「ここにもう少しゆとりを」を言葉でなく
番号と量で受ける:

    adjustments = {"2": 1.5, "6-9": -1.0}     # 2番に+1.5cm、6〜9番に-1cm

規律:

- **番号は決定的。** 同じ部品グラフなら毎回同じ番号が振られる
  (インスタンス名順 → 部品のカタログ順)。だから「30〜35」が次の
  周回で別の場所を指すことはない
- **番号が指すのは設計パラメータだけ。** 実測寸法は書き換えない —
  ゆとりの追加は設計の側の変更であって、測った数値は動かない
- **適用は記録される。** 何番が・いくつからいくつに変わったかを
  applied に出す。黙って変わったふりをしない
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from . import parts as _parts

#: 部品ごとの調整点カタログ(順序が番号の順)。**手続きが実際に読む
#: パラメータだけを載せる** — カタログに在るのに効かない項目は、
#: 番号の捏造です。
ZONE_CATALOG: Dict[str, List[Dict[str, str]]] = {
    "bodice": [
        {"param": "chest_ease", "label": "胸のゆとり"},
        {"param": "waist_ease", "label": "ウエストの楽"},
        {"param": "armhole_depth_add", "label": "袖ぐり深さの追加"},
    ],
    "cape": [
        {"param": "sector", "label": "扇の開き"},
    ],
    "collar": [
        {"param": "sector", "label": "扇の開き"},
        {"param": "collar_height", "label": "衿の高さ"},
    ],
    "skirt_panel": [
        {"param": "waist_ease", "label": "ウエストの楽"},
        {"param": "hip_ease", "label": "ヒップの楽"},
        {"param": "flare_ratio", "label": "フレアの割合"},
        {"param": "hi_lo_drop", "label": "ハイローの落ち差"},
    ],
    "sleeve": [
        {"param": "ease_in", "label": "袖山のいせ"},
        {"param": "cuff_add", "label": "袖口の広さ"},
    ],
}

NO_ZONE = "UNKNOWN_NO_SUCH_ZONE"


def catalog(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """部品グラフに番号を振る。**決定的**(インスタンス名順・カタログ順)。"""
    out: List[Dict[str, Any]] = []
    n = 0
    for inst in sorted(graph.get("parts") or [],
                       key=lambda i: i.get("instance", "")):
        part = inst.get("part", "")
        params = dict(inst.get("params") or {})
        for entry in ZONE_CATALOG.get(part, []):
            n += 1
            out.append({
                "id": n,
                "instance": inst.get("instance"),
                "part": part,
                "param": entry["param"],
                "label": entry["label"],
                "current": params.get(entry["param"]),
                # current が None は「手続きの既定を使っている」。
                # 調整が効くのは明示した値。
            })
    return out


def parse_selection(selection: str, zones: List[Dict[str, Any]]
                    ) -> Tuple[List[int], Optional[Dict[str, Any]]]:
    """``"2"`` / ``"6-9"`` / ``"1,3,5"`` を番号のリストに。"""
    valid = {z["id"] for z in zones}
    ids: List[int] = []
    for token in selection.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            lo_hi = token.split("-", 1)
            try:
                lo, hi = int(lo_hi[0]), int(lo_hi[1])
            except ValueError:
                return [], {"verdict": "UNKNOWN_BAD_ARGUMENTS",
                            "why": f"範囲は 数字-数字: {token}"}
            ids += list(range(lo, hi + 1))
        else:
            try:
                ids.append(int(token))
            except ValueError:
                return [], {"verdict": "UNKNOWN_BAD_ARGUMENTS",
                            "why": f"番号は整数: {token}"}
    unknown = [i for i in ids if i not in valid]
    if unknown:
        return [], {"verdict": NO_ZONE,
                    "which": unknown,
                    "valid": f"1-{max(valid)}" if valid else "無し",
                    "how_to_close": "catalog にある番号から選ぶ"}
    return sorted(set(ids)), None


def apply(graph: Dict[str, Any],
          adjustments: Dict[str, float]) -> Dict[str, Any]:
    """番号と差分から、**新しい部品グラフ**を作る。元は壊さない。

    戻り値に applied(何番が・いくつからいくつに)と graph' を載せる。
    再製図は呼び側が compose に graph' を渡して行う。
    """
    zones = catalog(graph)
    applied: List[Dict[str, Any]] = []
    import copy
    new_graph = copy.deepcopy(graph)
    by_instance: Dict[str, Dict[str, Any]] = {
        i.get("instance"): i for i in new_graph.get("parts") or []}

    for key, delta in adjustments.items():
        ids, err = parse_selection(str(key), zones)
        if err is not None:
            return err
        for zid in ids:
            z = next(z for z in zones if z["id"] == zid)
            inst = by_instance[z["instance"]]
            params = inst.setdefault("params", {})
            old = params.get(z["param"])
            base = 0.0 if old is None else float(old)
            params[z["param"]] = base + float(delta)
            applied.append({
                "id": zid, "instance": z["instance"], "part": z["part"],
                "param": z["param"], "label": z["label"],
                "was": old if old is not None else "既定",
                "delta": float(delta),
                "now": params[z["param"]],
            })

    applied.sort(key=lambda a: a["id"])
    return {"verdict": "ANSWER", "applied": applied, "graph": new_graph,
            "zones": catalog(new_graph),
            "note": "実測寸法は動いていません。変わったのは設計パラメータです"}
