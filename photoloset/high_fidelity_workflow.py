# -*- coding: utf-8 -*-
"""Unified typed workflow for the high-fidelity reference kernels.

Stages are independent numerical or calibration contracts.  Their verdicts
are never voted or averaged into truth.  The workflow runs every requested
stage so one refusal does not hide diagnostics from another independent stage.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Mapping

from . import incompressible_fluid
from . import implicit_shell_dynamics
from . import certified_collision
from . import material_calibration
from . import nonlinear_shell_fem
from . import physics_proof_cross
from . import production_collision
from . import seam_calibration
from . import sewing_topology
from . import turbulence_validation
from . import wearer_comfort
from . import yarn_needle


ANSWER = "ANSWER"
FAILED = "UNKNOWN_HIGH_FIDELITY_STAGE"
INVALID = "UNKNOWN_HIGH_FIDELITY_WORKFLOW_INPUT"
SCHEMA = "garment.high-fidelity-workflow.v1"


def capabilities() -> Dict[str, Any]:
    return {
        "verdict": ANSWER,
        "schema": SCHEMA,
        "stages": {
            "material_calibration": material_calibration.capabilities(),
            "nonlinear_shell": nonlinear_shell_fem.capabilities(),
            "proof_cross": physics_proof_cross.capabilities(),
            "production_collision": production_collision.capabilities(),
            "certified_collision": certified_collision.capabilities(),
            "incompressible_fluid": incompressible_fluid.capabilities(),
            "implicit_shell_dynamics": implicit_shell_dynamics.capabilities(),
            "yarn_needle": yarn_needle.capabilities(),
            "seam_calibration": seam_calibration.capabilities(),
            "sewing_topology": sewing_topology.capabilities(),
            "turbulence_validation": turbulence_validation.capabilities(),
            "wearer_comfort": wearer_comfort.capabilities(),
        },
        "gpu": {
            "macos_coordinator": "IntegratedCrossPhysicsGPUCoordinator",
            "xpbd_metal_completed_checkpoint": True,
            "cpu_continuation_is_typed": True,
            "all_stages_on_gpu": False,
            "python_mcp_direct_metal_execution": False,
        },
        "industrial_validation": False,
        "stage_verdicts_are_preserved": True,
    }


def run(request: Mapping[str, Any]) -> Dict[str, Any]:
    snapshot = copy.deepcopy(request)
    if not isinstance(request, Mapping):
        return {"verdict": INVALID, "why": "request must be an object",
                "immutable_input_snapshot": snapshot}
    if request.get("schema") != SCHEMA:
        return {"verdict": INVALID, "why": f"schema must be {SCHEMA}",
                "immutable_input_snapshot": snapshot}
    runners = (
        ("material_calibration", material_calibration.calibrate, "material_measurements"),
        ("proof_cross", physics_proof_cross.verify, "proof_obligations"),
        ("nonlinear_shell", nonlinear_shell_fem.solve, "nonlinear_shell"),
        ("production_collision", production_collision.solve, "production_collision"),
        ("certified_collision", certified_collision.solve, "certified_collision"),
        ("incompressible_fluid", incompressible_fluid.step, "incompressible_fluid"),
        ("implicit_shell_dynamics", implicit_shell_dynamics.solve,
         "implicit_shell_dynamics"),
        ("yarn_needle", yarn_needle.simulate, "yarn_needle"),
        ("seam_calibration", seam_calibration.calibrate, "seam_measurements"),
        ("sewing_topology", sewing_topology.simulate, "sewing_topology"),
        ("turbulence_validation", turbulence_validation.validate,
         "turbulence_validation"),
        ("wearer_comfort", wearer_comfort.evaluate, "wearer_comfort"),
    )
    stages: Dict[str, Any] = {}
    requested = 0
    for stage, runner, key in runners:
        if key not in request:
            stages[stage] = {"verdict": "SKIPPED_NOT_REQUESTED"}
            continue
        requested += 1
        payload = request[key]
        if not isinstance(payload, Mapping):
            stages[stage] = {"verdict": INVALID,
                             "why": f"{key} must be an object"}
            continue
        stages[stage] = runner(payload)

    if requested == 0:
        return {"verdict": INVALID, "why": "at least one stage must be requested",
                "stages": stages, "immutable_input_snapshot": snapshot}

    calibration = stages["material_calibration"]
    comfort = request.get("wearer_comfort")
    if (calibration.get("verdict") == ANSWER and isinstance(comfort, Mapping)
            and comfort.get("material_calibration_digest")
            != calibration.get("calibration_digest")):
        stages["wearer_comfort"] = {
            "verdict": "UNKNOWN_WEARER_CALIBRATION_BINDING",
            "why": "wearer trial is not bound to the calibration from this workflow",
            "expected": calibration.get("calibration_digest"),
            "actual": comfort.get("material_calibration_digest"),
        }

    success = {
        "material_calibration": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "proof_cross": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "nonlinear_shell": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "production_collision": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "certified_collision": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "incompressible_fluid": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "implicit_shell_dynamics": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "yarn_needle": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "seam_calibration": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "sewing_topology": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "turbulence_validation": {ANSWER, "SKIPPED_NOT_REQUESTED"},
        "wearer_comfort": {wearer_comfort.REVIEW, "SKIPPED_NOT_REQUESTED"},
    }
    failed = [name for name, result in stages.items()
              if result.get("verdict") not in success[name]]
    proof_run_id = str(request.get("run_id", "high-fidelity-run"))
    automatic_proof = physics_proof_cross.verify_stage_results(proof_run_id, stages)
    return {
        "verdict": ANSWER if not failed else FAILED,
        "schema": "garment.high-fidelity-result.v1",
        "failed_stages": failed,
        "stages": stages,
        "automatic_proof_cross": automatic_proof,
        "gpu_boundary": capabilities()["gpu"],
        "industrial_validation": False,
        "truth_contract": {
            "stage_verdicts_preserved": True,
            "unknown_is_not_imputed": True,
            "simulation_is_not_measurement": True,
            "review_is_not_medical_safety": True,
        },
        "immutable_input_snapshot": snapshot,
    }


__all__ = ["ANSWER", "FAILED", "INVALID", "SCHEMA", "capabilities", "run"]
