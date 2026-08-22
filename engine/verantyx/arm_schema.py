"""The three dualities — every claim gets the same six questions.

x: support / oppose      what backs it, what fights it
y: cause / effect        what produces it, what it produces
z: general / instance    what it abstracts to, what exemplifies it

Facts are assigned to arms by DETERMINISTIC surface cues (because → cause,
is-a → instance, ...), and a fact without a cue simply has no arm — untagged
is a first-class state, not an error, because a fuzzy tagger that guesses
arms would poison the very gate this exists to power.

Two things fall out of the assignment:

  1. An intent gate. "why does X ..." is a question about the cause arm; a
     core whose cause arm is empty must answer UNKNOWN_NO_CAUSE_RECORDED —
     "I know the thing, I do not know its why" — instead of stitching
     together whatever facets it does have. This attacks the measured
     over-answering weakness (answer_rate 1.0 vs defensible 0.167 on facet
     queries) with a stronger constraint than word coverage: the right KIND
     of knowledge must exist, not just overlapping words.

  2. A completeness checklist. The six arms are six questions every claim
     should eventually answer; an empty arm is a typed, targetable gap
     (empty instance arm = untestable; empty support arm = unverified),
     ready to feed growth signals with a WHAT-IS-MISSING attached.

Kept as a parallel index rather than a CrossStore change: arm knowledge is
an interpretation layered on facts, and interpretations should be droppable
without touching the facts they interpret.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ARMS = ("support+", "support-", "cause+", "cause-", "kind+", "kind-")

#: Surface cue → arm. Order matters (first hit wins); cues are chosen to be
#: nearly unambiguous in declarative sentences, and everything else stays
#: untagged on purpose.
_CUES = [
    ("cause+", re.compile(r"\b(because of|because|due to|caused by)\b", re.I)),
    ("cause-", re.compile(r"\b(therefore|leads to|results in|so that)\b", re.I)),
    ("support-", re.compile(r"\b(contradicts|refutes|against the claim|disputed by)\b", re.I)),
    ("support+", re.compile(r"\b(evidence that|confirmed by|supported by|according to)\b", re.I)),
    ("kind-", re.compile(r"\b(is a|is an|for example|such as|e\.g\.)\b", re.I)),
    ("kind+", re.compile(r"\b(in general|generally|typically|is a kind of|are kinds of)\b", re.I)),
]

#: Japanese cues (PREREGISTERED_2026-08-16_japanese_arms). Closed, and
#: matched only in the PREDICATE REGION — the tail of the clause. Japanese
#: has no word boundaries, so a bare substring match over-fires by default:
#: 「一種の冗談を言う」 contains 一種 and asserts nothing about a kind.
#: Position is what separates them, and it is the same repair that finally
#: worked for polarity — look at where the thing sits, not at whether the
#: characters occur.
#:
#: Order matters (first hit wins), longest and most specific first.
_JA_CUES = [
    ("support-", ("この限りでない", "を除く", "を除き", "ただし",
                  "適用されない", "限りでない")),
    ("support+", ("に規定される", "に規定されている", "に定められる",
                  "に定められている", "に支持されている", "によれば",
                  "とされている")),
    ("cause+",   ("によって発生する", "によって生じる", "が原因で",
                  "によって倒れる", "に起因する", "から生じる")),
    ("cause-",   ("をもたらす", "を引き起こす", "につながる",
                  "を生じさせる")),
    ("kind+",    ("は一般に", "は通常", "は総称", "の総称である")),
    ("kind-",    ("の一種である", "の一種", "に分類される", "の一つである",
                  "の例である")),
]

#: The predicate region is the text after the last case particle — but the
#: で of である is NOT one. Measured 2026-08-16: reading it as a case marker
#: cut 「りんごは果実の一種である」 down to 「ある」 and every cue with it,
#: which failed A2 on all ten items while A1 passed on all ten. Same shape
#: as every other defect found that day: a functional element taken for
#: something it is not. で before あ/は/も is the continuative of だ, and
#: に before よ heads a compound particle (による), not a case.
_JA_SKIP = re.compile(r"で(?=[あはも])|に(?=よ)")


def _ja_predicate_region(sentence: str) -> str:
    """The clause tail a cue may be read from.

    Scans for the last case particle that is not part of a copula or a
    compound-particle head. Falls back to the whole sentence when there is
    no particle at all — a fragment with no structure gets no special
    leniency, it simply has nowhere else for a predicate to be.
    """
    text = sentence or ""
    last = -1
    for i, ch in enumerate(text):
        if ch not in "はがをにでとへ":
            continue
        if _JA_SKIP.match(text, i):
            continue
        last = i
    return text[last + 1:] if last >= 0 else text


def classify_arm_ja(sentence: str) -> Optional[str]:
    """Arm for a Japanese sentence, or None. None is a first-class answer.

    A cue outside the predicate region does not count. That single rule is
    what keeps 「一種の冗談を言う」 untagged while 「りんごは果実の一種である」
    is kind-, and it is registered before any of this was measured.
    """
    tail = _ja_predicate_region(sentence)
    for arm, cues in _JA_CUES:
        for cue in cues:
            if cue in tail:
                return arm
    return None


_INTENT = [
    ("cause+", re.compile(r"\b(why|what causes|なぜ|どうして)\b", re.I)),
    ("cause-", re.compile(r"\b(what happens (if|when)|what does .* lead to)\b", re.I)),
    ("kind-", re.compile(r"\b(example|instance|such as what|for instance)\b", re.I)),
    ("support+", re.compile(r"\b(what evidence|how do we know|is it confirmed)\b", re.I)),
]

_ARM_GAP_VERDICT = {
    "cause+": "UNKNOWN_NO_CAUSE_RECORDED",
    "cause-": "UNKNOWN_NO_EFFECT_RECORDED",
    "kind-": "UNKNOWN_NO_INSTANCE_RECORDED",
    "kind+": "UNKNOWN_NO_GENERALIZATION_RECORDED",
    "support+": "UNKNOWN_NO_SUPPORT_RECORDED",
    "support-": "UNKNOWN_NO_COUNTEREVIDENCE_RECORDED",
}


def classify_arm(sentence: str) -> Optional[str]:
    for arm, rx in _CUES:
        if rx.search(sentence or ""):
            return arm
    # Japanese was invisible here until 2026-08-16: every fact in the
    # published store came back untagged, so judgement ran over facet sets
    # instead of over claims.
    return classify_arm_ja(sentence)


def classify_intent(query: str) -> Optional[str]:
    for arm, rx in _INTENT:
        if rx.search(query or ""):
            return arm
    return None


@dataclass
class ArmIndex:
    """core → arm → source snippets. An interpretation, not a store."""

    arms: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)

    def ingest(self, store, sentence: str) -> Dict[str, Any]:
        core = store.ingest_sentence(sentence)
        arm = classify_arm(sentence)
        if core and arm:
            self.arms.setdefault(core, {}).setdefault(arm, []).append(
                sentence.strip()[:200])
        return {"core": core, "arm": arm}

    def report(self, core: str) -> Dict[str, Any]:
        """The six-question checklist: which arms hold knowledge, which are
        the typed gaps. This is the shape a GapNode wants to be fed."""
        held = self.arms.get(core, {})
        return {
            "core": core,
            "filled": {a: len(held.get(a, [])) for a in ARMS if held.get(a)},
            "empty": [a for a in ARMS if not held.get(a)],
            "gap_verdicts": [_ARM_GAP_VERDICT[a] for a in ARMS if not held.get(a)],
        }

    def gate(self, out: Dict[str, Any], query: str) -> None:
        """Intent-specific honesty: a question about an arm the answered core
        does not hold gets the arm's own typed refusal — with what IS held,
        so the caller sees 'known, but not its why' rather than nothing."""
        if out.get("verdict") != "ANSWER":
            return
        intent = classify_intent(query)
        if intent is None:
            return
        core = str(out.get("core_key") or out.get("core") or "")
        held = self.arms.get(core, {})
        if held.get(intent):
            # The right kind of knowledge exists — replace the generic
            # answer text with the arm's own sentences, which is the point
            # of asking "why" rather than "what".
            out["arm"] = intent
            out["arm_evidence"] = held[intent]
            return
        out["verdict"] = _ARM_GAP_VERDICT[intent]
        out["missing_arm"] = intent
        out["held_arms"] = sorted(held.keys())
        out["reason"] = (f"core '{core}' is known but its {intent} arm is empty "
                        f"— the question asks for a kind of knowledge not recorded")

    # -- persistence -------------------------------------------------------

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.arms, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "ArmIndex":
        p = Path(path)
        if not p.is_file():
            return cls()
        try:
            return cls(arms=json.loads(p.read_text()))
        except (json.JSONDecodeError, OSError):
            return cls()
