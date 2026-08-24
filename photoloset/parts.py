# -*- coding: utf-8 -*-
"""構成部品ライブラリ。**立体十字に載る。**

「知識がない服」を検索で埋める、の入口。服全体の宣言(Block)を丸ごと
書く代わりに、服を**スロット(部位役割)と候補(バリアント)に分け**、
1つのバリアントが「この傾向の服はこう縫う」の断片を持ちます。

- 断片は facet として十字に載る。**容量(4面/腕)と矛盾検出と配置不変性
  は店の幾何がそのまま効く** — 候補が割れたら CONTESTED で見え、
  黙ってどれかが選ばれることはない。
- ``draftable: False`` の候補は宣言だけ持つ。引けないものを引けるふりを
  しないために、組立器はそれを選ばせた時点で型付きで断る。
- 検索で得た「こう縫われているらしい」は、まずここへ **提案facet**
  (source=検索結果) として載り、人が採用して初めて宣言に使われる。
  採用前の断片が製図に入る道は無い — 台帳と同じ扉の一本化。

まだ少ないのは正直に言うと、家族(スロット)の数です。今あるのは
スカートの3家族5候補。衿・袖・前立ては、それぞれの製図手続きが
エンジン側に登録されてから家族として足す(手続きの無い候補は置かない)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import cross as _cross

ROOT = "parts"

#: 家族(スロット)。**1つの服は各家族から高々1つ选ぶ。**
FAMILIES: Tuple[str, ...] = ("silhouette", "closure", "waist_finish")

#: 部品語彙 — **解析(ビジョンモデル)とライブラリの共通語彙。**
#: 服の「種類」はここに無い。種類は組合せに付ける名前であって、
#: 能力は部品の側にある。モデルがこの外の部品を出すときは new_part
#: として隔離され、採用されて初めてライブラリの家族になる。
PART_VOCAB: Dict[str, str] = {
    "bodice": "上身頃。襟ぐり・袖ぐり・ウエストを持つ",
    "skirt_panel": "スカートの1枚。ウエストと裾を持つ",
    "cape": "肩掛け。襟ぐり(または首)と自由な裾を持つ",
    "sleeve": "袖。袖ぐりと袖口を持つ",
    "collar": "衿。襟ぐりに付く",
    "closure": "開き。前立て・ファスナー・紐など",
    "waist_finish": "ウエストの処理。ベルト・ゴム・サッシュ",
    "decoration": "装飾。リボン・レース・刺繍。**型紙の幾何には"
                  "入らない**(台帳とマーキングのみ)",
}

#: 接続口。部品どうしはここでしか繋がらない。**閉じた語彙。**
PORTS: Tuple[str, ...] = (
    "neck", "shoulder_l", "shoulder_r",
    "armhole_l", "armhole_r", "cuff_l", "cuff_r",
    "waist", "hem", "center_front", "center_back",
)

#: 部品の幾何手続きレジストリ。**名前 → garment_parts の関数。**
#: 手続きが無い部品は draftable にならない — 宣言だけの部品を
#: 引けると言わない。
PART_GEOMETRY: Dict[str, str] = {
    "bodice": "draft_bodice",
    "skirt_panel": "draft_skirt_panel",
    "sleeve": "draft_sleeve",
    "cape": "draft_cape",
    # collar / closure / waist_finish / decoration は手続き未登録。
    # decoration は幾何に入らない(語彙の定義どおり)。
}

#: 部品が要る実測。**接続で決まるもの(袖山の袖ぐり合計)は除く。**
PART_MEASURES: Dict[str, Tuple[str, ...]] = {
    "bodice": ("chest", "shoulder", "waist", "bodice_length"),
    "skirt_panel": ("waist", "hip", "skirt_length"),
    "sleeve": ("chest", "sleeve_length"),
    "cape": ("neck", "cape_length"),
}

#: バリアント宣言。値は組立器がそのまま使う形で持つ。
#:
#: draftable: False は「宣言はあるが製図手続きが無い」。嘘をつかせるより、
#: 選べた瞬間に why_not を添えて断るほうが誠実。
VARIANTS: List[Dict[str, Any]] = [
    # ---- silhouette ---------------------------------------------------
    {"family": "silhouette", "key": "Aライン",
     "label": "Aライン（裾に向かって広がる）",
     "draftable": True,
     "params": [("flare_ratio", 1.35)],
     "formulas": [
         ("裾幅", "ヒップ幅 × flare_ratio"),
         ("flare_ratio", "1.35（Aライン。**この道具が決めた値**で、"
                         "服飾の標準ではない）"),
     ]},
    {"family": "silhouette", "key": "ストレート",
     "label": "ストレート（裾はほぼ真っ直ぐ）",
     "draftable": True,
     "params": [("flare_ratio", 1.02)],
     "formulas": [
         ("裾幅", "ヒップ幅 × flare_ratio"),
         ("flare_ratio", "1.02（ストレート。**この道具が決めた値**)"),
     ]},
    # ---- closure --------------------------------------------------------
    {"family": "closure", "key": "ゴムウエスト（開き無し）",
     "label": "ゴムウエスト。前後とも中心線は折り(わ)",
     "draftable": True,
     "params": [],
     "formulas": []},
    {"family": "closure", "key": "後ろセンターファスナー",
     "label": "後ろ中心に開きを入れる",
     "draftable": False,
     "why_not": "ファスナー用の開き量と、開きを持つ縫い代の取り方は"
                "まだ引けない。宣言だけ載せてある",
     "params": [],
     "formulas": []},
    # ---- waist_finish ---------------------------------------------------
    {"family": "waist_finish", "key": "シャーリング",
     "label": "ウエストに楽を持たせてゴムに寄せる",
     "draftable": True,
     "params": [("waist_ease_per_panel", 2.0)],
     "formulas": [
         ("ウエストの楽", "1枚あたり +2.0cm。ゴムに寄せる分"
          "（**既定**。生地とゴムで変わる）"),
     ]},
]

#: スカート共通の定数(バリアント非依存)。
SHARED_PARAMS: List[Tuple[str, float]] = [
    ("hip_depth", 20.0),
    ("hip_ease", 2.0),
]
SHARED_FORMULAS: List[Tuple[str, str]] = [
    ("ウエスト幅 (1枚)", "waist / 2 + ウエストの楽"),
    ("ヒップ幅 (1枚)", "max(hip / 2 + ヒップの楽, ウエスト幅)"),
    ("ヒップの位置", "ウエストから hip_depth 下がったところ"),
    ("hip_depth", "20.0cm（**この道具の既定**。標準では約18-20cmと"
                  "されるが、出典を確認していない）"),
    ("ヒップの楽", "+2.0cm（**既定**）"),
    ("丈", "skirt_length の実測そのまま"),
]


def _variant(family: str, key: str) -> Optional[Dict[str, Any]]:
    for v in VARIANTS:
        if v["family"] == family and v["key"] == key:
            return v
    return None


def family_core(family: str) -> str:
    """家族は**主題**。「params」という棚ではない。"""
    return f"{ROOT}:{family}"


def ingest(store: Optional[_cross.CrossStore] = None
           ) -> Tuple[_cross.CrossStore, str]:
    """ライブラリを店に載せる。戻り値は (店, 根コアの名前)。

    **家族と候補は kind+ / kind- の双対そのもの。** 家族(シルエット、
    開き、ウエストの処理)は「この抽象がある」という一般構造の主張なので
    kind+、候補(Aライン、ストレート)は「その例がこれ」なので kind-。
    以前は両方 ``params`` という一つの引き出しに ``_family:x`` と
    ``x:y`` という鍵で入っていて、抽象と実例の区別は鍵の書き方の
    習慣でしかなかった。

    家族の主張は**出典1本**(このライブラリ自身)しか持たないので、
    ``store.unbought_generics()`` は3件を
    UNKNOWN_GENERIC_NOT_BOUGHT として挙げる。それが正直な読みです —
    「silhouette は服飾一般の家族である」と言うには、この道具が
    そう決めたという以上の根拠が要る。
    """
    st = store if store is not None else _cross.CrossStore()
    source = "library:builtin"
    st.put(ROOT, "library", {"name": "photoloset parts"}, "declared", source)
    for fam in FAMILIES:
        core = family_core(fam)
        st.put(core, "family", {"open": True}, "generic", source)
        st.link((core, ""), (ROOT, ""), "part_of")
    for v in VARIANTS:
        rec = {k: v[k] for k in ("family", "key", "label",
                                 "draftable") if k in v}
        if "why_not" in v:
            rec["why_not"] = v["why_not"]
        core = family_core(v["family"])
        if not st.has_core(core):
            st.put(core, "family", {"open": True}, "generic", source)
            st.link((core, ""), (ROOT, ""), "part_of")
        st.put(core, f'variant:{v["key"]}', {
            "variant": rec,
            "params": v.get("params", []),
            "formulas": v.get("formulas", []),
        }, "specific", source)
    return st, ROOT


# ---------------------------------------------------------------------------
# 提案の隔離席。**検索やモデルが見つけた候補は、ここに載り、
# 人が採用して初めてライブラリに入る。**
_PROPOSALS: List[Dict[str, Any]] = []


def propose_variant(family: str, key: str, spec: Dict[str, Any],
                    source: str) -> Dict[str, Any]:
    """候補を隔離席へ。**採用されるまで製図には使えない。**

    spec は VARIANTS と同じ形(label/draftable/params/formulas)。
    家族は語彙に在ること。無い家族の提案は new_part として別に載せる。
    """
    if family not in PART_VOCAB:
        return {"verdict": "UNKNOWN_UNKNOWN_PART", "which": family,
                "how_to_close": "語彙に家族として足すか、new_part で提案する"}
    dup = any(p["family"] == family and p["key"] == key
              for p in _PROPOSALS)
    if not dup:
        _PROPOSALS.append({"family": family, "key": key,
                           "spec": dict(spec), "source": source})
    return {"verdict": "ANSWER", "staged": True,
            "note": "採用されるまでライブラリには入りません",
            "proposals": len(_PROPOSALS)}


def list_proposals() -> List[Dict[str, Any]]:
    return [dict(p) for p in _PROPOSALS]


def adopt_proposal(family: str, key: str) -> Dict[str, Any]:
    """提案を採用してライブラリに載せる。**採用者の名前は source に。**"""
    prop = next((p for p in _PROPOSALS
                 if p["family"] == family and p["key"] == key), None)
    if prop is None:
        return {"verdict": "UNKNOWN_NO_SUCH_PROPOSAL",
                "how_to_close": "propose_variant で先に提案する"}
    spec = dict(prop["spec"])
    spec.setdefault("family", family)
    spec.setdefault("key", key)
    spec.setdefault("draftable", False)
    spec.setdefault("params", [])
    spec.setdefault("formulas", [])
    # 次に Library が立つとき(組み立てのたび)この候補が載る。
    # 既存の店には遡って載せない — 採用は未来に効く。
    VARIANTS.append(spec)
    _PROPOSALS.remove(prop)
    return {"verdict": "ANSWER", "adopted": f"{family}/{key}",
            "source": prop["source"],
            "draftable": spec["draftable"]}


class Library:
    """ライブラリを読む口。**必ず店の get を通す。**"""

    def __init__(self, store: Optional[_cross.CrossStore] = None) -> None:
        self.store = store or _cross.CrossStore()
        self.root = ROOT
        if not self.store.has_core(ROOT):
            ingest(self.store)

    def families(self) -> List[str]:
        """家族を**宣言順で**。並びは格納場所ではなく seq が決める。"""
        out = []
        for core in self.store.part_of_children(ROOT):
            for f in self.store.seats(core, "family"):
                out.append((f["seq"], core.split(":", 1)[1]))
        out.sort()
        return [name for _seq, name in out]

    def variants(self, family: str) -> List[Dict[str, Any]]:
        core = family_core(family)
        if not self.store.has_core(core):
            return []
        out = []
        for f in self.store.seats(core, "variant:"):
            if f["verdict"] != "ANSWER":
                continue
            rec = dict(f["value"]["variant"])
            rec["params"] = f["value"]["params"]
            rec["formulas"] = f["value"]["formulas"]
            out.append(rec)
        return out

    def variant(self, family: str, key: str) -> Dict[str, Any]:
        for v in self.variants(family):
            if v["key"] == key:
                return v
        raise ValueError(
            f"{_cross.NOT_IN_CROSS}: {family}/{key} という候補は"
            "ライブラリに無い")

    def census(self) -> Dict[str, Any]:
        return self.store.census()

    def unbought_generics(self) -> List[Dict[str, Any]]:
        """**出典が2本無い一般構造の主張。** 家族の主張がここに出る。"""
        return self.store.unbought_generics()
