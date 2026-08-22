# -*- coding: utf-8 -*-
"""由来の台帳 — **オリジナルかどうかを決めない装置**。

事前登録: experiments/garment/PREREG2_PROVENANCE.md

服飾台帳 (garment.py) が「何が観測されたか」を持つのに対し、ここは
「**どこから来たか**」を持つ。二つを分けてあるのは、観測は起きた事で
後から動かせないのに対し、由来は後から証拠が増えるからである。

この装置に `ORIGINAL` という状態は無い。無いのは設計であって、実装の
手抜きではない — 「似たものが見つからなかった」から「オリジナルだ」を
導くのは、不在を否定に読み替える操作で、服飾台帳がずっと拒んできた
ものと同じ間違いである。探した範囲を伴う `UNKNOWN_NO_MATCH_IN` までしか
言えない。

## 立体十字のどの軸か

**一般/実例**。「ノッチドラペル」は一般(何千着に共通し、一つの作品に
辿れない)、「この襟の返り幅と第二ボタン位置の組み合わせ」は実例(名前の
付いた一つの作品に辿れる)。法的に意味を持つのはこの線引きなので、
新しい軸は入れない。

**支持/反論** は類似の申し立てに使う。「似ている」と「これは一般構造だ」の
両方を残し、片方を勝たせない — 観測が割れたときと同じ扱い。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# -- 由来の状態。**ORIGINAL は無い** ------------------------------------
UNCHECKED = "UNKNOWN_RIGHTS_NOT_CHECKED"
GENERIC = "GENERIC_CONSTRUCTION"        # 一般 — 独立2本以上で買う
SPECIFIC = "SPECIFIC_TO_SOURCE"         # 実例 — 一つの作品に辿れる
CONTESTED_ORIGIN = "CONTESTED_ORIGIN"   # 申し立てが割れた。人が決める
NO_MATCH = "UNKNOWN_NO_MATCH_IN"        # 探した範囲を必ず伴う
DECLARED = "DECLARED_BY"                # 人が自分の設計だと名乗った

#: 「一般構造」を名乗るのに要る独立した出典の本数。1本は「みんなやって
#: いる」の言い換えにしかならないので、2本を下限にしている。
GENERIC_MIN_SOURCES = 2

#: 用途。**許可証ではない** — 変わるのは宿題の一覧だけ。
INTENTS = ("personal", "cosplay", "study", "costume", "commercial")
_INTENT_JA = {"personal": "自分用", "cosplay": "コスプレ",
              "study": "学習・研究", "costume": "衣装制作",
              "commercial": "商用利用"}


@dataclass
class Origin:
    """由来の申し立てひとつ。**出典の無い申し立ては受け付けない。**"""

    part: str
    aspect: str
    claim: str            # generic / specific / no_match / declared
    source: str = ""      # 作品名・URL・資料。generic/specific に必須
    scope: str = ""       # no_match のとき、何を探したか。必須
    by: str = ""          # declared のとき、名乗った人。必須
    note: str = ""


@dataclass
class RightsLedger:
    """一着分の由来。観測台帳とは別に持つ。"""

    origins: List[Origin] = field(default_factory=list)
    intent: str = "personal"

    # -- 置く ------------------------------------------------------------
    def generic(self, part: str, aspect: str, source: str,
                note: str = "") -> Origin:
        """「これは一般構造だ」という申し立て。出典が要る。"""
        return self._add(part, aspect, "generic", source=source, note=note)

    def specific(self, part: str, aspect: str, source: str,
                 note: str = "") -> Origin:
        """「これは特定の作品に辿れる」という申し立て。出典が要る。"""
        return self._add(part, aspect, "specific", source=source, note=note)

    def no_match(self, part: str, aspect: str, scope: str,
                 note: str = "") -> Origin:
        """探したが見つからなかった。**何を探したかが本体**で、
        見つからなかったこと自体は結論を持たない。"""
        if not str(scope).strip():
            raise ValueError(
                "UNKNOWN_NO_SCOPE: 何を探したかが要る。"
                "範囲の無い『見つからなかった』は、何も言っていない")
        return self._add(part, aspect, "no_match", scope=scope, note=note)

    def declare(self, part: str, aspect: str, by: str,
                note: str = "") -> Origin:
        """人が「これは自分の設計だ」と名乗る。**名前が要る。**

        名乗りは他の申し立てを消さない — 特定の作品に辿れる証拠が
        あるなら、名乗りと並べて割れたままにする。
        """
        who = str(by or "").strip()
        if not who:
            raise ValueError(
                "UNKNOWN_NO_DECLARER: 名乗る人の名前が要る。"
                "誰が名乗ったか辿れない宣言は、後から確かめられない")
        return self._add(part, aspect, "declared", by=who, note=note)

    def set_intent(self, intent: str) -> str:
        """用途を決める。**どの側面の由来も変わらない** — 変わるのは
        宿題の一覧だけ。用途は許可証ではない。"""
        if intent not in INTENTS:
            raise ValueError(f"UNKNOWN_INTENT: {intent} は用途にない")
        self.intent = intent
        return intent

    def _add(self, part, aspect, claim, source="", scope="", by="",
             note="") -> Origin:
        if claim in ("generic", "specific") and not str(source).strip():
            raise ValueError(
                "UNKNOWN_NO_SOURCE: 由来の申し立てには出典が要る。"
                "出典の無い『一般構造だ』が一番危ない")
        o = Origin(part=str(part), aspect=str(aspect), claim=claim,
                   source=str(source).strip(), scope=str(scope).strip(),
                   by=str(by).strip(), note=str(note))
        self.origins.append(o)
        return o

    # -- 読む ------------------------------------------------------------
    def state(self, part: str, aspect: str) -> Dict[str, Any]:
        """ある側面の由来。**申し立ての集合だけから決める** — 入れた順は
        結論に入らない。
        """
        rows = [o for o in self.origins
                if o.part == part and o.aspect == aspect]
        gen = sorted({o.source for o in rows if o.claim == "generic"})
        spec = sorted({o.source for o in rows if o.claim == "specific"})
        scopes = sorted({o.scope for o in rows if o.claim == "no_match"})
        who = sorted({o.by for o in rows if o.claim == "declared"})

        generic_ok = len(gen) >= GENERIC_MIN_SOURCES
        out: Dict[str, Any] = {
            "part": part, "aspect": aspect,
            "generic_sources": gen, "specific_sources": spec,
            "searched_scopes": scopes, "declared_by": who,
        }

        # 実例の申し立てと、一般/名乗りが同時に立っている = 割れている。
        # 片方を勝たせない。裁定は人がする。
        sides = []
        if spec:
            sides.append("specific")
        if generic_ok:
            sides.append("generic")
        if who:
            sides.append("declared")

        if len(sides) >= 2:
            out["state"] = CONTESTED_ORIGIN
            out["sides"] = sides
            out["how_to_close"] = (
                "申し立てが割れている。どちらが正しいかはこの装置では"
                "決めない / 出典を並べて人が裁定する")
        elif spec:
            out["state"] = SPECIFIC
            out["how_to_close"] = (
                "特定の作品に辿れる。作り替えるか、権利者に確認する / "
                "一般構造である出典を2本以上足す")
        elif generic_ok:
            out["state"] = GENERIC
        elif gen:
            # 1本だけの「一般だ」は買えない。
            out["state"] = UNCHECKED
            out["how_to_close"] = (
                f"一般構造とするには独立した出典が{GENERIC_MIN_SOURCES}本要る"
                f"(今 {len(gen)} 本) / 別の資料で同じ構造を示す")
        elif who:
            out["state"] = DECLARED
            out["how_to_close"] = (
                "名乗りだけがある。似た先行作品を探した記録がまだ無い / "
                "範囲を決めて探し、結果を残す")
        elif scopes:
            # **ここが要**: 見つからなかったことは「オリジナル」ではない。
            out["state"] = NO_MATCH
            out["how_to_close"] = (
                "探した範囲の中に無かった、というだけ。範囲の外は"
                "分からない / 範囲を広げる、または人が判断する")
        else:
            out["state"] = UNCHECKED
            out["how_to_close"] = "この側面の由来をまだ調べていない"
        return out

    def report(self, parts: Dict[str, List[str]],
               confirmed: Optional[List[Dict[str, Any]]] = None
               ) -> Dict[str, Any]:
        """由来の一覧と宿題。

        **判定は返さない。** この装置が出せるのは、何を見たか・何を
        見ていないか・どこから来たか だけで、作ってよいかは人が決める。
        """
        rows = [self.state(p, a) for p, aspects in sorted(parts.items())
                for a in aspects]
        cut = {(r["part"], r["aspect"]) for r in (confirmed or [])}

        base: List[Dict[str, Any]] = []
        for r in rows:
            if r["state"] in (SPECIFIC, CONTESTED_ORIGIN):
                base.append({**r, "why": "特定の作品に辿れる申し立てがある"})
            elif (r["state"] == UNCHECKED
                    and (r["part"], r["aspect"]) in cut):
                base.append({**r, "why": "裁つ予定なのに由来を調べていない"})

        extra: List[Dict[str, Any]] = []
        if self.intent == "commercial":
            # 商用は**足すだけ**。減らすことはない。
            for r in rows:
                if r["state"] in (SPECIFIC, CONTESTED_ORIGIN):
                    extra.append({**r, "why":
                                  "商用: 作り替えるか、名前を出して"
                                  "承知の上で進めるかを人が決める"})
                elif r["state"] in (NO_MATCH, DECLARED):
                    extra.append({**r, "why":
                                  "商用: 探した範囲の外は分からない。"
                                  "範囲を書き残す"})
        return {
            "verdict": "ANSWER",
            "intent": self.intent,
            "intent_ja": _INTENT_JA.get(self.intent, self.intent),
            "rows": rows,
            "worklist": base + extra,
            "counts": {
                "specific": sum(1 for r in rows if r["state"] == SPECIFIC),
                "generic": sum(1 for r in rows if r["state"] == GENERIC),
                "contested": sum(1 for r in rows
                                 if r["state"] == CONTESTED_ORIGIN),
                "no_match": sum(1 for r in rows if r["state"] == NO_MATCH),
                "declared": sum(1 for r in rows if r["state"] == DECLARED),
                "unchecked": sum(1 for r in rows if r["state"] == UNCHECKED),
            },
            # 出力に「オリジナル」「合法」等の語を一切載せない。否定形で
            # あっても、切り出されて引用されれば断定に読める(測定 V63 が
            # この注記自身を捕まえた)。
            "note": "この一覧は判断の材料であって判断ではない。"
                    "この装置が持つのは、何を見たか・何を見ていないか・"
                    "どこから来たか まで",
        }

    def may_i_make_this(self, *_args, **_kwargs) -> Dict[str, Any]:
        """「作ってよいか」を問う口。**判定を返さない。**

        この口があるのは、無いと別のどこかで誰かが判定を作ってしまう
        からで、ここで型のついた断りに集約しておく。
        """
        return {
            "verdict": "UNKNOWN_NOT_A_LEGAL_JUDGMENT",
            "why": "著作権・意匠権・商標権の判断は国と用途で変わる。"
                   "この装置は観測と由来を並べるところまでしかできない",
            "how_to_close": "rights_report の一覧を持って、"
                            "用途(国・販売の有無・数量)と一緒に"
                            "弁理士・弁護士に確認する",
        }

    # -- 出し入れ --------------------------------------------------------
    def save(self, path: Any) -> Dict[str, Any]:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"intent": self.intent,
             "origins": [asdict(o) for o in self.origins]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        return {"verdict": "ANSWER", "path": str(p),
                "origins": len(self.origins)}

    @classmethod
    def load(cls, path: Any) -> "RightsLedger":
        p = Path(path)
        if not p.is_file():
            return cls()
        d = json.loads(p.read_text(encoding="utf-8"))
        led = cls(intent=d.get("intent", "personal"))
        led.origins = [Origin(**row) for row in d.get("origins", [])]
        return led


# ======================================================================
#  設計台帳 — 「似せる」と「作る」を分ける
# ======================================================================
#
# 観測台帳は**見た事**を持つ。設計台帳は**作る事**を持つ。二つを分けて
# あるのは、作る側をいくら書き換えても、見た事は変わらないからである。
# 一枚の台帳に混ぜると、設計を変えた瞬間に「原作品はこうだった」が
# 書き換わってしまい、後から辿れなくなる。
#
# 派生した項目は、値を変えた後も派生元を持ち続ける。「Xから変えた」ことは
# 消すべき履歴ではなく、由来そのものである。


@dataclass
class DesignEntry:
    """作る側の一項目。"""

    part: str
    aspect: str
    value: str
    kind: str             # kept / changed / new
    derived_from: str = ""      # "part/aspect" — new なら空
    original_value: str = ""    # changed のとき、元の値
    by: str = ""                # 決めた人
    note: str = ""


@dataclass
class Design:
    """一着分の設計。**観測台帳を書き換える手段を一切持たない。**"""

    title: str = ""
    entries: List[DesignEntry] = field(default_factory=list)

    def keep(self, ledger: Any, part: str, aspect: str,
             by: str) -> DesignEntry:
        """観測をそのまま使う。確定した値だけを取る — 推測や割れた側面を
        設計に持ち込まない。"""
        who = _who(by)
        val = _confirmed_value(ledger, part, aspect)
        if val is None:
            raise ValueError(
                f"UNKNOWN_NOT_CONFIRMED: {part}/{aspect} は確定していない。"
                "確定していない値を設計に持ち込むと、推測を裁つことになる")
        return self._add(part, aspect, val, "kept",
                         derived_from=f"{part}/{aspect}", by=who)

    def change(self, ledger: Any, part: str, aspect: str, value: str,
               by: str, note: str = "") -> DesignEntry:
        """観測から**変える**。元の値と派生元は残る。"""
        who = _who(by)
        val = _confirmed_value(ledger, part, aspect)
        if val is None:
            raise ValueError(
                f"UNKNOWN_NOT_CONFIRMED: {part}/{aspect} は確定していない。"
                "元が定まっていないものを『変えた』とは言えない")
        return self._add(part, aspect, str(value), "changed",
                         derived_from=f"{part}/{aspect}",
                         original_value=val, by=who, note=note)

    def create(self, part: str, aspect: str, value: str, by: str,
               note: str = "") -> DesignEntry:
        """観測に由来しない、新しく決めた項目。"""
        return self._add(part, aspect, str(value), "new", by=_who(by),
                         note=note)

    def _add(self, part, aspect, value, kind, derived_from="",
             original_value="", by="", note="") -> DesignEntry:
        e = DesignEntry(part=str(part), aspect=str(aspect), value=str(value),
                        kind=kind, derived_from=derived_from,
                        original_value=original_value, by=by, note=note)
        self.entries.append(e)
        return e

    def history(self, part: str, aspect: str) -> List[Dict[str, Any]]:
        """原作品 → 観測 → 設計 の履歴。**変えた後も派生元が残る。**"""
        return [asdict(e) for e in self.entries
                if e.part == part and e.aspect == aspect]

    def sheet(self) -> Dict[str, Any]:
        """設計の一覧。どこから来たかが各行に付く。"""
        rows = [asdict(e) for e in self.entries]
        return {
            "verdict": "ANSWER",
            "title": self.title,
            "rows": rows,
            "counts": {
                "kept": sum(1 for r in rows if r["kind"] == "kept"),
                "changed": sum(1 for r in rows if r["kind"] == "changed"),
                "new": sum(1 for r in rows if r["kind"] == "new"),
            },
            "note": "kept は観測のまま、changed は観測から変えた、"
                    "new は観測に由来しない。派生元は消えない",
        }

    def save(self, path: Any) -> Dict[str, Any]:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"title": self.title,
             "entries": [asdict(e) for e in self.entries]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        return {"verdict": "ANSWER", "path": str(p),
                "entries": len(self.entries)}

    @classmethod
    def load(cls, path: Any) -> "Design":
        p = Path(path)
        if not p.is_file():
            return cls()
        d = json.loads(p.read_text(encoding="utf-8"))
        out = cls(title=d.get("title", ""))
        out.entries = [DesignEntry(**row) for row in d.get("entries", [])]
        return out


def _who(by: str) -> str:
    who = str(by or "").strip()
    if not who:
        raise ValueError(
            "UNKNOWN_NO_AUTHOR: 決めた人の名前が要る。"
            "誰が決めたか辿れない設計は、後から直せない")
    return who


def _confirmed_value(ledger: Any, part: str, aspect: str) -> Optional[str]:
    """観測台帳から**確定した値だけ**を読む。読むだけで、書かない。"""
    for row in ledger.spec()["confirmed"]:
        if row["part"] == part and row["aspect"] == aspect:
            return row.get("value", "")
    return None
