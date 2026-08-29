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


TOOL_NAME = "garment_front_layered_compose"
REQUEST_SCHEMA = "garment.front-layered-composition.request.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _part(part_id: str, kind: str, dimensions: dict[str, float],
          placement: str) -> dict[str, Any]:
    return {
        "part_id": part_id,
        "kind": kind,
        "dimensions": dimensions,
        "placement": placement,
        "garment_unit": "look",
        "layer": 0,
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"front geometry supports {part_id}",
            "breaks_when": "another view or reviewer rejects it",
        },
    }


def _candidate() -> dict[str, Any]:
    return {
        "candidate_id": "front-stdio-a",
        "state": "PROPOSED",
        "parts": [
            _part(
                "body", "BODY_SHELL",
                {"height_cm": 43.0, "circumference_cm": 90.0},
                "front torso",
            ),
            _part(
                "skirt", "FLARE",
                {
                    "height_cm": 64.0,
                    "top_circumference_cm": 76.0,
                    "bottom_circumference_cm": 172.0,
                },
                "lower body",
            ),
        ],
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


def _request() -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "front_only": True,
        "source": {"image_id": "fixture:front-stdio", "view": "front"},
        "candidates": [_candidate()],
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
    response = _run_stdio(_rpc(
        "tools/call",
        request_id=request_id,
        params={
            "name": TOOL_NAME,
            "arguments": {"json_text": json.dumps(request, allow_nan=False)},
        },
    ))[0]
    return json.loads(response["result"]["content"][0]["text"])


class MCPFrontLayeredCompositionTests(unittest.TestCase):
    maxDiff = None

    def test_stdio_lists_typed_json_text_tool(self):
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

    def test_stdio_emits_source_bound_join_and_separate_alternatives(self):
        first = _call(_request())
        reordered = copy.deepcopy(_request())
        reordered["candidates"][0]["parts"].reverse()
        second = _call(reordered, request_id=2)

        self.assertEqual(first, second)
        self.assertEqual(first["verdict"], "REVIEW")
        self.assertEqual(first["candidate_count"], 2)
        self.assertTrue(first["human_choice"]["required"])
        self.assertIsNone(first["human_choice"]["selected_candidate_id"])
        operation_sets = {
            tuple(operation["kind"] for operation
                  in candidate["structure_graph"]["operations"])
            for candidate in first["candidates"]
        }
        self.assertEqual(operation_sets, {(), ("JOIN",)})
        for candidate in first["candidates"]:
            self.assertEqual(candidate["source_candidate_id"], "front-stdio-a")
            self.assertRegex(
                candidate["source_candidate_digest"], r"^[0-9a-f]{64}$")
            self.assertFalse(candidate["manufacturing_ready"])
            self.assertFalse(candidate["manufacturing_certified"])

    def test_stdio_refuses_front_only_authority_escalation(self):
        request = _request()
        request["candidates"][0]["rear_hypothesis"]["state"] = "OBSERVED"
        result = _call(request)

        self.assertEqual(
            result["verdict"], "UNKNOWN_NO_LAYERED_STRUCTURE_ALTERNATIVE")
        self.assertEqual(
            result["source_candidate_failures"][0]["verdict"],
            "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION",
        )
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])


if __name__ == "__main__":
    unittest.main()
