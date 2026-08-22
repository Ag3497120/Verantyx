"""CrossStore — core ごとに1つの十字を累積する多十字ネットワークの土台.

大量投入の欠落部品: "apple" が 1000 文に出たとき facets を **1つの apple
十字に累積・重み付け** する。殻 (6腕) の spill/上書きではなく、
core → {facet: count} を無制限に蓄え、読み出し時に上位 facet を
決定論で腕に載せる。

  add(core, facts)         → counts 累積 (mass = 出現回数)
  top_facets(core, k)      → count 降順・同数はアルファベット順 (決定論)
  ingest_rows(rows)        → 文分割 → classify_sentence → 累積
  save / load              → JSON checkpoint (途中再開可)

LM なし。retrieval + consensus 接続は consensus_store.py。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .en_decompose import classify_sentence, split_sentences
from .lex_filters import (
    is_junk_core,
    is_junk_facet,
    proper_lexicon_from_stats,
    proper_runs,
    sense_key,
    update_cap_stats,
)


@dataclass
class CrossStore:
    # core → facet → count
    crosses: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # core → 出現回数 (質量の元; facet ゼロ文でもカウント)
    core_count: Dict[str, int] = field(default_factory=dict)
    n_sentences: int = 0
    n_rows: int = 0
    source: str = ""
    # word → [n_cap_mid_sentence, n_lower]; 文頭大文字の二段判定に使う
    cap_stats: Dict[str, List[int]] = field(default_factory=dict)
    proper_lexicon: set = field(default_factory=set)
    # 出典・時刻 (opt-in; 大量 pour では既定オフ):
    #   provenance[core][facet] = [first_ts, last_ts, source_snippet]
    track_provenance: bool = False
    provenance: Dict[str, Dict[str, List[Any]]] = field(default_factory=dict)
    #: source label → {"published": free-form date string}. What makes
    #: "update" distinguishable from "dispute": two poles of one aspect
    #: from sources whose publication times ORDER are a supersession, not a
    #: disagreement — a road closed at 9:00 and reopened at 15:00 is one
    #: story, and reporting it as a conflict is how a tool loses the trust
    #: of the first responder who reads it.
    source_meta: Dict[str, Dict[str, str]] = field(default_factory=dict)
    #: core → the facets that should occupy its four faces, in read order.
    #: Computed once before shipping by `verantyx.placement`, never at query
    #: time. Absent for every store built before that module existed, and the
    #: shell builder falls back to top_facets when a core is missing here —
    #: so an old store keeps its exact historical behaviour.
    placement: Dict[str, List[str]] = field(default_factory=dict)
    #: Document labels this store ingested. `ingest_documents` appends
    #: "(reported by X)" to every sentence so the label reaches provenance,
    #: which also lands it in the cross as an ordinary facet — and an arm has
    #: four faces, so the citation was costing one of them. An event with
    #: 主体/対象/行為/原因 needs all four and had three. Kept in the store
    #: (it is real provenance) and skipped when filling faces.
    source_labels: set = field(default_factory=set)
    #: What produced `placement`: policy, weight, query source, measured delta.
    #: A placement without this is unattributable, and an unattributable
    #: geometry is the thing this project keeps refusing to ship.
    placement_meta: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # accumulate
    # ------------------------------------------------------------------
    def add(
        self,
        core: str,
        facts: Iterable[str],
        *,
        source: Optional[str] = None,
    ) -> None:
        core = str(core).casefold().strip()
        if not core:
            return
        cross = self.crosses.setdefault(core, {})
        self.core_count[core] = self.core_count.get(core, 0) + 1
        for f in facts:
            f = str(f).casefold().strip()
            if not f or f == core:
                continue
            cross[f] = cross.get(f, 0) + 1
            if self.track_provenance:
                import time

                now = round(time.time(), 2)
                slot = self.provenance.setdefault(core, {})
                if f in slot:
                    slot[f][1] = now
                    if source:
                        slot[f][2] = source[:200]
                else:
                    slot[f] = [now, now, (source or "")[:200]]

    # ------------------------------------------------------------------
    # 矛盾検出: key:value facet は同一 key で排他 (db:postgres vs db:mysql)
    # ------------------------------------------------------------------
    def contradictions(self, core: str) -> List[Dict[str, Any]]:
        cross = self.crosses.get(str(core).casefold().strip(), {})
        by_key: Dict[str, List[str]] = {}
        for f in cross:
            if ":" in f:
                k, v = f.split(":", 1)
                if k and v:
                    by_key.setdefault(k, []).append(f)
        # Two DIFFERENT values are not a disagreement unless they sit on
        # opposite POLES. 開設 and 開館 are synonyms — both the positive side
        # of the 開設 aspect — and 宇城市 saying 「避難所を開設しています」 while
        # 熊本市 says 「避難所として開館」 is two municipalities AGREEING. It
        # was reported as a conflict, which is the failure mode that makes an
        # information officer stop reading the board: a contradiction report
        # whose contradictions are not contradictions is worse than none.
        #
        # Found blind on municipal HTML, the fourth genre. The vocabulary has
        # carried the pole of every term since it was written; the detector
        # simply never asked.
        def _poles(values: List[str]) -> set:
            from .ja_grammar import ASPECT_OF as _ja
            from .polarity import _ASPECT_OF as _en
            signs = set()
            for v in values:
                word = v.split(":", 1)[1]
                if word.startswith("not_"):
                    base = word[4:]
                    hit = _ja.get(base) or _en.get(base)
                    if hit:
                        signs.add("-" if hit[1] == "+" else "+")
                    continue
                hit = _ja.get(word) or _en.get(word)
                if hit:
                    signs.add(hit[1])
                else:
                    # A value with no known pole cannot be shown to agree, so
                    # it is kept as its own side rather than assumed to match.
                    signs.add(word)
            return signs

        out: List[Dict[str, Any]] = []
        for k, vals in sorted(by_key.items()):
            if len(vals) > 1 and len(_poles(vals)) < 2:
                continue
            if len(vals) > 1:
                entry: Dict[str, Any] = {
                    "key": k,
                    "values": sorted(vals),
                    "counts": {v: cross[v] for v in vals},
                }
                if self.track_provenance and core in self.provenance:
                    entry["provenance"] = {
                        v: self.provenance[core].get(v) for v in vals
                    }
                out.append(entry)
        return out

    def ingest_sentence(self, text: str) -> Optional[str]:
        # Read structure from the CLAIM, keep the citation in provenance.
        # `ingest_documents` appends "(reported by <label>)", and the English
        # decomposer's word pattern happily split that label into facets —
        # `source_labels` only ever held the label WHOLE, so the skip that
        # protects a face never matched its pieces.
        from .lang import strip_attribution

        claim = strip_attribution(text) or text
        unit = classify_sentence(claim)
        if unit.core is None or is_junk_core(unit.core):
            return None
        runs = proper_runs(claim)
        key, run_rest = sense_key(
            unit.core, claim, runs, proper_lexicon=self.proper_lexicon
        )
        drop = set(run_rest)
        # 他の proper run に属する facts はその複合語に合流させる
        facts: List[str] = []
        for f in unit.facts:
            if f in drop or is_junk_facet(f):
                continue
            merged = None
            for run in runs:
                if f in run and unit.core not in run:
                    merged = "_".join(run) + "#p"
                    break
            facts.append(merged or f)
        self.add(key, dict.fromkeys(facts), source=text.strip())
        self.n_sentences += 1
        return key

    def scan_cap_stats(self, rows: Iterable[str]) -> int:
        """Pass 1: 大文字統計だけ累積し proper_lexicon を再構築."""
        n = 0
        for row in rows:
            for sent in split_sentences(row):
                update_cap_stats(self.cap_stats, sent)
                n += 1
        self.proper_lexicon = proper_lexicon_from_stats(self.cap_stats)
        return n

    def ingest_rows(
        self,
        rows: Iterable[str],
        *,
        max_sentences: Optional[int] = None,
        checkpoint_path: Optional[Path] = None,
        checkpoint_every: int = 5000,
    ) -> Dict[str, Any]:
        """Stream rows → sentences → accumulate. No full materialization."""
        done = 0
        for row in rows:
            self.n_rows += 1
            for sent in split_sentences(row):
                if max_sentences is not None and done >= max_sentences:
                    return self.report()
                if self.ingest_sentence(sent) is not None:
                    done += 1
                    if (
                        checkpoint_path is not None
                        and done % checkpoint_every == 0
                    ):
                        self.save(checkpoint_path)
        return self.report()

    # ------------------------------------------------------------------
    # read out
    # ------------------------------------------------------------------
    def top_facets(self, core: str, k: int = 4) -> List[Tuple[str, int]]:
        cross = self.crosses.get(str(core).casefold().strip())
        if not cross:
            return []
        items = sorted(cross.items(), key=lambda kv: (-kv[1], kv[0]))
        return items[:k]

    def mass(self, core: str) -> float:
        return float(self.core_count.get(str(core).casefold().strip(), 0))

    def has(self, core: str) -> bool:
        return str(core).casefold().strip() in self.crosses

    def n_cores(self) -> int:
        return len(self.crosses)

    def n_facet_links(self) -> int:
        return sum(len(c) for c in self.crosses.values())

    def report(self) -> Dict[str, Any]:
        return {
            "n_cores": self.n_cores(),
            "n_facet_links": self.n_facet_links(),
            "n_sentences": self.n_sentences,
            "n_rows": self.n_rows,
            "source": self.source,
        }

    # ------------------------------------------------------------------
    # checkpoint
    # ------------------------------------------------------------------
    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() in _SQLITE_SUFFIXES:
            _save_sqlite(self, path)
            return
        payload = {
            "crosses": self.crosses,
            "core_count": self.core_count,
            "n_sentences": self.n_sentences,
            "n_rows": self.n_rows,
            "source": self.source,
            "cap_stats": self.cap_stats,
            "provenance": self.provenance if self.track_provenance else {},
            "track_provenance": self.track_provenance,
            "source_meta": self.source_meta,
            "source_labels": sorted(self.source_labels),
            "placement": self.placement,
            "placement_meta": self.placement_meta,
        }
        # Atomic replace: the old failure mode was a half-written JSON on
        # crash mid-save, which loads as nothing — the store looked empty
        # rather than damaged. Correctness over speed, per the operating
        # decision: a slow save that cannot corrupt beats a fast one that can.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "CrossStore":
        path = Path(path)
        if path.suffix.lower() in _SQLITE_SUFFIXES:
            return _load_sqlite(cls, path)
        d = json.loads(path.read_text())
        st = cls(
            crosses={k: dict(v) for k, v in d.get("crosses", {}).items()},
            core_count=dict(d.get("core_count", {})),
            n_sentences=int(d.get("n_sentences", 0)),
            n_rows=int(d.get("n_rows", 0)),
            source=str(d.get("source", "")),
            cap_stats={k: list(v) for k, v in d.get("cap_stats", {}).items()},
            track_provenance=bool(d.get("track_provenance", False)),
            provenance={
                c: {f: list(p) for f, p in fs.items()}
                for c, fs in d.get("provenance", {}).items()
            },
        )
        st.source_meta = {k: dict(v) for k, v in d.get("source_meta", {}).items()}
        st.source_labels = set(d.get("source_labels", []))
        st.placement = {k: list(v) for k, v in d.get("placement", {}).items()}
        st.placement_meta = dict(d.get("placement_meta", {}))
        st.proper_lexicon = proper_lexicon_from_stats(st.cap_stats)
        return st


def pour_corpus(
    *,
    source: str = "auto",
    max_rows: Optional[int] = 2000,
    max_sentences: Optional[int] = None,
    checkpoint_path: Optional[Path] = None,
    store: Optional[CrossStore] = None,
    two_pass: bool = True,
    checkpoint_every: int = 5000,
) -> Tuple[CrossStore, Dict[str, Any]]:
    """corpus_en stream → CrossStore accumulate (resumable via ``store``).

    two_pass: pass 1 で大文字統計 → proper_lexicon 構築 → pass 2 で投入
    (文頭大文字の二段判定)。イテレータは source から作り直す。
    """
    from .corpus_en import iter_english_rows

    st = store or CrossStore()
    if two_pass:
        rows1, _tag, _fb, _meta = iter_english_rows(
            source=source, max_rows=max_rows
        )
        st.scan_cap_stats(rows1)

    rows, tag, fallback, meta = iter_english_rows(source=source, max_rows=max_rows)
    st.source = tag
    rep = st.ingest_rows(
        rows,
        max_sentences=max_sentences,
        checkpoint_path=checkpoint_path,
        checkpoint_every=checkpoint_every,
    )
    rep.update(
        {
            "fallback_reason": fallback,
            "meta": meta,
            "two_pass": two_pass,
            "proper_lexicon_size": len(st.proper_lexicon),
        }
    )
    if checkpoint_path is not None:
        st.save(checkpoint_path)
    return st, rep


# ---------------------------------------------------------------------------
# SQLite persistence — chosen for crash-safety, not speed
# ---------------------------------------------------------------------------
#
# The JSON checkpoint rewrites the whole store as one string; measured at
# 208 MB on an accumulated store, every save serialised a fifth of a
# gigabyte and a crash mid-write left a file that parses as nothing. SQLite
# fixes the failure mode first: WAL journaling means a crash mid-transaction
# rolls back to the previous good state, and readers are never blocked by a
# writer. The write is still a full rewrite inside one transaction —
# incremental upserts are a later optimisation, deliberately deferred,
# because "works and cannot corrupt" was the requirement and clever partial
# writes are where corruption bugs live.
#
# Store paths ending in .sqlite / .sqlite3 / .db use this backend; .json
# keeps the original format, so existing stores and sidecar tooling are
# untouched. One store, either format, identical contents — the round-trip
# equality is pinned in the eval suite.

_SQLITE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}


def _save_sqlite(store: "CrossStore", path: Path) -> None:
    import sqlite3

    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        with con:
            con.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
            con.execute("CREATE TABLE IF NOT EXISTS crosses ("
                        "core TEXT, facet TEXT, n INTEGER, "
                        "PRIMARY KEY (core, facet))")
            con.execute("CREATE TABLE IF NOT EXISTS provenance ("
                        "core TEXT, facet TEXT, slot TEXT, "
                        "PRIMARY KEY (core, facet))")
            con.execute("DELETE FROM crosses")
            con.execute("DELETE FROM provenance")
            con.execute("DELETE FROM meta")
            con.executemany(
                "INSERT INTO crosses VALUES (?, ?, ?)",
                ((c, f, n) for c, fs in store.crosses.items()
                 for f, n in fs.items()))
            if store.track_provenance:
                con.executemany(
                    "INSERT INTO provenance VALUES (?, ?, ?)",
                    ((c, f, json.dumps(list(slot), ensure_ascii=False))
                     for c, fs in store.provenance.items()
                     for f, slot in fs.items()))
            meta = {
                "core_count": json.dumps(store.core_count, ensure_ascii=False),
                "n_sentences": str(store.n_sentences),
                "n_rows": str(store.n_rows),
                "source": store.source,
                "cap_stats": json.dumps(store.cap_stats, ensure_ascii=False),
                "track_provenance": "1" if store.track_provenance else "0",
                "source_meta": json.dumps(store.source_meta, ensure_ascii=False),
                # These three were silently dropped by the first version of
                # this backend, while the comment above promised round-trip
                # equality. Found when a store baked by `placement --write`
                # came back with zero placed cores: the bake ran, the gate
                # accepted, the save discarded the result. source_labels
                # matters just as much — face-filling skips citation labels,
                # and a store that forgets its labels spends faces on them.
                "source_labels": json.dumps(sorted(store.source_labels),
                                            ensure_ascii=False),
                "placement": json.dumps(store.placement, ensure_ascii=False),
                "placement_meta": json.dumps(store.placement_meta,
                                             ensure_ascii=False),
            }
            con.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
    finally:
        con.close()


def _load_sqlite(cls, path: Path) -> "CrossStore":
    import sqlite3

    con = sqlite3.connect(path)
    try:
        meta = dict(con.execute("SELECT k, v FROM meta"))
        crosses: dict = {}
        for core, facet, n in con.execute("SELECT core, facet, n FROM crosses"):
            crosses.setdefault(core, {})[facet] = n
        provenance: dict = {}
        for core, facet, slot in con.execute(
                "SELECT core, facet, slot FROM provenance"):
            provenance.setdefault(core, {})[facet] = json.loads(slot)
    finally:
        con.close()
    st = cls(
        crosses=crosses,
        core_count=json.loads(meta.get("core_count", "{}")),
        n_sentences=int(meta.get("n_sentences", "0")),
        n_rows=int(meta.get("n_rows", "0")),
        source=meta.get("source", ""),
        cap_stats={k: list(v) for k, v in
                   json.loads(meta.get("cap_stats", "{}")).items()},
        track_provenance=meta.get("track_provenance") == "1",
        provenance=provenance,
    )
    st.source_meta = json.loads(meta.get("source_meta", "{}"))
    st.source_labels = set(json.loads(meta.get("source_labels", "[]")))
    st.placement = {k: list(v) for k, v in
                    json.loads(meta.get("placement", "{}")).items()}
    st.placement_meta = json.loads(meta.get("placement_meta", "{}"))
    st.proper_lexicon = proper_lexicon_from_stats(st.cap_stats)
    return st
