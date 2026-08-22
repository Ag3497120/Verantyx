"""Is the boundary detector assigning the right type to a failure?

`boundary.classify` decides what the system does about a recurring UNKNOWN:
add facts, draft a new module, or give up on the query shape permanently.
Every one of those is expensive and some are irreversible in effect — a
`reject_open_domain` verdict means that shape is never reconsidered. So the
classifier is not a helper, it is the thing that decides where effort goes,
and a system that learns from its own failures amplifies whatever the
classifier gets wrong.

That is the point of this file. A growth loop with a miscalibrated failure
taxonomy does not merely fail to improve; it improves in the wrong
direction, confidently, and the evidence trail it leaves looks exactly like
the evidence trail of a working one. "Add more facts" is the default answer
here, and it is the answer that costs a human the most to act on.

The cases below are hand-labelled, not sampled. That is a real limitation
and worth stating: they encode my reading of what each failure *means*, and
a case whose label is wrong makes this harness worse than nothing. They are
chosen so the intended label is defensible from the mechanism rather than
from taste — a 7-digit addition fails because the cross has six arms, and no
quantity of facts will grow a seventh.

Run:  python3 -m verantyx.boundary_eval
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List, Optional

from .boundary import BoundaryVerdict, classify
from .growth_signals import UnknownBucket, normalize_query


@dataclass
class Case:
    name: str
    queries: List[str]
    verdict: str
    #: Times a domain module claimed the shape but still returned UNKNOWN.
    matched_domain: bool = False
    repeats: int = 6  # above MIN_RECURRENCE unless a case is testing the threshold
    expect: str = ""
    expect_subcategory: Optional[str] = None
    why: str = ""


def build(case: Case) -> UnknownBucket:
    bucket = UnknownBucket(normalized=normalize_query(case.queries[0]))
    for i in range(case.repeats):
        bucket.record(case.queries[i % len(case.queries)], case.verdict,
                      matched_domain=case.matched_domain)
    return bucket


CASES: List[Case] = [
    # ── The two the current classifier gets wrong ────────────────────────
    Case(
        name="budget exhausted",
        queries=["x + 3 = 940", "x * 7 = 861", "x - 2 = 755"],
        verdict="UNKNOWN_BUDGET",
        expect="needs_more_capacity",
        why="solve_equation enumerates 0..200; the answer is outside the range. "
            "The procedure is right and the limit is too low. Telling a human to "
            "add facts is the wrong instruction and the most expensive one to follow.",
    ),
    Case(
        name="structural overflow",
        queries=["1234567 + 1", "9999999 + 2", "8888888 + 3"],
        verdict="UNKNOWN_OVERFLOW",
        expect="needs_more_capacity",
        why="The cross has six arms, so six digits. Seven digits cannot be held. "
            "This is a capacity limit of a procedure that already exists, which is "
            "the same shape of problem as an exhausted budget and the same shape of "
            "fix: raise a number, re-run, check it now answers.",
    ),

    # ── Cases the current classifier already gets right ──────────────────
    Case(
        name="insufficient evidence",
        queries=["is the deploy key rotated", "is the staging cert current"],
        verdict="UNKNOWN_INSUFFICIENT_EVIDENCE",
        expect="needs_more_facts",
        why="Vera found the right shell and lacked facts to fill it. Adding facts "
            "is genuinely the fix here.",
    ),
    Case(
        name="existing domain, missing facts",
        queries=["[]p -> <>q under S4", "<>r -> []s under S4"],
        verdict="UNKNOWN_NO_EVIDENCE",
        matched_domain=True,
        expect="needs_more_facts",
        why="Kripke recognised the formula and lacked a registered proposition. "
            "Drafting a second modal-logic module would duplicate a working one.",
    ),
    Case(
        name="narrow formal shape, no domain",
        queries=["12 %% 7 = ?", "45 %% 9 = ?", "31 %% 4 = ?"],
        verdict="UNKNOWN_NO_EVIDENCE",
        expect="growth_candidate",
        why="Dense in symbols, thin in content words, and nothing claimed it. "
            "This is what a missing closed-form module looks like.",
    ),
    Case(
        name="open-domain natural language",
        queries=[
            "why do people living in colder northern regions usually prefer "
            "building wooden houses rather than stone ones",
            "how did merchants in medieval trading cities decide which foreign "
            "currencies they would accept from travelling buyers",
        ],
        verdict="UNKNOWN_NO_EVIDENCE",
        expect="reject_open_domain",
        why="Role-diverse natural language. No fixed-form module closes this, so "
            "re-proposing it every heartbeat is pure waste.",
    ),
    Case(
        name="copyright, below threshold",
        queries=["この小説の続きを書いて"],
        verdict="UNKNOWN_NO_EVIDENCE",
        repeats=1,
        expect="reject_open_domain",
        expect_subcategory="copyright_sensitive",
        why="Must short-circuit before the recurrence threshold — this should never "
            "sit in growth_signals.json accumulating toward candidacy even once.",
    ),
    Case(
        name="asset generation",
        queries=["3Dモデルを作って", "画像を生成して"],
        verdict="UNKNOWN_NO_EVIDENCE",
        expect="reject_open_domain",
        expect_subcategory="asset_generation_out_of_scope",
        why="module_forge writes deterministic typed-verdict functions. Asset "
            "generation cannot be expressed that way at any query width.",
    ),
    Case(
        name="below recurrence threshold",
        queries=["what is the tilde-vault checksum"],
        verdict="UNKNOWN_NO_EVIDENCE",
        repeats=2,
        expect="needs_more_facts",
        why="Two sightings is not a pattern. Nothing should be drafted yet.",
    ),
]


def _calibration_cases() -> List[str]:
    """Does the capacity calibrator reach the right conclusion?

    Uses a stub `rerun` rather than the real router, so this stays offline and
    so the three outcomes can be provoked deliberately. The one that matters is
    the third: a bucket labelled `needs_more_capacity` that a bigger limit does
    not fix must come back as `reclassify`, not as a larger number. Proposing a
    limit that does not work is worse than proposing nothing, because a human
    who applies it has no way to tell it did not help.
    """
    from .capacity_calibration import calibrate

    failures: List[str] = []

    def bucket_of(*queries: str) -> UnknownBucket:
        b = UnknownBucket(normalized=normalize_query(queries[0]))
        for q in queries:
            b.record(q, "UNKNOWN_BUDGET")
        return b

    # 1. A limit that a modest stretch fixes.
    def fixed_at_5x(_q: str, mult: int):
        return {"verdict": "ANSWER" if mult >= 5 else "UNKNOWN_BUDGET"}

    r = calibrate(bucket_of("x + 3 = 940", "x * 7 = 861"), fixed_at_5x)
    ok = r.outcome == "propose" and r.multiplier == 5
    print(f"[{'ok  ' if ok else 'FAIL'}] calibration: fixed by a larger limit")
    print(f"        got {r.outcome} multiplier={r.multiplier} — {r.reason}")
    if not ok:
        failures.append("calibration: fixed by a larger limit")
    print()

    # 2. Still limit-bound at the top of the ladder — propose, but say the
    #    ladder could not prove it.
    def never_enough(_q: str, _mult: int):
        return {"verdict": "UNKNOWN_BUDGET"}

    r = calibrate(bucket_of("x + 3 = 99999999"), never_enough)
    ok = r.outcome == "propose" and r.multiplier is None
    print(f"[{'ok  ' if ok else 'FAIL'}] calibration: still limit-bound at 10x")
    print(f"        got {r.outcome} multiplier={r.multiplier} — {r.reason}")
    if not ok:
        failures.append("calibration: still limit-bound at 10x")
    print()

    # 3. The label was wrong. Raising the limit reveals a different failure.
    def different_failure(_q: str, mult: int):
        return {"verdict": "UNKNOWN_BUDGET" if mult < 5 else "UNKNOWN_NO_SOLUTION"}

    r = calibrate(bucket_of("x + 3 = -7"), different_failure)
    ok = r.outcome == "reclassify"
    print(f"[{'ok  ' if ok else 'FAIL'}] calibration: not a capacity problem after all")
    print(f"        got {r.outcome} — {r.reason}")
    if not ok:
        failures.append("calibration: not a capacity problem after all")
    print()

    # 4. One query freed, one still limit-bound. Neither verdict about "the
    #    bucket" is true, because the bucket is not one thing. This case
    #    caught a real error in the first version of `calibrate`, which saw a
    #    single non-limit verdict at the top rung and concluded "this was
    #    never a capacity problem" while a query sat there exhausting its
    #    budget.
    def only_one_answers(q: str, mult: int):
        if mult >= 5 and q.endswith("861"):
            return {"verdict": "ANSWER"}
        return {"verdict": "UNKNOWN_BUDGET"}

    r = calibrate(bucket_of("x + 3 = 940", "x * 7 = 861"), only_one_answers)
    ok = r.outcome == "mixed"
    print(f"[{'ok  ' if ok else 'FAIL'}] calibration: bucket holds more than one cause")
    print(f"        got {r.outcome} — {r.reason}")
    if not ok:
        failures.append("calibration: bucket holds more than one cause")
    print()

    return failures


def _end_to_end_case() -> List[str]:
    """The whole loop, on real failures: a query the math domain genuinely
    cannot answer at current limits → typed verdict → classification →
    calibration re-runs → quarantined proposal → human accept → the same
    query now answers.

    Nothing in this test simulates a verdict. Every arrow in the chain is the
    real function, with only the config file swapped for a temp path so
    accepting the proposal cannot touch the user's actual settings.
    """
    import tempfile
    from pathlib import Path

    from .capacity_calibration import capacity_pass
    from .capacity_ingest import CapacityQuarantine
    from .config import VeraConfig
    from .math_sim import math_ask

    failures: List[str] = []

    # Real failures, recorded with their real verdicts. x=937 exists and sits
    # outside the default 0..200 enumeration.
    bucket = UnknownBucket(normalized=normalize_query("x + 3 = 940"))
    for q in ("x + 3 = 940", "x + 4 = 941"):
        verdict = math_ask(q)["verdict"]
        for _ in range(3):
            bucket.record(q, verdict)

    got = classify(bucket)
    ok = got.classification == "needs_more_capacity"
    print(f"[{'ok  ' if ok else 'FAIL'}] end-to-end: real verdict classifies as capacity")
    print(f"        math_ask('x + 3 = 940') -> {bucket.dominant_verdict()} -> {got.classification}")
    if not ok:
        failures.append("end-to-end: real verdict classifies as capacity")
        return failures
    print()

    with tempfile.TemporaryDirectory() as td:
        cfg_path = Path(td) / "vera_config.json"
        VeraConfig().save(cfg_path)

        quarantine = CapacityQuarantine()
        results = capacity_pass([bucket], VeraConfig.load(cfg_path), quarantine)
        r = results[0] if results else {}
        ok = (r.get("outcome") == "propose" and r.get("queued")
              and r.get("parameter") == "math_solve_limit")
        print(f"[{'ok  ' if ok else 'FAIL'}] end-to-end: calibration queues a verified proposal")
        print(f"        {r.get('parameter')} x{r.get('multiplier')} — {r.get('reason')}")
        if not ok:
            failures.append("end-to-end: calibration queues a verified proposal")
            return failures
        print()

        out = quarantine.accept(0, config_path=cfg_path)
        applied = VeraConfig.load(cfg_path)
        answer = math_ask("x + 3 = 940", solve_limit=applied.math_solve_limit)
        ok = (out.get("ok") and applied.math_solve_limit == out.get("after")
              and answer["verdict"] == "ANSWER" and answer.get("x") == 937)
        print(f"[{'ok  ' if ok else 'FAIL'}] end-to-end: accept applies, and the failure stops failing")
        print(f"        math_solve_limit {out.get('before')} -> {out.get('after')}, "
              f"re-ask -> {answer['verdict']} x={answer.get('x')}")
        if not ok:
            failures.append("end-to-end: accept applies, and the failure stops failing")
        print()

    return failures


def main() -> int:
    print(f"boundary.classify — {len(CASES)} hand-labelled cases\n")
    failures: List[str] = []
    for case in CASES:
        got: BoundaryVerdict = classify(build(case))
        ok = got.classification == case.expect
        if case.expect_subcategory is not None:
            ok = ok and got.subcategory == case.expect_subcategory
        mark = "ok  " if ok else "FAIL"
        print(f"[{mark}] {case.name}")
        print(f"        expected {case.expect}"
              + (f" / {case.expect_subcategory}" if case.expect_subcategory else ""))
        print(f"        got      {got.classification} ({got.reason})"
              + (f" / {got.subcategory}" if got.subcategory else ""))
        if not ok:
            print(f"        why the label: {case.why}")
            failures.append(case.name)
        print()

    print("capacity_calibration.calibrate — 4 cases\n")
    failures.extend(_calibration_cases())

    print("end-to-end — real failure to applied limit\n")
    failures.extend(_end_to_end_case())

    if failures:
        print(f"{len(failures)}/{len(CASES)} misclassified: {', '.join(failures)}")
        print()
        print("A growth loop reading these would act on the wrong diagnosis. "
              "The default answer this classifier falls back to is "
              "'add more facts', which is also the instruction that costs a "
              "human the most to follow.")
        return 1
    print(f"all {len(CASES)} boundary cases + 4 calibration cases behaved as labelled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
