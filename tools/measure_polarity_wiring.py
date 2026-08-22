"""What the doors gain when they read the polarity-marked profiles.

W1a built typed negation and measured it at 97/97, and then nothing
read it: `extract`'s polarity fold is off by default, so the published
profiles carried zero ¬ keys and the federation carried zero ¬ facets.
The tell was in W3a's own numbers — 「しかし」 fired 0 times on 30 pairs,
correctly, because the only licence for it is an observed ¬ paired with
the same predicate asserted on the other side, and no ¬ existed to pair.
An organ built, measured, and unplugged.

This measures the plug. Nothing here touches the census: the marked
profiles are a hand-off sidecar in their own index table, and the
federation is untouched — storing ¬ facets where they could VOTE is a
separate decision that needs its own pre-registration.

Reported: how much negation exists, whether the frozen diff bank moves
(the same 30 pairs, same scoring, plain vs marked), and whether any
real pair can now reach 「しかし」 — the first opposition this project
can render with a licence instead of an inference.

## Measured — 2026-08-15

    polarity-marked build      1,419,406 subjects, 618.8 s (one dump pass)
    negation keys              53,885 over 48,730 subjects
    coverage >=3               0.2437 (plain 0.2399 — marks add keys)

    frozen 30-pair diff bank   plain            marked
      DIFF verdicts            23               23
      axis hits                16               16
      しかし                    0                0

    real pairs (found, not constructed)
      形式言語 x アンパサンド    しかし 1, licence observed-negation
                               pair ["¬である", "である"]
      東北地方 x 形式言語        しかし 1, same licence

The bank does not move, and that is the correct reading: its 30 pairs
hold no opposition, which is exactly what W3a's honest zero reported.
What changed is reachability — 「しかし」 went from impossible to
licensed, and the first two it renders are pairs the corpus wrote, not
a demonstration built for the occasion. Nothing regressed: same DIFF
count, same axis hits, and the doors now name their table
(`extractor() == "indexed+polarity"`) so no burned number is silently
re-attributed to a different profile build.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verantyx.connective_render import render_diff  # noqa: E402
from verantyx.meaning_index import maps  # noqa: E402
from verantyx.structural_diff import diff  # noqa: E402

BUILD = Path.home() / "Projects" / "vera-corpus" / "build"
BANK = Path(__file__).resolve().parent / "diff_bank_2026-08-14.json"


def load_bank():
    d = json.loads(BANK.read_text(encoding="utf-8"))
    return d.get("pairs") or d.get("items") or []


def axis_hit(out, axis) -> bool:
    toks = set()
    for key in ("shared", "only_a", "only_b"):
        for row in (out.get(key) or []):
            t = row.get("token")
            if t:
                toks.add(str(t))
    blob = " ".join(toks)
    return any(str(a) in blob for a in (axis or []))


def main() -> int:
    from verantyx import meaning_assets as ma

    idx = maps()
    if idx is None:
        print(json.dumps({"verdict": "UNKNOWN_NOT_LOADED"}))
        return 1
    plain, polar = idx["profiles"], idx.get("profiles_polar")
    if polar is None or not len(polar):
        print(json.dumps({"verdict": "UNKNOWN_NO_POLAR_TABLE"}))
        return 1

    aliases, lattice = ma.aliases(), ma.lattice()
    shelf, senses = ma.empty_shelf(), ma.senses()

    def run(profiles):
        hits = shikashi = renders = 0
        examples = []
        for item in load_bank():
            a = item.get("a") or item.get("A")
            b = item.get("b") or item.get("B")
            axis = list(item.get("axis_a") or []) + list(item.get("axis_b") or [])
            if not a or not b:
                continue
            out = diff(a, b, profiles=profiles, aliases=aliases,
                       lattice=lattice, shelf=shelf, senses=senses)
            if out.get("verdict") != "DIFF":
                continue
            renders += 1
            if axis_hit(out, axis):
                hits += 1
            r = render_diff(out)
            for c in (r.get("connectives") or []):
                if c.get("connective") == "しかし":
                    shikashi += 1
                    if len(examples) < 3:
                        examples.append({"a": a, "b": b,
                                         "pairs": c.get("pairs")})
        return {"diff_verdicts": renders, "axis_hits": hits,
                "shikashi": shikashi, "shikashi_examples": examples}

    print(json.dumps({
        "verdict": "ANSWER",
        "table_read_by_doors": ma.extractor(),
        "plain": run(plain),
        "polar": run(polar),
        "note": "same bank, same scoring; only the profile table differs",
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
