# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest

from photoloset import mcp


class TargetSculptClearanceMCPTests(unittest.TestCase):
    def test_tool_is_registered_and_bounded(self) -> None:
        self.assertIn("garment_target_sculpt_clearance_simulate", mcp.TOOLS)
        request = {
            "schema": "garment.target-sculpt-clearance.request.v1",
            "sculpt_surface": {
                "vertices_cm": [[-2, -2, 0], [2, -2, 0], [0, 2, 0]],
                "faces": [[0, 1, 2]],
            },
            "avatar_measurements_cm": {
                "height": 170, "chest_bust": 92, "waist": 76, "hip": 98,
            },
            "cloth_thickness_mm": 1,
            "removed_face_indices": [],
        }
        result = json.loads(mcp.TOOLS[
            "garment_target_sculpt_clearance_simulate"](json.dumps(request)))
        self.assertEqual(result["verdict"], "PROPOSED_GEOMETRIC_CLEARANCE")
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["fact_promotions"], [])


if __name__ == "__main__":
    unittest.main()
