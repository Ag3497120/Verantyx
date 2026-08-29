# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from photoloset.target_sculpt_clearance import solve_target_sculpt_clearance


def _request() -> dict:
    return {
        "schema": "garment.target-sculpt-clearance.request.v1",
        "sculpt_surface": {
            "vertices_cm": [
                [-4, -10, 0], [4, -10, 0], [4, 10, 0], [-4, 10, 0],
                [-4, -10, 2], [4, -10, 2], [4, 10, 2], [-4, 10, 2],
            ],
            "faces": [
                [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
                [0, 4, 5], [0, 5, 1],
            ],
        },
        "avatar_measurements_cm": {
            "height": 170, "chest_bust": 92, "waist": 76, "hip": 98,
        },
        "cloth_thickness_mm": 1.2,
        "removed_face_indices": [],
    }


class TargetSculptClearanceTests(unittest.TestCase):
    def test_projects_penetrating_vertices_and_reports_typed_limits(self) -> None:
        result = solve_target_sculpt_clearance(_request())
        self.assertEqual(result["verdict"], "PROPOSED_GEOMETRIC_CLEARANCE")
        self.assertGreater(result["statistics"]["moved_vertex_count"], 0)
        self.assertGreater(result["statistics"]["collision_face_count"], 0)
        self.assertGreaterEqual(
            result["statistics"]["minimum_clearance_after_mm"], 1.2 - 1e-6)
        self.assertEqual(len(result["face_clearances"]), 6)
        self.assertEqual(
            result["clearance_scale"]["kind"],
            "GEOMETRIC_CLEARANCE_NOT_PRESSURE",
        )
        self.assertEqual(
            {row["face_index"] for row in result["face_clearances"]},
            set(range(6)),
        )
        self.assertTrue(all(
            row["minimum_after_mm"] >= 1.2 - 1e-6
            and row["band"] in {
                "PENETRATION_CORRECTED",
                "THICKNESS_CLEARANCE_CORRECTED",
                "LOW_CLEARANCE",
                "MODERATE_CLEARANCE",
                "HIGH_CLEARANCE",
            }
            for row in result["face_clearances"]
        ))
        self.assertFalse(result["manufacturing_ready"])
        self.assertEqual(result["fact_promotions"], [])

    def test_is_deterministic_and_removed_faces_are_not_collisions(self) -> None:
        request = _request()
        request["removed_face_indices"] = [0, 1]
        first = solve_target_sculpt_clearance(request)
        second = solve_target_sculpt_clearance(request)
        self.assertEqual(first, second)
        self.assertNotIn(0, first["collision_face_indices"])
        self.assertNotIn(1, first["collision_face_indices"])
        self.assertNotIn(
            0, {row["face_index"] for row in first["face_clearances"]})
        self.assertNotIn(
            1, {row["face_index"] for row in first["face_clearances"]})

    def test_front_conformal_shell_keeps_avatar_origin_outside_the_photo_shell(self) -> None:
        request = _request()
        request["sculpt_surface"] = {
            "surface_mode": "FRONT_CONFORMAL_SHELL",
            "vertices_cm": [
                [-4, -10, 15.00], [4, -10, 15.00],
                [4, 10, 15.00], [-4, 10, 15.00],
                [-4, -10, 14.88], [4, -10, 14.88],
                [4, 10, 14.88], [-4, 10, 14.88],
            ],
            "faces": [[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6]],
        }

        result = solve_target_sculpt_clearance(request)

        self.assertEqual("FRONT_CONFORMAL_SHELL", result["surface_mode"])
        self.assertEqual(0, result["statistics"]["moved_vertex_count"])
        self.assertEqual([], result["collision_face_indices"])

    def test_refuses_unbounded_thickness_and_empty_edits(self) -> None:
        request = _request()
        request["cloth_thickness_mm"] = 50
        self.assertEqual(
            solve_target_sculpt_clearance(request)["verdict"],
            "UNKNOWN_TARGET_SCULPT_THICKNESS",
        )
        request = _request()
        request["removed_face_indices"] = list(range(6))
        self.assertEqual(
            solve_target_sculpt_clearance(request)["verdict"],
            "UNKNOWN_TARGET_SCULPT_EMPTY_AFTER_EDIT",
        )


if __name__ == "__main__":
    unittest.main()
