# -*- coding: utf-8 -*-
import json
import unittest

from photoloset import mcp


def call(name, arguments=None):
    response = mcp.handle({"method": "tools/call", "params": {
        "name": name, "arguments": arguments or {}}})
    return json.loads(response["content"][0]["text"])


class HighFidelityMCPTests(unittest.TestCase):
    def test_capability_door_publishes_honest_gpu_boundary(self):
        result = call("high_fidelity_capabilities")
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertFalse(result["gpu"]["all_stages_on_gpu"])
        self.assertFalse(result["industrial_validation"])

    def test_workflow_rejects_untyped_input(self):
        result = call("high_fidelity_workflow", {"json_text": "{}"})
        self.assertEqual(result["verdict"],
                         "UNKNOWN_HIGH_FIDELITY_WORKFLOW_INPUT")

    def test_small_fluid_case_runs_over_mcp(self):
        count = 8
        request = {
            "schema": "garment.high-fidelity-workflow.v1",
            "incompressible_fluid": {
                "shape": [2, 2, 2],
                "cell_size_m": 1.0,
                "time_step_s": 0.01,
                "density_kg_m3": 1.2,
                "kinematic_viscosity_m2_s": 0.0,
                "velocities_m_s": [[0.0, 0.0, 0.0]
                                     for _ in range(count)],
                "pressure_iterations": 20,
                "pressure_tolerance_s_inv": 1.0e-8,
            },
        }
        result = call("high_fidelity_workflow",
                      {"json_text": json.dumps(request)})
        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertEqual(result["stages"]["incompressible_fluid"]["verdict"],
                         "ANSWER")

    def test_each_stage_has_a_published_tool(self):
        expected = {
            "nonlinear_shell_solve", "production_collision_solve",
            "incompressible_fluid_step", "yarn_needle_simulate",
            "seam_calibrate", "wearer_comfort_evaluate",
            "proof_cross_verify", "certified_collision_solve",
            "implicit_shell_dynamics_solve", "turbulence_validate",
            "sewing_topology_simulate",
        }
        self.assertTrue(expected.issubset(mcp.TOOLS))

    def test_exact_proof_cross_obligation_runs_over_mcp(self):
        request = {
            "schema": "solver.proof-cross.v1", "run_id": "mcp-proof",
            "solver": "test", "obligations": [{
                "id": "identity", "predicate": "exact_equal",
                "data": {"left": "1/3", "right": "2/6"},
            }],
        }
        result = call("proof_cross_verify",
                      {"json_text": json.dumps(request)})
        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertEqual(result["obligations"][0]["verdict"],
                         "CERTIFIED_EXACT")


if __name__ == "__main__":
    unittest.main()
