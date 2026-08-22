"""Build the English sovereign to a durable path — the builder that was missing.

`build_ja` has existed since the corpus was lost twice. `english.pkl` did
not: the English sovereign was built once, by hand, in a session that is
gone, and nothing in this repository could reproduce it. That is the same
failure the manifests were written to end, one level up — a published
artifact nobody can rebuild is a number nobody can check, including us.

    <root>/wikipedia_en        whole articles      wikipedia_en_2026
    <root>/build/english.pkl

One store, not a federation. The Japanese side splits into leaves because
statutes carry their own divisions and routing through them tells a reader
why a question went where it went; 764 encyclopedia articles have no such
structure to route through, and inventing one would be clustering dressed as
provenance.

Deliberately NOT merged with the Japanese federation. A single store holding
both cannot be asked in either — the English decomposer collapses
「Article 199 provides for homicide」 onto the core `article`, which then
competes with 刑法第百九十九条 in a census over items neither reader produced.
See `polyglot`.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import argparse
import json
import pickle
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_ROOT = corpus_root()


def build(root: Path) -> Any:
    from .cross_store import CrossStore
    from .document_ingest import Document, ingest_documents

    st = CrossStore()
    docs: List[Document] = []
    for p in sorted((root / "wikipedia_en").rglob("*.txt")):
        label = f"en／{p.name}"
        st.source_labels.add(label)
        docs.append(Document(
            source=label,
            text=p.read_text(encoding="utf-8", errors="ignore")))
    # Capitalisation statistics decide which runs are proper nouns, and they
    # are a property of the WHOLE corpus. Scanning per document made the
    # first article's names common and the last article's proper.
    st.scan_cap_stats(d.text for d in docs)
    ingest_documents(st, docs)
    return st


#: Facets that are pieces of a source label rather than of a sentence. Not a
#: filter — nothing here removes them — but the measurement that says whether
#: the attribution span is being skipped. See `lang.strip_attribution`.
LABEL_PIECES = frozenset({"txt", "en", "html", "htm", "pdf", "json", "xml"})


def leak(store: Any) -> Dict[str, Any]:
    """How much of the store is citation mistaken for content."""
    facets = sum(len(c) for c in store.crosses.values())
    hit = sum(1 for c in store.crosses.values() for f in c
              if f in LABEL_PIECES)
    cores = sum(1 for c in store.crosses.values()
                if any(f in LABEL_PIECES for f in c))
    return {"facets": facets, "label_pieces": hit,
            "share": round(100.0 * hit / facets, 2) if facets else 0.0,
            "cores_touched": cores,
            "cores_share": round(100.0 * cores / len(store.crosses), 1)
                           if store.crosses else 0.0}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args(argv)

    root = Path(a.root)
    out = root / "build" / "english.pkl"
    out.parent.mkdir(parents=True, exist_ok=True)
    src = max((p.stat().st_mtime for p in (root / "wikipedia_en").rglob("*.txt")),
              default=0.0)
    if out.exists() and out.stat().st_mtime > src and not a.rebuild:
        print(json.dumps({"verdict": "ANSWER", "rebuilt": False,
                          "path": str(out)}, ensure_ascii=False, indent=2))
        return 0

    t0 = time.time()
    st = build(root)
    out.write_bytes(pickle.dumps(st))
    print(json.dumps({
        "verdict": "ANSWER", "rebuilt": True, "path": str(out),
        "documents": len(st.source_labels), "cores": len(st.crosses),
        "leak": leak(st), "seconds": round(time.time() - t0, 1),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
