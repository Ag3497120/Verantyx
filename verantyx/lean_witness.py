"""Lean as a witness type — derivation outside, memory and audit here.

The proof-verification layer of the math plan is deliberately NOT a
verifier built here: Lean's kernel already is one, complete and
maintained. What belongs here is the WITNESS SHAPE — running the
kernel over a self-contained source and returning a typed verdict the
store can hold beside a proposition, the same seat 検証済 URLs and
data-varied witnesses occupy.

## The types keep three different absences apart

    VERIFIED                  the kernel accepted the proof; the facet
                              names the toolchain so the witness is a
                              citation (verified:lean4:<version>)
    UNPROVEN                  THIS source does not check. Never read as
                              "false" — a broken proof of a true
                              theorem lands here too
    UNPROVEN_SORRY            the kernel exits 0 on `sorry` with only a
                              warning; a witness that counted that as
                              verified would be the quietest possible
                              fabrication, so it is caught by name
    UNKNOWN_TOOLCHAIN_MISSING no lean on this machine; not a judgment
    UNKNOWN_BUDGET_EXHAUSTED  the kernel ran out of time; not a
                              judgment either

「証明が無い」と「偽」を混ぜない — the same discipline NOT_ATTESTED
learned, applied at the seam where it matters most.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

#: Both quotings observed in the wild: `sorry` (4.34) and 'sorry'
#: (older releases). Missing either is the quiet-fabrication path.
_SORRY = re.compile(r"declaration uses ['`]sorry['`]")


def lean_binary() -> Optional[str]:
    """The lean executable, elan's user install included."""
    import shutil

    found = shutil.which("lean")
    if found:
        return found
    elan = Path.home() / ".elan" / "bin" / "lean"
    return str(elan) if elan.exists() else None


def verify(source: str, *, timeout: int = 120) -> Dict[str, Any]:
    """Run the kernel over a self-contained Lean source. Typed verdict.

    Self-contained means no imports beyond the prelude (mathlib-backed
    verification needs the built library and is a separate, heavier
    door). Every verdict carries what a reader needs to recount it:
    the toolchain version on success, the kernel's own words on
    failure.
    """
    binary = lean_binary()
    if binary is None:
        return {"verdict": "UNKNOWN_TOOLCHAIN_MISSING",
                "note": "no lean executable; install elan to open this "
                        "witness type"}
    with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lean", delete=False) as tf:
        tf.write(source)
        path = tf.name
    try:
        run = subprocess.run(
            [binary, path], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"verdict": "UNKNOWN_BUDGET_EXHAUSTED", "timeout_s": timeout,
                "note": "the kernel did not finish; that is a budget "
                        "fact, not a judgment on the proposition"}
    finally:
        Path(path).unlink(missing_ok=True)
    out = (run.stdout or "") + (run.stderr or "")
    if run.returncode == 0:
        if _SORRY.search(out):
            return {"verdict": "UNPROVEN_SORRY",
                    "note": "the kernel accepts `sorry` with a warning; "
                            "counting that as verified would be quiet "
                            "fabrication"}
        version = subprocess.run([binary, "--version"], capture_output=True,
                                 text=True).stdout.strip()
        return {"verdict": "VERIFIED",
                "witness": witness_facet(version),
                "toolchain": version}
    return {"verdict": "UNPROVEN",
            "errors": out.strip().split("\n")[:6],
            "note": "this source does not check — which is not a claim "
                    "that the proposition is false"}


def witness_facet(version: str) -> str:
    """The facet a VERIFIED proposition may carry in a store."""
    m = re.search(r"version ([\w.\-]+)", version)
    return "verified:lean4:%s" % (m.group(1) if m else "unknown")
