"""Case frames into the index, so nothing loads them to answer one question.

`meaning_index` exists because holding the meaning sidecars resident cost
2.4 GB and got the engine killed mid-call inside the IDE — and the app,
seeing no answer, fell through to a DIFFERENT refusal. The frames are
smaller today (12.6 MB of fillers) but they are on the same road: a
composer that must read every verb's fillers to write one sentence is a
door an application cannot open twice.

So they go in beside the others, in the same file, on the same connection.
This is not a migration to be done later — the frames were written on
2026-08-16 and are indexed the same day, before anything reads the json.

Three tables, one shape each, all read-through:

    frames    verb        -> {case: count}
    fillers   verb\\tcase  -> {noun: count}
    patterns  verb        -> {"に|を": count}   cases that co-occurred

`fillers` is keyed by the pair rather than nested under the verb because a
composer asks for one slot at a time; nesting would make every slot lookup
pull every slot the verb has.

    python3 tools/index_frames.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.meaning_index import INDEX  # noqa: E402
from verantyx.preregistration import Gate, guard  # noqa: E402

BUILD = Path.home() / "Projects" / "vera-corpus" / "build"
SOURCES = {
    "frames": BUILD / "case_frames.json",
    "fillers": BUILD / "frame_fillers.json",
    "patterns": BUILD / "frame_patterns.json",
}


def build(path: Path = INDEX) -> dict:
    missing = [n for n, p in SOURCES.items() if not p.is_file()]
    payload = {}
    if not missing:
        for name, src in SOURCES.items():
            payload[name] = json.loads(src.read_text(encoding="utf-8"))

    # The gates that matter are about the DATA, not the copy: an index
    # built from an empty or half-written export is worse than no index,
    # because every consumer would read it as authoritative.
    gates = [
        Gate("sources_present", not missing, "all three exports exist"),
        Gate("frames_nonempty", bool(payload.get("frames")),
             "case_frames.json holds verbs"),
        Gate("fillers_nonempty", bool(payload.get("fillers")),
             "frame_fillers.json holds slots"),
        Gate("kana_verbs_present",
             all(v in payload.get("frames", {})
                 for v in ("する", "ある", "いる")),
             "する/ある/いる survived — the C2 failure that once wrote a "
             "store with them removed must not be indexed"),
    ]

    def _write():
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        for name in SOURCES:
            conn.execute("DROP TABLE IF EXISTS %s" % name)
            conn.execute(
                "CREATE TABLE %s (k TEXT PRIMARY KEY, v TEXT NOT NULL)" % name)
            conn.executemany(
                "INSERT OR REPLACE INTO %s (k, v) VALUES (?, ?)" % name,
                ((k, json.dumps(val, ensure_ascii=False))
                 for k, val in payload[name].items()))
        conn.commit()
        rows = {n: conn.execute("SELECT COUNT(*) FROM %s" % n).fetchone()[0]
                for n in SOURCES}
        conn.close()
        return rows

    result = guard(gates, _write, what="frame tables")
    result["missing_sources"] = missing
    return result


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
