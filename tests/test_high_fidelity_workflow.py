# -*- coding: utf-8 -*-
import copy
import unittest

from photoloset import high_fidelity_workflow as workflow


class HighFidelityWorkflowTests(unittest.TestCase):
    def test_capabilities_preserve_gpu_boundary(self):
        report = workflow.capabilities()
        self.assertEqual(report["verdict"], "ANSWER")
        self.assertTrue(report["gpu"]["xpbd_metal_completed_checkpoint"])
        self.assertFalse(report["gpu"]["all_stages_on_gpu"])
        self.assertFalse(report["industrial_validation"])

    def test_all_requested_stages_run_even_when_one_refuses(self):
        request = {
            "schema": workflow.SCHEMA,
            "nonlinear_shell": {},
            "production_collision": {},
            "seam_measurements": {},
        }
        frozen = copy.deepcopy(request)
        result = workflow.run(request)
        self.assertEqual(result["verdict"], workflow.FAILED)
        self.assertEqual(set(result["failed_stages"]),
                         {"nonlinear_shell", "production_collision",
                          "seam_calibration"})
        self.assertEqual(request, frozen)
        self.assertEqual(result["stages"]["yarn_needle"]["verdict"],
                         "SKIPPED_NOT_REQUESTED")

    def test_small_incompressible_stage_runs_through_workflow(self):
        count = 2 * 2 * 2
        request = {
            "schema": workflow.SCHEMA,
            "incompressible_fluid": {
                "shape": [2, 2, 2],
                "cell_size_m": 1.0,
                "time_step_s": 0.01,
                "density_kg_m3": 1.2,
                "kinematic_viscosity_m2_s": 0.0,
                "velocities_m_s": [[0.0, 0.0, 0.0] for _ in range(count)],
                "pressure_iterations": 20,
                "pressure_tolerance_s_inv": 1.0e-8,
            },
        }
        result = workflow.run(request)
        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertEqual(result["stages"]["incompressible_fluid"]["verdict"],
                         "ANSWER")
        self.assertFalse(result["industrial_validation"])

    def test_empty_workflow_is_refused(self):
        result = workflow.run({"schema": workflow.SCHEMA})
        self.assertEqual(result["verdict"], workflow.INVALID)

    def test_proof_cross_stage_is_available_without_an_llm(self):
        result = workflow.run({
            "schema": workflow.SCHEMA,
            "proof_obligations": {
                "schema": "solver.proof-cross.v1",
                "run_id": "workflow-proof",
                "solver": "incompressible-fluid",
                "obligations": [{
                    "id": "mass",
                    "predicate": "conservation",
                    "data": {"before": "1", "after": "1.0001",
                             "tolerance": "0.001"},
                }],
            },
        })
        self.assertEqual(result["verdict"], "ANSWER", result)
        self.assertEqual(result["stages"]["proof_cross"]["verdict"], "ANSWER")


if __name__ == "__main__":
    unittest.main()
