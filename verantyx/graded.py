"""Quantize the VERDICT, not only the index.

The constellation varies grain across its members and reads the spread as
doubt. The verdict never did: one gate, whole terms, and a question one
character off the corpus refused with nothing said about how close it came.

The refusal is not hypothetical. 刑法第百九十九条 carries the facet 殺人 —
from its own caption, so the statute does name the offence — and the
doctrinal term is 殺人罪. One character apart, and the whole-grain gate
reports `query_terms_not_addressed:殺人罪` exactly as it reports a word the
corpus has never held. The two are not alike and nothing told them apart.

So the same three axes the sovereigns vary are turned on the judgment, over
CORES rather than leaves:

    grain     whole / 3 / 2         windows the term is matched through
    grammar   raw / nosuffix        傷害罪 -> 傷害, per `ja_morph`
    depth     how many facets of a core are indexed at all

`resolution.Ladder` already does this and abstains on ties; the first
version of this module reimplemented it by hand and reproduced every failure
the ladder was written to avoid. Scanning all 54,244 cores per query took
900ms, requiring every term to be covered and then preferring the core with
the most facets picked a junk hub — 「殺人罪の刑は」 came back 至 — and
coarsening answered 「超伝導とは」, a term the corpus does not hold, out of
a two-character collision. Reusing the calibrated machinery is the fix.

## Does coarsening generalize to a word the store does not hold

Measurably, partly, and by composition rather than by meaning. 120 cores
with eight or more facets were REMOVED from the index and then asked for.
57% were refused outright. Of the 43% answered, the core that came back
shared 19.0% of the removed core's facets against 1.6% for a random core of
the same richness — 12.1x, and only 12% landed with no overlap at all
against 84% at random.

Most of that survives the obvious confound. A held-out 電波法第二十九条 can
be answered by 電波法施行規則第二十九条, which shares facets because it
shares a name, not because anything was inferred. Splitting on a shared
three-character prefix: siblings 21.0%, genuinely different strings 17.9%,
still 11.4x over chance.

The mechanism is visible in what it returns. アバター lands on 人工知能ホロ
アバター and 火山活動 on 活動火山対策特別措置法 — Japanese is head-final and
its compounds are transparent, so a coarse window finds the compound that
CONTAINS the unheld term and inherits its subject. It also finds
鉱業法第百一条 for 漁業法第百一条, sharing a numeral and 0% of the facets.

So this reaches unseen WORDS and not unseen MEANINGS. 17.9% overlap is a
lead, not an answer, which is the whole reason a coarse reading is typed
`ANSWER_BY_COARSENING` and never promoted. The 0.0% generalization measured
on held-out terms elsewhere in this package is unchanged: nothing here
infers what a word means, it finds a longer word the corpus already held.

## Coarsening may add a reading and may never overturn one

A verdict that only a coarse member reached is typed `ANSWER_BY_COARSENING`
and carries the count. It is not promoted to `ANSWER`, and the strict
reading stays in the report for a caller that wants only that. What the
bands are worth on a given corpus is a measurement, not a property of this
code — see `calibrate`.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .resolution import Ladder, ask as rung_ask

#: One member per SETTING, one axis at a time. The cross product would be a
#: bigger census and a worse experiment: when members disagree, nothing
#: would say which axis did it.
#: `depth=1` indexes a core by its NAME alone; without it every setting
#: abstains on a one-term question. A ladder scores one point per matching
#: term, so every core that merely MENTIONS 傷害罪 ties with the one that
#: IS it, and a tie abstains — correctly, for the question the ladder was
#: written for. "Which document mentions this" and "which core is this" are
#: different questions and the store already tells them apart: name against
#: facet. Preferring the name is not a tie-break, it is reading the
#: distinction the store records.
DEFAULT_SETTINGS: Tuple[Tuple[str, Dict[str, Any]], ...] = (
    ("whole",       {"rungs": (("whole", 0),), "grammar": "raw", "depth": 1}),
    ("g3",          {"rungs": (("g3", 3),), "grammar": "raw", "depth": 1}),
    ("g2",          {"rungs": (("g2", 2),), "grammar": "raw", "depth": 1}),
    ("nosuffix",    {"rungs": (("whole", 0),), "grammar": "nosuffix", "depth": 1}),
    ("nosuffix.g2", {"rungs": (("g2", 2),), "grammar": "nosuffix", "depth": 1}),
    ("mentions",    {"rungs": (("whole", 0),), "grammar": "raw"}),
)


#: The three axes that were each measured to carry signal, and the
#: staircases built from them. Selectable rather than fixed, because the
#: finest staircase is not the best one — measured over 500 probes phrased
#: OUTSIDE the corpus's own word forms, plus 20 out-of-corpus words and 150
#: held-out cores:
#:
#:     staircase   build   reach   out-of-corpus   100% bands   unknown-word
#:                                 false answers                quality
#:     lean (6)     1.1s    464         2               1          16.7x
#:     wide (12)    2.5s    460         3               4           6.5x
#:     full (48)   52.2s    450         7              13            --
#:
#: Only ONE of four columns improves with more steps. Finer banding is real
#: — 48 steps expresses degrees of doubt 6 cannot — and it is paid for in
#: reach, in out-of-corpus precision, and in a 47x build. A caller who needs
#: graded confidence over a corpus it trusts takes `wide`; one answering
#: open questions where a wrong answer costs more than a refusal takes
#: `lean`.
#:
#: The axes themselves:
#:   grain      whole / 3 / 2      1 rung 19.3% -> 3 rungs 67.7% on leaves
#:   knowledge  facets per core    all-agree 98.1% against 14.0% alone
#:   grammar    raw/nosuffix/…     290 -> 359 answers on mismatched forms
GRAIN_AXIS: Tuple[Tuple[str, int], ...] = (("whole", 0), ("g3", 3), ("g2", 2))
GRAMMAR_AXIS: Tuple[str, ...] = ("raw", "nosuffix", "heads", "both")
DEPTH_AXIS: Tuple[Optional[int], ...] = (1, 4, 16, None)


def staircase(
    grains: Sequence[Tuple[str, int]] = GRAIN_AXIS,
    grammars: Sequence[str] = GRAMMAR_AXIS,
    depths: Sequence[Optional[int]] = (1,),
) -> Tuple[Tuple[str, Dict[str, Any]], ...]:
    """One setting per combination — the staircase, at the width asked for."""
    import itertools

    return tuple(
        ("%s.%s.d%s" % (gn, gr, dp if dp else "all"),
         {"rungs": ((gn, gs),), "grammar": gr, "depth": dp})
        for (gn, gs), gr, dp in itertools.product(grains, grammars, depths))


#: 12 steps: every grain against every grammar, cores keyed by name. Four
#: bands that were right every time, at 2.5s.
WIDE_SETTINGS = staircase()

#: 48 steps: knowledge depth as well. Thirteen bands, and the only
#: configuration that can say "9 of 12 agreed" — at 52s, seven wrong answers
#: about words the corpus never held, and unknown-word reach that lands
#: further from the mark.
FULL_SETTINGS = staircase(depths=DEPTH_AXIS)


#: Grain-free settings, for scripts where a character window collides.
#:
#: A two-character window over kanji is discriminating because there are
#: thousands of them; over latin there are twenty-six, so words share
#: windows freely. Measured on a nine-core English store against ten words
#: it never held:
#:
#:     English, 6 settings with windows   4 false answers
#:     English, whole grain only          0
#:     Japanese, 6 settings with windows  0
#:
#: superconductivity came back as `contract`, enzyme and polymer as
#: `employment`. The grain axis is a Japanese technique, not a general one,
#: and switching it off is not a loss in latin script — there was nothing
#: for it to reach.
LATIN_SETTINGS: Tuple[Tuple[str, Dict[str, Any]], ...] = (
    ("whole", {"rungs": (("whole", 0),), "grammar": "raw", "depth": 1}),
    ("mentions", {"rungs": (("whole", 0),), "grammar": "raw"}),
)


def settings_for(text: str) -> Tuple[Tuple[str, Dict[str, Any]], ...]:
    """The staircase this script can carry.

    Latin gets no character windows; anything else gets the measured six.
    """
    from .lang import detect

    return LATIN_SETTINGS if detect(text) in ("en", "latin") else DEFAULT_SETTINGS


#: Words that make an answer depend on WHEN it was asked. A store has no
#: clock, so a question carrying one of these cannot be answered from it —
#: and the failure is silent rather than absent: 「今日の天気は」 came back
#: ANSWER 今日, 「昨日の地震は」 ANSWER 地震, 「現在の株価は」 ANSWER 株価.
#: The corpus holds articles about weather and earthquakes, so every
#: time-dependent question found a timeless subject and answered with it.
#:
#: The signal is in the QUERY, not the store, which is why it can be caught
#: at all. `UNKNOWN_TIME_DEPENDENT` is the routing verdict for a tool: the
#: terms were read, a subject exists, and the answer still has to come from
#: something with a clock.
_TIME_DEICTIC = ("今日", "本日", "昨日", "明日", "今", "現在", "最新", "直近",
                 "今週", "今月", "今年", "最近", "リアルタイム", "いま",
                 "today", "now", "current", "latest", "yesterday", "tomorrow")


def time_dependent(query: str, terms: Sequence[str]) -> Optional[str]:
    """The deictic that makes this question about a moment, if any."""
    q = (query or "").lower()
    for w in _TIME_DEICTIC:
        if w in q or w in terms:
            return w
    return None


def cores_as_items(store: Any, *, depth: Optional[int] = None) -> Dict[str, List[str]]:
    """core -> the terms that identify it: itself plus its facets.

    Source labels are dropped. A label is provenance, and leaving it in lets
    a question be answered by the name of the file it would be answered
    from — which is the document citing itself.
    """
    labels = getattr(store, "source_labels", set()) or set()
    items: Dict[str, List[str]] = {}
    for core, cross in store.crosses.items():
        if core in labels:
            continue
        terms = [core] + sorted(f for f in (cross or ()) if f not in labels)
        items[core] = terms[:depth] if depth else terms
    return items


class GradedJudge:
    """One ladder per setting, over the cores of a store."""

    def __init__(self, settings: Sequence[Tuple[str, Dict[str, Any]]] = DEFAULT_SETTINGS,
                 *, read: Optional[Any] = None):
        #: How a QUERY is cut. It must match how the store was ingested: a
        #: federation built with hiragana as content still answered
        #: 「こんにちは」 with UNKNOWN_NO_SUBJECT, because the question went
        #: through the ordinary reader, which drops hiragana and produced no
        #: term to look up. The store held the greeting and the query could
        #: not spell it.
        self.read = read
        self.settings = list(settings)
        self.ladders: Dict[str, Ladder] = {}
        #: Every term the store holds, for the coverage report.
        self.held: set = set()
        #: Terms the store holds AS A CORE — a subject it can be asked
        #: about, as against one it merely mentions.
        self.cores: set = set()

    def build(self, store: Any) -> "GradedJudge":
        labels = getattr(store, "source_labels", set()) or set()
        self.cores = {c for c in store.crosses if c not in labels}
        self.held = set(self.cores)
        for cross in store.crosses.values():
            self.held |= {f for f in cross if f not in labels}
        cache: Dict[Optional[int], Dict[str, List[str]]] = {}
        for name, cfg in self.settings:
            depth = cfg.get("depth")
            if depth not in cache:
                cache[depth] = cores_as_items(store, depth=depth)
            self.ladders[name] = Ladder(
                rungs=cfg["rungs"], grammar=cfg.get("grammar", "raw"),
            ).build(cache[depth])
        return self

    def ask(self, query: str) -> Dict[str, Any]:
        """Every setting's reading, and the count. Never a promotion."""
        from .lang import ja_content_runs

        terms = (self.read or ja_content_runs)(query)
        if not terms:
            # Two different failures wore one name. 「こんにちは」 parses
            # perfectly and contains no content word — hiragana is grammar in
            # Japanese, so a greeting yields nothing to be asked about, and
            # no amount of extra grain helps because there is nothing to cut.
            # Calling that UNPARSED says the reader wrote something unreadable.
            #
            # It is the handoff signal a generation layer needs: this store
            # has no subject here and never will, so pass it on rather than
            # waiting for a verdict that cannot come.
            readable = bool((query or "").strip())
            return {
                "verdict": "UNKNOWN_NO_SUBJECT" if readable else "UNKNOWN_UNPARSED",
                "query": query, "terms": [],
                "note": "read without difficulty and holds no content word; "
                        "a knowledge store has nothing to say about it",
            }

        deictic = time_dependent(query, terms)
        if deictic is not None:
            return {
                "verdict": "UNKNOWN_TIME_DEPENDENT",
                "item": None, "terms": terms, "deictic": deictic,
                "note": "the answer depends on when this is asked and the "
                        "store has no clock; route to a source that does, "
                        "then ingest its result to make it citable",
            }

        readings: Dict[str, Optional[str]] = {}
        for name, _cfg in self.settings:
            r = rung_ask(self.ladders[name], terms)
            readings[name] = r["item"] if r["verdict"] == "ANSWER" else None

        # Which of the question's own terms the store holds at all. Concord
        # counts settings that agree on an item; it does not say the question
        # was addressed, and free-form questions are exactly where the two
        # come apart. 「パワハラを受けたらどうすればいいですか」 answered 受
        # at three settings of six — a verb stem, agreed on, about nothing
        # the reader asked. パワハラ is simply not in the store, and only
        # coverage says so.
        covered = [t for t in terms if t in self.held]
        missing = [t for t in terms if t not in self.held]

        spoke = [v for v in readings.values() if v]
        if not spoke:
            return {"verdict": "UNKNOWN_NOT_PRESENT", "item": None,
                    "terms": terms, "agreeing": 0, "of": len(self.settings),
                    "covered": covered, "missing": missing,
                    "coverage": round(len(covered) / max(len(terms), 1), 3),
                    "readings": readings}
        tally = Counter(spoke)
        top = max(tally.values())
        leaders = sorted(k for k, v in tally.items() if v == top)
        if len(leaders) > 1:
            return {"verdict": "AMBIGUOUS", "item": None, "terms": terms,
                    "agreeing": top, "of": len(self.settings),
                    "leaders": leaders[:4], "covered": covered,
                    "missing": missing,
                    "coverage": round(len(covered) / max(len(terms), 1), 3),
                    "readings": readings}
        item = leaders[0]
        strict = readings.get("whole")
        return {
            # Typed apart on purpose. A caller that wants the old contract
            # reads ANSWER and treats the other as a refusal.
            "verdict": "ANSWER" if strict == item else "ANSWER_BY_COARSENING",
            "item": item, "terms": terms,
            "agreeing": top, "of": len(self.settings),
            "covered": covered, "missing": missing,
            "coverage": round(len(covered) / max(len(terms), 1), 3),
            "spoke": len(spoke),
            "concord": round(top / len(spoke), 3),
            "readings": readings,
            "note": "a coarser setting may add a reading and may never "
                    "overturn a finer one",
        }


def band_annotation(judge: "GradedJudge", query: str) -> Optional[Dict[str, Any]]:
    """The staircase's reading of a query, shaped as an ANNOTATION.

    Rides BESIDE a store-level verdict, never inside it. The band counts
    how many cut-varied settings agreed on an item — that is STRUCTURE,
    while the verdict it annotates comes from its own consensus over the
    store — EVIDENCE. Pooling the two is the measured mistake (`vera.Vera
    .ask` documents it: summed, out-of-corpus terms reached quorum), so
    this function only ever returns something to display next to a
    verdict, and a caller that folds it into the verdict is wrong by
    construction.

    Returns None when the staircase has nothing to count: no content word,
    a time-dependent question, or an unreadable query. ``agree`` of 0 is
    NOT None — "no setting spoke" is a reading, and the one a fabricated
    subject should get.
    """
    g = judge.ask(query)
    if g.get("agreeing") is None:
        return None
    band: Dict[str, Any] = {"agree": g["agreeing"], "of": g["of"]}
    if g.get("item") is not None:
        band["item"] = g["item"]
    if g.get("concord") is not None:
        band["concord"] = g["concord"]
    return band
