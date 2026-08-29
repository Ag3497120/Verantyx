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


TOOL_NAME = "garment_design_requirement_profile"
REQUEST_SCHEMA = "garment.design-requirement-profile.request.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]


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


class MCPDesignRequirementProfileTests(unittest.TestCase):
    def test_tool_is_listed_and_stdio_applies_explicit_waist_ease(self):
        listed = _stdio(_rpc("tools/list", 1))[0]
        tools = {row["name"]: row for row in listed["result"]["tools"]}
        self.assertIn(TOOL_NAME, tools)
        request = {
            "schema": REQUEST_SCHEMA,
            "requirements": [
                {"kind": "BODY_MEASUREMENT", "target": "waist",
                 "value": .72, "unit": "m"},
                {"kind": "EASE", "target": "waist ease",
                 "value": 40, "unit": "mm"},
            ],
        }
        called = _stdio(_rpc("tools/call", 2, {
            "name": TOOL_NAME,
            "arguments": {"json_text": json.dumps(request)},
        }))[0]
        result = json.loads(called["result"]["content"][0]["text"])
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(result["primitive_overrides"]["FLARE"]
                         ["top_circumference_cm"]["value_cm"], 76)
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["claims"]["front_image_measured"])

    def test_bad_json_is_typed_unknown(self):
        response = _stdio(_rpc("tools/call", 3, {
            "name": TOOL_NAME, "arguments": {"json_text": "{"},
        }))[0]
        result = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(result["verdict"], "UNKNOWN_BAD_ARGUMENTS")


if __name__ == "__main__":
    unittest.main()
