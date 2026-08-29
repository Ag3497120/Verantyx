import copy
import math
import unittest

from photoloset import geometric_overlay, multi_view, outline_topology, second_skin


def mannequin():
    return {"verdict": "ANSWER",
            "_levels": [(0.0, 10.0, 7.0), (100.0, 10.0, 7.0)]}


def radius_at(_man, _height, theta):
    a, b = 10.0, 7.0
    return a*b/math.sqrt((b*math.cos(theta))**2+(a*math.sin(theta))**2)


def view(frame_id, angle, half_width, *, quality=True):
    value = {
        "frame_id": frame_id, "source": frame_id+".png",
        "azimuth_deg": angle, "cm_per_unit": 1.0,
        # Clockwise and repeated closing point exercise topology normalization.
        "outline": [[-half_width, 0], [-half_width, 100],
                    [half_width, 100], [half_width, 0], [-half_width, 0]],
    }
    if quality:
        value.update({"blur_sigma_units": 0.0,
                      "registration_error_units": 0.0})
    return value


def request(views):
    return {"mannequin": mannequin(), "garment": "dress",
            "radius_at": radius_at, "views": views,
            "segments": 8, "height_steps": 2,
            "y_bottom": 0.0, "y_top": 100.0}


class GeometricOverlayTests(unittest.TestCase):
    def test_single_view_keeps_overlay_but_does_not_invent_depth_or_back(self):
        result = geometric_overlay.build(request([view("front", 0, 12)]))
        self.assertEqual(result["verdict"], multi_view.INSUFFICIENT_PARALLAX)
        self.assertEqual(result["second_skin"]["verdict"], "ANSWER")
        self.assertEqual(len(result["overlays"][0]["primitives"]), 2)
        self.assertIsNone(result["constrained_second_skin"])
        self.assertIsNone(result["confirmed_structure"])
        self.assertFalse(result["unknown_promoted_to_fact"])
        self.assertTrue(all(candidate["state"] == "PROPOSED"
                            for candidate in result["structure_candidates"]))
        self.assertTrue(all("back" in " ".join(candidate["unresolved"])
                            for candidate in result["structure_candidates"]))

    def test_multi_view_supports_constrained_skin_but_structure_stays_proposed(self):
        result = geometric_overlay.build(request([
            view("side", 90, 9), view("front", 0, 12)]))
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["view_analysis"]["verdict"], "ANSWER")
        self.assertAlmostEqual(
            result["view_analysis"]["front_back_ratio"]["value"], 0.75)
        self.assertEqual(result["constrained_second_skin"]["verdict"], "ANSWER")
        self.assertEqual(
            result["constrained_second_skin"]["constraints"]["independent_axes"], 2)
        self.assertIsNone(result["confirmed_structure"])
        self.assertTrue(result["confirmation_required"])
        self.assertTrue(all(candidate["verdict"] == "PROPOSED"
                            for candidate in result["structure_candidates"]))
        self.assertTrue(all("seams" in candidate["unresolved"]
                            for candidate in result["structure_candidates"]))

    def test_triangle_overlay_exactly_covers_repaired_outline(self):
        result = geometric_overlay.build(request([view("front", 0, 12)]))
        coverage = result["overlays"][0]["coverage"]
        self.assertAlmostEqual(coverage["polygon_area_units2"],
                               coverage["triangle_area_units2"])
        self.assertEqual(coverage["absolute_error_units2"], 0.0)
        self.assertEqual(len(result["overlays"][0]["boundary_edges"]), 4)

    def test_missing_quality_remains_unknown_and_never_confirms_candidate(self):
        result = geometric_overlay.build(request([
            view("front", 0, 12), view("side", 90, 9, quality=False)]))
        self.assertEqual(result["verdict"], multi_view.FRAME_QUALITY_NOT_RECORDED)
        self.assertIsNone(result["confirmed_structure"])
        self.assertIsNone(result["constrained_second_skin"])
        self.assertTrue(all(candidate["state"] == "PROPOSED"
                            for candidate in result["structure_candidates"]))
        self.assertTrue(all(candidate["support"]["support_state"].startswith("UNKNOWN_")
                            for candidate in result["structure_candidates"]))

    def test_self_intersecting_outline_fails_before_overlay(self):
        bad = view("front", 0, 12)
        bad["outline"] = [[0, 0], [2, 2], [0, 2], [2, 0]]
        result = geometric_overlay.build(request([bad]))
        self.assertEqual(result["verdict"], outline_topology.SELF_INTERSECTS)
        self.assertNotIn("structure_candidates", result)
        self.assertIsNone(result["confirmed_structure"])

    def test_view_order_is_deterministic_and_input_is_immutable(self):
        original = request([view("side", 90, 9), view("front", 0, 12)])
        frozen = copy.deepcopy(original)
        first = geometric_overlay.build(original)
        second = geometric_overlay.build(request([
            view("front", 0, 12), view("side", 90, 9)]))
        self.assertEqual(first["overlays"], second["overlays"])
        self.assertEqual(first["structure_candidates"], second["structure_candidates"])
        self.assertEqual(original, frozen)

    def test_route_trace_uses_existing_generation_stage_names(self):
        result = geometric_overlay.build(request([view("front", 0, 12)]))
        stages = {entry["stage"] for entry in result["stage_trace"]}
        self.assertIn("image evidence", stages)
        self.assertIn("geometric construction", stages)

    def test_capabilities_do_not_claim_confirmation(self):
        report = geometric_overlay.capabilities()
        self.assertFalse(report["features"]["automatic_back_confirmation"])
        self.assertFalse(report["features"]["automatic_seam_confirmation"])
        self.assertTrue(report["features"]["unknown_preservation"])


if __name__ == "__main__":
    unittest.main()
