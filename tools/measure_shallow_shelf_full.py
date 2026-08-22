"""Post-build hole-rate measurement: same 200 probes, full shallow shelf.

Loads the already-built jawiki_shallow.json instead of re-ingesting, and
re-runs the coverage probe from measure_shallow_shelf so the before/after
numbers are on identical probes.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from measure_shallow_shelf import KANAJI, PROBE_N, TITLE_CAP, pages  # noqa: E402

from verantyx.coverage import closing_domains  # noqa: E402
from verantyx.cross_store import CrossStore  # noqa: E402

SHELF = Path.home() / "Projects" / "vera-corpus" / "build" / "jawiki_shallow.json"


def main() -> None:
    t0 = time.time()
    titles = []
    for ti, _lead in pages():
        titles.append(ti)
        if len(titles) >= TITLE_CAP:
            break
    probe_pool = [t for t in titles if KANAJI.match(t)]
    stride = max(1, len(probe_pool) // PROBE_N)
    probes = probe_pool[::stride][:PROBE_N]
    print("probes: %d, %.0fs" % (len(probes), time.time() - t0), flush=True)

    t1 = time.time()
    shelf = CrossStore.load(SHELF)
    print("shelf: %d cores, %.0fs" % (len(shelf.crosses), time.time() - t1),
          flush=True)

    from verantyx.export_sqlite import vera  # heavy import last

    v = vera(Path.home() / "Projects" / "vera-corpus" / "build" / "vera.db")
    atlas = dict(v.witnesses)

    before = sum(closing_domains(atlas, p)["coverage_hole"] for p in probes)
    atlas_plus = {**atlas, "浅層wiki": shelf}
    after = sum(closing_domains(atlas_plus, p)["coverage_hole"] for p in probes)

    print(json.dumps({
        "shelf_cores": len(shelf.crosses), "probes": len(probes),
        "holes_before": before, "holes_after": after,
        "hole_rate": {"before": round(before / len(probes), 3),
                      "after": round(after / len(probes), 3)},
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
