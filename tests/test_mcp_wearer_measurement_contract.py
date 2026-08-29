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


TOOL_NAME = "garment_wearer_measurement_contract"
REQUEST_SCHEMA = "garment.wearer-measurement.request.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _measurement(value: float, unit: str = "cm") -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "authority": "MEASURED",
        "source": {
            "kind": "TAPE_MEASURE",
            "reference": "stdio-fitting-2026-08-29",
        },
    }


def _request() -> dict[str, Any]:
    values = {
        "bust": 92.0,
        "waist": 72.0,
        "hip": 98.0,
        "body_length": 42.0,
        "inseam": 76.0,
        "shoulder": 39.0,
        "sleeve_length": 58.0,
        "height": 164.0,
    }
    return {
        "schema": REQUEST_SCHEMA,
        "target_wearer": {
            "wearer_id": "stdio-wearer",
            "measurements": {
                name: _measurement(value) for name, value in values.items()
            },
        },
        "fit": {"kind": "CUSTOM", "authority": "REQUESTED"},
        "ease": {
            "chest": {
                "minimum": 4.0,
                "maximum": 7.0,
                "unit": "cm",
                "authority": "REQUESTED",
            },
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
    response = _run_stdio(_rpc(
        "tools/call",
        request_id=request_id,
        params={
            "name": TOOL_NAME,
            "arguments": {"json_text": json.dumps(request, allow_nan=False)},
        },
    ))[0]
    return json.loads(response["result"]["content"][0]["text"])


class MCPWearerMeasurementContractTests(unittest.TestCase):
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

    def test_stdio_normalizes_measurements_without_crossing_readiness(self):
        first = _call(_request())
        metres = copy.deepcopy(_request())
        for record in metres["target_wearer"]["measurements"].values():
            record["value"] /= 100.0
            record["unit"] = "m"
        metres["ease"]["chest"].update({
            "minimum": 0.04,
            "maximum": 0.07,
            "unit": "m",
        })
        second = _call(metres, request_id=2)

        self.assertEqual(first["decision"], "READY")
        self.assertEqual(first["gate_status"], "READY")
        self.assertEqual(
            first["target_wearer"]["measurements"]["chest_bust"]["value_cm"],
            92.0,
        )
        self.assertEqual(first["contract_digest"], second["contract_digest"])
        self.assertFalse(first["manufacturing_ready"])
        self.assertFalse(
            first["claims"]["body_measurements_inferred_from_front_photo"])

    def test_stdio_stops_when_preview_or_photo_replaces_measurement(self):
        request = _request()
        del request["target_wearer"]["measurements"]["hip"]
        missing = _call(request)
        self.assertEqual(
            missing["reason_code"],
            "STOP_TARGET_WEARER_MEASUREMENTS_REQUIRED",
        )
        self.assertEqual(missing["missing_measurements"], ["hip"])
        self.assertFalse(missing["manufacturing_ready"])

        from_photo = _request()
        from_photo["target_wearer"]["measurements"]["waist"]["source"][
            "kind"] = "FRONT_PHOTO"
        refused = _call(from_photo, request_id=2)
        self.assertEqual(
            refused["reason_code"], "UNKNOWN_MEASUREMENT_SOURCE_KIND")
        self.assertFalse(
            refused["claims"]["body_measurements_inferred_from_front_photo"])


if __name__ == "__main__":
    unittest.main()
