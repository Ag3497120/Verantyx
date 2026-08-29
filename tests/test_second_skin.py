import math
import unittest

from photoloset import second_skin


def mannequin():
    return {
        "verdict": "ANSWER",
        "_levels": [(0.0, 10.0, 7.0), (100.0, 10.0, 7.0)],
    }


def radius_at(_man, _y, theta):
    a, b = 10.0, 7.0
    return a * b / math.sqrt((b * math.cos(theta)) ** 2
                             + (a * math.sin(theta)) ** 2)


def rectangle_view(frame_id, angle, half_width):
    return {
        "frame_id": frame_id,
        "azimuth_deg": angle,
        "cm_per_unit": 1.0,
        "primitives": [{
            "type": "rectangle", "center": (0.0, 50.0),
            "width": half_width * 2.0, "height": 100.0,
        }],
    }


class SecondSkinTests(unittest.TestCase):
    def test_dress_has_worn_and_stretched_rest_geometry(self):
        result = second_skin.build(
            mannequin(), "torso_dress", radius_at=radius_at,
            y_bottom=0.0, y_top=100.0, segments=8, height_steps=2,
            ease_field={0.0: 0.0, 100.0: 2.0},
            stretch_field=lambda y: 0.20 if y >= 50.0 else 0.0)
        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual("dress", result["garment"])
        self.assertEqual(24, result["vertices"])
        self.assertEqual(16, result["faces_count"])
        self.assertAlmostEqual(1.0, result["rings"][0]["rest_scale"])
        self.assertAlmostEqual(1.0 / 1.2, result["rings"][-1]["rest_scale"])
        self.assertGreater(math.hypot(result["verts"][-8][0],
                                     result["verts"][-8][2]),
                           math.hypot(result["rest_verts"][-8][0],
                                     result["rest_verts"][-8][2]))
        self.assertEqual("GENERATED", result["provenance"]["output"])

    def test_trousers_are_two_closed_and_separate_shells(self):
        result = second_skin.build(
            mannequin(), "leggings", radius_at=radius_at,
            segments=8, height_steps=2, ease=0.5, stretch=0.1)
        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual("trousers", result["garment"])
        self.assertEqual(2, result["shell_count"])
        self.assertEqual(["left_leg", "right_leg"], result["components"])
        per_shell = 3 * 8
        left_x = sum(v[0] for v in result["verts"][:per_shell]) / per_shell
        right_x = sum(v[0] for v in result["verts"][per_shell:]) / per_shell
        self.assertLess(left_x, 0.0)
        self.assertGreater(right_x, 0.0)
        self.assertEqual(32, result["faces_count"])
        for face in result["faces"]:
            self.assertTrue(max(face) < per_shell or min(face) >= per_shell)

    def test_single_view_refuses_to_invent_depth(self):
        result = second_skin.build(
            mannequin(), "dress", radius_at=radius_at,
            calibrated_views=[rectangle_view("front", 0.0, 12.0)])
        self.assertEqual(second_skin.SINGLE_VIEW, result["verdict"])
        self.assertEqual(1, result["constrained_axes"])
        self.assertEqual(1, result["unknown_axes"])
        self.assertNotIn("verts", result)
        self.assertEqual("OBSERVED",
                         result["provenance"]["views"][0]["kind"])

    def test_orthogonal_views_solve_both_axes_and_improve_constraint(self):
        result = second_skin.build(
            mannequin(), "skirt", radius_at=radius_at,
            y_bottom=0.0, y_top=100.0, segments=12, height_steps=4,
            calibrated_views=[rectangle_view("front", 0.0, 12.0),
                              rectangle_view("side", 90.0, 9.0)])
        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual(2, result["constraints"]["independent_axes"])
        self.assertEqual(5, result["constraints"]["constrained_ring_count"])
        self.assertTrue(result["constraints"]["improved"])
        self.assertLessEqual(result["constraints"]["projection_rmse_after_cm"],
                             result["constraints"]["projection_rmse_before_cm"])
        for ring in result["rings"]:
            self.assertAlmostEqual(12.0, ring["worn_width_radius_cm"])
            self.assertAlmostEqual(9.0, ring["worn_depth_radius_cm"])
            self.assertEqual("MULTI_VIEW_OBSERVED", ring["constraint"])

    def test_missing_radius_coverage_is_a_typed_refusal(self):
        def partial(_man, y, _theta):
            return 8.0 if y <= 50.0 else None

        result = second_skin.build(mannequin(), radius_at=partial,
                                   y_bottom=0.0, y_top=100.0)
        self.assertEqual(second_skin.NO_GEOMETRY, result["verdict"])
        self.assertIn("how_to_close", result)


if __name__ == "__main__":
    unittest.main()
