#!/usr/bin/env python3
import unittest

from photoloset.generation_job import (
    APPROVAL_STALE, INVALID_TRANSITION, MISSING_DIGEST,
    GarmentGenerationJob, JobRefusal, JobState, apply, new_job,
)


class GenerationJobTests(unittest.TestCase):
    def job(self):
        return GarmentGenerationJob("job-1", {"source": "test", "actor": "human"})

    def test_transition_requires_named_digest(self):
        result = self.job().transition(JobState.IMAGE_RECEIVED, {})
        self.assertIsInstance(result, JobRefusal)
        self.assertEqual(result.verdict, MISSING_DIGEST)

    def test_invalid_state_skip_is_typed_refusal(self):
        result = self.job().transition(JobState.STRUCTURE_APPROVED,
                                       {"structure": "sha256:1"})
        self.assertEqual(result.verdict, INVALID_TRANSITION)

    def test_transition_appends_event_and_preserves_provenance(self):
        job = self.job()
        event = job.transition(JobState.IMAGE_RECEIVED,
                               {"image": "sha256:image"})
        self.assertEqual(len(job.events), 1)
        self.assertEqual(event.kind, "STATE_TRANSITION")
        self.assertEqual(event.provenance["actor"], "human")
        self.assertEqual(job.snapshot.state, JobState.IMAGE_RECEIVED)

    def test_preview_does_not_mutate_active_snapshot(self):
        job = self.job()
        job.transition(JobState.IMAGE_RECEIVED, {"image": "sha256:image"},
                       data={"ease_cm": 0})
        before = job.snapshot
        preview = job.create_preview("c-1", {"ease_cm": 3}, ["pattern.30:35"],
                                     [{"verdict": "PASS"}])
        self.assertEqual(job.snapshot.digest, before.digest)
        self.assertEqual(preview.before.digest, before.digest)
        self.assertNotEqual(preview.after.digest, before.digest)
        self.assertEqual(preview.schema, "garment.preview.v1")

    def test_approval_is_digest_bound_and_stale_preview_refuses(self):
        job = self.job()
        job.transition(JobState.IMAGE_RECEIVED, {"image": "sha256:image"})
        preview = job.create_preview("c-1", {"ease_cm": 3}, ["pattern.30:35"],
                                     [{"verdict": "PASS"}])
        stale = job.approve_preview(preview.preview_id, "wrong", approver="A")
        self.assertEqual(stale.verdict, APPROVAL_STALE)
        self.assertEqual(job.snapshot.digest, preview.before.digest)

    def test_approval_applies_immutable_after_snapshot(self):
        job = self.job()
        job.transition(JobState.IMAGE_RECEIVED, {"image": "sha256:image"})
        preview = job.create_preview("c-1", {"ease_cm": 3}, ["pattern.30:35"],
                                     [{"verdict": "PASS"}])
        event = job.approve_preview(preview.preview_id, preview.digest,
                                    approver="Alice")
        self.assertEqual(event.kind, "PREVIEW_APPROVED")
        self.assertEqual(job.snapshot.data["ease_cm"], 3)
        with self.assertRaises(TypeError):
            job.snapshot.data["ease_cm"] = 5

    def test_old_preview_becomes_stale_after_another_approval(self):
        job = self.job()
        job.transition(JobState.IMAGE_RECEIVED, {"image": "sha256:image"})
        old = job.create_preview("old", {"v": 1}, ["v"],
                                 [{"verdict": "PASS"}])
        new = job.create_preview("new", {"v": 2}, ["v"],
                                 [{"verdict": "PASS"}])
        job.approve_preview(new.preview_id, new.digest, approver="Alice")
        result = job.approve_preview(old.preview_id, old.digest, approver="Alice")
        self.assertEqual(result.verdict, APPROVAL_STALE)

    def test_undo_appends_compensation_and_never_deletes_history(self):
        job = self.job()
        job.transition(JobState.IMAGE_RECEIVED, {"image": "sha256:image"},
                       data={"ease": 0})
        preview = job.create_preview("edit", {"ease": 3}, ["ease"],
                                     [{"verdict": "PASS"}])
        job.approve_preview(preview.preview_id, preview.digest, approver="Alice")
        count = len(job.events)
        result = job.undo(command_id="undo-1")
        self.assertEqual(result.kind, "COMPENSATING_UNDO")
        self.assertEqual(len(job.events), count + 1)
        self.assertEqual(job.snapshot.data["ease"], 0)
        self.assertEqual(job.events[-2].kind, "PREVIEW_APPROVED")

    def test_snapshot_digest_is_deterministic(self):
        a, b = self.job(), self.job()
        a.transition(JobState.IMAGE_RECEIVED, {"b": "2", "a": "1"},
                     data={"y": 2, "x": 1})
        b.transition(JobState.IMAGE_RECEIVED, {"a": "1", "b": "2"},
                     data={"x": 1, "y": 2})
        self.assertEqual(a.snapshot.digest, b.snapshot.digest)

    def test_public_api_is_json_serializable_and_functional(self):
        import json
        original = new_job("public-job")
        advanced = apply(original, {"kind": "TRANSITION",
                                    "state": "IMAGE_RECEIVED",
                                    "artifacts": {"image": "sha256:image"},
                                    "data": {"ease": 0}})
        self.assertIsNone(original["snapshot"]["state"])
        self.assertEqual(advanced["snapshot"]["state"], "IMAGE_RECEIVED")
        json.dumps(advanced)

    def test_public_preview_approval_and_undo(self):
        job = apply(new_job("public-job"), {
            "kind": "TRANSITION", "state": "IMAGE_RECEIVED",
            "artifacts": {"image": "sha256:image"}, "data": {"ease": 0}})
        job = apply(job, {"kind": "PREVIEW", "command_id": "edit",
                          "after_data": {"ease": 3},
                          "changed_addresses": ["ease"],
                          "validation_results": [{"verdict": "PASS"}]})
        preview = job["result"]
        job = apply(job, {"kind": "APPROVE",
                          "preview_id": preview["preview_id"],
                          "digest": preview["digest"], "approver": "Alice"})
        self.assertEqual(job["snapshot"]["data"]["ease"], 3)
        job = apply(job, {"kind": "UNDO", "command_id": "undo"})
        self.assertEqual(job["snapshot"]["data"]["ease"], 0)
        self.assertEqual(job["result"]["kind"], "COMPENSATING_UNDO")


if __name__ == "__main__":
    unittest.main()
