# Rights-gated corpus candidate catalog

`candidate-catalog.json` is metadata only. It contains no source repository,
garment image, pattern, mesh, or other training payload. Registration in the
content-addressed index means only that the candidate record passed the current
machine-readable rights and lineage gate; it is not legal advice or approval of
an unlisted asset.

The FreeSewing and GarmentCode entries describe MIT-licensed **source code**.
Their manifests intentionally contain no data modality. The MIT license on code
must not be copied onto project samples, generated datasets, website images, or
third-party assets without separate evidence.

The CC0 entry is an intake template for assets that individually identify CC0
1.0 as their controlling dedication. Its payload is absent, and every future
asset still requires its own source URL, provenance, bytes hash, and rights
record before payload ingestion.

Dry-run and commit examples:

```sh
python3 -m photoloset.corpus_ingest docs/corpora/candidate-catalog.json \
  --index /tmp/photoloset-corpus-index
python3 -m photoloset.corpus_ingest docs/corpora/candidate-catalog.json \
  --index /tmp/photoloset-corpus-index --commit
```

Committed objects are stored as `objects/<sha256>.json`; `index.json` binds a
stable candidate id to that digest. No network request is performed.

`content-index/` is the committed result for the bundled catalog. It contains
three immutable metadata objects and zero payloads. In particular, it does not
vendor FreeSewing, GarmentCode, GarmentCodeData, images, meshes, or patterns.

The Python API is `capabilities() -> dict`, `load_catalog(path) -> dict`, and
`ingest(catalog, index_path, *, commit=False) -> dict`. Pass the successful
result of `load_catalog` directly to `ingest`.
