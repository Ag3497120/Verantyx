#!/usr/bin/env python3
"""Contract tests for retrieval -> construct -> approval -> sewing search."""
from __future__ import annotations

import inspect
import unittest

from photoloset.retrieval_hypothesis import (
    CorpusProvenance, EvidenceKind, Modality, RetrievalHypothesisGate,
    Rights, Verdict,
)


def provenance(name="looks", *, rights=Rights.ALLOWED,
               lineage=("root-look-book",)):
    return CorpusProvenance(name, licence="fixture licence", rights=rights,
                            lineage=lineage, version="test-1", fixture=True)


class RetrievalHypothesisTests(unittest.TestCase):
    def setUp(self):
        self.gate = RetrievalHypothesisGate()

    def _retrieved(self):
        table = {
            "bodice": [
                {"id": "cape-bodice", "score": .91,
                 "visual_cues": {"neck": "high"}},
                {"id": "tunic-bodice", "score": .84,
                 "visual_cues": {"fit": "close"}},
            ],
            "skirt": [
                {"id": "circle-skirt", "score": .89,
                 "visual_cues": {"hem": "flared"}},
            ],
        }

        def fixture(query):
            return {"hits": table[query["part_id"]]}

        registered = self.gate.register_retrieval_source(
            "fixture:parts", Modality.REGION_EMBEDDING, fixture,
            provenance=provenance())
        self.assertEqual(registered["verdict"], "ANSWER")
        result = self.gate.retrieve_parts("image:anime-1", [
            {"region_id": "r1", "part_id": "bodice", "mask": "m1"},
            {"region_id": "r2", "part_id": "skirt", "mask": "m2"},
        ])
        self.assertEqual(result.verdict, Verdict.PROPOSED)
        return result["candidates"]

    def _constructed(self):
        fused = self.gate.fuse_per_part(self._retrieved())

        def constructor(query):
            # A fixture needs no model. It receives alternatives, not a
            # construction fact inferred from the largest similarity score.
            self.assertNotIn("winner", query)
            self.assertEqual(len(query["parts"][0]["candidates"]), 2)
            return {"hypotheses": [
                {"back_design": "zipper-back",
                 "geometry": {"panels": ["front", "back-zip"],
                              "seams": ["side", "center-back"]}},
                {"back_design": "open-cape-back",
                 "geometry": {"panels": ["front", "back-cape"],
                              "seams": ["side", "shoulder"]}},
            ]}

        result = self.gate.construct(
            fused["parts"], front_only=True, constructor=constructor,
            back_design_alternatives=("zipper-back", "open-cape-back"))
        self.assertEqual(result.verdict, Verdict.PROPOSED)
        return result["hypotheses"]

    def test_whole_image_embedding_cannot_make_part_claims(self):
        self.gate.register_retrieval_source(
            "fixture:whole", Modality.WHOLE_IMAGE_EMBEDDING,
            lambda query: {"hits": []}, provenance=provenance())
        result = self.gate.retrieve_parts(
            "image", [{"region_id": "r", "part_id": "sleeve"}])
        self.assertEqual(result.verdict, Verdict.WHOLE_IMAGE_ONLY)

    def test_embedding_hit_cannot_smuggle_construction_truth(self):
        self.gate.register_retrieval_source(
            "fixture:bad", Modality.REGION_EMBEDDING,
            lambda query: {"hits": [{"id": "look", "score": .99,
                                      "panels": ["asserted-panel"]}]},
            provenance=provenance())
        result = self.gate.retrieve_parts(
            "image", [{"region_id": "r", "part_id": "bodice"}])
        self.assertEqual(result.verdict,
                         Verdict.SIMILARITY_NOT_CONSTRUCTION)
        self.assertEqual(result["fields"], ["panels"])

    def test_fusion_preserves_sources_and_alternatives(self):
        candidates = self._retrieved()
        result = self.gate.fuse_per_part(candidates)
        bodice = next(p for p in result["parts"] if p.part_id == "bodice")
        self.assertEqual([c.reference for c in bodice.candidates],
                         ["cape-bodice", "tunic-bodice"])
        self.assertTrue(all(c.provenance.kind is EvidenceKind.VISUAL_SIMILARITY
                            for c in bodice.candidates))
        self.assertTrue(all(c.provenance.corpus.licence == "fixture licence"
                            for c in bodice.candidates))

    def test_front_only_requires_and_preserves_back_alternatives(self):
        fused = self.gate.fuse_per_part(self._retrieved())
        refused = self.gate.construct(
            fused["parts"], front_only=True,
            constructor=lambda q: {"hypotheses": []},
            back_design_alternatives=("one-back",))
        self.assertEqual(refused.verdict, Verdict.BACK_AMBIGUITY)

        hypotheses = self._constructed()
        self.assertEqual({h.selected_back_design for h in hypotheses},
                         {"zipper-back", "open-cape-back"})
        self.assertTrue(all(set(h.back_design_alternatives) ==
                            {"zipper-back", "open-cape-back"}
                            for h in hypotheses))
        self.assertEqual(len({h.digest for h in hypotheses}), 2)

    def test_named_digest_approval_is_the_only_sewing_gate(self):
        hypothesis = self._constructed()[0]
        calls = []

        def sewing(query):
            calls.append(query)
            return {"methods": [{"record": "method-7",
                                  "steps": ["join sides", "insert zip"]}]}

        self.gate.register_sewing_corpus(
            "fixture:sewing", sewing,
            provenance=provenance("sewing", lineage=("tailoring-root",)))

        blocked = self.gate.sewing_methods("made-up-approval")
        self.assertEqual(blocked.verdict, Verdict.APPROVAL_REQUIRED)
        self.assertEqual(calls, [])
        unnamed = self.gate.approve(hypothesis.hypothesis_id, approver="",
                                    expected_digest=hypothesis.digest)
        self.assertEqual(unnamed.verdict, Verdict.APPROVER_REQUIRED)
        wrong = self.gate.approve(hypothesis.hypothesis_id, approver="Mina",
                                  expected_digest="wrong")
        self.assertEqual(wrong.verdict, Verdict.APPROVAL_STALE)

        approved = self.gate.approve(
            hypothesis.hypothesis_id, approver="Mina",
            expected_digest=hypothesis.digest)
        answer = self.gate.sewing_methods(
            approved["approval"].approval_id)
        self.assertEqual(answer.verdict, Verdict.ANSWER)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["geometry_digest"], hypothesis.digest)
        self.assertEqual(answer["methods"][0]["for_approval"],
                         approved["approval"].approval_id)
        self.assertEqual(answer["methods"][0]["provenance"]["kind"],
                         EvidenceKind.CONSTRUCTION_CORPUS.value)
        self.assertEqual(answer["approval"]["approver"], "Mina")

        # The public search surface has no geometry/pattern/image bypass.
        params = list(inspect.signature(self.gate.sewing_methods).parameters)
        self.assertEqual(params, ["approval_id", "corpus_names"])

    def test_corpus_rights_and_lineage_ride_the_result(self):
        hypothesis = self._constructed()[0]
        approval = self.gate.approve(
            hypothesis.hypothesis_id, approver="Reviewer",
            expected_digest=hypothesis.digest)["approval"]
        self.gate.register_sewing_corpus(
            "fixture:no-rights", lambda q: {"methods": []},
            provenance=provenance("private", rights=Rights.UNKNOWN))
        refused = self.gate.sewing_methods(approval.approval_id)
        self.assertEqual(refused.verdict, Verdict.RIGHTS)

        gate = RetrievalHypothesisGate()
        # Recreate the approval in this gate through its normal route.
        self.gate = gate
        hypothesis = self._constructed()[0]
        approval = gate.approve(hypothesis.hypothesis_id, approver="Reviewer",
                                expected_digest=hypothesis.digest)["approval"]
        for name in ("sew-a", "sew-b"):
            gate.register_sewing_corpus(
                "fixture:" + name,
                lambda q, n=name: {"methods": [{"record": n}]},
                provenance=provenance(name, lineage=("same-generator",)))
        answer = gate.sewing_methods(approval.approval_id)
        self.assertEqual(answer["lineage_groups"]["same-generator"],
                         ["fixture:sew-a", "fixture:sew-b"])
        self.assertTrue(all(m["provenance"]["corpus"]["lineage"] ==
                            ["same-generator"] for m in answer["methods"]))


if __name__ == "__main__":
    unittest.main()
