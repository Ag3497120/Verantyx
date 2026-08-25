# -*- coding: utf-8 -*-
"""立体十字ストア。**Block の置き場所であって、辞書の代用品ではない。**

1核 = 6本の腕 × 4つの面 = **24席**。この上限は測定に由来する
(ノードの識別能力は 6腕×4面=24語、それを超える語は到達不能 0/60)。
だからこの店は**容量を超えた要求を黙って拡張しない** — 子コアに分れる
(マトリョーシカは選択ではなく幾何が要求すること)。

**腕は三つの双対で、書く側は腕を選べない。**

    x: support+ / support-   何が支えるか / 何が反するか
    y: cause+   / cause-     何が生んだか / 何を生むか
    z: kind+    / kind-      何に抽象されるか / 何がその例か

書く側が言うのは**主張の種別 (kind)** だけで、腕は ``KIND_ARM`` が決める
(親プロジェクトの ``arm_schema.ARMS`` / ``garment_cross.ARM_OF_KIND`` と
同じ形)。選べる引き出しが無いので「都合のいい腕に書く」ができない。

- ``support-`` は表に無い。**名指しで書けない腕**で、同じ住所に違う値が
  立ったときにだけ現れる。腕が住所の一部でないのはこのため — 腕まで
  住所に含めると support+ の観測と support- の観測は別住所になり、
  永久にぶつからない。
- ``no_match`` (探して無かった) は**載らない**。不在は主張ではない。
- ``proposed`` は腕を持たず ``<core>#proposed`` に隔離される。質量に
  混ぜない。**隔離核も同じ 24 の法に従う。** 席が腕を持たないので
  「6腕×4面」の割り算は効かないが、上限そのものは核の性質であって腕の
  性質ではないので、25本目の提案は子コアに分れる (厳密な書き口は断る)。
  以前ここだけ容量の検査を飛ばしていたので、``q#proposed`` が100席まで
  黙って伸びて ``census()`` は在庫ゼロと言った — **黙った例外は、上の
  「容量を超えた要求を黙って拡張しない」を嘘にする。** ``census()`` は
  隔離席を ``quarantined`` に別立てで数えるので、免除が要るときも
  黙ってではなく見える形になる。

**住所は (core, key) で、腕は席の性質であって座標ではない。**
容量は (core, 腕) ごとに**住所の数**で数える — 4人が同じ寸法に同意
しても席は1つで、重み (weight) が増えるだけ。だから
``GENERIC_MIN_SOURCES`` (一般構造の主張は独立した出典2本で買う) が
言葉として成立する。

守っている性質と、その根拠:

- **1核 = 24席は席の種類で割り引かない。** 腕ごとの4面と隔離核の24を
  別々に数えていたので、名前が隔離核の形をした核は「腕付き20席 + 隔離
  24席 = 44席」まで伸びて ``census()['over_capacity']`` は空だった。
  核の総席数も 24 で、書き口は 25 席目を断り ``verify()`` は挙げる。
- **隔離は名前の部分一致ではなく構造で見る。** ``_is_quarantine`` は
  末尾が ``#proposed`` か、その核から分れた子かだけを見る。以前は
  ``"#proposed" in core`` だったので ``review#proposed-revisions`` の
  ような核では提案が隔離されず、**噂が実測と同じ住所で争えた**。
- **名無しは出典ではない。** ``generic`` の主張に出典が無ければ断る。
  空文字が独立した一本として数えられていたので、
  ``GENERIC_MIN_SOURCES`` の片方が誰でもない状態が作れた。出典の同一性
  は空白と大小を畳んでから比べる (``Lab`` と ``lab `` は一本)。
- **保存できない値は受け取らない。** 保存形式は JSON なので、set /
  frozenset / 自作クラス / 文字列でない dict の鍵は書き口で断る
  (``UNKNOWN_UNIDENTIFIABLE_VALUE``)。受け取ってから
  ``json.dumps(to_dict())`` が落ちるのは、書けたのに保存できないという
  ことで、``_vkey`` の repr 落ちで**区別できる値が同じ観測に化ける**道
  もここで閉じる。
- **同点は棄権。** 同じ住所に値が違うものが立ったら、どちらも捨てずに
  CONTESTED を返す。多数決もアルファベット順も使わない — 恣意的な
  同点崩しは一致を捏造した (実測: 辞書順タイブレークで全一致の精度が
  73.3% → 23.7% に落ちた)。**割れの判定は nest 閉包の全体で行う** —
  マトリョーシカで別コアに落ちた値が「一致」に見えてはいけない。
- **格納順は答えを動かさない。** これを確かめるのは
  ``ingest_order_check()`` で、同じ書き込み計画を**別の順で入れ直して**
  住所→値の地図・割れの集合・断られた書き込みの集合を比べる。
  (以前ここにあった ``placement_check()`` は同じ店を二度**読む**だけで、
  構造上落ちようがなかった。互換のため残してあるが、本物はこちら。)
- **辺は関係の席。** 面(facet)は「何が在るか」、辺(edge)は「何と何が
  約束しているか」。片端しかない辺、居ない核を指す辺は**入れない**。
- **読みは何も作らない。** 無い核を読んでも核はできない。
- **店は値を所有する。** 出し入れで複製する。外から握ったままの
  オブジェクトを書き換えて CONTESTED を ANSWER に戻せない。
- **断りは戻り値。** 例外で境界を越えない。
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: 幾何。**この数は測定から来ている。** 変えるなら測定し直すこと。
#: 親プロジェクトの ``arm_schema.ARMS`` と同一。
ARMS = ("support+", "support-", "cause+", "cause-", "kind+", "kind-")
FACES_PER_ARM = 4
CAPACITY_PER_CORE = len(ARMS) * FACES_PER_ARM      # 24

#: 主張の種別 → 腕。**書く側が言うのは左、店が決めるのは右。**
#:
#: ``support-`` が無いのは意図的で、反証は**書けない**。同じ住所で値が
#: 割れたときに現れるだけ。``None`` の二つは腕を持たない:
#: ``proposed`` は隔離席へ、``no_match`` は載らない。
KIND_ARM: Dict[str, Optional[str]] = {
    "measured": "support+",   # 実測がその値を支える
    "cited":    "support+",   # 外の文献がその値を支える
    "input":    "cause+",     # 引くために要る実測 — 型紙を生む側
    "derived":  "cause+",     # 式・手順がその値を生んだ
    "feeds":    "cause-",     # この値があの値を生む
    "generic":  "kind+",      # 一般構造の主張(この一着のものではない)
    "specific": "kind-",      # この宣言が決めたこと
    "declared": "kind-",      # 名乗りも「この一着のもの」という実例側
    "proposed": None,         # 言われただけ。質量に混ぜない
    "no_match": None,         # 探して無かったは主張ではない。載せない
}

#: 空の腕 → 型付きの欠落。親プロジェクトの ``_ARM_GAP_VERDICT`` と同一。
ARM_GAP_VERDICT: Dict[str, str] = {
    "support+": "UNKNOWN_NO_SUPPORT_RECORDED",
    "support-": "UNKNOWN_NO_COUNTEREVIDENCE_RECORDED",
    "cause+":   "UNKNOWN_NO_CAUSE_RECORDED",
    "cause-":   "UNKNOWN_NO_EFFECT_RECORDED",
    "kind+":    "UNKNOWN_NO_GENERALIZATION_RECORDED",
    "kind-":    "UNKNOWN_NO_INSTANCE_RECORDED",
}

#: 一般構造の主張は**独立した出典2本で買う。** 1本の kind+ は
#: 「そう言われている」であって「一般にそうである」ではない。
GENERIC_MIN_SOURCES = 2

#: 辺の閉じた語彙。``seam:`` だけ接頭辞で開いている(縫い目の名前が入る)。
EDGE_LABELS = ("nest", "part_of", "feeds")
EDGE_LABEL_PREFIXES = ("seam:",)

NOT_IN_CROSS = "UNKNOWN_NOT_IN_CROSS"
CONTESTED_IN_CROSS = "CONTESTED_IN_CROSS"
ARM_FULL = "UNKNOWN_CROSS_ARM_FULL"
ORDER_DEPENDENT = "UNKNOWN_ORDER_DEPENDENT"
NO_SUCH_KIND = "UNKNOWN_NO_SUCH_KIND"
NOT_A_CLAIM = "UNKNOWN_ABSENCE_IS_NOT_A_CLAIM"
DANGLING_EDGE = "UNKNOWN_DANGLING_EDGE"
ARM_NOT_DERIVED = "UNKNOWN_ARM_NOT_DERIVED"
DUPLICATE_ADDRESS = "UNKNOWN_DUPLICATE_ADDRESS"
OVER_CAPACITY = "UNKNOWN_OVER_CAPACITY"
ORPHANED_CORE = "UNKNOWN_ORPHANED_CORE"
ALIASED_VALUE = "UNKNOWN_ALIASED_VALUE"
GENERIC_NOT_BOUGHT = "UNKNOWN_GENERIC_NOT_BOUGHT"
DUPLICATE_CLAIM = "UNKNOWN_DUPLICATE_CLAIM"
QUARANTINE_FULL = "UNKNOWN_QUARANTINE_FULL"
UNNAMED_SOURCE = "UNKNOWN_UNNAMED_SOURCE"
UNIDENTIFIABLE_VALUE = "UNKNOWN_UNIDENTIFIABLE_VALUE"

Addr = Tuple[str, str]          # (core, key) — **腕は住所に入らない**


class CrossFullError(ValueError):
    """腕の4面が埋まった。

    **もう送出されません。** 容量は ``put_strict()`` の戻り値
    (``verdict == ARM_FULL``) で返る — 断りは戻り値であって例外では
    ないため。この名前は import 互換のために残してあります。
    """


def _is_addr(a: Any) -> bool:
    return (isinstance(a, (tuple, list)) and len(a) == 2
            and isinstance(a[0], str) and a[0] != ""
            and isinstance(a[1], str))


def _vkey(v: Any) -> Any:
    """**値の同一性。型は値の一部。**

    ``==`` だけで一致を見ると、区別できるものが「同じ観測」に化ける:
    ``True`` と ``1``、``108.0`` と ``108``、``0`` と ``False`` は
    Python では等しいが、**別の観測**であって片方を黙って捨てて良い
    ものではない (実測: ``True``/``1`` を別々の出典で書くと重み2の
    ANSWER になり、どちらが残るかは格納順で決まった)。

    逆に ``float('nan')`` は自分自身と等しくないので、素の ``==`` では
    **同じ値が自分と争う**。自分と等しくない値は自分の敵ではないので、
    ここで一つの札に畳む。

    list と tuple は畳む。この店の保存形式は JSON で、往復すると
    tuple は list になる — 区別すると往復で答えが動いてしまい、
    「格納は答えを動かさない」の方が先に壊れる。
    """
    if isinstance(v, bool):             # bool を int より先に見る
        return ("b", v)
    if isinstance(v, int):
        return ("i", v)
    if isinstance(v, float):
        return ("f", "nan" if v != v else repr(v))
    if isinstance(v, str):
        return ("s", v)
    if v is None:
        return ("n", "")
    if isinstance(v, (list, tuple)):
        return ("l", tuple(_vkey(x) for x in v))
    if isinstance(v, dict):
        return ("d", tuple(sorted((_vkey(k), _vkey(val))
                                  for k, val in v.items())))
    if isinstance(v, (set, frozenset)):
        # **保存できない形。** set は JSON を往復しない (list/tuple を畳む
        # 理由はここには届かない)。書き口が ``_persistable`` で断るので
        # 店に入ってはこないが、手で書いた dict を ``from_dict`` から
        # 入れる道が残っているので札だけは作る。
        return ("S", tuple(sorted(_vkey(x) for x in v)))
    # **repr は同一性ではない。** ``repr`` が全ての欄を出さない値
    # (``Length(108, 'cm')`` と ``Length(108, 'in')`` が同じ ``Length(108)``
    # を出す、ごく普通の値オブジェクト) は、ここで**同じ観測に化ける** —
    # 実測: 別々の出典が矛盾したまま重み2の ANSWER になり、片方の単位が
    # 黙って消え、generic なら出典2本の値段まで払えた。だから書き口は
    # ``_persistable`` で断り、この行は ``from_dict`` から来た値のための
    # 最後の砦としてだけ残っている (``verify`` がそれを問題として挙げる)。
    return ("r", type(v).__name__, repr(v))


def _persistable(v: Any, path: str = "") -> List[str]:
    """**この店が往復できる値か。** 出来ないものの居場所を並べて返す。

    店の保存形式は JSON だと ``_vkey`` の docstring が言っている。だが
    書き口は set も frozenset も自作クラスも受け取っていて、
    ``json.dumps(store.to_dict())`` はそれで ``TypeError`` を出した —
    **書けたのに保存できない**、つまり店の言う保存形式が嘘になる。
    受け取れないものは受け取らない。断りは戻り値。

    dict の鍵も見る。JSON は鍵を文字列にするので ``{1: "a"}`` は往復で
    ``{"1": "a"}`` になり、「格納は答えを動かさない」が先に壊れる。
    """
    bad: List[str] = []
    if isinstance(v, (bool, int, float, str)) or v is None:
        return bad
    if isinstance(v, (list, tuple)):
        for i, x in enumerate(v):
            bad += _persistable(x, f"{path}[{i}]")
        return bad
    if isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str):
                bad.append(f"{path}{{{k!r}}}: 鍵が文字列ではない "
                           f"({type(k).__name__}) — JSON の往復で文字列に"
                           "化ける")
            else:
                bad += _persistable(x, f"{path}.{k}")
        return bad
    bad.append(f"{path or '値'}: {type(v).__name__} は JSON で往復しない")
    return bad


def _source_key(source: Any) -> str:
    """出典の同一性。**空白と大小は独立性を生まない。**

    独立性そのものは店には確かめられない — 名乗った名前が別々である
    ことだけが検査できる事実で、独立かどうかは**書く側の主張**です。
    せめて ``'Lab'`` と ``'lab '`` が二本の出典に化けないように、
    比べる前に空白を畳んで大小を落とす。
    """
    if not isinstance(source, str):
        return ""
    return " ".join(source.split()).casefold()


def _independent(sources: Sequence[Any]) -> List[str]:
    """数えられる出典だけ。**名無しは出典ではない。**

    ``put()`` の ``source`` は既定が ``""`` で、空文字が独立した一本と
    して数えられていた — ``GENERIC_MIN_SOURCES`` (独立した出典2本で買う)
    の片方が誰でもない、という状態が実測できた。
    """
    out: List[str] = []
    seen: set = set()
    for s in sources:
        k = _source_key(s)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _is_quarantine(core: str) -> bool:
    """隔離核か。分れた子 (``q#proposed·proposed·1``) も隔離核。

    **部分一致で見ない。** 以前は ``"#proposed" in core`` だったので、
    名前に ``#proposed`` を含むだけの核 — ``review#proposed-revisions``、
    ``notes#proposedX`` — が隔離核として扱われた。そこでは提案が隔離
    されず、**噂が実測と同じ住所で争う** (実測: 測った 108.0 に対して
    「工房で聞いた」999.0 が CONTESTED_IN_CROSS を返し、寸法が読めなく
    なった)。名前は書く側が握っているので、**構造の形だけを見る**:
    末尾が ``#proposed`` か、その核から分れた子か。
    """
    if not isinstance(core, str):
        return False
    return core.split("·")[0].endswith("#proposed")


def seat_arms(seat: Dict[str, Any]) -> List[str]:
    """**その席が載っている腕、全部。**

    席の腕は一本ではない。``values`` の各主張がそれぞれ自分の kind から
    腕を導き、席は**届いた種別すべての腕に現れる**。実測で支えられ、かつ
    式から導かれた値は support+ にも cause+ にも居る — 片方を捨てる理由が
    無いし、捨てると空いていない腕が「型付きの欠落」として報告される。

    だから**選べる「席の腕」というものが無い**。先に書いた者が腕を
    決める、が成り立たない (以前は ``values[0]`` だけを見ていたので
    成り立っていた)。
    """
    out: List[str] = []
    for e in (seat.get("values") or []):
        a = KIND_ARM.get(e.get("kind"))
        if a is not None and a not in out:
            out.append(a)
    return [a for a in ARMS if a in out]


def _arms_of(seats: Sequence[Tuple[str, Dict[str, Any]]]) -> List[str]:
    """閉包に散った同じ住所の席を合わせて、現れる腕を全部。"""
    out: List[str] = []
    for _cn, s in seats:
        for a in seat_arms(s):
            if a not in out:
                out.append(a)
    return [a for a in ARMS if a in out]


def _label_ok(label: Any) -> bool:
    if not isinstance(label, str) or not label:
        return False
    return (label in EDGE_LABELS
            or any(label.startswith(p) for p in EDGE_LABEL_PREFIXES))


class CrossStore:
    """核の集まりと、核どうしを結ぶ辺。

    核は**席(seat)の並び**。1席 = 1住所 = ``{key, arm, seq, values}``。
    ``values`` は ``{value, kind, sources}`` の並びで、長さが2以上なら
    その住所は割れている。
    """

    def __init__(self) -> None:
        self.cores: Dict[str, List[Dict[str, Any]]] = {}
        self.edges: List[Dict[str, Any]] = []
        #: 宣言の序数。**並びは格納ではなく宣言の内容**なので、
        #: 席が自分で覚える(散らばっても読む順が動かない)。
        self._seq = 0
        #: 断りの控え。書き口が返した非 ANSWER を溜める。
        self.refusals: List[Dict[str, Any]] = []
        #: **予算を払っていない腕の控え。** 既にある席に別の種別が
        #: 届いたとき、その腕には席が現れるのに面は一つも払われない。
        #: どう閉じるかは持ち主の決め (``_arm_load``) なので、店は
        #: 決めずに**数える**。
        self.uncharged: List[Dict[str, Any]] = []
        self.load_verdict: Dict[str, Any] = {"verdict": "ANSWER",
                                             "note": "built, not loaded"}

    # ------------------------------------------------------------ 内部
    def _core(self, name: str) -> List[Dict[str, Any]]:
        """**書き口専用。** 読みからは絶対に呼ばない(呼ぶと核ができる)。"""
        if name not in self.cores:
            self.cores[name] = []
        return self.cores[name]

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def has_core(self, name: str) -> bool:
        return name in self.cores

    # ------------------------------------------------------------ 閉包
    def _closure(self, core: str) -> List[str]:
        """nest 辺で繋がった核の連結成分。**これが一つの住所空間。**

        マトリョーシカは幾何が要求した分割であって別の主題ではないので、
        鎖の全体で1つの住所空間として解決する。``part_of`` は辿らない
        — ``block:coat`` と ``block:coat/piece:袖`` は**別の主題**で、
        同じ鍵が両方に立っても矛盾ではない。
        """
        out = [core]
        seen = {core}
        i = 0
        while i < len(out):
            cur = out[i]
            i += 1
            for e in self.edges:
                if e["label"] != "nest":
                    continue
                for x, y in ((e["a"], e["b"]), (e["b"], e["a"])):
                    if not _is_addr(x) or not _is_addr(y):
                        continue
                    if x[0] == cur and y[0] not in seen:
                        seen.add(y[0])
                        out.append(y[0])
        return out

    def _find_seat(self, core: str, key: str
                   ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """閉包の中で住所 (core, key) の席を探す。**核は作らない。**"""
        for cname in self._closure(core):
            for s in self.cores.get(cname, []):
                if s["key"] == key:
                    return cname, s
        return None

    def _arm_load(self, core: str, arm: str) -> int:
        """腕あたりの**座った住所の数**。容量はこちらで数える。

        **予算と意味は別のもの。** 容量の 24 は節点が区別できる語の数で、
        一つの住所は二本の腕に現れても一語のまま — だから予算は住所が
        **座ったとき**の腕 (``seat["arm"]``、最初の主張が導いた腕) で
        一度だけ数える。席がその後どの腕に現れるかは ``seat_arms`` で、
        それは意味であって予算ではない (``census()`` は両方を出す)。

        **未決 (持ち主に返す判断)。** 意味の側の腕は導出で順に依らない
        が、**予算の腕はまだ先に書いた者が決めている**。二つの種別が
        同じ住所に届いたとき、どちらの腕が面を一つ払うかが格納順で
        変わる (実測: measured→derived で support+、逆で cause+)。
        これは今 ``ingest_order_check`` が UNKNOWN_ORDER_DEPENDENT として
        **報告する** — 隠れてはいない。

        **これは「どの腕が払うか」より大きい。** 二つ目の種別が既にある
        席に届く枝 (``put_strict`` の second_kind) は**容量を一度も
        聞かない**ので、選び方は「書き込みが通るか」と「どの核に載るか」
        まで決めている。実測: support+ が4席で埋まった核に
        ``measured`` を直接書くと UNKNOWN_CROSS_ARM_FULL で**断られる**
        が、先に ``derived`` を書いてから同じ ``measured`` を書くと
        ANSWER で通り、``arms_present['support+']`` は 5 になる
        (``over_capacity`` は空、``verify()`` は ANSWER)。分ける書き口
        では、同じ二つの主張が順によって別の核に載る。

        **店は決めない。数えて言う。** ``census()`` は
        ``budget_arm_rule`` (今は ``first_kind_seated``)、
        ``two_kind_addresses``、``uncharged`` を返し、``put_strict`` は
        ``charged_arm`` と ``uncharged`` を返し、``ingest_order_check``
        は ``budget_arm_differences`` を数える。

        消すには三つの道があり、**どれも別のものを壊す**:

        (a) **ARMS 順の正準な腕にする。** 順に依らなくなる。壊れるのは
            容量で、後から来た種別が腕を動かすので**合法な書き込みで核が
            容量超過になりうる** (support+ が既に 4 席の核で cause+ の席
            が support+ に移ると 5)。``verify()`` の OVER_CAPACITY は
            書き込みの後で真になり、``put_strict`` は「通したのに店が
            壊れている」状態を作れる。移動のたびに再配置が要る。
        (b) **現れる腕すべてに課金する。** 順に依らない。壊れるのは
            容量の測定根拠で、「一住所 = 一語」(24 = 6腕×4面 は節点が
            区別できる語の数) が「一住所 = 種別の数だけの語」になる。
            核あたりの実効容量は下がり、今のコート (56住所/10核) は
            そのままでも、二種別の住所を持つ店は分割が増える。
        (c) **種別の違う二つ目を断る。** 順に依らない。壊れるのは住所の
            共有で、先に書いた者が住所を所有する — #1 で捨てた案そのもの
            であり、実測と導出が同じ値に届いても片方が載らない
            (``seat_arms`` が二本を返すことも、型付きの欠落が両方
            埋まることも無くなる)。

        どれを採っても、``verify()`` の ARM_NOT_DERIVED (``values[0]``
        の kind から席の腕を導く) と ``tests/run_checks.py`` の
        「arms are derived, not chosen」の pin は一緒に変わる。どちらも
        今は「腕は最初に来た種別のもの」を書いているため。

        コートにも部品ライブラリにも二種別の住所は一つも無いので、
        **今日の答えはどの道でも同じ** — だから急ぐ判断ではないが、
        黙っている判断でもない。
        """
        return sum(1 for s in self.cores.get(core, []) if s["arm"] == arm)

    def _uncharged(self, core: str, seat: Dict[str, Any],
                   arm: Optional[str]) -> Optional[Dict[str, Any]]:
        """既にある席に届いた**新しい腕**で、予算を払っていないもの。

        返すのは事実だけ — 課金するのか、断るのか、分けるのかは
        ``_arm_load`` に書いた三案のどれを採るかで、持ち主の決め。
        """
        if arm is None or arm == seat.get("arm"):
            return None
        return {"core": core, "charged_arm": seat.get("arm"),
                "uncharged_arm": arm,
                "arm_load": self._arm_load(core, arm),
                "would_overflow":
                    self._arm_load(core, arm) >= FACES_PER_ARM,
                "why": "この席は座ったときの腕にしか課金されていない"}

    def _quarantine_load(self, core: str) -> int:
        """隔離核の住所の数。腕を持たない席は**核あたり**で数える。"""
        return sum(1 for s in self.cores.get(core, []) if s["arm"] is None)

    # ------------------------------------------------------------ 格納
    def put_strict(self, core: str, key: str, value: Any, kind: str,
                   source: str = "", seq: Optional[int] = None
                   ) -> Dict[str, Any]:
        """**分けない書き口。** 腕が埋まったら ARM_FULL を返す。

        住所を先に解決する — 既に席がある住所への二つ目の値は
        「新しい席をくれ」ではなく「その席で争う」なので、**容量より
        先に争いを見る**。これが逆だと、埋まった腕の上では矛盾が
        「腕が満杯」に化けて永久に見えない。
        """
        if kind not in KIND_ARM:
            return {"verdict": NO_SUCH_KIND, "which": kind,
                    "known": sorted(KIND_ARM),
                    "how_to_close": "宣言に主張の種別を書く"}
        if kind == "no_match":
            return {"verdict": NOT_A_CLAIM, "stored": False,
                    "core": core, "key": key,
                    "why": "探して無かった、は主張ではない。載せません"}

        # **この店が往復できない値は受け取らない。** 受け取ってから
        # ``json.dumps(to_dict())`` が落ちるのは、書けたのに保存できない
        # ということで、店の言う保存形式が嘘になる。同じ断りが
        # ``_vkey`` の repr 落ちも塞ぐ — repr が全ての欄を出さない値は
        # 「同じ観測」に化けて、矛盾したまま重み2の ANSWER になっていた。
        why_not = _persistable(value)
        if why_not:
            return {"verdict": UNIDENTIFIABLE_VALUE, "stored": False,
                    "core": core, "key": key, "why": why_not[:6],
                    "type": type(value).__name__,
                    "how_to_close": "JSON で往復する形 (数・文字列・真偽・"
                                    "None・list・文字列鍵の dict) に直す"}

        # **名無しは出典ではない。** 一般構造の主張は独立した出典2本で
        # 買うと言っている以上、その片方が空文字であってはならない。
        if kind == "generic" and not _source_key(source):
            return {"verdict": UNNAMED_SOURCE, "stored": False,
                    "core": core, "key": key, "kind": kind,
                    "why": "一般構造の主張に出典が無い。空の出典は"
                           f"{GENERIC_MIN_SOURCES}本のうちの1本に数えない",
                    "how_to_close": "出典を名乗るか、specific に落とす"}

        arm = KIND_ARM[kind]
        if arm is None and not _is_quarantine(core):   # proposed — 隔離席へ
            core = f"{core}#proposed"

        vkey = _vkey(value)
        found = self._find_seat(core, key)
        if found is not None:
            where, seat = found
            # 同じ値で**同じ種別** → 一つの主張の裏付けが増える。
            for entry in seat["values"]:
                if _vkey(entry["value"]) != vkey or entry["kind"] != kind:
                    continue
                state = "already"
                # 同一性は正規化して見る。``'Lab'`` と ``'lab '`` は
                # 一本の出典であって二本ではない。
                known = {_source_key(x) for x in entry["sources"]}
                if _source_key(source) not in known:
                    entry["sources"].append(source)
                    state = "corroborated"
                return {"verdict": "ANSWER", "state": state,
                        "core": where, "key": key, "arm": seat["arm"],
                        "charged_arm": seat["arm"],
                        "arms": seat_arms(seat),
                        "weight": len(_independent(entry["sources"])),
                        "named_sources": len(entry["sources"]),
                        "seat_created": False}

            # ここから先は**新しい主張**。値が合っていても種別が違えば
            # 別の主張なので、出典だけ足して kind を捨ててはいけない —
            # 捨てると specific 一本で generic が買えてしまう。
            # **容量は聞かない。** 席の数は住所の数であって、既にある
            # 住所への二つ目の主張は「席をくれ」ではない。ここで腕の
            # 満杯を見ると、矛盾が「腕が満杯」に化けて永久に見えなく
            # なる — P2 で直したのと同じ欠陥が、別の帽子をかぶって
            # 戻ってくる (実測: 見た瞬間コートの56住所のうち21で
            # rival が CONTESTED ではなく ARM_FULL になった)。
            agrees = any(_vkey(e["value"]) == vkey for e in seat["values"])
            seat["values"].append({"value": copy.deepcopy(value),
                                   "kind": kind, "sources": [source]})
            # **課金されない腕を、黙って通さない。** 既にある席に新しい
            # 種別が届くと、その種別の腕には席が現れる (``seat_arms``) が
            # 予算は座ったときの腕にしか課されていない — この枝は容量を
            # 一度も聞かない。実測: support+ が4席で埋まった核に
            # ``derived`` を先に書いてから ``measured`` を書くと、直接
            # 書けば ARM_FULL で断られる主張が second_kind として通り、
            # ``arms_present['support+']`` が 5 になっても
            # ``over_capacity`` は空で ``verify()`` は ANSWER のまま。
            # **これをどう閉じるかは持ち主の決め** (``_arm_load`` の三案)
            # なので、ここでは変えずに**測って返す**: どの腕が課金されて
            # いないか、その腕が既に満杯か。``census()['uncharged']`` が
            # 店じゅうの同じものを数える。
            free_ride = self._uncharged(where, seat, arm)
            if free_ride is not None:
                self.uncharged.append(dict(free_ride, key=key))
            if agrees:
                # 値は一致、種別だけが新しい。**争いではない。**
                return {"verdict": "ANSWER", "state": "second_kind",
                        "core": where, "key": key, "arm": seat["arm"],
                        "charged_arm": seat["arm"],
                        "uncharged": free_ride,
                        "arms": seat_arms(seat), "kind": kind,
                        "weight": len(_independent(
                            [s for e in seat["values"]
                             if _vkey(e["value"]) == vkey
                             for s in e["sources"]])),
                        "seat_created": False}
            # 値が違う → **席は増やさない。その席で争う。**
            return {"verdict": CONTESTED_IN_CROSS, "core": where, "key": key,
                    "arm": seat["arm"], "charged_arm": seat["arm"],
                    "uncharged": free_ride,
                    "arms": seat_arms(seat),
                    "also_on": "support-",
                    "sides": len(seat["values"]), "seat_created": False,
                    "how_to_close": "宣言を確かめて、正しい方だけを残す"}

        if arm is not None and self._arm_load(core, arm) >= FACES_PER_ARM:
            return {"verdict": ARM_FULL, "core": core, "arm": arm,
                    "key": key,
                    "how_to_close": "子コアに分ける "
                                    "(マトリョーシカは幾何が要求すること)"}
        # 隔離席だけを数える枝はここに在った。**今は核の総席数が同じ
        # ことをより強く言う** (隔離席は必ず総席数の一部なので、
        # 隔離だけの上限は決して先に効かない — 効かない検査は無いのと
        # 同じで、この企画が八つ見つけた「落ちない検査」のコード版に
        # なる)。法は下の一箇所で、隔離核も腕付きの核も同じ 24。

        # **核そのものの上限。** 腕ごとの 4 と隔離席の 24 は別々に
        # 数えられていて、どちらも「核の全席」を見ていなかった — 名前が
        # 隔離核の形をした核は 20 の腕付き席 + 24 の隔離席 = 44 席まで
        # 伸びて、``census()['over_capacity']`` は空のままだった。
        # **1核 = 24席**は核の性質なので、席の種類で割り引かない。
        if len(self.cores.get(core, [])) >= CAPACITY_PER_CORE:
            return {"verdict": ARM_FULL, "core": core, "arm": arm,
                    "key": key, "seats": len(self.cores.get(core, [])),
                    "quarantined": self._quarantine_load(core),
                    "max": CAPACITY_PER_CORE,
                    "why": "1核 = 24席。腕ごとの予算とは別に、核そのものの"
                           "上限 — 隔離席も腕付きの席も同じ核の席として"
                           "数える",
                    "how_to_close": "子コアに分ける "
                                    "(マトリョーシカは幾何が要求すること)"}

        seat = {"key": key, "arm": arm,
                "seq": self._next_seq() if seq is None else seq,
                "values": [{"value": copy.deepcopy(value), "kind": kind,
                            "sources": [source]}]}
        self._core(core).append(seat)
        return {"verdict": "ANSWER", "state": "placed", "core": core,
                "key": key, "arm": arm, "weight": 1, "seat_created": True}

    def put(self, core: str, key: str, value: Any, kind: str,
            source: str = "", seq: Optional[int] = None) -> Dict[str, Any]:
        """**分ける書き口。** 腕が埋まったら子コアに分れ、nest 辺で繋ぐ。

        黙って席を増やさない — 分割は店の幾何(4面)が決めること。
        住所の解決は閉包の全体なので、分れた先に同じ鍵の別の値が
        落ちることはない(そちらは争いになる)。
        """
        r = self.put_strict(core, key, value, kind, source, seq)
        if r["verdict"] != ARM_FULL:
            if r["verdict"] != "ANSWER":
                self.refusals.append(dict(r))
            return r
        arm = KIND_ARM[kind]
        # ``proposed`` は隔離核に落ちている。分けるのはその核の側。
        # **既に隔離核の名前なら二度付けない。** ``put_strict`` は
        # :344 で ``and not _is_quarantine(core)`` を見ているのに、ここは
        # 見ていなかった — 自分が返した ``q#proposed`` をそのまま渡すと
        # ``q#proposed#proposed`` という**誰も作っていない核**の名前で
        # 分割が始まり、nest 辺は片端が居ないので断られ、子コアだけが
        # 宙に浮いた。実測: 30本の提案が孤立した6核に散って
        # ``contested()`` は空、``verify()`` は ANSWER、書いた側は二度
        # ANSWER を受け取り、``resolve`` は同じ住所を「無い」と答えた。
        if arm is None and not _is_quarantine(core):
            home = f"{core}#proposed"
        else:
            home = core
        label = arm if arm is not None else "proposed"
        chain = self._closure(home)
        for cur in chain[1:]:
            r = self.put_strict(cur, key, value, kind, source, seq)
            if r["verdict"] != ARM_FULL:
                if r["verdict"] != "ANSWER":
                    self.refusals.append(dict(r))
                return r

        n = len(chain)
        child = f"{home}·{label}·{n}"
        while child in self.cores:
            n += 1
            child = f"{home}·{label}·{n}"
        self._core(child)
        edge = self.link((chain[-1], ""), (child, ""), "nest")
        if edge["verdict"] != "ANSWER":
            # **繋がらなかった子には座らせない。** 親から届かない核の
            # 割れは構造上見えないので、そこに座った値は「載った」と
            # 言えない。以前はここで辺の断りを捨てて席だけ作り、
            # ``put()`` は ANSWER を返していた — 書いた側は成功したと
            # 思い、読む側は UNKNOWN_NOT_IN_CROSS を受け取った。
            self.cores.pop(child, None)
            r = {"verdict": DANGLING_EDGE, "stored": False, "core": home,
                 "child": child, "key": key, "why": edge.get("why"),
                 "how_to_close": "分ける先の親核を先に立ててから書く"}
            self.refusals.append(dict(r))
            return r
        r = self.put_strict(child, key, value, kind, source, seq)
        if r["verdict"] != "ANSWER":
            self.refusals.append(dict(r))
        return r

    def put_all(self, root: str, items: Sequence[Tuple[str, Any, str]],
                source: str) -> List[str]:
        """``(key, value, kind)`` を順に載せる。戻り値は載った核の列。"""
        for key, value, kind in items:
            self.put(root, key, value, kind, source)
        return self._closure(root)

    # ------------------------------------------------------------ 取り出し
    def resolve(self, core: str, key: str) -> Dict[str, Any]:
        """住所を解決する。**同点は棄権する。読みは何も作らない。**

        - 無い → UNKNOWN_NOT_IN_CROSS(「無い」は「0件の検索結果」と別)
        - 一意 → ANSWER(``weight`` は独立した出典の数)
        - 値が違うものが複数 → CONTESTED_IN_CROSS。両方を出し、
          **どちらも選ばない**。その住所は ``support-`` にも数える。
        """
        seats: List[Tuple[str, Dict[str, Any]]] = []
        for cname in self._closure(core):
            for s in self.cores.get(cname, []):
                if s["key"] == key:
                    seats.append((cname, s))
        if not seats:
            return {"verdict": NOT_IN_CROSS,
                    "why": f"{core} に {key} は載っていない",
                    "how_to_close": "宣言に足す"}

        entries = [(cn, e) for cn, s in seats for e in s["values"]]
        first = entries[0][1]["value"]
        arm = seats[0][1]["arm"]
        # **一致は ``_vkey`` で見る。素の ``==`` ではない。**
        # 書く側で True と 1 を割ったのに、読む側が ``==`` で畳んで
        # いたら、割れは席の中に居るのに誰にも見えない — 実測: put が
        # CONTESTED を返した直後に resolve が ANSWER / value=True /
        # weight 2 を返し、contested() も verify() も静かだった。
        # 断りが書き口にしか無いのは、断っていないのと同じ。
        vk_first = _vkey(first)
        if all(_vkey(e["value"]) == vk_first for _cn, e in entries):
            sources: List[str] = []
            for _cn, e in entries:
                for src in e["sources"]:
                    if src not in sources:
                        sources.append(src)
            by_kind: Dict[str, List[str]] = {}
            for _cn, e in entries:
                by_kind.setdefault(e["kind"], [])
                for src in e["sources"]:
                    if src not in by_kind[e["kind"]]:
                        by_kind[e["kind"]].append(src)
            return {"verdict": "ANSWER", "value": copy.deepcopy(first),
                    "sources": _independent(sources),
                    "weight": len(_independent(sources)),
                    #: **種別ごとの重み。** ``weight`` は住所ぜんぶの
                    #: 独立した出典で、種別をまたいで数える — つまり
                    #: specific 一本が generic の見かけの重みを 2 に
                    #: できる (門である ``unbought_generics`` は騙され
                    #: ないが、読んだ数字は騙される)。
                    #: ``GENERIC_MIN_SOURCES`` が値段を付けているのは
                    #: こちらの数。
                    "weight_by_kind": {k: len(_independent(v))
                                       for k, v in by_kind.items()},
                    "named_sources": list(sources),
                    "agreed": len(entries), "arm": arm,
                    #: **予算を払った一本**。意味の腕は ``arms``。
                    "charged_arm": arm,
                    #: **腕は読みからも見える。** ``arm`` は予算を払った
                    #: 一本、``arms`` は届いた種別すべての腕。読みから
                    #: 見えないと、順序検査が比べようがない。
                    #:
                    #: **``arm`` を読むものは順に依る。** 二種別が届いた
                    #: 住所では ``resolve()['arm']``、``['where']['arm']``、
                    #: ``seats()[]['arm']``、``census()['arms']``、
                    #: ``contested()[]['arm']`` の五つが書いた順で動く
                    #: (実測)。「単一の腕を読むものは無い」は誤りで、
                    #: 意味を運ぶのは ``arms`` の方。予算の腕をどう決める
                    #: かは ``_arm_load`` の未決の三案。
                    "arms": _arms_of(seats),
                    "kinds": [e["kind"] for _cn, e in entries],
                    "seq": min(s["seq"] for _cn, s in seats),
                    "where": {"core": seats[0][0], "arm": arm}}
        return {"verdict": CONTESTED_IN_CROSS,
                "sides": [{"value": copy.deepcopy(e["value"]),
                           "kind": e["kind"], "sources": list(e["sources"]),
                           "weight": len(_independent(e["sources"])),
                           "core": cn} for cn, e in entries],
                "arm": arm, "charged_arm": arm,
                "arms": _arms_of(seats), "also_on": "support-",
                "seq": min(s["seq"] for _cn, s in seats),
                "how_to_close": "宣言を確かめて、正しい方だけを残す",
                "where": {"core": seats[0][0], "arm": arm}}

    def require(self, core: str, key: str) -> Any:
        """値を必須で取る。断られたら例外で止まる(**埋めない**)。"""
        r = self.resolve(core, key)
        if r["verdict"] == "ANSWER":
            return r["value"]
        raise ValueError(f'{r["verdict"]}: {core}/{key}')

    def seats(self, core: str, prefix: Optional[str] = None
              ) -> List[Dict[str, Any]]:
        """閉包の席を**宣言順(seq)で**返す。``prefix`` で鍵を絞る。

        並びが seq なのは、**宣言の順は宣言の内容であって格納ではない**
        から。主題コアに散らばっても読む順は動かない。
        """
        out: List[Dict[str, Any]] = []
        seen: set = set()
        for cname in self._closure(core):
            for s in self.cores.get(cname, []):
                if prefix is not None and not s["key"].startswith(prefix):
                    continue
                if s["key"] in seen:
                    continue
                seen.add(s["key"])
                r = self.resolve(cname, s["key"])
                rec = dict(r)
                rec["core"] = cname
                rec["key"] = s["key"]
                rec["arm"] = s["arm"]
                rec["seq"] = s["seq"]
                out.append(rec)
        out.sort(key=lambda r: (r["seq"], r["key"]))
        return out

    def part_of_children(self, core: str) -> List[str]:
        """``a part_of b`` の a たち。**主題の子** — 閉包には入らない。"""
        out: List[str] = []
        for e in self.edges:
            if e["label"] == "part_of" and _is_addr(e["a"]) \
                    and _is_addr(e["b"]) and e["b"][0] == core:
                if e["a"][0] not in out:
                    out.append(e["a"][0])
        return out

    def contested(self) -> List[Dict[str, Any]]:
        """店じゅうの割れの一覧。**片方は選ばれていない。**

        判定は閉包ごと — 別コアに落ちた同じ鍵の別の値も割れとして見える。
        """
        out: List[Dict[str, Any]] = []
        done: set = set()
        for cname in list(self.cores):
            closure = self._closure(cname)
            token = frozenset(closure)
            if token in done:
                continue
            done.add(token)
            by_key: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
            for cn in closure:
                for s in self.cores.get(cn, []):
                    by_key.setdefault(s["key"], []).append((cn, s))
            for key, group in by_key.items():
                vals = [e["value"] for _cn, s in group for e in s["values"]]
                # 同じく ``_vkey``。NaN は自分と等しくないので素の ``!=``
                # だと自分自身と割れて見え、True/1 は逆に割れが消える。
                vks = [_vkey(v) for v in vals]
                if any(v != vks[0] for v in vks[1:]):
                    out.append({"core": group[0][0], "key": key,
                                "arm": group[0][1]["arm"],
                                "also_on": "support-",
                                "sides": len(vals)})
        out.sort(key=lambda r: (r["core"], r["key"]))
        return out

    # ------------------------------------------------------------ 腕の意味
    def arm_census(self, core: str) -> Dict[str, int]:
        """閉包の腕ごとの席数。**support- は割れた住所の数。**

        support- は誰も名指しで書けない腕なので、ここでだけ数が入る。
        """
        counts = {a: 0 for a in ARMS}
        closure = set(self._closure(core))
        for cn in closure:
            for s in self.cores.get(cn, []):
                for a in seat_arms(s):
                    counts[a] += 1
        counts["support-"] = sum(
            1 for c in self.contested() if c["core"] in closure)
        return counts

    def gaps(self, core: str) -> List[str]:
        """空いている腕を**型付きの欠落**として返す。

        「知らない」ではなく「どの種類の知識が無いか」。支えが無ければ
        UNKNOWN_NO_SUPPORT_RECORDED、由来が無ければ
        UNKNOWN_NO_CAUSE_RECORDED。
        """
        cen = self.arm_census(core)
        return [ARM_GAP_VERDICT[a] for a in ARMS if not cen[a]]

    def unbought_generics(self) -> List[Dict[str, Any]]:
        """**独立した出典が2本無い一般構造の主張。** 黙って信じない。"""
        out: List[Dict[str, Any]] = []
        for cname, seats in self.cores.items():
            for s in seats:
                # **一般構造だと言った主張だけを見る。** 席の腕ではなく
                # 各主張の kind を見るのは、同じ住所に specific が同意
                # しても一般構造を買ったことにはならないから。以前は
                # 出典が席にまとめられていたので、specific 一本で
                # generic が買えた (実測: parts:closure が 1→2 に増えて
                # 未購入から消えた)。
                gen = [e for e in s["values"] if e.get("kind") == "generic"]
                if not gen:
                    continue
                # **名無しは数えない。** 空の出典が一本として数えられて
                # いたので、``put(...,'generic')`` を出典なしで一度、
                # 名のある出典で一度書くだけで「独立した出典2本」が
                # 揃ったことになっていた (実測: 重み2、未購入から消えた)。
                weight = max((len(_independent(e["sources"])) for e in gen),
                             default=0)
                if weight < GENERIC_MIN_SOURCES:
                    out.append({"verdict": GENERIC_NOT_BOUGHT,
                                "core": cname, "key": s["key"],
                                "weight": weight,
                                "need": GENERIC_MIN_SOURCES,
                                "how_to_close":
                                    f"独立した出典を{GENERIC_MIN_SOURCES}本"
                                    "示すか、specific に落とす"})
        out.sort(key=lambda r: (r["core"], r["key"]))
        return out

    # ------------------------------------------------------------ 辺
    def link(self, a: Addr, b: Addr, label: str,
             value: Any = None) -> Dict[str, Any]:
        """辺を結ぶ。面を消費しない — **関係は席を要らない。**

        **片端の辺は関係ではない。** 両端が (core, key) の形で、両方の
        核が実在し、名前が閉じた語彙にあること。自分自身との関係は
        正しい(袖下線は一枚の二辺を縫う)。断りは戻り値で、そのとき
        辺は**増えない**。
        """
        bad: List[str] = []
        if not _is_addr(a):
            bad.append(f"a={a!r} は (core, key) の形ではない")
        elif a[0] not in self.cores:
            bad.append(f"a の核 {a[0]!r} は店に無い")
        if not _is_addr(b):
            bad.append(f"b={b!r} は (core, key) の形ではない")
        elif b[0] not in self.cores:
            bad.append(f"b の核 {b[0]!r} は店に無い")
        if not _label_ok(label):
            bad.append(f"label={label!r} は閉じた語彙 "
                       f"{EDGE_LABELS}+{EDGE_LABEL_PREFIXES} に無い")
        if bad:
            r = {"verdict": DANGLING_EDGE, "why": bad, "stored": False,
                 "how_to_close": "両端の核を先に立ててから結ぶ"}
            self.refusals.append(dict(r))
            return r
        self.edges.append({"a": (a[0], a[1]), "b": (b[0], b[1]),
                           "label": label, "value": copy.deepcopy(value)})
        return {"verdict": "ANSWER", "index": len(self.edges) - 1,
                "label": label}

    def edges_are_relations(self) -> Dict[str, Any]:
        """載っている辺が全部**二端の関係**かを見る(読み込み後の検査)。"""
        bad: List[Dict[str, Any]] = []
        for i, e in enumerate(self.edges):
            why: List[str] = []
            if not _is_addr(e.get("a")):
                why.append("a が (core, key) ではない")
            elif e["a"][0] not in self.cores:
                why.append(f'a の核 {e["a"][0]!r} が居ない')
            if not _is_addr(e.get("b")):
                why.append("b が (core, key) ではない")
            elif e["b"][0] not in self.cores:
                why.append(f'b の核 {e["b"][0]!r} が居ない')
            if not _label_ok(e.get("label")):
                why.append(f'label {e.get("label")!r} が語彙に無い')
            if why:
                bad.append({"verdict": DANGLING_EDGE, "index": i,
                            "edge": repr(e)[:120], "why": why})
        if bad:
            return {"verdict": DANGLING_EDGE, "bad": bad,
                    "checked": len(self.edges)}
        return {"verdict": "ANSWER", "checked": len(self.edges)}

    def edges_labeled(self, label_prefix: str) -> List[Dict[str, Any]]:
        return [copy.deepcopy(e) for e in self.edges
                if isinstance(e.get("label"), str)
                and e["label"].startswith(label_prefix)]

    def edges_from(self, core: str) -> List[Dict[str, Any]]:
        return [copy.deepcopy(e) for e in self.edges
                if (_is_addr(e.get("a")) and e["a"][0] == core)
                or (_is_addr(e.get("b")) and e["b"][0] == core)]

    # ------------------------------------------------------------ 検証
    def verify(self) -> Dict[str, Any]:
        """幾何が守られているかを店の全体で見る。**入口は一つではない。**

        ``from_dict`` は手で書いた JSON も受ける口なので、コンストラクタ
        だけ守っても意味がない。ここで見るのは:
        腕が既知の六本か / 腕が kind から導かれているか /
        一つの閉包に同じ住所が二つ無いか / 腕あたりの席が4以下か /
        辺が全部二端の関係か / 分れた子コアが nest 辺で届くか。
        """
        problems: List[Dict[str, Any]] = []
        for cname, seats in self.cores.items():
            if not isinstance(seats, list):
                problems.append({"verdict": "UNKNOWN_MALFORMED_CORE",
                                 "core": cname})
                continue
            for s in seats:
                arm = s.get("arm")
                if arm is not None and arm not in ARMS:
                    problems.append({"verdict": "UNKNOWN_NO_SUCH_ARM",
                                     "core": cname, "key": s.get("key"),
                                     "arm": arm})
                    continue
                vals = s.get("values") or []
                for e in vals:
                    if e.get("kind") not in KIND_ARM:
                        problems.append({"verdict": NO_SUCH_KIND,
                                         "core": cname, "key": s.get("key"),
                                         "kind": e.get("kind")})
                if vals and vals[0].get("kind") in KIND_ARM:
                    want = KIND_ARM[vals[0]["kind"]]
                    if want != arm:
                        problems.append(
                            {"verdict": ARM_NOT_DERIVED, "core": cname,
                             "key": s.get("key"), "arm": arm,
                             "kind": vals[0]["kind"], "should_be": want,
                             "why": "腕は kind から導かれる。"
                                    "書く側が選ぶものではない"})
                # 一つの席で (kind, 値) は一度だけ。同じ主張を二つの
                # 項目に分けて書くと、出典の数が席の数に化けて
                # GENERIC_MIN_SOURCES が数え間違える。
                claims: set = set()
                for e in vals:
                    if e.get("kind") not in KIND_ARM:
                        continue
                    tok = (e.get("kind"), _vkey(e.get("value")))
                    if tok in claims:
                        problems.append(
                            {"verdict": DUPLICATE_CLAIM, "core": cname,
                             "key": s.get("key"), "kind": e.get("kind"),
                             "why": "同じ席に同じ (種別, 値) が二つ。"
                                    "同じ主張の裏付けは出典を足すこと"})
                    claims.add(tok)
            for arm in ARMS:
                load = sum(1 for s in seats if s.get("arm") == arm)
                if load > FACES_PER_ARM:
                    problems.append({"verdict": OVER_CAPACITY,
                                     "core": cname, "arm": arm,
                                     "seats": load, "max": FACES_PER_ARM})
            free = sum(1 for s in seats
                       if isinstance(s, dict) and s.get("arm") is None)
            if free > CAPACITY_PER_CORE:
                problems.append({"verdict": OVER_CAPACITY, "core": cname,
                                 "arm": None, "seats": free,
                                 "max": CAPACITY_PER_CORE,
                                 "why": "隔離核も 1核=24席"})
            # **核そのものの総席数。** 腕ごとの 4 と隔離核の 24 は
            # 別々に数えられていて、どちらも核の全体を見ていなかった —
            # 一つの核が 20 の腕付き席 + 24 の隔離席 = 44 席を持って
            # いても ``over_capacity`` は空だった。「1核 = 24席」は
            # 席の種類ではなく核の性質。
            if len(seats) > CAPACITY_PER_CORE:
                problems.append({"verdict": OVER_CAPACITY, "core": cname,
                                 "arm": "total", "seats": len(seats),
                                 "max": CAPACITY_PER_CORE,
                                 "why": "1核 = 24席。腕付きの席と隔離席を"
                                        "合わせても超えない"})
            # **保存できない値が座っていないか。** 書き口は断るように
            # なったが、``from_dict`` は手で書いた JSON も受ける口なので
            # ここでも見る (set や自作クラスは JSON を往復しない)。
            for s in seats:
                if not isinstance(s, dict):
                    continue
                for e in (s.get("values") or []):
                    why_not = _persistable(e.get("value"))
                    if why_not:
                        problems.append(
                            {"verdict": UNIDENTIFIABLE_VALUE, "core": cname,
                             "key": s.get("key"), "why": why_not[:3],
                             "type": type(e.get("value")).__name__})

        done: set = set()
        for cname in list(self.cores):
            closure = self._closure(cname)
            token = frozenset(closure)
            if token in done:
                continue
            done.add(token)
            seen: Dict[str, str] = {}
            for cn in closure:
                for s in self.cores.get(cn, []):
                    k = s.get("key")
                    if k in seen:
                        problems.append({"verdict": DUPLICATE_ADDRESS,
                                         "key": k, "cores": [seen[k], cn],
                                         "why": "一つの閉包に同じ住所が二つ"})
                    else:
                        seen[k] = cn

        er = self.edges_are_relations()
        if er["verdict"] != "ANSWER":
            problems.extend(er["bad"])

        for cname in self.cores:
            if "·" not in cname:
                continue
            parent = cname.split("·")[0]
            # **親が居ない子も孤児。** 以前は ``parent in self.cores`` が
            # 前提だったので、**親が一度も作られていない**子 — 分割の
            # 名前だけが立って中身の無い核を指している状態 — は検査を
            # まるごと素通りした。実測: ``q#proposed#proposed·proposed·1``
            # から ``·6`` までの6核が誰からも届かないまま
            # ``verify() == ANSWER``。
            if parent not in self.cores:
                problems.append(
                    {"verdict": ORPHANED_CORE, "core": cname,
                     "parent": parent,
                     "why": "分れた子の親核が店に無い — "
                            "この核は誰からも届かない"})
            elif cname not in self._closure(parent):
                problems.append(
                    {"verdict": ORPHANED_CORE, "core": cname,
                     "parent": parent,
                     "why": "分れた子が nest 辺で親から届かない — "
                            "この核の割れは構造上見えない"})

        alias = self.aliased_values()
        if alias["verdict"] != "ANSWER":
            problems.extend(alias["bad"])

        if problems:
            return {"verdict": problems[0]["verdict"], "problems": problems,
                    "cores": len(self.cores)}
        return {"verdict": "ANSWER", "cores": len(self.cores),
                "seats": sum(len(s) for s in self.cores.values()),
                "edges": len(self.edges)}

    def aliased_values(self) -> Dict[str, Any]:
        """**同じオブジェクトが二箇所に座っていないか。**

        座っていると、外から一方を書き換えて CONTESTED を ANSWER に
        戻せてしまう(扉の外側に取っ手が付く)。不変な値は共有されても
        害が無いので、可変な入れ物だけ見る。
        """
        seen: Dict[int, Tuple[str, str]] = {}
        bad: List[Dict[str, Any]] = []
        for cname, seats in self.cores.items():
            for s in seats:
                for e in (s.get("values") or []):
                    v = e.get("value")
                    if not isinstance(v, (dict, list, set, bytearray)):
                        continue
                    if id(v) in seen:
                        first = seen[id(v)]
                        bad.append({"verdict": ALIASED_VALUE,
                                    "key": s.get("key"),
                                    "cores": [first[0], cname],
                                    "keys": [first[1], s.get("key")],
                                    "why": "同じオブジェクトが二席に居る。"
                                           "外から片方を書き換えられる"})
                    else:
                        seen[id(v)] = (cname, s.get("key"))
        if bad:
            return {"verdict": ALIASED_VALUE, "bad": bad}
        return {"verdict": "ANSWER", "checked": len(seen)}

    # ------------------------------------------------------------ 配置不変性
    def placement_check(self) -> Dict[str, Any]:
        """**解決器の後退よけ。** 本物の順序検査は ``ingest_order_check``。

        ここでやるのは、いま載っている席を書き込み計画として取り出し、
        分ける書き口で入れ直して、住所→値の地図が動かないことの確認。
        以前ここにあったものは同じ店を二度**読む**だけで、店は間に
        変わらないので落ちようがなかった(名前は「格納順」と言って
        いたのに、見ていたのは読む順)。
        """
        plan = self.write_plan()
        r = ingest_order_check(plan, nest=True)
        # ``"structural": True`` はここに在った。**定数は証拠ではない。**
        # 読む側はそれを根拠のように使えてしまい (実測: 検査の第二節が
        # ``inv.get("structural")`` で、機械を全部外しても緑のまま)、
        # 「通ったことは何かの確認である」と言いたい欄が、何も確認して
        # いないことの証明書になっていた。落ちうる欄だけを残す。
        return {"verdict": r["verdict"],
                "not_a_test": ("いま載っているものを入れ直しても答えが"
                               "動かない、という後退よけです。本物の"
                               "順序検査は ingest_order_check"),
                "addresses_checked": r["addresses"],
                "orders": r["orders"],
                "differences": r.get("differences", []),
                "why_it_matters":
                    "配置が答えを決めているなら、それは宣言ではなく並びの産物",
        }

    def write_plan(self) -> List[Tuple[str, str, Any, str, str]]:
        """いま載っているものを ``(core, key, value, kind, source)`` の列に。

        分れた子コアは閉包の代表(親)の名前に畳む — 住所は閉包の全体で
        一つなので、どの核から書いたかは計画の情報ではない。
        """
        roots: Dict[str, str] = {}
        for cname in sorted(self.cores):
            if cname in roots:
                continue
            closure = self._closure(cname)
            rep = min(closure, key=lambda n: (len(n), n))
            for cn in closure:
                roots[cn] = rep
        plan: List[Tuple[str, str, Any, str, str]] = []
        for cname, seats in self.cores.items():
            for s in seats:
                for e in s["values"]:
                    for src in e["sources"]:
                        plan.append((roots[cname], s["key"],
                                     copy.deepcopy(e["value"]), e["kind"],
                                     src))
        plan.sort(key=lambda t: (t[0], t[1]))
        return plan

    # ------------------------------------------------------------ 出し入れ
    def to_dict(self) -> Dict[str, Any]:
        return {"cores": {n: copy.deepcopy(seats)
                          for n, seats in self.cores.items()},
                "edges": [copy.deepcopy(e) for e in self.edges],
                "seq": self._seq}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrossStore":
        """読み込む。**幾何を検査して ``load_verdict`` に控える。**

        戻り値は店のまま(呼ぶ側が壊れない)。道具の境界には
        ``from_dict_checked`` を使う — 断りは戻り値であって、
        classmethod が突然 dict を返し始めるのは境界の壊し方。
        """
        st = cls()
        st.cores = {n: [
            {"key": s.get("key"), "arm": s.get("arm"),
             "seq": s.get("seq", 0),
             "values": [{"value": copy.deepcopy(e.get("value")),
                         "kind": e.get("kind"),
                         "sources": list(e.get("sources") or [])}
                        for e in (s.get("values") or [])]}
            for s in seats] for n, seats in data.get("cores", {}).items()}
        st.edges = []
        for e in data.get("edges", []):
            a, b = e.get("a"), e.get("b")
            st.edges.append({
                "a": tuple(a) if isinstance(a, (list, tuple)) else a,
                "b": tuple(b) if isinstance(b, (list, tuple)) else b,
                "label": e.get("label"),
                "value": copy.deepcopy(e.get("value"))})
        st._seq = int(data.get("seq") or 0) or max(
            (s["seq"] for seats in st.cores.values() for s in seats),
            default=0)
        st.load_verdict = st.verify()
        return st

    @classmethod
    def from_dict_checked(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """道具の境界用。``{verdict, store}`` を返す。**例外で越えない。**"""
        st = cls.from_dict(data)
        return {"verdict": st.load_verdict["verdict"], "store": st,
                "detail": st.load_verdict}

    # ------------------------------------------------------------ 観測
    def census(self) -> Dict[str, Any]:
        """店の在り方の集計。**席の数は幾何どおりに収まっているか。**

        ``seats`` は住所の数、``facets`` は値の数。4人が同意した1つの
        寸法は 1席 / 1facet / 4出典 — 同意は席を食わない。
        """
        seats = sum(len(s) for s in self.cores.values())
        facets = sum(len(x["values"]) for s in self.cores.values() for x in s)
        sources = sum(len(e["sources"]) for s in self.cores.values()
                      for x in s for e in x["values"])
        over = []
        #: ``arms`` は**座った**住所の数 (予算)。``arms_present`` は
        #: その腕に**現れる**住所の数 (意味) — 一つの席が二つの種別を
        #: 抱えていれば両方に現れるので、こちらは 4 を超えうる。
        arms = {a: 0 for a in ARMS}
        present = {a: 0 for a in ARMS}
        quarantine = {}
        for n, s in self.cores.items():
            for arm in ARMS:
                load = sum(1 for x in s if x["arm"] == arm)
                arms[arm] += load
                present[arm] += sum(1 for x in s if arm in seat_arms(x))
                if load > FACES_PER_ARM:
                    over.append((n, arm, load))
            # **隔離核も数える。** 腕を持たない席は核あたり 24 席まで。
            # 数えないでいると「この店は容量を超えた要求を黙って
            # 拡張しない」が proposed の側だけ嘘になる。
            free = sum(1 for x in s if x["arm"] is None)
            if free:
                quarantine[n] = free
                if free > CAPACITY_PER_CORE:
                    over.append((n, None, free))
            # **核の総席数も見る。** 腕ごとと隔離ごとを別々に数えると、
            # 両方を持つ核はどちらの予算も超えないまま 44 席まで伸びる。
            if len(s) > CAPACITY_PER_CORE:
                over.append((n, "total", len(s)))
        # **予算の腕は今どう決まっているか、口に出す。** 席の腕
        # (``arms``、予算) は**最初に届いた種別**が決めている。これは
        # 未決の設計判断で (``_arm_load`` の三案)、隠すと「腕は導かれる」
        # という店の看板と食い違う。だから数える: 二つ以上の種別が届いた
        # 住所はいくつあり、そのうち予算を払っていない腕はどれか。
        two_kind = []
        for n, s in self.cores.items():
            for x in s:
                kinds = [e.get("kind") for e in (x.get("values") or [])]
                if len({KIND_ARM.get(k) for k in kinds if k in KIND_ARM}) > 1:
                    two_kind.append((n, x["key"], x["arm"],
                                     seat_arms(x)))
        return {"cores": len(self.cores), "seats": seats, "facets": facets,
                "quarantined": quarantine,
                "sources": sources,
                "capacity_per_core": CAPACITY_PER_CORE,
                "over_capacity": over,
                "arms": arms,
                "arms_present": present,
                #: **予算の腕の決め方**と、それが効く住所。
                #: ``first_kind_seated`` = 先に座った種別の腕が面を払う。
                "budget_arm_rule": "first_kind_seated",
                "two_kind_addresses": sorted(two_kind),
                "uncharged": [dict(u) for u in self.uncharged],
                "edges": len(self.edges),
                "contested": len(self.contested())}


# ---------------------------------------------------------------------------
def _rep(v: Any) -> str:
    """比較用の札。**店が「同じ観測か」に使うのと同じ物差し。**

    ``repr`` を使っていると ``(1, 2)`` と ``[1, 2]`` が別物に見えるが、
    この店の保存形式は JSON なので往復すると同じものになる — 検査が
    往復で落ちるようになってしまう。``_vkey`` はそこを畳む。
    """
    return repr(_vkey(v))


def ingest_order_check(plan: Sequence[Tuple[str, str, Any, str, str]],
                       nest: bool = True) -> Dict[str, Any]:
    """**同じ計画を別の順で入れ直して、答えが動かないことを見る。**

    見るのは3つ: 住所 → (verdict, 値の集合, 重み) の地図、割れの集合、
    そして**断られた書き込みの集合**。ある順では座れて別の順では断られる
    書き込みがあるなら、それが順序依存の実体です。

    ``nest=False``(分けない書き口)で腕から溢れる計画は**本当に**順序
    依存になる — 先に来た4つが座り、5つ目が断られるので、どれが座るかは
    順で決まる。だからこの検査は落ちうるし、だから ``block.ingest`` は
    分けない書き口を使ってはいけない。
    """
    plan = list(plan)
    n = len(plan)
    orders = {
        "forward": list(range(n)),
        "reversed": list(reversed(range(n))),
        "rotated": list(range(n // 2, n)) + list(range(n // 2)),
    }
    runs: Dict[str, Dict[str, Any]] = {}
    for name, order in orders.items():
        st = CrossStore()
        refused: List[Tuple[str, str]] = []
        for i in order:
            core, key, value, kind, source = plan[i]
            r = (st.put(core, key, value, kind, source) if nest
                 else st.put_strict(core, key, value, kind, source))
            if r["verdict"] not in ("ANSWER", CONTESTED_IN_CROSS):
                refused.append((core, key))
        # **地図には腕も入れる。** (verdict, 値, 重み) だけを
        # 比べていたので、**腕で答えるものは全部この検査の外に居た** —
        # arm_census()、gaps()、型付きの欠落、unbought_generics()。
        # 腕が意味を運ぶという主張の店で、腕の置き場所が順で動いても
        # 「格納順は答えを動かさない」が ANSWER を返していた
        # (実測: 同じ値を measured→declared と declared→measured で
        #  入れると席の腕が support+ と kind- に分かれ、検査は ANSWER)。
        #
        # **``seq`` は入れない。入れてはいけない。** seq は「何番目に
        # 書かれたか」の控えで、答えではなく**格納順そのもの**。逆順で
        # 入れれば逆順の seq が付くのが正しい振る舞いなので、これを
        # 比べると検査は何を入れても必ず落ちる (実測: コートの56住所
        # 全部が forward seq 1..56 / reversed seq 56..1 で「相違」に
        # なった)。宣言の並びが読みを決めているかは
        # 「ordered reads follow the declaration」の持ち場で、あちらは
        # seq を**書く側が指定した**店で測っている。
        amap: Dict[Tuple[str, str], Any] = {}
        for core, key, _v, _k, _s in plan:
            r = st.resolve(core, key)
            shape = (r.get("arm"), tuple(r.get("arms") or ()))
            if r["verdict"] == "ANSWER":
                amap[(core, key)] = ("ANSWER", _rep(r["value"]),
                                     r["weight"], shape)
            elif r["verdict"] == CONTESTED_IN_CROSS:
                amap[(core, key)] = (
                    CONTESTED_IN_CROSS,
                    tuple(sorted(_rep(s["value"]) for s in r["sides"])),
                    0, shape)
            else:
                amap[(core, key)] = (r["verdict"], None, 0, shape)
        # **入れてみて外したもの、二つ。** どちらも実測して外した。
        #
        # 1. 型付きの欠落 (``gaps`` / ``arm_census``)。#3 が足せと言って
        #    いた節だが、これは (住所ごとの腕, 計画の核) の関数で、
        #    どちらも上の ``shape`` と鍵で既に比べている。**落ちようが
        #    無い節**で、この企画が三度出した「落ちない検査」の四度目に
        #    なる。腕は ``shape`` が運ぶ。
        # 2. 核の名前の集合。これは**本当に順で動く** (実測: コートの
        #    10核が forward では block:coat·cause+·1 / ·cause+·2 /
        #    ·kind-·3 / ·kind-·4、reversed では ·kind-·1..4 になる —
        #    どちらの腕が先に溢れたかが子の名前に入るので)。だが動いた
        #    のは**答えではなく格納の呼び名**で、56住所は全部どちらの
        #    順でも同じ値・同じ重み・同じ腕に解決する。ここで比べると、
        #    壊れていないコートを壊れていると言うことになる。
        runs[name] = {
            "map": amap,
            "contested": sorted((c["core"], c["key"]) for c in st.contested()),
            "refused": sorted(set(refused)),
        }

    base = runs["forward"]
    differences: List[Dict[str, Any]] = []
    for name, run in runs.items():
        if name == "forward":
            continue
        for addr in sorted(set(base["map"]) | set(run["map"])):
            if base["map"].get(addr) != run["map"].get(addr):
                differences.append({"order": name, "address": list(addr),
                                    "forward": base["map"].get(addr),
                                    "other": run["map"].get(addr)})
        if base["contested"] != run["contested"]:
            differences.append({"order": name, "what": "contested",
                                "forward": base["contested"],
                                "other": run["contested"]})
        if base["refused"] != run["refused"]:
            differences.append({"order": name, "what": "refused",
                                "forward": base["refused"],
                                "other": run["refused"]})
    # **予算の腕だけが違う相違を、別に数える。** 値も重みも意味の腕
    # (``arms``) も同じで、面を払った一本 (``shape[0]``) だけが順で動く
    # 相違は「答えが動いた」ではなく「**まだ決めていない**」の現れ方。
    # ``_arm_load`` の三案のどれを採るかで消え方が変わるので、混ぜずに
    # 数える。
    budget_only = 0
    for d in differences:
        f, o = d.get("forward"), d.get("other")
        if (isinstance(f, tuple) and isinstance(o, tuple) and len(f) == 4
                and len(o) == 4 and f[:3] == o[:3]
                and f[3][1] == o[3][1] and f[3][0] != o[3][0]):
            budget_only += 1
    return {
        "verdict": "ANSWER" if not differences else ORDER_DEPENDENT,
        "orders": len(orders),
        "addresses": len(base["map"]),
        "writes": n,
        "nesting": nest,
        "budget_arm_rule": "first_kind_seated",
        "budget_arm_differences": budget_only,
        "differences": differences[:12],
        "why_it_matters":
            "格納順が答えを決めているなら、それは宣言ではなく並びの産物",
    }
