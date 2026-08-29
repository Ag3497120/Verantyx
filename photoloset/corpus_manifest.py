# -*- coding: utf-8 -*-
"""Fail-closed manifest for optional garment corpora.

The engine does not ship or download a dataset.  This module only describes
the evidence and rights a future corpus must carry before a caller can register
it.  "Free to download" is deliberately not treated as commercial permission.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Sequence


ANSWER = "ANSWER"
BAD_MANIFEST = "UNKNOWN_BAD_CORPUS_MANIFEST"
RIGHTS_UNKNOWN = "UNKNOWN_CORPUS_COMMERCIAL_RIGHTS"
LINEAGE_UNKNOWN = "UNKNOWN_CORPUS_LINEAGE"
UNSUPPORTED_MODALITY = "UNKNOWN_CORPUS_MODALITY"

SCHEMA = "garment.corpus-manifest.v1"
RIGHT_VALUES = {"allowed", "denied", "unknown"}
MODALITIES = {
    "garment_images", "calibrated_multiview", "segmentation_masks",
    "structure_graphs", "patterns_2d", "sewing_construction",
    "material_measurements", "drape_sequences", "meshes_3d",
}

# A sewing answer needs construction-bearing records.  Image embeddings are a
# retrieval hint and intentionally are not a modality in this schema.
CONSTRUCTION_MODALITIES = {"patterns_2d", "sewing_construction"}


def _digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _refusal(code: str, why: str, **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "why": why, **extra}


def validate(manifest: Mapping[str, Any], *, require_commercial: bool = True,
             purpose: str = "retrieval") -> Dict[str, Any]:
    """Validate rights, lineage and machine-readable modalities.

    Legal review is represented as an explicit unknown; this function is not a
    legal opinion and never upgrades ambiguous licence text.
    """
    if not isinstance(manifest, Mapping):
        return _refusal(BAD_MANIFEST, "manifest must be an object")
    required = ("schema", "name", "version", "license", "lineage",
                "modalities", "record_format")
    missing = [key for key in required if key not in manifest]
    if missing:
        return _refusal(BAD_MANIFEST, "required fields are missing",
                        missing=missing)
    if manifest.get("schema") != SCHEMA:
        return _refusal(BAD_MANIFEST, f"schema must be {SCHEMA}")

    licence = manifest.get("license")
    if not isinstance(licence, Mapping):
        return _refusal(BAD_MANIFEST, "license must be an object")
    rights = licence.get("rights")
    if not isinstance(rights, Mapping):
        return _refusal(BAD_MANIFEST, "license.rights must be an object")
    right_names = ("commercial_use", "derivatives", "redistribution")
    malformed = [name for name in right_names
                 if rights.get(name) not in RIGHT_VALUES]
    if malformed:
        return _refusal(BAD_MANIFEST,
                        "every right must be allowed, denied, or unknown",
                        malformed=malformed)
    if not isinstance(licence.get("url"), str) or not licence["url"].strip():
        return _refusal(BAD_MANIFEST,
                        "license.url must cite the controlling text")
    if require_commercial and rights["commercial_use"] != "allowed":
        return _refusal(
            RIGHTS_UNKNOWN,
            "commercial use is not explicitly allowed by the recorded licence",
            commercial_use=rights["commercial_use"],
            legal_review_required=rights["commercial_use"] == "unknown")

    lineage = manifest.get("lineage")
    if (not isinstance(lineage, Sequence) or isinstance(lineage, (str, bytes))
            or not lineage
            or any(not isinstance(item, Mapping) or not item.get("source")
                   for item in lineage)):
        return _refusal(LINEAGE_UNKNOWN,
                        "lineage needs at least one named source record")

    modalities = manifest.get("modalities")
    if (not isinstance(modalities, Sequence)
            or isinstance(modalities, (str, bytes))):
        return _refusal(BAD_MANIFEST, "modalities must be a list")
    unknown = sorted(set(modalities) - MODALITIES)
    if unknown:
        return _refusal(UNSUPPORTED_MODALITY,
                        "manifest contains an unsupported modality",
                        unsupported=unknown)
    if purpose == "sewing" and not (set(modalities) & CONSTRUCTION_MODALITIES):
        return _refusal(UNSUPPORTED_MODALITY,
                        "sewing retrieval requires patterns or construction steps",
                        required=sorted(CONSTRUCTION_MODALITIES))

    record_format = manifest.get("record_format")
    if not isinstance(record_format, Mapping):
        return _refusal(BAD_MANIFEST, "record_format must be an object")
    if record_format.get("units") not in ("SI", "explicit_per_field"):
        return _refusal(BAD_MANIFEST,
                        "record_format.units must be SI or explicit_per_field")
    if not record_format.get("schema_url"):
        return _refusal(BAD_MANIFEST,
                        "record_format.schema_url is required")

    normalised = json.loads(json.dumps(manifest, ensure_ascii=False,
                                       sort_keys=True))
    return {
        "verdict": ANSWER,
        "manifest": normalised,
        "digest": _digest(normalised),
        "commercial_use_recorded": rights["commercial_use"] == "allowed",
        "legal_opinion": False,
        "modalities": sorted(set(modalities)),
        "construction_bearing": bool(set(modalities)
                                     & CONSTRUCTION_MODALITIES),
    }


def expected_record_fields(modality: str) -> Dict[str, Any]:
    """Return the typed payload expected for one modality."""
    fields = {
        "garment_images": ["asset_id", "image_uri", "view", "provenance"],
        "calibrated_multiview": ["asset_id", "camera", "scale", "view", "image_uri"],
        "segmentation_masks": ["asset_id", "image_uri", "mask_uri", "label_map"],
        "structure_graphs": ["asset_id", "nodes", "joins", "assumptions"],
        "patterns_2d": ["asset_id", "units", "pieces", "seam_pairs", "notches", "grain"],
        "sewing_construction": ["asset_id", "steps", "preconditions", "stitches", "tools"],
        "material_measurements": ["asset_id", "test_method", "SI_properties", "uncertainty"],
        "drape_sequences": ["asset_id", "frames", "time_step_s", "boundary_conditions"],
        "meshes_3d": ["asset_id", "vertices", "faces", "units", "correspondence"],
    }
    if modality not in fields:
        return _refusal(UNSUPPORTED_MODALITY, "unknown modality",
                        modality=modality)
    return {"verdict": ANSWER, "modality": modality,
            "required_fields": fields[modality]}
