# -*- coding: utf-8 -*-
"""Bounded, model-agnostic garment image proposal ensemble.

This module deliberately merges *proposals*, not facts.  A vision-language
model and a fashion retrieval model are independent proposal sources.  Their
agreement is useful review information, but neither a high similarity score
nor agreement promotes a claim to ``OBSERVED``.

Provider adapters are optional and injectable.  Production code can pass an
async callable (or an object with ``analyze``); tests and MCP clients can pass
already-computed results without downloading model weights.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Callable, Dict, List, Optional, Tuple


REQUEST_SCHEMA = "garment.image-analysis-ensemble.request.v1"
SCHEMA = "garment.image-analysis-ensemble.v1"

VISION_SOURCE = "VISION_LANGUAGE_MODEL"
RETRIEVAL_SOURCE = "MARQO_FASHION_RETRIEVAL"
VISION_STATE = "PROPOSED_VISION_UNCONFIRMED"
RETRIEVAL_STATE = "PROPOSED_RETRIEVAL"
HUMAN_AUDIT = "HUMAN_AUDIT"
AUTO_PROPOSED = "AUTO_PROPOSED"
AUTO_ACCEPTED_FOR_PREVIEW = "AUTO_ACCEPTED_FOR_PREVIEW"
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 5.0

_MISSING = object()
_CATEGORY_ORDER = {
    "GARMENT_INSTANCE": 0,
    "LAYER": 1,
    "GARMENT_NAME": 2,
    "VISIBLE_COMPONENT": 3,
    "LATERALITY": 4,
    "COLOR": 5,
    "VISIBLE_OBSERVATION": 6,
    "CONSTRUCTION_REGIME": 7,
    "MATERIAL": 8,
    "REAR_HIDDEN_STRUCTURE": 9,
}

_AUDIT_MODES = {HUMAN_AUDIT, AUTO_PROPOSED}
_MODEL_PROSE_KEYS = {
    "analysis", "answer", "content", "message", "narrative", "reasoning",
    "response", "text", "thinking",
}
_PROVIDER_AUTHORITY_KEYS = {
    "approval", "approved", "authority", "fact", "manufacturing_certified",
    "manufacturing_ready", "observed", "state", "strength_guarantee",
    "verdict",
}
_PART_VALUE_KEYS = {
    "asymmetry", "count", "geometry_role", "kind", "layer", "name",
    "part_id", "semantic_role", "visibility",
}


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _plain(value: Any) -> Any:
    """Return a deterministic JSON value, rejecting non-finite numbers."""
    if isinstance(value, Mapping):
        return {
            str(key): _plain(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if _sequence(value):
        return [_plain(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not valid provider output")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    return str(value)


def _proposal_value(value: Any) -> Any:
    """Strip provider authority vocabulary from semantic proposal values."""
    if isinstance(value, Mapping):
        return {
            str(key): _proposal_value(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key).lower() not in _PROVIDER_AUTHORITY_KEYS
            and str(key).lower() not in _MODEL_PROSE_KEYS
        }
    if _sequence(value):
        children = [_proposal_value(child) for child in value]
        return sorted(children, key=_canonical)
    return _plain(value)


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


def _token(value: Any) -> str:
    text = _text(value) or "unspecified"
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower()
    return text or "unspecified"


def _score(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _audit_mode(request: Mapping[str, Any]) -> str:
    mode = str(request.get("audit_mode", HUMAN_AUDIT)).strip().upper()
    if mode not in _AUDIT_MODES:
        raise ValueError(
            f"audit_mode must be {HUMAN_AUDIT!r} or {AUTO_PROPOSED!r}")
    return mode


def _image_view(request: Mapping[str, Any]) -> Dict[str, Any]:
    image = request.get("image")
    image = image if isinstance(image, Mapping) else {}
    declared = str(image.get(
        "source_view", image.get("view", request.get("source_view", "FRONT")))
    ).strip().upper().replace("-", "_").replace(" ", "_")
    view = ("OBLIQUE" if any(token in declared for token in (
        "OBLIQUE", "THREE_QUARTER", "3/4", "DIAGONAL",
    )) else "FRONT")
    return {
        "view": view,
        "declared_view": declared or "FRONT",
        "state": "PROPOSED",
        "front_visible": True,
        "oblique_visible": view == "OBLIQUE",
        "rear_visible": False,
        "rear_inference_required": True,
    }


def _timeout_seconds(request: Mapping[str, Any], key: str,
                     override: Optional[float]) -> float:
    value: Any = override
    if value is None:
        value = request.get(f"{key}_timeout_seconds")
    if value is None:
        timeouts = request.get("provider_timeouts")
        if isinstance(timeouts, Mapping):
            value = timeouts.get(key)
    if value is None:
        value = request.get("provider_timeout_seconds",
                            DEFAULT_PROVIDER_TIMEOUT_SECONDS)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} provider timeout must be a finite positive number")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{key} provider timeout must be a finite positive number")
    return value


def _ordered(value: Any) -> List[Any]:
    if not _sequence(value):
        return []
    return sorted((_plain(item) for item in value), key=_canonical)


def _side(value: Any) -> Optional[str]:
    text = (_text(value) or "").upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "L": "LEFT", "LEFT_SIDE": "LEFT", "R": "RIGHT",
        "RIGHT_SIDE": "RIGHT", "CENTRE": "CENTER", "MIDDLE": "CENTER",
        "BOTH": "BILATERAL", "PAIR": "BILATERAL",
    }
    text = aliases.get(text, text)
    return text if text in {
        "LEFT", "RIGHT", "CENTER", "BILATERAL", "ASYMMETRIC",
    } else None


def _colors(raw: Mapping[str, Any]) -> List[Any]:
    value = raw.get("colors", raw.get(
        "colours", raw.get("color", raw.get("colour", raw.get("palette")))))
    if value is None:
        return []
    values = list(value) if _sequence(value) else [value]
    return sorted((_plain(item) for item in values), key=_canonical)


def _construction_regime(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("code", value.get(
            "regime", value.get("kind", value.get("type"))))
    text = (_text(value) or "UNKNOWN_CONSTRUCTION").upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    aliases = {
        "SEWN": "SEWN_FITTED", "FITTED": "SEWN_FITTED",
        "RECTILINEAR": "SEWN_RECTILINEAR", "DRAPED": "DRAPED_UNSTITCHED",
        "DRAPE": "DRAPED_UNSTITCHED", "WRAP": "WRAPPED",
        "KNIT": "KNITTED", "LAYERED": "MODULAR_LAYERED",
    }
    text = aliases.get(text, text)
    allowed = {
        "SEWN_FITTED", "SEWN_RECTILINEAR", "DRAPED_UNSTITCHED",
        "WRAPPED", "KNITTED", "MODULAR_LAYERED", "HYBRID",
        "UNKNOWN_CONSTRUCTION",
    }
    return text if text in allowed else "UNKNOWN_CONSTRUCTION"


def _provider_config(request: Mapping[str, Any], key: str,
                     wrapper: Any) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    configured = request.get("provider_config")
    if isinstance(configured, Mapping) and isinstance(configured.get(key), Mapping):
        config.update(_plain(configured[key]))
    explicit = request.get(f"{key}_config")
    if isinstance(explicit, Mapping):
        config.update(_plain(explicit))
    if isinstance(wrapper, Mapping) and isinstance(wrapper.get("config"), Mapping):
        config.update(_plain(wrapper["config"]))
    # These fields are configuration/provenance only.  They never participate
    # in reconciliation and never add authority to a claim.
    allowed = {
        "provider_id", "model_id", "model_revision", "license",
        "license_id", "endpoint", "index_id", "index_revision",
    }
    if isinstance(wrapper, Mapping):
        for field in allowed:
            if field in wrapper:
                config[field] = _plain(wrapper[field])
    return {key: config[key] for key in sorted(config) if key in allowed}


def _embedded(request: Mapping[str, Any], key: str) -> Tuple[Any, Dict[str, Any]]:
    wrapper = request.get(key, _MISSING)
    config = _provider_config(request, key, wrapper)
    if isinstance(wrapper, Mapping) and "result" in wrapper:
        return wrapper.get("result"), config
    explicit = request.get(f"{key}_result", _MISSING)
    if explicit is not _MISSING:
        return explicit, config
    # A bare ``vision``/``retrieval`` object is also accepted as a precomputed
    # result, unless it contains configuration only.
    if wrapper is not _MISSING:
        if isinstance(wrapper, Mapping) and set(wrapper).issubset({"config"}):
            return _MISSING, config
        return wrapper, config
    return _MISSING, config


async def _invoke_provider(provider: Any, request: Mapping[str, Any]) -> Any:
    callable_provider = getattr(provider, "analyze", provider)
    if not callable(callable_provider):
        raise TypeError("provider must be callable or expose analyze(request)")
    payload = copy.deepcopy(dict(request))
    if inspect.iscoroutinefunction(callable_provider):
        return await callable_provider(payload)
    # A local/API adapter may expose a synchronous callable.  Running it in a
    # worker keeps the other provider and its timeout independent.
    result = await asyncio.to_thread(callable_provider, payload)
    if inspect.isawaitable(result):
        result = await result
    return result


async def _resolve_provider(
    *, key: str, provider: Any, embedded: Any, request: Mapping[str, Any],
    timeout_seconds: float,
) -> Dict[str, Any]:
    label = "vision-language" if key == "vision" else "fashion retrieval"
    unavailable_code = (
        "UNKNOWN_VISION_PROVIDER_UNAVAILABLE" if key == "vision"
        else "UNKNOWN_RETRIEVAL_PROVIDER_UNAVAILABLE"
    )
    failed_code = (
        "UNKNOWN_VISION_PROVIDER_FAILED" if key == "vision"
        else "UNKNOWN_RETRIEVAL_PROVIDER_FAILED"
    )
    timeout_code = (
        "UNKNOWN_VISION_PROVIDER_TIMEOUT" if key == "vision"
        else "UNKNOWN_RETRIEVAL_PROVIDER_TIMEOUT"
    )
    if provider is None and embedded is _MISSING:
        return {
            "available": False,
            "failure": {
                "verdict": unavailable_code,
                "why": f"no {label} provider or precomputed result was supplied",
                "how_to_close": f"supply an injectable {key} provider or {key}.result",
            },
        }
    try:
        result = (await asyncio.wait_for(
            _invoke_provider(provider, request), timeout=timeout_seconds)
                  if provider is not None else embedded)
    except asyncio.TimeoutError:
        return {
            "available": False,
            "failure": {
                "verdict": timeout_code,
                "why": f"{label} provider exceeded {timeout_seconds:g} seconds",
                "how_to_close": f"repair, replace, or raise the bounded {key} timeout",
            },
        }
    except Exception as exc:  # provider failure is data, not an ensemble crash
        return {
            "available": False,
            "failure": {
                "verdict": failed_code,
                "why": f"{type(exc).__name__}: {exc}",
                "how_to_close": f"repair or replace the {label} provider",
            },
        }
    if result is None or (
        isinstance(result, Mapping) and result.get("available") is False
    ):
        why = (result.get("why") if isinstance(result, Mapping) else None)
        return {
            "available": False,
            "failure": {
                "verdict": unavailable_code,
                "why": _text(why) or f"the {label} provider reported unavailable",
                "how_to_close": f"supply a usable {label} result",
            },
        }
    if not isinstance(result, Mapping):
        return {
            "available": False,
            "failure": {
                "verdict": failed_code,
                "why": f"{label} result must be an object",
                "how_to_close": "return a mapping that follows the proposal contract",
            },
        }
    try:
        normalised = _plain(result)
    except (TypeError, ValueError) as exc:
        return {
            "available": False,
            "failure": {
                "verdict": failed_code,
                "why": f"provider result normalization failed: {exc}",
                "how_to_close": "return finite JSON-compatible typed proposals",
            },
        }
    return {"available": True, "result": normalised}


def _claim(
    *, category: str, subject: str, value: Any, state: str, source: str,
    source_id: str, visibility: str, uncertainty: Any = None,
    provenance: Any = None, retrieval_score: Optional[float] = None,
    candidate_rank: Optional[int] = None,
) -> Dict[str, Any]:
    stable_value = _proposal_value(value)
    identity = {
        "category": category, "subject": subject, "value": stable_value,
        "source": source, "source_id": source_id,
        "candidate_rank": candidate_rank,
    }
    out: Dict[str, Any] = {
        "claim_id": "claim-" + hashlib.sha256(
            _canonical(identity).encode("utf-8")).hexdigest()[:16],
        "category": category,
        "subject": subject,
        "value": stable_value,
        "state": state,
        "source": source,
        "source_id": source_id,
        "visibility": visibility,
        "human_confirmation_required": True,
    }
    if uncertainty is not None:
        out["uncertainty"] = _plain(uncertainty)
    if provenance is not None:
        out["provenance"] = _plain(provenance)
    if retrieval_score is not None:
        out["retrieval_score"] = retrieval_score
        out["score_is_not_authority"] = True
    if candidate_rank is not None:
        out["candidate_rank"] = candidate_rank
    return out


def _instance_id(raw: Mapping[str, Any], index: int, prefix: str) -> str:
    given = (_text(raw.get("instance_id")) or _text(raw.get("garment_id"))
             or _text(raw.get("id")))
    if given:
        return _token(given)
    layer = raw.get("layer")
    name = (_text(raw.get("garment_name")) or _text(raw.get("name"))
            or _text(raw.get("label")))
    return f"{prefix}-{layer if isinstance(layer, int) else index}-{_token(name)}"


def _part_claims(
    parts: Any, *, instance: str, state: str, source: str, source_id: str,
    uncertainty: Any, provenance: Any, parent: Optional[str] = None,
    retrieval_score: Optional[float] = None,
    candidate_rank: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not _sequence(parts):
        return []
    out: List[Dict[str, Any]] = []
    for index, raw in enumerate(_ordered(parts)):
        laterality: Optional[str] = None
        color_values: List[Any] = []
        if isinstance(raw, str):
            value: Any = {"name": raw, "parent_part_id": parent}
            children: Any = []
            part_id = f"part-{index}-{_token(raw)}"
        elif isinstance(raw, Mapping):
            name = (_text(raw.get("name")) or _text(raw.get("label"))
                    or _text(raw.get("kind")) or f"part-{index}")
            part_id = _text(raw.get("part_id")) or _text(raw.get("id"))
            part_id = _token(part_id or f"part-{index}-{name}")
            value = {
                key: _plain(val) for key, val in raw.items()
                if key in _PART_VALUE_KEYS
                and key not in _MODEL_PROSE_KEYS
            }
            value.setdefault("name", name)
            value["part_id"] = part_id
            value["parent_part_id"] = parent
            children = raw.get("children", raw.get("parts", []))
            laterality = _side(raw.get(
                "laterality", raw.get("side", raw.get("left_right"))))
            color_values = _colors(raw)
        else:
            continue
        component = _claim(
            category="VISIBLE_COMPONENT", subject=f"instance:{instance}",
            value=value, state=state, source=source, source_id=source_id,
            visibility="VISIBLE_PROPOSED", uncertainty=uncertainty,
            provenance=provenance, retrieval_score=retrieval_score,
            candidate_rank=candidate_rank,
        )
        out.append(component)
        part_subject = f"part:{instance}:{part_id}"
        if laterality is not None:
            out.append(_claim(
                category="LATERALITY", subject=part_subject,
                value=laterality, state=state, source=source,
                source_id=source_id, visibility="VISIBLE_PROPOSED",
                uncertainty=uncertainty, provenance=provenance,
                retrieval_score=retrieval_score,
                candidate_rank=candidate_rank,
            ))
        for color in color_values:
            out.append(_claim(
                category="COLOR", subject=part_subject, value=color,
                state=state, source=source, source_id=source_id,
                visibility="VISIBLE_APPEARANCE_ONLY",
                uncertainty=uncertainty, provenance=provenance,
                retrieval_score=retrieval_score,
                candidate_rank=candidate_rank,
            ))
        out.extend(_part_claims(
            children, instance=instance, state=state, source=source,
            source_id=source_id, uncertainty=uncertainty,
            provenance=provenance, parent=part_id,
            retrieval_score=retrieval_score, candidate_rank=candidate_rank,
        ))
    return out


def _claims_from_instance(
    raw: Mapping[str, Any], *, index: int, state: str, source: str,
    source_id: str, prefix: str, candidate_rank: Optional[int] = None,
    retrieval_score: Optional[float] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    instance = _instance_id(raw, index, prefix)
    subject = f"instance:{instance}"
    uncertainty = raw.get("uncertainty")
    provenance = raw.get("provenance") or raw.get("source")
    common = {
        "state": state, "source": source, "source_id": source_id,
        "uncertainty": uncertainty, "provenance": provenance,
        "retrieval_score": retrieval_score, "candidate_rank": candidate_rank,
    }
    claims: List[Dict[str, Any]] = [_claim(
        category="GARMENT_INSTANCE", subject=subject,
        value={"instance_id": instance}, visibility="VISIBLE_PROPOSED", **common,
    )]
    if isinstance(raw.get("layer"), int) and not isinstance(raw.get("layer"), bool):
        claims.append(_claim(
            category="LAYER", subject=subject, value=raw["layer"],
            visibility="VISIBLE_PROPOSED", **common,
        ))
    laterality = _side(raw.get(
        "laterality", raw.get("side", raw.get("left_right"))))
    if laterality is not None:
        claims.append(_claim(
            category="LATERALITY", subject=subject, value=laterality,
            visibility="VISIBLE_PROPOSED", **common,
        ))
    for color in _colors(raw):
        claims.append(_claim(
            category="COLOR", subject=subject, value=color,
            visibility="VISIBLE_APPEARANCE_ONLY", **common,
        ))
    name = (_text(raw.get("garment_name")) or _text(raw.get("name"))
            or _text(raw.get("label")) or _text(raw.get("class_name")))
    if name:
        claims.append(_claim(
            category="GARMENT_NAME", subject=subject, value=name,
            visibility="VISIBLE_PROPOSED", **common,
        ))
    parts = raw.get("components", raw.get("parts", raw.get("part_hierarchy", [])))
    claims.extend(_part_claims(
        parts, instance=instance, state=state, source=source,
        source_id=source_id, uncertainty=uncertainty, provenance=provenance,
        retrieval_score=retrieval_score, candidate_rank=candidate_rank,
    ))
    observations = raw.get("visible_observations", raw.get("observations", []))
    if _sequence(observations):
        for observation in _ordered(observations):
            claims.append(_claim(
                category="VISIBLE_OBSERVATION", subject=subject,
                value=observation, visibility="VISIBLE_PROPOSED", **common,
            ))
    regime = raw.get("construction_regime", raw.get("construction"))
    if regime is not None:
        claims.append(_claim(
            category="CONSTRUCTION_REGIME", subject=subject,
            value=_construction_regime(regime),
            visibility="VISIBLE_AND_INFERRED_PROPOSED", **common,
        ))
    material = raw.get("material", raw.get("materials"))
    if material is not None:
        claims.append(_claim(
            category="MATERIAL", subject=subject, value=material,
            visibility="VISIBLE_APPEARANCE_ONLY", **common,
        ))
    hidden = raw.get("rear_structure", raw.get(
        "hidden_structure", raw.get("rear", raw.get("back"))))
    if hidden is not None:
        claims.append(_claim(
            category="REAR_HIDDEN_STRUCTURE", subject=subject, value=hidden,
            visibility="UNOBSERVED_HIDDEN", **common,
        ))
    return instance, claims


def _vision_claims(result: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    raw_instances = result.get("garment_instances", result.get("instances", []))
    if not _sequence(raw_instances):
        raw_instances = []
    if not raw_instances:
        # A single-instance model response may place fields at the root.
        garment_keys = {
            "garment_name", "name", "components", "parts", "layer",
            "construction_regime", "material", "rear_structure",
        }
        if garment_keys.intersection(result):
            raw_instances = [result]
    claims: List[Dict[str, Any]] = []
    instances: List[str] = []
    for index, raw in enumerate(_ordered(raw_instances)):
        if not isinstance(raw, Mapping):
            continue
        raw = dict(raw)
        raw.setdefault("provenance", result.get("provenance"))
        instance, rows = _claims_from_instance(
            raw, index=index, state=VISION_STATE, source=VISION_SOURCE,
            source_id="vision", prefix="vision",
        )
        instances.append(instance)
        claims.extend(rows)
    return claims, instances


def _retrieval_matches(result: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    for key in ("matches", "nearest_items", "items", "classifications", "labels"):
        value = result.get(key)
        if _sequence(value):
            rows: List[Mapping[str, Any]] = []
            for item in value:
                if isinstance(item, Mapping):
                    rows.append(item)
                elif isinstance(item, str):
                    rows.append({"label": item})
            return rows
    value = result.get("garment_instances", result.get("instances"))
    if _sequence(value):
        return [item for item in value if isinstance(item, Mapping)]
    if any(key in result for key in ("label", "name", "garment_name")):
        return [result]
    return []


def _retrieval_claims(
    result: Mapping[str, Any], *, vision_instances: Sequence[str] = (),
    vision_layers: Optional[Mapping[int, Sequence[str]]] = None,
) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    raw_matches = _retrieval_matches(result)

    def sort_score(row: Mapping[str, Any]) -> float:
        value = _score(row.get("score"))
        return -value if value is not None else float("inf")

    ordered = sorted(
        (_plain(row) for row in raw_matches),
        key=lambda row: (
            sort_score(row),
            _text(row.get("instance_id")) or "",
            _text(row.get("item_id")) or _text(row.get("id")) or "",
            _text(row.get("label")) or _text(row.get("name")) or "",
            _canonical(row),
        ),
    )
    ranks: Dict[str, int] = defaultdict(int)
    claims: List[Dict[str, Any]] = []
    instances: List[str] = []
    candidates: List[Dict[str, Any]] = []
    for stable_index, raw in enumerate(ordered):
        raw = dict(raw)
        raw.setdefault("provenance", result.get("provenance"))
        if not (_text(raw.get("instance_id")) or
                _text(raw.get("garment_id"))):
            layer = raw.get("layer")
            layer_matches = ((vision_layers or {}).get(layer, [])
                             if isinstance(layer, int) and not isinstance(layer, bool)
                             else [])
            if len(layer_matches) == 1:
                raw["instance_id"] = layer_matches[0]
            elif len(vision_instances) == 1:
                raw["instance_id"] = vision_instances[0]
            else:
                raw["instance_id"] = f"retrieval-{stable_index + 1}"
        instance_hint = (_text(raw.get("instance_id")) or
                         _text(raw.get("garment_id")) or "unspecified")
        ranks[instance_hint] += 1
        rank = ranks[instance_hint]
        score = _score(raw.get("score"))
        instance, rows = _claims_from_instance(
            raw, index=stable_index, state=RETRIEVAL_STATE,
            source=RETRIEVAL_SOURCE, source_id="retrieval", prefix="retrieval",
            candidate_rank=rank, retrieval_score=score,
        )
        instances.append(instance)
        claims.extend(rows)
        candidates.append({
            "candidate_id": _text(raw.get("item_id")) or _text(raw.get("id"))
                            or f"retrieval-{stable_index + 1}",
            "instance_id": instance,
            "rank_within_instance": rank,
            "label": (_text(raw.get("label")) or _text(raw.get("name"))
                      or _text(raw.get("garment_name"))),
            "score": score,
            "state": RETRIEVAL_STATE,
            "score_is_not_authority": True,
            "provenance": _plain(raw.get("provenance", raw.get("source"))),
        })
    return claims, instances, candidates


def _claim_sort_key(claim: Mapping[str, Any]) -> Tuple[Any, ...]:
    source_order = 0 if claim.get("source") == VISION_SOURCE else 1
    rank = claim.get("candidate_rank")
    return (
        _CATEGORY_ORDER.get(str(claim.get("category")), 99),
        str(claim.get("subject", "")), source_order,
        rank if isinstance(rank, int) else 0,
        _canonical(claim.get("value")), str(claim.get("claim_id", "")),
    )


def _reconcile(claims: Sequence[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    slots: Dict[Tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    comparable = {
        "LAYER", "GARMENT_NAME", "LATERALITY", "COLOR",
        "CONSTRUCTION_REGIME", "MATERIAL",
    }
    for claim in claims:
        if claim.get("category") not in comparable:
            continue
        # Only the nearest retrieval candidate for an instance/category is a
        # comparison claim.  Lower-ranked neighbours remain visible proposals.
        if (claim.get("source") == RETRIEVAL_SOURCE
                and claim.get("candidate_rank") not in (None, 1)):
            continue
        slots[(str(claim.get("subject")), str(claim.get("category")))].append(claim)

    agreements: List[Dict[str, Any]] = []
    contested: List[Dict[str, Any]] = []
    for (subject, category), rows in sorted(slots.items()):
        by_source: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            by_source[str(row.get("source"))].append(row)
        if len(by_source) < 2:
            continue
        value_to_rows: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            value_to_rows[_canonical(row.get("value"))].append(row)
        for canonical, same_value_rows in sorted(value_to_rows.items()):
            if len({str(row.get("source")) for row in same_value_rows}) >= 2:
                agreements.append({
                    "agreement_id": "agreement-" + hashlib.sha256(
                        f"{subject}|{category}|{canonical}".encode("utf-8")
                    ).hexdigest()[:12],
                    "subject": subject,
                    "category": category,
                    "value": _plain(same_value_rows[0].get("value")),
                    "state": "PROPOSED_AGREEMENT_UNCONFIRMED",
                    "claim_ids": sorted(str(row.get("claim_id"))
                                        for row in same_value_rows),
                    "human_confirmation_required": True,
                })
        source_values = {
            source: {_canonical(row.get("value")) for row in source_rows}
            for source, source_rows in by_source.items()
        }
        all_values = set().union(*source_values.values())
        if len(all_values) > 1:
            contested.append({
                "contest_id": "contest-" + hashlib.sha256(
                    f"{subject}|{category}|{'|'.join(sorted(all_values))}".encode("utf-8")
                ).hexdigest()[:12],
                "subject": subject,
                "category": category,
                "state": "CONTESTED",
                "alternatives": [
                    {
                        "value": _plain(row.get("value")),
                        "state": row.get("state"),
                        "source": row.get("source"),
                        "claim_id": row.get("claim_id"),
                    }
                    for row in sorted(rows, key=_claim_sort_key)
                ],
                "resolution": "HUMAN_REVIEW_REQUIRED",
                "no_averaging": True,
            })
    return agreements, contested


def _instances(claims: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for claim in claims:
        grouped[str(claim.get("subject"))].append(claim)
    out: List[Dict[str, Any]] = []
    for subject, rows in sorted(grouped.items()):
        if not subject.startswith("instance:"):
            continue
        categories: Dict[str, List[str]] = defaultdict(list)
        for row in sorted(rows, key=_claim_sort_key):
            categories[str(row.get("category"))].append(str(row.get("claim_id")))
        rear_claims = categories.get("REAR_HIDDEN_STRUCTURE", [])
        out.append({
            "instance_id": subject.split(":", 1)[1],
            "state": "PROPOSED_HUMAN_REVIEW_REQUIRED",
            "rear_hidden": {
                "state": ("PROPOSED_UNOBSERVED" if rear_claims
                          else "UNOBSERVED"),
                "observed": False,
                "proposal_claim_ids": list(rear_claims),
            },
            "claim_ids_by_category": {
                key: values for key, values in sorted(categories.items(),
                    key=lambda item: _CATEGORY_ORDER.get(item[0], 99))
            },
        })
    return out


def _typed_field_views(claims: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    fields = {
        "visible_parts": "VISIBLE_COMPONENT",
        "layers": "LAYER",
        "laterality": "LATERALITY",
        "colors": "COLOR",
        "construction_regimes": "CONSTRUCTION_REGIME",
    }
    out: Dict[str, Any] = {}
    for field, category in fields.items():
        out[field] = [
            {
                "claim_id": row.get("claim_id"),
                "subject": row.get("subject"),
                "value": _plain(row.get("value")),
                "state": row.get("state"),
                "source": row.get("source"),
            }
            for row in sorted(claims, key=_claim_sort_key)
            if row.get("category") == category
        ]

    rear_candidates: List[Dict[str, Any]] = []
    for row in sorted(claims, key=_claim_sort_key):
        if row.get("category") != "REAR_HIDDEN_STRUCTURE":
            continue
        value = row.get("value")
        alternatives = (value.get("alternatives")
                        if isinstance(value, Mapping) else None)
        if not _sequence(alternatives):
            alternatives = [value]
        for alternative in _ordered(alternatives):
            identity = {
                "claim_id": row.get("claim_id"),
                "value": alternative,
            }
            rear_candidates.append({
                "candidate_id": "rear-" + hashlib.sha256(
                    _canonical(identity).encode("utf-8")).hexdigest()[:16],
                "claim_id": row.get("claim_id"),
                "subject": row.get("subject"),
                "value": alternative,
                "state": row.get("state"),
                "source": row.get("source"),
                "visibility": "UNOBSERVED_HIDDEN",
                "observed": False,
            })
    out["rear_candidates"] = sorted(
        rear_candidates,
        key=lambda row: (str(row["subject"]), str(row["source"]),
                         _canonical(row["value"]), row["candidate_id"]),
    )
    return out


def _source_record(source: str, available: Mapping[str, Any],
                   config: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "source": source,
        "available": bool(available.get("available")),
        "configuration_metadata": _plain(config),
        "configuration_metadata_role": (
            "IDENTIFICATION_AND_LICENSE_CONFIGURATION_ONLY_NOT_CORRECTNESS_EVIDENCE"
        ),
    }
    if not out["available"]:
        out["capability_failure"] = _plain(available.get("failure"))
    return out


def _review_checklist(contested: Sequence[Mapping[str, Any]],
                      has_hidden: bool) -> List[Dict[str, Any]]:
    checklist: List[Dict[str, Any]] = [
        {
            "review_id": "confirm-visible-instances-and-layer-order",
            "status": "REQUIRED",
            "instruction": "Confirm how many visible garments exist and their inside-to-outside layer order.",
        },
        {
            "review_id": "confirm-visible-component-boundaries",
            "status": "REQUIRED",
            "instruction": "Confirm visible component/part boundaries, including trouser-leg versus skirt continuity and asymmetric overlays.",
        },
        {
            "review_id": "confirm-names-are-display-labels",
            "status": "REQUIRED",
            "instruction": "Accept, rename, or reject garment names; names do not determine construction truth.",
        },
        {
            "review_id": "confirm-construction-and-material-proposals",
            "status": "REQUIRED",
            "instruction": "Review construction-regime and material proposals independently of visual similarity scores.",
        },
    ]
    if has_hidden:
        checklist.append({
            "review_id": "review-unobserved-rear-hidden-structure",
            "status": "REQUIRED",
            "instruction": "Rear and hidden structure is unobserved; keep alternatives proposed until separate evidence or human approval exists.",
        })
    for row in contested:
        checklist.append({
            "review_id": f"resolve-{row['contest_id']}",
            "status": "REQUIRED",
            "instruction": f"Resolve contested {row['category']} for {row['subject']} without averaging the alternatives.",
            "contest_id": row["contest_id"],
        })
    return checklist


def _merge(
    request: Mapping[str, Any], vision: Mapping[str, Any],
    retrieval: Mapping[str, Any], vision_config: Mapping[str, Any],
    retrieval_config: Mapping[str, Any],
) -> Dict[str, Any]:
    audit_mode = _audit_mode(request)
    view_authority = _image_view(request)
    adoption = (AUTO_ACCEPTED_FOR_PREVIEW
                if audit_mode == AUTO_PROPOSED else "HUMAN_AUDIT_REQUIRED")
    audit_contract = {
        "mode": audit_mode,
        "proposal_authority": "PROPOSED",
        "preview_adoption": adoption,
        "observed_promotion": False,
        "human_review_required_for_observed_or_manufacturing_claims": True,
        "manufacturing_certification": False,
        "industrial_strength_guarantee": False,
    }
    available_count = int(bool(vision.get("available"))) + int(bool(retrieval.get("available")))
    sources = [
        _source_record(VISION_SOURCE, vision, vision_config),
        _source_record(RETRIEVAL_SOURCE, retrieval, retrieval_config),
    ]
    if available_count == 0:
        return {
            "schema": SCHEMA,
            "verdict": "UNKNOWN_GARMENT_ANALYSIS_PROVIDERS_UNAVAILABLE",
            "state": "UNKNOWN",
            "typed_stop": True,
            "why": "neither independent proposal provider is available",
            "how_to_close": "supply at least one vision or retrieval provider/result",
            "capabilities": {"sources": sources, "partial_result_allowed": True},
            "claims": [], "agreements": [], "contested": [],
            "garment_instances": [], "retrieval_candidates": [],
            "visible_parts": [], "layers": [], "laterality": [],
            "colors": [], "construction_regimes": [], "rear_candidates": [],
            "audit_contract": audit_contract,
            "authority": {"source_view": view_authority},
            "fact_promotions": [], "manufacturing_ready": False,
        }

    claims: List[Dict[str, Any]] = []
    retrieval_candidates: List[Dict[str, Any]] = []
    vision_instances: List[str] = []
    vision_layers: Dict[int, List[str]] = defaultdict(list)
    if vision.get("available"):
        rows, vision_instances = _vision_claims(vision["result"])
        claims.extend(rows)
        for row in rows:
            if row.get("category") != "LAYER":
                continue
            layer = row.get("value")
            subject = str(row.get("subject", ""))
            if isinstance(layer, int) and subject.startswith("instance:"):
                vision_layers[layer].append(subject.split(":", 1)[1])
    if retrieval.get("available"):
        rows, _, retrieval_candidates = _retrieval_claims(
            retrieval["result"], vision_instances=vision_instances,
            vision_layers=vision_layers,
        )
        claims.extend(rows)
    claims.sort(key=_claim_sort_key)
    agreements, contested = _reconcile(claims)
    typed_fields = _typed_field_views(claims)
    has_hidden = any(row.get("category") == "REAR_HIDDEN_STRUCTURE" for row in claims)
    image = request.get("image")
    return {
        "schema": SCHEMA,
        "analysis_id": _text(request.get("analysis_id")) or (
            "analysis-" + hashlib.sha256(_canonical({
                "image": image, "claims": [row["claim_id"] for row in claims],
            }).encode("utf-8")).hexdigest()[:16]
        ),
        "verdict": "ANSWER" if available_count == 2 else "ANSWER_PARTIAL",
        "state": ("PROPOSED_AUTO_ACCEPTED_FOR_PREVIEW"
                  if audit_mode == AUTO_PROPOSED else
                  "PROPOSED_HUMAN_REVIEW_REQUIRED"),
        "typed_stop": False,
        "image": _plain(image),
        "capabilities": {
            "sources": sources,
            "available_provider_count": available_count,
            "partial_result": available_count == 1,
            "partial_result_allowed": True,
        },
        "garment_instances": _instances(claims),
        "claims": claims,
        "agreements": agreements,
        "contested": contested,
        "retrieval_candidates": retrieval_candidates,
        **typed_fields,
        "audit_contract": audit_contract,
        "normalization": {
            "contract": "TYPED_GARMENT_PROPOSALS_ONLY",
            "provider_native_prose_enters_ir": False,
            "provider_specific_authority_removed": True,
            "merge_order": "CANONICAL_CONTENT_ORDER",
        },
        "human_review_checklist": _review_checklist(
            contested, has_hidden or bool(claims)),
        "authority": {
            "automatic_observed_promotion": False,
            "agreement_is_not_observation": True,
            "retrieval_score_is_not_truth": True,
            "image_similarity_is_not_manufacturing_fact": True,
            "rear_hidden_observed": False,
            "source_view": view_authority,
            "audit_mode": audit_mode,
            "preview_adoption": adoption,
        },
        "fact_promotions": [],
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        "industrial_strength_guaranteed": False,
    }


async def analyze_garment_image_async(
    request: Mapping[str, Any], *, vision_provider: Any = None,
    retrieval_provider: Any = None,
    provider_timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Run independent providers concurrently and deterministically merge.

    Async provider completion order is intentionally discarded: output source
    order is always vision then retrieval, and claims use a canonical sort.
    """
    if not isinstance(request, Mapping):
        return {
            "schema": SCHEMA, "verdict": "UNKNOWN_GARMENT_ANALYSIS_INPUT",
            "state": "UNKNOWN", "typed_stop": True,
            "why": "request must be an object", "fact_promotions": [],
        }
    if request.get("schema") not in (None, REQUEST_SCHEMA):
        return {
            "schema": SCHEMA, "verdict": "UNKNOWN_GARMENT_ANALYSIS_SCHEMA",
            "state": "UNKNOWN", "typed_stop": True,
            "why": f"schema must be exactly {REQUEST_SCHEMA}",
            "fact_promotions": [],
        }
    try:
        vision_embedded, vision_config = _embedded(request, "vision")
        retrieval_embedded, retrieval_config = _embedded(request, "retrieval")
        vision_timeout = _timeout_seconds(
            request, "vision", provider_timeout_seconds)
        retrieval_timeout = _timeout_seconds(
            request, "retrieval", provider_timeout_seconds)
        # gather gives actual overlap for async providers while preserving the
        # fixed result positions regardless of which provider finishes first.
        vision, retrieval = await asyncio.gather(
            _resolve_provider(
                key="vision", provider=vision_provider,
                embedded=vision_embedded, request=request,
                timeout_seconds=vision_timeout,
            ),
            _resolve_provider(
                key="retrieval", provider=retrieval_provider,
                embedded=retrieval_embedded, request=request,
                timeout_seconds=retrieval_timeout,
            ),
        )
        return _merge(
            request, vision, retrieval, vision_config, retrieval_config)
    except (TypeError, ValueError) as exc:
        return {
            "schema": SCHEMA, "verdict": "UNKNOWN_GARMENT_ANALYSIS_INPUT",
            "state": "UNKNOWN", "typed_stop": True,
            "why": str(exc), "fact_promotions": [],
        }


def analyze_garment_image(
    request: Mapping[str, Any], *, vision_provider: Any = None,
    retrieval_provider: Any = None,
    provider_timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Synchronous boundary for MCP and non-async callers."""
    if not isinstance(request, Mapping):
        return {
            "schema": SCHEMA, "verdict": "UNKNOWN_GARMENT_ANALYSIS_INPUT",
            "state": "UNKNOWN", "typed_stop": True,
            "why": "request must be an object", "fact_promotions": [],
        }
    if request.get("schema") not in (None, REQUEST_SCHEMA):
        return {
            "schema": SCHEMA, "verdict": "UNKNOWN_GARMENT_ANALYSIS_SCHEMA",
            "state": "UNKNOWN", "typed_stop": True,
            "why": f"schema must be exactly {REQUEST_SCHEMA}",
            "fact_promotions": [],
        }
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(analyze_garment_image_async(
            request, vision_provider=vision_provider,
            retrieval_provider=retrieval_provider,
            provider_timeout_seconds=provider_timeout_seconds,
        ))
    if vision_provider is None and retrieval_provider is None:
        # Avoid nesting an event loop for the common precomputed-result path.
        try:
            vision_embedded, vision_config = _embedded(request, "vision")
            retrieval_embedded, retrieval_config = _embedded(request, "retrieval")

            def direct(value: Any, key: str) -> Dict[str, Any]:
                if value is _MISSING or value is None or (
                    isinstance(value, Mapping) and value.get("available") is False
                ):
                    return {
                        "available": False,
                        "failure": {
                            "verdict": (
                                "UNKNOWN_VISION_PROVIDER_UNAVAILABLE"
                                if key == "vision" else
                                "UNKNOWN_RETRIEVAL_PROVIDER_UNAVAILABLE"
                            ),
                            "why": f"no usable {key} precomputed result was supplied",
                        },
                    }
                if not isinstance(value, Mapping):
                    return {
                        "available": False,
                        "failure": {
                            "verdict": (
                                "UNKNOWN_VISION_PROVIDER_FAILED"
                                if key == "vision" else
                                "UNKNOWN_RETRIEVAL_PROVIDER_FAILED"
                            ),
                            "why": f"{key} result must be an object",
                        },
                    }
                return {"available": True, "result": _plain(value)}

            return _merge(
                request, direct(vision_embedded, "vision"),
                direct(retrieval_embedded, "retrieval"),
                vision_config, retrieval_config,
            )
        except (TypeError, ValueError) as exc:
            return {
                "schema": SCHEMA,
                "verdict": "UNKNOWN_GARMENT_ANALYSIS_INPUT",
                "state": "UNKNOWN", "typed_stop": True,
                "why": str(exc), "fact_promotions": [],
            }
    raise RuntimeError(
        "use analyze_garment_image_async when calling async providers from an active event loop"
    )


# Short, explicit alias for code that treats the ensemble as a component.
analyze = analyze_garment_image
