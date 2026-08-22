# -*- coding: utf-8 -*-
"""服飾台帳を**立体十字に載せる**。

事前登録: experiments/garment/PREREG5_CROSS.md

ここまでの `garment.py` は立体十字から**規律だけ**を借りていて、配置の
本体は呼んでいなかった。閉じた部位×側面の表、三値を混ぜない、一般/実例、
同点は棄権 — 考え方は同じでも、それは「立体十字で作った」とは言えない。

`ARMS = ("support+", "support-", "cause+", "cause-", "kind+", "kind-")` は
三つの双対そのもので、服飾の主張はそのまま乗る:

    観測          core=garment:collar  facet=shape:ノッチドラペル  support+
    割れた観測    同上                 別の値                     support-
    推論          同上                 値                         cause+
    一般構造の主張 同上                facet=generic:教本p.88      kind+
    実例の主張    同上                 facet=specific:映画X        kind-

**十字は台帳の像であって台帳ではない。** 作り直しても台帳は変わらない。
像の側で何かを決めることもしない — 決めるのは相変わらず人で、十字が
出すのは「二つの装置が同じものを割れていると言うか」という照合である。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .cross_store import CrossStore
from .garment import (CONTESTED, INFERRED, OBSERVED, PARTS, PROPOSED,
                      Ledger, ref_key)

#: 台帳の種別 → アーム。**提案にアームを与えない** — 「言われた」は
#: 支持でも反論でもなく、まだ主張の外にある。
ARM_OF_KIND = {
    "observation": "support+",
    "inference": "cause+",
}

#: 由来の申し立て → アーム。一般/実例はここで kind± に乗る。
ARM_OF_CLAIM = {
    "generic": "kind+",
    "specific": "kind-",
    "declared": "kind-",     # 名乗りも「この一着のもの」という実例側
    "no_match": None,        # 探して無かったは主張ではない。載せない
}


def _row_key(row: Dict[str, Any]) -> tuple:
    return (row["part"], row["aspect"])


def core_of(part: str) -> str:
    return f"garment:{part}"


def facet_of(aspect: str, value: str) -> str:
    """`key:value` 形にする。十字の矛盾検出は同じ key の別の値を見る。"""
    return f"{aspect}:{value}"


def build(ledger: Ledger,
          rights: Optional[Any] = None) -> CrossStore:
    """台帳(と由来台帳)を十字に写す。**元は一切触らない。**

    同じコマからの重複した観測は一度だけ載せる。同じ絵を二度読んでも
    証拠は一つ、という台帳側の数え方と揃えるため — 揃えないと、十字の
    質量だけが読み直しの回数で膨らむ。
    """
    store = CrossStore()
    seen: set = set()
    for e in ledger.entries:
        arm = ARM_OF_KIND.get(e.kind)
        if arm is None:
            # 提案。載せるが、確定の質量には混ぜない別の core に置く。
            store.add(f"{core_of(e.part)}#proposed",
                      [facet_of(e.aspect, e.value)], source=e.source)
            continue
        key = (e.part, e.aspect, e.value, ref_key(e))
        if key in seen:
            continue
        seen.add(key)
        store.add(core_of(e.part), [facet_of(e.aspect, e.value)],
                  source=e.source)

    if rights is not None:
        for o in getattr(rights, "origins", []):
            arm = ARM_OF_CLAIM.get(o.claim)
            if arm is None:
                continue
            token = o.source or o.by
            if not token:
                continue
            # **主張を値に、出典を来歴に。** 出典を値にすると、同じ
            # 「一般構造だ」を支える2本の資料が、別々の値として立って
            # 矛盾に見える(実測 VC1 で踏んだ)。二本目は対立ではなく
            # 二本目の支持なので、同じ facet の回数として積む。
            #
            # 側面を key に含めるのは、core が部位単位だから — 含めないと
            # collar の shape と material の由来が同じ棚に乗る。
            store.add(core_of(o.part),
                      [facet_of(f"origin_{o.aspect}",
                                "generic" if arm == "kind+" else "specific")],
                      source=f"{o.claim}:{token}")
    return store


def split_aspects(ledger: Ledger, store: CrossStore,
                  origins: bool = False) -> Dict[str, Any]:
    """**二つの装置が同じものを割れていると言うか。**

    台帳は値の集合で割れを判定し、十字は facet の key:value で判定する。
    別々に出した答えが一致しなければ、どちらかが間違っている — 一致を
    確かめるためにだけ、両方を回す。

    `origins=True` にすると、観測の割れではなく**由来の割れ**
    (一般と実例が同じ側面に立った状態)を比べる。観測の割れと由来の割れは
    別の事なので、同じ集合に混ぜて比較しない。
    """
    from_ledger = set()
    if not origins:
        for part, aspects in PARTS.items():
            for aspect in aspects:
                if ledger.state(part, aspect)["state"] == CONTESTED:
                    from_ledger.add((part, aspect))

    from_cross = set()
    for part in PARTS:
        for row in store.contradictions(core_of(part)):
            keys = set()
            k = row.get("key") or row.get("aspect")
            if k:
                keys.add(str(k))
            for f in row.get("values", []) or []:
                if ":" in f:
                    keys.add(f.split(":", 1)[0])
            for k in keys:
                is_origin = k.startswith("origin_")
                if is_origin != origins:
                    continue
                from_cross.add((part, k[len("origin_"):] if is_origin else k))

    return {"ledger": sorted(from_ledger), "cross": sorted(from_cross),
            "agree": from_ledger == from_cross,
            "only_ledger": sorted(from_ledger - from_cross),
            "only_cross": sorted(from_cross - from_ledger)}


def report(ledger: Ledger, rights: Optional[Any] = None) -> Dict[str, Any]:
    store = build(ledger, rights)
    agreement = split_aspects(ledger, store)
    origin_split = split_aspects(ledger, store, origins=True)
    # 一般は**何本の出典で買えたか**が要るので、回数を持って出す。
    # 由来台帳の「独立2本」規則と、十字の facet 回数が同じ数になる。
    generic, specific = [], []
    for part in PARTS:
        for f, n in store.crosses.get(core_of(part), {}).items():
            if not f.startswith("origin_"):
                continue
            aspect, _, claim = f.partition(":")
            aspect = aspect[len("origin_"):]
            (generic if claim == "generic" else specific).append(
                {"part": part, "aspect": aspect, "sources": n})
    return {
        "verdict": "ANSWER",
        "arms": {"kind+ (一般)": sorted(generic, key=_row_key),
                 "kind- (実例)": sorted(specific, key=_row_key)},
        "cores": store.n_cores(),
        "facet_links": store.n_facet_links(),
        "mass": {p: store.mass(core_of(p)) for p in sorted(PARTS)
                 if store.has(core_of(p))},
        "contested_agreement": agreement,
        "origin_split_agreement": origin_split,
        "note": "十字は台帳の像であって台帳ではない。"
                "決めるのは人で、ここが出すのは照合まで",
    }
