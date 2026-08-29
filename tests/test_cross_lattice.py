# -*- coding: utf-8 -*-
"""Tests for the mesoscopic six-arm cloth cross lattice."""
import json
import math
import unittest

from photoloset.cross_lattice import (
    CrossLattice,
    jacobi_center_update,
    lattice_from_result,
    mesh_to_cross_lattice,
    stack_resolution_layers,
    typed_result_digest,
    validate_cross_lattice,
)


VERTICES = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0), (0.0, 1.0, 0.0))
FACES = ((0, 1, 2), (0, 2, 3))


class CrossLatticeTests(unittest.TestCase):
    def build(self):
        result = mesh_to_cross_lattice(
            VERTICES, FACES, face_material_ids=("jersey", "melton"),
            face_warp_directions=((1.0, 0.0, 0.0),) * 2,
            areal_density_kg_m2=0.6)
        self.assertEqual(result["verdict"], "ANSWER")
        return lattice_from_result(result)

    def test_topology_six_arms_and_link_neighborhoods(self):
        lattice = self.build()
        self.assertEqual(len(lattice.vertices), 4)
        self.assertTrue(all(len(vertex.arms) == 6 for vertex in lattice.vertices))
        self.assertEqual(tuple(arm.name for arm in lattice.vertices[0].arms),
                         ("+warp", "-warp", "+weft", "-weft",
                          "+normal", "-normal"))
        kinds = [link.kind for link in lattice.links]
        self.assertIn("warp", kinds)
        self.assertIn("weft", kinds)
        self.assertIn("bias", kinds)
        self.assertEqual(kinds.count("bending"), 1)
        bending = next(link for link in lattice.links if link.kind == "bending")
        self.assertEqual(bending.vertices, (1, 3))
        self.assertAlmostEqual(bending.rest_angle_rad, 0.0)

    def test_frames_are_orthonormal_right_handed(self):
        lattice = self.build()
        for vertex in lattice.vertices:
            axes = (vertex.warp, vertex.weft, vertex.normal)
            for axis in axes:
                self.assertAlmostEqual(sum(v * v for v in axis), 1.0)
            self.assertAlmostEqual(sum(a * b for a, b in zip(axes[0], axes[1])), 0.0)
            self.assertAlmostEqual(sum(a * b for a, b in zip(axes[0], axes[2])), 0.0)
            cross = (axes[0][1] * axes[1][2] - axes[0][2] * axes[1][1],
                     axes[0][2] * axes[1][0] - axes[0][0] * axes[1][2],
                     axes[0][0] * axes[1][1] - axes[0][1] * axes[1][0])
            self.assertAlmostEqual(sum(a * b for a, b in zip(cross, axes[2])), 1.0)
        self.assertIsNone(validate_cross_lattice(lattice))

    def test_material_ids_mass_and_provenance_are_preserved(self):
        lattice = self.build()
        self.assertEqual(tuple(face.material_id for face in lattice.faces),
                         ("jersey", "melton"))
        self.assertAlmostEqual(sum(vertex.mass_kg for vertex in lattice.vertices), 0.6)
        self.assertIn("mesoscopic", lattice.provenance.assumptions[0])
        self.assertNotIn("atom", lattice.discretization)

    def test_serialization_is_deterministic_and_round_trips(self):
        lattice = self.build()
        first = lattice.to_json()
        second = self.build().to_json()
        self.assertEqual(first, second)
        self.assertEqual(CrossLattice.from_json(first).to_json(), first)
        self.assertEqual(json.dumps(json.loads(first), sort_keys=True,
                                    separators=(",", ":")), first)

    def test_nonmanifold_edge_has_typed_refusal(self):
        vertices = VERTICES + ((0.5, -1.0, 0.0),)
        result = mesh_to_cross_lattice(
            vertices, ((0, 1, 2), (1, 0, 3), (0, 1, 4)))
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertEqual(result["code"], "UNKNOWN_NONMANIFOLD_EDGE")
        self.assertNotIn("lattice", result)

    def test_degenerate_faces_have_typed_refusals(self):
        repeated = mesh_to_cross_lattice(VERTICES, ((0, 1, 1),))
        self.assertEqual(repeated["code"], "UNKNOWN_DEGENERATE_FACE")
        collinear = mesh_to_cross_lattice(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
            ((0, 1, 2),))
        self.assertEqual(collinear["verdict"], "UNKNOWN")
        self.assertEqual(collinear["code"], "UNKNOWN_DEGENERATE_FACE")

    def test_inconsistent_winding_is_typed(self):
        result = mesh_to_cross_lattice(VERTICES, ((0, 1, 2), (0, 3, 2)))
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertEqual(result["code"], "UNKNOWN_INCONSISTENT_WINDING")

    def test_invalid_material_axis_is_typed(self):
        result = mesh_to_cross_lattice(
            VERTICES, FACES,
            face_warp_directions=((0.0, 0.0, 1.0),) * 2)
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertEqual(result["code"], "UNKNOWN_MATERIAL_AXES")

    def test_energy_decomposition_keeps_physics_separate_from_facets(self):
        facets = ({"facet_id": "visible-a", "signal_kind": "strain",
                   "energy_j": 0.25},
                  {"facet_id": "visible-b", "signal_kind": "strain",
                   "energy_j": 0.75})
        result = mesh_to_cross_lattice(
            VERTICES, FACES, face_energies_j=(2.0, 3.0),
            arm_physical_energies_j={(0, "+warp"): 7.0},
            arm_visible_facets={(0, "+warp"): facets})
        lattice = lattice_from_result(result)
        report = lattice.energy_report()
        self.assertEqual(report["section_energy_j"]["+warp"], 7.0)
        self.assertEqual(report["face_energy_j"], {"0": 2.0, "1": 3.0})
        self.assertEqual(report["total_physical_energy_j"], 12.0)
        self.assertEqual(sum(f["energy_j"] for f in
                             report["diagnostic_facets"]["+warp"]), 1.0)

    def test_fifth_visible_facet_requires_refinement_without_truncation(self):
        facets = tuple({"facet_id": name, "signal_kind": "load", "energy_j": 1.0}
                       for name in ("z", "a", "q", "b", "m"))
        result = mesh_to_cross_lattice(
            VERTICES, FACES,
            arm_physical_energies_j={(0, "+warp"): 5.0},
            arm_visible_facets={(0, "+warp"): facets})
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertEqual(result["code"], "UNKNOWN_REFINEMENT_REQUIRED")
        self.assertIn("5 independent contributions", result["reasons"][0])
        self.assertNotIn("lattice", result)

    def test_exactly_twenty_four_visible_facet_slots_are_supported(self):
        facets = {}
        for arm in ("+warp", "-warp", "+weft", "-weft",
                    "+normal", "-normal"):
            facets[(0, arm)] = tuple(
                {"facet_id": f"{arm}:{index}", "signal_kind": "diagnostic",
                 "energy_j": 0.0} for index in range(4))
        result = mesh_to_cross_lattice(
            VERTICES, FACES, arm_visible_facets=facets)
        self.assertEqual(result["verdict"], "ANSWER")
        lattice = lattice_from_result(result)
        self.assertEqual(sum(len(arm.visible_facets)
                             for arm in lattice.vertices[0].arms), 24)

    @staticmethod
    def sections(center=(0.0, 0.0, 0.0)):
        return [{"arm": arm, "physical_energy_j": index + 1.0,
                 "proposed_center_m": center,
                 "read_center_m": (0.0, 0.0, 0.0),
                 "signal_kind": "mechanical-center"}
                for index, arm in enumerate(
                    ("+warp", "-warp", "+weft", "-weft",
                     "+normal", "-normal"))]

    def test_jacobi_reduction_is_order_invariant_and_requires_stability(self):
        contributions = self.sections((0.01, 0.0, 0.0))
        forward = jacobi_center_update(
            (0.0, 0.0, 0.0), contributions,
            agreement_tolerance_m=1e-6, stability_tolerance_m=0.02)
        reverse = jacobi_center_update(
            (0.0, 0.0, 0.0), tuple(reversed(contributions)),
            agreement_tolerance_m=1e-6, stability_tolerance_m=0.02)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward["code"], "CONVERGED")
        self.assertEqual(forward["total_physical_energy_j"], 21.0)

        moving = jacobi_center_update(
            (0.0, 0.0, 0.0), contributions,
            agreement_tolerance_m=1e-6, stability_tolerance_m=0.001)
        self.assertEqual(moving["code"], "IN_PROGRESS")
        self.assertFalse(moving["converged"])

        stale = list(contributions)
        stale[5] = dict(stale[5], read_center_m=(0.1, 0.0, 0.0))
        refusal = jacobi_center_update(
            (0.0, 0.0, 0.0), stale,
            agreement_tolerance_m=1e-6, stability_tolerance_m=0.02)
        self.assertEqual(refusal["code"], "UNKNOWN_NON_JACOBI_READ")

    def test_section_disagreement_abstains_instead_of_breaking_a_tie(self):
        contributions = self.sections()
        contributions[0] = dict(contributions[0], proposed_center_m=(1.0, 0.0, 0.0))
        contributions[1] = dict(contributions[1], proposed_center_m=(-1.0, 0.0, 0.0))
        result = jacobi_center_update(
            (0.0, 0.0, 0.0), contributions,
            agreement_tolerance_m=0.1, stability_tolerance_m=0.1)
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertEqual(result["code"], "CONTESTED")
        self.assertIsNone(result["updated_center_m"])

    def test_resolution_layers_chain_same_target_without_voting(self):
        coarse = {"verdict": "ANSWER", "code": "COARSE",
                  "payload": {"cells": 2}}
        medium = {"verdict": "ANSWER", "code": "MEDIUM",
                  "payload": {"cells": 8}}
        fine = {"verdict": "ANSWER", "code": "FINE",
                "payload": {"cells": 32}}
        layers = (
            {"resolution": "coarse", "target_id": "dress-front",
             "signal_kind": "geometry", "output": coarse},
            {"resolution": "medium", "target_id": "dress-front",
             "signal_kind": "geometry", "input_digest": typed_result_digest(coarse),
             "output": medium},
            {"resolution": "fine", "target_id": "dress-front",
             "signal_kind": "geometry", "input_digest": typed_result_digest(medium),
             "output": fine})
        result = stack_resolution_layers(layers)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual([v["resolution"] for v in result["layers"]],
                         ["coarse", "medium", "fine"])

        identity_medium = dict(medium, payload=coarse["payload"])
        copied = (layers[0], dict(layers[1], output=identity_medium),
                  dict(layers[2], input_digest=typed_result_digest(identity_medium)))
        refusal = stack_resolution_layers(copied)
        self.assertEqual(refusal["code"], "UNKNOWN_IDENTITY_REFINEMENT")

        mixed = (layers[0], dict(layers[1], signal_kind="temperature"), layers[2])
        self.assertEqual(stack_resolution_layers(mixed)["code"],
                         "UNKNOWN_MIXED_SIGNAL")

    def test_semantic_digest_ignores_index_and_face_scan_order(self):
        original = self.build()
        permutation = (2, 0, 3, 1)
        inverse = {old: new for new, old in enumerate(permutation)}
        vertices = tuple(VERTICES[old] for old in permutation)
        remapped = tuple(tuple(inverse[index] for index in face) for face in FACES)
        result = mesh_to_cross_lattice(
            vertices, tuple(reversed(remapped)),
            face_material_ids=("melton", "jersey"),
            face_warp_directions=((1.0, 0.0, 0.0),) * 2,
            areal_density_kg_m2=0.6)
        perturbed = lattice_from_result(result)
        self.assertEqual(original.semantic_digest(), perturbed.semantic_digest())


if __name__ == "__main__":
    unittest.main()
