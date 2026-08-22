"""Build the full shallow shelf: every jawiki lead, one new sovereign.

The slice measurement (tools/measure_shallow_shelf.py) priced this:
ingest is seconds per 10k leads, the sequential bz2 walk is the cost,
and hole-closing scales linearly with coverage (72% -> 68% from a 0.5%
slice, proportional to its probe-pool share). So the full build is a
background walk of the 4.4GB dump, batched ingest, and one save.

Atlas-widening only: the shelf lands in its own store file
(vera-corpus/build/jawiki_shallow.json), joins coverage.closing_domains
as one more shelf, and never pools into any census — the abstract-noun
warning (technical prose, 0% contradiction precision) stands; breadth
is for the map, not for the vote.
"""
import bz2
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.cross_store import CrossStore
from verantyx.document_ingest import Document, ingest_documents

DUMP = (Path.home() / "Projects" / "vera-corpus" / "corpora" / "jawiki"
        / "jawiki-latest-pages-articles.xml.bz2")
TITLE_RE = re.compile(r"<title>([^<]+)</title>")
TEXT_RE = re.compile(r"<text[^>]*>(.*)")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _clean(line: str) -> str:
    line = COMMENT_RE.sub("", line)
    line = re.sub(r"\{\{[^{}]*\}\}", "", line)
    line = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", line)
    line = re.sub(r"'{2,}", "", line)
    line = re.sub(r"<[^>]+>", "", line)
    return line.strip()


def pages():
    """(title, lead) with template-depth tracking — the v2 reader.

    v1 took the single line after <text>. Modern articles open with a
    multi-line infobox, so that line was template junk, the length
    filter dropped it, and recall was 298,811 of 2,458,941 titles
    (~12%). v2 walks up to the first 80 lines of a page, counts {{ }}
    and {| |} depth so template and table spans are skipped whole, and
    takes the first PROSE line (not starting with markup, >= 30 chars
    after cleaning). Redirects still yield nothing here — they are the
    sidecar's material, not leads.
    """
    title = None
    collecting = False
    depth = 0
    seen = 0
    with bz2.open(DUMP, "rt", errors="replace") as fh:
        for raw in fh:
            m = TITLE_RE.search(raw)
            if m:
                title = m.group(1)
                collecting = False
                continue
            if title is None or ":" in title:
                continue
            if not collecting:
                t = TEXT_RE.search(raw)
                if not t:
                    continue
                collecting = True
                depth = 0
                seen = 0
                raw = t.group(1)
            if "</text>" in raw:
                raw = raw.split("</text>")[0]
                collecting = False
            seen += 1
            if seen > 80:
                collecting = False
            line = raw.strip()
            opened = line.count("{{") + line.count("{|")
            closed = line.count("}}") + line.count("|}")
            if depth > 0:
                depth = max(0, depth + opened - closed)
                continue
            depth = max(0, opened - closed)
            if depth > 0:
                continue
            if not line or line[0] in "*#=|{<:;!":
                continue
            lead = _clean(line)
            if len(lead) < 30:
                continue
            # Image/file caption lines survive the markup strip as
            # "thumb|100px|…" remnants; they are pictures' prose, not
            # the article's. Skip the LINE and keep scanning — junk
            # must not spend the page's one yield.
            if (lead.startswith("thumb") or "px|" in lead
                    or re.match(r"(?:ファイル|File|Image|画像)[:|]", lead)):
                continue
            yield title, lead
            title = None
            collecting = False

OUT = Path.home() / "Projects" / "vera-corpus" / "build" / "jawiki_shallow.json"
BATCH = 20_000


def main() -> None:
    t0 = time.time()
    shelf = CrossStore()
    batch = []
    n_docs = 0
    for ti, lead in pages():
        if len(lead) < 30:
            continue
        batch.append(Document(source="jawiki-lead:%s" % ti,
                              text="%sは、%s" % (ti, lead[:280])))
        if len(batch) >= BATCH:
            ingest_documents(shelf, batch)
            n_docs += len(batch)
            batch = []
            print("ingested %d docs, %d cores, %.0fs"
                  % (n_docs, len(shelf.crosses), time.time() - t0), flush=True)
    if batch:
        ingest_documents(shelf, batch)
        n_docs += len(batch)

    shelf.save(OUT)
    print(json.dumps({
        "docs": n_docs, "cores": len(shelf.crosses),
        "out": str(OUT), "seconds": round(time.time() - t0, 1),
    }, ensure_ascii=False))


# Guarded on purpose: an import of this module once STARTED a full
# rebuild (a smoke test importing pages() kicked off a 2.4M-page walk
# that would have overwritten the live shelf mid-measurement). Build
# only when asked to build.
if __name__ == "__main__":
    main()
