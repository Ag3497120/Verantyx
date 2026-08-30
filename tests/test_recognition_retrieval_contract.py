# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import unittest

from photoloset import resemble, sewing_search
from tests.test_hybrid_garment_retrieval import approved_factory_state


class RecognitionRetrievalContractTests(unittest.TestCase):
    def tearDown(self):
        resemble.reset()

    def test_per_part_similarity_is_only_a_rear_construction_proposal(self):
        resemble.install_fixture({
            "overlay-1": [{
                "aspect": "resembles",
                "value": {"family": "wrap panel"},
                "ref": "fixture://wrap-panel",
                "axis_scores": {
                    "part": 0.92, "structure": 0.79,
                    "seam": 0.54, "material": 0.68,
                },
                "structure_features": {"regime": "WRAPPED"},
                "seam_topology": ["waist anchor"],
                "material_features": {"appearance": "sheer"},
            }],
        })

        result = resemble.per_part(
            "fixture://front.png",
            [{"instance": "overlay-1", "part": "asymmetric overlay"}],
            regions={"overlay-1": "fixture://region/overlay"},
            image_id="look-1",
        )

        self.assertEqual("ANSWER", result["verdict"])
        self.assertFalse(result["candidate_contract"]
                         ["single_embedding_winner"])
        proposal = result["candidate_proposals"][0]
        self.assertEqual([
            "PROPOSE_REAR_CANDIDATE",
            "PROPOSE_CONSTRUCTION_CANDIDATE",
        ], proposal["use_scope"])
        self.assertTrue(proposal
                        ["requires_candidate_3d_and_named_human_approval"])
        self.assertTrue(proposal
                        ["not_a_pattern_sewing_or_manufacturing_fact"])
        self.assertEqual({"part", "structure", "seam", "material"},
                         set(proposal["feature_profile"]))

    def test_sewing_search_stops_before_corpus_without_approved_3d_digest(self):
        state = approved_factory_state()
        state["requires_candidate_3d_approval"] = True
        state["candidate_3d"] = {
            "candidate_id": "rear-candidate-b",
            "geometry_digest": "sha256:candidate-3d-b",
        }

        missing = sewing_search._hybrid_search_factory_state(state)

        self.assertEqual(sewing_search.CANDIDATE_3D_NOT_APPROVED,
                         missing["verdict"])
        self.assertNotIn("methods", missing)
        stale_state = copy.deepcopy(state)
        stale_state["candidate_3d_approval"] = {
            "digest": "sha256:old-candidate", "by": "Reviewer",
        }
        stale = sewing_search._hybrid_search_factory_state(stale_state)
        self.assertEqual(sewing_search.CANDIDATE_3D_APPROVAL_STALE,
                         stale["verdict"])
        self.assertNotIn("methods", stale)

    def test_approved_3d_unlocks_geometric_order_not_seam_finishing_claims(self):
        state = approved_factory_state()
        state.update({
            "requires_candidate_3d_approval": True,
            "candidate_3d": {
                "candidate_id": "rear-candidate-b",
                "geometry_digest": "sha256:candidate-3d-b",
            },
            "candidate_3d_approval": {
                "digest": "sha256:candidate-3d-b", "by": "Named Reviewer",
            },
        })

        result = sewing_search._hybrid_search_factory_state(state)

        self.assertEqual("PROPOSED", result["verdict"])
        gate = result["route"]["candidate_3d_gate"]
        self.assertEqual("HUMAN_APPROVED_CANDIDATE_3D_DIGEST",
                         gate["gate_kind"])
        self.assertEqual("Named Reviewer", gate["approved_by"])
        order = result["geometric_sewing_order"]
        self.assertEqual("DERIVED_GEOMETRY", order["state"])
        self.assertFalse(order["corpus_used"])
        self.assertEqual(sewing_search.SEAM_FINISHING_CORPUS_REQUIRED,
                         order["seam_finishing"]["verdict"])
        self.assertEqual(sewing_search.SEAM_FINISHING_CORPUS_REQUIRED,
                         result["seam_finishing_knowledge"]["verdict"])
        self.assertTrue(all(
            row["knowledge_scope"] == "GEOMETRIC_ASSEMBLY_ORDER_ONLY"
            for row in result["methods"]
        ))


if __name__ == "__main__":
    unittest.main()
