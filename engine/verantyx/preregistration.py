"""Stop conditions that live in the code, not only in the document.

Why this exists
---------------
Nine pre-registrations were written on 2026-08-16. Each named its stop
conditions plainly. Seven measurements stopped correctly — because a
person read the number and stopped.

One did not. `build_case_frames` gated its save on C1′ alone while its
pre-registration also carried C2, so a run that failed C2 wrote its files
anyway: 2,079 verbs were removed, 為る/在る/居る among them, and the store
on disk was wrong until the failure was noticed by eye afterwards.

The document was correct. The code did not know about it. A discipline
that depends on someone reading the output is a discipline that holds
until the one time nobody does.

Usage
-----
Declare every pass line as a `Gate`, then write through `guard`. A failing
gate means nothing is written and the refusal says which line failed:

    gates = [Gate("C1", c1_ok, "transitivity separates"),
             Gate("C2", c2_ok, "real kana verbs survive")]
    result = guard(gates, lambda: path.write_text(payload))

`guard` never raises on a failed gate — a failed pass line is an answer,
not an error, and the caller reports it the same way a typed refusal is
reported everywhere else in this project.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class Gate:
    """One pass line, named as its pre-registration names it."""

    name: str
    passed: bool
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"gate": self.name,
                "verdict": "PASS" if self.passed else "FAIL",
                "note": self.note}


def failed(gates: Sequence[Gate]) -> List[Gate]:
    return [g for g in gates if not g.passed]


def guard(gates: Sequence[Gate],
          write: Callable[[], Any],
          *,
          what: str = "output") -> Dict[str, Any]:
    """Run `write` only if every gate passed. Report either way.

    The asymmetry is deliberate: a passing run reports what it wrote, and
    a failing run reports what it did NOT write and why. A silent skip
    would leave the previous file on disk looking current, which is the
    same failure as writing the wrong one.
    """
    bad = failed(gates)
    if bad:
        return {"verdict": "WITHHELD",
                "wrote": None,
                "failed_gates": [g.as_dict() for g in bad],
                "gates": [g.as_dict() for g in gates],
                "note": "%s not written — a pre-registered pass line "
                        "failed, and the stop condition is enforced here "
                        "rather than left to the reader" % what}
    written = write()
    return {"verdict": "WROTE",
            "wrote": str(written) if written is not None else what,
            "gates": [g.as_dict() for g in gates]}


def require_environment(*modules: str) -> Optional[Dict[str, Any]]:
    """G0-style environment gate. Returns a refusal, or None when met.

    A run whose tooling is missing produces small, plausible, entirely
    wrong numbers — measured today: without fugashi the polarity reader
    returns `positive` for 水が流れない and reports it as a result. That
    is worse than an error, so it is one.
    """
    missing = []
    for m in modules:
        try:
            __import__(m)
        except Exception:
            missing.append(m)
    if not missing:
        return None
    return {"verdict": "VOID_ENVIRONMENT",
            "missing": missing,
            "note": "this run is VOID, not a null result — absent tooling "
                    "produces plausible numbers that mean nothing"}
