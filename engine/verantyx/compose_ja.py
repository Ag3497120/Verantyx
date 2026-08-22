"""Sentences, by recombining forms and contents that were both written down.

I claimed a read-out could not become prose because the particles and verb
endings a sentence needs are not in the store, and emitting one would break
the closure that makes fabrication impossible. That was wrong. The particles
are in the corpus — `events.runs_with_particles` already keeps them — they
were simply never indexed. What could not be produced was not unproducible;
it was discarded at ingest.

So a sentence here is a recombination of two things that were each written
by somebody:

    form      a sentence with its content words punched out
              「未遂罪も同様に処する」 -> 「<0>も<1>に<2>する」
    content   the cores and facets a walk passed through

Neither is invented. The closure holds; what changed is that the connective
tissue is now stored instead of thrown away.

## Forms and contents have different provenance, and must stay apart

A form's source wrote that shape, not the claim the shape ends up carrying.
Merged into one store, 「〜のようなものがある」 would arrive as something a
document asserted. Kept apart, a generated sentence can say both: this
content came from here, this shape came from there, and only the first is
evidence.

## Slots carry a case, or the output is grammatical noise

The first version punched holes without recording what fits them, and
produced 「放送開始な2週間としては…」 — 〜な wants an adjectival stem and got
a noun. The particle after a hole says what the hole is: を marks an object,
に a target, な an adjectival stem, は a topic. Filling a hole with a term
whose case cannot match is how a generator stops being a recombination and
starts being a scramble.

## Measured, including where it is still bad

    3,264 prose sentences   ->  127 sentence-initial forms, 2-3 holes
    1,271 verbal nouns learned from the corpus (terms it puts before する)
    300 subjects sampled    ->  300 produce a sentence, typed or untyped

That last line is the honest one. Typing the slots does NOT reject forms; it
changes WHICH term enters a hole. It removed the visible breakages —
放送開始な2週間 (a noun in an adjectival slot), 借主を地位する (a noun that
is not a verb), 安全:危険 (a polarity key, not a word) — and left the
sentences grammatical more often than not:

    消防法第十六条に削除がある。
    刑事訴訟法第三百五十条にも判決ができるようになっていたものもある。
    市販がインターネットにサービスされている。

and left plenty that are not:

    詳細っこいエルシーブイである。
    犯罪係数はアドバンテージをエリミネーターとしている。

## The wall is not selectional fit. It is that facets are not words.

I took the residue for a selectional problem and learned (noun, particle,
predicate) triples from the corpus to fix it — 8,805 of them over 2,291
slots. It barely moved, and measuring why settled it:

    88,789 distinct facets in the federation
    of a 2,000 sample, 7.4% appear three or more times in the prose corpus
    the other 93% are extraction fragments

エリミネーター, コンキスタドール, 1980アイコ are real facets and none of
them is a word a sentence can use. They are excellent for retrieval — the
resolution ladder is right 100% of the time it answers, on exactly these —
and useless as vocabulary, because a facet is whatever the reader cut out of
a sentence, not a lexical item.

## The selection layer had the same blind spot as the vocabulary

Learned from encyclopedia prose alone it was too thin to act on: 8,805
triples over 2,291 slots, 3.8 observations each. Adding the 29.6M
characters of statute body that the vocabulary needed anyway:

    encyclopedia only   8,805 triples   2,291 slots   3.8 obs   119 forms
    + statute bodies  382,884          8,545        44.8       478

    に関〜   50,144  施行 罰則 給与 実施
    を有〜   12,768  効力 権利 資格 経験
    を記載〜  5,783  事項 理由 氏名 内容

Ten times the slots and twelve times the density, and the forms follow the
register they came from — output now reads like a statute because most of
what attests it is one:

    事情は、いつでも届出を選択することができる。
    西文化圏において関係とする。

The share of fills selection can judge FELL, 43.8% to 32.7%, and that is
not a regression. Thin data said "no opinion" less often because a slot
with three observations rejects almost nothing; a slot with forty-five
knows what does not belong there.

Selection could only judge 43.8% of candidate fills at first (3.8
observations per slot), but that was the smaller problem. A generator over
this store is choosing from a bag that is 93% not-words.

**Re-measured 2026-08-19, and the 43.8% above is stale.** The number was
never re-taken after the statute bodies and the 1.4M dictionary definitions
grew SELECTION to 14,087 slots / 441,433 triples. Instrumented at FILL TIME
(counting every `selects()` call while generating document drafts for 13
real questions, 224 calls over 11 sentences):

    opinion (True or False)   85.7%
    attested (True)           11.6%
    no opinion (None)         14.3%

So the thin-data era is over for this store, and the residue is a different
shape from the one the paragraph above describes: selection now mostly says
"no" (166 of 224), which is what a dense table is supposed to do. What a
reader should NOT conclude is that drafts got 85.7% better — the opinion is
consulted as a RANKING, not a gate, and clumsiness now comes from the form
inventory rather than from a table with nothing to say.

## The vocabulary layer, and what it fixed

`verantyx/vocabulary.py` sifts the facets to the ones a prose corpus uses as
free-standing words — 12,362 of 88,789, 13.9% — and `compose` draws from
those, best-attested first. Measured over 300 subjects, whether every
content word in the output is itself an attested word:

    without vocabulary   219/300   73.0%
    with vocabulary      300/300  100.0%

    グリコ -> 人物,  エルシーブイ -> 同意,  ウィドマンシュテッテン -> 使用

One more class of breakage was left, and it was in the FORMS, not the
fills: the punch-out cut some words in half, so 例えば became <0>えば and
人懐っこい became <0>っこい, and filling those produced 本部長えば and
総務大臣裁定っこい. Six of 127. A form like that is dropped rather than
repaired — the boundary the extractor missed cannot be recovered from the
template. 119 forms remain.

What comes out now is a sentence more often than not:

    議論の必要がある。
    加盟国には原則のようなものがある。
    伊藤宏が当事者を実行する。
    第一章として法律のようなものがある。

and still sometimes not:

    符号に記録めている。
    自己決定権がいたら放送ず意味にする。

## What this is not

It does not know whether the sentence is true. A form says "X does Y to Z"
and the walk supplies an X, a Y and a Z that were near each other in the
store — that is a plausible-looking sentence assembled from real parts, and
the assembly is not evidence for it. Anything downstream must treat the
output as a draft with two citations attached, never as a claim the corpus
made. It is deliberately NOT wired into `gather`, `descend` or any verdict
path; a generated sentence must never be able to arrive where a reader
expects a citation.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

#: A content word: kanji, katakana, or the marks that bind them.
_CONTENT = re.compile(r"[㐀-䶿一-鿿ァ-ヺー々〆]+")

#: Markup, formulae and latin that are not Japanese prose. A form harvested
#: from 「{\displaystyle X}」 is not a sentence and filling it produces
#: nothing a reader would accept.
_NOT_PROSE = re.compile(r"[=\{\}\[\]\\<>|#*A-Za-z0-9]|displaystyle")

#: A sentence ends on a predicate. Without this the harvest is dominated by
#: headings and list fragments, which have no verb to carry a claim.
#: The polite register was absent entirely, so no conversational form could
#: be harvested at any corpus size. 「今日はいい天気ですね」, 「よろしくお願い
#: します」 and 「ご用件をお伺いします」 all failed the predicate test, and a
#: conversational corpus of 8 exchanges yielded ONE form — 「<0>はお<1>れさま
#: でした」, which is 「お疲れさまでした」 cut through the middle of 疲.
#:
#: That is why 「こんにちは」 could only be answered in statute voice: of 659
#: forms, 358 came from statutes and 0 from anything anyone would say aloud.
#: Not a limit of the structure; a register the harvester could not see.
_PREDICATE = re.compile(
    r"(である|でない|する|しない|した|ある|ない|いる|られる|れる|になる|となる|できる"
    r"|です|でした|ではない|ません|ました|ます|ください|ございます|でしょう"
    r"|ですね|ですか|ますか|ましょう"
    # 定義形の述語(2026-08-19)。法令の定義文は「〜をいう」「〜を指す」で
    # 閉じるが、この表に無く全滅していた — 実測: bulk 1200法令に「とは、
    # …をいう」文が1,802本ありながら、をいう末尾の文型は0本。
    r"|いう|指す)$")

#: What the character after a hole says the hole must hold.
#:
#:   な   an adjectival stem — 静かな, 主な. A plain noun breaks it, and
#:        this is the case that produced 放送開始な2週間 before slots were
#:        typed at all.
#:   を   an object          に  a target        へ  a direction
#:   は   a topic            が  a subject       の  a modifier
#:   で   a means or place   と  a companion or quotation
CASE_OF: Dict[str, str] = {
    "な": "adjstem", "を": "object", "に": "target", "へ": "target",
    "は": "topic", "が": "subject", "の": "modifier", "で": "means",
    "と": "with", "も": "topic", "から": "source", "まで": "limit",
}

#: Suffixes that mark a term as an adjectival stem rather than a plain noun.
_ADJ_STEM = ("的", "式", "様", "急", "重要", "主", "新た", "明らか")

#: A term that is mostly digits, a counter, or a bare fragment is not
#: something to put in a sentence. Untyped, the first fills were 10日間,
#: 1980アイコ and 17時枠 — every one a real facet and none of them a word a
#: sentence wants.
_NUMERISH = re.compile(r"[0-9０-９]|^[〇一二三四五六七八九十百千万]+")
_COUNTER = re.compile(
    r"(年|月|日|時|分|秒|回|人|件|個|台|本|枚|度|割|歳|代|周年|時台|時枠|番)$")

MIN_LEN, MAX_LEN = 8, 40
MIN_HOLES, MAX_HOLES = 2, 3

#: A hole followed by inflection is not a hole — it is the stem of a word
#: the punch-out cut in half. 例えば became <0>えば and 人懐っこい became
#: <0>っこい, so filling them produced 本部長えば and 総務大臣裁定っこい.
#: Six of 127 forms were like this; a form is dropped rather than repaired,
#: because the boundary the extractor missed cannot be recovered from the
#: template alone.
_CUT_STEM = re.compile(
    r"<\d>(えば|っこい|わない|ばれて|じて|らない|けない|しく|くて|きた|った)")


#: Character pairs the corpus writes. The last resort against a template
#: that was cut inside a word.
#:
#: `_CUT_STEM` below lists eleven inflection fragments by hand, which is a
#: rule written rather than learned and — measured — catches none of the 659
#: forms harvested at 626MB. 「う」 is not on it, so 「<0>うものとする」
#: survives and fills to 法律うものとする. The fragment is not the problem:
#: 「う」 is a fine ending for 行う. The JOIN is. 律+う never occurs in
#: 32,259,912 characters and 律+は occurs 3,863 times.
#:
#: So the test is on the seam, at fill time, where both sides are known.
#: Measured over 465 generated sentences it rejects 84 (18%) — 使用る,
#: 財産られている, 活動っている — and passes 解雿+は, which occurs once.
#: A threshold above 1 starts refusing rare words for being rare.
JOIN: Counter = Counter()

#: A hole and the kana that immediately follow it.
_HOLE_TAIL = re.compile(r"<(\d)>([ぁ-ん]{1,6})")


def learn_joins(texts: Iterable[Tuple[str, str]]) -> Dict[str, int]:
    for _src, body in texts:
        b = body or ""
        for i in range(len(b) - 1):
            JOIN[b[i:i + 2]] += 1
    return {"pairs": len(JOIN)}


def joins(left: str, right: str) -> bool:
    """Does the corpus ever write these two characters adjacent?"""
    if not left or not right:
        return True
    return JOIN.get(left[-1] + right[0], 0) >= 1


#: (particle, predicate) -> the nouns the corpus actually put in that slot.
#: The wall after grammar: co-occurrence in a store is not selectional fit,
#: and nothing in a cross says that アドバンテージ is a poor object for
#: 犯罪係数. The corpus says it, thousands of times, by never writing it.
SELECTION: Dict[Tuple[str, str], Counter] = defaultdict(Counter)

#: Backing off to the suffix. 5,433 triples over this corpus is sparse — a
#: specific noun is usually unseen in a specific slot even when its KIND is
#: attested. 被害/損失/災害 all end differently, but 地震被害 and 経済損失
#: share their heads with them, so the last one or two characters carry most
#: of what a slot selects for.
SELECTION_TAIL: Dict[Tuple[str, str], Counter] = defaultdict(Counter)

_PRED_HEAD = re.compile(r"^([㐀-䶿一-鿿]{1,6})(する|した|される|し|され|できる)")
_SLOT_PARTICLES = "をにでとがは"


def learn_selection(texts: Iterable[Tuple[str, str]]) -> Dict[str, int]:
    """Read (noun, particle, predicate) from prose. Learned, never listed.

    A slot's preferences are a fact about usage, and usage is what a corpus
    is. Writing a table by hand would encode my guesses about Japanese into
    a system whose whole claim is that it only repeats what it was shown.
    """
    n = 0
    for _source, body in texts:
        for s in re.split(r"[。\n]", body or ""):
            ms = list(_CONTENT.finditer(s))
            for i, m in enumerate(ms[:-1]):
                after = s[m.end():m.end() + 1]
                if after not in _SLOT_PARTICLES:
                    continue
                pm = _PRED_HEAD.match(s[ms[i + 1].start():])
                if not pm:
                    continue
                noun, verb = m.group(0), pm.group(1)
                if not (2 <= len(noun) <= 8 and 1 <= len(verb) <= 6):
                    continue
                SELECTION[(after, verb)][noun] += 1
                SELECTION_TAIL[(after, verb)][noun[-2:]] += 1
                SELECTION_TAIL[(after, verb)][noun[-1:]] += 1
                n += 1
    return {"triples": n, "slots": len(SELECTION)}


def dump_selection() -> Dict[str, Any]:
    """The learned slot tables, as data.

    They live in module globals because `selects` is called from inside the
    fill loop and threading them through every caller bought nothing. That
    makes them the one part of the writer that a reload cannot recover on
    its own, so they are dumped and restored explicitly rather than being
    silently empty in a process that loaded everything else.
    """
    return {
        "selection": {f"{p}\t{v}": dict(c) for (p, v), c in SELECTION.items()},
        "tails": {f"{p}\t{v}": dict(c) for (p, v), c in SELECTION_TAIL.items()},
    }


def load_selection(data: Dict[str, Any]) -> Dict[str, int]:
    """Restore what `dump_selection` wrote, replacing whatever is loaded.

    Replacing rather than merging: two corpora's tables added together are a
    third corpus nobody measured, and `selects` reads counts to decide
    whether a slot is attested well enough to answer at all.
    """
    SELECTION.clear()
    SELECTION_TAIL.clear()
    for key, counts in (data.get("selection") or {}).items():
        p, v = key.split("\t", 1)
        SELECTION[(p, v)] = Counter(counts)
    for key, counts in (data.get("tails") or {}).items():
        p, v = key.split("\t", 1)
        SELECTION_TAIL[(p, v)] = Counter(counts)
    # VERBAL_NOUNS は harvest()(構築時)でしか埋まらず、writer.json を
    # 読む実行時経路では空のままだった — fits(term,'verbalnoun') が常に
    # False になり、する動詞の穴は正しく型付けされるほど埋まらなくなる。
    # 実測 2026-08-19: 実行時 VERBAL_NOUNS=0語、その結果 free 型の穴を
    # 持つ不自然な文型へ充填が流れていた(「効力を方式している」)。
    # SELECTION の述語頭はコーパスが実際に する を付けた名詞そのもの
    # (キー ('を','解除') は「〜を解除する」の実測)なので、そこから
    # 復元する — 新しい主張はゼロ、積み込み経路の欠落を閉じるだけ。
    for (_p, pred) in SELECTION:
        if 2 <= len(pred) <= 8:
            VERBAL_NOUNS.add(pred)
    return {"slots": len(SELECTION),
            "triples": sum(sum(c.values()) for c in SELECTION.values()),
            "verbal_nouns": len(VERBAL_NOUNS)}


def selects(noun: str, particle: str, verb: str) -> Optional[bool]:
    """Has the corpus put this kind of noun in this slot?

    Three answers, and the third is the important one. True: attested,
    exactly or by its ending. False: the slot is well attested and nothing
    like this noun appears in it. None: the slot itself is barely seen, so
    the corpus has no opinion and refusing on that basis would be inventing
    a rule.
    """
    key = (particle, verb)
    seen = SELECTION.get(key)
    if not seen:
        return None
    if noun in seen:
        return True
    tails = SELECTION_TAIL.get(key) or Counter()
    if noun[-2:] in tails or noun[-1:] in tails:
        return True
    return False if sum(seen.values()) >= SELECTION_MIN else None


#: Below this many observations a slot has no opinion worth acting on.
SELECTION_MIN = 5


#: What a sentence SHAPE claims about whatever fills it. Prohibition is
#: listed before permission because 「することができない」 contains no
#: substring of 「することができる」 but 「してはならない」 must not be read
#: as the obligation 「ならない」 alone.
#: Written to OVER-refuse. A licence that misses a modality invents an
#: obligation; one that fires too often writes a plainer sentence. The first
#: version anchored on 「することができない」 and 「してはならない」 and was
#: audited at five survivors per 315 sentences, every one a hole breaking the
#: pattern up — 「することはできない」 with the topic は inserted, 「くこと
#: ができる」 on a stem that is not る, and a bare 「地震できる」. So the
#: できる/できない test is now unanchored.
_MODALITY: List[Tuple[str, Any]] = [
    ("prohibition", re.compile(
        r"できない|得ない|てはならない|てはいけない|限りでない"
        r"|ことを禁ずる|ずるものでない"
        # polite: the register the harvester could not see until just now
        r"|できません|ないでください|しないでください")),
    ("obligation", re.compile(
        r"なければならない|するものとする|を要する|べきである|べきもの"
        r"|しなければいけない|に処する|ねばならない"
        r"|なければなりません|ものとします")),
    # A polite imperative directs the reader as surely as 「しなければならない」
    # does, and read straight past the licence: 「<0>を<1>してください」 came
    # back modality=none, so a store holding encyclopedia prose could be made
    # to issue instructions it never carried. 「〜ができます」 states a
    # capability for the same reason 「することができる」 states a permission.
    ("directive", re.compile(
        r"てください|下さい|お願いします|お願いいたします"
        r"|いただけますか|いただけませんか|てほしい|ましょう|なさい")),
    ("permission", re.compile(
        r"できる|して差し支えない|することを妨げない|してもよい|て差し支えない"
        r"|できます|しても構いません|て構いません")),
]


@dataclass
class Form:
    """One sentence shape, with a case per hole and where it came from."""

    template: str
    cases: List[str] = field(default_factory=list)
    #: (particle, predicate) per hole where one is visible, else None.
    #: This is what lets a fill be checked against SELECTION rather than
    #: only against its case.
    slots: List[Optional[Tuple[str, str]]] = field(default_factory=list)
    count: int = 0
    example: str = ""
    source: str = ""

    @property
    def holes(self) -> int:
        return len(self.cases)

    @property
    def polarity(self) -> str:
        """positive / negative — the sign this SHAPE stamps on its content.

        Found when edges fixed the content side: with every content word
        attested and the pair sentence-licensed, the drafts still read
        「殺人罪は法定刑加重ではありません」 — the negation came from the
        TEMPLATE, not from any evidence. Presence evidence (counts, edges,
        co-occurrence) can license at most "these were written together",
        which is a positive-shaped claim; no amount of it licenses ない.
        The norm double-negative (なければならない) is stripped first — that
        is an obligation, the modality property's business, not a negation.
        """
        import re as _re

        # Blunt on purpose. The first version enumerated negation endings
        # and inflection walked straight past it — なれない, されていない,
        # しかない, さない all slipped through, and てはなりません dodged the
        # norm-strip because only てはならない was listed. Any ない/ません in
        # the shape marks it negative; the obligation double-negative
        # (なければならない) is marked negative too, which costs nothing —
        # callers speaking from presence evidence exclude norm-modality
        # forms before ever consulting polarity.
        if _re.search(r"(ない|ません|ぬ。|ず、|ず。)", self.template):
            return "negative"
        return "positive"

    @property
    def modality(self) -> str:
        """obligation / prohibition / permission / none — what this SHAPE
        asserts, before anything fills it.

        A form is not neutral about the relation it states. 「〜しなければ
        ならない」 asserts a duty whoever fills the holes, and a store that
        holds co-occurrence has no duty to report.

        Separate from `fusion.register_of` on purpose, and wider. That
        classifier is calibrated for the answer path, where it refines a
        field's declared register and is deliberately narrow — it fires on
        17.4% of statute sentences and stays silent elsewhere. Reused here it
        under-fired on exactly the modality that matters most: 「〜すること
        ができない」 and 「〜てはならない」 both came back `unknown`, so a
        first version of this licence let 「アダルトアニメは、制作される
        ことができない。」 through. Silence is the right default when
        refining a register and the wrong one when granting a licence.
        """
        for name, rx in _MODALITY:
            if rx.search(self.template):
                return name
        return "none"

    @property
    def register(self) -> str:
        """norm when the shape asserts any modality, else the classifier's."""
        if self.modality != "none":
            return "norm"
        from .fusion import register_of

        return register_of(self.template + "。")


#: Terms observed immediately before する / した / される in the corpus.
#: Learned, not listed: which nouns take する is a fact about Japanese that
#: the corpus already demonstrates thousands of times, and guessing it
#: produced 「借主を地位する」 — 地位 is a noun and never a verb.
VERBAL_NOUNS: Set[str] = set()

#: している/します/し、 を見落としていた実測(2026-08-19): 「<2>している」
#: の穴が free 型になり、する名詞でない語(方式)が詰まって「効力を方式
#: している」ができた。境界の門(_SLOT_ALLOW)が通す活用と同じ集合を見る。
_SURU = re.compile(r"(する|した|して|します|し[、。]|される|されて|された|しない)")


def _case_after(text: str, at: int) -> str:
    """The case a hole imposes, read from what follows it."""
    tail = text[at:at + 2]
    for k in ("から", "まで"):
        if tail.startswith(k):
            return CASE_OF[k]
    if _SURU.match(text[at:at + 4] or ""):
        return "verbalnoun"
    return CASE_OF.get(text[at:at + 1], "free")


#: 穴の直後に立ってよい形。助詞・句読点・する動詞の支えだけ。これ以外が
#: 穴に密着している文型は、収穫時にスロット境界が語の途中に開いたもの —
#: 「<2>ばれる」(呼ばれる)「<2>われる」(行われる)「<2>つである」(三つ)
#: 「<2>まれる」(含まれる)。そこへ名詞を詰めると「広義まれる」
#: 「不法領得つである」という切れ端文になる。実測 2026-08-19: 1,329文型
#: 中434がこの形。動詞語幹の穴として収穫されたものだが、この口の内容は
#: 名詞(facet/辺の端点)しか無いので、名詞の口では使えない型として弾く。
#:
#: 1文字の許可では3つ漏れた(同日実測):「か」は完成かれる(置かれる切断)、
#: 「し」は適用しい(形容詞切断)、「）」は対の無い閉じ括弧「保護）となる」。
#: する動詞の支えは2文字先読み(する/され/した/してい/します/し、/し。)で
#: 通し、それ以外の か・し・）は弾く。
_HOLE_NEXT = re.compile(
    r"<\d+>(?![はがをにでとのもへやな、。，．！？」]"
    r"|す(?=る)|さ(?=れ)|し(?=[てたま、。])|$)")


def slot_boundary_ok(template: str) -> bool:
    """穴の境界が語の途中に開いていない文型か。名詞充填の前提検査。"""
    return _HOLE_NEXT.search(template) is None


def harvest(
    texts: Iterable[Tuple[str, str]],
    *,
    head_only: bool = True,
) -> Dict[str, Form]:
    """Read documents into sentence forms. ``texts`` is (source, body).

    ``head_only`` keeps forms whose first hole is at the start of the
    sentence. Mid-sentence fragments — 「が<0>の<1>となる」 — are clauses cut
    out of a longer sentence and read as broken when used alone.
    """
    forms: Dict[str, Form] = {}
    # First pass: learn which nouns the corpus actually conjugates with する.
    for _source, body in texts:
        for m in _CONTENT.finditer(body or ""):
            if _SURU.match((body or "")[m.end():m.end() + 4]):
                w = m.group(0)
                if 2 <= len(w) <= 8:
                    VERBAL_NOUNS.add(w)
    for source, body in texts:
        for raw in re.split(r"[。\n]", body or ""):
            s = raw.strip()
            if not (MIN_LEN <= len(s) <= MAX_LEN):
                continue
            if _NOT_PROSE.search(s) or not _PREDICATE.search(s):
                continue
            parts: List[str] = []
            cases: List[str] = []
            slots: List[Optional[Tuple[str, str]]] = []
            pos = 0
            marks = list(_CONTENT.finditer(s))
            for j, m in enumerate(marks):
                parts.append(s[pos:m.start()])
                parts.append(f"<{len(cases)}>")
                cases.append(_case_after(s, m.end()))
                part = s[m.end():m.end() + 1]
                pred = None
                if part in _SLOT_PARTICLES and j + 1 < len(marks):
                    pm = _PRED_HEAD.match(s[marks[j + 1].start():])
                    if pm:
                        pred = (part, pm.group(1))
                slots.append(pred)
                pos = m.end()
            parts.append(s[pos:])
            tpl = "".join(parts)
            if not (MIN_HOLES <= len(cases) <= MAX_HOLES):
                continue
            if head_only and not (tpl.startswith("<0>")
                                  or tpl.startswith("「<0>」")):
                # 「<0>」とは、… は文頭形 — 先頭の鉤括弧は句読の飾りで、
                # 断片(文中切り出し)ではない。定義文の主要形。
                continue
            if _CUT_STEM.search(tpl):
                continue
            f = forms.get(tpl)
            if f is None:
                forms[tpl] = Form(template=tpl, cases=cases, slots=slots,
                                  count=1, example=s, source=source)
            else:
                f.count += 1
    return forms


def fits(term: str, case: str) -> bool:
    """Can this term stand in a hole of this case?

    Only the checks that can be made from the string are made. A noun in an
    object slot is accepted because nothing here can tell a good object from
    a bad one; an adjectival slot is checked because 〜な after a plain noun
    is wrong in a way that is visible without knowing the meaning.
    """
    t = (term or "").strip()
    if not t or len(t) > 12 or len(t) < 2:
        return False
    if _NUMERISH.search(t) or _COUNTER.search(t):
        return False
    if ":" in t or "：" in t:
        # A polarity-keyed facet (安全:危険) is a claim about an aspect, not
        # a word. It leaked into a sentence before this check existed.
        return False
    if case == "adjstem":
        return t.endswith(_ADJ_STEM)
    if case == "verbalnoun":
        return t in VERBAL_NOUNS
    if case == "modifier":
        return len(t) <= 8
    return True


@dataclass
class Draft:
    """A generated sentence, and the two places it came from."""

    text: str
    template: str
    fills: List[str]
    content_from: List[str] = field(default_factory=list)
    form_from: str = ""
    #: 選択制限が「実証済み」と言った充填の数。順位にだけ使い、門には
    #: しない — 意見なし(None)の穴は今まで通り埋まる。読み手には見える。
    attested: int = 0
    #: 引用行への忠実度(末尾形一致×10+語順保存の隣接対数)。順位のみ。
    line_fidelity: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "template": self.template,
                "fills": self.fills, "content_from": self.content_from,
                "form_from": self.form_from, "attested": self.attested,
                "note": "content and form have separate sources; neither "
                        "makes this sentence true"}


def compose(
    forms: Dict[str, Form],
    subject: str,
    facets: Sequence[str],
    *,
    limit: int = 3,
    content_from: Optional[Sequence[str]] = None,
    vocab: Optional[Any] = None,
    licence: str = "unknown",
    roles: Optional[Dict[str, str]] = None,
    order: Optional[Dict[str, int]] = None,
    tail: str = "",
) -> List[Draft]:
    """Sentences about ``subject`` using ``facets``, best-supported first.

    The subject takes hole 0 and the facets fill the rest, each checked
    against its slot's case. A form no available term fits is skipped rather
    than filled anyway — that skip is the whole difference between this and
    the untyped version.

    ``licence`` is the register of the CONTENT, and a form may not assert
    more than the content licenses. Closure keeps a store from emitting a
    symbol it does not hold — measured at 0 of 117 outputs. It says nothing
    about relations, and a form supplies one for free: 21.9% of generated
    sentences asserted a norm (obligation, prohibition, permission), and
    42.6% of those were about content no statute had spoken of. 【女性】は、
    【従事】を【行為】しなければならない is closed on every symbol and
    fabricated on the only thing that matters.

    So a norm-shaped form needs a norm-registered subject. Descriptive and
    unknown forms are always allowed — the restriction runs one way, because
    stating a legal duty as a plain fact loses nothing and stating a plain
    fact as a legal duty invents an obligation.
    """
    pool = [f for f in facets if f and f != subject]
    if vocab is not None:
        # A facet is whatever the reader cut out of a sentence; 93% of them
        # are not words. Filtering to attested vocabulary, best-attested
        # first, is what stops 1980アイコ entering an object slot — see
        # verantyx/vocabulary.py.
        from .vocabulary import filter_terms
        pool = filter_terms(pool, vocab)
        if subject not in vocab:
            return []
    out: List[Draft] = []
    n_tail_out = 0
    # Rotate the form order per subject. Taking the most frequent form that
    # fits gave every step of a walk the same shape — eight sentences all
    # reading 「<0>も<1>に<2>する」, which is a template being recited rather
    # than a text. The offset is derived from the subject, so it is stable.
    ranked = sorted(forms.items(), key=lambda kv: (-kv[1].count, kv[0]))
    if ranked:
        off = sum(ord(c) for c in subject) % len(ranked)
        ranked = ranked[off:] + ranked[:off]
    if tail:
        # 末尾一致形を列挙の先頭へ(2026-08-19)。収集は8本で打ち切るので、
        # 行が選んだ言い方(〜とする/である)の文型は、頻度順の奥に居ると
        # 候補に一度も入らない — 収集幅を広げる案は実測で棄却済み(悪い
        # 形も連れてくる)。並べ替えなら、末尾形も充填・継ぎ目・選択の
        # 同じ門を全て通った上で候補に入るだけ。順位であって門ではない:
        # 一致形が無ければ従来の並びのまま。
        tm = [kv for kv in ranked if kv[0].rstrip("。").endswith(tail)]
        if tm:
            ranked = tm + [kv for kv in ranked if not
                           kv[0].rstrip("。").endswith(tail)]
    for tpl, form in ranked:
        if not fits(subject, form.cases[0]):
            continue
        if form.register == "norm" and licence != "norm":
            continue
        picks: List[str] = [subject]
        used: Set[str] = {subject}
        ok = True
        n_attested = 0
        role_hits = 0
        role_miss = 0
        if roles:
            _c0 = tpl[len("<0>"):len("<0>") + 1] if tpl.startswith("<0>") else ""
            if _c0 in "のをにがはとでへもや" and roles.get(subject):
                # 主語穴も対称に: 一致は稼ぎ、逆転は失う。片側だけ数えると
                # 「利用**で**なくなつた…」(行では 利用を)が無傷で同点に並んだ。
                if roles.get(subject) == _c0:
                    role_hits += 1
                else:
                    role_miss += 1
        for hole, case in enumerate(form.cases[1:], start=1):
            slot = form.slots[hole] if hole < len(form.slots) else None
            cand = [t for t in pool if t not in used and fits(t, case)]
            # 係り受けの搬送(2026-08-19): 引用行で語が担っていた助詞
            # (新幹線**の**・利用**は**・移動**に**)を roles として受け、
            # 穴の助詞と一致する語を先に。順位であって門ではない —
            # 一致が無ければ従来の並びのまま。「新幹線と利用を移動する」
            # (行では 移動に だったのに を の穴へ入った)型の役割逆転を、
            # 行自身の読みで抑える。
            # 穴の直後の一文字を文型自身から読む。slots は「助詞+次の穴の
            # 述語頭」が揃った時だけ立つので、「<1>とする」のような文末
            # 穴には None が入り、役割の導きが効かなかった(2026-08-19
            # 実測: 「利用を原則とする」の と穴に 移動 が入る)。文型の
            # 字面は常にあるので、そこから読む — 解析ではなく写し。
            _after = ""
            _i = tpl.find(f"<{hole}>")
            if _i >= 0:
                _c = tpl[_i + len(f"<{hole}>"):_i + len(f"<{hole}>") + 1]
                if _c in "のをにがはとでへもや":
                    _after = _c
            if roles and (slot or _after):
                part = slot[0] if slot else _after
                matched = [t for t in cand if roles.get(t) == part]
                others = [t for t in cand if roles.get(t) != part]
                cand = matched + others
            if slot:
                # Attested first, unknown next, never one the corpus rejects.
                yes = [t for t in cand if selects(t, slot[0], slot[1]) is True]
                maybe = [t for t in cand if selects(t, slot[0], slot[1]) is None]
                if roles:
                    # 役割一致は選択実証より先 — 行が実際に書いた役割は、
                    # コーパス統計より強いライセンス。
                    part = slot[0] if slot else ""
                    rm = [t for t in (yes + maybe) if roles.get(t) == part]
                    ro = [t for t in (yes + maybe) if roles.get(t) != part]
                    cand = rm + ro
                else:
                    cand = yes + maybe
                if yes and cand and cand[0] in yes:
                    n_attested += 1
            if not cand:
                ok = False
                break
            picks.append(cand[0])
            used.add(cand[0])
            if roles and (slot or _after) and roles.get(cand[0]):
                if roles.get(cand[0]) == (slot[0] if slot else _after):
                    role_hits += 1
                else:
                    # 行が書いた役割と違う穴に立った — 役割逆転の実測類
                    # (「移動に」が も穴へ)。一致が稼ぐ分だけ失う。
                    role_miss += 1
        if not ok:
            continue
        # The seam test, after the fills are known. A template cut inside a
        # word only shows itself here: 「<0>うものとする」 is fine until 法律
        # lands in it and 律+う is a pair the corpus never writes.
        seam_ok = True
        for m in _HOLE_TAIL.finditer(tpl):
            h = int(m.group(1))
            if h < len(picks) and not joins(picks[h], m.group(2)):
                seam_ok = False
                break
        if not seam_ok:
            continue

        text = tpl
        for i, p in enumerate(picks):
            text = text.replace(f"<{i}>", p)
        # 係り受けの深化(2026-08-19): 引用行への忠実度2つを順位に足す。
        #   tail一致  行の末尾形(とする/である/認める…閉集合)と文型の
        #             末尾が一致 — 行が選んだ言い方をそのまま継ぐ。
        #   語順     充填語の並びが行の語順を保った隣接対の数。
        # どちらも順位のみ。行を持たない呼び出し(order/tail なし)では
        # 全下書きが同点で、従来の並びのまま。
        _tail_hit = 1 if (tail and tpl.rstrip("。").endswith(tail)) else 0
        _fid = 0
        if order:
            _pos = [order[p] for p in picks if p in order]
            _fid = sum(1 for a, b in zip(_pos, _pos[1:]) if a < b)
        # 役割一致数も忠実度へ(2026-08-19)。末尾一致だけでは とする形が
        # 8本同点になり、挿入順(頻度順)が勝敗を決めていた — 行が書いた
        # 助詞を最も多く保った下書きが同点を割る。重みは tail(10) > 役割
        # (2) > 語順(1): 行の言い方 > 行の役割 > 行の並び。
        out.append(Draft(text=text + "。", template=tpl, fills=picks,
                         content_from=list(content_from or []),
                         form_from=form.source, attested=n_attested,
                         line_fidelity=_tail_hit * 10
                         + (role_hits - role_miss) * 2 + _fid))
        n_tail_out += _tail_hit
        # 実証済みの充填を持つ下書きを、持たない下書きより先に返す。
        # 従来は「最初に埋まった limit 本」で打ち切っており、意見なしの
        # 穴だけで埋まった形が、実証済みの形より先に口へ届いていた。
        # 4倍まで集めて安定ソート — 回転(主語ハッシュ)による形の多様さは
        # 同点内でそのまま残る。門ではなく順位: 実証済みが1本も無ければ
        # 従来と同じものが出る。
        # 収集幅は8のまま。24へ広げる案は実測で棄却(2026-08-19):
        # att=0 の同点帯では、広げた候補が語順・役割の悪い形を連れてきて
        # 「会議の上限がある」→「上限を会議としている」と逆転した。
        # ただし末尾一致ブロックは全数収集(同日実測): 頻度順の先頭8本が
        # 枠を食い、count=8 の「<0>を<1>とする」——行の核そのもの——が
        # 一度も候補に入らなかった。tail は行が選んだ言い方のライセンスで、
        # 該当形は多くて数十本。汎用形の枠(8)はそのまま、tail 形だけ
        # 枠外で数える — 棄却された「汎用の広幅」とは別物。
        if len(out) - n_tail_out >= max(limit * 4, 8):
            break
    # 行 > コーパス統計(2026-08-19): 末尾・役割・語順の忠実度が先、
    # 実証は同点割り。行を持たない呼び出しでは全下書きが忠実度0で、
    # 従来どおり実証が決める。逆順(実証が先)では att=1 の汎用形が
    # 行の核「利用を原則とする」(att=0)を覆い隠した。
    # 忠実度同点の最後は形の飾りの少なさ(行つき呼び出しのみ)。同点15の
    # 「をもって、」と「を…とする」では、行の核をそのまま継ぐ短い方 —
    # 行なしの呼び出し(忠実度0)では従来の回転順を保つ。
    out.sort(key=lambda d: (-d.line_fidelity, -d.attested,
                            len(d.template) if d.line_fidelity > 0 else 0))
    return out[:limit]


def compose_walk(
    store: Any,
    forms: Dict[str, Form],
    trace: Any,
    *,
    per_step: int = 1,
    vocab: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """One or more sentences per step of a recorded walk.

    The walk supplies the order and the subject; the forms supply the shape.
    Both are recordings, so the same walk over the same store and forms
    produces the same text every time.
    """
    labels = getattr(store, "source_labels", set()) or set()
    out: List[Dict[str, Any]] = []
    for core in getattr(trace, "seen", []):
        facets = [f for f in (store.crosses.get(core) or {})
                  if f not in labels and 2 <= len(f) <= 10]
        drafts = compose(forms, core, sorted(facets), limit=per_step,
                         content_from=[core], vocab=vocab)
        for d in drafts:
            out.append(d.as_dict())
    return out
