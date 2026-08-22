"""A ladder of resolutions over one corpus — agreement as calibrated doubt.

The same text read at several grain sizes gives several readings, and how
many of them agree is a confidence signal that no single reading carries.
Measured on 10,222 statute articles, asked by their own captions, 600
probes:

    best single rung (g2), answering everything      29.8%

    four rungs answer, all agree      39 probes         100.0%
    three rungs answer, all agree     38                100.0%
    one rung answers alone            36                 75.0%
    two rungs answer, both agree     103                 31.1%
    no rung had grounds              383                  --

Unanimity among three or four rungs was right every time, and 64% of the
probes got no answer at all. That is the trade this makes: a deterministic
system cannot report a probability, but it can report how much of its own
structure concurred, and refuse when the answer would rest on nothing.

## Ties are ABSTENTIONS, and getting that wrong twice is the story

Breaking ties by insertion order made a rung's answer depend on which
article was ingested first. Breaking them lexicographically instead was
WORSE, and the measurement says so plainly: every tied rung then chose the
same smallest item, unanimity rose from 86 probes to 321 and its accuracy
fell from 73.3% to 23.7% — below the three-to-one majority. Determinism at
the tie manufactures agreement, because the rungs concur for a reason that
has nothing to do with evidence.

A rung with no single leader abstains. Unanimity then means what it says:
every rung that had grounds said the same thing.

## The rungs must be NESTED, not partitioned

The first attempt binned each term by its length: one-character terms to q1,
two to q2, and so on. That is a partition — a term lands in exactly one
rung, so no two rungs ever see it, and 507 of 600 probes had a single rung
answer at all. Agreement was not low; it was impossible.

A rung is a GRAIN SIZE applied to every term. 損害賠償 is one item at the
word rung, 損害/害賠/賠償 at the two-character rung, and four items at the
character rung. Every rung sees every term, at its own resolution — which is
what the quantisation analogy actually means.

## What it does not do

It does not make a wrong answer right. The ladder reranks nothing: each rung
votes with what it indexed, and the report says how much they concurred. An
answer all four rungs agree on is still wrong a quarter of the time here,
and the number is printed rather than rounded away.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

#: Grain sizes, coarse to fine. 0 means "the whole term, uncut".
DEFAULT_RUNGS: Tuple[Tuple[str, int], ...] = (
    ("whole", 0), ("g3", 3), ("g2", 2), ("g1", 1),
)


def grains(term: str, size: int) -> List[str]:
    """One term seen at one grain size.

    Sliding, not chunked: 損害賠償 at size 2 gives 損害/害賠/賠償, so a
    boundary the corpus draws differently is still covered. Chunking would
    make the rung sensitive to where a compound happens to start.
    """
    t = term or ""
    if size <= 0 or len(t) <= size:
        return [t] if t else []
    return [t[i:i + size] for i in range(len(t) - size + 1)]


@dataclass
class Ladder:
    """rung -> grain -> the items that contain it."""

    rungs: Tuple[Tuple[str, int], ...] = DEFAULT_RUNGS
    #: How terms are cut before any rung sees them — the third axis.
    grammar: str = "raw"
    index: Dict[str, Dict[str, Set[str]]] = field(default_factory=dict)

    def build(self, items: Dict[str, Iterable[str]]) -> "Ladder":
        """``items`` maps an id (an article, a leaf) to the terms it holds."""
        self.index = {name: defaultdict(set) for name, _ in self.rungs}
        for item, terms in items.items():
            for term in terms:
                for cut in recut(term, self.grammar):
                    for name, size in self.rungs:
                        for g in grains(cut, size):
                            self.index[name][g].add(item)
        return self

    def report(self) -> Dict[str, Any]:
        return {"rungs": [n for n, _ in self.rungs],
                "grains_per_rung": {n: len(self.index.get(n, {}))
                                    for n, _ in self.rungs}}

    def vote(self, query_terms: Sequence[str]) -> Dict[str, Optional[str]]:
        """Each rung's own best item for this query, or None if it has none."""
        out: Dict[str, Optional[str]] = {}
        cut_query = [c for t in query_terms for c in recut(t, self.grammar)]
        for name, size in self.rungs:
            score: Counter = Counter()
            for term in cut_query:
                for g in grains(term, size):
                    for item in self.index.get(name, {}).get(g, ()):
                        score[item] += 1
            # A tied rung ABSTAINS. It does not pick.
            #
            # most_common breaks ties by insertion order, so which article
            # was ingested first decided what a rung said. Breaking them
            # lexicographically instead was worse: every tied rung then
            # chose the same smallest item, unanimity rose from 86 probes to
            # 321 and its accuracy fell from 73.3% to 23.7% — below the 3-1
            # majority. Determinism at the tie MANUFACTURES agreement,
            # because the rungs concur for a reason unrelated to evidence.
            #
            # Abstaining keeps unanimity meaning what it claims: every rung
            # that had grounds said the same thing.
            if not score:
                out[name] = None
                continue
            best = max(score.values())
            leaders = [k for k, v in score.items() if v == best]
            out[name] = leaders[0] if len(leaders) == 1 else None
        return out


def ask(ladder: Ladder, query_terms: Sequence[str]) -> Dict[str, Any]:
    """The ladder's answer, with how much of it concurred.

    ``concord`` is answered-and-agreeing over answered — the fraction of
    rungs that could speak and said the same thing. It is a measurement of
    this structure, not a probability of being right, and the two are only
    related by the calibration table in the module docstring.
    """
    votes = ladder.vote(query_terms)
    answered = [v for v in votes.values() if v]
    if not answered:
        return {"verdict": "UNKNOWN_NOT_PRESENT", "item": None,
                "votes": votes, "answered": 0, "distinct": 0,
                "majority": 0, "concord": 0.0}
    tally = Counter(answered)
    # Ties are broken lexicographically, not by insertion order. Counter's
    # most_common keeps first-seen order among equal counts, so simply
    # reordering the rungs changed the answer on every split vote — the same
    # arbitrary tie-break that placement was measured to fabricate through.
    top = max(tally.values())
    item = sorted(k for k, v in tally.items() if v == top)[0]
    return {
        # A 2-2 split has no majority at all, and calling it AMBIGUOUS
        # separates it from 3-1, which does. Reporting only `distinct`
        # merged the two and hid that the tie-break was deciding.
        "verdict": "ANSWER" if len(tally) == 1 else
                   ("MAJORITY" if top * 2 > len(answered) else "AMBIGUOUS"),
        "item": item,
        "votes": votes,
        "answered": len(answered),
        "distinct": len(tally),
        "majority": top,
        "concord": round(top / len(answered), 3),
    }


#: The third axis: how a term is CUT before it is indexed at all. Grain size
#: and knowledge depth both take the vocabulary as given; this one changes
#: what counts as a term.
#:
#:   raw       the term as the reader produced it
#:   nosuffix  nominal suffixes stripped (傷害罪 -> 傷害), per ja_morph
#:   heads     the head half of an even kanji compound (建築確認 -> 確認)
#:   both      stripped and split
#:
#: These are grammatical claims, not string tricks, which is why the list is
#: the same short closed one `ja_morph` defends: a suffix that changes
#: reference (未遂, 準) is absent, because 殺人 and 殺人未遂 are different
#: things and merging them would be a fabrication with a grammar excuse.
#:
#: NEUTRAL ON PROBES THAT USE THE CORPUS'S OWN WORD FORMS, AND NOT
#: OTHERWISE. Over 500 multi-term probes on 1,098 leaves every grammar
#: answered at 100% and the recut ones answered LESS often — raw 431,
#: nosuffix 428, heads 421, both 417 — because a probe drawn from the corpus
#: already spells things the way the corpus does and there is no mismatch to
#: repair. That is a fact about the probe, not about the axis, and reading
#: it as "the grammar axis belongs to retrieval, not to the ladder" was
#: reading it too widely.
#:
#: Measured again on 400 probes whose form DIFFERS from the stored one —
#: 傷害罪 asked of a corpus that wrote 傷害 — against the same three grain
#: settings with and without the three grammars:
#:
#:     corpus's own forms   400/400 answered  ->  400/400   (no change)
#:     mismatched forms     290/400 answered  ->  359/400
#:
#: 69 more answers at 100% precision either way. Coverage 72.5% to 89.8%,
#: nothing lost. It also carries the retrieval fallback in `gather` on
#: questions phrased from outside, where it took recall from 26.7% to 73.3%
#: — the same effect, arrived at from the other side.
#:
#: So the axis earns its place wherever the asker's spelling is not the
#: corpus's, which is every real question and no probe built by sampling
#: the corpus. It stays selectable rather than default because which
#: grammars a corpus needs is a measurement.
GRAMMARS: Tuple[str, ...] = ("raw", "nosuffix", "heads", "both")


def recut(term: str, grammar: str = "raw") -> List[str]:
    """One term under one grammatical treatment."""
    if grammar == "raw":
        return [term]
    from .ja_morph import variants

    if grammar == "nosuffix":
        return variants(term, add=False, split=False)
    if grammar == "heads":
        return variants(term, add=False, split=True)[:1] + [
            v for v in variants(term, add=False, split=True)[1:]
            if len(v) * 2 == len(term)]
    if grammar == "both":
        return variants(term, add=False, split=True)
    raise ValueError(f"unknown grammar {grammar!r}; expected {GRAMMARS}")


@dataclass
class Stack:
    """Several ladders side by side — more rungs, finer grading.

    A ladder varies ONE thing (grain size). A stack varies a second (how much
    of each item was indexed), and the product is what gives the confidence
    scale its resolution. Measured on the same 600 probes:

        4 rungs (grain only)     100% band 77 probes, then 75%, then 31%
        16 rungs (grain x depth) 100% band 80,  then 88.6%, 71.4%, 28.8%

    The extra bands are the point. With four rungs a question is either
    unanimous or nearly worthless; with sixteen there is a middle — and a
    strong majority of many rungs (9 of 12, 12 of 16) was right every time,
    which four rungs cannot express at all.

    Coverage improves too: 354 probes with nothing to say instead of 383,
    because a depth one ladder never indexed can still have grounds.
    """

    ladders: Dict[str, Ladder] = field(default_factory=dict)

    def vote(self, query_terms: Sequence[str]) -> Dict[str, Optional[str]]:
        out: Dict[str, Optional[str]] = {}
        for name, lad in self.ladders.items():
            for rung, item in lad.vote(query_terms).items():
                out[f"{name}/{rung}"] = item
        return out

    def report(self) -> Dict[str, Any]:
        return {"ladders": sorted(self.ladders),
                "rungs": sum(len(l.rungs) for l in self.ladders.values())}


def ask_stack(stack: Stack, query_terms: Sequence[str]) -> Dict[str, Any]:
    """Same contract as `ask`, over every rung of every ladder."""
    votes = stack.vote(query_terms)
    answered = [v for v in votes.values() if v]
    if not answered:
        return {"verdict": "UNKNOWN_NOT_PRESENT", "item": None,
                "answered": 0, "distinct": 0, "majority": 0, "concord": 0.0,
                "rungs": len(votes)}
    tally = Counter(answered)
    top = max(tally.values())
    leaders = sorted(k for k, v in tally.items() if v == top)
    if len(leaders) > 1:
        # The stack ties for the same reason a rung does, and answers the
        # same way: it does not pick.
        return {"verdict": "AMBIGUOUS", "item": None, "answered": len(answered),
                "distinct": len(tally), "majority": top,
                "concord": round(top / len(answered), 3),
                "rungs": len(votes), "leaders": leaders[:4]}
    return {
        "verdict": "ANSWER" if len(tally) == 1 else "MAJORITY",
        "item": leaders[0],
        "answered": len(answered),
        "distinct": len(tally),
        "majority": top,
        "concord": round(top / len(answered), 3),
        "rungs": len(votes),
    }


def calibrate(
    ladder: Ladder,
    probes: Sequence[Tuple[str, Sequence[str]]],
    *,
    group_of: Optional[Any] = None,
) -> Dict[str, Any]:
    """Group probes by how the rungs split, and report accuracy per group.

    ``group_of(item)`` optionally adds a second axis — a field, a source, a
    document type — because the bands are not a constant and the useful
    question is usually "does this mean the same thing over here".

    Measured across a 1,098-leaf federation, asked with three mid-frequency
    terms per leaf, 900 probes: whenever the ladder ANSWERED it was right,
    in every field and at every band. 130 probes abstained. So in that
    setting `concord` is not a graded confidence — it is a certificate with
    an abstention, and what varies by field is how often it can be issued:

        数学 医療 経済 工学    abstain  4-8%    articles on distinct topics
        防災 民事 労働         abstain 22-25%
        刑事 情報 知財         abstain 29-43%   chapters sharing vocabulary

    Asked instead by their captions, the same articles gave a graded scale
    (100% / 31% / abstain). The bands therefore belong to a corpus AND a
    question shape, and neither transfers without being rebuilt.
    """
    buckets: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    groups: Dict[str, Dict[str, List[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0]))
    for want, terms in probes:
        r = ask(ladder, terms)
        key = ("none answered" if not r["answered"] else
               f"{r['answered']}答 / 最大派{r['majority']} [{r['verdict'][:8]}]")
        ok = int(r["item"] == want) if r["answered"] else 0
        buckets[key][0] += 1
        buckets[key][1] += ok
        if group_of is not None:
            g = str(group_of(want))
            groups[g][key][0] += 1
            groups[g][key][1] += ok

    def table(b: Dict[str, List[int]]) -> Dict[str, Any]:
        return {k: {"n": v[0], "correct": v[1],
                    "accuracy": round(v[1] / v[0], 4) if v[0] else 0.0}
                for k, v in sorted(b.items())}

    out: Dict[str, Any] = {"probes": len(probes), "buckets": table(buckets)}
    if group_of is not None:
        out["by_group"] = {
            g: {"probes": sum(v[0] for v in tab.values()),
                "answered_rate": round(
                    1 - (tab.get("none answered", [0, 0])[0]
                         / max(1, sum(v[0] for v in tab.values()))), 4),
                "buckets": table(tab)}
            for g, tab in sorted(groups.items())}
    return out
