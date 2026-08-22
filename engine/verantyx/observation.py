"""An observation is a cross. Nothing here is a check.

Why this is placement and not a gate
------------------------------------
The first draft of this module was four hand-written gates — pass
agreement, coverage, truncation, derivation — lifted straight off one
incident (a Teams screen read on 2026-08-13). That is the wrong shape,
and the reason is the one this codebase keeps rediscovering: a checklist
built from a failure only ever catches that failure. The next app fails
somewhere the checklist does not look, and a checklist that stays silent
reads exactly like a checklist that passed.

The structural version is smaller and older. ``arm_schema`` already
says what it is:

    The six arms are six questions every claim should eventually answer;
    an empty arm is a typed, targetable gap.

So an observation does not need to be checked. It needs to be PLACED —
and then the six arms ask their six questions, as they do for every
other claim in the store, and the existing typed refusals come out.

What the 8/13 run got wrong, structurally
-----------------------------------------
Five mistakes, caught then by a strong model auditing itself. Placed on
the cross they are not five things:

    「初めてのaijax」→"ajax" reported as read
        the cleaned string's origin is another facet, not a source, so
        its support+ arm is empty  →  UNKNOWN_NO_SUPPORT_RECORDED

    two OCR passes disagreed, one was silently picked
        both readings carry mass about the same subject, one supporting
        the other opposing  →  contested, and contested is already
        demoted and kept out of settled prose (compose.py)

    an unreadable date written as "(soonest, Monday)"
        the reading matched no arm at all  →  untagged, and untagged has
        never been promotable

    two of three tabs read, "the assignments are" reported
    the last row at y=0.821 with nothing below it established
        BOTH are one fact: the instances are open, so the general claim
        over them was stated but never held
        →  UNKNOWN_NO_GENERALIZATION_RECORDED

That last verdict is not the one this module was first written to
expect — UNKNOWN_NO_INSTANCE_RECORDED was, and it is wrong. The rows
WERE recorded; three assignments really were read. What was never
established is the generalization over them. Placing the observation
said so without being told, which is the whole argument for placing
rather than checking.

Five collapse to three, two of the three already work, and the third is
an arm verdict that already exists. The only thing missing was that a
screen reading never became a cross — it went into a prompt as prose,
where no arm could ask it anything.

Generality
----------
Nothing below mentions screens, OCR, or macOS. The six roles come from
the *act of observing*, which is why they are total: something produced
the reading, something may disagree with it, something brought this view
about, this view brings something about, the reading is about a whole,
and the whole has parts. A file, a command's stdout, a web page and a
window all have all six.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .arm_schema import ARMS, _ARM_GAP_VERDICT


@dataclass(frozen=True)
class Observation:
    """One act of observing, in the six roles the act itself has.

    Every field is optional because an absent role is not an error — it
    is the untagged state, and it is what makes the arm verdict fire.
    Filling a role you did not actually establish is the only way to
    break this, which is the same rule the rest of the store runs on.
    """

    subject: str

    #: What produced the reading — a pass name, an app, a file, a source.
    by: Tuple[str, ...] = ()
    #: Readings of the same subject that came back different.
    against: Tuple[str, ...] = ()

    #: The act that brought this view about (a click, a command, a load).
    after: str = ""
    #: What this view then produced (the postcondition that was observed).
    yielded: str = ""

    #: The collective statement being made about the subject.
    claim: str = ""
    #: The individual parts actually read.
    items: Tuple[str, ...] = ()
    #: Whether the parts are known to be ALL of them. False is the honest
    #: default: having instances and having every instance are different
    #: facts, and only the second supports a general claim. An unscrolled
    #: list and an unopened tab are the same unclosed arm.
    items_closed: bool = False

    def found(self) -> bool:
        """Did this establish anything, or only that something was looked at?

        `by` / `against` / `after` describe the ACT — which tool ran, what
        it ran against, what preceded it. `yielded` / `items` / `claim`
        describe the FINDING. Measured 2026-08-16: a stage that opened a
        window and saw nothing still placed seven arms, purely from the
        act, and the chain counted that as progress and reported DONE for
        a run that found nothing.

        Arms placed by looking are not arms placed by finding, and a
        harness that cannot tell them apart reports success for exactly
        the runs that most need to report failure.
        """
        return bool((self.yielded or "").strip()
                    or (self.claim or "").strip()
                    or [x for x in (self.items or ()) if str(x).strip()])


def place(obs: Observation) -> Dict[str, List[str]]:
    """The observation's six arms. Total, deterministic, no guessing.

    An arm is absent when its role was not established. It is never
    filled from a neighbouring role — inferring a cause from an effect
    is the fuzzy tagging ``arm_schema`` refuses by design.

    ``kind+`` is the one conditional placement, and the condition is
    structural rather than a threshold: a general claim is only placed
    when its instances are closed. While they are open the claim has
    been *stated* but not *held*, so the arm stays empty and reports
    itself missing — which is exactly what an unread third tab and an
    unscrolled last row both are.
    """
    arms: Dict[str, List[str]] = {}

    def put(arm: str, values: Sequence[str]) -> None:
        vals = [str(v).strip() for v in values if str(v).strip()]
        if vals:
            arms[arm] = vals

    put("support+", obs.by)
    put("support-", obs.against)
    put("cause+", [obs.after])
    put("cause-", [obs.yielded])
    put("kind-", obs.items)
    if obs.claim.strip() and obs.items_closed and obs.items:
        put("kind+", [obs.claim])

    return arms


def readings(subject: str, passes: Dict[str, str]) -> Observation:
    """Several passes over one target, placed by whether they agree.

    ``passes`` is pass-name → verbatim text. One rule, no special cases:

        all passes agree   →  support+ only. Nothing opposes it.
        any disagreement   →  EVERY variant lands on support+ AND on
                              support-, because in a disagreement each
                              reading is genuinely backed by the pass
                              that returned it and genuinely fought by
                              the ones that did not.

    Both arms carrying mass is the contested state the store already
    understands and already demotes, so no winner-picking function is
    needed — and none is wanted. An earlier draft ranked the variants
    and gave the majority support+, which quietly made a 2-vs-1 OCR
    split look settled and, worse, left support+ EMPTY on a 1-vs-1 tie:
    the most contested case possible reported as merely unsupported.
    Counts stay legible in the facets (each variant is listed once per
    pass that read it), so a human can see 2-vs-1 without this code
    deciding what it means.

    Giving observations their own private notion of "agreement" would be
    the pooling mistake (束ねず重ねる) in a new costume.
    """
    groups: Dict[str, List[str]] = {}
    for name, text in passes.items():
        groups.setdefault(text, []).append(name)

    if not groups:
        return Observation(subject=subject)

    labelled = tuple("%s=%s" % (n, t)
                     for t, names in sorted(groups.items())
                     for n in sorted(names))

    if len(groups) == 1:
        return Observation(subject=subject, by=labelled)

    return Observation(subject=subject, by=labelled, against=labelled)


def derived(raw: str, cleaned: str, reason: str) -> Observation:
    """A repaired string, placed so the repair cannot pass as a reading.

    The cleaned form's cause+ is the raw form and the repair's reason —
    a real causal fact, and the right arm for it. Its support+ stays
    empty, because nothing observed the cleaned string: something
    observed the raw one and then something changed it.

    That empty arm is the mechanism. 「初めてのaijax」→"ajax" may well be
    correct; it still answers UNKNOWN_NO_SUPPORT_RECORDED until a pass
    actually returns "ajax", and the store keeps both strings forever so
    the question stays askable.
    """
    return Observation(
        subject=cleaned,
        after="derived from %r (%s)" % (raw, reason.strip() or "unstated"),
    )


def report(obs: Observation) -> Dict[str, Any]:
    """The six-question checklist for this observation.

    Deliberately the same shape ``ArmIndex.report`` returns, so an
    observation feeds GapNodes and the answer gate through the paths
    that already exist rather than beside them.
    """
    arms = place(obs)
    empty = [a for a in ARMS if not arms.get(a)]
    return {
        "subject": obs.subject,
        "filled": {a: len(v) for a, v in arms.items()},
        "empty": empty,
        "gap_verdicts": [_ARM_GAP_VERDICT[a] for a in empty],
        "contested": bool(arms.get("support+") and arms.get("support-")),
        "instances_open": bool(obs.items) and not obs.items_closed,
        "arms": arms,
    }


def facets(obs: Observation) -> List[str]:
    """Store facets for an observation, arm-prefixed.

    Only placed roles become facets. A role that was not established
    contributes nothing — there is no placeholder, no "unknown" string,
    nothing for a later reader to mistake for a finding.
    """
    out: List[str] = []
    for arm, values in place(obs).items():
        for v in values:
            out.append("%s:%s" % (arm, v[:120]))
    return out
