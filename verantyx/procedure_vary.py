"""One success, many candidate methods — by variation, not by inference.

The question this answers
------------------------
A strong model read Teams on 2026-08-13 by building a route nobody had:
Vision OCR, two passes, CGEvent clicks, coordinate mapping. It worked
once. What can be got from that one success?

The tempting answer is "generalise it" — and it is wrong in a specific,
checkable way. **From a single success you cannot tell which conditions
were load-bearing.** The run happened on Retina, in Japanese, on
com.microsoft.teams2, with the window frontmost, after a click at
(207,392). Every one of those is a candidate precondition and the run
gives no way to rank them. A model asked to "generalise" will rank them
anyway, by plausibility, and plausibility is what wrote 「ajax」.

So this module does not derive. It ENUMERATES — deterministically, from
what was recorded — and each variation states what its own success would
establish. Running them is what turns one method into several; nothing
here claims a method that has not been run.

    proposing a variation   cheap, deterministic, no model
    verifying one           one real run, and the world decides
    remembering the verdict record_asset_outcome, already built

Single-change only
------------------
Every variation differs from the parent by exactly one thing. Not for
cost — for attribution. If two changes are made and the run fails, the
result names no cause, and an uninterpretable measurement is the failure
mode this codebase spends most of its docstrings refusing. The
combinatorial space is reachable by varying a variation that survived,
which keeps every step attributable.

What a surviving variation is worth
-----------------------------------
    a dropped step that still succeeds     the step was incidental —
                                           a strictly cheaper method
    a relaxed precondition that holds      the condition was not
                                           necessary — a wider method
    a swapped asset that works             the assets are
                                           interchangeable here — a
                                           method that survives the
                                           first one being unavailable

The third is the one that matters most for autonomy: it is the
difference between "Teams can be read" and "an app with an opaque
accessibility tree can be read", and only a run against a SECOND such
app can establish it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .procedure import Condition, Effect, Procedure, Step

#: A variation has been proposed but nothing has been run. It is the only
#: status this module may assign: assigning anything else would be the
#: module deciding an empirical question by itself.
UNTESTED = "UNTESTED"

DROP_STEP = "drop_step"
RELAX_PRECONDITION = "relax_precondition"
SWAP_ASSET = "swap_asset"


@dataclass(frozen=True)
class Variant:
    """A candidate method, and the question it would answer.

    ``establishes`` is not documentation. It is the reason the variation
    is worth a run, written before the run, which is the same
    pre-registration discipline the measurements here follow — a variant
    whose meaning is decided after seeing the result means nothing.
    """

    variant_id: str
    parent_id: str
    change: str
    changed: str
    procedure: Procedure
    establishes: str
    status: str = UNTESTED

    def as_dict(self) -> Dict[str, Any]:
        return {"variant_id": self.variant_id, "parent_id": self.parent_id,
                "change": self.change, "changed": self.changed,
                "establishes": self.establishes, "status": self.status,
                "procedure": self.procedure.as_dict()}


def _child(parent: Procedure, suffix: str, *,
           preconditions: Optional[List[Condition]] = None,
           steps: Optional[List[Step]] = None) -> Procedure:
    return Procedure(
        procedure_id="%s/%s" % (parent.procedure_id, suffix),
        preconditions=(parent.preconditions if preconditions is None
                       else preconditions),
        steps=parent.steps if steps is None else steps,
        expected_effects=list(parent.expected_effects),
        budget=parent.budget,
        status="DEFINED",
    )


def vary(parent: Procedure,
         alternatives: Optional[Dict[str, Sequence[str]]] = None,
         asset_key: str = "asset") -> List[Variant]:
    """Every single-change variation of a procedure that already worked.

    ``alternatives`` maps an asset name to the others that might stand
    in for it — exactly the shape ``assets_for(need)`` already returns,
    so the substitutes are ones this machine actually has rather than
    ones a model can name. Nothing is invented here: an asset with no
    recorded alternatives produces no swap variants.

    A parent that has not succeeded produces nothing. Varying a failure
    enumerates ways to fail differently, and the store has no use for
    those.
    """
    if parent.status not in ("VERIFIED", "TRUSTED"):
        return []

    alts = {k.strip().casefold(): tuple(v)
            for k, v in (alternatives or {}).items()}
    out: List[Variant] = []

    # 1. Drop one step. Only meaningful while more than one remains —
    #    a procedure of one step with that step dropped is not a method.
    if len(parent.steps) > 1:
        for i, s in enumerate(parent.steps):
            kept = [x for j, x in enumerate(parent.steps) if j != i]
            out.append(Variant(
                variant_id="%s/drop%d" % (parent.procedure_id, i),
                parent_id=parent.procedure_id,
                change=DROP_STEP, changed="step[%d]=%s" % (i, s.op),
                procedure=_child(parent, "drop%d" % i, steps=kept),
                establishes="step %s was incidental; the method is one "
                            "step cheaper" % s.op))

    # 2. Relax one precondition. Every condition observed during a single
    #    success is a suspect, including the ones that feel obviously
    #    required — "obviously" is the ranking this module refuses.
    for i, c in enumerate(parent.preconditions):
        kept = [x for j, x in enumerate(parent.preconditions) if j != i]
        out.append(Variant(
            variant_id="%s/relax%d" % (parent.procedure_id, i),
            parent_id=parent.procedure_id,
            change=RELAX_PRECONDITION, changed="precondition[%d]=%s" % (i, c.kind),
            procedure=_child(parent, "relax%d" % i, preconditions=kept),
            establishes="%s was not necessary; the method covers a wider "
                        "set of situations" % c.kind))

    # 3. Swap a named asset for one this machine already has.
    for i, s in enumerate(parent.steps):
        current = str(s.args.get(asset_key, "")).strip()
        if not current:
            continue
        for other in alts.get(current.casefold(), ()):  # noqa: B007
            if other.strip().casefold() == current.casefold():
                continue
            args = dict(s.args)
            args[asset_key] = other
            steps = list(parent.steps)
            steps[i] = Step(op=s.op, args=args)
            out.append(Variant(
                variant_id="%s/swap%d-%s" % (parent.procedure_id, i,
                                             other.strip().casefold()),
                parent_id=parent.procedure_id,
                change=SWAP_ASSET,
                changed="step[%d].%s: %s -> %s" % (i, asset_key, current, other),
                procedure=_child(parent, "swap%d_%s" % (i, other.strip().casefold()),
                                 steps=steps),
                establishes="%s and %s are interchangeable here; the method "
                            "survives %s being unavailable"
                            % (current, other, current)))

    return out


def agenda(parent: Procedure,
           alternatives: Optional[Dict[str, Sequence[str]]] = None) -> Dict[str, Any]:
    """The variations as a work list, with the cost stated up front.

    This is what an agent reads instead of thinking about what else it
    could try. The list is finite, ordered, and every item says what
    running it would establish — which is the part a weak model cannot
    produce for itself and does not have to.
    """
    vs = vary(parent, alternatives)
    return {
        "parent": parent.procedure_id,
        "parent_status": parent.status,
        "runs_required": len(vs),
        "methods_now": 1 if parent.status in ("VERIFIED", "TRUSTED") else 0,
        "methods_possible": 1 + len(vs),
        "variants": [v.as_dict() for v in vs],
        "note": "every variant is UNTESTED; a method that has not been "
                "run is not a method",
    }
