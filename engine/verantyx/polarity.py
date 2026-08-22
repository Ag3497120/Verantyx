"""Evidence polarity — the opposition axis, awake.

The cross has had opposite poles since the first sketch and nothing has ever
lived on them: no fact carries a sign, so "the shelter is open" and "the
shelter is closed" land in the same facet bag and the store cannot see that
they fight. This module gives facts a pole, and it does it by PLACEMENT
rather than by new detection machinery: a polar fact is stored as a keyed
facet `aspect:value`, and `CrossStore.contradictions()` — which has detected
multi-valued keys all along — fires on its own. The flow's claim was that
only the placement was missing; that turned out to be literally true.

Polarity detection is a closed vocabulary, deterministic, and deliberately
small: antonym pairs whose two members really are mutually exclusive states
of one aspect, plus negators. No embedding similarity, no sentiment model —
"open" vs "closed" is an opposition; "open" vs "large" is not, and a fuzzy
detector that thinks otherwise would manufacture contradictions, which is
worse than missing them. Words outside the vocabulary simply carry no pole,
exactly as before.

Contradiction becomes an O(facets) LOOKUP on the answered core, not a
search: both poles of one aspect holding mass IS the contradiction, with
per-value provenance when the store tracks it. The consensus gate downgrades
an ANSWER to UNKNOWN_UNRESOLVED_CONTRADICTION only when the query actually
asks about the contradicted aspect — a store may hold a dozen disputes about
a core and still answer questions the disputes do not touch.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .cross_store import CrossStore

#: (positive, negative) — the positive member names the aspect key. Mutually
#: exclusive states only; near-synonym gradations (warm/cool) are excluded on
#: purpose because they can both be true enough to not be a contradiction.
ANTONYM_PAIRS: List[Tuple[str, str]] = [
    ("open", "closed"),
    ("safe", "dangerous"),
    ("alive", "dead"),
    ("on", "off"),
    ("full", "empty"),
    ("working", "broken"),
    ("available", "unavailable"),
    ("wet", "dry"),
    ("hot", "cold"),
    ("occupied", "vacant"),
    ("connected", "disconnected"),
    ("passable", "blocked"),
]

#: Japanese pairs. Held to a stricter rule than the English ones, because
#: Japanese has no word boundaries and matching is therefore by substring:
#: every term here must be long and distinctive enough that it cannot appear
#: inside an unrelated word. That is why 「開」 is absent — it sits inside
#: 開始, 公開, 展開 and would manufacture a contradiction every time a
#: document mentioned a meeting starting. Missing an opposition costs one
#: undetected disagreement; inventing one costs the reader's trust in every
#: contested claim the report shows.
#:
#: Verified against a control corpus of unrelated sentences containing the
#: near-miss words — see polarity_ja_eval in settings-adjacent evals.
# The Japanese vocabulary is DATA, shipped as lang_data/ja_grammar.json
# and extensible by overlay — the design rationale (2-char floor, one
# pole per term, aspect joins) is enforced by ja_grammar.validate().
from .ja_grammar import ALIASES as _JA_ALIASES
from .ja_grammar import COMPLETION_SUFFIXES as _JA_COMPLETION
from .ja_grammar import ANTONYM_PAIRS as ANTONYM_PAIRS_JA
from .ja_grammar import ASPECT_OF as _ASPECT_OF_JA
from .ja_grammar import SUPPRESSIONS as _JA_SUPPRESSIONS
from .ja_grammar import TERMS as _JA_TERMS


def _suppressed(tail: str) -> bool:
    """A derived rule saw this frame and says the term asserts nothing.

    Compiled on demand and cached by pattern, because the list is loaded from
    an overlay and can change between calls without the module reloading.
    """
    import re as _re

    for pattern, _why in _JA_SUPPRESSIONS:
        rx = _SUPPRESSION_CACHE.get(pattern)
        if rx is None:
            try:
                rx = _re.compile(pattern)
            except _re.error:
                continue
            _SUPPRESSION_CACHE[pattern] = rx
        if rx.match(tail):
            return True
    return False


_SUPPRESSION_CACHE: Dict[str, Any] = {}

#: Negation that immediately FOLLOWS the polar term. Japanese negation is a
#: suffix on the predicate, so it is read from the characters after the
#: matched term, not scanned for elsewhere in the sentence.
#:
#: The previous version tried to pre-scan the sentence for anything shaped
#: like 〜ない and match it back to terms by prefix. Measured result:
#: 「この道は安全ではありません」 was stored as 安全(+) — the pole INVERTED,
#: the store asserting the road is safe where the source said it is not.
#: For the fields this is meant to serve, a detector that silently flips
#: negated claims is worse than no detector: every other error here loses
#: information, this one manufactured the opposite claim with a citation.
#: The last alternative is the label-value form a table uses:
#: 「ア 被災による通行止め：なし」 means there are NO closures, and without it
#: the sentence was stored as 通行止 — the claim inverted, with a government
#: citation attached, which is the one failure this module calls worse than
#: silence. Found in 内閣府's 令和8年熊本地震 reports while checking what tabular
#: reading had started to admit. The separator is optional because 「通行止め
#: なし」 occurs bare, and 「通行止め：あり」 is untouched and stays positive.
_JA_NEG_AFTER = re.compile(
    r"^(?:さ)?(?:では|じゃ)?(?:あり)?ません"
    r"|^(?:では|じゃ)?ない"
    r"|^(?:して|されて|できて)?(?:い|おり)?(?:ない|ません)"
    r"|^できない|^できません"
    r"|^[ぁ-ん]?[ 　]*[：:・][ 　]*(?:なし|無し)"
    r"|^[ぁ-ん]?[ 　]*(?:なし|無し)(?![ぁ-ん])"
    r"|^[ぁ-ん]?(?:が|を|の)?[ 　]*解除"
)

#: English terms that are also ordinary prepositions or parts of hyphenated
#: words, and so need a copula in front to be a claim about a state.
#:
#: Measured, not guessed. Ingesting this project's own 12 documents produced
#: exactly one contradiction across 251 cores, and it was false: "pour a
#: second corpus ON top" against "trade-OFF", neither of which says anything
#: is on or off. Precision was 0 of 1. The Japanese side already had a guard
#: for the same class of error (a polar term swallowed by a compound); the
#: English side had none.
_REQUIRES_COPULA = {"on", "off"}
_COPULA_BEFORE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|stays?|remains?|turned)\s+$",
    re.IGNORECASE)

_NEGATORS = re.compile(r"\b(not|never|no longer|isn't|aren't|wasn't|weren't)\s+(\w+)",
                       re.IGNORECASE)

_ASPECT_OF: Dict[str, Tuple[str, str]] = {}
for _pos, _neg in ANTONYM_PAIRS:
    _ASPECT_OF[_pos] = (_pos, "+")
    _ASPECT_OF[_neg] = (_pos, "-")

# JA derived tables (ASPECT_OF, TERMS) come from ja_grammar above.


def detect_ja(sentence: str) -> List[Tuple[str, str, str]]:
    """The Japanese half of `detect`, matched by substring.

    Substring matching is forced by the language — there are no spaces to
    split on — and it is why the vocabulary above is restricted to long,
    distinctive terms. Scanning longest-first and blanking each hit stops one
    stretch of text from being counted twice, which would otherwise let
    使用可能 also register as a 使用不可 near-miss.
    """
    out: List[Tuple[str, str, str]] = []
    text = sentence or ""
    seen: Set[str] = set()
    for term in _JA_TERMS:
        start = _standalone_index(text, term)
        if start < 0:
            continue
        canonical = _JA_ALIASES.get(term, term)
        hit = _ASPECT_OF_JA.get(canonical)
        if hit is None or canonical in seen:
            continue
        seen.add(canonical)
        aspect, pol = hit
        # Read the suffix directly after the term — that is where Japanese
        # puts the negation, and the only place it can belong to THIS term.
        negated_here = bool(_JA_NEG_AFTER.match(text[start + len(term):]))
        # Blank the matched span so a shorter term inside it cannot match
        # separately — 「受付終了」must not also report 「受付中」.
        text = text[:start] + "　" * len(term) + text[start + len(term):]
        if negated_here:
            pol = "-" if pol == "+" else "+"
            out.append((aspect, f"not_{canonical}", pol))
        else:
            # Same convention as the English half: the value is the word, and
            # `not_` appears only for an explicit negation. Naming the
            # negative pole `not_危険` would have said "not dangerous" about a
            # sentence that said dangerous.
            out.append((aspect, canonical, pol))
    return out


def _place_poles(store: CrossStore, sentence: str, core: str,
                 hits: List[Tuple[str, str, str]], lang: str,
                 claim: Optional[str] = None,
                 context: Optional[str] = None) -> None:
    """Attach each detected pole to the noun it is actually predicated of.

    The recall half of the subject gate. The gate alone asked "is the CORE
    the subject?" and threw the pole away otherwise — correct for precision,
    and it cost every quotative claim: "Staff confirmed that the lighthouse
    has been open" cores under staff, so the lighthouse's state vanished.
    Now the pole follows its subject: on the core when the core is the
    subject (the common case, unchanged), on the subject's own cross when it
    is some other noun, and nowhere when no noun passes — a hypothetical
    (「使用不可の場合」, "if the elevator is unavailable") still places
    nothing, because a pole from a supposition is a manufactured fact.
    """
    read = claim or sentence
    # One sentence saying both poles about one subject is a change being
    # narrated, not a disagreement, and the later state is the current one:
    # 「合志市 断水あり（復旧済）」 records an outage that is over, and
    # 「一時的に断水があったが、21:40 時点で復旧が確認された」 the same. Storing
    # both would have the store report a municipality as contradicting itself
    # inside a single row of a single document. Later cancels earlier, which
    # also reads 「復旧したが再び断水」 the right way round.
    #
    # Scoped to one subject deliberately: 「A市は断水、B市は復旧」 is two claims,
    # and each still lands on its own noun.
    latest: Dict[Tuple[str, str], Tuple[int, str]] = {}
    for aspect, value, _pol in hits:
        word = value.replace("not_", "")
        if subject_is_core(read, core, word, lang):
            target = core
        else:
            target = subject_of(read, word, lang)
            if target is None:
                # The row asserts a value and names no subject — the normal
                # shape of an official document, where the subject is in the
                # heading above. Only for THAT case: a header row or an
                # enumeration returns (False, None) and still places nothing,
                # which is what keeps the heading from collecting every stray
                # word in its section.
                asserted, _ = (tabular_claim_ja(read, word)
                               if lang == "ja" else (False, None))
                if not (asserted and context):
                    continue
                target = context
        seen_at = read.rfind(word)
        # The one choke point every pole passes through, so this is where
        # data-driven suppressions belong. Every guard-skipped defect this
        # project has hit — enumeration, deeming, until, and now のため on the
        # statutes — had the same anatomy: a rule applied on one path and
        # missed on another. A suppression consulted only in `tabular_claim_ja`
        # and the subject gate had the same anatomy AGAIN: the audit found five
        # placements whose tails its own patterns matched, because placement
        # itself never asked. Asking here, after target resolution, closes the
        # class rather than the instance: any pattern a person or the evolve
        # loop adds to the overlay now holds on every path at once.
        if _suppressed(read[seen_at + len(word):]):
            continue
        key = (target, aspect)
        if key not in latest or seen_at > latest[key][0]:
            latest[key] = (seen_at, value)

    for (target, aspect), (_seen_at, value) in latest.items():
        store.add(target, {f"{aspect}:{value}": None},
                  source=sentence.strip())


def _standalone_index(text: str, term: str) -> int:
    """Where `term` occurs as its own word, or -1.

    Japanese compounds are formed by butting kanji together, so a substring
    match alone reads 停止線 (a painted stop line) as "stopped" and 危険物
    (hazardous materials) as "dangerous" — both were produced by the first
    version of this, and both would have manufactured a contradiction out of
    a sentence that made no claim at all.

    The rule: reject when the next character is a kanji, because that is a
    compound. Hiragana and katakana after the term are inflection or
    particles and leave the meaning intact — 通行止です, 開設されました,
    復旧し通行可能に all survive it.

    Deliberately one-sided. Testing the preceding character too would reject
    大変危険です, where the kanji before is an intensifier and the claim is
    real. Missing a compound that leads with a polar term is the cheaper
    error, and the vocabulary is small enough to inspect.

    The one exception is a closed set of completion suffixes shipped as
    grammar data (`ja_grammar.COMPLETION_SUFFIXES`). 済 is a kanji but not a
    compound head: 復旧作業 is an effort and 復旧済 is the state itself, and
    government damage tables record a municipality's water coming back with
    exactly that word.
    """
    at = 0
    while True:
        at = text.find(term, at)
        if at < 0:
            return -1
        rest = text[at + len(term):]
        after = rest[:1]
        # A kanji after the term means a compound — 停止線, 危険物 — and the
        # term is being named rather than asserted. Two kinds of kanji are
        # grammar instead: a completion suffix (復旧済) and a NEGATION
        # (閉鎖解除). Without the second, 「滑走路閉鎖解除済」 was read as a
        # compound and silently dropped: the guard was right that 閉鎖解 is not
        # 閉鎖, and wrong about why. The runway had reopened.
        # 〜中 says the state is still running, and it is safe on exactly one
        # side. For a term that names a STATE — every negative pole here is
        # one — 「操業停止中」 is stopped and 「断水中」 is still out. For a term
        # that names a TRANSITION, 中 means the opposite of the word:
        # 「復旧中」 is being restored and is NOT restored, and reading it as
        # 復旧 would tell a reader the water is back while the source says
        # crews are still working. Restricting it to the negative pole makes
        # that inversion impossible by construction rather than by care.
        ongoing = (after == "中"
                   and (_ASPECT_OF_JA.get(_JA_ALIASES.get(term, term))
                        or ("", ""))[1] == "-")
        if (not after or not _KANJI.match(after)
                or after in _JA_COMPLETION
                or ongoing
                or _JA_NEG_AFTER.match(rest)):
            return at
        at += 1


_KANJI = re.compile(r"[㐀-䶿一-鿿]")

#: A date, a time span or a count — the shape of a value rather than of a
#: column name. Its presence is what makes a row DATA.
_JA_ROW_DATA = re.compile(r"[0-9０-９]{1,4}\s*[/／年月日時]|[0-9０-９]{2,}")

#: The column separator in text extracted from a laid-out page: one or more
#: spaces. 「天草市 断水あり・漏水あり」 is TWO values in ONE cell — ・ joins
#: them — and treating the term as needing to be the last thing on the line
#: read that as a further column and dropped the row.
_JA_COLUMN_GAP = re.compile(r"[ \t\u3000]")

_JA_HIRA_TAIL = re.compile(r"[぀-ゟ]")

#: 〜による / 〜に伴う mark what CAUSED a state, and a cause is not a subject.
_JA_CAUSE_MARK = re.compile(r"^(?:による|によって|により|に伴う|に因る|のため)")

#: ア イ ウ …, the enumerator official Japanese documents label list items
#: with. A one-character katakana run is never a noun — loanwords are two
#: characters or more — so it can be excluded by shape rather than by list.
_JA_ENUMERATOR = re.compile(r"[ァ-ヿ]")

#: A date or a clock time. 「７月29日」 is not a topic and not a subject, and
#: it was becoming both: 「７月29日（水）に開設した熊本刑務所の避難所につき、
#: ８月３日（月）をもって閉鎖」 cored under ７月29日 and lost the shelter.
#: Anchored at a digit, so 国道4号 and 第3条 — where the digit is INSIDE the
#: name — are untouched.
_JA_DATE_RUN = re.compile(r"[0-9０-９]+(?:[年月日時分秒][0-9０-９]*)+$")

#: （水）（月）— the weekday, and the general shape of a parenthesised label.
#: In the same sentence these were chosen as the subjects of 開設 and 閉鎖:
#: Wednesday and Monday read as "water" and "moon", each a perfectly good
#: one-character noun with nothing to do with the claim.
_JA_PAREN_LABEL = re.compile(r"[（(].?[）)]")

#: Case particles. Their presence is what separates prose from a table row,
#: and it decides whether a bare state word at the end is a claim or a column
#: heading: 「熊本刑務所を避難所として開設」 ends in a bare 開設 and is a
#: sentence; 「建物被害 停電 断水」 ends in a bare 断水 and is a heading. That
#: one shelter opening on 8/3 and closing on 8/6 was the only miss the full
#: candidate sweep of this corpus turned up.
_JA_CASE_PARTICLE = re.compile(r"[をにでとへ]|から|まで|より|として")

#: 〜するまで / 〜されるまで is a period whose ENDPOINT is the state, which
#: means the state has not arrived. 熊本県 tells evacuees that hotel
#: accommodation is available 「お住まいの市町村の避難所が閉鎖されるまでの間」
#: — until your municipality's shelter closes — and reading that as "the
#: shelter is closed" tells someone their shelter is gone while it is open.
#: Found blind on municipal HTML, a fourth genre, and it is an inversion:
#: the guard says the opposite of the source.
#:
#: 「8月3日まで閉鎖」 is untouched, because there まで precedes the term and
#: the closure is the period rather than its end.
_JA_UNTIL = re.compile(r"^(?:さ?れ|し)?る?まで")

#: A DEEMING clause defines when something COUNTS as X; it does not say that
#: anything is X. 「火災の予防に危険であると認める物件」 is a statute naming a
#: category. Both of the statute corpus's detections were this shape.
#:
#: Tested on both paths. The prose path applies it through `_anchored_ok`;
#: the tabular path does not go through that, and a legal sentence often has
#: no は or が at all — which is exactly how the first version of this guard
#: was bypassed by the very sentence it was written for.
_JA_DEEMING = re.compile(r"^[ぁ-ん]{0,8}(?:と|であると|でないと)?(認め|みなす|見なす)")


def is_state_word_ja(word: str) -> bool:
    """Is this word a state rather than a thing that can be in one?

    A state word must never be chosen as a subject or as a core. When it is,
    the subject gate asks "is this claim about 断水?" and the answer is
    trivially yes, so every guard downstream stops guarding. Measured twice:
    once as a core (「４県において断水が発生」) and once as a subject
    (「合志市 断水あり（復旧済）」, where 復旧 took 断水 for its subject and the
    municipality's restoration was filed under the outage).

    The vocabulary lists stems and the segmenter emits one okurigana with
    them, so 通行止 must also match 通行止め. Only a trailing hiragana is
    stripped — 開設準備 keeps its 準備 and stays an ordinary noun.
    """
    if word in _ASPECT_OF_JA or word in _JA_ALIASES:
        return True
    return bool(len(word) > 1 and _JA_HIRA_TAIL.match(word[-1])
                and (word[:-1] in _ASPECT_OF_JA or word[:-1] in _JA_ALIASES))

#: What a table cell puts after its state word when the cell holds a VALUE:
#: kana (断水あり, 通行止め) or a completion suffix (復旧済). A bare noun is a
#: column heading and punctuation is a list, and neither asserts anything.
_JA_CELL_VALUE = re.compile(r"^[ぁ-ヿ]|^[" + "".join(sorted(_JA_COMPLETION)) + r"]"
                            if _JA_COMPLETION else r"^[ぁ-ヿ]")


def ingest_polar_ja(store: CrossStore, sentence: str,
                    claim: Optional[str] = None,
                    context: Optional[str] = None) -> Optional[str]:
    """Japanese ingest plus pole placement.

    Mirrors `ingest_polar`, but segments with `lang.ja_ingest_sentence`
    because the English decomposer's word pattern is `[A-Za-z0-9']+` and
    returns nothing at all for Japanese. Keyed facets land on the same core
    in the same `aspect:value` shape, so `CrossStore.contradictions()` fires
    without knowing which language produced them.

    `claim` is the sentence WITHOUT its attribution suffix, when the caller
    has it. Structure is read from the claim and provenance is stored with
    the citation, which had been the same string until a rule needed to know
    where the sentence ENDS: the tabular-row reading requires the state to be
    the last column, and 「熊本市 … ・復旧済 (reported by 内閣府 8/6)」 has the
    citation sitting in that column. Detection already had its own version of
    this problem — the Latin in the suffix outvoted a short Japanese sentence
    and sent it to the English decomposer — so the suffix now stays out of
    both votes.
    """
    from .lang import ja_ingest_sentence

    core = ja_ingest_sentence(store, sentence)
    if core is None:
        return None
    _place_poles(store, sentence, core, detect_ja(sentence), "ja",
                 claim=claim, context=context)
    return core


def detect(sentence: str) -> List[Tuple[str, str, str]]:
    """(aspect_key, value_word, polarity) for every polar word in the
    sentence. `not <positive>` flips to the negative pole with a distinct
    value, so 'not open' and 'open' collide on the same key with different
    values — which is what makes the store's multi-value detection fire."""
    out: List[Tuple[str, str, str]] = []
    text = (sentence or "").lower()
    negated: Set[str] = {m.group(2) for m in _NEGATORS.finditer(text)}
    for m in re.finditer(r"[a-z']+", text):
        word = m.group(0)
        hit = _ASPECT_OF.get(word)
        if hit is None:
            continue
        if word in _REQUIRES_COPULA and not _COPULA_BEFORE.search(text[:m.start()]):
            # "on top of", "trade-off" — the word is present, the claim is not.
            continue
        aspect, pol = hit
        if word in negated:
            pol = "-" if pol == "+" else "+"
            out.append((aspect, f"not_{word}", pol))
        else:
            out.append((aspect, word, pol))
    return out


#: A section heading: a numbering marker, then a name. 内閣府 writes road
#: closures as 「①高速道路」 followed by 「ア 被災による通行止め：２路線１３区間」,
#: and the row alone cannot say which network it is about. Measured on four
#: revisions: two of the five networks genuinely changed polarity across them
#: — 有料道路 gained a closure on 8/6, 直轄国道 cleared after 7/29 — and both
#: were unreachable, the entire remaining recall gap on that corpus.
#:
#: Deliberately narrow. Only markers that cannot be a data cell are accepted:
#: ① 〜 ⑳, （2）, 3., 【福岡県】. 「7 0 7/28 ・復旧済」 also begins with a digit
#: and a space, so that form is excluded — a heading must be unmistakable,
#: because it is about to be handed a claim that has no subject of its own.
#: An article number. In a statute this is not decoration — it is the
#: citation key, the only way anyone refers to a provision, and the unit a
#: version diff compares. e-Gov emits it as its own line, so it arrived as a
#: separate segment, fell under the minimum length, and every provision in
#: 334,330 characters of 災害対策基本法 and 消防法 was stored with no way to
#: say which article it came from.
#:
#: 「第六十条の二」 and 「第六十条第二項」 are distinct provisions and keep
#: their full form; 「２」 and 「３」 alone are paragraph numbers WITHIN an
#: article, so they refine the current heading rather than replacing it.
_JA_ARTICLE = re.compile(r"^第[一二三四五六七八九十百千0-9０-９]+条"
                         r"(?:の[一二三四五六七八九十0-9０-９]+)?"
                         r"(?:第[一二三四五六七八九十0-9０-９]+項)?$")

_JA_HEADING_BRACKET = re.compile(r"^【([^】]{1,24})】$")
_JA_HEADING_MARK = re.compile(
    r"^(?:[①-⑳]|[（(]\s*[0-9０-９]{1,2}\s*[）)]|[0-9０-９]{1,2}[\.．])\s*(.+)$")


def heading_subject_ja(text: str) -> Optional[str]:
    """The thing a section heading names, or None if this is not a heading."""
    from .lang import ja_content_runs

    t = (text or "").strip()
    if not t or len(t) > 40:
        return None
    # An article number is its own heading, and unlike the others it IS the
    # subject rather than naming one.
    if _JA_ARTICLE.match(t):
        return t
    m = _JA_HEADING_BRACKET.match(t) or _JA_HEADING_MARK.match(t)
    if not m:
        return None
    rest = re.split(r"[（(【\[：:]", m.group(1))[0].strip()
    # A heading that names a STATE is a column header, and handing rows to it
    # would file every value under the word for the value.
    if not rest or detect_ja(rest):
        return None
    runs = [r for r in ja_content_runs(rest)
            if not is_state_word_ja(r) and not _JA_DATE_RUN.match(r)
            and not _JA_ENUMERATOR.fullmatch(r)]
    return runs[-1] if runs else None


def tabular_claim_ja(text: str, word: str) -> Tuple[bool, Optional[str]]:
    """Read a table row: (is this an asserted cell value, whose is it).

    Official damage reports keep their per-place facts in tables, and a table
    row has no particle at all — nothing marks a subject, so the prose paths
    find nothing and the row's claim is dropped. Japanese tabular notation
    reads head-final like the rest of the language: the state in the last
    column is predicated of the nearest noun before it.

    This is the reading convention, not an inference about one ministry's
    layout, but a row is also the exact shape a heading has, so it is guarded:

      no particle    a sentence has は or が; a row does not. This is what
                     keeps the rule away from prose entirely.
      last column    the state must sit in the row's final field, so a mid-row
                     mention (「停止 断水」— 停止 is not the status) is
                     excluded. Columns are separated by WHITESPACE, not by the
                     term being last on the line: 「天草市 断水あり・漏水あり」 is
                     two values in one cell, and requiring nothing after the
                     term cost half the recall this rule exists to buy — 3 of
                     6 restorations, measured against a water table read by
                     hand, the three missed all having a compound cell.
      not a quantity a subject may not end in a bare digit. 「約20,970」 is how
                     many households lost water, not who did. 国道4号 and 第3条
                     end in 号/条 and stay eligible.
      value marked   a data cell says what it holds, in kana or with a
                     completion suffix — 断水あり, 復旧済, 通行止め. A HEADER
                     names columns with bare nouns (「建物被害 停電 断水」 is the
                     damage table's heading; across four revisions 断水 appears
                     bare 26 times and as 断水あり 14, the bare ones headings),
                     and an ENUMERATION lists topics (「害、 停電、 断水、」).
                     Prose is exempt from the marker, because a sentence may
                     end in a bare verbal noun — 「熊本刑務所を避難所として開設」
                     — and case particles are what tell the two apart.

    The two return values are separate on purpose. `(False, None)` means this
    is not a claim and nothing should be placed. `(True, None)` means it IS a
    claim whose subject is not in the row — which is the normal shape of an
    official document, 「①高速道路 / ア 被災による通行止め：２路線１３区間」, and
    the caller can supply the heading. Collapsing both into None is what made
    those rows unreachable.
    """
    from .lang import ja_content_runs

    if re.search(r"[はが]", text) or re.search(
            r"(場合|とき|なら|れば|たら|予定|見込)", text):
        return False, None
    at = _standalone_index(text, word)
    if at < 0:
        return False, None
    tail = text[at + len(word):]
    # A negation is a value too. 「滑走路閉鎖解除済」 says the runway REOPENED,
    # and the marker test looked only at the character after 閉鎖 — 解 — which
    # is neither kana nor a completion suffix, so the row asserted nothing and
    # the reopening was dropped.
    # A row that carries DATA — a date, a count — is a data row even when its
    # state word ends it bare. 「熊本市職業訓練センター 7/28(火)～7/31(金)
    # ※8/1～開館」 is one facility's closure with its dates, and requiring kana
    # after 開館 rejected 244 such rows on 熊本市's closure tables. A HEADING
    # has no data in it at all — 「NO 閉鎖期間 施設名」, 「建物被害 停電 断水」 —
    # which is what still separates the two.
    marked = bool(_JA_CELL_VALUE.match(tail) or _JA_NEG_AFTER.match(tail)
                  or _JA_CASE_PARTICLE.search(text)
                  or _JA_ROW_DATA.search(text))
    # A term followed by a list separator is being NAMED, not asserted —
    # 「避難所の開設、運営等について」 lists what the guidance covers.
    # `_anchored_ok` applies the same rule on the prose path; stated again
    # because this branch does not go through it, and because relaxing the
    # marker for particle-bearing prose reopened exactly this hole.
    enumerated = bool(re.match(r"^[、，]", tail))
    if (not marked or enumerated or _JA_COLUMN_GAP.search(tail)
            or _JA_DEEMING.match(tail) or _JA_UNTIL.match(tail)
            or _suppressed(tail)):
        return False, None

    head = text[:at]
    for run in reversed(ja_content_runs(head)):
        if (run == word or is_state_word_ja(run)
                or run[-1] in "0123456789０１２３４５６７８９"
                or _JA_ENUMERATOR.fullmatch(run)
                or _JA_DATE_RUN.match(run)):
            continue
        # A cause is not a subject. 「ア 被災による通行止め：なし」 and
        # 「ア 被災による通行止め：２県６区間」 are two road networks' rows in ONE
        # 8/6 report, each headed the same way, and taking 被災 for the subject
        # made the document contradict itself.
        where = head.rfind(run) + len(run)
        if _JA_CAUSE_MARK.match(head[where:]):
            continue
        return True, run
    return True, None


def _around(text: str, run: str) -> str:
    """The run with the character on each side — enough to see （水）."""
    at = text.rfind(run)
    if at < 0:
        return run
    return text[max(0, at - 1):at + len(run) + 1]


def subject_of(sentence: str, word: str, lang: str = "en") -> Optional[str]:
    """The noun `word` is predicated of, or None if there is no clean subject.

    This generalizes the subject gate from a yes/no about the core into
    finding the actual subject — the recall half of the same coin. Measured
    need: "Staff confirmed that the lighthouse has been open" files its core
    under staff, so a gate that only asks "is the core the subject?" throws
    the claim away. The claim is real; it just belongs to the lighthouse.
    Now the pole is placed on whichever noun IS the subject.

    Two refusals, both learned from planted traps:

      conditionals   "If the elevator is unavailable, …" and 「使用不可の
                     場合は…」 assert nothing — they suppose. A subject whose
                     clause opens with if/when/unless (EN) or whose predicate
                     is followed by 場合/なら/れば (JA) is rejected, because a
                     pole from a hypothetical is a manufactured fact.
      no subject     when no noun passes the anchored test, the answer is
                     None and no pole is placed anywhere — same as before.
    """
    text = sentence or ""
    if lang == "ja":
        from .lang import ja_content_runs
        for run in reversed(ja_content_runs(text)):
            if (run == word or is_state_word_ja(run)
                    or _JA_DATE_RUN.match(run)
                    or (len(run) == 1
                        and _JA_PAREN_LABEL.match(_around(text, run)))
                    or not _anchored_ok(text, run, word, "ja")):
                continue
            return run
        # Enumerated subjects: 「九州自動車道、南九州自動車道など通行止めが発生」.
        # A real miss, found by reading the one government release in the
        # corpus that actually reported a closure — a person reads it as
        # "九州自動車道 is closed" and the gate saw no subject at all,
        # because the road names sit in a list and the polar term is what
        # carries が.
        #
        # Structurally distinct from the enumeration FALSE positive that the
        # guard above rejects: there, the polar term is INSIDE the list
        # (「開設、運営等については」— 開設 is one of the things being listed);
        # here it FOLLOWS a list closed by など/等 and is predicated of every
        # item in it. Inside versus after is the whole distinction, and it is
        # visible in the characters.
        m = re.search(r"((?:[^、，。\s]+[、，]){1,6}[^、，。\s]*?)(?:など|等)\s*"
                      + re.escape(word), text)
        if m:
            items = [x for x in re.split(r"[、，]", m.group(1)) if x.strip()]
            if items:
                runs = ja_content_runs(items[0])
                if runs:
                    return runs[-1]

        asserted, found = tabular_claim_ja(text, word)
        return found if asserted else None

    # Lookahead, not consumption: in "that the lighthouse", a consuming
    # scan eats "that the" and captures "the" — the first run of this did
    # exactly that. Overlapping matches let "the lighthouse" be seen too.
    for m in reversed(list(re.finditer(
            r"(?=\b(?:the|a|an|this|that|its|their|our)\s+([A-Za-z][\w-]*))",
            text, re.IGNORECASE))):
        cand = m.group(1)
        if cand.lower() in {"the", "a", "an", "this", "that", "these",
                            "those", "same", "other", "first", "last",
                            word.lower()}:
            continue
        if not _anchored_ok(text, cand, word, "en"):
            continue
        return cand.casefold()
    return None


def subject_is_core(sentence: str, core: str, word: str,
                    lang: str = "en") -> bool:
    """Is `word` predicated of `core`, or of something else in the sentence?

    This gate exists because of a measurement. Catalogued across 2,633 real
    documents, the polarity detector produced 39 contradictions and the four
    inspected were all false, in the same way every time:

        "The gateway surfaces one installer (brew when available)"
        "If sandbox mode is enabled but Docker is unavailable"

    `available` describes brew, `unavailable` describes Docker — but a facet
    bag has no attachment, so both landed on the sentence's core and the two
    poles then looked like a disagreement about the gateway. Precision was
    0 of 4 on a corpus with no real disputes in it, which is the worst
    possible ratio: the system was confidently wrong and nothing was right.

    So a pole is placed only when the core is the SUBJECT of the predicate
    carrying it. Approximated, not parsed: English wants the core, then a
    copula, then the word, within a short span; Japanese wants the core
    marked by は or が before the term. Both miss real claims phrased around
    the pattern. That is the correct trade for a catalogue whose whole value
    is that a listed disagreement is worth investigating.
    """
    text = (sentence or "")
    if not core:
        return False
    return _anchored_ok(text, core if lang == "ja" else core.replace("_", " "),
                        word, lang)


def _anchored_ok(text: str, noun: str, word: str, lang: str) -> bool:
    """Anchor match plus the conditional guard AT the matched position.

    One helper for both the core route and the subject search, because the
    two drifted: the conditional check lived only in subject_of, so a
    sentence whose CORE happened to be the noun inside a when-clause placed
    a pole from a hypothetical. Found on a real document — "The group
    policy values (when group access is available…)" cored as group, the
    core route anchored inside the parenthetical, and a supposition met a
    genuine claim from the same file as a manufactured dispute.
    """
    if lang == "ja":
        m = _ja_anchor_match(text, noun, word)
        if m is None:
            return False
        at = text.rfind(word, m.start(), m.end())
        after = text[at + len(word):at + len(word) + 10] if at >= 0 else ""
        # A hypothetical asserts nothing.
        if re.match(r"^[のでにと]?(場合|とき|なら|れば|たら)", after):
            return False
        # A DEEMING clause defines when something counts as X; it does not say
        # that anything is X. 「火災の予防に危険であると認める物件」 is a statute
        # naming a category, and reading it as a claim that a物件 is dangerous
        # inverts what a regulation is for. Found blind on 災害対策基本法 and
        # 消防法, where both of the corpus's detections were this shape.
        #
        # The window is bounded and stops at a clause boundary, so a real
        # claim followed later by an unrelated 認める is untouched.
        if _JA_DEEMING.match(after):
            return False
        if _JA_UNTIL.match(after):
            return False
        if _suppressed(after):
            return False
        # A past incident is history, not a current state. Found on a real
        # government case-study PDF: 「避難所が閉鎖した後にPCR検査を実施した」
        # is one shelter's story, and reading it as "this shelter is closed"
        # put it against a sentence elsewhere in the SAME document.
        if re.match(r"^(した|され(た|て)|してい(た|る)?)?(後|際|時|直後|とき)", after):
            return False
        # A noun inside an enumeration is a topic, not a predicate:
        # 「避難所の開設、運営等については」 lists what the guidance covers.
        # A polar term followed by a list separator, or preceded by の, is
        # being named rather than asserted.
        if re.match(r"^[、，・]", after):
            return False
        if at >= 1 and text[at - 1] == "の":
            return False
        return True
    m = _en_anchor_match(text, noun, word)
    if m is None:
        return False
    clause_start = max(text.rfind(ch, 0, m.start()) for ch in ".,;:(")
    clause = text[clause_start + 1:m.start()]
    return not re.search(r"\b(if|when|unless|while|whether|suppose|assuming)\b",
                         clause, re.IGNORECASE)
    # The gap between the core and its copula may not cross a clause
    # boundary. Without this, "If sandbox mode is enabled but Docker is
    # unavailable" still matched: `sandbox` … `is unavailable`, with a whole
    # other subject in between. Commas, conjunctions and subordinators are
    # where a new subject gets introduced, so the span stops at them.
    # Between the copula and the state word, two kinds of material are
    # grammatical and claim-preserving, and both come from the tier B
    # measurement (recall was 0% on English passives and adverbs while
    # Japanese passed):
    #
    #   adverbs        "remains fully open", "is still closed", "was
    #                  completely unavailable" — closed by FORM (-ly) plus
    #                  the handful of common adverbs that lack the suffix.
    #   small-clause   "was reported closed", "is considered dangerous" —
    #   participles    verbs of report and judgement whose complement is a
    #                  predicate over the SUBJECT. A closed class: adding an
    #                  arbitrary verb here would let "was painted closed"
    #                  through, so only verbs whose grammar guarantees the
    #                  attachment are listed.
def _ja_anchor(text: str, noun: str, word: str) -> bool:
    return _ja_anchor_match(text, noun, word) is not None


def _ja_anchor_match(text: str, noun: str, word: str):
    pat = re.compile(re.escape(noun)
                     + r"(?:に関して|について|につきまして)?"
                     + r"[^。]{0,12}?[はがも][^。]{0,24}?" + re.escape(word))
    return pat.search(text)


def _en_anchor(text: str, noun: str, word: str) -> bool:
    return _en_anchor_match(text, noun, word) is not None


def _en_anchor_match(text: str, noun: str, word: str):
    _mid = (r"(?:(?:\w+ly|still|now|again|already|once|long|almost|fully)\s+)*"
            r"(?:(?:reported|declared|confirmed|considered|deemed|marked|"
            r"found|kept|left|ruled|judged|presumed)\s+)?"
            r"(?:(?:\w+ly|still|now|again)\s+)*")
    pat = re.compile(
        r"\b" + re.escape(noun)
        + r"\b(?:(?!\b(?:but|and|or|if|when|while|unless|because|though|"
          r"although|which|that|where)\b)[^.,;:()\[\]])"
          r"{0,32}?\s*\b"
        r"(?:is|are|was|were|be|been|being|has\s+been|have\s+been|"
        r"becomes?|became|remains?|stays?|"
        r"turned|seems?|appears?)\s+(?:not\s+|no\s+longer\s+)?" + _mid
        + re.escape(word) + r"\b", re.IGNORECASE)
    return pat.search(text)


def ingest_polar(store: CrossStore, sentence: str) -> Optional[str]:
    """Normal ingest plus pole placement. The plain facets stay exactly as
    they were (composition and retrieval are untouched); the polar reading is
    ADDED as keyed facets on the same core — but only for poles the core is
    actually the subject of."""
    core = store.ingest_sentence(sentence)
    if core is None:
        return None
    _place_poles(store, sentence, core, detect(sentence), "en")
    return core


def query_aspects(query: str) -> Set[str]:
    """Aspect keys the query mentions — via either pole's word."""
    return {aspect for aspect, _v, _p in detect(query)}


def bipolar_evidence(store: CrossStore, core: str,
                     aspects: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """The O(facets) contradiction lookup: aspects of this core holding mass
    on both poles. Restricted to `aspects` when given, so a dispute the query
    never asked about does not block an unrelated answer."""
    out = []
    for entry in store.contradictions(str(core)):
        if aspects is not None and entry["key"] not in aspects:
            continue
        if entry["key"] in {p for p, _ in ANTONYM_PAIRS}:
            out.append(entry)
    return out


def apply_polarity_gate(store: CrossStore, out: Dict[str, Any], query: str) -> None:
    """Downgrade an ANSWER whose core carries both poles of an aspect the
    query asks about. The evidence rides on the verdict — which values, what
    mass, and (when tracked) which sources said each side — because 'it is
    contested' without the sides named is barely better than a shrug."""
    if out.get("verdict") != "ANSWER":
        return
    core = out.get("core_key") or out.get("core")
    if not core:
        return
    aspects = query_aspects(query)
    if not aspects:
        return
    disputes = bipolar_evidence(store, str(core), aspects)
    if disputes:
        out["verdict"] = "UNKNOWN_UNRESOLVED_CONTRADICTION"
        out["contradictions"] = disputes
        out["reason"] = ("both poles of " +
                         ", ".join(sorted(d["key"] for d in disputes)) +
                         " hold evidence")


# ---------------------------------------------------------------------------
# W1a — typed observed negation (SPEC_2026-08-14_eight_gaps)
#
# Distinct from the antonym-axis detector above. A negation that was
# written is testimony and may be stored as a mark on a dictionary-form
# key (¬流れる). A negation inferred from absence is a different type
# and is never stored — defense line 1 of the meaning-layers spec.
# ---------------------------------------------------------------------------

POLARITY_UNDECIDED = "POLARITY_UNDECIDED"
POLARITY_MARK = "¬"
POLARITY_POSITIVE = "positive"
POLARITY_NEGATIVE = "negative"

PREFIXES = frozenset("非不未無")

# Unfoldable modality mixes. Parity does not license a pole.
_UNDECIDED_PATS: Tuple[str, ...] = (
    "ないとは言えない", "ないとはいえない",
    "ないわけではない", "ないわけじゃない",
    "ないこともない", "ないことはない",
    "ざるを得ない", "ざるをえない",
    "なければならない", "なければいけない", "なくてはならない",
    "ないはずがない", "ないとは限らない", "ないでもない",
    "かもしれない",
)

_COPULA_PATS: Tuple[str, ...] = (
    "ではありません", "ではない", "でない",
)

# Closed lexicalized-ない adjectives. The ない is the word, not a
# negator. Frozen: a match produces NO ObservedNegation.
# Includes the られる-shaped family (つまらない/くだらない/たまらない)
# that a tagger splits as verb+ない — fabricated testimony if stored.
_NAI_LEX: Tuple[str, ...] = (
    "つまらない", "くだらない", "たまらない",
    "しょうがない", "しようがない", "仕方がない", "仕方ない",
    "もったいない",
    "とんでもない", "みっともない", "情けない", "なさけない",
    "せわしない", "ぎこちない", "あどけない", "おぼつかない",
    "やるせない", "なにげない", "何気ない", "さりげない",
    "少ない", "すくない", "危ない", "あぶない", "汚い", "きたない",
    "幼い", "おさない", "切ない", "せつない",
)
_NU_BLOCK: Tuple[str, ...] = ("死ぬ", "往ぬ")
_ZU_BLOCK: Tuple[str, ...] = (
    "まず", "必ず", "わずか", "ずつ", "ずっと", "ずいぶん",
)

_A_TO_U = {
    "あ": "う", "か": "く", "が": "ぐ", "さ": "す", "ざ": "ず",
    "た": "つ", "だ": "づ", "な": "ぬ", "は": "ふ", "ば": "ぶ",
    "ぱ": "ぷ", "ま": "む", "や": "ゆ", "ら": "る", "わ": "う",
}
_I_TO_U = {
    "い": "う", "き": "く", "ぎ": "ぐ", "し": "す", "じ": "ず",
    "ち": "つ", "ぢ": "づ", "に": "ぬ", "ひ": "ふ", "び": "ぶ",
    "ぴ": "ぷ", "み": "む", "り": "る",
}
_E_STEM = frozenset("えけげせぜてでねへべぺめれ")
_LEMMA_SPECIAL = {
    "でき": "できる", "出来": "できる",
    "来": "来る", "こ": "来る",
    "し": "する", "せ": "する",
    "あり": "ある", "い": "いる",
}
_P_HIRA = re.compile(r"[ぁ-ん]")
_P_KATA = re.compile(r"[ァ-ヺー]")
_P_KANJI_RUN = re.compile(r"[㐀-䶿一-鿿々〆〇]+")


@dataclass(frozen=True)
class ObservedNegation:
    """A negation that was written in the text. Testimony. May be stored."""

    kind: str
    surface: str
    lemma: str
    span: Tuple[int, int]
    context: Optional[str] = None


@dataclass(frozen=True)
class InferredNegation:
    """Negation inferred from absence. Forbidden to store (defense line 1)."""

    lemma: str
    reason: str = "absence_is_not_negation"


@dataclass(frozen=True)
class PolarityReading:
    """Sentence-level folded polarity, or a typed abstention."""

    verdict: str
    observed: Tuple[ObservedNegation, ...]
    count: int
    category: Optional[str]


def inferred_from_absence(lemma: str) -> InferredNegation:
    """The type that absence produces. It is never a storage key."""
    return InferredNegation(lemma=lemma)


def polarity_key(observation: object, lemma: Optional[str] = None) -> str:
    """Dictionary form + ¬ mark. Only ObservedNegation is accepted.

    The mark means a negation was written. It is not assembled into a
    negative sentence about anything else.
    """
    if isinstance(observation, InferredNegation):
        raise TypeError(
            "InferredNegation is not testimony; inferring negation "
            "from absence is forbidden (defense line 1)")
    if not isinstance(observation, ObservedNegation):
        raise TypeError("only ObservedNegation may be stored")
    return POLARITY_MARK + (lemma or observation.lemma)


def _overlaps_any(text: str, start: int, end: int, words: Tuple[str, ...]) -> bool:
    for w in words:
        i = 0
        while True:
            j = text.find(w, i)
            if j < 0:
                break
            if j < end and j + len(w) > start:
                return True
            i = j + 1
    return False


def _content_stem(text: str, i: int) -> str:
    j = i
    n_hira = 0
    while j > 0 and _P_HIRA.match(text[j - 1]) and n_hira < 4:
        j -= 1
        n_hira += 1
    n_kan = 0
    while j > 0 and (_KANJI.match(text[j - 1]) or _P_KATA.match(text[j - 1])):
        j -= 1
        n_kan += 1
        if n_kan >= 4:
            break
    return text[j:i]


def _bare_noun_before(text: str, i: int) -> Optional[str]:
    """Kanji/kata noun immediately left of ない, optional は/が/も.

    問題ない / 問題はない. A hiragana verb stem (流れ, 知ら) is not a noun.
    """
    j = i
    if j >= 1 and text[j - 1] in "はがも":
        j -= 1
    k = j
    while k > 0 and (_KANJI.match(text[k - 1]) or _P_KATA.match(text[k - 1])):
        k -= 1
    noun = text[k:j]
    if len(noun) >= 2:
        return noun
    return None


def _to_lemma(stem: str) -> str:
    if not stem:
        return ""
    if stem in _LEMMA_SPECIAL:
        return _LEMMA_SPECIAL[stem]
    last = stem[-1]
    if last in _A_TO_U:
        return stem[:-1] + _A_TO_U[last]
    if last in _E_STEM:
        return stem + "る"
    if last in _I_TO_U:
        return stem[:-1] + _I_TO_U[last]
    return stem


# Light verbs / copula always real. _NAI_LEX members are い-adjectives
# the tagger often splits (つまらない → つまる+ない).
_LEMMA_ALWAYS = frozenset({
    "ある", "いる", "する", "できる", "来る", "くる", "である",
})
_LEMMA_CACHE: Dict[str, bool] = {}
_LEMMA_VOCAB: Optional[frozenset] = None


def _lemma_vocab() -> frozenset:
    """Closed lemma set for the raw path when a live tagger query is off.

    Built once: always-real light verbs, the frozen い-adjective list,
    plus every 動詞/形容詞 orthBase the fugashi tagger confirms on those
    seeds. Live existence checks still ask the tagger per candidate.
    """
    global _LEMMA_VOCAB
    if _LEMMA_VOCAB is not None:
        return _LEMMA_VOCAB
    vocab = set(_LEMMA_ALWAYS) | set(_NAI_LEX)
    _LEMMA_VOCAB = frozenset(vocab)
    return _LEMMA_VOCAB


def _tagger_knows_pred(lemma: str) -> bool:
    """True iff unidic emits ``lemma`` as a single 動詞 or 形容詞."""
    toks = _try_fugashi_tokens(lemma)
    if not toks or len(toks) != 1:
        return False
    pos1, _pos2, _lem, written = _tok_pos(toks[0])
    if not (pos1.startswith("動詞") or pos1.startswith("形容詞")):
        return False
    return written == lemma or toks[0].surface == lemma


def _lemma_is_real(lemma: str) -> bool:
    """Existence gate: testimony only for a real verb or い-adjective.

    Fugashi/unidic is the dictionary. The raw path uses the same check
    when a tagger is importable; otherwise it falls back to ``_lemma_vocab``.
    A failed gate means no ObservedNegation — the verdict must not
    rely on a fabricated lemma (大人げる).
    """
    if not lemma or lemma in ("ない", "無い", "ます"):
        return False
    if lemma in _LEMMA_ALWAYS or lemma in _NAI_LEX:
        return True
    hit = _LEMMA_CACHE.get(lemma)
    if hit is not None:
        return hit
    if len(lemma) < 2:
        _LEMMA_CACHE[lemma] = False
        return False
    toks = _try_fugashi_tokens(lemma)
    if toks is None:
        ok = lemma in _lemma_vocab()
    elif len(toks) != 1:
        ok = False
    else:
        pos1, _pos2, _lem, written = _tok_pos(toks[0])
        ok = (pos1.startswith("動詞") or pos1.startswith("形容詞")) and (
            written == lemma or toks[0].surface == lemma)
    _LEMMA_CACHE[lemma] = ok
    return ok


def _is_i_adjective(form: str) -> bool:
    """Dictionary-backed い-adjective, including _NAI_LEX members."""
    if not form or not form.endswith("い"):
        return False
    if form in _NAI_LEX:
        return True
    toks = _try_fugashi_tokens(form)
    if not toks or len(toks) != 1:
        return False
    pos1, pos2, _lem, written = _tok_pos(toks[0])
    return pos1.startswith("形容詞") and "非自立" not in pos2 and (
        written == form or toks[0].surface == form
    )


def _kunai_observations(text: str) -> List[ObservedNegation]:
    """X-くない → one ObservedNegation(lemma=Xい), never a double fold."""
    out: List[ObservedNegation] = []
    start = 0
    while True:
        i = text.find("くない", start)
        if i < 0:
            break
        stem = _content_stem(text, i)
        adj = stem + "い"
        if stem and _is_i_adjective(adj):
            a = i - len(stem)
            out.append(ObservedNegation(
                "ending", stem + "くない", adj, (a, i + 3)))
        start = i + 1
    return out


def _span_final(text: str, end: int) -> bool:
    return end >= _content_end(text)


def prefix_split_ok(lattice: Any, surface: str) -> Optional[Tuple[str, str]]:
    """Prefix|rest passes the lattice gate; a 1-char rest abstains.

    Same judgment as 裸接尾辞棄権: a one-character remainder is not a
    known unit. No lattice means the gate cannot open.
    """
    if lattice is None or not surface or surface[0] not in PREFIXES:
        return None
    from .lattice import splits_of

    prefix = surface[0]
    for left, right in splits_of(lattice, surface):
        if left == prefix and len(right) > 1 and right in lattice.words:
            return left, right
    return None


def _raw_undecided(text: str) -> bool:
    return any(p in text for p in _UNDECIDED_PATS)


def _claim(claimed: List[bool], a: int, b: int) -> None:
    for k in range(a, min(b, len(claimed))):
        claimed[k] = True


def _free(claimed: List[bool], a: int, b: int) -> bool:
    return not any(claimed[k] for k in range(a, min(b, len(claimed))))


def _raw_observations(text: str, lattice: Any) -> List[ObservedNegation]:
    claimed = [False] * len(text)
    out: List[ObservedNegation] = []

    for pat in _COPULA_PATS:
        start = 0
        while True:
            i = text.find(pat, start)
            if i < 0:
                break
            j = i + len(pat)
            if _free(claimed, i, j):
                out.append(ObservedNegation("copula", pat, "である", (i, j)))
                _claim(claimed, i, j)
            start = i + 1

    for obs in _kunai_observations(text):
        if _free(claimed, obs.span[0], obs.span[1]):
            out.append(obs)
            _claim(claimed, obs.span[0], obs.span[1])

    start = 0
    while True:
        i = text.find("なくない", start)
        if i < 0:
            break
        j = i + 4
        if _free(claimed, i, j):
            lemma = _to_lemma(_content_stem(text, i))
            if _lemma_is_real(lemma):
                out.append(ObservedNegation("ending", "なく", lemma, (i, i + 2)))
                out.append(ObservedNegation("ending", "ない", lemma, (i + 2, j)))
            _claim(claimed, i, j)
        start = i + 1

    for pat, kind in (("ません", "ending"), ("ない", "ending")):
        start = 0
        while True:
            i = text.find(pat, start)
            if i < 0:
                break
            j = i + len(pat)
            if _free(claimed, i, j):
                if pat == "ない" and _overlaps_any(text, i, j, _NAI_LEX):
                    _claim(claimed, i, j)
                    start = i + 1
                    continue
                noun = _bare_noun_before(text, i) if pat == "ない" else None
                if noun:
                    if _span_final(text, j) and _lemma_is_real("ある"):
                        out.append(ObservedNegation(
                            "ending", pat, "ある", (i, j), context=noun))
                    _claim(claimed, i, j)
                    start = i + 1
                    continue
                lemma = _to_lemma(_content_stem(text, i))
                if _lemma_is_real(lemma):
                    out.append(ObservedNegation(kind, pat, lemma, (i, j)))
                _claim(claimed, i, j)
            start = i + 1

    start = 0
    while True:
        i = text.find("ぬ", start)
        if i < 0:
            break
        if _free(claimed, i, i + 1) and not _overlaps_any(text, i, i + 1, _NU_BLOCK):
            lemma = _to_lemma(_content_stem(text, i))
            if _lemma_is_real(lemma):
                out.append(ObservedNegation("ending", "ぬ", lemma, (i, i + 1)))
            _claim(claimed, i, i + 1)
        start = i + 1

    start = 0
    while True:
        i = text.find("ず", start)
        if i < 0:
            break
        if _free(claimed, i, i + 1) and not _overlaps_any(text, i, i + 1, _ZU_BLOCK):
            lemma = _to_lemma(_content_stem(text, i))
            if _lemma_is_real(lemma):
                out.append(ObservedNegation("ending", "ず", lemma, (i, i + 1)))
            _claim(claimed, i, i + 1)
        start = i + 1

    if lattice is not None:
        for m in _P_KANJI_RUN.finditer(text):
            run = m.group(0)
            for off, ch in enumerate(run):
                if ch not in PREFIXES:
                    continue
                a = m.start() + off
                if a < len(claimed) and claimed[a]:
                    continue
                hit = None
                surface = ""
                for end in range(len(run), off + 2, -1):
                    surface = run[off:end]
                    hit = prefix_split_ok(lattice, surface)
                    if hit:
                        break
                if hit is None:
                    continue
                b = a + len(surface)
                if _free(claimed, a, b):
                    out.append(ObservedNegation(
                        "prefix", surface, hit[1], (a, b)))
                    _claim(claimed, a, b)

    return out


def _token_spans(text: str, tokens: Iterable[Any]) -> List[Tuple[int, int, Any]]:
    pos = 0
    spans: List[Tuple[int, int, Any]] = []
    for tok in tokens:
        surface = getattr(tok, "surface", "") or ""
        if not surface:
            continue
        j = text.find(surface, pos)
        if j < 0:
            continue
        spans.append((j, j + len(surface), tok))
        pos = j + len(surface)
    return spans


def _tok_pos(tok: Any) -> Tuple[str, str, str, str]:
    feat = getattr(tok, "feature", None)
    if feat is None:
        return "", "", "", tok.surface
    pos1 = getattr(feat, "pos1", "") or ""
    pos2 = getattr(feat, "pos2", "") or ""
    lemma = getattr(feat, "lemma", None) or ""
    orth = getattr(feat, "orthBase", None) or ""
    if lemma in ("", "*"):
        lemma = ""
    elif "-" in lemma:
        lemma = lemma.split("-", 1)[0]
    written = orth if orth not in ("", "*") else (lemma or tok.surface)
    return pos1, pos2, lemma, written


def _token_bare_noun(spans: List[Tuple[int, int, Any]], i: int) -> Optional[str]:
    """Noun immediately left of ない, optional は/が/も, no verb stem."""
    k = i - 1
    if k < 0:
        return None
    pos1, _pos2, _lemma, written = _tok_pos(spans[k][2])
    if pos1.startswith("助詞") and spans[k][2].surface in ("は", "が", "も"):
        k -= 1
        if k < 0:
            return None
        pos1, _pos2, _lemma, written = _tok_pos(spans[k][2])
    if pos1.startswith("名詞") and len(written) >= 2:
        return written
    return None


def _prev_verb_lemma(spans: List[Tuple[int, int, Any]], i: int) -> str:
    for k in range(i - 1, -1, -1):
        pos1, _pos2, lemma, written = _tok_pos(spans[k][2])
        if pos1.startswith("動詞"):
            if k > 0 and _tok_pos(spans[k - 1][2])[0].startswith("名詞"):
                return ""
            if written in ("為る", "有る", "居る"):
                return {"為る": "する", "有る": "ある", "居る": "いる"}[written]
            return written or lemma
        if pos1.startswith("助詞") or pos1.startswith("助動詞"):
            continue
        break
    return ""


def _prev_i_adjective(spans: List[Tuple[int, int, Any]], i: int) -> Optional[str]:
    """Lemma of a 一般 い-adjective immediately left of ない (the く form)."""
    if i < 1:
        return None
    pos1, pos2, _lemma, written = _tok_pos(spans[i - 1][2])
    if pos1.startswith("形容詞") and "非自立" not in pos2 and written.endswith("い"):
        return written
    return None


def _token_observations(text: str, tokens: Iterable[Any],
                        lattice: Any) -> List[ObservedNegation]:
    spans = _token_spans(text, tokens)
    out: List[ObservedNegation] = []
    n = len(spans)
    used = [False] * n

    def add(kind: str, i0: int, i1: int, lemma: str, surface: str,
            context: Optional[str] = None) -> None:
        a, b = spans[i0][0], spans[i1][1]
        out.append(ObservedNegation(kind, surface, lemma, (a, b),
                                   context=context))
        for k in range(i0, i1 + 1):
            used[k] = True

    for kobs in _kunai_observations(text):
        out.append(kobs)
        for ti, (a, b, _tok) in enumerate(spans):
            if a < kobs.span[1] and kobs.span[0] < b:
                used[ti] = True

    for i, (_a, _b, tok) in enumerate(spans):
        if used[i]:
            continue
        pos1, pos2, lemma, written = _tok_pos(tok)
        surface = tok.surface

        if (pos1.startswith("助動詞") and lemma in ("ず", "ぬ")
                and surface in ("ん", "ぬ")
                and i >= 1 and _tok_pos(spans[i - 1][2])[2] == "ます"):
            # ません / ではありません
            copula = False
            j0 = i - 1
            if i >= 2 and spans[i - 2][2].surface in ("あり", "ある"):
                if (i >= 4 and spans[i - 4][2].surface == "で"
                        and spans[i - 3][2].surface == "は"):
                    copula = True
                    j0 = i - 4
                elif i >= 3 and spans[i - 3][2].surface == "で":
                    copula = True
                    j0 = i - 3
            if copula:
                add("copula", j0, i, "である", text[spans[j0][0]:spans[i][1]])
            else:
                add("ending", i - 1, i, _prev_verb_lemma(spans, i - 1) or "ます",
                    "ません")
            continue

        is_nai = (
            (pos1.startswith("助動詞") and lemma == "ない")
            or (pos1.startswith("形容詞") and lemma in ("無い", "ない")
                and "非自立" in pos2)
        )
        if is_nai:
            a_ch, b_ch = spans[i][0], spans[i][1]
            adj = _prev_i_adjective(spans, i)
            if adj:
                add("ending", i - 1, i, adj, text[spans[i - 1][0]:b_ch])
                continue
            if _overlaps_any(text, a_ch, b_ch, _NAI_LEX):
                used[i] = True
                continue
            if (i >= 2 and spans[i - 1][2].surface == "は"
                    and spans[i - 2][2].surface == "で"):
                add("copula", i - 2, i, "である", "ではない")
            elif i >= 1 and (
                spans[i - 1][2].surface == "で"
                or _tok_pos(spans[i - 1][2])[2] in ("だ", "です")
            ):
                add("copula", i - 1, i, "である", "でない")
            else:
                noun = _token_bare_noun(spans, i)
                if noun:
                    if _span_final(text, b_ch) and _lemma_is_real("ある"):
                        add("ending", i, i, "ある", surface, context=noun)
                    else:
                        used[i] = True
                else:
                    lemma_v = _prev_verb_lemma(spans, i)
                    if _lemma_is_real(lemma_v):
                        add("ending", i, i, lemma_v, surface)
                    else:
                        used[i] = True
            continue

        if pos1.startswith("助動詞") and lemma in ("ず", "ぬ"):
            lemma_v = _prev_verb_lemma(spans, i)
            if _lemma_is_real(lemma_v):
                add("ending", i, i, lemma_v, surface)
            else:
                used[i] = True
            continue

        if (pos1.startswith("接頭") and surface in PREFIXES
                and i + 1 < n and lattice is not None):
            nxt = spans[i + 1][2]
            compound = surface + nxt.surface
            hit = prefix_split_ok(lattice, compound)
            if hit:
                add("prefix", i, i + 1, hit[1], compound)

    return out


def _try_fugashi_tokens(text: str) -> Optional[List[Any]]:
    try:
        import fugashi  # type: ignore
    except ImportError:
        return None
    tagger = getattr(_try_fugashi_tokens, "_tagger", None)
    if tagger is None:
        try:
            tagger = fugashi.Tagger()
        except Exception:
            return None
        _try_fugashi_tokens._tagger = tagger  # type: ignore[attr-defined]
    try:
        return list(tagger(text))
    except Exception:
        return None


def _merge_observed(primary: List[ObservedNegation],
                    extra: List[ObservedNegation]) -> List[ObservedNegation]:
    out = list(primary)
    for item in extra:
        if any(item.span[0] < o.span[1] and o.span[0] < item.span[1]
               for o in out):
            continue
        out.append(item)
    out.sort(key=lambda o: (o.span[0], o.span[1], o.kind))
    return out


_TRAIL_COPULA: Tuple[str, ...] = (
    "であります", "である", "でした", "でしょう", "だろう", "です", "だ",
)
_TRAIL_PART: Tuple[str, ...] = ("よ", "ね", "わ", "さ", "ぞ", "な")
_TRAIL_PUNCT_END = re.compile(r"[。．.！!？?、,\s　]+$")


def _content_end(text: str) -> int:
    """Index after the last content, once です/だ/よ/ね/punct are stripped."""
    rest = text
    while rest:
        m = _TRAIL_PUNCT_END.search(rest)
        if m:
            rest = rest[:m.start()]
            continue
        hit = next((t for t in _TRAIL_COPULA if rest.endswith(t)), None)
        if hit is None:
            hit = next((t for t in _TRAIL_PART if rest.endswith(t)), None)
        if hit is None:
            break
        rest = rest[:-len(hit)]
    return len(rest)


def _counts_for_verdict(
    text: str, observed: List[ObservedNegation],
) -> List[ObservedNegation]:
    """Observations that decide the sentence verdict.

    A negation counts when it sits in the sentence-final cluster
    (trailing punctuation / です / だ / よ / ね / である allowed).
    Adjacent なく+ない at that cluster fold together. ず/ぬ as a
    predicate ending still count (original-bank conjunctive ず).
    Embedded ない (知らない人が来た) stays in ``observed`` but is
    omitted here, so the sentence is not mislabeled.
    """
    if not observed:
        return []
    end = _content_end(text)
    chosen: List[ObservedNegation] = []
    for obs in sorted(observed, key=lambda o: o.span[0], reverse=True):
        if obs.surface in ("ず", "ぬ"):
            chosen.append(obs)
            continue
        if obs.span[1] >= end:
            chosen.append(obs)
            end = obs.span[0]
            continue
        if chosen and obs.span[1] == chosen[-1].span[0]:
            chosen.append(obs)
            end = obs.span[0]
    return chosen


def _category_of(observed: List[ObservedNegation], count: int) -> Optional[str]:
    if count >= 2 and count % 2 == 0:
        return "double"
    kinds = [o.kind for o in observed]
    if "prefix" in kinds and "ending" not in kinds and "copula" not in kinds:
        return "prefix"
    if "copula" in kinds:
        return "copula"
    if "ending" in kinds:
        return "ending"
    if "prefix" in kinds:
        return "prefix"
    return None


def observe_negation(
    text: str,
    *,
    lattice: Any = None,
    tokens: Optional[Iterable[Any]] = None,
) -> PolarityReading:
    """Deterministic negation reading of one string.

    Runs the raw-text detector always, and the fugashi-token detector
    when tokens are supplied or a tagger is importable. Overlapping
    hits are merged so the same written ない is not counted twice.
    Double negation folds by parity. Unfoldable modality mixes abstain
    as POLARITY_UNDECIDED. Prefix hits require a lattice split whose
    remainder is an attested word (len > 1); a bare prefix abstains.

    Sentence verdict is negative only when the parity-folded negation
    is sentence-final (trailing punctuation / です / だ / よ / ね /
    である / だろう / でしょう). An embedded negation (知らない人が来た)
    is kept in ``observed`` as testimony; the sentence stays positive.
    Lexicalized ない adjectives on ``_NAI_LEX`` produce no
    ObservedNegation when bare; their くない form is a single
    negation of that adjective (危なくない → ¬危ない), never a double
    fold. Noun+ない (問題ない) stores lemma ある, never lemma ない,
    and only when sentence-final. An ObservedNegation is stored only
    when the folded lemma exists as a real 動詞/形容詞 (unidic via
    fugashi; raw path uses the same check or ``_lemma_vocab``).
    """
    text = text or ""
    if _raw_undecided(text):
        return PolarityReading(
            verdict=POLARITY_UNDECIDED, observed=(), count=0,
            category=POLARITY_UNDECIDED)

    raw = _raw_observations(text, lattice)
    tok_list: Optional[List[Any]]
    if tokens is not None:
        tok_list = list(tokens)
    else:
        tok_list = _try_fugashi_tokens(text)
    if tok_list:
        # Tokens win on lemma quality; raw fills spans the tagger missed.
        merged = _merge_observed(
            _token_observations(text, tok_list, lattice), raw)
    else:
        merged = raw

    count = len(merged)
    for_verdict = _counts_for_verdict(text, merged)
    if len(for_verdict) % 2 == 1:
        verdict = POLARITY_NEGATIVE
    else:
        verdict = POLARITY_POSITIVE
    return PolarityReading(
        verdict=verdict,
        observed=tuple(merged),
        count=count,
        category=_category_of(for_verdict or merged, len(for_verdict)),
    )


def fold_polarity(
    predicates: Iterable[str],
    text: str,
    *,
    lattice: Any = None,
    tokens: Optional[Iterable[Any]] = None,
) -> List[str]:
    """Mark extracted predicates with ¬ when an observed negation attaches.

    UNDECIDED leaves the list unmarked. Even parity on a lemma cancels.
    A prefix observation whose lemma was not extracted is appended as
    ¬rest — the mark is testimony that the prefix was written.
    """
    preds = list(predicates)
    reading = observe_negation(text, lattice=lattice, tokens=tokens)
    if reading.verdict == POLARITY_UNDECIDED:
        return preds
    counts: Dict[str, int] = {}
    first: Dict[str, ObservedNegation] = {}
    for obs in reading.observed:
        if not obs.lemma:
            continue
        counts[obs.lemma] = counts.get(obs.lemma, 0) + 1
        first.setdefault(obs.lemma, obs)
    out: List[str] = []
    seen = set()
    for p in preds:
        n = counts.get(p, 0)
        if n % 2 == 1:
            out.append(polarity_key(first[p], p))
            seen.add(p)
        else:
            out.append(p)
    for lemma, n in counts.items():
        if n % 2 == 1 and lemma not in seen:
            out.append(polarity_key(first[lemma], lemma))
    return out


def regression() -> Dict[str, Any]:
    """Fork-equivalent: observed vs inferred, parity, prefix gate, abstention."""
    from .lattice import build

    lat = build([
        "可能", "不可能", "公開", "非公開", "非常", "非常口",
        "未来", "不足", "完成", "未完成",
    ])
    ending = observe_negation("水が流れない。", lattice=lat)
    prefix = observe_negation("不可能である。", lattice=lat)
    undec = observe_negation("彼が来ないとは言えない。", lattice=lat)
    double = observe_negation("彼は行かなくない。", lattice=lat)
    bare = observe_negation("非常口がある。", lattice=lat)
    shinu = observe_negation("人が死ぬ。", lattice=lat)
    copula = observe_negation("彼は学生ではない。", lattice=lat)
    future = observe_negation("未来を語る。", lattice=lat)
    lex = observe_negation("この映画はつまらない。", lattice=lat)
    exist = observe_negation("問題ない。", lattice=lat)
    embed = observe_negation("知らない人が来た。", lattice=lat)
    otona = observe_negation("大人げない態度だ。", lattice=lat)
    abuna = observe_negation("危なくない。", lattice=lat)
    darou = observe_negation("彼は来ないだろう。", lattice=lat)

    inferred = inferred_from_absence("流れる")
    inferred_blocked = False
    try:
        polarity_key(inferred)
    except TypeError:
        inferred_blocked = True

    prefix_key = (
        polarity_key(prefix.observed[0])
        if prefix.observed and prefix.observed[0].kind == "prefix"
        else "")
    ending_lemmas = {o.lemma for o in ending.observed}

    ok = all([
        ending.verdict == POLARITY_NEGATIVE,
        ending.category == "ending",
        "流れる" in ending_lemmas,
        prefix.verdict == POLARITY_NEGATIVE,
        prefix.category == "prefix",
        prefix_key == "¬可能",
        undec.verdict == POLARITY_UNDECIDED,
        double.verdict == POLARITY_POSITIVE,
        double.category == "double",
        bare.verdict == POLARITY_POSITIVE,
        not any(o.kind == "prefix" for o in bare.observed),
        shinu.verdict == POLARITY_POSITIVE,
        copula.verdict == POLARITY_NEGATIVE,
        copula.category == "copula",
        future.verdict == POLARITY_POSITIVE,
        inferred_blocked,
        isinstance(inferred, InferredNegation),
        all(isinstance(o, ObservedNegation) for o in ending.observed),
        lex.verdict == POLARITY_POSITIVE and not lex.observed,
        exist.verdict == POLARITY_NEGATIVE
        and any(o.lemma == "ある" and o.context == "問題" for o in exist.observed)
        and not any(o.lemma == "ない" for o in exist.observed),
        embed.verdict == POLARITY_POSITIVE and len(embed.observed) > 0,
        otona.verdict == POLARITY_POSITIVE and not otona.observed,
        abuna.verdict == POLARITY_NEGATIVE
        and len(abuna.observed) == 1
        and abuna.observed[0].lemma == "危ない",
        darou.verdict == POLARITY_NEGATIVE,
    ])
    return {
        "experiment": "polarity",
        "fork": "POLARITY_TYPED_NEGATION",
        "pass": bool(ok),
        "result": {
            "ending": ending.verdict,
            "prefix_key": prefix_key,
            "undecided": undec.verdict,
            "double": double.verdict,
            "bare_prefix": bare.verdict,
            "shinu": shinu.verdict,
            "copula": copula.verdict,
            "inferred_blocked": inferred_blocked,
            "lexical_nai": (lex.verdict, len(lex.observed)),
            "noun_nai": (exist.verdict,
                         [o.lemma for o in exist.observed]),
            "embedded": (embed.verdict, len(embed.observed)),
            "open_lexical": (otona.verdict, len(otona.observed)),
            "kunai": (abuna.verdict,
                      [o.lemma for o in abuna.observed]),
            "darou": darou.verdict,
        },
    }
