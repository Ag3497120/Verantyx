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


TOOL_NAME = "garment_front_image_generation_contract"
REQUEST_SCHEMA = "garment.front-image-generation.request.v1"
REQUIRED_MEASUREMENTS = (
    "chest_circumference_cm",
    "waist_circumference_cm",
    "hip_circumference_cm",
    "body_length_cm",
)
REPO_ROOT = Path(__file__).resolve().parents[1]


def _measurements() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "value_cm": 82.0 + index,
            "authority": "USER_PROVIDED",
            "source": "named target wearer",
        }
        for index, name in enumerate(REQUIRED_MEASUREMENTS)
    }


def _candidate(candidate_id: str, rear: str, material: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "structure": {"nodes": [candidate_id], "operations": []},
        "rear_hypothesis": {
            "state": "PROPOSED",
            "value": rear,
            "basis": "the rear is absent and a rear view can falsify this",
        },
        "material_hypothesis": {
            "state": "PROPOSED",
            "value": material,
            "basis": "appearance only; swatch testing can falsify this",
        },
        "manufacturing_certified": False,
    }


def _artifact(candidate_id: str, kind: str, **payload: Any) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "state": "REVIEW" if kind == "manufacturing" else "PROPOSED",
        "payload": {"fixture": kind, **payload},
        "manufacturing_certified": False,
        **payload,
    }


def _request() -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "source": {"image_id": "sha256:mcp-front-fixture", "view": "front"},
        "vision": {
            "observations": [{
                "claim_id": "front-silhouette",
                "field": "front.silhouette",
                "value": "flared",
                "authority": "OBSERVED",
                "basis": "visible corrected front boundary",
            }],
            "proposals": [{
                "claim_id": "front-layer-count",
                "field": "front.layer_count",
                "value": 2,
                "authority": "PROPOSED",
                "basis": "occlusion may be a layer or an ornament",
            }],
        },
        "wearer_measurements": _measurements(),
        "candidates": [
            _candidate("candidate-a", "center_back_opening", "woven-light"),
            _candidate("candidate-b", "closed_back_side_opening", "knit-medium"),
        ],
        "artifacts": {},
        "approvals": {},
        "rounds": [],
        "max_rounds": 8,
    }


def _approve(request: dict[str, Any], gate: str, candidate_id: str,
             target_digest: str) -> dict[str, Any]:
    request = copy.deepcopy(request)
    request.setdefault("approvals", {})[gate] = {
        "decision": "APPROVE",
        "actor_type": "HUMAN",
        "by": "named pattern reviewer",
        "candidate_id": candidate_id,
        "target_digest": target_digest,
    }
    return request


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


def _call(request: dict[str, Any], request_id: int = 1) -> dict[str, Any]:
    response = _run_stdio(_rpc(
        "tools/call",
        request_id=request_id,
        params={
            "name": TOOL_NAME,
            "arguments": {"json_text": json.dumps(request, allow_nan=False)},
        },
    ))[0]
    return json.loads(response["result"]["content"][0]["text"])


def _assert_no_certification_claim(test: unittest.TestCase, value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {
                "manufacturing_certified",
                "certified_for_manufacture",
                "industrial_certified",
            }:
                test.assertIs(child, False, key)
            _assert_no_certification_claim(test, child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_certification_claim(test, child)


class MCPFrontImageGenerationContractTests(unittest.TestCase):
    maxDiff = None

    def test_stdio_lists_real_json_text_tool(self):
        response = _run_stdio(_rpc("tools/list", request_id=1))[0]
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}

        self.assertIn(TOOL_NAME, tools)
        self.assertEqual(tools[TOOL_NAME]["inputSchema"], {
            "type": "object",
            "properties": {
                "json_text": {"type": "string", "default": ""},
            },
            "required": [],
        })

    def test_stdio_exposes_deterministic_react_and_stable_digests(self):
        request = _request()
        first = _call(request)
        reordered = copy.deepcopy(request)
        reordered["candidates"].reverse()
        reordered["vision"]["observations"].reverse()
        second = _call(reordered, request_id=2)

        self.assertEqual(first, second)
        self.assertEqual(first["decision"], "CONTINUE")
        self.assertEqual(
            first["reason_code"],
            "CONTINUE_CANDIDATE_SPECIFIC_3D_REQUIRED",
        )
        self.assertEqual(first["missing_candidate_ids"], [
            "candidate-a", "candidate-b",
        ])
        self.assertEqual(
            first["react"]["controller"],
            "VERA_DETERMINISTIC_REACT_HARNESS",
        )
        self.assertEqual(first["react"]["llm_role"], "PROPOSE_ONLY")
        self.assertRegex(first["input_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(first["contract_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["rear_authority"], "PROPOSED")
        self.assertEqual(first["material_authority"], "PROPOSED")
        for candidate in first["candidates"]:
            self.assertEqual(candidate["state"], "PROPOSED")
            self.assertEqual(
                candidate["rear_hypothesis"]["state"], "PROPOSED")
            self.assertEqual(
                candidate["material_hypothesis"]["state"], "PROPOSED")
        _assert_no_certification_claim(self, first)

    def test_stdio_keeps_measurement_and_named_human_approval_gates(self):
        request = _request()
        request["wearer_measurements"] = {}
        missing = _call(request)
        self.assertEqual(
            missing["reason_code"], "STOP_WEARER_MEASUREMENTS_REQUIRED")
        self.assertEqual(
            missing["missing_measurements"], list(REQUIRED_MEASUREMENTS))
        self.assertTrue(missing["requires_human_approval"])

        request = _request()
        request["artifacts"] = {
            candidate_id: {
                "preview_3d": _artifact(
                    candidate_id, "preview_3d", mesh_faces=32),
            }
            for candidate_id in ("candidate-a", "candidate-b")
        }
        candidate_gate = _call(request, request_id=2)
        self.assertEqual(
            candidate_gate["reason_code"],
            "STOP_HUMAN_CANDIDATE_APPROVAL_REQUIRED",
        )
        self.assertTrue(candidate_gate["requires_human_approval"])
        self.assertEqual(set(candidate_gate["approval_targets"]), {
            "candidate-a", "candidate-b",
        })

        machine = copy.deepcopy(request)
        machine["approvals"]["candidate"] = {
            "decision": "APPROVE",
            "actor_type": "LLM",
            "by": "proposal model",
            "candidate_id": "candidate-a",
            "target_digest": candidate_gate["approval_targets"]["candidate-a"],
        }
        refused = _call(machine, request_id=3)
        self.assertEqual(
            refused["reason_code"],
            "UNKNOWN_NAMED_HUMAN_APPROVAL_REQUIRED",
        )
        _assert_no_certification_claim(self, refused)

    def test_stdio_carries_candidate_specific_artifacts_to_prototype_gate(self):
        request = _request()
        request["artifacts"] = {
            candidate_id: {
                "preview_3d": _artifact(
                    candidate_id, "preview_3d", mesh_faces=32),
            }
            for candidate_id in ("candidate-a", "candidate-b")
        }

        candidate_gate = _call(request)
        request = _approve(
            request, "candidate", "candidate-a",
            candidate_gate["approval_targets"]["candidate-a"],
        )
        pattern_step = _call(request, request_id=2)
        self.assertEqual(
            pattern_step["reason_code"],
            "CONTINUE_APPROVED_CANDIDATE_PATTERN_REQUIRED",
        )

        request["artifacts"]["candidate-a"]["pattern"] = _artifact(
            "candidate-a", "pattern", piece_count=8)
        pattern_gate = _call(request, request_id=3)
        request = _approve(
            request, "pattern", "candidate-a",
            pattern_gate["approval_target_digest"],
        )
        manufacturing_step = _call(request, request_id=4)
        self.assertEqual(
            manufacturing_step["reason_code"],
            "CONTINUE_MANUFACTURING_REVIEW_REQUIRED",
        )

        request["artifacts"]["candidate-a"]["manufacturing"] = _artifact(
            "candidate-a", "manufacturing", blocking_issues=[])
        manufacturing_gate = _call(request, request_id=5)
        request = _approve(
            request, "manufacturing_review", "candidate-a",
            manufacturing_gate["approval_target_digest"],
        )
        final = _call(request, request_id=6)

        self.assertEqual(
            final["reason_code"],
            "STOP_READY_FOR_PHYSICAL_PROTOTYPE_REVIEW",
        )
        selected = final["artifacts"]["candidate-a"]
        self.assertEqual(set(selected), {
            "preview_3d", "pattern", "manufacturing",
        })
        for kind, artifact in selected.items():
            self.assertEqual(artifact["candidate_id"], "candidate-a")
            self.assertEqual(artifact["kind"], kind)
            self.assertRegex(artifact["binding_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            final["approved_artifact_digests"],
            {kind: selected[kind]["binding_digest"] for kind in selected},
        )
        self.assertFalse(final["manufacturing_ready"])
        self.assertFalse(final["manufacturing_certified"])
        self.assertFalse(
            final["claims"]["manufacturing_certification_created"])
        json.dumps(final, sort_keys=True, allow_nan=False)
        _assert_no_certification_claim(self, final)


if __name__ == "__main__":
    unittest.main()
