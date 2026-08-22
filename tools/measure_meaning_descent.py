"""Meaning descent over the shallow-shelf post-measurement holes (W2b).

Protocol (SPEC_2026-08-14_eight_gaps W2b). The measured target is the
remaining coverage holes from `tools/measure_shallow_after.py`: the
same frozen 200 probes (`probes_200.json`), the same atlas + 浅層wiki
shelf, the same one-hop aliases. A probe is a hole when
`closing_domains(..., aliases=aliases)["coverage_hole"]` is True.
That protocol is not changed; the hole list is recomputed here.

For each hole subject, `descend` decomposes via the lattice and
fetches each unit's sidecar definition. Counts are the three-way
split the spec asked for:

    full      every first-level unit has a definition
    partial   some do, some are named in ungrounded_units
    none      no first-level unit has a definition

Baseline is 0 — the wiring did not exist. Five verbatim payloads
(mix of full / partial) are printed for designer eyeballing.

Lattice words = writer vocabulary ∪ definition titles of length 2–5,
so a unit that has a sentence can be a split point. Sidecar only;
no LLM.

## Measured — probes_200 holes_after_shelf, 2026-08-14

    holes_after_shelf                    91
    holes_after_shelf_and_aliases        83
    baseline                              0
    full                                 81
    partial                               0
    none                                 10
    verdicts
        EXPLAINED_BY_UNIT_DEFS           81
        UNGROUNDED_UNITS                  9
        ABSTAIN_BARE_SUFFIX_SPLIT         1
    fork MEANING_DESCENT_UNIT_DEFS       pass
    defs                                 1,419,406 titles
    lattice                              555,847 words, 815,080 slots
    descend_seconds                      0.001
    per_hole_ms_mean                     0.014
    wall_seconds                         29.6

    Verbatim (5)
        アンパサンド  full  own lead
            アンパサンドは、格子の分解単位を持たない。アンパサンド: アンパサンド（&amp;amp;, ）は、並立助詞「…と…」を意味する記号である。（構成的説明 — 証言ではない）
        外国語放送局  full  alias hop
            外国語放送局は、格子の分解単位を持たない。外国語放送局: 外国語放送（がいこくごほうそう）とは、外国語による放送のこと。（構成的説明 — 証言ではない）
        正常化  full  bare-suffix refused; term defined
            正常化は、格子の分解単位を持たない。正常化: 正常化（せいじょうか）とは、より正常な状態にして行くあらゆる過程のこと。（構成的説明 — 証言ではない）
        プクプク  none  named
            プクプクは、格子の分解単位を持たない。プクプク: （棚に定義なし）。（構成的説明 — 証言ではない）
        野城  none  ABSTAIN_BARE_SUFFIX_SPLIT, named
            野城は、格子の分解単位を持たない。野城: （棚に定義なし）。（構成的説明 — 証言ではない）
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.coverage import closing_domains
from verantyx.cross_store import CrossStore
from verantyx.lattice import build
from verantyx.meaning_descent import (
    DEFS_PATH,
    build_defs,
    descend,
    load_defs,
    regression,
)
from verantyx.writer import Writer

ROOT = Path.home() / "Projects" / "vera-corpus" / "build"
PROBES = ROOT / "probes_200.json"
SHELF = ROOT / "jawiki_shallow.json"
ALIASES = ROOT / "jawiki_aliases.json"
VERA_DB = ROOT / "vera.db"
WRITER = ROOT / "writer.json"


def hole_subjects(probes, atlas, shelf, aliases=None):
    """Same predicate as measure_shallow_after.

    The spec's 91 is holes_after_shelf (aliases not applied). The
    script also reports holes_after_shelf_and_aliases (83 on this
    store). ``aliases`` is optional so both counts reuse one walk.
    """
    plus = {**atlas, "浅層wiki": shelf}
    holes = []
    for p in probes:
        if closing_domains(plus, p, aliases=aliases)["coverage_hole"]:
            holes.append(p)
    return holes


#: Designer-eyeball set, in this order when present: own-lead full,
#: alias-hop full, bare-suffix-but-defined, named absence, bare-suffix
#: absence. Partial is empty on the 91 — not invented.
PREFERRED_EXAMPLES = (
    "アンパサンド", "外国語放送局", "正常化", "プクプク", "野城",
)


def pick_examples(rows):
    """Five verbatim rows. Preferred terms first, then fill by grounding."""
    by_term = {r["term"]: r for r in rows}
    out = [by_term[t] for t in PREFERRED_EXAMPLES if t in by_term]
    by = {"full": [], "partial": [], "none": []}
    for r in rows:
        if r["grounding"] in by:
            by[r["grounding"]].append(r)
    leftover = [r for r in (by["partial"] + by["full"] + by["none"])
                if r not in out]
    while len(out) < 5 and leftover:
        out.append(leftover.pop(0))
    return out[:5]


def main() -> int:
    t_all = time.time()
    fork = regression()
    print("fork:", json.dumps(fork, ensure_ascii=False), flush=True)
    if not fork.get("pass"):
        print("REFUSE: MEANING_DESCENT_UNIT_DEFS failed.", file=sys.stderr)
        return 2

    if not DEFS_PATH.exists():
        print("defs sidecar missing — building once from pages()", flush=True)
        build_defs(DEFS_PATH)
    t0 = time.time()
    defs = load_defs(DEFS_PATH)
    print("defs:", len(defs), "load %.1fs" % (time.time() - t0), flush=True)

    probes = json.loads(PROBES.read_text(encoding="utf-8"))
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))
    print("probes:", len(probes), "aliases:", len(aliases), flush=True)

    t0 = time.time()
    shelf = CrossStore.load(SHELF)
    print("shelf cores:", len(shelf.crosses),
          "load %.1fs" % (time.time() - t0), flush=True)

    t0 = time.time()
    from verantyx.export_sqlite import vera
    atlas = dict(vera(VERA_DB).witnesses)
    print("atlas domains:", sorted(atlas),
          "load %.1fs" % (time.time() - t0), flush=True)

    t0 = time.time()
    holes_shelf = hole_subjects(probes, atlas, shelf)
    holes_alias = hole_subjects(probes, atlas, shelf, aliases)
    # Spec W2b: the 91 are holes_after_shelf. Aliases are a later
    # increment and close 8 of them; descend still uses aliases.
    holes = holes_shelf
    print("holes_after_shelf:", len(holes_shelf),
          "holes_after_shelf_and_aliases:", len(holes_alias),
          "recompute %.1fs" % (time.time() - t0), flush=True)

    t0 = time.time()
    vocab = Writer.load(WRITER).vocab
    words = set(vocab.attested)
    for title in defs:
        if 2 <= len(title) <= 5:
            words.add(title)
    lat = build(words)
    print("lattice:", json.dumps(lat.report()),
          "build %.1fs" % (time.time() - t0), flush=True)

    t0 = time.time()
    rows = []
    for term in holes:
        t1 = time.time()
        got = descend(term, lattice=lat, defs=defs, aliases=aliases)
        rows.append({
            "term": term,
            "verdict": got["verdict"],
            "grounding": got["grounding"],
            "split": got.get("split"),
            "ungrounded_units": got.get("ungrounded_units") or [],
            "units": [
                {"unit": b["unit"],
                 "definition": b.get("definition"),
                 "source": b.get("source")}
                for b in (got.get("units") or [])
            ],
            "text": got.get("text"),
            "ms": round((time.time() - t1) * 1000, 3),
        })
    elapsed = time.time() - t0

    counts = {"full": 0, "partial": 0, "none": 0}
    verdicts = {}
    for r in rows:
        counts[r["grounding"]] = counts.get(r["grounding"], 0) + 1
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1

    examples = pick_examples(rows)
    ms = [r["ms"] for r in rows]
    ms_sorted = sorted(ms)
    p50 = ms_sorted[len(ms_sorted) // 2] if ms_sorted else None

    out = {
        "holes": len(holes),
        "holes_after_shelf": len(holes_shelf),
        "holes_after_shelf_and_aliases": len(holes_alias),
        "baseline": 0,
        "grounding": counts,
        "verdicts": dict(sorted(verdicts.items())),
        "defs_titles": len(defs),
        "aliases": len(aliases),
        "lattice": lat.report(),
        "timing": {
            "descend_seconds": round(elapsed, 3),
            "per_hole_ms_mean": round(sum(ms) / len(ms), 3) if ms else None,
            "per_hole_ms_p50": p50,
            "wall_seconds": round(time.time() - t_all, 1),
        },
        "fork": fork["fork"],
        "fork_pass": fork["pass"],
        "examples": examples,
        "hole_subjects": holes,
    }
    print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
