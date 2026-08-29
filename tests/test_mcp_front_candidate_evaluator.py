#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import unittest
from typing import Any

from photoloset import mcp_server
from photoloset.front_structure_hypotheses import (
    CueState,
    FrontStructureCues,
    TypedCue,
    hypothesize_front_structure,
)


def _cue(value: Any) -> TypedCue:
    return TypedCue(
        value,
        CueState.OBSERVED,
        "typed visible-front MCP fixture evidence",
        "a corrected front annotation or another view contradicts it",
    )


def _request() -> dict[str, Any]:
    cues = FrontStructureCues(
        source_id="fixture:mcp-front-evaluator",
        composition=_cue("one_piece"),
        silhouette=_cue("flared"),
        lower_shape=_cue("flare"),
        sleeve_shape=_cue("long"),
        layer_count=_cue(1),
        details=_cue(()),
    )
    return {
        "schema": mcp_server.REQUEST_SCHEMA,
        "candidates": hypothesize_front_structure(cues),
        "front_evidence": cues.as_dict(),
    }


def _call(request: dict[str, Any]) -> dict[str, Any]:
    response = mcp_server.handle({
        "method": "tools/call",
        "params": {
            "name": mcp_server.TOOL_NAME,
            "arguments": {"json_text": json.dumps(request)},
        },
    })
    return json.loads(response["content"][0]["text"])


class MCPFrontCandidateEvaluatorTests(unittest.TestCase):
    maxDiff = None

    def test_tool_is_listed_with_a_typed_json_text_parameter(self):
        listing = mcp_server.handle({"method": "tools/list"})
        tools = {tool["name"]: tool for tool in listing["tools"]}
        self.assertIn(mcp_server.TOOL_NAME, tools)
        schema = tools[mcp_server.TOOL_NAME]["inputSchema"]
        self.assertEqual(schema["properties"]["json_text"]["type"], "string")
        self.assertEqual(schema["properties"]["json_text"]["default"], "")

    def test_mcp_result_is_deterministic_pareto_only_and_review_gated(self):
        request = _request()
        first = _call(request)
        request["candidates"] = list(reversed(request["candidates"]))
        second = _call(request)

        self.assertEqual(first, second)
        self.assertTrue(first["pareto_frontier"])
        self.assertTrue(first["requires_human_approval"])
        self.assertIsNone(first["selected_candidate_id"])
        self.assertEqual(first["rear_authority"], "PROPOSED")
        self.assertEqual(first["material_authority"], "PROPOSED")
        self.assertFalse(first["manufacturing_ready"])
        self.assertFalse(first["manufacturing_certified"])
        self.assertFalse(first["claims"]["single_aggregate_used"])
        self.assertTrue(first["claims"]["pareto_only"])
        for report in first["candidates"]:
            self.assertTrue(report["verdict"].startswith(("REVIEW_", "UNKNOWN_")))
            self.assertFalse(report["manufacturing_ready"])
            self.assertFalse(report["manufacturing_certified"])

    def test_supplied_artifact_must_carry_its_map_candidate_id(self):
        request = _request()
        candidate_id = request["candidates"][0]["candidate_id"]
        request["patterns"] = {
            candidate_id: {
                "candidate_id": "a-different-candidate",
                "verdict": "ANSWER",
                "manufacturing_ready": False,
            },
        }
        result = _call(request)

        self.assertEqual(
            result["verdict"],
            "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_ID_MISMATCH",
        )
        self.assertEqual(result["map_candidate_id"], candidate_id)
        self.assertTrue(result["requires_human_approval"])
        self.assertIsNone(result["selected_candidate_id"])
        self.assertFalse(result["manufacturing_ready"])

    def test_front_only_authority_escalation_is_rejected(self):
        request = _request()
        candidate = copy.deepcopy(request["candidates"][0])
        candidate["candidate_id"] = "authority-leak"
        candidate["back_alternative"]["state"] = "OBSERVED"
        candidate["material_candidate"] = {
            "state": "APPROVED",
            "value": "melton",
        }
        request["candidates"] = [candidate]

        result = _call(request)
        authority = result["candidates"][0]["axes"]["evidence_authority"]
        self.assertEqual(authority["disposition"], "UNSATISFIED")
        self.assertEqual(
            authority["verdict"],
            "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION",
        )
        self.assertEqual(result["rear_authority"], "PROPOSED")
        self.assertEqual(result["material_authority"], "PROPOSED")
        self.assertTrue(result["requires_human_approval"])

    def test_wrong_request_schema_fails_closed(self):
        request = _request()
        request["schema"] = "garment.front-candidate-evaluation.request.v0"
        result = _call(request)

        self.assertEqual(
            result["verdict"],
            "UNKNOWN_FRONT_CANDIDATE_EVALUATION_SCHEMA",
        )
        self.assertEqual(result["pareto_frontier"], [])
        self.assertTrue(result["requires_human_approval"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])


if __name__ == "__main__":
    unittest.main()
