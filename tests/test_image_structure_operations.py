#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import json
import unittest

from photoloset import front_geometry_cues
from photoloset import front_region_structure_cues
from photoloset import garment_structure
from photoloset import mcp
from photoloset import structure_to_pattern


class ImageStructureOperationTests(unittest.TestCase):
    def source(self):
        return {
            "outline": [[0, 0], [100, 0], [100, 200], [0, 200]],
            "internal_boundaries": [
                [[40, 40], [60, 40], [60, 65], [40, 65]],
            ],
            "provenance": {"kind": "OBSERVED", "source": "front photo"},
        }

    @staticmethod
    def _operations(candidate):
        graph = candidate.get("structure", candidate)
        return graph.get("operations", [])

    def test_closed_front_geometry_opens_one_cutout_alternative(self):
        result = front_geometry_cues.hypothesize(
            self.source(), source_id="closed-front")
        self.assertEqual(result["verdict"], "PROPOSED")
        audit = result["image_structure_operation_audit"]
        self.assertEqual(audit["verdict"], "PROPOSED")
        self.assertFalse(audit["semantics_observed"])
        self.assertFalse(result["claims"]["internal_boundary_semantics_observed"])

        with_cutout = [candidate for candidate in result["hypotheses"]
                       if any(operation["kind"] == "CUTOUT"
                              for operation in self._operations(candidate))]
        self.assertEqual(len(with_cutout), 1)
        self.assertEqual(with_cutout[0]["candidate_id"],
                         audit["candidate_selected"])
        self.assertEqual(with_cutout[0]["state"], "PROPOSED")
        self.assertTrue(all(
            not any(operation["kind"] == "CUTOUT"
                    for operation in self._operations(candidate))
            for candidate in result["hypotheses"][:-1]))

        compiled = structure_to_pattern.compile(
            with_cutout[0]["structure"],
            candidate_id=with_cutout[0]["candidate_id"])
        self.assertEqual(compiled["verdict"], "ANSWER")
        inner = [contour for piece in compiled["pieces"]
                 for contour in piece.get("inner_cutouts", [])]
        self.assertEqual(len(inner), 1)
        self.assertEqual(inner[0]["state"], "PROPOSED")
        self.assertEqual(inner[0]["operation_id"],
                         audit["operations"][0]["operation_id"])
        self.assertTrue(inner[0]["source_front_boundary_digest"])

    def test_region_and_mcp_factory_envelopes_keep_candidate_cutout(self):
        source = self.source()
        source["regions"] = [
            {"region_id": "front-clothing", "state": "OBSERVED",
             "outline": [[5, 5], [95, 5], [95, 195], [5, 195]],
             "semantic_label": "clothing"},
        ]
        direct = front_region_structure_cues.hypothesize(
            source, source["regions"], source_id="region-cutout")
        self.assertEqual(direct["image_structure_operation_audit"]["verdict"],
                         "PROPOSED")
        self.assertEqual(sum(
            any(operation["kind"] == "CUTOUT"
                for operation in self._operations(candidate))
            for candidate in direct["hypotheses"]), 1)

        wired = json.loads(mcp.TOOLS["garment_front_outline_hypotheses"](
            json.dumps({"outline": source, "source_id": "region-cutout"})))
        self.assertTrue(wired["factory_envelope"])
        self.assertEqual(wired["image_structure_operation_audit"]["verdict"],
                         "PROPOSED")
        selected = [candidate for candidate in wired["hypotheses"]
                    if any(operation["kind"] == "CUTOUT"
                           for operation in candidate["structure"]["operations"])]
        self.assertEqual(len(selected), 1)
        self.assertEqual(
            garment_structure.build(selected[0]["structure"])["verdict"],
            "ANSWER")

    def test_unprojectable_boundary_does_not_corrupt_any_candidate(self):
        source = self.source()
        # It crosses the upper/lower address used by these alternatives.  The
        # visible line remains evidence, but no invalid inner contour is made.
        source["internal_boundaries"] = [
            [[25, 60], [75, 60], [75, 110], [25, 110]],
        ]
        result = front_geometry_cues.hypothesize(source)
        self.assertEqual(result["image_structure_operation_audit"]["verdict"],
                         "UNKNOWN_NO_VALID_CUTOUT_PROJECTION")
        self.assertFalse(any(
            operation["kind"] == "CUTOUT"
            for candidate in result["hypotheses"]
            for operation in self._operations(candidate)))
        for candidate in result["hypotheses"]:
            self.assertEqual(
                garment_structure.build(candidate["structure"])["verdict"],
                "ANSWER")

    def test_output_is_deterministic_and_cutout_semantics_remain_proposed(self):
        first = front_geometry_cues.hypothesize(
            self.source(), source_id="deterministic-cutout")
        second = front_geometry_cues.hypothesize(
            copy.deepcopy(self.source()), source_id="deterministic-cutout")
        self.assertEqual(first, second)
        selected = next(candidate for candidate in first["hypotheses"]
                        if any(operation["kind"] == "CUTOUT"
                               for operation in self._operations(candidate)))
        operation = next(operation for operation in self._operations(selected)
                         if operation["kind"] == "CUTOUT")
        self.assertEqual(operation["parameters"]["state"], "PROPOSED")
        self.assertIn("not observed", operation["parameters"]["semantics"])
        json.dumps(first, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
