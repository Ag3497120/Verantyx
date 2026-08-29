#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression for rich front-visible parts crossing every deterministic stage."""
import copy
import unittest

from photoloset.parts_ir_completion import bounded_preview_profile
from photoloset.parts_ir_pipeline import run_parts_ir_pipeline


def _visible(part_id):
    return {
        "state": "PROPOSED",
        "basis": f"front image proposes visible part {part_id}",
        "breaks_when": "another view or construction review contradicts it",
    }


def _part(part_id, kind, dimensions, *, layer=0, placement="front",
          **semantics):
    return {
        "part_id": part_id,
        "kind": kind,
        "layer": layer,
        "placement": placement,
        "visible_basis": _visible(part_id),
        "dimensions": copy.deepcopy(dimensions),
        **semantics,
    }


def _ornament(part_id, kind, dimensions, *, attached_to):
    return _part(
        part_id, kind, dimensions, layer=3,
        placement="visible center-front decoration",
        attached_to=attached_to,
        target_port_id="center-front",
        quantity=1,
        grain_direction="BIAS_45",
        seam_allowance_cm=0.8,
    )


def _candidate(suffix, *, body=92.0, waist=78.0, hem=180.0):
    unit = f"rich-look-{suffix}"
    body_id = f"body-{suffix}"
    skirt_id = f"skirt-{suffix}"
    parts = [
        _part(body_id, "BODY_SHELL", {
            "height_cm": 44.0,
            "circumference_cm": body,
            "bottom_circumference_cm": waist,
            "neck_circumference_cm": 39.0,
        }, garment_unit=unit, quantity=1),
        _part(f"sleeve-{suffix}", "SLEEVE", {
            "length_cm": 58.0,
            "upper_circumference_cm": 35.0,
            "cuff_circumference_cm": 20.0,
        }, placement="both arms", attached_to=body_id,
              garment_unit=unit, side="bilateral", shape="set_in",
              quantity=2),
        _part(skirt_id, "FLARE", {
            "height_cm": 64.0,
            "top_circumference_cm": waist,
            "bottom_circumference_cm": hem,
        }, placement="lower body", attached_to=body_id,
              garment_unit=unit, quantity=1),
        _part(f"overlay-{suffix}", "OVERLAY", {
            "height_cm": 34.0,
            "width_cm": 48.0,
        }, layer=2, placement="front upper layer", attached_to=body_id,
              garment_unit=unit, detail_role="overlay", quantity=1),
        _part(f"frill-{suffix}", "BAND", {
            "length_cm": hem * 1.35,
            "width_cm": 9.0,
        }, layer=2, placement="skirt hem", attached_to=skirt_id,
              garment_unit=unit, detail_role="frill", quantity=1),
        _ornament(f"bow-{suffix}", "BOW", {
            "body_length_cm": 24.0,
            "body_width_cm": 8.0,
            "knot_length_cm": 7.0,
            "knot_width_cm": 3.0,
        }, attached_to=body_id),
        _ornament(f"rosette-{suffix}", "ROSETTE", {
            "strip_length_cm": 48.0,
            "strip_width_cm": 4.0,
            "finished_inner_length_cm": 15.0,
        }, attached_to=body_id),
        _ornament(f"tie-{suffix}", "TIE", {
            "length_cm": 34.0,
            "top_width_cm": 7.0,
            "tip_width_cm": 2.0,
        }, attached_to=body_id),
    ]
    return {
        "candidate_id": f"rich-{suffix}",
        "state": "PROPOSED",
        "parts": parts,
    }


class PartsIRPipelineRichPartPreservationTests(unittest.TestCase):
    maxDiff = None

    def test_sleeves_layer_frill_and_ornaments_survive_3d_and_pattern(self):
        source = {
            "schema": "garment.parts-ir.v1",
            "state": "PROPOSED",
            "candidates": [
                _candidate("a"),
                _candidate("b", body=98.0, waist=84.0, hem=198.0),
            ],
        }
        result = run_parts_ir_pipeline(
            source,
            preview_profile=bounded_preview_profile(),
            radial_segments=8,
        )
        self.assertEqual(result["verdict"], "PROPOSED", result["failures"])

        for source_candidate, row in zip(source["candidates"],
                                         result["candidates"]):
            suffix = source_candidate["candidate_id"].removeprefix("rich-")
            expected_structural = {
                f"body-{suffix}", f"sleeve-{suffix}", f"skirt-{suffix}",
                f"overlay-{suffix}", f"frill-{suffix}",
            }
            expected_ornaments = {
                f"bow-{suffix}", f"rosette-{suffix}", f"tie-{suffix}",
            }

            self.assertEqual(row["execution_status"], "SUCCEEDED")
            self.assertTrue(row["part_preservation"][
                "all_visible_input_parts_preserved"])
            self.assertEqual(
                set(row["part_preservation"]["input_part_ids"]),
                expected_structural | expected_ornaments,
            )

            topology_ids = {
                node["node_id"] for node in row["structure"]["nodes"]
            }
            self.assertTrue(expected_structural <= topology_ids)
            ornament_bundle = row["structure"]["ornament_artifacts"]
            self.assertEqual(
                {item["ornament_id"]
                 for item in ornament_bundle["result_manifest"]},
                expected_ornaments,
            )

            preview = row["preview"]
            preview_structural = {
                part["source_node_id"] for part in preview["parts"]
                if part.get("geometry_role") != "ORNAMENT_CONSTRUCTION_PROXY"
            }
            preview_ornaments = {
                part["source_ornament_id"] for part in preview["parts"]
                if part.get("geometry_role") == "ORNAMENT_CONSTRUCTION_PROXY"
            }
            self.assertTrue(expected_structural <= preview_structural)
            self.assertEqual(preview_ornaments, expected_ornaments)
            self.assertTrue(preview["ornament_artifacts"][
                "all_pattern_pieces_bound_to_preview"])
            self.assertFalse(preview["ornament_artifacts"][
                "formed_geometry_claimed"])

            pattern = row["flat_pattern"]
            pattern_structural = {
                piece["source_node_id"] for piece in pattern["pieces"]
                if piece.get("source_node_id") is not None
            }
            self.assertTrue(expected_structural <= pattern_structural)
            expected_ornament_piece_ids = {
                piece["piece_id"]
                for piece in ornament_bundle["pattern_pieces"]
            }
            self.assertTrue(expected_ornament_piece_ids <= {
                piece["piece_id"] for piece in pattern["pieces"]
            })
            self.assertTrue(expected_ornament_piece_ids <= {
                piece["piece_id"]
                for piece in row["manufacturing_preview"]["pieces"]
            })

            frill_pieces = [
                piece for piece in pattern["pieces"]
                if piece.get("source_node_id") == f"frill-{suffix}"
            ]
            self.assertGreaterEqual(len(frill_pieces), 1)
            self.assertTrue(all(piece["role"] == "gathered_ruffle_segment"
                                for piece in frill_pieces))
            self.assertTrue(any(
                relation["source_node_id"] == f"overlay-{suffix}"
                for relation in preview["layer_relations"]
            ))


if __name__ == "__main__":
    unittest.main()
