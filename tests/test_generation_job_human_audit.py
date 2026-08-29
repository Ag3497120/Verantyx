#!/usr/bin/env python3
import json
import unittest

from photoloset.generation_job import (
    FUTURE_STAGE_NOT_IMPLEMENTED,
    INVALID_TRANSITION,
    REVIEWER_REQUIRED,
    STALE_ARTIFACT_REVISION,
    GarmentGenerationJob,
    JobRefusal,
    JobState,
    apply,
    new_job,
)


LAYERED_ASSERTIONS = [
    {
        "assertion_id": "garment-blouse",
        "field": "garment_instance",
        "value": "white blouse",
        "evidence_scope": "VISIBLE_FRONT",
        "layer": 0,
    },
    {
        "assertion_id": "garment-vest",
        "field": "garment_instance",
        "value": "navy cropped vest",
        "evidence_scope": "VISIBLE_FRONT",
        "layer": 1,
    },
    {
        "assertion_id": "garment-trousers",
        "field": "garment_instance",
        "value": "red skirt",
        "evidence_scope": "VISIBLE_FRONT",
        "layer": 0,
    },
    {
        "assertion_id": "garment-overlay",
        "field": "garment_instance",
        "value": "sheer asymmetric wrap overlay",
        "evidence_scope": "VISIBLE_FRONT",
        "layer": 1,
    },
    {
        "assertion_id": "rear-closure",
        "field": "closure",
        "value": "center-back zipper",
        "evidence_scope": "HIDDEN_REAR",
        "category": "rear",
    },
    {
        "assertion_id": "material-overlay",
        "field": "material_identity",
        "value": "silk organza",
        "evidence_scope": "VISIBLE_FRONT",
        "category": "material_identity",
    },
]


class GenerationJobHumanAuditTests(unittest.TestCase):
    def received_job(self, job_id="audit-job"):
        job = GarmentGenerationJob(
            job_id, {"source": "test", "actor": "harness"})
        result = job.transition(
            JobState.IMAGE_RECEIVED,
            {"image": "sha256:front"},
            data={"front_source": {"artifact_id": "front-1", "revision": 3}},
        )
        self.assertNotIsInstance(result, JobRefusal)
        return job

    def proposed_job(self, job_id="audit-job"):
        job = self.received_job(job_id)
        result = job.record_ai_analysis(
            source_artifact_id="front-1",
            source_revision=3,
            analysis_artifact_id="analysis-1",
            analysis_revision=7,
            analysis_digest="sha256:analysis",
            assertions=LAYERED_ASSERTIONS,
            provenance={"source": "MULTIMODAL_MODEL", "model": "test-model"},
        )
        self.assertNotIsInstance(result, JobRefusal)
        return job

    def audited_job(self, job_id="audit-job"):
        job = self.proposed_job(job_id)
        result = job.require_human_garment_audit(
            analysis_artifact_id="analysis-1", analysis_revision=7)
        self.assertNotIsInstance(result, JobRefusal)
        decisions = [
            {"assertion_id": "garment-blouse", "action": "ACCEPT"},
            {"assertion_id": "garment-vest", "action": "ACCEPT"},
            {
                "assertion_id": "garment-trousers",
                "action": "EDIT",
                "edits": {"value": "red wide-leg trousers"},
            },
            {"assertion_id": "garment-overlay", "action": "ACCEPT"},
            {"assertion_id": "rear-closure", "action": "ACCEPT"},
            {"assertion_id": "material-overlay", "action": "ACCEPT"},
        ]
        result = job.submit_human_garment_audit(
            analysis_artifact_id="analysis-1",
            analysis_revision=7,
            reviewer="Mina",
            decisions=decisions,
            provenance={"source": "HUMAN_REVIEW", "station": "front-audit"},
        )
        self.assertNotIsInstance(result, JobRefusal)
        return job

    def cleanup_review_job(self, job_id="audit-job"):
        job = self.audited_job(job_id)
        result = job.submit_foreground_cleanup(
            source_artifact_id="front-1",
            source_revision=3,
            mask_artifact_id="mask-1",
            mask_revision=2,
            mask_digest="sha256:mask",
            removed_classes=["background", "hair", "body", "other garment"],
            undo_lineage=["front-1@3", "mask-1@1", "mask-1@2"],
            reviewer="Mina",
            provenance={"source": "HUMAN_CLEANUP", "tool": "point-mask"},
        )
        self.assertNotIsInstance(result, JobRefusal)
        return job

    def test_layered_front_audit_promotes_only_visible_assertions(self):
        job = self.audited_job()
        self.assertEqual(job.snapshot.state,
                         JobState.FOREGROUND_CLEANUP_REQUIRED)
        audited = job.snapshot.data["human_garment_audit"]["assertions"]
        by_id = {item["assertion_id"]: item for item in audited}

        for assertion_id in (
                "garment-blouse", "garment-vest", "garment-trousers",
                "garment-overlay"):
            self.assertEqual(by_id[assertion_id]["evidence_state"],
                             "OBSERVED_BY_HUMAN_REVIEW")
        self.assertEqual(by_id["garment-trousers"]["value"],
                         "red wide-leg trousers")
        self.assertEqual(by_id["garment-trousers"]["ai_proposal"]["value"],
                         "red skirt")

        # A front reviewer may accept these as useful hypotheses, but cannot
        # turn a hidden rear closure or material identity into observation.
        self.assertEqual(by_id["rear-closure"]["evidence_state"],
                         "PROPOSED_AFTER_HUMAN_REVIEW")
        self.assertEqual(by_id["material-overlay"]["evidence_state"],
                         "PROPOSED_AFTER_HUMAN_REVIEW")

    def test_model_analysis_cannot_skip_human_boundaries_to_geometry(self):
        job = self.proposed_job()
        skipped = job.transition(JobState.GEOMETRY_CONTESTED,
                                 {"geometry": "sha256:invented"})
        self.assertEqual(skipped.verdict, INVALID_TRANSITION)
        self.assertEqual(job.snapshot.state, JobState.AI_ANALYSIS_PROPOSED)

        skipped = job.transition(JobState.TARGET_2_5D_READY,
                                 {"target": "sha256:invented"}, data={})
        self.assertEqual(skipped.verdict, INVALID_TRANSITION)
        self.assertEqual(job.snapshot.state, JobState.AI_ANALYSIS_PROPOSED)

    def test_cleanup_contract_records_refs_lineage_and_no_pixel_geometry(self):
        job = self.cleanup_review_job()
        self.assertEqual(job.snapshot.state, JobState.CLEANUP_REVIEW_REQUIRED)
        cleanup = job.snapshot.data["foreground_cleanup"]
        self.assertEqual(cleanup["mask"], {
            "artifact_id": "mask-1", "revision": 2, "digest": "sha256:mask"})
        self.assertEqual(cleanup["removed_classes"], (
            "BACKGROUND", "HAIR", "BODY", "OTHER_GARMENT"))
        self.assertEqual(cleanup["undo_lineage"], (
            "front-1@3", "mask-1@1", "mask-1@2"))
        self.assertEqual(cleanup["reviewer"], "Mina")
        self.assertFalse(cleanup["pixel_geometry_recorded"])
        self.assertNotIn("pixels", cleanup)
        self.assertNotIn("vertices", cleanup)

    def test_stale_revisions_missing_reviewer_and_skipped_stage_are_typed(self):
        job = self.proposed_job()
        stale = job.require_human_garment_audit(
            analysis_artifact_id="analysis-1", analysis_revision=6)
        self.assertEqual(stale.verdict, STALE_ARTIFACT_REVISION)

        job.require_human_garment_audit(
            analysis_artifact_id="analysis-1", analysis_revision=7)
        no_reviewer = job.submit_human_garment_audit(
            analysis_artifact_id="analysis-1", analysis_revision=7,
            reviewer="", decisions=[])
        self.assertEqual(no_reviewer.verdict, REVIEWER_REQUIRED)

        audited = self.audited_job("cleanup-errors")
        stale = audited.submit_foreground_cleanup(
            source_artifact_id="front-1", source_revision=2,
            mask_artifact_id="mask-x", mask_revision=1,
            mask_digest="sha256:x", removed_classes=[],
            undo_lineage=["front-1@2"], reviewer="Mina")
        self.assertEqual(stale.verdict, STALE_ARTIFACT_REVISION)

        cleanup = self.cleanup_review_job("review-errors")
        stale = cleanup.review_foreground_cleanup(
            mask_artifact_id="mask-1", mask_revision=1,
            reviewer="Mina", decision="APPROVE")
        self.assertEqual(stale.verdict, STALE_ARTIFACT_REVISION)
        no_reviewer = cleanup.review_foreground_cleanup(
            mask_artifact_id="mask-1", mask_revision=2,
            reviewer="", decision="APPROVE")
        self.assertEqual(no_reviewer.verdict, REVIEWER_REQUIRED)

    def test_cleanup_approval_records_front_facts_and_undo_restores_review(self):
        job = self.cleanup_review_job()
        result = job.review_foreground_cleanup(
            mask_artifact_id="mask-1", mask_revision=2,
            reviewer="Riku", decision="APPROVE")
        self.assertNotIsInstance(result, JobRefusal)
        self.assertEqual(job.snapshot.state, JobState.FRONT_FACTS_RECORDED)
        facts = job.snapshot.data["front_facts"]
        self.assertFalse(facts["rear_inference_performed"])
        self.assertFalse(facts["material_identity_confirmed"])
        self.assertEqual(len(facts["observed_assertions"]), 4)
        proposed_ids = {item["assertion_id"]
                        for item in facts["proposed_assertions"]}
        self.assertEqual(proposed_ids, {"rear-closure", "material-overlay"})

        undo = job.undo(command_id="undo-cleanup-approval")
        self.assertEqual(undo.kind, "COMPENSATING_UNDO")
        self.assertEqual(job.snapshot.state, JobState.CLEANUP_REVIEW_REQUIRED)
        self.assertEqual(job.events[-1].kind, "COMPENSATING_UNDO")

    def test_rejected_cleanup_can_be_undone_to_review_state(self):
        job = self.cleanup_review_job()
        job.review_foreground_cleanup(
            mask_artifact_id="mask-1", mask_revision=2,
            reviewer="Riku", decision="REJECT")
        self.assertEqual(job.snapshot.state, JobState.FOREGROUND_CLEANUP_REQUIRED)
        job.undo(command_id="undo-cleanup-rejection")
        self.assertEqual(job.snapshot.state, JobState.CLEANUP_REVIEW_REQUIRED)

    def test_front_facts_can_prepare_target_without_inventing_rear(self):
        job = self.cleanup_review_job()
        job.review_foreground_cleanup(
            mask_artifact_id="mask-1", mask_revision=2,
            reviewer="Riku", decision="APPROVE")
        result = job.prepare_target_2_5d(
            artifact_id="target-front-1", artifact_revision=1,
            artifact_digest="sha256:target")
        self.assertNotIsInstance(result, JobRefusal)
        self.assertEqual(job.snapshot.state, JobState.TARGET_2_5D_READY)
        target = job.snapshot.data["target_2_5d"]
        self.assertFalse(target["rear_inference_performed"])
        self.assertEqual(target["evidence_state"],
                         "PROPOSED_FROM_APPROVED_FRONT")

    def test_future_stages_are_declared_typed_requirements(self):
        job = self.received_job()
        for stage in (
                JobState.PART_SEGMENTATION_REQUIRED,
                JobState.REAR_CANDIDATES_REQUIRED,
                JobState.CAD_SCULPT_REQUIRED,
                JobState.TARGET_APPROVAL_REQUIRED,
                JobState.PATTERN_INVERSE_REQUIRED,
                JobState.REDRESS_COMPARISON_REQUIRED):
            refusal = job.future_stage_requirement(stage)
            self.assertEqual(refusal.verdict, FUTURE_STAGE_NOT_IMPLEMENTED)
            self.assertTrue(refusal.details["requirements"])

    def test_public_apply_round_trip_and_event_log_are_deterministic(self):
        def run():
            job = apply(new_job("public-audit"), {
                "kind": "TRANSITION", "state": "IMAGE_RECEIVED",
                "artifacts": {"image": "sha256:front"},
                "data": {"front_source": {
                    "artifact_id": "front-1", "revision": 3}},
            })
            job = apply(job, {
                "kind": "AI_ANALYSIS",
                "source_artifact_id": "front-1", "source_revision": 3,
                "analysis_artifact_id": "analysis-1", "analysis_revision": 7,
                "analysis_digest": "sha256:analysis",
                "assertions": LAYERED_ASSERTIONS,
                "provenance": {"source": "MODEL", "model": "test"},
            })
            job = apply(job, {
                "kind": "REQUIRE_HUMAN_GARMENT_AUDIT",
                "analysis_artifact_id": "analysis-1", "analysis_revision": 7,
            })
            return job

        first, second = run(), run()
        self.assertEqual(first["snapshot"]["digest"],
                         second["snapshot"]["digest"])
        self.assertEqual(first["events"], second["events"])
        json.dumps(first)


if __name__ == "__main__":
    unittest.main()
