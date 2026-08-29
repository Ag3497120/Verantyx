#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOL_NAME = "garment_candidate_pattern_sewing_assemble"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _request():
    required = (
        "chest_circumference_cm", "waist_circumference_cm",
        "hip_circumference_cm", "body_length_cm",
    )
    return {
        "schema": "garment.front-candidate-artifact-pipeline.request.v1",
        "front_image_request": {
            "schema": "garment.front-image-generation.request.v1",
            "source": {"image_id": "sha256:mcp-cut-sew", "view": "front"},
            "vision": {
                "observations": [{
                    "claim_id": "front-outline", "field": "front.silhouette",
                    "value": "typed geometry below", "authority": "OBSERVED",
                    "basis": "human-confirmed visible outer boundary",
                }],
                "proposals": [{
                    "claim_id": "depth", "field": "front.depth_interpretation",
                    "value": "candidate dependent", "authority": "PROPOSED",
                    "basis": "one front view does not observe depth",
                }],
            },
            "wearer_measurements": {
                name: {"value_cm": 84 + index,
                       "authority": "USER_PROVIDED",
                       "source": "named target wearer"}
                for index, name in enumerate(required)
            },
            "candidates": [{
                "candidate_id": "one-piece", "state": "PROPOSED",
                "parts": [
                    {"part_id": "body", "kind": "BODY_SHELL", "layer": 0,
                     "placement": "front torso", "garment_unit": "look",
                     "dimensions": {"height_cm": 43, "circumference_cm": 76},
                     "visible_basis": {"state": "PROPOSED",
                        "basis": "front geometry", "breaks_when": "review"}},
                    {"part_id": "skirt", "kind": "FLARE", "layer": 0,
                     "placement": "lower body", "garment_unit": "look",
                     "attached_to": "body", "attachment_relation": "JOIN",
                     "dimensions": {"height_cm": 64,
                         "top_circumference_cm": 76,
                         "bottom_circumference_cm": 172},
                     "visible_basis": {"state": "PROPOSED",
                        "basis": "front geometry", "breaks_when": "review"}},
                ],
                "rear_hypothesis": {"state": "PROPOSED",
                    "value": "center-back opening candidate",
                    "basis": "rear absent", "breaks_when": "rear view"},
                "material_hypothesis": {"state": "PROPOSED",
                    "value": "bounded drape range", "basis": "appearance only",
                    "breaks_when": "swatch test"},
                "manufacturing_ready": False,
                "manufacturing_certified": False,
            }],
            "artifacts": {}, "approvals": {}, "rounds": [], "max_rounds": 8,
        },
    }


def _rpc(method, request_id, params=None):
    row = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        row["params"] = params
    return row


def _stdio(*messages):
    with tempfile.TemporaryDirectory() as temp_home:
        environment = os.environ.copy()
        environment["PHOTOLOSET_HOME"] = temp_home
        completed = subprocess.run(
            [sys.executable, "-m", "photoloset.mcp"], cwd=REPO_ROOT,
            env=environment,
            input="".join(json.dumps(row) + "\n" for row in messages),
            text=True, capture_output=True, check=False, timeout=30,
        )
    if completed.returncode:
        raise AssertionError(completed.stderr)
    return [json.loads(line) for line in completed.stdout.splitlines() if line]


class MCPCandidatePatternSewingPipelineTests(unittest.TestCase):
    def test_stdio_lists_and_runs_digest_bound_cut_sew_pipeline(self):
        listed = _stdio(_rpc("tools/list", 1))[0]
        tools = {row["name"]: row for row in listed["result"]["tools"]}
        self.assertIn(TOOL_NAME, tools)
        called = _stdio(_rpc("tools/call", 2, {
            "name": TOOL_NAME,
            "arguments": {"json_text": json.dumps(_request())},
        }))[0]
        result = json.loads(called["result"]["content"][0]["text"])
        self.assertEqual(result["schema"],
                         "garment.candidate-pattern-sewing-pipeline.v1")
        candidate = result["candidates"][0]
        self.assertEqual(candidate["state"], "REVIEW")
        self.assertTrue(candidate["artifact_binding"]
                        ["all_downstream_artifacts_bound"])
        self.assertTrue(candidate["cutting_pattern"]["pieces"])
        self.assertTrue(candidate["sewing_plan"]["sewing_order"])
        self.assertFalse(candidate["sewing_plan"]["corpus_used"])
        self.assertFalse(candidate["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])

    def test_bad_json_is_typed_unknown(self):
        called = _stdio(_rpc("tools/call", 3, {
            "name": TOOL_NAME, "arguments": {"json_text": "{"},
        }))[0]
        result = json.loads(called["result"]["content"][0]["text"])
        self.assertEqual(result["verdict"], "UNKNOWN_BAD_ARGUMENTS")


if __name__ == "__main__":
    unittest.main()
