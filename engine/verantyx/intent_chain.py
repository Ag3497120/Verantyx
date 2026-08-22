"""A framed instruction as a chain that circulates, not a list that drains.

The problem
-----------
`intent_frames.parse` returns compounds flat:

    teamsを開いて課題を確認して
        {"op": ["OPEN", "CHECK"], "args": [{...}, {...}]}

Two frames side by side, with nothing between them. So execution becomes
enter-structure → leave → execute outside → enter again, and whatever the
first stage produced is gone by the time the second one runs. Wiring the
Teams route by hand worked only because a human held the thread.

The relation was never missing from the STRUCTURE. `arm_schema` already
carries it: what OPEN produces is its cause- arm, and what CHECK needs in
order to run is its cause+ arm, and those are the same fact seen from two
sides. The flat list is where it gets thrown away.

So a chain, and the chain circulates
------------------------------------
Each stage is a small cross. Stage n's cause- is stage n+1's cause+. A
stage does not receive arguments; it READS its own cause+ arm, and after
it runs its result is written onto its cause- — which is the next stage's
precondition, already in place.

Three things fall out of that one change, which is the reason to believe
it is the right shape rather than a rearrangement:

    handoff        the cause arms carry it; nobody passes anything
    precondition   a stage whose cause+ is empty cannot run — free
    progress       a lap that places no new arm has not advanced

Stopping
--------
A loop that watches itself can watch itself forever; that is the qwen
degeneration in different clothes. So termination is structural, never a
guessed iteration cap:

    STALLED        a lap placed no new arm. Nothing was learned, so
                   another identical lap will learn nothing either.
    BLOCKED        no stage is ready and none is done — the chain needs
                   something from outside (usually the person).
    UNKNOWN_BUDGET the recorded budget ran out with work still pending.
    DONE           every stage delivered.

Layering
--------
Laps are held here, not written into the store. Intermediate state and
settled fact in one layer is the flat-federation contamination this
project has already measured; the caller lifts finished stages across
deliberately (束ねず重ねる).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .observation import Observation, place

STALLED = "STALLED"
BLOCKED = "BLOCKED"
DONE = "DONE"
#: Every stage ran and the last one established nothing. Not a failure of
#: the harness — the honest outcome of a run that reached its end without
#: finding what it was sent for.
DONE_EMPTY = "DONE_NOTHING_FOUND"
RUNNING = "RUNNING"
BUDGET = "UNKNOWN_BUDGET"


@dataclass
class Stage:
    """One frame, and the two arms that tie it to its neighbours."""

    n: int
    op: str
    args: Dict[str, str]
    #: Filled by the previous stage's delivery. Stage 0 starts satisfied
    #: because the instruction itself is what makes it possible.
    cause_in: List[str] = field(default_factory=list)
    #: Filled by this stage's own delivery.
    cause_out: List[str] = field(default_factory=list)
    delivered: bool = False
    #: Did this stage establish anything, or only run? See Observation.found.
    found: bool = False
    observation: Optional[Observation] = None

    @property
    def ready(self) -> bool:
        return bool(self.cause_in) and not self.delivered

    def arms(self) -> Dict[str, List[str]]:
        if self.observation is None:
            return {}
        return place(self.observation)


def chain(parsed: Dict[str, Any]) -> List[Stage]:
    """Frames → linked stages. A refusal produces no chain."""
    if parsed.get("verdict") != "INTENT":
        return []
    ops = parsed["op"] if isinstance(parsed["op"], list) else [parsed["op"]]
    args = parsed["args"] if isinstance(parsed["args"], list) else [parsed["args"]]
    stages = [Stage(n=i, op=o, args=dict(a or {}))
              for i, (o, a) in enumerate(zip(ops, args))]
    if stages:
        stages[0].cause_in = ["instruction"]
    return stages


class Circulation:
    """Walks the chain, writing each result onto the next stage's arm.

    The caller does the world-facing work — this holds no opinion about
    screens, apps or shells. It says which stage may run, takes what came
    back, and decides whether anything moved.
    """

    def __init__(self, parsed: Dict[str, Any], budget: int = 8) -> None:
        self.stages = chain(parsed)
        self.budget = budget
        self.laps = 0
        self.history: List[Dict[str, Any]] = []

    # -- reading -----------------------------------------------------------

    def _placed(self) -> int:
        return sum(len(v) for s in self.stages for v in s.arms().values())

    def next_stage(self) -> Optional[Stage]:
        for s in self.stages:
            if s.ready:
                return s
        return None

    def status(self) -> str:
        if not self.stages:
            return BLOCKED
        if all(s.delivered for s in self.stages):
            # Every stage ran. Whether the GOAL was reached is a different
            # question, and conflating them is how a harness reports
            # success for a run that found nothing. Measured: 「teamsを開いて
            # 課題を見て」 delivered both stages, saw no 課題 at all, and
            # said DONE.
            if not any(getattr(s, "found", False) for s in self.stages[-1:]):
                return DONE_EMPTY
            return DONE
        if self.laps >= self.budget:
            return BUDGET
        if self.next_stage() is None:
            return BLOCKED
        return RUNNING

    # -- writing -----------------------------------------------------------

    def deliver(self, obs: Observation) -> Dict[str, Any]:
        """Hand back what a stage produced. Returns the lap's verdict.

        Progress is counted in ARMS PLACED, not in steps taken or bytes
        returned. A stage that ran, came back, and established nothing has
        not advanced the chain — and saying so here is the same measurement
        that stops a model re-deriving its way around a wall.
        """
        s = self.next_stage()
        if s is None:
            return {"verdict": self.status(), "note": "走れる段がない"}

        before = self._placed()
        s.observation = obs
        s.delivered = True
        after = self._placed()
        gained = after - before

        # The delivery becomes the next stage's precondition. Only a
        # delivery that established something may do so: handing an empty
        # result forward would let a stage run on a precondition that was
        # never actually met.
        s.found = obs.found()
        # The precondition is satisfied by a FINDING, never by the act of
        # looking. `gained > 0` was the old test and it passed for a stage
        # that established nothing, because the tool name and the subject
        # place arms on their own.
        if s.found and s.n + 1 < len(self.stages):
            s.cause_out = ["stage%d:%s" % (s.n, s.op)]
            self.stages[s.n + 1].cause_in = list(s.cause_out)

        self.laps += 1
        verdict = STALLED if gained == 0 else self.status()
        lap = {"lap": self.laps, "stage": s.n, "op": s.op,
               "arms_gained": gained, "verdict": verdict}
        self.history.append(lap)
        return lap

    def state(self) -> Dict[str, Any]:
        return {
            "status": self.status(),
            "laps": self.laps, "budget": self.budget,
            "arms_placed": self._placed(),
            "stages": [{"n": s.n, "op": s.op, "args": s.args,
                        "ready": s.ready, "delivered": s.delivered,
                        "cause_in": s.cause_in, "cause_out": s.cause_out,
                        "arms": {a: len(v) for a, v in s.arms().items()}}
                       for s in self.stages],
            "history": self.history,
        }
