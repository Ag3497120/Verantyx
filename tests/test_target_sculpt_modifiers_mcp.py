# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from photoloset import mcp
from photoloset.target_sculpt_modifiers import surface_digest


TOOL_NAME = "garment_target_sculpt_modifier"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _request() -> dict:
    vertices = [[0, 0, 0], [2, 0, 0], [0, 2, 0]]
    faces = [[0, 1, 2]]
    revision = 1
    digest = surface_digest(vertices, faces, revision)
    return {
        "schema": "garment.target-sculpt-modifier.request.v1",
        "sculpt_surface": {
            "vertices_cm": vertices,
            "faces": faces,
            "revision": revision,
            "digest": digest,
        },
        "expected_revision": revision,
        "expected_digest": digest,
        "modifier": {
            "kind": "PULL",
            "face_indices": [0],
            "distance_cm": 0.5,
            "direction": "LOCAL_NORMAL",
        },
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
    self_contained = [
        json.loads(line) for line in completed.stdout.splitlines() if line
    ]
    return self_contained


class TargetSculptModifierMCPTests(unittest.TestCase):
    def test_direct_registry_exposes_typed_modifier(self) -> None:
        self.assertIn(TOOL_NAME, mcp.TOOLS)
        result = json.loads(mcp.TOOLS[TOOL_NAME](json.dumps(_request())))
        self.assertEqual(result["verdict"], "PROPOSED_CAD_MODIFIER")
        self.assertEqual(result["mcp_request_schema"],
                         "garment.target-sculpt-modifier.request.v1")
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["fact_promotions"], [])

    def test_stdio_initialize_list_and_call_without_network(self) -> None:
        responses = _stdio(
            _rpc("initialize", 1),
            _rpc("tools/list", 2),
            _rpc("tools/call", 3, {
                "name": TOOL_NAME,
                "arguments": {"json_text": json.dumps(_request())},
            }),
        )
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "photoloset")
        tools = {row["name"] for row in responses[1]["result"]["tools"]}
        self.assertIn(TOOL_NAME, tools)
        result = json.loads(
            responses[2]["result"]["content"][0]["text"])
        self.assertEqual(result["verdict"], "PROPOSED_CAD_MODIFIER")
        self.assertEqual(result["revision"], 2)
        self.assertEqual(result["undo_parent_digest"], _request()["expected_digest"])

    def test_stdio_bad_json_is_typed_unknown(self) -> None:
        response = _stdio(_rpc("tools/call", 1, {
            "name": TOOL_NAME, "arguments": {"json_text": "{"},
        }))[0]
        result = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(result["verdict"], "UNKNOWN_BAD_ARGUMENTS")


if __name__ == "__main__":
    unittest.main()
