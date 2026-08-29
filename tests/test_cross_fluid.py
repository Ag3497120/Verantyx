# -*- coding: utf-8 -*-
import copy
import math
import unittest

from photoloset.cross_fluid import (
    ANSWER,
    CFL_UNSAFE,
    DOMAIN_MISS,
    INVALID_INPUT,
    capabilities,
    couple,
)


POSITIONS = ((0.25, 0.25, 0.5), (0.75, 0.25, 0.5),
             (0.25, 0.75, 0.5), (0.75, 0.75, 0.5))
FACES = ((0, 1, 2), (1, 3, 2))
VELOCITIES = ((0.0, 0.0, 0.0),) * 4
MATERIAL = {"drag_coefficient": 1.2, "lift_coefficient": 0.0,
            "permeability": 0.0}


def grid(velocity=(0.0, 0.0, -1.0), **overrides):
    value = {
        "density_kg_m3": 1.2,
        "cell_size_m": 1.0,
        "cfl_safety": 0.5,
        "grid": {"origin_m": (0.0, 0.0, 0.0), "shape": (1, 1, 1),
                 "velocities_m_s": (velocity,)},
    }
    value.update(overrides)
    return value


def solve(**overrides):
    arguments = dict(
        positions=POSITIONS, velocities=VELOCITIES, faces=FACES,
        face_material_ids=("cloth", "cloth"), materials={"cloth": MATERIAL},
        fluid=grid(), time_step_s=0.1,
    )
    arguments.update(overrides)
    return couple(**arguments)


class CrossFluidTests(unittest.TestCase):
    def test_capabilities_are_typed_and_honest(self):
        report = capabilities()
        self.assertEqual(report["verdict"], ANSWER)
        self.assertTrue(report["deterministic"])
        self.assertTrue(report["features"]["two_way_momentum_bookkeeping"])
        self.assertFalse(report["features"]["dns"])
        self.assertFalse(report["features"]["complete_cfd"])
        self.assertFalse(report["features"]["pressure_projection"])

    def test_drag_and_two_way_grid_momentum_balance(self):
        result = solve()
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["update_scheme"], "JACOBI_SAME_OLD_STATE")
        self.assertTrue(result["momentum_bookkeeping"]["balanced"])
        cloth = result["momentum_bookkeeping"]["cloth_impulse_n_s"]
        fluid = result["momentum_bookkeeping"]["fluid_reaction_impulse_n_s"]
        self.assertLess(cloth[2], 0.0)
        for a, b in zip(cloth, fluid):
            self.assertAlmostEqual(a, -b, places=14)
        old = result["fluid"]["grid"]["old_velocities_m_s"][0][2]
        new = result["fluid"]["grid"]["new_velocities_m_s"][0][2]
        self.assertGreater(new, old)

    def test_permeability_one_transmits_no_force(self):
        porous = dict(MATERIAL, permeability=1.0)
        result = solve(materials={"cloth": porous})
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual(result["cloth"]["total_impulse_n_s"], [0.0, 0.0, 0.0])

    def test_lift_is_per_face_and_finite(self):
        material = dict(MATERIAL, lift_coefficient=0.8)
        result = solve(materials={"cloth": material},
                       fluid=grid((1.0, 0.0, -1.0)), time_step_s=0.05)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertTrue(any(abs(component) > 0.0
                            for component in result["faces"][0]["lift_force_n"]))
        self.assertTrue(all(math.isfinite(component)
                            for face in result["faces"]
                            for component in face["total_force_n"]))

    def test_face_order_does_not_change_aggregated_old_state_result(self):
        forward = solve()
        reverse = solve(faces=tuple(reversed(FACES)),
                        face_material_ids=("cloth", "cloth"))
        self.assertEqual(forward["cloth"], reverse["cloth"])
        self.assertEqual(forward["fluid"], reverse["fluid"])
        self.assertEqual(forward["momentum_bookkeeping"],
                         reverse["momentum_bookkeeping"])

    def test_vortex_modes_are_deterministic_and_id_order_independent(self):
        modes = (
            {"id": "b", "center_m": (0.5, 0.5, 0.0), "axis": (0, 0, 1),
             "circulation_m2_s": 0.2, "core_radius_m": 0.1},
            {"id": "a", "center_m": (0.0, 0.0, 0.0), "axis": (0, 0, 1),
             "circulation_m2_s": -0.1, "core_radius_m": 0.2},
        )
        fluid = {"density_kg_m3": 1.2, "cell_size_m": 1.0,
                 "cfl_safety": 1.0, "vortex_modes": modes}
        first = solve(fluid=fluid, time_step_s=0.01)
        second = solve(fluid=dict(fluid, vortex_modes=tuple(reversed(modes))),
                       time_step_s=0.01)
        self.assertEqual(first, second)
        self.assertIsNone(first["fluid"]["grid"])
        reaction = first["fluid"]["external_reservoir_reaction_impulse_n_s"]
        self.assertEqual(reaction,
                         first["fluid"]["total_reaction_impulse_n_s"])

    def test_cfl_unsafe_is_a_typed_refusal(self):
        result = solve(fluid=grid((0.0, 0.0, -10.0)), time_step_s=0.1)
        self.assertEqual(result["verdict"], CFL_UNSAFE)
        self.assertEqual(result["cfl"]["required_substeps"], 2)

    def test_domain_and_invalid_inputs_are_typed(self):
        outside = solve(positions=((2.0, 2.0, 2.0), (2.1, 2.0, 2.0),
                                   (2.0, 2.1, 2.0)),
                        velocities=((0.0, 0.0, 0.0),) * 3,
                        faces=((0, 1, 2),), face_material_ids=("cloth",))
        self.assertEqual(outside["verdict"], DOMAIN_MISS)
        invalid = solve(materials={"cloth": dict(MATERIAL, permeability=1.1)})
        self.assertEqual(invalid["verdict"], INVALID_INPUT)

    def test_inputs_are_not_mutated(self):
        positions = [list(value) for value in POSITIONS]
        fluid = grid()
        snapshot = copy.deepcopy((positions, fluid))
        result = solve(positions=positions, fluid=fluid)
        self.assertEqual(result["verdict"], ANSWER)
        self.assertEqual((positions, fluid), snapshot)


if __name__ == "__main__":
    unittest.main()
