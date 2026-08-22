"""Generate gaps from structure alone — no person, no network, no model.

The loop already ran entirely on one machine: the audit page binds to
127.0.0.1, the gap graph lives in ~/.verantyx-audit, synthesis and
verification are local and deterministic. What it still needed was a person
to say "this finding is wrong", and a person is an external connection of a
different kind — the loop stops the moment nobody is looking.

This closes that end. Not by judging its own findings correct, which it
cannot do, but by noticing the SHAPES that a defect leaves in the store even
when nobody reads the output.

Four signals, each one a thing observed on this project's own corpora:

    polar core         A state word became a topic. Measured: disabling the
                       demotion put 断水, 欠航, 運休, 危険な back as cores on
                       内閣府's reports. A core that names a state collides
                       with every other mention of that state, and the subject
                       gate turns into a no-op on it.

    debris core        A single character, a date, a bracketed label. 日 became
                       a core when the layout spaced 「７月 30 日」 apart, and
                       7/29 and 7/30 were filed as one topic disagreeing with
                       itself.

    self conflict      One SOURCE holding both poles of one aspect on one core.
                       A document rarely contradicts itself; far more often
                       the engine read one of its sentences wrong.

    far evidence       The polar term sits a long way from where the sentence
                       ends. Measured on the eight confirmed-true findings:
                       evidence runs 35–67 characters, median 43. The one
                       false positive on municipal HTML ran 117. The two
                       ranges OVERLAP at 53, which is why this is a suspicion
                       and never a verdict.

What the module will not do, stated because the temptation is obvious: it
does not mark anything false. A signal opens a gap at severity QUALITY with
`observed_transition="suspected"`, and a suspected gap never reaches rule
synthesis — that path still requires reports a person made. Structure can say
"look here"; only a reader can say "this is wrong".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Where the confirmed-true findings sat. A span past this is unusual, not
#: wrong — the ranges overlap, and the overlap is the point.
FAR_EVIDENCE = 80

SIGNALS = {
    "polar_core": (
        "A state word is a topic. Every other mention of that state will "
        "collide with it, and the subject gate cannot filter a claim that is "
        "trivially about its own predicate."
    ),
    "debris_core": (
        "A single character, a date or a label became a topic. Usually the "
        "layout broke a word apart and one piece survived."
    ),
    "self_conflict": (
        "One source holds both poles. A document rarely contradicts itself; "
        "far more often one of its sentences was read wrong."
    ),
    "far_evidence": (
        "The polar term sits far from the end of its sentence, so it may have "
        "been swept in from a clause that was not asserting it."
    ),
}


@dataclass
class Suspicion:
    signal: str
    subject: str
    detail: str = ""
    #: Redacted, like everything else that leaves the reading path.
    shapes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in ("", [], None)}


def _redact(sentence: str) -> str:
    from .defect_report import skeleton

    return skeleton(sentence)


def scan(store, arms=None, *, far_evidence: int = FAR_EVIDENCE
         ) -> List[Suspicion]:
    """Every structural signal the store shows, without reading any output."""
    from .document_ingest import deep_report
    from .lang import _JA_DATE
    from .polarity import is_state_word_ja

    out: List[Suspicion] = []

    for core in store.crosses:
        poles = [k for k in store.crosses[core] if ":" in k]
        if not poles:
            continue
        if is_state_word_ja(core):
            out.append(Suspicion("polar_core", core,
                                 f"{len(poles)} pole(s) filed under a state word"))
        elif len(core) == 1 or _JA_DATE.match(core):
            out.append(Suspicion("debris_core", core,
                                 f"{len(poles)} pole(s) filed under debris"))

    for core in store.crosses:
        report = deep_report(store, core, arms)
        prov = (getattr(store, "provenance", {}) or {}).get(core, {})
        for entry in report.get("disputed", []):
            sources = {s for side in entry["sides"] for s in side["sources"]}
            evidence = []
            for side in entry["sides"]:
                slot = prov.get(f"{entry['aspect']}:{side['claim']}")
                if slot and len(slot) > 2:
                    evidence.append((str(slot[2]),
                                     side["claim"].replace("not_", "")))
            if len(sources) == 1:
                out.append(Suspicion(
                    "self_conflict", f"{core} / {entry['aspect']}",
                    f"both poles from one source",
                    [_redact(s) for s, _ in evidence]))
                continue
            far = [(s, t) for s, t in evidence if len(s) > far_evidence]
            if far:
                out.append(Suspicion(
                    "far_evidence", f"{core} / {entry['aspect']}",
                    f"evidence runs {max(len(s) for s, _ in far)} characters",
                    [_redact(s) for s, _ in far]))
    return out


def to_gaps(graph, suspicions: List[Suspicion]) -> List[Dict[str, Any]]:
    """File suspicions as gaps, deduplicated the way reports are.

    Severity is QUALITY without exception, and `observed_transition` says
    "suspected". A gap raised by structure has not been read by anyone, and
    the difference between "the shape is unusual" and "this is wrong" is the
    whole reason this project measures anything.
    """
    from .defect_gaps import SCOPE

    filed = []
    for s in suspicions:
        subject = f"self:{s.signal}:{s.subject}"
        existing = graph.find_by_scope_subject(SCOPE, subject)
        if existing is not None:
            filed.append({"status": "known", "gap_id": existing.gap_id,
                          "signal": s.signal, "subject": s.subject})
            continue
        node = graph.create(
            gap_type="reading_defect",
            subject=subject,
            scope=SCOPE,
            severity="QUALITY",
            failure_type=f"suspected_{s.signal}",
            observed_transition="suspected",
            expected_transition="a person reads it",
            blocks=list(s.shapes),
            caused_by=[f"signal:{s.signal}"],
            acquisition_methods=["human_review"],
            max_depth=1,
        )
        filed.append({"status": "created", "gap_id": node.gap_id,
                      "signal": s.signal, "subject": s.subject})
    return filed


def summary(suspicions: List[Suspicion]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for s in suspicions:
        counts[s.signal] = counts.get(s.signal, 0) + 1
    return {
        "total": len(suspicions),
        "by_signal": counts,
        "what_each_means": {k: v for k, v in SIGNALS.items() if k in counts},
        "not_a_verdict": (
            "These are shapes a defect tends to leave, not findings that are "
            "wrong. The ranges overlap with correct output — the one measured "
            "false positive ran 117 characters and a confirmed-true one ran "
            "53. A suspected gap is a place to look, and it never reaches rule "
            "synthesis on its own."
        ),
    }
