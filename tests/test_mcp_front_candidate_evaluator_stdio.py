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

from photoloset.front_structure_hypotheses import (
    CueState,
    FrontStructureCues,
    TypedCue,
    hypothesize_front_structure,
)


TOOL_NAME = "garment_front_candidate_evaluate"
REQUEST_SCHEMA = "garment.front-candidate-evaluation.request.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _cue(value: Any) -> TypedCue:
    return TypedCue(
        value,
        CueState.OBSERVED,
        "typed visible-front stdio fixture evidence",
        "a corrected front annotation or another view contradicts it",
    )


def _request() -> dict[str, Any]:
    cues = FrontStructureCues(
        source_id="fixture:mcp-front-evaluator-stdio",
        composition=_cue("one_piece"),
        silhouette=_cue("flared"),
        lower_shape=_cue("flare"),
        sleeve_shape=_cue("long"),
        layer_count=_cue(1),
        details=_cue(()),
    )
    return {
        "schema": REQUEST_SCHEMA,
        "candidates": hypothesize_front_structure(cues),
        "front_evidence": cues.as_dict(),
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


def _tool_result(response: dict[str, Any]) -> dict[str, Any]:
    return json.loads(response["result"]["content"][0]["text"])


class MCPFrontCandidateEvaluatorStdioTests(unittest.TestCase):
    maxDiff = None

    def test_tools_list_exposes_typed_json_text_contract(self):
        responses = _run_stdio(_rpc("tools/list", request_id=1))
        tools = {
            tool["name"]: tool
            for tool in responses[0]["result"]["tools"]
        }

        self.assertIn(TOOL_NAME, tools)
        schema = tools[TOOL_NAME]["inputSchema"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["properties"]["json_text"], {
            "type": "string",
            "default": "",
        })
        self.assertEqual(schema["required"], [])

    def test_tools_call_preserves_pareto_and_authority_boundaries(self):
        request = _request()
        call = _rpc(
            "tools/call",
            request_id=2,
            params={
                "name": TOOL_NAME,
                "arguments": {"json_text": json.dumps(request)},
            },
        )
        first = _tool_result(_run_stdio(call)[0])

        reversed_request = copy.deepcopy(request)
        reversed_request["candidates"].reverse()
        call["params"]["arguments"]["json_text"] = json.dumps(
            reversed_request)
        second = _tool_result(_run_stdio(call)[0])

        self.assertEqual(first, second)
        self.assertTrue(first["pareto_frontier"])
        self.assertTrue(first["claims"]["pareto_only"])
        self.assertFalse(first["claims"]["single_aggregate_used"])
        self.assertEqual(first["state"], "REVIEW")
        self.assertTrue(first["requires_human_approval"])
        self.assertIsNone(first["selected_candidate_id"])
        self.assertEqual(first["rear_authority"], "PROPOSED")
        self.assertEqual(first["material_authority"], "PROPOSED")
        self.assertFalse(first["manufacturing_ready"])
        self.assertFalse(first["manufacturing_certified"])

    def test_tools_call_rejects_cross_candidate_artifact_binding(self):
        request = _request()
        candidate_id = request["candidates"][0]["candidate_id"]
        request["patterns"] = {
            candidate_id: {
                "candidate_id": "another-candidate",
                "verdict": "ANSWER",
                "manufacturing_ready": True,
            },
        }
        response = _run_stdio(_rpc(
            "tools/call",
            request_id=3,
            params={
                "name": TOOL_NAME,
                "arguments": {"json_text": json.dumps(request)},
            },
        ))[0]
        result = _tool_result(response)

        self.assertEqual(
            result["verdict"],
            "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_ID_MISMATCH",
        )
        self.assertEqual(result["map_candidate_id"], candidate_id)
        self.assertEqual(result["state"], "REVIEW")
        self.assertTrue(result["requires_human_approval"])
        self.assertIsNone(result["selected_candidate_id"])
        self.assertEqual(result["rear_authority"], "PROPOSED")
        self.assertEqual(result["material_authority"], "PROPOSED")
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])


if __name__ == "__main__":
    unittest.main()
