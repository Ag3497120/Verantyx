#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest

from photoloset import mcp


class SameCameraProjectionMCPTests(unittest.TestCase):
    def test_tool_is_registered_and_schema_refusal_is_typed(self):
        self.assertIn("garment_same_camera_projection_prepare", mcp.TOOLS)
        result = json.loads(
            mcp.TOOLS["garment_same_camera_projection_prepare"](
                json_text=json.dumps({"schema": "wrong"})))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_SAME_CAMERA_PROJECTION_SCHEMA")
        self.assertEqual(result["fact_promotions"], [])


if __name__ == "__main__":
    unittest.main()
