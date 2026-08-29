#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The persisted factory cannot skip initial AI audit or target cleanup."""
from __future__ import annotations

import unittest

from photoloset import garment_factory


def confirmed_job():
    state = garment_factory.new_job("initial-human-gate")
    response = garment_factory.advance(state, {
        "type": "CONFIRM_IMAGE",
        "outline": {"verdict": "ANSWER", "outline": [[0, 0], [1, 0], [1, 2]]},
        "regions": [{"region_id": "garment-front", "part_id": "garment"}],
        "source": {"image_digest": "sha256:front"},
        "front_only": True,
        "evidence_state": "PROPOSED",
    })
    return response["state"]


def proposed_job():
    response = garment_factory.advance(confirmed_job(), {
        "type": "RECORD_AI_VISIBLE_ANALYSIS",
        "model": {"provider": "local-vlm", "name": "fixture"},
        "retrieval": {"state": "PROPOSED", "adapter": "FashionSigLIP"},
        "assertions": [
            {"inventory_part_id": "blouse", "kind": "BODY_SHELL",
             "semantic_role": "white blouse", "evidence_scope": "VISIBLE_FRONT"},
            {"inventory_part_id": "trouser-left", "kind": "TUBE",
             "semantic_role": "left trouser leg", "evidence_scope": "VISIBLE_FRONT"},
            {"inventory_part_id": "rear-zip", "field": "rear_closure",
             "value": "zipper", "evidence_scope": "HIDDEN_REAR", "category": "rear"},
            {"inventory_part_id": "fabric", "field": "material_identity",
             "value": "silk", "evidence_scope": "VISIBLE_FRONT", "category": "material"},
        ],
    })
    return response["state"]


def confirmed_auto_job(source_view="OBLIQUE_LEFT"):
    state = garment_factory.new_job(
        "initial-auto-gate", audit_mode=garment_factory.AUTO_PROPOSED)
    response = garment_factory.advance(state, {
        "type": "CONFIRM_IMAGE",
        "outline": {"verdict": "ANSWER", "outline": [[0, 0], [1, 0], [1, 2]]},
        "regions": [{"region_id": "garment-visible", "part_id": "garment"}],
        "source": {"image_digest": "sha256:oblique", "view": source_view},
        "source_view": source_view,
        "front_only": True,
        "evidence_state": "OBSERVED",
    })
    return response["state"]


def auto_analysis_event(*, include_cleanup=True):
    event = {
        "type": "RECORD_AI_VISIBLE_ANALYSIS",
        "model": {"provider": "local-vlm", "name": "fixture"},
        "retrieval": {"state": "OBSERVED", "adapter": "FashionSigLIP"},
        "assertions": [
            {"inventory_part_id": "blouse", "kind": "BODY_SHELL",
             "semantic_role": "white blouse"},
            {"inventory_part_id": "trousers", "kind": "TUBE_PAIR",
             "semantic_role": "red wide-leg trousers"},
            {"inventory_part_id": "rear-zip", "field": "rear_closure",
             "value": "zipper", "evidence_scope": "HIDDEN_REAR",
             "category": "rear"},
        ],
    }
    if include_cleanup:
        event["foreground_cleanup"] = {
            "target_digest": "sha256:auto-mask",
            "target_revision": 2,
            "removed_region_ids": ["background", "hair", "body"],
            "removed_face_indices": [9, 3, 9],
            "undo_parent_digests": ["sha256:auto-mask-r1"],
            "state": "APPROVED",
        }
    return event


class GarmentFactoryInitialHumanGateTests(unittest.TestCase):
    def test_default_api_remains_human_audit(self):
        state = garment_factory.new_job("backward-compatible-default")
        self.assertEqual(state["audit_mode"], garment_factory.HUMAN_AUDIT)
        self.assertEqual(state["truth_contract"]["approval"],
                         "named human + exact semantic digest")

    def test_ai_rows_are_proposals_and_gate_all_later_factory_events(self):
        state = proposed_job()
        self.assertEqual(state["phase"], "HUMAN_GARMENT_AUDIT_REQUIRED")
        self.assertTrue(all(row["state"] == "PROPOSED"
                            for row in state["visible_ai_analysis"]["assertions"]))
        self.assertEqual(state["visible_ai_analysis"]["fact_promotions"], [])
        refused = garment_factory.advance(state, {
            "type": "SUBMIT_RETRIEVAL", "source": {}, "hits": []})
        self.assertEqual(refused["verdict"], "UNKNOWN_HUMAN_GARMENT_AUDIT_REQUIRED")

    def test_named_digest_bound_audit_promotes_only_visible_front(self):
        state = proposed_job()
        digest = state["visible_ai_analysis"]["analysis_digest"]
        response = garment_factory.advance(state, {
            "type": "SUBMIT_HUMAN_VISIBLE_AUDIT",
            "reviewer": "Mina",
            "analysis_digest": digest,
            "decisions": [
                {"assertion_id": "blouse", "action": "ACCEPT"},
                {"assertion_id": "trouser-left", "action": "EDIT",
                 "edits": {"semantic_role": "red wide-leg trouser left"}},
                {"assertion_id": "rear-zip", "action": "ACCEPT"},
                {"assertion_id": "fabric", "action": "ACCEPT"},
            ],
        })
        self.assertEqual(response["verdict"], "APPROVED")
        state = response["state"]
        self.assertEqual(state["phase"], "FOREGROUND_CLEANUP_REQUIRED")
        by_id = {row["assertion_id"]: row
                 for row in state["human_visible_audit"]["assertions"]}
        self.assertEqual(by_id["blouse"]["evidence_state"],
                         "OBSERVED_BY_HUMAN_REVIEW")
        self.assertEqual(by_id["trouser-left"]["semantic_role"],
                         "red wide-leg trouser left")
        self.assertEqual(by_id["rear-zip"]["evidence_state"],
                         "PROPOSED_AFTER_HUMAN_REVIEW")
        self.assertEqual(by_id["fabric"]["evidence_state"],
                         "PROPOSED_AFTER_HUMAN_REVIEW")
        self.assertFalse(state["front_facts"]["rear_inference_performed"])
        self.assertFalse(state["front_facts"]["material_identity_confirmed"])

    def test_cleanup_adoption_is_revision_bound_and_opens_front_facts_only(self):
        state = proposed_job()
        digest = state["visible_ai_analysis"]["analysis_digest"]
        state = garment_factory.advance(state, {
            "type": "SUBMIT_HUMAN_VISIBLE_AUDIT",
            "reviewer": "Mina", "analysis_digest": digest,
            "decisions": [
                {"assertion_id": row["assertion_id"], "action": "ACCEPT"}
                for row in state["visible_ai_analysis"]["assertions"]
            ],
        })["state"]
        invalid = garment_factory.advance(state, {
            "type": "SUBMIT_FOREGROUND_CLEANUP", "reviewer": "Mina",
            "target_digest": "sha256:target", "target_revision": -1,
        })
        self.assertEqual(invalid["verdict"],
                         "UNKNOWN_INVALID_FOREGROUND_CLEANUP_RECORD")
        response = garment_factory.advance(state, {
            "type": "SUBMIT_FOREGROUND_CLEANUP",
            "reviewer": "Mina",
            "target_digest": "sha256:target",
            "target_revision": 4,
            "removed_region_ids": ["background", "hair"],
            "removed_face_indices": [7, 2, 7],
            "undo_parent_digests": ["sha256:target-r3"],
        })
        self.assertEqual(response["verdict"], "APPROVED")
        state = response["state"]
        self.assertEqual(state["phase"], "FRONT_FACTS_RECORDED")
        cleanup = state["foreground_cleanup"]
        self.assertEqual(cleanup["iteration"], 1)
        self.assertEqual(cleanup["removed_face_indices"], [2, 7])
        self.assertFalse(cleanup["rear_inference_performed"])
        self.assertFalse(cleanup["manufacturing_ready"])
        opened = garment_factory.advance(state, {
            "type": "OPEN_RETRIEVAL_AFTER_FRONT_REVIEW",
            "compiled_front_digest": "sha256:compiled-visible-front",
            "candidate_count": 3,
        })
        self.assertEqual(opened["verdict"], "PROPOSED")
        self.assertEqual(opened["state"]["phase"], "REGIONS_CONFIRMED")
        self.assertFalse(opened["state"]["front_compilation"]
                         ["rear_inference_performed"])

    def test_stale_audit_and_partial_decisions_fail_typed(self):
        state = proposed_job()
        stale = garment_factory.advance(state, {
            "type": "SUBMIT_HUMAN_VISIBLE_AUDIT", "reviewer": "Mina",
            "analysis_digest": "sha256:stale", "decisions": [],
        })
        self.assertEqual(stale["verdict"], "UNKNOWN_HUMAN_GARMENT_AUDIT_STALE")
        partial = garment_factory.advance(state, {
            "type": "SUBMIT_HUMAN_VISIBLE_AUDIT", "reviewer": "Mina",
            "analysis_digest": state["visible_ai_analysis"]["analysis_digest"],
            "decisions": [{"assertion_id": "blouse", "action": "ACCEPT"}],
        })
        self.assertEqual(partial["verdict"], "UNKNOWN_INVALID_HUMAN_GARMENT_AUDIT")

    def test_new_cad_target_revision_invalidates_and_reopens_the_full_loop(self):
        state = proposed_job()
        digest = state["visible_ai_analysis"]["analysis_digest"]
        state = garment_factory.advance(state, {
            "type": "SUBMIT_HUMAN_VISIBLE_AUDIT",
            "reviewer": "Mina", "analysis_digest": digest,
            "decisions": [
                {"assertion_id": row["assertion_id"], "action": "ACCEPT"}
                for row in state["visible_ai_analysis"]["assertions"]
            ],
        })["state"]
        state = garment_factory.advance(state, {
            "type": "SUBMIT_FOREGROUND_CLEANUP", "reviewer": "Mina",
            "target_digest": "sha256:target-r4", "target_revision": 4,
            "removed_region_ids": ["background"],
            "removed_face_indices": [2], "undo_parent_digests": [],
        })["state"]
        state = garment_factory.advance(state, {
            "type": "OPEN_RETRIEVAL_AFTER_FRONT_REVIEW",
            "compiled_front_digest": "sha256:compiled-r4",
            "candidate_count": 2,
        })["state"]

        revised = garment_factory.advance(state, {
            "type": "SUBMIT_FOREGROUND_CLEANUP", "reviewer": "Mina",
            "target_digest": "sha256:target-r5", "target_revision": 5,
            "removed_region_ids": ["background", "hair"],
            "removed_face_indices": [2, 9],
            "undo_parent_digests": ["sha256:target-r4"],
        })

        self.assertEqual(revised["verdict"], "APPROVED")
        next_state = revised["state"]
        self.assertEqual(next_state["phase"], "FRONT_FACTS_RECORDED")
        self.assertIsNone(next_state["front_compilation"])
        self.assertEqual(len(next_state["foreground_cleanup_history"]), 1)
        self.assertEqual(
            next_state["foreground_cleanup"]["supersedes_cleanup_digest"],
            next_state["foreground_cleanup_history"][0]["cleanup_digest"],
        )
        self.assertEqual(next_state["foreground_cleanup"]["iteration"], 2)
        self.assertEqual(next_state["front_facts"]["authority"],
                         "HUMAN_REVIEWED_VISIBLE_SOURCE")

        stale = garment_factory.advance(next_state, {
            "type": "SUBMIT_FOREGROUND_CLEANUP", "reviewer": "Mina",
            "target_digest": "sha256:target-r3", "target_revision": 3,
            "removed_region_ids": [], "removed_face_indices": [],
            "undo_parent_digests": [],
        })
        self.assertEqual(
            stale["verdict"],
            "UNKNOWN_FOREGROUND_CLEANUP_STALE_REVISION",
        )

        fresh_image = garment_factory.advance(next_state, {
            "type": "CONFIRM_IMAGE",
            "outline": {"verdict": "ANSWER",
                        "outline": [[0, 0], [2, 0], [2, 3]]},
            "regions": [{"region_id": "new-front", "part_id": "garment"}],
            "source": {"image_digest": "sha256:new-front"},
            "front_only": True,
            "evidence_state": "PROPOSED",
        })
        self.assertEqual(fresh_image["verdict"], "ANSWER")
        history = fresh_image["state"]["foreground_cleanup_history"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1]["cleanup_digest"],
                         next_state["foreground_cleanup"]["cleanup_digest"])

    def test_auto_mode_adopts_oblique_analysis_and_cleanup_for_preview_only(self):
        confirmed = confirmed_auto_job()
        evidence = confirmed["image_evidence"]
        self.assertEqual(evidence["state"], garment_factory.PROPOSED)
        self.assertEqual(evidence["view_authority"]["view"], "OBLIQUE")
        self.assertTrue(evidence["view_authority"]["oblique_visible"])
        self.assertEqual(evidence["view_authority"]["authority"],
                         garment_factory.AUTO_ACCEPTED_FOR_PREVIEW)

        response = garment_factory.advance(
            confirmed, auto_analysis_event(include_cleanup=True))
        self.assertEqual(response["verdict"], garment_factory.PROPOSED)
        state = response["state"]
        self.assertEqual(state["phase"], "FRONT_FACTS_RECORDED")
        self.assertIsNone(state["human_visible_audit"])

        audit = state["auto_visible_audit"]
        self.assertEqual(audit["state"], garment_factory.PROPOSED)
        self.assertEqual(audit["authority"],
                         garment_factory.AUTO_ACCEPTED_FOR_PREVIEW)
        self.assertEqual(audit["view_authority"]["view"], "OBLIQUE")
        self.assertEqual(audit["fact_promotions"], [])
        self.assertTrue(all(row["state"] == garment_factory.PROPOSED
                            and row["evidence_state"] ==
                            garment_factory.AUTO_ACCEPTED_FOR_PREVIEW
                            and row["fact"] is False
                            for row in audit["assertions"]))

        facts = state["front_facts"]
        self.assertEqual(facts["observed_assertions"], [])
        self.assertEqual(len(facts["proposed_assertions"]), 3)
        self.assertFalse(facts["manufacturing_certification"])
        self.assertFalse(facts["industrial_strength_guarantee"])

        cleanup = state["foreground_cleanup"]
        self.assertEqual(cleanup["state"], garment_factory.PROPOSED)
        self.assertEqual(cleanup["authority"],
                         garment_factory.AUTO_ACCEPTED_FOR_PREVIEW)
        self.assertEqual(cleanup["removed_face_indices"], [3, 9])
        self.assertFalse(cleanup["manufacturing_ready"])
        self.assertFalse(cleanup["manufacturing_certification"])
        self.assertFalse(cleanup["industrial_strength_guarantee"])
        self.assertEqual(
            [(item["type"], item["phase"]) for item in state["events"][-3:]],
            [
                ("RECORD_AI_VISIBLE_ANALYSIS", "HUMAN_GARMENT_AUDIT_REQUIRED"),
                ("AUTO_ACCEPT_VISIBLE_AUDIT", "FOREGROUND_CLEANUP_REQUIRED"),
                ("SUBMIT_FOREGROUND_CLEANUP", "FRONT_FACTS_RECORDED"),
            ],
        )

        opened = garment_factory.advance(state, {
            "type": "OPEN_RETRIEVAL_AFTER_FRONT_REVIEW",
            "compiled_front_digest": "sha256:auto-compiled-front",
            "candidate_count": 3,
        })
        self.assertEqual(opened["verdict"], garment_factory.PROPOSED)
        self.assertEqual(opened["state"]["phase"], "REGIONS_CONFIRMED")
        compilation = opened["state"]["front_compilation"]
        self.assertEqual(compilation["authority"],
                         garment_factory.AUTO_ACCEPTED_FOR_PREVIEW)
        self.assertFalse(compilation["manufacturing_certification"])
        self.assertFalse(compilation["industrial_strength_guarantee"])

    def test_auto_mode_uses_existing_cleanup_stop_and_accepts_later_ai_mask(self):
        state = confirmed_auto_job("FRONT")
        response = garment_factory.advance(
            state, auto_analysis_event(include_cleanup=False))
        self.assertEqual(response["verdict"], garment_factory.PROPOSED)
        state = response["state"]
        self.assertEqual(state["phase"], "FOREGROUND_CLEANUP_REQUIRED")

        stopped = garment_factory.advance(state, {
            "type": "SUBMIT_RETRIEVAL", "source": {}, "hits": []})
        self.assertEqual(stopped["verdict"],
                         "UNKNOWN_FOREGROUND_CLEANUP_REQUIRED")

        adopted = garment_factory.advance(state, {
            "type": "SUBMIT_FOREGROUND_CLEANUP",
            "target_digest": "sha256:later-auto-mask",
            "target_revision": 1,
            "removed_region_ids": ["background"],
            "removed_face_indices": [],
            "undo_parent_digests": [],
        })
        self.assertEqual(adopted["verdict"], garment_factory.PROPOSED)
        self.assertEqual(adopted["state"]["phase"], "FRONT_FACTS_RECORDED")
        self.assertEqual(adopted["state"]["foreground_cleanup"]["authority"],
                         garment_factory.AUTO_ACCEPTED_FOR_PREVIEW)

    def test_auto_mode_rejects_human_promotion_event(self):
        state = confirmed_auto_job()
        state = garment_factory.advance(
            state, auto_analysis_event(include_cleanup=False))["state"]
        response = garment_factory.advance(state, {
            "type": "SUBMIT_HUMAN_VISIBLE_AUDIT",
            "reviewer": "Mina",
            "analysis_digest": state["visible_ai_analysis"]["analysis_digest"],
            "decisions": [],
        })
        self.assertEqual(response["verdict"], "UNKNOWN_FACTORY_EVENT")
        self.assertEqual(response["state"]["front_facts"]["observed_assertions"], [])


if __name__ == "__main__":
    unittest.main()
