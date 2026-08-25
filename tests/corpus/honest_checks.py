#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HONEST — checks that CAN go red, in the shapes the detectors get wrong.

    python3 tests/corpus/honest_checks.py     # every line prints PASS

This file is the false-positive control. Every line here is a check a
reasonable person would write, and every one of them can fail: change the
fixture and it reddens. ``unfalsifiable.py --self-test`` scans this file and
asserts the reported REAL hits are none — the number that decides whether a
scanner gets left switched on.

It is also the suite the T7 runtime probe re-runs: ``zones()`` is made to
TRACK its store here (a write, then a read that must reflect it), while
``motto()`` is only ever compared against a literal. Statically both look
pinned. Freeze them and only one reddens — which is the whole of B1.
"""
from __future__ import annotations

import copy
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


def honest() -> None:
    st = store.MiniStore()
    v = store.MiniView(st)

    # A reader that TRACKS its store: the write happens here, and the read
    # after it has to carry the write. Freezing zones() reddens this line.
    before = v.zones()
    st.put("zone:3", "cuff")
    after = v.zones()
    check("H-tracks-the-store",
          after == ["collar", "hem", "cuff"] and len(after) == len(before) + 1
          and "cuff" not in before,
          f"a write reached the reader: {before} -> {after}")

    # A reader compared against a literal ONLY. This is what the static T7
    # calls "pinned" and what the runtime probe calls bypassable.
    check("H-motto-against-a-literal", v.motto() == "mini coat",
          f"{v.motto()}")

    # Two DIFFERENT objects that must agree — B6's false positive.
    left = store.MiniView(store.MiniStore())
    right = store.MiniView(store.MiniStore())
    check("H-two-objects-agree", left.zones() == right.zones(),
          f"two stores built apart report the same zones: {left.zones()}")

    # A transform that must MOVE its input — B5's false positive. This is the
    # repair for a T4, not an instance of one.
    doc = v.served()
    check("H-transform-moves-it", store.shout(doc)["motto"] != doc["motto"],
          f"{doc['motto']} -> {store.shout(doc)['motto']}")

    # A copy step is the identity ON PURPOSE: what is measured is the time
    # between the two reads, not the copy.
    snapshot = copy.deepcopy(doc)
    check("H-copy-is-not-a-transform", snapshot == doc,
          "a deepcopy taken here equals the original here")

    # `not all readers are unpinned` — prose that reads like a universal.
    residue = [z for z in v.zones() if z == "sleeve"]
    check("H-prose: not all readers are unpinned",
          len(residue) == 0 and len(v.zones()) == 3,
          f"the word 'all' here is prose, and the count IS pinned "
          f"({len(v.zones())})")

    # A count over a collection that cannot be empty.
    fixed = ["collar", "hem", "cuff"]
    missing = [z for z in fixed if z not in v.zones()]
    check("H-count-over-a-fixed-list", len(missing) == 0,
          f"{len(fixed)} names looked for, {len(missing)} missing")

    # A quantifier whose iterable is sized in the SAME condition.
    check("H-quantifier-is-sized",
          len(v.zones()) == 3 and all(isinstance(z, str) for z in v.zones()),
          f"{len(v.zones())} zones, every one of them a string")

    # A chain that pins its own operands. (`len(x) == len(sorted(x))` would
    # NOT be honest — sorting never changes a length — and the scanner says
    # so, which is why the second operand here is a list written out.)
    wanted = ["collar", "hem", "cuff"]
    check("H-chain-pins-itself", len(v.zones()) == len(wanted) == 3,
          f"{len(v.zones())} == {len(wanted)} == 3")

    # A before/after over one receiver, with the mutation written between.
    was = v.seams()
    st.put("zone:4", "belt")
    check("H-before-and-after", v.seams() == was + 1,
          f"{was} -> {v.seams()} after one more zone")

    # Pinning a constant the PACKAGE declares. After resolution both sides
    # read as the same literal, and the line still goes red the day the
    # package changes it — which is the only reason to write it.
    check("H-pins-a-package-constant",
          store.FROZEN_ZONES == ("collar", "hem"),
          f"the package still declares {store.FROZEN_ZONES}")

    # The detail prints exactly what the condition constrains.
    check("H-detail-is-constrained", len(v.zones()) == 4,
          f"{len(v.zones())} zones")


if __name__ == "__main__":
    print("honest checks — every one of them able to go red\n")
    honest()
    print(f"\n{len(FAILURES)} failed")
    raise SystemExit(1 if FAILURES else 0)
