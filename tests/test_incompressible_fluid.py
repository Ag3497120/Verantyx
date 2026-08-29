# -*- coding: utf-8 -*-
import copy
import math
import unittest

from photoloset.incompressible_fluid import (
    ANSWER,
    CFL_UNSAFE,
    DIFFUSION_UNSAFE,
    INVALID_INPUT,
    capabilities,
    step,
)


SHAPE = (4, 4, 4)
COUNT = 4 * 4 * 4


def request(velocities=None, **overrides):
    value = {
        "shape": SHAPE,
        "cell_size_m": 1.0,
        "density_kg_m3": 1.2,
        "kinematic_viscosity_m2_s": 0.0,
        "time_step_s": 0.05,
        "velocities_m_s": velocities or ((0.0, 0.0, 0.0),) * COUNT,
        "boundary": "periodic",
        "cfl_safety": 0.8,
        "pressure_iterations": 600,
        "pressure_tolerance_s_inv": 1.0e-10,
    }
    value.update(overrides)
    return value


class IncompressibleFluidTests(unittest.TestCase):
    def test_capabilities_are_honest_and_typed(self):
        report = capabilities()
        self.assertEqual(report["verdict"], ANSWER)
        self.assertTrue(report["deterministic"])
        self.assertTrue(report["features"]["pressure_projection"])
        self.assertFalse(report["features"]["dns"])
        self.assertFalse(report["features"]["complete_cfd"])
        self.assertEqual(report["verification"]["smagorinsky_les"],
                         "IMPLEMENTED_UNCALIBRATED_NOT_VALIDATED")

    def test_uniform_periodic_flow_is_an_exact_known_case(self):
        uniform = ((0.2, -0.1, 0.05),) * COUNT
        result = step(request(uniform, kinematic_viscosity_m2_s=0.02))
        self.assertEqual(result["verdict"], ANSWER)
        for actual in result["state"]["velocities_m_s"]:
            for component, expected in zip(actual, uniform[0]):
                self.assertAlmostEqual(component, expected, places=13)
        self.assertLess(result["diagnostics"]["divergence_after_projection"]
                        ["linf_s_inv"], 1.0e-13)

    def test_pressure_projection_reduces_discrete_divergence(self):
        velocity = []
        for flat_index in range(COUNT):
            i = flat_index % 4
            j = (flat_index // 4) % 4
            velocity.append((0.15 * math.sin(2.0 * math.pi * i / 4),
                             0.1 * math.cos(2.0 * math.pi * j / 4), 0.0))
        result = step(request(tuple(velocity)))
        self.assertEqual(result["verdict"], ANSWER)
        before = result["diagnostics"]["divergence_before_projection"]["l2_rms_s_inv"]
        after = result["diagnostics"]["divergence_after_projection"]["l2_rms_s_inv"]
        self.assertGreater(before, 1.0e-3)
        self.assertLess(after, before * 1.0e-6)
        self.assertEqual(result["terminal_verdict"], "PRESSURE_TOLERANCE_MET")

    def test_viscosity_decays_a_divergence_free_shear_mode(self):
        velocity = []
        for flat_index in range(COUNT):
            i = flat_index % 4
            velocity.append((0.0, (-1.0 if i % 2 else 1.0) * 0.1, 0.0))
        result = step(request(tuple(velocity), kinematic_viscosity_m2_s=0.1,
                              time_step_s=0.05))
        self.assertEqual(result["verdict"], ANSWER)
        old_energy = math.fsum(sum(c*c for c in value) for value in velocity)
        new_energy = math.fsum(sum(c*c for c in value)
                               for value in result["state"]["velocities_m_s"])
        self.assertLess(new_energy, old_energy)
        # The alternating periodic mode has discrete Laplacian -4u/h², so one
        # explicit step has the exact amplification 1 - 4*nu*dt/h² = 0.98.
        for old, new in zip(velocity, result["state"]["velocities_m_s"]):
            self.assertAlmostEqual(new[1], 0.98 * old[1], places=12)

    def test_solid_boundaries_have_zero_normal_flux_and_mass_ledger(self):
        velocity = ((0.1, 0.2, -0.1),) * COUNT
        result = step(request(velocity, boundary="solid_free_slip"))
        self.assertEqual(result["verdict"], ANSWER)
        for flat_index, value in enumerate(result["state"]["velocities_m_s"]):
            i = flat_index % 4
            j = (flat_index // 4) % 4
            k = flat_index // 16
            if i == 3:
                self.assertEqual(value[0], 0.0)
            if j == 3:
                self.assertEqual(value[1], 0.0)
            if k == 3:
                self.assertEqual(value[2], 0.0)
        ledger = result["diagnostics"]["mass_ledger"]
        self.assertEqual(ledger["mass_change_kg"], 0.0)
        self.assertAlmostEqual(ledger["boundary_volume_flow_after_m3_s"], 0.0,
                               places=11)

    def test_no_slip_uses_antisymmetric_tangential_viscous_ghosts(self):
        uniform = ((0.1, 0.1, 0.1),) * COUNT
        free = step(request(uniform, boundary="solid_free_slip",
                            kinematic_viscosity_m2_s=0.1))
        no_slip = step(request(uniform, boundary="solid_no_slip",
                               kinematic_viscosity_m2_s=0.1))
        self.assertEqual(no_slip["verdict"], ANSWER)
        # At x=0, y is tangential. The anti-symmetric no-slip ghost damps it
        # more strongly than the mirrored free-slip ghost.
        self.assertLess(abs(no_slip["state"]["velocities_m_s"][0][1]),
                        abs(free["state"]["velocities_m_s"][0][1]))
        self.assertLess(no_slip["diagnostics"]["divergence_after_projection"]
                        ["l2_rms_s_inv"], 1.0e-8)

    def test_cfl_and_diffusion_refusals_are_typed(self):
        fast = step(request(((20.0, 0.0, 0.0),) * COUNT, time_step_s=0.1))
        self.assertEqual(fast["verdict"], CFL_UNSAFE)
        viscous = step(request(kinematic_viscosity_m2_s=1.0, time_step_s=0.2))
        self.assertEqual(viscous["verdict"], DIFFUSION_UNSAFE)

    def test_smagorinsky_is_deterministic_and_marked_unvalidated(self):
        velocity = tuple((0.01 * (index % 4), 0.02 * ((index // 4) % 4), 0.0)
                         for index in range(COUNT))
        raw = request(velocity, les={"model": "smagorinsky", "coefficient": 0.12})
        first = step(raw)
        second = step(raw)
        self.assertEqual(first, second)
        self.assertEqual(first["diagnostics"]["effective_viscosity_m2_s"]
                         ["les_verification"],
                         "IMPLEMENTED_UNCALIBRATED_NOT_VALIDATED")
        self.assertGreater(first["diagnostics"]["effective_viscosity_m2_s"]
                           ["maximum"], 0.0)

    def test_input_is_immutable_and_bad_request_is_typed(self):
        raw = request()
        snapshot = copy.deepcopy(raw)
        self.assertEqual(step(raw)["verdict"], ANSWER)
        self.assertEqual(raw, snapshot)
        bad = request()
        bad["velocities_m_s"] = ((0.0, 0.0, 0.0),)
        self.assertEqual(step(bad)["verdict"], INVALID_INPUT)


if __name__ == "__main__":
    unittest.main()
