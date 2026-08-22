"""Debug consensus — bug localization by multi-section agreement.

The flagship code-reasoning workflow: independent evidence sections each
nominate candidate cause functions, and a cause is asserted **only when the
sections agree**. No agreement → typed UNKNOWN with the disagreement map
(never a guess, never a majority vote).

Sections (each a different kind of evidence):

  traceback   functions on the error stack (deepest = strongest)
  diff        recently-changed functions (regression prior)
  test        functions reachable from the failing test via the call graph

  ANSWER  ⟺  a unique function is nominated by ≥ min_sections sections
  else       UNKNOWN_SECTION_DISAGREEMENT / UNKNOWN_NO_EVIDENCE

Inputs are plain artifacts (traceback text, changed-function list, failing
test names) laid on top of a `code_ingest` call graph — no LM anywhere.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set

from .code_ingest import FN, calls_of
from .cross_store import CrossStore

_TB_LINE = re.compile(r"in ([A-Za-z_][A-Za-z0-9_]*)")


def traceback_section(store: CrossStore, traceback_text: str) -> List[str]:
    """Known functions on the stack, deepest last (= strongest candidate)."""
    fns = [m.casefold() for m in _TB_LINE.findall(traceback_text or "")]
    return [f for f in fns if store.has(FN + f) and f != "<module>"]


def diff_section(store: CrossStore, changed_functions: Sequence[str]) -> List[str]:
    return [
        f.casefold() for f in changed_functions if store.has(FN + f.casefold())
    ]


def test_section(
    store: CrossStore, failing_tests: Sequence[str], *, max_depth: int = 4
) -> List[str]:
    """Functions reachable from failing tests through forward call edges."""
    out: List[str] = []
    seen: Set[str] = set()
    frontier = [t.casefold() for t in failing_tests if store.has(FN + t.casefold())]
    for _ in range(max_depth):
        nxt: List[str] = []
        for f in frontier:
            for callee in calls_of(store, f).get("calls", []):
                if callee not in seen and store.has(FN + callee):
                    seen.add(callee)
                    nxt.append(callee)
                    out.append(callee)
        frontier = nxt
        if not frontier:
            break
    return out


def locate_bug(
    store: CrossStore,
    *,
    traceback_text: str = "",
    changed_functions: Sequence[str] = (),
    failing_tests: Sequence[str] = (),
    min_sections: int = 2,
) -> Dict[str, Any]:
    """Multi-section consensus over candidate cause functions."""
    sections: Dict[str, List[str]] = {}
    tb = traceback_section(store, traceback_text)
    if tb:
        sections["traceback"] = tb
    df = diff_section(store, changed_functions)
    if df:
        sections["diff"] = df
    ts = test_section(store, failing_tests)
    if ts:
        sections["test"] = ts

    if not sections:
        return {
            "verdict": "UNKNOWN_NO_EVIDENCE",
            "cause": None,
            "sections": {},
            "reason": "no_section_produced_candidates",
        }

    # votes: how many independent sections nominate each function
    votes: Dict[str, Set[str]] = {}
    for name, fns in sections.items():
        for f in fns:
            votes.setdefault(f, set()).add(name)

    # rank: (#sections desc, traceback depth desc, name) — deterministic
    tb_rank = {f: i for i, f in enumerate(tb)}  # later = deeper

    def key(f: str):
        return (-len(votes[f]), -tb_rank.get(f, -1), f)

    ranked = sorted(votes, key=key)
    top = ranked[0]
    n_agree = len(votes[top])
    ties = [f for f in ranked if len(votes[f]) == n_agree and f != top
            and tb_rank.get(f, -1) == tb_rank.get(top, -1)]

    result: Dict[str, Any] = {
        "sections": {k: v for k, v in sections.items()},
        "votes": {f: sorted(s) for f, s in votes.items()},
        "n_sections": len(sections),
    }
    if n_agree >= min_sections and not ties:
        return {
            **result,
            "verdict": "ANSWER",
            "cause": top,
            "agreed_by": sorted(votes[top]),
            "n_agree": n_agree,
        }
    if ties:
        return {
            **result,
            "verdict": "AMBIGUOUS",
            "cause": None,
            "candidates": [top, *ties],
            "reason": "tied_candidates",
        }
    return {
        **result,
        "verdict": "UNKNOWN_SECTION_DISAGREEMENT",
        "cause": None,
        "top_candidate": top,
        "n_agree": n_agree,
        "reason": f"only_{n_agree}_of_{len(sections)}_sections_agree",
    }


# ---------------------------------------------------------------------------
# baselines (for the benchmark): what naive strategies would answer
# ---------------------------------------------------------------------------

def baseline_traceback_top(store: CrossStore, traceback_text: str) -> Optional[str]:
    tb = traceback_section(store, traceback_text)
    return tb[-1] if tb else None


def baseline_recent_change(
    store: CrossStore, changed_functions: Sequence[str]
) -> Optional[str]:
    df = diff_section(store, changed_functions)
    return df[0] if df else None
