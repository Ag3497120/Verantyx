#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**THE COAT MUST NOT MOVE — as a number anyone can recompute.**

    python3 tests/coat_digest.py            # print the digests and the
                                            # headline figures
    python3 tests/coat_digest.py --check    # compare against the pinned
                                            # value; exit 1 on any drift
    python3 tests/coat_digest.py --out F    # write the whole snapshot

Every pass of this project has carried a sentence like "the coat is unmoved,
digest 7ce1a667…" — and the pass that tried to VERIFY that number could not
reproduce it, because the script that made it existed only in its author's
scratch directory. A digest whose generator is not in the tree is the same
disease as a check that cannot fail, one level up: it looks like a
measurement, it cannot be contradicted, and nobody can tell the difference.

So this file is the generator, and it is in the tree.

**What is in the digest.** The draft, the marks, the built mesh, the built
seams, both 2000-iteration drapes, the SVG and the extracted headline
figures. Floats are canonicalised to their exact IEEE-754 bit patterns — no
tolerance, no rounding — so a change in the last bit of the last coordinate
is a different number here.

**What is NOT in it.** The served block declaration, which legitimately grew
between passes (params(), settings(), three census keys). That part is
printed under ``full``, and it is not pinned: pinning a shape that is meant
to grow would make this file a nuisance rather than a guard.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: Measured at b1adef4 and at every commit back to cbbd045, and again after
#: the scanner pass that added this file. A different value here means the
#: geometry moved — say so out loud rather than editing this line.
GEOMETRY_DIGEST = "bbc1d025184d1cff58977def178faf49"

#: The sections the geometry digest covers, in this order.
GEOMETRY = ("draft", "marks", "built", "built.seams", "drape_default",
            "drape_k20x64", "svg", "headline")

WHO = "Kodai Motonishi"


def canon(o):
    """Total, type-preserving canonical form. Floats -> exact bit pattern."""
    if isinstance(o, float):
        return ["f64", struct.pack(">d", o).hex()]
    if isinstance(o, bool):
        return ["bool", o]
    if isinstance(o, int):
        return ["int", str(o)]
    if o is None:
        return ["null"]
    if isinstance(o, str):
        return ["str", o]
    if isinstance(o, (list, tuple)):
        return [type(o).__name__, [canon(x) for x in o]]
    if isinstance(o, dict):
        return ["dict", [[canon(k), canon(v)] for k, v in
                         sorted(o.items(), key=lambda kv: repr(kv[0]))]]
    if isinstance(o, set):
        return ["set", sorted(repr(x) for x in o)]
    if hasattr(o, "__dict__"):
        return ["obj:" + type(o).__name__, canon(dict(vars(o)))]
    return ["repr:" + type(o).__name__, repr(o)]


def snapshot():
    """Every measured section of the coat. Refusals are return values."""
    from photoloset import Measures
    from photoloset import garment_marks, garment_pattern, garment_sew

    snap, err = {}, {}

    def rec(name, fn):
        try:
            snap[name] = canon(fn())
        except Exception:                                    # noqa: BLE001
            err[name] = traceback.format_exc(limit=3)
            snap[name] = ["ERROR", err[name].strip().splitlines()[-1]]

    ms = Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 46.0)]:
        ms.measured(spot, value, "cm",
                    source="tape measure, reference coat laid flat", by=WHO)
    ms.measured("sleeve_length", 63.0, "cm",
                source="tape measure, the real coat measured again", by=WHO)
    ms.entries = [m for m in ms.entries
                  if not (m.spot == "sleeve_length" and m.value == 46.0)]

    draft = garment_pattern.draft(ms)
    rec("draft", lambda: draft)
    marks = garment_marks.apply(draft)
    rec("marks", lambda: marks)
    built = garment_sew.build(draft, marks=marks)
    rec("built", lambda: built)
    rec("built.seams", lambda: built["seams"])

    material = {"verdict": "ANSWER", "fabric": "wool melton",
                "gsm": 420.0, "thickness": 0.18, "stiffness": 20.0,
                "source": "supplier spec sheet"}
    # **The two drapes are computed ONCE.** They used to be run twice —
    # once for the digest section and once for the headline — which is 2000
    # iterations x 2 of identical arithmetic and doubled the cost of the one
    # check that has to run inside every whole-suite falsifier. The drape is
    # deterministic (that is the property this file exists to pin), so the
    # same object serves both, and the digest is unchanged: measured
    # bbc1d025184d1cff58977def178faf49 before and after.
    d0 = garment_sew.sew_and_drape(built, material, iterations=2000)
    d1 = garment_sew.sew_and_drape(built, material, iterations=2000,
                                   stitch_k=material["stiffness"] * 64.0)
    rec("drape_default", lambda: d0)
    rec("drape_k20x64", lambda: d1)
    rec("svg", lambda: garment_pattern.to_svg(marks))

    def headline():
        n_notch = sum(len(v) for v in marks["notches"].values())
        return {
            "pieces": [p["name"] for p in draft["pieces"]],
            "n_pieces": len(draft["pieces"]),
            "total_area_cm2": draft["total_area_cm2"],
            "n_formulas": len(draft["formulas"]),
            "notches": n_notch,
            "notch_pairs": len(marks["notch_pairs"]),
            "notch_unpaired": len(marks["notch_unpaired"]),
            "points": len(built["points"]),
            "edges": len(built["edges"]),
            "seams": len(built["seams"]),
            "stitches": d0["seam_gap"]["stitches"],
            "default_worst": d0["seam_gap"]["worst"],
            "default_over": d0["seam_gap"]["over_tolerance"],
            "default_closed": d0["seam_gap"]["closed"],
            "default_verdict": d0["verdict"],
            "k_worst": d1["seam_gap"]["worst"],
            "k_over": d1["seam_gap"]["over_tolerance"],
            "k_closed": d1["seam_gap"]["closed"],
            "k_verdict": d1["verdict"],
        }
    rec("headline", headline)

    def served():
        from photoloset import block as _b
        b = _b.coat()
        d = {}
        for meth in ("pieces", "measures", "formulas", "seams", "settings",
                     "placement", "served"):
            if hasattr(b, meth):
                try:
                    d[meth] = getattr(b, meth)()
                except Exception as exc:                     # noqa: BLE001
                    d[meth] = f"RAISED {type(exc).__name__}: {exc}"
        if hasattr(b, "seam_edges"):
            try:
                d["seam_edges"] = [
                    {"a": getattr(e, "a", None), "b": getattr(e, "b", None),
                     "repr": repr(e)} for e in b.seam_edges()]
            except Exception as exc:                         # noqa: BLE001
                d["seam_edges"] = f"RAISED {type(exc).__name__}: {exc}"
        return d
    rec("served_block", served)
    return snap, err


def digests():
    """The two numbers, plus the headline figures and any section that died."""
    snap, err = snapshot()
    full = hashlib.md5(json.dumps({"snapshot": snap}, sort_keys=True,
                                  separators=(",", ":")).encode()).hexdigest()
    geo = hashlib.md5(json.dumps({k: snap[k] for k in GEOMETRY},
                                 sort_keys=True,
                                 separators=(",", ":")).encode()).hexdigest()
    return {"verdict": "ANSWER" if not err else "UNKNOWN_SECTION_RAISED",
            "geometry": geo, "full": full, "errors": err, "snapshot": snap}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help=f"exit 1 unless the geometry digest is "
                         f"{GEOMETRY_DIGEST}")
    ap.add_argument("--out", default="", help="write the whole snapshot here")
    args = ap.parse_args(argv)

    got = digests()
    print(f"geometry {got['geometry']}  (pinned {GEOMETRY_DIGEST})")
    print(f"full     {got['full']}  (not pinned: the served declaration is "
          f"allowed to grow)")
    head = got["snapshot"].get("headline")
    if head:
        flat = {k[1]: v for k, v in head[1]}
        def show(key):
            v = flat.get(key)
            if not v:
                return "?"
            if v[0] == "f64":
                return repr(struct.unpack(">d", bytes.fromhex(v[1]))[0])
            return str(v[1])
        print(f"  {show('n_pieces')} pieces, {show('total_area_cm2')} cm2, "
              f"{show('n_formulas')} formulas, {show('notches')} notches / "
              f"{show('notch_pairs')} pairs / {show('notch_unpaired')} "
              f"unpaired")
        print(f"  {show('points')} points, {show('edges')} edges, "
              f"{show('seams')} seams, {show('stitches')} stitches")
        print(f"  default worst {show('default_worst')} cm, "
              f"{show('default_over')} over, closed={show('default_closed')}")
        print(f"  stitch_k 20*64 worst {show('k_worst')} cm, "
              f"{show('k_over')} over, closed={show('k_closed')}")
    if got["errors"]:
        print(f"SECTIONS THAT RAISED: {sorted(got['errors'])}")
    if args.out:
        Path(args.out).write_text(json.dumps(got, ensure_ascii=False,
                                             sort_keys=True, indent=0),
                                  encoding="utf-8")
        print(f"snapshot -> {args.out}")
    if args.check:
        if got["geometry"] != GEOMETRY_DIGEST:
            print("THE COAT MOVED — the geometry digest is not the pinned "
                  "one. Say so; do not edit the constant.")
            return 1
        if got["errors"]:
            return 1
        print("the coat did not move")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
