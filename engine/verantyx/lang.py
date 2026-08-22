"""Multilingual front-end — deterministic, rule-based, honest about depth.

Vera's cross substrate is language-agnostic (cores and facets are just
symbols); what differs per language is segmentation and function-word
filtering. This module provides:

  detect(text)              → "ja" | "en" | "latin"  (script heuristic)
  ingest_text(store, text)  → routes to the right elementary classifier
  ja_ask(store, query)      → elementary Japanese recall path

Depth per language (v0, no external tokenizers):
  en     — full elementary grammar pipeline (en_decompose)
  ja     — script-run segmentation (kanji/katakana runs = content,
           particles/hiragana = function). Recall path, no consensus yet.
  latin  — generic content-word window with per-language function stoplists
           (es / fr / de shipped; others fall back to the shared list)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .cross_store import CrossStore

# ---------------------------------------------------------------------------
# script detection
# ---------------------------------------------------------------------------

_RE_JA = re.compile(r"[぀-ヿ一-鿿]")
_RE_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")
_RE_KANA = re.compile(r"[ぁ-んァ-ヶー]")
_RE_HAN = re.compile(r"[㐀-䶿一-鿿]")


#: A latin WORD, for the language vote. `_RE_LATIN` stays character-based
#: because the `latin` verdict below still needs to know whether there is any
#: latin at all.
_RE_LATIN_WORD = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ][A-Za-z0-9Ａ-Ｚａ-ｚ０-９.+#_-]*")


def detect(text: str) -> str:
    """Script heuristic: "ja" | "zh" | "en" | "latin".

    Chinese and Japanese share the ideographs, so counting them cannot tell
    the languages apart — and cataloguing a real corpus showed the cost:
    Chinese documents were routed down the Japanese path and 如果 and 配置
    surfaced as "topics" with Chinese facets attached. What does separate
    them is kana: running Japanese prose without any kana is close to
    nonexistent, while Chinese never has it. Han without kana, at a length
    where the absence is meaningful, is therefore called "zh".

    Short han-only fragments (交通情報 — a headline, a label) stay "ja":
    four characters without kana is normal Japanese, forty is not.
    """
    t = text or ""
    n_ja = len(_RE_JA.findall(t))
    # Latin is counted in WORDS, Japanese in characters, because that is the
    # fair comparison: 実装言語 is four characters and one word, TypeScript is
    # ten characters and one word. Counting latin per character called
    # 「実装言語はTypeScriptを用いる。」 English — nine Japanese characters
    # against ten latin ones — and routed a Japanese sentence to the English
    # decomposer, which cored it under `typescript` and attached no facets.
    # One long tool name was enough to change the language of a sentence.
    n_lat = len(_RE_LATIN_WORD.findall(t))
    if n_ja > n_lat:
        han = len(_RE_HAN.findall(t))
        if han >= 6 and not _RE_KANA.search(t):
            return "zh"
        return "ja"
    if n_lat == 0:
        return "latin"
    # English vs other latin languages is decided by the caller via lang=;
    # auto default treats latin as English (richest pipeline).
    return "en"


# ---------------------------------------------------------------------------
# Japanese (elementary, tokenizer-free)
# ---------------------------------------------------------------------------

# A content run is a katakana word, or an ideograph sequence that may
# contain digits and end in one okurigana character.
#
# Each extension is a measured failure in a domain where the loss is fatal:
#
#   digits inside runs   「国道4号」 split into 国道+号 and dropped the 4;
#                        「第3条」 became 第+条 and 「1日2錠」 became 日+錠.
#                        A legal system that cannot say WHICH article, or a
#                        medical one that loses the dose, is not weaker —
#                        it is unusable, because the number was the claim.
#   trailing okurigana   「土砂崩れ」→ 土砂崩, 「通行止め」→ 通行止. The single
#                        trailing kana from a closed set is taken only when
#                        what follows is a particle, punctuation, or the end,
#                        so inflections (崩れて…) still stop at the stem.
#   conjunction heads    Legal and administrative Japanese joins nouns with
#                        又は・若しくは・及び・並びに, and the ideograph run
#                        swallowed the head: 「消防長又は消防署長」 became
#                        消防長又 + 消防署長, so the first party to a statute
#                        was stored under a word that does not exist. Found
#                        blind on 災害対策基本法 and 消防法 — 334,330 characters
#                        where every provision names two or three parties this
#                        way. The head is only released when its own particle
#                        follows (又は, 若しくは, 及び, 並びに), so 及第 and 並木
#                        keep theirs.
#   kanji then katakana  「水洗トイレ」 and 「仮設トイレ」 are single nouns, and
#                        splitting at the script change filed both under
#                        トイレ. Measured on two revisions of 内閣府's toilet
#                        guidance: 「汲み取り式のトイレが多数使用不可」 and
#                        「水洗トイレが使用可能になった」 became one topic
#                        holding both poles — a manufactured contradiction
#                        out of a document distinguishing two kinds of
#                        toilet, in the same paragraph, on purpose. Joining
#                        removed it and changed nothing else across five
#                        corpora. The join is one-way: katakana followed by
#                        kanji stays separate, because that boundary is where
#                        a loanword ends and the next word begins.
#
# い/な stay unconditional as before (adjective endings); the new set is
# conditional to avoid swallowing conjugation.
#
# The katakana class is spelled out rather than written as the block range
# ゠-ヿ because two characters in that block are punctuation, not letters:
# ・ (U+30FB) and ゠ (U+30A0). Taking the block wholesale made ・ a content
# run of its own, and 内閣府's damage reports bullet every line with it — so
# ・ became a CORE, and 「・今後、…復旧を進める」 and 「…断水あり・漏水あり」 were
# filed as claims about the same subject. That was the only detection the
# four-revision corpus produced, and it was false. ー (U+30FC) is a letter
# and stays: 「データ」「ラーメン」 need it.
#: Latin is a content run in Japanese prose, and leaving it out silently
#: removed a whole domain. 「実装言語はTypeScriptを用いる」 came back as
#: ['実装言語', '用い'] — the term the sentence is about was invisible — and
#: 「認証はAPIキーを用いる」 as ['認証', 'キー'], because only the katakana
#: tail matched. Every downstream layer inherited it: the store never linked
#: 実装言語 to TypeScript, so sibling inference, covenant checking and
#: attestation all worked on Japanese law and on nothing with a latin name.
#:
#: The latin branch is FIRST so a mixed token stays whole: APIキー matches
#: from the A, where the katakana branch would have taken キー alone. The
#: trailing class carries version and package punctuation — C++, .NET, JWT,
#: node-fetch — because a rule about a tool names the tool exactly.
_JA_RUN = re.compile(
    r"[A-Za-zＡ-Ｚａ-ｚ][A-Za-z0-9Ａ-Ｚａ-ｚ０-９.+#_-]*[ァ-ヺヽヾヿー]*"
    r"|[ァ-ヺヽヾヿー]+"
    r"|(?:(?![又若及並](?:は|しく|び))[㐀-䶿一-鿿0-9０-９])+[ァ-ヺヽヾヿー]*"
    r"(?:[いな]|[れめきちりつけ](?=[はがをにでとのへもや、。！？\s]|$))?"
)
_ALL_DIGITS = re.compile(r"^[0-9０-９]+$")
#: Words that are grammatically nouns and informationally nothing — formal
#: nouns, pronouns, and temporal/positional deictics. Excluded because a
#: content run becomes a CORE, and a core is meant to be a topic.
#:
#: Measured, not assembled from a grammar book. Ingesting 2,491 documents
#: from this author's repositories put 次(667), 彼(552), 現在(325), 今(235)
#: and 私(220) among the twenty most-discussed "topics" in the corpus. None
#: of them is a topic; they are what sentences are built out of.
#:
#: Kept to words that are near-always function-like. 中 and 上 are omitted on
#: purpose — 中 is genuinely ambiguous (「中止」の中 vs 「作業中」) and dropping a
#: real topic is the more expensive error for an index whose purpose is to
#: show what a body of work is about.
# Stopwords now ship as data (lang_data/ja_grammar.json) so an expert
# can extend them with an overlay instead of editing source. The
# rationale for each group lives with the data's git history.
from .ja_grammar import STOPWORDS as _JA_STOP
_JA_QUESTION = ("何", "誰", "どこ", "いつ", "なぜ", "どう", "ですか", "とは")


#: A date or a clock time. Excluded from cores for the reason the stopword
#: list exists — a core is meant to be a topic, and 「７月29日」 is not one.
#: Measured: 「７月29日（水）に開設した熊本刑務所の避難所につき、８月３日（月）を
#: もって閉鎖」 cored under ７月29日, so the shelter that opened and closed had
#: no topic to be filed under. Dates cannot be a word list, so this is a
#: shape: digits FIRST, then a temporal kanji. 国道4号 and 第3条 carry their
#: digit inside the name and are untouched.
_JA_DATE = re.compile(r"[0-9０-９]+(?:[年月日時分秒][0-9０-９]*)+$")

#: A date the layout has broken apart. PDF extraction spaces the digits from
#: their unit — 「７月 30 日」 — so the run scanner sees 月 and 日 as separate
#: single-character runs and only 日 survives, becoming the CORE. 内閣府's
#: ferry table then filed 7/29 and 7/30 under one topic called 日 and reported
#: them as a contradiction: two different days, read as one thing disagreeing
#: with itself. Whether the space is there is a fact about the PDF, not about
#: the sentence, so the run is judged on its surroundings.
_JA_DATE_PIECE = re.compile(r"[年月日時分秒]")
_JA_DATE_BEFORE = re.compile(r"[0-9０-９][\s ]*$")


#: （水）（月）— a single character alone inside brackets is a label: the
#: weekday beside a date, or an item marker. Read as content, 水 and 月 are
#: two perfectly ordinary nouns (water, moon), and in
#: 「７月29日（水）に開設した…８月３日（月）をもって閉鎖」 they were chosen as the
#: subjects of 開設 and 閉鎖 — Wednesday opened the shelter and Monday closed
#: it. Filtered here rather than in one caller, because a label is not
#: content for any purpose.
_JA_BRACKETS = ("（）", "()", "〔〕", "[]", "【】")


#: A compound particle wraps one kanji in kana — に対して、に関する、に基づく、
#: に際して、に応じて、に沿って、に向けて、に係る. The kanji is the middle of a
#: grammatical unit, not a noun, but a script-run scanner sees an isolated
#: ideograph and hands it back as content. 対 was then chosen as the SUBJECT
#: of a fire-code provision. Matched by shape rather than by list, because
#: the shape is what makes it a particle.
_JA_COMPOUND_PARTICLE = re.compile(r"^[にへを]$")
_JA_PARTICLE_TAIL = re.compile(r"^(?:し|す|する|して|づ|じ|っ|わ|い|り)")


def _inside_compound_particle(text: str, start: int, end: int) -> bool:
    if end - start != 1 or start < 1:
        return False
    if not _JA_COMPOUND_PARTICLE.match(text[start - 1]):
        return False
    return bool(_JA_PARTICLE_TAIL.match(text[end:end + 2]))


def _split_date_piece(text: str, run: str, start: int) -> bool:
    """One temporal character with a digit in front of it, across a space."""
    if len(run) != 1 or not _JA_DATE_PIECE.match(run):
        return False
    return bool(_JA_DATE_BEFORE.search(text[:start]))


def _bracketed_label(text: str, start: int, end: int) -> bool:
    if end - start != 1 or start < 1 or end >= len(text):
        return False
    return text[start - 1] + text[end] in _JA_BRACKETS


#: The provenance suffix `document_ingest` appends. Its own words are not
#: content, and once latin became a content run they started arriving as
#: facets — every ingested Japanese sentence gained `by` and `reported`, plus
#: whatever latin the filename held. Excluded by SPAN rather than by a word
#: list, so a source called `policy.docx` does not contribute `docx` either.
#: The citation suffix `ingest_documents` appends to every sentence. One
#: definition, because both decomposers have to agree on where the claim
#: ends — they did not, and only the Japanese one skipped it. The English
#: path read the label as content, so `en／99-year lease.txt` became the
#: facets `en` and `txt`: 6,608 of 138,797 facets on the English sovereign,
#: touching 43.5% of its cores, until `strip_attribution` was applied there
#: too.
#: Greedy, and anchored to the end, because the suffix is APPENDED and the
#: label may itself contain brackets. `[^)]*\)` stopped at the first bracket
#: of `en／Burden of proof (law).txt`, leaving `.txt)` in the sentence — which
#: is where 545 of the 566 surviving `txt` facets came from, i.e. every
#: Wikipedia disambiguation title in the corpus.
ATTRIBUTION = re.compile(r"\((?:reported|said) by .*\)\s*$")
_JA_ATTRIBUTION = ATTRIBUTION


def strip_attribution(text: str) -> str:
    """The claim without its citation suffix.

    Structure is read from this; provenance keeps the full string. Splitting
    the two is what lets a citation be stored without spending an arm's face
    on it.
    """
    return ATTRIBUTION.sub("", text or "").strip()


def ja_content_runs(text: str) -> List[str]:
    text = text or ""
    skip = [(m.start(), m.end()) for m in _JA_ATTRIBUTION.finditer(text)]
    out: List[str] = []
    for m in _JA_RUN.finditer(text):
        if any(a <= m.start() < b for a, b in skip):
            continue
        r = m.group(0)
        if (r in _JA_STOP or _ALL_DIGITS.match(r) or _JA_DATE.match(r)
                or _bracketed_label(text, m.start(), m.end())
                or _inside_compound_particle(text, m.start(), m.end())
                or _split_date_piece(text, r, m.start())):
            continue
        out.append(r)
    return out


#: The topic phrase: everything before the first は/が that follows a content
#: character. Used to pick the head noun as the core.
#:
#: Kept as a regex for callers that only need the old shape. Ingest uses
#: `ja_topic_match` instead: the regex is blind to parentheses — `)` before
#: は misses `ウマ (麻雀)は`, and が inside `（塩が…）` steals the topic —
#: and it cannot tell a named compound (クロイツ-タウブ塩) from a の-headed
#: phrase (本町の避難所).
_JA_TOPIC = re.compile(
    r"^(.*?[㐀-䶿一-鿿ァ-ヺヽヾヿー0-9０-９][いなれめきちりつけ]?)[はが]")

_TOPIC_MARK = frozenset("はが")
_HA_PREFIX = frozenset("でにとをへも")
_OKU_TOPIC = frozenset("いなれめきちりつけ")
_PAREN_OPEN = frozenset("（(")
_PAREN_CLOSE = frozenset("）)")
_CONTENT_CHAR = re.compile(r"[㐀-䶿一-鿿ァ-ヺヽヾヿー0-9０-９]")
_KATA_RUN = re.compile(r"^[ァ-ヺヽヾヿー]+$")
_LATIN_RUN = re.compile(r"^[A-Za-zＡ-Ｚａ-ｚ][A-Za-z0-9Ａ-Ｚａ-ｚ０-９.+#_-]*$")
_SHORT_KANJI = re.compile(r"^[㐀-䶿一-鿿]{1,2}$")
_COMPOUND_JOIN = re.compile(r"^[-‐−–—・·]*$")


def _paren_depth_at(text: str, i: int) -> int:
    depth = 0
    for ch in text[:i]:
        if ch in _PAREN_OPEN:
            depth += 1
        elif ch in _PAREN_CLOSE and depth:
            depth -= 1
    return depth


def _skip_trailing_parens(text: str, j: int) -> Tuple[int, str]:
    """Walk left from ``j`` over spaces and trailing parentheticals.

    Returns the index of the noun end and the concatenated interiors
    (so a caller can ask whether the paren held a content run).
    """
    interiors: List[str] = []
    while j > 0 and text[j - 1] in " 　":
        j -= 1
    while j > 0 and text[j - 1] in _PAREN_CLOSE:
        close = text[j - 1]
        open_ch = "（" if close == "）" else "("
        depth = 1
        k = j - 2
        while k >= 0 and depth:
            if text[k] == close:
                depth += 1
            elif text[k] == open_ch:
                depth -= 1
            k -= 1
        if depth != 0:
            break
        interiors.append(text[k + 2:j - 1])
        j = k + 1
        while j > 0 and text[j - 1] in " 　":
            j -= 1
    return j, "".join(reversed(interiors))


def _is_topic_particle(text: str, i: int) -> bool:
    """は/が at ``i`` is a topic marker, not では/には and not inside parens.

    A reading or sense parenthetical may sit between the noun and the
    particle: ``塩（しお）は`` and ``ウマ (麻雀)は`` both count. The
    previous regex required a content character immediately before は/が,
    so a closing ``)`` made the whole match fail and ingest fell through
    to the first-run fallback.
    """
    if i < 1 or text[i] not in _TOPIC_MARK:
        return False
    if _paren_depth_at(text, i):
        return False
    if text[i] == "は" and text[i - 1] in _HA_PREFIX:
        return False
    j, _interiors = _skip_trailing_parens(text, i)
    if j > 1 and text[j - 1] in _OKU_TOPIC and _CONTENT_CHAR.match(text[j - 2]):
        return True
    return bool(j > 0 and _CONTENT_CHAR.match(text[j - 1]))


def ja_topic_match(text: str) -> Optional[Tuple[str, bool]]:
    """(topic phrase, content-bearing paren before the particle) or None."""
    t = text or ""
    for i, ch in enumerate(t):
        if ch in _TOPIC_MARK and _is_topic_particle(t, i):
            j, interiors = _skip_trailing_parens(t, i)
            phrase = t[:j].rstrip(" 　")
            return phrase, bool(ja_content_runs(interiors))
    return None


def _adjacent_in(text: str, left: str, right: str) -> bool:
    """``right`` follows ``left`` immediately or across a hyphen/nakaguro."""
    i = text.find(left)
    if i < 0:
        return False
    j = i + len(left)
    k = text.find(right, j)
    if k < 0:
        return False
    gap = text[j:k]
    return gap == "" or bool(_COMPOUND_JOIN.match(gap))


def _is_split_name_compound(phrase: str, runs: List[str]) -> bool:
    """Katakana/latin + short kanji tail, adjacent — クロイツ-タウブ塩.

    ``ダイヤルされた番号`` has the same two runs but された sits between
    them; that is a verb modifier plus a head, not a named compound.
    """
    if len(runs) < 2:
        return False
    tail, prev = runs[-1], runs[-2]
    if not (_SHORT_KANJI.match(tail) and (
            _KATA_RUN.match(prev) or _LATIN_RUN.match(prev))):
        return False
    return _adjacent_in(phrase, prev, tail)


def _opening_is_split_compound(text: str, runs: List[str]) -> bool:
    """First two content runs are one noun (レモン果汁), not a new field.

    A spaced dash (``キレートレモン - レモン果汁``) is a field break, not
    a compound join.
    """
    if len(runs) < 2:
        return False
    i = text.find(runs[0])
    if i < 0:
        return False
    j = i + len(runs[0])
    k = text.find(runs[1], j)
    if k < 0:
        return False
    gap = text[j:k]
    return gap == "" or bool(_COMPOUND_JOIN.match(gap))


def ja_chosen_core(text: str) -> Optional[str]:
    """The core ``ja_ingest_sentence`` would file under, or None.

    None is a typed hole: the sentence has no identifiable single-noun
    topic, and filing it under a run stolen from a compound would glue
    an unrelated predicate onto that run. The hole stays a hole —
    this function does not invent a replacement core.
    """
    runs = ja_content_runs(text)
    if not runs:
        return None
    core = runs[0]
    topic_runs: List[str] = []
    hit = ja_topic_match(text or "")
    if hit:
        phrase, content_paren = hit
        topic_runs = ja_content_runs(phrase)
        if content_paren:
            # ウマ (麻雀)は — a named surface plus a domain tag. A
            # qualifier paren on a kanji topic (制度（無料）が) is not
            # a sense: keep the head. The hole is only for a katakana
            # or latin surface, where the paren names another sense.
            last = topic_runs[-1] if topic_runs else ""
            if last and (_KATA_RUN.match(last) or _LATIN_RUN.match(last)):
                return None
        if topic_runs:
            if "の" not in phrase and _is_split_name_compound(phrase, topic_runs):
                return None
            core = topic_runs[-1]
    elif _opening_is_split_compound(text or "", runs):
        return None

    if _is_polar_ja(core):
        from .polarity import subject_of
        found = subject_of(text, core, "ja")
        if found and not _is_polar_ja(found):
            return found
        rest = ([r for r in topic_runs if not _is_polar_ja(r)]
                or [r for r in runs if not _is_polar_ja(r)])
        if not rest:
            return None
        return rest[-1]
    return core


_POLAR_JA: Optional[frozenset] = None


def _polar_terms_ja() -> frozenset:
    """The words that are states rather than subjects.

    Imported late on purpose: `polarity` imports this module, so naming it at
    the top would be a cycle.
    """
    global _POLAR_JA
    if _POLAR_JA is None:
        from .polarity import ANTONYM_PAIRS_JA
        _POLAR_JA = frozenset(w for pair in ANTONYM_PAIRS_JA for w in pair)
    return _POLAR_JA


_HIRAGANA = re.compile(r"[぀-ゟ]")


def _is_polar_ja(word: str) -> bool:
    """The vocabulary lists stems; the segmenter emits one okurigana with them.

    通行止 is the listed term and 通行止め is what a sentence contains, so a
    bare membership test misses exactly the word that started this — the road
    closure that became its own topic. Only a trailing HIRAGANA is stripped,
    which is the one character the run rule can add; 開設準備 keeps its 準備 and
    stays a topic.
    """
    from .polarity import is_state_word_ja
    return is_state_word_ja(word)


def ja_ingest_sentence(store: CrossStore, text: str) -> Optional[str]:
    """Head of the topic phrase = core, remaining runs = facets.

    Japanese is head-final: in 「本町の避難所は開設されました」 the topic is
    本町の避難所 and its head — the thing the sentence is ABOUT — is the last
    noun, 避難所. The old rule took the FIRST run, so the shelter's status
    was filed under the neighbourhood: ask about 避難所 and the store had
    nothing; every fact about it sat on 本町. For a catalogue that answers
    "what do we know about the shelter", filing under the modifier is not a
    rough edge, it is the wrong index key.

    Sentences without a topic marker keep the first-run rule, stated rather
    than hidden: there is no head to find without a boundary to find it in.
    Two measured exceptions refuse rather than steal a run from a compound:
    a katakana/latin name with a short kanji tail (クロイツ-タウブ塩 → 塩)
    and a first-run prefix glued to the next run (レモン果汁 → レモン).
    A content-bearing parenthetical before は/が (ウマ (麻雀)は) is the
    same hole — the sentence is about a sense, not the bare surface.

    A polar term is never the core, because a core is a topic and a polar term
    is a predicate. This is not tidiness — it is what keeps the subject gate
    working at all. 「４県において断水が発生」 puts 断水 before が, so the
    head-final rule made 断水 the core; and then `subject_is_core` asks whether
    the claim is about 断水 and the answer is trivially yes, so every guard
    downstream is a no-op. Measured on 内閣府's 令和8年熊本地震 reports: the
    only detection the corpus produced was 断水 against 復旧 on the core 断水,
    from two sentences about different places — a government office whose
    supply had already come back, and fifteen municipalities where it had not.
    """
    runs = ja_content_runs(text)
    if not runs:
        return None
    core = ja_chosen_core(text)
    if core is None:
        return None

    facets = [r for r in runs if r != core]
    # `source=` is what CrossStore records as provenance, and the English
    # path has always passed it. Without it, anything reading provenance —
    # document_ingest's source attribution, which is the entire point of
    # ingesting several sources — got an empty answer for Japanese and could
    # not tell that it was empty because the language was unsupported rather
    # than because the sources agreed.
    store.add(core, dict.fromkeys(facets), source=text.strip())
    store.n_sentences += 1
    return core


def ja_ask(store: CrossStore, query: str, *, k: int = 5) -> Dict[str, Any]:
    """Elementary recall: first known content run answers with its facets.

    Honest scope: this is recall + refusal, not multi-frontier consensus
    (the consensus decomposer is English-only in v0).
    """
    runs = ja_content_runs(query)
    for r in runs:
        for key in (r, r + "#p"):
            if store.has(key):
                facets = [f for f, _ in store.top_facets(key, k)]
                return {
                    "verdict": "ANSWER",
                    "core": r,
                    "facets": facets,
                    "text": r + "は" + "、".join(facets) if facets else r,
                    "lang": "ja",
                    "mode": "recall",
                }
    if runs:
        return {
            "verdict": "UNKNOWN_NO_EVIDENCE",
            "core": None,
            "queried": runs,
            "lang": "ja",
        }
    return {"verdict": "UNKNOWN_UNPARSED", "lang": "ja"}


# ---------------------------------------------------------------------------
# generic latin languages (es / fr / de + fallback)
# ---------------------------------------------------------------------------

_FUNCTION_LATIN: Dict[str, set] = {
    "es": {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
           "en", "y", "o", "es", "son", "que", "por", "para", "con", "su",
           "se", "al", "lo", "como", "más", "muy", "no", "este", "esta"},
    "fr": {"le", "la", "les", "un", "une", "des", "de", "du", "en", "et",
           "ou", "est", "sont", "que", "qui", "pour", "avec", "son", "sa",
           "ses", "au", "aux", "ce", "cette", "très", "ne", "pas", "plus"},
    "de": {"der", "die", "das", "ein", "eine", "einen", "einem", "und",
           "oder", "ist", "sind", "von", "im", "in", "mit", "für", "auf",
           "zu", "den", "dem", "des", "sich", "nicht", "sehr", "auch"},
}
_FUNCTION_SHARED = {"the", "a", "an", "is", "are", "of", "and", "or", "in"}

_LATIN_WORD = re.compile(r"[A-Za-zÀ-ɏ]+")


def latin_ingest_sentence(
    store: CrossStore, text: str, lang: str = "latin"
) -> Optional[str]:
    """Generic: first content word = core, other content words = facets."""
    stop = _FUNCTION_LATIN.get(lang, set()) | _FUNCTION_SHARED
    words = [w.casefold() for w in _LATIN_WORD.findall(text or "")]
    content = [w for w in words if w not in stop and len(w) > 1]
    if not content:
        return None
    core, facets = content[0], [w for w in content[1:] if w != content[0]]
    store.add(core, dict.fromkeys(facets))
    store.n_sentences += 1
    return core


# ---------------------------------------------------------------------------
# unified entry
# ---------------------------------------------------------------------------

def ingest_text(
    store: CrossStore, text: str, *, lang: str = "auto"
) -> Dict[str, Any]:
    """Sentence-split & ingest in the detected/forced language."""
    if lang == "auto":
        lang = detect(text)
    n = 0
    cores: List[str] = []
    if lang == "ja":
        for sent in re.split(r"[。！？\n]", text or ""):
            key = ja_ingest_sentence(store, sent)
            if key:
                cores.append(key)
                n += 1
    elif lang == "en":
        from .en_decompose import split_sentences

        for sent in split_sentences(text or ""):
            key = store.ingest_sentence(sent)
            if key:
                cores.append(key)
                n += 1
    else:
        for sent in re.split(r"[.!?\n]", text or ""):
            key = latin_ingest_sentence(store, sent, lang)
            if key:
                cores.append(key)
                n += 1
    return {"lang": lang, "n_sentences": n, "cores": cores}


_TASK_LABEL = re.compile(
    r"^\s*(problem|exercise|question|task|q|puzzle)\s*\d*\s*[:.\)]", re.I
)
# Cue words that mark "asking to do something" regardless of position —
# needed once multi-line paste is supported: a labeled academic problem
# ("Problem 1: ... prove or disprove ...") defeats a first-word-only check,
# since the first token is the label ("problem"), not the verb.
_TASK_CUE_WORDS = {
    "prove", "disprove", "derive", "verify", "compute", "calculate",
    "determine", "evaluate", "solve", "show", "demonstrate",
}


def is_question(text: str, lang: str = "auto") -> bool:
    """Declarative vs interrogative/imperative/task — gate for auto-memory
    in chat (a task must never be mistaken for a fact to remember)."""
    t = (text or "").strip()
    if lang == "auto":
        lang = detect(t)
    if t.endswith("?") or t.endswith("？"):
        return True
    if lang == "ja":
        return any(m in t for m in _JA_QUESTION)
    if _TASK_LABEL.match(t):
        return True
    words = set(t.casefold().split())
    if words & _TASK_CUE_WORDS:
        return True
    head = t.casefold().split()[:1]
    # interrogatives AND request/imperative heads: neither is a fact to
    # remember ("tell me something" must not become a knowledge cross)
    return bool(head) and head[0] in {
        "what", "who", "where", "when", "why", "how", "which", "is", "are",
        "do", "does", "did", "can", "could", "should", "would", "solve",
        "tell", "give", "show", "explain", "describe", "list", "write",
        "help", "please", "find", "search", "make", "let",
    }


def regression() -> Dict[str, Any]:
    """The topic-core rule: compounds and parentheticals do not steal a run."""
    from .cross_store import CrossStore

    cases = [
        ("クロイツ-タウブ塩が代表例。", None),
        ("レモン果汁20%使用し、クエン酸を機能性表示成分として配合した"
         "155ml瓶入り（炭酸ガス入り）。", None),
        ("ウマ (麻雀)は、麻雀の牌の一つである。", None),
        ("本町の避難所は開設されました。", "避難所"),
        ("塩（しお）は、塩化ナトリウムを主な成分とする。", "塩"),
        ("水洗トイレが使用可能になった", "水洗トイレ"),
        ("キレートレモン - レモン果汁20%を使用した155ml瓶入り（炭酸ガス入り）。",
         "キレートレモン"),
        ("断水。", None),
        ("九州自動車道、南九州自動車道など通行止めが発生しております。",
         "九州自動車道"),
        ("レモンを22.5°のくし切りにカットし、急速冷凍したカット済み冷凍レモン。",
         "レモン"),
        ("もしダイヤルされた番号が使われていない。", "番号"),
        ("火災報知用電話制度（無料）が始まった。", "火災報知用電話制度"),
    ]
    rows = []
    ok = True
    for sentence, want in cases:
        got = ja_ingest_sentence(CrossStore(), sentence)
        hit = got == want
        ok = ok and hit
        rows.append({"sentence": sentence, "want": want, "got": got,
                     "pass": hit})
    from .cross_store import CrossStore as _CS
    from .stacked import yes_no
    toy = _CS()
    toy.crosses["塩"] = {"アンモニア": 1, "イオン": 1}
    yn = yes_no(toy, "塩はしょっぱいですか")
    yn_ok = yn is not None and str(yn.get("verdict")) == "NOT_ATTESTED" and not yn.get("text")
    ok = ok and yn_ok
    rows.append({"sentence": "塩はしょっぱいですか", "want": "NOT_ATTESTED",
                 "got": None if yn is None else yn.get("verdict"),
                 "pass": yn_ok})
    return {
        "experiment": "lang",
        "fork": "JA_TOPIC_COMPOUND_HOLE",
        "pass": bool(ok),
        "result": {"n": len(rows),
                   "n_pass": sum(1 for r in rows if r["pass"]),
                   "rows": rows},
    }
