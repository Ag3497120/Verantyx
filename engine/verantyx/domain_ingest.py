"""A document becomes a domain's vocabulary. The grammar is not rebuilt.

The measured split
------------------
Across an encyclopedia (1,419,406 leads), the Civil Code, the Labour
Standards Act and a two-page contest brief, a shared verb's dominant case
agrees at 0.735–0.857 against a 0.28 shuffled control, and the mean
co-occurrence pattern is 1.247 in law against 1.221 in the encyclopedia.

Grammar transfers. Vocabulary does not — 33% of the encyclopedia's fillers
are proper nouns and 70% occur exactly once.

So a new domain costs its **nouns**, not its grammar. This module reads a
document and writes one fillers table (and its patterns, which are kept
beside the shared ones rather than replacing them). `frames` is never
touched: it is the thin shared map.

Layered, not merged
-------------------
Domain tables are separate tables. They are never folded into the shared
ones, and a query reads them in order — domain first, shared behind. This
project has measured what merging costs: pooling stores whose notion of
agreement differs produced an out-of-corpus quorum of 0→8 and dropped
answers from 284 to 208, six times out of six. Layering gives the same
reach with the origin still attached.

    python3.11 -m verantyx.domain_ingest <name> <path>
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

CASES: Tuple[str, ...] = ("が", "を", "に", "で", "へ", "と", "から", "まで")
#: Domain names become table names, so they are restricted to what cannot
#: change the meaning of a statement. Not a sanitiser trying to be clever —
#: anything outside this is refused rather than rewritten.
_NAME = re.compile(r"^[a-z0-9_]{1,32}$")


def _tagger():
    import fugashi
    return fugashi.Tagger()


def read_document(path: Path) -> str:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:                       # pragma: no cover
            from PyPDF2 import PdfReader          # type: ignore
        text = "\n".join((pg.extract_text() or "") for pg in
                         PdfReader(str(p)).pages)
    else:
        text = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix.lower() in (".xml", ".html", ".htm"):
        text = re.sub(r"<[^>]+>", "", text)
    # Bullet glyphs sit where a noun would and became fillers (o正規表現).
    return re.sub(r"^\s*[o•・\-\*]\s*", "", text, flags=re.M)


def extract(text: str) -> Dict[str, Any]:
    """Fillers and patterns for one document. Frames are NOT produced.

    The same reading the shared map was built with, so a domain's numbers
    are comparable to it: 並立の と demoted when a later case arrives,
    サ変 and its potential restored onto the noun, the noun run before a
    particle taken as that particle's filler.
    """
    tagger = _tagger()
    fillers: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    patterns: Dict[str, Counter] = defaultdict(Counter)
    verbs: Counter = Counter()

    for line in (s.strip() for s in re.split(r"[。\n]", text)):
        if len(line) < 8:
            continue
        pending: list = []
        run: list = []
        sahen: Optional[str] = None
        for tok in tagger(line):
            f = tok.feature
            pos1 = f.pos1
            if pos1 == "助詞" and tok.surface in CASES:
                if tok.surface != "と":
                    pending = [x for x in pending if x[0] != "と"]
                pending.append((tok.surface, "".join(run)))
                run, sahen = [], None
                continue
            if pos1 == "動詞":
                lemma = getattr(f, "orthBase", None) or tok.surface
                used = ""
                if lemma in ("する", "できる") and sahen:
                    lemma, used = sahen + lemma, sahen
                verbs[lemma] += 1
                if pending:
                    patterns[lemma][frozenset(c for c, _ in pending)] += 1
                for case, noun in pending:
                    if noun and noun != used:
                        fillers[(lemma, case)][noun] += 1
                pending, run, sahen = [], [], None
                continue
            if pos1 == "名詞":
                run.append(tok.surface)
                sahen = (tok.surface
                         if getattr(f, "pos3", "") == "サ変可能" else None)
                continue
            run, sahen = [], None

    return {"fillers": fillers, "patterns": patterns, "verbs": verbs}


def register(name: str, text: str, index: Optional[Path] = None) -> Dict[str, Any]:
    """Write a domain's tables. Refuses rather than writes something thin.

    A domain with almost no verbs would compose almost nothing and would
    look, from the outside, exactly like a domain that was registered and
    simply had nothing to say. The refusal names the count instead.
    """
    from .meaning_index import INDEX
    from .preregistration import Gate, guard, require_environment

    void = require_environment("fugashi", "unidic_lite")
    if void:
        return void
    if not _NAME.match(name or ""):
        return {"verdict": "UNKNOWN_DOMAIN_NAME",
                "given": name,
                "note": "分野名は a-z 0-9 _ のみ。書き換えず拒否する"}

    got = extract(text)
    verbs, fillers, patterns = got["verbs"], got["fillers"], got["patterns"]

    gates = [
        Gate("has_verbs", len(verbs) >= 5,
             "at least five verbs were read (%d)" % len(verbs)),
        Gate("has_fillers", len(fillers) >= 5,
             "at least five slots were filled (%d)" % len(fillers)),
    ]

    path = Path(index) if index else INDEX
    ftab, ptab = "fillers__%s" % name, "patterns__%s" % name

    def _write():
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        for tab in (ftab, ptab):
            conn.execute("DROP TABLE IF EXISTS %s" % tab)
            conn.execute(
                "CREATE TABLE %s (k TEXT PRIMARY KEY, v TEXT NOT NULL)" % tab)
        conn.executemany(
            "INSERT OR REPLACE INTO %s (k, v) VALUES (?, ?)" % ftab,
            (("%s\t%s" % k, json.dumps(dict(v), ensure_ascii=False))
             for k, v in fillers.items()))
        conn.executemany(
            "INSERT OR REPLACE INTO %s (k, v) VALUES (?, ?)" % ptab,
            ((v, json.dumps({"|".join(sorted(p)): n for p, n in c.items()},
                            ensure_ascii=False))
             for v, c in patterns.items()))
        conn.commit()
        conn.close()
        return "%s / %s" % (ftab, ptab)

    out = guard(gates, _write, what="domain tables")
    out |= {"domain": name, "verbs": len(verbs), "slots": len(fillers),
            "patterns": len(patterns),
            "note": "frames は共有のまま。この分野が持つのは語彙だけ"}
    return out


def domains(index: Optional[Path] = None) -> list:
    from .meaning_index import connection
    conn = connection(Path(index)) if index else connection()
    if conn is None:
        return []
    return sorted(
        r[0][len("fillers__"):] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'fillers__%'"))


if __name__ == "__main__":                        # pragma: no cover
    if len(sys.argv) < 3:
        raise SystemExit("usage: python3.11 -m verantyx.domain_ingest "
                         "<name> <path>")
    print(json.dumps(register(sys.argv[1], read_document(Path(sys.argv[2]))),
                     ensure_ascii=False, indent=2))
