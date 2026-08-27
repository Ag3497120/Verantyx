# -*- coding: utf-8 -*-
"""滑らかな人台。**同じ5レベルを、折れ目なしで通す。**

``mannequin.build`` は5レベル(腰・胴・胸・肩・襟ぐり)を直線で結ぶ。これは
決定的で速いが、レベルとレベルの間に折れ目(接線が不連続な線)を作る —
``curvature.report`` の ``honest_limit`` が測って名指ししている通り、
曲率はそこに集中する。

**ここでやること。** 同じ5レベル(``mannequin.build`` が出す ``_levels``、
実測から作られる制御点そのもの)を、単調三次エルミート補間
(Fritsch–Carlson, 1980)で結ぶ。制御点は増やさない — 増えるのは実測が
増えたときだけで、ここは「同じ入力をどう結ぶか」だけを変える。

**単調にする理由。** 三次補間は制御点の間で行き過ぎる(オーバーシュート)
ことがある — 胸と腰の間に、どちらの実測にもない膨らみを作ってしまう。
Fritsch–Carlson は各区間の接線を、隣り合う区間の傾き(secant)から
外れないように制限するので、行き過ぎない。ブリーフの言葉で言えば
「実測の間で勝手に膨らまない」。

**境界の接線は直線版と一致する。** 最初と最後の区間の接線は secant
そのもの(``mannequin.build`` が直線で使う傾きと同じ)にしている。これは
Gauss-Bonnet の境界項を直線版と揃えるための選択で、恣意的ではない —
``curvature_comparison`` が測る「合計は一致に近づき、帯別分布だけが違う」
という結果は、この選択があって初めて成り立つ。境界の接線を変えれば境界
測地曲率が変わり、合計もズレる。この選択自体もブリーフの言う「仮定」の
一つとして、ここに明記する。

**このモジュールは ``mannequin`` を置き換えない。** ``radius_at`` は同じ
契約(範囲外は None)を守るので、``curvature.mesh``/``curvature.report``/
``base_garment.build`` はどちらの補間か知らずに使える — 呼ぶ側が選ぶ。
"""
from __future__ import annotations

import bisect
import functools
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import mannequin as _mq

Level = Tuple[float, float, float]

TOO_FEW_LEVELS = "UNKNOWN_NEEDS_AT_LEAST_TWO_LEVELS"

#: ``mannequin.build`` の ``STEPS_Y`` は関数内のローカル変数でモジュール
#: 定数ではないので、ここで同じ値を独立に持つ。``mannequin.SEGMENTS`` は
#: モジュール定数なのでそのまま読む — 周方向の刻みは合わせておかないと
#: 見た目のメッシュを比べるとき片方だけ粗くなる。
STEPS_Y = 16


def _fritsch_carlson(xs: Sequence[float], ys: Sequence[float]
                     ) -> List[float]:
    """各制御点の接線(傾き)を、行き過ぎない値に制限して返す。

    Fritsch & Carlson (1980)。まず両隣の secant の平均を仮の接線とし
    (符号が反転する点=極値では 0 — そこは水平でなければ行き過ぎる)、
    次に隣接区間ごとに接線と secant の比 (α, β) が α²+β²>9 のとき
    比を落として円の内側に収める。これが「単調」の中身で、証明は
    原論文にある。ここでは実装するだけで、証明はしない。
    """
    n = len(xs)
    if n < 2:
        return [0.0] * n
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [0.0] * n
    m[0] = d[0]
    m[-1] = d[-1]
    for i in range(1, n - 1):
        if d[i - 1] == 0.0 or d[i] == 0.0 or (d[i - 1] > 0) != (d[i] > 0):
            m[i] = 0.0          # 極値。水平にしないと必ず行き過ぎる
        else:
            m[i] = (d[i - 1] + d[i]) / 2.0
    for i in range(n - 1):
        if d[i] == 0.0:
            m[i] = 0.0
            m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        s = a * a + b * b
        if s > 9.0:
            t = 3.0 / math.sqrt(s)
            m[i] = t * a * d[i]
            m[i + 1] = t * b * d[i]
    return m


def _hermite(x0: float, x1: float, y0: float, y1: float,
            m0: float, m1: float, x: float) -> float:
    """3次エルミート基底での評価。区間 [x0,x1] の外は呼ばない前提。"""
    h = x1 - x0
    t = (x - x0) / h
    t2, t3 = t * t, t * t * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    return h00 * y0 + h10 * h * m0 + h01 * y1 + h11 * h * m1


@functools.lru_cache(maxsize=16)
def _slopes(levels: Tuple[Level, ...]
           ) -> Tuple[Tuple[float, ...], Tuple[float, ...]]:
    """5レベルぶんの接線を一度だけ計算してキャッシュする。

    メッシュを細かくすると同じ ``levels`` に対して数十万回 ``radius_at``
    が呼ばれる。呼ぶたびに Fritsch–Carlson をやり直すのは正しいが遅い
    ―― ``levels`` は5点のタプルなので、キャッシュ鍵として安全(実測が
    変われば別のタプルになり、別のキャッシュ枠に乗る)。
    """
    ys = tuple(lv[0] for lv in levels)
    return (tuple(_fritsch_carlson(ys, tuple(lv[1] for lv in levels))),
            tuple(_fritsch_carlson(ys, tuple(lv[2] for lv in levels))))


def _ab_at(levels: Sequence[Level], y: float) -> Tuple[float, float]:
    key = tuple((float(lv[0]), float(lv[1]), float(lv[2])) for lv in levels)
    slopes_a, slopes_b = _slopes(key)
    ys = [lv[0] for lv in levels]
    lo = max(0, min(len(ys) - 2, bisect.bisect_right(ys, y) - 1))
    hi = lo + 1
    a = _hermite(ys[lo], ys[hi], levels[lo][1], levels[hi][1],
                slopes_a[lo], slopes_a[hi], y)
    b = _hermite(ys[lo], ys[hi], levels[lo][2], levels[hi][2],
                slopes_b[lo], slopes_b[hi], y)
    return a, b


def radius_at(man: Dict[str, Any], y: float,
              theta: float) -> Optional[float]:
    """``mannequin.radius_at`` と同じ契約 — 範囲外・身体が無い高さは None。

    違いは範囲の**中**だけ: レベルの間を直線ではなく単調エルミートで結ぶ。
    ``man`` は ``mannequin.build`` の出力(または ``_levels`` を持つ同型の
    辞書)であればどちらでもよい ―― このモジュールは ``_levels`` しか
    読まない。
    """
    if man.get("verdict") != "ANSWER":
        return None
    levels = man["_levels"]
    if len(levels) < 2:
        return None
    if y < levels[0][0] - 1e-9 or y > levels[-1][0] + 1e-9:
        return None
    a, b = _ab_at(levels, y)
    return _mq._ellipse_radius(a, b, theta)


def build(measures: Any) -> Dict[str, Any]:
    """``mannequin.build`` と同じ実測規則・同じ制御点で、滑らかな人台を作る。

    実測の読み方とレベルの式は ``mannequin.build`` そのもの(委譲していて、
    二重に実装していない)。変わるのはメッシュの生成に使う補間だけ。
    """
    base = _mq.build(measures)
    if base.get("verdict") != "ANSWER":
        return base
    levels = base["_levels"]
    if len(levels) < 2:
        return {"verdict": TOO_FEW_LEVELS, "levels": len(levels),
                "how_to_close": "レベルが2つ未満では補間できません"}
    y_top = levels[-1][0]
    verts: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int, int]] = []
    for j in range(STEPS_Y + 1):
        y = y_top * j / STEPS_Y
        for i in range(_mq.SEGMENTS):
            theta = 2.0 * math.pi * i / _mq.SEGMENTS
            r = radius_at(base, y, theta)
            verts.append((r * math.cos(theta), y, r * math.sin(theta)))
    for j in range(STEPS_Y):
        for i in range(_mq.SEGMENTS):
            k = (i + 1) % _mq.SEGMENTS
            faces.append((j * _mq.SEGMENTS + i, j * _mq.SEGMENTS + k,
                         (j + 1) * _mq.SEGMENTS + k,
                         (j + 1) * _mq.SEGMENTS + i))
    out = dict(base)
    out["verts"] = verts
    out["faces"] = faces
    out["interpolation"] = (
        "単調三次エルミート(Fritsch–Carlson)で同じ5レベルを結ぶ。"
        "最初と最後の区間の接線は直線版の傾き(secant)と同じにしている"
        "— 境界の測地曲率を直線版と揃えるための選択で、これも仮定")
    out["not_more_control_points"] = (
        "制御点は mannequin.build と同じ5つ。増やしたのは結び方だけ")
    return out
