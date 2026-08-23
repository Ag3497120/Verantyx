"""Render the README pattern figure in English.

The geometry comes straight from `garment_pattern.to_svg`; `i18n.svg` swaps the
labels and re-wraps the notes for English line lengths. Nothing here relabels
anything by hand — if the figure is wrong, the translation table is wrong.

    python3 docs/make_figure.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from photoloset import Measure, Measures, i18n
from photoloset import garment_marks, garment_pattern


def main() -> None:
    ms = Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0)]:
        ms.measured(spot, value, "cm",
                    source="tape measure, reference coat laid flat",
                    by="Kodai Motonishi")

    draft = garment_pattern.draft(ms)
    marks = garment_marks.apply(draft)
    svg = i18n.svg(garment_pattern.to_svg(marks), "en")

    dest = Path(__file__).resolve().parent / "pattern.svg"
    dest.write_text(svg, encoding="utf-8")
    left = i18n.missing(svg)
    print(f"wrote {dest}  ({len(svg)} bytes)")
    print(f"pieces: {[p['name'] for p in draft['pieces']]}")
    print(f"area:   {draft['total_area_cm2']} cm2")
    print(f"untranslated: {left or 'none'}")


if __name__ == "__main__":
    main()
