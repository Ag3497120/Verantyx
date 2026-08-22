"""Inference by intersection, which is the half of the early idea that lives.

Two things were conflated under "the structure reasons":

    chaining      A -> B -> C, following facet edges
    intersection  A and B and C, narrowing a candidate set

Only the second works, and the difference is not a matter of degree.
Composing two facet edges does not compose two implications — an edge
records that two things were written near each other — and a chain measured
on the 626MB federation decays from 41.5% context retention at one step to
19.3% at five, nineteen times chance and less than half its own start.

Intersection does not decay, because each constraint is evaluated against
the same store rather than against the previous answer. Measured over 300
subjects, giving one true facet at a time:

    constraints   median candidates   holds the answer   unique
        1              93                  100.0%          6.0%
        2               9                  100.0%         22.0%
        3               3                  100.0%         37.0%
        4               1                  100.0%         60.7%
        5               1                  100.0%         63.7%

Ninety-three candidates to one, and the answer is never dropped. That is
what a puzzle is: not a chain of deductions but a set of conditions that
between them leave one thing standing.

## Monotone, so there is no relaxation to run

Each constraint can only remove candidates, never add them, so the descent
has no local minimum to escape and needs no annealing, no temperature and
no weights. `narrow` is the whole dynamic. What the early sketch called an
energy change is a strictly decreasing set size, and its floor is reached
when the conditions run out — not when a search gives up.

## A node is a filter, not an ALU

One cross holds 24 terms and answers "is this among them". Composed, those
are conjunctions over the same store. That is real computation and it is
set intersection, so the ceiling is what conditions a reader can supply —
the structure cannot invent a fourth condition to disambiguate the three it
was given, and `UNKNOWN_UNDERDETERMINED` says so rather than picking.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


@dataclass
class Puzzle:
    """A candidate set and the conditions that narrowed it."""

    store: Any
    candidates: Optional[Set[str]] = None
    used: List[str] = field(default_factory=list)
    trail: List[Tuple[str, int]] = field(default_factory=list)

    def _holders(self, term: str) -> Set[str]:
        labels = getattr(self.store, "source_labels", set()) or set()
        out = {c for c, cross in self.store.crosses.items()
               if c not in labels and term in (cross or ())}
        if term in self.store.crosses and term not in labels:
            out.add(term)
        return out

    def narrow(self, *terms: str) -> "Puzzle":
        """Add conditions. Candidates can only shrink."""
        for t in terms:
            got = self._holders(t)
            self.candidates = got if self.candidates is None else (self.candidates & got)
            self.used.append(t)
            self.trail.append((t, len(self.candidates)))
        return self

    def answer(self) -> Dict[str, Any]:
        """One survivor is an answer; several are a narrowing; none is a
        contradiction among the conditions, which is its own finding."""
        cand = self.candidates
        if cand is None:
            return {"verdict": "UNKNOWN_NO_CONDITIONS", "conditions": []}
        if not cand:
            return {
                # Not "I could not find it". The conditions given cannot all
                # hold at once in this store, which is information about the
                # question rather than about the corpus's coverage.
                "verdict": "UNKNOWN_CONDITIONS_CONFLICT",
                "conditions": list(self.used), "trail": self.trail,
                "note": "no core satisfies all of these together",
            }
        if len(cand) == 1:
            return {"verdict": "ANSWER", "item": next(iter(cand)),
                    "conditions": list(self.used), "trail": self.trail}
        return {
            "verdict": "UNKNOWN_UNDERDETERMINED",
            "candidates": sorted(cand)[:12], "remaining": len(cand),
            "conditions": list(self.used), "trail": self.trail,
            "note": "these conditions leave more than one standing; the "
                    "structure cannot invent another to choose between them",
        }


def solve(store: Any, conditions: Sequence[str]) -> Dict[str, Any]:
    """Narrow by every condition and report what is left."""
    return Puzzle(store=store).narrow(*conditions).answer()


def eliminate(store: Any, among: Sequence[str], condition: str) -> Dict[str, Any]:
    """Which of these candidates the condition rules out.

    The other half of a puzzle. `covenant.siblings` supplies the set —
    terms that occupy the same slot — and one true condition removes the
    ones that do not hold it. Measured on sibling sets of three or more, one
    condition shrank the set every time.
    """
    labels = getattr(store, "source_labels", set()) or set()
    keep, drop = [], []
    for w in among:
        cross = {f for f in (store.crosses.get(w) or ()) if f not in labels}
        (keep if condition in cross else drop).append(w)
    return {"verdict": "ANSWER" if drop else "UNKNOWN_NOTHING_RULED_OUT",
            "condition": condition, "kept": keep, "ruled_out": drop}
