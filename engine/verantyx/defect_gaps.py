"""Defect reports become GapNodes, and the same defect twice becomes one.

The loop this closes: somebody reads a worksheet, marks a finding false, and
the tool builds a report carrying no document. That report is a typed failure,
and typed failures already have a home here — `gap_graph` was built for
exactly this state, "something required is missing", and already routes every
proposal through quarantine so nothing becomes trusted without a human.

What the wiring adds is the part a report has that a growth bucket does not:
a defect names WHICH RULE decided it. That turns three things into lookups
rather than judgements.

    aggregation   Two reports are the same defect when the same rules fired,
                  not when their text matches. The key carries no text at all.
    routing       A gap whose frame ends in `none` is a rule that does not
                  exist yet — a READING gap. One where a rule fired and the
                  human still called it wrong is that rule being too wide.
                  One where the term is absent from the vocabulary is a
                  VOCABULARY gap, and only that kind can be proposed
                  automatically, because only there is the report enough.
    severity      A false positive on a state claim is CRITICAL: the engine
                  said the opposite of a source. A miss is QUALITY.

What it deliberately does NOT do is fix anything. A reading gap needs a person
to write a rule, and a vocabulary gap becomes a PROPOSAL that a person accepts
— the standing rule in this repository, and the one that makes the growth
loop something a municipal officer can be in.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .defect_report import Defect, frame, rules_fired

#: All defect gaps live under one scope, so `find_by_scope_subject` is the
#: deduplicator and no separate index is needed.
SCOPE = "engine.reading"

#: What a reader can be told to do next, per kind. The gap is useless if it
#: only records that something was wrong.
GAP_KINDS = {
    "reading_no_rule": (
        "No guard reads this frame. A rule has to be written, and the frame "
        "says where: the characters that follow the term."
    ),
    "reading_rule_too_wide": (
        "A guard fired and a person still called the reading wrong, so the "
        "guard admits a case it should not. Narrow it, and pin both "
        "directions."
    ),
    "vocabulary_missing": (
        "The term carries no pole, so nothing could have been read. This is "
        "the one kind a report contains enough to propose: an overlay entry, "
        "for a person to accept."
    ),
    "detector": (
        "Both sides were read correctly and the verdict is still wrong. "
        "Rare and severe — measure every corpus before and after."
    ),
}


def classify(defect: Defect, sentences: Optional[List[str]] = None) -> str:
    """Which of the four kinds this report is."""
    from .ja_grammar import ALIASES, ASPECT_OF

    term = (defect.value or "").replace("not_", "")
    if term and term not in ASPECT_OF and term not in ALIASES:
        return "vocabulary_missing"

    fired: List[str] = []
    for s in sentences or []:
        fired += rules_fired(s, term)
    if not fired:
        fired = [f.split(" + ")[-1] for f in defect.frames]

    if defect.kind == "false_negative" and any("none" in f for f in fired):
        return "reading_no_rule"
    if defect.kind == "false_positive":
        # A guard that fired and was still wrong is too wide; no guard at all
        # means the frame is unseen.
        real = [f for f in fired if f not in ("none", "cell_value")]
        return "reading_rule_too_wide" if real else "reading_no_rule"
    return "reading_no_rule"


def severity(defect: Defect) -> str:
    """A false positive is the engine saying the opposite of a source."""
    return "CRITICAL" if defect.kind == "false_positive" else "QUALITY"


def record(graph, defect: Defect, sentences: Optional[List[str]] = None
           ) -> Dict[str, Any]:
    """File a report as a gap, or reinforce the one already there.

    Returns what happened, not just the node: a reporter who cannot tell
    "this is new" from "this is the fourth time" has no way to know whether
    reporting was worth it.
    """
    subject = defect.frames[0] if defect.frames else f"{defect.aspect}:{defect.value}"
    kind = classify(defect, sentences)

    existing = graph.find_by_scope_subject(SCOPE, subject)
    if existing is not None:
        # Reinforcement is a count, kept where the node already keeps its
        # evidence. A second report of one defect is evidence about the
        # defect's reach, not a second defect.
        seen = [s for s in (existing.caused_by or []) if s.startswith("seen:")]
        n = int(seen[0].split(":", 1)[1]) + 1 if seen else 2
        others = [s for s in (existing.caused_by or []) if not s.startswith("seen:")]
        existing.caused_by = others + [f"seen:{n}"]
        for shape in defect.shapes:
            if shape not in (existing.blocks or []):
                existing.blocks = (existing.blocks or []) + [shape]
        return {"status": "reinforced", "gap_id": existing.gap_id,
                "kind": kind, "seen": n, "subject": subject}

    node = graph.create(
        gap_type="reading_defect",
        subject=subject,
        scope=SCOPE,
        severity=severity(defect),
        failure_type=kind,
        observed_transition=defect.kind,
        expected_transition=("no claim placed" if defect.kind == "false_positive"
                             else "a claim placed"),
        blocks=list(defect.shapes),
        caused_by=["seen:1"],
        # A reading gap is resolved by a person writing a rule; there is no
        # source to acquire it from, and saying so keeps the acquisition loop
        # from going looking.
        acquisition_methods=(["vocabulary_overlay"]
                             if kind == "vocabulary_missing" else ["human_rule"]),
        max_depth=1,
    )
    return {"status": "created", "gap_id": node.gap_id, "kind": kind,
            "seen": 1, "subject": subject}


def proposal(defect: Defect) -> Optional[Dict[str, Any]]:
    """For a vocabulary gap only: the overlay entry a person would accept.

    Returns None for every other kind, because for every other kind the report
    does not contain enough — a rule needs somebody to decide what it should
    admit, and guessing that from one sentence is how a guard becomes too wide.

    The proposal is never applied here. `ja_grammar.load_overlay` validates it
    and a human writes the file; this only saves them the typing.
    """
    from .ja_grammar import ALIASES, ASPECT_OF

    term = (defect.value or "").replace("not_", "")
    if not term or term in ASPECT_OF or term in ALIASES:
        return None
    if not defect.aspect:
        return None
    pole = "-" if defect.kind == "false_negative" else "+"
    return {
        "note": ("Proposed, not applied. Check it against sentences that must "
                 "stay silent before accepting — a term that fires on a "
                 "compound is worse than one that is absent."),
        "overlay": {"aspect_joins": [[term, defect.aspect, pole]]},
        "control_check": (
            f"Confirm these produce NO pole: compounds beginning {term}, and "
            f"any word where {term} is part of a longer noun."
        ),
    }
