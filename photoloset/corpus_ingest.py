# -*- coding: utf-8 -*-
"""Rights-gated, content-addressed intake for optional corpus catalog records.

This module never downloads assets.  A committed object records that a source
is a reviewed *candidate*, not that its data is bundled or fit for training.
Code licences are deliberately prevented from granting rights to data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Mapping, Sequence

from . import corpus_manifest


ANSWER = "ANSWER"
BAD_RECORD = "UNKNOWN_BAD_CORPUS_CATALOG_RECORD"
HASH_MISMATCH = "UNKNOWN_CORPUS_RECORD_HASH_MISMATCH"
SCOPE_MISMATCH = "UNKNOWN_CORPUS_LICENSE_SCOPE"
IDENTITY_CONFLICT = "UNKNOWN_CORPUS_IDENTITY_CONFLICT"
CATALOG_SCHEMA = "garment.corpus-candidate.v1"
INDEX_SCHEMA = "garment.corpus-content-index.v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def candidate_digest(record: Mapping[str, Any]) -> str:
    """Hash a record without its self-declaring ``record_sha256`` field."""
    body = dict(record)
    body.pop("record_sha256", None)
    return hashlib.sha256(_canonical(body)).hexdigest()


def _refusal(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why, **extra}


def validate_candidate(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply format, hash, rights, lineage, and licence-scope gates."""
    if not isinstance(record, Mapping):
        return _refusal(BAD_RECORD, "candidate record must be an object")
    required = ("schema", "candidate_id", "manifest", "source", "payload",
                "record_sha256")
    missing = [key for key in required if key not in record]
    if missing:
        return _refusal(BAD_RECORD, "candidate fields are missing",
                        missing=missing)
    if record.get("schema") != CATALOG_SCHEMA:
        return _refusal(BAD_RECORD, f"schema must be {CATALOG_SCHEMA}")
    candidate_id = record.get("candidate_id")
    if (not isinstance(candidate_id, str) or not candidate_id
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_." for c in candidate_id)):
        return _refusal(BAD_RECORD, "candidate_id must be a safe lowercase id")

    expected = candidate_digest(record)
    if record.get("record_sha256") != expected:
        return _refusal(HASH_MISMATCH,
                        "record_sha256 does not match the canonical catalog record",
                        expected=expected, actual=record.get("record_sha256"))

    source = record.get("source")
    payload = record.get("payload")
    if not isinstance(source, Mapping) or not isinstance(payload, Mapping):
        return _refusal(BAD_RECORD, "source and payload must be objects")
    if not isinstance(source.get("primary_license_url"), str):
        return _refusal(BAD_RECORD, "a primary licence URL is required")
    if payload.get("bundled") is not False:
        return _refusal(BAD_RECORD,
                        "this intake accepts metadata-only candidates; payload.bundled must be false")
    if payload.get("content_sha256") is not None:
        return _refusal(BAD_RECORD,
                        "an absent payload cannot claim a content hash")
    if not payload.get("absence_note"):
        return _refusal(BAD_RECORD,
                        "an absent payload needs an explicit absence_note")

    manifest = record.get("manifest")
    gated = corpus_manifest.validate(manifest, require_commercial=True)
    if gated.get("verdict") != ANSWER:
        return {**gated, "candidate_id": candidate_id}
    licence = manifest["license"]
    if licence.get("url") != source.get("primary_license_url"):
        return _refusal(SCOPE_MISMATCH,
                        "manifest licence must cite the same primary text as the source",
                        candidate_id=candidate_id)

    source_kind = source.get("kind")
    licence_scope = source.get("license_scope")
    modalities = manifest.get("modalities", [])
    if source_kind == "code_repository":
        if licence_scope != "source_code_only" or modalities:
            return _refusal(
                SCOPE_MISMATCH,
                "a code licence cannot be transferred to corpus data modalities",
                candidate_id=candidate_id)
    elif source_kind == "asset_catalog":
        if licence_scope != "candidate_assets_only_per_asset_verification_required":
            return _refusal(
                SCOPE_MISMATCH,
                "asset catalogs require per-asset licence verification before payload intake",
                candidate_id=candidate_id)
    else:
        return _refusal(BAD_RECORD, "unsupported source.kind",
                        candidate_id=candidate_id)

    normalised = json.loads(_canonical(record).decode("utf-8"))
    return {"verdict": ANSWER, "candidate_id": candidate_id,
            "digest": expected, "record": normalised,
            "payload_bundled": False, "manifest_gate": gated}


def capabilities() -> Dict[str, Any]:
    """Describe the deliberately narrow intake boundary."""
    return {
        "verdict": ANSWER,
        "catalog_schema": CATALOG_SCHEMA,
        "index_schema": INDEX_SCHEMA,
        "network_fetch": False,
        "payload_ingest": False,
        "metadata_only": True,
        "commercial_rights_gate": "fail_closed",
        "code_license_applies_to_data": False,
        "modes": ["dry-run", "commit"],
        "digest": "sha256-canonical-json",
    }


def load_catalog(path: os.PathLike[str] | str) -> Dict[str, Any]:
    """Load one local JSON catalog without validating or fetching its sources."""
    catalog_path = Path(path)
    with catalog_path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    records = value if isinstance(value, list) else [value]
    if any(not isinstance(item, Mapping) for item in records):
        return _refusal(BAD_RECORD, "catalog entries must be objects")
    return {"verdict": ANSWER, "records": records,
            "source_path": str(catalog_path), "network_used": False}


def _read_index(root: Path) -> Dict[str, Any]:
    path = root / "index.json"
    if not path.exists():
        return {"schema": INDEX_SCHEMA, "entries": {}}
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if (not isinstance(value, dict) or value.get("schema") != INDEX_SCHEMA
            or not isinstance(value.get("entries"), dict)):
        raise ValueError("invalid content-addressed index")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".corpus-", suffix=".tmp",
                                     dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ingest(catalog: Mapping[str, Any], index_path: os.PathLike[str] | str,
           *, commit: bool = False) -> Dict[str, Any]:
    """Validate candidates and optionally commit immutable catalog objects.

    Invalid records never reach the plan or index.  A duplicate means the exact
    digest was already seen; reusing an id with different content is refused.
    """
    if (not isinstance(catalog, Mapping) or catalog.get("verdict") != ANSWER
            or not isinstance(catalog.get("records"), Sequence)
            or isinstance(catalog.get("records"), (str, bytes))):
        return _refusal(BAD_RECORD,
                        "catalog must be the successful result of load_catalog")
    records = catalog["records"]
    root = Path(index_path)
    index = _read_index(root)
    entries = dict(index["entries"])
    seen_digests = set(entries.values())
    admitted, refused, duplicates = [], [], []

    for raw in records:
        checked = validate_candidate(raw)
        if checked.get("verdict") != ANSWER:
            refused.append(checked)
            continue
        candidate_id = checked["candidate_id"]
        digest = checked["digest"]
        previous = entries.get(candidate_id)
        if previous is not None and previous != digest:
            refused.append(_refusal(
                IDENTITY_CONFLICT,
                "candidate_id is already bound to different content",
                candidate_id=candidate_id, existing=previous, proposed=digest))
            continue
        if digest in seen_digests:
            duplicates.append({"candidate_id": candidate_id, "digest": digest})
            continue
        admitted.append(checked)
        entries[candidate_id] = digest
        seen_digests.add(digest)

    if commit and admitted:
        for item in admitted:
            _atomic_json(root / "objects" / f'{item["digest"]}.json',
                         item["record"])
        _atomic_json(root / "index.json",
                     {"schema": INDEX_SCHEMA, "entries": entries})

    return {
        "verdict": ANSWER,
        "mode": "commit" if commit else "dry-run",
        "admitted": [{"candidate_id": item["candidate_id"],
                      "digest": item["digest"]} for item in admitted],
        "duplicates": duplicates,
        "refused": refused,
        "writes": len(admitted) if commit else 0,
        "payloads_installed": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog")
    parser.add_argument("--index", required=True)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)
    result = ingest(load_catalog(args.catalog), args.index, commit=args.commit)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if not result["refused"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
