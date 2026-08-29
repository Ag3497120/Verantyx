# -*- coding: utf-8 -*-
"""Build an in-memory hand-off package for one garment candidate.

The module deliberately performs no file-system writes.  It binds the exact
candidate, structure and source-pattern digests into every exported artifact
and returns a fixed filename -> ``str``/``bytes`` map.  The DXF is encoded
using the encoding declared by the existing DXF payload (normally CP932).

This is a packaging boundary, not an authority boundary: proposed values,
engineering reviews and unfinished manufacturing gates remain visible and
can never become ``manufacturing_ready`` merely because files were bundled.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import html
import json
from pathlib import PurePath
from typing import Any, Dict, Mapping, Optional, Tuple, Union


ANSWER = "ANSWER"
INPUT_SCHEMA = "garment.manufacturing-preview-bundle.v1"
SEWING_SCHEMA = "garment.structure-sewing-plan.v1"
ENGINEERING_SCHEMA = "garment.engineering-review.v1"
SCHEMA = "garment.export-package.v1"

DEFAULT_FILENAMES = {
    "pattern_svg": "pattern.svg",
    "pattern_dxf": "pattern.dxf",
    "manifest": "manifest.json",
    "sewing_plan": "sewing-plan.json",
    "engineering_review": "engineering-review.json",
    "readme": "README",
}

FileValue = Union[str, bytes]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _content_bytes(value: FileValue) -> bytes:
    return value if isinstance(value, bytes) else value.encode("utf-8")


def _content_digest(value: FileValue) -> str:
    return hashlib.sha256(_content_bytes(value)).hexdigest()


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "schema": SCHEMA,
        "why": why,
        "files": {},
        "manufacturing_ready": False,
        **detail,
    }


def _text(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _safe_filename(value: Any) -> bool:
    """Accept one leaf filename and reject absolute/traversal spellings."""
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    if value in {".", ".."} or "/" in value or "\\" in value:
        return False
    path = PurePath(value)
    return not path.is_absolute() and len(path.parts) == 1 and path.name == value


def _filenames(overrides: Optional[Mapping[str, Any]]) -> Tuple[Optional[Dict[str, str]], Optional[Dict[str, Any]]]:
    names = dict(DEFAULT_FILENAMES)
    if overrides is not None:
        if not isinstance(overrides, Mapping):
            return None, _unknown(
                "UNKNOWN_EXPORT_FILENAME_MAP",
                "filenames must map known artifact keys to leaf filenames")
        unknown_keys = sorted(set(overrides) - set(DEFAULT_FILENAMES))
        if unknown_keys:
            return None, _unknown(
                "UNKNOWN_EXPORT_FILENAME_KEY",
                "filename overrides contain unknown artifact keys",
                keys=unknown_keys)
        names.update({key: value for key, value in overrides.items()})
    unsafe = sorted(key for key, value in names.items()
                    if not _safe_filename(value))
    if unsafe:
        return None, _unknown(
            "UNKNOWN_EXPORT_PATH_TRAVERSAL",
            "export names must be non-empty leaf filenames without path separators",
            keys=unsafe)
    if len(set(names.values())) != len(names):
        return None, _unknown(
            "UNKNOWN_EXPORT_FILENAME_COLLISION",
            "every package artifact needs a distinct filename")
    return names, None


def _candidate_digest(manufacturing: Mapping[str, Any],
                      engineering: Mapping[str, Any],
                      sewing: Mapping[str, Any], *,
                      candidate_id: str, structure_digest: str,
                      source_digest: str) -> Tuple[Optional[str], str, Optional[Dict[str, Any]]]:
    """Resolve an existing candidate digest or create a labelled transport binding."""
    values = []
    for value in (
            manufacturing.get("candidate_digest"),
            engineering.get("candidate_digest"),
            sewing.get("candidate_digest"),
            sewing.get("provenance", {}).get("approval_digest")
            if isinstance(sewing.get("provenance"), Mapping) else None,
            sewing.get("approval", {}).get("digest")
            if isinstance(sewing.get("approval"), Mapping) else None,
            sewing.get("approval", {}).get("candidate_digest")
            if isinstance(sewing.get("approval"), Mapping) else None):
        text = _text(value)
        if text and text not in values:
            values.append(text)
    if len(values) > 1:
        return None, "", _unknown(
            "UNKNOWN_CANDIDATE_DIGEST_MISMATCH",
            "the source artifacts name different candidate/approval digests",
            candidate_digests=values)
    if values:
        return values[0], "SOURCE_CANDIDATE_OR_APPROVAL_DIGEST", None
    binding = "sha256:" + _digest({
        "kind": "EXPORT_BINDING_NOT_APPROVAL",
        "candidate_id": candidate_id,
        "structure_digest": structure_digest,
        "source_digest": source_digest,
    })
    return binding, "EXPORT_BINDING_NOT_APPROVAL", None


def _matching_lineage(manufacturing: Mapping[str, Any],
                      engineering: Mapping[str, Any],
                      sewing: Mapping[str, Any]) -> Tuple[Optional[Dict[str, str]], Optional[Dict[str, Any]]]:
    candidate_id = _text(manufacturing.get("candidate_id"))
    structure_digest = _text(manufacturing.get("structure_digest"))
    source_digest = _text(manufacturing.get("source_digest"))
    if not candidate_id or not structure_digest or not source_digest:
        return None, _unknown(
            "UNKNOWN_EXPORT_LINEAGE_REQUIRED",
            "manufacturing bundle needs candidate_id, structure_digest and source_digest")

    comparisons = {
        "candidate_id": [engineering.get("candidate_id"), sewing.get("candidate_id")],
        "structure_digest": [engineering.get("structure_digest"),
                             sewing.get("structure_digest")],
        "source_digest": [engineering.get("pattern_digest"),
                          sewing.get("source_pattern_digest")],
    }
    expected = {
        "candidate_id": candidate_id,
        "structure_digest": structure_digest,
        "source_digest": source_digest,
    }
    mismatches = []
    for field, values in comparisons.items():
        for value in values:
            present = _text(value)
            if present is not None and present != expected[field]:
                mismatches.append({"field": field, "expected": expected[field],
                                   "actual": present})
    if mismatches:
        return None, _unknown(
            "UNKNOWN_EXPORT_LINEAGE_MISMATCH",
            "engineering review, sewing plan and manufacturing bundle do not describe the same candidate",
            mismatches=mismatches)

    candidate_digest, digest_kind, error = _candidate_digest(
        manufacturing, engineering, sewing, candidate_id=candidate_id,
        structure_digest=structure_digest, source_digest=source_digest)
    if error:
        return None, error
    assert candidate_digest is not None
    return {
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "candidate_digest_kind": digest_kind,
        "structure_digest": structure_digest,
        "source_digest": source_digest,
        "manufacturing_bundle_digest": _text(manufacturing.get("digest"))
        or "sha256:" + _digest(manufacturing),
        "sewing_plan_digest": _text(sewing.get("digest"))
        or "sha256:" + _digest(sewing),
        "engineering_review_digest": _text(engineering.get("digest"))
        or "sha256:" + _digest(engineering),
    }, None


def _walk_has_proposed(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_walk_has_proposed(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_walk_has_proposed(item) for item in value)
    return isinstance(value, str) and value.strip().upper() in {"PROPOSED", "INFERRED"}


def _inner_cuts(manufacturing: Mapping[str, Any]) -> Tuple[Optional[list[Dict[str, Any]]], Optional[str], Optional[Dict[str, Any]]]:
    raw = manufacturing.get("inner_cut_manifest", [])
    if not isinstance(raw, list):
        return None, None, _unknown(
            "UNKNOWN_EXPORT_INNER_CUT_MANIFEST",
            "manufacturing inner_cut_manifest must be a list")
    records: list[Dict[str, Any]] = []
    identities = set()
    for value in raw:
        if not isinstance(value, Mapping):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_MANIFEST",
                "every inner cut manifest row must be an object")
        row = copy.deepcopy(dict(value))
        identity = (row.get("piece_id"), row.get("operation_id"),
                    row.get("contour_id"))
        if (not all(isinstance(item, str) and item for item in identity)
                or identity in identities or row.get("kind") != "CUTOUT"):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_BINDING",
                "inner cut piece/operation/contour bindings must be unique and typed")
        identities.add(identity)
        for field in ("points", "svg_points", "dxf_points",
                      "contour_edge_lineage"):
            if not isinstance(row.get(field), list) or not row[field]:
                return None, None, _unknown(
                    "UNKNOWN_EXPORT_INNER_CUT_BINDING",
                    f"inner cut {identity} lacks {field}")
        if (not isinstance(row.get("approval_binding"), Mapping)
                or row.get("state") not in ("PROPOSED", "APPROVED")
                or row.get("svg_layer") != "INNER_CUT"
                or row.get("dxf_layer") != "INNER_CUT"):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_BINDING",
                f"inner cut {identity} loses state, approval, or layer binding")
        front_digest = row.get("source_front_boundary_digest")
        if front_digest is not None and (
                not isinstance(front_digest, str) or not front_digest.strip()
                or row.get("source_front_boundary_digest_state")
                != "PROPOSED_LINEAGE_ONLY"
                or row.get("source_front_boundary_semantics_observed") is not False):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_FRONT_BOUNDARY_LINEAGE",
                f"inner cut {identity} promotes front-boundary lineage beyond PROPOSED")
        expected = row.pop("digest", None)
        if expected != _digest(row):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_DIGEST",
                f"inner cut {identity} digest does not match its geometry and lineage")
        row["digest"] = expected
        records.append(row)
    digest = _digest(records)
    if manufacturing.get("inner_cut_digest", _digest([])) != digest:
        return None, None, _unknown(
            "UNKNOWN_EXPORT_INNER_CUT_DIGEST",
            "manufacturing inner_cut_digest does not match its manifest")
    svg = manufacturing.get("svg")
    dxf = manufacturing.get("dxf_export")
    if records:
        if (not isinstance(svg, str)
                or any(f'data-contour-digest="{row["digest"]}"' not in svg
                       for row in records)):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_SVG",
                "SVG does not carry every inner cut digest")
        if (not isinstance(dxf, Mapping)
                or dxf.get("inner_cut_digest") != digest
                or dxf.get("inner_cut_contours") != len(records)
                or dxf.get("layers", {}).get("inner_cut") != "INNER_CUT"):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_DXF",
                "DXF payload does not carry the same inner cut manifest")
    return records, digest, None


def _gates(manufacturing: Mapping[str, Any],
           engineering: Mapping[str, Any],
           sewing: Mapping[str, Any]) -> list[str]:
    rows = []
    for gate in manufacturing.get("remaining_gates", []):
        if isinstance(gate, str) and gate.strip():
            rows.append("manufacturing: " + gate.strip())
    for review in sewing.get("reviews", []):
        if not isinstance(review, Mapping):
            continue
        verdict = str(review.get("verdict", "REVIEW")).strip()
        scope = str(review.get("scope", "construction")).strip()
        why = str(review.get("why", "unresolved construction choice")).strip()
        rows.append(f"sewing: {verdict} [{scope}] - {why}")
    for gate in engineering.get("gates", []):
        if not isinstance(gate, Mapping) or gate.get("verdict") == "PASS":
            continue
        name = str(gate.get("gate", "engineering")).strip()
        verdict = str(gate.get("verdict", "REVIEW")).strip()
        why = str(gate.get("why", "unresolved engineering gate")).strip()
        rows.append(f"engineering: {name}: {verdict} - {why}")
    for name in engineering.get("actionable_gates", []):
        if isinstance(name, str) and name.strip():
            rows.append("engineering actionable: " + name.strip())
    return list(dict.fromkeys(rows))


def _json_artifact(document: Mapping[str, Any], lineage: Mapping[str, str],
                   *, manufacturing_ready: bool,
                   remaining_gates: list[str]) -> str:
    value = copy.deepcopy(dict(document))
    value["export_lineage"] = copy.deepcopy(dict(lineage))
    value["export_manufacturing_ready"] = manufacturing_ready
    value["export_remaining_gates"] = list(remaining_gates)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                      allow_nan=False) + "\n"


def _svg_artifact(svg: str, lineage: Mapping[str, str], *,
                  manufacturing_ready: bool,
                  remaining_gates: list[str],
                  inner_cut_digest: str,
                  inner_cut_count: int) -> Optional[str]:
    if not isinstance(svg, str) or "<svg" not in svg:
        return None
    opening = svg.find(">", svg.find("<svg"))
    if opening < 0:
        return None
    metadata = {
        "schema": SCHEMA,
        "lineage": dict(lineage),
        "manufacturing_ready": manufacturing_ready,
        "remaining_gates": list(remaining_gates),
        "inner_cut_digest": inner_cut_digest,
        "inner_cut_count": inner_cut_count,
    }
    node = ("\n<metadata id=\"photoloset-export-lineage\">"
            + html.escape(json.dumps(metadata, sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":")),
                          quote=False)
            + "</metadata>")
    return svg[:opening + 1] + node + svg[opening + 1:]


def _dxf_artifact(payload: Mapping[str, Any], lineage: Mapping[str, str], *,
                  manufacturing_ready: bool,
                  remaining_gates: list[str],
                  inner_cut_digest: str,
                  inner_cut_count: int) -> Tuple[Optional[bytes], Optional[Dict[str, Any]]]:
    if payload.get("verdict") != ANSWER or payload.get("typed_refusal") is True:
        return None, _unknown(
            "UNKNOWN_DXF_EXPORT_NOT_AVAILABLE",
            "manufacturing bundle contains a typed DXF refusal")
    text = payload.get("text")
    encoding = payload.get("encoding")
    if not isinstance(text, str) or not text or not isinstance(encoding, str) or not encoding:
        return None, _unknown(
            "UNKNOWN_DXF_PAYLOAD",
            "DXF export needs non-empty text and its declared encoding")
    candidate_b64 = base64.urlsafe_b64encode(
        lineage["candidate_id"].encode("utf-8")).decode("ascii").rstrip("=")
    comments = (
        "999\nphotoloset export package; metadata only; geometry unchanged\n"
        f"999\ncandidate_id_utf8_b64={candidate_b64}\n"
        f"999\ncandidate_digest={lineage['candidate_digest']}\n"
        f"999\nstructure_digest={lineage['structure_digest']}\n"
        f"999\nsource_digest={lineage['source_digest']}\n"
        f"999\nmanufacturing_ready={str(manufacturing_ready).lower()}\n"
        f"999\nremaining_gates_digest=sha256:{_digest(remaining_gates)}\n")
    comments += (f"999\ninner_cut_digest={inner_cut_digest}\n"
                 f"999\ninner_cut_count={inner_cut_count}\n")
    try:
        return (comments + text).encode(encoding), None
    except (LookupError, UnicodeEncodeError) as exc:
        return None, _unknown(
            "UNKNOWN_DXF_ENCODING",
            "DXF text cannot be encoded using its declared encoding",
            encoding=encoding, detail=str(exc))


def _readme(lineage: Mapping[str, str], *, candidate_state: str,
            manufacturing_ready: bool, contains_proposed: bool,
            remaining_gates: list[str], inner_cut_count: int) -> str:
    status = ("MANUFACTURING_READY asserted by every supplied source"
              if manufacturing_ready else
              "PREVIEW / REVIEW REQUIRED - NOT RELEASED FOR MANUFACTURING")
    proposed = ("YES - proposed or inferred content remains"
                if contains_proposed else "No PROPOSED/INFERRED state was detected")
    gates = ("\n".join(f"- {gate}" for gate in remaining_gates)
             if remaining_gates else "- No unresolved gate was listed by the supplied sources.")
    return f"""# Garment candidate hand-off

Status: {status}
Candidate state: {candidate_state}
Contains proposed/inferred content: {proposed}

## Exact lineage

- candidate_id: {lineage['candidate_id']}
- candidate_digest: {lineage['candidate_digest']}
- candidate_digest_kind: {lineage['candidate_digest_kind']}
- structure_digest: {lineage['structure_digest']}
- source_digest: {lineage['source_digest']}
- manufacturing_bundle_digest: {lineage['manufacturing_bundle_digest']}
- sewing_plan_digest: {lineage['sewing_plan_digest']}
- engineering_review_digest: {lineage['engineering_review_digest']}

## Files

- pattern.svg: inspectable cut/sew-line preview with embedded lineage metadata
- pattern.dxf: DXF R12 bytes in the source-declared encoding; no DXF-AAMA claim
- sewing-plan.json: deterministic topology order plus unresolved construction choices
- engineering-review.json: engineering gates and their current authority
- manifest.json: package lineage, hashes, readiness and unresolved gates
- nested inner cuts: {inner_cut_count}; exported separately as INNER_CUT, never merged with outer CUT_LINE

## Remaining gates

{gates}

This package does not convert a proposed back, material, seam method, strength,
comfort result, or industrial validation into an observed fact.  A true flag
only reports unanimous source flags; it is not an industrial, safety, medical,
fit, strength, or sewing certification.
"""


def build(manufacturing_bundle: Mapping[str, Any],
          engineering_review: Mapping[str, Any],
          sewing_plan: Mapping[str, Any], *,
          filenames: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return a deterministic in-memory export package without writing files."""
    if (not isinstance(manufacturing_bundle, Mapping)
            or manufacturing_bundle.get("schema") != INPUT_SCHEMA
            or manufacturing_bundle.get("verdict") != ANSWER):
        return _unknown(
            "UNKNOWN_MANUFACTURING_BUNDLE_REQUIRED",
            f"expected an ANSWER with schema {INPUT_SCHEMA}")
    if (not isinstance(engineering_review, Mapping)
            or engineering_review.get("schema") != ENGINEERING_SCHEMA):
        return _unknown(
            "UNKNOWN_ENGINEERING_REVIEW_REQUIRED",
            f"expected schema {ENGINEERING_SCHEMA}")
    if (not isinstance(sewing_plan, Mapping)
            or sewing_plan.get("schema") != SEWING_SCHEMA):
        return _unknown(
            "UNKNOWN_SEWING_PLAN_REQUIRED",
            f"expected schema {SEWING_SCHEMA}")

    names, error = _filenames(filenames)
    if error:
        return error
    assert names is not None
    lineage, error = _matching_lineage(
        manufacturing_bundle, engineering_review, sewing_plan)
    if error:
        return error
    assert lineage is not None

    inner_cuts, inner_cut_digest, error = _inner_cuts(manufacturing_bundle)
    if error:
        return error
    assert inner_cuts is not None and inner_cut_digest is not None

    dxf_export = manufacturing_bundle.get("dxf_export")
    if not isinstance(dxf_export, Mapping):
        return _unknown(
            "UNKNOWN_DXF_EXPORT_NOT_AVAILABLE",
            "manufacturing bundle has no typed dxf_export payload")

    remaining_gates = _gates(
        manufacturing_bundle, engineering_review, sewing_plan)
    candidate_state = str(manufacturing_bundle.get(
        "candidate_state", sewing_plan.get("candidate_state", "PROPOSED"))).upper()
    contains_proposed = (
        candidate_state != "APPROVED"
        or _walk_has_proposed(manufacturing_bundle)
        or _walk_has_proposed(engineering_review)
        or _walk_has_proposed(sewing_plan))
    source_readiness = {
        "manufacturing_bundle": manufacturing_bundle.get("manufacturing_ready") is True,
        "engineering_review": engineering_review.get("manufacturing_ready") is True,
        "sewing_plan": sewing_plan.get("manufacturing_ready") is True,
    }
    manufacturing_ready = all(source_readiness.values())
    if not manufacturing_ready and not remaining_gates:
        remaining_gates.append(
            "source artifacts do not unanimously assert manufacturing_ready")

    svg = _svg_artifact(
        manufacturing_bundle.get("svg"), lineage,
        manufacturing_ready=manufacturing_ready,
        remaining_gates=remaining_gates,
        inner_cut_digest=inner_cut_digest,
        inner_cut_count=len(inner_cuts))
    if svg is None:
        return _unknown(
            "UNKNOWN_SVG_EXPORT_NOT_AVAILABLE",
            "manufacturing bundle has no valid SVG payload")
    dxf_bytes, error = _dxf_artifact(
        dxf_export, lineage, manufacturing_ready=manufacturing_ready,
        remaining_gates=remaining_gates,
        inner_cut_digest=inner_cut_digest,
        inner_cut_count=len(inner_cuts))
    if error:
        return error
    assert dxf_bytes is not None

    sewing_json = _json_artifact(
        sewing_plan, lineage, manufacturing_ready=manufacturing_ready,
        remaining_gates=remaining_gates)
    engineering_json = _json_artifact(
        engineering_review, lineage, manufacturing_ready=manufacturing_ready,
        remaining_gates=remaining_gates)
    readme = _readme(
        lineage, candidate_state=candidate_state,
        manufacturing_ready=manufacturing_ready,
        contains_proposed=contains_proposed, remaining_gates=remaining_gates,
        inner_cut_count=len(inner_cuts))

    pending_files: Dict[str, FileValue] = {
        names["pattern_svg"]: svg,
        names["pattern_dxf"]: dxf_bytes,
        names["sewing_plan"]: sewing_json,
        names["engineering_review"]: engineering_json,
        names["readme"]: readme,
    }
    file_records = {
        filename: {
            "sha256": _content_digest(content),
            "bytes": len(_content_bytes(content)),
            "representation": "bytes" if isinstance(content, bytes) else "text",
            "encoding": (str(dxf_export["encoding"])
                         if filename == names["pattern_dxf"] else "utf-8"),
        }
        for filename, content in sorted(pending_files.items())
    }
    manifest = {
        "schema": SCHEMA,
        "lineage": dict(lineage),
        "candidate_state": candidate_state,
        "contains_proposed_or_inferred": contains_proposed,
        "source_readiness": source_readiness,
        "manufacturing_ready": manufacturing_ready,
        "remaining_gates": remaining_gates,
        "inner_cut_manifest": inner_cuts,
        "inner_cut_digest": inner_cut_digest,
        "files": file_records,
        "claims": {
            "package_is_in_memory": True,
            "filesystem_writes_performed": False,
            "geometry_changed": False,
            "manufacturing_readiness_synthesized": False,
            "industrial_certification": False,
        },
    }
    manifest["digest"] = _digest(manifest)
    manifest_text = json.dumps(
        manifest, sort_keys=True, ensure_ascii=False, indent=2,
        allow_nan=False) + "\n"
    files = {**pending_files, names["manifest"]: manifest_text}
    all_records = {
        filename: {
            "sha256": _content_digest(content),
            "bytes": len(_content_bytes(content)),
            "representation": "bytes" if isinstance(content, bytes) else "text",
        }
        for filename, content in sorted(files.items())
    }
    package_digest = _digest({
        "schema": SCHEMA,
        "lineage": lineage,
        "files": all_records,
    })
    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        "lineage": lineage,
        "candidate_state": candidate_state,
        "contains_proposed_or_inferred": contains_proposed,
        "manufacturing_ready": manufacturing_ready,
        "remaining_gates": remaining_gates,
        "inner_cut_manifest": inner_cuts,
        "inner_cut_digest": inner_cut_digest,
        "files": files,
        "file_metadata": all_records,
        "digest": package_digest,
        "filesystem_writes_performed": False,
    }


package = build
