# -*- coding: utf-8 -*-
"""Tests for the constitutive material field (not a cloth solver)."""
import math
import unittest

from photoloset.material_field import (
    FaceMaterial,
    Provenance,
    StrainState,
    TextileField,
    VerdictCode,
    compare_jersey_melton,
    jersey,
    melton,
)


class MaterialFieldTests(unittest.TestCase):
    def test_invalid_units_and_ranges_are_rejected(self):
        values = vars(jersey()).copy()
        values["thickness_m"] = -0.001
        with self.assertRaisesRegex(ValueError, "thickness_m"):
            FaceMaterial(**values)

        values = vars(jersey()).copy()
        values["friction_dynamic"] = values["friction_static"] + 0.1
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            FaceMaterial(**values)

        values = vars(jersey()).copy()
        values["warp_modulus_n_m"] = math.inf
        with self.assertRaisesRegex(ValueError, "finite"):
            FaceMaterial(**values)

    def test_spatial_face_override_and_provenance(self):
        source = Provenance("coupon A", "biaxial bench measurement", "r7")
        override_values = vars(jersey()).copy()
        override_values.update(areal_density_kg_m2=0.21, provenance=source)
        local = FaceMaterial(**override_values)
        field = TextileField(melton(), {"front:17": local})
        self.assertIs(field.at("front:17"), local)
        self.assertIs(field.at("back:4"), field.default)
        response = field.stress_response("front:17", StrainState(0.01, 0.0))
        self.assertEqual(response.provenance, source)

    def test_anisotropic_response_rotates_with_warp(self):
        material = melton()
        base = TextileField(material).stress_response(
            "f", StrainState(0.02, 0.0)).value
        rotated_values = vars(material).copy()
        rotated_values["warp_angle_rad"] = math.pi / 2.0
        rotated = TextileField(FaceMaterial(**rotated_values)).stress_response(
            "f", StrainState(0.02, 0.0)).value
        self.assertIsNotNone(base)
        self.assertIsNotNone(rotated)
        self.assertGreater(base.stress_xx_n_m, rotated.stress_xx_n_m)
        self.assertAlmostEqual(base.warp_strain, 0.02)
        self.assertAlmostEqual(rotated.weft_strain, 0.02)

    def test_stretch_limit_has_typed_review_verdict(self):
        result = TextileField(melton()).stress_response(
            "f", StrainState(0.20, 0.0))
        self.assertEqual(result.code, VerdictCode.REVIEW)
        self.assertFalse(result.accepted)
        self.assertIn("warp stretch limit exceeded", result.reasons)
        self.assertIsNotNone(result.value)

    def test_gravity_uses_area_and_areal_density(self):
        result = TextileField(melton()).gravity_load("f", 0.5)
        self.assertEqual(result.code, VerdictCode.PASS)
        self.assertAlmostEqual(result.value.mass_kg, 0.260)
        self.assertEqual(result.value.force_n[0], 0.0)
        self.assertAlmostEqual(result.value.force_n[1], -0.260 * 9.80665)
        with self.assertRaisesRegex(ValueError, "area_m2"):
            TextileField(melton()).gravity_load("f", 0.0)

    def test_seam_compatibility_is_typed_and_directional(self):
        field = TextileField(jersey(), {"coat": melton()})
        incompatible = field.seam_compatibility("knit", "coat")
        self.assertEqual(incompatible.code, VerdictCode.INCOMPATIBLE)
        self.assertGreater(incompatible.value.stretch_limit_ratio, 3.0)
        invalid = field.seam_compatibility("knit", "coat",
                                           direction_a="diagonal")
        self.assertEqual(invalid.code, VerdictCode.INVALID)
        self.assertIsNone(invalid.value)
        compatible = TextileField(jersey()).seam_compatibility("a", "b")
        self.assertEqual(compatible.code, VerdictCode.PASS)

    def test_jersey_and_melton_differ_on_identical_geometry(self):
        result = compare_jersey_melton(area_m2=0.25)
        self.assertEqual(result.code, VerdictCode.PASS)
        comparison = result.value
        self.assertGreater(comparison.melton_mass_kg,
                           comparison.jersey_mass_kg)
        self.assertGreater(comparison.melton_stress_norm_n_m,
                           comparison.jersey_stress_norm_n_m)
        self.assertGreater(comparison.melton_bending_moment_n,
                           comparison.jersey_bending_moment_n)
        self.assertIn("not a cloth solve", result.reasons[1])

    def test_deterministic_for_same_inputs(self):
        field = TextileField(jersey(), {"panel": melton()})
        strain = StrainState(0.011, -0.003, 0.002,
                             curvature_bias_1_m=1.5)
        self.assertEqual(field.stress_response("panel", strain),
                         field.stress_response("panel", strain))
        self.assertEqual(field.gravity_load("panel", 0.125),
                         field.gravity_load("panel", 0.125))


if __name__ == "__main__":
    unittest.main()
