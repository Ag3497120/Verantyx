"""Documents in, disagreement out — multi-source ingestion for deep search.

The use case this exists for: several articles about one event, and the
question "what is actually going on". An LLM summarises them into one fluent
story, and the disagreement between sources dissolves into that fluency —
which is exactly the information a person in a disaster needs most. Here the
disagreement is PRESERVED, because each source's claims land on their own
poles of the same aspect and the store's contradiction detection fires on
its own.

The output is three separated things, never blended:

    settled    every source that spoke agrees
    disputed   sources disagree — with WHICH source said WHICH side
    missing    no source answered a question the arms say should have one

`missing` is the part that turns this into DEEP search rather than
summarisation: an unanswered arm is a typed gap, and a typed gap is a search
query for the next round ("nobody wrote why — go find why"). That loop is
not invented here; it is the acquisition loop the GapGraph already runs,
pointed at news instead of at the system's own failures.

No LLM is used anywhere in this file. Sentence splitting, polarity, and arm
assignment are all deterministic, so the same documents always produce the
same report — which is what makes a disputed claim citable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .arm_schema import ArmIndex, classify_arm
from .cross_store import CrossStore
from .polarity import (ANTONYM_PAIRS, ANTONYM_PAIRS_JA, detect,
                       detect_ja, heading_subject_ja, ingest_polar,
                       ingest_polar_ja)

#: How many segments a section heading stays in reach. 内閣府 puts one to
#: three lines between 「①高速道路」 and the row it governs, and the next
#: heading arrives within a dozen; twelve is loose enough for that shape and
#: tight enough that a heading cannot adopt a claim from the next section.
_HEADING_REACH = 12

#: Recognised here as well as in `polarity`, because what makes an article
#: number special on THIS side is that it needs qualifying by its document.
_JA_ARTICLE_CORE = re.compile(r"^第[一二三四五六七八九十百千0-9０-９]+条")

#: Japanese does not put a space after 。, so a splitter that requires
#: trailing whitespace treats a whole article as one sentence — and then the
#: minimum-length filter and the English decomposer between them dropped it
#: entirely. Measured before this was fixed: a two-source Japanese corpus
#: ingested as zero sentences, silently, which is the worst way for the
#: disaster-information path to fail given who needs it.
#:
#: A newline is a boundary too, which is only safe because the loaders rejoin
#: lines the page merely wrapped (`document_loaders.unwrap_layout`). Without
#: that pairing this would shred prose at the column edge, and 「安全ではありま /
#: せん」 would be stored as 安全. With it, the rule is what lets a table row
#: be a claim at all: cutting only at 。 made 内閣府's 259-line road table one
#: sentence about 国土交通省.
#: The third alternative is a structural marker rather than punctuation. A
#: circled numeral ALWAYS begins an item, and PDF extraction glues it to the
#: line above: 「・E77 九州中央道（…）：１区間：隣接区間被災②有料道路」 hid the
#: heading 「②有料道路」 inside a detail line, so the row beneath it was filed
#: under the previous section — 高速道路 reported as having no closures when
#: it had thirteen. Splitting before the marker restores the heading.
#:
#: 〜、・ before it are excluded, because 「①〜③のとおり」 is a reference to
#: items rather than the start of one.
_SENT = re.compile(r"(?<=[.!?。！？])\s*|\n+"
                   r"|(?<=[^\s〜～、・])(?=[①-⑳])")

#: English abbreviations whose full stop is not a sentence end. Splitting at
#: every period cut 「Your channels are still connected (e.」 out of
#: migrating.md — the sentence lost its example and, more to the point, a
#: sentence can lose its NEGATION the same way, which turns a claim into its
#: opposite. Measured across 600 documents and 82,813 segments of this
#: author's repositories: 189 segments end at an abbreviation, led by etc.
#: (83) and al. (75), and e.g./i.e. are cut in the middle of themselves.
#:
#: The list is closed and the repair is conditional, because 「etc. The next
#: point」 really is two sentences. A rejoin happens only when the following
#: segment begins in lower case or a digit — the shape of a continuation
#: rather than of a new sentence.
#: Two tiers, because the repair has to be conditional for one and not the
#: other. NEVER_FINAL abbreviations do not end sentences at all, so what
#: follows joins whatever its case — 「(e.g. Telegram, Discord)」 continues
#: with a proper noun, and requiring lower case left the example severed.
#: MAY_END_SENTENCE ones genuinely can, so 「etc. The next point」 must stay
#: two sentences and only a lower-case or digit continuation rejoins.
_NEVER_FINAL = (
    "e.g.", "i.e.", "cf.", "vs.", "no.", "fig.", "vol.", "pp.", "ed.",
    "dr.", "mr.", "mrs.", "ms.", "prof.", "st.", "mt.", "approx.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.", "sep.", "sept.",
    "oct.", "nov.", "dec.",
)
_MAY_END_SENTENCE = (
    "etc.", "al.", "inc.", "ltd.", "co.", "corp.",
    "dept.", "univ.", "a.m.", "p.m.", "u.s.", "u.k.",
)
_ABBREVIATIONS = _NEVER_FINAL + _MAY_END_SENTENCE
_INITIAL_TAIL = re.compile(r"(?:^|[^A-Za-z])[A-Za-z]\.$")
_CONTINUES = re.compile(r"^[a-z0-9]")
#: The trailing token, bounded. Matching the abbreviation as a bare SUFFIX
#: read every word ending in -ed. as the abbreviation "ed." — so
#: 「The aquarium is closed.」 was joined to the sentence after it and two
#: planted contradictions vanished. The eval caught it, which is what the
#: planted suite is for.
_LAST_TOKEN = re.compile(r"(?:^|[^A-Za-z.])([A-Za-z.]{1,8}\.)$")


def _trailing_abbreviation(prev: str) -> str:
    m = _LAST_TOKEN.search(prev)
    return m.group(1).lower() if m else ""


def _rejoin_abbreviations(parts: List[str]) -> List[str]:
    """Undo splits the period did not mean, leaving the rest untouched."""
    out: List[str] = []
    for part in parts:
        if out:
            prev = out[-1].rstrip()
            nxt = part.lstrip()
            # The known abbreviations are tested first. Once 「(e.」 and
            # 「g.」 have been rejoined the result ends in a lone letter too,
            # and the no-space rule would then swallow the space before the
            # example itself: 「e.g.Telegram」.
            # A period between digits is a decimal point or a thousands
            # separator, not a sentence end. 「約9.900 戸」 (国交省 第33報, a
            # comma typed as a period) split into 約9. / 900 and the halves
            # joined to the rows around them.
            if prev.endswith(".") and len(prev) >= 2 and prev[-2].isdigit() \
                    and nxt[:1].isdigit():
                out[-1] = prev + nxt
                continue
            token = _trailing_abbreviation(prev)
            if token in _NEVER_FINAL and nxt:
                out[-1] = prev + " " + nxt
                continue
            if token in _MAY_END_SENTENCE and _CONTINUES.match(nxt):
                out[-1] = prev + " " + nxt
                continue
            # A lone initial is the middle of an abbreviation being cut in
            # half — 「(e.」 + 「g. …」 — and rejoins with no space.
            if _INITIAL_TAIL.search(prev) and nxt:
                out[-1] = prev + nxt
                continue
        out.append(part)
    return out


_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")

#: Sentence-length floor, by script. Twelve characters of Latin text is about
#: two words and carries nothing; twelve characters of Japanese is a full
#: claim — 「避難所は開いています」 is eleven. Holding both to one number is
#: how the Japanese path lost its content.
_MIN_SENT_CHARS = 12
_MIN_SENT_CHARS_CJK = 6


def _min_chars(text: str) -> int:
    return _MIN_SENT_CHARS_CJK if _CJK.search(text) else _MIN_SENT_CHARS


@dataclass
class Document:
    source: str           # citable label: outlet, URL, agency
    text: str
    published: str = ""   # free-form; kept for display, never parsed


@dataclass
class IngestReport:
    documents: int = 0
    sentences: int = 0
    #: Sentences the splitter produced, before any filter. sentences/seen is
    #: the coverage ratio — the first number to look at on an unfamiliar
    #: corpus, because a pipeline that silently drops most of its input
    #: produces a store that looks fine and holds almost nothing.
    sentences_seen: int = 0
    cores: List[str] = field(default_factory=list)
    polar_claims: int = 0
    per_source: Dict[str, int] = field(default_factory=dict)
    #: core → {lang: sentence count}. Kept per core rather than per document
    #: because one document can mix languages (this corpus does), and the
    #: catalogue's question is "what language is this TOPIC discussed in".
    core_lang: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"documents": self.documents, "sentences": self.sentences,
                "sentences_seen": self.sentences_seen,
                "cores": sorted(set(self.cores)), "polar_claims": self.polar_claims,
                "per_source": self.per_source, "core_lang": self.core_lang}


def _place(store: CrossStore, sentence: str,
           detect_on: Optional[str] = None,
           doc_lang: Optional[str] = None,
           context: Optional[str] = None) -> tuple:
    """Put one sentence in the store, using the right language's segmenter.

    `ingest_polar` goes through CrossStore.ingest_sentence, whose decomposer
    is `en_decompose` — its word pattern is `[A-Za-z0-9']+`, so a Japanese
    sentence yields no words at all and the whole string falls through as one
    core with zero facets. Nothing then links, contradicts, or answers.

    The Japanese segmenter already existed in `lang`; it simply was not on
    this path. Routing by script is the whole fix. Polarity still runs on the
    English path only, so a Japanese corpus gets cores and facets but not yet
    the open/closed contradiction pairs — stated here rather than discovered
    later, because deep_report's `disputed` list will be thinner in Japanese
    and that is a limit, not a finding about the sources.
    """
    from .lang import detect, ja_ingest_sentence

    # Detect on the ORIGINAL sentence, not the one carrying the attribution
    # suffix. `detect` compares Japanese characters against Latin ones, and
    # "(reported by f.docx)" adds enough Latin to outvote a short Japanese
    # sentence — which routed it to the English decomposer and turned the
    # whole sentence into a single core with no facets. The suffix is
    # bookkeeping; it must not get a vote on what language the claim is in.
    lang = detect(detect_on or sentence)
    # Han without kana is the signal that separates Chinese from Japanese, and
    # a Japanese TABLE ROW has no kana either: 「熊本市 約20,970 0 7/28～8/3
    # ・復旧済」 is six ideographs and not one syllabary character, so it was
    # called Chinese and routed to the path that deliberately places no poles.
    # That row is a municipality's water supply coming back, and it is the
    # other half of the update this corpus was fetched to test.
    #
    # A document has one language; a row inside it does not get its own. Where
    # the segment is script-ambiguous and the document as a whole — where kana
    # is plentiful — reads as Japanese, the document wins. A genuinely Chinese
    # document still detects as zh at document level, so its rows still route
    # to zh, which is the case the original rule was added for.
    if lang == "zh" and doc_lang == "ja":
        lang = "ja"
    if lang == "ja":
        return (ingest_polar_ja(store, sentence, claim=detect_on,
                                context=context), "ja")
    if lang == "zh":
        # Chinese gets segmentation (the ideograph-run scanner is script-,
        # not language-specific) but NOT the Japanese polarity pass: the
        # shared kanji make terms like 安全 match, while the negation and
        # predicate grammar around them is a different language's. Facts
        # without poles is the honest depth here — the alternative, routing
        # to the English decomposer, dropped Chinese sentences entirely,
        # which is the same silent-zero failure Japanese had.
        return ja_ingest_sentence(store, sentence), "zh"
    return ingest_polar(store, sentence), "en"


def ingest_documents(store: CrossStore, docs: List[Document],
                     arms: Optional[ArmIndex] = None) -> IngestReport:
    """Split each document into sentences and place them with source and
    polarity attached.

    Source attribution is appended to the sentence text so it reaches the
    store's own provenance (which records the originating snippet per
    facet). That is deliberately not a parallel bookkeeping structure: a
    citation that lives somewhere other than the evidence tends to drift
    away from it.
    """
    # Provenance defaults to off on CrossStore, which is fine for a store
    # built from one source. Here it is the whole contract: "which report
    # backed this claim" is what separates this from summarisation, and with
    # tracking off every `sources` list came back empty — indistinguishable
    # from sources that simply had nothing to say. Turned on rather than
    # required, because a caller who assembled the store elsewhere should not
    # have to know this flag exists to get attributed answers.
    store.track_provenance = True

    for doc in docs:
        if doc.published:
            store.source_meta.setdefault(doc.source, {})["published"] = doc.published

    from .lang import detect as _detect_lang

    rep = IngestReport()
    for doc in docs:
        rep.documents += 1
        count = 0
        doc_lang = _detect_lang(doc.text or "")
        # The section a row sits under. An official document names the thing
        # in a heading and states its condition in the rows below —
        # 「①高速道路」 then 「ア 被災による通行止め：２路線１３区間」 — so a row
        # that asserts a value and names no subject belongs to the heading.
        #
        # Bounded, not sticky. A heading is replaced by the next one and
        # expires after HEADING_REACH segments, because a heading that stays
        # live to the end of a document would collect every orphan claim
        # after it, and an orphan claim on the wrong subject is the error
        # this module spends everything else avoiding.
        heading: Optional[str] = None
        heading_age = 0
        for raw in _rejoin_abbreviations(_SENT.split(doc.text or "")):
            s = raw.strip()
            if not s:
                continue
            rep.sentences_seen += 1
            # Before the length floor, not after. A heading is SHORT by
            # nature — 「①高速道路」 is five characters and the floor is six —
            # so checking it after the filter meant the only headings ever
            # seen were the long ones, and every road network resolved to the
            # section title 道路 instead of to itself.
            found = heading_subject_ja(s) if doc_lang == "ja" else None
            if found:
                # An article number is only a citation key WITH its statute.
                # 第一条 exists in every law; five of them collapsed onto one
                # core, so the provision a reader was pointed at could be from
                # any of five documents. The source label is the discriminator
                # and it is already here.
                if _JA_ARTICLE_CORE.match(found):
                    found = f"{doc.source} {found}"
                heading, heading_age = found, 0
            elif heading is not None:
                heading_age += 1
                if heading_age > _HEADING_REACH:
                    heading = None

            if len(s) < _min_chars(s):
                continue

            store.source_labels.add(doc.source)
            tagged = f"{s} (reported by {doc.source})"
            core, lang = _place(store, tagged, detect_on=s, doc_lang=doc_lang,
                                context=heading)
            if core is None:
                continue
            by_lang = rep.core_lang.setdefault(core, {})
            by_lang[lang] = by_lang.get(lang, 0) + 1
            count += 1
            rep.sentences += 1
            rep.cores.append(core)
            # Counted with the same detector that placed the poles;
            # the English one alone reported zero polar claims for a
            # Japanese corpus whose poles were in fact placed.
            if detect(s) or detect_ja(s):
                rep.polar_claims += 1
            if arms is not None and classify_arm(s):
                arms.arms.setdefault(core, {}).setdefault(
                    classify_arm(s), []).append(f"{s[:180]} — {doc.source}")
        rep.per_source[doc.source] = count
    return rep


#: ISO, slash, and Japanese date forms, time optional. Free-form text that
#: matches none of them parses as None — and None never orders, so an
#: unparseable date can only ever leave a dispute standing, never invent an
#: update. The safe failure direction, chosen on purpose.
_WHEN = re.compile(
    r"(?:(\d{4})[-/年])?(\d{1,2})[-/月](\d{1,2})日?"
    r"(?:[ T　]*(\d{1,2})[:時](\d{1,2})?分?)?")


def parse_when(text: str) -> Optional[tuple]:
    """A publication stamp as a sortable tuple, or None.

    The leading element records whether a YEAR was present: 8月7日 and
    2026-08-07 must not order against each other, because "August 7th" of
    an unstated year is not before or after anything. Tuples with different
    leading flags are treated as incomparable by the caller.
    """
    m = _WHEN.search(text or "")
    if not m:
        return None
    y, mo, d, hh, mi = m.groups()
    return (1 if y else 0, int(y or 0), int(mo), int(d),
            int(hh or 0), int(mi or 0))


def _side_when(store: CrossStore, sources: List[str]) -> Optional[tuple]:
    """The latest parseable stamp among a side's sources, or None."""
    stamps = [parse_when((store.source_meta.get(src) or {}).get("published", ""))
              for src in sources]
    stamps = [t for t in stamps if t is not None]
    return max(stamps) if stamps else None


def _sources_for(store: CrossStore, core: str, facet: str) -> List[str]:
    """Which reports backed one facet, read out of the store's provenance."""
    prov = store.provenance.get(core, {}) if store.track_provenance else {}
    slot = prov.get(facet)
    if not slot or len(slot) < 3:
        return []
    m = re.search(r"reported by ([^)]+)\)", str(slot[2]))
    return [m.group(1)] if m else []


def deep_report(store: CrossStore, core: str,
                arms: Optional[ArmIndex] = None) -> Dict[str, Any]:
    """Settled / disputed / missing for one topic.

    The three lists are the answer to "what is going on", kept apart on
    purpose. Blending them is what a summary does and what makes a summary
    unusable for a decision: the reader cannot tell which parts are agreed,
    which are contested, and which nobody checked.
    """
    # Both languages' aspect keys. English-only here meant a Japanese
    # corpus produced poles that were placed correctly and then never
    # read, so every report came back "supported" no matter how hard
    # the sources disagreed.
    aspect_keys = ({p for p, _ in ANTONYM_PAIRS}
                   | {p for p, _ in ANTONYM_PAIRS_JA})
    disputed: List[Dict[str, Any]] = []
    for entry in store.contradictions(core):
        if entry["key"] not in aspect_keys:
            continue
        sides = []
        for value in entry["values"]:
            sides.append({
                "claim": value.split(":", 1)[1],
                "weight": entry["counts"].get(value, 0),
                "sources": _sources_for(store, core, value),
            })
        disputed.append({"aspect": entry["key"], "sides": sides})

    # Update vs dispute. Two poles whose sources ORDER in time are one story
    # told twice — 通行止 at 9:00 then 通行可能 at 15:00 is a reopening, not
    # a disagreement, and showing it as a conflict is the mistake that makes
    # an information officer stop trusting the board. The bar for calling it
    # an update is deliberately high: EVERY side must carry a parseable
    # stamp, all stamps must share the same year-known-ness, and the
    # ordering must be strict. Anything less stays a dispute, because
    # demoting a real conflict to an update hides exactly what this report
    # exists to surface.
    updated: List[Dict[str, Any]] = []
    still_disputed: List[Dict[str, Any]] = []
    for entry in disputed:
        stamped = [( _side_when(store, side["sources"]), side)
                   for side in entry["sides"]]
        if (all(t is not None for t, _ in stamped)
                and len({t[0] for t, _ in stamped}) == 1
                and len({t for t, _ in stamped}) == len(stamped)):
            ordered = sorted(stamped, key=lambda p: p[0])
            current_when, current = ordered[-1]
            updated.append({
                "aspect": entry["aspect"],
                "current": {**current, "when": "-".join(map(str, current_when[1:4]))},
                "superseded": [{**side, "when": "-".join(map(str, t[1:4]))}
                               for t, side in ordered[:-1]],
            })
        else:
            still_disputed.append(entry)
    disputed = still_disputed

    # Both the keyed form (open:closed) and the bare word (closed) must be
    # excluded. The bare word is also an ordinary facet of the sentence, so
    # without this a contested claim appears in BOTH lists — settled AND
    # disputed — which is the one thing this report exists to prevent.
    disputed_values = set()
    for e in store.contradictions(core):
        if e["key"] not in aspect_keys:
            continue
        for v in e["values"]:
            disputed_values.add(v)
            disputed_values.add(v.split(":", 1)[1])
            disputed_values.add(e["key"])
    # The attribution suffix is part of the ingested text, so its own words
    # become facets too ("city", "office", "reported"). They are provenance,
    # not claims, and a settled-facts list that includes the newspaper's name
    # as a fact about the shelter is worse than useless to a responder.
    attribution_words = {"reported", "by"} | _attribution_vocabulary(store, core)

    settled = []
    for facet, count in store.top_facets(core, k=12):
        if facet in disputed_values or ":" in facet:
            continue
        if facet in attribution_words:
            continue
        settled.append({"claim": facet, "weight": count,
                        "sources": _sources_for(store, core, facet)})

    missing: List[Dict[str, str]] = []
    if arms is not None:
        report = arms.report(core)
        for arm, verdict in zip(
            [a for a in report["empty"]], report["gap_verdicts"]
        ):
            missing.append({"arm": arm, "verdict": verdict,
                            "next_query": _gap_query(core, arm)})

    return {
        "core": core,
        "settled": settled,
        "disputed": disputed,
        "updated": updated,
        "missing": missing,
        # The headline number a responder actually reads first.
        "confidence": ("contested" if disputed
                       else "updated" if updated
                       else "supported" if settled else "unknown"),
    }


def _attribution_vocabulary(store: CrossStore, core: str) -> set:
    """Words that entered only through the "(reported by X)" suffix.

    Read back from provenance rather than guessed: every source label seen
    for this core is split into its words, and those words are excluded from
    the settled list. Doing it from the store's own record means a new
    outlet name never needs adding to a hardcoded list.
    """
    out: set = set()
    if not store.track_provenance:
        return out
    for slot in (store.provenance.get(core, {}) or {}).values():
        if not slot or len(slot) < 3:
            continue
        m = re.search(r"reported by ([^)]+)\)", str(slot[2]))
        if not m:
            continue
        label = m.group(1)
        out |= {w for w in re.split(r"[^a-z0-9]+", label.lower()) if w}
        # The Latin split treats every CJK character as a separator, so a
        # source called 「A新聞」 contributed only "a" and 新聞 leaked into the
        # settled facts as though the outlet's name were a fact about the
        # shelter. Same leak that was fixed for English labels; it came back
        # the moment Japanese reached this path, because the fix was written
        # in a pattern that could not see Japanese.
        out |= set(_CJK_RUN.findall(label))
        for run in _CJK_RUN.findall(label):
            # The segmenter emits sub-runs of a compound label, so exclude
            # those too — otherwise 新聞 is filtered but 新 or 聞 is not.
            out |= {run[i:j] for i in range(len(run))
                    for j in range(i + 1, len(run) + 1)}
    return out


#: Kanji/katakana runs — the same shape `lang.ja_content_runs` extracts, so
#: what a source label contributes here matches what ingestion put in. The
#: katakana class excludes ・ and ゠ for the reason given there: they sit in
#: the katakana block but are punctuation, and taking the block whole turned
#: a bullet point into a topic.
_CJK_RUN = re.compile(r"[ァ-ヺヽヾヿ]+|[㐀-䶿一-鿿]+")


_ARM_QUESTION = {
    "cause+": "why",
    "cause-": "what happens because of",
    "support+": "what evidence confirms",
    "support-": "what contradicts",
    "kind-": "an example of",
    "kind+": "what kind of thing is",
}


def _gap_query(core: str, arm: str) -> str:
    """A typed gap turned back into a search string — the step that makes
    this deep search instead of one-shot summarisation."""
    return f"{_ARM_QUESTION.get(arm, 'about')} {core}"
