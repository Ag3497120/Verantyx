#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from typing import Any


TOOL_NAME = "garment_front_candidate_artifact_pipeline"
REQUEST_SCHEMA = "garment.front-candidate-artifact-pipeline.request.v1"
FRONT_REQUEST_SCHEMA = "garment.front-image-generation.request.v1"
REQUIRED_MEASUREMENTS = (
    "chest_circumference_cm",
    "waist_circumference_cm",
    "hip_circumference_cm",
    "body_length_cm",
)
REPO_ROOT = Path(__file__).resolve().parents[1]


def _part(part_id: str, kind: str, dimensions: dict[str, float],
          placement: str, *, unit: str = "look", layer: int = 0,
          **extra: Any) -> dict[str, Any]:
    row = {
        "part_id": part_id,
        "kind": kind,
        "dimensions": dimensions,
        "placement": placement,
        "garment_unit": unit,
        "layer": layer,
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"front geometry supports {part_id}",
            "breaks_when": "another view or a human review rejects it",
        },
    }
    row.update(extra)
    return row


def _body(*, part_id: str = "body", unit: str = "look",
          layer: int = 0) -> dict[str, Any]:
    return _part(
        part_id,
        "BODY_SHELL",
        {"height_cm": 43.0, "circumference_cm": 90.0},
        "front torso",
        unit=unit,
        layer=layer,
    )


def _skirt(*, unit: str = "look", **extra: Any) -> dict[str, Any]:
    return _part(
        "skirt",
        "FLARE",
        {
            "height_cm": 64.0,
            "top_circumference_cm": 76.0,
            "bottom_circumference_cm": 172.0,
        },
        "lower body",
        unit=unit,
        **extra,
    )


def _candidate(candidate_id: str,
               parts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "parts": parts,
        "rear_hypothesis": {
            "state": "PROPOSED",
            "value": "center-back opening alternative",
            "basis": "the rear is absent from the front image",
            "breaks_when": "a rear or side view is supplied",
        },
        "material_hypothesis": {
            "state": "PROPOSED",
            "value": "medium drape range",
            "basis": "appearance only bounds material behaviour",
            "breaks_when": "a swatch or material test is supplied",
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }


def _measurements() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "value_cm": 82.0 + index,
            "authority": "USER_PROVIDED",
            "source": "named target wearer",
        }
        for index, name in enumerate(REQUIRED_MEASUREMENTS)
    }


def _request(*candidates: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "front_image_request": {
            "schema": FRONT_REQUEST_SCHEMA,
            "source": {"image_id": "sha256:mcp-artifact-fixture",
                       "view": "front"},
            "vision": {
                "observations": [{
                    "claim_id": "front-outline",
                    "field": "front.silhouette",
                    "value": "structured geometry supplied in candidates",
                    "authority": "OBSERVED",
                    "basis": "corrected visible front boundary",
                }],
                "proposals": [{
                    "claim_id": "front-depth",
                    "field": "front.depth_interpretation",
                    "value": "candidate dependent",
                    "authority": "PROPOSED",
                    "basis": "one front image does not observe depth",
                }],
            },
            "wearer_measurements": _measurements(),
            "candidates": list(candidates),
            "artifacts": {},
            "approvals": {},
            "rounds": [],
            "max_rounds": 8,
        },
    }


def _rpc(method: str, *, request_id: int,
         params: dict[str, Any] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        message["params"] = params
    return message


def _run_stdio(*messages: dict[str, Any]) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as temp_home:
        env = os.environ.copy()
        env["PHOTOLOSET_HOME"] = temp_home
        completed = subprocess.run(
            [sys.executable, "-m", "photoloset.mcp"],
            cwd=REPO_ROOT,
            env=env,
            input="".join(json.dumps(message) + "\n" for message in messages),
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    if completed.returncode != 0:
        raise AssertionError(
            f"stdio MCP exited {completed.returncode}: {completed.stderr}")
    return [json.loads(line) for line in completed.stdout.splitlines() if line]


def _call(request: Any, request_id: int = 1) -> dict[str, Any]:
    json_text = (request if isinstance(request, str)
                 else json.dumps(request, allow_nan=False))
    response = _run_stdio(_rpc(
        "tools/call",
        request_id=request_id,
        params={
            "name": TOOL_NAME,
            "arguments": {"json_text": json_text},
        },
    ))[0]
    return json.loads(response["result"]["content"][0]["text"])


def _assert_not_manufacturing_ready(test: unittest.TestCase,
                                    value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"manufacturing_ready", "manufacturing_certified"}:
                test.assertIs(child, False, key)
            _assert_not_manufacturing_ready(test, child)
    elif isinstance(value, list):
        for child in value:
            _assert_not_manufacturing_ready(test, child)


class MCPFrontCandidateArtifactPipelineTests(unittest.TestCase):
    maxDiff = None

    def test_tools_list_exposes_typed_json_text_and_bad_json_is_typed(self):
        response = _run_stdio(_rpc("tools/list", request_id=1))[0]
        tools = {tool["name"]: tool
                 for tool in response["result"]["tools"]}

        self.assertIn(TOOL_NAME, tools)
        self.assertEqual(tools[TOOL_NAME]["inputSchema"], {
            "type": "object",
            "properties": {
                "json_text": {"type": "string", "default": ""},
            },
            "required": [],
        })
        malformed = _call("{not-json", request_id=2)
        self.assertEqual(malformed["verdict"], "UNKNOWN_BAD_ARGUMENTS")
        self.assertIn(REQUEST_SCHEMA, malformed["why"])

    def test_stdio_binds_distinct_top_bottom_and_one_piece_digests(self):
        separated = _candidate("separated", [
            _body(unit="upper-unit"),
            _skirt(unit="lower-unit"),
        ])
        one_piece = _candidate("one-piece", [
            _body(),
            _skirt(attached_to="body", attachment_relation="JOIN"),
        ])
        request = _request(separated, one_piece)
        first = _call(request)
        reordered = copy.deepcopy(request)
        reordered["front_image_request"]["candidates"].reverse()
        second = _call(reordered, request_id=2)

        self.assertEqual(first, second)
        self.assertEqual(first["verdict"], "REVIEW")
        self.assertTrue(first["requires_human_approval"])
        self.assertTrue(first["human_choice"]["required"])
        self.assertIsNone(first["human_choice"]["selected_candidate_id"])
        self.assertEqual(first["source_candidate_count"], 2)
        self.assertEqual(first["structure_candidate_count"], 2)

        bundles = {row["candidate_id"]: row
                   for row in first["source_candidates"]}
        self.assertEqual(set(bundles), {"separated", "one-piece"})
        source_digests = {
            bundles[name]["candidate_digest"] for name in bundles
        }
        self.assertEqual(len(source_digests), 2)
        structure_digests = set()
        artifact_digests = set()
        for name, bundle in bundles.items():
            self.assertRegex(bundle["candidate_digest"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(bundle["structure_alternatives"]), 1)
            structure = bundle["structure_alternatives"][0]
            self.assertEqual(structure["source_candidate_id"], name)
            self.assertEqual(structure["source_candidate_digest"],
                             bundle["candidate_digest"])
            self.assertRegex(structure["candidate_digest"], r"^[0-9a-f]{64}$")
            self.assertRegex(structure["artifact_digest"], r"^[0-9a-f]{64}$")
            structure_digests.add(structure["candidate_digest"])
            artifact_digests.add(structure["artifact_digest"])
            pattern = structure["pattern_candidate"]
            self.assertEqual(pattern["candidate_id"],
                             structure["candidate_id"])
            self.assertEqual(pattern["candidate_digest"],
                             structure["candidate_digest"])
            self.assertTrue(pattern["requires_human_approval"])
            self.assertFalse(pattern["auto_approved"])

        self.assertEqual(len(structure_digests), 2)
        self.assertEqual(len(artifact_digests), 2)
        self.assertEqual(
            bundles["separated"]["structure_alternatives"][0]
            ["structure"]["structure_graph"]["operations"],
            [],
        )
        self.assertEqual(
            [row["kind"] for row in
             bundles["one-piece"]["structure_alternatives"][0]
             ["structure"]["structure_graph"]["operations"]],
            ["JOIN"],
        )
        _assert_not_manufacturing_ready(self, first)

    def test_stdio_compiles_explicit_layered_bodice_sleeve_parent(self):
        good = _candidate("good", [
            _body(unit="upper"),
            _skirt(unit="lower"),
        ])
        unsupported = _candidate("unsupported", [
            _body(part_id="inner-body", unit="inner", layer=0),
            _body(part_id="outer-body", unit="outer", layer=1),
            _part(
                "outer-sleeve",
                "SLEEVE",
                {
                    "length_cm": 55.0,
                    "upper_circumference_cm": 32.0,
                    "cuff_circumference_cm": 20.0,
                },
                "arms",
                unit="outer",
                layer=1,
                attached_to="outer-body",
            ),
        ])
        result = _call(_request(good, unsupported))
        bundles = {row["candidate_id"]: row
                   for row in result["source_candidates"]}

        compiled = bundles["good"]["structure_alternatives"][0]
        layered = bundles["unsupported"]["structure_alternatives"][0]
        self.assertEqual(compiled["pattern_candidate"]["verdict"], "ANSWER")
        self.assertEqual(layered["state"], "PROPOSED")
        self.assertEqual(layered["pattern_candidate"]["verdict"], "ANSWER")
        pattern = layered["pattern_candidate"]["compiler_result"]
        self.assertEqual(
            {piece.get("source_node_id") for piece in pattern["pieces"]},
            {"inner-body", "outer-body", "outer-sleeve"},
        )
        self.assertEqual(
            pattern["candidate_specific_expansions"][0]["source_nodes"],
            ["outer-body", "outer-sleeve"],
        )
        self.assertEqual(result["compiled_pattern_candidate_count"], 2)
        self.assertEqual(result["stopped_candidate_count"], 0)
        self.assertFalse(result["claims"]["failed_candidate_dropped"])
        self.assertTrue(result["requires_human_approval"])
        self.assertIsNone(result["human_choice"]["selected_candidate_id"])
        self.assertFalse(result["claims"]["candidate_auto_selected"])
        self.assertFalse(result["claims"]["candidate_auto_approved"])
        _assert_not_manufacturing_ready(self, result)


if __name__ == "__main__":
    unittest.main()
