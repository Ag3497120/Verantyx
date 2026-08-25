#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PLANTED — one check of every shape ``tests/unfalsifiable.py`` claims to see.

    python3 tests/corpus/planted_checks.py     # every line prints PASS

Each line here is GREEN and carries a clause that **cannot go red**: the
condition is true by construction, not because the fixture is in a particular
state. Some are wholly unfalsifiable; the ones marked "clause" are honest
checks with a tautology sitting beside the honest part, which is the harder
case and the one that hid a defect for four passes.

The name of each check is its shape id, and ``unfalsifiable.py --self-test``
asserts that the scanner reports exactly these, by that shape. A detector
fixed without a plant here is a guess; a plant here that the scanner misses
is a blind spot with a name.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from mini import store                                      # noqa: E402

FAILURES: list = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name:34} {detail}")
    if not ok:
        FAILURES.append(f"{name}: {detail}")


#: A module constant that is a LIVE CALL — comparing the call against it is
#: comparing one value with itself (finding #1, the first of the eight).
_V = store.view()
ZONES = _V.zones()


def _same_thing(v):
    """B8(a): the tautology is one function call away from the check."""
    return v.seams() == v.seams()


def planted() -> None:
    """Every shape, planted once."""
    v = store.view()
    coll = v.zones()
    sleeve_zones = [z for z in coll if z == "sleeve"]

    # -- T1 — the two sides are one thing ---------------------------------
    check("P-T1-literal", True,
          "the condition is a literal; nothing is measured")
    check("P-T1-twice", v.motto() == v.motto(),
          f"one read written twice: {v.motto()}")
    check("P-T1-module-const", v.zones() == ZONES,
          f"the constant IS this call, evaluated at import: {len(ZONES)}")
    hoisted = v.seams() == v.seams()
    check("P-T1-hoisted-beside", hoisted and len(coll) == 2,
          f"B2: a tautology hoisted into a local, beside an honest clause "
          f"({len(coll)} zones)")
    check("P-T1-chained", v.seams() == v.seams() == 5,
          "B3: the tautology is one link of a chained comparison")
    check("P-T1-helper", _same_thing(v),
          "B8(a): the tautology is inside a helper in this same file")
    served = v.served()
    check("P-T1-subscript", served["zones"] == v.zones(),
          "finding 28: a subscript of a local bound to a call on the same "
          "receiver")

    # -- T2 — a scan that covered nothing ---------------------------------
    unmatched = [z for z in coll if z == "no such zone"]
    check("P-T2-all-empty", all(z for z in unmatched),
          "all() over a scan this condition never sizes")
    bad = []
    for z in unmatched:
        if not z:
            bad.append(z)
    check("P-T2-not-scan", not bad,
          f"`not <scan>` — true when nothing was found AND when nothing was "
          f"scanned ({len(bad)})")
    check("P-T2-len-zero", len(bad) == 0,
          f"B4: the same vacuum written as a count ({len(bad)})")
    check("P-T2-sum-zero", sum(1 for z in unmatched if not z) == 0,
          "B4: the same vacuum written as a sum over a generator")

    # -- T3 — the wrong subject -------------------------------------------
    known = store.draft()
    seen_verdict = known["verdict"]          # this is what teaches the tool
    check("P-T3-verdict-known", "sleeve" not in known,
          f"a verdict-bearing subject, never constrained to ANSWER "
          f"({seen_verdict} is not asserted)")
    quiet = store.quiet_draft()
    check("P-T3-verdict-unread", "sleeve" not in quiet,
          "B8(c): the same shape over a callee no check in this file reads "
          "as ['verdict']")
    check("P-T3-universal: every sleeve is served", v.seams() == 5,
          f"the name quantifies over sleeves; the condition reads one number "
          f"({len(sleeve_zones)} sleeve zones exist and are not touched)")

    # -- T4 — one seed, one transform that may be the identity -------------
    doc = v.served()
    check("P-T4-one-step", store.translate(doc)["zones"] == doc["zones"],
          "both sides grow from `doc`; the only difference is a transform "
          "that is the identity today")
    check("P-T4-two-steps",
          store.translate(store.tidy(doc))["zones"] == doc["zones"],
          "B8(b): the same shape with TWO inserted steps")

    # -- T5 — a ratio that holds at zero ----------------------------------
    left_only = [z for z in coll if z == "nope"]
    right_only = [z for z in coll if z == "nor this"]
    third = [z for z in coll if z == "nor that"]
    check("P-T5-zero-ratio", len(left_only) == len(right_only),
          "two counts nobody pinned, equal at zero")
    check("P-T5-chained", len(left_only) == len(right_only) == len(third),
          "B3: the same ratio written as a chain")

    # -- T6 — the measurement is printed, never asserted -------------------
    check("P-T6-detail-shared", v.motto() == "mini coat",
          f"finding 10: the condition constrains the motto and prints "
          f"{len(v.zones())} zones — the counter shares only the receiver "
          f"name with the condition")
    zone_names = [z.upper() for z in coll]
    check("P-T6-detail-clean", v.motto() == "mini coat",
          f"a number the condition never mentions: {len(zone_names)}")


if __name__ == "__main__":
    print("planted checks — every one of them green, none of them able to "
          "go red\n")
    planted()
    print(f"\n{len(FAILURES)} failed")
    raise SystemExit(1 if FAILURES else 0)
