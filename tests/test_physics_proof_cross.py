# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import physics_proof_cross as proof


class PhysicsProofCrossTests(unittest.TestCase):
    def request(self, obligation):
        return {"schema": proof.SCHEMA, "run_id": "r-1", "solver": "cloth",
                "obligations": [obligation]}

    def test_exact_identity_is_distinct_from_bounded_certificate(self):
        result = proof.verify(self.request({
            "id": "mass", "predicate": "exact_equal",
            "data": {"left": "1.25", "right": "5/4"},
        }))
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["obligations"][0]["verdict"], "CERTIFIED_EXACT")

        bounded = proof.verify(self.request({
            "id": "residual", "predicate": "bounded_absolute",
            "data": {"value": "0.001", "bound": "0.01"},
        }))
        self.assertEqual(bounded["obligations"][0]["verdict"],
                         "CERTIFIED_BOUNDED")

    def test_failed_bound_is_refuted(self):
        result = proof.verify(self.request({
            "id": "divergence", "predicate": "bounded_absolute",
            "data": {"value": "0.2", "bound": "0.01"},
        }))
        self.assertEqual(result["verdict"], proof.REFUTED)

    def test_disagreeing_witness_emerges_as_contested(self):
        result = proof.verify(self.request({
            "id": "ccd", "predicate": "interval_contains",
            "data": {"lower": "0", "value": "1/2", "upper": "1"},
            "witnesses": [{"source": "independent-checker", "holds": False}],
        }))
        self.assertEqual(result["verdict"], proof.CONTESTED)
        self.assertEqual(result["obligations"][0]["cross_resolution"]["verdict"],
                         "CONTESTED_IN_CROSS")

    def test_generic_theorem_needs_two_sources(self):
        one = proof.verify(self.request({
            "id": "order", "predicate": "minimum_integer_order",
            "data": {"errors": ["1/4", "1/16"], "spacings": ["1/2", "1/4"],
                     "minimum_order": 2},
            "theorem": "quadratic refinement bound", "theorem_sources": ["A"],
        }))
        self.assertFalse(one["obligations"][0]["generic_theorem_bought"])
        two_request = self.request({
            "id": "order", "predicate": "minimum_integer_order",
            "data": {"errors": ["1/4", "1/16"], "spacings": ["1/2", "1/4"],
                     "minimum_order": 2},
            "theorem": "quadratic refinement bound", "theorem_sources": ["A", "B"],
        })
        two = proof.verify(two_request)
        self.assertTrue(two["obligations"][0]["generic_theorem_bought"])

    def test_input_is_immutable_and_unknown_is_typed(self):
        request = self.request({"id": "x", "predicate": "not-a-proof", "data": {}})
        frozen = copy.deepcopy(request)
        result = proof.verify(request)
        self.assertEqual(result["verdict"], proof.UNKNOWN)
        self.assertEqual(request, frozen)

    def test_capabilities_deny_pde_solving(self):
        self.assertIn("solve differential equations",
                      proof.capabilities()["does_not_do"])

    def test_stage_adapter_labels_self_report_scope(self):
        result = proof.verify_stage_results("stage-1", {
            "incompressible_fluid": {
                "verdict": "ANSWER",
                "diagnostics": {
                    "mass_ledger": {"initial_mass_kg": 2.0,
                                    "final_mass_kg": 2.0},
                    "divergence_before_projection": {"l2_rms_s_inv": 1.0},
                    "divergence_after_projection": {"l2_rms_s_inv": 0.1},
                },
            },
        })
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["scope"], "SELF_REPORTED_ARITHMETIC_ONLY")
        self.assertFalse(result["external_physical_validation"])


if __name__ == "__main__":
    unittest.main()
