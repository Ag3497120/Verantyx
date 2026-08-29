# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from photoloset import mcp


TOOL_NAME = "garment_body_image_separation_propose"
REQUEST_SCHEMA = "garment.body-image-separation.request.v1"
PROPOSED_STATE = "PROPOSED_BODY_GARMENT_SEPARATION"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _request(selection_mode: str = "AUTO_PROPOSED") -> dict:
    return {
        "schema": REQUEST_SCHEMA,
        "source": {
            "image_digest": "sha256:anonymous-mcp-separation-fixture",
            "width": 900,
            "height": 1400,
            "orientation": "FRONT",
        },
        "selection_mode": selection_mode,
    }


def _rpc(method: str, request_id: int, params: dict | None = None) -> dict:
    row = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        row["params"] = params
    return row


def _stdio(*messages: dict) -> list[dict]:
    with tempfile.TemporaryDirectory() as temp_home:
        environment = os.environ.copy()
        environment["PHOTOLOSET_HOME"] = temp_home
        completed = subprocess.run(
            [sys.executable, "-m", "photoloset.mcp"],
            cwd=REPO_ROOT,
            env=environment,
            input="".join(json.dumps(message) + "\n" for message in messages),
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    if completed.returncode:
        raise AssertionError(completed.stderr)
    return [
        json.loads(line) for line in completed.stdout.splitlines() if line
    ]


def _assert_bounded(test: unittest.TestCase, result: dict) -> None:
    test.assertEqual(result["mcp_request_schema"], REQUEST_SCHEMA)
    test.assertEqual(result["rear_state"], "UNKNOWN_UNOBSERVED")
    test.assertFalse(result["manufacturing_ready"])
    test.assertFalse(result["manufacturing_certified"])
    test.assertEqual(result["fact_promotions"], [])


class BodyImageSeparationMCPTests(unittest.TestCase):
    def test_direct_registry_returns_only_bounded_proposals(self) -> None:
        self.assertIn(TOOL_NAME, mcp.TOOLS)
        result = json.loads(mcp.TOOLS[TOOL_NAME](json.dumps(_request())))

        self.assertEqual(
            result["verdict"],
            "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES",
        )
        self.assertEqual(result["state"], PROPOSED_STATE)
        _assert_bounded(self, result)
        self.assertTrue(result["candidates"])
        for candidate in result["candidates"]:
            self.assertEqual(candidate["state"], PROPOSED_STATE)
            self.assertEqual(candidate["authority"], PROPOSED_STATE)
            self.assertEqual(
                candidate["back_generation_conditioning"]["rear_state"],
                "UNKNOWN_UNOBSERVED",
            )
            self.assertFalse(candidate["manufacturing_ready"])
            self.assertFalse(candidate["manufacturing_certified"])
            self.assertEqual(candidate["fact_promotions"], [])
        self.assertFalse(
            result["selection"]["may_open_manufacturing_gate"])

    def test_stdio_initialize_list_and_call_without_network(self) -> None:
        responses = _stdio(
            _rpc("initialize", 1),
            _rpc("tools/list", 2),
            _rpc("tools/call", 3, {
                "name": TOOL_NAME,
                "arguments": {"json_text": json.dumps(_request())},
            }),
        )

        self.assertEqual(
            responses[0]["result"]["serverInfo"]["name"], "photoloset")
        tools = {
            row["name"]: row for row in responses[1]["result"]["tools"]
        }
        self.assertIn(TOOL_NAME, tools)
        self.assertEqual(
            tools[TOOL_NAME]["inputSchema"]["properties"]["json_text"]["type"],
            "string",
        )
        result = json.loads(
            responses[2]["result"]["content"][0]["text"])
        self.assertEqual(
            result["verdict"],
            "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES",
        )
        _assert_bounded(self, result)

    def test_stdio_bad_json_is_typed_stop(self) -> None:
        response = _stdio(_rpc("tools/call", 1, {
            "name": TOOL_NAME,
            "arguments": {"json_text": "{"},
        }))[0]
        result = json.loads(response["result"]["content"][0]["text"])

        self.assertEqual(result["verdict"], "UNKNOWN_BAD_ARGUMENTS")
        self.assertEqual(result["state"], "UNKNOWN")
        _assert_bounded(self, result)

    def test_non_object_json_is_typed_stop(self) -> None:
        result = json.loads(mcp.TOOLS[TOOL_NAME](json.dumps([])))
        self.assertEqual(
            result["verdict"], "UNKNOWN_BODY_IMAGE_SEPARATION_REQUEST")
        self.assertEqual(result["state"], "UNKNOWN")
        _assert_bounded(self, result)

    def test_backend_cannot_cross_mcp_authority_boundary(self) -> None:
        unsafe = {
            "verdict": "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES",
            "state": PROPOSED_STATE,
            "rear_state": "OBSERVED",
            "manufacturing_ready": True,
            "manufacturing_certified": True,
            "fact_promotions": ["rear"],
            "candidates": [{
                "state": PROPOSED_STATE,
                "authority": "OBSERVED",
                "manufacturing_ready": True,
                "manufacturing_certified": True,
                "fact_promotions": ["body_shape"],
                "back_generation_conditioning": {
                    "rear_state": "OBSERVED",
                },
            }],
        }
        with mock.patch(
            "photoloset.body_image_separation.separate_body_image",
            return_value=unsafe,
        ):
            result = json.loads(
                mcp.TOOLS[TOOL_NAME](json.dumps(_request())))

        self.assertEqual(
            result["verdict"],
            "UNKNOWN_BODY_IMAGE_SEPARATION_AUTHORITY_BOUNDARY",
        )
        self.assertEqual(result["state"], "UNKNOWN")
        _assert_bounded(self, result)


if __name__ == "__main__":
    unittest.main()
