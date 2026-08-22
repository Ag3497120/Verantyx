"""Build the W2a sense sidecar from jawiki parenthetical titles.

One dump walk: every main-namespace title, plus the lead when
build_shallow_shelf.pages() would have one. Redirects arrive as
titles with an empty lead (aliases attach the unmarked sense at
resolve time). Sidecar, never a census.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_shallow_shelf import (  # type: ignore
    DUMP,
    TEXT_RE,
    TITLE_RE,
    _clean,
)

_FILE_CAPTION = re.compile(r"(?:ファイル|File|Image|画像)[:|]")
from verantyx.sense_split import OUT, build, report, save

ALIASES = (Path.home() / "Projects" / "vera-corpus" / "build"
           / "jawiki_aliases.json")


def iter_jawiki_articles():
    """(title, lead) for every main-namespace page. lead is '' if none."""
    import bz2

    title = None
    emitted = False
    collecting = False
    depth = 0
    seen = 0
    with bz2.open(DUMP, "rt", errors="replace") as fh:
        for raw in fh:
            m = TITLE_RE.search(raw)
            if m:
                if title and not emitted and ":" not in title:
                    yield title, ""
                title = m.group(1)
                emitted = False
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
                continue
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
            if (lead.startswith("thumb") or "px|" in lead
                    or _FILE_CAPTION.match(lead)):
                continue
            yield title, lead
            emitted = True
            collecting = False
        if title and not emitted and ":" not in title:
            yield title, ""


def main() -> None:
    t0 = time.time()
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))
    n = 0
    n_lead = 0

    def _progress():
        nonlocal n, n_lead
        for title, lead in iter_jawiki_articles():
            n += 1
            if lead:
                n_lead += 1
            if n % 200_000 == 0:
                print("pages %d leads %d %.0fs"
                      % (n, n_lead, time.time() - t0), flush=True)
            yield title, lead

    senses = build(_progress(), aliases=aliases,
                   extra_titles=list(aliases) + list(aliases.values()))
    save(senses, OUT)
    stats = report(senses, aliases)
    stats.update({
        "titles_seen": n,
        "titles_with_lead": n_lead,
        "aliases": len(aliases),
        "out": str(OUT),
        "seconds": round(time.time() - t0, 1),
        "spot": {
            s: [{"core": it["core"], "domain_tag": it["domain_tag"]}
                for it in senses.get(s, [])]
            for s in ("馬", "ウマ", "水", "自転車", "包丁")
        },
    })
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
