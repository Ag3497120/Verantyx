#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import unittest

from photoloset.design_requirement_profile import REQUEST_SCHEMA, compile_profile


def requirement(kind, target, *, value=None, unit=None, text=None):
    return {
        "kind": kind, "target": target, "value": value, "unit": unit,
        "text": text, "note": "explicit beginner-chat request",
    }


class DesignRequirementProfileTests(unittest.TestCase):
    maxDiff = None

    def test_explicit_waist_and_ease_drive_only_waist_boundaries(self):
        result = compile_profile({
            "schema": REQUEST_SCHEMA,
            "requirements": [
                requirement("STANDARD_SIZE", "wearer_size", text="M"),
                requirement("BODY_MEASUREMENT", "waist", value=72, unit="cm"),
                requirement("EASE", "waist ease", value=4, unit="cm"),
            ],
        })
        self.assertEqual(result["verdict"], "REVIEW")
        for primitive in ("FLARE", "FRUSTUM", "BAND"):
            field = "length_cm" if primitive == "BAND" else "top_circumference_cm"
            self.assertEqual(result["primitive_overrides"][primitive][field]["value_cm"], 76)
        self.assertNotIn("BODY_SHELL", result["primitive_overrides"])
        self.assertEqual(result["review_items"][0]["code"],
                         "UNKNOWN_STANDARD_SIZE_CHART_REQUIRED")
        self.assertFalse(result["manufacturing_ready"])

    def test_chest_body_length_sleeve_and_inseam_map_to_typed_fields(self):
        result = compile_profile({
            "schema": REQUEST_SCHEMA,
            "requirements": [
                requirement("BODY_MEASUREMENT", "bust", value=.88, unit="m"),
                requirement("EASE", "chest", value=3, unit="cm"),
                requirement("BODY_MEASUREMENT", "body_length", value=44, unit="cm"),
                requirement("BODY_MEASUREMENT", "sleeve_length", value=57, unit="cm"),
                requirement("BODY_MEASUREMENT", "inseam", value=76, unit="cm"),
            ],
        })
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(result["primitive_overrides"]["BODY_SHELL"]
                         ["circumference_cm"]["value_cm"], 91)
        self.assertEqual(result["primitive_overrides"]["BODY_SHELL"]
                         ["height_cm"]["value_cm"], 44)
        self.assertEqual(result["primitive_overrides"]["SLEEVE"]
                         ["length_cm"]["value_cm"], 57)
        self.assertEqual(result["primitive_overrides"]["TUBE"]
                         ["length_cm"]["value_cm"], 76)
        self.assertTrue(result["requires_measurement_source_before_manufacturing"])

    def test_specific_garment_lengths_override_matching_primitives(self):
        result = compile_profile({
            "schema": REQUEST_SCHEMA,
            "requirements": [
                requirement("LENGTH", "skirt length", value=63, unit="cm"),
                requirement("GARMENT_MEASUREMENT", "hem circumference",
                            value=1800, unit="mm"),
                requirement("LENGTH", "cape length", value=.52, unit="m"),
            ],
        })
        self.assertEqual(result["primitive_overrides"]["FLARE"], {
            "bottom_circumference_cm": result["primitive_overrides"]["FLARE"]
            ["bottom_circumference_cm"],
            "height_cm": result["primitive_overrides"]["FLARE"]["height_cm"],
        })
        self.assertEqual(result["primitive_overrides"]["FLARE"]
                         ["bottom_circumference_cm"]["value_cm"], 180)
        self.assertEqual(result["primitive_overrides"]["OVERLAY"]
                         ["height_cm"]["value_cm"], 52)

    def test_generic_ease_is_preserved_but_not_distributed(self):
        result = compile_profile({
            "schema": REQUEST_SCHEMA,
            "requirements": [
                requirement("EASE", "whole garment", value=4, unit="cm"),
            ],
        })
        self.assertEqual(result["verdict"], "REVIEW")
        self.assertEqual(result["primitive_overrides"], {})
        self.assertEqual(result["review_items"][0]["code"],
                         "UNKNOWN_EASE_TARGET_REQUIRED")
        self.assertFalse(result["claims"]["generic_ease_auto_distributed"])

    def test_units_are_canonical_but_conflicts_stop(self):
        centimetres = {
            "schema": REQUEST_SCHEMA,
            "requirements": [requirement(
                "BODY_MEASUREMENT", "waist", value=72, unit="cm")],
        }
        metres = copy.deepcopy(centimetres)
        metres["requirements"][0].update(value=.72, unit="m")
        self.assertEqual(
            compile_profile(centimetres)["primitive_overrides"],
            compile_profile(metres)["primitive_overrides"],
        )
        conflict = copy.deepcopy(centimetres)
        conflict["requirements"].append(requirement(
            "GARMENT_MEASUREMENT", "skirt length", value=60, unit="cm"))
        conflict["requirements"].append(requirement(
            "LENGTH", "skirt length", value=70, unit="cm"))
        result = compile_profile(conflict)
        self.assertEqual(result["reason_code"],
                         "UNKNOWN_CONFLICTING_REQUIREMENT_DIMENSIONS")

    def test_numeric_material_and_unitless_dimension_stop(self):
        numeric_material = compile_profile({
            "schema": REQUEST_SCHEMA,
            "requirements": [requirement(
                "MATERIAL", "fabric", value=2, unit="cm")],
        })
        self.assertEqual(numeric_material["reason_code"],
                         "UNKNOWN_NUMERIC_NON_DIMENSION_REQUIREMENT")
        unitless = compile_profile({
            "schema": REQUEST_SCHEMA,
            "requirements": [requirement(
                "BODY_MEASUREMENT", "waist", value=72)],
        })
        self.assertEqual(unitless["reason_code"],
                         "UNKNOWN_EXPLICIT_DIMENSION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
