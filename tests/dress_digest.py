#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**THE SECOND GARMENT, PINNED THE SAME WAY THE FIRST ONE IS.**

    python3 tests/dress_digest.py            # print the digests and the
                                              # headline figures
    python3 tests/dress_digest.py --check    # compare against the pinned
                                              # value; exit 1 on any drift
    python3 tests/dress_digest.py --out F    # write the whole snapshot

``tests/coat_digest.py`` exists because a number nobody can recompute is
not a measurement. This is the same generator, run over the SECOND
garment — the cape dress, now carrying the collar this task added
(bodice + skirt_panel + sleeve + cape + collar, composed through
``compose.compose``, never through a registered garment TYPE). It walks
every door the coat's own digest walks, plus the ones past composition
that only exist for a garment built from parts: stable numbering is not
pinned here (``points.Registry`` is exercised directly by
``tests/run_checks.py``, keyed off object identity rather than a plain
value this script could canonicalise), but composition, marks, the built
mesh and seams, both drape passes, the mannequin (build / align / dress /
clearance), the marker, the BOM, the DXF export and the SVG all are.

**What is in the digest.** compose, marks, built, built.seams, two drape
passes (the default stitch_k, which is PINNED to leave the seam open —
see ``tests/run_checks.py``'s ``compose_builds_a_whole_garment_from_parts``
— and 20*128, which closes it), the mannequin's build/align/dress/
clearance-as-fell/clearance-as-worn, the marker, the BOM, the DXF export,
the SVG, and the extracted headline figures. Floats are canonicalised to
their exact IEEE-754 bit patterns — no tolerance.

**What is NOT in it.** Anything sourced from wall-clock time or a
temp-file path (the DXF ``stamp`` field, which embeds the output path);
those are stripped before canonicalising rather than pinned as an
accident of where this script happened to run.
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

#: Measured on this task's own tree, after ``garment_parts.draft_collar``
#: and its registration in ``parts.py`` were written and
#: ``garment_parts.COLLAR_HEIGHT`` was tuned down to 1.2cm (the default
#: this file started from, 6.0cm, leaves the collar/cape seam 7.9cm apart
#: — 5.9cm over the 2.0cm tolerance — measured, not guessed; see
#: ``tests/falsifiers.py``'s "the collar grows past what the cape can be
#: sewn onto"). A different value here means the dress moved — say so out
#: loud rather than editing this line.
#:
#: **Re-pinned 2026-08-27, at the merge of four parallel worktrees, for
#: two REAL and independently verified reasons — not drift:** (1)
#: ``compose.PLACEMENT_TEMPLATE`` gained an explicit ``"衿": (0.0, 0.0,
#: 0.0)`` entry (an outside check found the collar's placement was
#: falling through to the same numeric silent default this project's own
#: discipline forbids — the VALUE is unchanged, but the "compose" section
#: of this digest hashes the whole composed draft, including the
#: ``placement`` dict's keys, so declaring explicitly what was implicit
#: still moves the byte). (2) ``photoloset/dxf.py`` gained a STYLE table
#: (a separate, cad-app-verify fix — QCAD drew the piece names' kanji as
#: "?" without it), which changes every DXF export this digest covers,
#: dress included. Reproduced twice on this tree, deterministic both
#: times. A different value from THIS one still means the dress moved —
#: say so out loud rather than editing this line.
#: **2026-08-27 に一度だけ動かした。** 前の値は
#: 493f74a274d4dac5a97c0bdf57b20037。動いた原因は分かっていて、
#: `garment_marks.offset_outline` が SEAM_ALLOWANCE に載っていない辺名を
#: 黙って 0.0cm に落としていたのを、`UNKNOWN_SEAM_ALLOWANCE_NOT_STATED`
#: で断るように直したこと。
#:
#: **16節のうち動いたのは marks / dxf / svg の3節だけで、3つとも縮んだ**
#: (100,123→87,909 / 20,209→18,244 / 8,615→8,057 バイト)。compose・built・
#: seams・drape 2種・mannequin 4種・marker・bom・headline は1バイトも
#: 動いていない。効いたのは7裁片のうち**衿ただ一つ**で、「衿の外周 (前)」
#: 「衿の外周 (後)」に幅を述べた者がいなかった — 以前はそこが 0cm になり、
#: 裁ち切り線が出来上がり線と同じ位置に引かれていた。**縫えない型紙が
#: ANSWER として通っていた。**
#:
#: **Re-pinned 2026-08-28, at the merge of the ops-harness batch (eleven
#: agents, garment_marks.py / marker.py / bom.py / structure.py all
#: gaining the assumed/kind/basis/alternatives inference-contract fields
#: on their refusals): only 2 of 16 sections moved, and both GREW —
#: ``marks`` 87,909→89,106 bytes, ``bom`` 4,986→7,400 bytes. Read byte for
#: byte (``diff`` against the pristine tree's snapshot, not eyeballed):
#: every added key is exactly ``assumed_by_edge``/``kind``/``alternatives``/
#: ``no_assumption`` reasons — new descriptive fields on refusals that
#: already existed, not a new numeric value anywhere. ``compose`` / built /
#: seams / drape / mannequin / marker / dxf / svg / headline are all
#: 1 byte identical to the previous pin. A different value from THIS one
#: still means the dress moved — say so out loud rather than editing this
#: line.
#: **2026-08-28 に一度だけ動かした。** 前の値は
#: 4c1dabf60bfafa549f9084d9828b2871。動いたのは marks と bom の2節だけで、
#: どちらも縮まず伸びた(marks 87,909→89,106 / bom 4,986→7,400 バイト)。
#: 中身は `assumed_by_edge`・`kind`・`alternatives`・`no_assumption` の
#: 理由文字列 ── 既存の拒否に説明を足しただけで、数値は1つも動いていない。
#: **Re-pinned 2026-08-30, for one reason, measured rather than assumed:**
#: ``photoloset/dxf.py`` gained a ``PROVENANCE`` layer — per piece, on the
#: drawing itself, where that piece came from (``OBSERVED`` was seen in the
#: photograph; ``PROPOSED``/``INFERRED`` was not; a piece that stated no
#: band is stamped ``UNKNOWN_BAND_NOT_STATED`` rather than left blank).
#: Verified against a worktree of the parent commit rather than eyeballed:
#: **15 of the 16 sections are byte-for-byte identical, and the only one
#: that moved is ``dxf``, 18,244 -> 21,045 bytes — it GREW.** No geometry
#: moved: the layer writes TEXT only and not one line changed, which is why
#: ``compose`` / ``marks`` / built / seams / both drapes / mannequin x4 /
#: ``marker`` / ``bom`` / ``svg`` / ``headline`` did not move a byte.
#: ``tests/coat_digest.py`` is unaffected and still PASSes, because its 8
#: sections do not include a DXF export at all — the two digests
#: disagreeing in exactly this way is itself the check that the change
#: touched what it claimed to touch and nothing else. The drawing's y
#: extent drops 2.4 cm (-37.1 -> -39.5) because the stamp sits below the
#: piece name AND is counted into the extents; not counting it would let
#: written text fall outside the declared range, which would make the
#: range lie about the drawing. A different value from THIS one still
#: means the dress moved — say so out loud rather than editing this line.
#: **2026-08-30 に一度だけ動かした。** 前の値は
#: 99eaa1ff3f965812f200731be9eecb9e。動いたのは 16節のうち ``dxf`` の
#: 1節だけで、縮まず伸びた(18,244→21,045 バイト)。親コミットの作業木と
#: 突き合わせて確かめた ── 残り15節は1バイトも動いていない。増えたのは
#: 裁片ごとの出所の判子(TEXT)で、線は一本も動いていない。
GEOMETRY_DIGEST = "10c2b18193686a320762f70664bbe965"

#: The sections the geometry digest covers, in this order.
GEOMETRY = ("compose", "marks", "built", "built.seams", "drape_default",
            "drape_k20x128", "mannequin_build", "mannequin_align",
            "mannequin_dress", "mannequin_clearance_fell",
            "mannequin_clearance_worn", "marker", "bom", "dxf", "svg",
            "headline")

WHO = "Kodai Motonishi"

#: The measure set this digest is drawn from — the same nine spots
#: ``tests/run_checks.py``'s ``the_dress_walks_every_stage_past_composition``
#: uses, body_length included (the ninth, real tape measurement this task
#: added so the mannequin stage can build at all instead of refusing).
MEASURES = [
    ("chest", 82.0), ("shoulder", 38.0), ("waist", 62.0),
    ("bodice_length", 22.0), ("sleeve_length", 52.0),
    ("hip", 88.0), ("skirt_length", 45.0),
    ("neck", 21.0), ("cape_length", 28.0), ("body_length", 90.0),
]

#: The parts graph. Five instances — bodice, skirt_panel, sleeve, cape,
#: collar — no garment TYPE registered anywhere; ``label`` is a name on
#: the combination, not a capability (``compose.py``'s own
#: ``kind_note``). The collar sits between the bodice's neckline and the
#: cape: bodice/neck -> collar/neck (the collar's inner edge), then
#: collar/collar_edge -> cape/neck (the cape mounts on the collar's OUTER
#: edge — the real construction order for a caped collar, not a fourth
#: thing fighting the bodice for the same port).
DRESS = {
    "parts": [
        {"instance": "bodice:1", "part": "bodice"},
        {"instance": "skirt:1", "part": "skirt_panel",
         "params": {"hi_lo_drop": 22.0}},
        {"instance": "sleeve:1", "part": "sleeve", "params": {"side": "左"}},
        {"instance": "cape:1", "part": "cape"},
        {"instance": "collar:1", "part": "collar"},
    ],
    "connections": [
        {"a": ["bodice:1", "waist"], "b": ["skirt:1", "waist"]},
        {"a": ["bodice:1", "armhole_l"], "b": ["sleeve:1", "armhole_l"]},
        {"a": ["bodice:1", "neck"], "b": ["collar:1", "neck"]},
        {"a": ["collar:1", "collar_edge"], "b": ["cape:1", "neck"]},
    ],
    "port_finish": {
        "cape:1": {"hem": "free", "center_front": "fold",
                   "center_back": "fold"},
        "skirt:1": {"hem": "free", "center_front": "fold",
                    "center_back": "fold"},
        "bodice:1": {"center_front": "fold", "center_back": "fold"},
        "sleeve:1": {"cuff_l": "free"},
        "collar:1": {"center_front": "fold", "center_back": "fold"},
    },
    "label": "ケープワンピース",
}

#: How many of each cut piece the marker/BOM lay onto cloth. 袖(左) is cut
#: twice (mirrored for the right side); every other piece is cut once,
#: on the fold declared in ``port_finish``.
CUT = {"前身頃": 1, "後身頃": 1, "スカート前": 1, "スカート後": 1,
       "袖(左)": 2, "ケープ": 1, "衿": 1}
FABRIC_WIDTH_CM = 150.0
SEAM_ALLOWANCE_CM = 1.5


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
    """Every measured section of the dress. Refusals are return values."""
    from photoloset import bom as _bom
    from photoloset import compose, dxf as _dxf
    from photoloset import garment_marks, garment_pattern, garment_sew
    from photoloset import mannequin as _mq, marker as _mkr
    from photoloset import Measures

    snap, err = {}, {}

    def rec(name, fn):
        try:
            snap[name] = canon(fn())
        except Exception:                                    # noqa: BLE001
            err[name] = traceback.format_exc(limit=3)
            snap[name] = ["ERROR", err[name].strip().splitlines()[-1]]

    ms = Measures()
    for spot, value in MEASURES:
        ms.measured(spot, value, "cm", source="tape measure, this task's "
                    "own dress", by=WHO)

    draft = compose.compose(DRESS, ms)
    rec("compose", lambda: draft)
    marks = garment_marks.apply(draft)
    rec("marks", lambda: marks)
    built = garment_sew.build(draft, marks=marks)
    rec("built", lambda: built)
    rec("built.seams", lambda: built["seams"])

    material = {"verdict": "ANSWER", "fabric": "wool melton",
                "gsm": 420.0, "thickness": 0.18, "stiffness": 20.0,
                "source": "supplier spec sheet"}
    # Two passes, computed once each and reused for both the digest
    # section and the headline — the same discipline coat_digest.py
    # documents for why this halves the cost of the one check that has
    # to run inside every whole-suite falsifier.
    d0 = garment_sew.sew_and_drape(built, material, iterations=2000)
    d1 = garment_sew.sew_and_drape(built, material, iterations=2000,
                                   stitch_k=material["stiffness"] * 128.0)
    rec("drape_default", lambda: d0)
    rec("drape_k20x128", lambda: d1)

    man = _mq.build(ms)
    rec("mannequin_build", lambda: man)
    fell = d1.get("points", [])

    def mannequin_align():
        return _mq.align(man, fell)
    rec("mannequin_align", mannequin_align)

    def mannequin_dress():
        return _mq.dress(man, fell)
    rec("mannequin_dress", mannequin_dress)

    def mannequin_clearance_fell():
        return _mq.clearance(man, fell)
    rec("mannequin_clearance_fell", mannequin_clearance_fell)

    def mannequin_clearance_worn():
        worn = _mq.dress(man, fell)
        return _mq.clearance(man, worn.get("points", []))
    rec("mannequin_clearance_worn", mannequin_clearance_worn)

    def marker():
        return _mkr.lay(draft, FABRIC_WIDTH_CM, CUT, SEAM_ALLOWANCE_CM)
    rec("marker", marker)

    def bom():
        return _bom.estimate(draft, FABRIC_WIDTH_CM, CUT, SEAM_ALLOWANCE_CM)
    rec("bom", bom)

    def dxf():
        out = _dxf.to_dxf(marks)
        # `stamp` (if to_dxf ever grows one the way save() has) would
        # embed a path or a timestamp; to_dxf() does not today, but the
        # pop is defensive rather than assumed.
        if isinstance(out, dict):
            out = dict(out)
            out.pop("stamp", None)
        return out
    rec("dxf", dxf)

    rec("svg", lambda: garment_pattern.to_svg(marks))

    def headline():
        n_notch = sum(len(v) for v in marks.get("notches", {}).values())
        c_worn = mannequin_clearance_worn()
        c_fell = mannequin_clearance_fell()
        return {
            "label": draft.get("label"),
            "pieces": [p["name"] for p in draft.get("pieces", [])],
            "n_pieces": len(draft.get("pieces", [])),
            "total_area_cm2": round(sum(p["area_cm2"]
                                        for p in draft.get("pieces", [])),
                                    1),
            "n_formulas": len(draft.get("formulas", {})),
            "seam_checks": len(draft.get("seam_checks", [])),
            "seam_checks_not_sewable": len([c for c in
                                            draft.get("seam_checks", [])
                                            if not c.get("sewable")]),
            "notches": n_notch,
            "points": len(built.get("points", [])),
            "edges": len(built.get("edges", [])),
            "seams": len(built.get("seams", [])),
            "stitches": d0["seam_gap"]["stitches"],
            "default_worst": d0["seam_gap"]["worst"],
            "default_over": d0["seam_gap"]["over_tolerance"],
            "default_closed": d0["seam_gap"]["closed"],
            "k_worst": d1["seam_gap"]["worst"],
            "k_over": d1["seam_gap"]["over_tolerance"],
            "k_closed": d1["seam_gap"]["closed"],
            "mannequin_vertices": man.get("vertices"),
            "mannequin_faces": len(man.get("faces", [])),
            "clearance_fell_inside": c_fell.get("inside_the_body"),
            "clearance_worn_inside": c_worn.get("inside_the_body"),
            "marker_pieces_laid": marker().get("pieces_laid"),
            "marker_length_cm": marker().get("length_cm"),
            "bom_fabric_m": bom().get("known", {}).get("fabric", {})
                                 .get("quantity"),
        }
    rec("headline", headline)
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
    print(f"full     {got['full']}  (not pinned)")
    head = got["snapshot"].get("headline")
    if head:
        flat = {k[1]: v for k, v in head[1]}
        def show(key):
            v = flat.get(key)
            if v is None:
                return "?"
            if v[0] == "f64":
                return repr(struct.unpack(">d", bytes.fromhex(v[1]))[0])
            if v[0] in ("list", "tuple"):
                return [(x[1] if x[0] == "str" else x) for x in v[1]]
            return str(v[1])
        print(f"  label {show('label')!r}, {show('n_pieces')} pieces "
              f"{show('pieces')}")
        print(f"  {show('total_area_cm2')} cm2, {show('n_formulas')} "
              f"formulas, {show('seam_checks')} seam checks "
              f"({show('seam_checks_not_sewable')} not sewable), "
              f"{show('notches')} notches")
        print(f"  {show('points')} points, {show('edges')} edges, "
              f"{show('seams')} seams, {show('stitches')} stitches")
        print(f"  default worst {show('default_worst')} cm, "
              f"{show('default_over')} over, closed={show('default_closed')}")
        print(f"  stitch_k 20*128 worst {show('k_worst')} cm, "
              f"{show('k_over')} over, closed={show('k_closed')}")
        print(f"  mannequin {show('mannequin_vertices')}v/"
              f"{show('mannequin_faces')}f; as-fell "
              f"{show('clearance_fell_inside')} points inside the body, "
              f"dressed {show('clearance_worn_inside')}")
        print(f"  marker {show('marker_pieces_laid')} pieces laid, "
              f"{show('marker_length_cm')} cm; BOM fabric "
              f"{show('bom_fabric_m')} m")
    if got["errors"]:
        print(f"SECTIONS THAT RAISED: {sorted(got['errors'])}")
    if args.out:
        Path(args.out).write_text(json.dumps(got, ensure_ascii=False,
                                             sort_keys=True, indent=0),
                                  encoding="utf-8")
        print(f"snapshot -> {args.out}")
    if args.check:
        if got["geometry"] != GEOMETRY_DIGEST:
            print("THE DRESS MOVED — the geometry digest is not the pinned "
                  "one. Say so; do not edit the constant.")
            return 1
        if got["errors"]:
            return 1
        print("the dress did not move")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
