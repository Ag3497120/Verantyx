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

- **核は主題で、引き出しではない。** ``block:coat`` と
  ``block:coat/piece:袖`` は別の主題。形を持ち、要る寸法を持ち、
  置き場所を持ち、他の一枚と縫い合う — 主題とはそういうもので、
  「params」や「settings」は主題ではなく棚の名前です。
- **腕は主張の種別が決める。** 宣言の各行は「どういう主張か」
  (declared / specific / derived / input / cited / measured / generic)
  を言い、腕はそこから導かれる。書く側は腕を選べない。
- **空の腕が型付きの欠落になる。** コートの20個の定数は**全部**
  この道具が決めたもの(specific)で、実測に支えられたものも、文献を
  引いたものも、一般構造だと言えるものも**一つも無い**。だから
  ``block:coat`` の support+ 腕と kind+ 腕は空で、``gaps()`` は
  UNKNOWN_NO_SUPPORT_RECORDED と UNKNOWN_NO_GENERALIZATION_RECORDED
  を返す。これはコメントに散文で書いてあったこと
  (「**この道具が決めた値**で、服飾の標準ではない」)が、初めて
  **問える住所を持った**という意味です。
- **容量が幾何である。** 1核は6腕×4面の24席。コートの kind- の主張は
  根だけで17件あるので、実際に子コアへ分れる。これは失敗でも設計判断
  でもなく、測定済みの容量則(ノードの識別能力は24、超えると到達不能
  0/60)が要求すること。
- **矛盾が割れて見える。** 同じ住所に違う値を二つ宣言したら、店は
  CONTESTED を返し、読む側は**どちらも使わない**。分れた子コアに
  落ちても見える(住所の解決は nest 閉包の全体)。
- **並びは宣言の内容。** 席は宣言の序数(seq)を覚えていて、読む順は
  格納場所ではなく seq が決める。主題コアに散らばっても17本の式の
  並びは動かない — SVG の注記の順序まで監査の対象なので。

まだエンジン側にあるもの(正直に): 合印の釣り合い規則や袖山を解く
手順といった**手続き**は ``garment_marks`` / ``garment_pattern`` の中に
ある。この段階で移すのはデータ(宣言)。手続きまで一般化するのは、
2つ目のBlock(スカート)が抽象を証明する段です。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import cross as _cross

#: 主題が言われていない行の置き場所。**「言われていない」は一級の状態**
#: であってエラーではない。名前の接頭辞(front_ / cap_)から主題を
#: 推し量ることはしない — 当てずっぽうの割り当ては、この店が支える
#: ための門をそのまま毒する。
NO_SUBJECT = None

AMBIGUOUS_ACROSS_SUBJECTS = "UNKNOWN_AMBIGUOUS_ACROSS_SUBJECTS"
NO_SUCH_SUBJECT = "UNKNOWN_NO_SUCH_SUBJECT"


# ---------------------------------------------------------------------------
# コートの宣言。**ここにしかない情報は、ここから来なければならない。**
# 値は製図が実際に使う数そのもの。式の文字列は監査出力にそのまま乗る。
#
# params の行は (鍵, 使う数, 監査出力に乗せる式, 主張の種別, 主題)。
# 主題は**行ごとに宣言する**もので、名前から推し量らない。ここでの
# 割り当ては garment_pattern.draft() を読んで、その定数が実際にどの
# 一枚の形を決めているかで付けた(前後で共有される定数は主題なしで
# block:coat に載る)。
#
# 種別は**全部 specific**。half_divisor 4.0 や neck_w_div 12.0 は製図の
# 標準の割り数に見えるので generic(一般構造)と言いたくなるが、
# GENERIC_MIN_SOURCES は一般構造の主張に独立した出典を2本要求し、
# この宣言は**0本**しか持っていない。generic に付け替えるのは由来の
# 捏造です。specific のままにしてあるから block:coat の kind+ 腕が
# 正直に空になる。
COAT_DECLARATION: Dict[str, Any] = {
    "name": "coat",
    "label": "三枚コート（前身頃・後身頃・袖）",
    "required": ("body_length", "chest", "shoulder"),
    "sleeve_required": ("sleeve_length",),
    # (名前, 必須か)。**袖だけ引けないことはある**ので optional を許す。
    "pieces": [("後身頃", True), ("前身頃", True), ("袖", False)],
    "params": [
        ("half_divisor",         4.0,  None, "specific", NO_SUBJECT),
        ("armhole_depth_div",    8.0,  None, "specific", NO_SUBJECT),
        ("armhole_depth_add",    6.5,  None, "specific", NO_SUBJECT),
        ("shoulder_drop_div",    10.0, None, "specific", NO_SUBJECT),
        ("neck_w_div",           12.0, None, "specific", NO_SUBJECT),
        ("neck_w_add",           1.5,  None, "specific", NO_SUBJECT),
        ("front_neck_add",       2.0,  None, "specific", "前身頃"),
        ("back_neck_depth",      2.0,  None, "specific", "後身頃"),
        ("shoulder_half_div",    2.0,  None, "specific", NO_SUBJECT),
        ("back_armhole_ctrl_dx", 1.0,  None, "specific", "後身頃"),
        ("front_armhole_ctrl_dx", 1.6, None, "specific", "前身頃"),
        ("armhole_ctrl_y_ratio", 0.55, None, "specific", NO_SUBJECT),
        ("cap_height_ratio",     0.78, None, "specific", "袖"),
        ("cuff_div",             8.0,  None, "specific", "袖"),
        ("cuff_add",             2.0,  None, "specific", "袖"),
        ("ease_in_cm",           2.0,  None, "specific", "袖"),
        ("cap_ctrl_x_ratio",     0.5,  None, "specific", "袖"),
        ("cap_ctrl_y_ratio",     0.22, None, "specific", "袖"),
        ("cap_solve_lo",         0.1,  None, "specific", "袖"),
        ("cap_solve_iterations", 60.0, None, "specific", "袖"),
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

#: 式の出力。**(名前, 文字列, 主題) を宣言順で。** 出力の並びは SVG の
#: 注記の順序まで含めて監査の対象なので、ここで固定する。i18n がこの
#: 文字列を翻訳する。主題は式が**何の形を決めるか**で付けてある。
FORMULA_ORDER: List[Tuple[str, str, Optional[str]]] = [
    ("身頃幅 (前後それぞれ)", "chest / 4", NO_SUBJECT),
    ("袖ぐり深さ", "chest / 8 + 6.5", NO_SUBJECT),
    ("肩線の下がり", "shoulder / 10", NO_SUBJECT),
    ("衿ぐり幅 (前後共通)", "chest / 12 + 1.5", NO_SUBJECT),
    ("前衿ぐり深さ", "chest / 12 + 2.0", "前身頃"),
    ("後衿ぐり深さ", "2.0（固定）", "後身頃"),
    ("袖山の高さ", "袖ぐり深さ × 0.78", "袖"),
    ("袖幅 (袖口側)", "chest / 8 + 2.0", "袖"),
    ("袖山の幅", "袖山の長さが「袖ぐりの合計 + いせ込み」になるよう解く",
     "袖"),
    ("いせ込み", "2.0cm（この道具の既定）", "袖"),
    ("肩先の位置 (x)", "shoulder / 2 ※ shoulder は肩幅の全長とみなす",
     NO_SUBJECT),
    ("後袖ぐりの control 点 (x)", "身頃幅 − 1.0（固定）", "後身頃"),
    ("前袖ぐりの control 点 (x)",
     "身頃幅 − 1.6（固定） ※ 前後の袖ぐりの違いはこの 0.6cm だけ",
     "前身頃"),
    ("袖ぐりの control 点 (y)", "袖ぐり深さ × 0.55", NO_SUBJECT),
    ("袖山の control 点 (x)", "袖山の幅 × 0.5", "袖"),
    ("袖山の control 点 (y)", "袖山の高さ × 0.22", "袖"),
    ("袖山の幅の解き方", "二分探索 60 回、範囲 (0.1, 袖ぐりの合計)", "袖"),
]


# ---------------------------------------------------------------------------
def _param_row(row: Any) -> Tuple[str, Any, Any, str, Optional[str]]:
    """params の行を正準化する。**古い3項の行も受ける。**

    組立器(assemble)が作る宣言は (鍵, 値, 式) の3項で、主張の種別は
    「この宣言が決めたこと」= specific、主題は言われていない。
    """
    row = tuple(row)
    key, value = row[0], row[1]
    formula = row[2] if len(row) > 2 else None
    kind = row[3] if len(row) > 3 else "specific"
    subject = row[4] if len(row) > 4 else NO_SUBJECT
    return key, value, formula, kind, subject


def _formula_row(row: Any) -> Tuple[str, str, Optional[str]]:
    """式の行を正準化する。**古い2項の行も受ける**(主題なし)。"""
    row = tuple(row)
    return row[0], row[1], (row[2] if len(row) > 2 else NO_SUBJECT)


def piece_core(root: str, name: str) -> str:
    """一枚の主題の名前。**引き出しではなく主題。**"""
    return f"{root}/piece:{name}"


def _subject_core(st: _cross.CrossStore, root: str, subject: Optional[str],
                  declared: Tuple[str, ...], key: str) -> str:
    """行が言った主題を核の名前にする。**知らない主題は黙って呑まない。**

    宣言されていない一枚を主題に書くと、その席は誰も辿れない核に座る
    — part_of 辺が無いので読む側の主題の一覧に出てこず、``param()`` は
    UNKNOWN_NOT_IN_CROSS と言い、値は**黙って消える**。載っているのに
    読めないのは、この店が断るために在る当のものです。だから根に載せて
    読めるようにした上で、断りを控えに残す。
    """
    if subject is NO_SUBJECT:
        return root
    if subject in declared:
        return piece_core(root, subject)
    st.refusals.append({
        "verdict": NO_SUCH_SUBJECT, "subject": subject, "key": key,
        "declared": list(declared), "seated_on": root,
        "why": "宣言されていない一枚を主題にすると、その席は誰も"
               "辿れない核に座る。根に載せて読めるようにしてある",
        "how_to_close": "pieces にその一枚を宣言するか、主題を外す"})
    return root


def ingest(store: Optional[_cross.CrossStore] = None,
           decl: Dict[str, Any] = COAT_DECLARATION,
           formulas: Optional[List[Any]] = None
           ) -> Tuple[_cross.CrossStore, str]:
    """宣言を十字に載せる。戻り値は (店, 根コアの名前)。

    **容量で落ちない。** 全部の分類を「分ける書き口」に通すので、
    4枚目のピースも5つ目の必須寸法も宣言できる(以前は素の put を
    使っていて、コートは6腕とも4/4だったため**最初の一つの拡張で
    ingest が例外で死んでいた** — 「服を足す = 新しい宣言」が言葉
    だけになっていた)。断りは店の refusals に溜まって
    ``BlockView.refusals()`` から見える。
    """
    st = store if store is not None else _cross.CrossStore()
    if formulas is None:
        formulas = (FORMULA_ORDER if decl is COAT_DECLARATION
                    else decl.get("formulas", []))
    root = f"block:{decl['name']}"
    source = f"declaration:{decl['name']}"

    # ---- 名乗り。**名前は「この一着のもの」という実例側の主張。**
    st.put(root, "label", decl["label"], "declared", source)

    declared = tuple(name for name, _req in decl["pieces"])

    # ---- 一枚ずつが主題になる。4枚目は4つ目の核であって5つ目の面ではない
    for piece_name, required in decl["pieces"]:
        core = piece_core(root, piece_name)
        st.put(core, "role", {"name": piece_name, "required": required},
               "declared", source)
        st.link((core, ""), (root, ""), "part_of")

    # ---- 要る実測は**型紙を生む側**なので cause+
    for spot in decl["required"]:
        st.put(root, f"measure:{spot}",
               {"required": True, "for": "draft"}, "input", source)
    for spot in decl.get("sleeve_required", ()):
        st.put(root, f"measure:{spot}",
               {"required": False, "for": "sleeve"}, "input", source)

    # ---- 縫い目。仕様は面に、関係は辺に。
    for spec in decl["seams"]:
        key = spec.get("label") or f'{spec["a"]} ↔ {spec["b"]}'
        st.put(root, f"seam:{key}", spec, "declared", source)
    # **辺も結ぶ。** 縫い目は二枚の間の約束であって、一枚の上の
    # 項目ではない。面(仕様の全文)と辺(関係)を両方持つ。
    # 同じピースの中の縫い目(袖下線)は一枚の内側の話なので辺にはしない。
    for spec in decl["seams"]:
        key = spec.get("label") or f'{spec["a"]} ↔ {spec["b"]}'
        if spec["a"][0] != spec["b"][0]:
            st.link((piece_core(root, spec["a"][0]), "role"),
                    (piece_core(root, spec["b"][0]), "role"),
                    f"seam:{key}", value=key)

    # ---- 道具の決めごと。**この宣言が決めたこと**なので specific
    for k, (v, basis) in decl["settings"].items():
        st.put(root, f"setting:{k}", {"value": v, "basis": basis},
               "specific", source)
    # 置き場所はその一枚の話なので、その一枚の主題に載る
    for name, (xyz, why) in decl["placement"].items():
        st.put(_subject_core(st, root, name, declared, f"placement:{name}"),
               f"placement:{name}",
               {"value": xyz, "basis": why}, "specific", source)

    # ---- 製図の定数。主題は行が言う(名前から推し量らない)
    for row in decl["params"]:
        key, value, _f, kind, subject = _param_row(row)
        core = _subject_core(st, root, subject, declared, f"param:{key}")
        st.put(core, f"param:{key}", {"value": value}, kind, source)

    # ---- 式は値を**生んだ**ものなので cause+
    for row in formulas:
        name, text, subject = _formula_row(row)
        core = _subject_core(st, root, subject, declared, f"formula:{name}")
        st.put(core, f"formula:{name}", text, "derived", source)

    return st, root


class BlockView:
    """十字に載った Block を読む口。**書き口は ingest だけ。**

    エンジンが直接触るのはこのクラス。宣言の辞書を辿らせず必ず店の
    resolve を通す — 矛盾が割れたとき、読む側が黙ってどちらかを
    拾わないための一本の扉です。
    """

    def __init__(self, store: _cross.CrossStore, root: str) -> None:
        self.store = store
        self.root = root

    # ---------------------------------------------------------- 巡回
    def _subjects(self) -> List[str]:
        """この Block の主題たち。**根と、その一枚一枚。**

        nest で分れた子コアは ``store.seats`` 側の閉包が拾うので、
        ここに出てくるのは主題だけ。
        """
        return [self.root] + self.store.part_of_children(self.root)

    def _ordered(self, prefix: str) -> List[Dict[str, Any]]:
        """接頭辞の付いた席を**宣言の序数(seq)の順で**返す。

        主題コアに散らばっても並びは動かない — 並びは格納場所ではなく
        宣言の内容だから。値が割れていたら落とす(読む側が黙って
        どちらかを拾うことがないように)。
        """
        out: List[Dict[str, Any]] = []
        for subj in self._subjects():
            out.extend(self.store.seats(subj, prefix))
        for r in out:
            if r["verdict"] == _cross.CONTESTED_IN_CROSS:
                raise ValueError(
                    f'{_cross.CONTESTED_IN_CROSS}: {r["key"]} の宣言が'
                    f'割れています。正しい方だけを残してください')
        out.sort(key=lambda r: (r["seq"], r["key"]))
        return out

    def _collect(self, key: str) -> Dict[str, Any]:
        """**主題をまたいで拾う。黙って先に見つけた方を返さない。**

        params が主題コアに載るようになって初めて現れる危険:
        ``param('x')`` は block:coat と一枚一枚の両方を探すので、
        二つの主題が同じ名前を違う値で宣言していたら、素朴な検索は
        先に出会った方を返す。それは**黙って選ぶ**ことで、この店が
        断るために在る当のものです。値が食い違ったら型付きで断る。
        コートには今そういう重複は無いので、コートは動かない。
        """
        hits: List[Dict[str, Any]] = []
        for subj in self._subjects():
            r = self.store.resolve(subj, key)
            if r["verdict"] == _cross.NOT_IN_CROSS:
                continue
            r = dict(r)
            r["subject"] = subj
            hits.append(r)
        if not hits:
            return {"verdict": _cross.NOT_IN_CROSS, "key": key}
        for h in hits:
            if h["verdict"] == _cross.CONTESTED_IN_CROSS:
                return h
        vals = [h["value"] for h in hits]
        if any(v != vals[0] for v in vals[1:]):
            return {"verdict": AMBIGUOUS_ACROSS_SUBJECTS, "key": key,
                    "subjects": [{"subject": h["subject"],
                                  "value": h["value"]} for h in hits],
                    "how_to_close": "主題を指して読むか、宣言をそろえる"}
        return hits[0]

    # ------------------------------------------------------------ 読み
    def label(self) -> str:
        return self.store.require(self.root, "label")

    def pieces(self, required_only: bool = False) -> List[str]:
        out = []
        for f in self._ordered("role"):
            if required_only and not f["value"]["required"]:
                continue
            out.append(f["value"]["name"])
        return out

    def measures(self, required_only: bool = False) -> List[str]:
        out = []
        for f in self._ordered("measure:"):
            if required_only and not f["value"]["required"]:
                continue
            out.append(f["key"].split(":", 1)[1])
        return out

    def required(self) -> Tuple[str, ...]:
        return tuple(self.measures(required_only=True))

    def sleeve_required(self) -> Tuple[str, ...]:
        return tuple(k for k in self.measures()
                     if k not in self.required())

    def param(self, key: str) -> float:
        r = self._collect(f"param:{key}")
        if r["verdict"] == "ANSWER":
            return r["value"]["value"]
        raise ValueError(f'{r["verdict"]}: param:{key} — '
                         "Block の宣言に足すか、宣言をそろえる")

    def formulas(self) -> Dict[str, str]:
        """式の出力。**宣言順を保つ**(注記の並びまで一致させる)。"""
        return {f["key"].split(":", 1)[1]: f["value"]
                for f in self._ordered("formula:")}

    def seams(self) -> List[Dict[str, Any]]:
        return [f["value"] for f in self._ordered("seam:")]

    def seam_edges(self) -> List[Dict[str, Any]]:
        """縫い目の**辺**(二枚の間の約束として結ばれたもの)。"""
        return self.store.edges_labeled("seam:")

    def placement(self) -> Dict[str, Tuple[float, float, float]]:
        out: Dict[str, Tuple[float, float, float]] = {}
        for f in self._ordered("placement:"):
            out[f["key"].split(":", 1)[1]] = f["value"]["value"]
        return out

    def setting(self, key: str) -> Any:
        r = self._collect(f"setting:{key}")
        if r["verdict"] == "ANSWER":
            return r["value"]["value"]
        raise ValueError(f'{r["verdict"]}: setting:{key} — '
                         "Block の宣言に足す")

    # ------------------------------------------------------------ 腕を問う
    def gaps(self) -> List[str]:
        """**空いている腕を型付きの欠落として返す。**

        コートが返すのは UNKNOWN_NO_SUPPORT_RECORDED(20個の定数を
        支える実測も引用も**一つも無い**)と
        UNKNOWN_NO_GENERALIZATION_RECORDED(一般構造だと言える主張が
        一つも無い。全部この道具が決めたこと)と、効果と反証の分。
        腕を消すとこの三つは問える住所を失って、またコメントの散文に
        戻ります。
        """
        return self.store.gaps(self.root)

    def arm_census(self) -> Dict[str, int]:
        return self.store.arm_census(self.root)

    def refusals(self) -> List[Dict[str, Any]]:
        """ingest が飲み込まずに溜めた断り。**例外で落ちない代わり。**"""
        return [dict(r) for r in self.store.refusals]

    def unbought_generics(self) -> List[Dict[str, Any]]:
        return self.store.unbought_generics()

    # ------------------------------------------------------------ 正準形
    def served(self) -> Dict[str, Any]:
        """**提供データの正準形。** 店の形は入らない — 出す中身だけ。"""
        return {
            "label": self.label(),
            "required": self.required(),
            "sleeve_required": self.sleeve_required(),
            "pieces": self.pieces(),
            "params": {k: self.param(k)
                       for k, _v, _f, _kd, _s
                       in (_param_row(r)
                           for r in COAT_DECLARATION["params"])},
            "formulas": self.formulas(),
            "seams": self.seams(),
            "placement": self.placement(),
            "settings": {k: self.setting(k)
                         for k in COAT_DECLARATION["settings"]},
            "seam_edges": len(self.seam_edges()),
        }

    def dump(self) -> str:
        """丸写し検収(round-trip)に使う。**中身 + 店の在り方。**"""
        import json
        out = dict(self.served())
        out["census"] = self.store.census()
        return json.dumps(out, ensure_ascii=False, sort_keys=True)


_CACHE: Dict[str, BlockView] = {}


def coat() -> BlockView:
    """コート Block。**モジュールで一つの店に載せ、皆そこから読む。**"""
    if "coat" not in _CACHE:
        st, root = ingest()
        _CACHE["coat"] = BlockView(st, root)
    return _CACHE["coat"]
