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
    "0 untranslated",
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
    "initialize",
    "42 tools",
    "every tool has a schema",
    "every tool returns an object",
    "absent tools say so",
    "anonymous adoption refused",
    "no check that cannot fail",
    "the falsifier harness reports every mutation",
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
    check("default stitch_k leaves it open", not loose["closed"],
          f'worst {loose["worst"]} cm, {loose["over_tolerance"]}/'
          f'{loose["stitches"]} over tolerance')
    tight = garment_sew.sew_and_drape(built, mat, iterations=2000,
                                      stitch_k=20.0 * 64)["seam_gap"]
    check("64x closes it", tight["closed"] and tight["over_tolerance"] == 0,
          f'worst {tight["worst"]} cm, {tight["over_tolerance"]} over')


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
    outs["cross.link.dangling"] = _st.link(("nope", ""), ("c", ""), "nest")
    outs["parts.unbought_generics"] = _parts.Library().unbought_generics()
    outs["zones.parse_selection.bad"] = _zones.parse_selection("99", {})
    outs["prompts.parse.bad"] = _prompts.parse_decomposition("default",
                                                             "{oops")

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
          not total_missing and len(swept) == 30,
          f"{len(set(total_missing))} strings across {len(swept)} outputs")

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
        check("initialize", init["serverInfo"]["name"] == "photoloset",
              f'{init["serverInfo"]["name"]} {init["protocolVersion"]}')
        tools = rpc("tools/list")["result"]["tools"]
        check("42 tools", len(tools) == 42, f"{len(tools)}")
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
        check("every tool has a schema",
              len(tools) == 42 and not no_schema and not no_props,
              f"{len(tools)} schemas derived from the signatures, "
              f"{len(no_schema)} not an object, {len(no_props)} without "
              "properties"
              + (f" — {no_schema + no_props}" if no_schema or no_props
                 else ""))

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
              len(tools) == 42 and not not_object and not crashed,
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
                           r"copy|time|datetime|hashlib|struct|unicodedata|"
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
          len(scanned) == 26 and not third_party,
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
              and set(cross.ARMS) == set(want),
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
              and drift["differences"],
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
              and skirt_served["placement"] == v_s2.placement()
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
              and len(walked) == 56 and every,
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
              and got["verdict"] == "ANSWER" and got["weight"] == 2
              and cen_b["support+"] == 1 and cen_b["cause+"] == 1
              and "UNKNOWN_NO_SUPPORT_RECORDED" not in both.gaps("m")
              and "UNKNOWN_NO_CAUSE_RECORDED" not in both.gaps("m")
              and twice.load_verdict["verdict"] == cross.DUPLICATE_CLAIM,
              f'one address, measured AND derived, sits on '
              f'{cross.seat_arms(seat)} — 1 address, weight '
              f'{got["weight"]}, and neither the support gap nor the cause '
              f'gap is reported; a store seating the same (kind, value) '
              f'twice loads as {twice.load_verdict["verdict"]}')

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
          'the budget arm is reported, never hidden')
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
              and names[0] != names[1] and len(names[0]) == len(names[1]),
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
              and core_local == []
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
        # ...and the other direction: a value that is not equal to itself is
        # not a rival to itself.
        nan = cross.CrossStore()
        nan.put("c", "k", float("nan"), "declared", "same source")
        nan.put("c", "k", float("nan"), "declared", "same source")
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
              and nan.contested() == []
              and nan.resolve("c", "k")["verdict"] == "ANSWER"
              and agree.resolve("c", "k")["verdict"] == "ANSWER"
              and agree.resolve("c", "k")["weight"] == 2,
              'True/1, 108.0/108, 0/False and {required: True}/{required: 1} '
              'each CONTEST rather than merging one into the other — at the '
              'writer AND at resolve(), contested() and the support- arm; '
              f'NaN put twice does not contest with itself '
              f'({len(nan.contested())} contests); 108.0 twice is still '
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
        # A core NAMED as quarantine takes armed writes too — that is how
        # the 44-seat core was built — so this is where the total is
        # measured: 5 writable arms x 4 faces = 20 armed seats, then
        # proposals fill it to exactly 24, then the next seat of ANY kind
        # is refused because the core itself is full.
        mixed = cross.CrossStore()
        for i in range(cross.FACES_PER_ARM):
            for kind in ("measured", "derived", "feeds", "specific",
                         "generic"):
                mixed.put_strict("m#proposed", f"{kind}{i}", float(i), kind,
                                 "a source")
        mixed_seats = len(mixed.cores["m#proposed"])
        spill = [mixed.put_strict("m#proposed", f"extra{i}", float(i),
                                  "proposed", "said")["verdict"]
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
              and spill == ["ANSWER"] * 4 + [cross.ARM_FULL]
              and len(mixed.cores["m#proposed"]) == cross.CAPACITY_PER_CORE
              and mixed.census()["over_capacity"] == []
              and loaded_mixed.load_verdict["verdict"] == cross.OVER_CAPACITY
              and ("m", "total", 25) in loaded_mixed.census()["over_capacity"],
              f'100 proposals nest into {len(sizes)} cores of {sizes} rather '
              f'than one core of 100; the strict writer refuses the 25th '
              f'({refused["verdict"]}); a hand-written 25-seat quarantine '
              f'core loads as {hand.load_verdict["verdict"]} and census() '
              f'names all {sum(cen_q["quarantined"].values())} quarantined '
              f'seats so the exemption cannot be silent; a core holding '
              f'{mixed_seats} armed seats takes 4 proposals and then refuses '
              f'the 25th seat of ANY kind ({spill[-1]}) because 1 core = 24 '
              f'seats counts every seat, and a 25-seat mixed core loads as '
              f'{loaded_mixed.load_verdict["verdict"]}')

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
        # ...and a core whose name merely CONTAINS the marker is not
        # quarantine: a rumour written there must not contest a measurement.
        look = "review#proposed-revisions"
        n = cross.CrossStore()
        n.put(look, "measure:chest", 108.0, "measured", "tape")
        rumour = n.put(look, "measure:chest", 999.0, "proposed",
                       "a rumour in the studio")
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
              and not cross._is_quarantine(look)
              and not cross._is_quarantine("notes#proposedX")
              and cross._is_quarantine("q#proposed")
              and cross._is_quarantine("q#proposed·proposed·1")
              and rumour["core"] == look + "#proposed"
              and n.contested() == []
              and n.resolve(look, "measure:chest")["verdict"] == "ANSWER"
              and lost.load_verdict["verdict"] == cross.ORPHANED_CORE
              and spilled["verdict"] == cross.DANGLING_EDGE
              and "c·kind-·1" not in nl.cores,
              f'30 proposals written back to the core put() itself returned '
              f'nest into {sorted(w.cores)} with {nests} nest edge — not a '
              f'"{home}#proposed" nobody created — so two rival hems at one '
              f'address answer {rival["verdict"]} instead of two ANSWERs the '
              f'reader cannot see; a core merely NAMED {look!r} is not '
              f'quarantine, so a rumour is isolated in '
              f'{rumour["core"]!r} and the measurement still reads '
              f'{n.resolve(look, "measure:chest")["verdict"]}; a child whose '
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
              f'second source buys it; a loaded store whose generic claim '
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
        kinds = {name: keep.put("c", f"k:{name}", v, "measured", "x")["verdict"]
                 for name, v in (("set", {1, 2}),
                                 ("frozenset", frozenset({1, 2})),
                                 ("bytes", b"108"),
                                 ("int-keyed dict", {1: "a"}),
                                 ("nested", {"a": [1, {2: "b"}]}))}
        ok_kinds = {name: keep.put("c", f"ok:{name}", v, "measured",
                                   "x")["verdict"]
                    for name, v in (("tuple", (0.0, 1.0, 2.0)),
                                    ("float", 108.0), ("bool", True),
                                    ("none", None),
                                    ("dict", {"required": True}))}
        try:
            _json.dumps(keep.to_dict())
            persists = True
        except TypeError:
            persists = False
        loaded = cross.CrossStore.from_dict({"cores": {"c": [
            {"key": "k", "arm": "support+", "seq": 1,
             "values": [{"value": {1: "a"}, "kind": "measured",
                         "sources": ["x"]}]}]}, "edges": []})
        check("the store refuses what it cannot persist",
              cm["verdict"] == cross.UNIDENTIFIABLE_VALUE
              and inch["verdict"] == cross.UNIDENTIFIABLE_VALUE
              and set(kinds.values()) == {cross.UNIDENTIFIABLE_VALUE}
              and set(ok_kinds.values()) == {"ANSWER"}
              and persists
              and loaded.load_verdict["verdict"]
              == cross.UNIDENTIFIABLE_VALUE,
              f'two Length objects whose repr is the same string — '
              f'Length(108, "cm") and Length(108, "in") — are '
              f'{cm["verdict"]} at the writer rather than one merged '
              f'ANSWER of weight 2 carrying whichever unit arrived first; '
              f'{len(kinds)} shapes the JSON form cannot hold are refused '
              f'and {len(ok_kinds)} that it can are seated, so '
              f'json.dumps(to_dict()) holds ({persists}); a hand-written '
              f'store carrying one loads as {loaded.load_verdict["verdict"]}')

    with guard('a generic claim is priced by its own kind'):
        # --- #0 residual: the GATE was not fooled, the READ was ------------
        pr = cross.CrossStore()
        pr.put("c", "k", 1, "generic", "a textbook")
        pr.put("c", "k", 1, "specific", "this coat's own sheet")
        r = pr.resolve("c", "k")
        check("a generic claim is priced by its own kind",
              r["weight"] == 2
              and r["weight_by_kind"] == {"generic": 1, "specific": 1}
              and [g["weight"] for g in pr.unbought_generics()] == [1]
              and sorted(r["kinds"]) == ["generic", "specific"],
              f'one generic source plus one specific source reads as weight '
              f'{r["weight"]} across kinds, but the number '
              f'GENERIC_MIN_SOURCES prices is now beside it — '
              f'{r["weight_by_kind"]} — and matches what the gate says '
              f'({[g["weight"] for g in pr.unbought_generics()]})')

    with guard('the budget arm is reported, never hidden'):
        # --- #1 residual: WHO PAYS THE FACE IS STILL THE WRITER'S ORDER ----
        # This check does not decide the question — it holds the store to
        # SAYING SO. The three ways out are written into cross._arm_load and
        # into README.md; whichever is chosen, this check changes with it.
        bud = cross.CrossStore()
        for i in range(cross.FACES_PER_ARM):
            bud.put_strict("c", f"k{i}", float(i), "measured", "tape")
        direct = bud.put_strict("c", "k5", 99.0, "measured", "tape")
        first = bud.put_strict("c", "k5", 99.0, "derived", "the formula")
        second = bud.put_strict("c", "k5", 99.0, "measured", "tape")
        cen = bud.census()
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
              and len(cen["uncharged"]) == 1
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
              f'alone. THE COAT HAS {len(coat_cen["two_kind_addresses"])} '
              f'two-kind addresses, so no answer moves today — the choice '
              f'among (a) canonical ARMS order, (b) charge every arm, '
              f'(c) refuse the second kind is the owner\'s, and cross.py '
              f'_arm_load says what each one costs')


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
    check("unknown variant refused", a["verdict"] == "UNKNOWN_NO_SUCH_VARIANT",
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
          and tuple(view.required()) == ("waist", "hip", "skirt_length"),
          f'{cen["cores"]} cores, {cen["facets"]} facets')

    d = garment_skirt.draft(ms, view)
    check("skirt drafts through the shared engine",
          d["verdict"] == "ANSWER"
          and [p["name"] for p in d["pieces"]] == ["前身頃", "後身頃"],
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
          and gap["over_tolerance"] == 0,
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
    check("unknown part refused", a["verdict"] == "UNKNOWN_NO_SUCH_PART",
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
          and len(seam_checks) == 10 and not bad,
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
          gap["closed"] and gap["over_tolerance"] == 0,
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
    check("zones are numbered deterministically",
          len(z1) == 10 and z1 == r2.get("zones")
          and [z["id"] for z in z1] == list(range(1, 11)),
          f'{len(z1)} zones, e.g. '
          f'{[(z["id"], z["label"]) for z in z1[:3]]}…')

    a = zones.apply(dress, {"1": 1.5, "7": 0.1})
    applied = a.get("applied", [])
    r3 = compose.compose(a["graph"], ms)
    area = round(sum(p["area_cm2"] for p in r3.get("pieces", [])), 1)
    check("applying a delta records what changed",
          a["verdict"] == "ANSWER" and len(applied) == 2
          and applied[0]["was"] == "既定" and applied[0]["now"] == 1.5
          and r3["verdict"] == "ANSWER",
          f'zone1 chest_ease 既定→{applied[0]["now"]}, '
          f'zone7 flare +{applied[1]["delta"]} — area {area} cm2')

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
          gap["closed"] and gap["over_tolerance"] == 0,
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
          and "zones" not in coat,
          f'legacy drafting keeps its byte-identical shape: '
          f'{coat["verdict"]}, {len(coat["pieces"])} pieces, '
          f'{coat["total_area_cm2"]} cm2, no zones key')


# ---------------------------------------------------------------------------
#: **The checks that cannot fail, and why each one is allowed to stand.**
#: ``tests/unfalsifiable.py`` reads every ``check()`` condition in this file
#: and reports the shapes that make a line green no matter what the code
#: does. This project shipped EIGHT of those in four separate passes, each
#: found by somebody looking harder — a method that does not scale. So the
#: sweep is a check of its own now, and the residue is enumerated here with
#: the argument for keeping it. **A hit that is not on this list turns the
#: suite red**, which is the whole point: the next one has to be argued in a
#: diff rather than discovered in six months.
KNOWN_UNFALSIFIABLE = [
    ("T1", "round trip moves nothing", "borderline",
     "Two calls of `.dump()` on two receivers IS the shape — but the same "
     "condition now pins the served sections by name, the formula and seam "
     "counts, and `len(b.dump()) > 2000` against literals, so a section "
     "vanishing from served() cannot drop out of both sides unnoticed. The "
     "tool downgrades it to borderline for exactly that reason. Falsifier: "
     "'#17 served() quietly stops carrying the formulas'."),
    ("T2", "a contest survives the matryoshka", "borderline",
     "The any() is a FILTER inside a list comprehension, not the assertion, "
     "and it is vacuously FALSE on empty — the direction that makes a check "
     "fail rather than pass. The tool says so itself."),
    ("T2", "equal is not the same observation", "borderline",
     "Same shape, same safe direction: a vacuously FALSE any() inside a "
     "comprehension. The genuine quantifier beside it, all(listed), carries "
     "`len(listed) == 4` in the same condition."),
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
    then 5-6, then 7-8. Every pass someone looked harder and found more.
    Looking harder is not a method — this is. ``tests/unfalsifiable.py``
    reads the AST of every ``check()`` in this file and reports the shapes
    that cannot go red; the residue is pinned in ``KNOWN_UNFALSIFIABLE``
    with an argument each, and anything new fails here.

    What it cannot see is printed by the tool itself and worth repeating:
    it reads CONDITIONS, so a perfectly shaped check whose callee answers
    from a cache is invisible to it, and so is a property nobody wrote a
    check for at all.
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
    unpinned = out.get("unpinned_readers", [])
    check("no check that cannot fail",
          out.get("verdict") == "ANSWER"
          and not out.get("unscanned")
          and out.get("checks_with_a_condition", 0) >= 85
          and len(known) == 4 and len(KNOWN_UNFALSIFIABLE) == 4
          and len(got) == len(KNOWN_UNFALSIFIABLE)
          and not new_hits and not gone
          and not unpinned,
          f'{out.get("checks_with_a_condition")} conditions swept, '
          f'{len(hits)} hits — all {len(KNOWN_UNFALSIFIABLE)} of them on '
          f'the record with a reason; {len(out.get("readers", []))} served '
          f'readers, {len(unpinned)} of them pinned to nothing; '
          f'{len(out.get("unscanned", []))} detectors refused'
          + (f' — NEW {new_hits}' if new_hits else '')
          + (f' — NO LONGER FIRING (delete it from the list) {gone}'
             if gone else '')
          + (f' — UNPINNED READERS {[r["method"] for r in unpinned]}'
             if unpinned else ''))


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
               the_mcp_server_answers,
               no_check_can_pass_by_construction,
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
