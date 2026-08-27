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
    "the flat seams come before the ones that close a loop",
    "the number of in-the-round seams is not a choice",
    "the flat store moves into a project once and only once",
    "two projects do not see each other",
    "a project name cannot reach outside the store",
    "the fabric book is shared, the garment is not",
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
    "the DXF declares a text style with a real font",
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
    "64x closes it is a snapshot, not the equilibrium",
    "the worst seam gap is non-increasing as iterations grow",
    "precondition=True changes the answer and stays finite",
    "precondition=True never declares settled early",
    "a fabric without bending is refused, the way weight and "
    "thickness already are",
    "mcp.py's fabric reader requires bending only where it is read",
    "bending is not wired in unless it changes the drape",
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
    "the collar joins the bodice to the cape and the dress still sews shut",
    "the dress has no notches yet, and marks says so honestly",
    "a dress piece keeps its number when a piece is inserted ahead of it",
    "a dart on the dress front closes at the address it sits",
    "the dress mannequin builds now that body_length is measured, and the "
    "garment fits onto it",
    "the dress marker lays eight cut pieces onto real cloth",
    "the dress BOM answers fabric and refuses three lines it cannot know",
    "the dress reaches DXF directly, because save() cannot draft it",
    "the dress has not moved",
    "initialize",
    "80 tools",
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
    "the smooth mannequin keeps the same five levels, and its total "
    "curvature converges near the linear one while its bands settle "
    "far tighter",
    "the monotone spline's four spans stay within their own measured "
    "girths",
    "the base garment is the body surface plus a constant radial "
    "offset",
    "the base garment ends where the body ends instead of "
    "extrapolating past it",
    "flattening a non-developable panel distorts both area and "
    "angle, measured triangle by triangle",
    "the smooth mannequin actually reaches base_garment and flatten "
    "through radius_at, not just curvature",
    "flatten refuses a grid too coarse to triangulate and a "
    "mannequin that never stood up",
    "ease solved from width alone reproduces the base's own silhouette "
    "near zero",
    "a silhouette narrower than the body at any height is refused by "
    "name and shortfall",
    "a silhouette far wider than this offset model can reach is refused "
    "by name and excess",
    "depth moves as a stated byproduct of width-only ease, not as a "
    "second measurement",
    "a degenerate or too-few-point outline is refused, not silently "
    "scanned",
    "an outline whose left and right extents are not equal and opposite "
    "still solves the same ease",
    "silhouette refuses an unbuilt mannequin, too coarse a grid, a "
    "height range outside the body, and an outline that leaves a gap",
    "the matched radius function plugs into base_garment.build without "
    "a second mesh builder",
    "a seam is placed where the flattened tube's distortion is worst, "
    "and buys a measured drop in it",
    "each panel's Gauss-Bonnet total splits into an outline share and "
    "a dart share, and the two sum back to exactly 360 degrees",
    "panels refuse a count that cannot fit the grid and a mannequin "
    "that never stood up",
    "the panel ring sews with exactly one seam in the round",
    "panels differ from the drafted coat in piece count and seam "
    "layout, not by accident",
    "the drafted coat's own doors answer or refuse the panels for a "
    "reason they name",
    "the symmetry axis is measured from the outline, not a hardcoded "
    "constant, and a tilted outline reports a large residual while a "
    "clean one reports zero",
    "the reported armpit height moves with the notch that produces it, "
    "not a fixed constant",
    "the armpit-vs-waist-taper bump-fraction boundary is a measured "
    "value, not assumed",
    "the shoulder search window's upper edge is a measured boundary, "
    "not open-ended",
    "from_outline refuses a missing-contract record, a degenerate "
    "outline, a re-closed outline, a self-crossing outline, and a "
    "non-positive frame by name -- and answers the valid neighbor of "
    "each",
    "the undersampled-outline and too-small-outline refusals fire at "
    "their exact measured boundary, not approximately there",
    "each of the six refused topics answers with its own verdict, not "
    "a shared one, and an unknown topic refuses by a different name "
    "than any of them",
    "a resolved hem always carries the front/back attribution refusal, "
    "and a top-level refusal carries no landmarks at all",
    "the part instances from_outline emits are consumable by "
    "resemble.per_part and resemble.structure_from, run for real",
    "from_outline gives byte-identical output for the same outline "
    "called twice",
    "a known edge reads its stated seam allowance, not a substituted "
    "number",
    "an edge name missing from the table refuses by name, not by 0cm",
    "a refused seam allowance leaves no cut line in the DXF, only the "
    "piece named",
    "the hem's shape is read off the whole bottom boundary, not off "
    "its two ends, and each of level / asymmetric_left_right / "
    "uneven is reachable from an outline that earns it",
    "no falsifier is defined below the line where the harness "
    "starts running, because one defined there is silently skipped",
    "the photograph sets the garment's shape and the tape sets "
    "only its scale, and the tape reaches the scale through the "
    "shoulder alone",
    "every falsifier's anchor still exists in the file it "
    "targets, so a refactor cannot disarm a mutation silently",
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
    ("the dress mannequin refuses the measure set the dress actually has",
     "collar-dress-full",
     "It pinned mannequin.build() refusing UNKNOWN_MISSING_MEASUREMENTS "
     "on the dress's measure set, because that set never carried "
     "body_length (only bodice_length + skirt_length). This task adds "
     "body_length as the dress's real ninth tape measurement, so the "
     "refusal is no longer what happens — its replacement, \"the dress "
     "mannequin builds now that body_length is measured, and the garment "
     "fits onto it\", walks build/align/dress/clearance on the composed, "
     "collared dress instead of stopping at the gate."),
    ("the dress marker lays seven cut pieces onto real cloth",
     "collar-dress-full",
     "Renamed, not dropped: the dress in this suite now carries a fifth "
     "part (衿/collar, between the bodice's neckline and the cape), so "
     "the same CUT dict now sums to eight pieces laid, not seven. Its "
     "replacement, \"the dress marker lays eight cut pieces onto real "
     "cloth\", is the identical check with the collar's count included."),
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
    import math
    from photoloset import Measures
    from photoloset import garment_drape, garment_marks, garment_pattern, garment_sew

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

    # **"64x closes it" is a snapshot, not the equilibrium.** Diagnosed
    # 2026-08-27: raising the iteration cap does not shrink the worst gap
    # further — it GROWS, because the 2000-iteration number sits in an
    # early, local "nearby points snap together fast" dip, before the
    # slow, whole-coat gravity settling that follows pulls the worst pair
    # apart again. Measured off-tree, well past this check's time budget:
    # left running to a true fixed point (positions stop moving to 4
    # decimals), 16x plateaus at 3.39 cm and 64x at 0.85 cm — NEITHER
    # closes under the 0.1 cm tolerance. Here, cheaply, is the direction
    # of that trend on the real coat: more iterations of the SAME,
    # unmodified solver make the "64x closes it" number worse, not better.
    longer = garment_sew.sew_and_drape(built, mat, iterations=8000,
                                       stitch_k=20.0 * 64)["seam_gap"]
    check("64x closes it is a snapshot, not the equilibrium",
          longer["worst"] > tight["worst"]
          and round(longer["worst"], 4) == 0.231,
          f'worst grew from {tight["worst"]} cm at 2000 iterations to '
          f'{longer["worst"]} cm at 8000 — rising, not settling, on the '
          f'unmodified solver')

    # **The residual does converge — the coat is just too large a mesh to
    # reach its fixed point inside a check's time budget.** The root cause
    # of the earlier growth: a stitched vertex is touched by many springs
    # at once (up to 8 cloth edges plus one or two stitches at 16x cloth
    # stiffness), and settling has to propagate from every free-hanging
    # vertex back to the two pins one edge per iteration — a diffusive
    # process whose iteration count scales with how many such hops the
    # mesh has. Measured off-tree, past this check's time budget: the full
    # coat (303 points) does reach a true fixed point, but only after
    # ~300000 iterations for 64x (worst plateaus at 0.85 cm) or ~900000 for
    # 1000x (0.05 cm — the first multiplier tried that actually closes
    # under 0.1 cm at true convergence; 16x, 64x and 100x all plateau
    # above tolerance). A coarser cut of the SAME pattern (cell=20cm
    # instead of the default 6cm) has far fewer hops and reaches its fixed
    # point inside a check that has to run promptly, on the SAME,
    # completely unmodified solver — proving the convergence itself, not
    # just the slowdown, is real:
    coarse = garment_sew.build(draft, cell=20.0, marks=marks)
    coarse_curve = [
        garment_sew.sew_and_drape(coarse, mat, iterations=n,
                                  stitch_k=20.0 * 64)["seam_gap"]["worst"]
        for n in (400, 1600, 6400)]
    check("the worst seam gap is non-increasing as iterations grow",
          coarse_curve[0] >= coarse_curve[1] >= coarse_curve[2]
          and coarse_curve == [0.0243, 0.0238, 0.0238]
          and len(coarse["points"]) == 58,
          f'worst gap at 400 / 1600 / 6400 iterations: {coarse_curve} cm '
          f'({len(coarse["points"])} points, coarsened so this check '
          f'finishes) — flat by 1600 and still flat at 100000, separately '
          f'measured off-tree')

    # **`precondition=True` (this pass) is wired in, not decoration.** It
    # sizes the step per vertex from that vertex's own total incident
    # stiffness instead of the single global worst case. It pushes the
    # worst seam gap under tolerance far sooner than the unmodified solver
    # does within any budget tested here (see `garment_sew.sew_and_drape`'s
    # own docstring for the full, corrected account — an earlier claim here
    # that this reaches "the same 0.85cm fixed point ~3-4x faster" did not
    # hold up under measurement and has been retracted, not merely because
    # of the ~80000-iteration number but because that low reading is itself
    # a transient trough, not a settled value). At only 400 iterations the
    # bigger per-vertex step for lightly-connected vertices has not settled
    # yet, so preconditioned is WORSE here, not better — which is exactly
    # why it has to be opt-in (the coat digest is pinned to the
    # unpreconditioned number at 2000 iterations). This check is only that
    # the flag is actually read: it changes the answer, and the answer
    # stays finite.
    precond = garment_sew.sew_and_drape(coarse, mat, iterations=400,
                                        stitch_k=20.0 * 64,
                                        precondition=True)
    check("precondition=True changes the answer and stays finite",
          len(precond["points"]) == 58
          and all(math.isfinite(c) for p in precond["points"] for c in p)
          and precond["seam_gap"]["worst"] == 24.2118
          and coarse_curve[0] == 0.0243,
          f'preconditioned worst at 400 iterations '
          f'{precond["seam_gap"]["worst"]} cm over '
          f'{len(precond["points"])} finite points vs unpreconditioned '
          f'{coarse_curve[0]} cm — different, and every coordinate finite')

    # **`precondition=True` must never self-declare "settled" early.**
    # 2026-08-27 実測で見つかった欠陥(``garment_sew.sew_and_drape`` の
    # docstring 参照): worst seam gap は有限個の対の最大値という滑らか
    # でない統計量で、その時点の最大を持つ対がたまたま静かでも他の場所は
    # まだ動いている——だから前処理ありのときは「50反復窓で動いていない」
    # を根拠にした早期打ち切りをそもそも使わない。ここでは対照実験で
    # それを直接示す:同じ coat の粗いメッシュ(cell=20)を、前処理なし
    # なら確実に早期停止する反復上限(100000。既に 550 反復・0.0238cm
    # で静定すると上の検査が言っている)で解いても前処理ありは全部使い
    # 切ることを見る。前処理なしは早期停止できるからこそ意味のある
    # 対照——両方が単に反復上限まで走るだけでは、この検査は「前処理あり
    # だけ早期停止しない」ことを何も確かめない。
    uncond_early = garment_sew.sew_and_drape(coarse, mat, iterations=100000,
                                              stitch_k=20.0 * 64)
    precond_full = garment_sew.sew_and_drape(coarse, mat, iterations=60000,
                                              stitch_k=20.0 * 64,
                                              precondition=True)
    check("precondition=True never declares settled early",
          uncond_early["iterations"] < 100000
          and uncond_early["seams_settled"]
          and precond_full["iterations"] == 60000
          and not precond_full["seams_settled"]
          and precond_full["seam_gap"]["worst"] <= 0.1,
          f'unpreconditioned: {uncond_early["iterations"]}/100000 used, '
          f'settled={uncond_early["seams_settled"]} (stops early once '
          f'quiet); preconditioned: {precond_full["iterations"]}/60000 '
          f'used, settled={precond_full["seams_settled"]}, worst '
          f'{precond_full["seam_gap"]["worst"]}cm (already under the '
          f'0.1cm tolerance, yet still runs the full budget rather than '
          f'trusting that the same worst-gap window means it is done)')

    # **Bending is required the way weight and thickness already are.**
    # Test both directions — a stub that refuses every fabric would pass a
    # one-sided version of this. `fabrics.number` is the only method
    # `material_from` calls, so a two-line stub is the whole double.
    class _FabricsStub:
        def __init__(self, table):
            self.table = table

        def number(self, fabric, key):
            return self.table.get(fabric, {}).get(key)

    no_bend = garment_drape.material_from(
        _FabricsStub({"melton": {"weight": 420.0, "thickness": 0.18}}),
        "melton")
    has_bend = garment_drape.material_from(
        _FabricsStub({"melton": {"weight": 420.0, "thickness": 0.18,
                                 "bending": 40.0}}), "melton")
    check("a fabric without bending is refused, the way weight and "
          "thickness already are",
          no_bend["verdict"] == garment_drape.NO_MATERIAL
          and no_bend["missing"] == ["bending"]
          and has_bend["verdict"] == "ANSWER"
          and has_bend["bending"] == 40.0,
          f'missing only bending -> {no_bend["verdict"]} naming '
          f'{no_bend.get("missing")}; all three present -> '
          f'{has_bend["verdict"]} bending={has_bend.get("bending")}')

    # **`mcp.py._fabric` requires `bending` only for the tools that read
    # it.** It has its own, separate fabric-table reader (does not call
    # `garment_drape.material_from` above) — 2026-08-27, an outside check
    # found an earlier version of this pass made it require `bending`
    # unconditionally, which meant `drape_validate` (whose call chain
    # never reads `bending` — confirmed by reading `garment_drape.validate`
    # -> `solve`) refused a fabric ledger entry it used to answer for, over
    # a field with zero effect on what that tool computes. Scoped with a
    # `require_bending` keyword instead: True (default) for `sew_and_drape`
    # and the internal `_fallen` used elsewhere, False for `drape_validate`.
    import importlib as _importlib
    import os as _os_mcp
    import tempfile as _tf_mcp

    mcp_home = Path(_tf_mcp.mkdtemp(prefix="fabricscope_"))
    old_home = _os_mcp.environ.get("HOME")
    # `projects_have_their_own_store` と同じ理由で PHOTOLOSET_HOME も外す
    # — mcp.HOME はそちらを先に見るので、環境に立っていると HOME の
    # 差し替えが効かない。
    old_ph_mcp = _os_mcp.environ.pop("PHOTOLOSET_HOME", None)
    _os_mcp.environ["HOME"] = str(mcp_home)
    try:
        import photoloset.mcp as _mcp
        _importlib.reload(_mcp)
        flat = mcp_home / ".photoloset"
        flat.mkdir(parents=True)
        Measures().save(flat / "measures.json")
        (flat / "fabrics.json").write_text(
            json.dumps({"nobend": {"gsm": 300.0, "thickness": 0.1,
                                   "stiffness": 12.0}}), encoding="utf-8")
        drape_no_bend = json.loads(
            _mcp.TOOLS["drape_validate"](fabric="nobend", iterations=20))
        sew_no_bend = json.loads(
            _mcp.TOOLS["sew_and_drape"](fabric="nobend"))
    finally:
        if old_home is None:
            _os_mcp.environ.pop("HOME", None)
        else:
            _os_mcp.environ["HOME"] = old_home
        if old_ph_mcp is not None:
            _os_mcp.environ["PHOTOLOSET_HOME"] = old_ph_mcp
    check("mcp.py's fabric reader requires bending only where it is read",
          drape_no_bend.get("verdict") != "UNKNOWN_NO_MATERIAL"
          and sew_no_bend.get("verdict") == "UNKNOWN_NO_MATERIAL"
          and sew_no_bend.get("missing") == ["bending"],
          f'fabric missing only "bending": drape_validate -> '
          f'{drape_no_bend.get("verdict")} (must not refuse — that path '
          f'never reads bending); sew_and_drape -> '
          f'{sew_no_bend.get("verdict")} naming {sew_no_bend.get("missing")} '
          f'(must refuse — that path does read it)')

    # **Two fabrics differing only in bending must drape measurably
    # differently, or bending is not wired in.** A separate, smaller cut
    # (cell=12) of the same pattern, three otherwise-identical materials
    # (gsm 200, thickness 0.08, stiffness 10 — a floppy jersey-weight base)
    # that vary only `bending`, same iteration count, same stitch_k. The
    # metric is the drape's own vertical spread (top to bottom): a fabric
    # that resists folding sags less under its own weight, monotonically.
    bend_built = garment_sew.build(draft, cell=12.0, marks=marks)
    jersey_mat = {"verdict": "ANSWER", "fabric": "jersey", "gsm": 200.0,
                  "thickness": 0.08, "stiffness": 10.0}

    def _y_range(bending):
        m = dict(jersey_mat)
        if bending is not None:
            m["bending"] = bending
        pts = garment_sew.sew_and_drape(bend_built, m, iterations=1500,
                                        stitch_k=10.0 * 16)["points"]
        ys = [p[1] for p in pts]
        return round(max(ys) - min(ys), 2)

    y_none, y_zero, y_low, y_high = (_y_range(None), _y_range(0.0),
                                     _y_range(5.0), _y_range(200.0))
    check("bending is not wired in unless it changes the drape",
          y_none == y_zero  # material.get("bending") is None: same as 0.0
          and y_zero > y_low > y_high  # stiffer fabric sags less, monotone
          and (y_none, y_low, y_high) == (164.07, 156.8, 112.46),
          f'vertical spread with no bending / bending=0 / bending=5 / '
          f'bending=200: {y_none} / {y_zero} / {y_low} / {y_high} cm — '
          f'falling as bending rises, no-op when absent')

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
    # **PHOTOLOSET_HOME も落とす。** 子プロセスの mcp.HOME は
    # PHOTOLOSET_HOME を先に見るので、これを渡したままだと HOME を
    # 差し替えても店が動かない — 「自分の HOME に書いた」を確かめる
    # この検査自身が、外から渡された隔離に壊される。
    env = dict(os.environ, HOME=home)
    env.pop("PHOTOLOSET_HOME", None)
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
        check("80 tools", len(tools) == 80, f"{len(tools)}")
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
              len(tools) == 80 and not no_schema and not no_props
              and len(published) == 152 and not wrong and not contradicted
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
              len(tools) == 80 and not not_object and not crashed,
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
          len(scanned) == 44 and not third_party,
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
          and len(a.get("known", [])) == 5,
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
@declares("the collar joins the bodice to the cape and the dress still "
          "sews shut",
          "the dress has no notches yet, and marks says so honestly",
          "a dress piece keeps its number when a piece is inserted ahead of it",
          "a dart on the dress front closes at the address it sits",
          "the dress mannequin builds now that body_length is measured, "
          "and the garment fits onto it",
          "the dress marker lays eight cut pieces onto real cloth",
          "the dress BOM answers fabric and refuses three lines it cannot know",
          "the dress reaches DXF directly, because save() cannot draft it",
          "the dress has not moved")
def the_dress_walks_every_stage_past_composition() -> None:
    """**The second garment, past the point ``compose_builds_a_whole_garment_from_parts``
    already reaches — now with a collar, all the way to the mannequin.**

    That check (above) already proves compose -> marks -> ``garment_sew.build``
    -> ``sew_and_drape`` closes for the 4-part cape dress (no collar). This
    one adds the fifth part — ``collar:1``, sitting between the bodice's
    neck and the cape (bodice ↔ collar/neck, collar/collar_edge ↔ cape) —
    and walks every stage past composition: stable numbering, a dart, the
    mannequin (build, align, dress, clearance — not just the refusal the
    measure set used to stop at), the marker, the BOM, and the DXF export —
    each called directly on the SAME composed draft, no new geometry
    invented beyond ``garment_parts.draft_collar``. Where a stage still
    refuses, the refusal is pinned as the answer, not routed around.

    ``collar`` used to be undraftable (``UNKNOWN_PART_NOT_DRAFTABLE``) — the
    fact this suite is now built against is that it drafts. Registering it
    took one procedure in ``garment_parts.py`` and three lines in
    ``parts.py`` (``PART_GEOMETRY``, ``PART_MEASURES``, one new port
    ``collar_edge``) — no branch in ``compose.py``. ``closure`` and
    ``waist_finish`` remain undraftable (their opening allowance and gather
    take-up are not designed yet); ``decoration`` was never going to get a
    procedure — the vocabulary says up front it does not enter the pattern
    geometry.

    The measure set also grows by one real spot: ``body_length``. The
    dress's own measures (``bodice_length`` + ``skirt_length``) are panel
    lengths, not the torso length ``mannequin.build()`` needs — so this is
    an actual ninth tape measurement, not a default standing in for one.

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
                        ("neck", 21.0), ("cape_length", 28.0),
                        ("body_length", 90.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")
    dress = {
        "parts": [
            {"instance": "bodice:1", "part": "bodice"},
            {"instance": "skirt:1", "part": "skirt_panel",
             "params": {"hi_lo_drop": 22.0}},
            {"instance": "sleeve:1", "part": "sleeve",
             "params": {"side": "左"}},
            {"instance": "cape:1", "part": "cape"},
            # **Appended, not inserted.** Keeping the first four instances
            # in their original order keeps every stable-number pin below
            # unmoved — the numbering test right after this composes the
            # same point that the earlier plain cape dress compat with,
            # then separately proves a piece inserted AHEAD does not move
            # it. Putting collar ahead of cape here would be testing the
            # same thing this file already tests elsewhere, at the cost of
            # every downstream pinned address moving for no reason.
            {"instance": "collar:1", "part": "collar"}],
        "connections": [
            {"a": ["bodice:1", "waist"], "b": ["skirt:1", "waist"]},
            {"a": ["bodice:1", "armhole_l"],
             "b": ["sleeve:1", "armhole_l"]},
            # The collar sits between the bodice and the cape — not a
            # fourth thing fighting bodice:1/neck for the same port. The
            # bodice's neckline goes to the collar's inner edge; the
            # cape now mounts on the collar's OUTER edge (port
            # collar_edge), the real construction order for a caped
            # collar (cape sewn onto the collar's roll line, not
            # straight onto the body's neckline).
            {"a": ["bodice:1", "neck"], "b": ["collar:1", "neck"]},
            {"a": ["collar:1", "collar_edge"], "b": ["cape:1", "neck"]}],
        "port_finish": {
            "cape:1": {"hem": "free", "center_front": "fold",
                       "center_back": "fold"},
            "skirt:1": {"hem": "free", "center_front": "fold",
                        "center_back": "fold"},
            "bodice:1": {"center_front": "fold", "center_back": "fold"},
            "sleeve:1": {"cuff_l": "free"},
            "collar:1": {"center_front": "fold", "center_back": "fold"}},
        "label": "ケープワンピース",
    }
    r = compose.compose(dress, ms)
    m = garment_marks.apply(r)

    with guard("the collar joins the bodice to the cape and the dress "
               "still sews shut"):
        # `collar` used to answer UNKNOWN_PART_NOT_DRAFTABLE the moment it
        # appeared in a parts list — this is the same gate
        # `compose_builds_a_whole_garment_from_parts` proves for the
        # collar-less dress, now with the fifth part in. Two NEW seam
        # checks pair (neck: bodice ↔ collar, and collar_edge: collar ↔
        # cape) on top of the original ten, and none of the twelve is over
        # tolerance — the collar's own radius/height defaults
        # (``garment_parts.COLLAR_SECTOR``/``COLLAR_HEIGHT``) were picked
        # so the seam it hands the cape is close enough to the cape's own
        # (independently measured) neckline to sew, not so a check would
        # pass by construction: the same 6.0cm height this file used to
        # carry left that seam 7.9cm apart (5.9cm over the 2.0cm tolerance), measured
        # before this value was lowered.
        seam_checks = r.get("seam_checks", [])
        bad = [c for c in seam_checks if not c["sewable"]]
        new_labels = sorted({c["label"].split(" (", 1)[0] for c in
                             seam_checks if c["label"].startswith(
                                 ("neck: bodice:1 ↔ collar:1",
                                  "collar_edge: collar:1 ↔ cape:1"))})
        built = garment_sew.build(r, marks=m)
        mat = {"verdict": "ANSWER", "fabric": "wool melton", "gsm": 420.0,
               "thickness": 0.18, "stiffness": 20.0}
        gap = garment_sew.sew_and_drape(built, mat, iterations=6000,
                                        stitch_k=20.0 * 128)["seam_gap"]
        # 衿は compose.PLACEMENT_TEMPLATE に明示の初期位置を持つこと —
        # 無ければ `placement_map.get(name, (0.0,0.0,0.0))` の無言既定に
        # 落ちる(数値としては同じ (0.0,0.0,0.0) だが、意図して選んだ値と
        # 無言の既定は別物 — このプロジェクトの規律そのもの)。
        collar_placed = "衿" in compose.PLACEMENT_TEMPLATE
        check("the collar joins the bodice to the cape and the dress "
              "still sews shut",
              r["verdict"] == "ANSWER" and len(r["pieces"]) == 7
              and "衿" in [p["name"] for p in r["pieces"]]
              and len(seam_checks) == 12 and not bad
              and new_labels == ["collar_edge: collar:1 ↔ cape:1",
                                 "neck: bodice:1 ↔ collar:1"]
              and gap["closed"] and gap["over_tolerance"] == 0
              and round(gap["worst"], 4) == 0.0699
              and gap["stitches"] == 50
              and collar_placed,
              f'{len(r["pieces"])} pieces (was 6 before the collar), '
              f'{len(seam_checks)} seam checks ({len(bad)} not sewable), '
              f'collar placement explicit: {collar_placed}, '
              f'sews shut at worst {gap["worst"]} cm over '
              f'{gap["stitches"]} stitches (was 45 for the 6-piece dress)')

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
        sa_refused = {name: sa[name]["verdict"] for name in sa
                      if sa[name].get("verdict") != "ANSWER"}
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
              # **7 のうち 6。** 衿だけが断る — 「衿の外周 (前)」
              # 「衿の外周 (後)」の幅を述べた者がいないため。以前は
              # SEAM_ALLOWANCE に無い辺名が黙って 0.0cm に落ちていて、
              # 7/7 が ANSWER に見えていた。裁ち切り線が出来上がり線と
              # 同じ位置に引かれた型紙が通っていたということで、
              # **数が減ったのは退行ではなく、嘘が一つ消えたということ。**
              # 断り自体は `sa_refused` で名指しで押さえる — 「6 個通った」
              # だけなら、どれが落ちても緑のままになってしまう。
              and len(sa_ok) == 6 and len(sa) == 7
              and sa_refused == {"衿": "UNKNOWN_SEAM_ALLOWANCE_NOT_STATED"}
              and grain_pieces == {p["name"] for p in r["pieces"]}
              and coat_angle == dress_angle == 90.0,
              f'0 notches across {len(sa)} pieces (notch_plan is an empty '
              f'declared list, not a missing one — the coat-only heuristic '
              f'never runs); {len(sa_ok)} seam allowances answer and '
              f'{sorted(sa_refused)} refuses by name; grain '
              f'lines on all {len(grain_pieces)} pieces, drawn at '
              f'{coat_angle}° read off the COAT\'s store — equal to the '
              f'dress\'s own declared {dress_angle}° today by coincidence, '
              f'not because anything reads the dress\'s value')

    reg = _pt.Registry()
    _pt.label(r, reg)
    with guard("a dress piece keeps its number when a piece is inserted "
               "ahead of it"):
        watch = [("後身頃", "e0", 0.0), ("スカート前", "e2", 0.5),
                 ("ケープ", "e10", 0.3), ("衿", "e0", 0.3)]
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
              before == [600, 1450, 3730, 7730] and after == before
              and where["piece"] == "後身頃" and where["edge"] == "e0"
              and where["number"] == 600,
              f'{watch} -> {before}, unchanged at {after} after a piece is '
              f'inserted at the front of a 7-piece dress (the coat\'s own '
              f'version of this check inserts at index 1; this one inserts '
              f'at index 0, the harder position). 衿/e0 at 7730 is the '
              f'collar\'s own address, appended after the original six '
              f'without moving any of them')

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

    # **A finding, not a routing-around.** dxf.save() still cannot draft
    # the composed dress — it internally re-drafts from
    # `garment_pattern.draft(measures)`, the COAT's fixed 3-piece shape,
    # never reading a parts graph. Before body_length was added, that was
    # invisible behind a shared refusal: both the dress's mannequin AND
    # the coat's draft were missing the same spot, so save() answered
    # UNKNOWN_MISSING_MEASUREMENTS and looked like it was refusing to
    # touch the dress specifically. It was not — it was refusing for its
    # OWN reason, on its OWN garment. body_length is also one of the
    # coat's four required spots (chest, shoulder, sleeve_length,
    # body_length — all already in this measure set), so now that it is
    # present, save() answers ANSWER: it silently drafts and writes the
    # COAT's 前身頃/後身頃/袖, not the dress's seven pieces, to a file named
    # "dress.dxf". That is measured below rather than assumed, and it is
    # exactly the "wrong garment gets the approval" failure this codebase
    # otherwise goes to some lengths to refuse — save() just never learned
    # to ask which garment. `dxf.to_dxf()` on the already-marked dress
    # draft (the next check) is the only door that reaches this garment.
    import tempfile as _tempfile
    from pathlib import Path as _Path
    with guard("the dress mannequin builds now that body_length is "
               "measured, and the garment fits onto it"):
        # This used to be the refusal the brief named ahead of time:
        # mannequin.build() needs chest/waist/hip/body_length, and the
        # dress's own measures (bodice_length + skirt_length) never
        # supplied it. body_length above is the real ninth tape
        # measurement that closes that gap — not a default standing in
        # for one. What follows is the same build/align/dress/clearance
        # walk `the_garment_goes_onto_a_body` proves for the coat, run
        # here on the composed, collared dress's own draped points.
        man = _mq.build(ms)
        with _tempfile.TemporaryDirectory() as _tmp:
            saved = _dxf.save(ms, str(_Path(_tmp) / "dress.dxf"))
        built = garment_sew.build(r, marks=m)
        mat = {"verdict": "ANSWER", "fabric": "wool melton", "gsm": 420.0,
               "thickness": 0.18, "stiffness": 20.0}
        fell = garment_sew.sew_and_drape(built, mat, iterations=6000,
                                         stitch_k=20.0 * 128)["points"]
        al = _mq.align(man, fell)
        worn = _mq.dress(man, fell)
        c_fell = _mq.clearance(man, fell)
        c_worn = _mq.clearance(man, worn["points"])
        total = (c_fell["inside_the_body"] + c_fell["clinging"]
                 + c_fell["apart"] + c_fell["no_body_at_that_height"])
        # dxf.save() writes the COAT — measured, not assumed: 3 pieces,
        # named 前身頃/後身頃/袖. Two of those three names are NOT
        # distinguishing — draft_bodice() (this dress's own bodice
        # procedure) happens to name its front/back pieces 前身頃/後身頃
        # too, so a caller who only checked "does the output mention
        # 前身頃" would see a false match. What IS distinguishing: the
        # coat's single sleeve piece is named plain "袖", never "袖(左)"
        # the way this dress's own sleeve is (draft_sleeve() puts the
        # side into the name), and the coat has 3 pieces where this dress
        # has 7. It answers ANSWER, not a refusal — see the comment above
        # the guard for why that is a finding, not a pass.
        saved_names = set(saved.get("placement", []))
        dress_names = {p["name"] for p in r["pieces"]}
        check("the dress mannequin builds now that body_length is "
              "measured, and the garment fits onto it",
              man["verdict"] == "ANSWER" and man["vertices"] == 408
              and len(man["faces"]) == 384
              and saved["verdict"] == "ANSWER" and len(saved["pieces"]) == 3
              and saved_names == {"前身頃", "後身頃", "袖"}
              and "袖" in saved_names and "袖(左)" not in saved_names
              and len(dress_names) == 7 and "袖(左)" in dress_names
              and round(al["rule"]["dy_cm"], 4) == 38.8742
              and round(al["rule"]["dx_cm"], 4) == -20.4661
              and worn["verdict"] == "ANSWER"
              and worn["points_below_the_form"] == 163
              and worn["min_clearance_cm"] == 1.0
              and total == c_fell["points"] == len(fell) == 291
              and c_fell["inside_the_body"] == 44
              and c_worn["inside_the_body"] == 0
              and round(c_fell["min_clearance_cm"], 4) == -8.9678
              and round(c_worn["min_clearance_cm"], 4) == 0.9999,
              f'mannequin {man["vertices"]}v/{len(man["faces"])}f; the '
              f'{len(fell)}-point draped dress moved onto it by dy '
              f'{al["rule"]["dy_cm"]}, dx {al["rule"]["dx_cm"]}; as it fell, '
              f'{c_fell["inside_the_body"]} of {len(fell)} points sit '
              f'inside the form (min clearance '
              f'{c_fell["min_clearance_cm"]} cm); dressed (pushed to '
              f'surface + gap), 0 do (min clearance '
              f'{c_worn["min_clearance_cm"]} cm, the gap by construction); '
              f'dxf.save() over the SAME measures now silently answers '
              f'{saved["verdict"]} writing {len(saved["pieces"])} pieces '
              f'named {sorted(saved_names)} — the COAT (this {len(dress_names)}'
              f'-piece dress\'s own sleeve is "袖(左)", never plain "袖") — '
              f'because body_length happens to complete the coat\'s own '
              f'required set too. save() cannot tell these two garments '
              f'apart; only to_dxf() on this garment\'s own marked draft '
              f'(next check) can')

    CUT = {"前身頃": 1, "後身頃": 1, "スカート前": 1, "スカート後": 1,
           "袖(左)": 2, "ケープ": 1, "衿": 1}
    with guard("the dress marker lays eight cut pieces onto real cloth"):
        no_count = _mkr.lay(r, 150.0, {}, 1.5)
        good = _mkr.lay(r, 150.0, CUT, 1.5)
        check("the dress marker lays eight cut pieces onto real cloth",
              no_count["verdict"] == _mkr.NO_COUNT
              and sorted(no_count["pieces"]) == sorted(p["name"]
                                                        for p in r["pieces"])
              and good["verdict"] == "ANSWER"
              and good["pieces_laid"] == 8 == sum(CUT.values())
              and round(good["length_cm"], 1) == 130.2
              and round(good["utilisation_pct"], 2) == 63.34,
              f'no counts -> {no_count["verdict"]} naming all '
              f'{len(no_count["pieces"])} pieces; 8 copies (袖(左) cut '
              f'twice, mirrored, the rest — now including 衿 — cut on the '
              f'fold declared in port_finish) need {good["length_cm"]} cm '
              f'at {good["utilisation_pct"]}% utilisation (up from 62.26% '
              f'over the same {good["length_cm"]} cm before the collar — '
              f'the small extra piece fit inside the length already spent, '
              f'it did not need more of it)')

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
              out["verdict"] == "ANSWER" and len(out["pieces"]) == 7
              and names == expected_names
              # **衿だけ裁ち切り線が無い。** 「衿の外周 (前)」「衿の外周
              # (後)」の縫い代を誰も述べていないので garment_marks が断り、
              # dxf は出来上がり線だけを書いて裁ち切り線を書かない。
              # 以前は述べられていない辺が黙って 0.0cm になり、裁ち切り線が
              # 出来上がり線にぴたりと重なった図が 7/7 で出ていた。
              # **裁てば縫い代ゼロの衿になる図が ANSWER で通っていた。**
              # ここを [] ではなく ["衿"] で押さえるのは、空リストだと
              # 「全部に裁ち切り線がある」と「そもそも書いていない」の
              # 区別が付かないから。
              and out["cut_line_missing"] == [
                  {"piece": "衿",
                   "verdict": "UNKNOWN_SEAM_ALLOWANCE_NOT_STATED"}]
              and sum(out["notch_lines"].values()) == 0
              and out["extents_cm"]["min"] == [10.0, -37.1]
              # x の右端が 286.026 から 285.865cm へ 0.161cm 縮んだ。
              # 消えたのは衿の裁ち切り線で、0cm でも角の面取りの分だけ
              # 出来上がり線の外に出ていた。
              and out["extents_cm"]["max"] == [285.865, 69.682],
              f'{len(out["pieces"])} pieces {names} written straight from '
              f'garment_marks.apply() output (to_dxf(), not save() — '
              f'save() re-drafts from garment_pattern.draft internally and '
              f'cannot see a composed garment at all); extents '
              f'{out["extents_cm"]["min"]} .. {out["extents_cm"]["max"]} cm, '
              f'no cut line for '
              f'{[m["piece"] for m in out["cut_line_missing"]]} '
              f'(its allowance is unstated, not zero); '
              f'0 notch lines matching the 0 notches marks produced')

    # **THE DRESS MUST NOT MOVE EITHER — as a number anyone can recompute.**
    # The same discipline tests/coat_digest.py exists for, applied to the
    # second garment: the generator is in the tree (tests/dress_digest.py,
    # not a script in someone's scratch directory), it canonicalises floats
    # to their exact IEEE-754 bit patterns, and the suite runs it — over
    # compose, marks, the built mesh and seams, both drape passes, the
    # mannequin (build/align/dress/clearance), the marker, the BOM, the DXF
    # export and the SVG, none of which tests/coat_digest.py's own digest
    # touches (that script only ever drafts the coat).
    sys.path.insert(0, str(ROOT / "tests"))
    import dress_digest
    dd = dress_digest.digests()
    check("the dress has not moved",
          dd["geometry"] == dress_digest.GEOMETRY_DIGEST
          and not dd["errors"]
          and dress_digest.GEOMETRY_DIGEST
          == "4c1dabf60bfafa549f9084d9828b2871"
          and len(dress_digest.GEOMETRY) == 16,
          f'geometry {dd["geometry"]} over {len(dress_digest.GEOMETRY)} '
          f'sections, recomputable by anyone with '
          f'`python3 tests/dress_digest.py --check`')


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
        # `collar` used to be the standing example of an undraftable part
        # here. It drafts now (garment_parts.draft_collar,
        # parts.PART_GEOMETRY) — `closure` takes its place: still in
        # PART_VOCAB, still with no procedure (the opening allowance and
        # its seam treatment are not designed yet), so this check keeps
        # testing what it always tested — a part inside the vocabulary but
        # without a drafting procedure — rather than one that happens not
        # to draft today.
        mixed = dict(good)
        mixed["instances"] = list(good["instances"]) + [
            {"instance": "closure:1", "part": "closure", "params": {}},
            {"instance": "mantle:1", "part": "mantle", "params": {}}]
        m = compose.graph_from(mixed)
        check("a retrieved family with no procedure refuses the whole "
              "construction",
              m["verdict"] == compose.NO_PART
              and m["undraftable"] == ["closure"]
              and m["unknown"] == ["mantle"]
              and "graph" not in m
              and "PART_GEOMETRY" in m["how_to_close"]
              and m["known"] == ["bodice", "cape", "collar", "skirt_panel",
                                 "sleeve"],
              f'{m["verdict"]} naming every offender — {m["unknown"]} outside '
              f'the vocabulary and {m["undraftable"]} inside it with no '
              f'procedure — and no graph at all. A garment silently missing '
              f'its cape collects approval for the wrong garment')

    with guard("the constructed graph names every part the retrieval named"):
        mixed = dict(good)
        mixed["instances"] = list(good["instances"]) + [
            {"instance": "closure:1", "part": "closure", "params": {}}]
        m = compose.graph_from(mixed)
        check("the constructed graph names every part the retrieval named",
              g["verdict"] == "ANSWER"
              and sorted(i["part"] for i in g["graph"]["parts"])
              == sorted(i["part"] for i in good["instances"])
              and len(g["graph"]["parts"]) == 4
              and m.get("graph") is None
              and m["asked_for"] == ["bodice", "cape", "closure",
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
        # `collar` drafts now (garment_parts.draft_collar) — `closure`
        # still does not, so it is the one that still reaches
        # UNKNOWN_PART_NOT_DRAFTABLE here.
        undraftable = compose.compose(
            {"parts": [{"instance": "closure:1", "part": "closure"}]}, ms)
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
    ("T1", "the flat store moves into a project once and only once",
     "borderline",
     "`again == moved` compares two lists, which is the T1 shape, and an "
     "idempotence test cannot avoid it — the property IS that a second run "
     "changes nothing. They are read at different times with a second "
     "migration call and a stray file between them, and the clauses beside "
     "them pin what must hold either way. Falsifier: 'the migration guard "
     "stops looking at whether projects/ exists', which sweeps the stray "
     "json into the project and makes them differ."),
    ("T3", "two projects do not see each other", "real",
     "The tool reads the check NAME as quantifying over 'other' and cannot "
     "find an identifier of that name in the condition. The condition does "
     "quantify — it walks every project and requires `leaked` (any project "
     "holding a spot written into another) to be empty. The heuristic "
     "matches on identifiers, not on the loop. Measured: "
     "{'cape': ['waist'], 'default': ['chest']}, 0 leaked. One shared "
     "directory shows both spots in both, which is what the flat store did "
     "and what the falsifier restores."),
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
     "`len(sa_ok) == 7 == len(sa)`, pinned against the marks pipeline "
     "actually running seam-allowance offsets on all seven pieces (the "
     "collar included), and the falsifier 'marks stop computing seam "
     "allowances' turns exactly that clause — and this check — red by "
     "breaking the offset step, without touching notch_plan at all."),
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
    ("T3", "each of the six refused topics answers with its own verdict, "
     "not a shared one, and an unknown topic refuses by a different name "
     "than any of them", "real",
     "The same heuristic as 'two projects do not see each other': the tool "
     "reads the check NAME as quantifying over 'the' (from '...refuses by "
     "a different name than any of THEM') and cannot find an identifier of "
     "that name in the condition. The condition does quantify — "
     "`by_topic = {t: cannot_answer(t)[\"verdict\"] for t in "
     "REFUSED_TOPICS}` walks every one of the six topics, `by_topic == "
     "expect` requires each to match its OWN named verdict (not a shared "
     "one), and `len(set(expect.values())) == 6` separately requires the "
     "six to be pairwise distinct, so a lookup table collapsed to one "
     "shared verdict for every topic cannot pass. Falsifier: \"cannot_"
     "answer's topic dispatch collapses to one topic's entry\", which "
     "makes five of the six by_topic entries disagree with expect."),
    ("T1", "from_outline gives byte-identical output for the same "
     "outline called twice", "borderline",
     "`s1 == s2` on two calls built from two freshly-constructed (not "
     "shared) input dicts IS the T1 shape, and a determinism check cannot "
     "avoid it — the property under test is literally that the same "
     "outline gives the same answer twice. What makes it non-vacuous: "
     "`_record()` is called separately for r1 and r2, so nothing is "
     "shared by reference, and the comparison is on the full serialized "
     "JSON of the answer, not a single field. Falsifier: 'the symmetry "
     "axis picks up a random term, breaking determinism', which makes "
     "the two calls disagree even though the input is unchanged."),
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
          and len(KNOWN_UNFALSIFIABLE) == 12
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


def _dxf_styles(blocks: list) -> list:
    """STYLE テーブルの各エントリを ``(name, primary font)`` で返す。
    group 3 が無い(空文字)エントリも含めて返す — フォントが「無い」
    ことそのものが、下の check が名指しで見る失敗の形。"""
    return [(codes.get(2, [""])[0], codes.get(3, [""])[0])
            for t, codes in blocks if t == "STYLE"]


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
          "the DXF round-trips into rebuilt piece areas",
          "the DXF declares a text style with a real font")
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

        with guard("the DXF declares a text style with a real font"):
            # **A parser could not have DISCOVERED this failure mode** —
            # only a real renderer shows a missing glyph. This check itself
            # IS a parser (the same group-code reader as the checks above
            # it), so once you know to look, it can verify the structural
            # fact — STYLE "STANDARD" names a non-empty font — even though
            # it cannot confirm that font actually carries CJK glyphs on
            # every reader. ezdxf decodes the TEXT bytes into the correct
            # Japanese string with or without a STYLE table — a parser
            # never draws a glyph, so it cannot see this failure on its
            # own. QCAD (実機の CAD アプリケーション。標準ライブラリでは
            # ない — 確かめるためだけに使った、jgen には持ち込まない)did: with
            # no STYLE table at all, the same three-character piece name
            # (後身頃) rendered as three "?" — the font QCAD assigned to
            # the implicit "STANDARD" style carried no kanji, even though
            # the bytes it decoded were exactly right. Naming a STYLE
            # entry anything other than "STANDARD" would not have fixed
            # it either: no TEXT entity here sets group 7, so every reader
            # falls back to whatever it treats as the implicit default —
            # which is why this check pins TEXT_STYLE == "STANDARD" AND
            # its font, not just "a STYLE table exists somewhere".
            styles = _dxf_styles(blocks)
            style_names = [n for n, _f in styles]
            standard_font = dict(styles).get(_dxf.TEXT_STYLE, "")
            check("the DXF declares a text style with a real font",
                  _dxf.TEXT_STYLE == "STANDARD"
                  and style_names.count(_dxf.TEXT_STYLE) == 1
                  and standard_font == _dxf.TEXT_FONT != "",
                  f'STYLE table has {style_names}; "{_dxf.TEXT_STYLE}" — '
                  f'the implicit default every TEXT entity here relies on '
                  f'(none sets group 7) — carries font "{standard_font}". '
                  f'Measured in QCAD, a real CAD application: without this '
                  f'table the same three-kanji piece name drew as three '
                  f'"?"; with "{_dxf.TEXT_FONT}" declared, it drew correctly')

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
@declares("the smooth mannequin keeps the same five levels, and its total "
          "curvature converges near the linear one while its bands settle "
          "far tighter",
          "the monotone spline's four spans stay within their own "
          "measured girths",
          "the base garment is the body surface plus a constant radial "
          "offset",
          "the base garment ends where the body ends instead of "
          "extrapolating past it",
          "flattening a non-developable panel distorts both area and "
          "angle, measured triangle by triangle",
          "flatten refuses a grid too coarse to triangulate and a "
          "mannequin that never stood up")
def a_body_becomes_a_flat_pattern_by_geometry() -> None:
    """**The geometric route: skin-tight base, offset, flatten. No corpus.**

    Dress the mannequin in a skin-tight base, offset it to make the
    garment surface, then flatten that surface into panels — the pattern
    comes from the body's own geometry, not from retrieval. Three modules,
    one pipeline: ``mannequin_spline`` (a smoother mannequin through the
    SAME five measured levels), ``base_garment`` (body surface + constant
    offset, bounded where the body is), and ``flatten`` (that surface cut
    open and relaxed into 2D, with the resulting distortion measured per
    triangle rather than hidden).

    ``mannequin.build`` interpolates its five levels linearly, which
    concentrates curvature at the five creases. Measured by
    ``curvature.report`` on the reference body, over the FULL
    circumference: 183.39 degrees in total, of which chest to shoulder
    carries 185.30 — **more than the whole**, because hip to waist
    (-16.25) and waist to chest (-1.02) are negative, saddle-shaped.
    There is no clean percentage to quote here and an earlier draft of
    this comment quoted one anyway: "89% of the front torso's curvature",
    attributed to a ``curvature.py`` docstring that does not say it. The
    89% came from a different region — a hand-run probe over the front
    HALF only — and was repeated as though it were what the shipped
    module reports. ``mannequin_spline`` interpolates the SAME five
    levels with a monotone cubic Hermite spline (Fritsch-Carlson, 1980)
    instead, and ``curvature.compare_interpolation`` measures what changes:
    the total converges to nearly the same value (the spline's endpoint
    tangents are set to the linear secant, so the Gauss-Bonnet boundary
    term is unchanged) while the band distribution settles far tighter
    than the linear version's, which never settles at all — its bands
    swing by tens of degrees at every resolution tested because a crease's
    angle defect lands on whichever grid row is nearest it, which moves
    as the grid changes.
    """
    import math as _math

    from photoloset import base_garment as _bg
    from photoloset import curvature as _cv
    from photoloset import flatten as _fl
    from photoloset import garment_measure as _gm
    from photoloset import mannequin as _mq
    from photoloset import mannequin_spline as _sp

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("waist", 92.0),
                        ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    man = _mq.build(ms)

    with guard("the smooth mannequin keeps the same five levels, and its "
              "total curvature converges near the linear one while its "
              "bands settle far tighter"):
        smooth_man = _sp.build(ms)
        same_levels = (smooth_man["_levels"] == man["_levels"]
                      and len(smooth_man["_levels"]) == 5)
        cmp = _cv.compare_interpolation(man)
        ratios = cmp["band_spread_ratio_linear_over_smooth"]
        # Every one of the 4 bands must be tighter under the smooth
        # interpolation, not just the average — a single band that got
        # WORSE would be hidden by a mean.
        all_tighter = [ratios[name] is not None and ratios[name] > 2.0
                      for name in ratios]
        check("the smooth mannequin keeps the same five levels, and its "
              "total curvature converges near the linear one while its "
              "bands settle far tighter",
              cmp["verdict"] == "ANSWER" and same_levels
              and cmp["total_settled"] and cmp["distribution_settled"]
              and cmp["total_deg_gap"] < 2.0
              and 180.0 < cmp["linear"]["total_deg"] < 186.0
              and 180.0 < cmp["smooth"]["total_deg"] < 190.0
              and len(ratios) == 4 == len(all_tighter)
              and all(all_tighter)
              and max(cmp["linear"]["band_spread_across_refinement_deg"]
                      .values()) > 20.0,
              f'levels unchanged: {same_levels}; total_deg linear='
              f'{cmp["linear"]["total_deg"]:.2f} smooth='
              f'{cmp["smooth"]["total_deg"]:.2f} (gap '
              f'{cmp["total_deg_gap"]} deg); band tightening ratios '
              f'{ratios}, every one over 2x; linear worst band spread '
              f'{max(cmp["linear"]["band_spread_across_refinement_deg"].values()):.1f}'
              f' deg across the same refinement steps that settle the '
              f'total — the crease distribution never converges, only '
              f'the total does')

    with guard("the monotone spline's four spans stay within their own "
              "measured girths"):
        levels = man["_levels"]
        # A single running worst-case rather than a list the property could
        # pass by never being scanned: len(levels) is pinned in the
        # condition below, so a body with a different level count cannot
        # make this vacuous by looping zero times.
        worst_over = 0.0
        worst_who = None
        SAMPLES = 40
        for lo_i in range(len(levels) - 1):
            y0, y1 = levels[lo_i][0], levels[lo_i + 1][0]
            a0, a1 = levels[lo_i][1], levels[lo_i + 1][1]
            b0, b1 = levels[lo_i][2], levels[lo_i + 1][2]
            a_lo, a_hi = min(a0, a1), max(a0, a1)
            b_lo, b_hi = min(b0, b1), max(b0, b1)
            for k in range(SAMPLES + 1):
                y = y0 + (y1 - y0) * k / SAMPLES
                r = _sp.radius_at(man, y, 0.0)      # theta=0 -> r == a(y)
                r90 = _sp.radius_at(man, y, _math.pi / 2)  # -> r == b(y)
                over_a = max(a_lo - r, r - a_hi, 0.0)
                over_b = max(b_lo - r90, r90 - b_hi, 0.0)
                if over_a > worst_over:
                    worst_over, worst_who = over_a, ("a", lo_i, y, r)
                if over_b > worst_over:
                    worst_over, worst_who = over_b, ("b", lo_i, y, r90)
        checked = (len(levels) - 1) * (SAMPLES + 1) * 2
        check("the monotone spline's four spans stay within their own "
              "measured girths",
              len(levels) == 5 and checked == 328
              and worst_over <= 1e-6,
              f'{checked} samples across all 4 spans between the 5 levels '
              f'(a and b axes each), worst excursion past that span\'s own '
              f'two endpoint values was {worst_over:.2e}cm — a spline that '
              f'ignored Fritsch-Carlson\'s limiter would bulge past a '
              f'measured girth between two others'
              + (f' at {worst_who}' if worst_who else ''))

    with guard("the base garment is the body surface plus a constant "
              "radial offset"):
        gap = 1.3
        segments = _mq.SEGMENTS
        base = _bg.build(man, gap=gap, segments=segments)
        body_lo = man["_levels"][0][0]
        # Read the ACTUAL built vertices back — the bottom ring is
        # verts[0:segments], one per i, at theta = 2*pi*i/segments — rather
        # than recomputing body_r+gap a second time on both sides of the
        # comparison, which would check nothing about base_garment.build
        # itself.
        probe_i = [0, segments // 4, segments // 2, 3 * segments // 4]
        deltas = []
        for i in probe_i:
            theta = 2.0 * _math.pi * i / segments
            expected_r = _mq.radius_at(man, body_lo, theta) + gap
            vx, vy, vz = base["verts"][i]
            got_r = _math.hypot(vx, vz)
            deltas.append(abs(got_r - expected_r))
        check("the base garment is the body surface plus a constant "
              "radial offset",
              base["verdict"] == "ANSWER" and len(deltas) == 4
              and all(d < 1e-9 for d in deltas)
              and base["gap_cm"] == gap,
              f'4 vertices read back from the built bottom ring '
              f'(base["verts"][{probe_i}]), each |xz|-radius = body radius '
              f'at the hip level + {gap}cm as independently computed by '
              f'mannequin.radius_at, max discrepancy {max(deltas):.2e}cm')

    with guard("the base garment ends where the body ends instead of "
              "extrapolating past it"):
        body_lo = man["_levels"][0][0]
        body_hi = man["_levels"][-1][0]
        overshoot_below = 40.0
        long_coat = _bg.build(man, gap=1.0, y_bottom=body_lo - overshoot_below)
        entirely_outside = _bg.build(man, y_bottom=body_hi + 50.0,
                                     y_top=body_hi + 100.0)
        normal = _bg.build(man, gap=1.0)
        check("the base garment ends where the body ends instead of "
              "extrapolating past it",
              long_coat["verdict"] == "ANSWER"
              and long_coat["y_range_used"][0] == round(body_lo, 4)
              and long_coat["clipped_bottom_cm"] == overshoot_below
              and long_coat["rings_dropped_for_no_body"] == 0
              and entirely_outside["verdict"] == _bg.NO_COVERAGE
              and normal["verdict"] == "ANSWER"
              and normal["clipped_bottom_cm"] == 0.0
              and normal["clipped_top_cm"] == 0.0,
              f'asking for a hem {overshoot_below}cm below the mannequin\'s '
              f'own hip level ({body_lo}cm) still starts the mesh AT '
              f'{long_coat["y_range_used"][0]}cm, reports '
              f'{long_coat["clipped_bottom_cm"]}cm clipped rather than '
              f'inventing a shape below it; a range entirely outside the '
              f'body is refused ({entirely_outside["verdict"]}); asking '
              f'for exactly the body\'s own range clips nothing')

    with guard("flattening a non-developable panel distorts both area and "
              "angle, measured triangle by triangle"):
        seg, hs = 12, 8
        flat = _fl.build(man, segments=seg, height_steps=hs, iterations=800)
        n_tri = 2 * seg * hs
        ar = flat.get("area_ratio", {})
        ae = flat.get("angle_error_deg", {})
        check("flattening a non-developable panel distorts both area and "
              "angle, measured triangle by triangle",
              flat["verdict"] == "ANSWER" and flat["triangles"] == n_tri
              and len(flat["per_triangle"]) == n_tri
              and ar.get("min") is not None and ar["min"] < 1.0
              and ar.get("max") is not None and ar["max"] > 1.0
              and ae.get("max", 0.0) > 1.0
              and flat["relaxation"]["energy_last"]
              < flat["relaxation"]["energy_first"],
              f'{n_tri} triangles from a {seg}x{hs} grid, area ratio '
              f'{ar.get("min")}..{ar.get("max")} (straddles 1.0 — some '
              f'triangles compressed, some stretched, neither claimed '
              f'good), worst angle error {ae.get("max")} deg, relax '
              f'energy {flat["relaxation"]["energy_first"]:.1f} -> '
              f'{flat["relaxation"]["energy_last"]:.1f}')

    with guard("the smooth mannequin actually reaches base_garment and "
              "flatten through radius_at, not just curvature"):
        # **The headline claim was "one pipeline: smoother mannequin feeds
        # base garment feeds flatten" — but every OTHER check above only
        # ever calls `base_garment.build`/`flatten.build` with their
        # default `radius_at` (linear `mannequin.radius_at`), never
        # `mannequin_spline.radius_at`.** 2026-08-27, an outside check
        # proved that gap by mutation: silently ignoring the `radius_at`
        # argument in both functions (always falling back to the linear
        # one) left the WHOLE suite green. This check closes it — it
        # passes `mannequin_spline.radius_at` through both `build()`s and
        # asserts the composed result differs measurably from the linear
        # one, at every vertex, not just one probed height (a single probe
        # near the waist/chest midpoint happens to land where the two
        # curves nearly coincide — a check anchored there would itself be
        # close to unfalsifiable).
        base_lin = _bg.build(man, gap=1.3, segments=_mq.SEGMENTS)
        base_smo = _bg.build(man, gap=1.3, segments=_mq.SEGMENTS,
                             radius_at=_sp.radius_at)
        vdiffs = [_math.dist(a, b) for a, b in
                 zip(base_lin["verts"], base_smo["verts"])]
        flat_lin = _fl.build(man, segments=12, height_steps=8,
                             iterations=800)
        flat_smo = _fl.build(man, segments=12, height_steps=8,
                             iterations=800, radius_at=_sp.radius_at)
        check("the smooth mannequin actually reaches base_garment and "
              "flatten through radius_at, not just curvature",
              base_lin["verdict"] == "ANSWER"
              and base_smo["verdict"] == "ANSWER"
              and len(vdiffs) == len(base_lin["verts"]) == 408
              and max(vdiffs) > 0.5 and sum(vdiffs) / len(vdiffs) > 0.05
              and flat_lin["verdict"] == "ANSWER"
              and flat_smo["verdict"] == "ANSWER"
              and flat_smo["relaxation"]["energy_last"]
              != flat_lin["relaxation"]["energy_last"]
              and flat_smo["angle_error_deg"]["max"]
              != flat_lin["angle_error_deg"]["max"],
              f'base_garment: {len(vdiffs)} vertices, linear vs smooth '
              f'radius_at differ by up to {max(vdiffs):.3f}cm (mean '
              f'{sum(vdiffs) / len(vdiffs):.3f}cm); flatten: relax energy '
              f'{flat_lin["relaxation"]["energy_last"]} (linear) vs '
              f'{flat_smo["relaxation"]["energy_last"]} (smooth), worst '
              f'angle error {flat_lin["angle_error_deg"]["max"]} vs '
              f'{flat_smo["angle_error_deg"]["max"]} deg')

    with guard("flatten refuses a grid too coarse to triangulate and a "
              "mannequin that never stood up"):
        bad_seg = _fl.build(man, segments=2)
        bad_height = _fl.build(man, height_steps=0)
        no_man = _fl.build({"verdict": _mq.NO_MEASURE, "missing": ["chest"]})
        check("flatten refuses a grid too coarse to triangulate and a "
              "mannequin that never stood up",
              bad_seg["verdict"] == _fl.BAD_RESOLUTION
              and bad_height["verdict"] == _fl.BAD_RESOLUTION
              and no_man["verdict"] == _fl.NO_MANNEQUIN,
              f'segments=2 -> {bad_seg["verdict"]}; height_steps=0 -> '
              f'{bad_height["verdict"]}; an unbuilt mannequin -> '
              f'{no_man["verdict"]}')


# ---------------------------------------------------------------------------
@declares(
    "ease solved from width alone reproduces the base's own silhouette "
    "near zero",
    "a silhouette narrower than the body at any height is refused by "
    "name and shortfall",
    "a silhouette far wider than this offset model can reach is refused "
    "by name and excess",
    "depth moves as a stated byproduct of width-only ease, not as a "
    "second measurement",
    "a degenerate or too-few-point outline is refused, not silently "
    "scanned",
    "an outline whose left and right extents are not equal and opposite "
    "still solves the same ease",
    "silhouette refuses an unbuilt mannequin, too coarse a grid, a "
    "height range outside the body, and an outline that leaves a gap",
    "the matched radius function plugs into base_garment.build without "
    "a second mesh builder",
)
def a_silhouette_constrains_only_the_projected_width() -> None:
    """**The last geometric step: a photo's outline pins width, nothing else.**

    ``silhouette.match`` reads a front-view outline — a closed 2D curve, no
    image in sight — and solves a per-height ease from ONE thing the
    outline actually contains: the projected width. It refuses, named by
    height, when that ease cannot be reached — too little (the body would
    not fit) or too much (this offset model cannot represent that much
    ease). Depth is never measured; the answer states what moved as a side
    effect of the offset model, and this is checked against an
    independent recomputation, not against the module's own claim about
    itself — the same discipline ``base_garment``'s own checks use when
    they read verts back rather than trust a field.

    Two checks were added after an outside read of the first six: an
    asymmetric outline (so ``outline_width_at`` is pinned on its actual
    job — true leftmost/rightmost x — not just on symmetric fixtures where
    a wrong ``max(|left|, |right|)`` shortcut would have looked identical),
    and the four typed refusal paths (``NO_MANNEQUIN``, ``BAD_RESOLUTION``,
    ``NO_COVERAGE``, ``OUTLINE_GAP``) that the first six never exercised
    even once.
    """
    import math as _math

    from photoloset import garment_measure as _gm
    from photoloset import mannequin as _mq
    from photoloset import silhouette as _sil

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("waist", 92.0),
                        ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    man = _mq.build(ms)
    body_lo, body_hi = man["_levels"][0][0], man["_levels"][-1][0]
    HS = 16
    GAP = 1.7
    # Independently recomputed, not read from anything ``match`` reports:
    # the ring grid ``match`` itself must be using (same formula as
    # ``base_garment``/``flatten``), and which of those 17 rings has the
    # largest body half-width — the ring a correct "worst violation" must
    # land on, since both the shortfall (narrower) and the excess (wider)
    # violations below scale with the body's own half-width at that ring.
    _ring_ys = [body_lo + (body_hi - body_lo) * j / HS for j in range(HS + 1)]
    _a_vals = [_mq.radius_at(man, y, 0.0) for y in _ring_ys]
    _worst_y = round(_ring_ys[_a_vals.index(max(_a_vals))], 4)

    def _own_outline(n: int, gap: float):
        """The base garment's own silhouette, as a closed polygon: right
        side ascending, left side descending, closing on a flat top and
        bottom edge (skipped by the scan, same as any horizontal edge)."""
        pts = []
        for k in range(n + 1):
            y = body_lo + (body_hi - body_lo) * k / n
            a = _mq.radius_at(man, y, 0.0)
            pts.append((a + gap, y))
        for k in range(n, -1, -1):
            y = body_lo + (body_hi - body_lo) * k / n
            a = _mq.radius_at(man, y, 0.0)
            pts.append((-(a + gap), y))
        return pts

    def _scaled_outline(n: int, factor: float):
        """A silhouette scaled by ``factor`` at every height — narrower
        (factor<1) or wider (factor>1) than the body itself, never matching
        the base's own gap."""
        pts = []
        for k in range(n + 1):
            y = body_lo + (body_hi - body_lo) * k / n
            a = _mq.radius_at(man, y, 0.0)
            pts.append((a * factor, y))
        for k in range(n, -1, -1):
            y = body_lo + (body_hi - body_lo) * k / n
            a = _mq.radius_at(man, y, 0.0)
            pts.append((-(a * factor), y))
        return pts

    def _partial_outline(n: int, gap: float, y_min: float):
        """The same silhouette, but only over ``[y_min, body_hi]`` — the
        bottom of the body is left with no scan-line coverage at all, so
        rings below ``y_min`` cannot be matched from this outline."""
        pts = []
        for k in range(n + 1):
            y = y_min + (body_hi - y_min) * k / n
            a = _mq.radius_at(man, y, 0.0)
            pts.append((a + gap, y))
        for k in range(n, -1, -1):
            y = y_min + (body_hi - y_min) * k / n
            a = _mq.radius_at(man, y, 0.0)
            pts.append((-(a + gap), y))
        return pts

    with guard("ease solved from width alone reproduces the base's own "
              "silhouette near zero"):
        outline = _own_outline(400, GAP)
        res = _sil.match(man, outline, height_steps=HS)
        eases = [e for _y, e in res.get("ease_by_height_cm", [])]
        wr = res.get("width_residual_cm", {})
        # A scalar, not a quantifier: the worst of the 17 is what the
        # condition pins AND what the detail prints, so the two cannot
        # drift apart the way a separate all() and a separate max() could.
        max_dev_from_gap = (max(abs(e - GAP) for e in eases) if eases
                            else float("inf"))
        check("ease solved from width alone reproduces the base's own "
              "silhouette near zero",
              res["verdict"] == "ANSWER" and len(eases) == 17
              and max_dev_from_gap < 1e-6
              and wr.get("probe_count") == 81 and wr.get("probe_gaps") == 0
              and wr.get("max", 1.0) < 0.01 and wr.get("mean", 1.0) < 0.01,
              f'{len(eases)} rings all solved ease={GAP}cm (max deviation '
              f'from that {max_dev_from_gap:.2e}cm); against '
              f'{wr.get("probe_count")} finer probe heights '
              f'({wr.get("probe_gaps")} uncovered) the width residual is '
              f'max={wr.get("max")}cm mean={wr.get("mean")}cm — the '
              f'base\'s own outline, fed back in, comes back as itself')

    with guard("a silhouette narrower than the body at any height is "
              "refused by name and shortfall"):
        narrow = _scaled_outline(60, 0.3)
        res_narrow = _sil.match(man, narrow, height_steps=HS)
        v = res_narrow.get("violations", [])
        worst = res_narrow.get("worst", {})
        check("a silhouette narrower than the body at any height is "
              "refused by name and shortfall",
              res_narrow["verdict"] == _sil.UNREACHABLE
              and len(v) == 17 and all(x["bound"] == "min" for x in v)
              and worst.get("bound") == "min"
              and worst.get("y") == _worst_y
              and worst.get("over_by_cm", 0.0) > 5.0,
              f'{len(v)}/{HS + 1} rings refused as narrower than the body '
              f'(bound=min); worst at y={worst.get("y")}cm — '
              f'independently the ring with the largest body half-width '
              f'is also y={_worst_y}cm — short by '
              f'{worst.get("over_by_cm")}cm (ease={worst.get("ease_cm")}'
              f'cm)')

    with guard("a silhouette far wider than this offset model can reach "
              "is refused by name and excess"):
        wide = _scaled_outline(60, 6.0)
        res_wide = _sil.match(man, wide, height_steps=HS)
        v = res_wide.get("violations", [])
        worst = res_wide.get("worst", {})
        check("a silhouette far wider than this offset model can reach "
              "is refused by name and excess",
              res_wide["verdict"] == _sil.UNREACHABLE
              and len(v) == 17 and all(x["bound"] == "max" for x in v)
              and worst.get("bound") == "max"
              and worst.get("y") == _worst_y
              and worst.get("over_by_cm", 0.0) > 50.0,
              f'{len(v)}/{HS + 1} rings refused as wider than any offset '
              f'this model reaches (bound=max); worst at y='
              f'{worst.get("y")}cm — matches the same largest-half-width '
              f'ring (y={_worst_y}cm) as the narrower case above — over '
              f'by {worst.get("over_by_cm")}cm (ease={worst.get("ease_cm")}'
              f'cm)')

    with guard("depth moves as a stated byproduct of width-only ease, "
              "not as a second measurement"):
        res2 = _sil.match(man, _own_outline(200, GAP), height_steps=HS)
        lim = res2.get("single_view_limits", {})
        rf = _sil.radius_at_for(res2)
        probe_y = (body_lo + body_hi) / 2.0
        body_depth = _mq.radius_at(man, probe_y, _math.pi / 2)
        matched_depth = rf(man, probe_y, _math.pi / 2)
        check("depth moves as a stated byproduct of width-only ease, "
              "not as a second measurement",
              res2["verdict"] == "ANSWER"
              and set(lim.keys()) == {
                  "depth_unconstrained_by_this_view",
                  "visual_hull_is_an_upper_bound",
                  "outline_scan_keeps_only_the_outer_extent"}
              and len(lim.get("depth_unconstrained_by_this_view", "")) > 20
              and len(lim.get("visual_hull_is_an_upper_bound", "")) > 20
              and len(lim.get("outline_scan_keeps_only_the_outer_extent",
                              "")) > 20
              and abs((matched_depth - body_depth) - GAP) < 1e-6,
              f'independently recomputed: body depth (θ=π/2) at y='
              f'{probe_y:.2f}cm is {body_depth:.4f}cm, matched depth is '
              f'{matched_depth:.4f}cm, a shift of '
              f'{matched_depth - body_depth:.4f}cm — equal to the width-'
              f'derived ease ({GAP}cm), which the outline never stated '
              f'about depth; 3 typed fields present, each over 20 chars')

    with guard("a degenerate or too-few-point outline is refused, not "
              "silently scanned"):
        # Different y's, so this is caught ONLY by the point-count guard —
        # not incidentally by the zero-height guard beside it.
        two_points = _sil.match(man, [(0.0, 0.0), (1.0, 10.0)],
                                height_steps=HS)
        flat = _sil.match(man, [(-1.0, 5.0), (1.0, 5.0), (0.0, 5.0)],
                          height_steps=HS)
        nonfinite = _sil.match(man, [(-1.0, 0.0), (1.0, 0.0),
                                     (float("inf"), 10.0)],
                               height_steps=HS)
        ok = _sil.match(man, _own_outline(60, GAP), height_steps=HS)
        check("a degenerate or too-few-point outline is refused, not "
              "silently scanned",
              two_points["verdict"] == _sil.BAD_OUTLINE
              and flat["verdict"] == _sil.BAD_OUTLINE
              and nonfinite["verdict"] == _sil.BAD_OUTLINE
              and ok["verdict"] == "ANSWER",
              f'2 points -> {two_points["verdict"]}; a zero-height triangle'
              f' -> {flat["verdict"]}; a non-finite coordinate -> '
              f'{nonfinite["verdict"]}; a real 122-point outline still -> '
              f'{ok["verdict"]}')

    with guard("an outline whose left and right extents are not equal "
              "and opposite still solves the same ease"):
        # Found by an outside attack on the first six checks: a mutant
        # outline_width_at that returns (-m, m) with m = max(|left|,
        # |right|) instead of the true (left, right) passes every one of
        # them unchanged, because every outline they build is symmetric
        # about x=0 by construction. Shifting the base's own outline
        # sideways by a constant does not change its true width at any
        # height (right - left is shift-invariant) but DOES break
        # left == -right, so this is the minimal fixture that only the
        # correct implementation gets right.
        shift = 7.3
        shifted = [(x + shift, y) for x, y in _own_outline(200, GAP)]
        res4 = _sil.match(man, shifted, height_steps=HS)
        eases4 = [e for _y, e in res4.get("ease_by_height_cm", [])]
        max_dev4 = (max(abs(e - GAP) for e in eases4) if eases4
                   else float("inf"))
        check("an outline whose left and right extents are not equal "
              "and opposite still solves the same ease",
              res4["verdict"] == "ANSWER" and len(eases4) == 17
              and max_dev4 < 1e-6,
              f'outline shifted +{shift}cm off-center at every height '
              f'(left and right extents no longer equal-and-opposite); '
              f'{len(eases4)} rings still all solve ease={GAP}cm (max '
              f'deviation {max_dev4:.2e}cm) — outline_width_at is reading '
              f'the true leftmost/rightmost x, not a symmetric '
              f'max(|left|,|right|) shortcut that a centered-only fixture '
              f'could not have told apart from the real thing')

    with guard("silhouette refuses an unbuilt mannequin, too coarse a "
              "grid, a height range outside the body, and an outline "
              "that leaves a gap"):
        no_man = _sil.match({"verdict": _mq.NO_MEASURE,
                             "missing": ["chest"]},
                            _own_outline(60, GAP), height_steps=HS)
        bad_res = _sil.match(man, _own_outline(60, GAP), segments=2,
                             height_steps=HS)
        no_cov = _sil.match(man, _own_outline(60, GAP), height_steps=HS,
                            y_bottom=body_hi + 10.0, y_top=body_hi + 20.0)
        y_min = body_lo + 15.0
        gap_out = _sil.match(man, _partial_outline(60, GAP, y_min),
                             height_steps=HS)
        missing_heights = gap_out.get("missing_heights", [])
        # Same name used for the length pin AND the quantifier below, so
        # the two cannot drift into different expressions — an all() over
        # an iterable this condition never proves non-empty is exactly the
        # T2 shape tests/unfalsifiable.py hunts for.
        check("silhouette refuses an unbuilt mannequin, too coarse a "
              "grid, a height range outside the body, and an outline "
              "that leaves a gap",
              no_man["verdict"] == _sil.NO_MANNEQUIN
              and bad_res["verdict"] == _sil.BAD_RESOLUTION
              and no_cov["verdict"] == _sil.NO_COVERAGE
              and gap_out["verdict"] == _sil.OUTLINE_GAP
              and len(missing_heights) > 0
              and all(h < y_min - 1e-6 for h in missing_heights),
              f'an unbuilt mannequin -> {no_man["verdict"]}; segments=2 '
              f'-> {bad_res["verdict"]}; a requested range entirely above '
              f'the body -> {no_cov["verdict"]}; an outline covering only '
              f'[{y_min}, {body_hi:.2f}] against the body\'s full '
              f'[{body_lo:.2f}, {body_hi:.2f}] -> {gap_out["verdict"]}, '
              f'{len(missing_heights)} rings named as missing, all below '
              f'{y_min}cm as expected')

    with guard("the matched radius function plugs into base_garment.build "
              "without a second mesh builder"):
        res3 = _sil.match(man, _own_outline(200, GAP), height_steps=HS)
        surf = _sil.to_surface(res3, man)
        expected_r = _mq.radius_at(man, res3["y_range_used"][0], 0.0) + GAP
        vx, vy, vz = surf["verts"][0]
        got_r = _math.hypot(vx, vz)
        check("the matched radius function plugs into base_garment.build "
              "without a second mesh builder",
              surf.get("verdict") == "ANSWER"
              and surf["vertices"] == res3["segments"] * (HS + 1)
              and abs(got_r - expected_r) < 1e-6,
              f'to_surface() routed through base_garment.build: '
              f'{surf["vertices"]} vertices ({res3["segments"]} segments '
              f'x {HS + 1} rings), bottom-ring θ=0 radius read back '
              f'{got_r:.4f}cm vs independently expected '
              f'{expected_r:.4f}cm (body radius at θ=0 + {GAP}cm ease)')


# ---------------------------------------------------------------------------
@declares("a seam is placed where the flattened tube's distortion is worst, "
          "and buys a measured drop in it",
          "each panel's Gauss-Bonnet total splits into an outline share and "
          "a dart share, and the two sum back to exactly 360 degrees",
          "panels refuse a count that cannot fit the grid and a mannequin "
          "that never stood up",
          "the panel ring sews with exactly one seam in the round",
          "panels differ from the drafted coat in piece count and seam "
          "layout, not by accident",
          "the drafted coat's own doors answer or refuse the panels for a "
          "reason they name")
def the_flattened_tube_becomes_panels() -> None:
    """**Cutting the flattened tube into panels — where, how much, and what
    it costs the doors built for the drafted coat.**

    ``flatten`` reports the distortion of ONE full-circumference panel cut
    at a single meridian. That is not a pattern. This measures where a
    second (and third) seam should go — the place the flattened tube's own
    per-triangle distortion is worst — cuts there, reflattens both sides,
    and reports how much each seam actually bought. It also splits each
    panel's Gauss-Bonnet total between its outline and its darts (verifying
    the split sums to 360 degrees rather than asserting it), places the
    dart share through ``darts.py`` unmodified, and feeds the panels
    through the same doors the drafted coat uses (``garment_marks``,
    ``dxf``, ``garment_sew`` / ``sewing_order``, ``darts.apply``) to see
    which open and which refuse.

    **A dart-address bug found by an outside read, fixed here.** The first
    version placed each dart on a SIMPLIFIED 4-corner outline internal to
    ``cut()``, addressing the seam edge by the literal name ``"e1"`` —
    which happens to be the seam only in that 4-point numbering. The same
    literal ``"e1"``, reused against the fine, many-vertex outline
    ``to_pieces()`` actually returns, pointed at a short hem segment
    instead — not the seam. ``panels._place_dart`` now places every dart
    directly on the real (fine) boundary ``_panel_boundary`` returns, and
    reports which of the seam's several segments it used, so nothing
    downstream has to guess an address a second time. All 3 dart-bearing
    panels' darts now fit the real seam (0 refused, not 1) — the earlier
    report's claim that a fine-mesh capacity limit was found is wrong; it
    was an address collision, not a length limit.
    """
    from photoloset import darts as _dt
    from photoloset import dxf as _dxf
    from photoloset import garment_marks as _mk
    from photoloset import garment_measure as _gm
    from photoloset import garment_pattern as _gp
    from photoloset import garment_sew as _gs
    from photoloset import mannequin as _mq
    from photoloset import panels as _pn
    from photoloset import sewing_order as _so

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0),
                        ("waist", 92.0), ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    man = _mq.build(ms)
    seg, hs, iters = 12, 8, 800
    out = _pn.cut(man, n_panels=4, segments=seg, height_steps=hs,
                  iterations=iters)

    with guard("a seam is placed where the flattened tube's distortion is "
              "worst, and buys a measured drop in it"):
        seams = out.get("seam_log") or []
        bought = [s["distortion_bought"] for s in seams]
        before = out.get("distortion_index_before_any_additional_cut")
        after = out.get("distortion_index_after_all_cuts")
        # Every individual seam has to buy something (its own local
        # before/after strictly improves), or picking "the worst spot"
        # would not be doing anything — a seam that bought nothing (or
        # made things worse) would mean the criterion is decoration. Read
        # as a minimum, not an `all()`, over the length just pinned below —
        # a 0-seam run would raise on `min([])` and go red through `guard`
        # rather than pass by never entering a loop.
        worst_gain = min(bought)
        check("a seam is placed where the flattened tube's distortion is "
              "worst, and buys a measured drop in it",
              out["verdict"] == "ANSWER" and out["n_panels_reached"] == 4
              and len(seams) == 3 and len(bought) == 3 and worst_gain > 0.0
              and before is not None and after is not None
              and after < before
              and round(before, 4) == 0.1347 and round(after, 4) == 0.0507
              and out["distortion_bought_total_pct"] > 60.0,
              f'4 panels reached from a {seg}x{hs} grid, 3 seams cut, each '
              f'one strictly lowering its own local distortion index '
              f'{bought}; the whole-tube index goes {before} -> {after} '
              f'({out["distortion_bought_total_pct"]}% lower) — a single '
              f'meridian cut alone (flatten.build) cannot be compared to '
              f'this number directly, since it is a different quantity '
              f'(mean |area ratio - 1| + mean angle error/45), but it '
              f'strictly falls with every seam this greedy criterion adds')

    with guard("each panel's Gauss-Bonnet total splits into an outline "
              "share and a dart share, and the two sum back to exactly "
              "360 degrees"):
        panels = out.get("panels") or []
        residuals = [p["curvature"]["gauss_bonnet_residual_deg"]
                    for p in panels]
        interior = [p["curvature"]["interior_deg"] for p in panels]
        boundary = [p["curvature"]["boundary_deg"] for p in panels]
        # Every panel is its own disc (one boundary loop), so the identity
        # holds PANEL BY PANEL, not just on average — a residual hiding in
        # one panel behind three exact ones would not show in a sum.
        check("each panel's Gauss-Bonnet total splits into an outline "
              "share and a dart share, and the two sum back to exactly "
              "360 degrees",
              len(panels) == 4 and len(residuals) == 4
              and len(interior) == 4
              and all(r < 1e-6 for r in residuals)
              and all(i >= 0.0 for i in interior)
              and sum(interior) > 30.0
              and any(i > 0.0 for i in interior)
              and out["gauss_bonnet_across_all_panels_deg"]
              == out["gauss_bonnet_expected_deg"] == 360.0 * 4,
              f'interior_deg (the dart share) per panel {interior}, '
              f'boundary_deg (the outline share, computed independently — '
              f'not 360 minus interior) {[round(b, 2) for b in boundary]}, '
              f'worst residual between the two computations and 360deg is '
              f'{max(residuals):.2e} degrees. Summed over all 4 panels: '
              f'{out["gauss_bonnet_across_all_panels_deg"]} deg == '
              f'4 * 360 exactly')

    with guard("panels refuse a count that cannot fit the grid and a "
              "mannequin that never stood up"):
        too_many = _pn.cut(man, n_panels=seg + 1, segments=seg,
                           height_steps=hs)
        bad_count = _pn.cut(man, n_panels=0, segments=seg, height_steps=hs)
        bad_res = _pn.cut(man, n_panels=2, segments=2, height_steps=hs)
        no_man = _pn.cut({"verdict": _mq.NO_MEASURE, "missing": ["chest"]},
                         n_panels=2)
        check("panels refuse a count that cannot fit the grid and a "
              "mannequin that never stood up",
              too_many["verdict"] == _pn.TOO_MANY_PANELS
              and bad_count["verdict"] == _pn.BAD_PANEL_COUNT
              and bad_res["verdict"] == _pn.BAD_RESOLUTION
              and no_man["verdict"] == _pn.NO_MANNEQUIN,
              f'n_panels={seg + 1} on {seg} columns -> {too_many["verdict"]}; '
              f'n_panels=0 -> {bad_count["verdict"]}; segments=2 -> '
              f'{bad_res["verdict"]}; an unbuilt mannequin -> '
              f'{no_man["verdict"]}')

    pieces = _pn.to_pieces(out)

    with guard("the panel ring sews with exactly one seam in the round"):
        built = _gs.build(pieces)
        plan = _so.plan(built)
        n = out["n_panels_reached"]
        # N panels in a ring (N seams, N pieces, 1 connected component) has
        # beta = N - N + 1 = 1 by construction, whatever N is — this is the
        # SAME formula sewing_order.py already proves for the drafted coat
        # (5-3+1=3), read here off a completely different garment shape.
        check("the panel ring sews with exactly one seam in the round",
              built["verdict"] == "ANSWER" and n == 4
              and len(built["seams"]) == 4
              and all(s["state"] == "SEWN" for s in built["seams"])
              and plan["verdict"] == "ANSWER"
              and plan["in_the_round"] == 1
              and plan["flat"] == n - 1
              and plan["in_the_round_minimum"] == 1
              and plan["at_the_minimum"] is True
              and plan["formula"].endswith(f"= {n} − {n} + 1 = 1"),
              f'{n} panels, {len(built["seams"])} seams (the last one '
              f'closes the original theta=0 cut back into a ring), all '
              f'SEWN; {plan["formula"]} — a gored construction like this '
              f'always has exactly 1 in-the-round seam, unlike the '
              f'drafted coat\'s 3 (front, back and sleeve are not a ring)')

    with guard("panels differ from the drafted coat in piece count and "
              "seam layout, not by accident"):
        draft = _gp.draft(ms)
        cmp = _pn.compare_to_draft(out, draft)
        check("panels differ from the drafted coat in piece count and "
              "seam layout, not by accident",
              cmp["verdict"] == "ANSWER"
              and cmp["panel_count"] == 4 and cmp["draft_piece_count"] == 3
              and cmp["panel_count"] != cmp["draft_piece_count"]
              and round(cmp["panel_total_area_cm2"], 2) == 6098.32
              and round(cmp["draft_total_area_cm2"], 1) == 7306.1
              and cmp["area_ratio_panels_over_draft"] is not None
              and 0.7 < cmp["area_ratio_panels_over_draft"] < 0.95
              and len(cmp["seam_positions"]["panels"]) == 3,
              f'{cmp["panel_count"]} geometric panels vs '
              f'{cmp["draft_piece_count"]} drafted pieces; total area '
              f'{cmp["panel_total_area_cm2"]}cm2 vs '
              f'{cmp["draft_total_area_cm2"]}cm2 (ratio '
              f'{cmp["area_ratio_panels_over_draft"]}) — the two routes '
              f'start from the same measurements and land on visibly '
              f'different shapes, which is the expected result stated up '
              f'front, not a discrepancy to explain away')

    with guard("the drafted coat's own doors answer or refuse the panels "
              "for a reason they name"):
        marked = _mk.apply(pieces)
        sa_verdicts = sorted({v.get("verdict")
                              for v in marked.get("seam_allowance", {})
                              .values()})
        dxf_out = _dxf.to_dxf(marked)
        # Each dart's own edge/t come back from panels.cut() itself
        # (``_place_dart`` reports which of the seam's segments it used),
        # not a literal re-guessed here — that literal ("e1") is exactly
        # the bug an outside read found: it happened to be the seam in the
        # SIMPLIFIED quad cut() used internally, but pointed at a hem
        # segment once replayed against the fine outline ``pieces`` below
        # actually carries.
        darts_list = [_dt.dart(p["name"], p["dart"]["darts_result"]["edge"],
                               p["dart"]["darts_result"]["t"],
                               p["dart"]["intake_cm_requested"],
                               length_cm=p["dart"]["depth_cm"])
                     for p in out["panels"] if p["dart"]["placed"]]
        applied = _dt.apply(pieces, darts_list)
        # garment_marks refuses a seam allowance for every panel — not a
        # crash, a named reason: our 下辺/右辺/上辺/左辺 edge names carry no
        # entry in garment_marks.SEAM_ALLOWANCE, so offset_outline refuses
        # up front, by name, before any width is computed (UNSTATED —
        # garment_marks.py's own fix for the naming-vocabulary gap: an
        # unrecognized edge name used to default silently to 0cm and get
        # refused, misleadingly, as WENT_INWARD, because 0cm added cannot
        # be told apart from "went inward" inside offset_outline's own
        # strict-growth proof; it now names the edges and refuses honestly
        # instead of guessing 0cm). This is a naming-vocabulary gap between
        # the two systems, not a folded or self-intersecting panel — the
        # underlying outline is untouched by this and dxf.to_dxf still
        # writes the sew line for every panel.
        check("the drafted coat's own doors answer or refuse the panels "
              "for a reason they name",
              marked["verdict"] == "ANSWER"
              and sa_verdicts == [_mk.UNSTATED]
              and dxf_out["verdict"] == "ANSWER"
              and len(darts_list) == 3
              and applied["verdict"] == "ANSWER"
              and applied["count"] == 3 and len(applied["refused"]) == 0,
              f'garment_marks.apply -> ANSWER, but seam_allowance for '
              f'every one of 4 panels is {sa_verdicts[0]} (refused by '
              f'name, naming the 4 edges, before any width was computed — '
              f'not a bad outline); '
              f'dxf.to_dxf -> {dxf_out["verdict"]} (writes the sew lines '
              f'regardless); darts.apply against the fine pattern-level '
              f'outline, addressed by the edge panels.cut() itself '
              f'reports (not a re-guessed literal), places all '
              f'{applied["count"]} of {len(darts_list)} darts — 0 '
              f'refused, because the real seam has {hs} segments each '
              f'~9-11cm long, comfortably wider than any of the three '
              f'requested intakes')


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
@declares("the hem's shape is read off the whole bottom boundary, not off "
          "its two ends, and each of level / asymmetric_left_right / "
          "uneven is reachable from an outline that earns it")
def the_hem_shape_is_measured_across_the_whole_bottom() -> None:
    """**structure.py's docstring records a hem classification for three
    synthetic garments. Nothing pinned it until now.**

    A skeptic gutting today's structure.py checks found that ``_hem`` could
    be replaced by a function ignoring its input entirely — ``pts``,
    ``min_x``, ``max_x``, ``garment_h``, all of it — and still keep every
    check green, because the only check reading ``_hem``'s output looked at
    the front/back refusal it always carries and at nothing else. The
    module measured ``"level"`` on two garments and
    ``"asymmetric_left_right"`` on a third, wrote those into its own
    docstring, and no check could tell whether it still did.

    **The discriminating case is a hem that dips in the middle.** Its two
    ends sit at exactly the same height, so ``left_right_diff_norm`` is
    0.0 — an implementation classifying from the two ends calls it
    ``"level"``. Its ``hem_range_norm`` is over the 0.02 threshold, so an
    implementation reading the whole boundary calls it ``"uneven"``.
    Pinning the tilted hem alone cannot tell those two apart; pinning the
    dip is what makes the word "whole" in this check's name mean anything.

    The sign is pinned too, so an implementation taking ``abs()`` — which
    would still name every shape correctly — goes red here.
    """
    import math
    from photoloset import structure as _st

    W, H, AXIS, HW, Y0 = 800, 1200, 400.0, 90.0, 250.0

    def _tube(hem_fn, n=240, m=40):
        pts = []
        for k in range(n + 1):
            t = k / n
            pts.append((AXIS + HW, Y0 + (hem_fn(AXIS + HW) - Y0) * t))
        for k in range(1, m):
            x = AXIS + HW - 2 * HW * k / m
            pts.append((x, hem_fn(x)))
        for k in range(n, -1, -1):
            t = k / n
            pts.append((AXIS - HW, Y0 + (hem_fn(AXIS - HW) - Y0) * t))
        return pts

    def _hem_of(hem_fn):
        r = _st.from_outline({"outline": _tube(hem_fn), "width_px": W,
                              "height_px": H, "source": "checks",
                              "fixture": False})
        if r.get("verdict") != "ANSWER":
            return {"shape": r.get("verdict")}
        return (r.get("landmarks") or {}).get("hem") or {}

    level = _hem_of(lambda x: 1150.0)
    dip = _hem_of(lambda x: 1150.0
                  + 90.0 * math.cos(math.pi * (x - AXIS) / (2 * HW)))
    right_low = _hem_of(lambda x: 1150.0
                        + 60.0 * (x - (AXIS - HW)) / (2 * HW))
    left_low = _hem_of(lambda x: 1150.0
                       + 60.0 * ((AXIS + HW) - x) / (2 * HW))

    name = ("the hem's shape is read off the whole bottom boundary, not "
            "off its two ends, and each of level / asymmetric_left_right "
            "/ uneven is reachable from an outline that earns it")
    with guard(name):
        check(name,
              level.get("shape") == "level"
              and level.get("hem_range_norm") == 0.0
              and dip.get("shape") == "uneven"
              and dip.get("left_right_diff_norm") == 0.0
              and dip.get("hem_range_norm", 0.0) > 0.05
              and right_low.get("shape") == "asymmetric_left_right"
              and left_low.get("shape") == "asymmetric_left_right"
              and right_low.get("left_right_diff_norm") == 0.05625
              and left_low.get("left_right_diff_norm") == -0.05625
              and len({level.get("shape"), dip.get("shape"),
                       right_low.get("shape")}) == 3,
              f'level hem -> {level.get("shape")!r} '
              f'(range {level.get("hem_range_norm")}); a hem dipping in '
              f'the middle -> {dip.get("shape")!r} with its two ends dead '
              f'level (left_right_diff_norm '
              f'{dip.get("left_right_diff_norm")}, range '
              f'{dip.get("hem_range_norm")}) — classified from the whole '
              f'boundary, not from the ends; tilted right -> '
              f'{right_low.get("shape")!r} at '
              f'{right_low.get("left_right_diff_norm")} and tilted left '
              f'at {left_low.get("left_right_diff_norm")}, the sign kept')


# ---------------------------------------------------------------------------
@declares("every falsifier's anchor still exists in the file it "
          "targets, so a refactor cannot disarm a mutation silently")
def every_falsifier_anchor_still_exists() -> None:
    """**A mutation whose anchor has moved tests nothing, and the sweep
    that says so takes twenty minutes to say it.**

    ``WHOLE_SUITE`` entries carry a literal find-string. When the source
    line it names is edited, the string stops matching, the harness prints
    ``SKIP ... anchor not found`` and returns 1 — the design is sound and it
    did fire. But it fires only after the whole sweep has run.

    On 2026-08-27 ``mcp.py``'s ``HOME`` was changed from
    ``Path.home() / ".photoloset"`` to a form that reads ``PHOTOLOSET_HOME``
    first. That silently disarmed ``#23 the server ignores the HOME it is
    given``, and the disarming was found by a twenty-minute run, at the end,
    in a summary that otherwise read 240/241. This check finds the same
    thing in about two seconds, which is the difference between noticing
    while you are still editing the line and noticing after you have moved
    on.

    **Both directions, for the reason the scanner keeps having to teach.**
    "No anchor is missing" is an empty list, and an empty list is also what
    a reader that examines nothing produces. So the same reader is run twice:
    over the real table, which must come back empty, and over a copy with one
    anchor deliberately corrupted, which must name exactly that entry.
    """
    import importlib.util as _ilu

    name = ("every falsifier's anchor still exists in the file it targets, "
            "so a refactor cannot disarm a mutation silently")
    root = Path(__file__).parent.parent

    spec = _ilu.spec_from_file_location(
        "_fals_anchors", Path(__file__).parent / "falsifiers.py")
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def missing_anchors(table):
        """Entries whose find-string is not in the file they name."""
        out = []
        for entry in table:
            label, rel, edits = entry[0], entry[1], entry[2]
            try:
                src = (root / rel).read_text(encoding="utf-8")
            except OSError:
                out.append((label, rel, "unreadable"))
                continue
            for find, _repl in edits:
                if find not in src:
                    out.append((label, rel, find[:40]))
        return out

    real = list(mod.WHOLE_SUITE)
    gone = missing_anchors(real)

    # The wrong table, built here rather than imagined: one anchor corrupted.
    doctored = list(real)
    victim = doctored[0]
    doctored[0] = (victim[0], victim[1],
                   [("__no_such_anchor_" + "x" * 12 + "__", "")], victim[3])
    caught = missing_anchors(doctored)

    with guard(name):
        check(name,
              len(real) > 100
              and gone == []
              and len(caught) == 1
              and caught[0][0] == victim[0],
              f'{len(real)} whole-suite entries, {len(gone)} with an anchor '
              f'their file no longer contains {gone}; the same reader over '
              f'a copy with one anchor corrupted names {len(caught)} '
              f'({caught[0][0][:40] if caught else "nothing"}) — so the '
              f'empty list above is a measurement, not what any reader '
              f'would have returned')


# ---------------------------------------------------------------------------
@declares("the photograph sets the garment's shape and the tape sets "
          "only its scale, and the tape reaches the scale through the "
          "shoulder alone")
def the_photograph_sets_the_shape_and_the_tape_sets_the_scale() -> None:
    """**The honest headline, written as something that can go red.**

    "photoloset understands a garment's structure from a photograph" is
    half true, and this check is where the halves are separated by
    measurement instead of by prose.

    Running ``photo_to_pattern.run`` over one A-line outline and varying
    only ONE input at a time:

      the outline's hem 160px -> 100px      area  -3.70%
      the outline's hem 160px -> 220px      area  +4.86%
      the outline's shoulder 90px -> 70px   area  -9.58%
      the tape's chest 88cm -> 108cm        area  -0.86%
      the tape's hip 94cm -> 114cm          area  -0.55%
      the tape's waist 68cm -> 88cm         area  -0.63%

    A 20cm chest — a 23% body — moves the pattern less than a percent, and
    ``scale_cm_per_px`` comes back **byte-identical** at chest 68, 88 and
    108. The calibration's own ``anchor_kind`` says why: ``shoulder_to_waist``.
    Only the shoulder measurement and the shoulder-to-waist vertical span
    reach the scale. Chest, waist and hip circumference never enter it.

    **So this is a scaled copy of a photographed silhouette, not a
    made-to-measure garment**, and that sentence is the one worth pinning.
    An implementation that quietly started fitting the body would move the
    scale and go red here — which is the point: if that ever becomes true,
    it should be because someone changed it deliberately and re-measured,
    not because the claim drifted.

    The photo half is pinned in the same breath. If a future change made
    the outline stop mattering — the failure mode where a photograph is
    decoration over a body-derived block — the hem sweep's spread would
    collapse and this goes red too.
    """
    from photoloset import photo_to_pattern as _p2p
    from photoloset import Measures as _Ms

    W, H, AXIS, Y0, Y1 = 800, 1200, 400.0, 250.0, 1150.0

    def _aline(shoulder=90.0, waist=60.0, hem=160.0, n=240):
        def hw(t):
            if t <= 0.15:
                return shoulder
            if t <= 0.35:
                return shoulder + (waist - shoulder) * (t - 0.15) / 0.20
            return waist + (hem - waist) * (t - 0.35) / 0.65
        pts = []
        for k in range(n + 1):
            t = k / n
            pts.append((AXIS + hw(t), Y0 + (Y1 - Y0) * t))
        for k in range(n, -1, -1):
            t = k / n
            pts.append((AXIS - hw(t), Y0 + (Y1 - Y0) * t))
        return pts

    def _rec(**kw):
        return {"outline": _aline(**kw), "width_px": W, "height_px": H,
                "source": "checks", "fixture": False}

    def _tape(**kw):
        vals = dict(chest=88.0, waist=68.0, hip=94.0,
                    body_length=140.0, shoulder=38.0)
        vals.update(kw)
        m = _Ms()
        for spot, v in vals.items():
            m.measured(spot, v, "cm", source="checks", by="Kodai Motonishi")
        return m

    def _area(r):
        return sum(p.get("area_cm2", 0.0) for p in (r.get("pieces") or []))

    base = _p2p.run(_rec(), _tape())
    b = _area(base)
    scale = (base.get("calibration") or {}).get("scale_cm_per_px")
    anchor = (base.get("calibration") or {}).get("anchor_kind")

    def _sweep_outline(cases):
        """Vary the OUTLINE, hold the tape. Returns {label: area change}."""
        return {lbl: _area(_p2p.run(_rec(**kw), _tape())) / b - 1.0
                for lbl, kw in cases}

    def _sweep_tape(cases):
        """Vary the TAPE, hold the outline. Returns the area changes and
        every distinct scale the calibration produced along the way."""
        moves, seen = {}, set()
        for lbl, kw in cases:
            r = _p2p.run(_rec(), _tape(**kw))
            moves[lbl] = _area(r) / b - 1.0
            seen.add((r.get("calibration") or {}).get("scale_cm_per_px"))
        return moves, seen

    photo = _sweep_outline([("hem_100", {"hem": 100.0}),
                            ("hem_220", {"hem": 220.0}),
                            ("shoulder_70", {"shoulder": 70.0})])
    TAPE_CASES = ("chest_68", "chest_108", "hip_114", "waist_88")
    tape, scales = _sweep_tape([("chest_68", {"chest": 68.0}),
                                ("chest_108", {"chest": 108.0}),
                                ("hip_114", {"hip": 114.0}),
                                ("waist_88", {"waist": 88.0})])

    name = ("the photograph sets the garment's shape and the tape sets "
            "only its scale, and the tape reaches the scale through the "
            "shoulder alone")
    with guard(name):
        check(name,
              base.get("verdict") == "ANSWER"
              and anchor == "shoulder_to_waist"
              # The tape's three circumferences do not reach the scale at
              # all: one value, not four.
              and scales == {scale}
              # ...and barely reach the pattern: under 1% for a 40cm chest
              # range and a 20cm hip.
              #
              # **Read through a literal list of the four keys, not through
              # the dict's own values().** `all()` over an empty iterable is
              # True, so "every tape change moved it under 1%" is also what
              # a sweep that ran zero times reports. Naming the four keys
              # here asks for more than non-emptiness: a sweep that produced
              # four DIFFERENT labels raises KeyError instead of passing
              # quietly. `len(tape) == 4` alone did not do that — it counted
              # the sweep without ever saying what should be in it.
              and len(tape) == 4 and len(photo) == 3
              and len(scales) == 1
              and all(abs(tape[k]) < 0.01 for k in TAPE_CASES)
              # The outline does reach it. Pinning only "the tape is small"
              # would stay green if BOTH went to zero — which is the shape
              # of a chain that stopped depending on its input at all.
              and abs(photo["shoulder_70"]) > 0.05
              and photo["hem_220"] > 0.03 and photo["hem_100"] < -0.03
              and max(photo.values()) - min(photo.values()) > 0.10,
              f'anchor {anchor!r} at {scale} cm/px, unchanged across chest '
              f'68/88/108 and hip 114 ({len(scales)} distinct value); the '
              f'tape moves the pattern by '
              f'{ {k: round(v * 100, 2) for k, v in tape.items()} }% and '
              f'the outline by '
              f'{ {k: round(v * 100, 2) for k, v in photo.items()} }% — '
              f'the photograph sets the shape, the tape only the scale, '
              f'and it reaches the scale through the shoulder alone')


# ---------------------------------------------------------------------------
@declares("no falsifier is defined below the line where the harness "
          "starts running, because one defined there is silently skipped")
def every_falsifier_is_reachable_when_run_as_a_script() -> None:
    """**A mutation added at the bottom of falsifiers.py does not exist.**

    ``tests/falsifiers.py`` ends with ``if __name__ == "__main__": raise
    SystemExit(main(...))``. Python runs module statements in order, so a
    ``WHOLE_SUITE += [...]`` written *after* that block is reached only when
    the file is IMPORTED, never when it is RUN. The entries are in the list
    if you import it and count them, and absent from the run that scores
    them.

    Not hypothetical: three mutations for the hem's shape were appended at
    the end of the file on 2026-08-27 and the suite reported "ran 131 of 131
    whole-suite entries" while ``import falsifiers`` showed 134. Nothing
    said anything was missing — **the count matched itself**, because both
    numbers came from the same truncated list.

    **Why this check reads the source text and then doctors it.** "Nothing
    sits below the line" is a claim about an empty list, and an empty list
    is what a scanner that never appends also produces — `not below` is
    green either way. So the same scanner is run twice: once over the real
    file, which must find nothing, and once over a copy with one table
    statement moved below the guard, which must find exactly that one. A
    scanner that always answers "nothing" fails the second half.
    """
    name = ("no falsifier is defined below the line where the harness "
            "starts running, because one defined there is silently skipped")
    GUARD_LINE = 'if __name__ == "__main__":'

    def below_the_guard(src: str):
        """Table statements that sit after the line that starts the run."""
        at = src.find(GUARD_LINE)
        if at < 0:
            return None
        found = []
        for line in src[at:].splitlines():
            head = line.strip()
            if (head.startswith(("WHOLE_SUITE", "MUTATIONS",
                                 "LOOP_MUTATIONS"))
                    and ("+=" in head or head.endswith("= ["))):
                found.append(head[:60])
        return found

    real = (Path(__file__).parent / "falsifiers.py").read_text(
        encoding="utf-8")
    # The wrong file, built here rather than imagined — appended at the end,
    # which is exactly where the three hem mutations were written before
    # anyone noticed the run could not see them.
    doctored = real.rstrip() + "\n\nWHOLE_SUITE += []\n"

    clean = below_the_guard(real)
    dirty = below_the_guard(doctored)
    with guard(name):
        check(name,
              clean == []
              and dirty is not None and len(dirty) == 1
              and dirty[0].startswith("WHOLE_SUITE +="),
              f'the real file has {clean} below the line that starts the '
              f'run; the same reader over a copy with one table statement '
              f'moved below it finds {dirty} — so "nothing is below" is a '
              f'measurement here, not an empty list that any reader would '
              f'have produced')


# ---------------------------------------------------------------------------
@declares("the flat store moves into a project once and only once",
          "two projects do not see each other",
          "a project name cannot reach outside the store",
          "the fabric book is shared, the garment is not")
def projects_have_their_own_store() -> None:
    """**A list that looks like isolation and is not, is worse than no list.**

    The app grew a project list before the engine had projects. Selecting a
    different garment highlighted the row and changed nothing: _p(name)
    resolved to one flat directory, so every project read and wrote the same
    ledger. Found by clicking, not by reading.
    """
    import importlib
    import json as _json
    import os as _os
    import shutil as _sh
    import tempfile as _tf

    from photoloset import garment_measure as _gm

    home = Path(_tf.mkdtemp(prefix="projchk_"))
    old = _os.environ.get("HOME")
    # **PHOTOLOSET_HOME も外す。** この検査は HOME を差し替えて mcp を
    # 読み直すことで隔離しているが、mcp.HOME は
    # `os.environ.get("PHOTOLOSET_HOME") or (Path.home() / ".photoloset")`
    # で、環境に PHOTOLOSET_HOME が立っていればそちらが勝つ。
    # 2026-08-27、この検査を `PHOTOLOSET_HOME=$(mktemp -d)` の下で回した
    # 作業者が、無関係な5件の偽の赤を受け取った — **隔離の検査自身が、
    # 外から渡された隔離に壊されていた。** 差し替えのあいだだけ外し、
    # 終わったら元に戻す。
    old_ph = _os.environ.pop("PHOTOLOSET_HOME", None)
    _os.environ["HOME"] = str(home)
    try:
        import photoloset.mcp as _mcp
        importlib.reload(_mcp)
        flat = home / ".photoloset"
        flat.mkdir(parents=True)
        ms = _gm.Measures()
        ms.measured("chest", 108.0, "cm", source="checks",
                    by="Kodai Motonishi")
        ms.save(flat / "measures.json")
        (flat / "fabrics.json").write_text("{}", encoding="utf-8")

        with guard("the flat store moves into a project once and only once"):
            first = _json.loads(_mcp.TOOLS["project_current"]())
            moved = sorted(f.name for f in
                           (flat / "projects" / "default").glob("*.json"))
            # A stray json put back afterwards. Without it the mutation
            # "the migration guard stops looking at whether projects/ exists"
            # went MISS: after a migration there is nothing left in HOME to
            # move, so a second guard stopped it anyway and the check could
            # not tell the two apart.
            (flat / "stray.json").write_text("{}", encoding="utf-8")
            _json.loads(_mcp.TOOLS["project_current"]())
            again = sorted(f.name for f in
                           (flat / "projects" / "default").glob("*.json"))
            kept = len(_gm.Measures.load(
                flat / "projects" / "default" / "measures.json").entries)
            check("the flat store moves into a project once and only once",
                  first["project"] == "default"
                  and moved == ["measures.json"] and again == moved
                  and kept == 1 and (flat / "stray.json").exists()
                  and not (flat / "measures.json").exists(),
                  f'measures.json moved to projects/default and the flat copy '
                  f'is gone; a second call left {again} unchanged, the {kept} '
                  f'measurement intact, and a stray json dropped in afterwards '
                  f'was left alone rather than swept in — which is the only '
                  f'thing the projects/ guard is for')

        with guard("two projects do not see each other"):
            _json.loads(_mcp.TOOLS["project_new"]("cape"))
            in_cape = len(_gm.Measures.load(_mcp._p("measures.json")).entries)
            m2 = _gm.Measures()
            m2.measured("waist", 92.0, "cm", source="checks",
                        by="Kodai Motonishi")
            m2.save(_mcp._p("measures.json"))
            after_cape = len(_gm.Measures.load(
                _mcp._p("measures.json")).entries)
            # **The name says "two projects", so the condition has to as
            # well.** The scanner caught the first draft asserting three
            # particular counts while promising a universal.
            written = {"default": "chest", "cape": "waist"}
            seen = {}
            for nm in sorted(written):
                _json.loads(_mcp.TOOLS["project_open"](nm))
                seen[nm] = sorted(
                    e.spot for e in
                    _gm.Measures.load(_mcp._p("measures.json")).entries)
            leaked = {n: seen[n] for n in written if seen[n] != [written[n]]}
            _json.loads(_mcp.TOOLS["project_open"]("default"))
            check("two projects do not see each other",
                  in_cape == 0 and after_cape == 1
                  and not leaked and len(seen) == 2,
                  f'a new project opens with {in_cape} measurements and takes '
                  f'{after_cape} after one is written; walking every project, '
                  f'each holds exactly what was written into it ({seen}) and '
                  f'{len(leaked)} hold anything from another. One shared '
                  f'directory would show both spots in both')

        with guard("a project name cannot reach outside the store"):
            bad = _json.loads(_mcp.TOOLS["project_new"]("../../escape"))
            dot = _json.loads(_mcp.TOOLS["project_new"](".hidden"))
            empty = _json.loads(_mcp.TOOLS["project_new"]("  "))
            good = _json.loads(_mcp.TOOLS["project_new"]("ケープドレス"))
            escaped = (flat / "projects" / ".." / ".." / "escape").resolve()
            check("a project name cannot reach outside the store",
                  bad["verdict"] == "UNKNOWN_PROJECT_NAME_UNUSABLE"
                  and dot["verdict"] == "UNKNOWN_PROJECT_NAME_UNUSABLE"
                  and empty["verdict"] == "UNKNOWN_PROJECT_NAME_UNUSABLE"
                  and good["verdict"] == "ANSWER" and not escaped.exists(),
                  f'"../../escape", ".hidden" and a blank are all '
                  f'{bad["verdict"]}, nothing was created at {escaped}, and a '
                  f'real name still opens — a guard that refused everything '
                  f'would have failed on the last one')

        with guard("the fabric book is shared, the garment is not"):
            _json.loads(_mcp.TOOLS["project_open"]("cape"))
            fab_cape, led_cape = _mcp._p("fabrics.json"), _mcp._p("ledger.json")
            _json.loads(_mcp.TOOLS["project_open"]("default"))
            fab_def, led_def = _mcp._p("fabrics.json"), _mcp._p("ledger.json")
            check("the fabric book is shared, the garment is not",
                  fab_cape == fab_def == flat / "fabrics.json"
                  and led_cape != led_def
                  and led_cape.parent.name == "cape"
                  and led_def.parent.name == "default"
                  and _mcp._SHARED == ("fabrics.json",),
                  f'both projects read {fab_def.name} from the same place, '
                  f'while their ledgers sit in {led_cape.parent.name} and '
                  f'{led_def.parent.name}. What you own is one book; what you '
                  f'observed about this garment is not')
    finally:
        if old is not None:
            _os.environ["HOME"] = old
        if old_ph is not None:
            _os.environ["PHOTOLOSET_HOME"] = old_ph
        import photoloset.mcp as _m2
        importlib.reload(_m2)
        _sh.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
@declares("the flat seams come before the ones that close a loop",
          "the number of in-the-round seams is not a choice")
def a_garment_can_be_sewn_in_some_order() -> None:
    """**"Can a person sew this" is the existence of a valid order.**

    A seam inside an already-closed tube cannot be reached, so construction
    has an order, and whether one exists is computable — no corpus needed.
    Finding it proves constructibility and IS the instruction sheet.
    """
    from photoloset import garment_marks as _mk
    from photoloset import garment_measure as _gm
    from photoloset import garment_pattern as _gp
    from photoloset import garment_sew as _gs
    from photoloset import sewing_order as _so

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0),
                        ("waist", 92.0), ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    built = _gs.build(_mk.apply(_gp.draft(ms)))
    plan = _so.plan(built)

    with guard("the flat seams come before the ones that close a loop"):
        kinds = [o["how"] for o in plan["order"]]
        first_round = kinds.index(_so.ROUND) if _so.ROUND in kinds else len(kinds)
        # A seam is FLAT only while its two sides are still separate pieces.
        # Every flat one must therefore precede every closing one, or the
        # classification was not read off the assembly at all.
        check("the flat seams come before the ones that close a loop",
              plan["verdict"] == "ANSWER"
              and kinds[:first_round] == [_so.FLAT] * first_round
              and set(kinds[first_round:]) <= {_so.ROUND}
              and plan["flat"] == 2 and plan["in_the_round"] == 3
              and plan["steps"] == 5
              and [o["step"] for o in plan["order"]] == [1, 2, 3, 4, 5],
              f'{plan["flat"]} flat then {plan["in_the_round"]} in the round, '
              f'steps {[o["step"] for o in plan["order"]]}; the first closing '
              f'seam is at position {first_round + 1} and nothing flat '
              f'follows it')

    with guard("the number of in-the-round seams is not a choice"):
        # beta = seams - pieces + components is the cycle rank, and a spanning
        # forest is exactly what can be sewn flat. So the count is a property
        # of the garment, not of the order — and an implementation that got
        # MORE than beta would be picking badly. Both bounds are asserted.
        empty = _so.plan({"seams": []})
        junk = _so.plan({"seams": [{"seam": "no arrow here"}]})
        check("the number of in-the-round seams is not a choice",
              plan["in_the_round"] == plan["in_the_round_minimum"] == 3
              and plan["at_the_minimum"] is True
              and len(plan["pieces"]) == 3 and plan["components"] == 1
              and plan["in_the_round_minimum"]
              == plan["steps"] - len(plan["pieces"]) + plan["components"]
              and empty["verdict"] == _so.NO_SEAMS
              and junk["verdict"] == _so.BAD_SEAM
              and plan["formula"].endswith("= 5 − 3 + 1 = 3"),
              f'{plan["formula"]}; the plan uses exactly that many, so no '
              f'other order sews more of it flat. No seams at all is '
              f'{empty["verdict"]}; a label with no ↔ is {junk["verdict"]}')


# ---------------------------------------------------------------------------
# structure.py --- 輪郭からの構造読み取り
@declares("the symmetry axis is measured from the outline, not a "
          "hardcoded constant, and a tilted outline reports a large "
          "residual while a clean one reports zero")
def symmetry_axis_and_residual_are_measured_not_hardcoded() -> None:
    """**The symmetry axis is a measurement, not a guess about where the
    photo was framed.**

    ``_symmetry`` reports ``axis_x_px`` (the median of the per-height
    midpoints) and a residual (how far the outline actually deviates from
    that axis). Two failure shapes are equally plausible: an
    implementation that always answers 0, and one that always answers the
    frame's own horizontal center. Both are pinned by placing the
    outline's own true axis at x=250px in an 800px-wide frame
    (center=400px) -- neither 0 nor the frame center. A second outline,
    identical except sheared sideways by 100px from top to bottom (the
    module's own docstring: a photo taken at an angle produces a large
    residual), must report a residual far above the clean outline's exact
    zero, and an axis that moved but stayed within the range the shear can
    possibly have produced.
    """
    from photoloset import structure as _st

    def _sym_outline(axis: float, hw: float, shear: float = 0.0,
                      n: int = 200, y0: float = 100.0, y1: float = 1000.0):
        pts = []
        for k in range(n + 1):
            t = k / n
            y = y0 + (y1 - y0) * t
            pts.append((axis + hw + shear * t, y))
        for k in range(n, -1, -1):
            t = k / n
            y = y0 + (y1 - y0) * t
            pts.append((axis - hw + shear * t, y))
        return pts

    W, H = 800, 1200
    AXIS, HW, SHEAR = 250.0, 80.0, 100.0
    name = ("the symmetry axis is measured from the outline, not a "
            "hardcoded constant, and a tilted outline reports a large "
            "residual while a clean one reports zero")
    with guard(name):
        clean = _st.from_outline({"outline": _sym_outline(AXIS, HW),
                                   "width_px": W, "height_px": H,
                                   "source": "checks", "fixture": True})
        tilted = _st.from_outline({"outline": _sym_outline(AXIS, HW,
                                                             shear=SHEAR),
                                    "width_px": W, "height_px": H,
                                    "source": "checks", "fixture": True})
        cs, ts = clean["symmetry"], tilted["symmetry"]
        check("the symmetry axis is measured from the outline, not a "
              "hardcoded constant, and a tilted outline reports a "
              "large residual while a clean one reports zero",
              clean["verdict"] == "ANSWER" and tilted["verdict"] == "ANSWER"
              and cs["axis_x_px"] == AXIS
              and cs["residual_mean_px"] == 0.0
              and cs["residual_max_px"] == 0.0
              and AXIS - 1e-6 <= ts["axis_x_px"] <= AXIS + SHEAR + 1e-6
              and ts["residual_mean_px"] > 5.0,
              f'clean outline (true axis={AXIS}px in an {W}px-wide frame, '
              f'center={W / 2}px): reported axis={cs["axis_x_px"]}px, '
              f'residual_mean={cs["residual_mean_px"]}px -- neither the '
              f'literal 0 nor the frame center {W / 2}. The same outline '
              f'sheared {SHEAR}px top-to-bottom: reported axis='
              f'{ts["axis_x_px"]}px (bounded by construction to '
              f'[{AXIS}, {AXIS + SHEAR}]), residual_mean='
              f'{ts["residual_mean_px"]}px vs the clean case\'s exact 0')


@declares("the reported armpit height moves with the notch that produces "
          "it, not a fixed constant")
def armpit_height_tracks_a_moved_notch() -> None:
    """**A landmark is only honest if it moves when its evidence moves.**

    The right-side armpit concavity is placed at a single controlled
    vertex (the "notch"). Moving that vertex down by 0.15 (in height
    fraction, i.e. 150px in this 900px-tall outline) must move the
    reported ``armpit_right.height_fraction`` by the same 0.15 -- this
    follows from height_fraction's own definition, (y - min_y) /
    height_span, with min_y and height_span unchanged by the shift (the
    notch never becomes the outline's own extremum).
    """
    from photoloset import structure as _st

    def _notch_outline(t_notch: float, y0: float = 0.0, y1: float = 1000.0):
        H = y1 - y0

        def y_at(t: float) -> float:
            return y0 + H * t

        right = [(80.0, y_at(0.0)), (140.0, y_at(0.10)),
                  (60.0, y_at(t_notch)), (70.0, y_at(0.60)),
                  (100.0, y_at(0.80)), (130.0, y_at(1.0))]
        left = [(-130.0, y_at(1.0)), (-100.0, y_at(0.80)),
                 (-70.0, y_at(0.60)), (-80.0, y_at(0.0))]
        return right + left

    name = ("the reported armpit height moves with the notch that produces "
            "it, not a fixed constant")
    with guard(name):
        r1 = _st.from_outline({"outline": _notch_outline(0.30),
                                "width_px": 800, "height_px": 1200,
                                "source": "checks", "fixture": True})
        r2 = _st.from_outline({"outline": _notch_outline(0.45),
                                "width_px": 800, "height_px": 1200,
                                "source": "checks", "fixture": True})
        a1 = r1["landmarks"]["armpit_right"]
        a2 = r2["landmarks"]["armpit_right"]
        check("the reported armpit height moves with the notch that "
              "produces it, not a fixed constant",
              r1["verdict"] == "ANSWER" and r2["verdict"] == "ANSWER"
              and "height_fraction" in a1 and "height_fraction" in a2
              and a1["point_index"] == 2 and a2["point_index"] == 2
              and a1["height_fraction"] == 0.30
              and a2["height_fraction"] == 0.45,
              f'notch at t=0.30 -> armpit_right.height_fraction='
              f'{a1["height_fraction"]}; notch moved to t=0.45 (a shift of '
              f'0.15) -> armpit_right.height_fraction='
              f'{a2["height_fraction"]}, a shift of '
              f'{a2["height_fraction"] - a1["height_fraction"]:.4f} -- the '
              f'same vertex (point_index={a2["point_index"]}) both times')


@declares("the armpit-vs-waist-taper bump-fraction boundary is a measured "
          "value, not assumed")
def armpit_bump_threshold_boundary_is_measured() -> None:
    """**A bulge just above the ARMPIT_MIN_BUMP_FRACTION floor is kept; the
    same bulge fractionally smaller is refused as an ordinary waist taper.**

    ``_armpit`` only accepts a concavity as an armpit if the width bulges
    out, before the concavity, by at least ``ARMPIT_MIN_BUMP_FRACTION``
    (5%) of the outline's own max width -- otherwise it looks like a plain
    taper toward the waist, which has the same convex-hull signature (see
    the module docstring). This pins the boundary at the peak width that
    makes rise == bump_floor exactly (measured on this fixture, not
    asserted): peak=85.0px accepts (rise=10.0px == floor 10.0px),
    peak=84.9px refuses (rise=9.8px, 0.2px short).
    """
    from photoloset import structure as _st

    def _bump_outline(peak: float, y0: float = 0.0, y1: float = 1000.0):
        H = y1 - y0

        def y_at(t: float) -> float:
            return y0 + H * t

        right = [(80.0, y_at(0.0)), (peak, y_at(0.10)), (60.0, y_at(0.30)),
                  (90.0, y_at(0.60)), (100.0, y_at(1.0))]
        left = [(-100.0, y_at(1.0)), (-90.0, y_at(0.60)),
                 (-60.0, y_at(0.30)), (-peak, y_at(0.10)), (-80.0, y_at(0.0))]
        return right + left

    name = ("the armpit-vs-waist-taper bump-fraction boundary is a "
            "measured value, not assumed")
    with guard(name):
        found = _st.from_outline({"outline": _bump_outline(85.0),
                                   "width_px": 800, "height_px": 1200,
                                   "source": "checks", "fixture": True})
        refused = _st.from_outline({"outline": _bump_outline(84.9),
                                     "width_px": 800, "height_px": 1200,
                                     "source": "checks", "fixture": True})
        fa = found["landmarks"]["armpit_right"]
        ra = refused["landmarks"]["armpit_right"]
        check("the armpit-vs-waist-taper bump-fraction boundary is a "
              "measured value, not assumed",
              fa["height_fraction"] == 0.30
              and round(fa["preceding_bump"]["rise_px"], 4) == 10.0
              and ra["verdict"] == _st.ARMPIT_NOT_FOUND
              and round(ra["rejected_bump"]["rise_px"], 4) == 9.8
              and round(ra["bump_floor_px"], 4) == 10.0,
              f'peak=85.0px: bulge rises '
              f'{fa["preceding_bump"]["rise_px"]}px against a floor of '
              f'{round(ra["bump_floor_px"], 4)}px -> kept as armpit at '
              f'height_fraction={fa["height_fraction"]}. peak=84.9px '
              f'(0.1px shorter): bulge only rises '
              f'{ra["rejected_bump"]["rise_px"]}px -> refused as '
              f'{ra["verdict"]}, same floor')


@declares("the shoulder search window's upper edge is a measured "
          "boundary, not open-ended")
def shoulder_search_window_boundary_is_measured() -> None:
    """**A knee exactly at SHOULDER_WINDOW_MAX is the shoulder; the same
    knee one hundredth further down is refused, not stretched for.**
    """
    from photoloset import structure as _st

    def _knee_outline(t_knee: float, y0: float = 0.0, y1: float = 1000.0):
        H = y1 - y0

        def y_at(t: float) -> float:
            return y0 + H * t

        right = [(80.0, y_at(0.0)), (80.0, y_at(0.05)), (80.0, y_at(t_knee)),
                  (150.0, y_at(0.60)), (150.0, y_at(1.0))]
        left = [(-150.0, y_at(1.0)), (-150.0, y_at(0.60)),
                 (-80.0, y_at(t_knee)), (-80.0, y_at(0.05)),
                 (-80.0, y_at(0.0))]
        return right + left

    name = ("the shoulder search window's upper edge is a measured "
            "boundary, not open-ended")
    with guard(name):
        at_edge = _st.from_outline({"outline": _knee_outline(0.20),
                                     "width_px": 800, "height_px": 1200,
                                     "source": "checks", "fixture": True})
        past_edge = _st.from_outline({"outline": _knee_outline(0.21),
                                       "width_px": 800, "height_px": 1200,
                                       "source": "checks", "fixture": True})
        s1 = at_edge["landmarks"]["shoulder"]
        s2 = past_edge["landmarks"]["shoulder"]
        check("the shoulder search window's upper edge is a "
              "measured boundary, not open-ended",
              s1.get("height_fraction") == 0.20
              and s2.get("verdict") == _st.SHOULDER_NOT_RESOLVED
              and s2.get("search_window") == [0.0, _st.SHOULDER_WINDOW_MAX],
              f'knee at t=0.20 (== SHOULDER_WINDOW_MAX) -> shoulder found '
              f'at height_fraction={s1.get("height_fraction")}; the same '
              f'knee moved to t=0.21 -> {s2.get("verdict")} over search '
              f'window {s2.get("search_window")}')


@declares("from_outline refuses a missing-contract record, a degenerate "
          "outline, a re-closed outline, a self-crossing outline, and a "
          "non-positive frame by name -- and answers the valid neighbor "
          "of each")
def structural_refusals_fire_on_their_input_and_not_on_a_valid_neighbor() -> None:
    """**Five structural guards in ``_validate``, each pinned against the
    one valid outline that sits right next to what it refuses.**

    A guard that always fires would make the valid rectangle fail too; a
    guard that never fires would make its own refused case become ANSWER.
    Both directions are asserted together so neither failure mode can hide
    behind the other.
    """
    from photoloset import structure as _st

    def _rect(n: int = 5, hw: float = 80.0, y0: float = 0.0,
              y1: float = 1000.0):
        pts = []
        for k in range(n):
            t = k / (n - 1)
            pts.append((hw, y0 + (y1 - y0) * t))
        for k in range(n - 1, -1, -1):
            t = k / (n - 1)
            pts.append((-hw, y0 + (y1 - y0) * t))
        return pts

    VALID = {"outline": _rect(), "width_px": 800, "height_px": 1200,
             "source": "checks", "fixture": True}
    name = ("from_outline refuses a missing-contract record, a degenerate "
            "outline, a re-closed outline, a self-crossing outline, and a "
            "non-positive frame by name -- and answers the valid neighbor "
            "of each")
    with guard(name):
        valid = _st.from_outline(VALID)
        no_outline = _st.from_outline({"width_px": 800, "height_px": 1200})
        not_dict = _st.from_outline([1, 2, 3])
        two_pts = _st.from_outline({**VALID, "outline": [(0.0, 0.0),
                                                           (1.0, 1.0)]})
        nonfinite = _st.from_outline({**VALID, "outline":
                                       _rect()[:-1] + [(float("nan"), 5.0)]})
        closed_dup = _st.from_outline({**VALID,
                                        "outline": _rect() + [_rect()[0]]})
        crossing_pts = _rect()
        crossing_pts[1], crossing_pts[7] = crossing_pts[7], crossing_pts[1]
        crossed = _st.from_outline({**VALID, "outline": crossing_pts})
        bad_frame = _st.from_outline({**VALID, "width_px": 0})
        check("from_outline refuses a missing-contract record, a "
              "degenerate outline, a re-closed outline, a "
              "self-crossing outline, and a non-positive frame by "
              "name -- and answers the valid neighbor of each",
              valid["verdict"] == "ANSWER"
              and no_outline["verdict"] == _st.NO_OUTLINE
              and not_dict["verdict"] == _st.NO_OUTLINE
              and two_pts["verdict"] == _st.BAD_OUTLINE
              and nonfinite["verdict"] == _st.BAD_OUTLINE
              and closed_dup["verdict"] == _st.NOT_CLOSED
              and crossed["verdict"] == _st.SELF_INTERSECTS
              and crossed["count"] == 2
              and bad_frame["verdict"] == _st.BAD_FRAME,
              f'valid rectangle -> {valid["verdict"]}; a record missing '
              f'"outline" -> {no_outline["verdict"]}; a bare list instead '
              f'of a record -> {not_dict["verdict"]}; 2 points -> '
              f'{two_pts["verdict"]}; a non-finite coordinate -> '
              f'{nonfinite["verdict"]}; the same valid outline with its '
              f'own first point appended again -> {closed_dup["verdict"]}; '
              f'two points swapped to force a crossing -> '
              f'{crossed["verdict"]} ({crossed["count"]} crossing pairs); '
              f'width_px=0 -> {bad_frame["verdict"]}')


@declares("the undersampled-outline and too-small-outline refusals fire "
          "at their exact measured boundary, not approximately there")
def numeric_refusal_boundaries_are_measured_not_approximate() -> None:
    """**Two floors in ``_validate``, each pinned one unit either side of
    the line.**

    UNDERSAMPLED trips at fewer than MIN_POINTS (8) vertices -- 7 refuses,
    8 (otherwise identical) answers. TOO_SMALL trips when the outline's
    own bbox height is under MIN_HEIGHT_FRACTION_OF_FRAME (5%) of the
    frame height -- 4.99% refuses, 5.01% answers, on the same shape.
    """
    from photoloset import structure as _st

    def _n_pt_outline(n: int):
        left_n = n // 2
        right_n = n - left_n
        pts = []
        for k in range(right_n):
            t = k / (right_n - 1) if right_n > 1 else 0.0
            pts.append((80.0, 1000.0 * t))
        for k in range(left_n - 1, -1, -1):
            t = k / (left_n - 1) if left_n > 1 else 0.0
            pts.append((-80.0, 1000.0 * t))
        return pts

    def _rect(hw: float, y0: float, y1: float, n: int = 5):
        pts = []
        for k in range(n):
            t = k / (n - 1)
            pts.append((hw, y0 + (y1 - y0) * t))
        for k in range(n - 1, -1, -1):
            t = k / (n - 1)
            pts.append((-hw, y0 + (y1 - y0) * t))
        return pts

    name = ("the undersampled-outline and too-small-outline refusals fire "
            "at their exact measured boundary, not approximately there")
    with guard(name):
        under = _st.from_outline({"outline": _n_pt_outline(7),
                                   "width_px": 800, "height_px": 1200,
                                   "source": "checks", "fixture": True})
        at_min = _st.from_outline({"outline": _n_pt_outline(8),
                                    "width_px": 800, "height_px": 1200,
                                    "source": "checks", "fixture": True})
        H = 1200
        too_small = _st.from_outline({
            "outline": _rect(200.0, 0.0, H * 0.0499),
            "width_px": 800, "height_px": H,
            "source": "checks", "fixture": True})
        just_big_enough = _st.from_outline({
            "outline": _rect(200.0, 0.0, H * 0.0501),
            "width_px": 800, "height_px": H,
            "source": "checks", "fixture": True})
        check("the undersampled-outline and too-small-outline "
              "refusals fire at their exact measured boundary, not "
              "approximately there",
              len(_n_pt_outline(7)) == 7 and len(_n_pt_outline(8)) == 8
              and under["verdict"] == _st.UNDERSAMPLED
              and under["points"] == 7 and under["minimum"] == 8
              and at_min["verdict"] == "ANSWER"
              and too_small["verdict"] == _st.TOO_SMALL
              and round(too_small["height_fraction_of_frame"], 4) == 0.0499
              and just_big_enough["verdict"] == "ANSWER",
              f'7 points -> {under["verdict"]} (points={under["points"]}, '
              f'minimum={under["minimum"]}); the same shape at 8 points -> '
              f'{at_min["verdict"]}. bbox height at 4.99% of the frame -> '
              f'{too_small["verdict"]} (height_fraction_of_frame='
              f'{too_small["height_fraction_of_frame"]}); the same shape '
              f'at 5.01% -> {just_big_enough["verdict"]}')


@declares("each of the six refused topics answers with its own verdict, "
          "not a shared one, and an unknown topic refuses by a different "
          "name than any of them")
def each_refused_topic_answers_by_its_own_name() -> None:
    """**A closed vocabulary, checked as a lookup table, not as a single
    boolean 'refused'.**
    """
    from photoloset import structure as _st

    name = ("each of the six refused topics answers with its own verdict, "
            "not a shared one, and an unknown topic refuses by a different "
            "name than any of them")
    with guard(name):
        by_topic = {t: _st.cannot_answer(t)["verdict"]
                    for t in _st.REFUSED_TOPICS}
        expect = {
            "front_or_back": _st.CANNOT_SIDE,
            "closure": _st.CANNOT_CLOSURE,
            "layering": _st.CANNOT_LAYERING,
            "fabric": _st.CANNOT_FABRIC,
            "seam_position": _st.CANNOT_SEAM,
            "dart_position": _st.CANNOT_DART,
        }
        unknown = _st.cannot_answer("closures")
        check("each of the six refused topics answers with its own "
              "verdict, not a shared one, and an unknown topic "
              "refuses by a different name than any of them",
              by_topic == expect
              and len(set(expect.values())) == 6
              and unknown["verdict"] == _st.NO_SUCH_TOPIC
              and unknown["verdict"] not in expect.values()
              and unknown["known"] == sorted(expect),
              f'{by_topic} -- 6 distinct verdicts for 6 topics; an unknown '
              f'topic ("closures", one letter off "closure") -> '
              f'{unknown["verdict"]}, listing known topics as '
              f'{unknown["known"]}')


@declares("a resolved hem always carries the front/back attribution "
          "refusal, and a top-level refusal carries no landmarks at all")
def hem_always_states_it_cannot_attribute_to_front_or_back() -> None:
    """**CANNOT_HEM_ATTRIBUTION is not conditional on the hem's shape -- it
    is a statement about what a single front view can ever say.**
    """
    from photoloset import structure as _st

    def _rect(n: int = 5, hw: float = 80.0, y0: float = 0.0,
              y1: float = 1000.0):
        pts = []
        for k in range(n):
            t = k / (n - 1)
            pts.append((hw, y0 + (y1 - y0) * t))
        for k in range(n - 1, -1, -1):
            t = k / (n - 1)
            pts.append((-hw, y0 + (y1 - y0) * t))
        return pts

    name = ("a resolved hem always carries the front/back attribution "
            "refusal, and a top-level refusal carries no landmarks at all")
    with guard(name):
        resolved = _st.from_outline({"outline": _rect(), "width_px": 800,
                                      "height_px": 1200, "source": "checks",
                                      "fixture": True})
        refused = _st.from_outline({"outline": [(0.0, 0.0), (1.0, 1.0)],
                                     "width_px": 800, "height_px": 1200,
                                     "source": "checks", "fixture": True})
        attr = resolved["landmarks"]["hem"]["front_back_attribution"]
        check("a resolved hem always carries the front/back "
              "attribution refusal, and a top-level refusal carries "
              "no landmarks at all",
              resolved["verdict"] == "ANSWER"
              and attr["verdict"] == _st.CANNOT_HEM_ATTRIBUTION
              and len(attr["why"]) > 20 and len(attr["how_to_close"]) > 10
              and refused["verdict"] != "ANSWER"
              and "landmarks" not in refused,
              f'a resolved outline\'s hem carries '
              f'front_back_attribution.verdict={attr["verdict"]}; a '
              f'refused outline ({refused["verdict"]}) carries no '
              f'"landmarks" key at all, so the attribution cannot be read '
              f'as though it fired')


@declares("the part instances from_outline emits are consumable by "
          "resemble.per_part and resemble.structure_from, run for real")
def structure_instances_are_consumable_by_resemble() -> None:
    """**structure.py's contract with resemble.py is checked by actually
    running resemble against structure.py's own output, not by asserting
    the shape looks right.**
    """
    from photoloset import resemble as _resemble
    from photoloset import structure as _st

    def _notch_outline(t_notch: float, y0: float = 0.0, y1: float = 1000.0):
        H = y1 - y0

        def y_at(t: float) -> float:
            return y0 + H * t

        right = [(80.0, y_at(0.0)), (140.0, y_at(0.10)),
                  (60.0, y_at(t_notch)), (70.0, y_at(0.60)),
                  (100.0, y_at(0.80)), (130.0, y_at(1.0))]
        left = [(-130.0, y_at(1.0)), (-100.0, y_at(0.80)),
                 (-70.0, y_at(0.60)), (-80.0, y_at(0.0))]
        return right + left

    name = ("the part instances from_outline emits are consumable by "
            "resemble.per_part and resemble.structure_from, run for real")
    _resemble.reset()
    with guard(name):
        res = _st.from_outline({"outline": _notch_outline(0.30),
                                 "width_px": 800, "height_px": 1200,
                                 "source": "checks", "fixture": True},
                                image_id="img1")
        parts = res["instances"]
        ids = sorted(p["instance"] for p in parts)
        _resemble.install_fixture({
            "body:1": [{"aspect": "family", "family": "coat",
                        "corpus": "c", "ref": "R1"}],
            "sleeve:1": [{"aspect": "family", "family": "sleeve",
                          "corpus": "c", "ref": "R2"}]})
        got = _resemble.per_part("photo.jpg", parts, image_id="img1")
        structured = _resemble.structure_from(got, image_id="img1")
        structured_ids = sorted(i["instance"]
                                 for i in structured["instances"])
        check("the part instances from_outline emits are consumable "
              "by resemble.per_part and resemble.structure_from, run "
              "for real",
              res["verdict"] == "ANSWER"
              and ids == ["body:1", "sleeve:1", "sleeve:2"]
              and got["verdict"] == "ANSWER"
              and sorted(got["searched"]["instances"]) == ids
              and sorted(got["searched"]["regions"]) == ids
              and structured["verdict"] == "ANSWER"
              and structured_ids == ["body:1", "sleeve:1"],
              f'structure.py emitted {ids}; resemble.per_part searched '
              f'{sorted(got["searched"]["instances"])} and regioned '
              f'{sorted(got["searched"]["regions"])} -- none dropped; '
              f'resemble.structure_from carried forward {structured_ids} '
              f'(the two the fixture table actually answered for)')
    _resemble.reset()


@declares("from_outline gives byte-identical output for the same outline "
          "called twice")
def from_outline_is_deterministic_for_the_same_outline() -> None:
    """**No hidden clock, counter, or iteration-order dependency.**

    Two structurally-identical but NOT object-identical input dicts (built
    fresh each time, so nothing is shared by reference) must produce
    byte-identical JSON.
    """
    import json as _json

    from photoloset import structure as _st

    def _notch_outline(t_notch: float, y0: float = 0.0, y1: float = 1000.0):
        H = y1 - y0

        def y_at(t: float) -> float:
            return y0 + H * t

        right = [(80.0, y_at(0.0)), (140.0, y_at(0.10)),
                  (60.0, y_at(t_notch)), (70.0, y_at(0.60)),
                  (100.0, y_at(0.80)), (130.0, y_at(1.0))]
        left = [(-130.0, y_at(1.0)), (-100.0, y_at(0.80)),
                 (-70.0, y_at(0.60)), (-80.0, y_at(0.0))]
        return right + left

    def _record():
        return {"outline": _notch_outline(0.30), "width_px": 800,
                "height_px": 1200, "source": "checks", "fixture": True}

    name = ("from_outline gives byte-identical output for the same "
            "outline called twice")
    with guard(name):
        r1 = _st.from_outline(_record(), image_id="img1")
        r2 = _st.from_outline(_record(), image_id="img1")
        s1 = _json.dumps(r1, sort_keys=True)
        s2 = _json.dumps(r2, sort_keys=True)
        check("from_outline gives byte-identical output for the "
              "same outline called twice",
              r1["verdict"] == "ANSWER" and s1 == s2,
              f'two calls on two freshly-built but structurally identical '
              f'records ({len(s1)} bytes of JSON each) are byte-identical: '
              f'{s1 == s2}')


# ---------------------------------------------------------------------------
# garment_marks.py --- 合印・縫い代・布目線
@declares("a known edge reads its stated seam allowance, not a "
          "substituted number")
def a_known_edge_reads_its_stated_seam_allowance() -> None:
    """**A drafted edge whose name IS in SEAM_ALLOWANCE gets exactly that
    width, not a value that merely happens to match.**

    The expected centimetres (1.27 / 0.95 / 0.64 / 2.54 / 0.0) are copied by
    hand from the SEAM_ALLOWANCE table's own entries, not read back as
    ``garment_marks.SEAM_ALLOWANCE[name][0]`` -- comparing ``offset_outline``'s
    output against the very table it reads from would be comparing a value
    with itself, which is exactly the shape this suite's own unfalsifiable
    scan hunts.
    """
    from photoloset import garment_marks as _mk
    from photoloset import garment_measure as _gm
    from photoloset import garment_pattern as _gp

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0),
                        ("waist", 92.0), ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    draft = _gp.draft(ms)

    with guard("a known edge reads its stated seam allowance, not a "
              "substituted number"):
        back = next(p for p in draft["pieces"] if p["name"] == "後身頃")
        off = _mk.offset_outline(back["outline"], back["edges"],
                                 piece_name="後身頃")
        by_edge = {}
        for row in off.get("segment_allowance", []):
            by_edge.setdefault(row["edge"], []).append(row["cm"])
        # Literal cm, hand-copied from the table -- not read back off it.
        expect = {"肩線": 1.27, "脇線": 1.27, "袖ぐり": 0.95,
                  "衿ぐり": 0.64, "裾": 2.54, "中心線": 0.0}
        # Flattened to (edge, cm) pairs rather than checked with a nested
        # any() per edge -- a per-edge list that happened to be empty would
        # make any() vacuously False and silently drop that edge out of
        # `mismatches` without ever comparing a number. `checked` pins how
        # many (edge, cm) pairs were actually scanned, so an empty scan
        # cannot pass as a clean one.
        checked = [(name, v) for name, vals in by_edge.items()
                  if name in expect for v in vals]
        mismatches = {(name, v): expect[name] for name, v in checked
                     if abs(v - expect[name]) > 1e-9}
        check("a known edge reads its stated seam allowance, not a "
              "substituted number",
              draft["verdict"] == "ANSWER" and off["verdict"] == "ANSWER"
              and set(expect) <= set(by_edge)
              and len(checked) == 7 and not mismatches,
              f'後身頃 segment_allowance by edge: '
              f'{ {k: v for k, v in by_edge.items() if k in expect} }; '
              f'expected {expect}; {len(checked)} (edge, cm) pairs '
              f'checked; mismatches {mismatches}')


@declares("an edge name missing from the table refuses by name, not by 0cm")
def an_edge_name_missing_from_the_table_refuses_by_name() -> None:
    """**Panel edges (下辺/右辺/上辺/左辺) are not in SEAM_ALLOWANCE's
    vocabulary. offset_outline must name them and refuse, not fall back to
    an implicit 0.0cm.**

    Pins the exact defect this task fixes: a 0.0cm default cannot be told
    apart, inside ``offset_outline``'s own outward-growth proof, from the
    seam allowance having gone inward -- so a naming-vocabulary gap used to
    surface as ``UNKNOWN_SEAM_ALLOWANCE_WENT_INWARD`` on a perfectly intact
    outline. The typed refusal (UNSTATED) must name every missing edge and
    carry a how_to_close, matching the other 157 refusals' shape.
    """
    from photoloset import garment_marks as _mk
    from photoloset import garment_measure as _gm
    from photoloset import mannequin as _mq
    from photoloset import panels as _pn

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0),
                        ("waist", 92.0), ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    man = _mq.build(ms)
    out = _pn.cut(man, n_panels=4, segments=12, height_steps=8,
                 iterations=800)
    pieces = _pn.to_pieces(out)

    with guard("an edge name missing from the table refuses by name, not "
              "by 0cm"):
        p0 = pieces["pieces"][0]
        off = _mk.offset_outline(p0["outline"], p0["edges"],
                                 piece_name=p0["name"])
        edge_names = sorted(p0["edges"].keys())
        named = set(off.get("edges") or [])
        # It must be the TYPED refusal this task adds, not the old
        # WENT_INWARD verdict the same 0cm default used to produce on this
        # exact input (regression guard against reverting to the default).
        # len(edge_names) pinned: a cut() panel is always a 4-sided quad
        # (下辺/右辺/上辺/左辺), and all() over an empty edge_names would
        # vacuously pass without ever checking that a single edge name is
        # absent from the table.
        check("an edge name missing from the table refuses by name, not "
              "by 0cm",
              off.get("verdict") == _mk.UNSTATED
              and set(edge_names) == named
              and len(edge_names) == 4
              and all(n not in _mk.SEAM_ALLOWANCE for n in edge_names)
              and isinstance(off.get("how_to_close"), str)
              and len(off["how_to_close"]) > 20
              and isinstance(off.get("why"), str) and len(off["why"]) > 20,
              f'panel edges {edge_names}, none in SEAM_ALLOWANCE -> '
              f'{off.get("verdict")} naming {sorted(named)}')


@declares("a refused seam allowance leaves no cut line in the DXF, only "
          "the piece named")
def a_refused_seam_allowance_leaves_no_cut_line_in_the_dxf() -> None:
    """**dxf.to_dxf must not fabricate a cut line for a piece whose seam
    allowance was refused -- that would be the exact "plausible number
    standing in for a refusal" shape this project refuses everywhere else.**

    The chosen behaviour (confirmed by reading, not assumed): the export as
    a whole still answers -- the sewing line, notches and grain for a piece
    are real regardless of whether its seam allowance is known -- but no
    CUT_LINE polyline entity is written for that piece, and the piece is
    named, with the refusal's own verdict, in ``cut_line_missing``.
    """
    from photoloset import dxf as _dxf
    from photoloset import garment_marks as _mk
    from photoloset import garment_measure as _gm
    from photoloset import mannequin as _mq
    from photoloset import panels as _pn

    ms = _gm.Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0),
                        ("waist", 92.0), ("hip", 104.0)]:
        ms.measured(spot, value, "cm", source="checks", by="Kodai Motonishi")
    man = _mq.build(ms)
    out = _pn.cut(man, n_panels=4, segments=12, height_steps=8,
                 iterations=800)
    pieces = _pn.to_pieces(out)
    marked = _mk.apply(pieces)

    with guard("a refused seam allowance leaves no cut line in the DXF, "
              "only the piece named"):
        d = _dxf.to_dxf(marked)
        import re as _re
        cut_polylines = len(_re.findall(r"0\nPOLYLINE\n8\nCUT_LINE\n",
                                        d.get("text", "")))
        # Bare names, scanned directly (rather than re-reading d[...] at
        # each use site), so a pin on the name's own length is the SAME
        # iterable the scan below runs over -- not a differently-spelled
        # reference to it.
        dxf_pieces = d.get("pieces", [])
        missing_rows = d.get("cut_line_missing", [])
        missing_names = {row["piece"] for row in missing_rows}
        piece_names = {p["name"] for p in marked["pieces"]}
        cut_vertices_reported = sum(
            p.get("cut_vertices", 0) for p in dxf_pieces)
        # Both scans are pinned to the real panel count (4): an empty
        # dxf_pieces would make "every piece reports 0 cut vertices"
        # vacuously true (no cut line was ever counted, let alone found
        # absent), and an empty missing_rows would make all() over it
        # vacuously True without ever checking a single piece's refusal
        # verdict.
        check("a refused seam allowance leaves no cut line in the DXF, "
              "only the piece named",
              d.get("verdict") == "ANSWER"
              and cut_polylines == 0
              and len(dxf_pieces) == 4
              and all(p.get("cut_vertices", 0) == 0 for p in dxf_pieces)
              and len(missing_rows) == 4
              and missing_names == piece_names
              and all(row["verdict"] == _mk.UNSTATED
                      for row in missing_rows),
              f'dxf verdict {d.get("verdict")}; {cut_polylines} CUT_LINE '
              f'polyline entities written (0 expected); cut_line_missing '
              f'names {sorted(missing_names)} of {sorted(piece_names)} '
              f'pieces, each {_mk.UNSTATED}')


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
               a_body_becomes_a_flat_pattern_by_geometry,
               a_silhouette_constrains_only_the_projected_width,
               the_flattened_tube_becomes_panels,
               the_marker_says_how_much_fabric,
               a_garment_can_be_sewn_in_some_order,
               the_hem_shape_is_measured_across_the_whole_bottom,
               every_falsifier_anchor_still_exists,
               the_photograph_sets_the_shape_and_the_tape_sets_the_scale,
               every_falsifier_is_reachable_when_run_as_a_script,
               projects_have_their_own_store,
               the_bom_says_what_to_buy,
               the_falsifier_harness_reports_everything,
               symmetry_axis_and_residual_are_measured_not_hardcoded,
               armpit_height_tracks_a_moved_notch,
               armpit_bump_threshold_boundary_is_measured,
               shoulder_search_window_boundary_is_measured,
               structural_refusals_fire_on_their_input_and_not_on_a_valid_neighbor,
               numeric_refusal_boundaries_are_measured_not_approximate,
               each_refused_topic_answers_by_its_own_name,
               hem_always_states_it_cannot_attribute_to_front_or_back,
               structure_instances_are_consumable_by_resemble,
               from_outline_is_deterministic_for_the_same_outline,
               a_known_edge_reads_its_stated_seam_allowance,
               an_edge_name_missing_from_the_table_refuses_by_name,
               a_refused_seam_allowance_leaves_no_cut_line_in_the_dxf,
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
