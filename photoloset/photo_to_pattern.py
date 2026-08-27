# -*- coding: utf-8 -*-
"""写真の輪郭から型紙まで。**一回の呼び出しで、繋ぎ目はすべて型付きで断る。**

四つのモジュールが別々に立った: ``structure.py``(輪郭→ランドマーク)、
``silhouette.py``(輪郭→密着ベースの変形)、``panels.py``(平面化した筒→
実際の裁片)、そして Swift 側の ``GarmentOutline``(写真→輪郭)。どれも
正しく動くが、どれも隣を知らない ── ``silhouette.match`` が要る
``outline`` は cm 単位で人台と同じ座標系、``structure.from_outline`` が
読む輪郭は px 単位で画像そのものの座標系。この二つを繋ぐ変換はどちらの
モジュールにも無い。ここがそれを持つ、**ただ一つの新しい仕事**。

**チェーンそのもの(実際に呼ぶ順、全部 ``run()`` の中):**

    outline (THE OUTLINE CONTRACT, px)
      -> structure.from_outline          幾何ランドマーク(肩・裾…)
      -> mannequin.build(measures)       実測から人台を立てる
      -> [このファイルの仕事] 較正       px→cm、肩→襟ぐり、ウエスト→ウエスト
      -> silhouette.match(man, outline_cm)   高さごとの ease を解く
      -> silhouette.to_surface           密着ベースの3次元メッシュ
      -> flatten.build(radius_at=...)    筒1枚に平面化、歪みを測る
      -> panels.cut(radius_at=...)       歪み最悪の場所で切る
      -> panels.to_pieces                garment_pattern.draft() と同じ形

``points.py`` / ``darts.py`` / ``sewing_order.py`` / ``marker.py`` /
``bom.py`` / ``dxf.py`` は ``panels.to_pieces()`` の形をそのまま読める ──
実測済み: ``{"verdict": "ANSWER", "pieces": run()の"pieces"}`` を
``marker.lay(..., fabric_width_cm=150.0, cut={各裁片名:1}, seam_allowance_
cm=1.0)`` にそのまま渡すと ``ANSWER``(``length_m≈0.92``、下の CEILING の
4パネルで)。ここでは呼ばない: それらは型紙が立った**後**の別の仕事で、
「一回の呼び出しで型紙まで」という約束の外にある。

**繋ぎ目で見つかった、本物のずれ二つ(直したのはこのファイルの中だけ)。**

1. **座標系が違う。** ``structure.py`` は px・画像座標(yは下向き)。
   ``silhouette.py``/``mannequin.py`` は cm・人台座標(yは上向き、y=0が
   腰)。定規もサイズ表記も写真には無いので、この二つを繋ぐには**仮定が
   一個要る**。**最初に書いた版**は: 輪郭の肩(``structure`` の
   ``landmarks.shoulder.y_px``)を人台の襟ぐり(``body_hi``)に、輪郭の
   bboxの最下端(裾)を人台の腰(``body_lo``)に対応させ、その間を等方
   スケールで写す ── これを実際にA-lineドレスの合成輪郭で走らせたところ
   ``silhouette_match`` で ``UNKNOWN_SILHOUETTE_UNREACHABLE``(17リング中
   9本が min ease 違反)になった。**理由は実測して分かった**: 裾が
   ウエストよりずっと下(スカートのフレア)にある服では、肩〜裾のpx距離
   を腰〜襟ぐりのcm距離へ一様に引き伸ばすと、輪郭自身のウエストのくびれ
   が人台のバスト付近まで押し上げられ、そこは人台の方が輪郭より太いので
   ease が負に落ちる。**今の版**は第二の足場を裾ではなく**ウエスト**
   (``structure`` が解決していれば ``landmarks.waist.y_px``、人台の
   ``_levels[1]`` の実際のウエスト高)に取る ── 輪郭のウエストは必ず
   人台のウエストに合う。ウエストが解決していない服だけ、裾→腰へ後退
   する(``anchor_kind: "shoulder_to_hem_fallback"``、弱い方の仮定だと
   ``assumption`` に明記)。**どちらの版でも、ウエストより下(裾・
   フレア)は較正がどう伸縮させても意味を持たない** ── 人台に元から
   その高さの身体が無いので、``silhouette.match`` の既定範囲(腰〜
   襟ぐり)には最初から入らない。``_calibrate`` の返り値に
   ``assumption``/``anchor_kind`` として毎回同梱する。
2. **二重のゆるみ。** ``flatten.build`` と ``panels.cut`` はどちらも既定
   ``gap=mannequin.GAP_CM``(1.0cm)を持つ ── これは「まだ何も測って
   いないとき、人台の表面に一定の空気層を足す」既定で、``silhouette.
   match`` が輪郭から解いた ``ease(y)`` を包む ``radius_at`` を渡すと、
   その上にさらに1cm足してしまう(``panels.cut`` 自身の docstring が
   この罠を名指しで警告している。``flatten.build`` の docstring は
   警告していないが同じ罠を持つ ── **実測で確認**: ``gap`` を渡し忘れて
   走らせると ``ease_range_cm`` が ``[-3.2, 4.8]`` 台の輪郭でも
   flatten側の見た目の半径だけ一律+1cm動く)。ここでは
   ``silhouette.radius_at_for()`` を渡す2箇所(``flatten.build`` /
   ``panels.cut``)に必ず ``gap=0.0`` を明示する。

**このファイルが追加で断るもの(型付き、``UNKNOWN_`` 接頭辞は他と同じ)。**

    UNKNOWN_NO_SHOULDER_ANCHOR_FOR_SCALE  肩が輪郭から解決できず、
        px→cm の足場が無い(``structure`` は ANSWER でも、その中の
        ``landmarks.shoulder`` が ``UNKNOWN_SHOULDER_NOT_RESOLVED`` の
        とき)
    UNKNOWN_DEGENERATE_PHOTO_SCALE  肩〜裾のpx方向の幅、または人台の
        腰〜襟ぐりのcm方向の幅が実質ゼロ
    UNKNOWN_BAD_MEASURES  ``measures`` が ``Measures`` と同じ形
        (``.entries`` を持つ)をしていない

それ以外の拒否はすべて下流(``structure`` / ``mannequin`` /
``silhouette`` / ``flatten`` / ``panels``)がそのまま持って上がる ──
ここで新しい verdict 名に化けない。``run()`` の返り値は失敗した場所でも
必ず ``failed_hop`` とそこまでの ``hops``(verdict・count・seconds)を
持つので、どこで止まったかは常に分かる。

**測った天井(実測、2026-08-27)。** ``run()`` は ``measures`` を直接受け取
る ── ``photoloset.garment_measure.Measures()`` をその場で組み立てて渡した
だけで、``~/.photoloset`` のどの置き場にも触れていない(念のため注記: この
リポジトリの ``mcp.py`` は ``PHOTOLOSET_HOME`` 環境変数を一切読まない ──
``HOME = Path.home() / ".photoloset"`` は決め打ち。店を切り替えたいなら
``mcp.HOME`` そのものではなく、それより先に束縛される ``PROJECTS``/
``CURRENT`` も含めて差し替える必要がある。**MCP経由(``photo_pattern``
ツール)で較正・チェーンの挙動を検査するときはこれを踏まえること** ──
このファイル自身の検証は ``run()`` をPythonから直接呼ぶ形でだけ行った)。

合成A-lineドレス輪郭(半幅: 肩90px[t≤0.15]→ウエスト60px[t=0.35]→裾160px
[t=1]、121点/辺=242点、キャンバス800×1200、y_top=100px〜y_bottom=1100px)、
実測寸法 chest=88cm/waist=68cm/hip=94cm/body_length=140cmの人台、既定
解像度(segments=24, height_steps=16, iterations=3000, n_panels=4)で
``run()`` に通した(3回走らせ、verdict/countは3回とも同一、secondsは
機体負荷で変動 ── 幅を併記する)::

    hop                    verdict  count  seconds(観測範囲)
    structure              ANSWER   121    0.03〜0.09   (width_profile行数)
    mannequin               ANSWER   408    0.0003〜0.001 (頂点数)
    calibration              ANSWER   1      0.000        (較正1個)
    silhouette_match         ANSWER   17     0.002〜0.007  (解いたリング数)
    base_garment_surface     ANSWER   408    0.0008〜0.003 (頂点数)
    flatten                  ANSWER   768    1.6〜4.7      (三角形数)
    panels_cut               ANSWER   4      6.4〜16.1     (到達パネル数)
    panels_to_pieces         ANSWER   4      0.000         (裁片数)
    合計                                     8.1〜21.0秒

較正(``calibration`` hop)の中身(この実行): ``axis_x_px=400.0``、
``y_top_px=250.0``(肩)、``y_second_px=450.0``(ウエスト、
``anchor_kind="shoulder_to_waist"``)、``scale_cm_per_px=0.259``、
``waist_level_cm=35.0``。``silhouette_match`` の ``ease_range_cm=
[4.80, 17.01]``、``width_residual_cm.max=0.74``。``panels_cut`` は歪み
指数を ``0.1186 → 0.0394``(``distortion_bought_total_pct=66.8%``)へ
落とし、``gauss_bonnet_across_all_panels_deg=1440.0``(期待値
``360×4=1440.0``、残差0)。仕上がり面積 ``total_area_cm2=9422.77``。

自己交差させた輪郭(同じA-lineの右辺と左辺を入れ替えて交差させたもの)は
``structure`` フェーズ(0.009秒)で ``UNKNOWN_OUTLINE_SELF_INTERSECTS`` ──
``run()`` はそこで止まり、``hops`` は1行だけ、``failed_hop: "structure"``。

実測した身体より明らかに狭い輪郭(半幅を全高でほぼ3px[肩だけ4px]に固定した
「鉛筆」形、41点/辺、キャンバス200×2000)は ``structure``/``mannequin``/
``calibration`` を無事通り(肩のknee検出もウエスト検出もscale計算も輪郭の
太さそのものには依存しない)、``silhouette_match`` で
``UNKNOWN_SILHOUETTE_UNREACHABLE``(``worst``: ``y=0.0cm``(腰)で
``bound="min"`` を ``11.689cm`` 超過、``ease_cm=-11.689``、輪郭が言う
半幅3.27cmに実測の腰半幅14.96cmが入らない)── 実測した身体が、写真の
言う輪郭の中に入らない、という「no body in range」の実例。

**この鎖が実際に写真から導く分量 ── 実測した数字で言う。**

``silhouette.match`` は既定で人台の全域(``body_lo``〜``body_hi``、腰〜
襟ぐり)だけを解く。人台にそれより下(スカートのフレア・実際の裾)の
身体は無い(``mannequin.radius_at`` がNoneを返す範囲)ので、**輪郭が
そこに何を写していても、``panels.to_pieces()`` が返す裁片には一切乗ら
ない。** 上のA-line実測でこれを数で言うと: 輪郭は t=0(フレーム最上部)
〜t=1(裾)の全域を持つが、較正が実際に使うのは肩(t≈0.15)〜人台の腰
に対応する高さ(t≈0.4851、上のcalibration実測から逆算)まで ── **輪郭
の縦方向の広がりのうち、約33.5ポイント分(t=0.15〜0.4851)だけが型紙に
届き、残り約51.5ポイント分(t=0.4851〜1.0、真のA-lineフレアから裾まで)
は較正にも``silhouette.match``にも一度も渡らない。** できあがる裁片は
「A-lineドレス」ではなく「肩〜腰の胴体ブロック」で、スカートの広がりも
実際の着丈も持っていない。

そのt≈0.15〜0.4851の範囲でも、``silhouette.match`` が解くのは高さごとの
ease(y) 一個だけ ── 輪郭の投影幅(左右)と人台の断面幅の差。それを全周
へ一様に足すので、**幅の起伏(肩の張り出し、ウエストの絞り)は輪郭が
決めるが、奥行・断面の形(前後の厚み比、楕円の向き)は人台の
``DEPTH_RATIO=0.70`` という仮定のまま**で、輪郭は一度もそこに触れない。
較正の仮定(上記1)により、**丈そのもの(何cm長いか)も輪郭は決めない**
── 決めるのは人台の ``body_length`` と ``0.25``/``0.62`` という既存の
仮定比率で、輪郭が言えるのは「肩から腰までのうち、どの高さで幅がどう
変わるか」という**比率**だけ。ダーツの深さ(``panels.
DEFAULT_DART_DEPTH_RATIO``)も解剖学的根拠のない既定値のまま。

**一文で言えば: 輪郭が決めるのは、肩から腰までという人台の胴体の範囲に
限った、高さ方向の幅プロファイルだけ。それより下(スカートのフレア・
実際の裾)は輪郭に何が写っていても型紙に届かず、丈の絶対値・奥行・
ダーツの深さ・断面の形は人台とこのモジュールの既定値が決めている。**
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import base_garment as _bg          # noqa: F401  (silhouette.to_surface が使う。直接は呼ばない)
from . import flatten as _flat
from . import mannequin as _mq
from . import mannequin_spline as _mqs
from . import panels as _panels
from . import silhouette as _sil
from . import structure as _structure

Vec2 = Tuple[float, float]

#: 肩が輪郭から解決できず、px→cm の足場が無い。
NO_SHOULDER_ANCHOR = "UNKNOWN_NO_SHOULDER_ANCHOR_FOR_SCALE"
#: 肩〜裾のpx方向の幅、または人台の腰〜襟ぐりのcm方向の幅が実質ゼロ。
DEGENERATE_SCALE = "UNKNOWN_DEGENERATE_PHOTO_SCALE"
#: ``measures`` が ``Measures`` と同じ形をしていない。
BAD_MEASURES = "UNKNOWN_BAD_MEASURES"

_EPS = 1e-6


# ---------------------------------------------------------------------------
# 較正: px(structure の座標系) -> cm(mannequin/silhouette の座標系)
# ---------------------------------------------------------------------------

def _calibrate(structure_out: Dict[str, Any], man: Dict[str, Any]
              ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """肩→襟ぐりを固定の第一の足場にし、第二の足場は**ウエストが解決
    していればウエスト**(人台の実際のウエスト高、``_levels[1]``)、
    無ければ**裾(bboxの最下端)→腰**へ後退する。等方スケール(縦横同じ
    px→cm比)で写す。

    **なぜウエストを優先するか。** 人台(``mannequin.build``)が持つ身体は
    腰〜襟ぐりの胴体だけで、それより下(スカートのフレア・裾)には
    ``radius_at`` が None を返す ── そこは元から model の外。肩〜裾の
    px 距離を腰〜襟ぐりの cm 距離へ一様に引き伸ばす(旧版の較正)と、
    ウエストより下の丈が長い服(この道具が実際にテストしたA-lineドレス
    で実測)ほど、輪郭自身のウエストのくびれが人台のバスト付近まで
    押し上げられ、そこでは人台の方が太いので ``ease`` が負に落ちて
    ``UNKNOWN_SILHOUETTE_UNREACHABLE`` に落ちた(実測: 較正の相違だけで
    9/17リングが破綻)。ウエストを第二の足場にすれば、輪郭のウエストは
    必ず人台のウエストに合う ── その代わり、**裾から先(ウエストより下)
    は人台に元から身体が無い範囲なので、この較正がどう伸縮させても
    ``silhouette.match`` の既定範囲(腰〜襟ぐり)には最初から入らない**
    ── フレアそのものはこのチェーンの外。

    **この仮定はモジュール docstring に明記した通り検証していない。**
    定規もサイズ表記も写真には無いので、これ以外に px を cm に変換する
    材料がこのチェーンには無い。
    """
    landmarks = structure_out["landmarks"]
    shoulder = landmarks["shoulder"]
    if "y_px" not in shoulder:
        return None, {
            "verdict": NO_SHOULDER_ANCHOR,
            "upstream": shoulder,
            "why": "px→cm の較正は肩の y_px を第一の足場にする。この輪郭"
                   "では structure.from_outline が肩線を解決できなかった "
                   "(landmarks.shoulder.verdict="
                   f"{shoulder.get('verdict')})",
            "how_to_close": "肩線が幅の折れとして写る角度で撮り直すか、"
                            "肩の y_px を人が宣言してください",
        }
    levels = man["_levels"]
    body_lo, body_hi = float(levels[0][0]), float(levels[-1][0])
    waist_level_cm = float(levels[1][0])
    y_top_px = float(shoulder["y_px"])

    waist = landmarks.get("waist", {})
    if "y_px" in waist and float(waist["y_px"]) > y_top_px:
        y_second_px = float(waist["y_px"])
        cm_second = waist_level_cm
        anchor_kind = "shoulder_to_waist"
    else:
        y_second_px = float(structure_out["bbox_px"]["max_y"])
        cm_second = body_lo
        anchor_kind = "shoulder_to_hem_fallback"

    span_px = y_second_px - y_top_px
    span_cm = body_hi - cm_second
    if span_px <= _EPS or span_cm <= _EPS:
        return None, {
            "verdict": DEGENERATE_SCALE,
            "anchor_kind": anchor_kind,
            "span_px": round(span_px, 4),
            "span_cm": round(span_cm, 4),
            "why": "肩〜第二の足場のpx方向の幅、またはそれに対応する人台"
                   "側のcm方向の幅が実質ゼロで、px→cmの縮尺を計算できま"
                   "せん",
            "how_to_close": "肩線と(ウエストまたは裾)がどちらも輪郭に"
                            "現れる写真を渡すか、実測(body_length等)を"
                            "確認してください",
        }
    scale = span_cm / span_px
    axis_x_px = float(structure_out["symmetry"]["axis_x_px"])
    return {
        "axis_x_px": axis_x_px,
        "y_top_px": y_top_px, "y_second_px": y_second_px,
        "anchor_kind": anchor_kind,
        "scale_cm_per_px": round(scale, 6),
        "body_lo_cm": body_lo, "body_hi_cm": body_hi,
        "waist_level_cm": waist_level_cm,
        "assumption": (
            "肩(landmarks.shoulder.y_px)を人台の襟ぐり(body_hi)に、"
            f"第二の足場({anchor_kind})を対応する人台の高さ"
            f"({round(cm_second, 2)}cm)に合わせ、その間を等方スケール"
            "(縦横同じpx→cm比)で写す。定規もサイズ表記も写真には無いの"
            "で、この仮定なしにはpxをcmに変換する方法がこのモジュールに"
            "は無い。shoulder_to_hem_fallback のときは、丈の長いドレスの"
            "裾は腰の高さへ圧縮され、丈の短いトップスの裾は腰よりずっと"
            "下へ引き伸ばされる ── どちらも実際の丈ではない。"
            "shoulder_to_waist のときも、ウエストより下(裾・フレア)は"
            "人台に元から身体が無い範囲なので、そこは較正の対象にすら"
            "なっていない"),
    }, None


def _outline_fraction_used(structure_out: Dict[str, Any], calib: Dict[str, Any]
                           ) -> Optional[Dict[str, Any]]:
    """輪郭の縦方向の広がり(bbox の min_y〜max_y、``structure`` の
    height_fraction=0〜1)のうち、実際に ``silhouette.match`` の既定範囲
    (人台の腰〜襟ぐり)へ写る区間だけを、**この呼び出し自身の較正値から**
    計算する。ハードコードした数字ではない ── ドキュストリングの CEILING
    実測はこの関数が返した値をそのまま書き写したもの。
    """
    bbox = structure_out["bbox_px"]
    span_px = float(bbox["max_y"]) - float(bbox["min_y"])
    if span_px <= _EPS or calib["scale_cm_per_px"] <= _EPS:
        return None
    y_hip_px = calib["y_top_px"] + calib["body_hi_cm"] / calib["scale_cm_per_px"]
    y_low = max(float(bbox["min_y"]), calib["y_top_px"])
    y_high = min(float(bbox["max_y"]), y_hip_px)
    used_px = max(0.0, y_high - y_low)
    return {
        "outline_height_fraction_start": round(
            (y_low - float(bbox["min_y"])) / span_px, 4),
        "outline_height_fraction_end": round(
            (y_high - float(bbox["min_y"])) / span_px, 4),
        "outline_height_fraction_used": round(used_px / span_px, 4),
        "why": ("silhouette.match の既定範囲は人台の腰〜襟ぐりだけ"
                "(mannequin.radius_at がそれより下でNoneを返すため)。"
                "輪郭のこの高さ区間の外は、写っていても panels.to_pieces()"
                "の裁片には一切乗らない"),
    }


def _map_point(p: Sequence[float], calib: Dict[str, Any]) -> Vec2:
    x_px, y_px = float(p[0]), float(p[1])
    x_cm = (x_px - calib["axis_x_px"]) * calib["scale_cm_per_px"]
    y_cm = calib["body_hi_cm"] - (y_px - calib["y_top_px"]) * calib["scale_cm_per_px"]
    return (x_cm, y_cm)


# ---------------------------------------------------------------------------
# 各ホップの記帳
# ---------------------------------------------------------------------------

def _hop(name: str, verdict: Optional[str], count: int, seconds: float
        ) -> Dict[str, Any]:
    return {"hop": name, "verdict": verdict, "count": count,
            "seconds": round(seconds, 4)}


def _refuse(hop_name: str, sub_result: Dict[str, Any],
           hops: List[Dict[str, Any]], t_start: float) -> Dict[str, Any]:
    """下流の拒否をそのまま持って上がる。**新しい verdict 名に化けない。**"""
    out = dict(sub_result)
    out["failed_hop"] = hop_name
    out["hops"] = hops
    out["total_seconds"] = round(time.perf_counter() - t_start, 4)
    return out


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def run(record: Dict[str, Any], measures: Any, *,
        n_panels: int = 4, segments: int = 24, height_steps: int = 16,
        iterations: int = _flat.DEFAULT_ITERATIONS,
        step: float = _flat.DEFAULT_STEP,
        dart_depth_ratio: float = _panels.DEFAULT_DART_DEPTH_RATIO,
        smooth: bool = False, image_id: str = "") -> Dict[str, Any]:
    """THE OUTLINE CONTRACT ちょうど1個 + 実測(``measures``)から、
    ``panels.to_pieces()`` と同じ形の裁片を返す一回の呼び出し。

    ``smooth=True`` で ``mannequin_spline.build``(単調エルミート補間、
    折れ目なし)を使う。既定は ``mannequin.build``(直線補間)── この
    リポジトリの他の幾何チェーン(``mcp.py`` の ``flatten_build`` /
    ``panels_cut`` など)と同じ既定に揃えている。

    途中で止まったら、返り値の ``failed_hop`` がどのホップで止まったかを
    名指しし、``hops`` にそこまでの各ホップの verdict・count・seconds が
    残る。止まった理由そのものは下流モジュールの verdict をそのまま運ぶ
    ── ここで新しい名前には化けない(``NO_SHOULDER_ANCHOR`` /
    ``DEGENERATE_SCALE`` / ``BAD_MEASURES`` の3つだけがこのファイル自身の
    拒否)。
    """
    t_start = time.perf_counter()
    hops: List[Dict[str, Any]] = []

    if not hasattr(measures, "entries"):
        out = {
            "verdict": BAD_MEASURES,
            "why": "measures は Measures と同じ形( .entries を持つ)で"
                   "なければなりません",
            "how_to_close": "photoloset.garment_measure.Measures のインス"
                            "タンスを渡してください",
        }
        out["failed_hop"] = "measures_shape"
        out["hops"] = hops
        out["total_seconds"] = round(time.perf_counter() - t_start, 4)
        return out

    # ---- 1. structure: 輪郭 -> ランドマーク ----------------------------
    t0 = time.perf_counter()
    st = _structure.from_outline(record, image_id=image_id)
    hops.append(_hop("structure", st.get("verdict"),
                     len(st.get("width_profile", []))
                     if st.get("verdict") == "ANSWER" else 0,
                     time.perf_counter() - t0))
    if st.get("verdict") != "ANSWER":
        return _refuse("structure", st, hops, t_start)

    # ---- 2. mannequin: 実測 -> 人台 ------------------------------------
    t0 = time.perf_counter()
    build_fn = _mqs.build if smooth else _mq.build
    man = build_fn(measures)
    hops.append(_hop("mannequin", man.get("verdict"),
                     man.get("vertices", 0), time.perf_counter() - t0))
    if man.get("verdict") != "ANSWER":
        return _refuse("mannequin", man, hops, t_start)

    # ---- 3. calibration: px -> cm(このファイルだけの仕事) -------------
    t0 = time.perf_counter()
    calib, refusal = _calibrate(st, man)
    hops.append(_hop("calibration", "ANSWER" if calib else refusal["verdict"],
                     1 if calib else 0, time.perf_counter() - t0))
    if calib is None:
        assert refusal is not None
        return _refuse("calibration", refusal, hops, t_start)

    outline_cm = [_map_point(p, calib) for p in record["outline"]]

    # ---- 4. silhouette.match: 高さごとの ease を解く -------------------
    t0 = time.perf_counter()
    match_res = _sil.match(man, outline_cm, segments=segments,
                           height_steps=height_steps)
    hops.append(_hop("silhouette_match", match_res.get("verdict"),
                     height_steps + 1, time.perf_counter() - t0))
    if match_res.get("verdict") != "ANSWER":
        return _refuse("silhouette_match", match_res, hops, t_start)

    rf = _sil.radius_at_for(match_res)

    # ---- 5. base_garment: フィットした3次元メッシュ(可視化・検算用) ---
    t0 = time.perf_counter()
    surface = _sil.to_surface(match_res, man)   # gap=0.0 が to_surface の既定
    hops.append(_hop("base_garment_surface", surface.get("verdict"),
                     surface.get("vertices", 0), time.perf_counter() - t0))
    if surface.get("verdict") != "ANSWER":
        return _refuse("base_garment_surface", surface, hops, t_start)

    # ---- 6. flatten.build: 筒1枚に平面化、歪みを測る -------------------
    # **gap=0.0 を明示する。** rf は既にフィット済みのease分を含むので、
    # flatten.build の既定 gap(=mannequin.GAP_CM=1.0cm)をそのまま重ねる
    # と二重にゆるみを足す(モジュール docstring の「繋ぎ目で見つかった
    # ずれ2」)。
    t0 = time.perf_counter()
    flat_res = _flat.build(man, gap=0.0, segments=segments,
                           height_steps=height_steps, radius_at=rf,
                           iterations=iterations, step=step)
    hops.append(_hop("flatten", flat_res.get("verdict"),
                     flat_res.get("triangles", 0), time.perf_counter() - t0))
    if flat_res.get("verdict") != "ANSWER":
        return _refuse("flatten", flat_res, hops, t_start)

    # ---- 7. panels.cut: 歪み最悪の場所で切る ---------------------------
    # 同じ理由で gap=0.0 を明示する。
    t0 = time.perf_counter()
    cut_res = _panels.cut(man, n_panels=n_panels, segments=segments,
                          height_steps=height_steps, gap=0.0, radius_at=rf,
                          iterations=iterations, step=step,
                          dart_depth_ratio=dart_depth_ratio)
    hops.append(_hop("panels_cut", cut_res.get("verdict"),
                     cut_res.get("n_panels_reached", 0),
                     time.perf_counter() - t0))
    if cut_res.get("verdict") != "ANSWER":
        return _refuse("panels_cut", cut_res, hops, t_start)

    # ---- 8. panels.to_pieces: garment_pattern.draft() と同じ形 ---------
    t0 = time.perf_counter()
    pieces_res = _panels.to_pieces(cut_res)
    hops.append(_hop("panels_to_pieces", pieces_res.get("verdict"),
                     len(pieces_res.get("pieces", [])),
                     time.perf_counter() - t0))
    if pieces_res.get("verdict") != "ANSWER":
        return _refuse("panels_to_pieces", pieces_res, hops, t_start)

    total_seconds = time.perf_counter() - t_start
    used = _outline_fraction_used(st, calib)
    if used is None:
        ceiling_text = (
            "silhouette.match が解くのは高さごとの ease(y) 一個だけ ── "
            "輪郭の投影幅と人台の断面幅の差。奥行・断面の形は mannequin."
            "DEPTH_RATIO=0.70 という仮定のまま輪郭は触れない。丈そのもの"
            "も較正の assumption が決める比率で、輪郭は言わない")
    else:
        ceiling_text = (
            "輪郭の縦方向の広がり(height_fraction 0〜1)のうち、実際に "
            f"型紙へ届いたのは {used['outline_height_fraction_start']}〜"
            f"{used['outline_height_fraction_end']}(幅にして "
            f"{used['outline_height_fraction_used']*100:.1f}ポイント分)"
            "だけ ── それより下(人台に身体が無い高さ、多くの場合フレア"
            "や実際の裾)は輪郭に何が写っていても panels.to_pieces() の"
            "裁片に一切乗らない。その区間の中でも silhouette.match が"
            "解くのは高さごとの ease(y) 一個(輪郭の投影幅と人台の断面幅"
            "の差)だけで、幅の起伏は輪郭が決めるが、奥行・断面の形は"
            "mannequin.DEPTH_RATIO=0.70 という仮定のまま。丈そのもの"
            "(何cmか)も較正の assumption(mannequin.py の body_length と"
            "レベル比率)が決め、輪郭は『どの高さで幅がどう変わるか』と"
            "いう比率しか言わない。ダーツの深さ(panels.DEFAULT_DART_"
            "DEPTH_RATIO)も解剖学的根拠のない既定値のまま")
    return {
        "verdict": "ANSWER",
        "what": "a photographed outline, carried through structure -> "
                "silhouette match -> flatten -> panel cut, to pieces in "
                "the same shape garment_pattern.draft() returns",
        "hops": hops,
        "total_seconds": round(total_seconds, 4),
        "calibration": calib,
        "outline_fraction_used": used,
        "structure_summary": {
            "landmarks": st["landmarks"],
            "instances": st["instances"],
            "coverage": st["coverage"],
        },
        "silhouette_match_summary": {
            "ease_range_cm": match_res["ease_range_cm"],
            "width_residual_cm": match_res["width_residual_cm"],
        },
        "flatten_summary": {
            "area_ratio": flat_res["area_ratio"],
            "angle_error_deg": flat_res["angle_error_deg"],
            "relaxation": flat_res["relaxation"],
        },
        "panels_cut_summary": {
            "seam_log": cut_res["seam_log"],
            "distortion_index_before_any_additional_cut":
                cut_res["distortion_index_before_any_additional_cut"],
            "distortion_index_after_all_cuts":
                cut_res["distortion_index_after_all_cuts"],
            "distortion_bought_total_pct": cut_res["distortion_bought_total_pct"],
            "gauss_bonnet_across_all_panels_deg":
                cut_res["gauss_bonnet_across_all_panels_deg"],
            "gauss_bonnet_expected_deg": cut_res["gauss_bonnet_expected_deg"],
        },
        "pieces": pieces_res["pieces"],
        "seam_specs": pieces_res["seam_specs"],
        "placement": pieces_res["placement"],
        "total_area_cm2": cut_res["total_area_cm2"],
        "ceiling": ceiling_text,
        "generated_not_evidence": (
            "この裁片は生成物です。観測の出典にはなりません。写真1枚が"
            "拘束するのは投影幅だけで、それ以外(奥行・丈の絶対値・断面の"
            "形・ダーツの位置)はここまでのモジュールが既に持っていた"
            "仮定です"),
    }
