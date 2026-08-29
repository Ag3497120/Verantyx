# -*- coding: utf-8 -*-
"""MCP extension surface for deterministic front-candidate evaluation.

The historical MCP implementation lives in :mod:`photoloset.mcp`.  This
module adds the front-only candidate evaluator to that same registry while
remaining executable as a normal stdio MCP server::

    python3 -m photoloset.mcp_server

The door is intentionally narrower than the Python evaluator.  It requires a
typed request, binds every supplied preview or pattern to an exact candidate
id, and never accepts approval or manufacturing authority from the caller.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Optional

from . import front_candidate_evaluator as _evaluator
from . import mcp as _mcp


REQUEST_SCHEMA = "garment.front-candidate-evaluation.request.v1"
TOOL_NAME = "garment_front_candidate_evaluate"


def _review_boundary(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Attach the non-negotiable authority boundary to every MCP reply."""
    bounded = dict(result)
    bounded.setdefault("schema", _evaluator.SCHEMA)
    bounded["state"] = "REVIEW"
    bounded["selected_candidate_id"] = None
    bounded["requires_human_approval"] = True
    bounded["rear_authority"] = "PROPOSED"
    bounded["material_authority"] = "PROPOSED"
    bounded["manufacturing_ready"] = False
    bounded["manufacturing_certified"] = False
    return bounded


def _refusal(verdict: str, why: str, **details: Any) -> str:
    result: Dict[str, Any] = {
        "schema": _evaluator.SCHEMA,
        "verdict": verdict,
        "why": why,
        "pareto_frontier": [],
    }
    result.update(details)
    return _mcp._ok(_review_boundary(result))


def _artifact_identity_error(
    artifacts: Any,
    *,
    kind: str,
    candidate_ids: set[str],
) -> Optional[Dict[str, Any]]:
    if artifacts is None:
        return None
    if not isinstance(artifacts, Mapping):
        return {
            "verdict": "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_MAP_REQUIRED",
            "why": f"{kind} must be an object keyed by candidate_id",
            "artifact_kind": kind,
        }
    for key in sorted(artifacts, key=str):
        artifact = artifacts[key]
        if not isinstance(key, str) or not key:
            return {
                "verdict": "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_ID_REQUIRED",
                "why": f"every supplied {kind} needs a non-empty candidate-id key",
                "artifact_kind": kind,
            }
        if key not in candidate_ids:
            return {
                "verdict": "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_ORPHANED",
                "why": f"supplied {kind} belongs to no candidate in this request",
                "artifact_kind": kind,
                "artifact_candidate_id": key,
            }
        if not isinstance(artifact, Mapping):
            return {
                "verdict": "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_REQUIRED",
                "why": f"{kind}[{key}] must be an artifact object",
                "artifact_kind": kind,
                "artifact_candidate_id": key,
            }
        embedded = artifact.get("candidate_id")
        if embedded != key:
            return {
                "verdict": "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_ID_MISMATCH",
                "why": (
                    f"{kind}[{key}] must carry that exact candidate_id; "
                    "artifacts are never matched by position"
                ),
                "artifact_kind": kind,
                "map_candidate_id": key,
                "artifact_candidate_id": embedded,
            }
    return None


@_mcp.tool
def garment_front_candidate_evaluate(json_text: str = "") -> str:
    """Pareto-evaluate typed front-only garment candidates without selecting one.

    ``json_text`` must be a
    ``garment.front-candidate-evaluation.request.v1`` object containing
    ``candidates`` and optional ``front_evidence``, candidate-id-keyed
    ``previews``, and candidate-id-keyed ``patterns``.  Rear and material
    claims remain PROPOSED.  Every result requires human approval and has
    ``manufacturing_ready=false``; no aggregate score or automatic winner is
    produced.
    """
    try:
        request = json.loads(json_text) if json_text.strip() else {}
    except json.JSONDecodeError as exc:
        return _refusal(
            "UNKNOWN_BAD_ARGUMENTS",
            f"json_text must be a {REQUEST_SCHEMA} JSON object: {exc}",
        )
    if not isinstance(request, Mapping):
        return _refusal(
            "UNKNOWN_FRONT_CANDIDATE_EVALUATION_REQUEST",
            f"request must be an object with schema {REQUEST_SCHEMA}",
        )
    if request.get("schema") != REQUEST_SCHEMA:
        return _refusal(
            "UNKNOWN_FRONT_CANDIDATE_EVALUATION_SCHEMA",
            f"schema must be exactly {REQUEST_SCHEMA}",
            received_schema=request.get("schema"),
        )

    candidates = request.get("candidates")
    if (not isinstance(candidates, Sequence)
            or isinstance(candidates, (str, bytes))
            or not candidates
            or any(not isinstance(candidate, Mapping)
                   for candidate in candidates)):
        return _refusal(
            "UNKNOWN_FRONT_CANDIDATES_REQUIRED",
            "candidates must be a non-empty array of candidate objects",
        )
    ids = [candidate.get("candidate_id") for candidate in candidates]
    candidate_ids = {
        value for value in ids if isinstance(value, str) and value.strip()
    }
    if len(candidate_ids) != len(candidates):
        verdict = (
            "UNKNOWN_DUPLICATE_FRONT_CANDIDATE_ID"
            if len(candidate_ids) < len(candidates)
            and all(isinstance(value, str) and value.strip() for value in ids)
            else "UNKNOWN_FRONT_CANDIDATE_ID_REQUIRED"
        )
        return _refusal(
            verdict,
            "every candidate needs a unique, non-empty candidate_id",
        )

    front_evidence = request.get("front_evidence", {})
    if not isinstance(front_evidence, Mapping):
        return _refusal(
            "UNKNOWN_FRONT_EVIDENCE_OBJECT_REQUIRED",
            "front_evidence must be an object",
        )
    for key in ("previews", "patterns"):
        error = _artifact_identity_error(
            request.get(key), kind=key, candidate_ids=candidate_ids)
        if error is not None:
            return _refusal(
                str(error.pop("verdict")), str(error.pop("why")), **error)

    result = _evaluator.evaluate_candidates(
        candidates,
        front_evidence=front_evidence,
        previews=request.get("previews"),
        patterns=request.get("patterns"),
    )
    bounded = _review_boundary(result)
    if (result.get("requires_human_approval") is not True
            or result.get("selected_candidate_id") is not None
            or result.get("manufacturing_ready") is not False
            or result.get("manufacturing_certified") is not False):
        return _refusal(
            "UNKNOWN_FRONT_CANDIDATE_AUTHORITY_BOUNDARY",
            "the evaluator attempted to cross the MCP approval or manufacturing boundary",
        )
    return _mcp._ok(bounded)


# Re-export the canonical protocol surface after registering the extension.
TOOLS = _mcp.TOOLS
handle = _mcp.handle
serve = _mcp.serve


if __name__ == "__main__":
    raise SystemExit(serve())
