# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest

from photoloset import mcp


TOOL = "garment_image_analysis_ensemble"


class GarmentAnalysisEnsembleMCPTests(unittest.TestCase):
    def test_tool_is_listed_as_one_json_text_boundary(self):
        listing = mcp.handle({"method": "tools/list"})
        tools = {row["name"]: row for row in listing["tools"]}
        self.assertIn(TOOL, tools)
        self.assertEqual({
            "type": "object",
            "properties": {"json_text": {"type": "string", "default": ""}},
            "required": [],
        }, tools[TOOL]["inputSchema"])

    def test_tool_returns_bounded_proposals_without_stdio_side_effects(self):
        request = {
            "schema": "garment.image-analysis-ensemble.request.v1",
            "image": {"reference": "fixture://front.png", "front_only": True},
            "vision": {"result": {"garment_instances": [{
                "instance_id": "lower", "garment_name": "skirt",
                "rear_structure": "zipper",
                "state": "OBSERVED",
            }]}},
            "retrieval": {"result": {"matches": [{
                "instance_id": "lower", "label": "trousers", "score": 0.999,
                "state": "OBSERVED",
            }]}},
        }
        response = mcp.handle({
            "method": "tools/call",
            "params": {"name": TOOL, "arguments": {
                "json_text": json.dumps(request),
            }},
        })
        result = json.loads(response["content"][0]["text"])

        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual("CONTESTED", result["contested"][0]["state"])
        self.assertNotIn("OBSERVED", [row["state"] for row in result["claims"]])
        rear = [row for row in result["claims"]
                if row["category"] == "REAR_HIDDEN_STRUCTURE"]
        self.assertEqual("UNOBSERVED_HIDDEN", rear[0]["visibility"])
        self.assertEqual([], result["fact_promotions"])

    def test_bad_json_is_typed(self):
        response = mcp.handle({
            "method": "tools/call",
            "params": {"name": TOOL, "arguments": {"json_text": "{bad"}},
        })
        result = json.loads(response["content"][0]["text"])
        self.assertEqual("UNKNOWN_BAD_ARGUMENTS", result["verdict"])


if __name__ == "__main__":
    unittest.main()
