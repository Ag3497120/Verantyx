"""Build the imported commonsense sovereign from ConceptNet 5.7 ja edges.

Pre-registration: tools/commonsense_import_preregistration_2026-08-16.json
(edf4d5a), thresholds fixed before the first byte was read. This sovereign
is HAND-OFF ONLY — it joins no census, and every facet carries its
relation name so an answer can say what kind of claim it repeats.

What enters:

    relations   the asserting subset only — IsA, HasProperty, UsedFor,
                CapableOf, AtLocation, PartOf, MadeOf, Causes,
                HasSubevent, HasA, Desires, HasPrerequisite.
                Lexical relations (Synonym, DerivedFrom, FormOf,
                EtymologicallyRelatedTo, RelatedTo, Antonym) stay out:
                the alias sidecar and the polarity layer are separate
                organs with their own licences.
    terms       both ends must contain at least one Japanese character
                (kana or CJK). ConceptNet ja is full of wiktionary rows
                like /c/ja/at/n whose surface is romaji — those are
                entries ABOUT Japanese, not Japanese.
    weight      ConceptNet's own edge weight, kept in the facet as a
                bucket (w1/w2/w4) so mass ranking can prefer
                crowd-confirmed edges without inventing a scale.

Facets are "rel:object" (isa:飲料, prop:冷たい), source label
"conceptnet5.7". The store is a CrossStore sidecar next to the published
build; capacity trimming is the structure's own law (mass keeps the
heaviest 24), and the trim count is reported, not hidden.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.cross_store import CrossStore

RELS = {
    "/r/IsA": "isa", "/r/HasProperty": "prop", "/r/UsedFor": "use",
    "/r/CapableOf": "can", "/r/AtLocation": "loc", "/r/PartOf": "part",
    "/r/MadeOf": "madeof", "/r/Causes": "causes",
    "/r/HasSubevent": "sub", "/r/HasA": "has", "/r/Desires": "want",
    "/r/HasPrerequisite": "needs",
}

_JA = re.compile(r"[぀-ヿ㐀-鿿]")


def surface(uri: str) -> str | None:
    # /c/ja/氷 or /c/ja/氷/n/... -> 氷 ; reject non-Japanese surfaces.
    parts = uri.split("/")
    if len(parts) < 4:
        return None
    term = parts[3].replace("_", "")
    if not term or not _JA.search(term):
        return None
    return term


def main() -> int:
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    edges: dict[tuple[str, str], float] = defaultdict(float)
    kept = skipped_rel = skipped_term = 0
    with src.open(encoding="utf-8") as fh:
        for line in fh:
            _a, rel, s_uri, o_uri, meta = line.rstrip("\n").split("\t", 4)
            short = RELS.get(rel)
            if short is None:
                skipped_rel += 1
                continue
            s, o = surface(s_uri), surface(o_uri)
            if s is None or o is None or s == o:
                skipped_term += 1
                continue
            w = float(json.loads(meta).get("weight", 1.0))
            edges[(s, "%s:%s" % (short, o))] += w
            kept += 1

    by_core: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (s, facet), w in edges.items():
        by_core[s].append((facet, w))

    # v2 (see commonsense_import_v2_preregistration_2026-08-16.json):
    # the six arms are relation groups, each keeping its 4 heaviest —
    # the capacity law used AS structure. AtLocation cannot crowd out
    # properties any more.
    ARMS = {"isa": "isa", "prop": "prop", "use": "act", "can": "act",
            "loc": "loc", "part": "comp", "madeof": "comp", "has": "comp",
            "causes": "ev", "sub": "ev", "needs": "ev", "want": "ev"}
    store = CrossStore()
    trimmed_edges = 0
    for core, facets in by_core.items():
        by_arm = {}
        for facet, w in facets:
            arm = ARMS.get(facet.partition(":")[0], "ev")
            by_arm.setdefault(arm, []).append((facet, w))
        keep = []
        for arm_facets in by_arm.values():
            arm_facets.sort(key=lambda t: (-t[1], t[0]))
            keep.extend(arm_facets[:4])
        trimmed_edges += len(facets) - len(keep)
        feats = []
        for facet, w in keep:
            bucket = "w4" if w >= 4 else ("w2" if w >= 2 else "w1")
            feats.append(facet)
            feats.append("%s|%s" % (bucket, facet))
        store.add(core, feats, source="conceptnet5.7")
    store.save(out)

    report = {
        "verdict": "ANSWER", "source": "conceptnet-assertions-5.7.0 /c/ja/",
        "edges_kept": kept, "cores": len(by_core),
        "skipped_non_assert_rel": skipped_rel,
        "skipped_non_japanese_term": skipped_term,
        "edges_trimmed_by_capacity": trimmed_edges,
        "out": str(out), "bytes": out.stat().st_size,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
