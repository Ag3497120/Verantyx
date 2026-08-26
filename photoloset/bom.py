# -*- coding: utf-8 -*-
"""買うものの一覧（部材表）。**これ一着を作るのに、何を買えばいいか。**

生産管理システムではない。正直な最小限で、分からないものは分からないと
言う。

型紙と裁断枚数から分かるのは三つのうち一つだけ本当の数で、残り二つは
**この道具の外の情報が要る。**

1. **生地。** ``marker.lay()`` が出す長さと幅。これは実数。ここでは
   その数をそのまま運ぶだけで、独自には作り直さない — 二重に計算すれば
   マーカーが動いたときにここが追随しない事故が起きる。
2. **糸。** 縫い目の長さは型紙から出せる（``seam_checks`` にある辺と、
   袖下線のように比較対象がなくて ``seam_checks`` に載らない辺を足す）。
   ただし**縫い目の長さから糸の使用量への比は、この道具の外の値**。
   ロックステッチは経験則で縫い目長の 2.5〜3 倍と言われるが、ステッチの
   種類・密度・糸の太さで変わり、このプロジェクトはそのどれも記録して
   いない。**だから比は既定値を持たない。** 呼び出し側が言わなければ
   ``UNKNOWN_THREAD_RATIO_NOT_STATED`` で拒否し、言えば比を出力に刻んで
   使う — 比を変えれば答えが変わることで、それが本当に使われている値だと
   確かめられるようにする。
3. **付属品（ボタン・ジップ・フック等）と接着芯。** 型紙はどちらも
   記録していない。輪郭からボタンの数を推測する手段はない — 何を付ける
   かは製作の決定で、この道具の管掌外。宣言してもらい、そのまま運ぶ。

**合計は出さない。** 生地はメートル、糸はメートル、付属品は個数で、
どれにも価格が付いていない。単位の違う数を足しても意味のある一つの数に
ならないし、値段のない BOM の「合計」は空欄を隠すのに向いている。だから
``known``（分かっている行）と ``refused``（拒否した行、なぜ拒否したかと
埋め方つき）を並べて返す。``complete`` を見ずに ``known`` だけを読めば、
付属品もない服が静かに完成した部材表として読めてしまう — それを許さない。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import marker as _marker

NO_NOTIONS = "UNKNOWN_NOTIONS_NOT_DECLARED"
NO_INTERFACING = "UNKNOWN_INTERFACING_NOT_DECLARED"
NO_THREAD_RATIO = "UNKNOWN_THREAD_RATIO_NOT_STATED"

#: 糸の消費比は経験則の**範囲**であって値ではない。既定値としては使わない
#: — ``how_to_close`` の中でだけ、呼び出し側が選ぶ材料として示す。
THREAD_RATIO_GUIDANCE = (
    "ロックステッチはおおむね縫い目長の2.5〜3倍が経験則(業界の目安で、"
    "検証済みの出典があるわけではない)。ステッチの種類・密度・糸の太さ"
    "で変わり、このプロジェクトはそのいずれも記録していないので、比は"
    "ここでは選ばない。決めて thread_ratio に渡してください")


def _seam_length_cm(draft: Dict[str, Any]) -> Tuple[float, List[str]]:
    """型紙から縫い目の長さを足す。**型紙が持っている辺だけを読む。**

    ``seam_checks`` は前後を突き合わせる辺（肩線・脇線・袖山と袖ぐり）を
    持つが、袖下線は比べる相手がない自分自身の折り返しなので、そこには
    載らない。``袖`` 裁片の辺から直接読む。無ければ足さない — 拒否せず、
    ただその分は無い。

    **左右を二倍しない。** 身頃はここでは半身（chest ÷ half_divisor）
    として引かれており、実物の一着は肩線・脇線がそれぞれ左右で二回ずつ
    現れるはずだが、「半身対称だから二倍してよい」は ``garment_pattern``
    のどこにも明記された宣言ではない。無断でその仮定を足すと、後で
    非対称な型紙が来たときに静かに間違う。ここは型紙に**書いてある**辺の
    長さだけを合計し、二倍が要るかどうかは呼び出し側の判断に残す。
    """
    total = 0.0
    parts: List[str] = []
    for sc in draft.get("seam_checks") or []:
        length = float(sc.get("length_a") or 0.0)
        total += length
        parts.append(f'{sc.get("label", "?")}: {length} cm')
    for p in draft.get("pieces") or []:
        edge = (p.get("edges") or {}).get("袖下線 (右)")
        if edge:
            length = float(edge.get("length") or 0.0)
            total += length
            parts.append(f'{p.get("name", "?")}/袖下線: {length} cm')
    return round(total, 2), parts


def estimate(draft: Dict[str, Any], fabric_width_cm: float,
             cut: Dict[str, int], seam_allowance_cm: float,
             thread_ratio: Optional[float] = None,
             notions: Optional[Dict[str, Any]] = None,
             interfacing: Optional[Dict[str, Any]] = None,
             nap: Optional[str] = None) -> Dict[str, Any]:
    """一着分の部材表。**分かる行と拒否した行を並べて返す。**

    生地は ``marker.lay()`` に丸投げする — ここで独自に計算し直すと、
    マーカーの計算が変わったときにこちらが追随しない食い違いが起きる。
    生地が拒否すれば（枚数・幅・縫い代のいずれか未定）、BOM 全体をその
    まま拒否で返す。生地の量が分からないのに糸や付属品の行だけ返すのは、
    土台のない部材表を「答えた」ことにしてしまう。
    """
    mk = _marker.lay(draft, fabric_width_cm, cut, seam_allowance_cm, nap=nap)
    if mk.get("verdict") != "ANSWER":
        return {**mk, "note": "生地が決まらないと部材表は組めません"}

    seam_len, seam_parts = _seam_length_cm(draft)

    known: Dict[str, Any] = {
        "fabric": {
            "quantity": mk["length_m"],
            "unit": "m",
            "width_cm": mk["fabric_width_cm"],
            "utilisation_pct": mk["utilisation_pct"],
            "source": "marker.lay() — ここでは作り直さない",
            "nap": mk["nap"],
            "nap_changes_nothing_here": mk["nap_changes_nothing_here"],
        },
    }
    refused: Dict[str, Any] = {}

    if thread_ratio is None or thread_ratio <= 0:
        refused["thread"] = {
            "verdict": NO_THREAD_RATIO,
            "seam_length_cm": seam_len,
            "seam_parts": seam_parts,
            "how_to_close": THREAD_RATIO_GUIDANCE,
        }
    else:
        ratio = float(thread_ratio)
        known["thread"] = {
            "quantity": round(seam_len * ratio / 100.0, 3),
            "unit": "m",
            "seam_length_cm": seam_len,
            "seam_parts": seam_parts,
            "consumption_ratio": ratio,
            "assumption": (
                f"糸の使用量 = 縫い目長 {seam_len} cm × 比 {ratio}。"
                "比はこの道具の外から渡された値で、ここでは検証していません。"
                + THREAD_RATIO_GUIDANCE),
        }

    if not notions:
        refused["notions"] = {
            "verdict": NO_NOTIONS,
            "how_to_close": ("ボタン・ジップ・フックなど、何を何個使うか"
                             "を declare してください。型紙は輪郭しか持たず、"
                             "そこからボタンの数を推測する手段はありません。"
                             '例: {"ボタン": 6, "ジップ": 1}'),
        }
    else:
        known["notions"] = {"items": dict(notions),
                            "source": "呼び出し側が宣言。ここでは導出していません"}

    if not interfacing:
        refused["interfacing"] = {
            "verdict": NO_INTERFACING,
            "how_to_close": ("どの裁片に接着芯を貼るかは製作側の決定で、"
                             "型紙には記録がありません。裁片名をキーに宣言"
                             'してください。例: {"衿": "接着芯 中厚"}'),
        }
    else:
        known["interfacing"] = {"items": dict(interfacing),
                                "source": "呼び出し側が宣言。ここでは導出していません"}

    return {
        "verdict": "ANSWER",
        "known": known,
        "refused": refused,
        "completeness": {
            "complete": not refused,
            "known_lines": sorted(known.keys()),
            "refused_lines": sorted(refused.keys()),
        },
        "no_total": ("合計は出しません。生地はメートル、糸はメートル、"
                     "付属品は個数で、どれにも価格が付いていません。"
                     "known だけを読んで completeness を見なければ、"
                     "付属品のない服が静かに完成した部材表に見えます"),
    }
