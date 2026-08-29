# -*- coding: utf-8 -*-
"""MCP boundary tests for the bounded front-reprojection evaluator."""
from __future__ import annotations

import json
import unittest

from photoloset import mcp


def _raster(*, candidate: bool = False, camera: str = "camera-a") -> dict:
    authority = "PROPOSED" if candidate else "OBSERVED"
    return {
        "candidate_id": "candidate-a" if candidate else None,
        "camera_digest": camera,
        "silhouette_mask": [[0, 1, 1, 0], [0, 1, 1, 0]],
        "silhouette_state": authority,
        "typed_part_masks": {
            "body": {
                "mask": [[0, 1, 1, 0], [0, 1, 1, 0]],
                "state": authority,
                "layer": 0,
                "color": "#336699",
            },
        },
    }


class FrontProjectionCompareMCPTests(unittest.TestCase):
    def _call(self, request: dict) -> dict:
        return json.loads(mcp.TOOLS["garment_front_projection_compare"](
            json.dumps(request)))

    def test_tool_is_registered_and_convergence_stays_proposed(self) -> None:
        self.assertIn("garment_front_projection_compare", mcp.TOOLS)
        result = self._call({
            "schema": "garment.front-projection-compare.request.v1",
            "observation": _raster(),
            "candidate_projection": _raster(candidate=True),
        })
        self.assertEqual(
            result["verdict"], "PROPOSED_FRONT_PROJECTION_EVALUATION")
        self.assertEqual(result["convergence"]["status"], "CONVERGED")
        self.assertTrue(result["no_aggregate_score"])
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        self.assertEqual(result["fact_promotions"], [])

    def test_camera_mismatch_is_typed_and_never_approves(self) -> None:
        result = self._call({
            "schema": "garment.front-projection-compare.request.v1",
            "observation": _raster(),
            "candidate_projection": _raster(candidate=True, camera="camera-b"),
        })
        self.assertEqual(
            result["verdict"], "UNKNOWN_FRONT_PROJECTION_CAMERA_MISMATCH")
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["fact_promotions"], [])

    def test_bad_schema_and_missing_rasters_are_typed(self) -> None:
        bad_schema = self._call({"schema": "wrong"})
        self.assertEqual(
            bad_schema["verdict"], "UNKNOWN_FRONT_PROJECTION_COMPARE_SCHEMA")
        missing = self._call({
            "schema": "garment.front-projection-compare.request.v1",
        })
        self.assertEqual(
            missing["verdict"], "UNKNOWN_FRONT_PROJECTION_RASTERS_REQUIRED")

    def test_invalid_config_is_a_typed_numerical_refusal(self) -> None:
        result = self._call({
            "schema": "garment.front-projection-compare.request.v1",
            "observation": _raster(),
            "candidate_projection": _raster(candidate=True),
            "config": {"min_silhouette_iou": 3.0},
        })
        self.assertEqual(result["verdict"], "UNKNOWN_FRONT_PROJECTION_INPUT")
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["fact_promotions"], [])


if __name__ == "__main__":
    unittest.main()
