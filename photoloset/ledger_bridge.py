# -*- coding: utf-8 -*-
"""橋 ── 幾何(``structure.py`` / ``photo_to_pattern.py``)から台帳
(``garment.Ledger``)へ。**片道しか繋がっていなかった。**

実測(2026-08-27、この企画の起点になった数字)::

    geometry -> ledger 参照:  silhouette 0, panels 0, flatten 0,
                              photo_to_pattern 0, mannequin 0, darts 0,
                              points 0, marker 0, bom 0, dxf 0,
                              sewing_order 0, curvature 0
    ledger -> geometry 参照:  confirm 21, sewing_search 26, compose 9,
                              parts 5

台帳は幾何を知っている(``confirm.py`` の ``approve()`` は ``garment.
Ledger.propose()`` + ``.adopt()`` で検索の提案を採用する)。幾何は台帳を
一度も知らない。だから写真の輪郭から ``structure.py`` / ``photo_to_
pattern.py`` が計算した数は、**一件の INFERRED も一件の PROPOSED も台帳
に置かれたことが無い** ── 「どこまで分かっているか」を見せるために在る
五状態の機構(``garment.OBSERVED`` / ``CONTESTED`` / ``INFERRED`` /
``PROPOSED`` / ``UNKNOWN_NOT_OBSERVED``)が、写真の経路を一度も検分しな
い。この橋はその欠落を塞ぐ ── **新しい状態は作らない。台帳に既にある
五つの状態へ、正しい住所で運ぶだけ。**

## この橋が運ぶ三つの区別

``garment.py`` 自身の語彙のまま、増やさない:

    構造から推した数(structure.py の landmarks に既に ``"kind":
    "INFERRED"`` が付いている、または ``"kind"`` が無く純粋に幾何から
    解決している)                    -> ``ledger.infer()``、``basis`` を
                                        ``note`` として運ぶ
    根拠は言えるが選べない二択(同じ landmarks に ``"kind": "PROPOSED"``
    + ``"alternatives"`` が付いている)-> ``ledger.propose()``。``assumed``
    と ``alternatives`` の**両方**を同じ住所に置く。未採用のまま ──
    ``ledger.spec()`` は PROPOSED を ``open`` に置き、``confirmed`` には
    絶対に出ない(``techpack()`` の注記どおり「01-05 の確定欄以外は裁断
    の根拠にしないこと」)
    実測(``measures`` 引数。``garment_measure.Measures`` 自身が既に持つ
    出典)                            -> **ここでは絶対に着地させない**。
    この橋の公開関数はどちらも ``measures`` を受け取らない(署名を見れば
    分かる)し、``ledger.observe()`` はこのファイルから一度も呼ばれない
    ── 呼べば二つ目の原典を作ってしまう。``grep -c 'ledger\\.observe('
    ledger_bridge.py`` は 0 であること自体が、この規律の検査になる。

## 住所は (part, aspect) だけ ── 生んだ関数の名前を住所に入れない

``resemble.land()`` の鍵の規律(``_key()`` は ``hit["aspect"]`` だけを見
て、出典 ``model_id`` は住所に入れない)と同じ理由がここにもある: 肩の
推測(``structure._shoulder``)とウエストの推測(``structure._waist``)が
別々の関数から来ても、どちらもこの服の全体の形について言っているなら
同じ ``("body", "silhouette")`` に置く。関数名を住所に混ぜると
``body/silhouette_from_shoulder`` と ``body/silhouette_from_waist`` という
二つの住所になり、食い違っても両方が ANSWER で返って読む側が気付けない
── ``resemble.py`` のモジュール docstring が言う「二つのバックエンドが
不一致でも二つの住所なら両方 ANSWER」と全く同じ壊れ方。

``garment.Ledger`` は ``(part, aspect)`` しか住所を持たない
(``cross.CrossStore`` の ``(core, key)`` と違って、腕も隔離核も無い) ──
だから「衝突させる」ための特別な仕掛けはここでは要らない。**正しい
(part, aspect) に正しい kind で置きさえすれば、あとは ``Ledger.state()``
が既に持っている規則がそのまま働く**:

- ``INFERRED`` は先着(``inf[0]``)の値を返すだけで、二件目が食い違って
  いても衝突を検査**しない**(``garment.py`` はこの企画の所有ファイルで
  はないので、ここを直すことはこの橋の仕事ではない)。だから食い違いを
  表に出したいなら ``PROPOSED`` で置く。
- ``PROPOSED`` は届いた提案を ``proposals`` にそのまま並べて返す ──
  どちらも選ばない。**採用されて初めて ``"observation"`` に変わる**
  (``Ledger.adopt`` が ``kind`` を書き換える、``garment.py`` の
  ``adopt()`` docstring 「採用が提案が事実になる唯一の道」)。そこで
  初めて ``Ledger.state()`` の OBSERVED/CONTESTED 分岐が値を比べる ──
  同じ住所に届いた二つの提案が**別々の人に採用**されると、値が食い違え
  ばそこで CONTESTED が出る。これは新しい仕掛けではなく ``Ledger`` が
  既に持っている一本道で、この橋は「正しい (part, aspect) に、正しい
  kind で置く」ことしかしていない。

## (part, aspect) の対応表 ── ``garment.PARTS`` は閉じた表なので増やさない

``garment.PARTS`` は ``spec()``/``techpack()`` が ``PARTS.items()`` だけ
を回って読む閉じた表で、``garment.py`` は所有ファイルではないので新しい
(part, aspect) をそこに足すことはできない。この橋が実際に運べるのは
``PARTS`` に既にある四つの住所だけ:

    ("body", "silhouette")   shoulder / waist の landmark、
                              silhouette_match の ease
    ("body", "length")       hem の landmark、calibration の較正結果
    ("body", "dart")         panels.cut に渡すダーツ深さ比(既定値)
    ("sleeve", "construction") armpit_left / armpit_right の landmark
                              (袖の有無)

``structure.py`` の ``front_or_back`` / ``hem.front_back_attribution``
(どちらも ``kind: "PROPOSED"`` + ``alternatives`` を持つ)は**運ばない**
── 「前身頃か後ろ身頃か」という向きは ``garment.PARTS`` のどの aspect
にも対応しない。無理に既存の aspect(例えば back/structure)へ押し込む
と、その aspect が本来言うべきこと(背面の構造)と混ざって読めなくなる。
足りない aspect を作ることは ``garment.py`` を書き換える別の仕事で、
ここでは名指しで断って何も置かない(``skipped`` に理由を残す)。

## 値の型 ── ``Entry.value`` は文字列

``garment.Entry.value: str`` で、``Ledger._add`` は ``str(value)`` する
だけ ── dict をそのまま渡すと Python の repr が住所ごとに文字順で崩れ、
同じ値のはずの二つの提案が別の文字列として重複してしまう(``propose()``
の重複判定はタプルの ``==`` で、文字列の並びが揺れると同じ値が二本に
割れる)。``confirm.py`` の ``approve()`` が ``json.dumps(..., sort_keys=
True, default=repr)`` で先に文字列へ固定しているのと同じ理由で、ここも
``_value_str()`` を通す ── 決定的な文字列にしてから ``Ledger`` に渡す。

## この橋につけるべき検査(文章として。後続が ``tests/run_checks.py`` へ
   移す)

1. **幾何の推論は INFERRED として届き、OBSERVED としては絶対に届かな
   い。** ``structure.from_outline`` の合成A-lineフィクスチャ(``photo_
   to_pattern.py`` のモジュール docstring が既に持っている実測フィクス
   チャと同じもの)を ``land_structure(ledger, structure_out)`` に通す。
   ``ledger.state("body", "silhouette")["state"]`` が ``garment.
   INFERRED`` であること、``garment.OBSERVED`` では**絶対にない**こと。
   落とし方(mutation): ``_land_landmarks`` の INFERRED 分岐が
   ``ledger.infer`` の代わりに ``ledger.observe`` を呼ぶよう書き換える
   と、``ref_path=""`` で ``is_generated("")`` は False を返すので
   ``observe()`` は素通りし、``state()`` は OBSERVED を返してしまう ──
   この検査はそこで red になる。
2. **提案は採用されるまで型紙に届かない。** 袖ぐりが見つからない合成
   輪郭(``structure.py`` モジュール docstring の straight shift フィク
   スチャ、``armpit_left``/``armpit_right`` が両方 ARMPIT_NOT_FOUND で
   ``kind="PROPOSED"`` になる入力)を ``land_structure`` に通したあと、
   ``ledger.spec()`` を呼ぶ。``("sleeve", "construction")`` は ``open``
   の中に ``state=PROPOSED`` として現れ、``confirmed`` には一件も現れな
   いこと。続けて ``ledger.adopt("sleeve", "construction", <採用する
   value_str>, by="atelier")`` を呼んでから ``spec()`` を取り直すと、
   今度は ``confirmed`` に移ること。落とし方: ``_land_landmarks`` の
   PROPOSED 分岐で ``ledger.propose`` の代わりに ``ledger.infer`` を
   呼ぶよう書き換えると、``adopt()`` は ``kind == "proposal"`` の行しか
   見ないので二度と採用できなくなり、かつ ``spec()`` の ``inferred``
   節に(未確認のまま)最初から現れてしまう ── どちらの壊れ方でも
   この検査は red になる。
3. **二つの hop が同じ側面で食い違えば CONTESTED になる、片方を黙って
   選ばない。** ``structure.py`` の fit-and-flare フィクスチャ(``_armpit``
   が候補はあるが膨らみ判定で落ちる側)は ``assumed={"sleeve_present":
   False}`` と ``alternatives=[{"value": {"sleeve_present": True}, ...}]``
   を同時に持つ ── 一つの hop の中に、既に食い違う二つの値がある。
   ``land_structure`` で両方を ``("sleeve", "construction")`` に
   ``propose()`` したあと、``ledger.adopt("sleeve", "construction",
   _value_str({"sleeve_present": False}), by="a")`` と ``ledger.adopt(
   "sleeve", "construction", _value_str({"sleeve_present": True}),
   by="b")`` を**両方**呼ぶ(採用は ``kind`` を ``"observation"`` に書
   き換えるので、ここで初めて ``state()`` の OBSERVED/CONTESTED 分岐が
   値を比べる)。``ledger.state("sleeve", "construction")["state"]`` が
   ``garment.CONTESTED`` で、``sides`` に両方の値が(片方だけを選ばずに)
   載っていること。落とし方: 住所の対応表 ``_LANDMARK_ADDRESS`` の
   ``"armpit_right"`` を ``("sleeve", "cuff")`` のような別の aspect に
   変えると、二つの値は別の住所に散って両方 ANSWER で返ってしまい、
   この検査は red になる ── これが「鍵の規律」そのものの pin。

``land_photo_to_pattern`` は ``land_structure`` と同じ ``_land_landmarks``
を ``result["structure_summary"]["landmarks"]``(``photo_to_pattern.run``
が ``structure.from_outline`` の ``landmarks`` をそのまま運んでいる、
``photo_to_pattern.py`` の ``run()`` 実装参照)に通したうえで、この橋の
モジュール自身は追加で二つの住所(``body/length`` の較正結果、``body/
silhouette`` の ease、``body/dart`` の既定比)を足す。この三つはどれも
``photo_to_pattern.py`` のモジュール docstring が既に「輪郭は何を決めて
何を決めないか」を実測で書いている数(``calibration.assumption`` の文言
そのもの、``silhouette_match_summary`` の ease、``panels.
DEFAULT_DART_DEPTH_RATIO``)で、ここで新しい主張を作ってはいない ──
その docstring が既に述べている事実を、初めて台帳の住所へ運ぶだけ。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from . import panels as _panels

NO_LEDGER = "UNKNOWN_NO_LEDGER"
NOTHING_TO_LAND = "UNKNOWN_NOTHING_TO_LAND"
BAD_ARGUMENTS = "UNKNOWN_BAD_ARGUMENTS"

#: ``garment.PARTS`` に既にある住所だけを使う。増やさない。
BODY_SILHOUETTE: Tuple[str, str] = ("body", "silhouette")
BODY_LENGTH: Tuple[str, str] = ("body", "length")
BODY_DART: Tuple[str, str] = ("body", "dart")
SLEEVE_CONSTRUCTION: Tuple[str, str] = ("sleeve", "construction")

#: ``structure.from_outline()["landmarks"]`` のキー -> この橋が運ぶ住所。
#: **住所に landmark 名や関数名を混ぜない** ── 同じ住所に集まって初めて
#: 衝突(CONTESTED への一本道)が起きる。``front_or_back`` はここに無い
#: ── 対応する aspect が ``garment.PARTS`` に無いので運ばない。
_LANDMARK_ADDRESS: Dict[str, Tuple[str, str]] = {
    "shoulder": BODY_SILHOUETTE,
    "waist": BODY_SILHOUETTE,
    "hem": BODY_LENGTH,
    "armpit_left": SLEEVE_CONSTRUCTION,
    "armpit_right": SLEEVE_CONSTRUCTION,
}


def _value_str(v: Any) -> str:
    """``Ledger.Entry.value`` は文字列。**決定的な文字列にしてから渡す**
    ── 同じ値が二つの提案として重複判定を素通りしないように。"""
    return json.dumps(v, ensure_ascii=False, sort_keys=True, default=repr)


def _rec(part: str, aspect: str, mode: str, source: str,
        value: str, note: str) -> Dict[str, Any]:
    return {"part": part, "aspect": aspect, "mode": mode,
            "source": source, "value": value, "note": note}


def _land_landmarks(ledger: Any, landmarks: Dict[str, Any], source: str
                    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """``structure.py`` の landmarks 一枚を運ぶ。**分類は landmark 自身が
    既に持っている ``kind`` を読むだけ** ── ここで新しい確信度を発明し
    ない。

    四つに分かれる(``structure.py`` の推論契約そのまま):

    - ``kind`` が無く ``verdict`` も無い ── 幅の knee やウエストの最狭
      点など、幾何から直接解決した値。観測ではないので ``infer()``。
    - ``kind == "INFERRED"`` ── 解決できず、``assumed`` の代入で埋めた
      値。``basis`` を ``note`` として運ぶ。
    - ``kind == "PROPOSED"`` ── 根拠はあるが選べない値。``assumed``(在
      れば)と ``alternatives`` の**全部**を同じ住所に ``propose()``。
    - ``kind`` が無く ``verdict`` だけがある ── 埋める根拠も無い純粋な
      拒否(``assumed`` も ``alternatives`` も無い)。**何も置かない**
      ── 埋めない拒否を埋めて置いたら、それは推測の主張になる。
    """
    landed: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for name, val in landmarks.items():
        address = _LANDMARK_ADDRESS.get(name)
        if address is None:
            skipped.append({
                "landmark": name,
                "why": "garment.PARTS にこの landmark に対応する "
                       "(part, aspect) が無い(front_or_back のような"
                       "向きの二択は、対応する aspect 自体が閉じた表に"
                       "存在しない)。足りない aspect を作るのは "
                       "garment.py を書き換える別の仕事",
            })
            continue
        if not isinstance(val, dict):
            skipped.append({"landmark": name,
                            "why": f"landmark の形が dict ではない "
                                   f"({type(val).__name__})"})
            continue
        part, aspect = address
        this_source = f"{source}:{name}"
        kind = val.get("kind")
        if kind == "INFERRED":
            if "assumed" not in val:
                skipped.append({"landmark": name,
                                "why": "kind=INFERRED だが assumed が無い"})
                continue
            note = str(val.get("basis") or "")
            e = ledger.infer(part, aspect, _value_str(val["assumed"]),
                             this_source, note=note)
            landed.append(_rec(part, aspect, "inferred", this_source,
                               e.value, note))
        elif kind == "PROPOSED":
            wrote = False
            if "assumed" in val:
                note = str(val.get("basis") or "")
                e = ledger.propose(part, aspect, _value_str(val["assumed"]),
                                   this_source, note=note)
                landed.append(_rec(part, aspect, "proposed", this_source,
                                   e.value, note))
                wrote = True
            for alt in (val.get("alternatives") or []):
                note = str(alt.get("basis") or "")
                e = ledger.propose(part, aspect, _value_str(alt.get("value")),
                                   this_source, note=note)
                landed.append(_rec(part, aspect, "proposed", this_source,
                                   e.value, note))
                wrote = True
            if not wrote:
                skipped.append({"landmark": name,
                                "why": "kind=PROPOSED だが assumed も "
                                       "alternatives も無い"})
        elif kind is None:
            if "verdict" in val:
                skipped.append({"landmark": name,
                                "why": f"埋める根拠の無い拒否 "
                                       f"({val.get('verdict')})。埋めない"
                                       "拒否を埋めて置くと、それ自体が"
                                       "推測の主張になる"})
                continue
            note = str(val.get("from") or val.get("how") or
                      "輪郭の幾何から直接解決した値(推測で埋めていない)")
            e = ledger.infer(part, aspect, _value_str(val), this_source,
                             note=note)
            landed.append(_rec(part, aspect, "inferred", this_source,
                               e.value, note))
        else:
            skipped.append({"landmark": name,
                            "why": f"未知の kind {kind!r}"})
    return landed, skipped


def land_structure(ledger: Any, structure_out: Dict[str, Any], *,
                   source: str = "structure.from_outline") -> Dict[str, Any]:
    """``structure.from_outline()`` の答え一個を台帳へ運ぶ。**幾何の
    landmarks だけを運ぶ** ── ``width_profile`` / ``knees`` /
    ``concavities`` のような中間の計算値、``refused_by_design`` のような
    名指しの拒否そのものは運ばない(拒否は主張ではないので置く先が無い)。

    ``ledger`` が ``None``、または ``structure_out`` が ANSWER でなけれ
    ば、**何も置かずに**断りを返す ── ``resemble.land()`` と同じ理由:
    止まった輪郭処理の途中の数を置くのは、幾何が断った不在を服について
    の主張に仕立てることになる。
    """
    if ledger is None:
        return {"verdict": NO_LEDGER,
                "how_to_close": "この橋が書き込む garment.Ledger を渡し"
                                "てください。誰も記録しない着地は無いのと"
                                "同じです"}
    if not isinstance(structure_out, dict):
        return {"verdict": BAD_ARGUMENTS,
                "why": "structure.from_outline() が返した dict を渡して"
                       "ください"}
    if structure_out.get("verdict") != "ANSWER":
        return {"verdict": NOTHING_TO_LAND,
                "carried": structure_out.get("verdict"),
                "why": "拒否は結果ではありません。止まった輪郭処理の途中"
                       "の数を置くと、幾何が断った不在がこの服についての"
                       "主張に化けます",
                "how_to_close": structure_out.get("how_to_close", "")}

    landed, skipped = _land_landmarks(
        ledger, structure_out.get("landmarks") or {}, source)
    return {"verdict": "ANSWER", "landed": landed, "skipped": skipped}


def land_photo_to_pattern(ledger: Any, result: Dict[str, Any], *,
                          source: str = "photo_to_pattern.run",
                          dart_depth_ratio: Optional[float] = None
                          ) -> Dict[str, Any]:
    """``photo_to_pattern.run()`` の答え一個を台帳へ運ぶ。**``measures``
    は受け取らない** ── 引数にすら無い。実測(タープメジャー等)は
    ``garment_measure.Measures`` 自身が既に出典を持つので、ここで
    ``ledger.observe()`` を呼んで二つ目の原典を作らない。

    運ぶのは四つ:

    1. ``structure_summary.landmarks``(``structure.from_outline`` が計算
       したものそのまま)── ``land_structure`` と同じ ``_land_landmarks``
       を通す。
    2. ``calibration`` ── px→cm の較正結果。``("body", "length")`` へ
       INFERRED、``note`` は較正関数自身が書いた ``assumption`` の文言
       そのもの(較正が何を仮定したかを、ここで言い直さない)。
    3. ``silhouette_match_summary`` ── 高さごとの ease。``("body",
       "silhouette")`` へ INFERRED。
    4. ダーツ深さ比 ── ``run()`` に渡した(または渡さなかった)
       ``dart_depth_ratio``。``("body", "dart")`` へ INFERRED、``note``
       は「輪郭は一度も触れない既定値」という事実(``panels.py`` の
       ``DEFAULT_DART_DEPTH_RATIO`` docstring の言うとおり)。

    ``result`` が ANSWER でなければ、**何も置かずに**断りを返す。途中の
    hop で止まった鎖は、そこまでの数値も途中の仮定であって確定した推論
    ではない ── 置けば「どのホップまで進んだか」を「この服について何が
    分かったか」にすり替えることになる。
    """
    if ledger is None:
        return {"verdict": NO_LEDGER,
                "how_to_close": "この橋が書き込む garment.Ledger を渡し"
                                "てください"}
    if not isinstance(result, dict):
        return {"verdict": BAD_ARGUMENTS,
                "why": "photo_to_pattern.run() が返した dict を渡してく"
                       "ださい"}
    if result.get("verdict") != "ANSWER":
        return {"verdict": NOTHING_TO_LAND,
                "carried": result.get("verdict"),
                "failed_hop": result.get("failed_hop"),
                "why": "拒否は結果ではありません。途中の hop で止まった"
                       "鎖のそこまでの数値を置くと、『どこまで進んだか』"
                       "が『この服について何が分かったか』にすり替わりま"
                       "す",
                "how_to_close": result.get("how_to_close", "")}

    landed: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    structure_summary = result.get("structure_summary") or {}
    l1, s1 = _land_landmarks(
        ledger, structure_summary.get("landmarks") or {},
        f"{source}#structure")
    landed += l1
    skipped += s1

    calib = result.get("calibration") or {}
    if calib:
        note = str(calib.get("assumption") or "")
        value = {k: calib.get(k) for k in
                ("anchor_kind", "scale_cm_per_px",
                 "body_hi_cm", "body_lo_cm", "waist_level_cm")}
        e = ledger.infer(*BODY_LENGTH, _value_str(value),
                         f"{source}#calibration", note=note)
        landed.append(_rec(*BODY_LENGTH, "inferred",
                           f"{source}#calibration", e.value, note))

    sil = result.get("silhouette_match_summary") or {}
    if sil:
        note = ("silhouette.match が解いた高さごとの ease(輪郭の投影幅と"
                "人台の断面幅の差)。奥行・断面の形は mannequin."
                "DEPTH_RATIO=0.70 の仮定のまま、輪郭は一度も触れない")
        e = ledger.infer(*BODY_SILHOUETTE, _value_str(sil),
                         f"{source}#silhouette_match", note=note)
        landed.append(_rec(*BODY_SILHOUETTE, "inferred",
                           f"{source}#silhouette_match", e.value, note))

    ratio = (_panels.DEFAULT_DART_DEPTH_RATIO if dart_depth_ratio is None
            else dart_depth_ratio)
    note = ("解剖学的根拠のない既定値(panels.DEFAULT_DART_DEPTH_RATIO)。"
            "輪郭は一度もダーツの深さに触れない")
    e = ledger.infer(*BODY_DART, _value_str({"dart_depth_ratio": ratio}),
                     f"{source}#panels_cut", note=note)
    landed.append(_rec(*BODY_DART, "inferred", f"{source}#panels_cut",
                       e.value, note))

    return {"verdict": "ANSWER", "landed": landed, "skipped": skipped,
            "not_relanded": [
                "measures ── garment_measure.Measures 自身が既に出典を"
                "持つ実測。ここで observe() すると二つ目の原典を作る"],
           }
