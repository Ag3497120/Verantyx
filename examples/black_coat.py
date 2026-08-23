"""End to end: a coat on screen becomes a pattern, or the tool says why it cannot.

    python3 examples/black_coat.py

Nothing here is invented. Every number is typed in with the person who measured
it and the thing they measured it on. The tool's job is to keep that link, and
to stop when the link is missing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from photoloset import Ledger, Measures
from photoloset import garment_marks, garment_pattern, garment_sew

WHO = "Kodai Motonishi"


def rule(title: str) -> None:
    print(f"\n{'-' * 68}\n{title}\n{'-' * 68}")


# --------------------------------------------------------------------------
rule("1. A vision model reads one frame and proposes")

ledger = Ledger(title="Black Coat")
ledger.propose("collar", "shape", "notched lapel",
               source="vision model, frame t001.89",
               ref_path="frames/t001.89.jpg", ref_mark="t001.89")
ledger.propose("pocket", "existence", "flap pocket",
               source="vision model, frame t001.89",
               ref_path="frames/t001.89.jpg", ref_mark="t001.89")

for part, aspect in [("collar", "shape"), ("pocket", "existence")]:
    print(f"  {part}/{aspect} -> {ledger.state(part, aspect)['state']}")
print("\n  Proposals are stored. They are not facts, and the drafting step")
print("  never reads them.")


# --------------------------------------------------------------------------
rule("2. A person adopts, by name")

try:
    ledger.adopt("collar", "shape", "notched lapel", by="")
except ValueError as e:
    print(f"  anonymous adoption -> refused")
    print(f"    {e}")

entry = ledger.adopt("collar", "shape", "notched lapel", by=WHO)
state = ledger.state("collar", "shape")
print(f"\n  collar/shape -> {state['state']}, adopted by {entry.adopted_by}")
print(f"  sources      {state['sources']}")
print("\n  A fact has an owner. That is the whole difference between step 1")
print("  and step 2.")


# --------------------------------------------------------------------------
rule("3. What has not been observed yet")

work = ledger.worklist()
print(f"  {len(work)} aspects are UNKNOWN_NOT_OBSERVED. The first three:")
for item in work[:3]:
    print(f"    {item['part']}/{item['aspect']:12} {item['state']}")
    print(f"      how to close: {item['how_to_close']}")
print("\n  An unknown is a result, not an error. It comes with the action")
print("  that would close it.")


# --------------------------------------------------------------------------
rule("4. Four numbers off a tape")

ms = Measures()
for spot, value in [("body_length", 112.0), ("chest", 108.0),
                    ("shoulder", 46.0), ("sleeve_length", 46.0)]:
    ms.measured(spot, value, "cm", source="tape measure, reference coat laid flat",
                by=WHO)
for m in ms.entries:
    print(f"  {m.spot:14} {m.value:6.1f} {m.unit}   by {m.by}")
print("\n  Footage has no scale in it. These come off a real garment.")


# --------------------------------------------------------------------------
rule("5. The same spot, measured twice, disagreeing")

ms.measured("sleeve_length", 63.0, "cm",
            source="tape measure, the real coat measured again", by=WHO)
state = ms.state("sleeve_length")
print(f"  sleeve_length -> {state['state']}")
for side in state["sides"]:
    print(f"    {side['value']:6.1f} {side['unit']}   {side['source']}")
print(f"  tolerance     {state['tolerance_cm']} cm")
print(f"  how to close  {state['how_to_close']}")
print("\n  It will draft a sleeve from 46, and it will draft one from 63.")
print("  It will not draft one from two, and it does not pick the first.")


# --------------------------------------------------------------------------
rule("6. Draft")

ms.entries = [m for m in ms.entries
              if not (m.spot == "sleeve_length" and m.value == 46.0)]
draft = garment_pattern.draft(ms)
print(f"  verdict     {draft['verdict']}")
print(f"  units       converted to {draft['units']['converted_to']}, "
      f"unknown units: {draft['units']['unknown_unit'] or 'none'}")
print(f"  pieces      {[p['name'] for p in draft['pieces']]}")
print(f"  total area  {draft['total_area_cm2']} cm2")
print(f"  formulas    {len(draft['formulas'])} printed in the output")
for c in draft["seam_checks"]:
    tag = "structural, proves nothing" if c.get("structural") else "a real test"
    print(f"  seam check  {c['label']:10} diff {c['difference']:5.2f} cm  [{tag}]")


# --------------------------------------------------------------------------
rule("7. Notches, seam allowance, grain")

marks = garment_marks.apply(draft)
n_notch = sum(len(v) for v in marks["notches"].values())
print(f"  notches     {n_notch} across {len(marks['notches'])} pieces, "
      f"{len(marks['notch_pairs'])} paired, {len(marks['notch_unpaired'])} unpaired")
print(f"  grain       {len(marks['grain'])} pieces carry a grain line")
print("  allowance   per edge, with the imperial equivalent printed:")
for edge, spec in list(garment_marks.SEAM_ALLOWANCE.items())[:4]:
    print(f"                {edge:14} {spec[0]:5.2f} cm  ({spec[1]})")
print("\n  Seam allowance is not stored as a number. It is the offset between")
print("  the cut line and the sewing line, so the two cannot disagree.")


# --------------------------------------------------------------------------
rule("8. Sew it and let it fall")

material = {
    "verdict": "ANSWER", "fabric": "wool melton",
    "gsm": 420.0, "thickness": 0.18, "stiffness": 20.0,
    "source": "supplier spec sheet",
}
built = garment_sew.build(draft, marks=marks)
print(f"  mesh        {len(built['points'])} points, {len(built['edges'])} edges, "
      f"{len(built['seams'])} seams")

# The engine default is STITCH_STIFFNESS_RATIO = 16. Measured on this
# three-piece garment that is not enough — the worst stitch stays 0.91 cm
# open, 15 of 41 past tolerance. Thread is far stiffer than cloth, so say so
# explicitly rather than accept a seam the tool itself reports as not closed.
drape = garment_sew.sew_and_drape(built, material, iterations=2000,
                                  stitch_k=material["stiffness"] * 64.0)
gap = drape["seam_gap"]
print(f"  verdict     {drape['verdict']}")
print(f"  stopped     after {drape['iterations']} of "
      f"{drape['iterations_cap']} iterations")
print(f"  worst gap   {gap['worst']} cm across {gap['stitches']} stitches")
print(f"  over tol.   {gap['over_tolerance']}")
print(f"  closed      {gap['closed']}")


# --------------------------------------------------------------------------
rule("9. Pattern out, at 1:1")

svg = garment_pattern.to_svg(marks)
out = Path(__file__).resolve().parent / "black_coat.svg"
out.write_text(svg, encoding="utf-8")
print(f"  wrote       {out.name}  ({len(svg)} bytes)")
print("  layers      cut line, notch, grain, sewing line — 1:1 in cm")
print("\n  The draped shape is generated. It is not evidence and cannot be")
print("  cited as an observation; the tool says so in its own output.")
