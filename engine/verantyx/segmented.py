"""Sovereigns that were BUILT differently, not indexed differently.

`graded.GradedJudge` holds one store and re-indexes it at several
resolutions. That is not the same structure as this, and the difference is
visible in what becomes a CORE:

    ingested by word    損害賠償 -> 不法行為, 債務不履行
    ingested 2 chars    賠償    -> 損害, 害賠, 不法, 債務, 務不, 履行
    ingested 1 char     償      -> 損, 害, 賠, 不, 法, 債

Japanese is head-final, so the head of the topic phrase is the last thing in
it — and at a coarser cut the last thing is a different string. These are
not three views of one federation; they are three federations that read the
same documents and disagree about what the documents are about. A question
answered the same way by two of them has been answered twice, by structures
that had to arrive at it separately.

## The band is the gate, and majority is not the band

Measured over 400 probes phrased outside the corpus's own word forms, and
15 words the corpus never held, on four sovereigns cut at word / 3 / 2 / 1:

    3 sovereigns answered, 3 agree    82 probes   98.8%
    3 answered, 2 agree               25         100.0%
    2 answered, 2 agree               42         100.0%
    1 answered                        97          97.9%
    answered and split                            0.0%

    out-of-corpus: 6 silent, 8 answered by ONE sovereign, 1 split
                   — none reached two agreeing

Reading that as a majority vote gives 8 wrong answers, because a
one-character sovereign answers almost anything and a majority of one is a
majority. Two sovereigns cut differently agreeing is the signal; a lone
sovereign is a lead.

## What it costs

Building four federations from 5.1M characters took 169 seconds against
about one to re-index a single store, and the coverage at two-or-more
agreeing is roughly a third of what re-indexing answers. This buys
separation, not reach: it is worth paying where a wrong answer costs more
than a refusal, and not otherwise.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: Runs when hiragana counts as content. Japanese writes its grammar in
#: hiragana, so the ordinary reader excludes it and 「こんにちは」 yields no
#: content run at any window size — there is nothing to cut. A greeting is
#: not grammar though, and a cut that includes hiragana reaches it:
#: こんにちは -> こん / んに / にち / ちは.
#:
#: The provenance span is excluded here too. Without it the 2-char cut
#: turned `(reported by policy.docx)` into by / ed / ep / or / po and gave
#: every core in the corpus the same five facets.
_HIRA_RUN = re.compile(r"[ぁ-んァ-ヺー㐀-䶿一-鿿々〆A-Za-z]+")


def hiragana_runs(text: str) -> List[str]:
    """Content runs with hiragana included, provenance still excluded."""
    from .lang import _JA_ATTRIBUTION

    text = text or ""
    skip = [(m.start(), m.end()) for m in _JA_ATTRIBUTION.finditer(text)]
    out: List[str] = []
    for m in _HIRA_RUN.finditer(text):
        if any(a <= m.start() < b for a, b in skip):
            continue
        out.append(m.group(0))
    return out


#: (name, characters per cut). 0 keeps the reader's own word boundaries.
DEFAULT_CUTS: Tuple[Tuple[str, int], ...] = (
    ("語", 0), ("三字", 3), ("二字", 2), ("一字", 1),
)

#: Sovereigns that must agree before an answer is more than a lead. Two,
#: measured: every out-of-corpus word stopped at one.
MIN_AGREE = 2


def cut_runs(runs: Sequence[str], size: int) -> List[str]:
    """Sliding windows of ``size`` over each run, or the runs unchanged."""
    if size <= 0:
        return list(runs)
    out: List[str] = []
    for r in runs:
        if len(r) <= size:
            out.append(r)
        else:
            out += [r[i:i + size] for i in range(len(r) - size + 1)]
    return out


def ingest_at(docs: Sequence[Tuple[str, str]], size: int,
              *, hiragana: bool = False) -> Any:
    """A whole federation, read at one cut.

    The cut is applied inside `lang.ja_content_runs`, so every layer that
    reads a document — topic detection, head selection, polarity — sees the
    cut text. Cutting after ingest would only relabel facets and leave the
    cores where the word-level reader put them, which is the thing this
    exists to avoid.
    """
    from . import lang
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents

    original = lang.ja_content_runs
    base = hiragana_runs if hiragana else original
    if size or hiragana:
        def cut(text: str) -> List[str]:
            return cut_runs(base(text), size)
        lang.ja_content_runs = cut
    try:
        store = CrossStore()
        ingest_documents(store, [Document(source=n, text=t) for n, t in docs])
        return store
    finally:
        lang.ja_content_runs = original


@dataclass
class SegmentedStaircase:
    """One federation per cut, asked together."""

    cuts: Sequence[Tuple[str, int]] = DEFAULT_CUTS
    #: Cut names whose store was built with hiragana as content.
    hiragana_cuts: Sequence[str] = ()
    stores: Dict[str, Any] = field(default_factory=dict)
    judges: Dict[str, Any] = field(default_factory=dict)
    built: Dict[str, Any] = field(default_factory=dict)

    def build(self, docs: Sequence[Tuple[str, str]]) -> "SegmentedStaircase":
        from .graded import GradedJudge

        rec: Dict[str, Any] = {}
        from .lang import ja_content_runs

        for name, size in self.cuts:
            t0 = time.time()
            hira = name in self.hiragana_cuts
            st = ingest_at(docs, size, hiragana=hira)
            self.stores[name] = st
            # The query is cut the way the store was. Without this a
            # hiragana federation holds 「こんにちは」 and cannot be asked
            # for it, because the ordinary reader gives the question no
            # terms at all.
            base = hiragana_runs if hira else ja_content_runs
            read = (lambda tx, _b=base, _s=size: cut_runs(_b(tx), _s))
            self.stores[name] = st
            self.judges[name] = GradedJudge(read=read).build(st)
            rec[name] = {"cores": len(st.crosses),
                         "seconds": round(time.time() - t0, 1)}
        self.built = {"cuts": rec, "documents": len(docs)}
        return self

    def ask(self, query: str, *, min_agree: int = MIN_AGREE) -> Dict[str, Any]:
        """The band, not the majority.

        `AGREED` means at least ``min_agree`` sovereigns cut differently
        arrived at the same item. `LEAD` means one did and the rest were
        silent — measured at 97.9% on in-corpus probes and the only band
        every out-of-corpus word reached, so it is reported and never
        promoted. `SPLIT` means they answered and disagreed, which was 0%
        right and is the one band worth refusing outright.
        """
        votes: Dict[str, Optional[str]] = {}
        for name, j in self.judges.items():
            r = j.ask(query)
            votes[name] = r["item"] if r["verdict"].startswith("ANSWER") else None
        spoke = [v for v in votes.values() if v]
        if not spoke:
            return {"verdict": "UNKNOWN_NOT_PRESENT", "item": None,
                    "answered": 0, "agreeing": 0, "of": len(self.judges),
                    "votes": votes}
        tally = Counter(spoke)
        top = max(tally.values())
        leaders = sorted(k for k, v in tally.items() if v == top)
        item = leaders[0] if len(leaders) == 1 else None
        if item is None:
            verdict = "SPLIT"
        elif top >= min_agree:
            verdict = "AGREED"
        elif len(spoke) > top:
            verdict = "SPLIT"
        else:
            verdict = "LEAD"
        return {
            "verdict": verdict,
            "item": item if verdict != "SPLIT" else None,
            "answered": len(spoke), "agreeing": top,
            "of": len(self.judges), "votes": votes,
            "note": "AGREED means sovereigns built from differently CUT text "
                    "arrived at this separately; LEAD is one sovereign and is "
                    "where every out-of-corpus word landed",
        }

    def report(self) -> Dict[str, Any]:
        return dict(self.built)
