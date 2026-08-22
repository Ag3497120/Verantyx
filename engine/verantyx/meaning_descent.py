"""Meaning descent — lattice units wired to shelf definition sentences.

SPEC_2026-08-14_eight_gaps W2b. The three-layer meaning design's bottom
was missing a wire: an unknown compound decomposes (電荷密度 → 電荷,
密度) through the existing lattice / explain conventions, and each
unit now HAS a definition available — the shallow shelf's jawiki lead
— but nothing fetched it. This module is that fetch.

The shallow CrossStore does not hold lead TEXT. Its facets are
ingest tokens (ref, gt, 呼, …) and its provenance snippets are other
articles' sentences that mentioned the core. Definitions therefore
live in a sidecar, one lead sentence per title, streamed from
`tools/build_shallow_shelf.pages()`:

    ~/Projects/vera-corpus/build/jawiki_defs.json

Hand-over only. Nothing here enters a verdict, a census, or the
concord vocabulary. The type marks construction, the same family as
EXPLAINED_BY_UNITS — never a judgment word.

    EXPLAINED_BY_UNIT_DEFS     at least one unit has a shelf sentence
    UNGROUNDED_UNITS           units named, none have a sentence
    ABSTAIN_SPLIT_TIED         two splits score the same (explain)
    ABSTAIN_BARE_SUFFIX_SPLIT  every split leaves a 1-char head
    ABSTAIN_CYCLE              recursion met a term already on the path

Units with no sentence are NAMED in ``ungrounded_units``. Absence is
honest and never skipped. Recursion is depth 2 (units of units);
a cycle cuts off.

## Measured — probes_200 holes_after_shelf, 2026-08-14

Same 200 frozen probes as `tools/measure_shallow_after.py`. The spec's
91 is holes_after_shelf (aliases not applied). Aliases close 8 of
those as coverage holes; descend still uses the one-hop sidecar.
Baseline 0 — the unit→definition wire did not exist.

    holes_after_shelf                    91
    holes_after_shelf_and_aliases        83
    baseline                              0
    full (all first-level units defined) 81
    partial                               0
    none                                 10
    verdicts
        EXPLAINED_BY_UNIT_DEFS           81
        UNGROUNDED_UNITS                  9
        ABSTAIN_BARE_SUFFIX_SPLIT         1   野城
    fork MEANING_DESCENT_UNIT_DEFS       pass
    defs sidecar                         1,419,406 titles  581.1s  262 MB
    aliases                              941,604
    lattice (writer ∪ def titles 2–5)    555,847 words, 815,080 slots
    descend on 91 holes                  0.001 s   mean 0.014 ms

Partial is 0 because these holes are almost all unsplittable (length
6–8, or a name the lattice will not cut). The term is the only unit:
either `pages()` v2 / one-hop alias has a lead sentence, or the
absence is named. 電荷密度 (not a hole) still splits 電荷+密度 and
both sentences attach — the wire the holes rarely reach.

    アンパサンド     full   own lead
    外国語放送局     full   jawiki:外国語放送 ← 外国語放送局
    正常化           full   bare-suffix refused; term has a lead
    プクプク         none   named
    野城             none   ABSTAIN_BARE_SUFFIX_SPLIT, named
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .explain import CONSTRUCTED_MARK
from .lattice import Lattice, splits_of

DEFS_PATH = (corpus_root() / "build"
             / "jawiki_defs.json")

EXPLAINED_BY_UNIT_DEFS = "EXPLAINED_BY_UNIT_DEFS"
UNGROUNDED_UNITS = "UNGROUNDED_UNITS"
ABSTAIN_SPLIT_TIED = "ABSTAIN_SPLIT_TIED"
ABSTAIN_BARE_SUFFIX_SPLIT = "ABSTAIN_BARE_SUFFIX_SPLIT"
ABSTAIN_CYCLE = "ABSTAIN_CYCLE"

_SENT_END = frozenset("。．.！!？?")


def first_sentence(lead: str) -> str:
    """One sentence: cut at the first Japanese/ASCII terminator, else all."""
    lead = (lead or "").strip()
    if not lead:
        return ""
    for i, ch in enumerate(lead):
        if ch in _SENT_END:
            return lead[: i + 1].strip()
    return lead


def canonical(term: str, aliases: Optional[Dict[str, str]]) -> str:
    """One hop only. An alias of an alias is a chain nobody attested."""
    t = (term or "").strip()
    if not t:
        return t
    hit = (aliases or {}).get(t)
    return hit if hit else t


def lookup_def(
    unit: str,
    defs: Optional[Dict[str, str]],
    aliases: Optional[Dict[str, str]],
) -> Tuple[Optional[str], str]:
    """(definition, source). Source names the page, and the hop when used."""
    table = defs or {}
    if unit in table:
        return table[unit], "jawiki:%s" % unit
    canon = canonical(unit, aliases)
    if canon != unit and canon in table:
        return table[canon], "jawiki:%s ← %s" % (canon, unit)
    return None, ""


def _speakable(lat: Lattice, term: str) -> List[Tuple[str, str]]:
    """Lattice-valid splits whose right half is not a one-character head.

    Same filter explain.py applies at the split: 発明者 → 者 is refused
    here, not later at a vocabulary gate.
    """
    return [(a, b) for a, b in splits_of(lat, term) if len(b) > 1]


def _unit_score(
    unit: str,
    lat: Lattice,
    defs: Optional[Dict[str, str]],
    aliases: Optional[Dict[str, str]],
) -> Tuple[int, int, int, int]:
    word = 1 if unit in lat.words else 0
    held = 1 if lookup_def(unit, defs, aliases)[0] is not None else 0
    return (held and word, word, held, len(unit))


def _split_score(
    pair: Tuple[str, str],
    lat: Lattice,
    defs: Optional[Dict[str, str]],
    aliases: Optional[Dict[str, str]],
) -> Tuple[int, int, int, int]:
    a = _unit_score(pair[0], lat, defs, aliases)
    b = _unit_score(pair[1], lat, defs, aliases)
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2], min(len(pair[0]), len(pair[1])))


def _pick_split(
    lat: Lattice,
    term: str,
    defs: Optional[Dict[str, str]],
    aliases: Optional[Dict[str, str]],
) -> Tuple[Optional[Tuple[str, str]], Optional[str]]:
    """One leading split, or a typed abstention. Never a guessed cut.

    Score is the explain convention with 'held' = has a sidecar sentence:
    (word-and-defined, word, defined, min-length). A tie abstains.
    """
    speakable = _speakable(lat, term)
    if speakable:
        ranked = sorted(
            speakable,
            key=lambda p: _split_score(p, lat, defs, aliases),
            reverse=True,
        )
        if (len(ranked) > 1
                and _split_score(ranked[0], lat, defs, aliases)
                == _split_score(ranked[1], lat, defs, aliases)):
            return None, ABSTAIN_SPLIT_TIED
        return ranked[0], None
    if splits_of(lat, term):
        return None, ABSTAIN_BARE_SUFFIX_SPLIT
    return None, None


def _draft(
    term: str,
    split: Optional[List[str]],
    units: List[Dict[str, Any]],
) -> str:
    if split and len(split) == 2:
        frame = "%sは、%sと%sに分解される。" % (term, split[0], split[1])
    else:
        frame = "%sは、格子の分解単位を持たない。" % term
    for b in units:
        u = b["unit"]
        d = b.get("definition")
        if d:
            frame += "%s: %s" % (u, d)
            if d[-1] not in _SENT_END:
                frame += "。"
        else:
            frame += "%s: （棚に定義なし）。" % u
    return frame + CONSTRUCTED_MARK


def grounding_of(result: Dict[str, Any]) -> str:
    """first-level units only: full / partial / none."""
    units = result.get("units") or []
    if not units:
        return "none"
    n = sum(1 for b in units if b.get("definition"))
    if n == len(units):
        return "full"
    if n:
        return "partial"
    return "none"


def descend(
    term: str,
    *,
    lattice: Lattice,
    defs: Optional[Dict[str, str]],
    aliases: Optional[Dict[str, str]],
    depth: int = 2,
    _seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Decompose ``term`` and attach each unit's shelf definition sentence.

    ``lattice`` is the caller's attested-word lattice (explain / lattice
    conventions). ``defs`` is title → one lead sentence. ``aliases`` is
    one-hop alias → canonical. Recursion depth 2 is units of units.
    """
    term = (term or "").strip()
    seen = set(_seen or ())
    base: Dict[str, Any] = {
        "constructed": True,
        "term": term,
        "units": [],
        "ungrounded_units": [],
        "split": None,
        "depth": depth,
    }
    if not term:
        base["verdict"] = UNGROUNDED_UNITS
        base["grounding"] = "none"
        base["text"] = CONSTRUCTED_MARK
        base["note"] = "empty term"
        return base
    if term in seen:
        base["verdict"] = ABSTAIN_CYCLE
        base["ungrounded_units"] = [term]
        base["grounding"] = "none"
        base["text"] = "%s: （循環打ち切り）。" % term + CONSTRUCTED_MARK
        base["note"] = "cycle cut-off; the unit is named, not skipped"
        return base
    seen = seen | {term}

    chosen, split_abstain = _pick_split(lattice, term, defs, aliases)
    if chosen:
        unit_names = [chosen[0], chosen[1]]
        split: Optional[List[str]] = [chosen[0], chosen[1]]
    else:
        unit_names = [term]
        split = None

    units: List[Dict[str, Any]] = []
    ungrounded: List[str] = []
    for u in unit_names:
        definition, source = lookup_def(u, defs, aliases)
        bundle: Dict[str, Any] = {
            "unit": u,
            "definition": definition,
            "source": source or None,
        }
        if definition is None:
            ungrounded.append(u)
        # Units of units: recurse into a chosen half, never into self
        # (the no-split case already is the term). Depth 2 at the
        # caller becomes depth 1 here.
        if depth > 1 and u != term:
            bundle["descended"] = descend(
                u, lattice=lattice, defs=defs, aliases=aliases,
                depth=depth - 1, _seen=seen,
            )
        units.append(bundle)

    n_def = sum(1 for b in units if b["definition"])
    if n_def == len(units) and units:
        grounding = "full"
        verdict = EXPLAINED_BY_UNIT_DEFS
    elif n_def:
        grounding = "partial"
        verdict = EXPLAINED_BY_UNIT_DEFS
    elif split_abstain:
        grounding = "none"
        verdict = split_abstain
    else:
        grounding = "none"
        verdict = UNGROUNDED_UNITS

    out: Dict[str, Any] = {
        "verdict": verdict,
        "constructed": True,
        "term": term,
        "split": split,
        "units": units,
        "ungrounded_units": ungrounded,
        "grounding": grounding,
        "depth": depth,
        "text": _draft(term, split, units),
        "note": ("constructed from unit shelf definitions; "
                 "not itself attested. missing units are named"),
    }
    if split_abstain and split is None:
        out["split_abstain"] = split_abstain
    return out


def load_defs(path: Path = DEFS_PATH) -> Dict[str, str]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_defs(out: Path = DEFS_PATH) -> Dict[str, Any]:
    """Stream pages() once. One lead sentence per title. Sidecar only."""
    tools = Path(__file__).resolve().parent.parent / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from build_shallow_shelf import pages  # type: ignore

    t0 = time.time()
    defs: Dict[str, str] = {}
    n_pages = 0
    for title, lead in pages():
        n_pages += 1
        sent = first_sentence(lead)
        if sent and title not in defs:
            defs[title] = sent
        if n_pages % 50_000 == 0:
            print("pages %d titles %d %.0fs"
                  % (n_pages, len(defs), time.time() - t0), flush=True)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(defs, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)
    report = {
        "pages": n_pages,
        "titles": len(defs),
        "out": str(out),
        "seconds": round(time.time() - t0, 1),
    }
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


def regression() -> Dict[str, Any]:
    """Fork-equivalent: construction mark, named absence, cycle, tie, alias."""
    from .lattice import build

    lat = build([
        "電荷", "密度", "電気", "電子", "質量",
        "発明", "未知", "保護者",
        "あい", "うえお", "あいう", "えお",
    ])
    defs = {
        "電荷": "電荷とは、物質が帯びる電気の量である。",
        "密度": "密度とは、単位体積あたりの質量である。",
        "電気": "電気とは、電荷の存在および流れに関する物理現象である。",
    }
    aliases = {"でんか": "電荷"}

    full = descend("電荷密度", lattice=lat, defs=defs, aliases=aliases)
    units_full = [b["unit"] for b in full.get("units") or []]
    defs_full = [b.get("definition") for b in full.get("units") or []]

    # 未知 is a lattice word with no sentence → partial, named missing.
    lat_p = build(["電荷", "密度", "未知語"])
    # 電荷未知語 (5): (3,2) 電荷未+知語 / (2,3) 電荷+未知語. Only 電荷+未知語
    # is node-valid if 未知語 is a word. Add both halves.
    lat_p = build(["電荷", "未知語", "密度"])
    partial = descend("電荷未知語", lattice=lat_p, defs=defs, aliases=aliases)

    none = descend("完全未知", lattice=lat, defs=defs, aliases=aliases)

    via = descend("でんか", lattice=lat, defs=defs, aliases=aliases)

    cyc = descend("電荷密度", lattice=lat, defs=defs, aliases=aliases,
                  _seen={"電荷密度"})

    # 発明者: (2,1) 発明+者 is bare suffix; (1,2) 発+明者 — 明者 not a node.
    bare = descend("発明者", lattice=lat, defs=defs, aliases=aliases)

    # あいうえお: (3,2) あいう+えお and (2,3) あい+うえお, same score, no defs.
    tied = descend("あいうえお", lattice=lat, defs=defs, aliases=aliases)

    constructed = (
        full.get("constructed") is True
        and CONSTRUCTED_MARK in (full.get("text") or "")
        and full.get("verdict") == EXPLAINED_BY_UNIT_DEFS
    )
    full_ok = (
        units_full == ["電荷", "密度"]
        and all(defs_full)
        and full.get("ungrounded_units") == []
        and full.get("grounding") == "full"
        and full.get("units")[0]["source"] == "jawiki:電荷"
    )
    # Recursion attached units-of-units on each half.
    rec_ok = all("descended" in b for b in full.get("units") or [])

    part_units = [b["unit"] for b in partial.get("units") or []]
    part_ok = (
        partial.get("verdict") == EXPLAINED_BY_UNIT_DEFS
        and partial.get("grounding") == "partial"
        and "未知語" in (partial.get("ungrounded_units") or [])
        and "電荷" in part_units
        and any(b.get("definition") for b in partial.get("units") or [])
    )
    none_ok = (
        none.get("verdict") in (UNGROUNDED_UNITS, ABSTAIN_BARE_SUFFIX_SPLIT,
                                ABSTAIN_SPLIT_TIED)
        and none.get("grounding") == "none"
        and "完全未知" in (none.get("ungrounded_units") or [none.get("term")])
    )
    alias_ok = (
        via.get("verdict") == EXPLAINED_BY_UNIT_DEFS
        and (via.get("units") or [{}])[0].get("definition") == defs["電荷"]
        and "← でんか" in ((via.get("units") or [{}])[0].get("source") or "")
    )
    cycle_ok = (
        cyc.get("verdict") == ABSTAIN_CYCLE
        and cyc.get("constructed") is True
        and "電荷密度" in (cyc.get("ungrounded_units") or [])
    )
    bare_ok = (
        bare.get("split_abstain") == ABSTAIN_BARE_SUFFIX_SPLIT
        or bare.get("verdict") == ABSTAIN_BARE_SUFFIX_SPLIT
    )
    tied_ok = (
        tied.get("split_abstain") == ABSTAIN_SPLIT_TIED
        or tied.get("verdict") == ABSTAIN_SPLIT_TIED
    )
    # Absence is in the payload, never dropped.
    named_ok = "未知語" in (partial.get("ungrounded_units") or [])

    ok = all([constructed, full_ok, rec_ok, part_ok, none_ok, alias_ok,
              cycle_ok, bare_ok, tied_ok, named_ok])
    return {
        "experiment": "meaning_descent",
        "fork": "MEANING_DESCENT_UNIT_DEFS",
        "pass": bool(ok),
        "result": {
            "full": [full.get("verdict"), full.get("split"),
                     full.get("grounding")],
            "partial": [partial.get("verdict"),
                        partial.get("ungrounded_units")],
            "none": none.get("verdict"),
            "alias_source": (via.get("units") or [{}])[0].get("source"),
            "cycle": cyc.get("verdict"),
            "bare": bare.get("verdict"),
            "tied": tied.get("verdict"),
        },
    }


def main() -> None:
    build_defs()


if __name__ == "__main__":
    main()
