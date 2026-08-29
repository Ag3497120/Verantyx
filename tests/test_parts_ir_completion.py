#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import unittest

from photoloset import garment_structure
from photoloset.front_structure_hypotheses import _DEFAULT_MEASUREMENTS
from photoloset.parts_ir_completion import (
    bounded_preview_profile,
    complete_parts_ir,
    required_dimensions,
)


def part(part_id, kind, *, dimensions=None, placement="front torso", layer=0):
    row = {
        "part_id": part_id,
        "kind": kind,
        "layer": layer,
        "placement": placement,
        "visible_basis": {
            "state": "PROPOSED",
            "basis": f"vision model proposed {part_id} from the visible front",
            "breaks_when": "another view or reviewer rejects this part proposal",
        },
    }
    if dimensions is not None:
        row["dimensions"] = dimensions
    return row


class PartsIRCompletionTests(unittest.TestCase):
    def test_bounded_profile_reuses_front_defaults_and_completes_every_kind(self):
        profile = bounded_preview_profile()
        for name, value in _DEFAULT_MEASUREMENTS.items():
            self.assertEqual(profile["values_cm"][name], value)
            lo, hi = profile["bounds_cm"][name]
            self.assertLessEqual(lo, value)
            self.assertGreaterEqual(hi, value)

        parts = []
        placements = {
            "TUBE": "lower leg",
            "BAND": "neck band",
            "OVERLAY": "lower skirt overlay",
            "OPENING": "center back opening",
        }
        for index, kind in enumerate(garment_structure.PrimitiveKind):
            parts.append(part(
                f"part-{index}", kind.value,
                placement=placements.get(kind.value, "front torso"),
                layer=1 if kind.value == "OVERLAY" else 0,
            ))
        result = complete_parts_ir(
            {"schema": "garment.parts-ir.v1", "parts": parts,
             "candidate_count": 2},
            preview_profile=profile,
        )
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(len({c["candidate_id"] for c in result["candidates"]}), 2)
        self.assertEqual(len({c["structure_digest"] for c in result["candidates"]}), 2)
        self.assertFalse(result["authority"]["approved"])
        self.assertFalse(result["authority"]["observed"])
        self.assertFalse(result["authority"]["answer"])
        self.assertEqual(required_dimensions(), {
            kind.value: tuple(garment_structure._REQUIRED_DIMENSIONS[kind])
            for kind in garment_structure.PrimitiveKind
        })

        for candidate in result["candidates"]:
            self.assertEqual(candidate["state"], "PROPOSED")
            self.assertEqual(garment_structure.validate(candidate)["verdict"],
                             "ANSWER")
            self.assertFalse(candidate["provenance"]["raw_pixels_consumed"])
            self.assertFalse(candidate["provenance"]["image_measurements_claimed"])
            for node in candidate["nodes"]:
                evidence = node["attributes"]["dimension_evidence"]
                self.assertEqual(set(evidence), set(node["dimensions"]))
                for name, row in evidence.items():
                    self.assertEqual(row["state"], "PROPOSED")
                    self.assertTrue(row["dimension_source"])
                    self.assertTrue(row["basis"])
                    self.assertTrue(row["breaks_when"])
                    self.assertTrue(row["not_measured_from_image"])
                    self.assertEqual(row["value_cm"], node["dimensions"][name])
            json.dumps(candidate, allow_nan=False)

    def test_model_values_and_completed_values_remain_distinct(self):
        result = complete_parts_ir(
            {"parts": [part(
                "sleeve", "SLEEVE", placement="left arm",
                dimensions={
                    "length_cm": {
                        "value": 71.0,
                        "state": "PROPOSED",
                        "basis": "model proposed a long sleeve",
                        "breaks_when": "the desired sleeve endpoint changes",
                    }
                },
            )]},
            preview_profile=bounded_preview_profile(),
        )
        self.assertEqual(result["verdict"], "PROPOSED")
        for candidate in result["candidates"]:
            node = candidate["nodes"][0]
            self.assertEqual(node["dimensions"]["length_cm"], 71.0)
            length = node["attributes"]["dimension_evidence"]["length_cm"]
            upper = node["attributes"]["dimension_evidence"][
                "upper_circumference_cm"]
            self.assertEqual(length["dimension_source"],
                             "MODEL_SUPPLIED_PROPOSAL")
            self.assertTrue(length["model_supplied"])
            self.assertFalse(length["completed"])
            self.assertEqual(upper["dimension_source"],
                             "BOUNDED_PREVIEW_MANNEQUIN_DERIVED_PROPOSAL")
            self.assertFalse(upper["model_supplied"])
            self.assertTrue(upper["completed"])

    def test_model_topology_hints_are_preserved_only_as_proposed_attributes(self):
        source = part(
            "ruffle", "BAND", placement="skirt hem", layer=2,
            dimensions={"length_cm": 140.0, "width_cm": 9.0},
        )
        source.update({
            "garment_unit": "dress-1",
            "attached_to": "skirt",
            "side": "bilateral",
            "shape": "wave",
            "detail_role": ["ruffle", "decorative_edge"],
            "quantity": 2,
        })
        result = complete_parts_ir({"parts": [source]})
        self.assertEqual(result["verdict"], "PROPOSED")
        for candidate in result["candidates"]:
            attributes = candidate["nodes"][0]["attributes"]
            for name in ("garment_unit", "attached_to", "side", "shape",
                         "detail_role", "quantity"):
                self.assertEqual(attributes[name], source[name])
                evidence = attributes["parts_ir_semantics"][name]
                self.assertEqual(evidence["state"], "PROPOSED")
                self.assertEqual(evidence["source"],
                                 "MODEL_SUPPLIED_PARTS_IR_PROPOSAL")
                self.assertTrue(evidence["basis"])
                self.assertTrue(evidence["breaks_when"])

        bad = dict(source)
        bad["quantity"] = 0
        refused = complete_parts_ir({"parts": [bad]})
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_PARTS_IR_INVALID_QUANTITY")

    def test_target_measurement_alias_is_derived_but_never_observed(self):
        result = complete_parts_ir(
            {"parts": [part("body", "BODY_SHELL")]},
            target_measurements={
                "source_id": "mannequin-A-caliper-sheet",
                "values_cm": {
                    "body_length_cm": {
                        "value": 44.0,
                        "state": "OBSERVED",
                        "basis": "calibrated mannequin tape measurement",
                        "breaks_when": "the mannequin is remeasured",
                    },
                    "chest_cm": 101.0,
                },
            },
        )
        self.assertEqual(result["verdict"], "PROPOSED")
        first, second = result["candidates"]
        self.assertEqual(first["nodes"][0]["dimensions"]["height_cm"], 44.0)
        self.assertEqual(first["nodes"][0]["dimensions"]["circumference_cm"],
                         105.04)
        self.assertEqual(second["nodes"][0]["dimensions"]["circumference_cm"],
                         113.12)
        evidence = first["nodes"][0]["attributes"]["dimension_evidence"]
        self.assertTrue(all(
            row["dimension_source"] == "TARGET_MANNEQUIN_DERIVED_PROPOSAL"
            for row in evidence.values()
        ))
        self.assertTrue(all(row["state"] == "PROPOSED"
                            for row in evidence.values()))
        height_source = evidence["height_cm"]["source_measurements"][0]
        self.assertEqual(height_source["state"], "PROPOSED")
        self.assertTrue(height_source["source_measurement_was_observed"])

    def test_partial_model_dimensions_only_require_metrics_for_missing_fields(self):
        result = complete_parts_ir(
            {"parts": [part(
                "body", "BODY_SHELL",
                dimensions={"circumference_cm": 110.0},
            )]},
            target_measurements={"upper_height_cm": 47.0},
        )
        self.assertEqual(result["verdict"], "PROPOSED")
        for candidate in result["candidates"]:
            node = candidate["nodes"][0]
            self.assertAlmostEqual(
                node["dimensions"]["height_cm"],
                47.0 * (1.0 if candidate["completion_variant"] == "balanced"
                        else 1.03),
            )
            self.assertEqual(node["dimensions"]["circumference_cm"], 110.0)

    def test_explicit_model_candidates_require_two_and_preserve_ids(self):
        one = complete_parts_ir(
            {"candidates": [{"candidate_id": "only",
                              "parts": [part("body", "BODY_SHELL")]}]},
            preview_profile=bounded_preview_profile(),
        )
        self.assertEqual(one["verdict"],
                         "UNKNOWN_PARTS_IR_CANDIDATES_INSUFFICIENT")

        two = complete_parts_ir(
            {"candidates": [
                {"candidate_id": "front-a",
                 "parts": [part("body-a", "BODY_SHELL")]},
                {"candidate_id": "front-b",
                 "parts": [part("body-b", "BODY_SHELL")]},
            ]},
            preview_profile=bounded_preview_profile(),
        )
        self.assertEqual(two["verdict"], "PROPOSED")
        self.assertEqual([row["candidate_id"] for row in two["candidates"]],
                         ["front-a", "front-b"])

    def test_typed_refusals_for_missing_source_unknown_kind_and_bad_value(self):
        missing = complete_parts_ir(
            {"parts": [part("body", "BODY_SHELL")]})
        self.assertEqual(missing["verdict"],
                         "UNKNOWN_PARTS_IR_MEASUREMENT_SOURCE_REQUIRED")

        unknown = complete_parts_ir(
            {"parts": [part("mystery", "MAGICAL_RUFFLE")]},
            preview_profile=bounded_preview_profile(),
        )
        self.assertEqual(unknown["verdict"],
                         "UNKNOWN_PARTS_IR_UNKNOWN_KIND")

        abnormal = complete_parts_ir(
            {"parts": [part(
                "body", "BODY_SHELL",
                dimensions={"height_cm": -2.0},
            )]},
            preview_profile=bounded_preview_profile(),
        )
        self.assertEqual(abnormal["verdict"],
                         "UNKNOWN_PARTS_IR_INVALID_DIMENSION")

    def test_complete_model_dimensions_need_no_fake_mannequin_fallback(self):
        result = complete_parts_ir({"parts": [part(
            "opening", "OPENING",
            dimensions={"length_cm": 31.0},
            placement="proposed center back",
        )]})
        self.assertEqual(result["verdict"], "PROPOSED")
        for candidate in result["candidates"]:
            evidence = candidate["nodes"][0]["attributes"][
                "dimension_evidence"]["length_cm"]
            self.assertEqual(evidence["dimension_source"],
                             "MODEL_SUPPLIED_PROPOSAL")
            self.assertFalse(evidence["completed"])

    def test_authority_escalation_and_unbounded_profile_are_refused(self):
        elevated = part("body", "BODY_SHELL")
        elevated["visible_basis"]["state"] = "OBSERVED"
        result = complete_parts_ir(
            {"parts": [elevated]},
            preview_profile=bounded_preview_profile(),
        )
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_IR_AUTHORITY_ESCALATION")

        unbounded = bounded_preview_profile()
        del unbounded["bounds_cm"]["body_circumference_cm"]
        result = complete_parts_ir(
            {"parts": [part("body", "BODY_SHELL")]},
            preview_profile=unbounded,
        )
        self.assertEqual(result["verdict"],
                         "UNKNOWN_PARTS_IR_UNBOUNDED_PREVIEW_VALUE")

    def test_deterministic_output(self):
        payload = {"parts": [part("flare", "FLARE", placement="lower body")]}
        profile = bounded_preview_profile()
        first = complete_parts_ir(payload, preview_profile=profile)
        second = complete_parts_ir(payload, preview_profile=profile)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
