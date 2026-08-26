#!/usr/bin/env python3
"""Everything CI checks, runnable on your own machine the same way.

    python3 tests/run_checks.py

Each check prints what it measured, not just whether it passed. A check that
only says PASS tells you nothing when it later starts lying.
"""
from __future__ import annotations

import contextlib
import functools
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []
#: Every check name that reported, in order, and the subset that went red.
#: These are the machine-readable form. Do NOT scrape the printed lines:
#: the name is padded into a 34-char field, so any name longer than that
#: runs into its own detail text and column-slicing silently merges the two
#: (that is how a DELETED check hid inside a rising total once already).
REPORTED: list[str] = []
FAILED_NAMES: list[str] = []
#: Declared checks whose code was never reached (see ``section``). These are
#: reported FAIL, but they are NOT evidence that the property is pinned —
#: nothing was measured. A mutation harness must score them as a miss.
NEVER_RAN: list[str] = []
#: Checks that reached their own setup and raised. The property demonstrably
#: did not hold, so this IS a red, but it is printed apart from an ordinary
#: assertion failure so nobody has to guess which happened.
CRASHED_NAMES: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name:34} {detail}")
    REPORTED.append(name)
    if not ok:
        FAILED_NAMES.append(name)
        FAILURES.append(f"{name}: {detail}")


@contextlib.contextmanager
def guard(name: str):
    """**A raise inside one check is that check going RED, not the run stopping.**

    Without this, an exception in a check's SETUP aborts the enclosing
    function and every line after it runs neither green nor red — the suite
    reports fewer checks than it appears to, and a mutation harness reading
    the output cannot tell "the property held" from "we never got there".
    Measured: regressing the rival-drops-silently defect used to abort
    ``the_block_lives_on_the_cross`` at ``sides["sides"]``, taking the four
    checks after it with it.

    The block's own ``check()`` call is the last statement inside the guard,
    so a crash always lands on a line that has not reported yet. If a name
    somehow reports twice the second one is renamed, because two verdicts
    under one name is how a count starts lying.
    """
    try:
        yield
    except Exception as exc:                                # noqa: BLE001
        detail = f"CRASHED {type(exc).__name__}: {exc}"
        # **Say when a crash is second-hand.** A guard catches the raise but
        # lets the function continue, so a name bound in the failed setup is
        # missing for every check after it and they all report
        # `UnboundLocalError: local variable 'b'`, which points at the
        # symptom instead of the cause. The first crash in this run is named
        # here so the misleading message cannot be read as the root.
        if CRASHED_NAMES:
            detail += (f" (after {CRASHED_NAMES[0]!r} crashed — likely a "
                       f"consequence of that, not the cause)")
        fired = name if name not in REPORTED else f"{name} (after)"
        CRASHED_NAMES.append(fired)
        check(fired, False, detail[:200])


@contextlib.contextmanager
def section(*names: str):
    """**Every name declared here reports exactly once, or the run is lying.**

    ``guard`` covers a raise INSIDE a check. It cannot cover a raise before
    any guard is entered — most importantly the function's own imports,
    because ``garment_pattern`` and ``garment_sew`` build the coat at module
    scope, so a regressed store raises on IMPORT. Measured: mutation "P2b
    resolution goes back to core-local" raised ``ValueError:
    UNKNOWN_NOT_IN_CROSS: param:ease_in_cm`` out of that import and eight
    named checks ran neither green nor red — the suite printed 66 lines and
    called itself whole.

    So the section declares its names up front. Whatever happens, on the way
    out any name that has not reported is reported FAIL. **A check that did
    not run is not a check that passed**, and the count printed at the end is
    the count that was actually measured.
    """
    start = len(REPORTED)
    why = "the section ended before this line was reached"
    try:
        yield
    except BaseException as exc:                             # noqa: BLE001
        why = f"CRASHED before this line: {type(exc).__name__}: {exc}"[:160]
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        seen = set(REPORTED[start:])
        for n in names:
            if n not in seen:
                NEVER_RAN.append(n)
                check(n, False, f"NEVER RAN — {why}")


def declares(*names: str):
    """Name a function's checks up front so ``section`` can hold it to them.

    The names live on the wrapper as ``check_names``, which is what
    "no check silently dropped" reads. A retired check has to be deleted
    from this list by hand, in a diff, which is the point: the last one
    that went missing left no trace but a total that kept rising.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper() -> None:
            with section(*names):
                fn()
        wrapper.check_names = tuple(names)
        return wrapper
    return deco


#: **The coat's served content, pinned as literals.** These exist because
#: `garment_pattern.FORMULAS` and `garment_sew.SEAMS` are themselves read off
#: the coat's store, so comparing the reader's output against them compared a
#: value with itself: `b.formulas() == garment_pattern.FORMULAS` is
#: `blk.coat().formulas() == blk.coat().formulas()`. Measured: replacing
#: BlockView.formulas()/seams() with dict literals that never touch the store
#: left both checks GREEN. A literal here cannot be quietly re-derived.
FORMULA_NAMES = [
    "身頃幅 (前後それぞれ)", "袖ぐり深さ", "肩線の下がり", "衿ぐり幅 (前後共通)",
    "前衿ぐり深さ", "後衿ぐり深さ", "袖山の高さ", "袖幅 (袖口側)", "袖山の幅",
    "いせ込み", "肩先の位置 (x)", "後袖ぐりの control 点 (x)",
    "前袖ぐりの control 点 (x)", "袖ぐりの control 点 (y)",
    "袖山の control 点 (x)", "袖山の control 点 (y)", "袖山の幅の解き方",
]

SEAM_LABELS = [
    "('前身頃', '肩線') ↔ ('後身頃', '肩線')",
    "('前身頃', '脇線') ↔ ('後身頃', '脇線')",
    "袖/袖山(前半) ↔ 前身頃/袖ぐり",
    "袖/袖山(後半) ↔ 後身頃/袖ぐり",
    "袖/袖下線(右) ↔ 袖/袖下線(左)",
]


def _seam_label(spec: dict) -> str:
    """A seam's name as the store keys it — explicit label, else the two ends."""
    if spec.get("label"):
        return spec["label"]
    return f'{tuple(spec["a"])} ↔ {tuple(spec["b"])}'


#: **Every check this suite runs, by name, pinned.** A check that is deleted
#: has to be deleted from THIS LIST, in a diff, with a reason — which is the
#: whole point. Measured: between cbbd045 and 3ed3f3c exactly one name
#: disappeared ("coat fills its root node exactly") while the total went
#: 58 -> 74, and the claim shipped as "58/58 existing checks still pass". A
#: rising total hides a retirement perfectly; a pinned set cannot.
#:
#: The honest statement of that history is: **57 of the 58 kept, 1 retired
#: deliberately, 24 added, 81 check lines green.** The retirement is recorded
#: in RETIRED_CHECKS below and its replacement names the reason inline.
#:
#: On the arithmetic, because it is easy to state loosely and this list
#: exists to stop exactly that: the suite prints **81** check lines. 80 of
#: them are pinned here and reported before the pin runs; the 81st IS the
#: pin ("no check went missing"), which cannot count itself. One name,
#: "unknown port refused", legitimately runs TWICE (two ports), so this list
#: carries it twice as well — the pin compares multiplicity, not a set, so a
#: check quietly running one fewer time is a failure too.
ALL_CHECK_NAMES = [
    "a marker refuses what it cannot know",
    "the seam allowance is inside the fabric it needs",
    "more copies need more fabric",
    "the same order lays the same marker",
    "a BOM names its known lines and its refused lines",
    "the BOM's fabric line is the marker's, not a second calculation",
    "the BOM's thread line depends on the ratio it names",
    "there is no body below the dress form",
    "the garment is moved onto the form without changing shape",
    "clearance is measured on the garment as it fell",
    "the clearance states partition every point",
    "closing a dart shortens the edge by the intake",
    "a dart whose apex leaves the panel is refused",
    "truing moves the dart until the legs match",
    "a dart never edits the outline it sits on",
    "overlapping darts are refused and separated ones are not",
    "a dart is addressed in the stable numbering",
    "the DXF file parses as group-code pairs",
    "every draft vertex survives to its DXF coordinate",
    "the cut line and sewing line are different curves on separate layers",
    "DXF notch and grain lines land at the marks' own positions",
    "the DXF round-trips into rebuilt piece areas",
    "a number is a function of its address",
    "adding a piece never moves a number",
    "a reshaped outline is refused, not renumbered",
    "a span across two edges is refused",
    "the registry round-trips",
    "no third-party imports",
    "example runs",
    "example shows UNKNOWN_NO_ADOPTER",
    "example shows CONTESTED_MEASUREMENT",
    "example shows ANSWER",
    "draft answers",
    "three pieces",
    "area 7306.1 cm2",
    "17 formulas printed",
    "seam checks self-report",
    "16 notches, 8 paired",
    "default stitch_k leaves it open",
    "64x closes it",
    "the coat has not moved",
    "0 untranslated",
    "the untranslated residue is measured",
    "pieces read in English",
    "SVG geometry untouched",
    "coat's arms are the three dualities",
    "empty arms are typed gaps",
    "formulas served from the cross",
    "seams served from the cross",
    "a fifth face is refused",
    "conflicting declarations go contested",
    "placement does not move answers",
    "round trip moves nothing",
    "the whole declaration is served from the cross",
    "arms are derived, not chosen",
    "support- is never written, only emerges",
    "absence is not a claim",
    "agreement does not consume seats",
    "a generic claim needs two sources",
    "a seat carries every kind that reached it",
    "a specific claim cannot buy a generic one",
    "ordered reads follow the declaration",
    "ingest order does not move answers",
    "two subjects cannot declare the same thing",
    "a seat that cannot name itself is refused",
    "contest is reachable at every address",
    "a contest survives the matryoshka",
    "an edge with one end is refused",
    "reads create nothing, loads are verified",
    "the store owns its values",
    "equal is not the same observation",
    "the quarantine core obeys the same law",
    "a fourth piece and a fifth measurement are declarable",
    "an undeclared subject does not swallow the seat",
    "param refuses across subjects",
    "a proposal stays quarantined",
    "an anonymous source buys nothing",
    "the store refuses what it cannot persist",
    "a generic claim is priced by its own kind",
    "the budget arm is reported, never hidden",
    "the loader never raises",
    "unknown slot refused",
    "unknown variant refused",
    "undraftable variant refuses by name",
    "assembled declaration lives on the cross",
    "skirt drafts through the shared engine",
    "skirt marks pair and face outward",
    "skirt sews shut hanging from the waist",
    "per-model prompts with versions",
    "discipline is inside every prompt",
    "siglip bank covers the part vocabulary",
    "valid decomposition accepted with provenance",
    "confidence numbers refused",
    "unknown port refused",
    "unknown part family refused",
    "malformed json refused",
    "everything lands as proposals",
    "unknown part refused",
    "unknown port refused",
    "open ports are named, never filled",
    "cape dress composes from parts",
    "the type name is only a label",
    "allowances face outward on every part",
    "the composed dress sews shut",
    "zones are numbered deterministically",
    "applying a delta records what changed",
    "measures never move",
    "unknown zone refused",
    "the adjusted dress still sews shut",
    "the coat has no zones (untouched path)",
    "the dress has no notches yet, and marks says so honestly",
    "a dress piece keeps its number when a piece is inserted ahead of it",
    "a dart on the dress front closes at the address it sits",
    "the dress mannequin refuses the measure set the dress actually has",
    "the dress marker lays seven cut pieces onto real cloth",
    "the dress BOM answers fabric and refuses three lines it cannot know",
    "the dress reaches DXF directly, because save() cannot draft it",
    "initialize",
    "61 tools",
    "every tool has a schema",
    "a refusal is typed, and the reply is JSON",
    "the sweep writes into a HOME of its own",
    "every tool returns an object",
    "absent tools say so",
    "anonymous adoption refused",
    "reads follow a second declaration",
    "the arm census counts the store it is given",
    "dump carries the store it read",
    "unbought generics come from the store",
    "the library census counts its own store",
    "retrieval without a backend refuses by name",
    "an empty result is not a refusal",
    "a whole-image backend cannot answer a per-part question",
    "photoloset registers no backend at import",
    "a fixture cannot pass as a backend",
    "a retrieval hit is unreadable at the part address",
    "two sources that disagree become contested, not ranked",
    "one corpus cannot buy a generic construction claim",
    "a search that found nothing is not seated",
    "a retrieved family with no procedure refuses the whole construction",
    "the constructed graph names every part the retrieval named",
    "instance numbering does not move between rounds",
    "the confirmation solid is built from the composed pieces",
    "the sheet states what the render does not claim",
    "a rejection must name a claim",
    "an open port becomes a claim, not a silent default",
    "an approval carries the name of the approver",
    "an approval names the claims it accepted",
    "an approval dies when the shape moves",
    "approval writes through the same door as an adoption",
    "the sewing search has no argument for an unapproved shape",
    "the sewing search refuses an unknown approval",
    "a stale approval does not open the search",
    "the sewing search names the corpora that would close it",
    "an embedding backend cannot be a construction corpus",
    "two corpora from one root are not two sources",
    "a repeated structural rejection escalates to a human",
    "convergence counts a rejected claim",
    "a new address continues the loop",
    "agreement is a fixed point without another round",
    "a contradiction is terminal, not a retry",
    "storage order can stop the loop, not just the address map",
    "reopening an adopted address needs a name",
    "the same rejected claim escalates, a different one each round does not",
    "no check that cannot fail",
    "every served reader reads its store",
    "the scanner finds every planted shape",
    "the falsifier harness reports every mutation",
    "a closed sphere totals four pi by angle defect",
    "a developable cylinder carries no curvature",
    "the mannequin's total curvature converges while its band "
    "distribution does not",
    "the curvature report shares the total, it does not compute a dart "
    "intake",
    "curvature refuses missing measurements and a grid too coarse to "
    "triangulate",
]

#: Checks that once existed and no longer do. Retiring one is allowed;
#: retiring one SILENTLY is not.
RETIRED_CHECKS = [
    ("coat fills its root node exactly", "cbbd045",
     "It asserted every root arm sat at exactly 4/4 (`all(len(s) == "
     "FACES_PER_ARM for s in root.values())`) back when a core was a dict of "
     "arm -> seats and the arms were storage drawers. Under the three "
     "dualities that assertion is false BY DESIGN: the coat holds 0 measured, "
     "0 cited and 0 generic claims, so support+ and kind+ are legitimately "
     "empty and are reported as typed gaps instead. Keeping it would have "
     "forced the arms back into being drawers to make a line green. Its "
     "replacement, \"coat's arms are the three dualities\", measures the "
     "actual distribution (10 cores, 56 seats, root kind- 17 / cause+ 10 / "
     "support+ 0 / kind+ 0) and pins over_capacity, and it has a falsifier."),
]


# ---------------------------------------------------------------------------
def the_example_runs() -> None:
    """The README's example is the one thing a reader runs first."""
    r = subprocess.run([sys.executable, "examples/black_coat.py"],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = r.stdout
    # The line count sat in the DETAIL and not in the condition, so an
    # example that exits 0 while printing nothing at all passed. Measured:
    # `print` rebound to a no-op in examples/black_coat.py left this line
    # green ("exit 0, 0 lines") while its three siblings went red. The
    # number was already being computed — it just was not being asserted.
    check("example runs",
          r.returncode == 0 and len(out.splitlines()) == 102,
          f"exit {r.returncode}, {len(out.splitlines())} lines")
    for want in ("UNKNOWN_NO_ADOPTER", "CONTESTED_MEASUREMENT", "ANSWER"):
        check(f"example shows {want}", want in out,
              "present" if want in out else "MISSING — the refusal stopped firing")


# ---------------------------------------------------------------------------
def the_pipeline_still_agrees() -> None:
    """The numbers the README quotes, re-measured."""
    from photoloset import Measures
    from photoloset import garment_marks, garment_pattern, garment_sew

    ms = Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")

    draft = garment_pattern.draft(ms)
    # `verdict == "ANSWER"` alone asks the code under test for its own
    # verdict and believes it — a drafter that always says ANSWER keeps it
    # green. The second clause makes the word mean something: the SAME call
    # with nothing measured has to refuse, so "ANSWER" is a decision rather
    # than a constant.
    refused_draft = garment_pattern.draft(Measures())
    check("draft answers",
          draft["verdict"] == "ANSWER"
          and refused_draft["verdict"] == "UNKNOWN_MISSING_MEASUREMENTS",
          f'{draft["verdict"]}; the same call with no measurements is '
          f'{refused_draft["verdict"]}')
    check("three pieces", len(draft["pieces"]) == 3,
          str([p["name"] for p in draft["pieces"]]))
    check("area 7306.1 cm2", abs(draft["total_area_cm2"] - 7306.1) < 0.05,
          f'{draft["total_area_cm2"]} cm2')
    check("17 formulas printed", len(draft["formulas"]) == 17,
          f'{len(draft["formulas"])}')
    structural = [c for c in draft["seam_checks"] if c.get("structural")]
    # `len(structural) == len(seam_checks)` is 0 == 0 on an empty list and
    # true for any subset that matches in size. Measured: truncating the
    # drafted seam checks to one of three, and to none at all, both left the
    # whole suite green. The coat has THREE and the README quotes three, so
    # both numbers are pinned.
    check("seam checks self-report",
          len(draft["seam_checks"]) == 3 and len(structural) == 3,
          f'{len(structural)}/{len(draft["seam_checks"])} labelled structural')

    marks = garment_marks.apply(draft)
    notches = sum(len(v) for v in marks["notches"].values())
    check("16 notches, 8 paired",
          notches == 16 and len(marks["notch_pairs"]) == 8
          and not marks["notch_unpaired"],
          f'{notches} notches, {len(marks["notch_pairs"])} pairs, '
          f'{len(marks["notch_unpaired"])} unpaired')

    built = garment_sew.build(draft, marks=marks)
    mat = {"verdict": "ANSWER", "fabric": "wool melton", "gsm": 420.0,
           "thickness": 0.18, "stiffness": 20.0}
    # The engine default (16x) does NOT close this garment — that is measured
    # and stated in the README. If it ever starts closing, the README is wrong.
    loose = garment_sew.sew_and_drape(built, mat, iterations=2000)["seam_gap"]
    # **The invariant is a DISTANCE.** `not closed` is a boolean the engine
    # computes from that distance, and the distance itself was printed at
    # five sites in this file and asserted at none — so the coat could move
    # by any amount short of closing and every line still said PASS.
    check("default stitch_k leaves it open",
          not loose["closed"] and round(loose["worst"], 4) == 0.9154
          and loose["over_tolerance"] == 15 and loose["stitches"] == 41,
          f'worst {loose["worst"]} cm, {loose["over_tolerance"]}/'
          f'{loose["stitches"]} over tolerance')
    tight = garment_sew.sew_and_drape(built, mat, iterations=2000,
                                      stitch_k=20.0 * 64)["seam_gap"]
    check("64x closes it",
          tight["closed"] and tight["over_tolerance"] == 0
          and round(tight["worst"], 4) == 0.0614,
          f'worst {tight["worst"]} cm, {tight["over_tolerance"]} over')

    # **THE COAT MUST NOT MOVE — as a number anyone can recompute.**
    # Every pass of this project has carried a sentence like "the coat is
    # unmoved, digest 7ce1a667…", and the pass that tried to VERIFY that
    # number could not: the script that produced it existed only in its
    # author's scratch directory, so the digest was a measurement nobody
    # but its author could contradict — the same disease as a check that
    # cannot fail, one level up. The generator is in the tree now
    # (tests/coat_digest.py), it canonicalises floats to their IEEE-754
    # bit patterns with no tolerance, and the suite runs it.
    sys.path.insert(0, str(ROOT / "tests"))
    import coat_digest
    coat = coat_digest.digests()
    figures = {k[1]: (v[1] if v[0] != "f64"
                      else round(struct.unpack(">d", bytes.fromhex(v[1]))[0],
                                 4))
               for k, v in coat["snapshot"]["headline"][1]}
    check("the coat has not moved",
          coat["geometry"] == coat_digest.GEOMETRY_DIGEST
          and not coat["errors"]
          and coat_digest.GEOMETRY_DIGEST
          == "bbc1d025184d1cff58977def178faf49"
          and len(coat_digest.GEOMETRY) == 8
          and figures["n_pieces"] == "3" and figures["n_formulas"] == "17"
          and figures["notches"] == "16" and figures["notch_pairs"] == "8"
          and figures["notch_unpaired"] == "0"
          and figures["points"] == "303" and figures["edges"] == "954"
          and figures["seams"] == "5" and figures["stitches"] == "41"
          and figures["total_area_cm2"] == 7306.1
          and figures["default_worst"] == 0.9154
          and figures["default_over"] == "15"
          and figures["default_closed"] is False
          and figures["k_worst"] == 0.0614 and figures["k_over"] == "0"
          and figures["k_closed"] is True,
          f'geometry {coat["geometry"]} over {len(coat_digest.GEOMETRY)} '
          f'sections (draft, marks, mesh, seams, both 2000-iteration drapes, '
          f'the SVG and the headline), floats as IEEE-754 bit patterns, no '
          f'tolerance — recomputable by anyone with '
          f'`python3 tests/coat_digest.py --check`; '
          f'{figures["n_pieces"]} pieces, {figures["total_area_cm2"]} cm2, '
          f'{figures["points"]}/{figures["edges"]}/{figures["seams"]}/'
          f'{figures["stitches"]}, worst {figures["default_worst"]} and '
          f'{figures["k_worst"]} cm'
          + (f' — SECTIONS RAISED {sorted(coat["errors"])}'
             if coat["errors"] else ''))


# ---------------------------------------------------------------------------
def english_is_complete() -> None:
    """The README claims 0 untranslated across every output path."""
    from photoloset import Ledger, Measures, i18n
    from photoloset import garment_drape, garment_marks, garment_pattern, garment_sew
    from photoloset.garment import PARTS
    from photoloset.garment_measure import SPOTS

    led = Ledger(title="ci")
    led.propose("collar", "shape", "notched lapel", source="frame")
    led.adopt("collar", "shape", "notched lapel", by="ci")
    led.infer("body", "silhouette", "A-line", source="from the hem")
    ms = Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")
    ms.ratio("waist", 0.62, basis="chest", source="assumed")
    ms.measured("sleeve_length", 46.0, "cm", source="again", by="ci")

    outs = {
        "ledger.spec": led.spec(), "ledger.worklist": led.worklist(),
        "ledger.techpack": led.techpack(), "ledger.timeline": led.timeline(),
        "ledger.state": [led.state(p, a) for p, asp in PARTS.items() for a in asp],
        "measures.sheet": ms.sheet(),
        "measures.state": [ms.state(s) for s in SPOTS],
    }
    ms.entries = [m for m in ms.entries
                  if not (m.spot == "sleeve_length" and m.value == 46.0)]
    draft = garment_pattern.draft(ms)
    marks = garment_marks.apply(draft)
    built = garment_sew.build(draft, marks=marks)
    mat = {"verdict": "ANSWER", "fabric": "f", "gsm": 420.0,
           "thickness": 0.18, "stiffness": 20.0}
    outs["draft"] = draft
    outs["marks"] = marks
    outs["built"] = built
    outs["drape"] = garment_sew.sew_and_drape(built, mat, iterations=200,
                                              stitch_k=20.0 * 64)
    outs["drape.validate"] = garment_drape.validate(40, 40, mat, iterations=100)
    outs["no_material"] = garment_drape.material_from(None, "cupro")
    outs["svg"] = garment_pattern.to_svg(marks)
    outs["draft.refused"] = garment_pattern.draft(Measures())

    # The second garment rides the same promise: every output path the
    # assembler can produce must translate too.
    from photoloset import assemble as _asm
    from photoloset import block as _blk
    from photoloset import garment_skirt as _skirt

    ms2 = Measures()
    for spot, value in [("waist", 64.0), ("hip", 90.0),
                        ("skirt_length", 58.0)]:
        ms2.measured(spot, value, "cm", source="tape", by="ci")
    a2 = _asm.assemble({"silhouette": "Aライン",
                        "closure": "ゴムウエスト（開き無し）",
                        "waist_finish": "シャーリング"})
    if a2["verdict"] == "ANSWER":
        d2 = a2["declaration"]
        st2, root2 = _blk.ingest(decl=d2, formulas=d2["formulas"])
        v2 = _blk.BlockView(st2, root2)
        sd = _skirt.draft(ms2, v2)
        sm = garment_marks.apply(sd)
        outs["skirt.draft"] = sd
        outs["skirt.marks"] = sm
        outs["skirt.built"] = garment_sew.build(sd, marks=sm)
        outs["skirt.draft.refused"] = _skirt.draft(Measures(), v2)

    # The composed garment rides the same promise.
    from photoloset import compose as _cp
    from photoloset import garment_sew as _gs
    ms3 = Measures()
    for spot, value in [("chest", 82.0), ("shoulder", 38.0), ("waist", 62.0),
                        ("bodice_length", 22.0), ("sleeve_length", 52.0),
                        ("hip", 88.0), ("skirt_length", 45.0),
                        ("neck", 21.0), ("cape_length", 28.0)]:
        ms3.measured(spot, value, "cm", source="tape", by="ci")
    dress = {
        "parts": [
            {"instance": "bodice:1", "part": "bodice"},
            {"instance": "skirt:1", "part": "skirt_panel",
             "params": {"hi_lo_drop": 22.0}},
            {"instance": "sleeve:1", "part": "sleeve",
             "params": {"side": "左"}},
            {"instance": "cape:1", "part": "cape"}],
        "connections": [
            {"a": ["bodice:1", "waist"], "b": ["skirt:1", "waist"]},
            {"a": ["bodice:1", "armhole_l"],
             "b": ["sleeve:1", "armhole_l"]},
            {"a": ["bodice:1", "neck"], "b": ["cape:1", "neck"]}],
        "port_finish": {
            "cape:1": {"hem": "free", "center_front": "fold",
                       "center_back": "fold"},
            "skirt:1": {"hem": "free", "center_front": "fold",
                        "center_back": "fold"},
            "bodice:1": {"center_front": "fold", "center_back": "fold"},
            "sleeve:1": {"cuff_l": "free"}},
    }
    rc = _cp.compose(dress, ms3)
    outs["composed"] = rc
    outs["composed.marks"] = garment_marks.apply(rc)
    outs["composed.refused"] = _cp.compose(
        {**dress, "port_finish": {}}, ms3)

    # **The refusals of the newly load-bearing modules ride the same
    # promise.** They did not, and 67 strings across block/cross/parts/
    # zones/prompts were untranslated while the README said 0. A refusal a
    # caller cannot read is the one string that most needs translating, so
    # every refusal-bearing path is swept here now. What is deliberately
    # NOT swept — the store's ADDRESSES (to_dict, write_plan, seats,
    # seam_edges: core names and seat keys) and the prompt bank's text,
    # which is written for the model — is stated in README.md with its
    # measured number, because a scope nobody writes down is how "0"
    # stopped being true.
    from photoloset import cross as _cross
    from photoloset import parts as _parts
    from photoloset import prompts as _prompts
    from photoloset import zones as _zones

    _st = _cross.CrossStore()
    _st.put("c", "k", 1, "specific", "s")
    outs["cross.resolve.absent"] = _st.resolve("c", "no:such:key")
    outs["cross.put.no_such_kind"] = _st.put_strict("c", "k2", 1, "guess", "s")
    outs["cross.put.unnamed_source"] = _st.put_strict("c", "k3", 1, "generic")
    outs["cross.put.unpersistable"] = _st.put_strict("c", "k4", {1, 2},
                                                     "specific", "s")
    # ...and the four refusals this pass added. A refusal that only exists
    # in Japanese is the one string a caller most needs, so each of them is
    # swept from the day it is written rather than the pass after.
    outs["cross.put.non_finite"] = _st.put_strict("c", "k5", float("inf"),
                                                  "measured", "tape")
    outs["cross.put.bad_address"] = _st.put_strict(("b", "c"), "k", 1,
                                                   "measured", "s")
    _q = _cross.CrossStore()
    _q.put("q", "x", 1, "proposed", "someone said")
    outs["cross.put.in_quarantine"] = _q.put_strict("q#proposed", "chest",
                                                    108.0, "measured", "tape")
    _empty = _cross.CrossStore.from_dict(
        {"cores": {"c": [{"key": "k", "arm": None, "seq": 1, "values": []}]},
         "edges": []})
    outs["cross.resolve.empty_seat"] = _empty.resolve("c", "k")
    outs["cross.load.malformed"] = _cross.CrossStore.from_dict_checked(
        {"cores": {"c": [{"key": ["a"], "arm": None, "seq": "x",
                          "values": [{"value": 1, "kind": "proposed",
                                      "sources": "s"}]}]},
         "edges": [1], "quarantine": 3})["detail"]
    outs["cross.link.dangling"] = _st.link(("nope", ""), ("c", ""), "nest")
    # ...and the measurement writer's own refusals, which reach a caller
    # through the MCP boundary as {verdict, why} — the shape _refused makes.
    for _label, _bad in (("not_a_number", "abc"), ("not_finite", "nan")):
        try:
            Measures().measured("chest", _bad, "cm", "tape")
        except ValueError as _e:
            outs[f"measures.refused.{_label}"] = {
                "verdict": str(_e).split(":")[0], "why": str(_e)}
    outs["parts.unbought_generics"] = _parts.Library().unbought_generics()
    outs["zones.parse_selection.bad"] = _zones.parse_selection("99", {})
    outs["prompts.parse.bad"] = _prompts.parse_decomposition("default",
                                                             "{oops")

    # **The look loop rides the same promise, from the day it is written.**
    # Its three new modules answer in English (like `mcp.py`, the boundary
    # they are read through) and `compose.graph_from` answers in Japanese
    # like the file it lives in — so this sweep is what says the mixture is
    # complete rather than a sentence claiming it is. The path that was
    # untranslated when it was added: graph_from's whole refusal.
    from photoloset import confirm as _confirm
    from photoloset import garment_rights as _rights_mod
    from photoloset import resemble as _resemble
    from photoloset import sewing_search as _search
    from photoloset.garment import Ledger as _Ledger

    _resemble.reset()
    _search.reset()
    _look = [{"instance": "bodice:1", "part": "bodice"},
             {"instance": "cape:1", "part": "cape"},
             {"instance": "skirt_panel:1", "part": "skirt_panel"},
             {"instance": "sleeve:1", "part": "sleeve"}]
    outs["resemble.per_part.refused"] = _resemble.per_part("look.jpg", _look)
    outs["resemble.whole.refused"] = _resemble.whole("look.jpg")
    _resemble.install_fixture({
        "bodice:1": [{"aspect": "family", "family": "bodice",
                      "corpus": "corpusA", "ref": "A", "region": "upper"}],
        "cape:1": [{"aspect": "family", "family": "cape",
                    "corpus": "corpusA", "ref": "A", "region": "shoulders"}],
        "skirt_panel:1": [{"aspect": "family", "family": "skirt_panel",
                           "corpus": "corpusA", "ref": "B"}],
        "sleeve:1": [{"aspect": "family", "family": "sleeve",
                      "corpus": "corpusA", "ref": "A"}]})
    _res = _resemble.per_part("look.jpg", _look, image_id="img1")
    outs["resemble.per_part"] = _res
    _look_store = _cross.CrossStore()
    _look_store.put("garment", "subject", {"name": "the look"}, "declared",
                    "ci")
    outs["resemble.land"] = _resemble.land(_look_store,
                                           _rights_mod.RightsLedger(), _res,
                                           image_id="img1")
    _structure = _resemble.structure_from(_res, image_id="img1")
    _structure["connections"] = [
        {"a": ["bodice:1", "waist"], "b": ["skirt_panel:1", "waist"]},
        {"a": ["bodice:1", "armhole_l"], "b": ["sleeve:1", "armhole_l"]},
        {"a": ["bodice:1", "neck"], "b": ["cape:1", "neck"]}]
    _structure["port_finish"] = {
        "cape:1": {"hem": "free", "center_front": "fold",
                   "center_back": "fold"},
        "skirt_panel:1": {"center_front": "fold", "center_back": "fold"},
        "bodice:1": {"center_front": "fold", "center_back": "fold"},
        "sleeve:1": {"cuff_l": "free"}}
    _structure["label"] = "ケープワンピース"
    outs["resemble.structure_from"] = _structure
    _g = _cp.graph_from(_structure)
    outs["compose.graph_from"] = _g
    outs["compose.graph_from.refused"] = _cp.graph_from(
        {"instances": [{"instance": "c:1", "part": "collar"},
                       {"instance": "m:1", "part": "mantle"}]})
    _draft = _cp.compose(_g["graph"], ms3)
    outs["confirm.solid"] = _confirm.solid_from_draft(_draft)
    _sheet = _confirm.sheet(_draft, image_ref="look.jpg",
                            retrieval=outs["resemble.land"],
                            graph=_g["graph"])
    outs["confirm.sheet"] = _sheet
    outs["confirm.reject.refused"] = _confirm.reject(_sheet, [], "ci")
    _led = _Ledger(title="ci")
    outs["confirm.approve.refused"] = _confirm.approve(
        _sheet, {c["id"]: "yes" for c in _sheet["claims"]}, "", _led)
    _ap = _confirm.approve(_sheet,
                           {c["id"]: "yes" for c in _sheet["claims"]},
                           "ci", _led, graph=_g["graph"])
    outs["confirm.approve"] = _ap
    outs["sewing_search.unapproved"] = _search.methods_for("nope")
    _search.bind(ledger=_led, measures=ms3)
    outs["sewing_search.no_corpus"] = _search.methods_for(_ap["approval_id"])
    _resemble.reset()
    _search.reset()

    swept = sorted(outs.items())
    total_missing = []
    for name, value in swept:
        missing = i18n.missing(i18n.translate(value))
        total_missing += missing
        if missing:
            print(f"        {name}: {missing[:2]}")
    # The count of OUTPUT PATHS swept sat in the detail only, so dropping a
    # path from the sweep was invisible — and the README's "0 untranslated"
    # is only worth what this scope is. Both are pinned here now: the number
    # of paths, and the fact that the newly load-bearing refusal texts are
    # among them (they were not, and 67 strings were untranslated outside
    # this table — see README.md, which now states the scope out loud).
    check("0 untranslated",
          not total_missing and len(swept) == 51,
          f"{len(set(total_missing))} strings across {len(swept)} outputs")

    # **The second number the README states, measured.** "0 untranslated"
    # is only worth what its scope is, and the scope above is 37 output
    # paths chosen for the engine's own results. The README also says what
    # is deliberately OUTSIDE that scope — the store's addresses and the
    # prompt bank's text — with a number beside it, and that number was
    # never measured by anything: it was 67 in one pass and 42 in the next,
    # both written by hand. A sentence nobody measures drifts exactly the
    # way the first one did.
    #
    # So the wide sweep is here, its scope is a list rather than a
    # paragraph, and the residue is CLASSIFIED: an address, a whole
    # Japanese document, or a string from the prompt bank — which is not a
    # hand-kept list either, it is read back out of prompts.for_model.
    # Anything else is prose an English caller was meant to read and this
    # check goes red. Three seat reasons and one how_to_close were exactly
    # that, and they are translated now.
    _b = _blk.coat()
    _store = _b.store
    _lib = _parts.Library()
    wide: dict = {}
    for _m in ("label", "pieces", "measures", "required", "formulas",
               "seams", "seam_edges", "placement", "params", "settings",
               "served", "dump", "gaps", "refusals", "arm_census",
               "sleeve_required", "unbought_generics"):
        wide[f"block.{_m}"] = getattr(_b, _m)()
    for _m in ("to_dict", "write_plan", "census", "contested", "verify",
               "unbought_generics", "aliased_values", "placement_check",
               "edges_are_relations"):
        wide[f"store.{_m}"] = getattr(_store, _m)()
    wide["store.seats"] = _store.seats(_b.root)
    wide["store.resolve"] = _store.resolve(_b.root, "measure:chest")
    wide["store.gaps"] = _store.gaps(_b.root)
    wide["store.arm_census"] = _store.arm_census(_b.root)
    for _m in ("families", "census", "unbought_generics"):
        wide[f"parts.{_m}"] = getattr(_lib, _m)()
    for _fam in _lib.families():
        wide[f"parts.variants.{_fam}"] = _lib.variants(_fam)
        for _v in _lib.variants(_fam):
            wide[f"parts.variant.{_fam}.{_v['key']}"] = _lib.variant(
                _fam, _v["key"])
    try:
        wide["parts.variant.missing"] = _lib.variant("closure", "nope")
    except ValueError as _e:
        wide["parts.variant.missing"] = {"verdict": str(_e).split(":")[0],
                                         "why": str(_e)}
    wide["parts.list_proposals"] = _parts.list_proposals()
    wide["parts.adopt_proposal.missing"] = _parts.adopt_proposal("closure",
                                                                 "nope")
    wide["prompts.profiles"] = _prompts.profiles()
    for _pid in _prompts.profiles():
        wide[f"prompts.for_model.{_pid}"] = _prompts.for_model(_pid)
    wide["prompts.for_model.unknown"] = _prompts.for_model("nope")
    wide["prompts.parse.bad"] = _prompts.parse_decomposition("default",
                                                             "{oops")
    wide["prompts.siglip"] = _prompts.siglip_queries()
    wide["compose.graph"] = rc
    _zs = _zones.catalog(rc)
    wide["zones.catalog"] = _zs
    wide["zones.parse_selection"] = _zones.parse_selection("1-3", _zs)
    wide["zones.parse_selection.bad"] = _zones.parse_selection("99", _zs)
    wide["zones.apply"] = _zones.apply(rc, {1: 1.5})
    residue = sorted({s for v in wide.values()
                      for s in i18n.missing(i18n.translate(v))})
    # An ADDRESS is a core name or a seat key: the store's coordinates,
    # which are the same word in both languages because they are what one
    # writes to read a value back.
    addresses = [s for s in residue
                 if s.startswith(("block:", "formula:", "placement:",
                                  "seam:", "parts:", "param:", "measure:",
                                  "("))]
    documents = [s for s in residue if s.lstrip().startswith("{")]
    bank = set()
    for _pid in list(_prompts.profiles()) + ["nope"]:
        bank |= set(i18n.missing(i18n.translate(_prompts.for_model(_pid))))
    prose = [s for s in residue
             if s not in addresses and s not in documents and s not in bank]
    # One of the two whole documents IS a prompt-bank string (the schema
    # the model is asked to fill), so the three groups are named with that
    # overlap stated rather than papered over.
    bank_only = sorted(bank - set(documents))
    check("the untranslated residue is measured",
          len(wide) == 55 and len(residue) == 39
          and len(addresses) == 32 and len(documents) == 2
          and len(bank) == 6 and len(bank_only) == 5 and not prose
          and sorted(set(addresses) | set(documents) | bank) == residue,
          f'{len(wide)} reader and refusal paths across block/cross/parts/'
          f'prompts/zones/compose leave {len(residue)} untranslated strings: '
          f'{len(addresses)} store addresses, {len(documents)} whole '
          f'documents (the coat\'s dump() and the prompt schema, Japanese by '
          f'design) and {len(bank_only)} further strings from the prompt '
          f'bank, which is written for the model. {len(prose)} are '
          f'prose an English caller was meant to read'
          + (f' — PROSE {[s[:40] for s in prose]}' if prose else ''))

    en = i18n.translate(outs["draft"])
    check("pieces read in English",
          en["pieces"][0]["name"] == "back bodice",
          en["pieces"][0]["name"])

    svg_en = i18n.svg(outs["svg"])
    import re
    strip = lambda d: re.sub(r"\s+", " ", re.sub(r"<text.*?</text>", "", d,
                                                 flags=re.S)).strip()
    geom_same = (strip(outs["svg"]).split("viewBox")[1].split(">")[1:]
                 == strip(svg_en).split("viewBox")[1].split(">")[1:])
    # X compared against a transform of X: green whenever the transform is
    # the IDENTITY, i.e. when nothing is translated at all. Measured: with
    # i18n.svg() made to return its argument this line stayed green. So the
    # two documents must be shown to differ where they are supposed to.
    check("SVG geometry untouched",
          geom_same and svg_en != outs["svg"] and "back bodice" in svg_en,
          f"every path identical apart from the canvas height; the two "
          f"documents do differ in their text "
          f"({len(svg_en) - len(outs['svg'])} chars) and the English one "
          f"says 'back bodice'")


# ---------------------------------------------------------------------------
def _no_constant(token: str):
    """A JSON reader that refuses the tokens JSON does not have.

    ``json.loads`` accepts bare ``NaN``, ``Infinity`` and ``-Infinity`` by
    default — a Python extension, not JSON. Every non-Python client refuses
    them, so a reply carrying one is unreadable in the field and readable
    here, which is how a NaN measurement shipped unnoticed.
    """
    raise ValueError(f"not JSON: {token}")


def the_mcp_server_answers() -> None:
    """Every tool, over the wire — not by import.

    Importing proves the function exists. It does not prove the server hands
    it a dictionary, which is the shape the app casts to; a bare array there
    turned the whole ledger unreadable once already.
    """
    # The server stores under Path.home(), and the sweep below calls the
    # mutating tools. Without this the suite writes into the operator's real
    # ledger — measurements, adoptions and intake rows that nobody entered.
    # Give the server a HOME of its own, the same way the tool sweep already
    # hands it a temporary directory for file outputs.
    home = tempfile.mkdtemp(prefix="photoloset-checks-")
    env = dict(os.environ, HOME=home)
    proc = subprocess.Popen([sys.executable, "-m", "photoloset.mcp"],
                            cwd=ROOT, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env)
    rid = [0]

    def rpc(method: str, params: dict | None = None) -> dict:
        rid[0] += 1
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid[0],
                                     "method": method,
                                     "params": params or {}}) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    try:
        init = rpc("initialize")["result"]
        check("initialize",
              init["serverInfo"]["name"] == "photoloset"
              and init["protocolVersion"] == "2024-11-05",
              f'{init["serverInfo"]["name"]} {init["protocolVersion"]}')
        tools = rpc("tools/list")["result"]["tools"]
        check("61 tools", len(tools) == 61, f"{len(tools)}")
        # A SIXTH check that could not fail, and the one directly above the
        # fifth. `all(... for t in tools)` is vacuously True on an empty
        # list, so with `tools == []` this line reported PASS while its own
        # sibling ("every tool returns an object") went red — measured: the
        # server mutated to answer `tools/list` with `[]` left this GREEN.
        # An `all()` over a sequence that arrives OVER THE WIRE is the same
        # defect as a literal True; the count has to be pinned in the same
        # condition, not on a neighbouring line that fails separately.
        no_schema = [t.get("name", "?") for t in tools
                     if t.get("inputSchema", {}).get("type") != "object"]
        no_props = [t.get("name", "?") for t in tools
                    if not isinstance(t.get("inputSchema", {})
                                      .get("properties"), dict)]
        # **"Derived from the signatures" was never measured.** The check
        # asserted only that a schema is an object with a properties dict —
        # true of a schema that types EVERY parameter as a string, which is
        # exactly what this server published: `from __future__ import
        # annotations` makes `par.annotation` the TEXT "float", the lookup
        # fell through to the default, and all 8 numeric parameters of the
        # 65 went out as {"type": "string"} — two of them beside a numeric
        # default. A client honouring the schema sent "2000" and got a
        # refusal. So the derivation is pinned here, parameter by
        # parameter, against the signatures themselves.
        published = {(t["name"], n): p.get("type")
                     for t in tools
                     for n, p in (t.get("inputSchema", {})
                                  .get("properties") or {}).items()}
        numeric = {
            ("measure_taken", "value"): "number",
            ("measure_ratio", "value"): "number",
            ("sew_and_drape", "iterations"): "integer",
            ("sew_and_drape", "cell"): "number",
            ("drape_validate", "width"): "number",
            ("drape_validate", "height"): "number",
            ("drape_validate", "iterations"): "integer",
            ("intake_add_clip", "seconds"): "number",
        }
        wrong = {k: (published.get(k), want) for k, want in numeric.items()
                 if published.get(k) != want}
        # ...and no parameter may publish a type its own default contradicts.
        contradicted = [(t["name"], n) for t in tools
                        for n, p in (t.get("inputSchema", {})
                                     .get("properties") or {}).items()
                        if isinstance(p.get("default"), (int, float))
                        and not isinstance(p.get("default"), bool)
                        and p.get("type") == "string"]
        check("every tool has a schema",
              len(tools) == 61 and not no_schema and not no_props
              and len(published) == 111 and not wrong and not contradicted
              and sorted(set(published.values())) == ["integer", "number",
                                                      "string"],
              f"{len(tools)} schemas derived from the signatures over "
              f"{len(published)} parameters, {len(no_schema)} not an object, "
              f"{len(no_props)} without properties; the {len(numeric)} "
              f"numeric parameters publish number/integer rather than string "
              f"and {len(contradicted)} publish a type their own default "
              f"contradicts"
              + (f" — {no_schema + no_props}" if no_schema or no_props
                 else "")
              + (f" — WRONG {wrong}" if wrong else "")
              + (f" — CONTRADICTED {contradicted}" if contradicted else ""))

        args = {
            "garment_observe": dict(part="collar", aspect="shape", value="v", source="s"),
            "garment_infer": dict(part="collar", aspect="shape", value="v", basis="b"),
            "garment_propose": dict(part="collar", aspect="shape", value="v", source="s"),
            "garment_adopt": dict(part="collar", aspect="shape", value="v", by="ci"),
            "measure_taken": dict(spot="chest", value=1.0, unit="cm", source="s"),
            "measure_ratio": dict(spot="waist", value=0.6, basis="chest"),
            "design_history": dict(part="collar", aspect="shape"),
            "rights_intent": dict(intent="personal"),
            "intake_register": dict(path=str(ROOT)),
            "intake_add_clip": dict(source_path=str(ROOT), clip_path="/tmp/a.jpg", mark="m"),
            "intake_origin": dict(clip_path="/tmp/a.jpg"),
            "sew_and_drape": dict(fabric="none", iterations=20),
            "drape_validate": dict(fabric="none", iterations=20),
        }
        # This line used to read `check("every tool returns an object", True,
        # ...)` — a literal True, so it reported PASS whatever the loop below
        # found, including when the loop ran zero times. The per-tool FAIL
        # lines it relied on carry DYNAMIC names, so they appear only on
        # failure and the falsifier harness (which pins declared names) could
        # never see them. This is the same defect as the two tautologies
        # above wearing a different hat: a check whose condition is a
        # constant. Found by hunting that shape across the whole suite.
        not_object: list = []
        crashed: list = []
        with tempfile.TemporaryDirectory() as tmp:
            for t in tools:
                name = t["name"]
                a = dict(args.get(name, {}))
                for key in ("path",):
                    # ``.get``, not ``[...]``: a tool whose schema is
                    # malformed is exactly what the check above is for, and
                    # indexing it here aborts the section so "every tool
                    # returns an object" never runs at all. Measured: the
                    # non-object-schema mutation used to take the whole
                    # function down with a KeyError, reported honestly as
                    # the section crashing but leaving the sibling check
                    # unmeasured. A check must be able to see the failure
                    # its neighbour was mutated into.
                    props = t.get("inputSchema", {}).get("properties")
                    if not isinstance(props, dict):
                        props = {}
                    if key in props and key not in a:
                        a[key] = f"{tmp}/out"
                r = rpc("tools/call", {"name": name, "arguments": a})
                body = json.loads(r["result"]["content"][0]["text"])
                if not isinstance(body, dict):
                    not_object.append((name, type(body).__name__))
                elif body.get("verdict") == "ERROR":
                    crashed.append((name, body.get("why", "")[:60]))
        check("every tool returns an object",
              len(tools) == 61 and not not_object and not crashed,
              f'{len(tools)} called over stdio, {len(not_object)} returned a '
              f'non-object, {len(crashed)} answered ERROR'
              + (f' — {not_object + crashed}' if not_object or crashed
                 else ''))

        absent = json.loads(rpc("tools/call", {"name": "garment_cross",
                                               "arguments": {}}
                                )["result"]["content"][0]["text"])
        check("absent tools say so",
              absent["verdict"] == "UNKNOWN_NOT_IN_THIS_BUILD",
              absent["verdict"])
        anon = json.loads(rpc("tools/call", {
            "name": "garment_adopt",
            "arguments": dict(part="collar", aspect="shape", value="v", by="")}
            )["result"]["content"][0]["text"])
        check("anonymous adoption refused",
              anon["verdict"] == "UNKNOWN_NO_ADOPTER", anon["verdict"])

        # **A stdlib message must not pose as a verdict.** `_refused` took
        # everything before the first colon, so a client that honoured the
        # (then wrong) schema and sent "2000" for a number was answered
        # `{"verdict": "could not convert string to float"}` — which
        # contradicts this module's own docstring, and which no caller can
        # branch on. And a value that is not JSON must not be written INTO
        # the reply: "nan" used to come back as
        # `{"verdict": "ANSWER", "entry": {... "value": NaN ...}}`, one bare
        # token that makes the whole line unreadable to a conforming parser.
        typed = {}
        for label, a in (
                ("text for a number",
                 dict(spot="chest", value="abc", unit="cm", source="s")),
                ("nan for a number",
                 dict(spot="chest", value="nan", unit="cm", source="s")),
                ("infinity for a number",
                 dict(spot="chest", value="inf", unit="cm", source="s"))):
            raw = rpc("tools/call", {"name": "measure_taken",
                                     "arguments": a}
                      )["result"]["content"][0]["text"]
            # The reply has to be JSON by a STRICT reader: json.loads
            # accepts the bare NaN token by default, which is precisely how
            # this went unnoticed.
            try:
                body = json.loads(raw, parse_constant=_no_constant)
                readable = True
            except ValueError:
                body, readable = {"verdict": "<unreadable>"}, False
            typed[label] = (body.get("verdict"), readable)
        # **This has to be a red, not a raise.** Reading the sheet with
        # the strict reader outside a guard made the mutation that puts NaN
        # back CRASH the section instead of failing this line — which is
        # the "a check that did not run is not a check that passed" rule,
        # one level down: the falsifier saw the crash, not the property.
        raw_sheet = rpc("tools/call", {"name": "measure_sheet",
                                       "arguments": {}}
                        )["result"]["content"][0]["text"]
        try:
            sheet = json.loads(raw_sheet, parse_constant=_no_constant)
        except ValueError:
            sheet = {"verdict": "<unreadable by a strict reader>"}
        # ...and the mapping itself, not only what a tool happens to reach:
        # every refusal path in this server is typed today, so the ONE
        # thing that could put a stdlib sentence in the verdict field is
        # _refused's own fallback. Measured directly, because a guard no
        # input reaches is a guard nobody has tested.
        from photoloset import mcp as _mcp_mod
        posed = json.loads(_mcp_mod._refused(
            ValueError("could not convert string to float: 'x'")))
        typed_kept = json.loads(_mcp_mod._refused(
            ValueError("UNKNOWN_NO_UNIT: a number with no unit")))
        # **The operator's own ledger is not a fixture.** Every mutating
        # tool was just called; this says where those writes landed. The
        # guarantee used to rest on an argument — "nothing in-process calls
        # Path.home()" — which is the kind of sentence that stops being
        # true the day somebody adds an import. Stated positively, because
        # the before/after form of it (~/.photoloset unchanged) is two
        # calls of one function compared, the shape this suite hunts, and
        # its only falsifier would have to write into the real ledger.
        wrote = sorted(f.name for f in Path(home).rglob("*.json"))
        check("the sweep writes into a HOME of its own",
              wrote == ["intake.json", "ledger.json", "measures.json",
                        "rights.json"]
              and Path(home) != Path.home()
              and not str(Path(home)).startswith(str(Path.home())),
              f'the {len(wrote)} store files the sweep wrote — {wrote} — are '
              f'under the temporary HOME it gave the server, which is not '
              f'yours and not inside it')

        check("a refusal is typed, and the reply is JSON",
              len(typed) == 3
              and set(typed.values()) == {("UNKNOWN_NOT_A_NUMBER", True)}
              and posed["verdict"] == "UNKNOWN_REFUSED"
              and "could not convert" in posed["why"]
              and typed_kept["verdict"] == "UNKNOWN_NO_UNIT"
              and sheet["verdict"] == "ANSWER"
              # ...and the only measurement on the sheet is the finite
              # one the tool sweep above wrote; none of the three refused
              # arguments reached the file.
              and [r["value"] for r in sheet.get("measured", [])] == [1.0],
              f'{len(typed)} arguments no number can be made of are refused '
              f'{sorted(set(v for v, _r in typed.values()))} — not a stdlib '
              f'sentence used as a verdict — and every reply parses under a '
              f'reader that rejects the bare NaN/Infinity tokens '
              f'({sorted(set(r for _v, r in typed.values()))}), so nothing '
              f'unreadable was stored either — the sheet holds '
              f'{[r["value"] for r in sheet.get("measured", [])]}, the one '
              f'finite measurement the sweep wrote; and a stdlib sentence handed '
              f'to _refused comes back {posed["verdict"]} rather than posing '
              f'as one, while a typed one is kept ({typed_kept["verdict"]})')
    finally:
        proc.stdin.close()
        proc.wait(timeout=30)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
def no_dependencies() -> None:
    """The badge says none. This is what makes that checkable."""
    import ast
    import re
    third_party = set()
    stdlib_ok = re.compile(r"^(\.|__future__|json|sys|os|re|math|"
                           r"random|inspect|pathlib|typing|dataclasses|http|"
                           r"socket|argparse|traceback|subprocess|tempfile|"
                           r"functools|collections|webbrowser|urllib|itertools|"
                           r"copy|time|datetime|hashlib|pickle|struct|unicodedata|"
                           r"textwrap|difflib|shutil|glob|enum|abc|contextlib|"
                           r"threading|queue|base64|uuid|csv|io|warnings|"
                           r"operator|bisect|heapq|statistics|photoloset)$")
    # Parsed, not grepped. A line-based scan reads the import examples inside
    # docstrings as imports, and misreads `from . import x` — which is the
    # package talking to itself — as a third party.
    # The glob's SIZE is asserted below: a scan that covers zero files finds
    # zero third-party imports and used to report "standard library only".
    # Measured: globbing "*.pyx" instead left this line green.
    scanned = sorted((ROOT / "photoloset").glob("*.py"))
    for path in scanned:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level > 0:              # relative: our own modules
                    continue
                name = (node.module or "").split(".")[0]
            elif isinstance(node, ast.Import):
                name = node.names[0].name.split(".")[0]
            else:
                continue
            if not stdlib_ok.match(name):
                third_party.add(f"{path.name}: {name}")
    check("no third-party imports",
          len(scanned) == 36 and not third_party,
          f"{len(scanned)} modules parsed, "
          + (f"{len(third_party)} found" if third_party
             else "standard library only"))
    for t in sorted(third_party):
        print(f"        {t}")


# ---------------------------------------------------------------------------
@declares("coat's arms are the three dualities",
          'empty arms are typed gaps',
          'formulas served from the cross',
          'seams served from the cross',
          'a fifth face is refused',
          'conflicting declarations go contested',
          'placement does not move answers',
          'round trip moves nothing',
          'the whole declaration is served from the cross')
def the_block_lives_on_the_cross() -> None:
    """The coat's declaration lives on the stereo cross, not in files.

    One node holds 6 arms x 4 faces = 24 seats. That capacity is measured,
    not chosen, so the declaration splits into child cores when an arm
    overflows — nesting is required by the geometry, not a design taste.
    The arms are the three dualities, and the arm a fact sits on is derived
    from what KIND of claim it is; nobody gets to choose a convenient one.
    """
    import copy as _copy
    import json as _json

    from photoloset import block as blk
    from photoloset import cross

    # ``blk.coat()`` is called through this, never at function scope, so a
    # regressed store raises INSIDE whichever guard first needs the coat and
    # that check goes red with the real reason. Built at function scope it
    # aborted the whole function and eight names ran neither green nor red;
    # ``section`` now reports those as NEVER RAN, which is honest but is not
    # a measurement. This makes them measurements again.
    _held: dict = {}

    def coat():
        if "b" not in _held:
            _held["b"] = blk.coat()
        return _held["b"]

    with guard("coat's arms are the three dualities"):
        b = coat()
        cen = b.store.census()
        arms = b.arm_census()
        # NOTE: this replaces the old "coat fills its root node exactly" check,
        # which asserted all six arms sat at exactly 4/4. That claim died with
        # the drawers: it could only ever hold while the arms were storage
        # categories. Under typed arms it would demand the coat hold 4 measured,
        # 4 cited, 4 derived, 4 feeds, 4 generic and 4 specific claims, and the
        # coat holds 0 measured, 0 cited and 0 generic. The replacement is
        # strictly stronger — it pins the actual shape AND its falsifier below.
        want = {"support+": 0, "support-": 0, "cause+": 10,
                "cause-": 0, "kind+": 0, "kind-": 17}
        check("coat's arms are the three dualities",
              arms == want and not cen["over_capacity"]
              and set(cross.ARMS) == set(want)
              and cen["cores"] == 10 and cen["seats"] == 56,
              f'{cen["cores"]} cores, {cen["seats"]} seats — root '
              f'kind- {arms["kind-"]}, cause+ {arms["cause+"]}, '
              f'support+ {arms["support+"]}, kind+ {arms["kind+"]}')

    with guard('empty arms are typed gaps'):
        b = coat()
        # Typed gaps, and the falsifier that must make one of them vanish.
        gaps = b.gaps()
        cited = _copy.deepcopy(blk.COAT_DECLARATION)
        cited["name"] = "coat_cited"
        cited["params"] = [("half_divisor", 4.0, None, "cited", None)] + [
            r for r in cited["params"] if r[0] != "half_divisor"]
        st_c, root_c = blk.ingest(decl=cited)
        st_c.put(root_c, "param:half_divisor", {"value": 4.0}, "cited",
                 "文化服装学院 文化ファッション大系 改訂版・服飾造形講座")
        v_c = blk.BlockView(st_c, root_c)
        falsified = "UNKNOWN_NO_SUPPORT_RECORDED" in v_c.gaps()
        check("empty arms are typed gaps",
              "UNKNOWN_NO_SUPPORT_RECORDED" in gaps
              and "UNKNOWN_NO_GENERALIZATION_RECORDED" in gaps
              and not falsified,
              f'{len(gaps)} gaps — nothing measured or cited backs the 20 '
              f'params, nothing is claimed generic; one `cited` param with a '
              f'second source removes the support gap ({len(v_c.gaps())} left)')

    with guard('formulas served from the cross'):
        # DO NOT compare b.formulas() against garment_pattern.FORMULAS.
        # garment_pattern.py:38 is `FORMULAS = _COAT.formulas()`, so that
        # comparison is blk.coat().formulas() == blk.coat().formulas() — it
        # is true no matter what the reader does, and it stayed GREEN when
        # BlockView.formulas() was replaced with a dict literal that never
        # touches the store. Two things replace it: the 17 names PINNED as
        # literals here, and a store the served dict has to TRACK.
        b = coat()
        served = b.formulas()
        st_f, root_f = blk.ingest()
        v_f = blk.BlockView(st_f, root_f)
        st_f.put(blk.piece_core(root_f, "袖"), "formula:試しの式",
                 "chest / 999", "derived", "declaration:probe")
        grew = v_f.formulas()
        dropped = _copy.deepcopy(blk.COAT_DECLARATION)
        dropped["name"] = "coat_less_one"
        st_g, root_g = blk.ingest(
            decl=dropped,
            formulas=[r for r in blk.FORMULA_ORDER if r[0] != "袖ぐり深さ"])
        shrank = blk.BlockView(st_g, root_g).formulas()
        check("formulas served from the cross",
              list(served) == FORMULA_NAMES
              and grew.get("試しの式") == "chest / 999"
              and len(grew) == 18
              and "袖ぐり深さ" not in shrank and len(shrank) == 16,
              f'{len(served)} names pinned as literals here, not read off '
              f'the drafting module; writing one `formula:` seat makes the '
              f'served dict {len(grew)}, removing one declaration makes it '
              f'{len(shrank)} — the reader tracks the store')

    with guard('seams served from the cross'):
        # Same defect, same treatment: garment_sew.py:38 is
        # `SEAMS = _block.coat().seams()`, so `b.seams() == garment_sew.SEAMS`
        # compared a value against itself and stayed GREEN both when
        # BlockView.seams() was replaced by a dict literal and when a seam
        # never reached the store at all. The 5 labels are pinned here, and
        # the served list has to follow a store edit.
        b = coat()
        seams = b.seams()
        st_s, root_s = blk.ingest()
        v_s = blk.BlockView(st_s, root_s)
        st_s.put(root_s, "seam:試しの縫い目",
                 {"a": ["袖", "袖口"], "b": ["袖", "袖口"],
                  "label": "試しの縫い目"},
                 "specific", "declaration:probe")
        grew_s = v_s.seams()
        fewer = _copy.deepcopy(blk.COAT_DECLARATION)
        fewer["name"] = "coat_open_shoulder"
        fewer["seams"] = list(fewer["seams"])[1:]
        st_t, root_t = blk.ingest(decl=fewer)
        shrank_s = blk.BlockView(st_t, root_t).seams()
        # #7: seam_edges()[].a/.b changed address shape in the reshaping —
        # ("block:coat", "pieces", "前身頃"), an arm as a coordinate, became
        # ("block:coat/piece:前身頃", "role"), a subject core. Nothing reads
        # those addresses (the only two call sites take len(), and
        # BlockView.served() reduces the list to a count), and the coat did
        # not move: every drafted, marked, built and draped number is
        # identical to cbbd045, with label and value on these edges
        # byte-equal. It was untested, which is why it could drift unnoticed;
        # it is pinned here now so the next drift has to be stated.
        edge_ends = [(e["a"], e["b"]) for e in b.seam_edges()]
        want_ends = [(("block:coat/piece:前身頃", "role"),
                      ("block:coat/piece:後身頃", "role")),
                     (("block:coat/piece:前身頃", "role"),
                      ("block:coat/piece:後身頃", "role")),
                     (("block:coat/piece:袖", "role"),
                      ("block:coat/piece:前身頃", "role")),
                     (("block:coat/piece:袖", "role"),
                      ("block:coat/piece:後身頃", "role"))]
        check("seams served from the cross",
              [_seam_label(s) for s in seams] == SEAM_LABELS
              and len(b.seam_edges()) == 4
              and edge_ends == want_ends
              and len(grew_s) == 6
              and grew_s[-1]["label"] == "試しの縫い目"
              and len(shrank_s) == 4
              and _seam_label(shrank_s[0]) != SEAM_LABELS[0],
              f'{len(seams)} labels pinned as literals here, not read off '
              f'the sewing module; one written `seam:` seat makes it '
              f'{len(grew_s)}, one dropped declaration makes it '
              f'{len(shrank_s)}; {len(b.seam_edges())} edges whose endpoints '
              f'name subject cores, pinned here')

    with guard('a fifth face is refused'):
        # A fifth ADDRESS on one arm. Refusal is a RETURN VALUE now, and the
        # nesting writer is what block.ingest uses, so it must not refuse.
        small = cross.CrossStore()
        for i in range(cross.FACES_PER_ARM):
            small.put_strict("t", f"k{i}", {"value": float(i)}, "specific", "src")
        refused = small.put_strict("t", "one-too-many", {"value": 1.0},
                                   "specific", "src")
        seated = small.put("t", "one-too-many", {"value": 1.0}, "specific", "src")
        check("a fifth face is refused",
              refused["verdict"] == cross.ARM_FULL
              and seated["verdict"] == "ANSWER"
              and seated["core"] != "t",
              f'{refused["verdict"]} from the strict writer — the nesting '
              f'writer put it on {seated["core"]} instead')

    with guard('conflicting declarations go contested'):
        b = coat()
        # The rival goes at the ROOT even though the seat lives on a child core.
        # Under address-global resolution the holder is irrelevant; under the
        # old core-local gate this could only be caught by hunting the holder.
        st2, root2 = blk.ingest()
        holder = next(n for n, seats in st2.cores.items()
                      if any(s["key"] == "setting:grain_angle_deg"
                             for s in seats))
        before_seats = st2.census()["seats"]
        rival = st2.put(root2, "setting:grain_angle_deg",
                        {"value": 0.0, "basis": "conflict"},
                        "specific", "declaration:conflict")
        sides = st2.resolve(root2, "setting:grain_angle_deg")
        v2 = blk.BlockView(st2, root2)
        picked = "kept quiet"
        try:
            v2.setting("grain_angle_deg")
        except ValueError as e:
            picked = str(e).split(":")[0]
        check("conflicting declarations go contested",
              rival["verdict"] == cross.CONTESTED_IN_CROSS
              and sides["verdict"] == cross.CONTESTED_IN_CROSS
              and len(sides["sides"]) == 2
              and st2.census()["seats"] == before_seats
              and picked == cross.CONTESTED_IN_CROSS,
              f'seat lives on a child core ({holder}), rival written at the '
              f'root — both kept '
              f'({len(sides["sides"])} sides), no seat consumed, reader '
              f'refuses to pick ({picked})')

    with guard('placement does not move answers'):
        # The second conjunct here used to be `inv.get("structural")`, which
        # was a hardcoded True inside placement_check — it read as evidence
        # and was a constant. Measured: gutting placement_check to an empty
        # plan, and reintroducing the original P1 defect, both left this
        # line GREEN. The constant is gone from cross.py and this line now
        # carries a store it MUST call order dependent, so the machinery
        # being removed turns it red rather than leaving it decorative.
        b = coat()
        inv = b.store.placement_check()
        moved = cross.CrossStore()
        moved.put("m", "measure:chest", 108.0, "measured", "tape")
        moved.put("m", "measure:chest", 108.0, "derived", "chest / 4 × 4")
        drift = moved.placement_check()
        check("placement does not move answers",
              inv["verdict"] == "ANSWER"
              and inv["addresses_checked"] == 56
              and "structural" not in inv
              and drift["verdict"] == cross.ORDER_DEPENDENT
              and drift["differences"]
              and inv["orders"] == 3,
              f'{inv["addresses_checked"]} coat addresses re-ingested in '
              f'{inv["orders"]} orders; one address reached by two kinds '
              f'IS order dependent — the seat is charged to whichever arm '
              f'seated first — and this says so '
              f'({drift["verdict"]}, {len(drift["differences"])} diffs)')

    with guard('round trip moves nothing'):
        b = coat()
        rt = cross.CrossStore.from_dict(
            _json.loads(_json.dumps(b.store.to_dict())))
        # `BlockView(rt, root).dump() == b.dump()` is the same method on two
        # receivers: whatever one side drops, the other drops too. Measured:
        # deleting `"formulas": self.formulas(),` from served() — the served
        # declaration silently stops carrying its 17 formulas — left the
        # whole suite green, and `dump()` returning "" passed as well. So
        # the SHAPE of what is round-tripped is pinned here, in the same
        # condition, against literals.
        served = b.served()
        check("round trip moves nothing",
              sorted(served) == ["formulas", "label", "params", "pieces",
                                 "placement", "required", "seam_edges",
                                 "seams", "settings", "sleeve_required"]
              and len(served["formulas"]) == 17
              and len(served["seams"]) == 5
              and served["seam_edges"] == 4
              and len(b.dump()) > 2000
              and blk.BlockView(rt, b.root).dump() == b.dump()
              and rt.load_verdict["verdict"] == "ANSWER",
              f'the served declaration is byte-equal after a storage round '
              f'trip, and it is {len(sorted(served))} sections carrying '
              f'{len(served["formulas"])} formulas, {len(served["seams"])} '
              f'seams and {served["seam_edges"]} seam edges — '
              f'{len(b.dump())} characters of dump, pinned here so a '
              f'section going missing cannot drop out of both sides at once')

    with guard('the whole declaration is served from the cross'):
        # #8/#9 again, for the four readers no check pinned to a literal:
        # label(), placement(), sleeve_required() and arm_census(). Measured
        # on head: placement() replaced with a frozen dict — it stops
        # reading the store entirely — kept all 81 checks green, and under
        # that bypass the SKIRT was served the coat's sleeve placement
        # (garment_skirt.py calls view.placement()). label() froze the same
        # way. Each is pinned as a literal here AND has to track the store.
        b = coat()
        st_p, root_p = blk.ingest()
        v_p = blk.BlockView(st_p, root_p)
        st_p.put(blk.piece_core(root_p, "袖"), "placement:試しの位置",
                 {"value": (1.0, 2.0, 3.0)}, "specific", "declaration:probe")
        grew_p = v_p.placement()
        fewer = _copy.deepcopy(blk.COAT_DECLARATION)
        fewer["name"] = "coat_flat"
        fewer["placement"] = {k: v for k, v in fewer["placement"].items()
                              if k != "袖"}
        fewer["pieces"] = [pc for pc in fewer["pieces"] if pc[0] != "袖"]
        fewer["seams"] = [sm for sm in fewer["seams"]
                          if "袖" not in _seam_label(
                              sm if isinstance(sm, dict) else {"a": sm[0],
                                                               "b": sm[1]})]
        st_q, root_q = blk.ingest(decl=fewer)
        shrank_p = blk.BlockView(st_q, root_q).placement()
        # ...and a Block serves only what ITS OWN root declared: the skirt
        # must not be handed the coat's pieces or the coat's params.
        import photoloset.assemble as _asm
        skirt_decl = _asm.assemble({"silhouette": "Aライン",
                                    "closure": "ゴムウエスト（開き無し）",
                                    "waist_finish": "シャーリング"})
        st_s2, root_s2 = blk.ingest(decl=skirt_decl["declaration"],
                                    formulas=skirt_decl["declaration"]
                                    ["formulas"])
        v_s2 = blk.BlockView(st_s2, root_s2)
        skirt_served = v_s2.served()
        # ...and the label has to TRACK the store: pinning it against the
        # literal alone is satisfied by a reader frozen to that literal,
        # which is the shape of #8/#9 (measured: label() answering from
        # COAT_DECLARATION for root "block:coat" kept all 81 checks green).
        # Same root name, different declared label.
        relabelled = _copy.deepcopy(blk.COAT_DECLARATION)
        relabelled["label"] = "試しのコート（差し替えた名乗り）"
        st_l, root_l = blk.ingest(decl=relabelled)
        other_label = blk.BlockView(st_l, root_l).label()
        check("the whole declaration is served from the cross",
              b.label() == "三枚コート（前身頃・後身頃・袖）"
              and root_l == b.root
              and other_label == "試しのコート（差し替えた名乗り）"
              and b.placement() == {"前身頃": (0.0, 0.0, 12.0),
                                    "後身頃": (0.0, 0.0, -12.0),
                                    "袖": (34.0, 0.0, 0.0)}
              and b.sleeve_required() == ("sleeve_length",)
              and b.required() == ("body_length", "chest", "shoulder")
              and b.arm_census()["kind-"] == 17
              and b.arm_census()["cause+"] == 10
              and b.arm_census()["support+"] == 0
              and b.params()["half_divisor"] == 4.0
              and b.params()["cap_height_ratio"] == 0.78
              and len(b.params()) == 20
              and b.settings()["grain_angle_deg"] == 90.0
              and b.settings()["pins_policy"] == "front_only_hanging"
              and len(b.settings()) == 3
              and len(grew_p) == 4 and grew_p["試しの位置"] == (1.0, 2.0, 3.0)
              and len(shrank_p) == 2 and "袖" not in shrank_p
              and sorted(skirt_served["pieces"]) == ["前身頃", "後身頃"]
              and sorted(skirt_served["params"]) == [
                  "flare_ratio", "hip_depth", "hip_ease",
                  "waist_ease_per_panel"]
              and "袖" not in skirt_served["placement"],
              f'label, placement, sleeve_required and the arm census are '
              f'pinned as literals here, not read off the drafting modules '
              f'(a second declaration under the SAME root name serves '
              f'{other_label!r}, so a reader frozen to the coat\'s label is '
              f'caught); '
              f'writing one `placement:` seat makes the served map '
              f'{len(grew_p)}, dropping the sleeve declaration makes it '
              f'{len(shrank_p)}; and a SKIRT block serves its own '
              f'{len(skirt_served["pieces"])} pieces and its own '
              f'{len(skirt_served["params"])} params — not the coat\'s')


# ---------------------------------------------------------------------------
@declares('arms are derived, not chosen',
          'support- is never written, only emerges',
          'absence is not a claim',
          'agreement does not consume seats',
          'a generic claim needs two sources',
          'a seat carries every kind that reached it',
          'a specific claim cannot buy a generic one',
          'ordered reads follow the declaration')
def the_arms_carry_meaning() -> None:
    """The arm a fact sits on is derived from its kind and has consequences.

    Six drawers named after storage categories would pass every check above
    while being inert. These are the checks that die if the vocabulary goes
    back to being decoration: each one names a store that VIOLATES the
    property and shows it being rejected.
    """
    with guard('arms are derived, not chosen'):
        # Imported INSIDE the guard: these modules build the coat at module
        # scope, so a regressed store raises on IMPORT and every guarded
        # line below would vanish instead of going red.
        from photoloset import block as blk, cross, parts

        b = blk.coat()

        # --- arms are derived, never chosen ---------------------------------
        liar = {"cores": {"c": [{"key": "param:x", "arm": "kind+", "seq": 1,
                                 "values": [{"value": 1, "kind": "specific",
                                             "sources": ["s"]}]}]},
                "edges": []}
        bad = cross.CrossStore.from_dict(liar)
        honest = b.store.verify()
        # `all(...)` over the coat's seats is vacuously TRUE on an empty
        # store, so the number of seats it walked is asserted here rather
        # than assumed — the shape that hid the sixth tautology.
        walked = [s for seats in b.store.cores.values() for s in seats]
        every = all(s["arm"] == cross.KIND_ARM[s["values"][0]["kind"]]
                    for s in walked)
        check("arms are derived, not chosen",
              bad.load_verdict["verdict"] == cross.ARM_NOT_DERIVED
              and honest["verdict"] == "ANSWER"
              and len(walked) == 56 and every
              and honest["seats"] == 56,
              f'a seat claiming kind+ while its claim is `specific` loads as '
              f'{bad.load_verdict["verdict"]}; all {len(walked)} coat seats '
              f'walked here (census says {honest["seats"]}) derive')

    with guard('support- is never written, only emerges'):
        # --- support- is unwritable, and emerges ----------------------------
        st = cross.CrossStore()
        st.put("c", "param:x", {"v": 1}, "specific", "a")
        before = st.arm_census("c")["support-"]
        st.put("c", "param:x", {"v": 2}, "specific", "b")
        after = st.arm_census("c")["support-"]
        check("support- is never written, only emerges",
              "support-" not in [a for a in cross.KIND_ARM.values()]
              and before == 0 and after == 1
              and st.resolve("c", "param:x")["also_on"] == "support-",
              f'no kind maps to support-; a collision moved it {before}→{after}')

    with guard('absence is not a claim'):
        # --- no_match is not stored -----------------------------------------
        st2 = cross.CrossStore()
        st2.put("c", "param:y", {"v": 1}, "specific", "a")
        snap = st2.census()
        nm = st2.put("c", "param:z", {"v": 9}, "no_match", "search")
        seated = {"cores": {"c": [{"key": "k", "arm": "kind-", "seq": 1,
                                   "values": [{"value": 1, "kind": "no_match",
                                               "sources": ["s"]}]}]},
                  "edges": []}
        seated_store = cross.CrossStore.from_dict(seated)
        check("absence is not a claim",
              nm["verdict"] == cross.NOT_A_CLAIM and nm["stored"] is False
              and st2.census() == snap
              and seated_store.load_verdict["verdict"] == cross.ARM_NOT_DERIVED,
              'a no_match put changes nothing; a store that seated one is '
              f'rejected as {seated_store.load_verdict["verdict"]}')

    with guard('agreement does not consume seats'):
        # --- agreement makes a seat heavier, not wider ----------------------
        st3 = cross.CrossStore()
        for src in ("tape", "second fitter", "photo", "the pattern"):
            st3.put_strict("c", "measure:chest", {"value": 108.0},
                           "measured", src)
        for spot in ("waist", "hip", "shoulder"):
            st3.put_strict("c", f"measure:{spot}", {"value": 80.0},
                           "measured", "tape")
        r = st3.resolve("c", "measure:chest")
        keys = {s["key"] for s in st3.cores["c"]}
        others = [st3.resolve("c", f"measure:{x}")["verdict"]
                  for x in ("waist", "hip", "shoulder")]
        triples = {"cores": {"c": [
            {"key": "measure:chest", "arm": "support+", "seq": i,
             "values": [{"value": 108.0, "kind": "measured",
                         "sources": [f"s{i}"]}]} for i in range(4)]},
            "edges": []}
        dup = cross.CrossStore.from_dict(triples)
        check("agreement does not consume seats",
              r["weight"] == 4 and len(st3.cores["c"]) == 4
              and keys == {"measure:chest", "measure:waist", "measure:hip",
                           "measure:shoulder"}
              and others == ["ANSWER"] * 3
              and st3.census()["over_capacity"] == []
              and dup.load_verdict["verdict"] == cross.DUPLICATE_ADDRESS,
              f'4 sources on one measurement = 1 seat of weight '
              f'{r["weight"]}, and 3 OTHER measurements still seat on the same '
              f'arm ({len(keys)} distinct addresses); the triple-counted shape '
              f'loads as {dup.load_verdict["verdict"]}')

    with guard('a generic claim needs two sources'):
        # --- a generic claim must be bought ---------------------------------
        lib = parts.Library()
        unbought = lib.unbought_generics()
        # ...and families() must TRACK the store, not answer from a list it
        # carries: a reader frozen to the right literal is the shape of #8
        # and #9. One more family declared into a fresh store has to appear.
        grown_lib = parts.Library()
        gcore = parts.family_core("裾線")
        grown_lib.store.put(gcore, "family", {"open": True}, "generic",
                            "library:probe")
        grown_lib.store.link((gcore, ""), (parts.ROOT, ""), "part_of")
        grown_families = grown_lib.families()
        bought = cross.CrossStore()
        bought.put("p:s", "family", {"open": True}, "generic", "文化ファッション大系")
        bought.put("p:s", "family", {"open": True}, "generic", "文化服装学院")
        check("a generic claim needs two sources",
              lib.families() == ["silhouette", "closure", "waist_finish"]
              and grown_families == ["silhouette", "closure", "waist_finish",
                                     "裾線"]
              and len(unbought) == 3
              and all(u["verdict"] == cross.GENERIC_NOT_BOUGHT
                      for u in unbought)
              and bought.unbought_generics() == []
              and b.store.unbought_generics() == [],
              f'{len(unbought)} family claims — {lib.families()}, read from '
              f'the store and pinned here as literals — rest on the library '
              f'alone; declaring one more family makes the reader answer '
              f'{grown_families}; a second independent source clears one; '
              f'the coat has no generic claims at all')

    with guard('a seat carries every kind that reached it'):
        # --- #1: there is no single seat arm, so nobody can choose one -----
        # THE DECISION. Two kinds at one address is not a contest and not a
        # refusal: it is one address holding two claims, and the seat appears
        # on the arm of EACH. Argued from the module's own reason for keeping
        # the arm out of the address — if a support+ observation and a
        # cause+ derivation of the same value could not share an address they
        # would never meet, which is the failure the address shape exists to
        # prevent. A refusal would also hand the writer the arm back, by
        # racing: whoever wrote first would own the address and the other
        # claim would be dropped.
        both = cross.CrossStore()
        both.put("m", "measure:chest", 108.0, "measured", "tape")
        second = both.put("m", "measure:chest", 108.0, "derived",
                          "chest / 4 × 4")
        seat = both.cores["m"][0]
        got = both.resolve("m", "measure:chest")
        cen_b = both.arm_census("m")
        # ...and the store that seated the same claim twice, which is how the
        # weight of a claim could be inflated into the weight of an address.
        twice = cross.CrossStore.from_dict({"cores": {"c": [
            {"key": "k", "arm": "kind-", "seq": 1, "values": [
                {"value": 1, "kind": "specific", "sources": ["a"]},
                {"value": 1, "kind": "specific", "sources": ["b"]}]}]},
            "edges": []})
        check("a seat carries every kind that reached it",
              cross.seat_arms(seat) == ["support+", "cause+"]
              and second["verdict"] == "ANSWER"
              and second["state"] == "second_kind"
              and got["verdict"] == "ANSWER"
              # **The weight does not cross the kinds.** Two kinds, one
              # source each, used to read as weight 2 — a number the gate
              # never agreed to (`unbought_generics` prices each kind on
              # its OWN sources). One address, two claims, one source each.
              and got["weight"] == 1
              and got["weight_by_kind"] == {"measured": 1, "derived": 1}
              and len(got["named_sources"]) == 2
              and cen_b["support+"] == 1 and cen_b["cause+"] == 1
              and "UNKNOWN_NO_SUPPORT_RECORDED" not in both.gaps("m")
              and "UNKNOWN_NO_CAUSE_RECORDED" not in both.gaps("m")
              and twice.load_verdict["verdict"] == cross.DUPLICATE_CLAIM,
              f'one address, measured AND derived, sits on '
              f'{cross.seat_arms(seat)} — 1 address, weight '
              f'{got["weight"]} for each kind that reached it '
              f'({got["weight_by_kind"]}) over '
              f'{len(got["named_sources"])} named sources, and neither the '
              f'support gap nor the cause gap is reported; a store seating '
              f'the same (kind, value) twice loads as '
              f'{twice.load_verdict["verdict"]}')

    with guard('a specific claim cannot buy a generic one'):
        # --- #0: the kind is recorded PER SOURCE, so agreement from a
        # different kind does not pay for a general claim. Measured against
        # the shipped library, not a hand-built store.
        lib2 = parts.Library()
        n_before = len(lib2.unbought_generics())
        agreed = lib2.store.resolve("parts:closure", "family")["value"]
        laundered = lib2.store.put("parts:closure", "family", agreed,
                                   "specific", "this one coat agrees")
        n_after = len(lib2.unbought_generics())
        # ...and the honest way to buy it still works.
        lib2.store.put("parts:closure", "family", agreed, "generic",
                       "文化ファッション大系")
        n_bought = len(lib2.unbought_generics())
        check("a specific claim cannot buy a generic one",
              n_before == 3 and n_after == 3
              and laundered["verdict"] == "ANSWER" and n_bought == 2
              and laundered["state"] == "second_kind"
              and lib2.store.verify()["verdict"] == "ANSWER",
              f'a `specific` claim agreeing with the family claim is '
              f'recorded ({laundered["state"]}) but buys nothing '
              f'({n_before} unbought → {n_after}); a second INDEPENDENT '
              f'`generic` source buys it ({n_bought} left)')

    with guard('ordered reads follow the declaration'):
        # --- ordered reads follow the declaration, not the traversal --------
        honest_order = list(b.formulas())
        st4, root4 = blk.ingest()
        st4.put(blk.piece_core(root4, "袖"), "formula:割り込み",
                "seq 0 に割り込む式", "derived", "declaration:coat", seq=0)
        v4 = blk.BlockView(st4, root4)
        injected = list(v4.formulas())
        check("ordered reads follow the declaration",
              honest_order == [n for n, _t, _s in blk.FORMULA_ORDER]
              and injected[0] == "割り込み"
              and injected[1:] == honest_order,
              f'17 formulas in declaration order across 4 subject cores; a '
              f'seat with seq 0 on a piece core reads FIRST ({injected[0]}), '
              'so the reader sorts by seq, not by traversal')


# ---------------------------------------------------------------------------
@declares('ingest order does not move answers',
          'two subjects cannot declare the same thing',
          'a seat that cannot name itself is refused',
          'contest is reachable at every address',
          'a contest survives the matryoshka',
          'an edge with one end is refused',
          'reads create nothing, loads are verified',
          'the store owns its values',
          'equal is not the same observation',
          'the quarantine core obeys the same law',
          'a fourth piece and a fifth measurement are declarable',
          'an undeclared subject does not swallow the seat',
          'param refuses across subjects',
          'a proposal stays quarantined',
          'an anonymous source buys nothing',
          'the store refuses what it cannot persist',
          'a generic claim is priced by its own kind',
          'the budget arm is reported, never hidden',
          'the loader never raises')
def the_cross_refuses_what_it_should() -> None:
    """Each refusal, with the store that provokes it.

    Every check here was built by first writing the store that violates the
    property and confirming the check rejects it. A check that cannot fail
    is not a check; this project shipped two of those, which is how these
    defects survived a first review.
    """
    with guard('ingest order does not move answers'):
        # Imported INSIDE the guard: these modules build the coat at module
        # scope, so a regressed store raises on IMPORT and every guarded
        # line below would vanish instead of going red.
        import copy as _copy
        import json as _json

        from photoloset import block as blk, cross

        b = blk.coat()

        # --- P1: the order check that can actually fail ---------------------
        plan = [("t", f"k{i}", {"value": float(i)}, "specific", "src")
                for i in range(5)]
        loose = cross.ingest_order_check(plan, nest=False)
        tight = cross.ingest_order_check(plan, nest=True)
        coat_plan = cross.ingest_order_check(b.store.write_plan(), nest=True)
        # #3/#11: the map now carries the ARM, so a plan whose seat lands on
        # a different arm depending on order is order dependent and says so.
        # It did not before: the map was (verdict, repr(value), weight), so
        # every arm-valued answer was outside the check that certifies
        # storage order does not move answers.
        two_kinds = cross.ingest_order_check(
            [("m", "measure:chest", 108.0, "measured", "tape"),
             ("m", "measure:chest", 108.0, "declared", "the catalogue")],
            nest=True)
        arms_seen = sorted({d["forward"][3][0] for d in
                            two_kinds["differences"]}
                           | {d["other"][3][0] for d in
                              two_kinds["differences"]})
        # ...and one thing that DOES move with order and is deliberately not
        # compared, measured here so it is on the record rather than hidden:
        # the child cores' NAMES carry which arm overflowed first, so the
        # coat builds block:coat·cause+·1 forward and block:coat·kind-·1
        # reversed. Every address still resolves to the same value, weight
        # and arm, which is why the check above is green. Comparing the
        # names would call an unbroken coat broken.
        names = []
        for order in (b.store.write_plan(),
                      list(reversed(b.store.write_plan()))):
            s = cross.CrossStore()
            for c, k, v, kd, src in order:
                s.put(c, k, v, kd, src)
            names.append(sorted(s.cores))
        check("ingest order does not move answers",
              loose["verdict"] == cross.ORDER_DEPENDENT
              and tight["verdict"] == "ANSWER"
              and coat_plan["verdict"] == "ANSWER"
              and two_kinds["verdict"] == cross.ORDER_DEPENDENT
              and arms_seen == ["kind-", "support+"]
              and names[0] != names[1] and len(names[0]) == len(names[1])
              and len(loose["differences"]) == 6
              and coat_plan["addresses"] == 56
              and coat_plan["orders"] == 3,
              f'5 addresses on one arm through the NON-nesting writer are '
              f'genuinely order dependent ({len(loose["differences"])} '
              f'differences); nesting makes the same plan order independent; '
              f'the coat\'s {coat_plan["addresses"]} addresses re-ingest '
              f'identically in {coat_plan["orders"]} orders. One address '
              f'reached by two kinds lands on {arms_seen} depending on '
              f'order and is now CAUGHT ({two_kinds["verdict"]}). '
              f'The {len(names[0])} child-core NAMES do differ by order '
              f'and are deliberately not compared — no address moved')

    with guard('two subjects cannot declare the same thing'):
        # --- #2: the cross-subject guard was on _collect but not _ordered --
        # param()/setting() go through _collect and refused correctly. Every
        # COLLECTION read — pieces(), measures(), formulas(), seams(),
        # placement() — goes through _ordered, which had no such guard, so a
        # second subject holding the same name was resolved by the shape of
        # the container instead of by a refusal. Measured before the repair:
        # 18 formula rows declared, formulas() served 17 and the declared
        # 袖ぐり深さ×0.78 was simply gone; a second `role` naming 後身頃 at
        # the root made pieces() serve ['後身頃','前身頃','袖','後身頃'];
        # measures() listed chest twice. contested() was empty, refusals()
        # was empty and verify() said ANSWER for all three.
        def _refusal(fn):
            try:
                fn()
                return "served it anyway"
            except ValueError as exc:
                return str(exc).split(":")[0]

        dup_f = _copy.deepcopy(blk.COAT_DECLARATION)
        dup_f["name"] = "coat_dup_formula"
        st_a, root_a = blk.ingest(
            decl=dup_f,
            formulas=list(blk.FORMULA_ORDER)
            + [("袖ぐり深さ", "別のテキスト", "前身頃")])
        v_a = blk.BlockView(st_a, root_a)

        st_b, root_b = blk.ingest()
        st_b.put(root_b, "role", {"name": "後身頃", "required": True},
                 "declared", "declaration:second")
        v_b = blk.BlockView(st_b, root_b)

        st_c, root_c = blk.ingest()
        st_c.put(blk.piece_core(root_c, "袖"), "measure:chest",
                 {"required": False}, "declared", "declaration:sleeve")
        v_c2 = blk.BlockView(st_c, root_c)

        # ...and the same NAME with the same VALUE is still a refusal, because
        # a collection read cannot be right either way: formulas() would fold
        # the two into one and measures() would list it twice.
        same = [r for r in blk.FORMULA_ORDER if r[0] == "袖ぐり深さ"][0]
        st_d, root_d = blk.ingest(
            decl=_copy.deepcopy(dup_f),
            formulas=list(blk.FORMULA_ORDER)
            + [("袖ぐり深さ", same[1], "前身頃")])
        v_d = blk.BlockView(st_d, root_d)

        got = [_refusal(v_a.formulas), _refusal(v_b.pieces),
               _refusal(v_c2.measures), _refusal(v_d.formulas)]
        quiet = (st_a.contested() == [] and st_b.contested() == []
                 and st_a.verify()["verdict"] == "ANSWER")
        # ...and a genuinely new subject is still declarable.
        grown2 = _copy.deepcopy(blk.COAT_DECLARATION)
        grown2["name"] = "coat_hood2"
        grown2["pieces"] = list(grown2["pieces"]) + [("フード", False)]
        grown2["required"] = tuple(grown2["required"]) + ("neck",)
        grown2["placement"]["フード"] = ((0.0, 40.0, 0.0), "フードは上")
        st_e, root_e = blk.ingest(decl=grown2)
        v_e = blk.BlockView(st_e, root_e)
        check("two subjects cannot declare the same thing",
              got == [blk.AMBIGUOUS_ACROSS_SUBJECTS] * 4
              and quiet
              and len(v_e.pieces()) == 4 and len(v_e.measures()) == 5
              and len(b.formulas()) == 17 and len(b.pieces()) == 3,
              'a duplicate formula name, a duplicate piece name, a duplicate '
              'measurement and a duplicate name carrying the SAME value all '
              f'refuse as {got[0]} — none of them contests, so contested() '
              'and verify() stay silent and only the reader can catch it; a '
              f'genuinely new piece still declares ({len(v_e.pieces())} '
              f'pieces, {len(v_e.measures())} measurements)')

    with guard('a seat that cannot name itself is refused'):
        # --- the hole the #2 fix left open ---------------------------------
        # ``pieces()`` reads the name out of the VALUE, so the guard above
        # needs a callback to say what "the same thing" is. That callback can
        # itself fail on a malformed value, and ``_ordered`` used to answer a
        # failing callback with ``except Exception: continue``. Skipping broke
        # it twice over: the malformed seat evaded the same-name gate, and it
        # stayed in the returned list, so ``pieces()`` died on the raw value
        # with ``TypeError: string indices must be integers`` — an accident,
        # not a refusal. Measured before the repair: a bare-string ``role``
        # gave TypeError and a ``role`` dict with no ``name`` gave KeyError,
        # both with contested() and verify() silent.
        def _refuse(fn):
            try:
                fn()
                return "served it anyway"
            except ValueError as exc:
                return str(exc).split(":")[0]
            except Exception as exc:            # 事故は断りではない
                return f"CRASHED {type(exc).__name__}"

        st_s, root_s = blk.ingest()
        st_s.put(root_s, "role", "後身頃", "declared", "declaration:bare")
        st_t, root_t = blk.ingest()
        st_t.put(root_t, "role", {"required": True}, "declared",
                 "declaration:noname")
        broke = [_refuse(blk.BlockView(st_s, root_s).pieces),
                 _refuse(blk.BlockView(st_t, root_t).pieces)]
        check("a seat that cannot name itself is refused",
              broke == [blk.UNNAMED_IN_COLLECTION] * 2
              and st_s.verify()["verdict"] == "ANSWER"
              and len(b.pieces()) == 3,
              f'a role written as a bare string and a role dict with no '
              f'name both refuse as {broke[0]} instead of crashing the '
              f'reader; the store itself stays ANSWER, so only the reader '
              f'can catch it, and the coat still serves {len(b.pieces())} '
              'pieces')

    with guard('contest is reachable at every address'):
        # --- P2: contest is reachable at EVERY address ----------------------
        subjects = [b.root] + b.store.part_of_children(b.root)
        addresses = [(s, seat["key"]) for s in subjects
                     for seat in b.store.seats(s)]
        bad_addr = []
        for subj, key in addresses:
            st, root = blk.ingest()
            subj2 = subj.replace(b.root, root, 1)
            before = st.census()["seats"]
            r = st.put(subj2, key, {"__rival__": True}, "specific", "rival")
            listed = any(c["key"] == key for c in st.contested())
            if (r["verdict"] != cross.CONTESTED_IN_CROSS
                    or st.census()["seats"] != before or not listed):
                bad_addr.append((subj2, key, r["verdict"]))
        # #15: the numerator used to be len(addresses) too, so a failing run
        # printed "56 of 56 addresses answer CONTESTED ... 53 refused with
        # the wrong verdict" — a message that contradicts itself in one
        # line. Print what was actually measured.
        check("contest is reachable at every address",
              not bad_addr and len(addresses) == 56,
              f'{len(addresses) - len(bad_addr)} of {len(addresses)} coat '
              f'addresses answer CONTESTED to a rival value, consume no '
              f'seat, and appear in contested(); '
              f'{len(bad_addr)} refused with the wrong verdict')

    with guard('a contest survives the matryoshka'):
        # --- P2b: the matryoshka does not hide a contest --------------------
        st = cross.CrossStore()
        for i in range(cross.FACES_PER_ARM):
            st.put("r", f"k{i}", {"v": i}, "specific", "src")
        spill = st.put("r", "k4", {"v": 4}, "specific", "src")
        rival = st.put("r", "k0", {"v": 99}, "specific", "other")
        child = spill["core"]
        orphan = {"cores": {
            "r": [{"key": "param:x", "arm": "kind-", "seq": 1,
                   "values": [{"value": 1, "kind": "specific",
                               "sources": ["a"]}]}],
            "r·kind-·1": [{"key": "param:x", "arm": "kind-", "seq": 2,
                           "values": [{"value": 2, "kind": "specific",
                                       "sources": ["b"]}]}]},
            "edges": []}
        orph = cross.CrossStore.from_dict(orphan)
        # #13: contested()'s CLOSURE walk was unpinned — scanning one core at
        # a time instead of the nest chain left the whole suite green,
        # because in the store above both rival values sit in the same core.
        # This twin puts them in DIFFERENT cores of one nest chain, which is
        # the shape the matryoshka actually produces, and a core-local scan
        # sees no disagreement at all (measured: 0 seats look contested to a
        # per-core scan, while the closure walk finds 1).
        twin = cross.CrossStore.from_dict({"cores": {
            "r": [{"key": "param:x", "arm": "kind-", "seq": 1,
                   "values": [{"value": 1, "kind": "specific",
                               "sources": ["a"]}]}],
            "r·kind-·1": [{"key": "param:x", "arm": "kind-", "seq": 2,
                           "values": [{"value": 2, "kind": "specific",
                                       "sources": ["b"]}]}]},
            "edges": [{"a": ["r", ""], "b": ["r·kind-·1", ""],
                       "label": "nest"}]})
        core_local = [(cn, s["key"]) for cn, seats in twin.cores.items()
                      for s in seats
                      if any(cross._vkey(e["value"])
                             != cross._vkey(s["values"][0]["value"])
                             for e in s["values"][1:])]
        check("a contest survives the matryoshka",
              child != "r" and rival["verdict"] == cross.CONTESTED_IN_CROSS
              and st.resolve("r", "k0")["verdict"] == cross.CONTESTED_IN_CROSS
              and st.resolve(child, "k0")["verdict"] == cross.CONTESTED_IN_CROSS
              and [(c["key"], c["sides"]) for c in st.contested()] == [("k0", 2)]
              and orph.load_verdict["verdict"] == cross.ORPHANED_CORE
              and [(c["core"], c["key"]) for c in twin.contested()]
              == [("r", "param:x")]
              and core_local == [] and len(twin.cores) == 2
              and twin.arm_census("r")["support-"] == 1
              and twin.load_verdict["verdict"] == cross.DUPLICATE_ADDRESS,
              f'k4 spilled to {child}; a rival for k0 contests from both ends '
              f'of the chain; a child its parent cannot reach loads as '
              f'{orph.load_verdict["verdict"]}; two rival values split across '
              f'a nest chain are invisible to a per-core scan '
              f'({len(core_local)} seen) and named by the closure walk '
              f'({len(twin.contested())} seen, support- '
              f'{twin.arm_census("r")["support-"]})')

    with guard('an edge with one end is refused'):
        # --- P4: an edge with one end is not a relation ---------------------
        st2 = cross.CrossStore()
        st2.put("a", "k", {"v": 1}, "specific", "s")
        n_before = len(st2.edges)
        e1 = st2.link(("a", "k"), None, "seam:junk")
        e2 = st2.link(("nowhere", "k"), ("a", "k"), "nest")
        e3 = st2.link(("a", "k"), ("a", "k"), "")
        ok = st2.link(("a", "k"), ("a", "k"), "seam:袖下線")
        poisoned = cross.CrossStore.from_dict(
            {"cores": {"a": []},
             "edges": [{"a": ["a", "k"], "b": None, "label": "nest"},
                       {"a": ["ghost", "k"], "b": ["a", "k"], "label": "nest"},
                       {"a": ["a", "k"], "b": ["a", "k"], "label": ""}]})
        n_bad = len([p for p in poisoned.load_verdict.get("problems", [])
                     if "index" in p])
        check("an edge with one end is refused",
              all(e["verdict"] == cross.DANGLING_EDGE for e in (e1, e2, e3))
              and ok["verdict"] == "ANSWER"
              and len(st2.edges) == n_before + 1
              and poisoned.load_verdict["verdict"] == cross.DANGLING_EDGE
              and n_bad == 3,
              f'3 malformed edges refused and NOT stored ({len(st2.edges)} '
              f'edge, the legal self-relation); a loaded store carrying all '
              f'three names {n_bad}')

    with guard('reads create nothing, loads are verified'):
        # --- P5: reads create nothing, loads are verified -------------------
        st3 = cross.CrossStore()
        st3.put("a", "k", {"v": 1}, "specific", "s")
        snap = _copy.deepcopy(st3.to_dict())
        for i in range(100):
            st3.resolve(f"ghost{i}", "nope")
            st3.contested()
            st3.census()
        poison = {"cores": {"c": [
            {"key": f"k{i}", "arm": "kind-", "seq": i,
             "values": [{"value": i, "kind": "specific", "sources": ["s"]}]}
            for i in range(5)]}, "edges": []}
        over = cross.CrossStore.from_dict(poison)
        # #12: the BOUNDARY form was only ever handed a valid empty store,
        # so `checked["verdict"] == "ANSWER"` could not fail — measured:
        # making from_dict_checked return ANSWER unconditionally left the
        # whole suite green, and a poisoned store crossed the tool boundary
        # as an answer. It is now given stores it must REFUSE, and the
        # refusal has to arrive as a return value, not as a raise.
        refused_at_boundary = []
        for bad in (poison,
                    {"cores": {"c": [{"key": "k", "arm": "kind+", "seq": 1,
                                      "values": [{"value": 1,
                                                  "kind": "specific",
                                                  "sources": ["s"]}]}]},
                     "edges": []},
                    {"cores": {"a": []},
                     "edges": [{"a": ["a", "k"], "b": None,
                                "label": "nest"}]}):
            try:
                refused_at_boundary.append(
                    cross.CrossStore.from_dict_checked(bad)["verdict"])
            except Exception as exc:                        # noqa: BLE001
                refused_at_boundary.append(f"RAISED {type(exc).__name__}")
        checked = cross.CrossStore.from_dict_checked({"cores": {}, "edges": []})
        # #13: put_strict's NO_SUCH_KIND gate was never given an unknown
        # kind by any check — measured: silently registering the kind and
        # filing it on kind- left 55/55 green.
        nk = cross.CrossStore()
        guessed = nk.put_strict("c", "k", 1, "guess", "src")
        guessed_nesting = nk.put("c", "k", 1, "guess", "src")
        check("reads create nothing, loads are verified",
              st3.to_dict() == snap and list(st3.cores) == ["a"]
              and over.load_verdict["verdict"] == cross.OVER_CAPACITY
              and over.census()["over_capacity"] == [("c", "kind-", 5)]
              and refused_at_boundary == [cross.OVER_CAPACITY,
                                          cross.ARM_NOT_DERIVED,
                                          cross.DANGLING_EDGE]
              and checked["verdict"] == "ANSWER"
              and isinstance(checked["store"], cross.CrossStore)
              and guessed["verdict"] == cross.NO_SUCH_KIND
              and guessed_nesting["verdict"] == cross.NO_SUCH_KIND
              and nk.cores == {} and len(nk.refusals) == 1,
              f'100 probes of absent addresses left {len(st3.cores)} core; a '
              f'hand-edited store with 5 seats on one arm loads as '
              f'{over.load_verdict["verdict"]} and census() names it '
              f'{over.census()["over_capacity"]}; three poisoned stores come '
              f'back through the boundary form as {refused_at_boundary} '
              f'rather than raising; an unknown claim kind is '
              f'{guessed["verdict"]} through both writers and stores '
              f'nothing ({len(nk.cores)} cores)')

    with guard('the store owns its values'):
        # --- P6: the store owns its values ----------------------------------
        st4 = cross.CrossStore()
        held = {"value": 1}
        st4.put("c", "k", held, "specific", "a")
        st4.put("c", "k", {"value": 2}, "specific", "b")
        was = st4.resolve("c", "k")["verdict"]
        held["value"] = 2
        still = st4.resolve("c", "k")["verdict"]
        st4.put("c", "j", {"value": 7}, "specific", "a")
        got = st4.resolve("c", "j")
        got["value"]["value"] = 999
        unmoved = st4.resolve("c", "j")["value"]["value"]
        shared = {"value": 1}
        aliased = cross.CrossStore()
        aliased.cores = {"c": [
            {"key": "k1", "arm": "kind-", "seq": 1,
             "values": [{"value": shared, "kind": "specific", "sources": ["a"]}]},
            {"key": "k2", "arm": "kind-", "seq": 2,
             "values": [{"value": shared, "kind": "specific", "sources": ["b"]}]}]}
        check("the store owns its values",
              was == cross.CONTESTED_IN_CROSS
              and still == cross.CONTESTED_IN_CROSS
              and unmoved == 7
              and aliased.aliased_values()["verdict"] == cross.ALIASED_VALUE
              and st4.aliased_values()["verdict"] == "ANSWER",
              'a caller mutating the object it still holds cannot collapse '
              'CONTESTED into ANSWER, and mutating what resolve() returned '
              'leaves the seat at 7; two seats sharing one object are named '
              f'{aliased.aliased_values()["verdict"]}')

    with guard('equal is not the same observation'):
        # --- #4: values that compare equal but are distinguishable ----------
        pairs = [(True, 1), (108.0, 108), (0, False),
                 ({"required": True}, {"required": 1})]
        verdicts = []
        read_back = []
        listed = []
        for a, bb in pairs:
            s = cross.CrossStore()
            s.put("c", "k", a, "declared", "decl-A")
            verdicts.append(s.put("c", "k", bb, "declared", "decl-B")
                            ["verdict"])
            # **The reader has to see it too.** The writer refusing while
            # resolve() folds the two back together with a bare `==` is the
            # same silent discard one layer down, and this check used to
            # assert only the put verdict. Measured before the repair:
            # put -> CONTESTED, then resolve -> ANSWER value=True weight=2,
            # contested() empty, arm_census support- 0.
            read_back.append(s.resolve("c", "k")["verdict"])
            listed.append(len(s.contested()) == 1
                          and s.arm_census("c")["support-"] == 1)
        # ...and the other direction: a value that is not equal to itself
        # is not a rival to itself. **NaN no longer reaches a seat** — it
        # cannot round-trip through the JSON this store saves in, so the
        # writer refuses it (see "the store refuses what it cannot
        # persist"). The property is still the store's, so it is measured
        # where it still lives: at the identity token every comparison in
        # the store goes through, and on a store LOADED with two NaNs, which
        # is the only way one can be seated at all.
        nan = cross.CrossStore()
        nan_refused = [nan.put("c", "k", float("nan"), "declared",
                               "same source")["verdict"] for _ in range(2)]
        nan_loaded = cross.CrossStore.from_dict({"cores": {"c": [
            {"key": "k", "arm": "kind-", "seq": 1, "values": [
                {"value": float("nan"), "kind": "declared",
                 "sources": ["same source"]},
                {"value": float("nan"), "kind": "specific",
                 "sources": ["another"]}]}]}, "edges": []})
        # ...and genuine agreement still costs nothing.
        agree = cross.CrossStore()
        agree.put("c", "k", 108.0, "declared", "a")
        agree.put("c", "k", 108.0, "declared", "b")
        check("equal is not the same observation",
              verdicts == [cross.CONTESTED_IN_CROSS] * 4
              and read_back == [cross.CONTESTED_IN_CROSS] * 4
              # `len(listed) == 4` is redundant with the two clauses above
              # (all three lists are appended in one loop), but `all()` over
              # a sequence whose length is only implied is the shape that
              # hid the sixth tautology. State it.
              and len(listed) == 4 and all(listed)
              and cross._vkey(float("nan")) == ("f", "nan")
              and nan_refused == [cross.UNIDENTIFIABLE_VALUE] * 2
              and nan.cores == {}
              and nan_loaded.contested() == []
              and nan_loaded.resolve("c", "k")["verdict"] == "ANSWER"
              # ...and that store is refused at the loader for the same
              # reason the writer refuses it: it cannot be saved.
              and nan_loaded.load_verdict["verdict"]
              == cross.UNIDENTIFIABLE_VALUE
              and agree.resolve("c", "k")["verdict"] == "ANSWER"
              and agree.resolve("c", "k")["weight"] == 2,
              'True/1, 108.0/108, 0/False and {required: True}/{required: 1} '
              'each CONTEST rather than merging one into the other — at the '
              'writer AND at resolve(), contested() and the support- arm; '
              f'NaN is {nan_refused[0]} at the writer (it is not JSON), and '
              f'where one IS seated — loaded from a hand-written store — it '
              f'does not contest with itself '
              f'({len(nan_loaded.contested())} contests), because the '
              f'identity token folds it; 108.0 twice is still '
              f'weight {agree.resolve("c", "k")["weight"]} on one seat')

    with guard('the quarantine core obeys the same law'):
        # --- #5: 1 core = 24 seats, everywhere or nowhere -------------------
        q = cross.CrossStore()
        for i in range(100):
            q.put("q", f"p{i}", i, "proposed", "someone said")
        sizes = sorted((len(v) for v in q.cores.values()), reverse=True)
        strict = cross.CrossStore()
        for i in range(cross.CAPACITY_PER_CORE):
            strict.put_strict("z", f"p{i}", i, "proposed", "said")
        refused = strict.put_strict("z", "one-too-many", 1, "proposed", "said")
        hand = cross.CrossStore.from_dict({"cores": {"z#proposed": [
            {"key": f"k{i}", "arm": None, "seq": i,
             "values": [{"value": i, "kind": "proposed", "sources": ["s"]}]}
            for i in range(cross.CAPACITY_PER_CORE + 1)]}, "edges": []})
        cen_q = q.census()
        # The law was enforced per ARM (4) and per QUARANTINE (24), and
        # nothing ever compared a core's TOTAL. A core that holds both kinds
        # of seat therefore ran to 20 armed + 24 quarantined = 44 while
        # `over_capacity` stayed empty and verify() said ANSWER. Measured
        # here from both ends: the writer refuses the 25th seat of ANY kind,
        # and a hand-written 25-seat mixed core loads as OVER_CAPACITY.
        # A core NAMED as quarantine takes armed writes — a name is not a
        # type, and that is how the 44-seat core was built. What it can no
        # longer do is take PROPOSALS: those land in a core the store
        # itself mints, so the writer cannot mix armed and quarantined
        # seats in one core at all. Measured from both ends here: the
        # writer's 20 armed seats stay 20 while the 5 proposals go
        # somewhere else, and the mixed 25-seat core is built at the
        # loader, where it can still be handed in.
        mixed = cross.CrossStore()
        for i in range(cross.FACES_PER_ARM):
            for kind in ("measured", "derived", "feeds", "specific",
                         "generic"):
                mixed.put_strict("m#proposed", f"{kind}{i}", float(i), kind,
                                 "a source")
        mixed_seats = len(mixed.cores["m#proposed"])
        spill = [mixed.put_strict("m#proposed", f"extra{i}", float(i),
                                  "proposed", "said")["core"]
                 for i in range(5)]
        # 20 armed seats (4 on each of the 5 writable arms) + 5 quarantined
        # = 25. Every per-arm budget is legal and the quarantine budget is
        # legal; ONLY the core's own total is broken, so nothing but the
        # total rule can catch this store.
        legal_arms = [(k, cross.KIND_ARM[k]) for k in
                      ("measured", "derived", "feeds", "specific", "generic")]
        loaded_mixed = cross.CrossStore.from_dict({"cores": {"m": (
            [{"key": f"{kind}{i}", "arm": arm, "seq": 100 + i,
              "values": [{"value": float(i), "kind": kind,
                          "sources": ["a source"]}]}
             for kind, arm in legal_arms
             for i in range(cross.FACES_PER_ARM)]
            + [{"key": f"p{i}", "arm": None, "seq": 200 + i,
                "values": [{"value": i, "kind": "proposed",
                            "sources": ["said"]}]}
               for i in range(5)])}, "edges": []})
        check("the quarantine core obeys the same law",
              max(sizes) <= cross.CAPACITY_PER_CORE and sum(sizes) == 100
              and refused["verdict"] == cross.ARM_FULL
              and hand.load_verdict["verdict"] == cross.OVER_CAPACITY
              and hand.census()["over_capacity"] == [
                  ("z#proposed", None, 25), ("z#proposed", "total", 25)]
              and cen_q["over_capacity"] == []
              and sum(cen_q["quarantined"].values()) == 100
              # ...and the same 24 counted over the WHOLE core, not per arm.
              and mixed_seats == 20
              and spill == ["m#proposed#proposed"] * 5
              and len(mixed.cores["m#proposed"]) == 20
              and mixed.census()["over_capacity"] == []
              and loaded_mixed.load_verdict["verdict"] == cross.OVER_CAPACITY
              and ("m", "total", 25) in loaded_mixed.census()["over_capacity"],
              f'100 proposals nest into {len(sizes)} cores of {sizes} rather '
              f'than one core of 100; the strict writer refuses the 25th '
              f'({refused["verdict"]}); a hand-written 25-seat quarantine '
              f'core loads as {hand.load_verdict["verdict"]} and census() '
              f'names all {sum(cen_q["quarantined"].values())} quarantined '
              f'seats so the exemption cannot be silent; a core holding '
              f'{mixed_seats} armed seats cannot be filled to 25 by the '
              f'writer at all — its 5 proposals land in {spill[-1]!r}, a '
              f'core the store minted — and the 25-seat mixed core, which '
              f'can still be handed to the loader, comes back '
              f'{loaded_mixed.load_verdict["verdict"]} on the total alone')

    with guard('a fourth piece and a fifth measurement are declarable'):
        # --- P8: the declaration can grow -----------------------------------
        grown = _copy.deepcopy(blk.COAT_DECLARATION)
        grown["name"] = "coat_hooded"
        grown["pieces"] = list(grown["pieces"]) + [("フード", False)]
        grown["required"] = tuple(grown["required"]) + ("neck", "waist")
        grown["placement"]["フード"] = ((0.0, 40.0, 0.0), "フードは上")
        st5, root5 = blk.ingest(decl=grown)
        v5 = blk.BlockView(st5, root5)
        twice = _copy.deepcopy(blk.COAT_DECLARATION)
        twice["name"] = "coat_twice"
        twice["pieces"] = list(twice["pieces"]) + [("後身頃", False)]
        st6, root6 = blk.ingest(decl=twice)
        v6 = blk.BlockView(st6, root6)
        dbl = st6.contested()
        served = "served a list anyway"
        try:
            v6.pieces()
        except ValueError as e:
            served = str(e).split(":")[0]
        check("a fourth piece and a fifth measurement are declarable",
              len(v5.pieces()) == 4 and len(v5.measures()) == 6
              and st5.census()["over_capacity"] == []
              and st5.census()["cores"] == 11
              and not st5.contested()
              and len(st6.part_of_children(root6)) == 3
              and len(dbl) == 1 and dbl[0]["key"] == "role"
              and served == cross.CONTESTED_IN_CROSS
              and len(v6.refusals()) == 1,
              f'{len(v5.pieces())} pieces, {len(v5.measures())} measurements, '
              f'{st5.census()["cores"]} cores, no crash; re-declaring 後身頃 '
              f'with a different `required` contests at the existing piece '
              f'rather than seating a 4th ({len(st6.part_of_children(root6))} '
              f'pieces), and the reader refuses to serve the list ({served})')

    with guard('an undeclared subject does not swallow the seat'):
        # --- a subject nobody declared must not swallow the seat ------------
        ghost = _copy.deepcopy(blk.COAT_DECLARATION)
        ghost["name"] = "coat_ghost"
        ghost["params"] = [("half_divisor", 4.0, None, "specific", "存在しない枚")
                           ] + [r for r in ghost["params"]
                                if r[0] != "half_divisor"]
        st8, root8 = blk.ingest(decl=ghost)
        v8 = blk.BlockView(st8, root8)
        stranded = [n for n in st8.cores if "存在しない" in n]
        ref = v8.refusals()
        try:
            readable = v8.param("half_divisor")
        except ValueError as e:
            readable = str(e).split(":")[0]
        check("an undeclared subject does not swallow the seat",
              readable == 4.0
              and len(st8.cores) == 10 and not stranded
              and len(ref) == 1 and ref[0]["verdict"] == blk.NO_SUCH_SUBJECT
              and ref[0]["key"] == "param:half_divisor"
              and not b.refusals(),
              'a param declared against a piece that was never declared would '
              'sit in a core no part_of edge reaches — readable by nobody, '
              f'refused by nobody. It now seats on the root (reads back '
              f'{readable}) and says '
              f'{ref[0]["verdict"] if ref else "nothing"}; '
              f'{len(stranded)} stranded cores of {len(st8.cores)} scanned)')

    with guard('param refuses across subjects'):
        # --- the new hazard the reshaping creates ---------------------------
        st7, root7 = blk.ingest()
        st7.put(blk.piece_core(root7, "袖"), "param:half_divisor",
                {"value": 3.0}, "specific", "declaration:sleeve")
        v7 = blk.BlockView(st7, root7)
        picked = "silently picked one"
        try:
            v7.param("half_divisor")
        except ValueError as e:
            picked = str(e).split(":")[0]
        check("param refuses across subjects",
              picked == blk.AMBIGUOUS_ACROSS_SUBJECTS
              and st7.contested() == []
              and b.param("half_divisor") == 4.0,
              'block:coat says 4.0 and block:coat/piece:袖 says 3.0 — two '
              'DIFFERENT addresses, so contested() is correctly silent, and '
              f'a naive search would return whichever it met first ({picked})')

    with guard('a proposal stays quarantined'):
        # --- #5 residual: the write-back path, and the substring test ------
        # put() handed back "q#proposed" and then computed the split home as
        # "q#proposed#proposed" — a core NOBODY EVER CREATED. The nest link
        # was refused (one end missing), the children floated free, and the
        # writer was told ANSWER twice for two contradictory values at one
        # address while the reader was told the address does not exist.
        w = cross.CrossStore()
        home = w.put("q", "p0", 0, "proposed", "someone said")["core"]
        for i in range(1, 30):
            w.put(home, f"p{i}", i, "proposed", "someone said")
        nests = sum(1 for e in w.edges if e["label"] == "nest")
        a = w.put(home, "hem_length", 88.0, "proposed", "the tailor")
        rival = w.put(home, "hem_length", 999.0, "proposed", "the catalogue")
        # ...and a core whose name merely LOOKS like quarantine is not
        # quarantine: a rumour written there must not contest a measurement.
        # **The name is not the type.** The previous pass narrowed the test
        # from "contains #proposed" to "ends with #proposed" and called it
        # structural. A suffix is not a structure: the store itself PUBLISHES
        # such names (put() returns "q#proposed"; to_dict and census carry
        # it), so a writer who round-trips the store's own core list writes
        # straight into the quarantine test. Measured then, on three names
        # nobody had to invent: a measurement at "review#proposed" was
        # CONTESTED by a rumour, and verify() said ANSWER.
        looks = ["review#proposed-revisions", "review#proposed",
                 "notes#proposed", "block:coat#proposed"]
        rumours = {}
        for nm in looks:
            t = cross.CrossStore()
            t.put(nm, "measure:chest", 108.0, "measured", "tape")
            r_ = t.put(nm, "measure:chest", 999.0, "proposed",
                       "a rumour in the studio")
            rumours[nm] = (r_["core"], len(t.contested()),
                           t.resolve(nm, "measure:chest")["verdict"])
        look = looks[0]
        n = cross.CrossStore()
        n.put(look, "measure:chest", 108.0, "measured", "tape")
        rumour = n.put(look, "measure:chest", 999.0, "proposed",
                       "a rumour in the studio")
        # ...and the strongest form, needing no invented name at all: the
        # store mints "q#proposed", publishes it, and a writer feeds it back
        # with a MEASUREMENT. That claim used to be seated — on a real arm,
        # inside quarantine, where resolve() from the subject could not
        # reach it (UNKNOWN_NOT_IN_CROSS) while it spent support+ budget.
        back = cross.CrossStore()
        minted = back.put("q", "hem", 999.0, "proposed", "gossip")["core"]
        armed = back.put(minted, "measure:chest", 108.0, "measured", "tape")
        # ...and a core the WRITER already owns under that name is not taken
        # over: the store mints the next free address instead.
        taken = cross.CrossStore()
        taken.put("x#proposed", "measure:chest", 108.0, "measured", "tape")
        elsewhere = taken.put("x", "hem", 999.0, "proposed", "gossip")["core"]
        # ...and quarantine survives storage, because it is state and not a
        # spelling. A set that evaporates on save is a name test again.
        trip = cross.CrossStore.from_dict(_json.loads(
            _json.dumps(back.to_dict())))
        trip_armed = trip.put(minted, "measure:sleeve", 60.0, "measured",
                              "tape")
        # ...and the case a NAME could never carry across storage: the
        # collision core "x#proposed2" is quarantine because the store said
        # so, and nothing about its spelling says so. If the set did not
        # travel, this is the line that would notice.
        trip_taken = cross.CrossStore.from_dict(_json.loads(
            _json.dumps(taken.to_dict())))
        trip_taken_armed = trip_taken.put_strict("x#proposed2", "chest",
                                                 108.0, "measured", "tape")
        # ...and an armed seat handed IN through the loader is named, not
        # accepted in silence.
        smuggled = cross.CrossStore.from_dict({
            "cores": {"z#proposed": [
                {"key": "chest", "arm": "support+", "seq": 1,
                 "values": [{"value": 108.0, "kind": "measured",
                             "sources": ["tape"]}]}]},
            "quarantine": ["z#proposed"], "edges": []})
        # ...and a split child whose parent was never created is an orphan,
        # which is what made the write-back damage invisible to verify().
        lost = cross.CrossStore.from_dict({"cores": {
            "ghost·proposed·1": [
                {"key": "k", "arm": None, "seq": 1,
                 "values": [{"value": 1, "kind": "proposed",
                             "sources": ["s"]}]}]}, "edges": []})
        # ...and a split that cannot be linked must not report ANSWER.
        class _NoLink(cross.CrossStore):
            def link(self, a, b, label, value=None):
                return {"verdict": cross.DANGLING_EDGE, "why": ["refused"],
                        "stored": False}
        nl = _NoLink()
        for i in range(cross.FACES_PER_ARM):
            nl.put_strict("c", f"k{i}", float(i), "specific", "s")
        spilled = nl.put("c", "k9", 9.0, "specific", "s")
        check("a proposal stays quarantined",
              home == "q#proposed"
              and sorted(w.cores) == ["q#proposed", "q#proposed·proposed·1"]
              and nests == 1
              and w.verify()["verdict"] == "ANSWER"
              and rival["verdict"] == cross.CONTESTED_IN_CROSS
              and len(w.contested()) == 1
              and w.resolve(home, "hem_length")["verdict"]
              == cross.CONTESTED_IN_CROSS
              # **quarantine is the store's own set, not a spelling.**
              and w._is_quarantine("q#proposed")
              and w._is_quarantine("q#proposed·proposed·1")
              and not w._is_quarantine("q")
              and not n._is_quarantine(look)
              and not n._is_quarantine("notes#proposedX")
              # ...so every core that merely looks quarantined keeps its
              # measurement and isolates the rumour somewhere else.
              and rumours == {
                  "review#proposed-revisions":
                      ("review#proposed-revisions#proposed", 0, "ANSWER"),
                  "review#proposed": ("review#proposed#proposed", 0,
                                      "ANSWER"),
                  "notes#proposed": ("notes#proposed#proposed", 0, "ANSWER"),
                  "block:coat#proposed": ("block:coat#proposed#proposed", 0,
                                          "ANSWER")}
              and rumour["core"] == look + "#proposed"
              and n.contested() == []
              and n.resolve(look, "measure:chest")["verdict"] == "ANSWER"
              # ...and the store's OWN published name refuses an armed claim
              # from both directions, before and after storage.
              and minted == "q#proposed"
              and armed["verdict"] == cross.CLAIM_IN_QUARANTINE
              and back.resolve("q", "measure:chest")["verdict"]
              == cross.NOT_IN_CROSS
              and trip.quarantine == back.quarantine
              and trip_armed["verdict"] == cross.CLAIM_IN_QUARANTINE
              and sorted(trip_taken.quarantine) == ["x#proposed2"]
              and trip_taken_armed["verdict"] == cross.CLAIM_IN_QUARANTINE
              and smuggled.load_verdict["verdict"]
              == cross.CLAIM_IN_QUARANTINE
              # ...and a name the writer already owns is not taken over.
              and elsewhere == "x#proposed2"
              and taken.resolve("x#proposed", "measure:chest")["verdict"]
              == "ANSWER"
              and lost.load_verdict["verdict"] == cross.ORPHANED_CORE
              and spilled["verdict"] == cross.DANGLING_EDGE
              and "c·kind-·1" not in nl.cores,
              f'30 proposals written back to the core put() itself returned '
              f'nest into {sorted(w.cores)} with {nests} nest edge — not a '
              f'"{home}#proposed" nobody created — so two rival hems at one '
              f'address answer {rival["verdict"]} instead of two ANSWERs the '
              f'reader cannot see; NONE of the {len(rumours)} cores merely '
              f'NAMED like quarantine is quarantine, so each rumour is '
              f'isolated elsewhere ({rumour["core"]!r}) and each measurement '
              f'still reads '
              f'{n.resolve(look, "measure:chest")["verdict"]}; feeding the '
              f'store its OWN published core name back with a measurement is '
              f'{armed["verdict"]} (and still {trip_armed["verdict"]} after '
              f'a JSON round trip, because the quarantine set travels), one '
              f'smuggled in through the loader is '
              f'{smuggled.load_verdict["verdict"]}, and a core the writer '
              f'already owns under that name is left alone — the store mints '
              f'{elsewhere!r} instead, whose SPELLING says nothing and which '
              f'is still quarantine after a round trip '
              f'({trip_taken_armed["verdict"]}); a child whose '
              f'parent was never created loads as '
              f'{lost.load_verdict["verdict"]}; a split whose nest link is '
              f'refused answers {spilled["verdict"]} and seats nothing')

    with guard('an anonymous source buys nothing'):
        # --- #0 residual: "" was counted as one of the two sources ---------
        an = cross.CrossStore()
        blank = an.put("c", "k", "wrap fronts cross right over left",
                       "generic")
        after_blank = len(an.cores)
        named = an.put("c", "k", "wrap fronts cross right over left",
                       "generic", "a textbook")
        # ...and trivial respellings of ONE witness are not two witnesses.
        sp = cross.CrossStore()
        sp.put("c", "k", 1, "generic", "Bunka Fashion College, 1999")
        sp.put("c", "k", 1, "generic", " bunka fashion college,  1999 ")
        second = sp.put("c", "k", 1, "generic", "the tailor's own sheet")
        # **Whitespace and case were the only two spellings folded**, and
        # each pair below is ONE witness that BOUGHT the claim: punctuation,
        # a hyphen, a curly apostrophe, and — in a Japanese-first codebase,
        # routine rather than adversarial — full-width digits. Measured
        # then: unbought_generics() == [], weight_by_kind {'generic': 2}.
        one_witness = {}
        for a_, b_ in (("Bunka College, 1999", "Bunka College 1999"),
                       ("Bunka College", "Bunka College."),
                       ("Bunka-College", "Bunka College"),
                       ("O'Hara's", "O’Hara’s"),
                       ("文化 1999", "文化 １９９９")):
            t_ = cross.CrossStore()
            t_.put("c", "k", 1, "generic", a_)
            t_.put("c", "k", 1, "generic", b_)
            one_witness[a_] = (t_.resolve("c", "k")["weight"],
                               len(t_.unbought_generics()),
                               len(t_.cores["c"][0]["values"][0]["sources"]))
        # ...and two genuinely different names still buy it, so the folding
        # is not simply "everything is one source".
        two_witnesses = cross.CrossStore()
        two_witnesses.put("c", "k", 1, "generic", "Bunka College")
        two_witnesses.put("c", "k", 1, "generic", "the tailor's own sheet")
        # ...a blank source on a claim that is NOT generic still stores; the
        # gate priced here is GENERIC_MIN_SOURCES, not authorship.
        # ...and a store LOADED from JSON can still carry a blank source,
        # which is the path the writer's refusal cannot cover: the price is
        # counted from the named sources only.
        loaded_blank = cross.CrossStore.from_dict({"cores": {"c": [
            {"key": "k", "arm": "kind+", "seq": 1,
             "values": [{"value": 1, "kind": "generic",
                         "sources": ["", "", "a textbook"]}]}]},
            "edges": []})
        sk = cross.CrossStore()
        specific = sk.put("c", "k", 1, "specific", "")
        check("an anonymous source buys nothing",
              blank["verdict"] == cross.UNNAMED_SOURCE
              and blank["stored"] is False
              and after_blank == 0
              and named["verdict"] == "ANSWER"
              and [g["weight"] for g in an.unbought_generics()] == [1]
              and an.resolve("c", "k")["weight"] == 1
              and sp.resolve("c", "k")["weight"] == 2
              and second["verdict"] == "ANSWER"
              and sp.unbought_generics() == []
              and len(sp.cores["c"][0]["values"][0]["sources"]) == 2
              and one_witness == {
                  "Bunka College, 1999": (1, 1, 1),
                  "Bunka College": (1, 1, 1),
                  "Bunka-College": (1, 1, 1),
                  "O'Hara's": (1, 1, 1),
                  "文化 1999": (1, 1, 1)}
              and two_witnesses.unbought_generics() == []
              and two_witnesses.resolve("c", "k")["weight"] == 2
              and [g["weight"] for g in loaded_blank.unbought_generics()]
              == [1]
              and loaded_blank.resolve("c", "k")["weight"] == 1
              and specific["verdict"] == "ANSWER",
              f'a generic claim with no source is {blank["verdict"]} and '
              f'stores nothing ({after_blank} cores), so one named source '
              f'leaves it unbought at weight '
              f'{[g["weight"] for g in an.unbought_generics()]}; four '
              f'spellings of one witness count '
              f'{len(sp.cores["c"][0]["values"][0]["sources"])} and a real '
              f'second source buys it; {len(one_witness)} further pairs — '
              f'a comma, a full stop, a hyphen, a curly apostrophe and '
              f'full-width digits — each stay ONE witness (weight 1, still '
              f'unbought, and the second spelling adds no name) while two '
              f'genuinely different names still buy the claim at weight '
              f'{two_witnesses.resolve("c", "k")["weight"]}; '
              f'a loaded store whose generic claim '
              f'lists ["", "", "a textbook"] is still unbought at weight '
              f'{[g["weight"] for g in loaded_blank.unbought_generics()]}; '
              f'a blank source on a `specific` claim is still '
              f'{specific["verdict"]}')

    with guard('the store refuses what it cannot persist'):
        # --- #4/#5 residual: repr() is not identity, and set never
        # round-trips through the JSON this store says it saves in.
        class _Length:
            def __init__(self, n, unit):
                self.n, self.unit = n, unit

            def __repr__(self):
                return f"Length({self.n})"

        keep = cross.CrossStore()
        cm = keep.put("c", "measure:chest", _Length(108, "cm"), "measured",
                      "the tailor (cm)")
        inch = keep.put("c", "measure:chest", _Length(108, "in"), "measured",
                        "the catalogue (inches)")
        cyc = []
        cyc.append(cyc)
        self_ref = {}
        self_ref["self"] = self_ref
        kinds = {name: keep.put("c", f"k:{name}", v, "measured", "x")["verdict"]
                 for name, v in (("set", {1, 2}),
                                 ("frozenset", frozenset({1, 2})),
                                 ("bytes", b"108"),
                                 ("int-keyed dict", {1: "a"}),
                                 ("nested", {"a": [1, {2: "b"}]}),
                                 # **NaN and ±Infinity are floats and are
                                 # not JSON.** They were accepted, and
                                 # `json.dumps` then wrote the bare tokens
                                 # NaN / Infinity, which no conforming
                                 # parser reads — over MCP that makes the
                                 # whole JSON-RPC reply unreadable, and the
                                 # saved file too. The check that pinned
                                 # this asserted only that `json.dumps`
                                 # raised TypeError, and NaN does not raise
                                 # TypeError, so the check stayed green
                                 # while the property in its own name was
                                 # false. It is asserted with
                                 # allow_nan=False below.
                                 ("nan", float("nan")),
                                 ("inf", float("inf")),
                                 ("-inf", float("-inf")),
                                 ("nan inside a list", [1.0, float("nan")]),
                                 # ...and a value that contains itself is
                                 # REFUSED rather than raising
                                 # RecursionError out of the store — the
                                 # format it saves in can say "circular
                                 # reference", so the store cannot be worse
                                 # at refusing than the format.
                                 ("a list holding itself", cyc),
                                 ("a dict holding itself", self_ref))}
        # **A seat has four fields, not one.** `source`, `key` and the core
        # NAME reproduced the exact TypeError the value check exists for —
        # through the public writer, with put() and verify() both ANSWER.
        fields = {
            "source": keep.put("c", "k:src", 1.0, "measured", {"lab"}),
            "key": keep.put("c", frozenset({"a"}), 1, "measured", "t"),
            "core": keep.put(("b", "c"), "k", 1, "measured", "t"),
            "tuple key": keep.put("c", ("measure", "chest"), 108.0,
                                  "measured", "t"),
            "empty core": keep.put("", "k", 1, "measured", "t"),
        }
        ok_kinds = {name: keep.put("c", f"ok:{name}", v, "measured",
                                   "x")["verdict"]
                    for name, v in (("tuple", (0.0, 1.0, 2.0)),
                                    ("float", 108.0), ("bool", True),
                                    ("none", None),
                                    ("dict", {"required": True}))}
        # **The assertion has to be the promise.** `json.dumps` without
        # allow_nan=False emits NaN and Infinity happily, so the old form of
        # this line could not see the three values it was supposed to
        # refuse.
        try:
            _json.dumps(keep.to_dict(), allow_nan=False)
            persists = True
        except (TypeError, ValueError):
            persists = False
        loaded = cross.CrossStore.from_dict({"cores": {"c": [
            {"key": "k", "arm": "support+", "seq": 1,
             "values": [{"value": {1: "a"}, "kind": "measured",
                         "sources": ["x"]}]}]}, "edges": []})
        check("the store refuses what it cannot persist",
              cm["verdict"] == cross.UNIDENTIFIABLE_VALUE
              and inch["verdict"] == cross.UNIDENTIFIABLE_VALUE
              and len(kinds) == 11
              and set(kinds.values()) == {cross.UNIDENTIFIABLE_VALUE}
              and len(fields) == 5
              and set(f["verdict"] for f in fields.values()) \
              == {cross.UNIDENTIFIABLE_VALUE}
              and sorted(f["field"] for f in fields.values()) \
              == ["core", "core", "key", "key", "source"]
              and set(ok_kinds.values()) == {"ANSWER"}
              and persists
              and loaded.load_verdict["verdict"]
              == cross.UNIDENTIFIABLE_VALUE,
              f'two Length objects whose repr is the same string — '
              f'Length(108, "cm") and Length(108, "in") — are '
              f'{cm["verdict"]} at the writer rather than one merged '
              f'ANSWER of weight 2 carrying whichever unit arrived first; '
              f'{len(kinds)} shapes the JSON form cannot hold are refused '
              f'— including NaN, ±Infinity and a value that contains itself '
              f'(which used to raise RecursionError out of the store) — and '
              f'{len(ok_kinds)} that it can are seated, so '
              f'json.dumps(to_dict(), allow_nan=False) holds ({persists}); '
              f'the other {len(fields)} FIELDS of a seat are refused by the '
              f'same measure ({sorted(set(f["field"] for f in fields.values()))}'
              f'), which is what json.dumps used to die on with put() '
              f'answering ANSWER; a hand-written '
              f'store carrying one loads as {loaded.load_verdict["verdict"]}')

    with guard('a generic claim is priced by its own kind'):
        # --- #0 residual: the GATE was not fooled, the READ was ------------
        # The previous pass put `weight_by_kind` BESIDE the misleading
        # number and left `weight` — the key every reader reaches for —
        # carrying the union across kinds. Measured then: one generic claim
        # plus three other kinds, each with one source, read as weight 4
        # while `unbought_generics` priced the same claim at 1. **The union
        # is gone**: `weight` is the strongest single kind — the same
        # measure GENERIC_MIN_SOURCES prices with — so no scalar in the
        # payload can outrun the gate any more.
        pr = cross.CrossStore()
        pr.put("c", "k", 1, "generic", "a textbook")
        pr.put("c", "k", 1, "specific", "this coat's own sheet")
        r = pr.resolve("c", "k")
        four = cross.CrossStore()
        for kind, who in (("generic", "a textbook"), ("specific", "this coat"),
                          ("declared", "the label"), ("measured", "tape")):
            four.put("parts", "closure", "v", kind, who)
        r4 = four.resolve("parts", "closure")
        gate4 = [g["weight"] for g in four.unbought_generics()]
        scalars = sorted(v for k, v in r4.items()
                         if isinstance(v, int) and not isinstance(v, bool)
                         and k not in ("agreed", "seq"))
        check("a generic claim is priced by its own kind",
              r["weight"] == 1 and r["weight_kind"] == "generic"
              and r["weight_by_kind"] == {"generic": 1, "specific": 1}
              and r["sources"] == ["a textbook"]
              and [g["weight"] for g in pr.unbought_generics()] == [1]
              and sorted(r["kinds"]) == ["generic", "specific"]
              # ...and the four-kind form the finding measured: nothing in
              # the payload prices the claim above what the gate does.
              and r4["weight"] == 1 and gate4 == [1]
              and max(scalars) <= gate4[0]
              and r4["weight_by_kind"] == {"generic": 1, "specific": 1,
                                           "declared": 1, "measured": 1}
              and len(r4["named_sources"]) == 4,
              f'one generic source plus one specific source reads as weight '
              f'{r["weight"]} — the number GENERIC_MIN_SOURCES prices, not '
              f'the union across kinds — and matches what the gate says '
              f'({[g["weight"] for g in pr.unbought_generics()]}); with all '
              f'four kinds on one address the gate prices it at {gate4[0]} '
              f'and the largest number resolve() reports is {max(scalars)} '
              f'({r4["weight_by_kind"]} over '
              f'{len(r4["named_sources"])} named sources)')

    with guard('the budget arm is reported, never hidden'):
        # --- #1 residual: WHO PAYS THE FACE IS STILL THE WRITER'S ORDER ----
        # This check does not decide the question — it holds the store to
        # SAYING SO. The three ways out are written into cross._arm_load and
        # into README.md; whichever is chosen, this check changes with it.
        bud = cross.CrossStore()
        placed = [bud.put_strict("c", f"k{i}", float(i), "measured", "tape")
                  for i in range(cross.FACES_PER_ARM)]
        direct = bud.put_strict("c", "k5", 99.0, "measured", "tape")
        first = bud.put_strict("c", "k5", 99.0, "derived", "the formula")
        second = bud.put_strict("c", "k5", 99.0, "measured", "tape")
        cen = bud.census()
        # **The instrument has to survive being saved.** `uncharged` was a
        # WRITE-SESSION LOG: two stores with identical cores, edges and
        # answers reported different free-riding arms depending on whether
        # they had just been written or just been loaded (measured: 1 entry
        # before storage, 0 after, with every condition it described
        # unchanged). The owner cannot decide the budget-arm question on an
        # instrument that evaporates on save, so it is derived from the
        # seats now and the round trip is asserted here.
        stored = cross.CrossStore.from_dict(
            _json.loads(_json.dumps(bud.to_dict())))
        cen_stored = stored.census()
        plan = [("m", "measure:chest", 108.0, "measured", "tape"),
                ("m", "measure:chest", 108.0, "derived", "chest / 4 x 4")]
        drift = cross.ingest_order_check(plan, nest=True)
        coat_cen = b.store.census()
        check("the budget arm is reported, never hidden",
              direct["verdict"] == cross.ARM_FULL
              and first["verdict"] == "ANSWER"
              and second["state"] == "second_kind"
              and second["charged_arm"] == "cause+"
              and second["uncharged"]["uncharged_arm"] == "support+"
              and second["uncharged"]["would_overflow"] is True
              and cen["budget_arm_rule"] == "first_kind_seated"
              and len(cen["two_kind_addresses"]) == 1
              and len(drift["differences"]) == 2
              and len(cen["uncharged"]) == 1
              # ...and storage does not move it, in either direction.
              and cen_stored["uncharged"] == cen["uncharged"]
              and cen_stored["two_kind_addresses"] \
              == cen["two_kind_addresses"]
              # ...and every accepted write says which arm paid, including
              # the one that CHOOSES the arm.
              and [r["charged_arm"] for r in placed] == ["support+"] * 4
              and [r["arm"] for r in placed] == ["support+"] * 4
              and placed[0]["state"] == "placed"
              and first["charged_arm"] == "cause+"
              and cen["arms_present"]["support+"] == 5
              and cen["arms"]["support+"] == 4
              and drift["verdict"] == cross.ORDER_DEPENDENT
              and drift["budget_arm_differences"] == 2
              # ...and the coat has no such address, which is why the
              # question is open rather than urgent.
              and coat_cen["two_kind_addresses"] == []
              and coat_cen["uncharged"] == [],
              f'a support+ claim REFUSED directly ({direct["verdict"]}) is '
              f'accepted as a second kind on a seat opened by cause+ '
              f'({second["state"]}), so support+ shows '
              f'{cen["arms_present"]["support+"]} present against '
              f'{cen["arms"]["support+"]} charged; the store now says which '
              f'arm paid ({second["charged_arm"]}), which one rode free '
              f'({second["uncharged"]["uncharged_arm"]}, already full: '
              f'{second["uncharged"]["would_overflow"]}) and how many '
              f'addresses this touches ({len(cen["two_kind_addresses"])}); '
              f'ingest_order_check calls the same plan '
              f'{drift["verdict"]} with {drift["budget_arm_differences"]} of '
              f'{len(drift["differences"])} differences being the budget arm '
              f'alone; the seat-CREATING write says it too '
              f'(state {placed[0]["state"]}, charged_arm '
              f'{[r["charged_arm"] for r in placed]}), and a JSON round trip '
              f'reports '
              f'the same {len(cen_stored["uncharged"])} uncharged arm '
              f'rather than none. THE COAT HAS '
              f'{len(coat_cen["two_kind_addresses"])} '
              f'two-kind addresses, so no answer moves today — the choice '
              f'among (a) canonical ARMS order, (b) charge every arm, '
              f'(c) refuse the second kind is the owner\'s, and cross.py '
              f'_arm_load says what each one costs')

    with guard('the loader never raises'):
        # --- the boundary-safe loader RAISED, on plain hand-written JSON ---
        # `from_dict_checked` exists for one sentence — "a refusal is a
        # return value; nothing crossing a tool boundary may raise" — and it
        # raised TypeError on a seat whose key was a list (inside verify's
        # `if k in seen`) and on a store with a text `seq` (inside
        # from_dict's own `max()`). Both are reachable without hand-editing
        # anything: put() accepted a tuple key and a text seq, answered
        # ANSWER, and json.dumps of THAT store produced the blob that killed
        # the loader.
        #
        # Every blob below is fed to the loader; nothing may raise, each
        # must come back as a verdict, and the store it hands back must be
        # readable — seats(), census(), verify(), to_dict() and json.dumps
        # all run over it, because a loader that returns a store nobody can
        # read has only moved the raise one line down.
        blobs = {
            "a key that is a list": {"cores": {"c": [
                {"key": ["a", "b"], "arm": None, "seq": 1, "values": []}]},
                "edges": []},
            "a seq that is a word": {"cores": {"c": [
                {"key": "k1", "arm": None, "seq": "first", "values": []},
                {"key": "k2", "arm": None, "seq": 2, "values": []}]},
                "edges": []},
            "a core name that is a number": {"cores": {1: []}, "edges": []},
            "a core that is not a list": {"cores": {"c": "seats"},
                                          "edges": []},
            "a seat that is not a dict": {"cores": {"c": ["seat"]},
                                          "edges": []},
            "an arm that is a number": {"cores": {"c": [
                {"key": "k", "arm": 7, "seq": 1, "values": []}]},
                "edges": []},
            "values that are a string": {"cores": {"c": [
                {"key": "k", "arm": None, "seq": 1, "values": "one"}]},
                "edges": []},
            "sources that are a string": {"cores": {"c": [
                {"key": "k", "arm": "kind-", "seq": 1, "values": [
                    {"value": 1, "kind": "specific", "sources": "s"}]}]},
                "edges": []},
            "edges that are not a list": {"cores": {}, "edges": 3},
            "an edge that is a number": {"cores": {}, "edges": [7]},
            "a quarantine that is a number": {"cores": {}, "edges": [],
                                              "quarantine": 3},
            "a seq the store cannot count": {"cores": {}, "edges": [],
                                             "seq": "many"},
            "cores that are a list": {"cores": [], "edges": []},
            "no store at all": "a store",
            "nothing": {},
        }
        raised = []
        verdicts = {}
        for label, blob in blobs.items():
            try:
                r = cross.CrossStore.from_dict_checked(blob)
                verdicts[label] = r["verdict"]
                st_ = r["store"]
                for core in list(st_.cores):
                    st_.seats(core)
                st_.census()
                st_.verify()
                st_.contested()
                _json.dumps(st_.to_dict(), allow_nan=False)
            except BaseException as exc:                    # noqa: BLE001
                raised.append(f"{label}: {type(exc).__name__}: {exc}")
        # ...and the SAME blob a writer can produce without touching the
        # JSON: a tuple key round-tripped through json is a list key.
        writer = cross.CrossStore()
        tuple_key = writer.put("c", ("measure", "chest"), 108.0, "measured",
                               "tape")
        # ...and the well-formed part of a broken store still loads, so the
        # loader is not simply refusing everything.
        half = cross.CrossStore.from_dict_checked({"cores": {"c": [
            {"key": "good", "arm": "support+", "seq": 1, "values": [
                {"value": 108.0, "kind": "measured", "sources": ["tape"]}]},
            {"key": ["bad"], "arm": None, "seq": 2, "values": []}]},
            "edges": []})
        check("the loader never raises",
              not raised
              and len(verdicts) == 15
              and verdicts["a key that is a list"] == cross.MALFORMED_SEAT
              and verdicts["a seq that is a word"] == cross.MALFORMED_SEAT
              and verdicts["a core name that is a number"] \
              == cross.MALFORMED_CORE
              and verdicts["no store at all"] == cross.MALFORMED_STORE
              and verdicts["nothing"] == "ANSWER"
              and tuple_key["verdict"] == cross.UNIDENTIFIABLE_VALUE
              and half["verdict"] == cross.MALFORMED_SEAT
              and half["store"].resolve("c", "good")["value"] == 108.0
              and len(half["detail"]["problems"]) == 1,
              f'{len(verdicts)} malformed stores — a list key, a text seq, '
              f'a numeric core name, a store that is a string — come back as '
              f'verdicts and {len(raised)} of them raise; every store handed '
              f'back reads (seats, census, verify, to_dict, json.dumps); the '
              f'writer can no longer make the blob that killed it '
              f'({tuple_key["verdict"]} for a tuple key); and a store with '
              f'one bad seat still serves its good one '
              f'({half["store"].resolve("c", "good")["value"]}), naming what '
              f'it did not load'
              + (f' — RAISED {raised[:2]}' if raised else ''))


# ---------------------------------------------------------------------------
def parts_assemble_a_second_garment() -> None:
    """The assembler turns approved part choices into a sewable declaration.

    The library holds candidates as facets on the stereo cross. A variant
    that has no drafting procedure is declared but not draftable — picking
    it must refuse by name, never silently substitute.
    """
    from photoloset import assemble, block, garment_marks
    from photoloset import garment_pattern, garment_sew, garment_skirt
    from photoloset import Measures

    a = assemble.assemble({"nosuch": "x"})
    check("unknown slot refused", a["verdict"] == "UNKNOWN_NO_SUCH_SLOT",
          a["verdict"])
    a = assemble.assemble({"silhouette": "存在しない"})
    check("unknown variant refused",
          a["verdict"] == "UNKNOWN_NO_SUCH_VARIANT"
          and len(a.get("known", [])) == 2,
          f'known: {len(a.get("known", []))}')
    a = assemble.assemble({"closure": "後ろセンターファスナー"})
    check("undraftable variant refuses by name",
          a["verdict"] == "UNKNOWN_PART_NOT_DRAFTABLE"
          and a.get("alternatives"),
          f'{a.get("why", "")[:40]}… alt {a.get("alternatives")}')

    ms = Measures()
    for spot, value in [("waist", 64.0), ("hip", 90.0),
                        ("skirt_length", 58.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")
    a = assemble.assemble({"silhouette": "Aライン",
                           "closure": "ゴムウエスト（開き無し）",
                           "waist_finish": "シャーリング"})
    if a["verdict"] != "ANSWER":
        check("assembler builds the skirt declaration", False, a["verdict"])
        return
    decl = a["declaration"]
    st, root = block.ingest(decl=decl, formulas=decl["formulas"])
    cen = st.census()
    view = block.BlockView(st, root)
    check("assembled declaration lives on the cross",
          not cen["over_capacity"] and not cen["contested"]
          and tuple(view.required()) == ("waist", "hip", "skirt_length")
          and cen["cores"] == 5 and cen["facets"] == 26,
          f'{cen["cores"]} cores, {cen["facets"]} facets')

    d = garment_skirt.draft(ms, view)
    check("skirt drafts through the shared engine",
          d["verdict"] == "ANSWER"
          and [p["name"] for p in d["pieces"]] == ["前身頃", "後身頃"]
          and d.get("total_area_cm2") == 5652.2
          and len(d.get("formulas", {})) == 9,
          f'{d.get("total_area_cm2")} cm2, {len(d.get("formulas", {}))} '
          "formulas")

    m = garment_marks.apply(d)
    n_notches = sum(len(v) for v in m.get("notches", {}).values())
    # `all()` over a dict that can be empty, with the count in the DETAIL
    # instead of the condition: deleting the line that records an allowance
    # made `seam_allowance` come back {} for every piece and this line
    # stayed green. The count is asserted here now.
    sa = list(m.get("seam_allowance", {}).values())
    # The quantifier sits in the condition beside its own count: hoisting it
    # into a local one line above is exactly how the previous sweep missed
    # this clause — it read the expression PASSED to check() and saw a bare
    # name.
    check("skirt marks pair and face outward",
          n_notches == 4 and len(m["notch_pairs"]) == 2
          and not m["notch_unpaired"] and len(sa) == 2
          and all(v.get("verdict") == "ANSWER" for v in sa),
          f'{n_notches} notches, {len(m["notch_pairs"])} pairs, '
          f'{len(m["notch_unpaired"])} unpaired, {len(sa)} pieces offset')

    built = garment_sew.build(d, marks=m)
    mat = {"verdict": "ANSWER", "fabric": "twill", "gsm": 280.0,
           "thickness": 0.12, "stiffness": 12.0}
    gap = garment_sew.sew_and_drape(built, mat, iterations=2000,
                                    stitch_k=12.0 * 64)["seam_gap"]
    check("skirt sews shut hanging from the waist",
          built["pins_policy"] == "waist_extremes" and gap["closed"]
          and gap["over_tolerance"] == 0
          and round(gap["worst"], 4) == 0.0973,
          f'worst {gap["worst"]} cm, {gap["over_tolerance"]} over, '
          f'hung by {built["pins_policy"]}')


# ---------------------------------------------------------------------------
def prompts_switch_per_model_and_keep_discipline() -> None:
    """Prompts are per-model; the receiver, not the prompt, enforces discipline.

    A prompt asking nicely for no confidence numbers proves nothing on the
    day the model ignores it — so the parser refuses them by name.
    """
    import json as _json

    from photoloset import prompts

    qwen = prompts.for_model("lmstudio:qwen3.6:35b-a3b")
    sibling = prompts.for_model("lmstudio:some-future-model")
    stranger = prompts.for_model("openai:some-vision-model")
    check("per-model prompts with versions",
          qwen["matched"] == "profile" and stranger["matched"] == "default"
          and qwen["version"] and stranger["version"],
          f'qwen={qwen["version"]} (profile); a new lmstudio model '
          f'inherits it ({sibling["matched"]}); an unknown family '
          f'falls back to default ({stranger["version"]})')

    # The name quantifies over PROMPTS; the condition read one prompt —
    # qwen's — and the clause count sat in the detail. Measured: replacing
    # the DEFAULT profile's text with "Describe the garment as JSON." left
    # this green, and so did emptying DISCIPLINE to () (`not []` over an
    # empty tuple is vacuously true). Every registered profile plus the
    # fallback is checked here, and the number of clauses is pinned.
    # Every profile that INSTRUCTS a model (role "center"), plus the
    # fallback every unregistered model gets. A "parallel" profile carries a
    # query bank and no instruction text — it is listed here as having no
    # text rather than quietly skipped, because a silent skip is how the
    # single-prompt version of this check missed the default entirely.
    centers = sorted(mid for mid, v in prompts._PROMPTS.items()
                     if v.get("role") == "center")
    textless = sorted(mid for mid, v in prompts._PROMPTS.items()
                      if not v.get("text"))
    prompt_ids = centers + ["openai:unknown"]
    missing = [(mid, c[:12]) for mid in prompt_ids
               for c in prompts.DISCIPLINE
               if c[:12] not in (prompts.for_model(mid)["text"] or "")]
    check("discipline is inside every prompt",
          len(prompts.DISCIPLINE) == 4 and len(prompt_ids) >= 2
          # Pinned as a literal rather than quantified: today exactly one
          # registered profile carries no instruction text, and it is the
          # siglip query bank. Another one appearing has to be stated in a
          # diff instead of quietly dropping out of the sweep above.
          and textless == ["siglip:marqo-fashionSigLIP"]
          and not missing,
          f'{len(prompts.DISCIPLINE)} clauses embedded in each of '
          f'{len(prompt_ids)} instructing prompts ({", ".join(prompt_ids)}); '
          f'{len(textless)} profile(s) carry no text and all of those are '
          f'query banks (role "parallel")'
          + (f' — MISSING {missing[:3]}' if missing else ''))

    from photoloset import parts as _pv
    bank = prompts.siglip_queries()
    # The `all()` here iterates PART_VOCAB, so an empty vocabulary would
    # make it vacuously true — the same shape as the sixth tautology, only
    # over a module constant instead of a wire response. It cannot empty at
    # runtime, but "cannot happen today" is what the other five relied on,
    # so the length is pinned in the SAME condition rather than assumed.
    uncovered = [fam for fam in _pv.PART_VOCAB
                 if fam not in prompts.PART_QUERY_BANK]
    check("siglip bank covers the part vocabulary",
          len(_pv.PART_VOCAB) == 8
          and len(bank) >= len(prompts.PART_QUERY_BANK)
          and not uncovered,
          f"{len(bank)} queries across "
          f'{len(prompts.PART_QUERY_BANK)} families, covering all '
          f'{len(_pv.PART_VOCAB)} part families'
          + (f" — uncovered: {uncovered}" if uncovered else ""))

    good = prompts.parse_decomposition("lmstudio:qwen3.6:35b-a3b", _json.dumps({
        "kind_guess": None,
        "parts": [{"part": "cape", "variant_hint": "肩から裾へ",
                   "ports": ["neck", "shoulder_l", "shoulder_r"],
                   "evidence": "肩の白い布", "region": "上半分"}],
        "unknowns": [{"aspect": "背面の開き", "why": "背面が写っていない",
                      "candidate_hints": ["開き無し", "中央開き"]}],
        "queries": ["white cape dress"]}))
    check("valid decomposition accepted with provenance",
          good["verdict"] == "ANSWER"
          and "prompt=" in good["source"]
          and "white cape dress" in good["queries"],
          f'source: {good.get("source", "")[:48]}…')

    sneaky = _json.dumps({"parts": [{"part": "cape", "ports": ["neck"],
                                     "confidence": 0.93}]})
    check("confidence numbers refused",
          prompts.parse_decomposition("default", sneaky)["verdict"]
          == "UNKNOWN_FORBIDDEN_CONFIDENCE",
          "VM2 — the model's self-reported number never reaches a fact")

    check("unknown port refused",
          prompts.parse_decomposition(
              "default", _json.dumps({"parts": [
                  {"part": "sleeve", "ports": ["elbow_l"]}]})
          )["verdict"] == "UNKNOWN_UNKNOWN_PORT",
          "closed port vocabulary")

    check("unknown part family refused",
          prompts.parse_decomposition(
              "default", _json.dumps({"parts": [{"part": "mantle"}]})
          )["verdict"] == "UNKNOWN_UNKNOWN_PART",
          "new parts must arrive as new_part, not as a guess")

    check("malformed json refused",
          prompts.parse_decomposition("default", "すみません、")["verdict"]
          == "UNKNOWN_MALFORMED_PROPOSAL",
          "a refusal, not a crash")

    props = prompts.to_proposals(good)
    check("everything lands as proposals",
          props and all(p["source"].startswith("lmstudio:") for p in props)
          and len(props) == 2,
          f'{len(props)} proposals (1 part, 1 unknown), all PROPOSED')


# ---------------------------------------------------------------------------
def compose_builds_a_whole_garment_from_parts() -> None:
    """A garment is a parts graph. Type names are labels, not capability.

    The cape dress — unclassifiable as a "type" — must compose from
    bodice + high-low skirt + sleeve + cape, with every open port named
    and every connection's length difference printed.
    """
    import json as _json

    from photoloset import compose, garment_marks, garment_sew
    from photoloset import Measures

    ms = Measures()
    for spot, value in [("chest", 82.0), ("shoulder", 38.0), ("waist", 62.0),
                        ("bodice_length", 22.0), ("sleeve_length", 52.0),
                        ("hip", 88.0), ("skirt_length", 45.0),
                        ("neck", 21.0), ("cape_length", 28.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")

    a = compose.compose({"parts": [{"instance": "x:1", "part": "mantle"}]},
                        ms)
    check("unknown part refused",
          a["verdict"] == "UNKNOWN_NO_SUCH_PART"
          and len(a.get("known", [])) == 4,
          f'{a.get("which")} — known: {len(a.get("known", []))}')
    a = compose.compose({"parts": [{"instance": "bodice:1",
                                    "part": "bodice"}],
                         "connections": [{"a": ["bodice:1", "elbow_l"],
                                          "b": ["bodice:1", "waist"]}]}, ms)
    check("unknown port refused", a["verdict"] == "UNKNOWN_UNKNOWN_PORT",
          a.get("which", ""))

    dress = {
        "parts": [
            {"instance": "bodice:1", "part": "bodice"},
            {"instance": "skirt:1", "part": "skirt_panel",
             "params": {"hi_lo_drop": 22.0}},
            {"instance": "sleeve:1", "part": "sleeve",
             "params": {"side": "左"}},
            {"instance": "cape:1", "part": "cape"}],
        "connections": [
            {"a": ["bodice:1", "waist"], "b": ["skirt:1", "waist"]},
            {"a": ["bodice:1", "armhole_l"], "b": ["sleeve:1", "armhole_l"]},
            {"a": ["bodice:1", "neck"], "b": ["cape:1", "neck"]}],
        "port_finish": {
            "cape:1": {"hem": "free", "center_front": "fold",
                       "center_back": "fold"},
            "skirt:1": {"hem": "free", "center_front": "fold",
                        "center_back": "fold"},
            "bodice:1": {"center_front": "fold", "center_back": "fold"},
            "sleeve:1": {"cuff_l": "free"}},
        "label": "ケープワンピース",
    }
    naked = dict(dress)
    naked["port_finish"] = {}
    a = compose.compose(naked, ms)
    open_ports = sorted({(o["instance"], o["port"])
                         for o in a.get("open", [])})
    check("open ports are named, never filled",
          a["verdict"] == "UNKNOWN_OPEN_PORT" and len(open_ports) >= 6,
          f'{len(open_ports)} open, e.g. {open_ports[:3]}')

    r = compose.compose(dress, ms)
    # `not bad` over `r.get("seam_checks", [])` is true when the scan found
    # nothing AND when it covered nothing — a compose() that emits zero
    # seam checks would pass. The piece count in the condition pins a
    # different collection, so the seam checks are counted too.
    seam_checks = r.get("seam_checks", [])
    bad = [c for c in seam_checks if not c["sewable"]]
    check("cape dress composes from parts",
          r["verdict"] == "ANSWER" and len(r["pieces"]) == 6
          and len(seam_checks) == 10 and not bad
          and len(r["seam_specs"]) == 10,
          f'{len(r["pieces"])} pieces, {len(r["seam_specs"])} seams, '
          f'{len(seam_checks)} seam checks, {len(bad)} not sewable')
    check("the type name is only a label",
          r.get("label") == "ケープワンピース" and "ラベル" in
          r.get("kind_note", ""),
          "no registration happened — the label rides the combination")

    m = garment_marks.apply(r)
    # The name says EVERY PART and the condition named no part: `all()` over
    # a dict that can be empty, with the piece count in the detail. Both are
    # fixed — the parts are named here as literals and each one's allowance
    # has to answer.
    parts_offset = sorted(m.get("seam_allowance", {}))
    sa = [m["seam_allowance"][name] for name in parts_offset]
    check("allowances face outward on every part",
          len(sa) == 6
          and all(v.get("verdict") == "ANSWER" for v in sa)
          and parts_offset == sorted(p["name"] for p in r["pieces"]),
          f'{len(sa)} pieces offset: {parts_offset}')

    b = garment_sew.build(r, marks=m)
    mat = {"verdict": "ANSWER", "fabric": "wool melton", "gsm": 420.0,
           "thickness": 0.18, "stiffness": 20.0}
    gap = garment_sew.sew_and_drape(b, mat, iterations=6000,
                                    stitch_k=20.0 * 128)["seam_gap"]
    check("the composed dress sews shut",
          gap["closed"] and gap["over_tolerance"] == 0
          and round(gap["worst"], 4) == 0.0703 and gap["stitches"] == 45,
          f'worst {gap["worst"]} cm, {gap["over_tolerance"]} over, '
          f'{gap["stitches"]} stitches')


# ---------------------------------------------------------------------------
def zones_number_the_garment_for_adjustment() -> None:
    """Every design knob gets a stable number; measures never move.

    The agent loop says "give zone 1 more ease" — not "make it nicer".
    Numbers are deterministic per parts graph, and applying them records
    what changed instead of quietly mutating.
    """
    from photoloset import compose, garment_marks, garment_sew, zones
    from photoloset import Measures

    ms = Measures()
    for spot, value in [("chest", 82.0), ("shoulder", 38.0), ("waist", 62.0),
                        ("bodice_length", 22.0), ("sleeve_length", 52.0),
                        ("hip", 88.0), ("skirt_length", 45.0),
                        ("neck", 21.0), ("cape_length", 28.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")
    dress = {
        "parts": [
            {"instance": "bodice:1", "part": "bodice"},
            {"instance": "skirt:1", "part": "skirt_panel",
             "params": {"hi_lo_drop": 22.0}},
            {"instance": "sleeve:1", "part": "sleeve",
             "params": {"side": "左"}},
            {"instance": "cape:1", "part": "cape"}],
        "connections": [
            {"a": ["bodice:1", "waist"], "b": ["skirt:1", "waist"]},
            {"a": ["bodice:1", "armhole_l"],
             "b": ["sleeve:1", "armhole_l"]},
            {"a": ["bodice:1", "neck"], "b": ["cape:1", "neck"]}],
        "port_finish": {
            "cape:1": {"hem": "free", "center_front": "fold",
                       "center_back": "fold"},
            "skirt:1": {"hem": "free", "center_front": "fold",
                        "center_back": "fold"},
            "bodice:1": {"center_front": "fold", "center_back": "fold"},
            "sleeve:1": {"cuff_l": "free"}},
    }

    r1 = compose.compose(dress, ms)
    r2 = compose.compose(dress, ms)
    z1 = r1.get("zones", [])
    # **A number has to keep pointing at the same knob.** The module's own
    # claim is 番号は決定的 — that "zone 7" is not a different knob next time
    # round — and asserting the COUNT, the agreement of two calls in one
    # process and the ids 1..10 says nothing about what any number MEANS.
    # Two calls agreeing is one process agreeing with itself; the id list is
    # a range. So the map itself is pinned, address by address: the next
    # check adjusts zone 1 and zone 7 by number, and those two lines now
    # disagree if the numbering ever slides.
    knobs = [(z["id"], z["instance"], z["param"]) for z in z1]
    check("zones are numbered deterministically",
          len(z1) == 10 and z1 == r2.get("zones")
          and [z["id"] for z in z1] == list(range(1, 11))
          and knobs == [(1, "bodice:1", "chest_ease"),
                        (2, "bodice:1", "waist_ease"),
                        (3, "bodice:1", "armhole_depth_add"),
                        (4, "cape:1", "sector"),
                        (5, "skirt:1", "waist_ease"),
                        (6, "skirt:1", "hip_ease"),
                        (7, "skirt:1", "flare_ratio"),
                        (8, "skirt:1", "hi_lo_drop"),
                        (9, "sleeve:1", "ease_in"),
                        (10, "sleeve:1", "cuff_add")],
          f'{len(z1)} zones, and each number names one knob: '
          f'{knobs[0]} … {knobs[6]} … {knobs[-1]}')

    a = zones.apply(dress, {"1": 1.5, "7": 0.1})
    applied = a.get("applied", [])
    r3 = compose.compose(a["graph"], ms)
    area = round(sum(p["area_cm2"] for p in r3.get("pieces", [])), 1)
    # **The number in the name is a knob, not an index.** This line named
    # chest_ease in its detail and asserted only that SOMETHING was recorded
    # — so with the zone order reversed it stayed green while zone 1 became
    # a different parameter (nothing in the fixture carries an explicit
    # value, so `was == "既定"` holds for whichever knob zone 1 now is).
    check("applying a delta records what changed",
          a["verdict"] == "ANSWER" and len(applied) == 2
          and applied[0]["was"] == "既定" and applied[0]["now"] == 1.5
          and applied[0]["param"] == "chest_ease"
          and applied[0]["instance"] == "bodice:1"
          and applied[1]["param"] == "flare_ratio"
          and applied[1]["instance"] == "skirt:1"
          and applied[1]["delta"] == 0.1
          and r3["verdict"] == "ANSWER",
          f'zone1 {applied[0]["instance"]}/{applied[0]["param"]} '
          f'既定→{applied[0]["now"]}, zone7 '
          f'{applied[1]["instance"]}/{applied[1]["param"]} '
          f'+{applied[1]["delta"]} — area {area} cm2')

    check("measures never move",
          ms.state("chest")["state"] == "MEASURED"
          and ms.sheet()["measured"][0]["value"] == 82.0,
          "adjustment touches design params only")

    e = zones.apply(dress, {"99": 1.0})
    check("unknown zone refused",
          e["verdict"] == "UNKNOWN_NO_SUCH_ZONE" and e.get("valid"),
          f'valid: {e.get("valid")}')

    m = garment_marks.apply(r3)
    b = garment_sew.build(r3, marks=m)
    mat = {"verdict": "ANSWER", "fabric": "wool melton", "gsm": 420.0,
           "thickness": 0.18, "stiffness": 20.0}
    gap = garment_sew.sew_and_drape(b, mat, iterations=6000,
                                    stitch_k=20.0 * 128)["seam_gap"]
    check("the adjusted dress still sews shut",
          gap["closed"] and gap["over_tolerance"] == 0
          and round(gap["worst"], 4) == 0.0703,
          f'worst {gap["worst"]} cm after adjustment')

    from photoloset import garment_pattern
    # `draft(ms if False else Measures())` drafts NOTHING: the dead
    # conditional always takes the empty default, so `coat` was a refusal
    # dict, and "zones" not in a refusal is true whatever the drafting code
    # does. Measured: adding `"zones": [...]` to draft()'s ANSWER return —
    # exactly the regression this line is named for — left the whole suite
    # green; adding it to the REFUSAL return turned it red, which is where
    # the check was really looking. So the coat is drafted for real, and
    # the branch is pinned in the same condition.
    coat_ms = Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0)]:
        coat_ms.measured(spot, value, "cm", source="tape", by="ci")
    coat = garment_pattern.draft(coat_ms)
    check("the coat has no zones (untouched path)",
          coat["verdict"] == "ANSWER" and len(coat["pieces"]) == 3
          and "zones" not in coat
          and coat["total_area_cm2"] == 7306.1,
          f'legacy drafting keeps its byte-identical shape: '
          f'{coat["verdict"]}, {len(coat["pieces"])} pieces, '
          f'{coat["total_area_cm2"]} cm2, no zones key')


# ---------------------------------------------------------------------------
@declares("the dress has no notches yet, and marks says so honestly",
          "a dress piece keeps its number when a piece is inserted ahead of it",
          "a dart on the dress front closes at the address it sits",
          "the dress mannequin refuses the measure set the dress actually has",
          "the dress marker lays seven cut pieces onto real cloth",
          "the dress BOM answers fabric and refuses three lines it cannot know",
          "the dress reaches DXF directly, because save() cannot draft it")
def the_dress_walks_every_stage_past_composition() -> None:
    """**The second garment, past the point ``compose_builds_a_whole_garment_from_parts``
    already reaches.**

    That check (above) already proves compose -> marks -> ``garment_sew.build``
    -> ``sew_and_drape`` closes for the cape dress. This one walks the stages
    past it: stable numbering, a dart, the mannequin, the marker, the BOM,
    and the DXF export — each called directly on the SAME composed draft, no
    new geometry invented. Where a stage refuses, the refusal is pinned as
    the answer, not routed around.

    **``sewing_order.py`` is not in this walk.** It is not in this
    repository's git history — ``git log --all`` names no commit that adds
    it, and no check, falsifier, or import anywhere references it. It exists
    only as an untracked file sitting in the working copy this task started
    from. Read (not imported — this suite runs against the committed tree
    only) and hand-run against both garments: fed the coat's own
    ``garment_sew.build()`` output it reproduces its own docstring's worked
    example exactly (β = 5 − 3 + 1 = 3 — the coat has 3 seams that must be
    sewn in the round). Fed the composed dress's ``build()`` output it
    refuses ``UNKNOWN_SEAM_NAMES_NO_PIECES``, correctly — one internal seam
    label from ``garment_parts.draft_sleeve`` ("袖下線: 袖(左) の筒") has no
    "↔" separator, while every coat-side label does. That refusal is the
    honest edge of what exists; there is no committed module here to pin a
    check against, so none is added. (Forcing only that one label past the
    refusal, to see how deep the mismatch runs, shows the module's own
    parser is looser than its docstring claims: ``_sides()`` accepts ANY
    string containing "↔", not only the "裁片/辺 ↔ 裁片/辺" form it
    documents, so the other nine dress labels — none of which contain "/" —
    would each mint a bogus one-off "piece" name instead of the real ones
    and the module would answer ANSWER with a 15-node graph that does not
    describe this dress. That is a defect in the untracked file itself, not
    something this task's dress touches, and it is reported rather than
    fixed — the file is not part of this repository yet, and it is not
    this check's job to adopt someone else's in-flight module.)
    """
    import copy as _copy

    from photoloset import bom as _bom
    from photoloset import compose, darts as _dt, dxf as _dxf
    from photoloset import garment_marks, garment_sew
    from photoloset import mannequin as _mq, marker as _mkr, points as _pt
    from photoloset import Measures

    ms = Measures()
    for spot, value in [("chest", 82.0), ("shoulder", 38.0), ("waist", 62.0),
                        ("bodice_length", 22.0), ("sleeve_length", 52.0),
                        ("hip", 88.0), ("skirt_length", 45.0),
                        ("neck", 21.0), ("cape_length", 28.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")
    dress = {
        "parts": [
            {"instance": "bodice:1", "part": "bodice"},
            {"instance": "skirt:1", "part": "skirt_panel",
             "params": {"hi_lo_drop": 22.0}},
            {"instance": "sleeve:1", "part": "sleeve",
             "params": {"side": "左"}},
            {"instance": "cape:1", "part": "cape"}],
        "connections": [
            {"a": ["bodice:1", "waist"], "b": ["skirt:1", "waist"]},
            {"a": ["bodice:1", "armhole_l"],
             "b": ["sleeve:1", "armhole_l"]},
            {"a": ["bodice:1", "neck"], "b": ["cape:1", "neck"]}],
        "port_finish": {
            "cape:1": {"hem": "free", "center_front": "fold",
                       "center_back": "fold"},
            "skirt:1": {"hem": "free", "center_front": "fold",
                        "center_back": "fold"},
            "bodice:1": {"center_front": "fold", "center_back": "fold"},
            "sleeve:1": {"cuff_l": "free"}},
        "label": "ケープワンピース",
    }
    r = compose.compose(dress, ms)
    m = garment_marks.apply(r)

    with guard("the dress has no notches yet, and marks says so honestly"):
        # compose() ships `"notch_plan": []` — an EMPTY declared plan, not a
        # missing one. `apply()` reads that as "the declarative branch, zero
        # steps" rather than falling to the coat's hardcoded armhole-notch
        # heuristic (which only fires when notch_plan is None). So the dress
        # gets a real ANSWER with zero notches, which is the honest state of
        # an unwritten policy — not a crash and not the coat's notches
        # borrowed by accident.
        n_notch = sum(len(v) for v in m["notches"].values())
        sa = m["seam_allowance"]
        sa_ok = [name for name in sa if sa[name].get("verdict") == "ANSWER"]
        grain_pieces = {g["piece"] for g in m["grain"]}
        # The grain angle itself is not the dress's own
        # `settings.grain_angle_deg` (compose emits one, 90.0) — `apply()`
        # reads `_block.coat().setting("grain_angle_deg")`, the COAT's
        # singleton store, and only 90.0 == 90.0 by coincidence hides that a
        # second garment's marks stage is wired to the first garment's
        # settings, not its own.
        from photoloset import block as _block
        coat_angle = _block.coat().setting("grain_angle_deg")
        dress_angle = r["settings"]["grain_angle_deg"]
        check("the dress has no notches yet, and marks says so honestly",
              m.get("verdict", "ANSWER") == "ANSWER" and n_notch == 0
              and m["notch_pairs"] == [] and m["notch_unpaired"] == []
              and len(sa_ok) == 6 == len(sa)
              and grain_pieces == {p["name"] for p in r["pieces"]}
              and coat_angle == dress_angle == 90.0,
              f'0 notches across {len(sa)} pieces (notch_plan is an empty '
              f'declared list, not a missing one — the coat-only heuristic '
              f'never runs); {len(sa_ok)} seam allowances answer; grain '
              f'lines on all {len(grain_pieces)} pieces, drawn at '
              f'{coat_angle}° read off the COAT\'s store — equal to the '
              f'dress\'s own declared {dress_angle}° today by coincidence, '
              f'not because anything reads the dress\'s value')

    reg = _pt.Registry()
    _pt.label(r, reg)
    with guard("a dress piece keeps its number when a piece is inserted "
               "ahead of it"):
        watch = [("後身頃", "e0", 0.0), ("スカート前", "e2", 0.5),
                 ("ケープ", "e10", 0.3)]
        before = [_pt.number(reg, a, b, t) for a, b, t in watch]
        grown = _copy.deepcopy(r)
        grown["pieces"].insert(0, {"name": "割り込み", "area_cm2": 1.0,
                                   "outline": [[0.0, 0.0], [1.0, 0.0],
                                               [1.0, 1.0]]})
        probe = _pt.Registry(dict(reg._bases), dict(reg._shape))
        _pt.label(grown, probe)
        after = [_pt.number(probe, a, b, t) for a, b, t in watch]
        where = _pt.resolve(reg, before[0])
        check("a dress piece keeps its number when a piece is inserted "
              "ahead of it",
              before == [600, 1450, 3730] and after == before
              and where["piece"] == "後身頃" and where["edge"] == "e0"
              and where["number"] == 600,
              f'{watch} -> {before}, unchanged at {after} after a piece is '
              f'inserted at the front of a 6-piece dress (the coat\'s own '
              f'version of this check inserts at index 1; this one inserts '
              f'at index 0, the harder position)')

    with guard("a dart on the dress front closes at the address it sits"):
        # 前身頃/e3 is the side seam (脇線) — verified against the piece's
        # own named edge before picking it: outline[3]->outline[4] equals
        # 脇線's two points exactly. Not a bust dart (no `toward` aimed at an
        # anatomical point); a plain waist-shaping wedge on the side, same
        # perpendicular construction the coat's own dart check exercises.
        d = _dt.apply(r, [_dt.dart("前身頃", "e3", 0.5, 2.5, 8.0,
                                   role="waist")])
        one = d["darts"][0]
        n_dart = _pt.number(reg, one["piece"], one["edge"], one["t"])
        shrink = one["edge_cm_before"] - one["edge_cm_after_closing"]
        check("a dart on the dress front closes at the address it sits",
              d["count"] == 1 and d["refused"] == []
              and abs(shrink - 2.5) < 1e-9
              and round(one["edge_cm_before"], 4) == 7.6035
              and round(one["edge_cm_after_closing"], 4) == 5.1035
              and one["developable"] is False and one["trued"] is False
              and n_dart == 350,
              f'{one["edge_cm_before"]:.4f} -> '
              f'{one["edge_cm_after_closing"]:.4f} cm on 前身頃/脇線, '
              f'shrink {shrink:.4f} == intake 2.5; addressed at stable '
              f'number {n_dart}, developable={one["developable"]}')

    with guard("the dress mannequin refuses the measure set the dress "
               "actually has"):
        # Exactly the candidate refusal the brief named ahead of time:
        # mannequin.build() needs chest/waist/hip/body_length, and the dress
        # graph never declares body_length — it declares bodice_length and
        # skirt_length as two separate real measurements instead. This is
        # pinned as the honest result, not routed around by inventing a
        # body_length nobody measured.
        man = _mq.build(ms)
        # Same call through dxf.save(), which internally re-drafts from
        # `garment_pattern.draft(measures)` — the COAT's fixed shape, not
        # the composed dress. It refuses on the same missing spot, which is
        # reassuring (no silent wrong-garment export) but also proves
        # `save()` cannot be pointed at a composed garment at all — only
        # `dxf.to_dxf()` on an already-marked draft can, which the next
        # check below uses instead.
        import tempfile as _tempfile
        from pathlib import Path as _Path
        with _tempfile.TemporaryDirectory() as _tmp:
            saved = _dxf.save(ms, str(_Path(_tmp) / "dress.dxf"))
        check("the dress mannequin refuses the measure set the dress "
              "actually has",
              man["verdict"] == "UNKNOWN_MISSING_MEASUREMENTS"
              and man["missing"] == ["body_length"]
              and saved["verdict"] == "UNKNOWN_MISSING_MEASUREMENTS"
              and saved["missing"] == ["body_length"],
              f'mannequin.build(dress measures) -> {man["verdict"]} naming '
              f'{man["missing"]} (the dress has bodice_length + '
              f'skirt_length, never body_length); dxf.save() over the same '
              f'measures refuses identically rather than silently drafting '
              f'the coat\'s own 3-piece shape from the dress\'s numbers')

    CUT = {"前身頃": 1, "後身頃": 1, "スカート前": 1, "スカート後": 1,
           "袖(左)": 2, "ケープ": 1}
    with guard("the dress marker lays seven cut pieces onto real cloth"):
        no_count = _mkr.lay(r, 150.0, {}, 1.5)
        good = _mkr.lay(r, 150.0, CUT, 1.5)
        check("the dress marker lays seven cut pieces onto real cloth",
              no_count["verdict"] == _mkr.NO_COUNT
              and sorted(no_count["pieces"]) == sorted(p["name"]
                                                        for p in r["pieces"])
              and good["verdict"] == "ANSWER"
              and good["pieces_laid"] == 7 == sum(CUT.values())
              and round(good["length_cm"], 1) == 130.2
              and round(good["utilisation_pct"], 2) == 62.26,
              f'no counts -> {no_count["verdict"]} naming all '
              f'{len(no_count["pieces"])} pieces; 7 copies (袖(左) cut '
              f'twice, mirrored, the rest cut on the fold declared in '
              f'port_finish) need {good["length_cm"]} cm at '
              f'{good["utilisation_pct"]}% utilisation')

    with guard("the dress BOM answers fabric and refuses three lines it "
               "cannot know"):
        bm = _bom.estimate(r, 150.0, CUT, 1.5)
        refused = sorted(bm["refused"])
        check("the dress BOM answers fabric and refuses three lines it "
              "cannot know",
              bm["verdict"] == "ANSWER"
              and bm["known"]["fabric"]["quantity"] == 1.302
              and bm["known"]["fabric"]["unit"] == "m"
              and refused == ["interfacing", "notions", "thread"]
              and not bm["completeness"]["complete"]
              and bm["completeness"]["known_lines"] == ["fabric"],
              f'fabric {bm["known"]["fabric"]["quantity"]} m from the '
              f'marker (not recomputed); refused: {refused}; '
              f'complete={bm["completeness"]["complete"]}')

    with guard("the dress reaches DXF directly, because save() cannot "
               "draft it"):
        out = _dxf.to_dxf(m)
        names = sorted(p["piece"] for p in out["pieces"])
        expected_names = sorted(p["name"] for p in r["pieces"])
        check("the dress reaches DXF directly, because save() cannot "
              "draft it",
              out["verdict"] == "ANSWER" and len(out["pieces"]) == 6
              and names == expected_names
              and out["cut_line_missing"] == []
              and sum(out["notch_lines"].values()) == 0
              and out["extents_cm"]["min"] == [10.0, -37.1]
              and out["extents_cm"]["max"] == [263.685, 69.682],
              f'{len(out["pieces"])} pieces {names} written straight from '
              f'garment_marks.apply() output (to_dxf(), not save() — '
              f'save() re-drafts from garment_pattern.draft internally and '
              f'cannot see a composed garment at all); extents '
              f'{out["extents_cm"]["min"]} .. {out["extents_cm"]["max"]} cm, '
              f'0 notch lines matching the 0 notches marks produced')


# ---------------------------------------------------------------------------
def served_readers_track_their_stores() -> None:
    """**A reader has to answer from its store, and a literal cannot say so.**

    Seven readers here were pinned only against the literal they return for
    the coat — ``sleeve_required``, ``arm_census``, ``seam_edges``,
    ``settings``, ``dump``, ``unbought_generics`` and the library's
    ``census``. Measured, not argued: each was replaced by ``return <that
    literal>``, the whole suite was re-run, and every check stayed green
    (``tests/t7_readers.json`` records the runs). A comparison against a
    constant is satisfied by a reader frozen to that constant; only a SECOND
    store, whose answer is a different constant, can tell the two apart.

    So each line below reads one reader from two stores in one condition,
    and pins both answers. Freezing the reader breaks one of them.
    """
    import copy as _copy
    from photoloset import block as blk, cross, parts

    with guard('reads follow a second declaration'):
        b = blk.coat()
        other = _copy.deepcopy(blk.COAT_DECLARATION)
        other["label"] = "袖まで必須のコート"
        other["required"] = tuple(list(other["required"]) + ["sleeve_length"])
        other["sleeve_required"] = ()
        other["settings"] = dict(other["settings"])
        other["settings"]["grain_angle_deg"] = (45.0, "斜め地。試しの宣言")
        other["seams"] = other["seams"][:2]
        st2, root2 = blk.ingest(decl=other)
        v2 = blk.BlockView(st2, root2)
        check("reads follow a second declaration",
              b.sleeve_required() == ("sleeve_length",)
              and v2.sleeve_required() == ()
              and v2.required() == ("body_length", "chest", "shoulder",
                                    "sleeve_length")
              and b.settings()["grain_angle_deg"] == 90.0
              and v2.settings()["grain_angle_deg"] == 45.0
              and len(b.seam_edges()) == 4 and len(v2.seam_edges()) == 2
              and len(b.seams()) == 5 and len(v2.seams()) == 2,
              f'the same four readers, two declarations: sleeve_required '
              f'{b.sleeve_required()} vs {v2.sleeve_required()}, grain '
              f'{b.settings()["grain_angle_deg"]} vs '
              f'{v2.settings()["grain_angle_deg"]}, seam edges '
              f'{len(b.seam_edges())} vs {len(v2.seam_edges())}, seams '
              f'{len(b.seams())} vs {len(v2.seams())}')

    with guard('the arm census counts the store it is given'):
        b = blk.coat()
        thin = _copy.deepcopy(blk.COAT_DECLARATION)
        thin["required"] = tuple(list(thin["required"]) + ["sleeve_length"])
        thin["sleeve_required"] = ()
        thin["seams"] = thin["seams"][:2]
        st3, root3 = blk.ingest(decl=thin)
        v3 = blk.BlockView(st3, root3)
        check("the arm census counts the store it is given",
              b.arm_census()["cause+"] == 10 and b.arm_census()["kind-"] == 17
              and v3.arm_census()["cause+"] == 4
              and v3.arm_census()["kind-"] == 14
              and sorted(v3.arm_census()) == sorted(cross.ARMS),
              f'cause+ {b.arm_census()["cause+"]} vs '
              f'{v3.arm_census()["cause+"]}, kind- '
              f'{b.arm_census()["kind-"]} vs {v3.arm_census()["kind-"]} — '
              f'the same reader over two stores')

    with guard('dump carries the store it read'):
        b = blk.coat()
        relabelled = _copy.deepcopy(blk.COAT_DECLARATION)
        relabelled["label"] = "写しのコート（別の名乗り）"
        st4, root4 = blk.ingest(decl=relabelled)
        v4 = blk.BlockView(st4, root4)
        check("dump carries the store it read",
              "写しのコート（別の名乗り）" in v4.dump()
              and "写しのコート（別の名乗り）" not in b.dump()
              and "三枚コート（前身頃・後身頃・袖）" in b.dump()
              and len(b.dump()) > 2000 and len(v4.dump()) > 1500,
              f'two stores under one root name, two dumps: the label rides '
              f'in the dump ({len(b.dump())} and {len(v4.dump())} bytes)')

    with guard('unbought generics come from the store'):
        b = blk.coat()
        st5, root5 = blk.ingest()
        st5.put(root5, "param:試しの一般論", 1.0, "generic", "一冊の本")
        v5 = blk.BlockView(st5, root5)
        lone = [u["key"] for u in v5.unbought_generics()]
        check("unbought generics come from the store",
              b.unbought_generics() == []
              and lone == ["param:試しの一般論"]
              and cross.GENERIC_MIN_SOURCES == 2,
              f'the coat owes nothing ({len(b.unbought_generics())}); a lone '
              f'`generic` claim on a second store is owed by name: {lone}')

    with guard('the library census counts its own store'):
        lib = parts.Library()
        lib2 = parts.Library()
        lib2.store.put("parts:試しの家族", "family", {"name": "試しの家族"},
                       "generic", "文化ファッション大系")
        check("the library census counts its own store",
              lib.census()["cores"] == 4 and lib.census()["seats"] == 9
              and lib2.census()["cores"] == 5 and lib2.census()["seats"] == 10
              and len(lib.unbought_generics()) == 3
              and len(lib2.unbought_generics()) == 4,
              f'{lib.census()["cores"]} cores / {lib.census()["seats"]} seats '
              f'against {lib2.census()["cores"]} / {lib2.census()["seats"]} '
              f'once one family is added; unbought '
              f'{len(lib.unbought_generics())} against '
              f'{len(lib2.unbought_generics())}')


# ---------------------------------------------------------------------------
# The look loop: resemble -> construct -> confirm -> approve -> search
#
# The ORDER is the property. Approval comes BEFORE the sewing-method search,
# because a method retrieved for the wrong garment is a plausible wrong answer
# and plausible wrong answers reach cutting tables.
# ---------------------------------------------------------------------------

#: The four parts of the unclassifiable garment, as a centre model would name
#: them. Instance names are the model's; ``compose.graph_from`` assigns its own
#: deterministic ones and returns the map.
LOOK_PARTS = [{"instance": "bodice:1", "part": "bodice"},
              {"instance": "cape:1", "part": "cape"},
              {"instance": "skirt_panel:1", "part": "skirt_panel"},
              {"instance": "sleeve:1", "part": "sleeve"}]

#: What the FIXTURE backend answers. It measured nothing; every hit it returns
#: is marked ``fixture`` and every source string it stamps begins ``fixture:``.
LOOK_TABLE = {
    "bodice:1": [{"aspect": "family", "family": "bodice",
                  "corpus": "corpusA", "ref": "A", "region": "upper third"}],
    "cape:1": [{"aspect": "family", "family": "cape",
                "corpus": "corpusA", "ref": "A", "region": "shoulders"}],
    "skirt_panel:1": [{"aspect": "family", "family": "skirt_panel",
                       "corpus": "corpusA", "ref": "B", "region": "lower"},
                      {"aspect": "variant", "variant": "high-low",
                       "corpus": "corpusA", "region": "hem"}],
    "sleeve:1": [{"aspect": "family", "family": "sleeve",
                  "corpus": "corpusA", "ref": "A", "region": "left arm"}],
}

LOOK_CONNECTIONS = [
    {"a": ["bodice:1", "waist"], "b": ["skirt_panel:1", "waist"]},
    {"a": ["bodice:1", "armhole_l"], "b": ["sleeve:1", "armhole_l"]},
    {"a": ["bodice:1", "neck"], "b": ["cape:1", "neck"]}]

LOOK_PORT_FINISH = {
    "cape:1": {"hem": "free", "center_front": "fold", "center_back": "fold"},
    "skirt_panel:1": {"center_front": "fold", "center_back": "fold"},
    "bodice:1": {"center_front": "fold", "center_back": "fold"},
    "sleeve:1": {"cuff_l": "free"}}


def _look_measures():
    from photoloset import Measures
    ms = Measures()
    for spot, value in [("chest", 82.0), ("shoulder", 38.0), ("waist", 62.0),
                        ("bodice_length", 22.0), ("sleeve_length", 52.0),
                        ("hip", 88.0), ("skirt_length", 45.0),
                        ("neck", 21.0), ("cape_length", 28.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")
    return ms


def _look_structure(result, image_id="img1"):
    """The retrieved structure, with the connections and finishes a human
    would have answered on the previous round's sheet."""
    from photoloset import resemble
    s = resemble.structure_from(result, image_id=image_id)
    s["connections"] = [dict(c) for c in LOOK_CONNECTIONS]
    s["port_finish"] = {k: dict(v) for k, v in LOOK_PORT_FINISH.items()}
    s["label"] = "ケープワンピース"
    return s


def _look_retrieval(table=None, image_id="img1"):
    """Run the fixture backend over the four parts and return its answer."""
    from photoloset import resemble
    resemble.reset()
    resemble.install_fixture(LOOK_TABLE if table is None else table)
    return resemble.per_part("look.jpg", LOOK_PARTS, image_id=image_id)


def _look_store():
    from photoloset import cross
    st = cross.CrossStore()
    st.put("garment", "subject", {"name": "the look"}, "declared", "ci")
    return st


def _look_draft():
    """retrieval -> structure -> graph -> composed draft. The whole front half
    of the loop, as the checks below all need it."""
    from photoloset import compose
    res = _look_retrieval()
    g = compose.graph_from(_look_structure(res))
    ms = _look_measures()
    return res, g, compose.compose(g["graph"], ms), ms


# ---------------------------------------------------------------------------
@declares("retrieval without a backend refuses by name",
          "an empty result is not a refusal",
          "a whole-image backend cannot answer a per-part question",
          "photoloset registers no backend at import",
          "a fixture cannot pass as a backend",
          "a retrieval hit is unreadable at the part address",
          "two sources that disagree become contested, not ranked",
          "one corpus cannot buy a generic construction claim",
          "a search that found nothing is not seated")
def retrieval_asks_per_part() -> None:
    """Retrieval is PER PART, and it lands where nobody can read it yet.

    A global embedding answers one question — which image is most similar —
    and an unclassifiable garment is compositional, so the per-part question
    needs segmentation before embedding and says so by name when it has none.
    What comes back lands as ``proposed`` in the store's quarantine: a cosine
    score must not buy the seat a tape measure buys.
    """
    from photoloset import cross, garment_rights, resemble

    resemble.reset()
    with guard("retrieval without a backend refuses by name"):
        a = resemble.per_part("look.jpg", LOOK_PARTS, image_id="img1")
        b = resemble.whole("look.jpg", image_id="img1")
        check("retrieval without a backend refuses by name",
              a["verdict"] == "UNKNOWN_NO_RETRIEVAL_BACKEND"
              and b["verdict"] == "UNKNOWN_NO_RETRIEVAL_BACKEND"
              and "hits" not in a and "hits" not in b
              and "resemble.register" in a["how_to_close"]
              and resemble.backends() == [],
              f'per_part {a["verdict"]} / whole {b["verdict"]}, neither '
              f'carrying a hits list — an empty list would say "nothing is '
              f'similar" and the true sentence is "nothing was asked"')

    with guard("an empty result is not a refusal"):
        resemble.reset()
        resemble.install_fixture({})              # ran, found nothing
        r = resemble.per_part("look.jpg", LOOK_PARTS, image_id="img1")
        check("an empty result is not a refusal",
              r["verdict"] == "ANSWER" and r["hits"] == []
              and sorted(r["searched"]["instances"])
              == sorted(p["instance"] for p in LOOK_PARTS)
              and r["searched"]["backends"] == ["fixture:table"]
              and len(r["searched"]["instances"]) == 4,
              f'{r["verdict"]} with {len(r["hits"])} hits and the scope of '
              f'the search attached: {len(r["searched"]["instances"])} '
              f'instances against {r["searched"]["backends"]}')

    with guard("a whole-image backend cannot answer a per-part question"):
        resemble.reset()
        resemble.register("siglip:marqo-fashionSigLIP", "parallel",
                          "image_embedding",
                          lambda q: {"hits": [{"aspect": "resembles",
                                               "ref": "A",
                                               "corpus": "corpusA"}]})
        w = resemble.whole("look.jpg", image_id="img1")
        p = resemble.per_part("look.jpg", LOOK_PARTS, image_id="img1")
        check("a whole-image backend cannot answer a per-part question",
              p["verdict"] == "UNKNOWN_WHOLE_IMAGE_ONLY"
              and p["missing_stage"] == "UNKNOWN_NO_SEGMENTER"
              and "segmenter" in p["how_to_close"]
              and "resemble.whole()" in p["how_to_close"]
              and w["verdict"] == "ANSWER" and len(w["hits"]) == 1,
              f'the whole-garment question answers ({w["verdict"]}, '
              f'{len(w["hits"])} hit) and the per-part one refuses '
              f'{p["verdict"]}, naming the missing stage '
              f'{p["missing_stage"]} — one global vector cannot say the cape '
              f'resembles A while the skirt resembles B')

    with guard("photoloset registers no backend at import"):
        probe = subprocess.run(
            [sys.executable, "-c",
             "import json, photoloset.resemble as r, "
             "photoloset.sewing_search as s; "
             "print(json.dumps({'backends': r.backends(), "
             "'segmenters': r.segmenters(), 'corpora': s.corpora()}))"],
            cwd=ROOT, capture_output=True, text=True, timeout=300)
        try:
            fresh = json.loads(probe.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            fresh = {"backends": ["<unreadable>"], "segmenters": [],
                     "corpora": []}
        check("photoloset registers no backend at import",
              probe.returncode == 0 and fresh["backends"] == []
              and fresh["segmenters"] == [] and fresh["corpora"] == [],
              f'a fresh interpreter imports resemble and sewing_search and '
              f'finds {len(fresh["backends"])} backends, '
              f'{len(fresh["segmenters"])} segmenters and '
              f'{len(fresh["corpora"])} corpora — the "ships no model" claim '
              f'measured rather than asserted'
              + ("" if probe.returncode == 0
                 else f' — {probe.stderr[-200:]}'))

    with guard("a fixture cannot pass as a backend"):
        resemble.reset()
        wrong_name = resemble.register("siglip:real", "parallel",
                                       "region_embedding",
                                       lambda q: {"hits": []}, fixture=True)
        wrong_flag = resemble.register("fixture:table", "parallel",
                                       "region_embedding",
                                       lambda q: {"hits": []})
        after_refusals = resemble.backends()
        got = _look_retrieval()
        marks = {b["model_id"]: b["fixture"] for b in resemble.backends()}
        fixture_hits = [h for h in got["hits"] if h.get("fixture")]
        check("a fixture cannot pass as a backend",
              wrong_name["verdict"] == "UNKNOWN_FIXTURE_NOT_DECLARED"
              and wrong_flag["verdict"] == "UNKNOWN_FIXTURE_NOT_DECLARED"
              and after_refusals == []
              and marks == {"fixture:table": True}
              and len(fixture_hits) == 5 and len(got["hits"]) == 5,
              f'a fixture under a real name and a real name under the fixture '
              f'flag are both {wrong_name["verdict"]}, so nothing registered '
              f'({len(after_refusals)} backends); the fixture that does '
              f'register is marked in its id, its registration and all '
              f'{len(fixture_hits)} of its {len(got["hits"])} hits')

    with guard("a retrieval hit is unreadable at the part address"):
        st = _look_store()
        rights = garment_rights.RightsLedger()
        got = _look_retrieval()
        land = resemble.land(st, rights, got, image_id="img1")
        at_part = st.resolve("look:img1:cape:1", "family")
        in_quarantine = st.resolve("look:img1:cape:1#proposed", "family")
        kinds = sorted({l["kind"] for l in land["landed"]})
        armless = [l for l in land["landed"] if l["arm"] is None]
        check("a retrieval hit is unreadable at the part address",
              at_part["verdict"] == cross.NOT_IN_CROSS
              and in_quarantine["verdict"] == "ANSWER"
              and kinds == ["proposed"]
              and len(land["landed"]) == 5 and len(armless) == 5,
              f'{len(land["landed"])} hits landed {kinds}, all '
              f'{len(armless)} carrying no arm; resolve() at the part\'s own '
              f'address answers {at_part["verdict"]} while the quarantine '
              f'core answers {in_quarantine["verdict"]} — a cosine score does '
              f'not buy the seat a tape measure buys')

    with guard("two sources that disagree become contested, not ranked"):
        resemble.reset()
        resemble.install_fixture(LOOK_TABLE)
        resemble.install_fixture(
            {"skirt_panel:1": [{"aspect": "variant", "variant": "tiered",
                                "corpus": "corpusC", "region": "hem"}]},
            model_id="fixture:rival", segmenter=False)
        both = resemble.per_part("look.jpg", LOOK_PARTS, image_id="img1")
        st2 = _look_store()
        land2 = resemble.land(st2, garment_rights.RightsLedger(), both,
                              image_id="img1")
        split = st2.resolve("look:img1:skirt_panel:1#proposed", "variant")
        keys = sorted({l["key"] for l in land2["landed"]})
        sides = sorted(s["value"].get("variant") for s in
                       split.get("sides", []))
        check("two sources that disagree become contested, not ranked",
              split["verdict"] == cross.CONTESTED_IN_CROSS
              and sides == ["high-low", "tiered"]
              and keys == ["family", "variant"]
              and len(land2["contested"]) == 1
              and "value" not in split,
              f'two backends claiming the variant write to ONE address '
              f'({keys}) and collide: {split["verdict"]} carrying {sides} '
              f'with neither chosen. Put the source in the key and they '
              f'become two addresses, both ANSWER, and somebody downstream '
              f'sorts them by score')

    with guard("one corpus cannot buy a generic construction claim"):
        one = garment_rights.RightsLedger()
        resemble.land(_look_store(), one, _look_retrieval(), image_id="img1")
        s1 = one.state("cape", "family")
        two = garment_rights.RightsLedger()
        resemble.land(_look_store(), two, _look_retrieval(), image_id="img1")
        resemble.land(_look_store(), two, _look_retrieval(
            {"cape:1": [{"aspect": "family", "family": "cape",
                         "corpus": "corpusD", "ref": "A"}]}),
            image_id="img1")
        s2 = two.state("cape", "family")
        check("one corpus cannot buy a generic construction claim",
              s1["state"] == garment_rights.UNCHECKED
              and s1["generic_sources"] == ["corpusA"]
              and "2" in s1["how_to_close"]
              and s2["state"] == garment_rights.GENERIC
              and s2["generic_sources"] == ["corpusA", "corpusD"],
              f'one corpus leaves the construction claim {s1["state"]} with '
              f'{s1["generic_sources"]}; a second, independently named one '
              f'makes it {s2["state"]} with {s2["generic_sources"]}. A '
              f'construction found in one corpus is "traceable to a source", '
              f'not "general knowledge"')

    with guard("a search that found nothing is not seated"):
        nothing = _look_retrieval({})
        st3 = _look_store()
        rights3 = garment_rights.RightsLedger()
        land3 = resemble.land(st3, rights3, nothing, image_id="img1")
        cores = sorted(st3.to_dict()["cores"])
        verdicts = sorted({n["verdict"] for n in land3["not_seated"]})
        seen = rights3.state("cape", "resembles")
        # **The whole core list, not the absence of one prefix.** "No core
        # under look:" is true when the scan found nothing and when it
        # covered nothing; the store's entire contents are named here
        # instead, so a store that lost its subject core is a failure too.
        check("a search that found nothing is not seated",
              land3["landed"] == [] and cores == ["garment"]
              and verdicts == [cross.NOT_A_CLAIM]
              and len(land3["not_seated"]) == 4
              and seen["state"] == garment_rights.NO_MATCH
              and len(seen["searched_scopes"]) == 1
              and "fixture:table" in seen["searched_scopes"][0],
              f'the backend ran and found nothing: the store still holds '
              f'{cores} and nothing under look:, '
              f'{len(land3["not_seated"])} offers to it all '
              f'refused {verdicts}, and the record of HAVING SEARCHED on the '
              f'rights ledger as {seen["state"]} with its scope '
              f'{seen["searched_scopes"]}. "Searched nothing" cannot be '
              f'written down as "found nothing"')
    resemble.reset()


# ---------------------------------------------------------------------------
@declares("a retrieved family with no procedure refuses the whole construction",
          "the constructed graph names every part the retrieval named",
          "instance numbering does not move between rounds",
          "the confirmation solid is built from the composed pieces",
          "the sheet states what the render does not claim",
          "a rejection must name a claim",
          "an open port becomes a claim, not a silent default")
def the_look_becomes_a_shape() -> None:
    """The retrieval is CONSTRUCTED and dropped to 3D, so a human can check it.

    "cosine 0.83 to garment A" cannot be checked by a person; "here is the
    garment that similarity implies" can be checked in two seconds. The solid
    is therefore the falsifier for the retrieval, and it is built from the
    composed draft's own edges — never from a body ratio.
    """
    import copy as _copy

    from photoloset import compose, confirm, convergence

    res, g, draft, ms = _look_draft()
    good = _look_structure(res)

    with guard("a retrieved family with no procedure refuses the whole "
               "construction"):
        mixed = dict(good)
        mixed["instances"] = list(good["instances"]) + [
            {"instance": "collar:1", "part": "collar", "params": {}},
            {"instance": "mantle:1", "part": "mantle", "params": {}}]
        m = compose.graph_from(mixed)
        check("a retrieved family with no procedure refuses the whole "
              "construction",
              m["verdict"] == compose.NO_PART
              and m["undraftable"] == ["collar"]
              and m["unknown"] == ["mantle"]
              and "graph" not in m
              and "PART_GEOMETRY" in m["how_to_close"]
              and m["known"] == ["bodice", "cape", "skirt_panel", "sleeve"],
              f'{m["verdict"]} naming every offender — {m["unknown"]} outside '
              f'the vocabulary and {m["undraftable"]} inside it with no '
              f'procedure — and no graph at all. A garment silently missing '
              f'its cape collects approval for the wrong garment')

    with guard("the constructed graph names every part the retrieval named"):
        mixed = dict(good)
        mixed["instances"] = list(good["instances"]) + [
            {"instance": "collar:1", "part": "collar", "params": {}}]
        m = compose.graph_from(mixed)
        check("the constructed graph names every part the retrieval named",
              g["verdict"] == "ANSWER"
              and sorted(i["part"] for i in g["graph"]["parts"])
              == sorted(i["part"] for i in good["instances"])
              and len(g["graph"]["parts"]) == 4
              and m.get("graph") is None
              and m["asked_for"] == ["bodice", "cape", "collar",
                                     "skirt_panel", "sleeve"]
              and draft["verdict"] == "ANSWER",
              f'{len(g["graph"]["parts"])} parts in, '
              f'{len(g["graph"]["parts"])} out, and the composition answers '
              f'{draft["verdict"]}; add one undraftable part and there is no '
              f'graph at all rather than a graph of {len(m["asked_for"]) - 1}')

    with guard("instance numbering does not move between rounds"):
        shuffled = dict(good)
        shuffled["instances"] = list(reversed(good["instances"]))
        g2 = compose.graph_from(shuffled)
        check("instance numbering does not move between rounds",
              g2["named"] == g["named"]
              and g2["renamed"] == g["renamed"]
              and g["named"] == ["bodice:1", "skirt_panel:1", "cape:1",
                                 "sleeve:1"]
              and len(g["named"]) == 4,
              f'the same four parts in the opposite order get the same four '
              f'names {g2["named"]} — the numbering is (vocabulary order, '
              f'content), so "zone 3" does not point somewhere else next '
              f'round')

    with guard("the confirmation solid is built from the composed pieces"):
        solid = confirm.solid_from_draft(draft)
        moved = _copy.deepcopy(draft)
        touched = ""
        for p in moved["pieces"]:
            if "裾" in p["edges"]:
                p["edges"]["裾"]["length"] += 5.0
                touched = p["name"]
                break
        after = confirm.solid_from_draft(moved)
        sources = sorted({f.split("/")[0] for r in solid["rings"]
                          for f in r["from"]})
        check("the confirmation solid is built from the composed pieces",
              solid["verdict"] == "ANSWER"
              and after["vertices"] != solid["vertices"]
              and len(solid["rings"]) == 8
              and solid["skipped"] == []
              and sources == sorted(p["name"] for p in draft["pieces"])
              and len(sources) == 6,
              f'{len(solid["rings"])} rings read off {len(sources)} composed '
              f'pieces; lengthening {touched}\'s hem edge by 5 cm moves the '
              f'vertices ({after["vertices"] != solid["vertices"]}). A girth '
              f'taken from a body ratio would not have moved')

    with guard("the sheet states what the render does not claim"):
        solid = confirm.solid_from_draft(draft)
        sheet = confirm.sheet(draft, solid, image_ref="look.jpg", graph=g["graph"])
        says = sheet["does_not_claim"]
        check("the sheet states what the render does not claim",
              solid["not_a_simulation"] in says
              and solid["surface_carries_no_information"] in says
              and draft["seam_allowance"] in says
              and draft["not_a_published_system"] in says
              and len(says) == 5
              and str(confirm.ASSUMED_DEPTH_RATIO) in says[-1]
              and "not a fit simulation" in solid["not_a_simulation"],
              f'{len(says)} sentences, quoted from the objects themselves: '
              f'the solid\'s "not a fit simulation" and its facet count, the '
              f'draft\'s seam allowance and its "not a published system", and '
              f'the assumed depth ratio {confirm.ASSUMED_DEPTH_RATIO}. The '
              f'user is being asked to judge SHAPE, not fit')

    with guard("a rejection must name a claim"):
        from photoloset import garment_rights as _gr
        from photoloset import resemble as _resemble
        res2 = _look_retrieval()
        land = _resemble.land(_look_store(), _gr.RightsLedger(), res2,
                              image_id="img1")
        sheet = confirm.sheet(draft, image_ref="look.jpg", retrieval=land,
                              graph=g["graph"])
        unnamed = confirm.reject(sheet, [], "Kodai Motonishi")
        ghost = confirm.reject(sheet, ["c99"], "Kodai Motonishi")
        anon = confirm.reject(sheet, ["c1"], "")
        named = confirm.reject(sheet, ["c1"], "Kodai Motonishi",
                               note="the mesh looks bad")
        check("a rejection must name a claim",
              unnamed["verdict"] == confirm.UNNAMED_REJECTION
              and ghost["verdict"] == confirm.NO_CLAIM
              and ghost["which"] == ["c99"]
              and anon["verdict"] == confirm.NO_REJECTER
              and named["verdict"] == "ANSWER"
              and len(named["rejected"]) == 1
              and named["rejected"][0]["note"] == "the mesh looks bad"
              and named["rejected"][0]["source"] == sheet["claims"][0]["source"],
              f'an empty rejection is {unnamed["verdict"]} and an unknown '
              f'claim is {ghost["verdict"]}; free text rides BESIDE a named '
              f'claim as a note and is not itself a rejection of anything, so '
              f'a correct retrieval cannot be killed by an ugly render')

    with guard("an open port becomes a claim, not a silent default"):
        naked = dict(g["graph"])
        naked["port_finish"] = {}
        refused = compose.compose(naked, ms)
        sheet = confirm.sheet(refused, image_ref="look.jpg", graph=naked)
        ports = [c for c in sheet["claims"] if c["kind"] == "open_port"]
        answers = sorted({c["answer"] for c in ports})
        # ...and the sheet says whether the LOOP is ending, which is
        # convergence.py's first caller in the tree.
        ending = sheet.get("convergence") or {}
        check("an open port becomes a claim, not a silent default",
              refused["verdict"] == compose.OPEN_PORT
              and len(ports) == 8
              and answers == ["cannot_tell"]
              and sheet["solid"]["verdict"] == confirm.NO_SOLID
              and all(c["aspect"].startswith("port:") for c in ports)
              and len(ports) == 8
              and sheet["shape"]["verdict"] == confirm.NOT_COMPOSED
              and ending.get("verdict") == convergence.IN_PROGRESS
              and ending.get("counters", {}).get("open_ports") == 8,
              f'{len(ports)} ports neither connected nor finished become '
              f'{len(ports)} claims answered {answers} — on a single '
              f'front-facing photograph "the back is not visible" is the '
              f'EXPECTED first state, and it is put to the human rather than '
              f'filled in with a finish nobody chose. The sheet reports the '
              f'loop as {ending.get("verdict")} with '
              f'{ending.get("counters", {}).get("open_ports")} ports still '
              f'open')


# ---------------------------------------------------------------------------
@declares("an approval carries the name of the approver",
          "an approval names the claims it accepted",
          "an approval dies when the shape moves",
          "approval writes through the same door as an adoption",
          "the sewing search has no argument for an unapproved shape",
          "the sewing search refuses an unknown approval",
          "a stale approval does not open the search",
          "the sewing search names the corpora that would close it",
          "an embedding backend cannot be a construction corpus",
          "two corpora from one root are not two sources",
          "a repeated structural rejection escalates to a human",
          "convergence counts a rejected claim")
def the_gate_holds() -> None:
    """**The sewing-method search is unreachable without a named approval.**

    A method retrieved for the wrong garment is a plausible wrong answer, and
    plausible wrong answers reach cutting tables. So the block is on the
    SEARCH, it is enforced by the argument surface rather than by discipline,
    and it dies the moment the shape moves.
    """
    import inspect

    from photoloset import (compose, confirm, convergence, cross,
                            garment_rights, resemble, sewing_search, zones)
    from photoloset.garment import Ledger

    res, g, draft, ms = _look_draft()
    st = _look_store()
    land = resemble.land(st, garment_rights.RightsLedger(), res,
                         image_id="img1")
    sheet = confirm.sheet(draft, image_ref="look.jpg", retrieval=land,
                          graph=g["graph"])
    yes = {c["id"]: "yes" for c in sheet["claims"]}
    WHO = "Kodai Motonishi"

    with guard("an approval carries the name of the approver"):
        led = Ledger(title="ci")
        anon = confirm.approve(sheet, yes, "", led, graph=g["graph"])
        blank = confirm.approve(sheet, yes, "   ", led, graph=g["graph"])
        adopters = sorted({e.adopted_by for e in led.entries
                           if e.kind == "observation"})
        # The ledger's OWN size is pinned beside the emptiness claim: the one
        # entry both attempts left behind is an unadopted proposal, so
        # "nobody adopted anything" is not "nothing was written at all".
        kinds = sorted(e.kind for e in led.entries)
        check("an approval carries the name of the approver",
              anon["verdict"] == confirm.NO_ADOPTER
              and blank["verdict"] == confirm.NO_ADOPTER
              and "approval_id" not in anon
              and adopters == []
              and len(led.entries) == 1 and kinds == ["proposal"],
              f'an empty name and a blank one are both {anon["verdict"]} and '
              f'no approval id came back; the {len(led.entries)} entry both '
              f'attempts left is {kinds}, adopted by nobody. '
              f'The check is in Ledger.adopt, not '
              f'in this door — an earlier version put it in the door and '
              f'measurement V60 walked around it')

    with guard("an approval names the claims it accepted"):
        led = Ledger(title="ci")
        short = confirm.approve(sheet, {}, WHO, led, graph=g["graph"])
        said_no = confirm.approve(sheet, {**yes, "c1": "no"}, WHO, led,
                                  graph=g["graph"])
        ap = confirm.approve(sheet, yes, WHO, led, graph=g["graph"])
        named = [a for a in ap.get("adopted", [])
                 if a["adopted_by"] == WHO and "fixture:" in a["source"]]
        check("an approval names the claims it accepted",
              short["verdict"] == confirm.UNANSWERED
              and said_no["verdict"] == confirm.REJECTED
              and said_no["which"] == ["c1"]
              and ap["verdict"] == "ANSWER"
              and ap["accepted"] == [c["id"] for c in sheet["claims"]]
              and len(ap["adopted"]) == 5 and len(named) == 5,
              f'skipping a claim is {short["verdict"]} and rejecting one is '
              f'{said_no["verdict"]}; a full yes adopts {len(ap["adopted"])} '
              f'entries, every one carrying {WHO} and the retrieval source '
              f'that proposed it. The approval is a record of which claims a '
              f'named person accepted, not one opaque token')

    with guard("an approval dies when the shape moves"):
        import tests.coat_digest as _coat
        # **A literal on one side.** `confirm.canon(x) == coat.canon(x)`
        # alone holds whenever both drop the same thing, so what this module
        # answers is written out here in full: 1.0, an int, a bool, a null
        # and 0.1+0.2, each as its exact IEEE-754 bit pattern.
        sample = {"a": [1.0, 2, True, None], "b": {"x": 0.1 + 0.2}}
        BITS = ["dict", [[["str", "a"],
                          ["list", [["f64", "3ff0000000000000"],
                                    ["int", "2"], ["bool", True],
                                    ["null"]]]],
                         [["str", "b"],
                          ["dict", [[["str", "x"],
                                     ["f64", "3fd3333333333334"]]]]]]]
        led = Ledger(title="ci")
        ap = confirm.approve(sheet, yes, WHO, led, graph=g["graph"])
        nudged = zones.apply(g["graph"], {"1": 0.1})
        after = compose.compose(nudged["graph"], ms)
        moved = confirm.shape_digest(after, nudged["graph"])
        sewing_search.reset()
        sewing_search.bind(ledger=led, measures=ms)
        led2 = Ledger(title="ci")
        confirm.approve(confirm.sheet(after, graph=nudged["graph"]), {}, WHO,
                        led2, graph=nudged["graph"])
        sewing_search.bind(ledger=led2, measures=ms)
        stale = sewing_search.methods_for(ap["approval_id"])
        check("an approval dies when the shape moves",
              moved["digest"] != ap["digest"]
              and moved["structure_digest"] != ap["structure_digest"]
              and confirm.canon(sample) == BITS
              and _coat.canon(sample) == BITS
              and stale["verdict"] == sewing_search.SHAPE_NOT_APPROVED,
              f'a +0.1 cm adjustment on zone 1 recomposes to a different '
              f'digest ({ap["digest"][:8]} -> {moved["digest"][:8]}), the '
              f'canonical form is the one tests/coat_digest.py pins the coat '
              f'with (exact IEEE-754, no tolerance), and the old approval no '
              f'longer opens the search: {stale["verdict"]}')

    with guard("approval writes through the same door as an adoption"):
        led = Ledger(title="ci")
        ap = confirm.approve(sheet, yes, WHO, led, graph=g["graph"])
        summary = [e for e in led.entries
                   if e.part == confirm.APPROVAL_PART
                   and e.aspect == confirm.APPROVAL_ASPECT]
        proposals = [e for e in led.entries if e.kind == "proposal"]
        check("approval writes through the same door as an adoption",
              ap["verdict"] == "ANSWER"
              and len(led.entries) == 7
              and len(summary) == 1
              and summary[0].kind == "observation"
              and summary[0].adopted_by == WHO
              and summary[0].value == ap["approval_id"]
              and proposals == []
              and ap["by"] == WHO,
              f'the summary entry (part={confirm.APPROVAL_PART!r}, '
              f'aspect={confirm.APPROVAL_ASPECT!r}) is an ADOPTED proposal — '
              f'kind {summary[0].kind}, adopted_by {summary[0].adopted_by!r} '
              f'— with {len(proposals)} of {len(led.entries)} entries left '
              f'unadopted. Written straight into the entry list it would '
              f'carry no adopter')

    with guard("the sewing search has no argument for an unapproved shape"):
        from photoloset import mcp as _mcp
        # **Every parameter the walk READ is collected**, not only the
        # offending ones: `offenders == []` alone is true when the scan found
        # nothing and when it covered nothing, and a walk that covered nothing
        # is exactly how this gate would quietly stop being enforced.
        walked = []
        surface = []
        for name, fn in sorted(vars(sewing_search).items()):
            if (name.startswith("_") or inspect.isclass(fn)
                    or not callable(fn)
                    or getattr(fn, "__module__", "") != sewing_search.__name__):
                continue
            surface.append(name)
            walked += [(name, p) for p in inspect.signature(fn).parameters]
        reaches = []
        for tname, tfn in sorted(_mcp.TOOLS.items()):
            try:
                src = inspect.getsource(tfn)
            except (OSError, TypeError):
                continue
            if "sewing_search" not in src:
                continue
            reaches.append(tname)
            walked += [(tname, p) for p in inspect.signature(tfn).parameters]
        offenders = [w for w in walked
                     if w[1] in sewing_search.FORBIDDEN_PARAMETERS]
        check("the sewing search has no argument for an unapproved shape",
              len(offenders) == 0 and len(walked) == 9
              and reaches == ["sewing_methods"]
              and sorted(inspect.signature(
                  sewing_search.methods_for).parameters)
              == ["approval_id", "corpus"]
              and surface == ["bind", "corpora", "methods_for",
                              "register_corpus", "reset"]
              and len(sewing_search.FORBIDDEN_PARAMETERS) == 30,
              f'{len(surface)} public callables in sewing_search and '
              f'{len(reaches)} MCP tool that reaches it, {len(walked)} '
              f'parameters read and checked against '
              f'{len(sewing_search.FORBIDDEN_PARAMETERS)} forbidden names: '
              f'{len(offenders)} offenders. methods_for takes '
              f'{sorted(inspect.signature(sewing_search.methods_for).parameters)} '
              f'and nothing else, so the gate cannot be bypassed by adding a '
              f'convenience overload'
              + (f' — OFFENDERS {offenders}' if offenders else ''))

    with guard("the sewing search refuses an unknown approval"):
        led = Ledger(title="ci")
        ap = confirm.approve(sheet, yes, WHO, led, graph=g["graph"])
        sewing_search.reset()
        unbound = sewing_search.methods_for(ap["approval_id"])
        sewing_search.bind(ledger=led, measures=ms)
        ghost = sewing_search.methods_for("deadbeefdeadbeefdeadbeefdeadbeef")
        empty = sewing_search.methods_for("")
        fresh = sewing_search.methods_for(ap["approval_id"])
        check("the sewing search refuses an unknown approval",
              unbound["verdict"] == sewing_search.NO_RECORDS
              and ghost["verdict"] == sewing_search.SHAPE_NOT_APPROVED
              and empty["verdict"] == sewing_search.SHAPE_NOT_APPROVED
              and "cutting tables" in empty["why"]
              and fresh["verdict"] == sewing_search.NO_SEWING_CORPUS
              and fresh["approved_by"] == WHO,
              f'no records bound is {unbound["verdict"]}, an approval id '
              f'nobody adopted is {ghost["verdict"]}, and no id at all is '
              f'{empty["verdict"]}. The one that WAS adopted gets past the '
              f'gate and stops at {fresh["verdict"]}, which is a different '
              f'sentence')

    with guard("a stale approval does not open the search"):
        led = Ledger(title="ci")
        ap = confirm.approve(sheet, yes, WHO, led, graph=g["graph"])
        thicker = _look_measures()
        thicker.measured("chest", 96.0, "cm", source="tape again", by="ci")
        thicker.entries = [m for m in thicker.entries
                           if not (m.spot == "chest" and m.value == 82.0)]
        sewing_search.reset()
        sewing_search.bind(ledger=led, measures=thicker)
        sewing_search.register_corpus(_Corpus("SewFactory", ()))
        stale = sewing_search.methods_for(ap["approval_id"])
        sewing_search.bind(measures=ms)
        opens = sewing_search.methods_for(ap["approval_id"])
        check("a stale approval does not open the search",
              stale["verdict"] == sewing_search.APPROVAL_STALE
              and stale["what_moved"] == "geometry"
              and "methods" not in stale
              and opens["verdict"] == "ANSWER"
              and len(opens["methods"]) == 4,
              f'the chest is re-measured, the approved structure recomposes '
              f'to a different digest and the search refuses '
              f'{stale["verdict"]} ({stale["what_moved"]}) WITH a corpus '
              f'registered — the gate is before the corpus, not after it. '
              f'Put the original measurements back and the same approval '
              f'opens {len(opens["methods"])} methods')

    with guard("the sewing search names the corpora that would close it"):
        led = Ledger(title="ci")
        ap = confirm.approve(sheet, yes, WHO, led, graph=g["graph"])
        sewing_search.reset()
        sewing_search.bind(ledger=led, measures=ms)
        none = sewing_search.methods_for(ap["approval_id"])
        text = none["how_to_close"]
        check("the sewing search names the corpora that would close it",
              none["verdict"] == sewing_search.NO_SEWING_CORPUS
              and "SewFactory" in text and "GarmentCodeData" in text
              and "GarmentCode" in text
              and "register_corpus" in text
              and len(none["would_serve"]) == 3
              and "methods" not in none,
              f'{none["verdict"]} names {len(none["would_serve"])} corpora '
              f'that would serve and the entry point that would register one, '
              f'rather than returning an empty list. This tree ships none of '
              f'them and has measured nothing about them')

    with guard("an embedding backend cannot be a construction corpus"):
        sewing_search.reset()
        emb = sewing_search.register_corpus(
            _Corpus("marqo", (), modality="image_embedding"))
        nolineage = sewing_search.register_corpus(
            _Corpus("NoLineage", None))
        nolicence = sewing_search.register_corpus(
            _Corpus("NoLicence", (), licence=""))
        ok = sewing_search.register_corpus(_Corpus("SewFactory", ()))
        check("an embedding backend cannot be a construction corpus",
              emb["verdict"] == sewing_search.EMBEDDING_NOT_CONSTRUCTION
              and "8.5%" in emb["why"]
              and nolineage["verdict"] == sewing_search.BAD_CORPUS
              and nolineage["field"] == "derived_from"
              and nolicence["verdict"] == sewing_search.BAD_CORPUS
              and ok["verdict"] == "ANSWER"
              and [c["name"] for c in sewing_search.corpora()] == ["SewFactory"],
              f'an image-embedding backend is {emb["verdict"]} — this '
              f'project measured its material ranking flipping 8.5% under a '
              f'horizontal flip, so the finding is a type error rather than a '
              f'paragraph — and a corpus with no lineage or no licence is '
              f'{nolineage["verdict"]}. {len(sewing_search.corpora())} '
              f'registered')

    with guard("two corpora from one root are not two sources"):
        led = Ledger(title="ci")
        ap = confirm.approve(sheet, yes, WHO, led, graph=g["graph"])
        sewing_search.reset()
        sewing_search.bind(ledger=led, measures=ms, store=cross.CrossStore(),
                           rights=garment_rights.RightsLedger())
        sewing_search.register_corpus(_Corpus("GarmentCode", ()))
        sewing_search.register_corpus(_Corpus("GarmentCodeData",
                                              ("GarmentCode",)))
        clash = sewing_search.methods_for(ap["approval_id"])
        sewing_search.reset()
        rights = garment_rights.RightsLedger()
        sewing_search.bind(ledger=led, measures=ms, store=cross.CrossStore(),
                           rights=rights)
        sewing_search.register_corpus(_Corpus("SewFactory", ()))
        sewing_search.register_corpus(_Corpus("Independent", ()))
        clean = sewing_search.methods_for(ap["approval_id"])
        bought = rights.state("bodice", "method:m1")
        check("two corpora from one root are not two sources",
              clash["verdict"] == sewing_search.SHARED_LINEAGE
              and clash["which"] == ["GarmentCode", "GarmentCodeData"]
              and clash["shared_roots"] == ["GarmentCode"]
              and "methods" not in clash
              and clean["verdict"] == "ANSWER"
              and bought["state"] == garment_rights.GENERIC
              and bought["generic_sources"] == ["Independent", "SewFactory"],
              f'GarmentCodeData is generated FROM GarmentCode, so their '
              f'agreement is one generator agreeing with itself: '
              f'{clash["verdict"]} naming {clash["which"]} and their shared '
              f'root {clash["shared_roots"]}. Two corpora with different '
              f'roots do buy the claim ({bought["state"]} from '
              f'{bought["generic_sources"]}) — cross._source_key can see that '
              f'two NAMES differ and cannot see lineage')

    with guard("a repeated structural rejection escalates to a human"):
        history = []
        rounds = [convergence.check(draft, rejected=["c1"], history=history)
                  for _ in range(3)]
        verdicts = [r["verdict"] for r in rounds]
        different = []
        h2 = []
        for i in range(3):
            different.append(convergence.check(draft, rejected=[f"c{i}"],
                                               history=h2)["verdict"])
        undraftable = compose.compose(
            {"parts": [{"instance": "collar:1", "part": "collar"}]}, ms)
        h3 = []
        stuck = [convergence.check(undraftable, history=h3)["verdict"]
                 for _ in range(3)][-1]
        check("a repeated structural rejection escalates to a human",
              verdicts == [convergence.IN_PROGRESS, convergence.IN_PROGRESS,
                           convergence.ESCALATE]
              and different == [convergence.IN_PROGRESS] * 3
              and stuck == convergence.ESCALATE
              and "garment_parts" in convergence.check(
                  undraftable, history=list(h3))["why_escalate"],
              f'three rounds with the SAME claim rejected: {verdicts}. Three '
              f'rounds each rejecting a different claim stay '
              f'{sorted(set(different))} — that loop is making progress. An '
              f'undraftable part three times over is {stuck}, and the message '
              f'names the procedure that is missing rather than saying "try '
              f'again"')

    with guard("convergence counts a rejected claim"):
        clean = convergence.check(draft, history=[])
        churning = convergence.check(draft, rejected=["c1"], history=[])
        check("convergence counts a rejected claim",
              clean["verdict"] == convergence.CONVERGED
              and clean["total_open"] == 0
              and churning["verdict"] == convergence.IN_PROGRESS
              and churning["counters"]["rejected_claims"] == 1
              and churning["total_open"] == 1
              and sorted(clean["counters"]) == ["contested", "failed_checks",
                                                "not_sewable", "open_ports",
                                                "rejected_claims", "unknown"],
              f'the same composed draft is {clean["verdict"]} with nothing '
              f'rejected and {churning["verdict"]} with one claim the human '
              f'answered no. Without that counter every other one reads zero '
              f'and the loop reports CONVERGED on a garment the human keeps '
              f'rejecting')
    sewing_search.reset()
    resemble.reset()


# ---------------------------------------------------------------------------
@declares("a new address continues the loop",
          "agreement is a fixed point without another round",
          "a contradiction is terminal, not a retry",
          "storage order can stop the loop, not just the address map",
          "reopening an adopted address needs a name",
          "the same rejected claim escalates, a different one each round does not")
def the_loop_decides_when_a_round_ends() -> None:
    """**convergence.loop() — the entry point convergence.py was written for.**

    ``check()`` counts what a single state looks like. ``loop()`` decides what
    a ROUND of revisions against the cross-store does next, and the four ways
    it can end are structural, not a retry budget: a new address continues,
    agreement is a fixed point, a contradiction is terminal, and an address
    the ledger has ADOPTED needs a name to reopen. This is a CLAIM, not a
    proof — what is measured here is only that each clause can be made to
    fail on its own mutation, not that the claim is correct.
    """
    from photoloset import convergence
    from photoloset.cross import CrossStore
    from photoloset.garment import OBSERVED, Ledger

    with guard("a new address continues the loop"):
        st = CrossStore()
        r = convergence.loop(
            [{"id": "r1", "core": "coat", "key": "chest", "value": 108.0,
              "kind": "measured", "source": "tape"}], st, history=[])
        check("a new address continues the loop",
              r["verdict"] == convergence.CONTINUE
              and r["new_addresses"] == ["r1"]
              and r["rejected"] == []
              and r["results"][0]["status"] == "NEW_ADDRESS"
              and r["results"][0]["seat_created"] is True,
              f'one revision at an empty store is {r["verdict"]}, landed as '
              f'{r["results"][0]["status"]} — the address space is finite but '
              f'not full, so this is progress, not an ending')

    with guard("agreement is a fixed point without another round"):
        st = CrossStore()
        history: list = []
        first = convergence.loop(
            [{"core": "coat", "key": "chest", "value": 108.0,
              "kind": "measured", "source": "tape"}], st, history=history)
        second = convergence.loop(
            [{"core": "coat", "key": "chest", "value": 108.0,
              "kind": "measured", "source": "tape2"}], st, history=history)
        # A round with NO proposals at all is also a fixed point, on the
        # very first call — it does not need the stagnation counter to have
        # accumulated three matching rounds first.
        empty = convergence.loop([], CrossStore(), history=[])
        check("agreement is a fixed point without another round",
              first["verdict"] == convergence.CONTINUE
              and second["verdict"] == convergence.CONVERGED
              and second["results"][0]["status"] == "AGREES"
              and second["new_addresses"] == []
              and len(history) == 2
              and empty["verdict"] == convergence.CONVERGED
              and empty["history_len"] == 1,
              f'placing then re-proposing the SAME value: {first["verdict"]} '
              f'then {second["verdict"]} after only {len(history)} rounds '
              f'(not the {convergence.STAGNATION_LIMIT}-round stagnation '
              f'limit) — the second call agrees with what is already there, '
              f'so nothing moved and nothing is owed. An empty round against '
              f'a fresh store is {empty["verdict"]} too')

    with guard("a contradiction is terminal, not a retry"):
        st = CrossStore()
        convergence.loop(
            [{"core": "coat", "key": "chest", "value": 108.0,
              "kind": "measured", "source": "tape"}], st, history=[])
        r = convergence.loop(
            [{"core": "coat", "key": "chest", "value": 999.0,
              "kind": "measured", "source": "rumor"}], st, history=[])
        resolved = st.resolve("coat", "chest")
        sides = sorted(s["value"] for s in resolved.get("sides", []))
        # **A THIRD round, resubmitting one of the two already-contested
        # values.** At the STORE layer this is an exact match (verdict
        # ANSWER, state "corroborated" — the value+kind pair is already
        # sitting in that seat from round 2). The defect this guards
        # against: loop() reading that bare ANSWER as agreement without
        # asking whether the ADDRESS itself is still contested. Measured
        # against the shipped-before-this-fix behaviour, which read this as
        # AGREES/CONVERGED — silently un-terminaling a contradiction the
        # module's own reason string calls terminal.
        third = convergence.loop(
            [{"core": "coat", "key": "chest", "value": 108.0,
              "kind": "measured", "source": "third-source"}], st, history=[])
        resolved_after = st.resolve("coat", "chest")
        sides_after = sorted(s["value"] for s in resolved_after.get(
            "sides", []))
        check("a contradiction is terminal, not a retry",
              r["verdict"] == convergence.CONTESTED
              and r["history_len"] == 1
              and resolved["verdict"] == "CONTESTED_IN_CROSS"
              and sides == [108.0, 999.0]
              and third["verdict"] == convergence.CONTESTED
              and third["results"][0]["status"] == "CONTESTED"
              and resolved_after["verdict"] == "CONTESTED_IN_CROSS"
              and sides_after == [108.0, 999.0],
              f'a second, different value at an address that already holds '
              f'one is {r["verdict"]} on the FIRST round it happens (history '
              f'length {r["history_len"]}), not '
              f'after retries. The store itself now resolves '
              f'{resolved["verdict"]} with both {sides} kept — the second '
              f'value did not overwrite the first, and this loop stopped '
              f'rather than picking one. A THIRD round resubmitting one of '
              f'those two sides (108.0, exact match at the store) is '
              f'{third["verdict"]}, not falsely CONVERGED — the address '
              f'still resolves {resolved_after["verdict"]} with both '
              f'{sides_after} kept, and resubmitting a value already on '
              f'file cannot silently declare the contest settled')

    with guard("storage order can stop the loop, not just the address map"):
        ordered = CrossStore()
        history: list = []
        convergence.loop(
            [{"core": "x", "key": "k1", "value": 5.0, "kind": "derived",
              "source": "formula"}], ordered, history=history)
        moved = convergence.loop(
            [{"core": "x", "key": "k1", "value": 5.0, "kind": "measured",
              "source": "tape"}], ordered, history=history)
        # The negative: two DIFFERENT keys never interact this way, so an
        # ordinary round is not order-dependent by construction — the check
        # would not fail if this branch always said ORDER_DEPENDENT either.
        clean = CrossStore()
        settled = convergence.loop(
            [{"core": "y", "key": "k1", "value": 1.0, "kind": "measured",
              "source": "a"}], clean, history=[])
        settled2 = convergence.loop(
            [{"core": "y", "key": "k2", "value": 2.0, "kind": "measured",
              "source": "b"}], clean, history=[])
        check("storage order can stop the loop, not just the address map",
              moved["verdict"] == convergence.ORDER_DEPENDENT
              and moved["order_check"]["differences"]
              and settled["verdict"] != convergence.ORDER_DEPENDENT
              and settled2["verdict"] != convergence.ORDER_DEPENDENT,
              f'the same key written derived-then-measured is '
              f'{moved["verdict"]} with '
              f'{len(moved["order_check"]["differences"])} differing '
              f'addresses when the plan is re-ingested in another order — '
              f'cross.py already names this as the unsettled budget-arm rule. '
              f'Two ordinary, unrelated writes stay {settled["verdict"]} / '
              f'{settled2["verdict"]}, so the check does not fire on '
              f'everything')

    with guard("reopening an adopted address needs a name"):
        anonymous_ledger = Ledger()
        try:
            anonymous_ledger.propose("coat", "shoulder", "46", "tape")
            anonymous_ledger.adopt("coat", "shoulder", "46", by="")
            raised = None
        except ValueError as exc:
            raised = str(exc)

        # **A plain observe(), recorded BEFORE the matching propose()+
        # adopt() at the SAME value, must not mask the adoption.**
        # ``Ledger.state`` used to always read ``obs[0]`` — the first
        # observation in insertion order — for ``adopted_by``. A bare
        # ``observe()`` predating the adopted entry sits first, so the
        # state would report ``adopted_by == ""`` even though the address
        # HAD been adopted (measured directly against the un-fixed code:
        # this exact sequence returned "" before the fix). This is what
        # loop()'s reopen gate actually reads, so a masked adopted_by would
        # make an already-adopted address reopen with no name required.
        masking_ledger = Ledger()
        masking_ledger.observe("coat", "waist", "92", "plain-tape")
        masking_ledger.propose("coat", "waist", "92", "measure-app")
        masking_ledger.adopt("coat", "waist", "92", by="ci-waist")
        masked_state = masking_ledger.state("coat", "waist")

        st = CrossStore()
        led = Ledger()
        # The store carries the SAME 46 the ledger is about to adopt — a
        # human approving a measurement that is already sitting on the
        # cross, the ordinary case, not a fresh address.
        convergence.loop(
            [{"core": "coat", "key": "shoulder", "value": 46.0,
              "kind": "measured", "source": "tape"}], st, history=[])
        led.propose("coat", "shoulder", "46", "tape")
        led.adopt("coat", "shoulder", "46", by="ci")
        blocked = convergence.loop(
            [{"core": "coat", "key": "shoulder", "value": 47.0,
              "kind": "measured", "source": "retape"}], st, ledger=led,
            history=[])
        untouched = st.resolve("coat", "shoulder")
        signed = convergence.loop(
            [{"core": "coat", "key": "shoulder", "value": 47.0,
              "kind": "measured", "source": "retape", "by": "ci2"}], st,
            ledger=led, history=[])
        after = st.resolve("coat", "shoulder")
        # **A THIRD round, no signature, after the ledger already holds TWO
        # observations at this address (46 and the reopened 47).** This is
        # exactly the state where the gate used to break: ``Ledger.state``
        # had flipped from OBSERVED to CONTESTED the moment the reopen
        # landed a second differing observation, and the old gate only
        # fired on ``state == OBSERVED``. Re-asserting the SUPERSEDED value
        # (46) with no `by` must still be blocked — the address was
        # adopted, and adoption does not expire after one use.
        third_superseded = convergence.loop(
            [{"core": "coat", "key": "shoulder", "value": 46.0,
              "kind": "measured", "source": "x3"}], st, ledger=led,
            history=[])
        # Re-asserting the CURRENTLY adopted value (47) needs no signature
        # (it matches what was last adopted) — but the ADDRESS itself is
        # still store-contested (both 46 and 47 are on file, per the fix
        # above), so this must not be silently reported as agreement.
        third_current = convergence.loop(
            [{"core": "coat", "key": "shoulder", "value": 47.0,
              "kind": "measured", "source": "x4"}], st, ledger=led,
            history=[])
        check("reopening an adopted address needs a name",
              raised is not None and "UNKNOWN_NO_ADOPTER" in raised
              and masked_state["state"] == OBSERVED
              and masked_state["adopted_by"] == "ci-waist"
              and blocked["results"][0]["status"] == "REOPEN_BLOCKED"
              and blocked["verdict"] != convergence.CONTESTED
              and untouched["verdict"] == "ANSWER"
              and untouched["value"] == 46.0
              and signed["results"][0]["status"] == "REOPENED_OVER_CONTEST"
              and after["verdict"] == "CONTESTED_IN_CROSS"
              and third_superseded["results"][0]["status"] == "REOPEN_BLOCKED"
              and third_current["results"][0]["status"] == "CONTESTED",
              f'Ledger.adopt on an empty name raises {raised!r}. A plain '
              f'observe() recorded before the matching propose()+adopt() at '
              f'the same value still reports adopted_by='
              f'{masked_state["adopted_by"]!r}, not masked by insertion '
              f'order. Reopening the ADOPTED shoulder (store: 46) with no '
              f'adopter is {blocked["results"][0]["status"]} and the store '
              f'still reads {untouched.get("value")} ({untouched["verdict"]}) '
              f'— the 47 never landed; with a name it is '
              f'{signed["results"][0]["status"]} and the store honestly '
              f'reports {after["verdict"]}. A THIRD round with no name, '
              f'after the ledger already holds two differing observations '
              f'at this address, still gets '
              f'{third_superseded["results"][0]["status"]} on the superseded '
              f'value (46) — the gate survives past its first use — and '
              f'{third_current["results"][0]["status"]} on the currently '
              f'adopted value (47), because the store itself is still '
              f'contested even though no signature was needed to say so')

    with guard("the same rejected claim escalates, a different one each round does not"):
        st = CrossStore()
        led = Ledger()
        led.propose("coat", "waist", "92", "tape")
        led.adopt("coat", "waist", "92", by="ci")
        history: list = []
        rounds = [convergence.loop(
            [{"id": "rev-waist", "core": "coat", "key": "waist",
              "value": 999.0, "kind": "measured", "source": "bad"}], st,
            ledger=led, history=history) for _ in range(3)]
        same = [r["verdict"] for r in rounds]

        st2, led2 = CrossStore(), Ledger()
        h2: list = []
        rounds2 = []
        for i in range(3):
            led2.propose("coat", f"p{i}", "x", "tape")
            led2.adopt("coat", f"p{i}", "x", by="ci")
            rounds2.append(convergence.loop(
                [{"id": f"rev-{i}", "core": "coat", "key": f"p{i}",
                  "value": "y", "kind": "measured", "source": "bad"}], st2,
                ledger=led2, history=h2))
        different = [r["verdict"] for r in rounds2]
        check("the same rejected claim escalates, a different one each round does not",
              same == [convergence.CONTINUE, convergence.CONTINUE,
                       convergence.ESCALATE]
              and different == [convergence.CONTINUE] * 3,
              f'the SAME blocked reopen three rounds running: {same}. Three '
              f'rounds each blocked on a DIFFERENT address: {different} — '
              f'a loop making progress on different fronts is not held to '
              f'the same limit as one stuck on one')


class _Corpus:
    """A FIXTURE construction corpus. **It measured nothing** — it answers one
    method per query from a literal, and it exists so the gate can be driven
    end to end without a dataset. Nothing registers it at import."""

    def __init__(self, name, roots, modality="parametric_program",
                 licence="fixture licence (verify from the dataset card)"):
        self._name, self._roots = name, roots
        self._modality, self._licence = modality, licence

    def name(self):
        return self._name

    def licence(self):
        return self._licence

    def derived_from(self):
        return self._roots

    def modality(self):
        return self._modality

    def synthetic(self):
        return True

    def find(self, query):
        return {"verdict": "ANSWER",
                "methods": [{"id": "m1", "step": "m1",
                             "panels": query.get("panels"),
                             "seams": query.get("seam_labels"),
                             "stitch_order": ["side", "shoulder"]}],
                "searched": query}


# ---------------------------------------------------------------------------
#: **The checks that cannot fail, and why each one is allowed to stand.**
#: ``tests/unfalsifiable.py`` reads every ``check()`` condition in this file
#: and reports the shapes that make a line green no matter what the code
#: does. This project shipped ELEVEN of those across five passes, each found
#: by somebody looking harder — a method that does not scale. So the sweep is
#: a check of its own now, and the residue is enumerated here with the
#: argument for keeping it. **A hit that is not on this list turns the suite
#: red**, which is the whole point: the next one has to be argued in a diff
#: rather than discovered in six months.
#:
#: The list is SHORT because the last pass fixed rather than argued: twenty
#: conditions grew the number they had been printing (both drape distances,
#: the coat's area, the census counts, the known-variant lists), one
#: tautological clause was deleted, and seven readers that could have been
#: frozen to a constant now answer from two stores in one condition.
KNOWN_UNFALSIFIABLE = [
    ("T1", "the same order lays the same marker", "borderline",
     "`a[\"placement\"] == b[\"placement\"]` on two identical calls IS the T1 "
     "shape, and a determinism check cannot avoid it — the property under "
     "test is literally that the same input gives the same output. What "
     "makes it non-vacuous is the clause beside it: a DIFFERENT order "
     "(counts doubled) must give a different placement list AND a different "
     "length. So the equality has to discriminate before its passing means "
     "anything. Falsifier: 'the marker sorts by insertion order instead of "
     "height', which makes the two identical calls agree and the doubled "
     "order stop differing in the way the check pins."),
    ("T1", "a dart is addressed in the stable numbering", "borderline",
     "`n_before == n_after` is literally two calls with the same arguments, "
     "which is the T1 shape. They are not the same value by construction: "
     "`_pt.label(grown, reg)` runs BETWEEN them and registers four new edges "
     "on the same registry object. A registry that renumbered on growth — "
     "the whole failure `points.py` exists to prevent — makes them differ, "
     "and that is measured: the falsifier 'the registry re-sorts itself, so "
     "a new piece shifts the old bases' turns this check red. The tool "
     "cannot see the mutation between the two calls, so it rates the shape "
     "and not the timing."),
    ("T1", "round trip moves nothing", "borderline",
     "Two calls of `.dump()` on two receivers IS the shape, and the two "
     "receivers here are DIFFERENT objects — one is the coat, the other is "
     "a BlockView over a store rebuilt from its own to_dict(). A check like "
     "that can go red: it goes red the day the round trip loses something, "
     "which is the property. The tool rates it borderline for that reason "
     "and the same condition also pins the served sections by name, the "
     "formula and seam counts, and `len(b.dump()) > 2000` against literals. "
     "Falsifier: '#17 served() quietly stops carrying the formulas'."),
    ("T2", "a contest survives the matryoshka", "borderline",
     "The any() is a FILTER inside a list comprehension, not the assertion, "
     "and it is vacuously FALSE on empty — the direction that makes a check "
     "fail rather than pass. The tool says so itself."),
    ("T2", "equal is not the same observation", "borderline",
     "Same shape, same safe direction: a vacuously FALSE any() inside a "
     "comprehension. The genuine quantifier beside it, all(listed), carries "
     "`len(listed) == 4` in the same condition."),
    ("T2", "the dress has no notches yet, and marks says so honestly", "real",
     "The scan really is over nothing: compose() hard-codes "
     "`\"notch_plan\": []` in its own ANSWER — a literal, not derived from "
     "the input graph — so nothing in this codebase can make a composed "
     "garment's notch_plan non-empty yet (garment_parts's own docstring "
     "names this as unfinished: 合印の方針は次の段で宣言ごとに足す). There is "
     "no non-empty case to point at inside THIS draft for that reason. The "
     "condition is not vacuous as a whole, though: it also carries "
     "`len(sa_ok) == 6 == len(sa)`, pinned against the marks pipeline "
     "actually running seam-allowance offsets on all six pieces, and the "
     "falsifier 'marks stop computing seam allowances' turns exactly that "
     "clause — and this check — red by breaking the offset step, without "
     "touching notch_plan at all."),
    ("T2", "the dress reaches DXF directly, because save() cannot draft it",
     "real",
     "Same reason: with 0 notches produced upstream (see the entry above), "
     "`out[\"notch_lines\"]` summing to 0 is a certainty, not a discovery. "
     "The condition also pins `out[\"extents_cm\"]` to two literal "
     "coordinate pairs, which the falsifier 'the DXF export spaces pieces "
     "further apart on the sheet' moves by widening GAP_CM — no coat check "
     "reads extents_cm literally, so that mutation is invisible everywhere "
     "except this line, which is exactly what makes it a real falsifier "
     "for this check rather than for the notch count."),
    ("T4", "SVG geometry untouched", "real",
     "The property IS 'this document and its translation have the same "
     "geometry', so both sides necessarily grow from one source; no "
     "rewriting removes that. What the shape warns about — the transform "
     "silently becoming the identity — is covered in the same condition by "
     "`svg_en != outs[\'svg\']` and `\'back bodice\' in svg_en`, and by "
     "the falsifier 'i18n.svg() becomes the identity', which turns this "
     "line red."),
]


def no_check_can_pass_by_construction() -> None:
    """**A check that cannot fail is a defect, and the suite hunts them now.**

    Eight of them shipped before anyone noticed, in four passes: 1, then 3,
    then 5-6, then 7-8, and three more were found by hand after that.
    Looking harder is not a method — this is. ``tests/unfalsifiable.py``
    reads the AST of every ``check()`` in this file and reports the shapes
    that cannot go red; the residue is pinned in ``KNOWN_UNFALSIFIABLE``
    with an argument each, and anything new fails here.

    **Three checks, because one of them was itself a check that could not
    fail.** The sweep is static, so it can only report the shape of a
    condition; T7 — "this reader could be a frozen constant and nobody would
    notice" — is not visible in any condition at all, and the version of
    this line that asked whether a literal appears NEXT TO a reader answered
    yes for five readers that could be frozen with the suite green. So the
    T7 verdict is read from ``tests/t7_readers.json``, which records what
    happened when each reader WAS frozen and the whole suite re-run, keyed
    by a digest of the reader's own source so a stale answer cannot pass.
    And the scanner's ``--self-test`` runs here, because a detector nobody
    tests is the same defect one level further up.

    What it still cannot see is printed by the tool itself and worth
    repeating: it reads CONDITIONS, so a perfectly shaped check whose callee
    answers from a cache is invisible to it, and so is a property nobody
    wrote a check for at all.
    """
    sys.path.insert(0, str(ROOT / "tests"))
    import unfalsifiable

    out = unfalsifiable.scan(ROOT / "tests" / "run_checks.py",
                             ROOT / "photoloset",
                             ROOT / "tests" / "falsifiers.py")
    hits = out.get("hits", [])
    known = {(shape, name, conf) for shape, name, conf, _why
             in KNOWN_UNFALSIFIABLE}
    got = [(h["shape"], h["check"], h["confidence"]) for h in hits]
    new_hits = [g for g in got if g not in known]
    gone = [k for k in known if k not in got]
    readers = out.get("readers", [])
    unscanned = out.get("unscanned", [])
    check("no check that cannot fail",
          out.get("verdict") == "ANSWER"
          and unscanned == []
          and out.get("checks_with_a_condition", 0) >= 85
          and len(known) == len(KNOWN_UNFALSIFIABLE)
          and len(KNOWN_UNFALSIFIABLE) == 8
          and len(got) == len(KNOWN_UNFALSIFIABLE)
          and not new_hits and not gone
          and len(readers) == 18,
          f'{out.get("checks_with_a_condition")} conditions swept, '
          f'{len(hits)} hits — {len(got) - len(new_hits)} of them on the '
          f'record of {len(KNOWN_UNFALSIFIABLE)} with a reason, '
          f'{len(new_hits)} not; {len(readers)} served readers; '
          f'{len(unscanned)} detectors refused'
          + (f' — NEW {new_hits}' if new_hits else '')
          + (f' — NO LONGER FIRING (delete it from the list) {gone}'
             if gone else ''))

    # **T7, by mutation.** Live when asked for (about 20 minutes), from the
    # ledger otherwise — and the ledger is not a note in a handoff: it is
    # keyed by the digest of each reader's source, so changing a reader
    # without re-probing it turns this line red rather than carrying an
    # answer about code that no longer exists.
    live = (os.environ.get("PHOTOLOSET_T7_RUNTIME") == "1"
            and not os.environ.get("PHOTOLOSET_T7_PROBE"))
    if live:
        probes = unfalsifiable.run_probes(readers, ROOT, jobs=4)
        bypassable = sorted(p["reader"] for p in probes if p.get("bypassable"))
        refused = sorted(p.get("reader", "?") for p in probes
                         if p.get("verdict") != "ANSWER")
        how = f'measured now, {len(probes)} probes'
    else:
        gate = out.get("ledger", {})
        bypassable = gate.get("bypassable", []) + gate.get("stale", [])
        refused = gate.get("missing", [])
        how = (f'from {unfalsifiable.LEDGER.name}, recorded '
               f'{gate.get("generated", "?")}, {gate.get("probed", 0)} '
               f'readers (set PHOTOLOSET_T7_RUNTIME=1 to re-measure)')
    check("every served reader reads its store",
          not bypassable and not refused and len(readers) == 18,
          f'{len(readers)} readers, each one frozen to the literal it '
          f'returns today and the whole suite re-run — {how}'
          + (f' — BYPASSABLE OR STALE {bypassable}' if bypassable else '')
          + (f' — NEVER PROBED {refused}' if refused else ''))

    # **The scanner scanned.** One check of every shape it claims to detect,
    # planted in tests/corpus/ and asserted to be found; honest checks in the
    # same shapes asserted NOT to be called certainties; and T7 answered by
    # mutation on a fixture whose answer is known.
    fails, lines = unfalsifiable.self_test(verbose=False, report=True)
    planted = len(unfalsifiable.PLANTED)
    check("the scanner finds every planted shape",
          not fails and planted >= 20,
          f'{planted} shapes planted and found, 0 false positives at "real" '
          f'on the honest corpus, the harness guard read for what it catches, '
          f'and one reader proved bypassable by freezing it'
          + (f' — SELF-TEST FAILED {fails}' if fails else ''))


def the_falsifier_harness_reports_everything() -> None:
    """**The mutation harness must not stop early either.**

    ``tests/falsifiers.py`` proves each check can go red. It had the defect
    it exists to find, one level up: a raise anywhere in its own loop ended
    the sweep at mutation N, the rest neither ran nor were named, no summary
    printed, and the file it had mutated was never restored — so anything
    that did continue would have been scored against a poisoned tree.

    ``--self-test`` runs the harness over three entries with a POISONED one
    in the middle, twice: once raising before the file is read and once
    raising inside the run, after the file is already mutated. It passes
    only if the entries after the poison still ran and still went red, the
    poison was named, the summary printed and the tree came back clean.
    """
    r = subprocess.run([sys.executable, "tests/falsifiers.py", "--self-test"],
                       cwd=ROOT, capture_output=True, text=True, timeout=900)
    passed = [l for l in r.stdout.splitlines() if l.startswith("  RED ")]
    # The universal in the name is EVERY MUTATION, so the line names it: in
    # both poisoned sweeps the harness has to say "ran 3 of 3" — the count
    # that tells a short run from a complete one — and it has to restore
    # every file it touched.
    mutations_reported = [l for l in r.stdout.splitlines()
                          if l.startswith("        entries named: 3 of 3")]
    check("the falsifier harness reports every mutation",
          r.returncode == 0 and len(passed) == 2
          and len(mutations_reported) == 2
          and "2/2 harness self-tests" in r.stdout,
          f'{len(passed)}/2 poisoned sweeps still ran and reported every '
          f'entry after the raise ({len(mutations_reported)}/2 said "3 of 3"'
          f'), restored the tree and printed the summary '
          f'(exit {r.returncode})'
          + ("" if r.returncode == 0 else f" — {r.stdout[-200:]}"))


# ---------------------------------------------------------------------------
@declares("a number is a function of its address",
          "adding a piece never moves a number",
          "a reshaped outline is refused, not renumbered",
          "a span across two edges is refused",
          "the registry round-trips")
def numbers_survive_a_revision() -> None:
    """**"Loosen 30 to 35" has to mean the same place next time round.**

    If the numbering shifts when the pattern is revised, the user's own
    instruction changes meaning between iterations and the agent loop cannot
    converge — it would be chasing a moving target it created itself.

    So the number is DERIVED from the address (piece, edge, t) rather than
    allocated by walking a list. The failure this exists for is the obvious
    implementation: enumerate the current pieces and hand out consecutive
    numbers. That works until a piece is added, and then every number after
    it points somewhere else.
    """
    import copy as _copy

    from photoloset import garment_measure as _gm
    from photoloset import garment_pattern as _gp
    from photoloset import points as _pt

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    draft = _gp.draft(ms)

    reg = _pt.Registry()
    labelled = _pt.label(draft, reg)

    with guard("a number is a function of its address"):
        # **The falsifier, run inline.** The obvious wrong implementation is
        # to walk the current pieces and hand out consecutive numbers. It
        # passes any test that only registers once. So this check builds
        # that implementation, runs BOTH against the same revision, and
        # requires the naive one to BREAK — if it does not, the property
        # under test is true by construction and this check is worthless.
        def naive(d):
            """Numbering by enumeration — what this module must not be."""
            out, n = {}, 0
            for piece in d.get("pieces") or []:
                nm = piece.get("name") or "?"
                for k in range(len(piece.get("outline") or [])):
                    out[f"{nm}/e{k}"] = n
                    n += _pt.STRIDE
            return out

        watch = [("後身頃", "e0", 0.0), ("後身頃", "e3", 0.5),
                 ("袖", "e2", 1.0)]
        grown0 = _copy.deepcopy(draft)
        grown0["pieces"].insert(0, {"name": "先頭に割り込む裁片",
                                    "area_cm2": 1.0,
                                    "outline": [[0.0, 0.0], [1.0, 0.0],
                                                [1.0, 1.0]]})
        mine_before = [_pt.number(reg, a, b, t) for a, b, t in watch]
        naive_before = naive(draft)
        probe = _pt.Registry(dict(reg._bases), dict(reg._shape))
        _pt.label(grown0, probe)
        mine_after = [_pt.number(probe, a, b, t) for a, b, t in watch]
        naive_after = naive(grown0)
        naive_moved = [k for k in naive_before
                       if naive_after.get(k) != naive_before[k]]
        check("a number is a function of its address",
              mine_before == mine_after
              and len(watch) == 3
              and len(naive_moved) >= 15
              and naive_before["後身頃/e0"] != naive_after["後身頃/e0"],
              f'a piece inserted at the FRONT: these numbers {mine_before} '
              f'are unchanged, while enumeration moves {len(naive_moved)} '
              f'of {len(naive_before)} edges including 後身頃/e0 '
              f'({naive_before["後身頃/e0"]} -> {naive_after["後身頃/e0"]}). '
              f'If enumeration had survived this, the check would be vacuous')

    with guard("adding a piece never moves a number"):
        before = _pt.Registry(dict(reg._bases), dict(reg._shape))
        watched = {n: _pt.resolve(reg, n) for n in (0, 30, 35, 99, 100, 250)}
        grown = _copy.deepcopy(draft)
        grown["pieces"].insert(1, {"name": "ケープ", "area_cm2": 200.0,
                                   "outline": [[0.0, 0.0], [10.0, 0.0],
                                               [10.0, 20.0], [0.0, 20.0]]})
        _pt.label(grown, reg)
        moved = _pt.renumber_check(before, reg)
        # Counted, not all()-ed: `all` over an empty dict is True, so a
        # watch list that silently became empty would read as a pass.
        agreed = sum(
            1 for n, was in watched.items()
            if (was["piece"], was["edge"], was["t_lo"])
            == (_pt.resolve(reg, n)["piece"], _pt.resolve(reg, n)["edge"],
                _pt.resolve(reg, n)["t_lo"]))
        check("adding a piece never moves a number",
              moved["stable"] and agreed == 6 and len(watched) == 6
              and len(moved["added"]) == 4
              and moved["checked"] == 21,
              f'{moved["checked"]} edges checked, {len(moved["moved"])} '
              f'moved, {len(moved["added"])} added by the cape; '
              f'{agreed} of {len(watched)} sampled numbers resolve to the '
              f'same piece/edge/t. A registry that renumbered would have '
              f'moved every number past the cape')

    with guard("a reshaped outline is refused, not renumbered"):
        # The remaining hole, made loud. Edge names are eN off the outline's
        # vertex order, so inserting ONE vertex makes e1 a different segment
        # while every base stays put — renumber_check says "stable" and the
        # numbers point somewhere else. Measured before this refusal existed:
        # 100/150/250/300 all kept their edge NAME across the insertion.
        reshaped = _copy.deepcopy(draft)
        for piece in reshaped["pieces"]:
            if piece["name"] == "後身頃":
                a, b = piece["outline"][0], piece["outline"][1]
                piece["outline"].insert(
                    1, [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0])
        fresh = _pt.Registry(dict(reg._bases), dict(reg._shape))
        said = _pt.label(reshaped, fresh)
        blind = _pt.renumber_check(
            _pt.Registry(dict(reg._bases), dict(reg._shape)), fresh)
        check("a reshaped outline is refused, not renumbered",
              said["verdict"] == _pt.RESHAPED
              and said["pieces"] == [{"piece": "後身頃", "was": 7, "now": 8}]
              and blind["stable"],
              f'{said["verdict"]} naming 後身頃 7 -> 8. renumber_check '
              f'still says stable={blind["stable"]} — no base moved, which '
              f'is exactly why this refusal has to exist separately')

    with guard("a span across two edges is refused"):
        inside = _pt.span(reg, 30, 35)
        across = _pt.span(reg, 95, 105)
        unknown = _pt.resolve(reg, 10 ** 6)
        check("a span across two edges is refused",
              inside["verdict"] == "ANSWER"
              and inside["piece"] == "後身頃" and inside["edge"] == "e0"
              and len(inside["numbers"]) == 6
              and round(inside["t_lo"], 4) == 0.303
              and round(inside["t_hi"], 4) == 0.3636
              and across["verdict"] == "UNKNOWN_SPAN_CROSSES_EDGES"
              and unknown["verdict"] == _pt.NO_NUMBER,
              f'30..35 is {inside["piece"]}/{inside["edge"]} '
              f't {inside["t_lo"]:.3f}..{inside["t_hi"]:.3f}; 95..105 '
              f'crosses an edge and is refused; 10^6 is {unknown["verdict"]}')

    with guard("the registry round-trips"):
        blob = json.dumps(reg.to_json(), ensure_ascii=False)
        back = _pt.Registry.from_json(json.loads(blob))
        stale = dict(reg.to_json())
        stale["stride"] = _pt.STRIDE + 1
        try:
            _pt.Registry.from_json(stale)
            refused = ""
        except ValueError as exc:
            refused = str(exc).split(":")[0]
        check("the registry round-trips",
              back._bases == reg._bases and back._shape == reg._shape
              and refused == _pt.MOVED,
              f'{len(back._bases)} bases and {len(back._shape)} shapes '
              f'survive JSON; a saved registry with a different stride is '
              f'{refused or "ACCEPTED — every saved number would move"}')


# ---------------------------------------------------------------------------
@declares("closing a dart shortens the edge by the intake",
          "a dart whose apex leaves the panel is refused",
          "truing moves the dart until the legs match",
          "a dart never edits the outline it sits on",
          "overlapping darts are refused and separated ones are not",
          "a dart is addressed in the stable numbering")
def darts_make_the_panel_three_dimensional() -> None:
    """**The first thing here that is not a flat development.**

    Every piece so far unrolls flat. A dart is a wedge taken out so the two
    legs can be sewn together and the cloth becomes a cone — the bust, the
    shoulder blade, the waist. Without it a garment is a tube.

    The dart is NOT written into the outline. Inserting its legs as vertices
    would change the vertex count, which is exactly what ``points`` refuses
    as UNKNOWN_OUTLINE_RESHAPED — every number on that piece would move.
    So darts are a separate layer addressed at (piece, edge, t), the same
    address the numbering uses.
    """
    import copy as _copy

    from photoloset import darts as _dt
    from photoloset import garment_measure as _gm
    from photoloset import garment_pattern as _gp
    from photoloset import points as _pt

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    draft = _gp.draft(ms)
    frozen = _copy.deepcopy(draft)

    with guard("closing a dart shortens the edge by the intake"):
        r = _dt.apply(draft, [_dt.dart("後身頃", "e2", 0.5, 3.0, 12.0,
                                       role="ウエスト")])
        one = r["darts"][0]
        shrink = one["edge_cm_before"] - one["edge_cm_after_closing"]
        # The measurable content of a dart: the edge gets shorter by exactly
        # the intake when the legs are sewn together. An implementation that
        # forgot to subtract would report the same length twice.
        check("closing a dart shortens the edge by the intake",
              r["count"] == 1 and abs(shrink - 3.0) < 1e-9
              and round(one["edge_cm_before"], 4) == 7.0682
              and round(one["edge_cm_after_closing"], 4) == 4.0682
              and one["developable"] is False,
              f'{one["edge_cm_before"]:.4f} -> '
              f'{one["edge_cm_after_closing"]:.4f} cm, shrink '
              f'{shrink:.4f} == intake 3.0; the piece reports '
              f'developable={one["developable"]}')

    with guard("a dart whose apex leaves the panel is refused"):
        # Found by the sweep, not by design: the mutation "an apex outside
        # the panel is accepted" went MISS because nothing here exercised a
        # dart deep enough to leave the piece. The refusal existed and was
        # tested by hand; no check constrained it, so deleting it changed
        # nothing anybody was watching.
        #
        # Two failure modes, one accept, and the boundary between them is
        # 0.5 cm wide — measured on this piece, not chosen:
        #   26.5 cm  apex inside, margin 0.505  ->  accepted
        #   27.0 cm  apex inside, margin 0.053  ->  refused, too near the edge
        #   27.5 cm  apex outside the panel     ->  refused
        ok = _dt.apply(draft, [_dt.dart("後身頃", "e2", 0.5, 3.0, 26.5)])
        tight = _dt.apply(draft, [_dt.dart("後身頃", "e2", 0.5, 3.0, 27.0)])
        gone = _dt.apply(draft, [_dt.dart("後身頃", "e2", 0.5, 3.0, 27.5)])
        check("a dart whose apex leaves the panel is refused",
              ok["count"] == 1 and ok["refused"] == []
              and round(ok["darts"][0]["apex_margin_cm"], 4) == 0.5053
              and tight["count"] == 0
              and tight["refused"][0]["verdict"] == _dt.APEX_OUT
              and round(tight["refused"][0]["margin_cm"], 4) == 0.0526
              and gone["count"] == 0
              and gone["refused"][0]["verdict"] == _dt.APEX_OUT
              and _dt.APEX_MARGIN_CM == 0.5,
              f'26.5 cm deep is kept with margin '
              f'{ok["darts"][0]["apex_margin_cm"]:.4f} >= '
              f'{_dt.APEX_MARGIN_CM}; 27.0 cm is {_dt.APEX_OUT} at margin '
              f'{tight["refused"][0]["margin_cm"]:.4f}; 27.5 cm leaves the '
              f'panel entirely. A guard that refused everything would not '
              f'have kept the first')

    with guard("truing moves the dart until the legs match"):
        # A perpendicular dart has equal legs BY CONSTRUCTION — the apex sits
        # on the base's perpendicular bisector — so testing equality there
        # proves nothing. Only a dart aimed at an anatomical point can have
        # unequal legs, and truing is what a pattern maker does about it.
        perp = _dt.apply(draft, [_dt.dart("後身頃", "e2", 0.5, 3.0, 12.0)]
                         )["darts"][0]
        aimed = _dt.apply(draft, [_dt.dart("後身頃", "e4", 0.5, 3.0,
                                           toward=(14.0, 60.0))])["darts"][0]
        check("truing moves the dart until the legs match",
              perp["trued"] is False
              and aimed["trued"] is True
              and round(aimed["trued_from_t"], 6) == 0.5
              and round(aimed["t"], 6) == 0.434783
              and abs(aimed["leg_a_cm"] - aimed["leg_b_cm"]) < 1e-6
              and abs(perp["leg_a_cm"] - perp["leg_b_cm"]) < 1e-9,
              f'perpendicular: legs equal without truing (trued='
              f'{perp["trued"]}); aimed at (14,60): t 0.5 -> '
              f'{aimed["t"]:.6f} and legs {aimed["leg_a_cm"]:.6f} == '
              f'{aimed["leg_b_cm"]:.6f}. Untrued legs would differ')

    with guard("a dart never edits the outline it sits on"):
        _dt.apply(draft, [_dt.dart("後身頃", "e2", 0.5, 3.0, 12.0),
                          _dt.dart("前身頃", "e2", 0.4, 2.0, 9.0)])
        counts = {p["name"]: len(p["outline"]) for p in draft["pieces"]}
        reg = _pt.Registry()
        _pt.label(frozen, reg)
        after = _pt.label(draft, _pt.Registry(dict(reg._bases),
                                              dict(reg._shape)))
        check("a dart never edits the outline it sits on",
              draft == frozen and counts == {"後身頃": 7, "前身頃": 7,
                                             "袖": 7}
              and after["verdict"] == "ANSWER",
              f'two darts applied, outlines still {counts} and the draft is '
              f'byte-identical; the numbering says {after["verdict"]}. '
              f'Legs written in as vertices would give '
              f'{_pt.RESHAPED} and move every number on the piece')

    with guard("overlapping darts are refused and separated ones are not"):
        clash = _dt.apply(draft, [_dt.dart("後身頃", "e4", 0.5, 4.0, 10.0,
                                           role="A"),
                                  _dt.dart("後身頃", "e4", 0.51, 4.0, 10.0,
                                           role="B")])
        apart = _dt.apply(draft, [_dt.dart("後身頃", "e4", 0.3, 4.0, 10.0,
                                           role="A"),
                                  _dt.dart("後身頃", "e4", 0.7, 4.0, 10.0,
                                           role="B")])
        # Both directions. A refusal that fires on everything is not a check.
        check("overlapping darts are refused and separated ones are not",
              clash["count"] == 1
              and [x["verdict"] for x in clash["refused"]] == [_dt.OVERLAP]
              and apart["count"] == 2 and apart["refused"] == [],
              f'0.50 and 0.51 on a 92 cm edge: {clash["count"]} kept, '
              f'{[x["verdict"] for x in clash["refused"]]}; 0.30 and 0.70: '
              f'{apart["count"]} kept, {len(apart["refused"])} refused')

    with guard("a dart is addressed in the stable numbering"):
        reg = _pt.Registry()
        _pt.label(draft, reg)
        d = _dt.apply(draft, [_dt.dart("後身頃", "e4", 0.5, 4.0, 10.0)]
                      )["darts"][0]
        n_before = _pt.number(reg, d["piece"], d["edge"], d["t"])
        grown = _copy.deepcopy(draft)
        grown["pieces"].insert(0, {"name": "割り込み", "area_cm2": 1.0,
                                   "outline": [[0.0, 0.0], [1.0, 0.0],
                                               [1.0, 1.0]]})
        _pt.label(grown, reg)
        n_after = _pt.number(reg, d["piece"], d["edge"], d["t"])
        where = _pt.resolve(reg, n_before)
        check("a dart is addressed in the stable numbering",
              n_before == n_after
              and where["piece"] == "後身頃" and where["edge"] == "e4"
              and _dt.apply(draft, [_dt.dart("後身頃", "nope", 0.5, 3.0,
                                             9.0)])["refused"][0]["verdict"]
              == _dt.NO_EDGE,
              f'the dart sits at number {n_before}, still {n_after} after a '
              f'piece is inserted at the front, and resolves to '
              f'{where["piece"]}/{where["edge"]}. An unknown edge is '
              f'{_dt.NO_EDGE}')


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# A tiny, INDEPENDENT DXF reader — group-code/value pairs, never the writer's
# own code. It has to read the file the way an outsider's CAD would, so a bug
# shared between ``photoloset.dxf`` and the check that verifies it could not
# make a broken export look correct.
def _dxf_blocks(text: str) -> list:
    """Split into ``(entity_type, {code: [values...]})`` at each group-0
    boundary. HEADER variables have no ``0`` of their own, so the whole
    HEADER section lands in one block — that is read directly by callers
    that need a header variable, not re-split here."""
    lines = text.splitlines()
    pairs = [(int(lines[i].strip()), lines[i + 1])
             for i in range(0, len(lines) - 1, 2)]
    blocks: list = []
    cur_type, cur_codes = None, None
    for code, val in pairs:
        if code == 0:
            if cur_type is not None:
                blocks.append((cur_type, cur_codes))
            cur_type, cur_codes = val.strip(), {}
        elif cur_codes is not None:
            cur_codes.setdefault(code, []).append(val.strip())
    if cur_type is not None:
        blocks.append((cur_type, cur_codes))
    return blocks


def _dxf_polylines(blocks: list) -> list:
    """Reassemble POLYLINE/VERTEX/SEQEND runs into closed point lists."""
    polys: list = []
    i = 0
    while i < len(blocks):
        t, codes = blocks[i]
        if t == "POLYLINE":
            layer = codes.get(8, ["0"])[0]
            closed = bool(int(codes.get(70, ["0"])[0]) & 1)
            verts = []
            j = i + 1
            while j < len(blocks) and blocks[j][0] == "VERTEX":
                vc = blocks[j][1]
                verts.append((float(vc[10][0]), float(vc[20][0])))
                j += 1
            polys.append({"layer": layer, "closed": closed,
                          "vertices": verts})
            i = j + 1 if j < len(blocks) and blocks[j][0] == "SEQEND" else j
            continue
        i += 1
    return polys


def _dxf_lines(blocks: list) -> list:
    return [{"layer": codes.get(8, ["0"])[0],
             "a": (float(codes[10][0]), float(codes[20][0])),
             "b": (float(codes[11][0]), float(codes[21][0]))}
            for t, codes in blocks if t == "LINE"]


def _dxf_texts(blocks: list) -> list:
    return [{"layer": codes.get(8, ["0"])[0],
             "x": float(codes[10][0]), "y": float(codes[20][0]),
             "text": codes.get(1, [""])[0]}
            for t, codes in blocks if t == "TEXT"]


def _shoelace(points: list) -> float:
    """Polygon area, independent of ``garment_pattern._area`` — this file
    reads the parsed coordinates back, it does not call the drafter's own
    formula on them."""
    n = len(points)
    s = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _pt_close(a: tuple, b: tuple, tol: float = 1e-3) -> bool:
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


@declares("the DXF file parses as group-code pairs",
          "every draft vertex survives to its DXF coordinate",
          "the cut line and sewing line are different curves on separate layers",
          "DXF notch and grain lines land at the marks' own positions",
          "the DXF round-trips into rebuilt piece areas")
def pattern_exports_to_a_cad_file() -> None:
    """**The piece that lets an outsider verify the whole project.**

    Every other check here reads this project's own data structures. A DXF
    opens in somebody else's software — this repository verified its own
    output against ``ezdxf`` while writing it (not shipped: standard library
    only), and it opened with zero audit errors and every Japanese piece
    name intact. No ASTM D6673 / DXF-AAMA conformance is claimed — that
    standard was withdrawn in 2019 with no replacement — so this checks the
    file as a plain R12 group-code stream, never by grepping for strings.
    """
    import math
    import tempfile
    from pathlib import Path

    from photoloset import dxf as _dxf
    from photoloset import garment_marks, garment_pattern
    from photoloset import garment_measure as _gm
    from photoloset.garment_marks import arc_lengths, at_arc

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    draft = garment_pattern.draft(ms)
    marked = garment_marks.apply(draft)

    with tempfile.TemporaryDirectory() as tmp:
        out = _dxf.save(ms, str(Path(tmp) / "coat.dxf"))
        raw = Path(out["path"]).read_bytes()
        text = raw.decode(_dxf.ENCODING)
        blocks = _dxf_blocks(text)
        polys = _dxf_polylines(blocks)
        lines = _dxf_lines(blocks)
        texts = _dxf_texts(blocks)
        sew_polys = [p for p in polys if p["layer"] == _dxf.LAYER_SEW]
        cut_polys = [p for p in polys if p["layer"] == _dxf.LAYER_CUT]

        with guard("the DXF file parses as group-code pairs"):
            section_names = [c.get(2, [""])[0] for t, c in blocks
                             if t == "SECTION"]
            endsec = sum(1 for t, _c in blocks if t == "ENDSEC")
            eof = sum(1 for t, _c in blocks if t == "EOF")
            layer_names = sorted(c.get(2, [""])[0] for t, c in blocks
                                 if t == "LAYER")
            expected_layers = sorted([_dxf.LAYER_SEW, _dxf.LAYER_CUT,
                                      _dxf.LAYER_NOTCH, _dxf.LAYER_GRAIN,
                                      _dxf.LAYER_LABEL])
            header_block = next(
                (c for t, c in blocks if t == "SECTION"
                and c.get(2, [""])[0] == "HEADER"), {})
            # $DWGCODEPAGE is the only HEADER variable this file writes
            # under group code 3, so it can be read directly by code —
            # the other variables ($ACADVER, $INSBASE, $EXTMIN, $EXTMAX)
            # use different group codes and are not needed here.
            dwgcodepage = header_block.get(3, [None])[0]
            total_vertices = sum(len(p["vertices"]) for p in polys)
            expected_vertices = sum(
                len(p["outline"])
                + (len(marked["seam_allowance"][p["name"]]["cut_line"])
                  if marked["seam_allowance"][p["name"]].get("verdict")
                  == "ANSWER" else 0)
                for p in marked["pieces"])
            # NOT a count on its own: the decoded TEXT strings must equal the
            # real piece names (a writer that labelled every piece "PIECE"
            # would still pass a count-only check but fails this).
            text_names = sorted(t["text"] for t in texts)
            expected_names = sorted(p["name"] for p in marked["pieces"])
            check("the DXF file parses as group-code pairs",
                  section_names == ["HEADER", "TABLES", "ENTITIES"]
                  and endsec == 3 and eof == 1
                  and layer_names == expected_layers
                  and dwgcodepage == _dxf.DWGCODEPAGE
                  and total_vertices == expected_vertices > 0
                  and len(texts) == len(marked["pieces"]) == 3
                  and text_names == expected_names,
                  f'sections {section_names}, {endsec} ENDSEC, {eof} EOF, '
                  f'{len(layer_names)} layers {layer_names}, '
                  f'$DWGCODEPAGE={dwgcodepage}, {total_vertices} POLYLINE '
                  f'vertices == {expected_vertices} expected from the '
                  f'draft outlines plus the cut lines, {len(texts)} TEXT '
                  f'labels reading {text_names} for pieces {expected_names}')

        with guard("every draft vertex survives to its DXF coordinate"):
            n_pieces = len(marked["pieces"])
            expected_vertices = sum(len(p["outline"])
                                    for p in marked["pieces"])
            checked = 0
            good = 0
            mismatches = []
            for piece, poly in zip(marked["pieces"], sew_polys):
                dx = out["placement"][piece["name"]][0]
                draft_pts = [(round(x, 4), round(y, 4))
                            for x, y in piece["outline"]]
                file_pts = [(round(x - dx, 4), round(y, 4))
                           for x, y in poly["vertices"]]
                checked += len(draft_pts)
                if file_pts == draft_pts:
                    good += 1
                else:
                    mismatches.append((piece["name"], file_pts[:2],
                                      draft_pts[:2]))
            closed_count = sum(1 for p in sew_polys if p["closed"])
            # **Every clause below names a POSITIVE count and pins it to the
            # literal 3 on its own** — never one count chained straight
            # against another (that reads as "however many there happened
            # to be, they matched", true at zero too). ``good`` is the
            # number of pieces whose file vertices matched the draft
            # EXACTLY; a scan that covered nothing leaves ``good == 0``,
            # which fails ``good == 3`` outright.
            check("every draft vertex survives to its DXF coordinate",
                  len(sew_polys) == 3 and n_pieces == 3
                  and good == 3 and closed_count == 3
                  and checked == expected_vertices and expected_vertices > 0,
                  f'{len(sew_polys)} SEWING_LINE polylines for {n_pieces} '
                  f'pieces, {good}/{n_pieces} exact after subtracting each '
                  f'piece\'s own placement offset ({checked} vertices '
                  f'checked against {expected_vertices} in the draft, not '
                  f'rounded further), {closed_count}/{len(sew_polys)} closed'
                  + (f' — MISMATCHES {mismatches}' if mismatches else ''))

        with guard("the cut line and sewing line are different curves on "
                   "separate layers"):
            pairs = list(zip(sew_polys, cut_polys))
            n_pairs = len(pairs)
            # Counted, not all() — a count compared to the SAME literal 3
            # that pins ``n_pairs`` cannot read "every pair agreed" when
            # there were zero pairs to agree.
            layer_hits = sum(1 for a, b in pairs
                             if a["layer"] == _dxf.LAYER_SEW
                             and b["layer"] == _dxf.LAYER_CUT)
            differ_hits = sum(1 for a, b in pairs
                              if set(a["vertices"]) != set(b["vertices"]))
            # Area from the FILE's own points, by a formula this file does
            # not share with ``garment_pattern`` or ``garment_marks`` — the
            # seam allowance has to have made it out to the export, not
            # merely be present in the source dict.
            area_grows = [_shoelace(b["vertices"]) - _shoelace(a["vertices"])
                         for a, b in pairs]
            growth_hits = sum(1 for g in area_grows if g > 5.0)
            check("the cut line and sewing line are different curves on "
                 "separate layers",
                  n_pairs == 3 and layer_hits == 3 and differ_hits == 3
                  and growth_hits == 3,
                  f'{n_pairs} pieces: SEWING_LINE/CUT_LINE layers correct '
                  f'on {layer_hits}/{n_pairs}, vertex sets differ on '
                  f'{differ_hits}/{n_pairs}, cut area exceeds sew area on '
                  f'{growth_hits}/{n_pairs} by '
                  f'{[round(g, 1) for g in area_grows]} cm2 — if the seam '
                  f'allowance never reached the export, cut would equal '
                  f'sew and none of these would hold')

        with guard("DXF notch and grain lines land at the marks' own "
                   "positions"):
            # NOT a population count. For every notch this file's own
            # to_dxf() drew, INDEPENDENTLY recompute the tangent/normal at
            # its (edge, arc_cm) and the endpoint its depth_cm and kind
            # imply, using only garment_marks.arc_lengths/at_arc (never
            # photoloset.dxf's own code) — then require a NOTCHES-layer
            # LINE at those exact two points (translated by that piece's
            # placement offset). This is the check that catches a flipped
            # notch-normal sign or a zeroed depth: both change the file's
            # actual endpoints away from what the marks + geometry require,
            # while a population count could not tell.
            def _expected_notch_segments():
                segs = []
                for p in marked["pieces"]:
                    name = p["name"]
                    dx = out["placement"][name][0]
                    edges = p["edges"]
                    for n in marked["notches"].get(name, []):
                        edge = edges.get(n["edge"])
                        if not edge:
                            continue
                        pl = edge["points"]
                        total = arc_lengths(pl)[-1]
                        base = at_arc(pl, n["arc_cm"])
                        ahead = at_arc(pl, min(n["arc_cm"] + 0.5, total))
                        back = at_arc(pl, max(n["arc_cm"] - 0.5, 0.0))
                        tx, ty = ahead[0] - back[0], ahead[1] - back[1]
                        L = math.hypot(tx, ty) or 1.0
                        nx, ny = ty / L, -tx / L
                        d = n["depth_cm"]
                        offsets = (0.0,) if n["kind"] == "single" \
                            else (-0.3, 0.3)
                        for o in offsets:
                            bx = base[0] + tx / L * o
                            by = base[1] + ty / L * o
                            a = (bx + dx, by)
                            b = (bx + nx * d + dx, by + ny * d)
                            segs.append((a, b))
                return segs

            def _expected_grain_segments():
                segs = []
                grain_by_piece = {g["piece"]: g for g in marked["grain"]}
                for p in marked["pieces"]:
                    name = p["name"]
                    dx = out["placement"][name][0]
                    g = grain_by_piece.get(name)
                    if not g:
                        continue
                    (gx1, gy1), (gx2, gy2) = g["line"]
                    segs.append(((gx1 + dx, gy1), (gx2 + dx, gy2)))
                return segs

            notch_file = [ln for ln in lines if ln["layer"] == _dxf.LAYER_NOTCH]
            grain_file = [ln for ln in lines if ln["layer"] == _dxf.LAYER_GRAIN]
            expected_notch = _expected_notch_segments()
            expected_grain = _expected_grain_segments()

            def _match(expected, file_lines):
                remaining = list(file_lines)
                hits = 0
                for a, b in expected:
                    for i, ln in enumerate(remaining):
                        if _pt_close(ln["a"], a) and _pt_close(ln["b"], b):
                            hits += 1
                            del remaining[i]
                            break
                return hits

            notch_hits = _match(expected_notch, notch_file)
            grain_hits = _match(expected_grain, grain_file)
            expected_notch_lines = sum(
                1 if n["kind"] == "single" else 2
                for ns in marked["notches"].values() for n in ns)
            check("DXF notch and grain lines land at the marks' own "
                 "positions",
                  len(notch_file) == expected_notch_lines == len(expected_notch)
                  and notch_hits == expected_notch_lines > 0
                  and len(grain_file) == len(expected_grain)
                  == len(marked["grain"])
                  and grain_hits == len(expected_grain) > 0,
                  f'{notch_hits}/{expected_notch_lines} NOTCHES-layer LINE '
                  f'entities land exactly on an independently-recomputed '
                  f'(edge, arc_cm, depth_cm, kind) endpoint (single=1 line, '
                  f'double=2); {grain_hits}/{len(expected_grain)} '
                  f'GRAIN_LINES entities land exactly on the marks\' own '
                  f'grain["line"], translated by placement — a flipped '
                  f'notch normal or a zeroed depth moves the actual '
                  f'endpoint away from this and would drop the hit count')

        with guard("the DXF round-trips into rebuilt piece areas"):
            piece_area = {p["name"]: p["area_cm2"] for p in marked["pieces"]}
            sa = marked["seam_allowance"]
            # **Rounding the outline to 4 decimals before writing it already
            # moves the shoelace area a measurable amount** — measured
            # directly on the DRAFT's own stored (2-decimal) outline, before
            # any DXF is involved: 袖 alone is 0.277 cm2 off from its
            # reported area_cm2 (which garment_pattern computes on the
            # UNROUNDED points, then rounds only the final number). 0.35 cm2
            # sits above that measured noise floor and far below what a
            # dropped vertex or a mis-offset cut line would move — those are
            # multiple cm2 at minimum on a piece this size.
            TOL = 0.35
            sew_diffs = [abs(_shoelace(poly["vertices"])
                            - piece_area[piece["name"]])
                        for piece, poly in zip(marked["pieces"], sew_polys)]
            cut_diffs = [abs(_shoelace(poly["vertices"])
                            - sa[piece["name"]]["cut_area_cm2"])
                        for piece, poly in zip(marked["pieces"], cut_polys)]
            total_rebuilt = round(sum(_shoelace(p["vertices"])
                                      for p in sew_polys), 1)
            n_pieces = len(marked["pieces"])
            sew_hits = sum(1 for d in sew_diffs if d < TOL)
            cut_hits = sum(1 for d in cut_diffs if d < TOL)
            # Each count below is pinned to the literal 3 on its own line —
            # ``sew_hits`` (how many pieces passed) is never chained
            # straight against ``len(sew_diffs)`` (how many pieces were
            # measured), because that pairing would hold at zero too.
            check("the DXF round-trips into rebuilt piece areas",
                  n_pieces == 3 and len(sew_diffs) == 3 and len(cut_diffs) == 3
                  and sew_hits == 3 and cut_hits == 3
                  and abs(total_rebuilt - draft["total_area_cm2"]) < 1.0,
                  f'rebuilding each SEWING_LINE polygon from the file and '
                  f'measuring its area (shoelace, computed in this check — '
                  f'not garment_pattern\'s) matches area_cm2 to within '
                  f'{TOL} cm2 on {sew_hits}/{len(sew_diffs)} pieces (worst '
                  f'{max(sew_diffs):.4f} cm2); the same for CUT_LINE '
                  f'against cut_area_cm2 on {cut_hits}/{len(cut_diffs)} '
                  f'(worst {max(cut_diffs):.4f} cm2); total rebuilt '
                  f'{total_rebuilt} cm2 vs draft\'s '
                  f'{draft["total_area_cm2"]} cm2')

@declares("there is no body below the dress form",
          "the garment is moved onto the form without changing shape",
          "clearance is measured on the garment as it fell",
          "the clearance states partition every point")
def the_garment_goes_onto_a_body() -> None:
    """**The step between a pattern and "loosen 30 to 35".**

    dress() used to raise on every garment: radius_at did
    ``max(i for i ... if levels[i][0] <= y)`` and the generator is empty for
    any height below the form. A long coat's hem hanging below a torso form
    is not an error — it is what actually happens, and the true answer there
    is "there is no body at this height".

    The two frames genuinely disagree. Measured on the reference coat: the
    garment falls from y -5.89 to -130.92 with its x centred on 20.7, while
    the form stands from 0 to 69.44 on the axis. The alignment is stated in
    the output rather than assumed.
    """
    import math as _math

    from photoloset import garment_marks as _mk
    from photoloset import garment_measure as _gm
    from photoloset import garment_pattern as _gp
    from photoloset import garment_sew as _gs
    from photoloset import mannequin as _mq

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0),
                        ("waist", 92.0), ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    draft = _gp.draft(ms)
    built = _gs.build(_mk.apply(draft))
    mat = {"verdict": "ANSWER", "fabric": "wool melton", "gsm": 420.0,
           "thickness": 0.18, "stiffness": 20.0}
    fell = _gs.sew_and_drape(built, mat, iterations=400)["points"]
    man = _mq.build(ms)

    with guard("there is no body below the dress form"):
        top = man["_levels"][-1][0]
        inside = _mq.radius_at(man, top * 0.5, 0.0)
        under = _mq.radius_at(man, -50.0, 0.0)
        over = _mq.radius_at(man, top + 50.0, 0.0)
        # Both directions. A radius_at that returned None everywhere would
        # make dress() answer nothing at all and still pass a one-sided test.
        check("there is no body below the dress form",
              isinstance(inside, float) and inside > 0.0
              and under is None and over is None
              and round(top, 2) == 69.44,
              f'the form stands 0..{top:.2f}; at half height the surface is '
              f'{inside:.3f} cm, at -50 it is {under}, at {top + 50:.0f} it '
              f'is {over}. This used to raise ValueError for every garment')

    with guard("the garment is moved onto the form without changing shape"):
        al = _mq.align(man, fell)
        moved = al["points"]

        def spread(ps):
            return (max(q[0] for q in ps) - min(q[0] for q in ps),
                    max(q[1] for q in ps) - min(q[1] for q in ps),
                    max(q[2] for q in ps) - min(q[2] for q in ps))

        def d(ps, i, j):
            return _math.dist(ps[i], ps[j])

        pairs = [(0, 40), (5, 120), (77, 200), (12, 296)]
        kept = sum(1 for i, j in pairs
                   if abs(d(fell, i, j) - d(moved, i, j)) < 1e-9)
        before, after = spread(fell), spread(moved)
        axes = sum(1 for a, b in zip(before, after) if abs(a - b) < 1e-9)
        check("the garment is moved onto the form without changing shape",
              kept == len(pairs) == 4
              and axes == 3 and len(before) == len(after) == 3
              and round(al["rule"]["dy_cm"], 2) == 75.33
              and round(al["rule"]["dx_cm"], 2) == -20.71
              and round(max(q[1] for q in moved), 4)
              == round(man["_levels"][-1][0], 4),
              f'dy {al["rule"]["dy_cm"]}, dx {al["rule"]["dx_cm"]}: '
              f'{kept} of {len(pairs)} sampled distances unchanged to 1e-9 '
              f'and {axes} of 3 bounding-box axes identical. The top now sits exactly '
              f'on the form\'s neckline. A scale would have moved both')

    with guard("clearance is measured on the garment as it fell"):
        worn = _mq.dress(man, fell)
        c_fell = _mq.clearance(man, fell)
        c_worn = _mq.clearance(man, worn["points"])
        # THE POINT. dress() pushes every point out to surface + gap, so the
        # clearance of a dressed garment is the gap BY CONSTRUCTION. Measuring
        # fit on that output would be a check that cannot fail. The two are
        # run side by side here so the difference is a measurement.
        spread_worn = (c_worn["max_clearance_cm"]
                       - c_worn["min_clearance_cm"])
        spread_fell = (c_fell["max_clearance_cm"]
                       - c_fell["min_clearance_cm"])
        # The dressed spread is not exactly zero: dress() rounds its points
        # to four decimals, so 0.0064 cm of rounding survives. That is the
        # honest number, and it is still three orders of magnitude below the
        # spread of the garment as it fell.
        check("clearance is measured on the garment as it fell",
              spread_worn < 0.01
              and spread_fell > 20.0
              and spread_fell / spread_worn > 1000.0
              and c_fell["inside_the_body"] == 101
              and c_worn["inside_the_body"] == 0
              and round(c_fell["min_clearance_cm"], 4) == -14.4256
              and round(c_fell["max_clearance_cm"], 4) == 12.9008
              and round(c_worn["min_clearance_cm"], 4) == 0.9968,
              f'dressed: every clearance is {c_worn["min_clearance_cm"]} cm, '
              f'spread {spread_worn:.9f} — the gap, by construction. '
              f'As it fell: {c_fell["min_clearance_cm"]} to '
              f'{c_fell["max_clearance_cm"]} cm, spread {spread_fell:.2f} — '
              f'{spread_fell / spread_worn:.0f}x wider — with '
              f'{c_fell["inside_the_body"]} points inside the body. '
              f'That is what no collision handling costs')

    with guard("the clearance states partition every point"):
        c = _mq.clearance(man, fell)
        total = (c["inside_the_body"] + c["clinging"] + c["apart"]
                 + c["no_body_at_that_height"])
        states = {r["state"] for r in c["per_point"]}
        check("the clearance states partition every point",
              total == c["points"] == len(fell) == 297
              and states == {"INSIDE_THE_BODY", "CLINGING", "APART",
                             _mq.NO_BODY}
              and c["no_body_at_that_height"] == 138
              and c["worst"]["state"] == "INSIDE_THE_BODY",
              f'{c["inside_the_body"]} inside + {c["clinging"]} clinging + '
              f'{c["apart"]} apart + {c["no_body_at_that_height"]} with no '
              f'body = {total} = every one of the {len(fell)} points, and '
              f'all four states occur. A state nothing lands in would let a '
              f'whole category go unnoticed')


# ---------------------------------------------------------------------------
@declares("a closed sphere totals four pi by angle defect",
          "a developable cylinder carries no curvature",
          "the mannequin's total curvature converges while its band "
          "distribution does not",
          "the curvature report shares the total, it does not compute a "
          "dart intake",
          "curvature refuses missing measurements and a grid too coarse "
          "to triangulate")
def a_pattern_piece_absorbs_curvature_two_ways() -> None:
    """**Gauss-Bonnet, made into a number a pattern maker can read.**

    ``curvature.angle_sums`` is checked here against two ground truths it
    does not depend on the mannequin for: a closed sphere (angle defect
    must total exactly 4*pi, a topological identity, not an asymptotic
    one) and a developable cylinder (must total exactly 0, since a
    cylinder unrolls flat without stretching). A quad four-neighbour
    scheme — the shape this module's docstring says the first attempt
    used — satisfies neither identity; only a genuine triangle-fan does.

    Then the mannequin itself: total curvature over (20,12) -> (40,24) ->
    (80,48) -> (160,96) grids settles (that is a measurement), while the
    SAME four grids' height-band split swings by tens of degrees (that is
    the honest limit — the mannequin's five levels are creases, and a
    crease's curvature lands on whichever grid row is nearest it, which
    moves as the grid changes). Finally: the report never turns the total
    into a dart intake in centimetres — the earlier mistake this module's
    docstring records (90 degrees / 12 cm dart = 18.85 cm, against a real
    bust dart of 2-4 cm, from ignoring the boundary term) — and it refuses
    rather than defaults on missing measurements or an untriangulable grid.
    """
    import json as _json
    import math as _math

    from photoloset import curvature as _cv
    from photoloset import garment_measure as _gm
    from photoloset import mannequin as _mq

    def _sphere_total_deg(segments: int, hsteps: int,
                          radius: float = 10.0) -> float:
        """Closed UV sphere with the poles as SINGLE vertices. A naive UV
        grid that gives each pole `segments` coincident-but-distinct
        vertices double-counts the pole's angle and reports 1440 degrees
        instead of 720 — that duplicate-vertex mistake is how this
        helper's own correctness was checked before it went into the
        suite, and it is why the poles are collapsed here."""
        verts = [(0.0, radius, 0.0)]
        npole = 0
        ring_start: dict = {}
        for j in range(1, hsteps):
            phi = _math.pi * j / hsteps
            ring_start[j] = len(verts)
            for i in range(segments):
                th = 2 * _math.pi * i / segments
                verts.append((radius * _math.sin(phi) * _math.cos(th),
                             radius * _math.cos(phi),
                             radius * _math.sin(phi) * _math.sin(th)))
        spole = len(verts)
        verts.append((0.0, -radius, 0.0))
        faces = []
        r1 = ring_start[1]
        for i in range(segments):
            i2 = (i + 1) % segments
            faces.append((npole, r1 + i, r1 + i2))
        for j in range(1, hsteps - 1):
            ra, rb = ring_start[j], ring_start[j + 1]
            for i in range(segments):
                i2 = (i + 1) % segments
                faces.append((ra + i, ra + i2, rb + i2))
                faces.append((ra + i, rb + i2, rb + i))
        r_last = ring_start[hsteps - 1]
        for i in range(segments):
            i2 = (i + 1) % segments
            faces.append((spole, r_last + i2, r_last + i))
        sums = _cv.angle_sums(verts, faces)
        return _math.degrees(sum(2 * _math.pi - s for s in sums))

    def _cylinder_total_deg(segments: int, hsteps: int, radius: float = 10.0,
                            height: float = 20.0) -> float:
        verts = []
        for j in range(hsteps + 1):
            y = height * j / hsteps
            for i in range(segments):
                th = 2 * _math.pi * i / segments
                verts.append((radius * _math.cos(th), y,
                             radius * _math.sin(th)))
        faces = []
        for j in range(hsteps):
            for i in range(segments):
                i2 = (i + 1) % segments
                a_i, b_i = j * segments + i, j * segments + i2
                c_i, d_i = (j + 1) * segments + i2, (j + 1) * segments + i
                faces.append((a_i, b_i, c_i))
                faces.append((a_i, c_i, d_i))
        sums = _cv.angle_sums(verts, faces)
        total = 0.0
        for j in range(1, hsteps):
            for i in range(segments):
                total += 2 * _math.pi - sums[j * segments + i]
        return _math.degrees(total)

    with guard("a closed sphere totals four pi by angle defect"):
        s_coarse = _sphere_total_deg(20, 10)
        s_fine = _sphere_total_deg(80, 40)
        check("a closed sphere totals four pi by angle defect",
              abs(s_coarse - 720.0) < 1e-6 and abs(s_fine - 720.0) < 1e-6,
              f'20x10 UV sphere: {s_coarse:.9f} deg, 80x40: {s_fine:.9f} '
              f'deg — both within 1e-6 of 4*pi = 720 deg. Discrete '
              f'Gauss-Bonnet on a CLOSED surface is an exact identity, not '
              f'an asymptotic one, when the per-vertex sum is a genuine '
              f'triangle-fan')

    with guard("a developable cylinder carries no curvature"):
        c_coarse = _cylinder_total_deg(20, 12)
        c_fine = _cylinder_total_deg(80, 48)
        check("a developable cylinder carries no curvature",
              abs(c_coarse) < 1e-6 and abs(c_fine) < 1e-6,
              f'20x12 cylinder: {c_coarse:.2e} deg, 80x48: {c_fine:.2e} '
              f'deg — both within 1e-6 of 0. A cylinder unrolls flat, so '
              f'its angle defect must vanish; paired with the sphere '
              f'above this checks the same primitive against one nonzero '
              f'and one zero ground truth')

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("waist", 92.0),
                        ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    man = _mq.build(ms)
    rep = _cv.report(man)

    with guard("the mannequin's total curvature converges while its band "
              "distribution does not"):
        totals = [s["total_deg"] for s in rep["refinement"]]
        # Pairs, not `range(len(totals) - 1)`: the length clause below has
        # to pin the SAME sequence `all()` consumes, or a static reader
        # cannot tell the range is non-empty from a length asserted about a
        # different name (tests/unfalsifiable.py's T2 flagged exactly the
        # `range(len(totals) - 1)` form as unpinned even with `len(totals)
        # == 4` sitting right beside it, because the iterable inside all()
        # was the range object, not `totals` itself).
        step_pairs = list(zip(totals, totals[1:]))
        spreads = rep["band_spread_across_refinement_deg"]
        min_spread = min(spreads.values())
        spread_summary = {k: round(v, 1) for k, v in spreads.items()}
        check("the mannequin's total curvature converges while its band "
              "distribution does not",
              rep["verdict"] == "ANSWER" and len(totals) == 4
              and len(step_pairs) == 3
              and all(a < b for a, b in step_pairs)
              and round(rep["total_deg_change_last_step"], 4) == 0.0298
              and 180.0 < rep["total_deg_coarsest"] < rep["total_deg"] < 185.0
              and min_spread > 10.0,
              f'total_deg over (20,12)->(40,24)->(80,48)->(160,96): '
              f'{[round(t, 3) for t in totals]} deg, strictly increasing, '
              f'settling to a last-step change of '
              f'{rep["total_deg_change_last_step"]:.4f} deg. Over the SAME '
              f'four grids every band swings by more than 10 deg, '
              f'spread {spread_summary} — the total is a measurement, the '
              f'per-band split is a function of grid alignment against the '
              f"mannequin's 5 fixed creases")

    with guard("the curvature report shares the total, it does not "
              "compute a dart intake"):
        blob = _json.dumps(rep, default=str)
        forbidden = [k for k in ("dart_intake", "intake_cm", "dart_cm",
                                 "recommended_dart") if k in blob]
        check("the curvature report shares the total, it does not "
              "compute a dart intake",
              rep["verdict"] == "ANSWER" and not forbidden
              and "ダーツ" in rep["total_is_shared_not_split"]
              and "輪郭" in rep["total_is_shared_not_split"],
              f'{len(forbidden)} forbidden keys found in the report '
              f'{forbidden}; total_is_shared_not_split names both the '
              f'outline (輪郭) and darts (ダーツ) as the two payers '
              f'without assigning either a number of centimetres')

    with guard("curvature refuses missing measurements and a grid too "
              "coarse to triangulate"):
        empty_man = _mq.build(_gm.Measures())
        good = _cv.mesh(man, 20, 12)
        bad_segments = _cv.mesh(man, 2, 12)
        bad_height = _cv.mesh(man, 20, 0)
        one_res = _cv.report(man, [(20, 12)])
        no_res = _cv.report(man, [])
        missing = _cv.report(empty_man)
        check("curvature refuses missing measurements and a grid too "
              "coarse to triangulate",
              rep["verdict"] == "ANSWER" and good["verdict"] == "ANSWER"
              and missing["verdict"] == _mq.NO_MEASURE
              and bad_segments["verdict"] == _cv.BAD_RESOLUTION
              and bad_height["verdict"] == _cv.BAD_RESOLUTION
              and one_res["verdict"] == _cv.NEEDS_TWO
              and no_res["verdict"] == _cv.NO_RESOLUTIONS,
              f'good grid (20,12) -> {good["verdict"]}; missing '
              f'measurements -> {missing["verdict"]}; segments=2 -> '
              f'{bad_segments["verdict"]}; height_steps=0 -> '
              f'{bad_height["verdict"]}; one resolution -> '
              f'{one_res["verdict"]}; zero resolutions -> '
              f'{no_res["verdict"]}')


# ---------------------------------------------------------------------------
@declares("a marker refuses what it cannot know",
          "the seam allowance is inside the fabric it needs",
          "more copies need more fabric",
          "the same order lays the same marker")
def the_marker_says_how_much_fabric() -> None:
    """**The number somebody has to buy against.**

    A correct pattern nobody can order cloth for is not finished. Getting the
    number needs three things the pattern does not carry, and each is refused
    rather than defaulted: how many of each piece to cut, the seam allowance
    (the draft is the SEWING line, so counting on it would always come up
    short), and the fabric width.
    """
    from photoloset import garment_measure as _gm
    from photoloset import garment_pattern as _gp
    from photoloset import marker as _mkr

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0),
                        ("waist", 92.0), ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    draft = _gp.draft(ms)
    CUT = {"後身頃": 1, "前身頃": 2, "袖": 2}

    with guard("a marker refuses what it cannot know"):
        no_count = _mkr.lay(draft, 150.0, {}, 1.5)
        no_sa = _mkr.lay(draft, 150.0, CUT, None)
        no_width = _mkr.lay(draft, 0.0, CUT, 1.5)
        too_wide = _mkr.lay(draft, 25.0, CUT, 1.5)
        good = _mkr.lay(draft, 150.0, CUT, 1.5)
        # Five outcomes, four of them refusals and one an answer. A gate that
        # refused everything would pass any test that only checked refusals.
        check("a marker refuses what it cannot know",
              no_count["verdict"] == _mkr.NO_COUNT
              and sorted(no_count["pieces"]) == ["前身頃", "後身頃", "袖"]
              and no_sa["verdict"] == _mkr.NO_SA
              and no_width["verdict"] == _mkr.NO_WIDTH
              and too_wide["verdict"] == _mkr.TOO_WIDE
              and round(too_wide["widest_cm"], 2) == 34.0
              and good["verdict"] == "ANSWER",
              f'no counts -> {no_count["verdict"]} naming all 3 pieces; '
              f'no allowance -> {no_sa["verdict"]}; no width -> '
              f'{no_width["verdict"]}; a 34.0 cm piece on 25 cm cloth -> '
              f'{too_wide["verdict"]}; and a real order answers')

    with guard("the seam allowance is inside the fabric it needs"):
        tight = _mkr.lay(draft, 150.0, CUT, 0.0)
        wide = _mkr.lay(draft, 150.0, CUT, 3.0)
        one = _mkr.lay(draft, 150.0, CUT, 1.5)
        # The draft is the sewing line. If the allowance did not reach the
        # fabric figure, ordering by it would always come up short, and the
        # error would only appear at the cutting table.
        check("the seam allowance is inside the fabric it needs",
              one["sewing_line_area_cm2"] < one["cut_rectangle_area_cm2"]
              and one["cut_rectangle_area_cm2"] <= one["fabric_area_cm2"]
              and tight["cut_rectangle_area_cm2"]
              < one["cut_rectangle_area_cm2"]
              < wide["cut_rectangle_area_cm2"]
              and tight["length_cm"] < wide["length_cm"]
              and round(one["sewing_line_area_cm2"], 1) == 11666.4,
              f'sewing line {one["sewing_line_area_cm2"]} cm2 < cut '
              f'rectangles {one["cut_rectangle_area_cm2"]} cm2 <= cloth '
              f'{one["fabric_area_cm2"]} cm2; 0 cm allowance gives '
              f'{tight["length_cm"]} cm of cloth and 3 cm gives '
              f'{wide["length_cm"]} cm')

    with guard("more copies need more fabric"):
        one = _mkr.lay(draft, 150.0, CUT, 1.5)
        twice = _mkr.lay(draft, 150.0,
                         {k: v * 2 for k, v in CUT.items()}, 1.5)
        narrow = _mkr.lay(draft, 90.0, CUT, 1.5)
        ratio = twice["length_cm"] / one["length_cm"]
        # NOT 2x: doubling the order lets the shelves pack better. If this
        # came out at exactly 2.0 the packer would be laying each copy on its
        # own row and calling it a marker.
        check("more copies need more fabric",
              twice["length_cm"] > one["length_cm"]
              and 1.4 < ratio < 1.9
              and twice["pieces_laid"] == 10 == one["pieces_laid"] * 2
              and narrow["utilisation_pct"] > one["utilisation_pct"]
              and round(one["utilisation_pct"], 2) == 53.91
              and round(narrow["utilisation_pct"], 2) == 89.85
              and round(one["length_m"], 3) == 1.966
              and round(twice["length_m"], 3) == 3.116,
              f'5 pieces on 150 cm: {one["length_m"]} m at '
              f'{one["utilisation_pct"]}%. Ten pieces: {twice["length_m"]} m '
              f'— {ratio:.2f}x, not 2x, because the shelves fill. The same '
              f'five on 90 cm cloth: {narrow["utilisation_pct"]}% used')

    with guard("the same order lays the same marker"):
        import copy as _copy

        a = _mkr.lay(draft, 150.0, CUT, 1.5)
        b = _mkr.lay(draft, 150.0, CUT, 1.5)
        # **The marker must not depend on the order the pieces arrive in.**
        # Found by the sweep: "the marker lays pieces in the order they
        # arrived" went MISS, because on the reference coat the pieces are
        # already generated tallest-first (112, 112, 78.6) and removing the
        # sort changed nothing anybody was watching. Handing the sleeve in
        # first is the case that can tell.
        shuffled = _copy.deepcopy(draft)
        shuffled["pieces"] = (
            [q for q in shuffled["pieces"] if q["name"] == "袖"]
            + [q for q in shuffled["pieces"] if q["name"] != "袖"])
        reordered = _mkr.lay(shuffled, 150.0, CUT, 1.5)
        napped = _mkr.lay(draft, 150.0, CUT, 1.5, nap="none")
        # `a == b` on two identical calls is the same-value-on-both-sides
        # shape, and on its own it would pass even if the comparison could
        # not tell two markers apart. So a DIFFERENT order is compared too:
        # the equality has to discriminate before its passing means anything.
        other = _mkr.lay(draft, 150.0,
                         {k: v * 2 for k, v in CUT.items()}, 1.5)
        # Nap is recorded and changes nothing, and the module says so rather
        # than reporting a freedom it does not use: rotating a bounding
        # rectangle by 180 degrees gives the same rectangle.
        check("the same order lays the same marker",
              a["placement"] == b["placement"]
              and reordered["placement"] == a["placement"]
              and [q["name"] for q in shuffled["pieces"]]
              != [q["name"] for q in draft["pieces"]]
              and other["placement"] != a["placement"]
              and other["length_cm"] != a["length_cm"]
              and a["length_cm"] == b["length_cm"]
              and napped["length_cm"] == a["length_cm"]
              and napped["nap"] == "none" and a["nap"] == _mkr.NAP_UNKNOWN
              and "rotation_used" not in a
              and len(a["placement"]) == 5,
              f'two identical orders give the same {len(a["placement"])} '
              f'placements and the same {a["length_cm"]} cm, while '
              f'a doubled order gives {len(other["placement"])} placements '
              f'and {other["length_cm"]} cm — so the comparison discriminates. '
              f'Handing the sleeve in first lays the identical marker, which '
              f'is what the height sort is for. '
              f'Saying the cloth has no nap gives {napped["length_cm"]} cm, '
              f'the same, and the answer says why rather than flagging a '
              f'rotation it never performs')


# ---------------------------------------------------------------------------
@declares("a BOM names its known lines and its refused lines",
          "the BOM's fabric line is the marker's, not a second calculation",
          "the BOM's thread line depends on the ratio it names")
def the_bom_says_what_to_buy() -> None:
    """**What somebody has to buy, once — and what nobody has told it yet.**

    Fabric is a real number (the marker's). Thread needs a ratio this
    project does not record. Notions and interfacing are not in the pattern
    at all. A BOM that answered by omission — silently leaving out the
    buttons — would read as complete and would not be.
    """
    from photoloset import bom as _bom
    from photoloset import garment_measure as _gm
    from photoloset import garment_pattern as _gp
    from photoloset import marker as _mkr

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0),
                        ("waist", 92.0), ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    draft = _gp.draft(ms)
    CUT = {"後身頃": 1, "前身頃": 2, "袖": 2}

    with guard("a BOM names its known lines and its refused lines"):
        bare = _bom.estimate(draft, 150.0, CUT, 1.5)
        declared = _bom.estimate(draft, 150.0, CUT, 1.5,
                                 notions={"ボタン": 6})
        # Nothing declared: fabric is the only known line, and all three of
        # thread/notions/interfacing are refused BY NAME, not silently
        # dropped. `complete` says so without anybody having to count.
        check("a BOM names its known lines and its refused lines",
              bare["verdict"] == "ANSWER"
              and bare["completeness"]["complete"] is False
              and bare["completeness"]["known_lines"] == ["fabric"]
              and bare["completeness"]["refused_lines"]
              == ["interfacing", "notions", "thread"]
              and bare["refused"]["thread"]["verdict"] == _bom.NO_THREAD_RATIO
              and bare["refused"]["notions"]["verdict"] == _bom.NO_NOTIONS
              and bare["refused"]["interfacing"]["verdict"]
              == _bom.NO_INTERFACING
              # Declare the buttons and ONLY that refusal goes — the other
              # two are untouched, so this is not one switch that clears
              # everything at once.
              and declared["completeness"]["refused_lines"]
              == ["interfacing", "thread"]
              and "notions" in declared["completeness"]["known_lines"]
              and declared["known"]["notions"]["items"] == {"ボタン": 6},
              f'undeclared: known={bare["completeness"]["known_lines"]}, '
              f'refused={bare["completeness"]["refused_lines"]} '
              f'({bare["refused"]["thread"]["verdict"]}, '
              f'{bare["refused"]["notions"]["verdict"]}, '
              f'{bare["refused"]["interfacing"]["verdict"]}); declaring '
              f'6 buttons leaves refused='
              f'{declared["completeness"]["refused_lines"]}')

    with guard("the BOM's fabric line is the marker's, not a second "
              "calculation"):
        one = _bom.estimate(draft, 150.0, CUT, 1.5)
        mk_one = _mkr.lay(draft, 150.0, CUT, 1.5)
        DOUBLE = {k: v * 2 for k, v in CUT.items()}
        twice = _bom.estimate(draft, 150.0, DOUBLE, 1.5)
        mk_twice = _mkr.lay(draft, 150.0, DOUBLE, 1.5)
        # Equal to the marker's OWN output on the same order (not just
        # plausible-looking), and a DIFFERENT order changes both together —
        # otherwise "equal to the marker" could pass with a hard-coded copy
        # of one number. Also carries the marker's nap fields through
        # unchanged, rather than swallowing a freedom marker.py discloses.
        check("the BOM's fabric line is the marker's, not a second "
              "calculation",
              one["known"]["fabric"]["quantity"] == mk_one["length_m"] == 1.966
              and one["known"]["fabric"]["utilisation_pct"]
              == mk_one["utilisation_pct"] == 53.91
              and one["known"]["fabric"]["nap"] == mk_one["nap"]
              and one["known"]["fabric"]["nap_changes_nothing_here"]
              == mk_one["nap_changes_nothing_here"]
              and twice["known"]["fabric"]["quantity"] == mk_twice["length_m"]
              == 3.116
              and twice["known"]["fabric"]["quantity"]
              != one["known"]["fabric"]["quantity"],
              f'one order: BOM {one["known"]["fabric"]["quantity"]} m == '
              f'marker {mk_one["length_m"]} m; doubled: BOM '
              f'{twice["known"]["fabric"]["quantity"]} m == marker '
              f'{mk_twice["length_m"]} m — the two never disagree and the '
              f'doubled order moves both')

    with guard("the BOM's thread line depends on the ratio it names"):
        refused = _bom.estimate(draft, 150.0, CUT, 1.5)
        low = _bom.estimate(draft, 150.0, CUT, 1.5, thread_ratio=2.75)
        high = _bom.estimate(draft, 150.0, CUT, 1.5, thread_ratio=3.0)
        # Two ways this could be a check that cannot fail: the ratio
        # appearing in the output while the answer ignores it, or the
        # refusal not naming the seam length it already has. Both are
        # pinned against measured numbers, not just "is present".
        check("the BOM's thread line depends on the ratio it names",
              refused["refused"]["thread"]["verdict"] == _bom.NO_THREAD_RATIO
              and refused["refused"]["thread"]["seam_length_cm"] == 203.15
              and "thread" not in refused["known"]
              and low["known"]["thread"]["consumption_ratio"] == 2.75
              and low["known"]["thread"]["quantity"] == 5.587
              and high["known"]["thread"]["consumption_ratio"] == 3.0
              and high["known"]["thread"]["quantity"] == 6.095
              and low["known"]["thread"]["quantity"]
              != high["known"]["thread"]["quantity"]
              and "thread" not in low["refused"],
              f'no ratio -> {refused["refused"]["thread"]["verdict"]} naming '
              f'{refused["refused"]["thread"]["seam_length_cm"]} cm of seam; '
              f'ratio 2.75 -> {low["known"]["thread"]["quantity"]} m, ratio '
              f'3.0 -> {high["known"]["thread"]["quantity"]} m — the ratio '
              f'in the output is the ratio that moved the answer')


# ---------------------------------------------------------------------------
def no_check_went_missing() -> None:
    """**The set of checks is itself pinned.** A retirement has to be stated.

    Run last, and it reads what the run actually reported rather than what
    the source looks like it should report. The failure this exists for is
    not a check going red — it is a check DISAPPEARING while the total goes
    up, which is what happened between cbbd045 and 3ed3f3c and was reported
    as "58/58 existing checks still pass".
    """
    ran = list(REPORTED)
    missing = [n for n in ALL_CHECK_NAMES if n not in ran]
    extra = [n for n in ran if n not in ALL_CHECK_NAMES]
    dropped = [n for n, _rev, _why in RETIRED_CHECKS if n in ran]
    check("no check went missing",
          not missing and not extra and not dropped
          and len(ran) == len(ALL_CHECK_NAMES),
          f'{len(ran)} checks ran, {len(ALL_CHECK_NAMES)} pinned by name, '
          f'{len(RETIRED_CHECKS)} retired on the record'
          + (f' — MISSING {missing}' if missing else '')
          + (f' — UNPINNED {extra}' if extra else ''))


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"photoloset checks — python {sys.version.split()[0]}\n")
    for fn in (no_dependencies, the_example_runs, the_pipeline_still_agrees,
               english_is_complete, the_block_lives_on_the_cross,
               the_arms_carry_meaning, the_cross_refuses_what_it_should,
               parts_assemble_a_second_garment,
               prompts_switch_per_model_and_keep_discipline,
               compose_builds_a_whole_garment_from_parts,
               zones_number_the_garment_for_adjustment,
               the_dress_walks_every_stage_past_composition,
               retrieval_asks_per_part,
               the_look_becomes_a_shape,
               the_gate_holds,
               the_loop_decides_when_a_round_ends,
               the_mcp_server_answers,
               served_readers_track_their_stores,
               no_check_can_pass_by_construction,
               numbers_survive_a_revision,
               darts_make_the_panel_three_dimensional,
               pattern_exports_to_a_cad_file,
               the_garment_goes_onto_a_body,
               a_pattern_piece_absorbs_curvature_two_ways,
               the_marker_says_how_much_fabric,
               the_bom_says_what_to_buy,
               the_falsifier_harness_reports_everything,
               no_check_went_missing):
        print(f"{fn.__doc__.splitlines()[0]}")
        # A crash in shared setup must not take the REST OF THE SUITE with
        # it. The named lines inside each function are guarded individually;
        # this catches whatever is left over and reports it as a failure of
        # that function, so the run is never shorter than it looks.
        try:
            fn()
        except Exception as exc:                            # noqa: BLE001
            check(f"{fn.__name__} completes", False,
                  f"CRASHED {type(exc).__name__}: {exc}"[:200])
        print()
    if FAILURES:
        print(f"{len(FAILURES)} failed:")
        for f in FAILURES:
            print(f"  {f}")
        raise SystemExit(1)
    print("all checks passed")
