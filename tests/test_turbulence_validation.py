# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import turbulence_validation as validation


def dataset(kind="dns"):
    measurements = {
        "velocity": {"field": "u"}, "sampling": {"time_step_s": 0.01},
        "coordinates": {"frame": "facility"},
    }
    if kind == "dns":
        measurements.update({
            "pressure": {"field": "p"}, "grid_resolution": [128, 128, 128],
            "numerical_method": "documented spectral fixture",
            "convergence": {"residual": 1.0e-9},
        })
    else:
        measurements.update({
            "force_or_pressure": {"drag_n": True},
            "calibration": {"certificate": "fixture"},
            "facility": "fixture tunnel",
        })
    return {
        "schema": validation.MANIFEST_SCHEMA,
        "dataset_id": f"fixture-{kind}", "kind": kind,
        "license": {"url": "https://example.invalid/license",
                    "commercial_use": "allowed"},
        "lineage": [{"source": "fixture-origin"}],
        "conditions": {"geometry": "unit periodic box",
                       "boundary_conditions": "periodic",
                       "fluid_properties": {"density_kg_m3": 1.2},
                       "units": "SI"},
        "measurements": measurements,
        "uncertainty": {"method": "fixture interval", "values": {"velocity": 0.01}},
        "checksum_sha256": "a" * 64,
    }


class TurbulenceValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = validation.validate({
            "resolutions": [4, 8, 16], "pressure_iterations": 300,
            "pressure_tolerance_s_inv": 1.0e-8,
            "minimum_observed_order": 1.0,
        })

    def test_capabilities_do_not_claim_dns_or_formal_gci(self):
        report = validation.capabilities()
        self.assertEqual(report["verdict"], validation.ANSWER)
        self.assertFalse(report["limits"]["harness_is_dns"])
        self.assertFalse(report["limits"]["gci_is_formal_asme_gci"])
        self.assertFalse(report["limits"]["les_validated_by_manufactured_cases"])

    def test_manufactured_case_is_digest_bound_and_divergence_free(self):
        case = validation.manufactured_case("taylor_green_periodic", 4)
        self.assertEqual(case["verdict"], validation.ANSWER)
        changed = validation.manufactured_case("taylor_green_periodic", 4,
                                               amplitude_m_s=0.2)
        self.assertNotEqual(case["digest"], changed["digest"])
        evidence = self.report["validation"]["manufactured_cases"]
        self.assertTrue(evidence["passed"])
        self.assertEqual({case["case"] for case in evidence["cases"]},
                         {"uniform_periodic", "taylor_green_periodic"})
        uniform = next(case for case in evidence["cases"]
                       if case["case"] == "uniform_periodic")
        self.assertTrue(uniform["exact_invariance_passed"])
        self.assertLess(evidence["maximum_post_projection_divergence_l2_s_inv"],
                        1.0e-6)

    def test_pressure_projection_reduces_divergence(self):
        projection = self.report["validation"]["pressure_projection"]
        self.assertTrue(projection["passed"])
        self.assertGreater(projection["before_l2_rms_s_inv"], 0.0)
        self.assertLess(projection["after_over_before"], 1.0e-5)

    def test_grid_refinement_reports_observed_order_and_gci_like_value(self):
        refinement = self.report["validation"]["grid_refinement"]
        self.assertTrue(refinement["passed"])
        self.assertGreater(refinement["conservative_observed_order"], 1.0)
        self.assertGreater(refinement["gci_like_fine_uncertainty_m_s"], 0.0)
        self.assertFalse(refinement["formal_asme_gci"])

    def test_energy_and_mass_ledgers_are_finite_and_balanced(self):
        ledgers = self.report["validation"]["ledgers"]
        self.assertTrue(ledgers["passed"])
        for level in ledgers["levels"]:
            self.assertEqual(level["mass_change_kg"], 0.0)
            self.assertAlmostEqual(level["boundary_volume_balance_m3_s"], 0.0,
                                   places=9)
            self.assertGreaterEqual(level["final_kinetic_energy_j"], 0.0)
            self.assertLessEqual(level["final_kinetic_energy_j"],
                                 level["initial_kinetic_energy_j"] + 1.0e-12)

    def test_dns_and_wind_tunnel_manifests_are_digest_bound(self):
        dns = dataset("dns")
        wind = dataset("wind_tunnel")
        dns_result = validation.validate_dataset_manifest(dns)
        wind_result = validation.validate_dataset_manifest(wind)
        self.assertEqual(dns_result["verdict"], validation.ANSWER)
        self.assertEqual(wind_result["verdict"], validation.ANSWER)
        self.assertNotEqual(dns_result["manifest_digest"],
                            wind_result["manifest_digest"])

    def test_manifest_gate_fails_closed_on_rights_and_uncertainty(self):
        unknown = dataset(); unknown["license"]["commercial_use"] = "unknown"
        self.assertEqual(validation.validate_dataset_manifest(unknown)["verdict"],
                         validation.MANIFEST_REFUSAL)
        missing = dataset(); del missing["uncertainty"]
        self.assertEqual(validation.validate_dataset_manifest(missing)["verdict"],
                         validation.MANIFEST_REFUSAL)
        malformed = dataset(); malformed["measurements"] = [{"not": "a mapping"}]
        self.assertEqual(validation.validate_dataset_manifest(malformed)["verdict"],
                         validation.MANIFEST_REFUSAL)

    def test_external_claim_needs_manifest_and_in_tolerance_comparison(self):
        refused = validation.assess_claims(
            [{"name": "dns_agreement"}], self.report["validation"])
        self.assertEqual(refused["verdict"], validation.CLAIM_REFUSAL)
        accepted = validation.assess_claims([{
            "name": "dns_agreement",
            "evidence": {"dataset_manifest": dataset("dns"),
                         "comparison": {"metric": "normalized_rmse", "value": 0.02,
                                        "threshold": 0.05, "sample_count": 128}},
        }], self.report["validation"])
        self.assertEqual(accepted["verdict"], validation.ANSWER)

    def test_internal_claim_must_name_generated_evidence(self):
        refused = validation.assess_claims(
            [{"name": "pressure_projection_verified"}],
            self.report["validation"])
        self.assertEqual(refused["verdict"], validation.CLAIM_REFUSAL)
        accepted = validation.assess_claims(
            [{"name": "pressure_projection_verified",
              "evidence": ["pressure_projection"]}], self.report["validation"])
        self.assertEqual(accepted["verdict"], validation.ANSWER)

    def test_input_is_immutable_and_bad_refinement_is_typed(self):
        raw = {"resolutions": [4, 8, 12]}
        snapshot = copy.deepcopy(raw)
        result = validation.validate(raw)
        self.assertEqual(result["verdict"], validation.INVALID_INPUT)
        self.assertEqual(raw, snapshot)


if __name__ == "__main__":
    unittest.main()
