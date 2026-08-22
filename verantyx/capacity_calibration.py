"""What to do about a bucket classified `needs_more_capacity`.

The signal says a procedure that already exists ran and hit a limit. The
tempting reading is "the search algorithm needs improving", and that reading
is a trap: improving an algorithm is unbounded work with no verification
harness, so a loop that proposes it produces suggestions nobody can check.
`module_verify` can decide whether a drafted module is safe and behaves; no
equivalent gate exists for "is this search better".

The bounded version of the same signal is a number. `solve_equation`
enumerates 0..200; `wire_mul` allows 500 steps; the cross has six arms. Each
is a constant, each has a known failure mode when raised (slower, more
memory), and each can be checked by re-running the very queries that
exhausted it. That is the whole of what this module does — it does not
invent, it re-runs at a larger limit and reports whether the verdict changed.

**The re-run is the test of the classification, not just of the fix.** If
raising the limit turns UNKNOWN_BUDGET into ANSWER, the bucket really was a
capacity problem. If it does not, the label was wrong and saying so is more
useful than proposing a larger number anyway — which is why a failed probe
returns `reclassify` rather than a bigger suggestion.

Nothing here writes a setting. A proposal goes to the same human-approval
queue everything else goes through.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .growth_signals import UnknownBucket

#: How far to stretch a limit before giving up on the capacity hypothesis.
#: Deliberately a small ladder rather than one huge jump: the point is to
#: find the smallest limit that answers, and a single 100x probe would both
#: hide that and take the longest possible time to fail.
LADDER = (2, 5, 10)

#: Verdicts that mean "still stuck at this limit".
_STUCK = frozenset({"UNKNOWN_BUDGET", "UNKNOWN_OVERFLOW"})


@dataclass
class Probe:
    """One re-run of one query at one enlarged limit."""
    query: str
    multiplier: int
    verdict: str
    answered: bool


@dataclass
class CalibrationResult:
    normalized: str
    #: "propose" | "reclassify" | "mixed" | "no_examples"
    outcome: str
    reason: str
    #: Smallest multiplier at which every probed query answered, if any.
    multiplier: Optional[int] = None
    probes: List[Probe] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "normalized": self.normalized,
            "outcome": self.outcome,
            "reason": self.reason,
            "multiplier": self.multiplier,
            "probes": [
                {"query": p.query, "multiplier": p.multiplier,
                 "verdict": p.verdict, "answered": p.answered}
                for p in self.probes
            ],
        }


def calibrate(
    bucket: UnknownBucket,
    rerun: Callable[[str, int], Dict[str, Any]],
    ladder: tuple = LADDER,
    max_examples: int = 3,
) -> CalibrationResult:
    """Re-run this bucket's own failing queries at progressively larger limits.

    `rerun(query, multiplier) -> {"verdict": ...}` is injected rather than
    imported so this stays runnable offline against a stub — the same reason
    `boundary_eval` exists. A calibration loop that can only be tested by
    running the real router is a calibration loop nobody tests.

    Requires *every* probed query to answer before proposing. One of three
    answering is not a limit that fixes the bucket, and proposing it would put
    a number in front of a human that does not do what its justification says.
    """
    examples = (bucket.examples or [])[:max_examples]
    if not examples:
        return CalibrationResult(bucket.normalized, "no_examples",
                                 "bucket recorded no example queries to re-run")

    probes: List[Probe] = []
    for mult in ladder:
        answered_all = True
        for q in examples:
            verdict = str(rerun(q, mult).get("verdict", "UNKNOWN_UNPARSED"))
            answered = verdict == "ANSWER"
            probes.append(Probe(q, mult, verdict, answered))
            if not answered:
                answered_all = False
        if answered_all:
            return CalibrationResult(
                bucket.normalized, "propose",
                f"every probed query answered at {mult}x",
                multiplier=mult, probes=probes,
            )

    # Nothing answered every query at any rung. Three different things can
    # look like this and they need different answers, which an earlier version
    # of this function got wrong: it checked only whether *any* non-limit
    # verdict appeared at the top rung, so a bucket where one query was fixed
    # and another was still budget-bound came back as "this was never a
    # capacity problem" — a claim contradicted by the query still hitting the
    # budget.
    top = [p for p in probes if p.multiplier == ladder[-1]]
    stuck = [p for p in top if p.verdict in _STUCK]

    if len(stuck) == len(top):
        # Uniformly limit-bound. The hypothesis survives; this ladder is just
        # too short to confirm a value.
        return CalibrationResult(
            bucket.normalized, "propose",
            f"still limit-bound at {ladder[-1]}x — a larger limit may work, "
            f"but this ladder cannot show it",
            probes=probes,
        )

    if not stuck:
        # Nothing is limit-bound any more, yet not everything answers. The
        # queries fail for some other reason, so the label was wrong.
        other = sorted({p.verdict for p in top})
        return CalibrationResult(
            bucket.normalized, "reclassify",
            f"raising the limit did not help; at {ladder[-1]}x the queries return "
            f"{', '.join(other)} — this was never a capacity problem",
            probes=probes,
        )

    # Some queries are still limit-bound and others are not. The bucket holds
    # more than one kind of failure, so no single number is the right answer
    # and neither verdict about "the bucket" is true. The defect is upstream,
    # in whatever grouped these queries together — `normalize_query` strips
    # enough that queries with different causes can share a key.
    freed = sorted({p.verdict for p in top if p.verdict not in _STUCK})
    return CalibrationResult(
        bucket.normalized, "mixed",
        f"{len(stuck)} of {len(top)} queries are still limit-bound at "
        f"{ladder[-1]}x while the rest return {', '.join(freed)} — this bucket "
        f"groups more than one cause and should be split before any limit is "
        f"proposed",
        probes=probes,
    )


# ---------------------------------------------------------------------------
# The wiring: needs_more_capacity buckets → real re-runs → quarantine.
# ---------------------------------------------------------------------------

def _math_parameter_for(bucket: UnknownBucket) -> Optional[str]:
    """Which config knob does this bucket's failure point at?

    Read from the baseline failure's `reason` string rather than guessed from
    the verdict alone, because UNKNOWN_BUDGET is produced by two different
    limits: `repeat>N` is wire_mul's step budget, `no_solution_in_0..N` is
    solve_equation's enumeration range. Returns None when the bucket's own
    examples no longer reproduce a capacity failure — in which case there is
    nothing to calibrate and saying so beats proposing a number.
    """
    from .math_sim import math_ask

    for q in (bucket.examples or [])[:3]:
        r = math_ask(q)
        reason = str(r.get("reason", ""))
        if reason.startswith("repeat>"):
            return "math_mul_steps"
        if reason.startswith("no_solution_in_"):
            return "math_solve_limit"
        if reason.startswith("needs>") or reason == "carry_out_of_last_arm":
            # N_ARMS — the geometry of the cross. Not runtime capacity.
            return "STRUCTURAL"
    return None


def capacity_pass(buckets, cfg, quarantine) -> List[Dict[str, Any]]:
    """One heartbeat's worth of capacity work, shared by the MCP tool and the
    CLI so the two cannot drift apart.

    For every bucket the boundary detector marked `needs_more_capacity`:
    re-run its own failing queries at ladder-scaled limits, and

      propose     → queue the smallest working limit for human approval
      reclassify  → report that the label was wrong (nothing queued)
      mixed       → report that the bucket needs splitting (nothing queued)
      STRUCTURAL  → report only; N_ARMS is not a number to raise

    Every outcome is returned, not just the proposals — a heartbeat that
    only reports its successes is the kind of log this whole failure-typing
    exercise exists to replace.
    """
    from . import boundary
    from .math_sim import math_ask

    results: List[Dict[str, Any]] = []
    for bucket in buckets:
        verdict = boundary.classify(bucket)
        if verdict.classification != "needs_more_capacity":
            continue

        parameter = _math_parameter_for(bucket)
        if parameter == "STRUCTURAL":
            results.append({
                "normalized": bucket.normalized, "outcome": "structural",
                "reason": "limit is N_ARMS, the cross geometry itself — a design "
                          "decision, not a number this loop may raise",
            })
            continue
        if parameter is None:
            results.append({
                "normalized": bucket.normalized, "outcome": "stale",
                "reason": "the bucket's examples no longer reproduce a capacity "
                          "failure at current limits",
            })
            continue

        current = int(getattr(cfg, parameter))

        def rerun(q: str, mult: int) -> Dict[str, Any]:
            # Both limits scale together. Only the binding one changes the
            # outcome; scaling the other is harmless and avoids a second
            # parameter-detection pass being wrong about which one binds.
            return math_ask(
                q,
                solve_limit=cfg.math_solve_limit * mult,
                mul_steps=cfg.math_mul_steps * mult,
            )

        cal = calibrate(bucket, rerun)
        entry_queued = False
        if cal.outcome == "propose" and cal.multiplier is not None:
            entry = quarantine.propose(
                parameter=parameter, current=current,
                proposed=current * cal.multiplier,
                normalized=bucket.normalized, reason=cal.reason,
                probes=[{"query": p.query, "multiplier": p.multiplier,
                         "verdict": p.verdict} for p in cal.probes],
            )
            entry_queued = entry is not None
        results.append({
            "normalized": bucket.normalized,
            "outcome": cal.outcome,
            "parameter": parameter,
            "multiplier": cal.multiplier,
            "reason": cal.reason,
            "queued": entry_queued,
        })
    return results
