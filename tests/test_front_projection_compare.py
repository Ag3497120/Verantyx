#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import unittest

from photoloset.front_projection_compare import (
    ProjectionCompareConfig,
    compare_front_projection,
    decode_mask,
    deterministic_tie_break,
    encode_rle,
    stable_digest,
)


CAMERA = {
    "projection": "orthographic",
    "view": "front",
    "position": [0.0, 1.2, 4.0],
    "target": [0.0, 1.2, 0.0],
    "scale": 1.0,
}

SILHOUETTE = [
    [0, 1, 1, 0],
    [1, 1, 1, 1],
    [1, 1, 1, 1],
    [0, 1, 1, 0],
]

OVERLAY = [
    [0, 0, 0, 0],
    [0, 1, 1, 0],
    [0, 1, 1, 0],
    [0, 0, 0, 0],
]


def _observation():
    return {
        "camera": copy.deepcopy(CAMERA),
        "silhouette_mask": {"mask": copy.deepcopy(SILHOUETTE),
                            "state": "OBSERVED"},
        "typed_part_masks": {
            "body": {"mask": copy.deepcopy(SILHOUETTE),
                     "state": "OBSERVED", "layer": 0},
            "front_overlay": {"mask": copy.deepcopy(OVERLAY),
                              "state": "OBSERVED", "layer": 1},
            "rear_panel": {"mask": copy.deepcopy(SILHOUETTE),
                           "state": "UNKNOWN", "visibility": "REAR",
                           "layer": 2},
        },
        "visible_color_swatches": {
            "body": {"rgb": [180, 40, 40], "state": "OBSERVED"},
            "front_overlay": {"rgb": [20, 40, 160], "state": "OBSERVED"},
            "rear_panel": {"rgb": [0, 0, 0], "state": "UNKNOWN"},
        },
        "occlusion_unknown_mask": [[0, 0, 0, 0] for _ in range(4)],
    }


def _render(candidate_id="candidate-a"):
    return {
        "candidate_id": candidate_id,
        "camera_digest": stable_digest(CAMERA),
        "silhouette_mask": {"mask": copy.deepcopy(SILHOUETTE),
                            "state": "PROPOSED"},
        "typed_part_masks": {
            "body": {"mask": copy.deepcopy(SILHOUETTE),
                     "state": "PROPOSED", "layer": 0},
            "front_overlay": {"mask": copy.deepcopy(OVERLAY),
                              "state": "PROPOSED", "layer": 1},
        },
        "visible_color_swatches": {
            "body": {"rgb": [180, 40, 40], "state": "PROPOSED"},
            "front_overlay": {"rgb": [20, 40, 160], "state": "PROPOSED"},
        },
        "occlusion_unknown_mask": [[0, 0, 0, 0] for _ in range(4)],
    }


class MaskEncodingTests(unittest.TestCase):
    def test_matrix_and_rle_round_trip_without_image_dependencies(self):
        encoded = encode_rle(SILHOUETTE)
        self.assertEqual(encoded["encoding"], "rle")
        self.assertEqual(encoded["size"], [4, 4])
        self.assertEqual(decode_mask(encoded), decode_mask(SILHOUETTE))
        json.dumps(encoded, sort_keys=True, allow_nan=False)

    def test_malformed_rle_is_refused(self):
        with self.assertRaisesRegex(ValueError, "do not fill"):
            decode_mask({"encoding": "rle", "size": [2, 2],
                         "counts": [1, 2], "starts_with": 0})


class FrontProjectionCompareTests(unittest.TestCase):
    def test_exact_same_camera_projection_converges_without_fact_promotion(self):
        first = compare_front_projection(_observation(), _render())
        second = compare_front_projection(_observation(), _render())

        self.assertEqual(first, second)
        self.assertEqual(first["state"], "PROPOSED")
        self.assertEqual(first["convergence"]["status"], "CONVERGED")
        self.assertTrue(first["convergence"]["all_independent_bounds_met"])
        self.assertTrue(first["convergence"]["requires_human_approval"])
        self.assertEqual(first["fact_promotions"], [])
        self.assertTrue(first["no_aggregate_score"])
        self.assertNotIn("score", first)
        self.assertEqual(first["axes"]["silhouette"]["iou"], 1.0)
        self.assertEqual(first["axes"]["parts"]["minimum_iou"], 1.0)
        self.assertEqual(
            first["axes"]["edge_chamfer"]
            ["distance_normalized_by_image_diagonal"], 0.0)
        self.assertEqual(first["axes"]["color_distance"]["maximum_delta_e"], 0.0)
        self.assertEqual(
            first["axes"]["layer_occlusion"]["pixel_mismatch_ratio"], 0.0)
        self.assertEqual(
            first["excluded_from_scoring"]["observation_excluded_part_ids"],
            ["rear_panel"])
        self.assertEqual(first["authority"]["rear"], "PROPOSED")
        self.assertEqual(
            first["evaluation_digest"],
            stable_digest({key: value for key, value in first.items()
                           if key != "evaluation_digest"}))
        json.dumps(first, sort_keys=True, allow_nan=False)

    def test_unknown_pixels_are_excluded_not_penalised_or_inferred(self):
        observed = _observation()
        rendered = _render()
        observed["occlusion_unknown_mask"][0][0] = 1
        rendered["silhouette_mask"]["mask"][0][0] = 1
        rendered["typed_part_masks"]["body"]["mask"][0][0] = 1

        result = compare_front_projection(observed, rendered)

        self.assertEqual(result["axes"]["silhouette"]["iou"], 1.0)
        self.assertEqual(
            result["excluded_from_scoring"]["observation_unknown_pixels"], 1)
        self.assertEqual(
            result["excluded_from_scoring"]["render_known_coverage_of_observed_front"],
            1.0)
        self.assertEqual(result["authority"]["unknown_regions"],
                         "EXCLUDED_NOT_INFERRED")
        self.assertEqual(result["fact_promotions"], [])

    def test_each_axis_remains_separate_and_proposals_are_bounded(self):
        rendered = _render()
        rendered["silhouette_mask"]["mask"] = [
            [0, 0, 0, 0],
            [0, 1, 1, 0],
            [0, 1, 1, 0],
            [0, 0, 0, 0],
        ]
        rendered["typed_part_masks"]["body"]["mask"] = copy.deepcopy(
            rendered["silhouette_mask"]["mask"])
        rendered["typed_part_masks"]["front_overlay"]["layer"] = -1
        rendered["visible_color_swatches"]["body"]["rgb"] = [0, 255, 0]
        config = ProjectionCompareConfig(max_proposals=3)

        result = compare_front_projection(_observation(), rendered, config=config)

        self.assertEqual(result["convergence"]["status"], "CONTINUE")
        self.assertLess(result["axes"]["silhouette"]["iou"], 1.0)
        self.assertLess(result["axes"]["parts"]["per_part"]["body"]["iou"], 1.0)
        self.assertGreater(
            result["axes"]["edge_chamfer"]
            ["distance_normalized_by_image_diagonal"], 0.0)
        self.assertGreater(
            result["axes"]["color_distance"]["per_part"]["body"]["delta_e_76"],
            12.0)
        self.assertTrue(
            result["axes"]["layer_occlusion"]["reversed_observed_relations"])
        self.assertLessEqual(len(result["proposals"]), 3)
        self.assertTrue(all(row["state"] == "PROPOSED"
                            for row in result["proposals"]))
        self.assertTrue(all(row["does_not_assert_observed_geometry"]
                            for row in result["proposals"]))
        self.assertEqual(result["proposal_limit"], 3)
        self.assertFalse(result["convergence"]["all_independent_bounds_met"])

    def test_single_part_shape_error_is_not_relabelled_as_layer_order_error(self):
        observed = _observation()
        rendered = _render()
        observed["typed_part_masks"].pop("front_overlay")
        observed["typed_part_masks"].pop("rear_panel")
        observed["visible_color_swatches"].pop("front_overlay")
        observed["visible_color_swatches"].pop("rear_panel")
        rendered["typed_part_masks"].pop("front_overlay")
        rendered["visible_color_swatches"].pop("front_overlay")
        rendered["silhouette_mask"]["mask"] = copy.deepcopy(OVERLAY)
        rendered["typed_part_masks"]["body"]["mask"] = copy.deepcopy(OVERLAY)

        result = compare_front_projection(observed, rendered)

        layer = result["axes"]["layer_occlusion"]
        self.assertEqual(layer["status"], "NOT_SCORED")
        self.assertEqual(layer["observation_relations"], [])
        self.assertEqual(layer["observation_overlap_pixels"], 0)
        self.assertEqual(layer["evaluated_pixels"], 0)
        self.assertEqual(layer["pixel_mismatch_count"], 0)
        self.assertEqual(layer["pixel_mismatch_ratio"], 0.0)
        self.assertNotIn(
            "REORDER_VISIBLE_FRONT_LAYERS",
            {proposal["operation"] for proposal in result["proposals"]},
        )
        self.assertIn(
            "SILHOUETTE_IOU_BELOW_BOUND",
            result["convergence"]["unmet_bounds"],
        )

    def test_any_regression_rejects_even_when_other_axes_improve(self):
        previous_render = _render("candidate-round-1")
        previous_render["silhouette_mask"]["mask"][1][0] = 0
        previous_render["typed_part_masks"]["body"]["mask"][1][0] = 0
        previous = compare_front_projection(
            _observation(), previous_render, round_index=1)
        self.assertEqual(previous["convergence"]["status"], "CONTINUE")

        current_render = _render("candidate-round-2")
        current_render["visible_color_swatches"]["body"]["rgb"] = [0, 255, 0]
        current = compare_front_projection(
            _observation(), current_render, round_index=2, previous=previous)

        self.assertEqual(current["convergence"]["status"], "REJECT_WORSENED")
        self.assertTrue(current["convergence"]["reject_current_round"])
        regression_paths = {
            row["axis_path"]
            for row in current["comparison_to_previous"]["regressions"]
        }
        improvement_paths = {
            row["axis_path"]
            for row in current["comparison_to_previous"]["improvements"]
        }
        self.assertIn("color_distance/body/delta_e_76", regression_paths)
        self.assertIn("silhouette/iou_loss", improvement_paths)
        self.assertTrue(
            current["comparison_to_previous"]
            ["improvements_never_offset_regressions"])

    def test_resolving_a_missing_visible_swatch_is_an_improvement_not_a_domain_error(self):
        previous_render = _render("candidate-missing-colour")
        previous_render["visible_color_swatches"].pop("body")
        previous = compare_front_projection(
            _observation(), previous_render, round_index=1)
        self.assertEqual(previous["convergence"]["status"], "CONTINUE")
        self.assertEqual(
            previous["axis_losses_for_iteration_only"]
            ["color_distance/body/delta_e_76"], None)

        current = compare_front_projection(
            _observation(), _render("candidate-colour-bound"),
            round_index=2, previous=previous)

        self.assertEqual(current["convergence"]["status"], "CONVERGED")
        self.assertEqual(current["comparison_to_previous"]["regressions"], [])
        improved = {
            row["axis_path"]
            for row in current["comparison_to_previous"]["improvements"]
        }
        self.assertIn("color_distance/body/missing", improved)

    def test_max_round_and_exact_tie_terminate_the_loop_deterministically(self):
        poor = _render("candidate-z")
        poor["silhouette_mask"]["mask"] = [[0] * 4 for _ in range(4)]
        poor["typed_part_masks"]["body"]["mask"] = [[0] * 4 for _ in range(4)]
        at_limit = compare_front_projection(
            _observation(), poor, round_index=3,
            config=ProjectionCompareConfig(max_rounds=3))
        self.assertEqual(at_limit["convergence"]["status"],
                         "MAX_ROUNDS_REACHED")
        self.assertFalse(at_limit["convergence"]["may_advance_to_next_round"])

        first = compare_front_projection(_observation(), poor, round_index=1)
        tied = copy.deepcopy(poor)
        tied["candidate_id"] = "candidate-a"
        second = compare_front_projection(
            _observation(), tied, round_index=2, previous=first)
        self.assertEqual(second["convergence"]["status"], "STALLED_TIE")
        self.assertIn(second["convergence"]["tie_winner"],
                      {"CURRENT", "PREVIOUS"})
        self.assertFalse(second["convergence"]["may_advance_to_next_round"])

        ordered = deterministic_tie_break([first, second])
        self.assertEqual(ordered["verdict"],
                         "PROPOSED_DETERMINISTIC_TIE_ORDER")
        expected = min(
            [(first["render_digest"], "candidate-z"),
             (second["render_digest"], "candidate-a")])[1]
        self.assertEqual(ordered["winner_candidate_id"], expected)
        self.assertFalse(ordered["quality_claim"])

    def test_tradeoffs_are_not_forced_through_tie_break(self):
        first = compare_front_projection(_observation(), _render("first"))
        changed = _render("second")
        changed["visible_color_swatches"]["body"]["rgb"] = [0, 255, 0]
        second = compare_front_projection(_observation(), changed)

        result = deterministic_tie_break([first, second])
        self.assertEqual(result["verdict"], "UNKNOWN_NOT_AN_EXACT_AXIS_TIE")
        self.assertIn("no aggregate score", result["why"])

    def test_camera_mismatch_and_tampered_previous_are_refused(self):
        rendered = _render()
        rendered["camera_digest"] = "sha256:different-camera"
        mismatch = compare_front_projection(_observation(), rendered)
        self.assertEqual(mismatch["verdict"],
                         "UNKNOWN_FRONT_PROJECTION_CAMERA_MISMATCH")
        self.assertEqual(mismatch["proposals"], [])

        previous = compare_front_projection(_observation(), _render())
        previous["axes"]["silhouette"]["iou"] = 0.0
        tampered = compare_front_projection(
            _observation(), _render("next"), round_index=2, previous=previous)
        self.assertEqual(tampered["verdict"],
                         "UNKNOWN_PREVIOUS_EVALUATION_DIGEST")

        too_late = compare_front_projection(
            _observation(), _render(), round_index=2,
            config=ProjectionCompareConfig(max_rounds=1))
        self.assertEqual(too_late["verdict"],
                         "UNKNOWN_FRONT_PROJECTION_INPUT")
        self.assertIn("exceeds", too_late["why"])

    def test_matrix_and_rle_inputs_produce_the_same_digest(self):
        observed_matrix = _observation()
        rendered_matrix = _render()
        observed_rle = copy.deepcopy(observed_matrix)
        rendered_rle = copy.deepcopy(rendered_matrix)
        observed_rle["silhouette_mask"]["mask"] = encode_rle(SILHOUETTE)
        rendered_rle["silhouette_mask"]["mask"] = encode_rle(SILHOUETTE)
        for document in (observed_rle, rendered_rle):
            for part in document["typed_part_masks"].values():
                part["mask"] = encode_rle(part["mask"])

        matrix_result = compare_front_projection(observed_matrix, rendered_matrix)
        rle_result = compare_front_projection(observed_rle, rendered_rle)

        self.assertEqual(matrix_result["axes"], rle_result["axes"])
        # Input digests intentionally retain the caller's distinct encoding,
        # while deterministic metrics and repeated calls remain identical.
        self.assertNotEqual(matrix_result["observation_digest"],
                            rle_result["observation_digest"])
        self.assertEqual(
            rle_result,
            compare_front_projection(observed_rle, rendered_rle))


if __name__ == "__main__":
    unittest.main()
