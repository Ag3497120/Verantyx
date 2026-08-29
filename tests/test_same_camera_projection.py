#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import unittest

from photoloset.same_camera_projection import prepare_same_camera_projection


def _request():
    return {
        "schema": "garment.same-camera-projection.request.v1",
        "camera_digest": "camera:front:locked",
        "base_avatar": {
            "avatar_id": "preview-balanced-170",
            "geometry_digest": "avatar:balanced:170",
        },
        "target": {
            "target_digest": "target-a",
            "state": "HUMAN_CONFIRMED_TARGET",
            "human_edit_digest": "human-edit-a",
            "width_px": 100,
            "height_px": 100,
            "outline": [[10, 10], [90, 10], [90, 90], [10, 90]],
        },
        "candidate": {
            "candidate_id": "candidate-a",
            "vertices": [
                [-1, 1, 0], [1, 1, 0], [1, -1, 0], [-1, -1, 0],
            ],
            "faces": [[0, 1, 2], [0, 2, 3]],
        },
        "raster_size": 48,
    }


class SameCameraProjectionTests(unittest.TestCase):
    def test_exact_front_shape_is_bound_without_design_adoption(self):
        result = prepare_same_camera_projection(_request())

        self.assertEqual(result["verdict"],
                         "PROPOSED_SAME_CAMERA_COMPARISON")
        self.assertEqual(result["state"], "PROPOSED")
        self.assertEqual(result["evaluation"]["reference_authority"],
                         "HUMAN_CONFIRMED_TARGET")
        self.assertEqual(result["camera_digest"], "camera:front:locked")
        self.assertTrue(result["base_avatar"]["locked_for_loop"])
        self.assertEqual(result["alignment"]["authority"],
                         "PROPOSED_PREVIEW")
        self.assertTrue(result["alignment"]
                        ["does_not_measure_body_or_depth"])
        self.assertEqual(result["evaluation"]["convergence"]["status"],
                         "CONVERGED")
        self.assertTrue(result["evaluation"]["convergence"]
                        ["requires_human_approval"])
        self.assertEqual(result["design_decision_owner"], "HUMAN")
        self.assertEqual(result["fact_promotions"], [])
        self.assertFalse(result["manufacturing_ready"])

    def test_different_shape_proposes_bounded_refinement(self):
        request = _request()
        request["candidate"]["vertices"] = [
            [0, 1, 0], [1, -1, 0], [-1, -1, 0],
        ]
        request["candidate"]["faces"] = [[0, 1, 2]]

        result = prepare_same_camera_projection(request)

        self.assertEqual(result["verdict"],
                         "PROPOSED_SAME_CAMERA_COMPARISON")
        evaluation = result["evaluation"]
        self.assertEqual(evaluation["convergence"]["status"], "CONTINUE")
        self.assertGreater(len(evaluation["proposals"]), 0)
        self.assertTrue(all(row["state"] == "PROPOSED"
                            for row in evaluation["proposals"]))
        self.assertTrue(evaluation["no_aggregate_score"])

    def test_avatar_camera_and_mesh_are_required(self):
        for key, expected in (
            ("camera_digest", "UNKNOWN_SAME_CAMERA_PROJECTION_CAMERA_REQUIRED"),
            ("base_avatar", "UNKNOWN_SAME_CAMERA_PROJECTION_AVATAR_REQUIRED"),
        ):
            request = _request()
            request.pop(key)
            self.assertEqual(
                prepare_same_camera_projection(request)["verdict"], expected)

        request = _request()
        request["candidate"] = copy.deepcopy(request["candidate"])
        request["candidate"]["faces"] = []
        self.assertEqual(
            prepare_same_camera_projection(request)["verdict"],
            "UNKNOWN_SAME_CAMERA_PROJECTION_INPUT")

    def test_unconfirmed_cad_target_cannot_enter_comparison(self):
        request = _request()
        request["target"]["state"] = "PROPOSED"
        request["target"].pop("human_edit_digest")
        self.assertEqual(
            prepare_same_camera_projection(request)["verdict"],
            "UNKNOWN_SAME_CAMERA_TARGET_CONFIRMATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
