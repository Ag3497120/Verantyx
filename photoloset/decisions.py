# -*- coding: utf-8 -*-
"""判断リスト — 連鎖のどこかで何が仮定され、何がまだ人待ちかを、一箇所で言う。

このモジュールは経路を知らない。``compose`` の結果も ``bom`` の結果も
``confirm`` の結果も、辞書のリストの辞書という同じ形をしているという
一点にだけ依存する。ホップの名前(``"levels"`` とか ``"rings"`` とか)を
どこにも書かない — 書けば、後から増える七本目のモジュールの形が変わった
日に、ここが黙って見落とす側になる。

**契約は上流が守る。** この一連の他のファイルが、拒否の辞書に
``assumed`` / ``basis`` / ``kind`` / ``alternatives`` を足していく
(``verdict`` / ``why`` / ``how_to_close`` は今までどおり)。ここはそれを
**読むだけ**。値を選ばない、result を書き換えない、上流が言っていない
ことを埋めない — ``collect`` が返すのは元の辞書を deepcopy して path を
添えたものだけで、そこに無い情報をこのモジュールが足すことは無い。

分類は三段、上から順に判定する:

1. ``assumed`` キーが有り、値が ``None`` でない → 何かが仮定された。
   ``basis`` が有り、かつ ``kind`` が ``INFERRED``/``PROPOSED`` の
   どちらかであれば、その通り ``inferred``/``proposed`` へ。
   **それ以外は全部 defect。** ``basis`` が無い・空、``kind`` が
   ``OBSERVED`` を含め上の二つでない — どちらであっても、上流が契約を
   破ったということであって、それを ``inferred`` に紛れ込ませて緑に
   見せることは絶対にしない。これがこのモジュールの存在理由そのもの
   (契約の規則1: 「根拠の言えない値は assumed を書かない」を、上流が
   守らなかった場合の受け皿)。
2. ``assumed`` が無く、``verdict`` が文字列で ``UNKNOWN_`` から始まる →
   正直な値が無いまま止まっている hard stop。``blocked`` へ。
3. どちらでもなく、``kind`` か ``state`` が文字列 ``"OBSERVED"`` →
   テープか輪郭そのものから来た値。``measured`` へ。この契約を実装する
   六本の refusal はどれも ``OBSERVED`` を名乗ることが無い(定義上、
   拒否は測定していないから拒否している)ので、この列は今日はほぼ
   確実に空になる。それはバグではなく、出典を名乗っていない値を実測
   扱いにしないという誠実さの結果 — 空を埋めて見栄えを良くする方が
   簡単だが、それこそがこの一連のファイルが拒んでいる「もっともらしい
   数字が拒否の代わりに立つ」形そのものになる。

どの段にも当てはまらない辞書(たとえば ``ANSWER`` の本体そのもの、
``alternatives`` の中の ``{"value", "basis"}`` だけの要素)は、ただ潜って
中を見るだけでどのリストにも載らない。
"""
from __future__ import annotations

import copy
from typing import Any, Dict, FrozenSet, List, Union

#: ``kind`` としてこのモジュールが認める、仮定の種類。``OBSERVED`` は
#: 仮定の kind としては絶対に来てはいけない値(契約の規則1) — 来ても
#: ここでは黙って弾き、defect に回す。
INFERRED = "INFERRED"
PROPOSED = "PROPOSED"
OBSERVED = "OBSERVED"
_ASSUMPTION_KINDS = (INFERRED, PROPOSED)

_UNKNOWN_PREFIX = "UNKNOWN_"

#: パスの一区間。dict は key(str)、list/tuple は添字(int)。
PathStep = Union[str, int]


def _path_str(path: List[PathStep]) -> str:
    """``$`` を根に、辞書キーは ``.key``、添字は ``[i]`` で綴る。

    JSON Path 風にしているのは読みやすさのためだけで、この文字列を
    後から parse して result 側へ逆に辿る用途では使っていない — UI が
    「ここを指している」と示すためのラベルであって、住所として
    再解析するものではない。
    """
    out = "$"
    for seg in path:
        out += f"[{seg}]" if isinstance(seg, int) else f".{seg}"
    return out


def _entry(path: List[PathStep], node: Dict[str, Any]) -> Dict[str, Any]:
    """元の辞書を書き換えず、path を添えて包むだけの器。

    フィールド名を先回りして拾わない — ``assumed``/``basis``/``verdict``
    /``why``/``how_to_close``/``alternatives`` のどれを見るかは呼び出し側
    (UI)が決める。``deepcopy`` するのは、後で誰かが
    ``entry["entry"]["alternatives"].append(...)`` のようなことをしても
    元の result が動かないようにするため。このモジュールは「報告する
    だけ」で、返した先で起きた変更が結果側に漏れ返ることも無い。
    """
    return {"path": _path_str(path), "entry": copy.deepcopy(node)}


def _defect(path: List[PathStep], node: Dict[str, Any],
           reason: str) -> Dict[str, Any]:
    """契約違反そのものを報告する一行。値を直したり、basis を作ったりしない。

    ``module`` は node 自身が ``module``/``source``/``from`` のどれかで
    名乗っていればそれを使う。無ければ ``None`` のまま — 「どこで
    生まれたか分からない」まで含めて誠実に言う。作り話の犯人捜しは
    しない。
    """
    out = _entry(path, node)
    out["reason"] = reason
    out["module"] = node.get("module") or node.get("source") or node.get(
        "from")
    return out


def _classify(node: Dict[str, Any], path: List[PathStep],
             measured: List[Dict[str, Any]], inferred: List[Dict[str, Any]],
             proposed: List[Dict[str, Any]], blocked: List[Dict[str, Any]],
             defects: List[Dict[str, Any]]) -> None:
    """一つの辞書ノードを、上のモジュール docstring の三段に振り分ける。

    ``return`` を早めに打つのは、一つのノードが二段目以上に重複して
    数えられるのを防ぐため — たとえば ``assumed`` を持つ拒否辞書は
    ``verdict`` も ``UNKNOWN_`` かもしれないが、それは defect/inferred/
    proposed のどれかとして一度だけ数える。「assumed は書いたが基準は
    無い」を blocked としても数えてしまうと、同じ不備が二箇所で違う
    顔をして現れる。
    """
    has_assumed = "assumed" in node and node["assumed"] is not None
    if has_assumed:
        basis = node.get("basis")
        kind = node.get("kind")
        if not basis or kind not in _ASSUMPTION_KINDS:
            missing = []
            if not basis:
                missing.append("basisが無い(空 or 未設定)")
            if kind not in _ASSUMPTION_KINDS:
                missing.append(f"kindが{kind!r}(INFERRED/PROPOSEDのどちら"
                               f"でもない)")
            defects.append(_defect(
                path, node,
                "assumedを名乗りながら " + "、".join(missing) + " — 契約"
                "違反。この値をinferredとして緑に見せることはしない"))
        elif kind == INFERRED:
            inferred.append(_entry(path, node))
        else:
            proposed.append(_entry(path, node))
        return

    verdict = node.get("verdict")
    if isinstance(verdict, str) and verdict.startswith(_UNKNOWN_PREFIX):
        blocked.append(_entry(path, node))
        return

    if node.get("kind") == OBSERVED or node.get("state") == OBSERVED:
        measured.append(_entry(path, node))


def collect(result: Any) -> Dict[str, Any]:
    """result のどこに何があるか知らないまま、判断リストを一つにして返す。

    歩き方は JSON の再帰そのもの — dict はキーを、list/tuple は添字を
    辿る。ホップの名前を一つも書いていないので、``compose`` が
    ``draft.levels[2].hip`` を返そうと ``bom`` が
    ``refused.thread`` を返そうと、このコードは変えずに済む。

    このモジュールは**報告するだけ**。result を一切書き換えず、値も
    選ばない — ``measured``/``inferred``/``proposed``/``blocked`` の
    どれか一本の値を見て「じゃあこっちを採用しよう」とする判断は、
    このファイルの外でしかできない。返す4つのリストの中身は元の辞書を
    deepcopy したものへの参照で、呼び出し側がそれをいじっても result
    側には響かない。

    表示順は blocked → defects → proposed → inferred → measured。
    人がまず見るべき順 — 「答えが無い」が最優先、次に「上流が契約を
    破った(basisの無いassumed)」、それから「まだ人が選んでいない」、
    その次に「機械的に運ばれてきた推定」、最後に「測った値そのもの」。
    """
    measured: List[Dict[str, Any]] = []
    inferred: List[Dict[str, Any]] = []
    proposed: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    defects: List[Dict[str, Any]] = []

    def walk(node: Any, path: List[PathStep],
             ancestors: FrozenSet[int]) -> None:
        # ``ancestors`` は今たどっている経路上の id() だけを持つ —
        # 全域で一度見た id を二度と見ないやり方だと、同じ辞書オブジェクト
        # が result の中で意図的に複数の場所から参照されている場合に
        # 二箇所目を silently 見落とす。祖先だけを見れば、本物の循環
        # (無限再帰)だけを止めて、正当な共有参照はそれぞれの path で
        # ちゃんと数える。
        if isinstance(node, dict):
            if id(node) in ancestors:
                return
            _classify(node, path, measured, inferred, proposed, blocked,
                     defects)
            nxt = ancestors | {id(node)}
            for key, value in node.items():
                walk(value, path + [key], nxt)
        elif isinstance(node, (list, tuple)):
            if id(node) in ancestors:
                return
            nxt = ancestors | {id(node)}
            for i, value in enumerate(node):
                walk(value, path + [i], nxt)
        # str/int/float/bool/None には潜る先が無い

    walk(result, [], frozenset())

    counts = {
        "blocked": len(blocked), "defects": len(defects),
        "proposed": len(proposed), "inferred": len(inferred),
        "measured": len(measured),
    }
    if sum(counts.values()) == 0:
        note = ("仮定も未決も停止も契約不備も見つからなかった — 歩いた"
               "先はすべて実測マーカーの無いスカラーか空の構造だった")
    else:
        note = (f'見るべき順に — 停止{counts["blocked"]}件、契約不備'
               f'{counts["defects"]}件、未決{counts["proposed"]}件、'
               f'推定{counts["inferred"]}件、実測{counts["measured"]}件')

    return {
        "verdict": "ANSWER",
        "blocked": blocked,
        "defects": defects,
        "proposed": proposed,
        "inferred": inferred,
        "measured": measured,
        "counts": counts,
        "note": note,
    }
