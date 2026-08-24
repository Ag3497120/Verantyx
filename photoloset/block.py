# -*- coding: utf-8 -*-
"""Block — 服の種類の宣言。**立体十字に載る。**

目的は「服を増やすことが容易な構造」。そのために、いま1着分の知識が
製図・縫製の各ファイルに散らばっている状態をやめる:

- 必要な実測寸法 → ``garment_pattern.REQUIRED``
- 製図の定数と17の式 → ``garment_pattern`` のリテラル
- 縫い目(どの辺とどの辺を縫うか) → ``garment_sew.SEAMS``
- 初期配置 → ``garment_sew.PLACEMENT``

これらを **1つの宣言** に集め、立体十字ストアに載せる。製図エンジンは
宣言を読んで解釈する側になり、服を足す = 新しい宣言になる。

なぜ辞書でなく十字か:

- **容量が幾何である。** 1核は6腕×4面の24席。コートの定数は20個、
  式は17本で、4面の腕には載らない — 実際に子コアへ分れる(下の
  ``ingest``)。これは失敗でも設計判断でもなく、測定済みの容量則
  (ノードの識別能力は24、超えると到達不能 0/60)が要求すること。
  分れた先は辺(label="nest")で親子が結ばれ、店自身がどこに何を
  置いたかを持つ。
- **矛盾が割れて見える。** 同じ住所に違う値を二つ宣言したら、店は
  CONTESTED を返し、読む側は**どちらも使わない**。黙って後勝ち
  しない。
- **配置は答えを動かさない。** ``placement_check()`` が店じゅうを
  二つの決定的な順で歩いて、取り出しが格納順に依らないことを
  店自身が確かめる。

まだエンジン側にあるもの(正直に): 合印の釣り合い規則や袖山を解く
手順といった**手続き**は ``garment_marks`` / ``garment_pattern`` の中に
ある。この段階で移すのはデータ(宣言)。手続きまで一般化するのは、
2つ目のBlock(スカート)が抽象を証明する段です。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import cross as _cross


# ---------------------------------------------------------------------------
# コートの宣言。**ここにしかない情報は、ここから来なければならない。**
# 値は製図が実際に使う数そのもの。式の文字列は監査出力にそのまま乗る。
COAT_DECLARATION: Dict[str, Any] = {
    "name": "coat",
    "label": "三枚コート（前身頃・後身頃・袖）",
    "required": ("body_length", "chest", "shoulder"),
    "sleeve_required": ("sleeve_length",),
    # (名前, 必須か)。**袖だけ引けないことはある**ので optional を許す。
    "pieces": [("後身頃", True), ("前身頃", True), ("袖", False)],
    # 製図の定数。(鍵, 使う数, 監査出力に乗せる式)
    "params": [
        ("half_divisor",         4.0,  None),
        ("armhole_depth_div",    8.0,  None),
        ("armhole_depth_add",    6.5,  None),
        ("shoulder_drop_div",    10.0, None),
        ("neck_w_div",           12.0, None),
        ("neck_w_add",           1.5,  None),
        ("front_neck_add",       2.0,  None),
        ("back_neck_depth",      2.0,  None),
        ("shoulder_half_div",    2.0,  None),
        ("back_armhole_ctrl_dx", 1.0,  None),
        ("front_armhole_ctrl_dx", 1.6, None),
        ("armhole_ctrl_y_ratio", 0.55, None),
        ("cap_height_ratio",     0.78, None),
        ("cuff_div",             8.0,  None),
        ("cuff_add",             2.0,  None),
        ("ease_in_cm",           2.0,  None),
        ("cap_ctrl_x_ratio",     0.5,  None),
        ("cap_ctrl_y_ratio",     0.22, None),
        ("cap_solve_lo",         0.1,  None),
        ("cap_solve_iterations", 60.0, None),
    ],
    # 縫い目。**型紙の名前付き辺で書く。近さでは決めない。**
    # span は袖山が前後の袖ぐりに半分ずつ付くための刻み向きと範囲。
    # 向きは端点で決まる(袖ぐりは肩端→脇端、袖山は脇の下→肩→脇の下)。
    # どちらの半分を前にするかはこの道具が決めたことで、測ったものでは
    # ない(左右対称なので長さは変わらない)。
    "seams": [
        {"a": ("前身頃", "肩線"), "b": ("後身頃", "肩線")},
        {"a": ("前身頃", "脇線"), "b": ("後身頃", "脇線")},
        {"a": ("袖", "袖山"), "b": ("前身頃", "袖ぐり"), "span": (0.5, 0.0),
         "label": "袖/袖山(前半) ↔ 前身頃/袖ぐり"},
        {"a": ("袖", "袖山"), "b": ("後身頃", "袖ぐり"), "span": (0.5, 1.0),
         "label": "袖/袖山(後半) ↔ 後身頃/袖ぐり"},
        # **袖下線は袖自身の二辺を縫い合わせて筒にする。** 同じピースの
        # 中の縫い目なので a と b のピース名が同じになります。
        {"a": ("袖", "袖下線 (右)"), "b": ("袖", "袖下線 (左)"),
         "label": "袖/袖下線(右) ↔ 袖/袖下線(左)"},
    ],
    # 型紙を3次元に置く初期位置。**初期配置であって形ではない。**
    "placement": {
        "前身頃": ((0.0, 0.0, 12.0), "前は手前"),
        "後身頃": ((0.0, 0.0, -12.0), "後ろは奥"),
        "袖": ((34.0, 0.0, 0.0), "袖は横"),
    },
    "settings": {
        "grain_angle_deg": (90.0, "たて地。中心線と平行"),
        "pins_policy": ("front_only_hanging",
                        "吊るのは前身頃だけ。後ろは肩の縫い目を通して"
                        "ぶら下がる"),
        "ease_free_to_pitch": (True,
                               "袖山のいせ込みを脇の下側に入れない"
                               "(テーラリングの通説)"),
    },
}

#: 式の出力。**(名前, 文字列) を宣言順で。** 出力の並びは SVG の注記の
#: 順序まで含めて監査の対象なので、ここで固定する。i18n がこの文字列を
#: 翻訳する。
FORMULA_ORDER: List[Tuple[str, str]] = [
    ("身頃幅 (前後それぞれ)", "chest / 4"),
    ("袖ぐり深さ", "chest / 8 + 6.5"),
    ("肩線の下がり", "shoulder / 10"),
    ("衿ぐり幅 (前後共通)", "chest / 12 + 1.5"),
    ("前衿ぐり深さ", "chest / 12 + 2.0"),
    ("後衿ぐり深さ", "2.0（固定）"),
    ("袖山の高さ", "袖ぐり深さ × 0.78"),
    ("袖幅 (袖口側)", "chest / 8 + 2.0"),
    ("袖山の幅", "袖山の長さが「袖ぐりの合計 + いせ込み」になるよう解く"),
    ("いせ込み", "2.0cm（この道具の既定）"),
    ("肩先の位置 (x)", "shoulder / 2 ※ shoulder は肩幅の全長とみなす"),
    ("後袖ぐりの control 点 (x)", "身頃幅 − 1.0（固定）"),
    ("前袖ぐりの control 点 (x)",
     "身頃幅 − 1.6（固定） ※ 前後の袖ぐりの違いはこの 0.6cm だけ"),
    ("袖ぐりの control 点 (y)", "袖ぐり深さ × 0.55"),
    ("袖山の control 点 (x)", "袖山の幅 × 0.5"),
    ("袖山の control 点 (y)", "袖山の高さ × 0.22"),
    ("袖山の幅の解き方", "二分探索 60 回、範囲 (0.1, 袖ぐりの合計)"),
]


# ---------------------------------------------------------------------------
def _put_all(store: _cross.CrossStore, root: str, arm: str,
             items: List[Tuple[str, Any]], source: str) -> List[str]:
    """店の put_all への委譲(互換のための名前)。"""
    return store.put_all(root, arm, items, source)


def ingest(store: Optional[_cross.CrossStore] = None,
           decl: Dict[str, Any] = COAT_DECLARATION,
           formulas: List[Tuple[str, str]] = FORMULA_ORDER
           ) -> Tuple[_cross.CrossStore, str]:
    """宣言を十字に載せる。戻り値は (店, 根コアの名前)。"""
    st = store if store is not None else _cross.CrossStore()
    root = f"block:{decl['name']}"
    source = f"declaration:{decl['name']}"

    st.put(root, "pieces", "_label", decl["label"], source)
    for piece_name, required in decl["pieces"]:
        st.put(root, "pieces", piece_name,
               {"required": required}, source)

    for spot in decl["required"]:
        st.put(root, "measures", spot,
               {"required": True, "for": "draft"}, source)
    for spot in decl.get("sleeve_required", ()):
        st.put(root, "measures", spot,
               {"required": False, "for": "sleeve"}, source)

    seam_items: List[Tuple[str, Any]] = []
    for spec in decl["seams"]:
        key = spec.get("label") or f'{spec["a"]} ↔ {spec["b"]}'
        seam_items.append((key, spec))
    _put_all(st, root, "seams", seam_items, source)
    # **辺も結ぶ。** 縫い目は二枚の間の約束であって、一枚の上の
    # 項目ではない。面(仕様の全文)と辺(関係)を両方持つ。
    # 同じピースの中の縫い目(袖下線)は一枚の内側の話なので辺にはしない。
    for spec in decl["seams"]:
        key = spec.get("label") or f'{spec["a"]} ↔ {spec["b"]}'
        if spec["a"][0] != spec["b"][0]:
            st.link((root, "pieces", spec["a"][0]),
                    (root, "pieces", spec["b"][0]),
                    f"seam:{key}", value=key)

    settings: List[Tuple[str, Any]] = []
    for k, (v, basis) in decl["settings"].items():
        settings.append((k, {"value": v, "basis": basis}))
    for name, (xyz, why) in decl["placement"].items():
        settings.append((f"placement:{name}",
                         {"value": xyz, "basis": why}))
    _put_all(st, root, "settings", settings, source)

    _put_all(st, root, "params",
             [(k, {"value": v}) for k, v, _f in decl["params"]], source)
    _put_all(st, root, "rules", list(formulas), source)

    return st, root


class BlockView:
    """十字に載った Block を読む口。**書き口は ingest だけ。**

    エンジンが直接触るのはこのクラス。宣言の辞書を辿らせず必ず店の
    get を通す — 矛盾が割れたとき、読む側が黙ってどちらかを拾わない
    ための一本の扉です。
    """

    def __init__(self, store: _cross.CrossStore, root: str) -> None:
        self.store = store
        self.root = root

    # ---------------------------------------------------------- 巡回
    def _chain(self, arm: str) -> List[str]:
        """arm を持つ核を、nest 辺の鎖の順で列挙する。"""
        cores = [self.root]
        seen = {self.root}
        changed = True
        while changed:
            changed = False
            for e in self.store.edges:
                if e["label"] == "nest" and e["a"][0] in seen \
                        and e["b"][0] not in seen \
                        and self.store.cores.get(e["b"][0], {}).get(arm):
                    cores.append(e["b"][0])
                    seen.add(e["b"][0])
                    changed = True
        return cores

    def _ordered(self, arm: str) -> List[Dict[str, Any]]:
        """arm の全 facet を鎖の順で返す。**値が割れていたら落とす。**

        読む側が黙ってどちらかを拾うことがないように。同じ鍵の再掲で
        値が同じものは1件に数える(同じ絵を9回見ても1件)。"""
        out: List[Dict[str, Any]] = []
        seen: Dict[str, Dict[str, Any]] = {}
        for cname in self._chain(arm):
            for f in self.store.cores[cname][arm]:
                prev = seen.get(f["key"])
                if prev is not None:
                    if prev["value"] != f["value"]:
                        raise ValueError(
                            f'{_cross.CONTESTED_IN_CROSS}: {arm}/'
                            f'{f["key"]} の宣言が割れています '
                            f'({prev["source"]} / {f["source"]})。'
                            "正しい方だけを残してください")
                    continue
                seen[f["key"]] = f
                out.append(f)
        return out

    # ------------------------------------------------------------ 読み
    def label(self) -> str:
        return self.store.require(self.root, "pieces", "_label")

    def pieces(self, required_only: bool = False) -> List[str]:
        out = []
        for f in self._ordered("pieces"):
            if f["key"] == "_label":
                continue
            if required_only and not f["value"]["required"]:
                continue
            out.append(f["key"])
        return out

    def measures(self, required_only: bool = False) -> List[str]:
        out = []
        for f in self._ordered("measures"):
            if required_only and not f["value"]["required"]:
                continue
            out.append(f["key"])
        return out

    def required(self) -> Tuple[str, ...]:
        return tuple(self.measures(required_only=True))

    def sleeve_required(self) -> Tuple[str, ...]:
        return tuple(k for k in self.measures()
                     if k not in self.required())

    def param(self, key: str) -> float:
        for f in self._ordered("params"):
            if f["key"] == key:
                return f["value"]["value"]
        raise ValueError(f'{_cross.NOT_IN_CROSS}: params/{key} — '
                         "Block の宣言に足す")

    def formulas(self) -> Dict[str, str]:
        """式の出力。**宣言順を保つ**(注記の並びまで一致させる)。"""
        return {f["key"]: f["value"] for f in self._ordered("rules")}

    def seams(self) -> List[Dict[str, Any]]:
        return [f["value"] for f in self._ordered("seams")]

    def seam_edges(self) -> List[Dict[str, Any]]:
        """縫い目の**辺**(二枚の間の約束として結ばれたもの)。"""
        return self.store.edges_labeled("seam:")

    def placement(self) -> Dict[str, Tuple[float, float, float]]:
        out: Dict[str, Tuple[float, float, float]] = {}
        for f in self._ordered("settings"):
            if f["key"].startswith("placement:"):
                out[f["key"].split(":", 1)[1]] = f["value"]["value"]
        return out

    def setting(self, key: str) -> Any:
        for f in self._ordered("settings"):
            if f["key"] == key:
                return f["value"]["value"]
        raise ValueError(f'{_cross.NOT_IN_CROSS}: settings/{key} — '
                         "Block の宣言に足す")

    def dump(self) -> str:
        """提供データの正準形。**丸写し検収(round-trip)に使う。**"""
        import json
        return json.dumps({
            "label": self.label(),
            "required": self.required(),
            "sleeve_required": self.sleeve_required(),
            "pieces": self.pieces(),
            "params": {k: self.param(k)
                       for k, _v, _f in COAT_DECLARATION["params"]},
            "formulas": self.formulas(),
            "seams": self.seams(),
            "placement": self.placement(),
            "settings": {k: self.setting(k)
                         for k in COAT_DECLARATION["settings"]},
            "seam_edges": len(self.seam_edges()),
            "census": self.store.census(),
        }, ensure_ascii=False, sort_keys=True)


_CACHE: Dict[str, BlockView] = {}


def coat() -> BlockView:
    """コート Block。**モジュールで一つの店に載せ、皆そこから読む。**"""
    if "coat" not in _CACHE:
        st, root = ingest()
        _CACHE["coat"] = BlockView(st, root)
    return _CACHE["coat"]
