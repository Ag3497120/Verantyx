"""The redirect sidecar: jawiki's alias map, built from #REDIRECT lines.

The full shelf left パワハラ and クォータニオン as holes because they
are redirects — the encyclopedia's own alias layer, which the lead
parser deliberately skips (a redirect has no lead). This builder reads
exactly what the parser skips: every page whose text begins with
#REDIRECT/#転送 becomes one (alias -> canonical title) pair in
build/jawiki_aliases.json.

A sidecar, not a store: aliases are lookup material for the coverage
atlas (「この語は正題Xの別名で、Xなら棚が持つ」), never cores, never
votes. Fragments (#section targets) are cut to the page title; targets
in other namespaces are dropped.
"""
import bz2
import json
import re
import sys
import time
from pathlib import Path

DUMP = (Path.home() / "Projects" / "vera-corpus" / "corpora" / "jawiki"
        / "jawiki-latest-pages-articles.xml.bz2")
OUT = Path.home() / "Projects" / "vera-corpus" / "build" / "jawiki_aliases.json"

TITLE = re.compile(r"<title>([^<]+)</title>")
TEXT = re.compile(r"<text[^>]*>(.*)")
REDIRECT = re.compile(
    r"^#(?:REDIRECT|redirect|Redirect|転送)\s*\[\[([^\]#|]+)", re.IGNORECASE)

t0 = time.time()
aliases = {}
title = None
with bz2.open(DUMP, "rt", errors="replace") as fh:
    for raw in fh:
        m = TITLE.search(raw)
        if m:
            title = m.group(1)
            continue
        if title is None or ":" in title:
            continue
        t = TEXT.search(raw)
        if not t:
            continue
        r = REDIRECT.match(t.group(1).strip())
        if r:
            target = r.group(1).strip()
            if target and ":" not in target and target != title:
                aliases[title] = target
        title = None

OUT.write_text(json.dumps(aliases, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"aliases": len(aliases), "out": str(OUT),
                  "seconds": round(time.time() - t0, 1),
                  "spot": {k: aliases[k] for k in
                           ["パワハラ", "クォータニオン"] if k in aliases}},
                 ensure_ascii=False))
