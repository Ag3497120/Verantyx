"""SQLite persistence for CrossStore — 増分保存で規模の天井を外す.

JSON checkpoint は全書き換え (190MB 級で数秒×毎回) なので、エージェント
記憶 (MCP / chat) や巨大 pour には SQLite を使う:

  * `save_sqlite(store, path)`      full sync (initial import)
  * `SqliteSync(store, path)`       write-through: add をバッファし
                                    flush() で UPSERT だけ書く (差分)
  * `load_sqlite(path)`             → CrossStore (in-memory as usual)

正直な注記: 実行時の作業セットは従来どおり RAM 上の dict。SQLite が
解くのは「保存コスト」「起動選択ロード」「配布形式」であり、RAM を
超えるストアのクエリはまだ対象外 (ロードを列で絞る `cores_like` はある)。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .cross_store import CrossStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS cores (
  core TEXT PRIMARY KEY, count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS facets (
  core TEXT NOT NULL, facet TEXT NOT NULL, count INTEGER NOT NULL,
  PRIMARY KEY (core, facet)
);
CREATE TABLE IF NOT EXISTS cap_stats (
  word TEXT PRIMARY KEY, cap INTEGER NOT NULL, low INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS provenance (
  core TEXT NOT NULL, facet TEXT NOT NULL,
  first_ts REAL, last_ts REAL, source TEXT,
  PRIMARY KEY (core, facet)
);
CREATE INDEX IF NOT EXISTS idx_facets_facet ON facets(facet);
"""


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    return conn


def save_sqlite(store: CrossStore, path: Path) -> Dict[str, Any]:
    """Full import of an in-memory store (replaces file contents)."""
    path = Path(path)
    if path.exists():
        path.unlink()
    conn = _connect(path)
    with conn:
        conn.executemany(
            "INSERT INTO cores VALUES (?,?)", store.core_count.items()
        )
        conn.executemany(
            "INSERT INTO facets VALUES (?,?,?)",
            (
                (c, f, n)
                for c, cross in store.crosses.items()
                for f, n in cross.items()
            ),
        )
        conn.executemany(
            "INSERT INTO cap_stats VALUES (?,?,?)",
            ((w, v[0], v[1]) for w, v in store.cap_stats.items()),
        )
        if store.track_provenance:
            conn.executemany(
                "INSERT INTO provenance VALUES (?,?,?,?,?)",
                (
                    (c, f, p[0], p[1], p[2])
                    for c, fs in store.provenance.items()
                    for f, p in fs.items()
                ),
            )
        conn.execute(
            "INSERT INTO meta VALUES ('source',?)", (store.source,)
        )
        conn.execute(
            "INSERT INTO meta VALUES ('n_sentences',?)",
            (str(store.n_sentences),),
        )
        conn.execute(
            "INSERT INTO meta VALUES ('track_provenance',?)",
            ("1" if store.track_provenance else "0",),
        )
    n = conn.execute("SELECT COUNT(*) FROM facets").fetchone()[0]
    conn.close()
    return {"cores": len(store.core_count), "facet_rows": n, "path": str(path)}


def load_sqlite(
    path: Path, *, cores_like: Optional[str] = None
) -> CrossStore:
    """Load into a normal in-memory CrossStore (optionally filtered)."""
    conn = _connect(Path(path))
    st = CrossStore()
    where, args = "", ()
    if cores_like:
        where, args = " WHERE core LIKE ?", (cores_like,)
    for core, cnt in conn.execute("SELECT core,count FROM cores" + where, args):
        st.core_count[core] = cnt
        st.crosses.setdefault(core, {})
    for core, facet, cnt in conn.execute(
        "SELECT core,facet,count FROM facets" + where, args
    ):
        st.crosses.setdefault(core, {})[facet] = cnt
    for w, cap, low in conn.execute("SELECT word,cap,low FROM cap_stats"):
        st.cap_stats[w] = [cap, low]
    meta = dict(conn.execute("SELECT k,v FROM meta"))
    st.source = meta.get("source", "")
    st.n_sentences = int(meta.get("n_sentences", 0) or 0)
    st.track_provenance = meta.get("track_provenance") == "1"
    if st.track_provenance:
        for core, facet, t0, t1, src in conn.execute(
            "SELECT core,facet,first_ts,last_ts,source FROM provenance" + where,
            args,
        ):
            st.provenance.setdefault(core, {})[facet] = [t0, t1, src]
    conn.close()
    from .lex_filters import proper_lexicon_from_stats

    st.proper_lexicon = proper_lexicon_from_stats(st.cap_stats)
    return st


class SqliteSync:
    """Write-through wrapper: mark cores dirty on add, flush deltas only."""

    def __init__(self, store: CrossStore, path: Path):
        self.store = store
        self.path = Path(path)
        self._dirty: set = set()
        self._orig_add = store.add

        def tracked_add(core, facts, **kw):
            self._orig_add(core, facts, **kw)
            self._dirty.add(str(core).casefold().strip())

        store.add = tracked_add  # type: ignore[method-assign]

    def flush(self) -> int:
        if not self._dirty:
            return 0
        conn = _connect(self.path)
        st = self.store
        with conn:
            for core in self._dirty:
                if core not in st.core_count:  # forgotten
                    conn.execute("DELETE FROM cores WHERE core=?", (core,))
                    conn.execute("DELETE FROM facets WHERE core=?", (core,))
                    continue
                conn.execute(
                    "INSERT INTO cores VALUES (?,?) "
                    "ON CONFLICT(core) DO UPDATE SET count=excluded.count",
                    (core, st.core_count[core]),
                )
                for f, n in st.crosses.get(core, {}).items():
                    conn.execute(
                        "INSERT INTO facets VALUES (?,?,?) "
                        "ON CONFLICT(core,facet) DO UPDATE SET count=excluded.count",
                        (core, f, n),
                    )
                for f, p in st.provenance.get(core, {}).items():
                    conn.execute(
                        "INSERT INTO provenance VALUES (?,?,?,?,?) "
                        "ON CONFLICT(core,facet) DO UPDATE SET "
                        "last_ts=excluded.last_ts, source=excluded.source",
                        (core, f, p[0], p[1], p[2]),
                    )
        conn.close()
        n = len(self._dirty)
        self._dirty.clear()
        return n
