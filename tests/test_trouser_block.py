#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import json
import unittest

from photoloset import trouser_block


def structure():
    return {
        "schema": "garment.structure.v1",
        "nodes": [
            {"node_id": "leg-left", "kind": "TUBE",
             "dimensions": {"length_cm": 102.0, "circumference_cm": 56.0},
             "attributes": {"side": "left", "garment_unit": "lower"}},
            {"node_id": "leg-right", "kind": "TUBE",
             "dimensions": {"length_cm": 102.0, "circumference_cm": 56.0},
             "attributes": {"side": "right", "garment_unit": "lower"}},
            {"node_id": "crotch-gusset", "kind": "GUSSET",
             "dimensions": {"length_cm": 18.0, "width_cm": 8.0},
             "attributes": {"garment_unit": "lower"}},
        ],
        "operations": [],
    }


class TrouserBlockTests(unittest.TestCase):
    def test_two_tubes_and_gusset_expand_to_connected_addressable_pattern(self):
        source = structure()
        before = copy.deepcopy(source)
        result = trouser_block.find_and_draft(source)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["state"], "PROPOSED")
        self.assertEqual(len(result["pieces"]), 5)
        self.assertEqual(len(result["seams"]), 10)
        self.assertEqual(source, before)
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        self.assertFalse(result["authority"]["observed"])
        self.assertTrue(all(row["geometrically_equal"]
                            for row in result["seam_balance"]))
        self.assertEqual(
            {piece["piece_id"] for piece in result["pieces"]},
            {"leg-left:front", "leg-left:back", "leg-right:front",
             "leg-right:back", "crotch-gusset"},
        )

        adjacency = {piece["piece_id"]: set()
                     for piece in result["pieces"]}
        for seam in result["seams"]:
            a, b = seam["a"]["piece_id"], seam["b"]["piece_id"]
            adjacency[a].add(b)
            adjacency[b].add(a)
        seen = set()
        frontier = [next(iter(adjacency))]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(adjacency[current] - seen)
        self.assertEqual(seen, set(adjacency))
        json.dumps(result, allow_nan=False)

    def test_front_and_back_topology_is_not_collapsed_to_one_tube(self):
        result = trouser_block.find_and_draft(structure())
        roles = {piece["role"] for piece in result["pieces"]}
        self.assertIn("left_front_leg_panel", roles)
        self.assertIn("left_back_leg_panel", roles)
        self.assertIn("right_front_leg_panel", roles)
        self.assertIn("right_back_leg_panel", roles)
        seam_roles = {seam["construction_role"] for seam in result["seams"]}
        self.assertEqual(
            seam_roles,
            {"LEG_OUTSEAM", "LEG_INSEAM", "CENTRE_FRONT_RISE",
             "CENTRE_BACK_RISE", "CROTCH_GUSSET"},
        )

    def test_digest_is_deterministic_and_changes_with_geometry(self):
        first = trouser_block.find_and_draft(structure())
        second = trouser_block.find_and_draft(structure())
        changed = structure()
        changed["nodes"][0]["dimensions"]["length_cm"] = 98.0
        third = trouser_block.find_and_draft(changed)
        self.assertEqual(first["digest"], second["digest"])
        self.assertNotEqual(first["digest"], third["digest"])

    def test_missing_side_or_shared_unit_refuses(self):
        missing_side = structure()
        del missing_side["nodes"][0]["attributes"]["side"]
        self.assertEqual(
            trouser_block.find_and_draft(missing_side)["verdict"],
            "UNKNOWN_TROUSER_TOPOLOGY_CARDINALITY",
        )
        wrong_unit = structure()
        wrong_unit["nodes"][1]["attributes"]["garment_unit"] = "other"
        self.assertEqual(
            trouser_block.find_and_draft(wrong_unit)["verdict"],
            "UNKNOWN_TROUSER_GARMENT_UNIT",
        )

    def test_one_tube_or_missing_gusset_never_claims_trousers(self):
        one = structure()
        one["nodes"] = one["nodes"][:1]
        result = trouser_block.find_and_draft(one)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_TROUSER_TOPOLOGY_CARDINALITY")
        self.assertNotIn("pieces", result)

    def test_gusset_that_consumes_the_inseam_refuses(self):
        impossible = structure()
        impossible["nodes"][2]["dimensions"] = {
            "length_cm": 160.0, "width_cm": 80.0}
        result = trouser_block.find_and_draft(impossible)
        self.assertEqual(result["verdict"],
                         "UNKNOWN_TROUSER_GUSSET_DOES_NOT_FIT")


if __name__ == "__main__":
    unittest.main()
