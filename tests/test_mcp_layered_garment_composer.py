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


TOOL_NAME = "garment_layered_compose"
REQUEST_SCHEMA = "garment.layered-vision.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
RELATIONS = {"JOIN", "SEPARATE", "LAYER", "CONTACT", "OVERLAP"}


def _boundary(component_id: str) -> dict[str, Any]:
    return {
        "boundary_id": "anchor",
        "length_cm": 20,
        "interface": "layer-anchor",
        "role": "edge",
        "visibility": "FRONT_VISIBLE",
        "state": "PROPOSED",
        "basis": f"typed front boundary for {component_id}",
        "breaks_when": "another view changes the boundary",
    }


def _component(component_id: str, primitive_kind: str,
               dimensions: dict[str, float], layer: int) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "primitive_kind": primitive_kind,
        "dimensions": dimensions,
        "boundaries": [_boundary(component_id)],
        "layer": layer,
        "coverage_zones": ["torso"],
        "semantic_role": "geometric volume",
        "garment_unit": component_id,
    }


def _alternative(relation: str) -> dict[str, Any]:
    return {
        "alternative_id": relation.lower(),
        "relation": relation,
        "source": {"component_id": "outer", "boundary_id": "anchor"},
        "target": {"component_id": "inner", "boundary_id": "anchor"},
        "state": "PROPOSED",
        "contact_zone": "torso",
        "basis": f"{relation} is consistent with the visible front",
        "breaks_when": "a rear view or construction review rejects it",
    }


def _request() -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "source_id": "fixture:mcp-layered-front",
        "front_only": True,
        "components": [
            _component(
                "outer", "OVERLAY", {"height_cm": 35, "width_cm": 30}, 1),
            _component(
                "inner", "BODY_SHELL",
                {"height_cm": 40, "circumference_cm": 80}, 0),
        ],
        "attachment_choices": [{
            "choice_id": "front-compatible-topology",
            "alternatives": [_alternative(relation) for relation in RELATIONS],
        }],
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
    text = response["result"]["content"][0]["text"]
    result = json.loads(text)
    json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return result


def _assert_manufacturing_boundary(test: unittest.TestCase,
                                   value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"manufacturing_ready", "manufacturing_certified"}:
                test.assertIs(child, False, key)
            _assert_manufacturing_boundary(test, child)
    elif isinstance(value, list):
        for child in value:
            _assert_manufacturing_boundary(test, child)


def _assert_class_name_free(test: unittest.TestCase, value: Any) -> None:
    forbidden = {
        "garment_class", "garment_class_name", "garment_name",
        "category_name", "taxonomy_label", "classified_as",
    }
    if isinstance(value, dict):
        test.assertTrue(forbidden.isdisjoint(value), set(value) & forbidden)
        for child in value.values():
            _assert_class_name_free(test, child)
    elif isinstance(value, list):
        for child in value:
            _assert_class_name_free(test, child)


class MCPLayeredGarmentComposerTests(unittest.TestCase):
    maxDiff = None

    def test_stdio_lists_one_json_string_composer_tool(self):
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

    def test_stdio_preserves_every_topology_and_requires_human_choice(self):
        result = _call(_request())

        self.assertEqual(result["verdict"], "REVIEW")
        self.assertEqual(
            result["reason_code"], "REVIEW_JOIN_TOPOLOGY_CHOICE_REQUIRED")
        self.assertEqual(result["candidate_count"], len(RELATIONS))
        self.assertTrue(result["human_choice"]["required"])
        self.assertIsNone(result["human_choice"]["selected_candidate_id"])
        self.assertTrue(result["requires_human_approval"])
        preserved = {
            attachment["relation"]
            for candidate in result["candidates"]
            for attachment in candidate["constraints"]["attachment"]
        }
        self.assertEqual(preserved, RELATIONS)
        self.assertFalse(result["claims"]["garment_name_classification_used"])
        _assert_class_name_free(self, result)
        _assert_manufacturing_boundary(self, result)

    def test_stdio_is_deterministic_and_keeps_hidden_claims_proposed(self):
        request = _request()
        first = _call(request)
        reordered = copy.deepcopy(request)
        reordered["components"].reverse()
        reordered["attachment_choices"][0]["alternatives"].reverse()
        second = _call(reordered, request_id=2)

        self.assertEqual(first, second)
        self.assertRegex(first["source_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(first["digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["unobserved"], {
            "rear": "PROPOSED",
            "material": "PROPOSED",
            "occluded_boundaries": "PROPOSED",
        })
        for candidate in first["candidates"]:
            self.assertEqual(candidate["authority"]["rear"], "PROPOSED")
            self.assertEqual(candidate["authority"]["material"], "PROPOSED")
            self.assertEqual(
                candidate["authority"]["occluded_boundaries"], "PROPOSED")
        _assert_manufacturing_boundary(self, first)

    def test_stdio_refuses_front_only_authority_escalation_as_json(self):
        request = _request()
        request["components"][0]["rear"] = {
            "state": "OBSERVED",
            "basis": "model guess",
            "breaks_when": "a rear image is supplied",
        }
        result = _call(request)

        self.assertEqual(
            result["verdict"], "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION")
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        _assert_class_name_free(self, result)


if __name__ == "__main__":
    unittest.main()
