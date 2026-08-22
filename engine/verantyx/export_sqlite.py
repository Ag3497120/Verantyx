"""The federation as one SQLite file — the form it can actually be published in.

`build_ja` writes `federation.pkl`, and pickle is the wrong thing to hand to
anyone. `pickle.loads` executes whatever the file says to execute, so a
published .pkl is a published code-execution primitive; that is why Hugging
Face scans for them and warns. It is also opaque — a reader who wants to
check a number in the model card cannot look inside it without running the
project's own code, which is the same circularity this project keeps trying
to remove from its measurements.

SQLite fixes both. The file loads without executing anything, and anyone can
audit the claims directly:

    sqlite3 vera.db "SELECT count(*) FROM cores"
    sqlite3 vera.db "SELECT facet, count FROM facets
                     WHERE core='正当防衛' ORDER BY count DESC LIMIT 5"

## One file, not 6,037

`CrossStore.save()` already speaks SQLite, but a federation is a dict of
domain -> leaf -> store, and one file per leaf is not a distribution. The
leaf becomes a column instead, which is also what lets a reader ask which
statute division a facet came from — a question the per-store format cannot
answer at all.

## Both languages in one file, still two sovereigns

`lang` is a column, and `load` hands back one store per language exactly as
the pickle path did. Storing them together is not pooling them: nothing ever
queries across the column, because a cross-language census counts a tokenizer
collision as corroboration (see `polyglot`).

The distributed file must answer what the built one answers; `--verify`
checks that on a question bank rather than trusting the round trip.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import argparse
import json
import pickle
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = """
PRAGMA journal_mode=OFF;
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS leaves (
  id INTEGER PRIMARY KEY, lang TEXT NOT NULL,
  domain TEXT NOT NULL, name TEXT NOT NULL,
  merged INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cores (
  leaf INTEGER NOT NULL, core TEXT NOT NULL, count INTEGER NOT NULL,
  PRIMARY KEY (leaf, core)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS facets (
  leaf INTEGER NOT NULL, core TEXT NOT NULL,
  facet TEXT NOT NULL, count INTEGER NOT NULL,
  PRIMARY KEY (leaf, core, facet)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS labels (leaf INTEGER NOT NULL, label TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS edges (
  core TEXT NOT NULL, f1 TEXT NOT NULL, f2 TEXT NOT NULL,
  PRIMARY KEY (core, f1, f2)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS caps (
  leaf INTEGER NOT NULL, word TEXT NOT NULL,
  cap INTEGER NOT NULL, low INTEGER NOT NULL,
  PRIMARY KEY (leaf, word)
) WITHOUT ROWID;
"""

#: Built after the bulk insert, never before — building an index per row is
#: what made the first version take minutes instead of seconds.
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_cores_core ON cores(core);
CREATE INDEX IF NOT EXISTS idx_facets_core ON facets(core);
CREATE INDEX IF NOT EXISTS idx_facets_facet ON facets(facet);
CREATE INDEX IF NOT EXISTS idx_labels_leaf ON labels(leaf);
CREATE INDEX IF NOT EXISTS idx_edges_core ON edges(core);
"""


def _stores(root: Path) -> List[Tuple[str, str, str, Any]]:
    """(lang, domain, leaf name, store) in the order `vera.load` merges them.

    Insertion order, NOT sorted. The merge below overwrites rather than adds,
    so the order decides the answer, and sorting the leaves here silently
    changed two of twelve bank questions the first time this was written.
    """
    out: List[Tuple[str, str, str, Any]] = []
    fed = root / "build" / "federation.pkl"
    if fed.exists():
        doms = pickle.loads(fed.read_bytes())
        for d in doms:
            for name in doms[d]:
                out.append(("ja", d, name, doms[d][name]))
    eng = root / "build" / "english.pkl"
    if eng.exists():
        obj = pickle.loads(eng.read_bytes())
        if isinstance(obj, dict):
            for name in obj:
                out.append(("en", "en", name, obj[name]))
        else:
            out.append(("en", "en", "english", obj))
    return out


def export(root: Path, out: Path) -> Dict[str, Any]:
    t0 = time.time()
    out = Path(out)
    if out.exists():
        out.unlink()
    con = sqlite3.connect(str(out))
    con.executescript(SCHEMA)

    n_cores = n_facets = 0
    by_lang: Dict[str, int] = {}
    stores_list = _stores(root)
    with con:
        for i, (lang, dom, name, st) in enumerate(stores_list):
            # `merged` records that this leaf was one of many folded into a
            # single sovereign, which is what decides whether its core_count
            # survives the load. See `load`.
            con.execute("INSERT INTO leaves VALUES (?,?,?,?,?)",
                        (i, lang, dom, name, int(lang == "ja")))
            labels = getattr(st, "source_labels", set()) or set()
            con.executemany("INSERT INTO labels VALUES (?,?)",
                            ((i, l) for l in sorted(labels)))
            cc = getattr(st, "core_count", {}) or {}
            con.executemany(
                "INSERT OR REPLACE INTO cores VALUES (?,?,?)",
                ((i, c, int(cc.get(c, 0))) for c in st.crosses))
            rows = [(i, c, f, int(n))
                    for c, cross in st.crosses.items()
                    for f, n in cross.items()]
            con.executemany("INSERT OR REPLACE INTO facets VALUES (?,?,?,?)",
                            rows)
            caps = getattr(st, "cap_stats", {}) or {}
            con.executemany(
                "INSERT OR REPLACE INTO caps VALUES (?,?,?,?)",
                ((i, w, int(v[0]), int(v[1])) for w, v in caps.items()
                 if isinstance(v, (list, tuple)) and len(v) >= 2))
            n_cores += len(st.crosses)
            n_facets += len(rows)
            by_lang[lang] = by_lang.get(lang, 0) + 1
    con.executescript(INDEXES)
    with con:
        con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
            ("format", "vera-federation-1"),
            ("built", time.strftime("%Y-%m-%dT%H:%M:%S")),
            ("leaves", str(sum(by_lang.values()))),
            ("cores", str(n_cores)),
            ("facets", str(n_facets)),
            ("languages", json.dumps(by_lang, sort_keys=True)),
        ])
    con.execute("VACUUM")
    con.close()
    return {"path": str(out), "mb": round(out.stat().st_size / 1048576, 1),
            "leaves": sum(by_lang.values()), "cores": n_cores,
            "facets": n_facets, "by_language": by_lang,
            "seconds": round(time.time() - t0, 1)}


def export_edges(root: Path, out: Path, *, top: int = 32,
                 max_group: int = 12) -> Dict[str, Any]:
    """The edge sidecar: same-sentence facet pairs, in their own file.

    A face holds an item; an edge holds a RELATION, and the relation the
    corpus attests is same-sentence co-occurrence — provenance stores the
    originating sentence per (core, facet), so facets sharing a snippet
    were written together in one sentence. Measured: 91% of cores carry an
    edge, and every silenced evidence-tied core sampled (97/97) had an
    edge-attested pair among its shown facets.

    A separate file, not a table in vera.db: unrestricted the edges tripled
    the artifact (142MB -> 405MB), and even capped they double it. The
    sidecar is optional — the engine answers identically without it and
    speaks more with it — which is exactly what optional means.
    """
    t0 = time.time()
    out = Path(out)
    if out.exists():
        out.unlink()
    merged: Dict[str, Dict[str, int]] = {}
    stores_list = _stores(root)
    for lang, _d, _n, st in stores_list:
        if lang != "ja":
            continue
        for c, cr in st.crosses.items():
            dst = merged.setdefault(c, {})
            for f, n in cr.items():
                dst[f] = dst.get(f, 0) + n
    keep = {c: set(sorted(cr, key=lambda f: (-cr[f], f))[:top])
            for c, cr in merged.items()}
    del merged

    con = sqlite3.connect(str(out))
    con.executescript(
        "PRAGMA journal_mode=OFF;"
        "CREATE TABLE IF NOT EXISTS edges (core TEXT, f1 TEXT, f2 TEXT,"
        " PRIMARY KEY (core, f1, f2)) WITHOUT ROWID;"
        "CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);")
    n = 0
    with con:
        for lang, _d, _n2, st in stores_list:
            if lang != "ja":
                continue
            for core, by_facet in (getattr(st, "provenance", None) or {}).items():
                groups: Dict[str, List[str]] = {}
                for f, rec in by_facet.items():
                    snip = (rec[2] if isinstance(rec, (list, tuple))
                            and len(rec) > 2 else None)
                    if snip:
                        groups.setdefault(snip, []).append(f)
                kp = keep.get(core, set())
                rows = []
                for fs in groups.values():
                    fs = sorted(set(fs) & kp)
                    if len(fs) > max_group:
                        continue
                    rows += [(core, fs[x], fs[y])
                             for x in range(len(fs))
                             for y in range(x + 1, len(fs))]
                con.executemany("INSERT OR IGNORE INTO edges VALUES (?,?,?)",
                                rows)
                n += len(rows)
        con.execute("INSERT OR REPLACE INTO meta VALUES ('format',"
                    "'vera-edges-1')")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('rule',"
                    "'same-sentence co-occurrence, top-%d facets')" % top)
    con.execute("VACUUM")
    con.close()
    return {"path": str(out), "mb": round(out.stat().st_size / 1048576, 1),
            "edges": n, "seconds": round(time.time() - t0, 1)}


def edge_pairs_of(path: Path, core: str,
                  facets: List[str]) -> List[Tuple[str, str]]:
    """Edges among these facets of this core, from the sidecar."""
    if not facets or not Path(path).exists():
        return []
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    marks = ",".join("?" * len(facets))
    rows = con.execute(
        "SELECT f1, f2 FROM edges WHERE core=? AND f1 IN (%s) AND f2 IN (%s)"
        % (marks, marks), [core] + facets + facets).fetchall()
    con.close()
    return [(a, b) for a, b in rows]


def edge_partners_of(path: Path, core: str, limit: int = 48) -> List[str]:
    """この核の辺の端点、決定論的な順で。生成の内容供給用。

    腕1本(先端+4面=5枠)しか読めない生成に、コーパスが実際に書いた
    共起相手を渡す — 窃盗罪の辺は (他人,財物)(使用,故意)(不法領得,意思)
    を持ち、facet の切れ端(不法領得つ)と違って端点は語として立っている。
    辺はコーパス由来なので「配置は情報を増やせない」に抵触しない。
    順序は (f1,f2) の主キー順そのまま = 決定論。"""
    if not Path(path).exists():
        return []
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT f1, f2 FROM edges WHERE core=? ORDER BY f1, f2 LIMIT ?",
        (core, limit)).fetchall()
    con.close()
    out: List[str] = []
    for a, b in rows:
        for w in (a, b):
            if w not in out:
                out.append(w)
    return out


#: A cross has six arms times four faces. `export_web` keeps this many facets
#: per core and no more, which is not a size compromise but the capacity the
#: geometry already imposes — a 25th facet has nowhere to sit.
CROSS_CAPACITY = 24


def export_web(root: Path, out: Path, *, cap: int = CROSS_CAPACITY) -> Dict[str, Any]:
    """The structure trimmed to what a browser can carry, cut where it is safe.

    Two cuts were measured against the full file on a 34-question bank:

        top 6,000 cores, 24 facets   16.2 MB   verdicts 85%   SUBJECT 65%
        every core, 24 facets        84.9 MB   verdicts 97%   SUBJECT 100%

    The first is the obvious cut and it is the wrong one. Dropping cores does
    not make the engine refuse more, it makes it seed onto whatever core
    survived: 窃盗罪とは came back about 殺人罪, and 「Wie geht es dir」 — which
    the full store correctly refuses — became a confident ANSWER. Trimming
    the index turns correct refusals into wrong answers, which is the exact
    opposite of what this system is for.

    Cutting FACETS instead never moves the subject. Every core the full file
    holds is still held, so a question about an unheld thing is still refused
    for the same reason; only the evidence behind an answer is shallower. The
    one bank difference is a refusal becoming a different refusal.

    Leaves are merged per language here — the browser cannot route by statute
    division anyway, and `load` merges them on the way in regardless.
    """
    out = Path(out)
    if out.exists():
        out.unlink()
    stores = load(root / "build" / "vera.db") if (root / "build" / "vera.db").exists() \
        else None
    if stores is None:
        raise SystemExit("build/vera.db first: python3 -m verantyx.export_sqlite")

    # One leaf per SELECTION RULE, not per language. The first version
    # wrote a single ja-merged leaf, which quietly erased the domain
    # column — and with it the witnesses: the browser build answered with
    # 独立合議 1/1 on subjects the full store attests 3/3, because the
    # partition the witnesses are built from no longer existed in the
    # file. The cap still applies to the MERGED cross (the shown faces
    # must match), and each kept facet is written back per domain with
    # its domain-local count, so the summing load reassembles the same
    # totals AND the same witnesses.
    from .vera import load as _pickle_load  # noqa: F401  (doc anchor)

    per_domain: Dict[str, Dict[str, Any]] = {}
    if (root / "build" / "federation.pkl").exists():
        doms = pickle.loads((root / "build" / "federation.pkl").read_bytes())
        for d in doms:
            agg: Dict[str, Dict[str, int]] = {}
            for st0 in doms[d].values():
                for c, cr in st0.crosses.items():
                    dst = agg.setdefault(c, {})
                    for f, n in cr.items():
                        dst[f] = dst.get(f, 0) + n
            per_domain[d] = agg

    con = sqlite3.connect(str(out))
    con.executescript(SCHEMA)
    n_f = 0
    with con:
        leaf_id = 0
        for lang, s in sorted(stores.items()):
            kept = {c: set(sorted(cross, key=lambda f: (-cross[f], f))[:cap])
                    for c, cross in s.crosses.items()}
            groups = (sorted(per_domain) if (lang == "ja" and per_domain)
                      else [f"{lang}-merged"])
            for d in groups:
                agg = per_domain.get(d, s.crosses)
                con.execute("INSERT INTO leaves VALUES (?,?,?,?,?)",
                            (leaf_id, lang, d if lang == "ja" else lang,
                             d, 0))
                rows = [(leaf_id, c, f, int(n))
                        for c, cross in agg.items()
                        for f, n in cross.items()
                        if f in kept.get(c, ())]
                con.executemany("INSERT INTO facets VALUES (?,?,?,?)", rows)
                n_f += len(rows)
                con.executemany(
                    "INSERT INTO cores VALUES (?,?,?)",
                    ((leaf_id, c, 0) for c in agg))
                leaf_id += 1
            # Labels and caps ride on the first leaf of the language —
            # load() unions labels per language and caps are global.
            first = leaf_id - len(groups)
            con.executemany("INSERT INTO labels VALUES (?,?)",
                            ((first, l) for l in sorted(s.source_labels)))
            con.executemany(
                "INSERT INTO caps VALUES (?,?,?,?)",
                ((first, w, int(v[0]), int(v[1]))
                 for w, v in (getattr(s, "cap_stats", {}) or {}).items()
                 if isinstance(v, (list, tuple)) and len(v) >= 2))
    con.executescript(INDEXES)
    with con:
        con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
            ("format", "vera-federation-1"),
            ("subset", f"every core; facets capped at {cap}, the cross capacity"),
            ("cores", str(sum(len(s.crosses) for s in stores.values()))),
            ("facets", str(n_f)),
        ])
    con.execute("VACUUM")
    con.close()
    import gzip as _gz
    return {"path": str(out), "mb": round(out.stat().st_size / 1048576, 1),
            "gzip_mb": round(len(_gz.compress(out.read_bytes(), 9)) / 1048576, 1),
            "facets": n_f, "cap": cap}


def load(path: Path) -> Dict[str, Any]:
    """Reconstruct one CrossStore per language. No code is executed.

    Mirrors `vera.load` exactly — the file published as "the model" must
    answer as the model whose numbers the card reports, and `--verify`
    checks that on every export. Both now SUM across leaves: a (core, facet)
    pair two leaves attest keeps the sum, because cross-leaf corroboration
    is the one evidential signal a flat corpus has, and the previous
    `dict.update` overwrote it away and made the merge depend on leaf
    order. `core_count` sums the same way, so `mass()` works on the
    Japanese sovereign too.
    """
    from .cross_store import CrossStore

    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    leaves = list(con.execute(
        "SELECT id, lang, merged FROM leaves ORDER BY id"))
    lang_of = {i: l for i, l, _m in leaves}
    stores: Dict[str, Any] = {l: CrossStore() for l in set(lang_of.values())}

    for leaf, label in con.execute("SELECT leaf, label FROM labels"):
        stores[lang_of[leaf]].source_labels.add(label)

    # Every core, including the ones holding no facets. Rebuilding `crosses`
    # from the facets table alone dropped 1,828 of the English sovereign's
    # 15,268 cores — and a facet-less core is not a nothing: it is the
    # difference between UNKNOWN_NOT_PRESENT (the term is held, nothing
    # supports an answer) and UNKNOWN_NO_EVIDENCE (no such term at all).
    for leaf, core, n in con.execute("SELECT leaf, core, count FROM cores"):
        st = stores[lang_of[leaf]]
        st.crosses.setdefault(core, {})
        st.core_count[core] = st.core_count.get(core, 0) + n
    for leaf, core, facet, n in con.execute(
            "SELECT leaf, core, facet, count FROM facets"):
        cr = stores[lang_of[leaf]].crosses.setdefault(core, {})
        cr[facet] = cr.get(facet, 0) + n
    for leaf, w, cap, low in con.execute(
            "SELECT leaf, word, cap, low FROM caps"):
        stores[lang_of[leaf]].cap_stats[w] = [cap, low]
    con.close()
    return stores


def witnesses(path: Path) -> Dict[str, Any]:
    """One merged store per selection rule (the `domain` column), summed.

    The same partition `vera.load` builds from the pickles, reconstructed
    from the published file — the leaves table kept the domain of every
    leaf precisely so that questions like this stay answerable after the
    pickles are gone.
    """
    from .cross_store import CrossStore

    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    dom_of = {i: d for i, l, d in con.execute(
        "SELECT id, lang, domain FROM leaves WHERE lang='ja'")}
    out: Dict[str, Any] = {}
    for leaf, label in con.execute("SELECT leaf, label FROM labels"):
        d = dom_of.get(leaf)
        if d is not None:
            out.setdefault(d, CrossStore()).source_labels.add(label)
    for leaf, core, facet, n in con.execute(
            "SELECT leaf, core, facet, count FROM facets"):
        d = dom_of.get(leaf)
        if d is None:
            continue
        cr = out.setdefault(d, CrossStore()).crosses.setdefault(core, {})
        cr[facet] = cr.get(facet, 0) + n
    for leaf, core, n in con.execute("SELECT leaf, core, count FROM cores"):
        d = dom_of.get(leaf)
        if d is None:
            continue
        st = out.setdefault(d, CrossStore())
        st.crosses.setdefault(core, {})
        st.core_count[core] = st.core_count.get(core, 0) + n
    con.close()
    return {d: s for d, s in out.items() if s.crosses}


def origin_of(path: Path, core: str, facets: List[str]) -> Dict[str, List[str]]:
    """Which leaves supplied these facets of this core. Provenance, on demand.

    The sense-pollution fix that survived measurement. Per-facet witness
    attestation was tried first and decided nothing (0 of 1,776 tied cores)
    — two selection rules almost never write the same (core, facet) pair.
    What the file DOES know is where each pair came from, and that is the
    fact a reader needs: 時効's leading facets trace to 法学／法の不遡及.txt,
    an article about non-retroactivity that cites the Korean special law —
    visibly not an article about 時効. Nothing is reordered or suppressed;
    the origin is shown and the reader does the discounting.
    """
    if not facets:
        return {}
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    out: Dict[str, List[str]] = {}
    q = ("SELECT l.domain, l.name FROM facets f JOIN leaves l ON l.id=f.leaf "
         "WHERE f.core=? AND f.facet=?")
    for f in facets:
        rows = con.execute(q, (core, f)).fetchall()
        out[f] = sorted({f"{d}／{n.split('／')[-1]}" if "／" not in n else n
                         for d, n in rows})[:3]
    con.close()
    return out


def vera(path: Path) -> Any:
    """A `Vera` built from the published file rather than from pickles."""
    from .vera import Vera
    from .writer import Writer

    path = Path(path)
    v = Vera()
    for lang, st in sorted(load(path).items()):
        v.add(lang, st)
    v.witnesses = witnesses(path)
    v.origin = lambda core, facets: origin_of(path, core, facets)
    epath = path.parent / "vera_edges.db"
    if epath.exists():
        v.edges = lambda core, facets: edge_pairs_of(epath, core, facets)
        v.edge_partners = lambda core: edge_partners_of(epath, core)
    gpath = path.parent / "vera_gaps.db"
    if gpath.exists():
        from .cross_store import CrossStore
        try:
            v.gaps = CrossStore.load(gpath)
        except Exception:
            pass
    w = path.parent / "writer.json"
    if w.exists():
        v.writer = Writer.load(w)
    return v


#: Deliberately spans the answering verdicts AND the refusing ones. A round
#: trip that keeps the answers and loses the refusals would look green on a
#: bank of questions the store can answer.
BANK = ("正当防衛とは", "殺人罪の刑は", "契約の成立要件は", "時効とは",
        "過失相殺とは", "超伝導とは", "今日の天気は", "こんにちは",
        "フロベニウス双対とは", "negligence", "consideration", "jurisdiction")


def _shape(v: Any) -> Dict[str, Any]:
    return {lang: {"cores": len(s.crosses),
                   "facets": sum(len(c) for c in s.crosses.values()),
                   "labels": len(getattr(s, "source_labels", ()) or ())}
            for lang, s in sorted(v.stores.items())}


def verify(root: Path, path: Path) -> Dict[str, Any]:
    """Does the published file hold what the built one holds, and answer the same?

    Both halves are needed. The bank alone passed 12/12 while the round trip
    was silently dropping every facet-less core, because a core with nothing
    on it cannot answer a question either way — the shape check is what
    catches a loss the answers cannot show.
    """
    from .vera import load as pickle_load

    a, b = pickle_load(root), vera(path)
    shape_a, shape_b = _shape(a), _shape(b)
    rows, same = [], 0
    for q in BANK:
        ra, rb = a.ask(q), b.ask(q)
        ok = (ra.get("verdict") == rb.get("verdict")
              and ra.get("core") == rb.get("core")
              and ra.get("text") == rb.get("text"))
        same += ok
        rows.append({"q": q, "same": ok, "pickle": ra.get("verdict"),
                     "sqlite": rb.get("verdict"),
                     "core": rb.get("core"), "text": rb.get("text")})
    ok = same == len(BANK) and shape_a == shape_b
    return {"verdict": "ANSWER" if ok else "DRIFTED",
            "identical": f"{same}/{len(BANK)}",
            "shape_matches": shape_a == shape_b,
            "shape": {"pickle": shape_a, "sqlite": shape_b},
            "rows": rows}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(corpus_root()))
    ap.add_argument("--out")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--edges", metavar="OUT",
                    help="write the same-sentence edge sidecar")
    ap.add_argument("--web", metavar="OUT",
                    help="also write the browser-sized structure")
    a = ap.parse_args(argv)
    root = Path(a.root)
    out = Path(a.out) if a.out else root / "build" / "vera.db"

    rep: Dict[str, Any] = {"verdict": "ANSWER"}
    if not a.verify or not out.exists():
        rep["export"] = export(root, out)
    if a.edges:
        rep["edges"] = export_edges(root, Path(a.edges))
    if a.web:
        rep["web"] = export_web(root, Path(a.web))
    if a.verify:
        t = time.time()
        rep["load_seconds"] = None
        v = verify(root, out)
        rep["verify"] = v
        rep["verdict"] = v["verdict"]
        rep["load_seconds"] = round(time.time() - t, 1)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep["verdict"] == "ANSWER" else 1


if __name__ == "__main__":
    sys.exit(main())
