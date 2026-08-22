"""Which facets are words — a separate layer, for a separate job.

A facet is whatever the reader cut out of a sentence. That is the right
thing for retrieval and the wrong thing for generation, and the gap is not
small: of 2,000 facets sampled from an 88,789-facet federation, 7.4% appear
three or more times as free-standing words in prose. エリミネーター,
コンキスタドール, 1980アイコ are real facets and none of them is a word a
sentence can use.

So generation needs a vocabulary, and a vocabulary is a different structure
from an index:

    index        every string that identifies something. 88,789 entries,
                 answers retrieval at 100% when the ladder speaks
    vocabulary   the subset attested as words, with the corpus that attested
                 them and how often. Feeds composition; never feeds a verdict

## Attested, not judged

A word here is one that occurs NOT flanked by further kanji, at least
`MIN_ATTEST` times, in a corpus that did not produce the facet. That test
already earned its place in `granularity`, where it separated real coinages
(自動, 定理, 人権) from substrings (事訴 inside 民事訴訟法, 法上 inside
憲法上) and raised the advantage over chance from 4.9x to 15x by dropping
the fragments.

Nothing here decides what a word MEANS, and nothing marks a facet wrong for
failing — 1980アイコ is a perfectly good retrieval key. It is only unfit for
one job, and this layer records which.

## Why the attesting corpus must be named

A vocabulary is a claim about usage, so it inherits the usage it was
measured on. Statutes attest 拘禁刑 and not コンキスタドール; an
encyclopedia attests the reverse. Recording which corpus attested each term
is what stops a vocabulary built from one register being used to judge
another — the same discipline that keeps `placement` from carrying one
domain's demand into a different one.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

#: Occurrences unflanked by further kanji before a facet counts as a word.
#: One is a line break or a typo; three is a usage.
MIN_ATTEST = 3

#: Below and above this, a run is not a lexical item worth composing with.
MIN_LEN, MAX_LEN = 2, 12

_FLANK = "㐀-䶿一-鿿"
_NUMERISH = re.compile(r"[0-9０-９]")


@dataclass
class Vocabulary:
    """Terms attested as free-standing words, and who attested them."""

    #: term -> corpus label -> standalone occurrences
    attested: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def add(self, term: str, corpus: str, n: int) -> None:
        self.attested.setdefault(term, {})[corpus] = n

    def __contains__(self, term: str) -> bool:
        return term in self.attested

    def support(self, term: str) -> int:
        return sum((self.attested.get(term) or {}).values())

    def sources(self, term: str) -> List[str]:
        return sorted(self.attested.get(term) or ())

    def report(self) -> Dict[str, Any]:
        by: Counter = Counter()
        for v in self.attested.values():
            for c in v:
                by[c] += 1
        return {"terms": len(self.attested), "by_corpus": dict(by.most_common())}

    def save(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps(self.attested, ensure_ascii=False, sort_keys=True),
            encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Vocabulary":
        v = cls()
        v.attested = json.loads(Path(path).read_text(encoding="utf-8"))
        return v


def standalone(term: str, text: str) -> int:
    """How often ``term`` appears not flanked by further kanji.

    The flanking test is the whole filter: 事訴 occurs thousands of times
    inside 民事訴訟法 and never on its own.
    """
    return len(re.findall(
        f"(?<![{_FLANK}])" + re.escape(term) + f"(?![{_FLANK}])", text))


#: A maximal run of the characters a Japanese content word is made of.
#: A term "stands alone" exactly when it IS one of these, so counting runs
#: once answers the question for every candidate at the same time.
_RUN = re.compile(r"[㐀-䶿一-鿿ァ-ヺー々〆]+")


def runs(text: str) -> Counter:
    """Maximal content runs and their counts. One pass over the corpus."""
    c: Counter = Counter()
    for m in _RUN.finditer(text or ""):
        c[m.group(0)] += 1
    return c


def attest(
    candidates: Iterable[str],
    corpora: Sequence[Tuple[str, str]],
    *,
    min_attest: int = MIN_ATTEST,
) -> Vocabulary:
    """Which candidates a corpus uses as words. ``corpora`` is (label, text).

    Counts maximal runs once per corpus rather than searching per candidate.
    The first version did the latter — a flanking regex for every candidate
    against every corpus — and did not finish 20,000 candidates against 3MB
    in ten minutes. The two are equivalent by construction: a term is
    unflanked exactly when it is a maximal run.
    """
    vocab = Vocabulary()
    keep = {c for c in candidates
            if c and MIN_LEN <= len(c) <= MAX_LEN and not _NUMERISH.search(c)}
    for label, text in corpora:
        counts = runs(text)
        for term in keep:
            n = counts.get(term, 0)
            if n >= min_attest:
                vocab.add(term, label, n)
    return vocab


def statute_text(paths: Iterable[Path]) -> str:
    """The prose of e-Gov statute XML — <Sentence> bodies, nothing else.

    Needed because a vocabulary built only from encyclopedia prose does not
    grow when statutes are added: 626MB of law raised the facet count 1.4x
    and the vocabulary not at all (12,362 -> 12,348), because nothing was
    attesting legal usage. Adding the statute bodies took it to 35,051.
    場合, 被保険者, 普通地方公共団体 are words the law uses constantly and an
    encyclopedia rarely does.
    """
    import xml.etree.ElementTree as ET

    out: List[str] = []
    for p in paths:
        try:
            root = ET.parse(Path(p)).getroot()
        except Exception:
            continue
        out.append("".join((s.text or "") for s in root.iter("Sentence")))
    return "".join(out)


def from_stores(
    stores: Iterable[Any],
    corpora: Sequence[Tuple[str, str]],
    *,
    min_attest: int = MIN_ATTEST,
    limit: Optional[int] = None,
    include_cores: bool = True,
) -> Vocabulary:
    """Sift a federation's terms into the ones that are words.

    ``corpora`` must attest the register the stores were built from. A
    vocabulary is a claim about usage and cannot judge usage it never saw.

    Cores are candidates as well as facets, because generation asks about a
    core — a walk moves core to core, and every sentence is ABOUT one. Facets
    alone leave that gate half-shut: of 56,310 cores in the 626MB federation,
    38,028 (67.5%) never appear as anyone's facet, so a facet-only vocabulary
    silently refuses to write about two thirds of the subjects a walk can
    reach. The attestation test is unchanged and does the same work either
    way — 0000gallery and 100円 are cores and still not words.
    """
    terms: Counter = Counter()
    for st in stores:
        labels = getattr(st, "source_labels", set()) or set()
        for core, cross in st.crosses.items():
            if include_cores and core not in labels:
                terms[core] += 1
            for f in cross:
                if f not in labels:
                    terms[f] += 1
    ranked = [t for t, _n in terms.most_common(limit)] if limit else list(terms)
    return attest(ranked, corpora, min_attest=min_attest)


def from_cuts(
    docs: Sequence[Tuple[str, str]],
    corpora: Sequence[Tuple[str, str]],
    *,
    sizes: Sequence[int] = (2, 3),
    min_attest: int = MIN_ATTEST,
) -> Vocabulary:
    """Words a WORD-level reader buried inside longer compounds.

    A reader that takes 損害賠償 whole never proposes 賠償, so the vocabulary
    is missing terms the corpus writes constantly. Re-reading the same
    documents at a coarser cut proposes them, and the ordinary attestation
    test decides — nothing is admitted for being splittable.

    This is the only expansion measured to raise quality rather than trade
    it away. Against 20M held-out characters, the share of admitted terms
    that the held-out text also writes standalone three or more times:

        current vocabulary                52%
        MIN_ATTEST lowered from 3 to 1     4%   (小林一三, 各出展)
        morphological variants admitted    2%   (物価統制令第三十八条)
        cores from a 2 or 3 character cut 62%   (北航路, 絶縁物, 放牧地, 借用)

    The first two double the share of path centres that count as words, from
    32% to 64% and 48%, and they do it by calling proper nouns and extraction
    fragments words. This adds 7,537 terms at a HIGHER attestation rate than
    the vocabulary already had.
    """
    from .segmented import ingest_at

    proposed: Set[str] = set()
    for size in sizes:
        store = ingest_at(docs, size)
        labels = getattr(store, "source_labels", set()) or set()
        proposed |= {c for c in store.crosses
                     if c not in labels and MIN_LEN <= len(c) <= MAX_LEN}
    return attest(sorted(proposed), corpora, min_attest=min_attest)


def merge(*vocabs: Vocabulary) -> Vocabulary:
    """One vocabulary from several, keeping every attesting corpus."""
    out = Vocabulary()
    for v in vocabs:
        for term, by in v.attested.items():
            for corpus, n in by.items():
                cur = out.attested.setdefault(term, {})
                cur[corpus] = max(cur.get(corpus, 0), n)
    return out


def filter_terms(
    terms: Iterable[str],
    vocab: Vocabulary,
    *,
    min_support: int = 1,
) -> List[str]:
    """The terms of ``terms`` that are words, best-attested first.

    Order is by attestation then alphabetical, so a caller taking the first
    fill gets the most-used word rather than the alphabetically luckiest —
    which is what put 1980アイコ in a sentence before this existed.
    """
    got = [(vocab.support(t), t) for t in terms if vocab.support(t) >= min_support]
    got.sort(key=lambda st: (-st[0], st[1]))
    return [t for _s, t in got]
