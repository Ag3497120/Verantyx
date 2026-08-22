# -*- coding: utf-8 -*-
"""コーパスを新しい店へ入れる — 既存の取り込み経路をそのまま使う。

`verantyx.document_ingest.ingest_documents` / `Document` 以外の経路は
使わない(治具は測るものと同じ経路で作る)。前処理もしない — md の記法も
コードブロックもそのまま渡す。

保存先: experiments/guard/corpus/guard_store.json
**本店 vera_store.json には一切触れない。**
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from verantyx.cross_store import CrossStore  # noqa: E402
from verantyx.document_ingest import Document, ingest_documents  # noqa: E402

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "corpus_manifest.json"
STORE = HERE / "guard_store.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    docs = []
    for row in manifest["kept"]:
        p = Path(row["path"])
        docs.append(Document(source=str(p), text=p.read_text(encoding="utf-8")))
    print(f"documents={len(docs)}")

    store = CrossStore(source="guard-corpus:local-technical-docs")
    t0 = time.time()
    rep = ingest_documents(store, docs)
    ingest_s = round(time.time() - t0, 1)

    t1 = time.time()
    store.save(STORE)
    save_s = round(time.time() - t1, 1)

    out = {
        "store_path": str(STORE),
        "store_bytes": STORE.stat().st_size,
        "ingest_seconds": ingest_s,
        "save_seconds": save_s,
        "documents": rep.documents,
        "sentences": rep.sentences,
        "sentences_seen": rep.sentences_seen,
        "coverage_ratio": round(rep.sentences / max(rep.sentences_seen, 1), 4),
        "polar_claims": rep.polar_claims,
        "cores": len(store.crosses),
        "distinct_cores_reported": len(set(rep.cores)),
        "facet_slots": sum(len(v) for v in store.crosses.values()),
        "source_labels": len(store.source_labels),
        "corpus_files": manifest["files"],
        "corpus_chars": manifest["chars"],
        "corpus_by_lang": manifest["by_lang"],
    }
    (HERE / "results_ingest.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
