#!/usr/bin/env python3
import copy
import json
import unittest

from photoloset import decorative_pattern


class DecorativePatternTests(unittest.TestCase):
    def test_ruffle_is_a_measured_gathered_strip_with_two_boundaries(self):
        result = decorative_pattern.ruffle(
            "skirt-frill", finished_length_cm=40, depth_cm=8,
            gather_ratio=2.0, seam_allowance_cm=1.0, layer=2,
            attach_to={"piece_id": "skirt", "edge": "e3"})
        self.assertEqual(result["verdict"], "ANSWER")
        piece = result["piece"]
        self.assertEqual(piece["outline"], [[0.0, 0.0], [80.0, 0.0],
                                             [80.0, 8.0], [0.0, 8.0]])
        self.assertEqual(piece["attachment_edge"]["cut_length_cm"], 80.0)
        self.assertEqual(piece["attachment_edge"]["finished_length_cm"], 40.0)
        self.assertEqual(piece["transforms"][-1]["kind"], "GATHER")
        self.assertEqual(piece["transforms"][-1]["ratio"], 2.0)
        self.assertEqual(piece["boundary_layers"], {"sew_line": 14, "cut_line": 1})
        self.assertGreater(piece["cut_area_cm2"], piece["sew_area_cm2"])
        self.assertNotEqual(piece["cut_boundary"], piece["sew_boundary"])
        self.assertFalse(result["provenance"]["corpus_used"])
        json.dumps(result, allow_nan=False)

    def test_frill_uses_the_same_geometry_but_keeps_its_declared_kind(self):
        result = decorative_pattern.frill(
            "neck-frill", finished_length_cm=30, depth_cm=4,
            gather_ratio=1.5, seam_allowance_cm=0.7, layer=3)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["piece"]["kind"], "FRILL")
        self.assertEqual(result["piece"]["attachment_edge"]["cut_length_cm"], 45.0)

    def test_tiered_ruffles_preserve_each_explicit_measurement(self):
        tiers = [
            {"finished_length_cm": 50, "depth_cm": 7,
             "gather_ratio": 1.5, "layer": 1},
            {"piece_id": "lower", "finished_length_cm": 70, "depth_cm": 10,
             "gather_ratio": 2.0, "layer": 2},
        ]
        frozen = copy.deepcopy(tiers)
        result = decorative_pattern.tiered_ruffles(
            "tier-set", tiers=tiers, seam_allowance_cm=1.2)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual([row["piece_id"] for row in result["pieces"]],
                         ["tier-set:tier:1", "lower"])
        self.assertEqual([row["attachment_edge"]["cut_length_cm"]
                          for row in result["pieces"]], [75.0, 140.0])
        self.assertEqual([row["tier"] for row in result["tier_order"]], [1, 2])
        self.assertEqual(tiers, frozen)
        self.assertFalse(result["provenance"]["corpus_used"])

    def test_overlay_emits_cut_and_sew_boundaries_and_attachment_edges(self):
        result = decorative_pattern.overlay(
            "cape-overlay", width_cm=24, height_cm=35,
            seam_allowance_cm=1.0, layer=4, attach_edges=["e0", 3])
        self.assertEqual(result["verdict"], "ANSWER")
        piece = result["piece"]
        self.assertEqual(piece["kind"], "OVERLAY")
        self.assertEqual(piece["attach_edges"], ["e0", "e3"])
        self.assertEqual(piece["outline"], piece["sew_boundary"])
        self.assertNotEqual(piece["cut_boundary"], piece["sew_boundary"])
        self.assertFalse(piece["provenance"]["corpus_used"])

    def test_explicit_layer_order_is_complete_and_transitive(self):
        pieces = [
            {"piece_id": "lining", "layer": 0},
            {"piece_id": "shell", "layer": 1},
            {"piece_id": "overlay", "layer": 2},
        ]
        result = decorative_pattern.order_layers(
            pieces, order=["lining", "shell", "overlay"])
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["inner_to_outer"], ["lining", "shell", "overlay"])
        self.assertEqual(result["relations"], [
            {"inner": "lining", "outer": "shell",
             "relation": "inside_before_outside"},
            {"inner": "lining", "outer": "overlay",
             "relation": "inside_before_outside"},
            {"inner": "shell", "outer": "overlay",
             "relation": "inside_before_outside"},
        ])

    def test_layer_order_can_use_unique_explicit_layer_numbers(self):
        result = decorative_pattern.order_layers([
            {"piece_id": "outer", "layer": 7},
            {"piece_id": "inner", "layer": 2},
        ])
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["inner_to_outer"], ["inner", "outer"])

    def test_missing_or_invalid_physical_inputs_return_typed_unknown(self):
        cases = [
            decorative_pattern.ruffle(
                "r", depth_cm=5, gather_ratio=2, seam_allowance_cm=1),
            decorative_pattern.ruffle(
                "r", finished_length_cm=20, depth_cm=5,
                gather_ratio=1, seam_allowance_cm=1),
            decorative_pattern.ruffle(
                "r", finished_length_cm=20, depth_cm=5, gather_ratio=2),
            decorative_pattern.overlay(
                "o", width_cm=10, seam_allowance_cm=1, layer=1),
            decorative_pattern.overlay(
                "o", width_cm=10, height_cm=10,
                seam_allowance_cm=-1, layer=1),
            decorative_pattern.tiered_ruffles(
                "set", tiers=[{"finished_length_cm": 20, "depth_cm": 5}],
                seam_allowance_cm=1),
        ]
        for result in cases:
            with self.subTest(result=result):
                self.assertTrue(result["verdict"].startswith("UNKNOWN_"))
                self.assertIn("how_to_close", result)

    def test_ambiguous_or_incomplete_layer_order_fails_closed(self):
        ambiguous = decorative_pattern.order_layers([
            {"piece_id": "a", "layer": 1}, {"piece_id": "b", "layer": 1}])
        incomplete = decorative_pattern.order_layers([
            {"piece_id": "a"}, {"piece_id": "b"}], order=["a"])
        self.assertEqual(ambiguous["verdict"], "UNKNOWN_LAYER_ORDER_AMBIGUOUS")
        self.assertEqual(incomplete["verdict"], "UNKNOWN_LAYER_ORDER_INCOMPLETE")

    def test_dispatcher_is_typed_and_does_not_require_a_corpus(self):
        result = decorative_pattern.apply({
            "kind": "RUFFLE", "piece_id": "r", "finished_length_cm": 12,
            "depth_cm": 3, "gather_ratio": 2,
            "seam_allowance_cm": 0.8, "layer": 0,
        })
        unknown = decorative_pattern.apply({"kind": "BEADING"})
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertFalse(result["provenance"]["corpus_used"])
        self.assertEqual(unknown["verdict"], "UNKNOWN_DECORATIVE_OPERATION")


if __name__ == "__main__":
    unittest.main()
