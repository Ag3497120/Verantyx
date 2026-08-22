"""A catalogue of a body of work — every entry traceable, the whole thing reproducible.

Point it at years of documents and it answers "what is in here": the topics,
what is said about each, which files said it, where the sources disagree, and
which of the six questions nobody answered. Not a summary — a summary is one
person's reading, and the reading is the part you cannot check.

Three properties, in the order a regulated buyer asks about them:

  Reproducible   The same corpus produces a byte-identical catalogue. The
                 manifest carries a hash of every input file, so a catalogue
                 can be tied to exactly the inputs that produced it and a
                 later run either matches or names what changed. Nothing here
                 samples, sorts by dict order, or calls a model.

  Traceable      Every claim carries the file it came from. `audit(topic)`
                 walks back from a line in the catalogue to the sentence in
                 the source document, which is the question an auditor
                 actually asks and the one a vector index cannot answer.

  Honest about coverage
                 `coverage` reports what fraction of sentences produced a
                 topic at all. A catalogue built from a corpus it mostly
                 failed to parse looks identical to one built from a corpus
                 it understood, unless the number is printed. It is printed.

What this is not: a ranking of importance. Topics are ordered by how often
they are discussed, which is a fact about the corpus, not a judgement about
the work.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .arm_schema import ARMS, ArmIndex
from .cross_store import CrossStore
from .document_ingest import Document, deep_report, ingest_documents
from .document_loaders import SUPPORTED, load_paths

#: Cores below this length are almost never topics — they are fragments left
#: by segmentation. Script-aware, for the same reason the sentence floor is.
_MIN_CORE_LATIN = 3
_MIN_CORE_CJK = 2
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")


@dataclass
class Entry:
    topic: str
    mass: int                                  # total mentions across the corpus
    documents: int = 0                         # how many distinct files mention it
    #: Majority language of the sentences that discuss this topic. From the
    #: per-sentence router, not guessed from the topic string — a two-kanji
    #: word cannot be told apart from Chinese by its own characters, but the
    #: sentences it came from already voted.
    lang: str = "en"
    facets: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    contested: List[Dict[str, Any]] = field(default_factory=list)
    missing_arms: List[str] = field(default_factory=list)


@dataclass
class Manifest:
    """What went in, precisely enough to reproduce or to dispute.

    `corpus_hash` is over the file contents, not their names or timestamps:
    a moved file produces the same catalogue, an edited one does not, and
    that is the distinction that matters when someone asks whether a
    conclusion still holds.
    """

    files: int
    chars: int
    sentences: int
    topics: int
    corpus_hash: str
    skipped: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Catalog:
    entries: List[Entry]
    manifest: Manifest
    coverage: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {"manifest": self.manifest.as_dict(),
                "coverage": self.coverage,
                "entries": [asdict(e) for e in self.entries]}


def _min_core_len(core: str) -> int:
    return _MIN_CORE_CJK if _CJK.search(core) else _MIN_CORE_LATIN


def _corpus_hash(docs: List[Document]) -> str:
    """Content hash, order-independent.

    Sorting the per-document digests before combining means the catalogue
    does not change when the filesystem returns paths in a different order —
    which it does, across machines, and which would otherwise make
    "reproducible" false for reasons that have nothing to do with the corpus.
    """
    digests = sorted(hashlib.sha256(d.text.encode("utf-8")).hexdigest()
                     for d in docs)
    return hashlib.sha256("".join(digests).encode()).hexdigest()[:16]


def build_catalog(paths: List[str], *, top: int = 200,
                  facets_per_topic: int = 10) -> Catalog:
    """Read the files, place the sentences, and report what is in there."""
    res = load_paths(paths)

    # Content-level dedupe. The corpus has whole files duplicated across
    # repository copies (the same 7.8 MB notes file exists twice), and a
    # duplicate is not a second document: it doubles every mention count and
    # inflates document-frequency, which is the ranking signal. Duplicates
    # are counted and named in the manifest rather than silently merged.
    docs: List[Document] = []
    seen_hash: Dict[str, str] = {}
    duplicates: List[Dict[str, Any]] = []
    for d in res["documents"]:
        h = hashlib.sha256(d.text.encode("utf-8")).hexdigest()
        if h in seen_hash:
            duplicates.append({"path": d.source, "duplicate_of": seen_hash[h]})
            continue
        seen_hash[h] = d.source
        docs.append(d)

    store, arms = CrossStore(), ArmIndex()
    # Per-document ingestion, so document frequency can be counted. Ranking by
    # raw mentions made the catalogue a portrait of the longest file: one
    # imported AI primer put モデル(14,646), 強化学習(14,520) and 機械学習(14,457)
    # at the top, each from a single source, while everything the author
    # actually worked on for years sat below them. How many separate documents
    # return to a topic is the question "what is this body of work about"
    # actually asks.
    doc_freq: Dict[str, int] = {}
    core_lang: Dict[str, Dict[str, int]] = {}
    rep = None
    for doc in docs:
        before = set(store.crosses)
        one = ingest_documents(store, [doc], arms)
        for core in set(store.crosses) - before | set(one.cores):
            doc_freq[core] = doc_freq.get(core, 0) + 1
        for core, langs in one.core_lang.items():
            slot = core_lang.setdefault(core, {})
            for lg, n in langs.items():
                slot[lg] = slot.get(lg, 0) + n
        if rep is None:
            rep = one
        else:
            rep.documents += one.documents
            rep.sentences += one.sentences
            rep.sentences_seen += one.sentences_seen
            rep.cores.extend(one.cores)
            rep.polar_claims += one.polar_claims
            rep.per_source.update(one.per_source)
    if rep is None:
        from .document_ingest import IngestReport
        rep = IngestReport()

    # Mass ordering, with the core name as the tiebreak. Without the
    # tiebreak two topics discussed equally often could swap places between
    # runs, and a catalogue that reorders itself is not reproducible even
    # when every fact in it is identical.
    ranked: List[Tuple[int, int, str]] = sorted(
        ((doc_freq.get(core, 0), store.core_count.get(core, 0), core)
         for core in store.crosses if len(core) >= _min_core_len(core)),
        key=lambda t: (-t[0], -t[1], t[2]))

    entries: List[Entry] = []
    for documents, mass, topic in ranked[:top]:
        detail = deep_report(store, topic, arms)
        langs = core_lang.get(topic, {})
        entries.append(Entry(
            topic=topic,
            mass=mass,
            documents=documents,
            lang=max(langs, key=langs.get) if langs else "en",
            facets=[s["claim"] for s in detail["settled"][:facets_per_topic]],
            sources=sorted({src for s in detail["settled"] for src in s["sources"]}),
            contested=[{"aspect": d["aspect"],
                        "sides": [{"claim": s["claim"], "sources": s["sources"]}
                                  for s in d["sides"]]}
                       for d in detail["disputed"]],
            missing_arms=[m["arm"] for m in (detail.get("missing") or [])],
        ))

    manifest = Manifest(
        files=res["loaded"],
        chars=sum(len(d.text) for d in docs),
        sentences=rep.sentences,
        topics=len(store.crosses),
        corpus_hash=_corpus_hash(docs),
        skipped=res["skipped"] + [
            {"path": d["path"], "verdict": "DUPLICATE",
             "reason": f"identical content to {d['duplicate_of']}"}
            for d in duplicates],
    )

    # Coverage is stated even when it is bad, because the failure mode this
    # guards is a catalogue that looks complete over a corpus that was mostly
    # not understood.
    placed = rep.sentences
    contested_topics = sum(1 for e in entries if e.contested)
    from .intake_quality import assess
    intake = assess(store, rep, duplicates=len(duplicates), files=res["loaded"])

    coverage = {
        "intake": intake,
        "sentences_placed": placed,
        "topics_total": len(store.crosses),
        "topics_catalogued": len(entries),
        "topics_contested": contested_topics,
        "polar_claims": rep.polar_claims,
        "per_source": rep.per_source,
    }
    return Catalog(entries=entries, manifest=manifest, coverage=coverage)


def audit(catalog: Catalog, store: CrossStore, topic: str) -> Dict[str, Any]:
    """Walk one topic back to the sentences that produced it.

    The question an auditor asks is never "what does the system think"; it is
    "show me where that came from". Provenance holds the originating snippet
    per facet, so this is a lookup rather than a search — and it returns the
    raw sentence, not a paraphrase of it.
    """
    entry = next((e for e in catalog.entries if e.topic == topic), None)
    if entry is None:
        return {"verdict": "UNKNOWN_NOT_CATALOGUED", "topic": topic,
                "reason": "no entry with that name in this catalogue"}
    prov = store.provenance.get(topic, {}) if store.track_provenance else {}
    trail = []
    for facet in entry.facets:
        slot = prov.get(facet)
        trail.append({"claim": facet,
                      "sentence": str(slot[2]) if slot and len(slot) > 2 else "",
                      "traced": bool(slot and len(slot) > 2)})
    untraced = [t["claim"] for t in trail if not t["traced"]]
    return {"verdict": "ANSWER" if not untraced else "UNKNOWN_PARTIAL_TRAIL",
            "topic": topic, "trail": trail, "untraced": untraced}


def render_catalog(catalog: Catalog, *, limit: int = 100) -> str:
    """The catalogue as Markdown."""
    m = catalog.manifest
    out: List[str] = [
        "# Catalogue",
        "",
        f"{m.files} documents · {m.chars:,} characters · {m.sentences:,} "
        f"sentences · {m.topics:,} topics",
        "",
        f"Corpus hash `{m.corpus_hash}`. Re-running over the same files "
        f"reproduces this document exactly; a different hash means the inputs "
        f"changed, not the method.",
        "",
    ]
    intake = catalog.coverage.get("intake") or {}
    if intake:
        v = intake.get("verdict", "")
        out += [f"Intake health: **{v}**"
                + ("" if v == "INTAKE_OK" else
                   " — this catalogue should be read with the findings below in mind"),
                ""]
        for f in intake.get("findings", []):
            out += [f"> {f['verdict']}: {f['meaning']} "
                    f"(measured {f.get('measured', '—')})", ""]

    if m.skipped:
        out += [f"{len(m.skipped)} file(s) were not read:", ""]
        for s in m.skipped[:10]:
            out.append(f"- `{s.get('path')}` — {s['verdict']}: {s.get('reason')}")
        out.append("")

    contested = [e for e in catalog.entries if e.contested]
    if contested:
        out += ["## Where the documents disagree", "",
                "Kept separate from the settled entries, because a reader who "
                "cannot tell agreed from contested has learned nothing they "
                "can act on.", ""]
        for e in contested:
            for c in e.contested:
                sides = " vs ".join(
                    f"**{s['claim']}** ({', '.join(s['sources']) or 'unattributed'})"
                    for s in c["sides"])
                out.append(f"- **{e.topic}** — {c['aspect']}: {sides}")
        out.append("")

    shown = catalog.entries[:limit]
    by_lang: Dict[str, List[Entry]] = {}
    for e in shown:
        by_lang.setdefault(e.lang, []).append(e)
    _LANG_TITLE = {"en": "English", "ja": "日本語", "zh": "中文", "latin": "Other"}
    out += ["## Topics", ""]
    if len(by_lang) > 1:
        counts = " · ".join(f"{_LANG_TITLE.get(lg, lg)} {len(es)}"
                            for lg, es in sorted(by_lang.items()))
        out += [f"By language: {counts}. Grouped below, because a reader "
                f"scanning for their own language should not wade through the "
                f"others — and because 如果 sitting beside 結論 as if they were "
                f"one language was exactly the confusion this fixes.", ""]
    for lg in sorted(by_lang):
        if len(by_lang) > 1:
            out += [f"### {_LANG_TITLE.get(lg, lg)}", ""]
        for e in by_lang[lg]:
            out.append(f"#### {e.topic}" if len(by_lang) > 1 else f"### {e.topic}")
            out.append("")
            out.append(f"Discussed {e.mass} times in {e.documents} documents.")
            if e.facets:
                out.append("What is said: " + ", ".join(f"`{f}`" for f in e.facets))
            if e.sources:
                srcs = e.sources[:6]
                more = f" (+{len(e.sources) - 6})" if len(e.sources) > 6 else ""
                out.append("Sources: " + ", ".join(srcs) + more)
            if e.missing_arms:
                out.append("Not recorded: " + ", ".join(e.missing_arms))
            out.append("")
    return "\n".join(out)


def reproducibility_check(paths: List[str]) -> Dict[str, Any]:
    """Build the catalogue twice and compare.

    Cheap, and it is the claim most worth testing rather than asserting: any
    dependence on dict ordering, filesystem order, or a stray timestamp shows
    up here as two different hashes over the same files. A buyer in a
    regulated industry will ask for exactly this, and "we believe it is
    deterministic" is not an answer.
    """
    a = build_catalog(paths)
    b = build_catalog(paths)
    ra, rb = render_catalog(a), render_catalog(b)
    same_text = ra == rb
    same_hash = a.manifest.corpus_hash == b.manifest.corpus_hash
    return {"verdict": "ANSWER" if (same_text and same_hash)
                       else "UNKNOWN_NONDETERMINISTIC",
            "identical_output": same_text,
            "identical_corpus_hash": same_hash,
            "corpus_hash": a.manifest.corpus_hash,
            "topics": len(a.entries)}


#: What a catalogue of a body of WORK is made of. Deliberately not every
#: format the loaders can read.
#:
#: Measured the hard way: collecting every supported suffix across three
#: repositories found 40,992 files and 381 MB, of which 38,341 were .json —
#: including a 208 MB file that was Vera's own store. A catalogue tool that
#: ingests its own database is not slow, it is wrong, and the size was the
#: only symptom anyone would have noticed.
PROSE_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".docx", ".pdf",
                  ".html", ".htm"}

#: Structured data is real input for some corpora — an exported register, a
#: CSV of incidents — but it has to be asked for, because in a source
#: repository almost every .json is configuration.
DATA_SUFFIXES = {".json", ".csv", ".tsv"}

#: Above this a file is a dump or an export, not something anyone wrote.
#: Set high on purpose: the first value excluded a 7.8 MB notes file and a
#: 2.6 MB working document, both of them genuinely this author's writing and
#: exactly what a catalogue of their work should contain. The 208 MB problem
#: that motivated a cap was a .json, which the suffix restriction already
#: removes, so the cap only needs to catch the rare enormous text dump.
#: Skipped files are named rather than dropped, so this choice stays visible.
MAX_DOCUMENT_BYTES = 12_000_000

#: Universal machine-artifact names only. An earlier version also listed
#: this project's own store files (vera_store, growth_signals, …) — overfit
#: residue: every one of them is a .json or .jcross and the prose-suffix
#: restriction already excludes them on ANY corpus. Rules that encode one
#: corpus's filenames are exactly what a general intake must not contain.
_MACHINE_NAMES = re.compile(
    r"(package-lock|yarn\.lock|pnpm-lock|Cargo\.lock|\.min\.)")


def collect(roots: List[str], *, exclude: Optional[List[str]] = None,
            include_data: bool = False,
            max_bytes: int = MAX_DOCUMENT_BYTES) -> Dict[str, Any]:
    """Documents under these roots, plus what was left out and why.

    Returns both lists rather than just the files. A collector that silently
    drops half its input produces a catalogue that is wrong in a way nobody
    can see; naming the omissions makes the coverage question answerable.

    Sorted, because an unsorted walk makes the catalogue depend on the
    filesystem rather than on the corpus.
    """
    skip = exclude or ["/node_modules/", "/.git/", "/.venv", "/site-packages/",
                       "/build/", "/dist/", "/DerivedData/", "/__pycache__/"]
    wanted = PROSE_SUFFIXES | (DATA_SUFFIXES if include_data else set())

    found: set = set()
    omitted: List[Dict[str, Any]] = []
    for root in roots:
        base = Path(root)
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            s = str(p)
            if any(x in s for x in skip):
                continue
            if p.suffix.lower() not in wanted:
                continue
            if _MACHINE_NAMES.search(p.name):
                omitted.append({"path": s, "reason": "machine-generated"})
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > max_bytes:
                omitted.append({"path": s, "reason": f"{size:,} bytes exceeds "
                                                     f"{max_bytes:,}"})
                continue
            found.add(s)
    return {"files": sorted(found), "omitted": omitted}
