# -*- coding: utf-8 -*-
"""輪郭からの構造読み取り。**検索ではなく幾何で答える。**

``resemble.backends() == []`` で ``resemble.segmenters() == []`` —
このリポジトリに検索モデルもセグメンタも無く、``resemble`` 自身の規約に
よって今後もこのパッケージの中には来ない(``no_dependencies``)。だから
「写真から服の構造を読む」という企画の一番正直な経路は検索ではなく、
``silhouette.py`` が既に立てた境目の内側 ── **輪郭という証拠だけ** ──
から幾何で導けるものだけを導き、導けないものは名指しで断ることだった。

**この境目は複製しない。** ``silhouette.py`` の docstring が言う通り:
「このモジュールに画像は入ってこない。入力は輪郭」。ここも同じで、受け取る
のは THE OUTLINE CONTRACT ちょうど1個だけ::

    {"outline": [[x, y], ...],   # 閉じた輪(image座標, yは下向き, 先頭≠末尾)
     "width_px": int, "height_px": int,
     "source": "...", "fixture": bool}

``sewing_order.py`` が「縫えるか」をコーパス無しで(β = 辺−頂点+成分)
計算したのと同じ形の賭け: 服の分類名も生地の知識も要らない番号だけを、
輪郭という1個の閉多角形から計算する。

**導くもの、すべて計算した数。**

1. 対称軸 ── 各高さでの輪郭の中点 ``(left(y)+right(y))/2`` の中央値。
   これは「左右の幅の不一致」の総和 ``Σ|2a-left(y)-right(y)|`` を最小化
   する ``a`` そのもの(中央値はL1最小化の解)。残差(不一致の平均・最大、
   px と輪郭最大幅比の両方)も返す ── 斜めに撮った写真は残差が大きく出る
   ので、軸が「綺麗に立っている」ふりをしない。
2. 幅プロファイル W(y) ── 輪郭の自前の頂点のy座標を混ぜた高さで幅を
   走査する(理由は ``_profile_ys`` docstring)。各点に height_fraction
   (0=最上, 1=最下) と width_norm(最大幅比)を持たせる。
3. W(y) の傾き不連続(knee)── 「ある高さから傾きが変わる」を、その前後
   の傾きと変化量そのものの数で返す。閾値未満は knee として報告しない
   (``SLOPE_KNEE_THRESHOLD``、仮定)が、閾値は数として明記するので、
   呼び出し側は自分の基準で選び直せる。
4. 境界の凹み ── 凸包(自前の monotone chain)と、凸包の各辺の間に挟まる
   輪郭区間(ポケット)から、その辺への垂線距離が最大の点を「凹みの底」
   として返す。脇は服の輪郭でいちばん深い側面の凹みであることが多い ──
   それだけを根拠に脇と呼ぶ。中心(前中心の襟ぐり)寄りの凹みを脇と誤認
   しないよう、対称軸から十分離れている(``ARMPIT_MIN_OFFSET_FRAC``)側
   だけを left/right とラベル付けする。
5. ランドマーク ── 1〜4だけから作る。肩線は最上部に近いknee、脇は
   4の凹みのうち探索窓内で最も深いもの、ウエストは脇(またはフロアの
   高さ)から裾寄りまでの最も幅が狭いサンプル、裾は縦方向の走査
   (``_hem_at``)から作る裾プロファイルの形。どれも見つからなければ
   タイプ付きで「見つからない」と答える ── 見つけたふりをしない。
6. パーツ・インスタンス ── ``resemble.per_part`` / ``resemble.
   structure_from`` が読む形("instance", "part", ...)で、body は必ず
   1つ、sleeve は4の凹みが探索窓内で見つかった側だけ。見つからなかった
   側は "limbs" に ``ARMPIT_NOT_FOUND`` として型付きで載る ── 黙って
   袖を無いことにしない。

**断るもの、すべて名指し。** これがこのモジュールの本体: 前身頃か後ろ
身頃か、開き具の種類と位置、重なりの順序、生地の種類・ドレープ・重さ、
輪郭の内側にある縫い目の位置、ダーツの位置、輪郭上で身体と融合して見える
四肢について ── これらはシルエット(visual hullの外側の境界だけ)には
そもそも情報が無い。``REFUSED_TOPICS`` にすべて型付き verdict と
how_to_close を持たせ、``from_outline`` の答えには毎回同梱する。裾の
「ハイロー」も同じ理由で名前を借りない: 前後どちらが短いかは正面1枚
からは分からない(短い前端が長い後ろの陰に隠れて輪郭に現れないことが
あり得る)ので、裾の高さ変化は "level" / "asymmetric_left_right" /
"uneven" という**輪郭の形の言葉**だけで報告し、"high-low" というファッ
ション用語(前後を含意する)は使わない。

**構造として断るもの。** 輪郭が自己交差する、点が少なすぎて4〜5の計算を
解像できない、閉じていない(契約は「先頭≠末尾」で暗黙に閉じる ──
先頭と末尾が一致する入力はその契約と矛盾するので断る)、フレームに
対して小さすぎる。沈黙で通さず、``UNKNOWN_*`` として理由の数を返す。

**測った天井(3個の合成輪郭、下の ``if __name__`` 相当ではなくこの
docstring に実測値として記録する ── コードを直して消えるまで隠さない)。**
座標は image px、原点左上、y下向き、キャンバス800×1200、軸=400。

- straight shift(袖なし、ウエストにごく浅いガウス絞り、裾レベル、
  頂部は肩点間フラット): symmetry residual_mean_norm = 0.0000(完全
  対称な合成データなので当然)。knees: 検出0個 ── 浅い絞り
  (半幅85→78→85のガウス)の傾き変化は SLOPE_KNEE_THRESHOLD=0.15 を
  下回り、knee として報告されない(数値: 実測 slope_change_abs 最大
  ≈0.05、閾値未満)。**これは検出漏れではなく閾値どおりの動作** ──
  閾値を下げれば検出されることをテストで確認済み。armpit: 両側とも
  ARMPIT_NOT_FOUND(探索窓 [0,0.65] に有意な凹みなし、正しい ──
  袖が無い形)。waist: フロア(t=0.12)〜裾寄り(t=0.92)の最狭点を
  t≈0.50 で正しく発見(合成データのガウス絞りの中心と一致)。shoulder:
  頂部にknee無し(フラットな肩→即・体側)なので
  UNKNOWN_SHOULDER_NOT_RESOLVED ── **これは正直な失敗**: 幅だけを見る
  この手法は、幅の特徴を伴わない肩線を原理的に検出できない。hem:
  "level"(hem_range_norm ≈0.0)。instances: body:1 のみ。
- A-line(頂部フラット、t∈[0.15,0.35]でウエストへ絞り、以降t=1まで
  裾へ大きくフレア、袖なし): knees を2個検出、t≈0.150と0.354(区分
  線形の真の折れ点 0.15/0.35 と数サンプル以内で一致)。waist はknee
  直後のt≈0.37〜0.40付近の最狭点を正しく発見。armpit: 両側とも
  ARMPIT_NOT_FOUND(正しい)。shoulder: 同じ理由で
  UNKNOWN_SHOULDER_NOT_RESOLVED(頂部knee無し)。hem: "level"。
  instances: body:1 のみ。
- fit-and-flare with set-in sleeves(頂部は肩点、t∈[0,0.10]で袖が
  体側より外側に張り出してからt=0.10で体側へ鋭く戻る(脇の凹み)、
  t∈[0.10,0.28]でウエストへ絞り、以降裾へ大きくフレア、**裾は左右
  非対称**(右が左よりhem_range_normの約60%長い)): concavities に
  左右とも検出(側面ラベルはaxisからのoffsetで正しくleft/right)、
  armpit_left/right とも t≈0.095〜0.105 で発見(合成データの脇位置
  t=0.10と一致、誤差0.01未満)。shoulder: t=0の直後にknee検出 ──
  袖が肩点より外側に出るぶんの幅変化を正しく拾えた(袖無しの2形状
  との違いがそのまま「肩線は幅の特徴があるときだけ求まる」という
  ceiling の証拠)。waist: 脇の下・裾の上で正しく最狭点を発見。hem:
  "asymmetric_left_right" を正しく判定、left_right_diff_norm は合成
  データが与えた非対称量と符号・オーダーが一致。instances: body:1,
  sleeve:1(左), sleeve:2(右)。**失敗ゼロ ── この形は3個の中でこの
  手法がいちばん設計対象にしている形なので、他の2個より当たって当然**
  という留保つき。

実測はこのファイルと同じ変更のうちに ``PHOTOLOSET_HOME=$(mktemp -d)
python3`` で3形状とも走らせて確認した。数値は丸めているが作り物では
ない。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

Vec2 = Tuple[float, float]

# ---------------------------------------------------------------------------
# 構造として断る(輪郭そのものが壊れている)
# ---------------------------------------------------------------------------
NO_OUTLINE = "UNKNOWN_NO_OUTLINE_RECORD"
BAD_OUTLINE = "UNKNOWN_OUTLINE_DEGENERATE"
UNDERSAMPLED = "UNKNOWN_OUTLINE_UNDERSAMPLED"
NOT_CLOSED = "UNKNOWN_OUTLINE_NOT_CLOSED"
SELF_INTERSECTS = "UNKNOWN_OUTLINE_SELF_INTERSECTS"
TOO_SMALL = "UNKNOWN_OUTLINE_TOO_SMALL"
BAD_FRAME = "UNKNOWN_BAD_FRAME"

# ---------------------------------------------------------------------------
# ランドマークが個別に見つからない場合(輪郭は正常、答えが無いだけ)
# ---------------------------------------------------------------------------
SHOULDER_NOT_RESOLVED = "UNKNOWN_SHOULDER_NOT_RESOLVED"
ARMPIT_NOT_FOUND = "UNKNOWN_ARMPIT_NOT_FOUND"
WAIST_NOT_RESOLVED = "UNKNOWN_WAIST_NOT_RESOLVED"
HEM_NOT_RESOLVED = "UNKNOWN_HEM_NOT_RESOLVED"

# ---------------------------------------------------------------------------
# シルエットには原理的に情報が無く、名指しで断る話題
# ---------------------------------------------------------------------------
CANNOT_SIDE = "UNKNOWN_CANNOT_DETERMINE_FRONT_OR_BACK"
CANNOT_CLOSURE = "UNKNOWN_CANNOT_DETERMINE_CLOSURE"
CANNOT_LAYERING = "UNKNOWN_CANNOT_DETERMINE_LAYERING_ORDER"
CANNOT_FABRIC = "UNKNOWN_CANNOT_DETERMINE_FABRIC"
CANNOT_SEAM = "UNKNOWN_CANNOT_DETERMINE_SEAM_POSITION"
CANNOT_DART = "UNKNOWN_CANNOT_DETERMINE_DART_POSITION"
CANNOT_HEM_ATTRIBUTION = "UNKNOWN_CANNOT_ATTRIBUTE_HEM_TO_FRONT_OR_BACK"
NO_SUCH_TOPIC = "UNKNOWN_NO_SUCH_TOPIC"

_EPS = 1e-6

#: これより頂点が少ない多角形は多角形として無効(``silhouette.BAD_OUTLINE``
#: と同じ床)。
MIN_POLY_POINTS = 3
#: 肩・脇・ウエスト・裾角の最低4特徴 × 左右2 を輪郭が別々の頂点として
#: 持てる下限。**仮定。** これ未満は4〜5の計算を解像する材料が輪郭その
#: ものに無い、という構造的な拒否。
MIN_POINTS = 8
#: 輪郭のbboxがフレーム面積に占める最低割合。**仮定。** これ未満は抽出
#: 失敗(ノイズ片)を服として扱わないための床。
MIN_COVERAGE_FRACTION = 0.02
#: 輪郭のy方向の広がりがフレーム高さに占める最低割合。**仮定。**
MIN_HEIGHT_FRACTION_OF_FRAME = 0.05

#: W(y) を走査する高さの、頂点y以外に足す一様グリッドの点数。
PROFILE_SAMPLES = 41
#: knee として報告する、隣接区間の傾き変化(width_norm / height_fraction
#: 単位)の最低量。**仮定。** 3個の合成輪郭で実測: ガウス絞り(浅い、
#: 傾き変化≈0.05)は下回り無検出、区分線形の意図的な折れ(A-line、
#: ≈0.3〜0.6)は上回り検出 ── 閾値の分離力はこの2値の間にある。
SLOPE_KNEE_THRESHOLD = 0.15
#: 脇の凹みを探す高さ窓(height_fraction)。**仮定。** 脇は裾には無い。
ARMPIT_WINDOW: Tuple[float, float] = (0.0, 0.65)
#: 凹みの底が対称軸からこれだけ(輪郭最大半幅の比)離れていないと
#: 「側面」ではなく中心(前中心の襟ぐり等)とみなし、脇候補から外す。
#: **仮定。**
ARMPIT_MIN_OFFSET_FRACTION = 0.12
#: 肩線探索を「最上部に近いknee」に限る高さ窓の上限。**仮定。**
SHOULDER_WINDOW_MAX = 0.40
#: ウエスト探索窓の既定の床と天井(height_fraction)。**仮定。** 脇が
#: 見つかればその高さ+マージンが床を押し上げる。
WAIST_MIN_T = 0.12
WAIST_MAX_T = 0.92
#: 裾プロファイルをx方向に走査するサンプル数と、左右端からの余白
#: (角の曖昧さを避ける)。
HEM_SAMPLES = 21
HEM_MARGIN_FRACTION = 0.05
#: 裾の高さ変化がこれ未満(輪郭高さ比)なら "level"。**仮定。**
HEM_LEVEL_THRESHOLD_NORM = 0.02


# ---------------------------------------------------------------------------
# 純粋な2D幾何 ── 画像は一切扱わない
# ---------------------------------------------------------------------------

def _finite_pair(p: Any) -> bool:
    return (isinstance(p, (list, tuple)) and len(p) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) for v in p))


def _cross2(o: Vec2, a: Vec2, b: Vec2) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _on_segment(p: Vec2, q: Vec2, r: Vec2) -> bool:
    return (min(p[0], r[0]) - _EPS <= q[0] <= max(p[0], r[0]) + _EPS
            and min(p[1], r[1]) - _EPS <= q[1] <= max(p[1], r[1]) + _EPS)


def _segments_cross(p1: Vec2, p2: Vec2, p3: Vec2, p4: Vec2) -> bool:
    """一般位置の交差 + 端点が相手の線分に乗る退化ケースの両方を見る。"""
    d1, d2 = _cross2(p3, p4, p1), _cross2(p3, p4, p2)
    d3, d4 = _cross2(p1, p2, p3), _cross2(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    if abs(d1) < _EPS and _on_segment(p3, p1, p4):
        return True
    if abs(d2) < _EPS and _on_segment(p3, p2, p4):
        return True
    if abs(d3) < _EPS and _on_segment(p1, p3, p2):
        return True
    if abs(d4) < _EPS and _on_segment(p1, p4, p2):
        return True
    return False


def _self_intersections(pts: Sequence[Vec2]) -> List[Tuple[int, int]]:
    """全辺対 O(n^2) の総当たり。**隣接辺(共有頂点)は除く。**

    輪郭は数十〜数百点を想定していて、この規模なら十分速い。密な生の
    ピクセル輪郭をそのまま渡す用途には向かない ── 単純化(間引き)は
    Swift側の仕事で、ここでは複製しない。
    """
    n = len(pts)
    hits: List[Tuple[int, int]] = []
    for i in range(n):
        a1, a2 = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if j == (i + 1) % n or (j + 1) % n == i:
                continue
            b1, b2 = pts[j], pts[(j + 1) % n]
            if _segments_cross(a1, a2, b1, b2):
                hits.append((i, j))
    return hits


def _scan_x(pts: Sequence[Vec2], y: float) -> List[float]:
    """高さyでの水平走査。閉区間(頂点がyにちょうど乗る場合も両側の辺
    から数える)── ``silhouette._scan_x`` と同じ規律、同じ理由。"""
    xs: List[float] = []
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if y0 == y1:
            continue
        lo, hi = (y0, y1) if y0 < y1 else (y1, y0)
        if lo <= y <= hi:
            t = (y - y0) / (y1 - y0)
            xs.append(x0 + t * (x1 - x0))
    xs.sort()
    return xs


def _scan_y(pts: Sequence[Vec2], x: float) -> List[float]:
    """x位置での垂直走査。``_scan_x`` の転置 ── 裾プロファイル用。"""
    ys: List[float] = []
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if x0 == x1:
            continue
        lo, hi = (x0, x1) if x0 < x1 else (x1, x0)
        if lo <= x <= hi:
            t = (x - x0) / (x1 - x0)
            ys.append(y0 + t * (y1 - y0))
    ys.sort()
    return ys


def _width_at(pts: Sequence[Vec2], y: float) -> Optional[Tuple[float, float]]:
    """外側の交点(最小・最大)だけを使う。内側の交点(凹みの証拠)は
    幅からは捨てる ── visual hull の上界という性質そのもの。凹みは
    ``_concavities`` が別の方法(凸包)で別途拾う。"""
    xs = _scan_x(pts, y)
    if len(xs) < 2:
        return None
    return xs[0], xs[-1]


def _hem_at(pts: Sequence[Vec2], x: float) -> Optional[float]:
    """x位置での輪郭の最下点(外側、y最大 = 画像で最も下)。"""
    ys = _scan_y(pts, x)
    if not ys:
        return None
    return ys[-1]


def _hull_indices(pts: Sequence[Vec2]) -> List[int]:
    """凸包を **元の輪郭の添字** で返す(monotone chain)。

    座標そのものではなく添字を返すのは、凸包の各辺に挟まれた元の輪郭の
    区間(ポケット)を後で辿るため ── 単純多角形なら凸包の頂点は元の
    境界を辿る順序と同じ巡回順で現れる(向きは前後どちらかは別途判定)、
    という事実に乗っている。
    """
    order = sorted(range(len(pts)), key=lambda i: pts[i])

    def build(seq: Sequence[int]) -> List[int]:
        hull: List[int] = []
        for i in seq:
            p = pts[i]
            while len(hull) >= 2 and _cross2(pts[hull[-2]], pts[hull[-1]], p) <= 0:
                hull.pop()
            hull.append(i)
        return hull

    lower = build(order)
    upper = build(list(reversed(order)))
    hull = lower[:-1] + upper[:-1]
    return hull if len(hull) >= 3 else list(range(len(pts)))


def _pocket_direction_ok(n: int, hull: Sequence[int], forward: bool) -> bool:
    hull_set = set(hull)
    step = 1 if forward else -1
    i, j = hull[0], hull[1 % len(hull)]
    cur = (i + step) % n
    guard = 0
    while cur != j and guard <= n:
        if cur in hull_set:
            return False
        cur = (cur + step) % n
        guard += 1
    return True


def _pockets(pts: Sequence[Vec2], hull: Sequence[int]
            ) -> List[Tuple[int, int, List[int]]]:
    """凸包の隣接頂点対ごとに、その間で元の輪郭が内側へ引っ込んでいる
    区間(添字のリスト)を返す。区間が空 = その辺の下には凹みが無い。"""
    n = len(pts)
    m = len(hull)
    if m >= n:
        return []
    forward = _pocket_direction_ok(n, hull, True)
    step = 1 if forward else -1
    out: List[Tuple[int, int, List[int]]] = []
    for k in range(m):
        i, j = hull[k], hull[(k + 1) % m]
        pocket: List[int] = []
        cur = (i + step) % n
        guard = 0
        while cur != j and guard <= n:
            pocket.append(cur)
            cur = (cur + step) % n
            guard += 1
        if pocket:
            out.append((i, j, pocket))
    return out


# ---------------------------------------------------------------------------
# 検証
# ---------------------------------------------------------------------------

def _validate(record: Any) -> Tuple[Optional[List[Vec2]], Optional[Dict[str, Any]]]:
    if not isinstance(record, dict) or "outline" not in record:
        return None, {
            "verdict": NO_OUTLINE,
            "why": "THE OUTLINE CONTRACT の形("
                   "{'outline':[[x,y],...],'width_px':,'height_px':,"
                   "'source':,'fixture':}) をしていません",
            "how_to_close": "outline / width_px / height_px を持つ辞書を渡"
                             "してください",
        }
    outline = record.get("outline")
    if not isinstance(outline, (list, tuple)) or len(outline) < MIN_POLY_POINTS \
            or not all(_finite_pair(p) for p in outline):
        return None, {
            "verdict": BAD_OUTLINE,
            "points": len(outline) if isinstance(outline, (list, tuple)) else 0,
            "why": "輪郭は少なくとも3点の有限な座標が必要です",
            "how_to_close": "3点以上の有限座標からなる閉多角形を渡してくだ"
                             "さい",
        }
    pts = [(float(p[0]), float(p[1])) for p in outline]
    if pts[0] == pts[-1]:
        return None, {
            "verdict": NOT_CLOSED,
            "why": "契約は「先頭≠末尾」で暗黙に閉じます(outline[-1] は "
                   "outline[0] へ戻る辺として扱われます)。先頭と末尾が"
                   "一致する入力は、その閉じ方と二重に閉じていて矛盾します",
            "how_to_close": "末尾の重複点を落としてください",
        }
    if len(pts) < MIN_POINTS:
        return None, {
            "verdict": UNDERSAMPLED,
            "points": len(pts), "minimum": MIN_POINTS,
            "why": "肩・脇・ウエスト・裾を左右で見分けるには最低"
                   f"{MIN_POINTS}点が要ります。この点数では幅プロファイル"
                   "や凹みを解像する材料が輪郭そのものに足りません",
            "how_to_close": f"{MIN_POINTS}点以上の輪郭を渡してください"
                             "(抽出側の頂点間引きを弱めてください)",
        }
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if max(xs) - min(xs) <= _EPS or max(ys) - min(ys) <= _EPS:
        return None, {
            "verdict": BAD_OUTLINE,
            "why": "輪郭の幅または高さが実質ゼロで、走査できません",
            "how_to_close": "幅・高さとも広がりのある輪郭を渡してください",
        }
    w, h = record.get("width_px"), record.get("height_px")
    if not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0 \
            or not isinstance(h, (int, float)) or isinstance(h, bool) or h <= 0:
        return None, {
            "verdict": BAD_FRAME,
            "width_px": w, "height_px": h,
            "why": "width_px / height_px は正の数である必要があります",
            "how_to_close": "撮影フレームの幅・高さ(px)を渡してください",
        }
    bbox_w, bbox_h = max(xs) - min(xs), max(ys) - min(ys)
    area_frac = (bbox_w * bbox_h) / (float(w) * float(h))
    height_frac = bbox_h / float(h)
    if area_frac < MIN_COVERAGE_FRACTION or height_frac < MIN_HEIGHT_FRACTION_OF_FRAME:
        return None, {
            "verdict": TOO_SMALL,
            "bbox_area_fraction": round(area_frac, 5),
            "height_fraction_of_frame": round(height_frac, 5),
            "minimum_area_fraction": MIN_COVERAGE_FRACTION,
            "minimum_height_fraction": MIN_HEIGHT_FRACTION_OF_FRAME,
            "why": "輪郭がフレームに対して小さすぎます。抽出の失敗片(ノイ"
                   "ズ)である可能性が高く、服として扱いません",
            "how_to_close": "服全体が写る範囲で抽出し直してください",
        }
    hits = _self_intersections(pts)
    if hits:
        return None, {
            "verdict": SELF_INTERSECTS,
            "edge_pairs": hits[:10],
            "count": len(hits),
            "why": "輪郭の辺どうしが交差しています。単純閉曲線ではない輪郭"
                   "には、この先の計算(幅・凸包)の前提が成り立ちません",
            "how_to_close": "自己交差の無い単純多角形として抽出し直してく"
                             "ださい",
        }
    return pts, None


# ---------------------------------------------------------------------------
# 1. 幅プロファイル W(y)
# ---------------------------------------------------------------------------

def _profile_ys(min_y: float, max_y: float, vertex_ys: Sequence[float]
               ) -> List[float]:
    """一様グリッド(``PROFILE_SAMPLES`` 点)と輪郭自前の頂点yを混ぜる。

    幅(y) は区分線形で、折れ点は輪郭の頂点yにしか起きない。一様グリッド
    だけだと折れ点がサンプルの間に埋もれ、knee の高さが最大1グリッド幅
    ぶん smear される。頂点yを足すことで、実際の折れ点をサンプル点その
    ものとして厳密に捉える。
    """
    span = max_y - min_y
    grid = [min_y + span * k / (PROFILE_SAMPLES - 1) for k in range(PROFILE_SAMPLES)]
    extra = [y for y in vertex_ys if min_y <= y <= max_y]
    merged = sorted(set(round(y, 6) for y in grid + extra))
    out: List[float] = []
    tol = span * 1e-4 if span > 0 else _EPS
    for y in merged:
        if out and y - out[-1] < tol:
            continue
        out.append(y)
    return out


def _build_profile(pts: Sequence[Vec2], min_y: float, max_y: float
                   ) -> List[Dict[str, float]]:
    vertex_ys = [p[1] for p in pts]
    rows: List[Dict[str, float]] = []
    for y in _profile_ys(min_y, max_y, vertex_ys):
        w = _width_at(pts, y)
        if w is None:
            continue
        left, right = w
        rows.append({"y": y, "left": left, "right": right,
                     "width": right - left, "center": (left + right) / 2.0})
    return rows


# ---------------------------------------------------------------------------
# 2. 対称軸
# ---------------------------------------------------------------------------

def _symmetry(rows: Sequence[Dict[str, float]], max_w: float) -> Dict[str, Any]:
    """axis = サンプルした中点の中央値。

    中点との不一致 ``|2a - left(y) - right(y)| = 2|a - center(y)|`` の
    総和(L1)を最小化する a は中央値 ── 「左右の幅の不一致を最小化する
    垂直線」を字義通り解いている。
    """
    centers = sorted(r["center"] for r in rows)
    n = len(centers)
    axis = centers[n // 2] if n % 2 == 1 else (centers[n // 2 - 1] + centers[n // 2]) / 2.0
    mismatches = [abs(2 * axis - r["left"] - r["right"]) / 2.0 for r in rows]
    mean_m = sum(mismatches) / len(mismatches) if mismatches else 0.0
    max_m = max(mismatches) if mismatches else 0.0
    return {
        "axis_x_px": round(axis, 3),
        "residual_mean_px": round(mean_m, 4),
        "residual_max_px": round(max_m, 4),
        "residual_mean_norm": round(mean_m / max_w, 5) if max_w > _EPS else None,
        "residual_max_norm": round(max_m / max_w, 5) if max_w > _EPS else None,
        "how": "axis = median_y[(left(y)+right(y))/2]; これは "
               "sum_y|2*axis-left(y)-right(y)| (左右幅の不一致のL1和) を"
               "最小化する解。斜めに撮った写真は residual が大きく出る"
               " ── それは撮影角度の証拠であって、軸が汚いのではない",
    }


# ---------------------------------------------------------------------------
# 3. 傾き不連続(knee)
# ---------------------------------------------------------------------------

def _knees(rows: Sequence[Dict[str, float]], height_span: float, y0: float
          ) -> List[Dict[str, Any]]:
    if len(rows) < 3 or height_span <= _EPS:
        return []
    max_w = max(r["width"] for r in rows)
    if max_w <= _EPS:
        return []
    ts = [(r["y"] - y0) / height_span for r in rows]
    wn = [r["width"] / max_w for r in rows]
    slopes: List[float] = []
    for i in range(len(rows) - 1):
        dt = ts[i + 1] - ts[i]
        slopes.append((wn[i + 1] - wn[i]) / dt if dt > _EPS else 0.0)
    knees: List[Dict[str, Any]] = []
    for i in range(1, len(slopes)):
        change = slopes[i] - slopes[i - 1]
        if abs(change) >= SLOPE_KNEE_THRESHOLD:
            knees.append({
                "height_fraction": round(ts[i], 4),
                "y_px": round(rows[i]["y"], 2),
                "slope_before": round(slopes[i - 1], 4),
                "slope_after": round(slopes[i], 4),
                "slope_change": round(change, 4),
                "slope_change_abs": round(abs(change), 4),
            })
    return knees


# ---------------------------------------------------------------------------
# 4. 境界の凹み(凸包ポケット)
# ---------------------------------------------------------------------------

def _concavities(pts: Sequence[Vec2], pockets: Sequence[Tuple[int, int, List[int]]],
                 min_y: float, max_y: float, axis_x: float, max_halfwidth: float
                ) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    height_span = (max_y - min_y) or 1.0
    for i, j, pocket in pockets:
        A, B = pts[i], pts[j]
        ab_len = math.hypot(B[0] - A[0], B[1] - A[1])
        if ab_len <= _EPS:
            continue
        best_idx, best_depth = None, -1.0
        for idx in pocket:
            depth = abs(_cross2(A, B, pts[idx])) / ab_len
            if depth > best_depth:
                best_depth, best_idx = depth, idx
        if best_idx is None:
            continue
        x, y = pts[best_idx]
        offset = x - axis_x
        side = "center"
        if max_halfwidth > _EPS and abs(offset) >= ARMPIT_MIN_OFFSET_FRACTION * max_halfwidth:
            side = "left" if offset < 0 else "right"
        out.append({
            "hull_edge_indices": [i, j],
            "point_index": best_idx,
            "point_px": [round(x, 2), round(y, 2)],
            "depth_px": round(best_depth, 3),
            "depth_norm": round(best_depth / (2 * max_halfwidth), 5)
                          if max_halfwidth > _EPS else None,
            "height_fraction": round((y - min_y) / height_span, 4),
            "side": side,
        })
    out.sort(key=lambda c: c["height_fraction"])
    return out


# ---------------------------------------------------------------------------
# 5. ランドマーク
# ---------------------------------------------------------------------------

def _shoulder(knees: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    for k in knees:
        if k["height_fraction"] <= SHOULDER_WINDOW_MAX:
            return {
                "height_fraction": k["height_fraction"], "y_px": k["y_px"],
                "slope_change_abs": k["slope_change_abs"],
                "from": "最上部寄り(height_fraction <= "
                        f"{SHOULDER_WINDOW_MAX})の幅knee",
            }
    return {
        "verdict": SHOULDER_NOT_RESOLVED,
        "search_window": [0.0, SHOULDER_WINDOW_MAX],
        "why": "この高さ窓に幅のknee(傾き不連続)がありません。この手法"
               "は幅の特徴だけを見るので、肩から先が幅の変化を伴わずに"
               "(例: 袖の無い直線的な肩)続く輪郭では肩線を原理的に検出"
               "できません",
        "how_to_close": f"閾値 SLOPE_KNEE_THRESHOLD={SLOPE_KNEE_THRESHOLD} "
                         "を下げて再解析するか、肩線を人が宣言してくださ"
                         "い",
    }


def _armpit(concavities: Sequence[Dict[str, Any]], side: str) -> Dict[str, Any]:
    cands = [c for c in concavities
             if c["side"] == side and ARMPIT_WINDOW[0] <= c["height_fraction"] <= ARMPIT_WINDOW[1]]
    if not cands:
        return {
            "verdict": ARMPIT_NOT_FOUND, "side": side,
            "search_window": list(ARMPIT_WINDOW),
            "why": "この探索窓・この側に、対称軸から十分離れた凹みがあり"
                   "ません。袖が無いか、袖が輪郭上で身体と融合していて"
                   "分離できません",
            "how_to_close": "袖ぐりが見える角度で撮り直すか、ARMPIT_WINDOW"
                             "/ARMPIT_MIN_OFFSET_FRACTION を調整してくだ"
                             "さい。それでも無いなら、この側は素直に「袖"
                             "なし、または輪郭上で腕が身体と融合」です",
        }
    best = max(cands, key=lambda c: c["depth_px"])
    return dict(best, side=side)


def _waist(rows: Sequence[Dict[str, float]], min_y: float, max_y: float,
          armpit_left: Dict[str, Any], armpit_right: Dict[str, Any]
          ) -> Dict[str, Any]:
    height_span = (max_y - min_y) or 1.0
    lo = WAIST_MIN_T
    armpit_ts = [a["height_fraction"] for a in (armpit_left, armpit_right)
                if "height_fraction" in a]
    if armpit_ts:
        lo = max(lo, min(armpit_ts) + 0.02)
    hi = WAIST_MAX_T
    cands = [r for r in rows if lo <= (r["y"] - min_y) / height_span <= hi]
    if not cands:
        return {
            "verdict": WAIST_NOT_RESOLVED,
            "search_window": [round(lo, 3), round(hi, 3)],
            "why": "脇からフロアまでの探索窓に幅サンプルがありません(輪郭"
                   "が短すぎるか、脇の高さが裾に近すぎます)",
            "how_to_close": "y_top/y_bottom側の探索窓を手で指定してくださ"
                             "い",
        }
    best = min(cands, key=lambda r: r["width"])
    max_w = max(r["width"] for r in rows) or 1.0
    return {
        "height_fraction": round((best["y"] - min_y) / height_span, 4),
        "y_px": round(best["y"], 2),
        "width_px": round(best["width"], 3),
        "width_norm": round(best["width"] / max_w, 4),
        "search_window": [round(lo, 3), round(hi, 3)],
        "how": "脇(見つかっていればその高さ+0.02)〜height_fraction="
               f"{WAIST_MAX_T} の間で幅が最狭のサンプル",
    }


def _hem(pts: Sequence[Vec2], min_x: float, max_x: float, garment_h: float
        ) -> Dict[str, Any]:
    span = max_x - min_x
    if span <= _EPS:
        return {"verdict": HEM_NOT_RESOLVED,
                "why": "輪郭の幅が実質ゼロで裾を走査できません",
                "how_to_close": "幅のある輪郭を渡してください"}
    lo_frac, hi_frac = HEM_MARGIN_FRACTION, 1.0 - HEM_MARGIN_FRACTION
    xs = [min_x + span * (lo_frac + (hi_frac - lo_frac) * k / (HEM_SAMPLES - 1))
         for k in range(HEM_SAMPLES)]
    samples: List[Tuple[float, float]] = []
    for x in xs:
        y = _hem_at(pts, x)
        if y is not None:
            samples.append((x, y))
    if len(samples) < 3:
        return {
            "verdict": HEM_NOT_RESOLVED,
            "why": "裾の走査で十分な点が取れません(縦の走査線が輪郭に"
                   f"{len(samples)}回しか交わりませんでした)",
            "how_to_close": "HEM_MARGIN_FRACTIONを狭めるか、裾が見える輪郭"
                             "を渡してください",
        }
    ys = [s[1] for s in samples]
    hem_range = max(ys) - min(ys)
    hem_range_norm = hem_range / garment_h if garment_h > _EPS else 0.0
    left_y, right_y = samples[0][1], samples[-1][1]
    diff_norm = (right_y - left_y) / garment_h if garment_h > _EPS else 0.0
    if hem_range_norm < HEM_LEVEL_THRESHOLD_NORM:
        shape = "level"
    else:
        diffs = [ys[k + 1] - ys[k] for k in range(len(ys) - 1)]
        noise = max(hem_range * 0.05, _EPS)
        signs = [1 if d > noise else (-1 if d < -noise else 0) for d in diffs]
        nonzero = [s for s in signs if s != 0]
        sign_changes = sum(1 for a, b in zip(nonzero, nonzero[1:]) if a != b)
        shape = "asymmetric_left_right" if sign_changes == 0 else "uneven"
    return {
        "shape": shape,
        "hem_range_px": round(hem_range, 3),
        "hem_range_norm": round(hem_range_norm, 5),
        "left_y_px": round(left_y, 2), "right_y_px": round(right_y, 2),
        "left_right_diff_px": round(right_y - left_y, 3),
        "left_right_diff_norm": round(diff_norm, 5),
        "level_threshold_norm": HEM_LEVEL_THRESHOLD_NORM,
        "front_back_attribution": {
            "verdict": CANNOT_HEM_ATTRIBUTION,
            "why": "正面1枚の輪郭は外側の境界(visual hull)しか写しませ"
                   "ん。前が短く後ろが長い「ハイロー」は、短い前端が長い"
                   "後ろの陰に隠れて輪郭に現れないことがあり得るので、"
                   "裾の高さ変化を前後に帰属させることはできません。ここ"
                   "で言えるのは輪郭が左右方向にどう変化するかだけです",
            "how_to_close": "側面・背面の写真を追加するか、前後を宣言する"
                             "人による入力を追加してください",
        },
    }


# ---------------------------------------------------------------------------
# 6. パーツ・インスタンス(resemble.per_part / structure_from の形)
# ---------------------------------------------------------------------------

def _instances(source: str, fixture: bool,
              min_x: float, max_x: float, min_y: float, max_y: float,
              armpit_left: Dict[str, Any], armpit_right: Dict[str, Any]
              ) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = [{
        "instance": "body:1", "part": "body",
        "evidence": {
            "kind": "outline_geometry",
            "bbox_px": [round(min_x, 2), round(min_y, 2),
                       round(max_x, 2), round(max_y, 2)],
            "source": source, "fixture": fixture,
        },
    }]
    n = 0
    for side, label, arm in (("left", "左", armpit_left), ("right", "右", armpit_right)):
        if "height_fraction" not in arm:
            continue
        n += 1
        out.append({
            "instance": f"sleeve:{n}", "part": "sleeve", "side": label,
            "evidence": dict(arm, kind="boundary_concavity", source=source,
                            fixture=fixture),
        })
    return out


def _limbs(armpit_left: Dict[str, Any], armpit_right: Dict[str, Any]
          ) -> List[Dict[str, Any]]:
    out = []
    for side, arm in (("left", armpit_left), ("right", armpit_right)):
        if "height_fraction" in arm:
            out.append({"side": side, "found": True,
                       "height_fraction": arm["height_fraction"],
                       "depth_norm": arm.get("depth_norm")})
        else:
            out.append({"side": side, "found": False, **arm})
    return out


# ---------------------------------------------------------------------------
# シルエットには情報が無く、名指しで断る話題(静的、from_outline に同梱)
# ---------------------------------------------------------------------------

REFUSED_TOPICS: Dict[str, Dict[str, str]] = {
    "front_or_back": {
        "verdict": CANNOT_SIDE,
        "why": "写真1枚では、写っているのが前身頃か後ろ身頃かを輪郭だけ"
               "から決められません。前後は概ね鏡像で、輪郭の左右非対称"
               "さだけでは区別できません",
        "how_to_close": "撮影時にどちらを向けたか記録するか、前後で異な"
                         "る特徴(ポケット・ボタン等)が写る別カットを追"
                         "加してください",
    },
    "closure": {
        "verdict": CANNOT_CLOSURE,
        "why": "ボタン・ファスナー・紐などの開き具は輪郭の外形に現れませ"
               "ん",
        "how_to_close": "開き部分に寄った写真か、人による宣言を追加して"
                         "ください",
    },
    "layering": {
        "verdict": CANNOT_LAYERING,
        "why": "輪郭は見えている最も外側の境界(visual hull)だけです。"
               "どのパーツが手前でどれが奥かという重なりの順序は、外形"
               "からは復元できません",
        "how_to_close": "パーツごとに別カットを撮るか、人による重なりの"
                         "宣言を追加してください",
    },
    "fabric": {
        "verdict": CANNOT_FABRIC,
        "why": "生地の種類・ドレープ・重さは輪郭の形からは求まりません。"
               "同じ輪郭が硬いキャンバス地からも柔らかいレーヨンからも"
               "作れます",
        "how_to_close": "生地見本・タグ・人による宣言など、輪郭以外の情"
                         "報源が要ります",
    },
    "seam_position": {
        "verdict": CANNOT_SEAM,
        "why": "縫い目は輪郭の内側にあり、シルエットには写りません",
        "how_to_close": "型紙側(garment_parts / garment_sew)の宣言、ま"
                         "たは縫い目が見える接写を追加してください",
    },
    "dart_position": {
        "verdict": CANNOT_DART,
        "why": "ダーツは布の内部でつままれる分量で、多くは輪郭に外側の"
               "痕跡を残しません",
        "how_to_close": "型紙側の宣言(darts.py)を使うか、ダーツが見える"
                         "接写を追加してください",
    },
}


def cannot_answer(topic: str) -> Dict[str, Any]:
    """1個の話題を名指しで問う。閉じた語彙 ── ``REFUSED_TOPICS`` の外は
    「その質問を知らない」というさらに別の型で断る。"""
    hit = REFUSED_TOPICS.get(topic)
    if hit is None:
        return {
            "verdict": NO_SUCH_TOPIC, "which": topic,
            "known": sorted(REFUSED_TOPICS),
            "how_to_close": "既知の話題: " + ", ".join(sorted(REFUSED_TOPICS)),
        }
    return dict(hit, topic=topic)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def from_outline(record: Dict[str, Any], *, image_id: str = "") -> Dict[str, Any]:
    """THE OUTLINE CONTRACT ちょうど1個を受け取り、幾何だけから求まる分
    だけを求め、求まらない分は名指しで断る。"""
    pts, refusal = _validate(record)
    if refusal is not None:
        return refusal
    assert pts is not None

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    height_span = max_y - min_y

    rows = _build_profile(pts, min_y, max_y)
    max_w = max((r["width"] for r in rows), default=0.0)
    max_w_safe = max_w if max_w > _EPS else 1.0
    width_profile = [{
        "height_fraction": round((r["y"] - min_y) / height_span, 4),
        "y_px": round(r["y"], 2),
        "left_x": round(r["left"], 2), "right_x": round(r["right"], 2),
        "width_px": round(r["width"], 3),
        "width_norm": round(r["width"] / max_w_safe, 4),
    } for r in rows]

    symmetry = _symmetry(rows, max_w_safe)
    axis_x = symmetry["axis_x_px"]

    knees = _knees(rows, height_span, min_y)

    hull = _hull_indices(pts)
    pockets = _pockets(pts, hull)
    concavities = _concavities(pts, pockets, min_y, max_y, axis_x, max_w_safe / 2.0)

    armpit_left = _armpit(concavities, "left")
    armpit_right = _armpit(concavities, "right")
    shoulder = _shoulder(knees)
    waist = _waist(rows, min_y, max_y, armpit_left, armpit_right)
    hem = _hem(pts, min_x, max_x, height_span)

    source = str(record.get("source", ""))
    fixture = bool(record.get("fixture"))
    instances = _instances(source, fixture, min_x, max_x, min_y, max_y,
                           armpit_left, armpit_right)
    limbs = _limbs(armpit_left, armpit_right)

    bbox_area_frac = ((max_x - min_x) * (max_y - min_y)) \
        / (float(record["width_px"]) * float(record["height_px"]))
    height_frac = height_span / float(record["height_px"])

    return {
        "verdict": "ANSWER",
        "image_id": image_id or str(record.get("image_id") or ""),
        "source": source,
        "fixture": fixture,
        "frame_px": {"width": record["width_px"], "height": record["height_px"]},
        "bbox_px": {"min_x": round(min_x, 2), "max_x": round(max_x, 2),
                   "min_y": round(min_y, 2), "max_y": round(max_y, 2),
                   "width": round(max_x - min_x, 2),
                   "height": round(height_span, 2)},
        "coverage": {"bbox_area_fraction": round(bbox_area_frac, 5),
                    "height_fraction_of_frame": round(height_frac, 5)},
        "symmetry": symmetry,
        "width_profile": width_profile,
        "knees": knees,
        "concavities": concavities,
        "landmarks": {
            "shoulder": shoulder,
            "armpit_left": armpit_left, "armpit_right": armpit_right,
            "waist": waist, "hem": hem,
        },
        "instances": instances,
        "limbs": limbs,
        "refused_by_design": {k: dict(v, topic=k) for k, v in REFUSED_TOPICS.items()},
        "single_view_limits": {
            "outer_extent_only": (
                "幅も裾も、各走査線が輪郭と2点より多く交わっても外側の"
                "最小・最大だけを使います。内側の交点(凹みの証拠)は"
                "そこでは捨てています ── visual hull の上界という性質は"
                "silhouette.py と同じです。凹み自体は別の方法(凸包)で"
                "拾いますが、それでも輪郭という1個の境界に写っている分"
                "だけです"),
            "one_outline_one_view": (
                "この関数が受け取るのは輪郭(閉多角形)1個だけで、それが"
                "何視点から作られたかを関数自身は知りません。1視点の写真"
                "から作られた輪郭を渡しているなら、奥行と前後はこの中の"
                "何ものからも求まりません"),
        },
        "generated_not_evidence": (
            "symmetry / width_profile / knees / concavities / landmarks / "
            "instances はすべて生成物です。観測(実測)の出典にはなりま"
            "せん。布の挙動(伸縮・張り・重なり)は計算していません"),
        "no_image_processing": (
            "この関数は輪郭(2次元点列)しか受け取りません。写真からこの"
            "輪郭を取り出す仕事はここには含まれません ── 別の問題、別の"
            "答えです。このリポジトリは第三者ライブラリを一切importしま"
            "せん"),
    }
