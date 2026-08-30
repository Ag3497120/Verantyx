# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import copy
import json
import unittest

from photoloset.garment_analysis_ensemble import (
    AUTO_ACCEPTED_FOR_PREVIEW,
    AUTO_PROPOSED,
    HUMAN_AUDIT,
    RETRIEVAL_STATE,
    VISION_STATE,
    analyze_garment_image,
    analyze_garment_image_async,
)


def _layered_vision() -> dict:
    return {
        "garment_instances": [
            {
                "instance_id": "blouse", "layer": 0,
                "garment_name": "white blouse",
                "parts": [
                    {"part_id": "body", "name": "bodice", "children": [
                        {"part_id": "sleeve-left", "name": "left sleeve"},
                        {"part_id": "sleeve-right", "name": "right sleeve"},
                    ]},
                ],
                "visible_observations": ["white long sleeves", "high neckline"],
                "construction_regime": "SEWN_FITTED",
                "material": {"appearance": "opaque woven-like"},
                "rear_structure": {"alternatives": ["center-back opening", "side opening"]},
                "uncertainty": {"rear": "high"},
            },
            {
                "instance_id": "vest", "layer": 1,
                "garment_name": "navy cropped vest",
                "parts": [{"name": "cropped body"}, {"name": "lapels"}],
                "construction_regime": "SEWN_FITTED",
            },
            {
                "instance_id": "trousers", "layer": 0,
                "garment_name": "red wide-leg trousers",
                "parts": [{"name": "left trouser leg"}, {"name": "right trouser leg"}],
                "visible_observations": ["two visibly separated legs"],
                "construction_regime": "SEWN_FITTED",
            },
            {
                "instance_id": "overlay", "layer": 2,
                "garment_name": "asymmetric sheer overlay",
                "parts": [{"name": "right-waist hanging panel"}],
                "construction_regime": "WRAPPED",
                "material": {"appearance": "sheer"},
                "rear_structure": {"state": "unknown", "alternatives": ["tie", "waist seam"]},
            },
        ],
        "provenance": {"request_id": "vlm-request-7"},
    }


def _layered_retrieval() -> dict:
    return {
        "matches": [
            {"instance_id": "overlay", "item_id": "item-overlay", "layer": 2,
             "label": "asymmetric sheer overlay", "score": 0.81,
             "construction_regime": "WRAPPED",
             "provenance": {"collection": "configured-index", "row": "77"}},
            {"instance_id": "trousers", "item_id": "item-trousers", "layer": 0,
             "label": "red wide-leg trousers", "score": 0.94,
             "construction_regime": "SEWN_FITTED"},
            {"instance_id": "blouse", "item_id": "item-blouse", "layer": 0,
             "label": "white blouse", "score": 0.91,
             "construction_regime": "SEWN_FITTED"},
            {"instance_id": "vest", "item_id": "item-vest", "layer": 1,
             "label": "navy cropped vest", "score": 0.87,
             "construction_regime": "SEWN_FITTED"},
        ],
    }


def _typed_vision() -> dict:
    return {
        "analysis": "provider-native prose must not become garment IR",
        "garment_instances": [{
            "instance_id": "outer-unit",
            "layer": 2,
            "garment_name": "asymmetric outer unit",
            "color": "charcoal",
            "construction_regime": "modular layered",
            "parts": [
                {
                    "part_id": "panel-right", "name": "hanging panel",
                    "side": "right", "color": "teal",
                    "message": "provider narration must be ignored",
                    "seam_topology": "must not enter visible-part IR",
                },
                {
                    "part_id": "panel-left", "name": "short panel",
                    "laterality": "left", "colors": ["black", "gray"],
                },
            ],
            "rear_structure": {
                "state": "OBSERVED",
                "manufacturing_ready": True,
                "alternatives": ["center opening", "side opening"],
            },
        }],
    }


def _request(vision=None, retrieval=None) -> dict:
    out = {
        "schema": "garment.image-analysis-ensemble.request.v1",
        "analysis_id": "layered-fixture",
        "image": {"reference": "fixture://front.png", "front_only": True},
        "provider_config": {
            "vision": {
                "provider_id": "local-openai-compatible",
                "model_id": "configured-vlm",
                "license_id": "configured-license",
            },
            "retrieval": {
                "provider_id": "marqo",
                "model_id": "Marqo/marqo-fashionSigLIP",
                "license_id": "configured-license",
                "index_id": "garments-test",
            },
        },
    }
    if vision is not None:
        out["vision"] = {"result": vision}
    if retrieval is not None:
        out["retrieval"] = {"result": retrieval}
    return out


def _states(value):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "state":
                found.append(child)
            found.extend(_states(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_states(child))
    return found


class GarmentAnalysisEnsembleTests(unittest.TestCase):
    maxDiff = None

    def test_local_api_and_retrieval_remain_independent_in_instance_graph(self):
        request = _request(None, _layered_retrieval())
        request["multimodal_sources"] = [
            {
                "source_id": "local-vlm", "provider_kind": "LOCAL",
                "result": _layered_vision(),
            },
            {
                "source_id": "api-vlm", "provider_kind": "API",
                "result": _layered_vision(),
            },
        ]

        result = analyze_garment_image(request)

        self.assertEqual("ANSWER", result["verdict"])
        graph = result["garment_instance_graph"]
        self.assertEqual("garment.instance-graph.v1", graph["schema"])
        self.assertFalse(graph["single_whole_image_class_label"])
        instances = [row["instance_id"] for row in graph["nodes"]
                     if row["node_type"] == "GARMENT_INSTANCE"]
        self.assertEqual(["blouse", "overlay", "trousers", "vest"],
                         instances)
        sources = {(row["source_id"], row["provider_kind"])
                   for row in result["capabilities"]["sources"]}
        self.assertEqual({
            ("api-vlm", "API"), ("local-vlm", "LOCAL"),
            ("retrieval", "RETRIEVAL"),
        }, sources)
        self.assertTrue(graph["uncertainty_preserved_per_source"])

    def test_one_multimodal_backend_failure_is_typed_and_does_not_erase_other(self):
        request = _request(None, _layered_retrieval())
        request["multimodal_sources"] = [
            {
                "source_id": "local-vlm", "provider_kind": "LOCAL",
                "result": _layered_vision(),
            },
            {"source_id": "api-vlm", "provider_kind": "API"},
        ]

        def unavailable(_request):
            raise RuntimeError("configured API is offline")

        result = analyze_garment_image(
            request, multimodal_providers={"api-vlm": unavailable})

        self.assertEqual("ANSWER", result["verdict"])
        sources = {row["source_id"]: row
                   for row in result["capabilities"]["sources"]}
        self.assertFalse(sources["api-vlm"]["available"])
        self.assertEqual("UNKNOWN_VISION_PROVIDER_FAILED",
                         sources["api-vlm"]["capability_failure"]["verdict"])
        self.assertTrue(sources["local-vlm"]["available"])
        self.assertEqual(1, result["capabilities"]
                         ["available_multimodal_provider_count"])
        self.assertTrue(result["capabilities"]["partial_result"])
        self.assertTrue(result["garment_instance_graph"]["nodes"])

    def test_layered_blouse_vest_trousers_and_asymmetric_overlay_stay_separate(self):
        result = analyze_garment_image(_request(
            _layered_vision(), _layered_retrieval()))

        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual(
            ["blouse", "overlay", "trousers", "vest"],
            [row["instance_id"] for row in result["garment_instances"]],
        )
        categories = {row["category"] for row in result["claims"]}
        self.assertTrue({
            "GARMENT_NAME", "VISIBLE_COMPONENT", "VISIBLE_OBSERVATION",
            "CONSTRUCTION_REGIME", "MATERIAL", "REAR_HIDDEN_STRUCTURE",
        }.issubset(categories))
        hidden = [row for row in result["claims"]
                  if row["category"] == "REAR_HIDDEN_STRUCTURE"]
        self.assertTrue(hidden)
        self.assertTrue(all(row["visibility"] == "UNOBSERVED_HIDDEN"
                            for row in hidden))
        self.assertTrue(all(row["state"] == VISION_STATE for row in hidden))
        self.assertEqual([], result["fact_promotions"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertGreaterEqual(len(result["agreements"]), 4)

    def test_skirt_vs_trouser_is_contested_and_not_averaged(self):
        vision = {
            "garment_instances": [{
                "instance_id": "lower", "layer": 0,
                "garment_name": "long skirt",
                "visible_observations": ["dark lower garment"],
            }],
        }
        retrieval = {"matches": [{
            "instance_id": "lower", "item_id": "trouser-neighbour",
            "label": "wide-leg trousers", "score": 0.97,
        }]}

        result = analyze_garment_image(_request(vision, retrieval))

        contests = [row for row in result["contested"]
                    if row["category"] == "GARMENT_NAME"]
        self.assertEqual(1, len(contests))
        self.assertEqual("CONTESTED", contests[0]["state"])
        self.assertTrue(contests[0]["no_averaging"])
        self.assertEqual(
            {"long skirt", "wide-leg trousers"},
            {row["value"] for row in contests[0]["alternatives"]},
        )
        self.assertEqual("HUMAN_REVIEW_REQUIRED", contests[0]["resolution"])

    def test_one_provider_unavailable_returns_typed_partial_result(self):
        result = analyze_garment_image(_request(_layered_vision(), None))

        self.assertEqual("ANSWER_PARTIAL", result["verdict"])
        self.assertTrue(result["capabilities"]["partial_result"])
        sources = {row["source"]: row for row in
                   result["capabilities"]["sources"]}
        unavailable = sources["MARQO_FASHION_RETRIEVAL"]
        self.assertFalse(unavailable["available"])
        self.assertEqual(
            "UNKNOWN_RETRIEVAL_PROVIDER_UNAVAILABLE",
            unavailable["capability_failure"]["verdict"],
        )
        self.assertTrue(result["claims"])
        self.assertTrue(all(row["state"] == VISION_STATE
                            for row in result["claims"]))

    def test_both_unavailable_is_a_typed_stop(self):
        result = analyze_garment_image(_request())
        self.assertEqual(
            "UNKNOWN_GARMENT_ANALYSIS_PROVIDERS_UNAVAILABLE",
            result["verdict"],
        )
        self.assertTrue(result["typed_stop"])
        self.assertEqual([], result["claims"])

    def test_no_score_or_agreement_promotes_any_claim_to_observed(self):
        result = analyze_garment_image(_request(
            _layered_vision(), _layered_retrieval()))
        claim_states = {row["state"] for row in result["claims"]}

        self.assertEqual({VISION_STATE, RETRIEVAL_STATE}, claim_states)
        self.assertNotIn("OBSERVED", _states(result))
        self.assertTrue(result["authority"]["agreement_is_not_observation"])
        self.assertTrue(result["authority"]["retrieval_score_is_not_truth"])
        retrieval_claims = [row for row in result["claims"]
                            if row["state"] == RETRIEVAL_STATE]
        self.assertTrue(retrieval_claims)
        self.assertTrue(all(row.get("score_is_not_authority") is True
                            for row in retrieval_claims))

    def test_model_and_license_metadata_are_configuration_not_correctness(self):
        result = analyze_garment_image(_request(
            _layered_vision(), _layered_retrieval()))
        for source in result["capabilities"]["sources"]:
            self.assertIn("model_id", source["configuration_metadata"])
            self.assertEqual(
                "IDENTIFICATION_AND_LICENSE_CONFIGURATION_ONLY_NOT_CORRECTNESS_EVIDENCE",
                source["configuration_metadata_role"],
            )

    def test_typed_fields_keep_parts_layers_sides_colors_regime_and_rear_separate(self):
        result = analyze_garment_image(_request(
            _typed_vision(), _layered_retrieval()))

        self.assertTrue(result["visible_parts"])
        self.assertEqual([2], [row["value"] for row in result["layers"]
                               if row["source"] == "VISION_LANGUAGE_MODEL"])
        self.assertEqual(
            {"LEFT", "RIGHT"},
            {row["value"] for row in result["laterality"]},
        )
        self.assertEqual(
            {"black", "charcoal", "gray", "teal"},
            {row["value"] for row in result["colors"]},
        )
        self.assertIn(
            "MODULAR_LAYERED",
            {row["value"] for row in result["construction_regimes"]},
        )
        self.assertEqual(
            {"center opening", "side opening"},
            {row["value"] for row in result["rear_candidates"]},
        )
        self.assertTrue(all(row["observed"] is False
                            and row["visibility"] == "UNOBSERVED_HIDDEN"
                            for row in result["rear_candidates"]))

        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
        claim_values = json.dumps(
            [row["value"] for row in result["claims"]],
            ensure_ascii=False, sort_keys=True)
        self.assertNotIn("provider-native prose", encoded)
        self.assertNotIn("provider narration", encoded)
        self.assertNotIn("seam_topology", encoded)
        self.assertNotIn("manufacturing_ready", claim_values)
        self.assertNotIn("OBSERVED", _states(result))
        self.assertFalse(result["normalization"]["provider_native_prose_enters_ir"])

    def test_retrieval_only_is_partial_and_never_manufacturing_authority(self):
        result = analyze_garment_image(_request(None, _layered_retrieval()))

        self.assertEqual("ANSWER_PARTIAL", result["verdict"])
        self.assertTrue(result["claims"])
        self.assertTrue(all(row["state"] == RETRIEVAL_STATE
                            for row in result["claims"]))
        self.assertTrue(
            result["authority"]["image_similarity_is_not_manufacturing_fact"])
        self.assertFalse(result["manufacturing_ready"])
        self.assertFalse(result["manufacturing_certified"])
        self.assertFalse(result["industrial_strength_guaranteed"])

    def test_front_oblique_authority_and_both_audit_modes_are_typed(self):
        human_request = _request(_typed_vision(), _layered_retrieval())
        human_request["image"] = {
            "reference": "fixture://arbitrary-input-a.dat",
            "front_only": True,
            "source_view": "oblique_left",
        }
        human_request["audit_mode"] = HUMAN_AUDIT
        auto_request = copy.deepcopy(human_request)
        auto_request["image"]["reference"] = "fixture://renamed-input-z.dat"
        auto_request["audit_mode"] = AUTO_PROPOSED

        human = analyze_garment_image(human_request)
        automatic = analyze_garment_image(auto_request)

        self.assertEqual("OBLIQUE", human["authority"]["source_view"]["view"])
        self.assertEqual("PROPOSED", human["authority"]["source_view"]["state"])
        self.assertEqual(HUMAN_AUDIT, human["audit_contract"]["mode"])
        self.assertEqual("HUMAN_AUDIT_REQUIRED",
                         human["audit_contract"]["preview_adoption"])
        self.assertEqual(AUTO_PROPOSED, automatic["audit_contract"]["mode"])
        self.assertEqual(AUTO_ACCEPTED_FOR_PREVIEW,
                         automatic["audit_contract"]["preview_adoption"])
        self.assertEqual("PROPOSED_AUTO_ACCEPTED_FOR_PREVIEW",
                         automatic["state"])
        self.assertFalse(automatic["audit_contract"]["observed_promotion"])
        self.assertFalse(automatic["audit_contract"]["manufacturing_certification"])
        # Renaming the image cannot change normalized semantic proposals.
        for field in (
                "claims", "agreements", "contested", "visible_parts", "layers",
                "laterality", "colors", "construction_regimes", "rear_candidates"):
            self.assertEqual(human[field], automatic[field], field)

    def test_provider_array_order_does_not_change_merge(self):
        vision_a = _layered_vision()
        retrieval_a = _layered_retrieval()
        vision_b = copy.deepcopy(vision_a)
        retrieval_b = copy.deepcopy(retrieval_a)
        vision_b["garment_instances"].reverse()
        for instance in vision_b["garment_instances"]:
            if isinstance(instance.get("parts"), list):
                instance["parts"].reverse()
            if isinstance(instance.get("visible_observations"), list):
                instance["visible_observations"].reverse()
        retrieval_b["matches"].reverse()

        first = analyze_garment_image(_request(vision_a, retrieval_a))
        second = analyze_garment_image(_request(vision_b, retrieval_b))

        self.assertEqual(
            json.dumps(first, sort_keys=True, ensure_ascii=False),
            json.dumps(second, sort_keys=True, ensure_ascii=False),
        )


class GarmentAnalysisEnsembleAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_providers_overlap_and_output_order_is_deterministic(self):
        active = 0
        max_active = 0

        async def provider(value, delay):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(delay)
            active -= 1
            return copy.deepcopy(value)

        async def vision_slow(_):
            return await provider(_layered_vision(), 0.03)

        async def retrieval_fast(_):
            return await provider(_layered_retrieval(), 0.001)

        async def vision_fast(_):
            return await provider(_layered_vision(), 0.001)

        async def retrieval_slow(_):
            return await provider(_layered_retrieval(), 0.03)

        request = _request()
        first = await analyze_garment_image_async(
            request, vision_provider=vision_slow,
            retrieval_provider=retrieval_fast,
        )
        second = await analyze_garment_image_async(
            request, vision_provider=vision_fast,
            retrieval_provider=retrieval_slow,
        )

        self.assertGreaterEqual(max_active, 2)
        self.assertEqual(
            json.dumps(first, sort_keys=True, ensure_ascii=False),
            json.dumps(second, sort_keys=True, ensure_ascii=False),
        )
        self.assertEqual(
            ["VISION_LANGUAGE_MODEL", "MARQO_FASHION_RETRIEVAL"],
            [row["source"] for row in first["capabilities"]["sources"]],
        )

    async def test_provider_timeout_is_isolated_as_a_partial_result(self):
        async def slow_vision(_):
            await asyncio.sleep(0.05)
            return _typed_vision()

        async def fast_retrieval(_):
            await asyncio.sleep(0)
            return _layered_retrieval()

        result = await analyze_garment_image_async(
            _request(), vision_provider=slow_vision,
            retrieval_provider=fast_retrieval,
            provider_timeout_seconds=0.005,
        )

        self.assertEqual("ANSWER_PARTIAL", result["verdict"])
        sources = {row["source"]: row
                   for row in result["capabilities"]["sources"]}
        self.assertEqual(
            "UNKNOWN_VISION_PROVIDER_TIMEOUT",
            sources["VISION_LANGUAGE_MODEL"]["capability_failure"]["verdict"],
        )
        self.assertTrue(sources["MARQO_FASHION_RETRIEVAL"]["available"])
        self.assertTrue(all(row["source"] == "MARQO_FASHION_RETRIEVAL"
                            for row in result["claims"]))

    async def test_sync_local_provider_error_does_not_cancel_api_provider(self):
        def broken_local_vision(_):
            raise RuntimeError("local provider fixture failure")

        async def api_retrieval(_):
            return _layered_retrieval()

        result = await analyze_garment_image_async(
            _request(), vision_provider=broken_local_vision,
            retrieval_provider=api_retrieval,
        )

        self.assertEqual("ANSWER_PARTIAL", result["verdict"])
        sources = {row["source"]: row
                   for row in result["capabilities"]["sources"]}
        self.assertEqual(
            "UNKNOWN_VISION_PROVIDER_FAILED",
            sources["VISION_LANGUAGE_MODEL"]["capability_failure"]["verdict"],
        )
        self.assertTrue(sources["MARQO_FASHION_RETRIEVAL"]["available"])

    async def test_invalid_provider_payload_isolated_during_normalization(self):
        async def malformed_vision(_):
            return {"garment_instances": [{"score": float("nan")}]}

        async def valid_retrieval(_):
            return _layered_retrieval()

        result = await analyze_garment_image_async(
            _request(), vision_provider=malformed_vision,
            retrieval_provider=valid_retrieval,
        )

        self.assertEqual("ANSWER_PARTIAL", result["verdict"])
        sources = {row["source"]: row
                   for row in result["capabilities"]["sources"]}
        self.assertEqual(
            "UNKNOWN_VISION_PROVIDER_FAILED",
            sources["VISION_LANGUAGE_MODEL"]["capability_failure"]["verdict"],
        )
        self.assertTrue(sources["MARQO_FASHION_RETRIEVAL"]["available"])


if __name__ == "__main__":
    unittest.main()
