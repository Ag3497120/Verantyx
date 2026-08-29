#!/usr/bin/env python3
import copy
import json
import unittest

from photoloset import front_geometry_cues
from photoloset import garment_structure


class FrontGeometryCueTests(unittest.TestCase):
    def outline(self):
        return {"outline": [[40, 0], [60, 0], [65, 40], [95, 100],
                            [5, 100], [35, 40]],
                "provenance": {"kind": "OBSERVED"}}

    def test_one_outline_opens_diverse_valid_candidates_without_back_claim(self):
        result = front_geometry_cues.hypothesize(self.outline(), source_id="photo-a")
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(len(result["hypotheses"]), 3)
        self.assertFalse(result["claims"]["back_observed"])
        self.assertFalse(result["claims"]["measurements_from_pixels"])
        kinds = []
        for candidate in result["hypotheses"]:
            self.assertEqual(candidate["state"], "PROPOSED")
            self.assertEqual(garment_structure.build(candidate["structure"])["verdict"],
                             "ANSWER")
            kinds.append({node["kind"] for node in candidate["structure"]["nodes"]})
        self.assertTrue(any("GUSSET" in row for row in kinds))
        self.assertTrue(any("OVERLAY" in row for row in kinds))
        self.assertTrue(any("BAND" in row for row in kinds))

    def test_deterministic_and_scale_invariant_metrics(self):
        first = front_geometry_cues.hypothesize(self.outline())
        second = front_geometry_cues.hypothesize(copy.deepcopy(self.outline()))
        self.assertEqual(first, second)
        scaled = copy.deepcopy(self.outline())
        scaled["outline"] = [[x * 3, y * 3] for x, y in scaled["outline"]]
        other = front_geometry_cues.hypothesize(scaled)
        self.assertEqual(first["metrics"], other["metrics"])
        json.dumps(first, allow_nan=False)

    def test_internal_front_lines_propose_separates_layers_and_ruffle(self):
        source = self.outline()
        source["internal_boundaries"] = [
            [[18, 44], [82, 44]],
            [[16, 61], [84, 61]],
            [[18, 72], [28, 67], [38, 73], [48, 67],
             [58, 73], [68, 67], [82, 72]],
        ]
        result = front_geometry_cues.hypothesize(source, source_id="layered-front")
        cues = result["typed_cues"]
        self.assertEqual(cues["composition"]["value"], "separates")
        self.assertEqual(cues["composition"]["state"], "PROPOSED")
        self.assertEqual(cues["layer_count"]["value"], 3)
        self.assertEqual(set(cues["details"]["value"]), {"overlay", "ruffle"})
        self.assertFalse(result["claims"]["internal_boundary_semantics_observed"])
        self.assertEqual(result["metrics"]["oscillating_boundary_count"], 1.0)
        for candidate in result["hypotheses"]:
            operations = {row["kind"] for row in candidate["structure"]["operations"]}
            self.assertIn("LAYER", operations)
            self.assertIn("GATHER", operations)
            self.assertEqual(candidate["unobserved"]["back"], "PROPOSED")
            self.assertEqual(candidate["state"], "PROPOSED")

    def test_internal_geometry_participates_in_digest_and_scale_invariance(self):
        first_source = self.outline()
        first_source["internal_boundaries"] = [[[20, 48], [80, 48]]]
        first = front_geometry_cues.hypothesize(first_source)
        changed_source = self.outline()
        changed_source["internal_boundaries"] = [[[20, 62], [80, 62]]]
        changed = front_geometry_cues.hypothesize(changed_source)
        self.assertNotEqual(first["front_geometry_digest"],
                            changed["front_geometry_digest"])
        scaled_source = copy.deepcopy(first_source)
        scaled_source["outline"] = [[x * 4, y * 4]
                                    for x, y in scaled_source["outline"]]
        scaled_source["internal_boundaries"] = [
            [[x * 4, y * 4] for x, y in boundary]
            for boundary in scaled_source["internal_boundaries"]
        ]
        scaled = front_geometry_cues.hypothesize(scaled_source)
        self.assertEqual(first["metrics"], scaled["metrics"])

    def test_bad_outline_fails_closed(self):
        result = front_geometry_cues.hypothesize({"outline": [[0, 0], [0, 0]]})
        self.assertTrue(result["verdict"].startswith("UNKNOWN_"))
        self.assertNotIn("hypotheses", result)


if __name__ == "__main__":
    unittest.main()
