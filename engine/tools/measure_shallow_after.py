"""The pre-registered post-measurement: hole rate with the FULL shelf.

PREREGISTERED_2026-08-14_tree_and_shelf.md froze the protocol before
any result existed: same 200 probes (deterministic stride over the
whole dump's title stream, same 2-8 char kana/kanji filter), hole rate
before (measured 144/200 = 72%) against after (atlas + the full
jawiki_shallow shelf). This script is the "after", plus the honest
recording the registration demands: the gap between the linear
extrapolation's optimism and reality.

One recall note the builder run surfaced: the full build yielded
298,811 leads from the whole dump — the crude first-line parser, not
an article cap (nested templates defeat it on many pages). So "full
shelf" means full-dump-parsed, ~21% of raw articles; the probe set is
drawn from ALL titles either way, so the number below prices exactly
what was built, parser recall included.
"""
import bz2
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.coverage import closing_domains
from verantyx.cross_store import CrossStore

DUMP = (Path.home() / "Projects" / "vera-corpus" / "corpora" / "jawiki"
        / "jawiki-latest-pages-articles.xml.bz2")
SHELF = Path.home() / "Projects" / "vera-corpus" / "build" / "jawiki_shallow.json"
PROBE_N = 200

TITLE = re.compile(r"<title>([^<]+)</title>")
KANAJI = re.compile(r"^[㐀-䶿一-鿿ぁ-ゖァ-ヺー]{2,8}$")

# The probe set is now PERSISTED — the first run's drift (144/200 vs
# 149/200 baselines from a prefilter difference) is the recorded defect
# this fixes: one derivation, written down, reused byte-identically.
PROBES_FILE = (Path.home() / "Projects" / "vera-corpus" / "build"
               / "probes_200.json")
if PROBES_FILE.exists():
    probes = json.loads(PROBES_FILE.read_text(encoding="utf-8"))
    print("probes: loaded %d (frozen)" % len(probes), flush=True)
else:
    titles = []
    with bz2.open(DUMP, "rt", errors="replace") as fh:
        for raw in fh:
            m = TITLE.search(raw)
            if m and ":" not in m.group(1):
                titles.append(m.group(1))
    print("titles:", len(titles), flush=True)
    probe_pool = [t for t in titles if KANAJI.match(t)]
    stride = max(1, len(probe_pool) // PROBE_N)
    probes = probe_pool[::stride][:PROBE_N]
    PROBES_FILE.write_text(json.dumps(probes, ensure_ascii=False),
                           encoding="utf-8")
    print("probes: derived and frozen to %s" % PROBES_FILE, flush=True)

shelf = CrossStore.load(SHELF)
print("shelf cores:", len(shelf.crosses), flush=True)

from verantyx.export_sqlite import vera  # noqa: E402

v = vera(Path.home() / "Projects" / "vera-corpus" / "build" / "vera.db")
atlas = dict(v.witnesses)

ALIASES = (Path.home() / "Projects" / "vera-corpus" / "build"
           / "jawiki_aliases.json")
aliases = (json.loads(ALIASES.read_text(encoding="utf-8"))
           if ALIASES.exists() else {})

plus = {**atlas, "浅層wiki": shelf}
before = sum(closing_domains(atlas, p)["coverage_hole"] for p in probes)
after = sum(closing_domains(plus, p)["coverage_hole"] for p in probes)
with_alias = sum(
    closing_domains(plus, p, aliases=aliases)["coverage_hole"]
    for p in probes)
print(json.dumps({
    "probes": len(probes), "aliases": len(aliases),
    "holes_before": before, "holes_after_shelf": after,
    "holes_after_shelf_and_aliases": with_alias,
    "hole_rate": {"before": round(before / len(probes), 3),
                  "shelf": round(after / len(probes), 3),
                  "shelf_and_aliases": round(with_alias / len(probes), 3)},
}, ensure_ascii=False, indent=1))
