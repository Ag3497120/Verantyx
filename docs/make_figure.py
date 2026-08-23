"""Render the README pattern figure.

The geometry is exactly what `garment_pattern.to_svg` produces — this script
only relabels it. The tool's own labels are Japanese today; the README is in
English, so the piece names and the legend are swapped and the long Japanese
note is dropped (the README carries the same caveats in English).

    python3 docs/make_figure.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from photoloset import Measure, Measures
from photoloset import garment_marks, garment_pattern

LABELS = {
    "たて地": "grain",
    "後身頃": "back bodice",
    "前身頃": "front bodice",
    "袖": "sleeve",
}
LEGEND = ("solid = sewing line   dashed = cut line   "
          "blue = notch (single front, double back)   green = grain   "
          "scale 1:1 in cm")


def main() -> None:
    ms = Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0)]:
        ms.entries.append(Measure(
            spot=spot, kind="measured", value=value, unit="cm",
            basis="reference coat, laid flat",
            source="tape measure", by="Kodai Motonishi"))

    draft = garment_pattern.draft(ms)
    marks = garment_marks.apply(draft)
    svg = garment_pattern.to_svg(marks)

    texts = list(re.finditer(r"<text([^>]*)>(.*?)</text>", svg, re.S))
    # The legend is the first line that is not a piece label; everything from
    # there on is prose, and prose is the README's job.
    keep_upto = next(i for i, m in enumerate(texts) if "実線" in m.group(2))
    legend_y = float(re.search(r'y="([\d.]+)"', texts[keep_upto].group(1)).group(1))

    out = svg
    for m in reversed(texts[keep_upto:]):
        out = out[:m.start()] + out[m.end():]
    for ja, en in LABELS.items():
        out = out.replace(f">{ja}<", f">{en}<")

    height = legend_y + 12
    out = re.sub(r'height="[\d.]+" viewBox="0 0 ([\d.]+) [\d.]+"',
                 lambda m: f'height="{height:.0f}" viewBox="0 0 {m.group(1)} {height:.0f}"',
                 out, count=1)
    attrs = re.search(r'<text([^>]*)>', svg).group(1)
    attrs = re.sub(r'x="[\d.]+"', 'x="12"', attrs)
    attrs = re.sub(r'y="[\d.]+"', f'y="{legend_y:.1f}"', attrs)
    attrs = re.sub(r'font-size="[\d.]+"', 'font-size="3.2"', attrs)
    attrs = re.sub(r'fill="[^"]*"', 'fill="#555"', attrs)
    out = out.replace("</svg>", f'<text{attrs}>{LEGEND}</text>\n</svg>')

    dest = Path(__file__).resolve().parent / "pattern.svg"
    dest.write_text(out, encoding="utf-8")
    print(f"wrote {dest}  ({len(out)} bytes)")
    print(f"pieces: {[p['name'] for p in draft['pieces']]}")
    print(f"area:   {draft['total_area_cm2']} cm2")


if __name__ == "__main__":
    main()
