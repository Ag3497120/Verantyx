#!/usr/bin/env python3
import copy
import unittest

from photoloset import front_geometry_cues
from photoloset import garment_structure


class FrontGeometryInternalLineTests(unittest.TestCase):
    def outline(self):
        return {
            "outline": [[40, 0], [60, 0], [65, 40], [95, 100],
                        [5, 100], [35, 40]],
            "provenance": {"kind": "OBSERVED"},
        }

    def assert_proposed_only(self, result):
        for cue in result["typed_cues"].values():
            if isinstance(cue, dict) and "state" in cue:
                self.assertEqual(cue["state"], "PROPOSED")
        self.assertFalse(result["claims"]["internal_line_semantics_observed"])
        for candidate in result["hypotheses"]:
            self.assertEqual(candidate["state"], "PROPOSED")
            self.assertEqual(
                garment_structure.build(candidate["structure"])["verdict"],
                "ANSWER",
            )

    def test_open_waist_line_proposes_separates_without_observing_a_seam(self):
        source = self.outline()
        source["internal_lines"] = [[[18, 50], [82, 50]]]

        result = front_geometry_cues.hypothesize(source, source_id="waist-line")

        self.assertEqual(result["metrics"]["internal_line_count"], 1.0)
        self.assertEqual(
            result["metrics"]["waist_like_internal_line_count"], 1.0)
        self.assertEqual(result["typed_cues"]["composition"]["value"],
                         "separates")
        self.assertEqual(result["typed_cues"]["composition"]["state"],
                         "PROPOSED")
        self.assert_proposed_only(result)

    def test_non_waist_transverse_line_proposes_overlay_structure(self):
        source = self.outline()
        source["internal_lines"] = [[[16, 82], [84, 82]]]

        result = front_geometry_cues.hypothesize(source, source_id="hem-line")

        self.assertEqual(
            result["metrics"]["transverse_internal_line_count"], 1.0)
        self.assertEqual(
            result["metrics"]["waist_like_internal_line_count"], 0.0)
        self.assertIn("overlay", result["typed_cues"]["details"]["value"])
        for candidate in result["hypotheses"]:
            self.assertIn(
                "LAYER",
                {operation["kind"]
                 for operation in candidate["structure"]["operations"]},
            )
        self.assert_proposed_only(result)

    def test_open_wave_proposes_ruffle_and_gather(self):
        source = self.outline()
        source["internal_lines"] = [[
            [16, 80], [26, 74], [36, 82], [46, 74],
            [56, 82], [66, 74], [84, 80],
        ]]

        result = front_geometry_cues.hypothesize(source, source_id="wave-line")

        self.assertEqual(
            result["metrics"]["oscillating_internal_line_count"], 1.0)
        self.assertIn("ruffle", result["typed_cues"]["details"]["value"])
        for candidate in result["hypotheses"]:
            self.assertIn(
                "GATHER",
                {operation["kind"]
                 for operation in candidate["structure"]["operations"]},
            )
        self.assert_proposed_only(result)

    def test_lines_join_digest_and_metrics_are_scale_invariant(self):
        source = self.outline()
        source["internal_boundaries"] = [[[20, 44], [80, 44]]]
        source["internal_lines"] = [[[18, 78], [82, 78]]]
        first = front_geometry_cues.hypothesize(source)

        without_line = self.outline()
        without_line["internal_boundaries"] = copy.deepcopy(
            source["internal_boundaries"])
        boundary_only = front_geometry_cues.hypothesize(without_line)
        self.assertNotEqual(first["front_geometry_digest"],
                            boundary_only["front_geometry_digest"])
        self.assertEqual(first["metrics"]["internal_boundary_count"], 1.0)

        scaled = copy.deepcopy(source)
        scaled["outline"] = [[x * 4, y * 4] for x, y in scaled["outline"]]
        for key in ("internal_boundaries", "internal_lines"):
            scaled[key] = [
                [[x * 4, y * 4] for x, y in geometry]
                for geometry in scaled[key]
            ]
        other = front_geometry_cues.hypothesize(scaled)
        self.assertEqual(first["metrics"], other["metrics"])

    def test_invalid_lines_are_ignored_and_do_not_change_identity(self):
        baseline = front_geometry_cues.hypothesize(self.outline())
        source = self.outline()
        source["internal_lines"] = [[], [[1, 2]], [[False, 2], [3, 4]],
                                    "not-a-line"]

        result = front_geometry_cues.hypothesize(source)

        self.assertEqual(result["front_geometry_digest"],
                         baseline["front_geometry_digest"])
        self.assertEqual(result["metrics"]["internal_line_count"], 0.0)


if __name__ == "__main__":
    unittest.main()
