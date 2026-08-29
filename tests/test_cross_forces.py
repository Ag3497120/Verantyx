# -*- coding: utf-8 -*-
"""Tests for deterministic cross-lattice cloth force kernels."""
import copy
import math
import unittest

from photoloset.cross_forces import (
    build_facet_diagnostics,
    compute_forces,
    integrate_semi_implicit,
    jacobi_cross_update,
    solve_cross_layers,
    total_energy,
)


def material(**updates):
    value = {
        "warp_stiffness_n_m": 100.0,
        "weft_stiffness_n_m": 25.0,
        "shear_stiffness_n_m": 12.0,
        "bending_stiffness_n_m": 2.0,
        "damping_n_s_m": 0.2,
    }
    value.update(updates)
    return value


def lattice(kind="warp", length=1.0, velocity=(0.0, 0.0, 0.0), *, face=False):
    result = {
        "nodes": {
            "a": {"position_m": [0.0, 0.0, 0.0], "velocity_m_s": list(velocity),
                  "mass_kg": 0.1, "fixed": False},
            "b": {"position_m": [length, 0.0, 0.0], "velocity_m_s": [0.0, 0.0, 0.0],
                  "mass_kg": 0.1, "fixed": False},
        },
        "links": [{"a": "a", "b": "b", "kind": kind,
                   "rest_length_m": 1.0, "material": material()}],
        "faces": [],
    }
    if face:
        result["nodes"]["c"] = {
            "position_m": [0.0, 1.0, 0.0], "velocity_m_s": [0.0, 0.0, 0.0],
            "mass_kg": 0.1, "fixed": False,
        }
        result["faces"] = [{"nodes": ["a", "b", "c"],
                            "material": {"drag_coefficient": 1.1,
                                         "lift_coefficient": 0.4}}]
    return result


ZERO = {"gravity_m_s2": [0.0, 0.0, 0.0], "air_density_kg_m3": 0.0}


class CrossForceTests(unittest.TestCase):
    def test_zero_force_equilibrium(self):
        result = compute_forces(lattice(), ZERO)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["value"]["forces_n"]["a"], [0.0, 0.0, 0.0])
        self.assertEqual(result["value"]["forces_n"]["b"], [0.0, 0.0, 0.0])
        advanced = integrate_semi_implicit(lattice(), 0.1, ZERO)
        self.assertEqual(advanced["value"]["lattice"]["nodes"]["a"]["position_m"],
                         [0.0, 0.0, 0.0])

    def test_warp_weft_anisotropy(self):
        warp = compute_forces(lattice("warp", 1.1), ZERO)["value"]["forces_n"]["a"][0]
        weft = compute_forces(lattice("weft", 1.1), ZERO)["value"]["forces_n"]["a"][0]
        self.assertAlmostEqual(warp / weft, 4.0)
        self.assertGreater(warp, weft)

    def test_shear_and_bending_have_material_specific_energy(self):
        shear = total_energy(lattice("shear", 1.2), ZERO)["value"]["elastic_energy_j"]
        bend = total_energy(lattice("bend", 1.2), ZERO)["value"]["elastic_energy_j"]
        self.assertAlmostEqual(shear, 0.5 * 12.0 * 0.2**2)
        self.assertAlmostEqual(bend, 0.5 * 2.0 * 0.2**2)

    def test_wind_direction_reversal_reverses_aerodynamic_force(self):
        sheet = lattice(face=True)
        positive = compute_forces(sheet, {
            "gravity_m_s2": [0.0, 0.0, 0.0], "wind_velocity_m_s": [0.0, 0.0, 5.0]
        })["value"]["forces_n"]["a"]
        negative = compute_forces(sheet, {
            "gravity_m_s2": [0.0, 0.0, 0.0], "wind_velocity_m_s": [0.0, 0.0, -5.0]
        })["value"]["forces_n"]["a"]
        for p, n in zip(positive, negative):
            self.assertAlmostEqual(p, -n)
        self.assertGreater(positive[2], 0.0)

    def test_damping_reports_dissipation_and_reduces_energy(self):
        moving = lattice(velocity=(1.0, 0.0, 0.0))
        environment = dict(ZERO, linear_damping_n_s_m=1.0)
        before = total_energy(moving, environment)["value"]
        after_state = integrate_semi_implicit(moving, 0.01, environment)["value"]["lattice"]
        after = total_energy(after_state, environment)["value"]
        self.assertGreater(before["dissipation_power_w"], 0.0)
        self.assertLess(after["total_energy_j"], before["total_energy_j"])

    def test_adaptive_substeps_remain_finite(self):
        stiff = lattice(length=1.4)
        stiff["links"][0]["material"]["warp_stiffness_n_m"] = 1.0e6
        result = integrate_semi_implicit(stiff, 0.02, ZERO,
                                         cfl_safety=0.2, max_substeps=10000)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertGreater(result["value"]["substeps"], 1)
        values = result["value"]["lattice"]["nodes"].values()
        self.assertTrue(all(math.isfinite(x) for node in values
                            for key in ("position_m", "velocity_m_s") for x in node[key]))

    def test_typed_unknown_for_missing_material_or_unsafe_budget(self):
        invalid = lattice()
        del invalid["links"][0]["material"]
        self.assertEqual(compute_forces(invalid, ZERO)["verdict"],
                         "UNKNOWN_INVALID_INPUT")
        stiff = lattice(length=1.1)
        stiff["links"][0]["material"]["warp_stiffness_n_m"] = 1.0e9
        refused = integrate_semi_implicit(stiff, 1.0, ZERO, max_substeps=2)
        self.assertEqual(refused["verdict"], "UNKNOWN_TIMESTEP_TOO_LARGE")

    def test_deterministic_and_does_not_mutate_input(self):
        original = lattice(face=True)
        snapshot = copy.deepcopy(original)
        first = integrate_semi_implicit(original, 0.01, ZERO)
        second = integrate_semi_implicit(original, 0.01, ZERO)
        self.assertEqual(first, second)
        self.assertEqual(original, snapshot)


def six_section_cross(values=(2.0,) * 6, old=2.0, signal="temperature_k"):
    directions = ("x-", "x+", "y-", "y+", "z-", "z+")
    return {
        "old_center_state": [old],
        "sections": {
            direction: {
                "outer_state": [value],
                "signal_kind": signal,
                "material": {"coupling_j_per_unit2": index + 1.0,
                             "transfer_gain": 1.0},
            }
            for index, (direction, value) in enumerate(zip(directions, values))
        },
    }


class SixSectionContractTests(unittest.TestCase):
    def test_scan_order_and_meaning_preserving_placement_are_invariant(self):
        original = six_section_cross(values=(2.0, 2.0, 2.0, 2.0, 2.0, 2.0))
        reversed_scan = copy.deepcopy(original)
        reversed_scan["sections"] = dict(reversed(list(
            reversed_scan["sections"].items())))
        # Equal-valued sections may be permuted geometrically without changing
        # meaning; material/energy travels with the section payload.
        permuted = copy.deepcopy(original)
        payloads = list(permuted["sections"].values())
        permuted["sections"] = dict(zip(permuted["sections"], payloads[2:] + payloads[:2]))
        first = jacobi_cross_update(original)
        self.assertEqual(first, jacobi_cross_update(reversed_scan))
        shifted = jacobi_cross_update(permuted)
        self.assertEqual(first["value"]["proposed_center_state"],
                         shifted["value"]["proposed_center_state"])
        self.assertAlmostEqual(first["value"]["total_energy_j"],
                               shifted["value"]["total_energy_j"])

    def test_agreement_and_stability_are_both_required(self):
        stable = jacobi_cross_update(six_section_cross())
        self.assertEqual(stable["verdict"], "ANSWER")
        self.assertEqual(stable["value"]["committed_center_state"], [2.0])

        agreeing_but_moving = jacobi_cross_update(
            six_section_cross(values=(3.0,) * 6), stability_tolerance=0.1)
        self.assertEqual(agreeing_but_moving["verdict"], "UNKNOWN_NOT_STABLE")
        self.assertIsNone(agreeing_but_moving["value"]["committed_center_state"])

    def test_split_or_tie_is_contested_and_not_selected(self):
        split = jacobi_cross_update(
            six_section_cross(values=(1.0, 1.0, 1.0, 3.0, 3.0, 3.0)),
            agreement_tolerance=0.01, stability_tolerance=10.0)
        self.assertEqual(split["verdict"], "CONTESTED_SECTION_DISAGREEMENT")
        self.assertIsNone(split["value"]["committed_center_state"])
        self.assertEqual(split["value"]["proposed_center_state"], [2.0])

    def test_section_energy_decomposition_sums_exactly(self):
        result = jacobi_cross_update(
            six_section_cross(values=(1.0, 1.0, 1.0, 1.0, 1.0, 1.0), old=0.0),
            stability_tolerance=2.0)
        parts = result["value"]["energy_by_section_j"]
        self.assertEqual(set(parts), {"x-", "x+", "y-", "y+", "z-", "z+"})
        self.assertAlmostEqual(result["value"]["total_energy_j"], sum(parts.values()))
        self.assertEqual(result["value"]["update_scheme"], "JACOBI_SAME_OLD_STATE")

    def test_mixed_signal_meanings_are_not_fused(self):
        mixed = six_section_cross()
        mixed["sections"]["z+"]["signal_kind"] = "pressure_pa"
        result = jacobi_cross_update(mixed)
        self.assertEqual(result["verdict"], "UNKNOWN_MIXED_SIGNAL_MEANING")
        self.assertIsNone(result["value"])

    def test_coarse_medium_fine_pass_typed_outputs(self):
        layers = []
        observations = (2.0000003, 2.0000005, 2.0000006)
        for scale, resolution, observation in zip(
                ("coarse", "medium", "fine"), (0.1, 0.01, 0.001), observations):
            layers.append({"scale": scale, "target_id": "same-cloth-cell",
                           "resolution_m": resolution,
                           "input_signal_kind": "temperature_k",
                           "cross": six_section_cross(values=(observation,) * 6)})
        result = solve_cross_layers(layers, stability_tolerance=1.0e-6)
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["value"]["completed_scale"], "fine")
        self.assertEqual([item["scale"] for item in result["value"]["layers"]],
                         ["coarse", "medium", "fine"])

        layers[1]["input_signal_kind"] = "pressure_pa"
        refused = solve_cross_layers(layers)
        self.assertEqual(refused["verdict"], "UNKNOWN_MIXED_SIGNAL_MEANING")

    def test_identity_upper_layer_and_target_partition_are_rejected(self):
        layers = [{"scale": scale, "target_id": "one-target",
                   "resolution_m": resolution,
                   "input_signal_kind": "temperature_k", "cross": six_section_cross()}
                  for scale, resolution in zip(
                      ("coarse", "medium", "fine"), (0.1, 0.01, 0.001))]
        identity = solve_cross_layers(layers)
        self.assertEqual(identity["verdict"], "UNKNOWN_IDENTITY_LAYER")
        layers[1]["target_id"] = "partition-b"
        partitioned = solve_cross_layers(layers)
        self.assertEqual(partitioned["verdict"], "UNKNOWN_TARGET_MISMATCH")

    def test_facet_capacity_never_drops_physical_contributions(self):
        contributions = [
            {"id": f"c{i}", "arm": "x+", "force_n": [float(i + 1), 0.0, 0.0],
             "energy_j": float(i), "signal_kind": "cloth_force"}
            for i in range(5)
        ]
        result = build_facet_diagnostics(contributions)
        self.assertEqual(result["verdict"], "UNKNOWN_REFINEMENT_REQUIRED")
        physical = result["value"]["physical_accumulation"]
        self.assertEqual(physical["input_contribution_count"], 5)
        self.assertEqual(physical["by_arm"]["x+"]["contribution_count"], 5)
        self.assertEqual(physical["total_force_n"], [15.0, 0.0, 0.0])
        self.assertEqual(result["value"]["facet_table"]["x+"]["facets"], None)
        self.assertEqual(result["value"]["capacity"]["visible_facet_slots"], 24)

    def test_explicit_nested_refinement_retains_more_than_four_facets(self):
        contributions = [
            {"id": f"c{i}", "arm": "z-", "force_n": [0.0, 0.0, 1.0],
             "energy_j": 0.5, "signal_kind": "cloth_force",
             "refinement_cell": "near" if i < 3 else "far"}
            for i in range(6)
        ]
        result = build_facet_diagnostics(contributions)
        self.assertEqual(result["verdict"], "ANSWER")
        arm = result["value"]["facet_table"]["z-"]
        self.assertTrue(arm["refined"])
        self.assertEqual(sum(len(cell) for cell in arm["cells"].values()), 6)
        self.assertEqual(result["value"]["physical_accumulation"]["total_energy_j"], 3.0)


if __name__ == "__main__":
    unittest.main()
