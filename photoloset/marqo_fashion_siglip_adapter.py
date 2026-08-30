# -*- coding: utf-8 -*-
"""Runtime adapter for Marqo FashionSigLIP retrieval proposals.

The adapter has deliberately boring startup behaviour: importing this module,
constructing the adapter, and probing its capabilities do not import a model
runtime, open an endpoint, or download weights.  A caller must select one of
three explicit execution modes:

``precomputed``
    Rank supplied embeddings, or normalize already-computed nearest items.
``local_http``
    Call an explicitly enabled loopback endpoint with a bounded timeout.
``local_model``
    Use an injected embedder/index, or local model files at an existing path.

Retrieval is proposal evidence only.  Model metadata identifies/configures the
runtime; it is never evidence that a match is correct.  Asset rights metadata
is carried through so a later human/rights gate can review it.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse


SCHEMA = "marqo-fashion-siglip.runtime.v1"
RESULT_SCHEMA = "marqo-fashion-siglip.retrieval-result.v1"
PROPOSAL_STATE = "PROPOSED_RETRIEVAL"
FEATURE_AXES = ("part", "structure", "seam", "material")
CANDIDATE_USE_SCOPE = (
    "PROPOSE_REAR_CANDIDATE",
    "PROPOSE_CONSTRUCTION_CANDIDATE",
)
DEFAULT_MODEL_ID = "Marqo/marqo-fashionSigLIP"
DEFAULT_MODEL_LICENSE = "Apache-2.0"
METADATA_ROLE = (
    "IDENTIFICATION_AND_LICENSE_CONFIGURATION_ONLY_NOT_CORRECTNESS_EVIDENCE"
)
MAX_HTTP_TIMEOUT_SECONDS = 30.0
DEFAULT_HTTP_TIMEOUT_SECONDS = 5.0


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _plain(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if _sequence(value):
        return [_plain(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite values are not valid retrieval data")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    return str(value)


def _canonical(value: Any) -> str:
    return json.dumps(
        _plain(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )


def _text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _finite_score(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _typed_stop(verdict: str, why: str, how_to_close: str,
                **extra: Any) -> Dict[str, Any]:
    out = {
        "schema": RESULT_SCHEMA,
        "verdict": verdict,
        "state": "UNKNOWN",
        "typed_stop": True,
        "why": why,
        "how_to_close": how_to_close,
        "matches": [],
    }
    out.update(_plain(extra))
    return out


def _config(request: Mapping[str, Any]) -> Dict[str, Any]:
    configured = request.get("config")
    out = dict(configured) if isinstance(configured, Mapping) else {}
    for key in (
        "mode", "model_id", "model_license", "license", "model_revision",
        "model_hash", "weights_hash", "endpoint", "allow_http",
        "timeout_seconds", "model_path", "index_id", "index_revision",
        "top_k", "local_adapter", "open_clip_model_name",
    ):
        if key in request:
            out[key] = request[key]
    return out


def _model_metadata(config: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "model_id": _text(config.get("model_id")) or DEFAULT_MODEL_ID,
        "license": (
            _text(config.get("model_license"))
            or _text(config.get("license"))
            or DEFAULT_MODEL_LICENSE
        ),
        "metadata_role": METADATA_ROLE,
        "correctness_evidence": False,
    }
    for key in ("model_revision", "model_hash", "weights_hash"):
        value = _text(config.get(key))
        if value:
            out[key] = value
    return out


def _dependency_readiness(
    dependency_probe: Optional[Callable[[str], bool]] = None,
) -> Dict[str, bool]:
    def available(name: str) -> bool:
        if dependency_probe is not None:
            return bool(dependency_probe(name))
        return importlib.util.find_spec(name) is not None

    # ``find_spec`` reads import metadata only.  It does not import either
    # framework and therefore cannot trigger model registration/downloads.
    return {
        "transformers": available("transformers"),
        "open_clip": available("open_clip"),
    }


def _loopback_endpoint(endpoint: Any) -> Tuple[bool, Optional[str]]:
    value = _text(endpoint)
    if not value:
        return False, None
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        port = None
    valid = (
        parsed.scheme in {"http", "https"}
        and host in {"localhost", "127.0.0.1", "::1"}
        and bool(port)
    )
    return valid, value


def _timeout(value: Any) -> Optional[float]:
    if value is None:
        return DEFAULT_HTTP_TIMEOUT_SECONDS
    score = _finite_score(value)
    if score is None or score <= 0 or score > MAX_HTTP_TIMEOUT_SECONDS:
        return None
    return score


def _items_from_request(request: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    index = request.get("index")
    if isinstance(index, Mapping):
        raw = index.get("items", index.get("candidates", []))
        if _sequence(raw):
            return [row for row in raw if isinstance(row, Mapping)]
    for key in ("items", "candidates"):
        raw = request.get(key)
        if _sequence(raw):
            return [row for row in raw if isinstance(row, Mapping)]
    return []


def _direct_result(request: Mapping[str, Any]) -> Any:
    for key in ("precomputed_result", "precomputed_results", "result"):
        if key in request:
            return request[key]
    return None


def _matches_from_result(value: Any) -> List[Mapping[str, Any]]:
    if isinstance(value, Mapping) and isinstance(value.get("result"), Mapping):
        value = value["result"]
    if isinstance(value, Mapping):
        for key in ("matches", "nearest_items", "items"):
            rows = value.get(key)
            if _sequence(rows):
                return [row for row in rows if isinstance(row, Mapping)]
        if any(key in value for key in ("item_id", "id")):
            return [value]
    if _sequence(value):
        return [row for row in value if isinstance(row, Mapping)]
    return []


def _vector(value: Any) -> Optional[List[float]]:
    if not _sequence(value) or not value:
        return None
    out: List[float] = []
    for child in value:
        score = _finite_score(child)
        if score is None:
            return None
        out.append(score)
    return out


def _query_embedding(request: Mapping[str, Any]) -> Optional[List[float]]:
    direct = _vector(request.get("query_embedding"))
    if direct is not None:
        return direct
    query = request.get("query")
    if isinstance(query, Mapping):
        return _vector(query.get("embedding"))
    return None


def _cosine(left: Sequence[float], right: Sequence[float]) -> Optional[float]:
    if len(left) != len(right) or not left:
        return None
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return None
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _item_id(row: Mapping[str, Any]) -> Optional[str]:
    return _text(row.get("item_id")) or _text(row.get("id"))


def _metadata(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return _plain(row[key])
    return {}


def _axis_scores(row: Mapping[str, Any]) -> Dict[str, float]:
    raw = row.get("axis_scores", row.get("similarity_axes", {}))
    raw = raw if isinstance(raw, Mapping) else {}
    out: Dict[str, float] = {}
    for axis in FEATURE_AXES:
        value = _finite_score(raw.get(axis))
        if value is not None:
            out[axis] = value
    return out


def _feature_profile(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep retrieval evidence split by construction-relevant axis."""
    candidates = {
        "part": (
            "part_features", "target_part", "parts", "components"),
        "structure": (
            "structure_features", "construction_features", "structure",
            "construction_regime", "rear_structure"),
        "seam": (
            "seam_features", "seam_topology", "seams", "openings"),
        "material": (
            "material_features", "material", "materials"),
    }
    out: Dict[str, Any] = {}
    for axis in FEATURE_AXES:
        values = {key: _plain(row[key]) for key in candidates[axis]
                  if key in row and row[key] is not None}
        out[axis] = values
    return out


def _normalize_match(row: Mapping[str, Any], score: float) -> Optional[Dict[str, Any]]:
    item_id = _item_id(row)
    if not item_id:
        return None
    asset = _metadata(row, "asset", "asset_metadata")
    license_metadata = _metadata(row, "license", "asset_license", "license_metadata")
    source = _metadata(row, "source", "source_metadata")
    rights_review = _metadata(row, "rights_review", "rights")
    if not rights_review:
        rights_review = {
            "state": "UNKNOWN_RIGHTS_REVIEW_REQUIRED",
            "use_authorized": None,
        }
    item_provenance = _metadata(row, "provenance")
    provenance = {
        "adapter": "marqo-fashion-siglip-runtime",
        "item": item_provenance,
        "asset": asset,
        "license": license_metadata,
        "source": source,
        "rights_review": rights_review,
    }
    axis_scores = _axis_scores(row)
    feature_profile = _feature_profile(row)
    out: Dict[str, Any] = {
        "item_id": item_id,
        "score": score,
        "state": PROPOSAL_STATE,
        "score_is_not_authority": True,
        "human_confirmation_required": True,
        "axis_scores": axis_scores,
        "feature_profile": feature_profile,
        "missing_feature_axes": [
            axis for axis in FEATURE_AXES
            if not feature_profile[axis] and axis not in axis_scores
        ],
        "candidate_use_scope": list(CANDIDATE_USE_SCOPE),
        "not_a_sewing_or_manufacturing_fact": True,
        "provenance": provenance,
        "asset": asset,
        "license": license_metadata,
        "source": source,
        "rights_review": rights_review,
    }
    # Labels and garment structure are copied only when the configured index
    # supplied them.  The adapter never guesses a category from an item ID.
    for key in (
        "label", "name", "garment_name", "instance_id", "garment_id",
        "layer", "parts", "components", "construction_regime", "material",
        "rear_structure", "visible_observations", "target_part",
        "part_features", "structure_features", "construction_features",
        "seam_features", "seam_topology", "seams", "openings",
        "material_features", "rear_candidates", "construction_candidates",
    ):
        if key in row:
            out[key] = _plain(row[key])
    return out


def _rank_matches(rows: Sequence[Mapping[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        score = _finite_score(row.get("score", row.get("similarity")))
        if score is None:
            continue
        match = _normalize_match(row, score)
        if match is not None:
            normalized.append(match)
    def axis_order(row: Mapping[str, Any]) -> Tuple[int, float]:
        scores = row.get("axis_scores", {})
        values = [float(scores[axis]) for axis in FEATURE_AXES
                  if isinstance(scores, Mapping) and axis in scores]
        return len(values), (sum(values) / len(values) if values else 0.0)

    normalized.sort(key=lambda row: (
        -axis_order(row)[0], -axis_order(row)[1], -float(row["score"]),
        str(row["item_id"]),
        str(row.get("label", row.get("name", row.get("garment_name", "")))),
        _canonical(row.get("source", {})),
    ))
    return normalized[:top_k]


def _rank_embeddings(
    query: Sequence[float], rows: Sequence[Mapping[str, Any]], top_k: int,
) -> List[Dict[str, Any]]:
    scored: List[Dict[str, Any]] = []
    for row in rows:
        embedding = _vector(row.get("embedding"))
        if embedding is None:
            continue
        score = _cosine(query, embedding)
        if score is None:
            continue
        with_score = dict(row)
        with_score["score"] = score
        scored.append(with_score)
    return _rank_matches(scored, top_k)


def _top_k(value: Any) -> Optional[int]:
    if value is None:
        return 10
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= 100 else None


def _result(matches: Sequence[Mapping[str, Any]], *, mode: str,
            config: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "verdict": "ANSWER",
        "state": PROPOSAL_STATE,
        "typed_stop": False,
        "mode": mode,
        "matches": [_plain(row) for row in matches],
        "feature_axes": list(FEATURE_AXES),
        "candidate_use_scope": list(CANDIDATE_USE_SCOPE),
        "model_metadata": _model_metadata(config),
        "authority": {
            "retrieval_is_proposal_only": True,
            "scores_are_not_correctness_evidence": True,
            "axis_scores_remain_separate": True,
            "single_embedding_winner_is_not_construction_authority": True,
            "retrieval_may_only_propose_rear_or_construction_candidates": True,
            "automatic_observed_promotion": False,
            "rights_review_required_before_asset_use": True,
        },
    }


def _invoke_transport(transport: Any, endpoint: str,
                      payload: Mapping[str, Any], timeout: float) -> Any:
    caller = getattr(transport, "post_json", transport)
    if not callable(caller):
        raise TypeError("transport must be callable or expose post_json")
    try:
        return caller(endpoint, _plain(payload), timeout=timeout)
    except TypeError as first:
        try:
            return caller(endpoint, _plain(payload), timeout)
        except TypeError:
            raise first


def _stdlib_http_transport(endpoint: str, payload: Mapping[str, Any],
                           timeout: float) -> Any:
    # Imported only after an explicitly enabled inference call reaches here.
    # Merely importing/probing this adapter therefore has no network surface.
    from urllib.request import Request, urlopen

    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    request = Request(
        endpoint, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - loopback only
        return json.loads(response.read().decode("utf-8"))


def _invoke_embedder(embedder: Any, request: Mapping[str, Any]) -> List[float]:
    if hasattr(embedder, "embed") and callable(embedder.embed):
        value = embedder.embed(_plain(request.get("query", request)))
    elif hasattr(embedder, "embed_image") and callable(embedder.embed_image):
        image_ref = request.get("image_ref")
        if image_ref is None and isinstance(request.get("query"), Mapping):
            image_ref = request["query"].get("image_ref")
        value = embedder.embed_image(image_ref)
    elif callable(embedder):
        value = embedder(_plain(request.get("query", request)))
    else:
        raise TypeError("embedder must be callable or expose embed/embed_image")
    vector = _vector(value)
    if vector is None:
        raise ValueError("embedder returned no finite vector")
    return vector


def _invoke_index(index: Any, embedding: Sequence[float], top_k: int) -> Any:
    caller = getattr(index, "search", index)
    if not callable(caller):
        raise TypeError("index must be callable or expose search")
    try:
        return caller(list(embedding), top_k=top_k)
    except TypeError as first:
        try:
            return caller(list(embedding), top_k)
        except TypeError:
            raise first


class _TransformersLocalEmbedder:
    """Lazy local-only Transformers bridge.

    This is intentionally instantiated only during an explicit local-model
    run.  ``local_files_only=True`` is load-bearing: even a valid Hugging Face
    model ID cannot cause a network fetch through this path.
    """

    def __init__(self, model_path: str):
        from transformers import AutoModel, AutoProcessor

        self._processor = AutoProcessor.from_pretrained(
            model_path, local_files_only=True, trust_remote_code=False)
        self._model = AutoModel.from_pretrained(
            model_path, local_files_only=True, trust_remote_code=False)

    def embed(self, query: Mapping[str, Any]) -> List[float]:
        image_ref = _text(query.get("image_ref"))
        if not image_ref or not Path(image_ref).is_file():
            raise ValueError("local image_ref is required for local model inference")
        from PIL import Image
        import torch

        with Image.open(image_ref) as image:
            inputs = self._processor(images=image.convert("RGB"), return_tensors="pt")
        with torch.no_grad():
            if hasattr(self._model, "get_image_features"):
                features = self._model.get_image_features(**inputs)
            else:
                output = self._model(**inputs)
                features = getattr(output, "image_embeds", None)
                if features is None:
                    raise ValueError("local model exposes no image embedding output")
        value = features[0].detach().cpu().tolist()
        vector = _vector(value)
        if vector is None:
            raise ValueError("local model returned no finite vector")
        return vector


class MarqoFashionSigLIPAdapter:
    """Provider-neutral bounded runtime adapter.

    ``transport``, ``embedder`` and ``index`` are dependency-injection points.
    They are especially useful for an application-owned runtime and tests; no
    global provider is installed at import time.
    """

    def __init__(
        self, *, transport: Any = None, embedder: Any = None, index: Any = None,
        dependency_probe: Optional[Callable[[str], bool]] = None,
    ):
        self.transport = transport
        self.embedder = embedder
        self.index = index
        self.dependency_probe = dependency_probe

    def capabilities(self, request: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        request = request if isinstance(request, Mapping) else {}
        config = _config(request)
        dependencies = _dependency_readiness(self.dependency_probe)
        endpoint_valid, endpoint = _loopback_endpoint(config.get("endpoint"))
        model_path = _text(config.get("model_path"))
        path_exists = bool(model_path and Path(model_path).exists())
        has_items = bool(_items_from_request(request))
        has_results = bool(_matches_from_result(_direct_result(request)))
        has_index = self.index is not None or has_items
        return {
            "schema": SCHEMA,
            "verdict": "ANSWER",
            "state": "CAPABILITY_REPORT_NOT_INFERENCE",
            "network_probe_performed": False,
            "model_loaded": False,
            "downloads_attempted": False,
            "model_metadata": _model_metadata(config),
            "analysis_contract": {
                "feature_axes": list(FEATURE_AXES),
                "candidate_use_scope": list(CANDIDATE_USE_SCOPE),
                "single_class_label_output": False,
                "manufacturing_authority": False,
            },
            "modes": {
                "precomputed": {
                    "supported": True,
                    "ready": has_results or (
                        _query_embedding(request) is not None and has_items
                    ),
                    "has_results": has_results,
                    "has_index": has_items,
                },
                "local_http": {
                    "supported": True,
                    "ready": bool(config.get("allow_http") is True and endpoint_valid),
                    "explicitly_enabled": config.get("allow_http") is True,
                    "endpoint_configured": endpoint is not None,
                    "endpoint_is_loopback": endpoint_valid,
                    "endpoint_reachable": "NOT_PROBED",
                    "bounded_timeout_seconds": _timeout(config.get("timeout_seconds")),
                },
                "local_model": {
                    "supported": True,
                    "ready": bool(
                        model_path and path_exists and has_index and (
                            self.embedder is not None or any(dependencies.values())
                        )
                    ),
                    "model_path_configured": model_path is not None,
                    "model_path_exists": path_exists,
                    "embedder_injected": self.embedder is not None,
                    "index_injected_or_precomputed": has_index,
                    "dependencies": dependencies,
                    "dependencies_imported": False,
                },
            },
        }

    def run(self, request: Mapping[str, Any]) -> Dict[str, Any]:
        if not isinstance(request, Mapping):
            return _typed_stop(
                "UNKNOWN_FASHION_RETRIEVAL_INPUT",
                "request must be an object",
                "supply a typed adapter request",
            )
        config = _config(request)
        mode = _text(config.get("mode")) or "precomputed"
        top_k = _top_k(config.get("top_k"))
        if top_k is None:
            return _typed_stop(
                "UNKNOWN_FASHION_RETRIEVAL_TOP_K",
                "top_k must be an integer from 1 through 100",
                "supply a bounded top_k",
            )
        if mode == "precomputed":
            return self._run_precomputed(request, config, top_k)
        if mode == "local_http":
            return self._run_http(request, config, top_k)
        if mode == "local_model":
            return self._run_local_model(request, config, top_k)
        return _typed_stop(
            "UNKNOWN_FASHION_RETRIEVAL_MODE",
            f"unsupported adapter mode: {mode}",
            "choose precomputed, local_http, or local_model",
        )

    def _run_precomputed(
        self, request: Mapping[str, Any], config: Mapping[str, Any], top_k: int,
    ) -> Dict[str, Any]:
        direct = _direct_result(request)
        if direct is not None:
            rows = _matches_from_result(direct)
            if not rows:
                return _typed_stop(
                    "UNKNOWN_NO_FASHION_RETRIEVAL_INDEX",
                    "the supplied precomputed retrieval result contains no candidate corpus",
                    "supply licensed nearest-item results or an embedding index",
                    model_metadata=_model_metadata(config),
                )
            matches = _rank_matches(rows, top_k)
        else:
            rows = _items_from_request(request)
            query = _query_embedding(request)
            if not rows:
                return _typed_stop(
                    "UNKNOWN_NO_FASHION_RETRIEVAL_INDEX",
                    "no fashion retrieval corpus/index was supplied",
                    "configure a rights-reviewed index or precomputed nearest items",
                    model_metadata=_model_metadata(config),
                )
            if query is None:
                return _typed_stop(
                    "UNKNOWN_FASHION_RETRIEVAL_QUERY_EMBEDDING",
                    "precomputed mode needs a finite query embedding",
                    "supply query_embedding or precomputed nearest-item results",
                    model_metadata=_model_metadata(config),
                )
            matches = _rank_embeddings(query, rows, top_k)
        if not matches:
            return _typed_stop(
                "UNKNOWN_FASHION_RETRIEVAL_NO_RESULTS",
                "the configured retrieval source produced no scored identifiable candidates",
                "verify item IDs, finite scores/embeddings, and index dimensions",
                model_metadata=_model_metadata(config),
            )
        return _result(matches, mode="precomputed", config=config)

    def _run_http(
        self, request: Mapping[str, Any], config: Mapping[str, Any], top_k: int,
    ) -> Dict[str, Any]:
        valid, endpoint = _loopback_endpoint(config.get("endpoint"))
        if config.get("allow_http") is not True:
            return _typed_stop(
                "UNKNOWN_FASHION_RETRIEVAL_HTTP_NOT_ENABLED",
                "local HTTP inference was not explicitly enabled",
                "set allow_http=true for a configured loopback endpoint",
                model_metadata=_model_metadata(config),
            )
        if not valid or endpoint is None:
            return _typed_stop(
                "UNKNOWN_FASHION_RETRIEVAL_ENDPOINT",
                "endpoint must be an explicit loopback HTTP(S) URL with a port",
                "configure localhost, 127.0.0.1, or ::1",
                model_metadata=_model_metadata(config),
            )
        timeout = _timeout(config.get("timeout_seconds"))
        if timeout is None:
            return _typed_stop(
                "UNKNOWN_FASHION_RETRIEVAL_TIMEOUT",
                f"timeout must be greater than 0 and at most {MAX_HTTP_TIMEOUT_SECONDS:g} seconds",
                "supply a bounded timeout_seconds",
                model_metadata=_model_metadata(config),
            )
        payload = {
            "query": _plain(request.get("query", {})),
            "query_features": _plain(request.get("query_features", {})),
            "feature_axes": list(FEATURE_AXES),
            "candidate_use_scope": list(CANDIDATE_USE_SCOPE),
            "image_ref": _plain(request.get("image_ref")),
            "top_k": top_k,
            "model": _model_metadata(config),
            "index_id": _plain(config.get("index_id")),
            "index_revision": _plain(config.get("index_revision")),
        }
        transport = self.transport or _stdlib_http_transport
        try:
            response = _invoke_transport(transport, endpoint, payload, timeout)
        except Exception as exc:  # endpoint failure is a typed capability value
            return _typed_stop(
                "UNKNOWN_FASHION_RETRIEVAL_ENDPOINT_FAILED",
                f"{type(exc).__name__}: {exc}",
                "start/repair the configured local endpoint or use a precomputed result",
                model_metadata=_model_metadata(config),
                timeout_seconds=timeout,
            )
        rows = _matches_from_result(response)
        if not rows:
            return _typed_stop(
                "UNKNOWN_NO_FASHION_RETRIEVAL_INDEX",
                "the endpoint returned no candidate corpus/results",
                "configure a rights-reviewed endpoint index",
                model_metadata=_model_metadata(config),
            )
        matches = _rank_matches(rows, top_k)
        if not matches:
            return _typed_stop(
                "UNKNOWN_FASHION_RETRIEVAL_NO_RESULTS",
                "the endpoint returned no scored identifiable candidates",
                "return item_id plus a finite score for each candidate",
                model_metadata=_model_metadata(config),
            )
        return _result(matches, mode="local_http", config=config)

    def _run_local_model(
        self, request: Mapping[str, Any], config: Mapping[str, Any], top_k: int,
    ) -> Dict[str, Any]:
        model_path = _text(config.get("model_path"))
        if not model_path:
            return _typed_stop(
                "UNKNOWN_FASHION_SIGLIP_MODEL_PATH_REQUIRED",
                "local model mode requires an explicitly configured model_path",
                "configure an existing local model directory/file",
                model_metadata=_model_metadata(config),
            )
        if not Path(model_path).exists():
            return _typed_stop(
                "UNKNOWN_FASHION_SIGLIP_MODEL_PATH_NOT_FOUND",
                "the explicitly configured local model path does not exist",
                "install weights out of band and point model_path to them",
                model_metadata=_model_metadata(config),
            )
        request_items = _items_from_request(request)
        index = self.index
        if index is None and not request_items:
            return _typed_stop(
                "UNKNOWN_NO_FASHION_RETRIEVAL_INDEX",
                "local model files are present but no search corpus/index was supplied",
                "inject an index or supply rights-reviewed embedded items",
                model_metadata=_model_metadata(config),
            )
        embedder = self.embedder
        if embedder is None:
            dependencies = _dependency_readiness(self.dependency_probe)
            if not any(dependencies.values()):
                return _typed_stop(
                    "UNKNOWN_FASHION_SIGLIP_LOCAL_DEPENDENCY",
                    "neither transformers nor open_clip is installed",
                    "install a compatible local runtime or inject an embedder",
                    model_metadata=_model_metadata(config),
                    dependencies=dependencies,
                )
            # A local-only Transformers bridge is the built-in production
            # implementation.  An open_clip-specific setup remains injectable
            # because checkpoint/model-name pairings are application-specific.
            if not dependencies.get("transformers"):
                return _typed_stop(
                    "UNKNOWN_FASHION_SIGLIP_LOCAL_ADAPTER_REQUIRED",
                    "open_clip is present but no compatible local embedder was injected",
                    "inject the configured open_clip embedder/index pair",
                    model_metadata=_model_metadata(config),
                    dependencies=dependencies,
                )
            try:
                embedder = _TransformersLocalEmbedder(model_path)
            except Exception as exc:
                return _typed_stop(
                    "UNKNOWN_FASHION_SIGLIP_LOCAL_LOAD_FAILED",
                    f"{type(exc).__name__}: {exc}",
                    "verify the local-only model files and dependency versions",
                    model_metadata=_model_metadata(config),
                )
        try:
            embedding = _invoke_embedder(embedder, request)
            if index is not None:
                rows = _matches_from_result(_invoke_index(index, embedding, top_k))
                matches = _rank_matches(rows, top_k)
            else:
                matches = _rank_embeddings(embedding, request_items, top_k)
        except Exception as exc:
            return _typed_stop(
                "UNKNOWN_FASHION_SIGLIP_LOCAL_INFERENCE_FAILED",
                f"{type(exc).__name__}: {exc}",
                "repair the injected local embedder/index contract",
                model_metadata=_model_metadata(config),
            )
        if not matches:
            return _typed_stop(
                "UNKNOWN_FASHION_RETRIEVAL_NO_RESULTS",
                "the local index produced no scored identifiable candidates",
                "verify index embeddings, dimensions, item IDs, and scores",
                model_metadata=_model_metadata(config),
            )
        return _result(matches, mode="local_model", config=config)


def capability_probe(
    request: Optional[Mapping[str, Any]] = None, *, embedder: Any = None,
    index: Any = None, dependency_probe: Optional[Callable[[str], bool]] = None,
) -> Dict[str, Any]:
    return MarqoFashionSigLIPAdapter(
        embedder=embedder, index=index, dependency_probe=dependency_probe,
    ).capabilities(request)


def run_retrieval(
    request: Mapping[str, Any], *, transport: Any = None, embedder: Any = None,
    index: Any = None, dependency_probe: Optional[Callable[[str], bool]] = None,
) -> Dict[str, Any]:
    return MarqoFashionSigLIPAdapter(
        transport=transport, embedder=embedder, index=index,
        dependency_probe=dependency_probe,
    ).run(request)
