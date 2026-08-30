# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from photoloset.garment_analysis_ensemble import analyze_garment_image
from photoloset.marqo_fashion_siglip_adapter import (
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_LICENSE,
    METADATA_ROLE,
    PROPOSAL_STATE,
    MarqoFashionSigLIPAdapter,
    capability_probe,
    run_retrieval,
)


def _licensed_item(item_id: str, score=None, embedding=None) -> dict:
    out = {
        "item_id": item_id,
        "label": "wide-leg trousers",
        "asset": {"uri": f"fixture://{item_id}.png", "asset_id": item_id},
        "license": {"spdx": "CC-BY-4.0", "commercial_use": True},
        "source": {"collection": "rights-reviewed-fixture", "row": item_id},
        "rights_review": {"state": "REVIEWED", "review_id": f"rr-{item_id}"},
        "provenance": {"index_revision": "fixture-r1"},
    }
    if score is not None:
        out["score"] = score
    if embedding is not None:
        out["embedding"] = embedding
    return out


class _FakeEmbedder:
    def __init__(self):
        self.calls = []

    def embed(self, query):
        self.calls.append(query)
        return [1.0, 0.0]


class _FakeIndex:
    def __init__(self):
        self.calls = []

    def search(self, embedding, top_k=10):
        self.calls.append((embedding, top_k))
        return {"matches": [
            _licensed_item("local-b", score=0.72),
            _licensed_item("local-a", score=0.91),
        ]}


class MarqoFashionSigLIPAdapterTests(unittest.TestCase):
    maxDiff = None

    def test_import_has_no_model_runtime_or_network_import_side_effect(self):
        code = (
            "import json, sys; "
            "import photoloset.marqo_fashion_siglip_adapter; "
            "print(json.dumps({"
            "'transformers': 'transformers' in sys.modules, "
            "'open_clip': 'open_clip' in sys.modules, "
            "'urllib_request': 'urllib.request' in sys.modules}))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code], check=True, text=True,
            capture_output=True,
        )
        loaded = json.loads(completed.stdout)
        self.assertEqual({
            "transformers": False,
            "open_clip": False,
            "urllib_request": False,
        }, loaded)

    def test_capability_probe_does_not_contact_endpoint_or_load_model(self):
        calls = []

        def transport(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("capability probe must not use transport")

        adapter = MarqoFashionSigLIPAdapter(
            transport=transport, dependency_probe=lambda _name: False)
        result = adapter.capabilities({
            "config": {
                "endpoint": "http://127.0.0.1:48123/infer",
                "allow_http": True,
                "model_path": "/definitely/not/present",
            },
        })

        self.assertEqual("ANSWER", result["verdict"])
        self.assertFalse(result["network_probe_performed"])
        self.assertFalse(result["model_loaded"])
        self.assertFalse(result["downloads_attempted"])
        self.assertEqual([], calls)
        self.assertEqual("NOT_PROBED", result["modes"]["local_http"]["endpoint_reachable"])
        self.assertTrue(result["modes"]["local_http"]["ready"])
        self.assertFalse(result["modes"]["local_model"]["model_path_exists"])

    def test_default_metadata_is_identification_not_correctness_evidence(self):
        result = capability_probe({})
        metadata = result["model_metadata"]
        self.assertEqual(DEFAULT_MODEL_ID, metadata["model_id"])
        self.assertEqual(DEFAULT_MODEL_LICENSE, metadata["license"])
        self.assertEqual(METADATA_ROLE, metadata["metadata_role"])
        self.assertFalse(metadata["correctness_evidence"])

        revised = capability_probe({"config": {
            "model_revision": "rev-17", "weights_hash": "sha256:abc",
        }})["model_metadata"]
        self.assertEqual("rev-17", revised["model_revision"])
        self.assertEqual("sha256:abc", revised["weights_hash"])

    def test_precomputed_embeddings_rank_deterministically_with_item_id_tie_break(self):
        first = _licensed_item("item-b", embedding=[1.0, 0.0])
        second = _licensed_item("item-a", embedding=[1.0, 0.0])
        result = run_retrieval({
            "mode": "precomputed",
            "query_embedding": [1.0, 0.0],
            "index": {"items": [first, second]},
            "top_k": 2,
        })

        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual(
            ["item-a", "item-b"],
            [row["item_id"] for row in result["matches"]],
        )
        self.assertTrue(all(row["state"] == PROPOSAL_STATE
                            for row in result["matches"]))
        self.assertTrue(all(row["score_is_not_authority"]
                            for row in result["matches"]))

    def test_precomputed_result_retains_asset_license_source_rights_and_provenance(self):
        item = _licensed_item("licensed-1", score=0.88)
        result = run_retrieval({
            "mode": "precomputed",
            "precomputed_result": {"matches": [item]},
        })
        match = result["matches"][0]

        self.assertEqual(item["asset"], match["asset"])
        self.assertEqual(item["license"], match["license"])
        self.assertEqual(item["source"], match["source"])
        self.assertEqual(item["rights_review"], match["rights_review"])
        self.assertEqual(item["provenance"], match["provenance"]["item"])
        self.assertEqual(item["rights_review"], match["provenance"]["rights_review"])

    def test_similarity_axes_stay_separate_and_only_propose_candidate_structure(self):
        item = _licensed_item("axis-aware", score=0.99)
        item.update({
            "target_part": "right-waist overlay",
            "structure_features": {"regime": "WRAPPED", "layer": 2},
            "seam_topology": ["waist anchor", "free hanging edge"],
            "material_features": {"appearance": "sheer"},
            "axis_scores": {
                "part": 0.95, "structure": 0.83,
                "seam": 0.61, "material": 0.72,
            },
        })

        result = run_retrieval({
            "mode": "precomputed",
            "precomputed_result": {"matches": [item]},
        })
        match = result["matches"][0]

        self.assertEqual(item["axis_scores"], match["axis_scores"])
        self.assertEqual({"part", "structure", "seam", "material"},
                         set(match["feature_profile"]))
        self.assertEqual([
            "PROPOSE_REAR_CANDIDATE",
            "PROPOSE_CONSTRUCTION_CANDIDATE",
        ], match["candidate_use_scope"])
        self.assertTrue(match["not_a_sewing_or_manufacturing_fact"])
        self.assertEqual([], match["missing_feature_axes"])

    def test_empty_index_is_typed_unknown_not_fabricated_label(self):
        result = run_retrieval({
            "mode": "precomputed",
            "query_embedding": [1.0, 0.0],
            "index": {"items": []},
        })
        self.assertEqual("UNKNOWN_NO_FASHION_RETRIEVAL_INDEX", result["verdict"])
        self.assertTrue(result["typed_stop"])
        self.assertEqual([], result["matches"])
        self.assertNotIn("label", result)

    def test_local_model_uses_injected_embedder_and_index_without_dependency_import(self):
        embedder = _FakeEmbedder()
        index = _FakeIndex()
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "configured-model"
            model_path.mkdir()
            adapter = MarqoFashionSigLIPAdapter(
                embedder=embedder, index=index,
                dependency_probe=lambda _name: False,
            )
            result = adapter.run({
                "mode": "local_model",
                "model_path": str(model_path),
                "query": {"image_ref": "fixture://front.png"},
                "top_k": 2,
            })

        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual(["local-a", "local-b"],
                         [row["item_id"] for row in result["matches"]])
        self.assertEqual([{"image_ref": "fixture://front.png"}], embedder.calls)
        self.assertEqual([([1.0, 0.0], 2)], index.calls)

    def test_local_model_missing_optional_dependencies_is_typed_capability_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result = MarqoFashionSigLIPAdapter(
                dependency_probe=lambda _name: False,
            ).run({
                "mode": "local_model",
                "model_path": directory,
                "query": {"image_ref": "fixture://front.png"},
                "items": [_licensed_item("one", embedding=[1.0, 0.0])],
            })
        self.assertEqual("UNKNOWN_FASHION_SIGLIP_LOCAL_DEPENDENCY",
                         result["verdict"])

    def test_http_requires_explicit_enable_and_endpoint_failure_is_typed(self):
        disabled = run_retrieval({
            "mode": "local_http",
            "endpoint": "http://127.0.0.1:48123/infer",
        }, transport=lambda *_args, **_kwargs: {})
        self.assertEqual("UNKNOWN_FASHION_RETRIEVAL_HTTP_NOT_ENABLED",
                         disabled["verdict"])

        calls = []

        def failing(endpoint, payload, timeout):
            calls.append((endpoint, payload, timeout))
            raise TimeoutError("bounded fixture timeout")

        failed = run_retrieval({
            "mode": "local_http",
            "endpoint": "http://localhost:48123/infer",
            "allow_http": True,
            "timeout_seconds": 0.25,
            "query": {"image_ref": "fixture://front.png"},
        }, transport=failing)

        self.assertEqual("UNKNOWN_FASHION_RETRIEVAL_ENDPOINT_FAILED",
                         failed["verdict"])
        self.assertEqual(1, len(calls))
        self.assertEqual(0.25, calls[0][2])

        unbounded = run_retrieval({
            "mode": "local_http",
            "endpoint": "http://localhost:48123/infer",
            "allow_http": True,
            "timeout_seconds": 31,
        }, transport=failing)
        self.assertEqual("UNKNOWN_FASHION_RETRIEVAL_TIMEOUT",
                         unbounded["verdict"])
        self.assertEqual(1, len(calls))

    def test_mocked_http_success_remains_proposed_and_preserves_rights(self):
        item = _licensed_item("endpoint-item", score=0.93)

        def transport(_endpoint, payload, timeout):
            self.assertEqual(3, payload["top_k"])
            self.assertLessEqual(timeout, 30.0)
            return {"result": {"matches": [item]}}

        result = run_retrieval({
            "mode": "local_http",
            "endpoint": "http://127.0.0.1:48123/infer",
            "allow_http": True,
            "timeout_seconds": 1.0,
            "top_k": 3,
        }, transport=transport)

        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual(PROPOSAL_STATE, result["matches"][0]["state"])
        self.assertEqual(item["rights_review"],
                         result["matches"][0]["rights_review"])

    def test_result_plugs_directly_into_ensemble_retrieval_result_contract(self):
        retrieval = run_retrieval({
            "mode": "precomputed",
            "precomputed_result": {"matches": [
                _licensed_item("ensemble-item", score=0.9),
            ]},
        })
        ensemble = analyze_garment_image({
            "schema": "garment.image-analysis-ensemble.request.v1",
            "image": {"reference": "fixture://front.png", "front_only": True},
            "vision": {"result": {"garment_instances": [{
                "instance_id": "lower", "garment_name": "wide-leg trousers",
            }]}},
            "retrieval": {"result": retrieval},
        })

        self.assertEqual("ANSWER", ensemble["verdict"])
        retrieval_claims = [row for row in ensemble["claims"]
                            if row["source"] == "MARQO_FASHION_RETRIEVAL"]
        self.assertTrue(retrieval_claims)
        self.assertTrue(all(row["state"] == PROPOSAL_STATE
                            for row in retrieval_claims))
        candidate = ensemble["retrieval_candidates"][0]
        self.assertEqual("REVIEWED",
                         candidate["provenance"]["rights_review"]["state"])


if __name__ == "__main__":
    unittest.main()
