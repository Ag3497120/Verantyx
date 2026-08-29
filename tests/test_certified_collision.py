from decimal import Decimal
from fractions import Fraction
import copy
import unittest

from photoloset.certified_collision import (
    ALGEBRAIC_ROOT, ANSWER, COMPLEXITY, COPLANAR_MOTION,
    FINITE_THICKNESS, capabilities, certify_edge_edge,
    certify_vertex_triangle, orientation2d, orientation3d, solve,
)


class AdaptivePredicateTests(unittest.TestCase):
    def test_orientation2d_fraction_fallback_resolves_tiny_positive(self):
        tiny = Fraction(1, 10**60)
        result = orientation2d(
            [Fraction(0), Fraction(0)],
            [Fraction(1), Fraction(1, 10**30)],
            [Fraction(2), Fraction(2, 10**30)+tiny])
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["sign"], 1)
        self.assertEqual(result["method"], "FRACTION_EXACT")
        self.assertEqual(result["absolute_error_bound"], "0")

    def test_orientation3d_exact_zero(self):
        result = orientation3d([0, 0, 0], [1, 0, 0],
                               [0, 1, 0], [Decimal("0.1"), Decimal("0.1"), 0])
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["sign"], 0)
        self.assertEqual(result["method"], "FRACTION_EXACT")

    def test_exact_bit_budget_is_typed_unknown(self):
        tiny = Fraction(1, 2**200)
        result = orientation2d([0, 0], [1, tiny], [2, 2*tiny+tiny*tiny],
                               max_exact_bits=16)
        self.assertEqual(result["verdict"], COMPLEXITY)

    def test_float_filter_overflow_falls_back_to_typed_budget_result(self):
        huge = Fraction(10**6000)
        result = orientation2d([huge, 0], [huge+1, 0], [huge, 1],
                               max_exact_bits=128)
        self.assertEqual(result["verdict"], COMPLEXITY)


class ContinuousCertificateTests(unittest.TestCase):
    def test_vertex_triangle_exact_rational_hit(self):
        result = certify_vertex_triangle(
            [Fraction(1, 4), Fraction(1, 4), 1],
            [Fraction(1, 4), Fraction(1, 4), -1],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]])
        self.assertEqual(result["verdict"], ANSWER)
        self.assertTrue(result["hit"])
        self.assertEqual(result["toi_exact"], "1/2")
        self.assertEqual(result["toi_error_bound"], "0")
        self.assertTrue(result["earliest_certified"])

    def test_coplanarity_outside_triangle_certifies_miss(self):
        result = certify_vertex_triangle(
            [2, 2, 1], [2, 2, -1],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]])
        self.assertEqual(result["verdict"], ANSWER)
        self.assertFalse(result["hit"])
        self.assertIn("separation_certificate", result)

    def test_edge_edge_exact_rational_hit(self):
        result = certify_edge_edge(
            [[-1, 0, 0], [1, 0, 0]], [[-1, 0, 0], [1, 0, 0]],
            [[0, -1, 1], [0, 1, 1]], [[0, -1, -1], [0, 1, -1]])
        self.assertEqual(result["verdict"], ANSWER)
        self.assertTrue(result["hit"])
        self.assertEqual(result["toi_exact"], "1/2")

    def test_identically_coplanar_motion_is_unknown(self):
        result = certify_vertex_triangle(
            [Fraction(1, 4), Fraction(1, 4), 0],
            [Fraction(3, 4), Fraction(1, 4), 0],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]])
        self.assertEqual(result["verdict"], COPLANAR_MOTION)
        self.assertEqual(result["proof_obligations"][0]["status"], "UNRESOLVED")

    def test_non_rational_root_stays_bracketed_unknown(self):
        result = certify_vertex_triangle(
            [0, 0, 0], [0, 0, 0],
            [[1, 0, 0], [0, 0, 1], [0, Fraction(1, 2), 0]],
            [[1, 0, 0], [0, 1, 1], [0, Fraction(1, 2), 1]],
            max_depth=24)
        self.assertEqual(result["verdict"], ALGEBRAIC_ROOT)
        self.assertIn("normalized_error_bound", result)
        self.assertTrue(result["unresolved_brackets"])

    def test_finite_thickness_overlap_is_unknown_but_aabb_separation_is_proved(self):
        overlap = certify_vertex_triangle(
            [Fraction(1, 4), Fraction(1, 4), Fraction(1, 10)],
            [Fraction(1, 4), Fraction(1, 4), Fraction(1, 10)],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]], thickness_m=Fraction(1, 5))
        self.assertEqual(overlap["verdict"], FINITE_THICKNESS)
        separated = certify_vertex_triangle(
            [10, 10, 10], [10, 10, 10],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]], thickness_m=1)
        self.assertEqual(separated["verdict"], ANSWER)
        self.assertFalse(separated["hit"])

    def test_solve_is_order_invariant_and_immutable(self):
        hit = {"id": "b", "kind": "VERTEX_TRIANGLE",
               "vertex_start": [Fraction(1, 4), Fraction(1, 4), 1],
               "vertex_end": [Fraction(1, 4), Fraction(1, 4), -1],
               "triangle_start": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
               "triangle_end": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}
        miss = {"id": "a", "kind": "VERTEX_TRIANGLE",
                "vertex_start": [10, 10, 10], "vertex_end": [10, 10, 10],
                "triangle_start": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "triangle_end": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}
        request = {"queries": [hit, miss]}
        frozen = copy.deepcopy(request)
        first = solve(request)
        second = solve({"queries": [miss, hit]})
        self.assertEqual(first["verdict"], ANSWER)
        self.assertEqual(first["results"], second["results"])
        self.assertEqual(request, frozen)

    def test_capabilities_are_honest(self):
        report = capabilities()
        self.assertTrue(report["features"]["fraction_exact_fallback"])
        self.assertFalse(report["features"]["exact_all_algebraic_roots"])
        self.assertFalse(report["features"]["certified_finite_thickness_distance"])
        self.assertFalse(report["features"]["industrial_certification"])


if __name__ == "__main__":
    unittest.main()
