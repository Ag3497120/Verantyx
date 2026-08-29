#!/usr/bin/env python3
import unittest

from photoloset import garment_engineering_review
from photoloset.parts_ir_topology import apply_parts_ir_topology
from photoloset.structure_to_pattern import compile_structure
from tests.test_parts_ir_topology import completion, dress_parts


class StructureToPatternBodiceAttachmentTests(unittest.TestCase):
    def test_dress_waist_collar_and_ruffle_expand_to_real_sewable_edges(self):
        topology = apply_parts_ir_topology(completion(dress_parts()))
        self.assertEqual(topology["verdict"], "PROPOSED")
        for candidate in topology["candidates"]:
            result = compile_structure(
                candidate, candidate_id=candidate["candidate_id"])
            self.assertEqual(result["verdict"], "ANSWER")
            self.assertTrue(result["pieces"])
            roles = [piece["role"] for piece in result["pieces"]]
            self.assertEqual(roles.count("front_bodice"), 1)
            self.assertEqual(roles.count("back_bodice"), 1)
            self.assertEqual(roles.count("lower_waist_segment"), 4)
            self.assertEqual(roles.count("collar_segment"), 4)
            self.assertEqual(roles.count("gathered_ruffle_segment"), 4)
            self.assertEqual(roles.count("set_in_sleeve_left"), 1)
            self.assertEqual(roles.count("set_in_sleeve_right"), 1)
            self.assertTrue(all(row["geometrically_sewable"]
                                for row in result["seam_checks"]))
            self.assertEqual(
                garment_engineering_review.assembly_connectivity(result)["verdict"],
                "ANSWER")
            kinds = {row["kind"] for row in result["candidate_specific_expansions"]}
            self.assertEqual(kinds, {
                "BODICE_SET_IN_SLEEVE_BRIDGE",
                "BODICE_WAIST_ATTACHMENT",
                "BODICE_NECK_ATTACHMENT",
                "SEGMENTED_GATHER_ATTACHMENT",
            })
            collar = next(row for row in result["candidate_specific_expansions"]
                          if row["kind"] == "BODICE_NECK_ATTACHMENT")
            self.assertTrue(collar["adjustments"][0]["requires_human_approval"])
            self.assertFalse(result["manufacturing_ready"])


if __name__ == "__main__":
    unittest.main()
