#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from photoloset import corpus_manifest
from photoloset import mcp
from photoloset import mannequin


class GarmentMCPWorkflowTests(unittest.TestCase):
    def isolated_store(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        stack = patch.multiple(mcp, HOME=root, PROJECTS=root / "projects",
                               CURRENT=root / "current_project")
        stack.start()
        self.addCleanup(stack.stop)
        self.addCleanup(temporary.cleanup)

    def test_point_apex_is_a_zero_radius_cross_section(self):
        for theta in (0.0, 0.7, 1.57, 3.14):
            self.assertEqual(mannequin._ellipse_radius(0.0, 0.0, theta), 0.0)

    def test_beginner_command_job_preview_approval_and_undo(self):
        self.isolated_store()
        command = json.loads(mcp.TOOLS["garment_command"](
            "30番から35番を3cm広げて"))
        self.assertEqual(command["intent"], "ADJUST_PATTERN_SPAN")
        self.assertFalse(command["commit"])

        job = json.loads(mcp.TOOLS["garment_job"]("", "workflow-test"))
        transition = {"event": {"kind": "TRANSITION",
                                 "state": "IMAGE_RECEIVED",
                                 "artifacts": {"image": "sha256:image"},
                                 "data": {"ease_cm": 0}}}
        job = json.loads(mcp.TOOLS["garment_job"](json.dumps(transition)))
        self.assertEqual(job["snapshot"]["state"], "IMAGE_RECEIVED")

        preview_event = {"event": {
            "kind": "PREVIEW", "command_id": command["command_id"],
            "after_data": {"ease_cm": 3},
            "changed_addresses": ["pattern.30:35"],
            "validation_results": [{"verdict": "PASS"}]}}
        job = json.loads(mcp.TOOLS["garment_job"](
            json.dumps(preview_event)))
        preview = job["result"]
        self.assertEqual(job["snapshot"]["data"]["ease_cm"], 0)

        approved = {"event": {"kind": "APPROVE",
                               "preview_id": preview["preview_id"],
                               "digest": preview["digest"],
                               "approver": "Tester"}}
        job = json.loads(mcp.TOOLS["garment_job"](json.dumps(approved)))
        self.assertEqual(job["snapshot"]["data"]["ease_cm"], 3)
        job = json.loads(mcp.TOOLS["garment_job"](json.dumps(
            {"event": {"kind": "UNDO", "command_id": "undo-test"}})))
        self.assertEqual(job["snapshot"]["data"]["ease_cm"], 0)
        self.assertEqual(job["result"]["kind"], "COMPENSATING_UNDO")

    def test_integrated_workflow_binds_edit_approval_and_undo(self):
        self.isolated_store()
        command = json.loads(mcp.TOOLS["garment_command"](
            "30番から35番を3cm広げて"))
        previewed = json.loads(mcp.TOOLS["garment_workflow"](
            json.dumps(command)))
        self.assertEqual(previewed["verdict"], "ANSWER")
        preview = previewed["result"]
        self.assertEqual(preview["changed_addresses"], ["pattern.30:35"])
        self.assertEqual(previewed["snapshot"]["data"], {})

        approval_command = {
            "schema": "garment.command.v1", "command_id": "approve-1",
            "intent": "APPROVE", "target": {},
            "operation": {"preview_digest": preview["digest"]},
            "commit": True, "provenance": "HUMAN_INPUT"}
        approved = json.loads(mcp.TOOLS["garment_workflow"](
            json.dumps(approval_command), "Tester"))
        self.assertEqual(approved["verdict"], "ANSWER")
        self.assertEqual(approved["snapshot"]["data"]["pattern_edits"][0]
                         ["normalized_value_cm"], 3)

        undo_command = {
            "schema": "garment.command.v1", "command_id": "undo-1",
            "intent": "UNDO", "target": {}, "operation": {},
            "commit": True, "provenance": "HUMAN_INPUT"}
        undone = json.loads(mcp.TOOLS["garment_workflow"](
            json.dumps(undo_command)))
        self.assertEqual(undone["verdict"], "ANSWER")
        self.assertEqual(undone["snapshot"]["data"], {})

    def test_image_generation_requires_and_uses_confirmed_clothing_outline(self):
        self.isolated_store()
        command = {
            "schema": "garment.command.v1", "command_id": "image-1",
            "intent": "GENERATE_FROM_IMAGE",
            "target": {"kind": "SELECTED_IMAGE", "reference": "/tmp/front.png"},
            "operation": {}, "commit": False,
            "provenance": "HUMAN_INPUT",
        }
        missing = json.loads(mcp.TOOLS["garment_workflow"](
            json.dumps(command)))
        self.assertEqual(missing["verdict"],
                         "UNKNOWN_GARMENT_REGION_CONFIRMATION_REQUIRED")

        outline = {"outline": [[0, 0], [20, 0], [20, 40], [0, 40]],
                   "width_px": 20, "height_px": 40,
                   "source": "human-confirmed", "fixture": False}
        generated = {"verdict": "ANSWER", "pieces": [{"piece_id": "front"}],
                     "decisions": {"proposed": []},
                     "hops": [{"name": "structure", "verdict": "ANSWER"}]}
        with patch("photoloset.photo_to_pattern.run",
                   return_value=generated) as run:
            previewed = json.loads(mcp.TOOLS["garment_workflow"](
                json.dumps({"command": command,
                            "context": {"confirmed_outline": outline}})))
        self.assertEqual(previewed["verdict"], "ANSWER")
        self.assertEqual(previewed["result"]["changed_addresses"],
                         ["image.confirmed_clothing", "pattern.generated"])
        self.assertEqual(previewed["snapshot"]["data"], {})
        self.assertEqual(run.call_args.args[0], outline)

    def test_open_ended_model_requirements_are_preview_only(self):
        self.isolated_store()
        command = {
            "schema": "garment.command.v1", "command_id": "requirements-1",
            "intent": "SET_REQUIREMENTS", "target": {"kind": "ACTIVE_GARMENT"},
            "operation": {"kind": "SET_REQUIREMENTS", "requirements": [
                {"kind": "STANDARD_SIZE", "target": "whole garment", "text": "M"},
                {"kind": "DETAIL", "target": "collar", "text": "more rounded"},
                {"kind": "GARMENT_MEASUREMENT", "target": "finished length",
                 "value": 110, "unit": "cm"},
            ]},
            "commit": False, "provenance": "MODEL_PROPOSAL",
        }
        previewed = json.loads(mcp.TOOLS["garment_workflow"](
            json.dumps(command)))
        self.assertEqual(previewed["verdict"], "ANSWER")
        self.assertEqual(previewed["snapshot"]["data"], {})
        preview = previewed["result"]
        self.assertEqual(len(preview["after"]["data"]["design_requirements"]), 3)
        checks = {row["check"]: row["verdict"]
                  for row in preview["validation_results"]}
        self.assertEqual(checks["typed_requirement_ir"], "PASS")
        self.assertEqual(checks["standard_size_chart_required"], "REVIEW")

    def test_xpbd_is_reachable_and_reports_the_real_backend(self):
        material = {"areal_density_kg_m2": .2,
                    "warp_stiffness_n_m": 800,
                    "weft_stiffness_n_m": 80,
                    "shear_stiffness_n_m": 40,
                    "bending_stiffness_n_m": .02,
                    "damping_ratio": .02}
        request = {"solver": "xpbd",
                   "vertices": [[0, 1, 0], [1, 1, 0],
                                [1, 0, 0], [0, 0, 0]],
                   "faces": [[0, 1, 2], [0, 2, 3]],
                   "face_material_ids": ["cloth", "cloth"],
                   "materials": {"cloth": material},
                   "fixed_vertices": [0, 1], "steps": 1}
        result = json.loads(mcp.TOOLS["cross_cloth_simulate"](
            json.dumps(request)))
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["diagnostics"]["projection"],
                         "XPBD_JACOBI_SAME_OLD_STATE")
        capabilities = json.loads(mcp.TOOLS["cross_cloth_capabilities"]())
        self.assertFalse(capabilities["gpu"]["available"])
        self.assertTrue(capabilities["metal_app_backend"]["implemented"])
        self.assertFalse(capabilities["metal_app_backend"]
                         ["wired_to_python_mcp"])

    def test_geometric_overlay_is_reachable_without_model_or_corpus(self):
        self.isolated_store()
        mannequin = {"verdict": "ANSWER",
                     "_levels": [[0.0, 10.0, 7.0], [100.0, 10.0, 7.0]]}
        view = {
            "frame_id": "front", "source": "front.png",
            "azimuth_deg": 0.0, "cm_per_unit": 1.0,
            "blur_sigma_units": 0.0, "registration_error_units": 0.0,
            "outline": [[-12, 0], [-12, 100], [12, 100], [12, 0]],
        }
        with patch.object(mcp._mq, "build", return_value=mannequin):
            result = json.loads(mcp.TOOLS["geometric_garment_overlay"](
                json.dumps({"garment": "dress", "views": [view],
                            "segments": 8, "height_steps": 2})))
        self.assertTrue(result["verdict"].startswith("UNKNOWN_"))
        self.assertEqual(len(result["overlays"][0]["primitives"]), 2)
        self.assertIsNone(result["confirmed_structure"])
        self.assertTrue(all(candidate["state"] == "PROPOSED"
                            for candidate in result["structure_candidates"]))

    def test_mannequin_dress_uses_the_supplied_photo_surface(self):
        surface = {
            "verdict": "ANSWER",
            "verts": [[2, 3, 0], [0, 4, 2], [2, 5, 2]],
            "faces": [[0, 1, 2]],
        }
        result = json.loads(mcp.TOOLS["mannequin_dress"](
            garment_json=json.dumps({"garment_surface": surface}),
            gap_cm=1.0))
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["source"], "photo_pattern.garment_surface")
        self.assertEqual(result["points"][:2],
                         [[3.0, 3.0, 0.0], [0.0, 4.0, 3.0]])
        self.assertEqual(result["edges"], [[0, 1], [1, 2], [2, 0]])
        self.assertEqual(result["owner"], ["photo_pattern"] * 3)

    def test_photo_pattern_preview_mannequin_is_proposed_and_not_saved(self):
        self.isolated_store()
        outline = {"outline": [[0, 0], [20, 0], [20, 40], [0, 40]],
                   "width_px": 20, "height_px": 40,
                   "source": "human-confirmed", "fixture": False}

        def generated(_outline, measures, **_kwargs):
            used = {entry.spot: entry.value for entry in measures.entries}
            self.assertEqual(used, {"chest": 88.0, "waist": 68.0,
                                    "hip": 94.0, "body_length": 140.0})
            return {"verdict": "ANSWER", "pieces": [],
                    "assumptions_used": [], "decisions": {}}

        with patch("photoloset.photo_to_pattern.run", side_effect=generated):
            result = json.loads(mcp.TOOLS["photo_pattern"](
                json.dumps(outline), preview_mannequin=True))
        self.assertEqual(result["preview_mannequin"]["state"], "PROPOSED")
        self.assertTrue(result["preview_mannequin"]["not_measurement"])
        self.assertEqual(mcp._measures().entries, [])

    def test_photo_pattern_repair_exposes_the_bounded_transcript(self):
        repaired = {"rounds": 1, "stop_reason": "done", "sewable": True,
                    "transcript": [{"round": 1, "repair": "surface_split",
                                    "verdict": "ANSWER", "applied": True}],
                    "pattern": {"verdict": "ANSWER", "pieces": []}}
        with patch("photoloset.repairs.make_sewable",
                   return_value=repaired) as run:
            result = json.loads(mcp.TOOLS["photo_pattern_repair"](
                json.dumps({"verdict": "ANSWER", "pieces": []}), budget=4))
        self.assertEqual(result["verdict"], "ANSWER")
        self.assertEqual(result["transcript"][0]["repair"], "surface_split")
        self.assertEqual(run.call_args.kwargs["budget"], 4)

    def test_corpus_rights_gate_is_reachable(self):
        manifest = {
            "schema": corpus_manifest.SCHEMA, "name": "fixture", "version": "1",
            "license": {"url": "https://example.invalid/license",
                        "rights": {"commercial_use": "unknown",
                                   "derivatives": "allowed",
                                   "redistribution": "allowed"}},
            "lineage": [{"source": "fixture"}],
            "modalities": ["patterns_2d"],
            "record_format": {"units": "SI", "schema_url": "schema.json"}}
        result = json.loads(mcp.TOOLS["corpus_manifest_check"](
            json.dumps(manifest), "sewing", True))
        self.assertEqual(result["verdict"],
                         "UNKNOWN_CORPUS_COMMERCIAL_RIGHTS")

    def test_structure_candidates_and_pattern_transform_are_one_mcp_surface(self):
        structure = {
            "schema": "garment.structure.v1",
            "nodes": [{"node_id": "shell", "kind": "BODY_SHELL",
                       "dimensions": {"height_cm": 90,
                                      "circumference_cm": 92}}],
            "operations": []}
        built = json.loads(mcp.TOOLS["garment_structure"](
            json.dumps(structure)))
        self.assertEqual(built["verdict"], "ANSWER")

        candidates = [{
            "candidate_id": name,
            "payload": {"closure": closure},
            "constraints": [{"front_silhouette": "consistent"}],
            "assumptions": ["back is not observed"],
            "source_evidence": [{"image": "sha256:front"}]}
            for name, closure in (("back-a", "zip"),
                                  ("back-b", "buttons"))]
        sheet = json.loads(mcp.TOOLS["garment_candidates"](json.dumps({
            "kind": "back", "evidence": {"view": "front"},
            "candidates": candidates})))
        self.assertEqual(sheet["verdict"], "PROPOSED")
        chosen = sheet["candidates"][0]["digest"]
        approval = json.loads(mcp.TOOLS["garment_candidates"](
            json.dumps({"sheet": sheet}), "approve", chosen, "Tester"))
        self.assertEqual(approval["verdict"], "APPROVED")

        transformed = json.loads(mcp.TOOLS["garment_pattern_transform"](
            json.dumps({
                "pattern": {"piece_id": "front",
                            "outline": [[0, 0], [20, 0], [20, 30], [0, 30]]},
                "operation": {"kind": "PLEAT", "edge": "e0",
                              "count": 2, "depth_cm": 2}})))
        self.assertEqual(transformed["verdict"], "ANSWER")
        self.assertEqual(transformed["changed_addresses"], ["e0"])

    def test_parts_ir_completion_is_a_typed_mcp_authority_boundary(self):
        request = {
            "parts_ir": {
                "schema": "garment.parts-ir.v1",
                "candidate_count": 2,
                "parts": [{
                    "part_id": "visible-body",
                    "kind": "BODY_SHELL",
                    "layer": 0,
                    "placement": "front torso",
                    "visible_basis": {
                        "state": "PROPOSED",
                        "basis": "vision model proposed a visible torso shell",
                        "breaks_when": "another view contradicts the proposal",
                    },
                }],
            },
            "use_bounded_preview_profile": True,
        }
        result = json.loads(mcp.TOOLS["garment_parts_ir_complete"](
            json.dumps(request)))
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(result["candidate_count"], 2)
        self.assertFalse(result["authority"]["approved"])
        self.assertFalse(result["provenance"]["image_measurements_claimed"])
        for candidate in result["candidates"]:
            self.assertEqual(candidate["state"], "PROPOSED")
            self.assertEqual(candidate["schema"], "garment.structure.v1")
            evidence = candidate["nodes"][0]["attributes"][
                "dimension_evidence"]
            self.assertTrue(all(row["not_measured_from_image"]
                                for row in evidence.values()))

        missing_source = json.loads(mcp.TOOLS[
            "garment_parts_ir_complete"](json.dumps({
                "parts_ir": request["parts_ir"],
            })))
        self.assertEqual(
            missing_source["verdict"],
            "UNKNOWN_PARTS_IR_MEASUREMENT_SOURCE_REQUIRED",
        )

        conflicting_profile = json.loads(mcp.TOOLS[
            "garment_parts_ir_complete"](json.dumps({
                **request,
                "preview_profile": {"profile_id": "caller-profile"},
            })))
        self.assertEqual(conflicting_profile["verdict"],
                         "UNKNOWN_BAD_ARGUMENTS")

    def test_parts_ir_topology_is_a_proposal_only_mcp_boundary(self):
        def part(part_id, kind, dimensions, **semantics):
            row = {
                "part_id": part_id,
                "kind": kind,
                "layer": semantics.pop("layer", 0),
                "placement": semantics.pop("placement", "front torso"),
                "visible_basis": {
                    "state": "PROPOSED",
                    "basis": f"vision model proposed {part_id}",
                    "breaks_when": f"another view rejects {part_id}",
                },
                "dimensions": dimensions,
            }
            row.update(semantics)
            return row

        parts = [
            part("body", "BODY_SHELL", {
                "height_cm": 42.0,
                "circumference_cm": 80.0,
                "bottom_circumference_cm": 80.0,
            }, garment_unit="dress"),
            part("skirt", "FLARE", {
                "height_cm": 65.0,
                "top_circumference_cm": 80.0,
                "bottom_circumference_cm": 120.0,
            }, placement="lower body", garment_unit="dress",
                 attached_to="body"),
        ]
        completed = json.loads(mcp.TOOLS["garment_parts_ir_complete"](
            json.dumps({
                "parts_ir": {
                    "schema": "garment.parts-ir.v1",
                    "candidates": [
                        {"candidate_id": "back-a", "state": "PROPOSED",
                         "parts": parts},
                        {"candidate_id": "back-b", "state": "PROPOSED",
                         "parts": parts},
                    ],
                },
            })))
        self.assertEqual(completed["verdict"], "PROPOSED")

        result = json.loads(mcp.TOOLS["garment_parts_ir_topology"](
            json.dumps({"completion": completed})))
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(result["candidate_count"], 2)
        self.assertFalse(result["authority"]["approved"])
        for candidate in result["candidates"]:
            self.assertEqual(candidate["state"], "PROPOSED")
            self.assertEqual(candidate["operations"][0]["kind"], "JOIN")
            self.assertEqual(
                candidate["operations"][0]["parameters"]["relation_source"],
                "MODEL_SUPPLIED_ATTACHED_TO_PLUS_TYPED_RULE",
            )

        bad = json.loads(mcp.TOOLS["garment_parts_ir_topology"](
            json.dumps({"completion": {"verdict": "ANSWER"}})))
        self.assertEqual(
            bad["verdict"], "UNKNOWN_PARTS_TOPOLOGY_COMPLETION_STATE")

    def test_parts_ir_pipeline_binds_candidate_3d_and_pattern(self):
        def body(part_id, circumference):
            return {
                "part_id": part_id,
                "kind": "BODY_SHELL",
                "layer": 0,
                "placement": "front torso",
                "visible_basis": {
                    "state": "PROPOSED",
                    "basis": f"vision proposed {part_id}",
                    "breaks_when": "another view rejects it",
                },
                "dimensions": {
                    "height_cm": 44.0,
                    "circumference_cm": circumference,
                },
            }
        result = json.loads(mcp.TOOLS["garment_parts_ir_pipeline"](
            json.dumps({
                "parts_ir": {
                    "schema": "garment.parts-ir.v1",
                    "candidates": [
                        {"candidate_id": "rear-a",
                         "parts": [body("body-a", 86.0)]},
                        {"candidate_id": "rear-b",
                         "parts": [body("body-b", 98.0)]},
                    ],
                },
                "use_bounded_preview_profile": True,
            })))
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(result["successful_candidate_count"], 2)
        for candidate in result["candidates"]:
            binding = candidate["artifact_binding"]
            self.assertTrue(binding["same_structure_digest"])
            self.assertEqual(binding["preview_structure_digest"],
                             binding["pattern_structure_digest"])
            self.assertFalse(candidate["flat_pattern"]["manufacturing_ready"])

        invalid = json.loads(mcp.TOOLS["garment_parts_ir_pipeline"](
            json.dumps({
                "parts_ir": {"schema": "garment.parts-ir.v1"},
                "use_bounded_preview_profile": True,
                "radial_segments": 4,
            })))
        self.assertEqual(invalid["verdict"], "UNKNOWN_BAD_ARGUMENTS")

    def test_factory_compiles_the_approved_candidate_not_the_generic_body_block(self):
        self.isolated_store()
        started = json.loads(mcp.TOOLS["garment_factory"](
            json.dumps({"job_id": "candidate-pattern"}), "start"))
        self.assertEqual(started["state"]["phase"], "EMPTY")
        outline = {"outline": [[0, 0], [24, 0], [28, 90], [-4, 90]],
                   "width_px": 32, "height_px": 90,
                   "source": "human-confirmed"}
        confirmed = json.loads(mcp.TOOLS["garment_factory"](json.dumps({
            "event": {"type": "CONFIRM_IMAGE", "outline": outline,
                      "regions": [{"region_id": "clothing", "part_id": "dress"}],
                      "front_only": True, "evidence_state": "OBSERVED"}})))
        self.assertEqual(confirmed["state"]["phase"], "REGIONS_CONFIRMED")
        retrieved = json.loads(mcp.TOOLS["garment_factory"](json.dumps({
            "event": {"type": "HYBRID_RETRIEVE", "request": {
                "parts": ["dress", "sleeves"], "layers": ["base", "overlay"],
                "shape": {"hem": "flared"}}}})))
        self.assertEqual(retrieved["state"]["phase"], "BACK_CANDIDATES_READY")
        candidate = retrieved["state"]["hypothesis_sheet"]["candidates"][0]
        approved = json.loads(mcp.TOOLS["garment_factory"](json.dumps({
            "event": {"type": "APPROVE_HYPOTHESIS",
                      "candidate_id": candidate["candidate_id"],
                      "digest": candidate["digest"], "by": "MCP Reviewer"}})))
        self.assertEqual(approved["verdict"], "APPROVED")

        baseline = {"verdict": "ANSWER", "pieces": [{"piece_id": "generic"}],
                    "decisions": {}, "hops": []}
        with patch("photoloset.photo_to_pattern.run", return_value=baseline):
            generated = json.loads(mcp.TOOLS["garment_factory"](json.dumps({
                "event": {"type": "GENERATE_PATTERN",
                          "preview_mannequin": True}})))
        pattern = generated["state"]["pattern"]
        self.assertEqual(generated["state"]["phase"], "PATTERN_READY")
        self.assertEqual(pattern["candidate_id"], candidate["candidate_id"])
        self.assertEqual(pattern["approved_hypothesis_binding"]
                         ["candidate_digest"], candidate["digest"])
        self.assertNotEqual([piece["piece_id"] for piece in pattern["pieces"]],
                            ["generic"])
        self.assertEqual(pattern["outline_body_block_baseline"], baseline)
        self.assertEqual(pattern["candidate_preview"]["verdict"], "ANSWER")
        self.assertTrue(pattern["garment_surface"]["preview_only"])
        self.assertEqual(pattern["topology_sewing_plan"]["order_verdict"],
                         "ANSWER")
        manufacturing = pattern["manufacturing_preview"]
        self.assertEqual(manufacturing["verdict"], "ANSWER")
        self.assertTrue(manufacturing["manufacturing_preview_ready"])
        self.assertFalse(manufacturing["manufacturing_ready"])
        self.assertTrue(manufacturing["svg"].startswith("<svg"))
        self.assertEqual(manufacturing["candidate_id"],
                         candidate["candidate_id"])
        self.assertEqual(manufacturing["structure_digest"],
                         pattern["structure_digest"])
        package = pattern["export_package"]
        self.assertEqual(package["verdict"], "ANSWER")
        self.assertFalse(package["manufacturing_ready"])
        self.assertEqual(package["files"]["pattern.dxf"]["representation"],
                         "base64")
        self.assertEqual(package["files"]["pattern.svg"]["representation"],
                         "text")
        verification = pattern["export_verification"]
        self.assertEqual(verification["verdict"], "ANSWER")
        self.assertTrue(verification["verified"])
        self.assertFalse(verification["manufacturing_certified"])
        self.assertEqual(verification["package_digest"], package["digest"])
        self.assertEqual(package["lineage"]["candidate_id"],
                         candidate["candidate_id"])

    def test_factory_mcp_persists_reject_alternative_and_undo_reapproval(self):
        self.isolated_store()
        json.loads(mcp.TOOLS["garment_factory"](
            json.dumps({"job_id": "decision-roundtrip"}), "start"))
        outline = {"outline": [[0, 0], [20, 0], [20, 60], [0, 60]],
                   "width_px": 20, "height_px": 60,
                   "source": "human-confirmed"}

        def advance(event):
            return json.loads(mcp.TOOLS["garment_factory"](
                json.dumps({"event": event})))

        advance({"type": "CONFIRM_IMAGE", "outline": outline,
                 "regions": [{"region_id": "dress", "part_id": "body"}],
                 "front_only": True, "evidence_state": "OBSERVED"})
        advance({
            "type": "SUBMIT_RETRIEVAL",
            "source": {"name": "fixture:decision-roundtrip",
                       "modality": "region_embedding",
                       "license": "fixture permissive",
                       "lineage": ["fixture-root"],
                       "rights": {"commercial": True,
                                  "derivatives": True}},
            "hits": [{"part_id": "body", "region_id": "dress",
                      "reference": "fixture-look", "score": 0.9}],
        })

        def structure(name):
            return {"schema": "garment.structure.v1", "nodes": [{
                "node_id": "body-" + name, "kind": "BODY_SHELL",
                "dimensions": {"height_cm": 60.0,
                               "circumference_cm": 92.0},
                "attributes": {"back_design": name},
            }], "operations": []}

        proposed = advance({
            "type": "SUBMIT_HYPOTHESES", "front_only": True,
            "hypotheses": [
                {"candidate_id": "back-a", "back_design": "back-a",
                 "structure": structure("back-a")},
                {"candidate_id": "back-b", "back_design": "back-b",
                 "structure": structure("back-b")},
            ],
        })
        first, second = proposed["state"]["hypothesis_sheet"]["candidates"]
        rejected = advance({
            "type": "REJECT_HYPOTHESIS",
            "candidate_id": first["candidate_id"],
            "digest": first["digest"], "by": "MCP Reviewer",
            "reason": "choose the other inferred back",
        })
        self.assertEqual(rejected["verdict"], "REJECTED")

        approved = advance({
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": second["candidate_id"],
            "digest": second["digest"], "by": "MCP Reviewer",
        })
        self.assertEqual(approved["verdict"], "APPROVED")
        first_approval_id = approved["state"]["shape_approval"]["approval_id"]

        undone = advance({
            "type": "UNDO_HYPOTHESIS_DECISION",
            "command_id": "mcp-undo-1", "by": "MCP Reviewer",
        })
        self.assertEqual(undone["verdict"], "ANSWER")
        self.assertIsNone(undone["state"]["shape_approval"])
        self.assertEqual(undone["state"]["phase"], "BACK_CANDIDATES_READY")

        reapproved = advance({
            "type": "APPROVE_HYPOTHESIS",
            "candidate_id": second["candidate_id"],
            "digest": second["digest"], "by": "MCP Reviewer",
        })
        self.assertEqual(reapproved["verdict"], "APPROVED")
        self.assertEqual(reapproved["state"]["shape_approval"]["approval_id"],
                         first_approval_id)
        self.assertEqual(
            [row["action"] for row in reapproved["state"]["shape_decisions"]],
            ["REJECT", "APPROVE", "UNDO", "APPROVE"])

    def test_structure_preview_and_pattern_tools_share_candidate_identity(self):
        structure = {
            "schema": "garment.structure.v1",
            "nodes": [{"node_id": "shell", "kind": "BODY_SHELL",
                       "dimensions": {"height_cm": 60.0,
                                      "circumference_cm": 90.0},
                       "attributes": {"back_design": "proposed-side-opening"}}],
            "operations": [],
        }
        request = json.dumps({"candidate_id": "candidate-a",
                              "structure": structure})
        preview = json.loads(mcp.TOOLS["garment_structure_preview"](request))
        pattern = json.loads(mcp.TOOLS["garment_structure_pattern"](request))
        self.assertEqual(preview["verdict"], "ANSWER")
        self.assertEqual(pattern["verdict"], "ANSWER")
        self.assertEqual(preview["candidate_id"], pattern["candidate_id"])
        self.assertEqual(preview["structure_digest"], pattern["structure_digest"])
        self.assertEqual(pattern["pieces"][0]["construction_features"][0]
                         ["state"], "PROPOSED")

    def test_confirmed_region_components_reach_factory_shaped_hypotheses(self):
        outline = {
            "outline": [[40, 0], [60, 0], [90, 100], [10, 100]],
            "internal_lines": [[[18, 50], [82, 50]]],
            "provenance": {"kind": "OBSERVED"},
            "regions": [
                {"region_id": "left-side", "state": "OBSERVED",
                 "outline": [[5, 10], [28, 10], [25, 60], [0, 60]],
                 "semantic_label": "clothing"},
                {"region_id": "right-side", "state": "OBSERVED",
                 "outline": [[72, 10], [95, 10], [100, 60], [75, 60]],
                 "semantic_label": "clothing"},
                {"region_id": "lower-left", "state": "OBSERVED",
                 "outline": [[25, 48], [48, 48], [44, 98], [18, 98]],
                 "semantic_label": "clothing"},
                {"region_id": "lower-right", "state": "OBSERVED",
                 "outline": [[52, 48], [75, 48], [82, 98], [56, 98]],
                 "semantic_label": "clothing"},
            ],
        }
        result = json.loads(mcp.TOOLS["garment_front_outline_hypotheses"](
            json.dumps({"outline": outline, "source_id": "region-wire"})))
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertTrue(result["factory_envelope"])
        self.assertEqual(len(result["hypotheses"]), 3)
        for row in result["hypotheses"]:
            self.assertEqual(row["state"], "PROPOSED")
            self.assertEqual(row["structure"]["schema"],
                             "garment.structure.v1")
            self.assertTrue(row["back_design"])
            self.assertTrue(row["front_region_evidence_digest"])
            self.assertEqual(row["front_geometry_digest"],
                             result["front_geometry_digest"])


if __name__ == "__main__":
    unittest.main()
