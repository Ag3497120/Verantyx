# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest

from photoloset import mcp


TOOL = "garment_body_image_separation_precomputed"
SCHEMA = "garment.body-image-separation.precomputed-adapter.request.v1"


def _request() -> dict:
    return {
        "schema": SCHEMA,
        "provider_id": "apple-vision-audit",
        "provider_kind": "MACOS_VISION_PRECOMPUTED",
        "source": {
            "image_digest": "sha256:mcp-precomputed-fixture",
            "width": 800,
            "height": 1200,
            "orientation": "UP",
        },
        "masks": [{
            "mask_id": "front-garment",
            "class": "GARMENT",
            "outline": [[0.2, 0.1], [0.8, 0.1], [0.75, 0.9], [0.25, 0.9]],
        }],
        "pose": {
            "coordinate_space": "NORMALIZED",
            "origin": "TOP_LEFT",
            "keypoints": {"nose": {"x": 0.5, "y": 0.1, "confidence": 0.9}},
        },
        "selection_mode": "AUTO_PROPOSED",
    }


class PrecomputedBodyImageSeparationMCPTests(unittest.TestCase):
    def _call(self, payload: dict) -> dict:
        response = mcp.handle({
            "method": "tools/call",
            "params": {"name": TOOL, "arguments": {
                "json_text": json.dumps(payload),
            }},
        })
        return json.loads(response["content"][0]["text"])

    def test_tool_is_listed_and_capability_is_offline(self) -> None:
        tools = {row["name"] for row in mcp.handle({
            "method": "tools/list"})["tools"]}
        self.assertIn(TOOL, tools)
        result = self._call({"action": "capability"})
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertFalse(result["network_used"])
        self.assertFalse(result["model_download_attempted"])
        self.assertEqual(result["rear_state"], "UNKNOWN_UNOBSERVED")

    def test_precomputed_run_reaches_existing_typed_boundary(self) -> None:
        result = self._call({"action": "run", **_request()})
        self.assertEqual(
            result["verdict"],
            "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES")
        self.assertEqual(result["rear_state"], "UNKNOWN_UNOBSERVED")
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        self.assertEqual(result["fact_promotions"], [])
        self.assertEqual(
            result["separation"]["selection"]["status"],
            "AUTO_PROPOSED_SELECTED")

    def test_build_preserves_unknown_channels_without_fabrication(self) -> None:
        result = self._call({"action": "build", **_request()})
        self.assertEqual(
            result["verdict"], "PROPOSED_PRECOMPUTED_PROVIDER_OUTPUT")
        availability = result["channel_availability"]
        self.assertTrue(availability["GARMENT"]["available"])
        self.assertFalse(availability["BODY"]["available"])
        self.assertFalse(availability["HAIR"]["available"])
        self.assertFalse(availability["BACKGROUND"]["available"])

    def test_bad_action_is_typed_and_bounded(self) -> None:
        result = self._call({"action": "download"})
        self.assertEqual(result["verdict"], "UNKNOWN_BAD_ARGUMENTS")
        self.assertEqual(result["rear_state"], "UNKNOWN_UNOBSERVED")
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["fact_promotions"], [])


if __name__ == "__main__":
    unittest.main()
