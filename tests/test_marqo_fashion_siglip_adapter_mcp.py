# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest

from photoloset import mcp


TOOL = "marqo_fashion_siglip_runtime"


class MarqoFashionSigLIPAdapterMCPTests(unittest.TestCase):
    def test_combined_capability_inference_tool_is_listed(self):
        tools = {row["name"]: row for row in
                 mcp.handle({"method": "tools/list"})["tools"]}
        self.assertIn(TOOL, tools)
        self.assertEqual({
            "type": "object",
            "properties": {"json_text": {"type": "string", "default": ""}},
            "required": [],
        }, tools[TOOL]["inputSchema"])

    def test_capability_call_is_offline_and_reports_default_metadata(self):
        response = mcp.handle({
            "method": "tools/call",
            "params": {"name": TOOL, "arguments": {
                "json_text": json.dumps({
                    "action": "capability",
                    "endpoint": "http://127.0.0.1:48123/infer",
                    "allow_http": True,
                }),
            }},
        })
        result = json.loads(response["content"][0]["text"])
        self.assertEqual("ANSWER", result["verdict"])
        self.assertFalse(result["network_probe_performed"])
        self.assertFalse(result["downloads_attempted"])
        self.assertEqual("Marqo/marqo-fashionSigLIP",
                         result["model_metadata"]["model_id"])

    def test_precomputed_run_returns_ensemble_compatible_proposal(self):
        request = {
            "action": "run",
            "mode": "precomputed",
            "precomputed_result": {"matches": [{
                "item_id": "mcp-item", "label": "cropped vest", "score": 0.8,
                "asset": {"uri": "fixture://mcp-item.png"},
                "license": {"spdx": "CC-BY-4.0"},
                "source": {"collection": "fixture"},
                "rights_review": {"state": "REVIEWED"},
            }]},
        }
        response = mcp.handle({
            "method": "tools/call",
            "params": {"name": TOOL, "arguments": {
                "json_text": json.dumps(request),
            }},
        })
        result = json.loads(response["content"][0]["text"])
        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual("PROPOSED_RETRIEVAL", result["matches"][0]["state"])
        self.assertEqual("REVIEWED",
                         result["matches"][0]["rights_review"]["state"])

    def test_no_index_and_bad_action_are_typed(self):
        no_index = mcp.handle({
            "method": "tools/call",
            "params": {"name": TOOL, "arguments": {
                "json_text": json.dumps({"action": "run", "mode": "precomputed"}),
            }},
        })
        self.assertEqual(
            "UNKNOWN_NO_FASHION_RETRIEVAL_INDEX",
            json.loads(no_index["content"][0]["text"])["verdict"],
        )

        bad_action = mcp.handle({
            "method": "tools/call",
            "params": {"name": TOOL, "arguments": {
                "json_text": json.dumps({"action": "download"}),
            }},
        })
        self.assertEqual("UNKNOWN_BAD_ARGUMENTS",
                         json.loads(bad_action["content"][0]["text"])["verdict"])


if __name__ == "__main__":
    unittest.main()
