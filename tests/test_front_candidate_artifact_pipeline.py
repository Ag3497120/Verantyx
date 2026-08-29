#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import unittest

from photoloset.front_candidate_artifact_pipeline import (
    REQUEST_SCHEMA,
    assemble,
)
from photoloset.front_image_generation_contract import (
    REQUEST_SCHEMA as FRONT_REQUEST_SCHEMA,
    REQUIRED_WEARER_MEASUREMENTS,
)


def _visible(part_id):
    return {
        "state": "PROPOSED",
        "basis": f"the front image supports {part_id} geometry",
        "breaks_when": "another view or a human review contradicts it",
    }


def _part(part_id, kind, dimensions, placement, *, unit="look", layer=0,
          **extra):
    row = {
        "part_id": part_id,
        "kind": kind,
        "dimensions": copy.deepcopy(dimensions),
        "placement": placement,
        "garment_unit": unit,
        "layer": layer,
        "visible_basis": _visible(part_id),
    }
    row.update(extra)
    return row


def _body(part_id="body", *, unit="look", layer=0, **extra):
    return _part(
        part_id, "BODY_SHELL",
        {"height_cm": 43.0, "circumference_cm": 90.0},
        "front torso", unit=unit, layer=layer, **extra,
    )


def _skirt(*, unit="look", **extra):
    return _part(
        "skirt", "FLARE",
        {"height_cm": 64.0, "top_circumference_cm": 76.0,
         "bottom_circumference_cm": 172.0},
        "lower body", unit=unit, **extra,
    )


def _candidate(candidate_id, parts, *, rear="center-back opening",
               material="medium-drape woven range"):
    return {
        "candidate_id": candidate_id,
        "state": "PROPOSED",
        "parts": copy.deepcopy(parts),
        "rear_hypothesis": {
            "state": "PROPOSED",
            "value": rear,
            "basis": "the rear is absent from the front image",
            "breaks_when": "a rear or side view is supplied",
        },
        "material_hypothesis": {
            "state": "PROPOSED",
            "value": material,
            "basis": "appearance only bounds material mechanics",
            "breaks_when": "a swatch or material test is supplied",
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }


def _measurements():
    return {
        name: {
            "value_cm": 82.0 + index,
            "authority": "USER_PROVIDED",
            "source": "named target wearer",
        }
        for index, name in enumerate(REQUIRED_WEARER_MEASUREMENTS)
    }


def _request(*candidates):
    return {
        "schema": REQUEST_SCHEMA,
        "front_image_request": {
            "schema": FRONT_REQUEST_SCHEMA,
            "source": {"image_id": "sha256:front-fixture", "view": "front"},
            "vision": {
                "observations": [{
                    "claim_id": "front-outline",
                    "field": "front.silhouette",
                    "value": "structured geometry supplied below",
                    "authority": "OBSERVED",
                    "basis": "corrected visible front boundary",
                }],
                "proposals": [{
                    "claim_id": "front-depth",
                    "field": "front.depth_interpretation",
                    "value": "candidate dependent",
                    "authority": "PROPOSED",
                    "basis": "one front image does not observe depth",
                }],
            },
            "wearer_measurements": _measurements(),
            "candidates": list(candidates),
            "artifacts": {},
            "approvals": {},
            "rounds": [],
            "max_rounds": 8,
        },
    }


def _selected_avatar():
    return {
        "avatar_id": "selected-preview-body",
        "kind": "PARAMETRIC_GAME_AVATAR",
        "authority": "PROPOSED_PREVIEW",
        "geometry_digest": "selected-preview-body-geometry",
        "measurements_cm": {
            "height": 170, "chest_bust": 90, "waist": 72, "hip": 96,
        },
    }


def _disconnected_front_target():
    # Three deliberately disconnected source-view components: an upper panel
    # and two lower limbs.  The right side is wider, so a later generic or
    # mirrored replacement is observable in the regression.
    return {
        "schema": "garment.target-sculpt-surface.v1",
        "state": "PROPOSED",
        "authority": "PROPOSED_IMAGE_COMPONENT_FRONT",
        "digest": "source-front-components-a",
        "vertices_cm": [
            [-22, 55, 14], [22, 55, 14], [19, 25, 15], [-20, 25, 15],
            [-20, 20, 14], [-3, 20, 15], [-5, -65, 12], [-23, -65, 11],
            [3, 20, 15], [25, 20, 14], [29, -65, 10], [5, -65, 12],
        ],
        "faces": [
            [0, 2, 1], [0, 3, 2],
            [4, 6, 5], [4, 7, 6],
            [8, 10, 9], [8, 11, 10],
        ],
        "face_region_ids": ["front-visible-surface"] * 6,
        "face_component_ids": [
            "upper", "upper", "lower-left", "lower-left",
            "lower-right", "lower-right",
        ],
        "texture_coordinates": [
            [0.28, 0.16], [0.72, 0.16], [0.69, 0.42], [0.30, 0.42],
            [0.30, 0.46], [0.47, 0.46], [0.45, 0.96], [0.27, 0.96],
            [0.53, 0.46], [0.75, 0.46], [0.79, 0.96], [0.55, 0.96],
        ],
    }


class FrontCandidateArtifactPipelineTests(unittest.TestCase):
    maxDiff = None

    def _single_structure(self, result, source_id):
        self.assertIn(result["verdict"], {"PROPOSED", "REVIEW"}, result)
        source = next(row for row in result["source_candidates"]
                      if row["candidate_id"] == source_id)
        contract_source = next(
            row for row in result["front_contract_result"]["candidates"]
            if row["candidate_id"] == source_id)
        self.assertEqual(source["candidate_digest"],
                         contract_source["candidate_digest"])
        self.assertEqual(source["front_candidate"], contract_source)
        self.assertEqual(len(source["structure_alternatives"]), 1, source)
        structure = source["structure_alternatives"][0]
        self.assertEqual(structure["source_candidate_id"], source_id)
        self.assertEqual(structure["source_candidate_digest"],
                         source["candidate_digest"])
        self.assertEqual(structure["candidate_id"],
                         structure["structure"]["candidate_id"])
        self.assertEqual(structure["candidate_digest"],
                         structure["structure"]["candidate_digest"])
        pattern = structure["pattern_candidate"]
        self.assertEqual(pattern["candidate_id"], structure["candidate_id"])
        self.assertEqual(pattern["candidate_digest"],
                         structure["candidate_digest"])
        self.assertEqual(pattern["verdict"], "ANSWER", pattern)
        self.assertTrue(pattern["cuttable_geometric_prototype"])
        for row in (result, source, structure, pattern,
                    pattern["compiler_result"]):
            self.assertFalse(row["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        self.assertFalse(source["manufacturing_certified"])
        self.assertFalse(structure["manufacturing_certified"])
        self.assertFalse(pattern["manufacturing_certified"])
        self.assertIsNone(result["human_choice"]["selected_candidate_id"])
        self.assertFalse(result["claims"]["candidate_auto_selected"])
        self.assertEqual(pattern["authority"], {
            "rear": "PROPOSED",
            "material": "PROPOSED",
            "dimensions": "PROPOSED",
            "hidden_joins": "PROPOSED",
        })
        return structure

    def test_separated_top_and_bottom_bundle_to_a_cuttable_candidate(self):
        source = _candidate("separated", [
            _body(unit="upper-unit"),
            _skirt(unit="lower-unit"),
        ])
        result = assemble(_request(source))
        structure = self._single_structure(result, "separated")
        self.assertEqual(structure["structure"]["structure_graph"][
            "operations"], [])
        self.assertGreaterEqual(len(structure["pattern_candidate"][
            "compiler_result"]["pieces"]), 2)

    def test_one_piece_join_preserves_source_and_structure_identity(self):
        source = _candidate("one-piece", [
            _body(),
            _skirt(attached_to="body", attachment_relation="JOIN"),
        ])
        result = assemble(_request(source))
        structure = self._single_structure(result, "one-piece")
        operations = structure["structure"]["structure_graph"]["operations"]
        self.assertEqual([row["kind"] for row in operations], ["JOIN"])
        self.assertTrue(structure["pattern_candidate"]["compiler_result"][
            "seams"])

    def test_two_legs_and_gusset_compile_without_a_trouser_enum(self):
        source = _candidate("split-lower", [
            _body(),
            _part("leg-left", "TUBE",
                  {"length_cm": 99.0, "circumference_cm": 57.0},
                  "left lower leg", side="left"),
            _part("leg-right", "TUBE",
                  {"length_cm": 99.0, "circumference_cm": 57.0},
                  "right lower leg", side="right"),
            _part("crotch-gusset", "GUSSET",
                  {"length_cm": 18.0, "width_cm": 8.0},
                  "crotch"),
        ])
        result = assemble(_request(source))
        structure = self._single_structure(result, "split-lower")
        kinds = {row["kind"] for row in structure["structure"][
            "structure_graph"]["nodes"]}
        self.assertEqual(kinds, {"BODY_SHELL", "TUBE", "GUSSET"})
        self.assertFalse(result["claims"]["garment_class_enum_added"])
        self.assertFalse(result["claims"]["garment_name_classifier_used"])

    def test_layering_and_ornament_use_existing_primitives(self):
        source = _candidate("layered-ornament", [
            _body("underlayer", layer=0),
            _part("outer-panel", "OVERLAY",
                  {"height_cm": 46.0, "width_cm": 55.0},
                  "front torso overlay", layer=1,
                  attached_to="underlayer"),
            _part("front-bow", "BOW",
                  {"body_length_cm": 24.0, "body_width_cm": 8.0,
                   "knot_length_cm": 7.0, "knot_width_cm": 3.0},
                  "front torso decoration", layer=2,
                  attached_to="outer-panel"),
        ])
        result = assemble(_request(source))
        structure = self._single_structure(result, "layered-ornament")
        nodes = {row["node_id"]: row for row in structure["structure"][
            "structure_graph"]["nodes"]}
        self.assertEqual(nodes["front-bow"]["kind"], "OVERLAY")
        self.assertEqual(nodes["front-bow"]["attributes"][
            "dimension_authority"], "PROPOSED_FRONT_GEOMETRY")
        self.assertTrue(any(row["kind"] == "LAYER" for row in
                            structure["structure"]["structure_graph"][
                                "operations"]))

    def test_explicit_layered_bodice_sleeve_parent_compiles_beside_sibling(self):
        good = _candidate("good", [
            _body(unit="upper"), _skirt(unit="lower"),
        ])
        unsupported = _candidate("unsupported", [
            _body("inner-body", unit="inner", layer=0),
            _body("outer-body", unit="outer", layer=1),
            _part("outer-sleeve", "SLEEVE",
                  {"length_cm": 55.0, "upper_circumference_cm": 32.0,
                   "cuff_circumference_cm": 20.0},
                  "arms", unit="outer", layer=1,
                  attached_to="outer-body"),
        ])
        request = _request(good, unsupported)
        first = assemble(request)
        reordered = copy.deepcopy(request)
        reordered["front_image_request"]["candidates"].reverse()
        second = assemble(reordered)

        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(first["source_candidate_count"], 2)
        good_bundle = next(row for row in first["source_candidates"]
                           if row["candidate_id"] == "good")
        bad_bundle = next(row for row in first["source_candidates"]
                          if row["candidate_id"] == "unsupported")
        self.assertEqual(good_bundle["structure_alternatives"][0][
            "pattern_candidate"]["verdict"], "ANSWER")
        layered = bad_bundle["structure_alternatives"][0]
        self.assertEqual(layered["state"], "PROPOSED")
        self.assertEqual(layered["pattern_candidate"]["verdict"], "ANSWER")
        self.assertEqual(layered["source_candidate_id"], "unsupported")
        self.assertEqual(layered["source_candidate_digest"],
                         bad_bundle["candidate_digest"])
        compiled = layered["pattern_candidate"]["compiler_result"]
        self.assertEqual(
            {piece.get("source_node_id") for piece in compiled["pieces"]},
            {"inner-body", "outer-body", "outer-sleeve"},
        )
        expansion = compiled["candidate_specific_expansions"][0]
        self.assertEqual(expansion["source_nodes"],
                         ["outer-body", "outer-sleeve"])
        self.assertFalse(compiled["manufacturing_ready"])
        self.assertFalse(compiled["manufacturing_certified"])
        self.assertTrue(first["claims"]["failed_candidate_dropped"] is False)
        self.assertEqual(first["compiled_pattern_candidate_count"], 2)
        self.assertEqual(first["stopped_candidate_count"], 0)
        json.dumps(first, sort_keys=True, ensure_ascii=False, allow_nan=False)

    def test_image_front_is_fixed_while_distinct_structures_change_hidden_3d(self):
        separated = _candidate("upper-lower-separate", [
            _body(unit="upper"),
            _skirt(unit="lower"),
        ])
        split_lower = _candidate("two-lower-limbs", [
            _body(unit="upper"),
            _part("left-lower", "TUBE",
                  {"length_cm": 96.0, "circumference_cm": 55.0},
                  "left lower", unit="lower", side="left"),
            _part("right-lower", "TUBE",
                  {"length_cm": 96.0, "circumference_cm": 59.0},
                  "right lower", unit="lower", side="right"),
            _part("right-layer", "OVERLAY",
                  {"height_cm": 58.0, "width_cm": 34.0, "x_cm": 18.0},
                  "right outer surface", unit="outer", layer=2,
                  side="right"),
        ])
        request = _request(separated, split_lower)
        request["front_target_surface"] = _disconnected_front_target()
        request["base_avatar"] = _selected_avatar()

        result = assemble(request)

        self.assertTrue(result["claims"]["existing_structure_preview_called"])
        self.assertTrue(result["claims"]["image_front_target_binding_used"])
        bound = {}
        for source in result["source_candidates"]:
            self.assertEqual(len(source["structure_alternatives"]), 1, source)
            artifact = source["structure_alternatives"][0]
            self.assertEqual(artifact["state"], "PROPOSED", artifact)
            self.assertEqual(artifact["preview_candidate"]["verdict"], "ANSWER")
            target_preview = artifact["target_bound_preview"]
            self.assertEqual(target_preview["verdict"], "ANSWER", target_preview)
            self.assertTrue(target_preview["binding"]["front_fixed"])
            self.assertEqual(target_preview["preservation"][
                "front_component_ids"],
                ["lower-left", "lower-right", "upper"])
            self.assertFalse(target_preview["manufacturing_ready"])
            self.assertEqual(target_preview["authority"]["rear"], "PROPOSED")
            bound[source["candidate_id"]] = target_preview

        front_count = len(_disconnected_front_target()["vertices_cm"])
        first = bound["upper-lower-separate"]
        second = bound["two-lower-limbs"]
        self.assertEqual(first["mesh"]["vertices"][:front_count],
                         second["mesh"]["vertices"][:front_count])
        self.assertNotEqual(first["mesh"]["vertices"][front_count:],
                            second["mesh"]["vertices"][front_count:])
        self.assertNotEqual(first["mesh"]["face_node_ids"],
                            second["mesh"]["face_node_ids"])

        reordered = copy.deepcopy(request)
        reordered["front_image_request"]["candidates"].reverse()
        self.assertEqual(result["digest"], assemble(reordered)["digest"])


if __name__ == "__main__":
    unittest.main()
