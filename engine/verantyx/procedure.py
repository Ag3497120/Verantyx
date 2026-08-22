"""Milestone Q — Procedure: hand-written functions lifted into data.

Context (design discussion, stage 2 of the user's own ARC-AGI-3 roadmap):
math_sim.py's wire_add/wire_sub/etc are correctly described as "developer-
defined procedures mapped onto the cross structure and executed" -- NOT a
system that discovers structure on its own. This module doesn't change
that fact; it changes the REPRESENTATION so a procedure is data
(preconditions/steps/expected_effects), not a fixed Python function --
the first step toward a world where a procedure candidate can be
generated, verified, and quarantined the same way Milestone M already
does for whole modules, but with a much smaller, auditable surface (a
closed instruction set, not arbitrary code -- see procedure_exec.py).

Deliberately NOT wired into math_ask() yet. This is a parallel
representation, verified for equivalence against the existing wire_add
(see the regression check this milestone ships with), not a replacement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class Condition:
    kind: str  # "natural_number" | "within_capacity" | ...
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Step:
    op: str  # must be one of procedure_exec.ALLOWED_OPS -- enforced at execution time, not here
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Effect:
    kind: str  # "digit_written" | "carry_propagated" | "overflow" | ...
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Procedure:
    procedure_id: str
    preconditions: List[Condition]
    steps: List[Step]
    expected_effects: List[Effect]
    budget: int
    status: str = "DEFINED"  # DEFINED | VERIFIED | QUARANTINED | TRUSTED

    def as_dict(self) -> Dict[str, Any]:
        return {
            "procedure_id": self.procedure_id,
            "preconditions": [{"kind": c.kind, "params": c.params} for c in self.preconditions],
            "steps": [{"op": s.op, "args": s.args} for s in self.steps],
            "expected_effects": [{"kind": e.kind, "params": e.params} for e in self.expected_effects],
            "budget": self.budget,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Procedure":
        return cls(
            procedure_id=d["procedure_id"],
            preconditions=[Condition(c["kind"], c.get("params", {})) for c in d.get("preconditions", [])],
            steps=[Step(s["op"], s.get("args", {})) for s in d.get("steps", [])],
            expected_effects=[Effect(e["kind"], e.get("params", {})) for e in d.get("expected_effects", [])],
            budget=d.get("budget", 1000),
            status=d.get("status", "DEFINED"),
        )
