"""Does a shallow shelf close coverage holes? A slice, measured first.

The bulk plan is Wikipedia-ja LEAD PARAGRAPHS ONLY as one new shelf —
shallow on purpose, atlas-widening, never census. Before building all
~1.4M, this measures the marginal value of a 10k-article slice:

    probes     200 article titles, deterministic stride over the WHOLE
               dump's title stream (so probes are mostly OUTSIDE the
               slice — the number measures generalization of breadth,
               not self-lookup)
    before     coverage_hole rate against the current federation atlas
    after      the same probes against atlas + the slice shelf

Also reported: build cost of the slice (seconds, cores), so the full
build is an extrapolation from measured numbers instead of a guess.

## Measured — jawiki dump 2026-08 (4.4GB), slice of the first 10k leads

    title stream (300k cap)     188.6s   (bz2 decompression is the cost)
    slice shelf                 10,000 leads -> 13,917 cores in 1.8s
    probes (200, stride over the 300k pool)
        holes before            144 / 200  (72%)
        holes after             136 / 200  (68%)

The 72% is the honest baseline: the current atlas misses nearly three
of four stride-sampled wiki titles — the breadth the demand-driven
loop cannot see because nobody asked yet. The slice closed 8 of 144
holes, almost exactly its share of the probe pool (~5%), so closing
scales linearly with coverage and the full shelf (~2M pages) projects
to: ~20min of streaming, minutes of ingest, and a shelf that answers
the title-probe class near-completely. Ingest is NOT the bottleneck —
the sequential bz2 walk is.
"""
import bz2
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.coverage import closing_domains
from verantyx.cross_store import CrossStore
from verantyx.document_ingest import Document, ingest_documents

DUMP = (Path.home() / "Projects" / "vera-corpus" / "corpora" / "jawiki"
        / "jawiki-latest-pages-articles.xml.bz2")
SLICE_N = 10_000
PROBE_N = 200

TITLE = re.compile(r"<title>([^<]+)</title>")
TEXT = re.compile(r"<text[^>]*>(.*)")
KANAJI = re.compile(r"^[㐀-䶿一-鿿ぁ-ゖァ-ヺー]{2,8}$")


def clean(line: str) -> str:
    line = re.sub(r"\{\{[^{}]*\}\}", "", line)
    line = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", line)
    line = re.sub(r"'{2,}", "", line)
    line = re.sub(r"<[^>]+>", "", line)
    return line.strip()


def pages():
    """(title, lead) pairs, streamed; tolerates a partial file."""
    title = None
    in_text = False
    try:
        with bz2.open(DUMP, "rt", errors="replace") as fh:
            for raw in fh:
                m = TITLE.search(raw)
                if m:
                    title = m.group(1)
                    in_text = False
                    continue
                if title and not in_text:
                    t = TEXT.search(raw)
                    if t:
                        in_text = True
                        first = clean(t.group(1))
                        if first.startswith("#") or ":" in title:
                            title = None  # redirects, namespaced pages
                            continue
                        yield title, first
                        title = None
    except (EOFError, OSError):
        return


#: Title-stream cap: the dump is one sequential bz2 stream, and walking
#: all of it costs ~full decompression. 300k titles reach ~30x past the
#: slice, which is spread enough for a generalization probe and states
#: its own limit here.
TITLE_CAP = 300_000

def main() -> None:
    t0 = time.time()
    titles = []
    slice_docs = []
    for ti, lead in pages():
        titles.append(ti)
        if len(titles) >= TITLE_CAP:
            break
        if len(slice_docs) < SLICE_N and len(lead) >= 30:
            slice_docs.append(Document(source="jawiki-lead:%s" % ti,
                                       text="%sは、%s" % (ti, lead[:280])))
    print("stream: %d titles, slice %d docs, %.1fs"
          % (len(titles), len(slice_docs), time.time() - t0), flush=True)

    probe_pool = [t for t in titles if KANAJI.match(t)]
    stride = max(1, len(probe_pool) // PROBE_N)
    probes = probe_pool[::stride][:PROBE_N]

    t1 = time.time()
    shelf = CrossStore()
    ingest_documents(shelf, slice_docs)
    print("shelf: %d cores, %.1fs" % (len(shelf.crosses), time.time() - t1),
          flush=True)

    from verantyx.export_sqlite import vera  # heavy import last

    v = vera(Path.home() / "Projects" / "vera-corpus" / "build" / "vera.db")
    atlas = dict(v.witnesses)

    before = sum(closing_domains(atlas, p)["coverage_hole"] for p in probes)
    atlas_plus = {**atlas, "浅層wiki": shelf}
    after = sum(closing_domains(atlas_plus, p)["coverage_hole"]
                for p in probes)

    print(json.dumps({
        "titles_seen": len(titles), "slice_docs": len(slice_docs),
        "shelf_cores": len(shelf.crosses),
        "probes": len(probes),
        "holes_before": before, "holes_after": after,
        "hole_rate": {"before": round(before / len(probes), 3),
                      "after": round(after / len(probes), 3)},
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
