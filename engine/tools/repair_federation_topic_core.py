"""Rule-derived filter: drop claims ja_chosen_core would not file on that core.

The ingest rule in `verantyx.lang.ja_chosen_core` refuses to steal a run
from a compound or a parenthetical sense. This tool walks every provenance
snippet in federation.pkl and removes (core, facet) pairs the new rule
would not place on that core. It does not re-file under a replacement
core — the hole stays a hole.

    python3.11 tools/repair_federation_topic_core.py --diagnose
    python3.11 tools/repair_federation_topic_core.py --apply
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.lang import (  # noqa: E402
    _is_split_name_compound,
    _opening_is_split_compound,
    ja_chosen_core,
    ja_content_runs,
    ja_topic_match,
)

ROOT = Path.home() / "Projects" / "vera-corpus"
FED = ROOT / "build" / "federation.pkl"
LEDGER = ROOT / "build" / "federation_repair_ledger_2026-08-14.jsonl"


def _pattern(snip: str, old: str, new: Optional[str]) -> str:
    hit = ja_topic_match(snip)
    runs = ja_content_runs(snip)
    if hit and hit[1]:
        return "content_paren_before_ha"
    if hit:
        phrase, _ = hit
        tr = ja_content_runs(phrase)
        if "の" not in phrase and _is_split_name_compound(phrase, tr):
            return "topic_name_compound_last_run"
        if new is None:
            return "topic_hole"
        if new.casefold() != old.casefold():
            return "topic_particle_retargeted"
        return "topic_unchanged"
    if _opening_is_split_compound(snip or "", runs):
        return "first_run_compound_prefix"
    if new is None:
        return "no_identifiable_topic"
    if new.casefold() != old.casefold():
        return "core_changed"
    return "kept"


def iter_slots(fed: Dict[str, Any]) -> Iterator[Tuple[str, str, str, str, str]]:
    """(domain, leaf, core, facet, snippet)."""
    for domain, leaves in fed.items():
        for name, st in leaves.items():
            prov = getattr(st, "provenance", None) or {}
            for core, by_f in prov.items():
                for facet, rec in by_f.items():
                    snip = ""
                    if isinstance(rec, (list, tuple)) and len(rec) > 2:
                        snip = rec[2] or ""
                    yield domain, name, core, facet, snip


def diagnose(fed: Dict[str, Any]) -> Dict[str, Any]:
    by_pat: Counter = Counter()
    examples: Dict[str, List[Dict[str, Any]]] = {}
    n_slots = 0
    n_drop = 0
    unique_pairs = set()
    drop_pairs = set()
    for domain, name, core, facet, snip in iter_slots(fed):
        n_slots += 1
        unique_pairs.add((core, facet))
        new = ja_chosen_core(snip) if snip else None
        if new is not None and new.casefold() == core.casefold():
            continue
        n_drop += 1
        drop_pairs.add((core, facet))
        pat = _pattern(snip, core, new)
        by_pat[pat] += 1
        bucket = examples.setdefault(pat, [])
        if len(bucket) < 3:
            bucket.append({
                "leaf": name,
                "core": core,
                "facet": facet,
                "new_core": new,
                "pattern": pat,
                "source_sentence": snip[:240],
            })
    return {
        "n_provenance_slots": n_slots,
        "n_unique_core_facet": len(unique_pairs),
        "n_slots_dropped": n_drop,
        "n_unique_pairs_dropped": len(drop_pairs),
        "by_pattern": dict(by_pat),
        "examples": examples,
    }


def apply(fed: Dict[str, Any], ledger_path: Path) -> Dict[str, Any]:
    n_drop = 0
    by_pat: Counter = Counter()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("w", encoding="utf-8") as out:
        for domain, leaves in fed.items():
            for name, st in leaves.items():
                prov = getattr(st, "provenance", None) or {}
                doomed: List[Tuple[str, str, str, Optional[str], str]] = []
                for core, by_f in list(prov.items()):
                    for facet, rec in list(by_f.items()):
                        snip = ""
                        if isinstance(rec, (list, tuple)) and len(rec) > 2:
                            snip = rec[2] or ""
                        new = ja_chosen_core(snip) if snip else None
                        if new is not None and new.casefold() == core.casefold():
                            continue
                        pat = _pattern(snip, core, new)
                        doomed.append((core, facet, snip, new, pat))
                for core, facet, snip, new, pat in doomed:
                    cr = st.crosses.get(core)
                    if cr is not None:
                        cr.pop(facet, None)
                    slot = prov.get(core)
                    if slot is not None:
                        slot.pop(facet, None)
                        if not slot:
                            prov.pop(core, None)
                    n_drop += 1
                    by_pat[pat] += 1
                    out.write(json.dumps({
                        "domain": domain,
                        "leaf": name,
                        "core": core,
                        "facet": facet,
                        "new_core": new,
                        "pattern": pat,
                        "source_sentence": snip,
                    }, ensure_ascii=False) + "\n")
    return {"n_slots_dropped": n_drop, "by_pattern": dict(by_pat),
            "ledger": str(ledger_path)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fed", default=str(FED))
    ap.add_argument("--ledger", default=str(LEDGER))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--diagnose", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)

    t0 = time.time()
    fed = pickle.loads(Path(a.fed).read_bytes())
    print("loaded %.1fs" % (time.time() - t0), flush=True)
    if a.diagnose:
        rep = diagnose(fed)
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    stats = apply(fed, Path(a.ledger))
    Path(a.fed).write_bytes(pickle.dumps(fed))
    from verantyx.export_sqlite import export

    exp = export(ROOT, ROOT / "build" / "vera.db")
    print(json.dumps({**stats, "export": exp,
                      "seconds": round(time.time() - t0, 1)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
