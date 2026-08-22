"""Fold the meaning sidecars into one SQLite index (see meaning_index).

Reads the json sidecars once, writes build/meaning_index.db. The json
files stay on disk: they are the source of record, and the measurement
scripts (which run once and exit) keep reading them. Only the doors —
which live inside a long-running application — switch to the index.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BUILD = Path.home() / "Projects" / "vera-corpus" / "build"
OUT = BUILD / "meaning_index.db"

TABLES = ("aliases", "senses", "profiles", "profiles_polar", "defs")


def main() -> int:
    if OUT.exists():
        OUT.unlink()
    con = sqlite3.connect(OUT)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    for t in TABLES:
        con.execute("CREATE TABLE %s (k TEXT PRIMARY KEY, v TEXT)" % t)

    report = {}

    def pour(table: str, path: Path, encode) -> None:
        if not path.is_file():
            report[table] = "MISSING: %s" % path.name
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if table == "senses":
            data = data.get("senses", data)
        rows = ((k, encode(v)) for k, v in data.items())
        con.executemany(
            "INSERT OR REPLACE INTO %s (k, v) VALUES (?, ?)" % table, rows)
        con.commit()
        report[table] = len(data)
        del data

    ident = lambda v: v if isinstance(v, str) else json.dumps(
        v, ensure_ascii=False)
    dump = lambda v: json.dumps(v, ensure_ascii=False)

    pour("aliases", BUILD / "jawiki_aliases.json", ident)
    pour("senses", BUILD / "jawiki_senses.json", dump)
    pour("profiles", BUILD / "predicate_profiles.json", dump)
    # The polarity-marked build (¬流れる). Kept in its OWN table: the
    # plain profiles are what every burned measurement was taken on, and
    # a door that reads the marked ones must be able to say which it read.
    pour("profiles_polar", BUILD / "predicate_profiles_polar.json", dump)
    pour("defs", BUILD / "jawiki_defs.json", ident)

    con.execute("VACUUM")
    con.close()
    report["out"] = str(OUT)
    report["bytes"] = OUT.stat().st_size
    print(json.dumps({"verdict": "ANSWER", **report},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
