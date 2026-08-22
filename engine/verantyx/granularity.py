"""Composition across granularities — where a closed system stops being closed.

A store at one granularity cannot produce a symbol it does not hold. Measured
over 117 real queries, the search emitted a symbol absent from the initial
shell zero times, and it cannot: faces are filled from the store and the
moves permute faces. That closure is what makes fabrication structurally
impossible, and it is also why the same system cannot generalise — router
accuracy on terms it was never given is 0.0%.

Two stores at DIFFERENT granularities over the same corpus do not share that
limit. A word-level store holds 断水 as an atom. A character-level store over
the same text holds 断 and 水 as atoms and holds their positions — which
character starts a compound, which ends one — and those positions license
combinations the word-level store cannot form.

## The claim is falsifiable, so it was tested that way

Recombining the 120 most common initial characters with the 120 most common
final characters of the legal corpus's two-character words gives 13,967
strings the word-level store does not have. A held-out corpus (2.4M
characters of encyclopedia text, never used to build either store) says
which of them are Japanese:

    present as a substring          1,911   13.7%
    standing alone 3+ times           236    1.7%   <- words, not fragments
    same characters, random pairing    33    0.2%
                                            x7.10

自動 死去 公式 人権 主義 実数 定理 — real words, none of them in the legal
vocabulary that generated them. The gain over random pairing of the SAME
characters is the whole result: what the character-level store contributes
is not the characters, it is where they go.

## Why the strict number is the honest one

13.7% counts 事訴 (inside 民事訴訟法) and 法上 (inside 憲法上) as hits. They
are substrings, not words. Requiring a candidate to appear NOT flanked by
further kanji, three times or more, drops the yield eightfold and raises the
advantage over chance — which is the direction that says the structure is
doing the work rather than the corpus being large.

## What this does and does not license

It proposes. A generated string is a candidate with a frequency in a
held-out corpus attached, and nothing here decides it is a word, still less
what it means. Anything downstream of this must treat the output as a queue
for approval, exactly as `vocab_growth` does — the closure that prevents
fabrication is deliberately broken here, so the gate has to be somewhere.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_KANJI = re.compile(r"^[㐀-䶿一-鿿]+$")

#: How many of each position's most common characters to recombine. The
#: product is the candidate count, so this is the cost knob; 120 x 120 over
#: the reference corpus gave 13,967 candidates in about a second.
TOP_CHARS = 120

#: A candidate must stand alone this many times in the held-out text before
#: it counts as a word. Once is a typo or a line break; three is a usage.
MIN_STANDALONE = 3


@dataclass
class CharModel:
    """Where characters sit inside the words of a corpus.

    Deliberately only positions, not meanings. What a character means is not
    recoverable from where it appears, and pretending otherwise is the
    failure this package keeps refusing.
    """

    initial: Counter = field(default_factory=Counter)
    final: Counter = field(default_factory=Counter)
    anywhere: Counter = field(default_factory=Counter)
    source_words: Set[str] = field(default_factory=set)

    def report(self) -> Dict[str, Any]:
        return {"words": len(self.source_words),
                "distinct_chars": len(self.anywhere),
                "initial_chars": len(self.initial),
                "final_chars": len(self.final)}


def decompose(words: Iterable[str], *, length: int = 2) -> CharModel:
    """Read a word-level vocabulary one character at a time."""
    m = CharModel()
    for w in words:
        w = (w or "").strip()
        if not w or not _KANJI.match(w):
            continue
        m.source_words.add(w)
        m.anywhere.update(w)
        if len(w) == length:
            m.initial[w[0]] += 1
            m.final[w[-1]] += 1
    return m


def propose(
    model: CharModel,
    *,
    top: int = TOP_CHARS,
    exclude: Optional[Set[str]] = None,
) -> List[str]:
    """Strings the character model licenses and the word model does not hold.

    Sorted by the product of the two positional counts, so the most
    structurally supported come first and a caller taking a prefix gets the
    best of them rather than an alphabetical slice.
    """
    known = set(model.source_words) | set(exclude or ())
    heads = model.initial.most_common(top)
    tails = model.final.most_common(top)
    scored: List[Tuple[int, str]] = []
    for h, hc in heads:
        for t, tc in tails:
            w = h + t
            if w in known:
                continue
            scored.append((-(hc * tc), w))
    scored.sort()
    return [w for _s, w in scored]


# ---------------------------------------------------------------------------
# Longer words are composed of UNITS, not of characters
# ---------------------------------------------------------------------------

#: How a word of length n is cut. Japanese compounds are morphemic, not
#: positional: 公務員 is 公務+員 and 再開発 is 再+開発, so a three-character
#: proposal is a two-character word beside a one-character affix — never
#: three characters chosen by position, which would propose 公再員.
SPLITS: Dict[int, Tuple[Tuple[int, int], ...]] = {
    2: ((1, 1),),
    3: ((2, 1), (1, 2)),
    4: ((2, 2), (3, 1), (1, 3)),
    5: ((3, 2), (2, 3)),
}


@dataclass
class UnitModel:
    """Which units of each length open and close the words of a corpus.

    A superset of CharModel: at (1,1) the units are characters and this is
    the same model. The reason to generalise is that the productive layer of
    Japanese compounding is the morpheme — 損害 + 賠償, 行政 + 処分 — and a
    character-position model cannot see it.
    """

    #: (part length, position) -> unit -> count, position in {"L", "R"}
    slots: Dict[Tuple[int, str], Counter] = field(default_factory=dict)
    units: Dict[int, Set[str]] = field(default_factory=dict)
    source_words: Set[str] = field(default_factory=set)

    def _slot(self, size: int, side: str) -> Counter:
        return self.slots.setdefault((size, side), Counter())

    def report(self) -> Dict[str, Any]:
        return {
            "words": len(self.source_words),
            "units_by_length": {k: len(v) for k, v in sorted(self.units.items())},
            "slots": {f"{k[0]}{k[1]}": len(v) for k, v in sorted(self.slots.items())},
        }


def decompose_units(
    words: Iterable[str], *, lengths: Sequence[int] = (2, 3, 4),
) -> UnitModel:
    """Read a vocabulary as units in left and right positions.

    A unit is only counted as such when the WHOLE word it came from is in
    the vocabulary, so 賠償 earns its right-hand slot from 損害賠償 rather
    than from any string that happens to end in those characters.
    """
    m = UnitModel()
    kept = [w.strip() for w in words if w and _KANJI.match(w.strip())]
    m.source_words = set(kept)
    for w in kept:
        m.units.setdefault(len(w), set()).add(w)
    for w in kept:
        for a, b in SPLITS.get(len(w), ()):
            m._slot(a, "L")[w[:a]] += 1
            m._slot(b, "R")[w[a:]] += 1
    return m


def propose_units(
    model: UnitModel,
    *,
    length: int = 3,
    top: int = 60,
    exclude: Optional[Set[str]] = None,
) -> List[str]:
    """Compositions of ``length`` the vocabulary does not already hold.

    Every split of that length is tried and the results merged, so a
    three-character proposal may be 2+1 or 1+2 and a reader cannot tell
    which — nor should they, since both are ordinary Japanese.
    """
    known = set(model.source_words) | set(exclude or ())
    scored: Dict[str, int] = {}
    for a, b in SPLITS.get(length, ()):
        left = model.slots.get((a, "L"), Counter()).most_common(top)
        right = model.slots.get((b, "R"), Counter()).most_common(top)
        for l, lc in left:
            for r, rc in right:
                w = l + r
                if len(w) != length or w in known:
                    continue
                scored[w] = max(scored.get(w, 0), lc * rc)
    return [w for w, _s in sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))]


def control_units(
    model: UnitModel,
    n: int,
    *,
    length: int = 3,
    seed: int = 0,
    exclude: Optional[Set[str]] = None,
) -> List[str]:
    """The same units, paired at random. The number a proposal must beat."""
    import random

    rng = random.Random(seed)
    known = set(model.source_words) | set(exclude or ())
    pools: List[Tuple[List[str], List[str]]] = []
    for a, b in SPLITS.get(length, ()):
        L = sorted(model.slots.get((a, "L"), Counter()))
        R = sorted(model.slots.get((b, "R"), Counter()))
        if L and R:
            pools.append((L, R))
    if not pools:
        return []
    out: Set[str] = set()
    for _ in range(n * 8):
        L, R = pools[rng.randrange(len(pools))]
        w = rng.choice(L) + rng.choice(R)
        if len(w) == length and w not in known:
            out.add(w)
        if len(out) >= n:
            break
    return sorted(out)


def discover_units(
    words: Iterable[str],
    held_out: str,
    *,
    length: int = 3,
    top: int = 60,
    min_standalone: int = MIN_STANDALONE,
) -> Dict[str, Any]:
    """Compose at ``length``, verify against held-out text, report the lift."""
    model = decompose_units(words)
    proposals = propose_units(model, length=length, top=top)
    got = verify(proposals, held_out, min_standalone=min_standalone)
    ctl = verify(control_units(model, len(proposals), length=length),
                 held_out, min_standalone=min_standalone)
    lift = (got["word_rate"] / ctl["word_rate"]) if ctl["word_rate"] else None
    return {
        "length": length,
        "model": model.report(),
        "proposed": got,
        "control": ctl,
        "lift_over_chance": round(lift, 2) if lift else None,
        "verdict": "ANSWER" if lift and lift > 1.0 else "UNKNOWN_NO_ADVANTAGE",
    }


def standalone_count(word: str, text: str) -> int:
    """How often ``word`` appears not flanked by further kanji.

    The flanking test is what separates a word from a fragment: 事訴 occurs
    2,000 times inside 民事訴訟法 and never on its own.
    """
    pat = re.compile(r"(?<![㐀-䶿一-鿿])" + re.escape(word) + r"(?![㐀-䶿一-鿿])")
    return len(pat.findall(text))


def verify(
    candidates: Sequence[str],
    held_out: str,
    *,
    min_standalone: int = MIN_STANDALONE,
) -> Dict[str, Any]:
    """Which proposals a corpus that built neither model says are words.

    Returns the loose count as well as the strict one, because the gap
    between them IS the fragment problem and hiding it would make the yield
    look eight times better than it is.
    """
    substring = [w for w in candidates if w in held_out]
    words: List[Tuple[str, int]] = []
    for w in substring:
        n = standalone_count(w, held_out)
        if n >= min_standalone:
            words.append((w, n))
    words.sort(key=lambda wn: (-wn[1], wn[0]))
    n = max(1, len(candidates))
    return {
        "candidates": len(candidates),
        "substring_hits": len(substring),
        "substring_rate": round(len(substring) / n, 4),
        "words": len(words),
        "word_rate": round(len(words) / n, 4),
        "top": words[:40],
    }


def control(
    model: CharModel,
    n: int,
    *,
    seed: int = 0,
    exclude: Optional[Set[str]] = None,
) -> List[str]:
    """The same characters, paired at random. The number to beat.

    Without this, a yield of 1.7% could be a fact about how many
    two-character kanji strings happen to be Japanese, rather than about the
    structure. It is 0.2%.
    """
    import random

    rng = random.Random(seed)
    chars = sorted(model.anywhere)
    known = set(model.source_words) | set(exclude or ())
    out: Set[str] = set()
    for _ in range(n * 2):
        w = rng.choice(chars) + rng.choice(chars)
        if w not in known:
            out.add(w)
        if len(out) >= n:
            break
    return sorted(out)


def discover(
    words: Iterable[str],
    held_out: str,
    *,
    top: int = TOP_CHARS,
    min_standalone: int = MIN_STANDALONE,
) -> Dict[str, Any]:
    """The whole procedure, with its control, in one call.

    The advantage over the control is the finding; the raw yield is not.
    """
    model = decompose(words)
    proposals = propose(model, top=top)
    got = verify(proposals, held_out, min_standalone=min_standalone)
    ctl = verify(control(model, len(proposals)), held_out,
                 min_standalone=min_standalone)
    lift = (got["word_rate"] / ctl["word_rate"]) if ctl["word_rate"] else None
    return {
        "model": model.report(),
        "proposed": got,
        "control": ctl,
        "lift_over_chance": round(lift, 2) if lift else None,
        "verdict": "ANSWER" if lift and lift > 1.0 else "UNKNOWN_NO_ADVANTAGE",
    }
