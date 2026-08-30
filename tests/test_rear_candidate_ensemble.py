#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import unittest

from photoloset.rear_candidate_ensemble import (
    CONTESTED,
    HYPOTHESIS_AXES,
    REQUEST_SCHEMA,
    PROPOSED,
    SHAPE_NOT_APPROVED,
    UNKNOWN_UNOBSERVED,
    generate_rear_candidates,
    sewing_search_gate,
    stable_digest,
)


def _visible_unknown_anime():
    return {
        "graph_id": "anime-front-1",
        "garment_name": "unclassifiable anime costume",
        "parts": [
            {
                "part_id": "torso-mystery",
                "kind": "UNKNOWN_ANIME_BODY_SURFACE",
                "garment_unit": "anime-upper",
                "layer": 0,
                "placement": "front torso",
            },
            {
                "part_id": "fin-right",
                "kind": "UNKNOWN_ASYMMETRIC_FIN",
                "garment_unit": "anime-upper",
                "layer": 2,
                "side": "right",
                "placement": "right shoulder to hip",
            },
        ],
    }


def _layered_separates():
    return {
        "graph_id": "layered-front-1",
        "parts": [
            {"part_id": "blouse-body", "kind": "BODY_SHELL",
             "garment_unit": "blouse", "layer": 0},
            {"part_id": "blouse-sleeve-left", "kind": "SLEEVE",
             "garment_unit": "blouse", "layer": 0, "side": "left"},
            {"part_id": "vest-body", "kind": "BODY_SHELL",
             "garment_unit": "vest", "layer": 1},
            {"part_id": "trouser-left", "kind": "TUBE",
             "garment_unit": "trousers", "layer": 0, "side": "left"},
            {"part_id": "trouser-right", "kind": "TUBE",
             "garment_unit": "trousers", "layer": 0, "side": "right"},
            {"part_id": "sheer-wrap", "kind": "OVERLAY",
             "garment_unit": "waist-overlay", "layer": 2, "side": "right"},
        ],
        "relations": [
            {"relation_id": "visible-overlay-layer",
             "kind": "LAYER", "source": "sheer-wrap",
             "target": "trouser-right", "connection": "OVERLAP"},
        ],
    }


def _simple_skirt():
    return {
        "graph_id": "skirt-front-1",
        "parts": [
            {"part_id": "waistband", "kind": "BAND",
             "garment_unit": "skirt", "layer": 0},
            {"part_id": "skirt-body", "kind": "FLARED_SURFACE",
             "garment_unit": "skirt", "layer": 0,
             "placement": "waist to calf"},
        ],
        "relations": [
            {"relation_id": "waistband-to-skirt", "kind": "ATTACH",
             "source": "waistband", "target": "skirt-body"},
        ],
    }


def _simple_trousers():
    return {
        "graph_id": "trousers-front-1",
        "parts": [
            {"part_id": "trouser-waist", "kind": "BAND",
             "garment_unit": "trousers", "layer": 0},
            {"part_id": "leg-left", "kind": "TUBE",
             "garment_unit": "trousers", "layer": 0, "side": "left"},
            {"part_id": "leg-right", "kind": "TUBE",
             "garment_unit": "trousers", "layer": 0, "side": "right"},
        ],
        "relations": [
            {"relation_id": "crotch-front", "kind": "JOIN",
             "source": "leg-left", "target": "leg-right"},
        ],
    }


def _fashion_hits():
    return {
        "schema": "marqo-fashion-siglip.retrieval-result.v1",
        "matches": [
            {
                "item_id": "look-center-zip", "score": 0.97,
                "parts": ["rear bodice", "two trouser backs", "overlay"],
                "rear_structure": {
                    "configuration": "center back zip opening",
                    "layer_order": ["blouse", "vest", "overlay"],
                },
                "seam_topology": ["center back zip", "side seams"],
                "material": {"family": "woven", "drape": "medium"},
                "provenance": {"index": "fixture-fashion-index", "row": 7},
            },
            {
                "item_id": "look-center-zip-lower-score", "score": 0.41,
                "parts": ["rear bodice", "two trouser backs", "overlay"],
                "rear_structure": {
                    "configuration": "center back zip opening",
                    "layer_order": ["blouse", "vest", "overlay"],
                },
                "seam_topology": ["center back zip", "side seams"],
                "material": {"family": "woven", "drape": "medium"},
            },
        ],
    }


def _multimodal_proposals():
    return {
        "proposals": [
            {
                "proposal_id": "model-side-opening",
                "model_id": "fixture-vlm",
                "rear_structure": {
                    "state": "OBSERVED",
                    "configuration": "closed back with side opening",
                    "layer_order": ["blouse", "vest", "overlay"],
                },
                "parts": ["continuous blouse back", "trouser backs",
                          "asymmetric overlay continuation"],
                "seams": ["side opening", "shoulder continuation"],
                "material": {
                    "state": "OBSERVED", "family": "knit",
                    "drape": "soft",
                },
                "provenance": {"request_id": "vlm-22"},
            },
        ],
    }


def _geometric_rule_evidence():
    return {
        "rules": [{
            "id": "rule-rear-balance",
            "rule_set_id": "fixture-geometric-rules",
            "closure": "center back join",
            "back_volume": "flared volume",
            "layer_continuation": "continue each visible layer",
            "attachment_topology": "shoulder yoke anchor",
            "rear_structure": {
                "configuration": "center back join",
                "volume_profile": "flared volume",
            },
        }],
    }


def _user_audit_evidence():
    return {
        "audits": [{
            "id": "audit-visible-wrap",
            "auditor": "fixture reviewer",
            "closure": "overlapped wrap closure",
            "back_volume": "asymmetric draped volume",
            "layer_continuation": "terminate at side anchor",
            "attachment_topology": "waist anchored",
            "parts": ["audited visible asymmetric overlay"],
        }],
    }


def _all_state_values(value):
    states = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"state", "observation_state", "visibility"}:
                states.append(child)
            states.extend(_all_state_values(child))
    elif isinstance(value, list):
        for child in value:
            states.extend(_all_state_values(child))
    return states


class RearCandidateEnsembleTests(unittest.TestCase):
    maxDiff = None

    def test_unknown_anime_parts_get_class_independent_distinct_geometry(self):
        result = generate_rear_candidates(_visible_unknown_anime())

        self.assertEqual(PROPOSED, result["verdict"])
        self.assertGreaterEqual(result["candidate_count"], 2)
        self.assertEqual(
            result["candidate_count"],
            len({row["structure_signature"] for row in result["candidates"]}),
        )
        self.assertTrue(all(
            row["origin"] == "GEOMETRY_ONLY_FALLBACK"
            for row in result["candidates"]
        ))
        for candidate in result["candidates"]:
            rear_values = [
                row["value"]
                for row in candidate["rear_structure"]["value"]["rear_parts"]
            ]
            self.assertEqual(
                {"UNKNOWN_ANIME_BODY_SURFACE", "UNKNOWN_ASYMMETRIC_FIN"},
                {row["kind"] for row in rear_values},
            )
            self.assertFalse(candidate["rear_structure"]["value"]
                             ["garment_name_used_for_geometry"])
            self.assertTrue(candidate["human_approval_required"])
            self.assertFalse(candidate["auto_approved"])

    def test_layered_separates_preserve_units_layers_and_ownership(self):
        result = generate_rear_candidates(_layered_separates())
        expected_units = {
            "blouse", "vest", "trousers", "waist-overlay",
        }

        for candidate in result["candidates"]:
            rear = candidate["rear_structure"]["value"]
            self.assertEqual(expected_units, set(rear["garment_units"]))
            self.assertEqual([0, 1, 2], rear["layers"])
            self.assertFalse(rear["cross_garment_unit_joins_added"])
            parts = [row["value"] for row in rear["rear_parts"]]
            self.assertEqual(expected_units,
                             {row["garment_unit"] for row in parts})
            for relation in rear["hidden_relations"]:
                self.assertIn(relation["value"]["garment_unit"],
                              expected_units)

    def test_typed_rear_hypotheses_are_class_independent_and_front_preserving(self):
        fixtures = {
            "skirt": _simple_skirt(),
            "trousers": _simple_trousers(),
            "layered-asymmetric": _layered_separates(),
            "anime-like": _visible_unknown_anime(),
        }

        for name, graph in fixtures.items():
            with self.subTest(name=name):
                result = generate_rear_candidates(graph)
                self.assertGreaterEqual(result["candidate_count"], 2)
                self.assertEqual(
                    result["candidate_count"],
                    len({candidate["structure_signature"]
                         for candidate in result["candidates"]}),
                )
                visible_digest = result["visible_part_graph_digest"]
                profiles = set()
                for candidate in result["candidates"]:
                    hypothesis = candidate["rear_hypothesis"]
                    self.assertEqual(
                        set(HYPOTHESIS_AXES),
                        set(hypothesis["axis_values"]),
                    )
                    self.assertTrue(hypothesis["axes_are_independent"])
                    self.assertTrue(hypothesis["conflicts_are_not_averaged"])
                    self.assertFalse(hypothesis["front_mutation_allowed"])
                    profiles.add(tuple(
                        hypothesis["axis_values"][axis]
                        for axis in HYPOTHESIS_AXES))
                    front = candidate["front_preservation_contract"]
                    self.assertEqual(front["visible_graph_digest"],
                                     visible_digest)
                    self.assertTrue(front[
                        "visible_front_is_immutable_across_rear_alternatives"])
                    self.assertEqual(front["allowed_mutation_domain"],
                                     "UNOBSERVED_REAR_ONLY")
                    self.assertTrue(candidate[
                        "candidate_specific_3d_required"])
                    self.assertFalse(candidate["generic_fallback_used"])
                    self.assertFalse(candidate["rear_structure"]["value"]
                                     ["generic_cape_fallback_used"])
                self.assertGreaterEqual(len(profiles), 2)

    def test_no_retrieval_backend_has_two_deterministic_no_corpus_fallbacks(self):
        request = {
            "schema": REQUEST_SCHEMA,
            "visible_part_graph": _layered_separates(),
        }
        first = generate_rear_candidates(request)
        second = generate_rear_candidates(copy.deepcopy(request))

        self.assertEqual("DETERMINISTIC_GEOMETRY_ONLY",
                         first["provider_status"]["mode"])
        self.assertEqual(2, first["candidate_count"])
        self.assertEqual(first, second)
        self.assertEqual(first["digest"], stable_digest({
            key: value for key, value in first.items() if key != "digest"
        }))
        for candidate in first["candidates"]:
            provenance = candidate["provenance"]
            self.assertFalse(provenance["corpus_used"])
            self.assertIsNone(provenance["corpus"])
            self.assertEqual([], provenance["sources"])

    def test_retrieval_and_multimodal_are_scored_per_aspect_not_one_embedding(self):
        result = generate_rear_candidates(
            _layered_separates(),
            fashion_siglip_hits=_fashion_hits(),
            multimodal_proposals=_multimodal_proposals(),
        )

        fields = {row["field"] for row in result["source_claims"]}
        self.assertTrue(
            {"structure", "parts", "seams", "material"}.issubset(fields))
        self.assertTrue({"closure", "layer_continuation"}.issubset(fields))
        source_pairs = {
            (row["provenance"]["source_kind"],
             row["provenance"]["source_id"])
            for row in result["source_claims"]
        }
        self.assertIn(("FASHION_SIGLIP_RETRIEVAL", "look-center-zip"),
                      source_pairs)
        self.assertIn(("MULTIMODAL_MODEL_PROPOSAL", "model-side-opening"),
                      source_pairs)
        self.assertFalse(result["ranking"]["single_embedding_winner"])
        self.assertTrue(result["ranking"][
            "fashion_siglip_score_is_not_construction_authority"])
        self.assertIsNone(result["selected_candidate_id"])
        for candidate in result["candidates"]:
            self.assertEqual(
                {"structure", "parts", "seams", "material"},
                set(candidate["ranking_vector"]["axis_scores"]),
            )
            self.assertFalse(candidate["ranking_vector"]["source_score_used"])
            self.assertTrue(candidate["rank_only_not_authority"])

    def test_all_four_independent_evidence_channels_preserve_conflicts(self):
        result = generate_rear_candidates(
            _layered_separates(),
            fashion_siglip_hits=_fashion_hits(),
            multimodal_proposals=_multimodal_proposals(),
            geometric_rule_evidence=_geometric_rule_evidence(),
            user_audit_evidence=_user_audit_evidence(),
        )

        source_kinds = {
            claim["provenance"]["source_kind"]
            for claim in result["source_claims"]
        }
        self.assertEqual(source_kinds, {
            "FASHION_SIGLIP_RETRIEVAL",
            "MULTIMODAL_MODEL_PROPOSAL",
            "GEOMETRIC_RULE_EVIDENCE",
            "USER_AUDIT_EVIDENCE",
        })
        self.assertTrue(result["provider_status"]["fashion_siglip"]
                        ["available"])
        self.assertTrue(result["provider_status"]["multimodal"]
                        ["available"])
        self.assertTrue(result["provider_status"]["geometric_rules"]
                        ["available"])
        self.assertTrue(result["provider_status"]["user_audit"]
                        ["available"])

        contested = {row["aspect"]: row for row in result["contested"]}
        for axis in HYPOTHESIS_AXES:
            self.assertIn(axis, contested)
            self.assertEqual(contested[axis]["state"], CONTESTED)
            self.assertTrue(contested[axis]["no_averaging"])
            self.assertGreaterEqual(len(contested[axis]["alternatives"]), 2)
            self.assertTrue(all(
                alternative["state"] == PROPOSED
                for alternative in contested[axis]["alternatives"]))

        candidate_source_kinds = {
            source["source_kind"]
            for candidate in result["candidates"]
            if candidate["origin"] != "GEOMETRY_ONLY_FALLBACK"
            for source in candidate["provenance"]["sources"]
        }
        self.assertEqual(candidate_source_kinds, source_kinds)
        for candidate in result["candidates"]:
            self.assertTrue(candidate["rear_hypothesis"]
                            ["conflicts_are_not_averaged"])
            self.assertFalse(candidate["rear_hypothesis"]
                             ["front_mutation_allowed"])

    def test_contradictory_sources_are_separate_proposals_never_averaged(self):
        result = generate_rear_candidates(
            _layered_separates(),
            fashion_siglip_hits=_fashion_hits(),
            multimodal_proposals=_multimodal_proposals(),
        )

        contested = {row["aspect"]: row for row in result["contested"]}
        self.assertIn("structure", contested)
        self.assertIn("material", contested)
        self.assertTrue(contested["structure"]["no_averaging"])
        self.assertTrue(contested["material"]["no_averaging"])
        self.assertEqual(CONTESTED, contested["structure"]["state"])
        source_strategies = {
            row["strategy"] for row in result["candidates"]
            if row["origin"] != "GEOMETRY_ONLY_FALLBACK"
        }
        self.assertGreaterEqual(len(source_strategies), 2)
        self.assertIn("CENTER_BACK_OPENING", source_strategies)
        self.assertIn("CLOSED_BACK_SIDE_OPENING", source_strategies)

        # Provider-native OBSERVED assertions are stripped at this boundary.
        for claim in result["source_claims"]:
            self.assertEqual(PROPOSED, claim["state"])
            self.assertEqual(UNKNOWN_UNOBSERVED,
                             claim["observation_state"])
            self.assertNotIn("OBSERVED", _all_state_values(claim))
            self.assertTrue(claim["basis"])
            self.assertTrue(claim["breaks_when"])
            self.assertTrue(claim["provenance"])
            self.assertTrue(claim["digest"])

    def test_rear_hidden_and_material_fields_have_falsifiable_provenance(self):
        result = generate_rear_candidates(
            _visible_unknown_anime(),
            multimodal_proposals=_multimodal_proposals(),
        )
        for candidate in result["candidates"]:
            rear = candidate["rear_structure"]
            self.assertEqual(PROPOSED, rear["state"])
            self.assertEqual(UNKNOWN_UNOBSERVED, rear["observation_state"])
            self.assertFalse(rear["observed"])
            self.assertTrue(rear["basis"])
            self.assertTrue(rear["breaks_when"])
            self.assertTrue(rear["provenance"])
            self.assertTrue(rear["digest"])
            for hidden in (rear["value"]["rear_parts"]
                           + rear["value"]["hidden_relations"]):
                self.assertEqual(PROPOSED, hidden["state"])
                self.assertEqual(UNKNOWN_UNOBSERVED,
                                 hidden["observation_state"])
                self.assertFalse(hidden["observed"])
                self.assertTrue(hidden["basis"])
                self.assertTrue(hidden["breaks_when"])
                self.assertTrue(hidden["provenance"])
                self.assertTrue(hidden["digest"])
            for material in candidate["material_hypotheses"]:
                self.assertEqual(PROPOSED, material["state"])
                self.assertEqual(UNKNOWN_UNOBSERVED,
                                 material["observation_state"])
                self.assertFalse(material["observed"])
                self.assertTrue(material["basis"])
                self.assertTrue(material["breaks_when"])
                self.assertTrue(material["provenance"])
                self.assertTrue(material["digest"])

    def test_sewing_search_is_blocked_until_named_digest_approval(self):
        result = generate_rear_candidates(_visible_unknown_anime())
        self.assertFalse(result["sewing_search_before_human_approval"])
        self.assertEqual(SHAPE_NOT_APPROVED,
                         result["sewing_search_gate"]["verdict"])
        self.assertFalse(result["sewing_search_gate"]["allowed"])
        self.assertFalse(result["sewing_search_gate"]["sewing_search_invoked"])

        candidate = result["candidates"][0]
        unnamed = sewing_search_gate(result, {
            "kind": "HUMAN_APPROVAL", "approver": "",
            "candidate_id": candidate["candidate_id"],
            "candidate_digest": candidate["candidate_digest"],
        })
        self.assertEqual(SHAPE_NOT_APPROVED, unnamed["verdict"])
        stale = sewing_search_gate(result, {
            "kind": "HUMAN_APPROVAL", "approver": "Mina",
            "candidate_id": candidate["candidate_id"],
            "candidate_digest": "stale",
        })
        self.assertEqual("UNKNOWN_GEOMETRY_APPROVAL_STALE", stale["verdict"])
        approved = sewing_search_gate(result, {
            "kind": "HUMAN_APPROVAL", "approver": "Mina",
            "candidate_id": candidate["candidate_id"],
            "candidate_digest": candidate["candidate_digest"],
        })
        self.assertTrue(approved["allowed"])
        self.assertFalse(approved["sewing_search_invoked"])
        self.assertFalse(approved["automatic_invocation"])

    def test_source_order_does_not_change_claims_candidates_or_digest(self):
        fashion = _fashion_hits()
        multimodal = _multimodal_proposals()
        fashion_reversed = copy.deepcopy(fashion)
        fashion_reversed["matches"].reverse()
        multimodal_reversed = copy.deepcopy(multimodal)
        multimodal_reversed["proposals"].reverse()

        first = generate_rear_candidates(
            _layered_separates(), fashion_siglip_hits=fashion,
            multimodal_proposals=multimodal,
        )
        second = generate_rear_candidates(
            copy.deepcopy(_layered_separates()),
            fashion_siglip_hits=fashion_reversed,
            multimodal_proposals=multimodal_reversed,
        )
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True),
            json.dumps(second, ensure_ascii=False, sort_keys=True),
        )


if __name__ == "__main__":
    unittest.main()
