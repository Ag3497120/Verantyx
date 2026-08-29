#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest

from photoloset import corpus_manifest, garment_factory, mcp, retrieval_hypothesis
from photoloset import sewing_search


def manifest(name: str, modalities, *, commercial="allowed"):
    return {
        "schema": "garment.corpus-manifest.v1",
        "name": name,
        "version": "fixture-1",
        "license": {
            "url": f"https://example.invalid/{name}/license",
            "rights": {"commercial_use": commercial,
                       "derivatives": "allowed",
                       "redistribution": "allowed"},
        },
        "lineage": [{"source": f"fixture:{name}:root"}],
        "modalities": list(modalities),
        "record_format": {"units": "SI",
                          "schema_url": f"https://example.invalid/{name}/schema"},
    }


def image_request(**extra):
    request = {
        "outline": {"outline": [[0, 0], [20, 0], [20, 80], [0, 80]]},
        "regions": [
            {"region_id": "r-bodice", "part_id": "bodice"},
            {"region_id": "r-skirt", "part_id": "skirt"},
        ],
        "front_only": True,
        "request": {
            "shape": {"fit": "close", "hem": "flared"},
            "parts": ["bodice", "skirt"],
            "layers": ["base", "overlay"],
            "openings": ["center back"],
            "seam_topology": ["side join", "waist join"],
            "material_ranges": {
                "areal_density_kg_m2": [0.15, 0.35],
                "stretch_ratio": [1.0, 1.25],
            },
        },
    }
    request.update(extra)
    return request


def approved_factory_state():
    state = garment_factory.new_job("hybrid-test")
    confirmed = garment_factory.advance(state, {
        "type": "CONFIRM_IMAGE",
        "outline": image_request()["outline"],
        "regions": image_request()["regions"],
        "front_only": True,
    })
    retrieved = garment_factory.advance(confirmed["state"], {
        "type": "HYBRID_RETRIEVE",
        "request": image_request()["request"],
    })
    candidate = retrieved["state"]["hypothesis_sheet"]["candidates"][0]
    approved = garment_factory.advance(retrieved["state"], {
        "type": "APPROVE_HYPOTHESIS",
        "candidate_id": candidate["candidate_id"],
        "digest": candidate["digest"], "by": "Fixture Reviewer",
    })
    return approved["state"]


class HybridGarmentRetrievalTests(unittest.TestCase):
    def test_empty_corpus_returns_two_honest_procedural_hits_and_hypotheses(self):
        result = retrieval_hypothesis.multi_stage_retrieve(image_request())
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(set(("verdict", "source", "hits", "route",
                              "corpus_status", "hypotheses")) - set(result), set())
        self.assertGreaterEqual(len(result["hits"]), 2)
        self.assertGreaterEqual(len(result["hypotheses"]), 2)
        self.assertTrue(all(hit["reference"].startswith("procedural:")
                            for hit in result["hits"]))
        self.assertTrue(all(not hit["provenance"]["real_corpus_record"]
                            for hit in result["hits"]))
        self.assertEqual(result["source"]["name"],
                         "procedural:geometry-hybrid-no-corpus")
        self.assertEqual(result["source"]["modality"], "structure_embedding")
        self.assertEqual(len({row["back_design"]
                              for row in result["hypotheses"]}),
                         len(result["hypotheses"]))
        self.assertTrue(all(row["state"] == "PROPOSED"
                            and row["provenance"]["origin"] ==
                            "PROCEDURAL_GEOMETRY_COMPOSITION"
                            for row in result["hypotheses"]))
        shell = result["hypotheses"][0]["structure"]["nodes"][0]
        self.assertEqual(shell["attributes"]["observed_outline_metrics"]
                         ["width_height_ratio"], 0.25)
        self.assertTrue(shell["attributes"]
                        ["outline_units_are_not_centimetres"])
        self.assertEqual(result["corpus_status"]["mode"], "PROCEDURAL_ONLY")
        self.assertFalse(result["corpus_status"]["real_corpus_search_performed"])

    def test_local_corpus_is_scored_per_axis_and_kept_distinct(self):
        structure = {
            "schema": "garment.structure.v1",
            "nodes": [{"node_id": "shell", "kind": "BODY_SHELL",
                       "dimensions": {"height_cm": 88.0,
                                      "circumference_cm": 94.0}}],
            "operations": [],
        }
        package = {
            "manifest": manifest("local-looks",
                                 ["garment_images", "structure_graphs"]),
            "records": [{
                "record_id": "look-17",
                "features": image_request()["request"],
                "back_design": "corpus_laced_back",
                "structure": structure,
            }],
        }
        result = retrieval_hypothesis.multi_stage_retrieve(
            image_request(corpora=[package]))
        corpus_hits = [row for row in result["hits"]
                       if row["reference"].startswith("corpus:")]
        procedural = [row for row in result["hits"]
                      if row["reference"].startswith("procedural:")]
        self.assertEqual(len(corpus_hits), 1)
        self.assertGreaterEqual(len(procedural), 2)
        self.assertTrue(corpus_hits[0]["provenance"]["real_corpus_record"])
        ranking = result["route"]["multi_stage_ranking"][0]["fit"]
        self.assertEqual(set(ranking["axis_scores"]), {
            "shape", "parts", "layers", "openings", "seam_topology",
            "material_ranges"})
        self.assertFalse(ranking["single_embedding_winner"])
        self.assertEqual(result["corpus_status"]["corpus_hits"], 1)
        self.assertTrue(all(row["provenance"]["origin"] ==
                            "PROCEDURAL_GEOMETRY_COMPOSITION"
                            for row in result["hypotheses"]))
        self.assertEqual(len(result["route"]["corpus_structure_proposals"]), 1)
        self.assertTrue(result["route"]["corpus_structure_proposals"][0]
                        ["provenance"]["real_corpus_record"])

    def test_unknown_commercial_rights_fall_back_without_false_corpus_hit(self):
        package = {
            "manifest": manifest("unclear", ["garment_images"],
                                 commercial="unknown"),
            "records": [{"record_id": "unusable",
                         "features": image_request()["request"]}],
        }
        result = retrieval_hypothesis.multi_stage_retrieve(
            image_request(corpora=[package]))
        self.assertTrue(all(row["reference"].startswith("procedural:")
                            for row in result["hits"]))
        self.assertEqual(result["corpus_status"]["eligible"], 0)
        self.assertEqual(result["corpus_status"]["refused"][0]["verdict"],
                         "UNKNOWN_CORPUS_COMMERCIAL_RIGHTS")

    def test_factory_accepts_proposed_regionpicker_evidence_and_hybrid_route(self):
        state = garment_factory.new_job("region-picker")
        proposed = garment_factory.advance(state, {
            "type": "CONFIRM_IMAGE", "outline": image_request()["outline"],
            "regions": image_request()["regions"],
            "evidence_state": "PROPOSED", "front_only": True,
        })
        self.assertEqual(proposed["state"]["image_evidence"]["state"],
                         "PROPOSED")
        routed = garment_factory.advance(proposed["state"], {
            "type": "HYBRID_RETRIEVE",
            "request": image_request()["request"],
        })
        self.assertEqual(routed["verdict"], "PROPOSED")
        self.assertEqual(routed["state"]["phase"], "BACK_CANDIDATES_READY")
        self.assertGreaterEqual(
            len(routed["state"]["hypothesis_sheet"]["candidates"]), 2)
        self.assertEqual(routed["state"]["hybrid_retrieval"]["verdict"],
                         "PROPOSED")

        refused = garment_factory.advance(state, {
            "type": "CONFIRM_IMAGE", "outline": image_request()["outline"],
            "regions": image_request()["regions"],
            "evidence_state": "ANSWER",
        })
        self.assertEqual(refused["verdict"],
                         "UNKNOWN_IMAGE_EVIDENCE_STATE")
        self.assertIsNone(refused["state"]["image_evidence"])

    def test_mcp_tool_returns_factory_ready_events_and_top_level_hypotheses(self):
        result = json.loads(mcp.TOOLS["garment_hybrid_retrieve"](
            json.dumps(image_request())))
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertGreaterEqual(len(result["hypotheses"]), 2)
        events = result["route"]["factory_events"]
        self.assertEqual([row["type"] for row in events],
                         ["SUBMIT_RETRIEVAL", "SUBMIT_HYPOTHESES"])
        self.assertEqual(events[0]["source"], result["source"])
        self.assertEqual(events[1]["hypotheses"], result["hypotheses"])


class HybridSewingSearchTests(unittest.TestCase):
    def test_unapproved_state_cannot_search(self):
        result = sewing_search._hybrid_search_factory_state(
            garment_factory.new_job("blocked"))
        self.assertEqual(result["verdict"], "UNKNOWN_SHAPE_NOT_APPROVED")

    def test_no_corpus_returns_only_explicit_procedural_methods(self):
        state = approved_factory_state()
        result = sewing_search._hybrid_search_factory_state(state)
        self.assertEqual(result["verdict"], "PROPOSED")
        self.assertEqual(len(result["methods"]), 2)
        self.assertTrue(all(row["method_id"].startswith("procedural:")
                            and not row["real_corpus_record"]
                            and not row["manufacturing_validated"]
                            for row in result["methods"]))
        self.assertEqual(result["route"]["shape_approval_id"],
                         state["shape_approval"]["approval_id"])
        self.assertEqual(result["corpus_status"]["mode"], "PROCEDURAL_ONLY")
        self.assertFalse(result["real_corpus_records_present"])
        checked = corpus_manifest.validate(result["manifest"],
                                           require_commercial=True,
                                           purpose="sewing")
        self.assertEqual(checked["verdict"], "ANSWER")
        self.assertFalse(result["manifest"]["real_corpus_records_present"])
        event = result["route"]["factory_event"]
        self.assertEqual(event["type"], "SUBMIT_SEWING_METHODS")
        self.assertEqual(event["manifest"], result["manifest"])
        self.assertEqual(event["methods"], result["methods"])

    def test_real_construction_record_and_procedural_plan_are_not_mixed(self):
        state = approved_factory_state()
        package = {
            "manifest": manifest("local-sewing",
                                 ["patterns_2d", "sewing_construction"]),
            "records": [{
                "record_id": "method-9",
                "features": {"parts": ["BODY_SHELL", "FLARE"],
                             "layers": [0], "openings": ["center back"]},
                "method": {"steps": ["join side seams", "install closure"],
                           "stitches": ["lockstitch"]},
                "manufacturing_validated": True,
            }],
        }
        result = sewing_search._hybrid_search_factory_state(state, [package])
        corpus_rows = [row for row in result["methods"]
                       if row["real_corpus_record"]]
        generated = [row for row in result["methods"]
                     if not row["real_corpus_record"]]
        self.assertEqual(len(corpus_rows), 1)
        self.assertEqual(len(generated), 2)
        self.assertEqual(corpus_rows[0]["provenance"]["corpus"],
                         "local-sewing")
        self.assertEqual(generated[0]["provenance"]["corpus"], None)
        self.assertTrue(result["real_corpus_records_present"])
        self.assertTrue(result["manifest"]["real_corpus_records_present"])

        via_factory = garment_factory.advance(state, {
            "type": "HYBRID_SEWING_SEARCH", "corpora": [package]})
        self.assertEqual(via_factory["verdict"], "PROPOSED")
        self.assertEqual(via_factory["state"]["phase"],
                         "SEWING_CANDIDATES_READY")
        self.assertEqual(via_factory["state"]["sewing"]["route"]
                         ["shape_approval_id"],
                         state["shape_approval"]["approval_id"])

    def test_mcp_does_not_expose_a_forgeable_state_sewing_bypass(self):
        self.assertNotIn("garment_hybrid_sewing_search", mcp.TOOLS)

    def test_factory_event_routes_approved_state_to_sewing_search(self):
        state = approved_factory_state()
        patterned = garment_factory.advance(
            state, {"type": "GENERATE_PATTERN"},
            pattern_runner=lambda _state, _event: {
                "verdict": "ANSWER", "digest": "sha256:pattern",
                "pieces": [{"piece_id": "front"}, {"piece_id": "back"}],
            })
        routed = garment_factory.advance(patterned["state"], {
            "type": "HYBRID_SEWING_SEARCH", "corpora": [],
            "require_commercial": True})
        self.assertEqual(routed["verdict"], "PROPOSED")
        self.assertEqual(routed["state"]["phase"],
                         "SEWING_CANDIDATES_READY")
        self.assertFalse(routed["state"]["sewing"]["methods"][0]
                         ["real_corpus_record"])


if __name__ == "__main__":
    unittest.main()
