"""Sovereigns in parallel, with nothing above them.

Measured, a single apex is a routing ceiling: one root has six arms and four
faces, so it distinguishes 24 terms and no depth beneath it raises that.
Asked 1,536 anticipated questions it placed 24; the same tree queried at its
twelve field roots in parallel placed 220. A sovereign is good for identity
and governance and bad for routing, because routing capacity is per-root and
one root is one ceiling.

So a constellation has no top. Each sovereign holds the whole corpus at its
own SETTING — a grain size, a knowledge depth, a grammar — and a question
goes to all of them at once. What comes back is not one answer but a census:
how many sovereigns spoke, and how many said the same thing.

    resolution   whole / 3-char / 2-char / 1-char grains
    depth        how many facts per item were indexed at all
    grammar      raw, suffix-stripped, compound-split

Those three were each measured to carry signal on their own. Resolution
graded doubt (unanimity 100%, a lone rung 29.8%); depth did the same (98.1%
against 14.0%); grammar did not, on the ladder, and is kept selectable so
the placement stays a measurement.

## Why this is not the matryoshka again

`matryoshka_consensus` copies the same shell upward and re-searches it —
measured cell-for-cell identical, 6 arms of 6, an identity map. A
constellation's members are not copies. They index the same documents
differently, so they can disagree, and disagreement is the only thing an
agreement signal can be made of.

## Measured at 626MB

Eight sovereigns over the same 5,401 leaves — four resolutions, three
knowledge depths, one alternate grammar — built in 4 seconds, 1,200 probes
answered in 7:

    single sovereign (one 4-rung ladder)    964/1200   80.3%
    constellation (8 in parallel)          1012/1200   84.3%

    agreeing   probes   accuracy
        7          44    100.0%
        6          92    100.0%
        5         191    100.0%
        4         499    100.0%
        3         119     97.5%
        2          88     67.0%
        1         145      7.6%
        0          22        --

Four or more concurring covers 69% of the probes and was right every time.
The staircase the design asked for is that column: not a single verdict with
a hidden confidence, but a count a reader can act on differently at 7 than
at 2.

## What a constellation must never do

Vote a wrong answer into a right one. Members that split are reported split;
the reader is told how many spoke and how many concurred, and a bare
majority is labelled as such. The calibration for those bands belongs to a
corpus and a question shape and has to be rebuilt — see `resolution`.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .resolution import DEFAULT_RUNGS, Ladder


@dataclass
class Sovereign:
    """One whole view of the corpus, at one setting."""

    name: str
    #: The setting that makes this sovereign different from its neighbours.
    setting: Dict[str, Any] = field(default_factory=dict)
    ladder: Optional[Ladder] = None
    #: leaf -> terms, as this sovereign indexed them.
    items: Dict[str, Any] = field(default_factory=dict)

    def build(self, items: Dict[str, Iterable[str]]) -> "Sovereign":
        rungs = self.setting.get("rungs", DEFAULT_RUNGS)
        grammar = self.setting.get("grammar", "raw")
        depth = self.setting.get("depth")
        if depth:
            items = {k: sorted(v)[:depth] for k, v in items.items()}
        self.items = items
        self.ladder = Ladder(rungs=rungs, grammar=grammar).build(items)
        return self

    def vote(self, query_terms: Sequence[str]) -> Optional[str]:
        """This sovereign's single answer, or None if it abstains.

        Abstention is the same rule as a rung's: a sovereign with no single
        leader does not pick. Letting it break the tie would manufacture
        agreement across the constellation for a reason unrelated to
        evidence, which is exactly what the lexicographic tie-break did one
        level down (unanimity 86 probes -> 321, accuracy 73.3% -> 23.7%).
        """
        from .resolution import ask

        if self.ladder is None:
            return None
        r = ask(self.ladder, query_terms)
        return r["item"] if r["verdict"] == "ANSWER" else None

    def report(self) -> Dict[str, Any]:
        return {"name": self.name, "setting": {k: str(v)[:40]
                                               for k, v in self.setting.items()},
                "leaves": len(self.items),
                "grains": sum(len(v) for v in (self.ladder.index.values()
                                               if self.ladder else []))}


@dataclass
class Constellation:
    """Several sovereigns, queried together, with nothing above them."""

    members: List[Sovereign] = field(default_factory=list)

    def report(self) -> Dict[str, Any]:
        return {"sovereigns": len(self.members),
                "members": [m.report() for m in self.members]}

    #: Every term any member indexed, built once. Scanning the leaves per
    #: query term is 5,401 leaves x 7 members x 400 terms per lookup, which
    #: turns a 7-millisecond census into a walk of the whole federation.
    _terms: Optional[Set[str]] = None

    def vocabulary(self) -> Set[str]:
        if self._terms is None:
            t: Set[str] = set()
            for m in self.members:
                for terms in m.items.values():
                    t |= set(terms)
            self._terms = t
        return self._terms

    def add(self, s: Sovereign) -> "Constellation":
        self.members.append(s)
        self._terms = None
        return self

    def indexed(self, term: str) -> bool:
        """Is this term anywhere in any member's index?"""
        return term in self.vocabulary()

    def ask(self, query_terms: Sequence[str]) -> Dict[str, Any]:
        """The census, and what of the question it actually covers.

        Concord counts sovereigns that agree on a LEAF. It does not say the
        question was answered, and the two come apart badly when a query
        mixes a term the federation holds with one it does not: measured
        over 80 such questions, only 3 were refused and 8 reached four or
        more concurring — the band calibrated at 100% — while the answer was
        about the other term entirely. A reader asking about 超伝導 got a
        confident leaf chosen on the word next to it.

        So coverage is reported beside the census and never folded into it.
        `ja_consensus_ask` has refused on unaddressed terms since it was
        written; this path had the same hole and no gate. Uncovered terms do
        not lower the concord — they are a different fact about the answer,
        and a reader who wants the leaf anyway can still have it.
        """
        covered = [t for t in query_terms if self.indexed(t)]
        missing = [t for t in query_terms if t not in covered]
        votes: Dict[str, Optional[str]] = {}
        for m in self.members:
            votes[m.name] = m.vote(query_terms)
        spoke = [v for v in votes.values() if v]
        if not spoke:
            return {"verdict": "UNKNOWN_NOT_PRESENT", "item": None,
                    "spoke": 0, "of": len(self.members), "agreeing": 0,
                    "concord": 0.0, "covered": covered, "missing": missing,
                "coverage": round(len(covered) / max(len(query_terms), 1), 3),
                "votes": votes}
        tally = Counter(spoke)
        top = max(tally.values())
        leaders = sorted(k for k, v in tally.items() if v == top)
        if len(leaders) > 1:
            return {"verdict": "AMBIGUOUS", "item": None, "spoke": len(spoke),
                    "of": len(self.members), "agreeing": top,
                    "concord": round(top / len(spoke), 3),
                    "leaders": leaders[:4], "covered": covered, "missing": missing,
                "coverage": round(len(covered) / max(len(query_terms), 1), 3),
                "votes": votes}
        return {
            "verdict": "ANSWER" if len(tally) == 1 else "MAJORITY",
            "item": leaders[0],
            "spoke": len(spoke), "of": len(self.members),
            "agreeing": top, "concord": round(top / len(spoke), 3),
            "covered": covered, "missing": missing,
                "coverage": round(len(covered) / max(len(query_terms), 1), 3),
                "votes": votes,
        }


#: The staircase: one step per rung of resolution, then one per depth, then
#: the grammars. Each is a setting that was measured to matter on its own.
def staircase(
    items: Dict[str, Iterable[str]],
    *,
    resolutions: Sequence[Tuple[str, int]] = (("whole", 0), ("g3", 3),
                                              ("g2", 2), ("g1", 1)),
    depths: Sequence[int] = (4, 8, 16),
    grammars: Sequence[str] = ("raw",),
) -> Constellation:
    """Build a constellation by varying one setting at a time.

    Deliberately one axis per member rather than the cross product. Sixteen
    sovereigns of every combination would be a bigger census and a worse
    experiment: when they disagree, nothing says which axis did it.
    """
    c = Constellation()
    for name, size in resolutions:
        c.add(Sovereign(name=f"res:{name}",
                        setting={"rungs": ((name, size),)}).build(items))
    for d in depths:
        c.add(Sovereign(name=f"depth:{d}",
                        setting={"depth": d}).build(items))
    for g in grammars:
        if g == "raw":
            continue
        c.add(Sovereign(name=f"gram:{g}",
                        setting={"grammar": g}).build(items))
    return c
