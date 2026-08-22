"""The meaning sidecars as an INDEX, not as resident dictionaries.

Measured on the real build, one process, peak RSS:

    aliases   941,604 pairs        +488 MB
    senses    122,988 surfaces     +496 MB
    profiles  the predicate table  +1,304 MB
    lattice   built from writer     +132 MB
                                   ------
    a single `vera_diff` call       2.4 GB

That is not a door an application can open. The engine process inside
the IDE was being killed mid-call and the app, seeing no answer, fell
through to a DIFFERENT refusal — 「りんごとみかんの違い」 came back
UNKNOWN_NOT_PRESENT while the engine itself, run alone, answered
AMBIGUOUS_SENSE with the senses named. A refusal that changes shape
because a process died is the worst kind: it is a wrong answer wearing
a typed answer's clothes.

So the three big sidecars become one SQLite file and the callers stop
holding them. `SqliteMap` is read-through and dict-shaped — `.get`,
`in`, `[]` — because every consumer (sense_split, structural_diff,
meaning_descent) already speaks that shape and none of them iterates
the whole table. The lattice stays in memory: 132 MB is a fair price
for a structure every split consults, and it is built, not stored.

Same lesson as the quantized JGEN blocks: residency is the whole game.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional

BUILD = corpus_root() / "build"
INDEX = BUILD / "meaning_index.db"


class SqliteMap(Mapping):
    """A read-through mapping over one (key, value) table.

    ``decode`` turns the stored TEXT into what the caller expects — the
    identity for aliases, ``json.loads`` for senses and profiles. Reads
    are cached in a small dict because a diff asks for the same two
    subjects across six layers.
    """

    def __init__(self, conn: sqlite3.Connection, table: str,
                 decode=None, cache_max: int = 4096) -> None:
        self._conn = conn
        self._table = table
        self._decode = decode
        self._cache: Dict[str, Any] = {}
        self._cache_max = cache_max

    def __getitem__(self, key: str) -> Any:
        if key in self._cache:
            v = self._cache[key]
            if v is None:
                raise KeyError(key)
            return v
        row = self._conn.execute(
            "SELECT v FROM %s WHERE k = ?" % self._table, (key,)).fetchone()
        val = None if row is None else (
            self._decode(row[0]) if self._decode else row[0])
        if len(self._cache) < self._cache_max:
            self._cache[key] = val
        if val is None:
            raise KeyError(key)
        return val

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        try:
            self[str(key)]
            return True
        except KeyError:
            return False

    def __len__(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM %s" % self._table).fetchone()
        return int(row[0]) if row else 0

    def __iter__(self) -> Iterator[str]:
        # Present for the Mapping contract. Nothing on the answer path
        # iterates these tables; a caller that starts to should be
        # reading the json instead and saying why.
        for (k,) in self._conn.execute("SELECT k FROM %s" % self._table):
            yield k

    def __bool__(self) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM %s LIMIT 1" % self._table).fetchone() is not None


_conn: Optional[sqlite3.Connection] = None


def connection(path: Path = INDEX) -> Optional[sqlite3.Connection]:
    """The shared read-only connection, or None when unbuilt."""
    global _conn
    if _conn is None:
        if not Path(path).is_file():
            return None
        _conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True,
                                check_same_thread=False)
        _conn.execute("PRAGMA mmap_size=268435456")
    return _conn


def maps(path: Path = INDEX) -> Optional[Dict[str, SqliteMap]]:
    """aliases / senses / profiles / defs as read-through mappings."""
    conn = connection(path)
    if conn is None:
        return None
    out = {
        "aliases": SqliteMap(conn, "aliases"),
        "senses": SqliteMap(conn, "senses", json.loads),
        "profiles": SqliteMap(conn, "profiles", json.loads),
        "defs": SqliteMap(conn, "defs"),
    }
    # The polarity-marked profiles, when an index carries them. Optional
    # because an older index predates the table and every caller must
    # tolerate its absence rather than crash.
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        ("profiles_polar",),
    ).fetchone():
        out["profiles_polar"] = SqliteMap(conn, "profiles_polar", json.loads)
    return out
