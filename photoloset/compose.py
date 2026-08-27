# -*- coding: utf-8 -*-
"""組立て — 部品グラフから1着の型紙を作る。**種類は名前に過ぎない。**

入力は部品インスタンスと接続のリスト:

    {"parts": [{"instance": "bodice:1", "part": "bodice"},
               {"instance": "sleeve:1", "part": "sleeve",
                "params": {"side": "左"}}, ...],
     "connections": [{"a": ["bodice:1", "waist"],
                      "b": ["skirt_panel:1", "waist"]}, ...],
     "label": "ケープワンピース",          # **名前。能力ではない**
     "port_finish": {"cape:1": {"hem": "free"}}}

門(全部型付き):

- 知らない部品/接続口 → ``UNKNOWN_NO_SUCH_PART`` / ``UNKNOWN_UNKNOWN_PORT``
- 同じ接続口の二重予約 → ``UNKNOWN_PORT_DOUBLE_BOOKED``
- 繋がっておらず、処理の指定も無い口 → ``UNKNOWN_OPEN_PORT``
  (**背面が見えない、の技術的な顔**。候補を出して人に選ばせる)

接続の検査は既存の縫い合わせ検査と同じく**差を出す**ことで、
合っていると主張しない。袖の袖山は接続先(上身頃)の袖ぐり合計から
解かれる — 部品は単独では完結しない。服だから。
"""
from __future__ import annotations

import json as _json
from typing import Any, Dict, List, Optional, Tuple

from . import garment_parts as _geom
from . import parts as _parts

NO_PART = "UNKNOWN_NO_SUCH_PART"
NO_PORT = "UNKNOWN_UNKNOWN_PORT"
DOUBLE = "UNKNOWN_PORT_DOUBLE_BOOKED"
OPEN_PORT = "UNKNOWN_OPEN_PORT"

#: 部品ごとの初期配置。**接続点どうしが初期で重なるように**上身頃丈から
#: 動的に出す。固定のオフセットだと、ウエストの縫い目が重力に逆らう
#: 初期ギャップを背負い、いつまでも閉じない(2026-08-24 実測)。
PLACEMENT_TEMPLATE: Dict[str, Tuple[float, float, float]] = {
    "ケープ": (0.0, 6.0, 24.0),
    "前身頃": (0.0, 0.0, 12.0),
    "後身頃": (0.0, 0.0, -12.0),
    # 半身は +x 側を描く(わ裁ち)。袖も同じ側に置く。
    "袖(左)": (34.0, 0.0, 0.0),
    "袖(右)": (34.0, 0.0, 0.0),
    # 衿は前身頃/後身頃のように前後で別インスタンスに分かれない
    # (1枚のケープと同じ弧の骨格、片側の port が前後両方の辺を持つ) —
    # だから z は「前(12)と後(-12)のどちらにも同じだけ近い」対称点、
    # 0.0 を明示で選ぶ。y=0.0 は上身頃自身の原点(neck_depth の頂点、
    # 襟ぐりの上端)と揃え、初期位置を襟ぐりの高さに合わせる。x=0.0 は
    # 他の中心部品(前後身頃)と同じ。**この3値は前のバージョンでは
    # このテーブルに無く、`placement_map.get(name, (0.0,0.0,0.0))` の
    # 無言既定に落ちていた** — 数値としては同じ (0.0,0.0,0.0) だが、
    # 意図して選んだと分かるように明示する。数値を変えれば衿の初期位置
    # だけが動く(drape は反復で辻褄を合わせるので、最終形は大きくは
    # 動かない見込みだが、確かめずに断定はしない)。
    "衿": (0.0, 0.0, 0.0),
}


def _placements(bodice_length: float) -> Dict[str, Tuple[float, float, float]]:
    out = dict(PLACEMENT_TEMPLATE)
    out["スカート前"] = (0.0, -bodice_length, 12.0)
    out["スカート後"] = (0.0, -bodice_length, -12.0)
    return out


def _procedure(part: str):
    name = _parts.PART_GEOMETRY.get(part)
    if name is None:
        return None
    return getattr(_geom, name, None)


def _port_edges(part_out: Dict[str, Any]) -> Dict[Tuple[str, str], str]:
    """(piece名, port) → 辺名 の逆引き表。"""
    m: Dict[Tuple[str, str], str] = {}
    for p in part_out["pieces"]:
        for port, edge in p.get("ports", {}).items():
            m[(p["name"], port)] = edge
    return m


def compose(graph: Dict[str, Any], measures: Any,
            measures_get: Optional[Any] = None) -> Dict[str, Any]:
    """部品グラフを検証し、1着分の draft_out を組み立てる。

    measures_get(spot) は実測値を返す呼び出し(欠けは例外)。テストと
    アプリの両方から同じ門を通すために外から渡せるようにしてある。
    """
    instances = graph.get("parts") or []
    connections = graph.get("connections") or []
    label = graph.get("label") or ""
    port_finish = graph.get("port_finish") or {}

    # ---- 門1: 部品は知っているものか --------------------------------
    for inst in instances:
        part = inst.get("part")
        if part not in _parts.PART_VOCAB or part not in _parts.PART_GEOMETRY:
            known = sorted(_parts.PART_GEOMETRY)
            return {"verdict": NO_PART,
                    "which": part,
                    "known": known,
                    "how_to_close": f"手続きのある部品から選ぶ: {known}"}
        if _procedure(part) is None:
            return {"verdict": "UNKNOWN_PART_NOT_DRAFTABLE",
                    "which": part,
                    "how_to_close": "garment_parts に手続きを登録する"}

    # ---- 門2: 接続口は語彙か ----------------------------------------
    for c in connections:
        for end in (c.get("a"), c.get("b")):
            if not end or len(end) != 2:
                return {"verdict": "UNKNOWN_BAD_ARGUMENTS",
                        "why": f"接続の端は [instance, port]: {end}"}
            owner = next((i for i in instances
                          if i.get("instance") == end[0]), None)
            if owner is None:
                return {"verdict": NO_PART, "which": end[0],
                        "how_to_close": "parts にあるインスタンスを指す"}
            if end[1] not in _parts.PORTS:
                return {"verdict": NO_PORT, "which": end[1],
                        "how_to_close":
                            f"接続口は {'/'.join(_parts.PORTS)} のみ"}

    # ---- 門3: 二重予約 ----------------------------------------------
    used: Dict[Tuple[str, str], str] = {}
    for c in connections:
        for end in (c.get("a"), c.get("b")):
            key = (end[0], end[1])
            if key in used:
                return {"verdict": DOUBLE,
                        "which": list(key),
                        "first": used[key],
                        "how_to_close": "1つの口は1本にしか繋げない"}
            used[key] = c.get("label") or f'{c["a"]} ↔ {c["b"]}'

    # ---- 製図。袖は接続先の袖ぐり合計を要る --------------------------
    def mget(spot: str) -> float:
        if measures_get is not None:
            return float(measures_get(spot))
        raise ValueError(f"UNKNOWN_MISSING_MEASUREMENTS: {spot}")

    if measures_get is None and measures is not None:
        from .garment_pattern import TO_CM as _TO_CM
        sheet = measures.sheet()
        table: Dict[str, float] = {}
        for row in sheet["measured"] + sheet["derived"]:
            unit = (row.get("unit") or "").strip().lower()
            k = _TO_CM.get(unit)
            if k is not None:
                table[row["spot"]] = float(row["value"]) * k
        measures_get = table.get

        def mget(spot: str) -> float:
            if spot in table:
                return table[spot]
            raise ValueError(f"UNKNOWN_MISSING_MEASUREMENTS: {spot}")

    drafted: Dict[str, Dict[str, Any]] = {}
    formulas: List[Tuple[str, str]] = []
    for inst in instances:
        iid, part = inst["instance"], inst["part"]
        params = dict(inst.get("params") or {})
        need = _parts.PART_MEASURES.get(part, ())
        missing = []
        for spot in need:
            try:
                mget(spot)
            except ValueError:
                missing.append(spot)
        if missing:
            return {"verdict": "UNKNOWN_MISSING_MEASUREMENTS",
                    "missing": missing, "for": iid,
                    "how_to_close": "、".join(missing) + " を実測すれば引ける"}
        if part == "sleeve":
            # **袖山は接続先の袖ぐりから。** まだ接続が解決していない
            # ので、armhole への接続を探して先に上身頃を引く。
            arm_total = _armhole_total_for(iid, connections, instances,
                                           drafted, mget, params)
            if arm_total is None:
                return {"verdict": OPEN_PORT,
                        "which": [f"{iid}:armhole"],
                        "how_to_close": "袖は上身頃の袖ぐりに繋ぐ。"
                                        "接続を先に決める"}
            out = _geom.draft_sleeve(mget, params, arm_total)
        else:
            out = _procedure(part)(mget, params)
        drafted[iid] = out
        formulas += out.get("formulas", [])

    # ---- 門4: 開いた接続口 ------------------------------------------
    open_ports: List[Dict[str, Any]] = []
    for inst in instances:
        iid = inst["instance"]
        for p in drafted[iid]["pieces"]:
            for port in p.get("ports", {}):
                if (iid, port) in used:
                    continue
                finish = (port_finish.get(iid) or {}).get(port)
                if finish is None:
                    open_ports.append({
                        "instance": iid, "port": port,
                        "piece": p["name"],
                        "how_to_close": "接続するか、port_finish で "
                                        "わ(fold)か 端処理(free) を決める"})
    if open_ports:
        return {"verdict": OPEN_PORT, "open": open_ports,
                "why": "繋がっておらず、処理も決まっていない口があります。"
                       "黙って閉じた服に見せません"}

    # ---- 結合。pieces はインスタンスで一意になるよう改名 --------------
    pieces: List[Dict[str, Any]] = []
    seam_specs: List[Dict[str, Any]] = []
    rename: Dict[str, str] = {}
    for inst in instances:
        iid = inst["instance"]
        for p in drafted[iid]["pieces"]:
            new_name = p["name"] if p["name"] not in rename else \
                f'{p["name"]}·{iid}'
            rename[p["name"]] = new_name
            np = dict(p)
            np["name"] = new_name
            np["instance"] = iid
            pieces.append(np)
        for s in drafted[iid].get("seams", []):
            seam_specs.append({
                "a": (rename.get(s["a"][0], s["a"][0]), s["a"][1]),
                "b": (rename.get(s["b"][0], s["b"][0]), s["b"][1]),
                "label": s.get("label", f'{s["a"]} ↔ {s["b"]}'),
            })

    # ---- 門5: 縫い目は実在する辺を指す ------------------------------
    # 部品の手続きが改名後のピース名と食い違っていたら、黙って別の辺を
    # 縫うより、ここで断る(2026-08-24 実測: スカートの脇線が改名前の
    # 名前のまま上身頃の脇線と衝突し、縫い目が0本になる事故)。
    by_name_early = {p["name"]: p for p in pieces}
    for s in seam_specs:
        for end in (s["a"], s["b"]):
            p = by_name_early.get(end[0])
            if p is None or end[1] not in p["edges"]:
                return {"verdict": "UNKNOWN_SEAM_EDGE_MISSING",
                        "which": f"{end[0]}/{end[1]}",
                        "how_to_close": "部品手続きの seams を実名に直す"}

    # ---- 接続の縫い目 + 検査(**差を出す**) ---------------------------
    checks: List[Dict[str, Any]] = []
    by_name = {p["name"]: p for p in pieces}
    for c in connections:
        (ia, pa), (ib, pb) = c["a"], c["b"]
        # **わ裁ちの半身では、同じ port が前後の2枚(または1枚の前後弧)
        # に載る。** 両側の一致する辺を全部集め、決定的な順で zip して
        # ペアを作る。1対だけ縫んで残りを黙って捨てない — それが
        # 「縫い目が足りず閉じない」事故の形だった(2026-08-24 実測)。
        edges_a: List[Tuple[str, str]] = []
        edges_b: List[Tuple[str, str]] = []
        for p in pieces:
            ports = p.get("ports", {})
            if p.get("instance") == ia:
                ev = ports.get(pa)
                for e in ([ev] if isinstance(ev, str) else list(ev or [])):
                    edges_a.append((p["name"], e))
            if p.get("instance") == ib:
                ev = ports.get(pb)
                for e in ([ev] if isinstance(ev, str) else list(ev or [])):
                    edges_b.append((p["name"], e))
        if not edges_a or not edges_b:
            continue
        edges_a.sort()
        edges_b.sort()
        many = len(edges_a) > 1 or len(edges_b) > 1
        for ea, eb in zip(edges_a, edges_b):
            seam_specs.append({
                "a": ea, "b": eb,
                "label": (c.get("label") or f"{pa}: {ia} ↔ {ib}")
                         + (f" ({ea[0]}↔{eb[0]})" if many else "")})
            la = by_name[ea[0]]["edges"][ea[1]]["length"]
            lb = by_name[eb[0]]["edges"][eb[1]]["length"]
            diff = round(la - lb, 2)
            checks.append({
                "label": seam_specs[-1]["label"],
                "a": f"{ea[0]}/{ea[1]}", "b": f"{eb[0]}/{eb[1]}",
                "length_a": la, "length_b": lb, "difference": diff,
                "tolerance": 2.0,
                "sewable": abs(diff) <= 2.0,
                "structural": False,
                "why": "接続する辺の長さ差。**差が出るのが普通** — "
                       "ギャザーの分だけ長い側が寄る",
            })
    # 部品内の縫い目も検査に載せる。**点を比べて structural を自動判定**
    # する(コートと同じ規律。決め打ちの札ではない)。
    seen_labels = {c["label"] for c in checks}
    for s in seam_specs:
        if s.get("label") in seen_labels:
            continue
        ra = by_name.get(s["a"][0], {}).get("edges", {}).get(s["a"][1])
        rb = by_name.get(s["b"][0], {}).get("edges", {}).get(s["b"][1])
        if ra is None or rb is None:
            continue
        same = ra["points"] == rb["points"]
        diff = round(ra["length"] - rb["length"], 2)
        checks.append({
            "label": s.get("label", f'{s["a"]} ↔ {s["b"]}'),
            "a": f'{s["a"][0]}/{s["a"][1]}',
            "b": f'{s["b"][0]}/{s["b"][1]}',
            "length_a": ra["length"], "length_b": rb["length"],
            "difference": diff, "tolerance": 0.3,
            "sewable": abs(diff) <= 0.3,
            "structural": same,
            "not_a_test": ("同じ点から引いているので差は構成上ゼロです"
                           if same else None),
            "why": "縫い合わせる辺の長さ差",
        })

    from . import zones as _zones
    return {
        "verdict": "ANSWER",
        "label": label,
        # **調整点の番号表。** エージェントループはこの番号で差分を
        # 指定する。番号は決定的(インスタンス名順・カタログ順)。
        "zones": _zones.catalog(graph),
        "kind_note": ("種類名はこの組合せのラベルです。能力は部品の側に"
                      "あります" if label else ""),
        "pieces": pieces,
        "seam_checks": checks,
        "seam_specs": seam_specs,
        "placement": _placements(
            float(measures_get("bodice_length"))
            if any(i.get("part") in ("skirt_panel",) for i in instances)
            else 0.0),
        "settings": {"pins_policy": "shoulder_front_only",
                     "grain_angle_deg": 90.0},
        "notch_plan": [],          # 合印の方針は次の段で宣言ごとに足す
        "formulas": dict(formulas),
        "used": {},
        "units": {"converted_to": "cm"},
        "seam_allowance":
            "縫い代は入っていません。引いたのは出来上がり線です。",
        "not_a_published_system":
            "これはこの道具の簡易製図です。式は全て出しています。",
        "note": "部品の組合せから組み立てました。種類の登録はありません",
    }


def _armhole_total_for(iid: str, connections, instances, drafted,
                       mget, params) -> Optional[float]:
    """袖インスタンスの袖ぐり合計。接続から接続先を辿って合計する。"""
    total = 0.0
    found = False
    for c in connections:
        for end, other in ((c.get("a"), c.get("b")),
                           (c.get("b"), c.get("a"))):
            if end and end[0] == iid and end[1] in ("armhole_l", "armhole_r"):
                owner_iid, owner_port = other[0], other[1]
                src = drafted.get(owner_iid)
                if src is None:
                    src = _procedure(_part_of(instances, owner_iid))(
                        mget, dict(_params_of(instances, owner_iid)))
                    drafted[owner_iid] = src
                for p in src["pieces"]:
                    edge = p.get("ports", {}).get(owner_port)
                    if edge:
                        total += p["edges"][edge]["length"]
                        found = True
    return total if found else None


def _part_of(instances, iid: str) -> str:
    for i in instances:
        if i.get("instance") == iid:
            return i.get("part")
    return ""


def _params_of(instances, iid: str) -> Dict[str, Any]:
    for i in instances:
        if i.get("instance") == iid:
            return dict(i.get("params") or {})
    return {}


# ---------------------------------------------------------------------------
# 検索で得た構造 → 部品グラフ。**画素からではない。**
# ---------------------------------------------------------------------------

CONTESTED_STRUCTURE = "UNKNOWN_CONTESTED_STRUCTURE"
NOT_DRAFTABLE = "UNKNOWN_PART_NOT_DRAFTABLE"


def _catalog_rank(part: Any) -> Tuple[int, str]:
    """部品語彙の宣言順。**番号を決めるのは語彙であって入力順ではない。**"""
    names = list(_parts.PART_VOCAB)
    name = str(part or "")
    return (names.index(name) if name in names else len(names), name)


def _shape_key(rec: Dict[str, Any]) -> str:
    """インスタンス名を**除いた**中身の正準形。同じ中身は同じ鍵。"""
    body = {k: v for k, v in rec.items()
            if k not in ("instance", "sources", "refs")}
    try:
        return _json.dumps(body, ensure_ascii=False, sort_keys=True,
                           default=repr)
    except (TypeError, ValueError):
        return repr(sorted(body.items(), key=lambda kv: str(kv[0])))


def graph_from(structure: Dict[str, Any]) -> Dict[str, Any]:
    """検索で得た構造を部品グラフにする。**引けない部品があれば全部断る。**

    入力は ``resemble.structure_from()`` の形:
    ``{"instances": [{"instance", "part", "family", "variant", "params"}],
    "connections": [...], "port_finish": {...}, "label": ...}``。

    **引ける部分だけ作らない。** ケープが黙って落ちた服は、検索が指した
    服とは別の服で、その別の服に対して人が承認を出してしまう。承認は
    次段(縫い方の検索)の門を開ける鍵なので、間違った服の鍵になる。だから
    語彙に無い部品と手続きの無い部品を**全部並べて**断る。

    **番号は入力順に依らない。** インスタンス名は (語彙の宣言順, 中身の
    正準形) で並べてから振るので、同じ集合なら並べ替えても同じ名前が
    付く — 次の周回で「3番」が別の場所を指さない。
    """
    if not isinstance(structure, dict):
        return {"verdict": "UNKNOWN_BAD_ARGUMENTS",
                "why": "構造は instances を持つ辞書です"}
    records = [dict(r) for r in (structure.get("instances")
                                 or structure.get("parts") or [])
               if isinstance(r, dict)]
    if not records:
        return {"verdict": "UNKNOWN_EMPTY_STRUCTURE",
                "how_to_close": "検索が部品を1つも指していない。"
                                "先に per_part で部品ごとに聞く"}

    # ---- 門0: 割れている構造は建てない ------------------------------
    contested = list(structure.get("contested") or [])
    if contested:
        return {"verdict": CONTESTED_STRUCTURE,
                "which": contested,
                "why": "同じ部品の同じ側面に別々の値が来ている。"
                       "どちらかを選んで建てると、選んだことが記録に"
                       "残らないまま承認を集めます",
                "how_to_close": "割れた側面を人が裁定してから建てる"}

    # ---- 門1: 語彙と手続き。**部分的には作らない** -------------------
    unknown = sorted({str(r.get("part")) for r in records
                      if str(r.get("part")) not in _parts.PART_VOCAB})
    undraftable = sorted({str(r.get("part")) for r in records
                          if str(r.get("part")) in _parts.PART_VOCAB
                          and (str(r.get("part")) not in _parts.PART_GEOMETRY
                               or _procedure(str(r.get("part"))) is None)})
    if unknown or undraftable:
        known = sorted(_parts.PART_GEOMETRY)
        return {"verdict": NO_PART if unknown else NOT_DRAFTABLE,
                "which": unknown + undraftable,
                "unknown": unknown,
                "undraftable": undraftable,
                "known": known,
                "asked_for": sorted({str(r.get("part")) for r in records}),
                "why": "引ける部品だけで建てると、検索が指した服とは"
                       "別の服に承認が出ます",
                "how_to_close":
                    "unknown の部品は parts.PART_VOCAB に足すか new_part "
                    "として提案する。undraftable の部品は garment_parts に"
                    "手続きを書き、parts.PART_GEOMETRY に登録する。"
                    "いま引けるのは known にある部品だけです"}

    # ---- 番号を振る。**決定的** --------------------------------------
    ordered = sorted(records, key=lambda r: (_catalog_rank(r.get("part")),
                                             _shape_key(r)))
    renamed: Dict[str, str] = {}
    seen: Dict[str, int] = {}
    instances: List[Dict[str, Any]] = []
    for rec in ordered:
        part = str(rec.get("part"))
        seen[part] = seen.get(part, 0) + 1
        iid = f"{part}:{seen[part]}"
        old = str(rec.get("instance") or iid)
        renamed[old] = iid
        params = dict(rec.get("params") or {})
        if rec.get("variant"):
            params.setdefault("variant", rec["variant"])
        inst: Dict[str, Any] = {"instance": iid, "part": part}
        if params:
            inst["params"] = params
        instances.append(inst)

    def _end(end: Any) -> Any:
        if isinstance(end, (list, tuple)) and len(end) == 2:
            return [renamed.get(str(end[0]), str(end[0])), end[1]]
        return end

    connections = [{**c, "a": _end(c.get("a")), "b": _end(c.get("b"))}
                   for c in (structure.get("connections") or [])
                   if isinstance(c, dict)]
    port_finish = {renamed.get(str(k), str(k)): v
                   for k, v in (structure.get("port_finish") or {}).items()}

    return {"verdict": "ANSWER",
            "graph": {"parts": instances,
                      "connections": connections,
                      "port_finish": port_finish,
                      "label": structure.get("label") or ""},
            "named": [i["instance"] for i in instances],
            "renamed": renamed,
            "from": "検索で得た構造。画素からではありません",
            "note": "名前は (語彙の宣言順, 中身) で決まります。"
                    "入力の並びは番号に入りません"}
