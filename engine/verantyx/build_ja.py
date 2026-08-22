"""Build the Japanese federation and writer once, to a durable path.

Everything measured at 626MB was rebuilt from scratch each session, in a
session temp directory, from a corpus that has now been cleaned away twice.
The manifests were fixed so the corpus can be refetched; this is so the
things built ON it survive too — a federation ingest and a writer build cost
minutes each and are pure functions of inputs that are already pinned.

    <root>/bulk                e-Gov statute XML     egov_bulk_2026
    <root>/wikipedia_domains   lead sections         wikipedia_ja_domains_2026
    <root>/wikipedia_cited     whole articles        wikipedia_ja_cited_2026
    <root>/build/federation.pkl
    <root>/build/writer.json

The default root is deliberately NOT a temp directory and NOT inside the
repository: the corpus is third-party government and encyclopedia text that
this project publishes manifests for rather than redistributing.

Rebuilding is skipped when the outputs are newer than the corpus, and forced
with --rebuild. The skip is on mtime rather than a checksum because the
corpus is a directory of a thousand files and `corpus_fetch --verify` is the
tool that already answers the checksum question properly.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import argparse
import json
import pickle
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_ROOT = corpus_root()


def _newest(folder: Path, pattern: str = "*") -> float:
    return max((p.stat().st_mtime for p in folder.rglob(pattern)
                if p.is_file()), default=0.0)


def prose_corpora(root: Path) -> List[Tuple[str, str]]:
    """(label, text) per SOURCE, never per file.

    One field per source is the rule the fusion measurement established:
    slicing one source into several fields makes its prose style arrive as
    if it were agreement between fields.
    """
    out: List[Tuple[str, str]] = []
    for label, folder in (("百科", "wikipedia_domains"),
                          ("引用", "wikipedia_cited"),
                          ("法学", "wikipedia_doctrine"),
                          ("多分野", "wikipedia_fields"),
                          ("指名", "wikipedia_named")):
        d = root / folder
        if not d.is_dir():
            continue
        text = "".join(p.read_text(encoding="utf-8", errors="ignore")
                       for p in sorted(d.rglob("*.txt")))
        if text:
            out.append((label, text))
    return out


def build_federation(root: Path) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """One store per LEAF: a statute's own division, or an article.

    The statute's divisions come from the legislature, not from clustering —
    刑法 is two 編 over 55 章 — so routing through them tells a reader why
    the question went where it went. Old-format statutes carry no division
    markup at all and fall back to one leaf for the whole law rather than
    being dropped; that is 11 files in 40 on this corpus, so dropping them
    silently would lose a quarter of it.

    Everything goes through `ingest_documents`, the same write path any
    other source uses. A second write path is how two readers of one corpus
    begin to disagree about what it said.
    """
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents
    from .egov import article_sentences, divisions, law_title

    doms: Dict[str, Dict[str, Any]] = {"法令": {}, "百科": {}}
    stats = {"laws": 0, "laws_without_divisions": 0, "unreadable": 0}

    for p in sorted((root / "bulk").glob("*.xml")):
        try:
            name = law_title(p)
            divs = divisions(p, law=name)
        except Exception:
            stats["unreadable"] += 1
            continue
        stats["laws"] += 1
        if not divs:
            stats["laws_without_divisions"] += 1
            try:
                sents = article_sentences(p, law=name)
            except Exception:
                sents = []
            if not sents:
                continue
            st = CrossStore()
            st.source_labels.add(name)
            ingest_documents(st, [Document(source=name, text="".join(sents))])
            if st.crosses:
                doms["法令"][name] = st
            continue
        for d in divs:
            arts = d.get("articles") or []
            if not arts:
                continue
            label = "／".join(x for x in (name, d.get("marker") or "",
                                          d.get("division") or "") if x)
            text = "".join(
                f"{core}は、{'、'.join(facets)}である。"
                for core, _mid, facets in arts if facets)
            if not text:
                continue
            st = CrossStore()
            st.source_labels.add(label)
            ingest_documents(st, [Document(source=label, text=text)])
            if st.crosses:
                doms["法令"][label] = st

    # A separate domain per SELECTION RULE, not per topic. 引用 is "articles
    # that cite statutes" and 法学 is "articles in these Wikipedia
    # categories"; they overlap in subject and were chosen by different
    # rules, and the fusion measurement is only readable when one field is
    # one source — slicing a source across fields makes its prose style
    # arrive as if it were agreement between them.
    # 多分野 is its own domain for the same reason 法学 is: it was selected
    # by a different rule (16 named categories against "cites a statute"),
    # and one field must be one source or the fusion measurement stops being
    # readable. Aozora dialogue is deliberately absent — fiction asserts
    # nothing about the world and is read for FORMS only, in `writer`.
    # English is absent too: mixing languages in one store was measured to
    # answer superconductivity with contract.
    # 指名 is its own domain for the same reason the others are: it was
    # selected by a different rule — the refusal log. Subjects the engine
    # named as missing during operation, fetched by name, with the rule in
    # the manifest. This is the trajectory's 「拒否のログがそのまま作業
    # 待ち行列」 executed: the corpus grows where the questions said it was
    # thin, not where a curator thought it should.
    for folder, domain in (("wikipedia_cited", "百科"),
                           ("wikipedia_doctrine", "法学"),
                           ("wikipedia_fields", "多分野"),
                           ("wikipedia_named", "指名")):
        for p in sorted((root / folder).rglob("*.txt")):
            label = f"{domain}／{p.name}"
            st = CrossStore()
            st.source_labels.add(label)
            try:
                ingest_documents(st, [Document(
                    source=label,
                    text=p.read_text(encoding="utf-8", errors="ignore"))])
            except Exception:
                stats["unreadable"] += 1
                continue
            if st.crosses:
                doms.setdefault(domain, {})[label] = st
    return doms, stats


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args(argv)

    root = Path(a.root)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    fed_path, writer_path = build / "federation.pkl", build / "writer.json"

    corpus_at = max(_newest(root / "bulk"), _newest(root / "wikipedia_cited"),
                    _newest(root / "wikipedia_domains"),
                    _newest(root / "wikipedia_doctrine"),
                    _newest(root / "wikipedia_fields"),
                    _newest(root / "wikipedia_named"))
    fresh = (fed_path.exists() and writer_path.exists()
             and fed_path.stat().st_mtime > corpus_at
             and writer_path.stat().st_mtime > corpus_at)
    if fresh and not a.rebuild:
        print(json.dumps({"verdict": "ANSWER", "rebuilt": False,
                          "federation": str(fed_path),
                          "writer": str(writer_path),
                          "note": "outputs are newer than the corpus; "
                                  "pass --rebuild to force"},
                         ensure_ascii=False, indent=2))
        return 0

    t0 = time.time()
    doms, stats = build_federation(root)
    fed_path.write_bytes(pickle.dumps(doms))
    t_fed = time.time() - t0

    from .writer import Writer

    t1 = time.time()
    stores = [s for d in doms.values() for s in d.values()]
    w = Writer.build(stores, prose_corpora(root),
                     statutes=sorted((root / "bulk").glob("*.xml")))
    saved = w.save(writer_path)
    print(json.dumps({
        "verdict": "ANSWER", "rebuilt": True,
        "federation": {"path": str(fed_path),
                       "stores": sum(len(v) for v in doms.values()),
                       "by_domain": {k: len(v) for k, v in doms.items()},
                       **stats,
                       "seconds": round(t_fed, 1)},
        "writer": {**saved, "seconds": round(time.time() - t1, 1),
                   "report": w.report()},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
