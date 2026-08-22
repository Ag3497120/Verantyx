"""The mouth. Typed refusals already hold the candidates — this returns them.

Every stopping point this project produces is already the right shape for
a question, and none of them could be asked:

    AMBIGUOUS_ON_SCREEN      「課題」 at two places, both located
    UNKNOWN_APP_NOT_PRESENT  「ブラウザ」 is a category, and the machine
                             holds safari / chrome / firefox
    BLOCKED                  a chain that needs something from outside
    UNKNOWN_PARTIAL_COVERAGE tabs read, tabs not read, both named

In each case the refusal is holding a short, closed list of exactly the
thing the person could settle in one word. Circulating harder produces
nothing — which browser they meant is not derivable from anything on this
machine — so more inference is the wrong direction and asking is the whole
remaining capability.

Why the answer is stored differently from a finding
---------------------------------------------------
A person's answer is testimony, not measurement. It lands on support+
sourced to `human`, never merged into what a run established, so the store
keeps its one indispensable property: being able to say which half an
answer stands on. 「あります」 from a survey, 「効きました」 from a
witness, 「これです」 from the person — three different claims, never one.

An answer off the list is allowed and marked as such. People know things
the machine has not surveyed; silently rejecting them would teach the
person that the question was rhetorical.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Refusals that carry a candidate list and are therefore askable. A
#: refusal outside this set is not a question — it is a gap that no answer
#: from the person would close, and dressing it as a question wastes them.
ASKABLE = {
    "AMBIGUOUS_ON_SCREEN": "画面のどこを指しているか",
    "AMBIGUOUS_APP": "どのアプリか",
    "UNKNOWN_APP_NOT_PRESENT": "どれを指しているか",
    "AMBIGUOUS_READING": "どちらの読みが正しいか",
    "UNKNOWN_PARTIAL_COVERAGE": "残りも見るか",
    "BLOCKED": "次に何をすべきか",
}


@dataclass(frozen=True)
class Question:
    """One thing only the person knows, with what is already known beside it."""

    subject: str
    verdict: str
    asks: str
    candidates: Tuple[str, ...] = ()
    #: What the machine DID establish. Shown with the question so the
    #: person is not asked to re-supply what is already known.
    known: Tuple[str, ...] = ()

    @property
    def askable(self) -> bool:
        return self.verdict in ASKABLE

    def render(self) -> str:
        lines = ["%s — %s" % (self.subject, self.asks)]
        for i, c in enumerate(self.candidates, 1):
            lines.append("  %d) %s" % (i, c))
        if not self.candidates:
            lines.append("  (候補なし — 自由に答えてください)")
        if self.known:
            lines.append("  既知: " + " / ".join(self.known))
        return "\n".join(lines)

    def as_dict(self) -> Dict[str, Any]:
        return {"subject": self.subject, "verdict": self.verdict,
                "asks": self.asks, "candidates": list(self.candidates),
                "known": list(self.known), "askable": self.askable}


def question(subject: str, verdict: str,
             candidates: Sequence[str] = (),
             known: Sequence[str] = ()) -> Optional[Question]:
    """A refusal as a question, or None when nothing may be asked.

    Returning None is not a failure to phrase something. It means the
    person cannot settle this — UNKNOWN_CAPTURE_EMPTY is not answerable by
    a human choosing from a list, it is answerable by fixing a permission
    — and asking anyway would train them to ignore the questions that
    matter.
    """
    v = (verdict or "").strip()
    if v not in ASKABLE:
        return None
    return Question(subject=subject.strip(), verdict=v, asks=ASKABLE[v],
                    candidates=tuple(str(c) for c in candidates if str(c).strip()),
                    known=tuple(str(k) for k in known if str(k).strip()))


CHOSE = "chose"
SUPPLIED = "supplied"


@dataclass(frozen=True)
class Answer:
    """What the person said, and which kind of saying it was."""

    question: Question
    value: str
    kind: str                     # CHOSE | SUPPLIED

    def facets(self) -> List[str]:
        # support+ because a person vouching for something IS support —
        # and `human` in the source so it never passes as a measurement.
        return ["support+:human:%s" % self.value[:100],
                "answered:%s" % self.question.verdict,
                "answer_kind:%s" % self.kind]


def resolve(q: Question, said: str) -> Dict[str, Any]:
    """Take the person's answer. Accepts off-list answers, marked.

    An index ("2") or an exact candidate both count as CHOSE. Anything
    else is SUPPLIED: legitimate, kept, and distinguishable forever —
    because "the person picked one of the three I found" and "the person
    told me about a fourth" are different facts about how much of the
    world this machine has surveyed.
    """
    s = (said or "").strip()
    if not s:
        return {"verdict": "UNKNOWN_NO_ANSWER", "question": q.as_dict()}

    if s.isdigit() and q.candidates:
        i = int(s)
        if 1 <= i <= len(q.candidates):
            a = Answer(q, q.candidates[i - 1], CHOSE)
            return {"verdict": "ANSWER", "value": a.value, "kind": a.kind,
                    "facets": a.facets()}
        return {"verdict": "UNKNOWN_CHOICE_OUT_OF_RANGE",
                "given": s, "candidates": list(q.candidates)}

    for c in q.candidates:
        if s.casefold() == c.casefold():
            a = Answer(q, c, CHOSE)
            return {"verdict": "ANSWER", "value": a.value, "kind": a.kind,
                    "facets": a.facets()}

    a = Answer(q, s, SUPPLIED)
    return {"verdict": "ANSWER", "value": a.value, "kind": a.kind,
            "facets": a.facets(),
            "note": "候補外。機械が見ていないものを人が知っていた、として記録"}


def from_circulation(circ, subject: str = "") -> Optional[Question]:
    """A blocked chain as a question about what to do next.

    The candidates are the stages that have not run, because "which of
    these should happen" is something the person can answer and the chain
    cannot.
    """
    st = circ.state()
    if st["status"] != "BLOCKED":
        return None
    pending = ["%d) %s %s" % (s["n"], s["op"], s["args"])
               for s in st["stages"] if not s["delivered"]]
    done = ["%s" % s["op"] for s in st["stages"] if s["delivered"]]
    return question(subject or "この指示", "BLOCKED", pending, done)
