# -*- coding: utf-8 -*-
"""Verify a transported garment hand-off package without trusting its wrapper.

The exporter binds candidate lineage and hashes into six artifacts.  This
module checks those bindings again after UI/MCP transport, where text and DXF
bytes may have been copied, decoded, or replaced.  Verification proves package
integrity and lineage consistency only; it never certifies fit, strength,
comfort, sewing technique, or manufacturing readiness.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from pathlib import PurePath
from typing import Any, Dict, Mapping, Optional, Tuple, Union


ANSWER = "ANSWER"
SCHEMA = "garment.export-verification.v1"
PACKAGE_SCHEMA = "garment.export-package.v1"
FileValue = Union[str, bytes]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _bytes(value: FileValue) -> bytes:
    return value if isinstance(value, bytes) else value.encode("utf-8")


def _unknown(code: str, why: str, **detail: Any) -> Dict[str, Any]:
    return {
        "verdict": code,
        "schema": SCHEMA,
        "verified": False,
        "manufacturing_certified": False,
        "why": why,
        **detail,
    }


def _leaf(name: Any) -> bool:
    if not isinstance(name, str) or not name or "\x00" in name:
        return False
    path = PurePath(name)
    return (name not in {".", ".."} and "/" not in name and "\\" not in name
            and not path.is_absolute() and len(path.parts) == 1)


def _decode_file(name: str, value: Any) -> Tuple[Optional[FileValue], Optional[Dict[str, Any]]]:
    if isinstance(value, (str, bytes)):
        return value, None
    if not isinstance(value, Mapping):
        return None, _unknown(
            "UNKNOWN_EXPORT_TRANSPORT_VALUE",
            "each transported file must be text, bytes, or a typed transport object",
            filename=name)
    representation = value.get("representation")
    declared_bytes = value.get("bytes")
    if representation == "text" and isinstance(value.get("text"), str):
        decoded: FileValue = value["text"]
    elif representation == "base64" and isinstance(value.get("data"), str):
        try:
            decoded = base64.b64decode(value["data"], validate=True)
        except (ValueError, TypeError) as exc:
            return None, _unknown(
                "UNKNOWN_EXPORT_BASE64",
                "binary transport is not strict base64",
                filename=name, detail=str(exc))
    else:
        return None, _unknown(
            "UNKNOWN_EXPORT_TRANSPORT_REPRESENTATION",
            "transport representation must be text or base64 and carry its payload",
            filename=name, representation=representation)
    if (isinstance(declared_bytes, bool) or not isinstance(declared_bytes, int)
            or declared_bytes != len(_bytes(decoded))):
        return None, _unknown(
            "UNKNOWN_EXPORT_TRANSPORT_LENGTH",
            "transport byte count does not match the decoded payload",
            filename=name, declared=declared_bytes,
            actual=len(_bytes(decoded)))
    return decoded, None


def _decode_files(raw: Any) -> Tuple[Optional[Dict[str, FileValue]], Optional[Dict[str, Any]]]:
    if not isinstance(raw, Mapping) or not raw:
        return None, _unknown("UNKNOWN_EXPORT_FILES_REQUIRED",
                              "a non-empty filename to payload map is required")
    files: Dict[str, FileValue] = {}
    for name, value in raw.items():
        if not _leaf(name):
            return None, _unknown("UNKNOWN_EXPORT_PATH_TRAVERSAL",
                                  "package entries must be leaf filenames",
                                  filename=name)
        decoded, error = _decode_file(name, value)
        if error:
            return None, error
        assert decoded is not None
        files[name] = decoded
    return files, None


def _manifest(files: Mapping[str, FileValue]) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    matches = []
    for name, value in files.items():
        if not isinstance(value, str):
            continue
        try:
            document = json.loads(value)
        except (TypeError, ValueError):
            continue
        if isinstance(document, dict) and document.get("schema") == PACKAGE_SCHEMA:
            matches.append((name, document))
    if len(matches) != 1:
        return None, None, _unknown(
            "UNKNOWN_EXPORT_MANIFEST",
            "exactly one package manifest must be present",
            manifest_count=len(matches))
    return matches[0][0], matches[0][1], None


def _same_lineage(actual: Any, expected: Mapping[str, Any]) -> bool:
    return isinstance(actual, Mapping) and dict(actual) == dict(expected)


def _inner_manifest(manifest: Mapping[str, Any]) -> Tuple[Optional[list[Dict[str, Any]]], Optional[str], Optional[Dict[str, Any]]]:
    raw = manifest.get("inner_cut_manifest", [])
    if not isinstance(raw, list):
        return None, None, _unknown(
            "UNKNOWN_EXPORT_INNER_CUT_MANIFEST",
            "manifest inner_cut_manifest must be a list")
    records: list[Dict[str, Any]] = []
    identities = set()
    for value in raw:
        if not isinstance(value, Mapping):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_MANIFEST",
                "manifest inner cut rows must be objects")
        row = dict(value)
        identity = (row.get("piece_id"), row.get("operation_id"),
                    row.get("contour_id"))
        if (not all(isinstance(item, str) and item for item in identity)
                or identity in identities or row.get("kind") != "CUTOUT"):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_BINDING",
                "inner cut piece/operation/contour binding is invalid")
        identities.add(identity)
        front_digest = row.get("source_front_boundary_digest")
        if front_digest is not None and (
                not isinstance(front_digest, str) or not front_digest.strip()
                or row.get("source_front_boundary_digest_state")
                != "PROPOSED_LINEAGE_ONLY"
                or row.get("source_front_boundary_semantics_observed") is not False):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_FRONT_BOUNDARY_LINEAGE",
                "front-boundary digest must remain non-semantic PROPOSED lineage",
                identity=identity)
        expected = row.pop("digest", None)
        if expected != _digest(row):
            return None, None, _unknown(
                "UNKNOWN_EXPORT_INNER_CUT_DIGEST",
                "inner cut geometry/lineage digest does not match",
                identity=identity)
        row["digest"] = expected
        records.append(row)
    digest = _digest(records)
    if manifest.get("inner_cut_digest", _digest([])) != digest:
        return None, None, _unknown(
            "UNKNOWN_EXPORT_INNER_CUT_DIGEST",
            "manifest inner_cut_digest does not match its rows")
    return records, digest, None


def _parse_svg_points(text: str) -> Optional[list[list[float]]]:
    points = []
    try:
        for pair in text.split():
            x, y = pair.split(",", 1)
            points.append([round(float(x), 6), round(float(y), 6)])
    except (TypeError, ValueError, OverflowError):
        return None
    return points if len(points) >= 3 else None


def _verify_json_artifact(name: str, value: FileValue,
                          lineage: Mapping[str, Any], manifest: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(value, str):
        return _unknown("UNKNOWN_EXPORT_JSON_NOT_TEXT",
                        "JSON artifacts must remain UTF-8 text", filename=name)
    try:
        document = json.loads(value)
    except (TypeError, ValueError) as exc:
        return _unknown("UNKNOWN_EXPORT_JSON_INVALID",
                        "JSON artifact no longer parses", filename=name,
                        detail=str(exc))
    if not isinstance(document, Mapping) or not _same_lineage(
            document.get("export_lineage"), lineage):
        return _unknown("UNKNOWN_EXPORT_ARTIFACT_LINEAGE",
                        "JSON artifact lineage differs from the manifest",
                        filename=name)
    if document.get("export_manufacturing_ready") is not manifest.get(
            "manufacturing_ready"):
        return _unknown("UNKNOWN_EXPORT_READINESS_MISMATCH",
                        "JSON artifact readiness differs from the manifest",
                        filename=name)
    if document.get("export_remaining_gates") != manifest.get("remaining_gates"):
        return _unknown("UNKNOWN_EXPORT_GATES_MISMATCH",
                        "JSON artifact gates differ from the manifest",
                        filename=name)
    return None


def _verify_svg(name: str, value: FileValue,
                lineage: Mapping[str, Any], manifest: Mapping[str, Any],
                inner_cuts: list[Dict[str, Any]],
                inner_cut_digest: str) -> Optional[Dict[str, Any]]:
    if not isinstance(value, str):
        return _unknown("UNKNOWN_EXPORT_SVG_NOT_TEXT",
                        "SVG must remain UTF-8 text", filename=name)
    match = re.search(
        r'<metadata\s+id="photoloset-export-lineage">(.*?)</metadata>',
        value, flags=re.DOTALL)
    if not match:
        return _unknown("UNKNOWN_EXPORT_SVG_METADATA",
                        "SVG lineage metadata is missing", filename=name)
    try:
        metadata = json.loads(html.unescape(match.group(1)))
    except (TypeError, ValueError) as exc:
        return _unknown("UNKNOWN_EXPORT_SVG_METADATA",
                        "SVG lineage metadata no longer parses",
                        filename=name, detail=str(exc))
    if not isinstance(metadata, Mapping) or not _same_lineage(
            metadata.get("lineage"), lineage):
        return _unknown("UNKNOWN_EXPORT_ARTIFACT_LINEAGE",
                        "SVG lineage differs from the manifest", filename=name)
    if metadata.get("manufacturing_ready") is not manifest.get("manufacturing_ready"):
        return _unknown("UNKNOWN_EXPORT_READINESS_MISMATCH",
                        "SVG readiness differs from the manifest", filename=name)
    if metadata.get("remaining_gates") != manifest.get("remaining_gates"):
        return _unknown("UNKNOWN_EXPORT_GATES_MISMATCH",
                        "SVG gates differ from the manifest", filename=name)
    if (metadata.get("inner_cut_digest") != inner_cut_digest
            or metadata.get("inner_cut_count") != len(inner_cuts)):
        return _unknown("UNKNOWN_EXPORT_INNER_CUT_SVG",
                        "SVG inner cut metadata differs from the manifest",
                        filename=name)
    actual = {}
    for attribute_text in re.findall(r'<polygon\b([^>]*)/?>', value,
                                     flags=re.DOTALL):
        attributes = {
            key: html.unescape(item)
            for key, item in re.findall(
                r'([A-Za-z_:][A-Za-z0-9_.:-]*)="([^"]*)"',
                attribute_text)
        }
        if attributes.get("data-layer") != "INNER_CUT":
            continue
        digest = attributes.get("data-contour-digest")
        points = _parse_svg_points(attributes.get("points", ""))
        if not digest or points is None or digest in actual:
            return _unknown("UNKNOWN_EXPORT_INNER_CUT_SVG",
                            "SVG has an invalid or duplicate INNER_CUT polygon",
                            filename=name)
        actual[digest] = {
            "piece_id": attributes.get("data-piece"),
            "operation_id": attributes.get("data-operation-id"),
            "contour_id": attributes.get("data-contour-id"),
            "state": attributes.get("data-state"),
            "source_front_boundary_digest": attributes.get(
                "data-source-front-boundary-digest"),
            "points": points,
        }
    expected = {
        row["digest"]: {
            "piece_id": row["piece_id"],
            "operation_id": row["operation_id"],
            "contour_id": row["contour_id"],
            "state": row["state"],
            "source_front_boundary_digest": row.get(
                "source_front_boundary_digest"),
            "points": [[round(float(x), 6), round(float(y), 6)]
                       for x, y in row["svg_points"]],
        }
        for row in inner_cuts
    }
    if actual != expected:
        return _unknown("UNKNOWN_EXPORT_INNER_CUT_SVG",
                        "SVG INNER_CUT geometry or binding differs from the manifest",
                        filename=name)
    return None


def _dxf_comments(value: FileValue, encoding: str) -> Tuple[Optional[Dict[str, str]], Optional[Dict[str, Any]]]:
    raw = _bytes(value)
    try:
        text = raw.decode(encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        return None, _unknown("UNKNOWN_EXPORT_DXF_ENCODING",
                              "DXF cannot be decoded with its manifest encoding",
                              encoding=encoding, detail=str(exc))
    lines = text.splitlines()
    comments: Dict[str, str] = {}
    for index in range(len(lines) - 1):
        if lines[index].strip() != "999" or "=" not in lines[index + 1]:
            continue
        key, value_text = lines[index + 1].split("=", 1)
        comments[key.strip()] = value_text.strip()
    return comments, None


def _dxf_inner_records(value: FileValue, encoding: str) -> Tuple[Optional[list[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    try:
        lines = _bytes(value).decode(encoding).splitlines()
    except (LookupError, UnicodeDecodeError) as exc:
        return None, _unknown("UNKNOWN_EXPORT_DXF_ENCODING",
                              "DXF inner cuts cannot be decoded",
                              encoding=encoding, detail=str(exc))
    if len(lines) % 2:
        return None, _unknown("UNKNOWN_EXPORT_DXF_STRUCTURE",
                              "DXF group-code/value stream has odd line count")
    pairs = [(lines[index].strip(), lines[index + 1].strip())
             for index in range(0, len(lines), 2)]
    records: list[Dict[str, Any]] = []
    pending: Optional[Dict[str, Any]] = None
    index = 0
    while index < len(pairs):
        code, value_text = pairs[index]
        if code == "999" and value_text.startswith("inner_cut_record_b64="):
            encoded = value_text.split("=", 1)[1]
            try:
                pending_value = json.loads(base64.urlsafe_b64decode(
                    encoded.encode("ascii")).decode("utf-8"))
            except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
                return None, _unknown("UNKNOWN_EXPORT_INNER_CUT_DXF",
                                      "DXF inner cut binding metadata is invalid",
                                      detail=str(exc))
            if not isinstance(pending_value, dict):
                return None, _unknown("UNKNOWN_EXPORT_INNER_CUT_DXF",
                                      "DXF inner cut binding must decode to an object")
            pending = pending_value
            index += 1
            continue
        if code == "0" and value_text == "POLYLINE":
            layer = None
            cursor = index + 1
            while cursor < len(pairs) and pairs[cursor][0] != "0":
                if pairs[cursor][0] == "8":
                    layer = pairs[cursor][1]
                cursor += 1
            points: list[list[float]] = []
            while cursor < len(pairs):
                entity_code, entity_name = pairs[cursor]
                if entity_code == "0" and entity_name == "SEQEND":
                    cursor += 1
                    break
                if entity_code != "0" or entity_name != "VERTEX":
                    break
                cursor += 1
                x = y = None
                vertex_layer = None
                while cursor < len(pairs) and pairs[cursor][0] != "0":
                    group, field = pairs[cursor]
                    if group == "8":
                        vertex_layer = field
                    elif group == "10":
                        x = field
                    elif group == "20":
                        y = field
                    cursor += 1
                if layer == "INNER_CUT" or vertex_layer == "INNER_CUT":
                    try:
                        points.append([round(float(x), 4), round(float(y), 4)])
                    except (TypeError, ValueError, OverflowError):
                        return None, _unknown("UNKNOWN_EXPORT_INNER_CUT_DXF",
                                              "DXF INNER_CUT vertex is not finite")
            if layer == "INNER_CUT":
                if pending is None or len(points) < 3:
                    return None, _unknown("UNKNOWN_EXPORT_INNER_CUT_DXF",
                                          "DXF INNER_CUT lacks binding metadata or vertices")
                records.append({**pending, "points": points})
                pending = None
            index = cursor
            continue
        index += 1
    if pending is not None:
        return None, _unknown("UNKNOWN_EXPORT_INNER_CUT_DXF",
                              "DXF inner cut metadata is not followed by its polyline")
    return records, None


def _verify_dxf(name: str, value: FileValue, record: Mapping[str, Any],
                lineage: Mapping[str, Any], manifest: Mapping[str, Any],
                inner_cuts: list[Dict[str, Any]],
                inner_cut_digest: str) -> Optional[Dict[str, Any]]:
    encoding = record.get("encoding")
    if not isinstance(encoding, str) or not encoding:
        return _unknown("UNKNOWN_EXPORT_DXF_ENCODING",
                        "manifest must name the DXF encoding", filename=name)
    comments, error = _dxf_comments(value, encoding)
    if error:
        return error
    assert comments is not None
    expected = {
        "candidate_digest": lineage.get("candidate_digest"),
        "structure_digest": lineage.get("structure_digest"),
        "source_digest": lineage.get("source_digest"),
        "manufacturing_ready": str(bool(manifest.get("manufacturing_ready"))).lower(),
        "remaining_gates_digest": "sha256:" + _digest(manifest.get("remaining_gates")),
        "inner_cut_digest": inner_cut_digest,
        "inner_cut_count": str(len(inner_cuts)),
    }
    for key, expected_value in expected.items():
        if comments.get(key) != expected_value:
            return _unknown("UNKNOWN_EXPORT_ARTIFACT_LINEAGE",
                            "DXF metadata differs from the manifest",
                            filename=name, field=key,
                            expected=expected_value, actual=comments.get(key))
    candidate_b64 = comments.get("candidate_id_utf8_b64")
    try:
        padded = str(candidate_b64) + "=" * (-len(str(candidate_b64)) % 4)
        candidate_id = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        return _unknown("UNKNOWN_EXPORT_DXF_CANDIDATE_ID",
                        "DXF candidate id metadata does not decode",
                        filename=name, detail=str(exc))
    if candidate_id != lineage.get("candidate_id"):
        return _unknown("UNKNOWN_EXPORT_ARTIFACT_LINEAGE",
                        "DXF candidate id differs from the manifest",
                        filename=name, expected=lineage.get("candidate_id"),
                        actual=candidate_id)
    decoded, error = _dxf_inner_records(value, encoding)
    if error:
        error["filename"] = name
        return error
    assert decoded is not None
    actual = {
        row.get("digest"): {
            "piece_id": row.get("piece_id"),
            "operation_id": row.get("operation_id"),
            "contour_id": row.get("contour_id"),
            "source_front_boundary_digest": row.get(
                "source_front_boundary_digest"),
            "points": row.get("points"),
        }
        for row in decoded
    }
    expected_inner = {
        row["digest"]: {
            "piece_id": row["piece_id"],
            "operation_id": row["operation_id"],
            "contour_id": row["contour_id"],
            "source_front_boundary_digest": row.get(
                "source_front_boundary_digest"),
            "points": [[round(float(x), 4), round(float(y), 4)]
                       for x, y in row["dxf_points"]],
        }
        for row in inner_cuts
    }
    if actual != expected_inner:
        return _unknown("UNKNOWN_EXPORT_INNER_CUT_DXF",
                        "DXF INNER_CUT geometry or binding differs from the manifest",
                        filename=name)
    return None


def verify(package: Mapping[str, Any]) -> Dict[str, Any]:
    """Verify exact package bytes/text after either in-memory or MCP transport."""
    if not isinstance(package, Mapping) or package.get("schema") != PACKAGE_SCHEMA:
        return _unknown("UNKNOWN_EXPORT_PACKAGE_REQUIRED",
                        f"expected schema {PACKAGE_SCHEMA}")
    if package.get("verdict") != ANSWER:
        return _unknown("UNKNOWN_EXPORT_PACKAGE_REFUSED",
                        "a refused export cannot be verified as a complete package")
    files, error = _decode_files(package.get("files"))
    if error:
        return error
    assert files is not None
    manifest_name, manifest, error = _manifest(files)
    if error:
        return error
    assert manifest_name is not None and manifest is not None
    lineage = manifest.get("lineage")
    if not isinstance(lineage, Mapping) or not _same_lineage(
            package.get("lineage"), lineage):
        return _unknown("UNKNOWN_EXPORT_PACKAGE_LINEAGE",
                        "package wrapper and manifest lineage differ")
    manifest_copy = dict(manifest)
    manifest_digest = manifest_copy.pop("digest", None)
    if manifest_digest != _digest(manifest_copy):
        return _unknown("UNKNOWN_EXPORT_MANIFEST_DIGEST",
                        "manifest digest does not match its content")
    inner_cuts, inner_cut_digest, error = _inner_manifest(manifest)
    if error:
        return error
    assert inner_cuts is not None and inner_cut_digest is not None
    wrapper_fields = {
        "candidate_state": manifest.get("candidate_state"),
        "contains_proposed_or_inferred": manifest.get(
            "contains_proposed_or_inferred"),
        "manufacturing_ready": manifest.get("manufacturing_ready"),
        "remaining_gates": manifest.get("remaining_gates"),
        "inner_cut_manifest": inner_cuts,
        "inner_cut_digest": inner_cut_digest,
    }
    wrapper_mismatches = [
        field for field, expected in wrapper_fields.items()
        if package.get(field) != expected
    ]
    if wrapper_mismatches:
        return _unknown("UNKNOWN_EXPORT_WRAPPER_STATE",
                        "package wrapper state differs from the manifest",
                        fields=wrapper_mismatches)
    records = manifest.get("files")
    if not isinstance(records, Mapping):
        return _unknown("UNKNOWN_EXPORT_MANIFEST_FILES",
                        "manifest files table is missing")
    payload_names = set(files) - {manifest_name}
    if payload_names != set(records):
        return _unknown("UNKNOWN_EXPORT_FILE_SET",
                        "transported files differ from the manifest",
                        missing=sorted(set(records) - payload_names),
                        unexpected=sorted(payload_names - set(records)))
    for name, record in records.items():
        if not isinstance(record, Mapping):
            return _unknown("UNKNOWN_EXPORT_FILE_RECORD",
                            "manifest file record must be an object", filename=name)
        raw = _bytes(files[name])
        if record.get("sha256") != hashlib.sha256(raw).hexdigest():
            return _unknown("UNKNOWN_EXPORT_FILE_DIGEST",
                            "artifact bytes differ from the manifest", filename=name)
        if record.get("bytes") != len(raw):
            return _unknown("UNKNOWN_EXPORT_FILE_LENGTH",
                            "artifact byte count differs from the manifest", filename=name)

    wrapper_metadata = package.get("file_metadata")
    if not isinstance(wrapper_metadata, Mapping) or set(wrapper_metadata) != set(files):
        return _unknown("UNKNOWN_EXPORT_WRAPPER_METADATA",
                        "wrapper metadata must cover every transported file")
    computed_metadata = {
        name: {
            "sha256": hashlib.sha256(_bytes(value)).hexdigest(),
            "bytes": len(_bytes(value)),
            "representation": "bytes" if isinstance(value, bytes) else "text",
        }
        for name, value in sorted(files.items())
    }
    if {name: dict(row) for name, row in wrapper_metadata.items()
            if isinstance(row, Mapping)} != computed_metadata:
        return _unknown("UNKNOWN_EXPORT_WRAPPER_METADATA",
                        "wrapper file metadata differs from decoded content")
    expected_package_digest = _digest({
        "schema": PACKAGE_SCHEMA,
        "lineage": dict(lineage),
        "files": computed_metadata,
    })
    if package.get("digest") != expected_package_digest:
        return _unknown("UNKNOWN_EXPORT_PACKAGE_DIGEST",
                        "package digest does not match its decoded files")

    for name, record in records.items():
        value = files[name]
        encoding = record.get("encoding")
        if isinstance(value, str) and "photoloset-export-lineage" in value:
            error = _verify_svg(name, files[name], lineage, manifest,
                                inner_cuts, inner_cut_digest)
        elif encoding != "utf-8":
            error = _verify_dxf(name, files[name], record, lineage, manifest,
                                inner_cuts, inner_cut_digest)
        else:
            try:
                document = json.loads(value) if isinstance(value, str) else None
            except (TypeError, ValueError):
                document = None
            error = (_verify_json_artifact(name, value, lineage, manifest)
                     if isinstance(document, Mapping)
                     and "export_lineage" in document else None)
        if error:
            return error

    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        "verified": True,
        "package_digest": expected_package_digest,
        "manifest_filename": manifest_name,
        "file_count": len(files),
        "lineage": dict(lineage),
        "contains_proposed_or_inferred": bool(
            manifest.get("contains_proposed_or_inferred")),
        "manufacturing_ready": manifest.get("manufacturing_ready") is True,
        "manufacturing_certified": False,
        "inner_cut_count": len(inner_cuts),
        "inner_cut_digest": inner_cut_digest,
        "verification_scope": "transport integrity and candidate lineage only",
    }


check = verify
