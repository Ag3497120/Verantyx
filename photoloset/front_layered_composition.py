# -*- coding: utf-8 -*-
"""Bridge front-image candidate parts into layered structure alternatives.

The upstream boundary is shaped like the candidate side of
``front_image_generation_contract``: every candidate has an id, is a
``PROPOSED`` hypothesis, carries explicit rear/material hypotheses, and owns a
list of geometry-first parts.  This module does not classify a garment name
and does not run vision.  It deterministically translates those parts into the
input accepted by :mod:`photoloset.layered_garment_composer`.

The bridge is intentionally conservative.  A front image may support visible
shape evidence, but it cannot observe a rear construction, material mechanics,
or the exact attachment hidden inside a seam.  Those claims remain
``PROPOSED``.  Ambiguous joins are emitted as separate valid
``garment.structure.v1`` alternatives and are never auto-selected.  Every
alternative is bound to the source candidate id and digest, and no result is a
manufacturing claim.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .garment_structure import PrimitiveKind
from .layered_garment_composer import (
    REQUEST_SCHEMA as LAYERED_REQUEST_SCHEMA,
    compose as compose_layered_garment,
)


REQUEST_SCHEMA = "garment.front-layered-composition.request.v1"
SCHEMA = "garment.front-layered-composition.v1"
PROPOSED = "PROPOSED"
OBSERVED = "OBSERVED"
REVIEW = "REVIEW"

_RELATIONS = {"JOIN", "SEPARATE", "LAYER", "CONTACT", "OVERLAP"}
_HIDDEN_TOKENS = {
    "back", "rear", "backside", "hidden", "occluded", "背面", "後身頃",
    "不可視", "隠れ",
}
_ORNAMENT_KINDS = {"BOW", "RIBBON", "ROSETTE", "TIE", "FLAP"}
_UPPER_KINDS = {"BODY_SHELL", "YOKE"}
_LOWER_KINDS = {"FLARE", "FRUSTUM", "TUBE"}
_ONE_PIECE_TOKENS = {"JOIN", "ONE_PIECE", "ONE-PIECE", "CONTINUOUS"}
_SEPARATE_TOKENS = {"SEPARATE", "SEPARATED", "TWO_PIECE", "TWO-PIECE"}


class _Refusal(Exception):
    def __init__(self, code: str, why: str, **detail: Any) -> None:
        super().__init__(why)
        self.code = code
        self.why = why
        self.detail = detail


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_plain(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not canonical JSON")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    raise TypeError(f"value is not canonical JSON: {type(value).__name__}")


def stable_digest(value: Any) -> str:
    encoded = json.dumps(
        _plain(value), sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unknown(request: Any, code: str, why: str, **detail: Any) -> Dict[str, Any]:
    try:
        input_digest = stable_digest(request)
    except (TypeError, ValueError, OverflowError):
        input_digest = None
    result = {
        "schema": SCHEMA,
        "verdict": code,
        "state": "UNRESOLVED",
        "reason_code": code,
        "why": why,
        "how_to_close": (
            "supply proposal-only front candidates with explicit primitive "
            "dimensions and falsifiable rear/material hypotheses"
        ),
        "input_digest": input_digest,
        "manufacturing_ready": False,
        "manufacturing_certified": False,
        **copy.deepcopy(detail),
    }
    result["digest"] = stable_digest(result)
    return result


def _identifier(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _Refusal("UNKNOWN_IDENTIFIER_REQUIRED",
                       f"{field} must be a non-empty string", field=field)
    return value.strip()


def _authority(value: Any, default: str = "") -> str:
    if isinstance(value, Mapping):
        return str(value.get("state", value.get("authority", default))).upper()
    return default.upper()


def _proposal_claim(value: Any, *, field: str, default_value: str,
                    default_basis: str, default_breaks_when: str) -> Dict[str, Any]:
    if value is None:
        return {
            "state": PROPOSED,
            "value": default_value,
            "basis": default_basis,
            "breaks_when": default_breaks_when,
        }
    if isinstance(value, str) and value.strip():
        return {
            "state": PROPOSED,
            "value": value.strip(),
            "basis": default_basis,
            "breaks_when": default_breaks_when,
        }
    if not isinstance(value, Mapping):
        raise _Refusal("UNKNOWN_TYPED_HYPOTHESIS_REQUIRED",
                       f"{field} must be a typed proposal", field=field)
    claimed = _authority(value, PROPOSED)
    if claimed != PROPOSED:
        raise _Refusal(
            "UNKNOWN_FRONT_ONLY_AUTHORITY_ESCALATION",
            f"{field} cannot be observed from one front image",
            field=field, claimed_state=claimed, required_state=PROPOSED,
        )
    if "value" not in value:
        raise _Refusal("UNKNOWN_HYPOTHESIS_VALUE_REQUIRED",
                       f"{field} needs a value", field=field)
    basis = value.get("basis", default_basis)
    breaks = value.get("breaks_when", default_breaks_when)
    if (not isinstance(basis, str) or not basis.strip()
            or not isinstance(breaks, str) or not breaks.strip()):
        raise _Refusal("UNKNOWN_HYPOTHESIS_BASIS_REQUIRED",
                       f"{field} needs basis and breaks_when", field=field)
    result = _plain(value)
    result["state"] = PROPOSED
    result.pop("authority", None)
    result["basis"] = basis.strip()
    result["breaks_when"] = breaks.strip()
    return result


def _candidate_digest(candidate: Mapping[str, Any]) -> Tuple[str, bool]:
    supplied = candidate.get("candidate_digest")
    if supplied is not None:
        return _identifier(supplied, field="candidate_digest"), True
    canonical = {
        key: copy.deepcopy(value) for key, value in candidate.items()
        if key not in {"candidate_digest", "approval_target_digest"}
    }
    parts = canonical.get("parts")
    if isinstance(parts, Sequence) and not isinstance(parts, (str, bytes)):
        canonical["parts"] = sorted(
            (_plain(row) for row in parts),
            key=lambda row: (str(row.get("part_id", "")), stable_digest(row)),
        )
    structure = canonical.get("structure")
    if isinstance(structure, Mapping):
        structure = copy.deepcopy(dict(structure))
        nested = structure.get("parts")
        if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes)):
            structure["parts"] = sorted(
                (_plain(row) for row in nested),
                key=lambda row: (str(row.get("part_id", "")), stable_digest(row)),
            )
        canonical["structure"] = structure
    return stable_digest(canonical), False


def _number(value: Any, *, field: str, allow_zero: bool = False) -> float:
    if isinstance(value, Mapping):
        claimed = _authority(value, PROPOSED)
        if claimed not in {PROPOSED, OBSERVED}:
            raise _Refusal("UNKNOWN_DIMENSION_AUTHORITY",
                           f"{field} has an invalid authority", field=field)
        value = value.get("value_cm", value.get("value"))
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or (float(value) < 0.0 if allow_zero else float(value) <= 0.0)):
        raise _Refusal("UNKNOWN_POSITIVE_DIMENSION_REQUIRED",
                       f"{field} must be finite and positive", field=field)
    return float(value)


def _dimension_map(part: Mapping[str, Any], part_id: str) -> Dict[str, float]:
    raw = part.get("dimensions")
    if not isinstance(raw, Mapping):
        raise _Refusal("UNKNOWN_PART_DIMENSIONS_REQUIRED",
                       f"{part_id}.dimensions must be an object", part_id=part_id)
    result: Dict[str, float] = {}
    for name in sorted(raw):
        key = _identifier(name, field=f"{part_id}.dimension")
        coordinate = key in {"x_cm", "y_cm", "z_cm"} or key.endswith("_angle_deg")
        result[key] = _number(raw[name], field=f"{part_id}.{key}",
                              allow_zero=coordinate)
    return result


def _first_dimension(dimensions: Mapping[str, float], names: Iterable[str],
                     *, field: str) -> float:
    for name in names:
        value = dimensions.get(name)
        if isinstance(value, (int, float)) and float(value) > 0.0:
            return float(value)
    raise _Refusal("UNKNOWN_ORNAMENT_DIMENSION_REQUIRED",
                   f"{field} cannot be derived from supplied ornament geometry",
                   field=field, accepted=list(names))


def _primitive(part: Mapping[str, Any], part_id: str) -> Tuple[str, Dict[str, float], str]:
    source_kind = _identifier(
        part.get("kind", part.get("primitive_kind")),
        field=f"{part_id}.kind",
    ).upper()
    dimensions = _dimension_map(part, part_id)
    if source_kind == "BOW":
        mapped = {
            "height_cm": _first_dimension(
                dimensions, ("body_width_cm", "height_cm", "knot_length_cm"),
                field=f"{part_id}.height_cm"),
            "width_cm": _first_dimension(
                dimensions, ("body_length_cm", "width_cm"),
                field=f"{part_id}.width_cm"),
        }
        return "OVERLAY", mapped, source_kind
    if source_kind == "RIBBON":
        mapped = {
            "length_cm": _first_dimension(
                dimensions, ("length_cm", "body_length_cm"),
                field=f"{part_id}.length_cm"),
            "width_cm": _first_dimension(
                dimensions, ("width_cm", "body_width_cm"),
                field=f"{part_id}.width_cm"),
        }
        return "BAND", mapped, source_kind
    if source_kind == "ROSETTE":
        strip_width = _first_dimension(
            dimensions, ("strip_width_cm", "width_cm"),
            field=f"{part_id}.strip_width_cm")
        inner = _first_dimension(
            dimensions, ("finished_inner_length_cm", "strip_length_cm"),
            field=f"{part_id}.finished_inner_length_cm")
        return "OVERLAY", {
            "height_cm": strip_width * 2.0,
            "width_cm": max(strip_width * 2.0, inner / math.pi),
        }, source_kind
    if source_kind == "TIE":
        return "BAND", {
            "length_cm": _first_dimension(
                dimensions, ("length_cm",), field=f"{part_id}.length_cm"),
            "width_cm": _first_dimension(
                dimensions, ("top_width_cm", "width_cm", "tip_width_cm"),
                field=f"{part_id}.width_cm"),
        }, source_kind
    if source_kind == "FLAP":
        return "OVERLAY", {
            "height_cm": _first_dimension(
                dimensions, ("depth_cm", "height_cm"),
                field=f"{part_id}.height_cm"),
            "width_cm": _first_dimension(
                dimensions, ("attachment_width_cm", "outer_width_cm", "width_cm"),
                field=f"{part_id}.width_cm"),
        }, source_kind
    try:
        PrimitiveKind(source_kind)
    except ValueError as exc:
        raise _Refusal(
            "UNKNOWN_GEOMETRIC_PRIMITIVE",
            "parts must use an existing geometric primitive or supported ornament mapping",
            part_id=part_id, kind=source_kind,
            allowed=[kind.value for kind in PrimitiveKind],
            mapped_ornaments=sorted(_ORNAMENT_KINDS),
        ) from exc
    if source_kind == "DRAPE_ANCHOR" and not dimensions:
        dimensions = {"x_cm": 0.0}
    return source_kind, dimensions, source_kind


def _text(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("value", value.get("name", ""))
    return str(value or "").strip()


def _visibility(part: Mapping[str, Any]) -> str:
    explicit = str(part.get("visibility", "")).upper()
    if explicit in {"REAR", "OCCLUDED", "HIDDEN", "UNKNOWN"}:
        return explicit
    text = " ".join((_text(part.get("placement")),
                     _text(part.get("semantic_role")),
                     _text(part.get("detail_role")))).lower()
    if any(token in text for token in _HIDDEN_TOKENS):
        return "OCCLUDED"
    return "FRONT_VISIBLE"


def _visible_evidence(part: Mapping[str, Any], part_id: str) -> Dict[str, str]:
    raw = part.get("visible_basis")
    if isinstance(raw, str) and raw.strip():
        result = {
            "state": PROPOSED,
            "basis": raw.strip(),
            "breaks_when": "another view or a human structure edit contradicts it",
        }
    elif isinstance(raw, Mapping):
        state = _authority(raw, PROPOSED)
        if state not in {PROPOSED, OBSERVED}:
            raise _Refusal("UNKNOWN_VISIBLE_BASIS_AUTHORITY",
                           f"{part_id}.visible_basis has invalid authority")
        basis = raw.get("basis", raw.get("description", raw.get("source")))
        breaks = raw.get(
            "breaks_when", "another view or a human structure edit contradicts it")
        if (not isinstance(basis, str) or not basis.strip()
                or not isinstance(breaks, str) or not breaks.strip()):
            raise _Refusal("UNKNOWN_VISIBLE_BASIS_REQUIRED",
                           f"{part_id}.visible_basis needs basis and breaks_when")
        result = {"state": state, "basis": basis.strip(),
                  "breaks_when": breaks.strip()}
    else:
        raise _Refusal("UNKNOWN_VISIBLE_BASIS_REQUIRED",
                       f"{part_id} needs typed visible_basis", part_id=part_id)
    if _visibility(part) != "FRONT_VISIBLE" and result["state"] == OBSERVED:
        raise _Refusal(
            "UNKNOWN_HIDDEN_PART_AUTHORITY_ESCALATION",
            "rear, hidden, and occluded parts cannot be OBSERVED from a front image",
            part_id=part_id, visibility=_visibility(part),
        )
    return result


def _zones(part: Mapping[str, Any], kind: str) -> List[str]:
    raw = part.get("coverage_zones")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        zones = sorted({str(value).strip() for value in raw
                        if isinstance(value, str) and value.strip()})
        if zones:
            return zones
    text = " ".join((_text(part.get("placement")), _text(part.get("side")),
                     _text(part.get("detail_role")))).lower()
    result: Set[str] = set()
    if any(token in text for token in ("torso", "bodice", "upper", "chest", "back")):
        result.add("torso")
    if any(token in text for token in ("lower", "waist", "hip", "skirt", "leg")):
        result.add("lower-body")
    if "left" in text:
        result.add("left-lower" if "lower-body" in result else "left")
    if "right" in text:
        result.add("right-lower" if "lower-body" in result else "right")
    if "crotch" in text or kind == "GUSSET":
        result.add("crotch")
    if "neck" in text or kind in {"COLLAR", "HOOD"}:
        result.add("neck")
    if "arm" in text or kind == "SLEEVE":
        result.add("arms")
    if kind in _UPPER_KINDS and not result:
        result.add("torso")
    if kind in _LOWER_KINDS and not result:
        result.add("lower-body")
    if kind == "OVERLAY" and not result:
        result.add("torso")
    return sorted(result or {"unspecified"})


def _targets(value: Any, *, field: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if (isinstance(value, Sequence) and not isinstance(value, (str, bytes))
            and all(isinstance(item, str) and item.strip() for item in value)):
        result = sorted({item.strip() for item in value})
        if result:
            return result
    raise _Refusal("UNKNOWN_ATTACHMENT_TARGET",
                   f"{field} must name one or more part ids", field=field)


def _normalize_part(part: Any, *, candidate_id: str,
                    rear: Mapping[str, Any], material: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(part, Mapping):
        raise _Refusal("UNKNOWN_CANDIDATE_PART",
                       "candidate parts must contain objects")
    part = copy.deepcopy(dict(part))
    part_id = _identifier(part.get("part_id", part.get("component_id")),
                          field=f"{candidate_id}.part_id")
    kind, dimensions, source_kind = _primitive(part, part_id)
    visible = _visible_evidence(part, part_id)
    layer = part.get("layer", 0)
    if (isinstance(layer, bool) or not isinstance(layer, int)
            or not 0 <= layer <= 15):
        raise _Refusal("UNKNOWN_PART_LAYER",
                       f"{part_id}.layer must be an integer from 0 through 15")
    part_material = _proposal_claim(
        part.get("material", material), field=f"{part_id}.material",
        default_value=str(material.get("value", "unknown material alternative")),
        default_basis=str(material.get("basis", "appearance cannot determine mechanics")),
        default_breaks_when=str(material.get(
            "breaks_when", "a swatch or material test is supplied")),
    )
    part_rear = _proposal_claim(
        part.get("rear", rear), field=f"{part_id}.rear",
        default_value=str(rear.get("value", "unknown rear alternative")),
        default_basis=str(rear.get("basis", "the rear is absent")),
        default_breaks_when=str(rear.get(
            "breaks_when", "a rear or side view is supplied")),
    )
    placement = _text(part.get("placement")) or "unspecified placement"
    semantic = (_text(part.get("semantic_role"))
                or _text(part.get("detail_role"))
                or f"{source_kind.lower()} geometric part")
    unit = _text(part.get("garment_unit")) or candidate_id
    raw_relation = _text(part.get(
        "attachment_relation", part.get("relation"))).upper()
    if raw_relation and raw_relation not in _RELATIONS:
        raise _Refusal("UNKNOWN_ATTACHMENT_RELATION",
                       f"{part_id} has an unsupported attachment relation",
                       part_id=part_id, relation=raw_relation)
    relation_candidates = part.get("relation_candidates", [])
    if relation_candidates:
        if (not isinstance(relation_candidates, Sequence)
                or isinstance(relation_candidates, (str, bytes))):
            raise _Refusal("UNKNOWN_ATTACHMENT_RELATIONS",
                           f"{part_id}.relation_candidates must be an array")
        relation_candidates = sorted({str(value).upper()
                                      for value in relation_candidates})
        if not relation_candidates or any(value not in _RELATIONS
                                          for value in relation_candidates):
            raise _Refusal("UNKNOWN_ATTACHMENT_RELATION",
                           f"{part_id} has unsupported relation candidates")
    if str(part.get("attachment_state", part.get(
            "attachment_authority", PROPOSED))).upper() != PROPOSED:
        raise _Refusal(
            "UNKNOWN_ATTACHMENT_AUTHORITY_ESCALATION",
            "exact attachment topology from one front image must remain PROPOSED",
            part_id=part_id,
        )
    return {
        "part_id": part_id,
        "kind": kind,
        "source_kind": source_kind,
        "dimensions": dimensions,
        "layer": layer,
        "placement": placement,
        "coverage_zones": _zones(part, kind),
        "semantic_role": semantic,
        "garment_unit": unit,
        "visible": visible,
        "visibility": _visibility(part),
        "rear": part_rear,
        "material": part_material,
        "attached_to": _targets(part.get("attached_to"),
                                field=f"{part_id}.attached_to"),
        "attachment_relation": raw_relation,
        "relation_candidates": list(relation_candidates),
        "assembly": _text(part.get("assembly", part.get("construction"))).upper(),
        "side": _text(part.get("side")).lower(),
        "is_ornament": source_kind in _ORNAMENT_KINDS,
    }


def _connection_extent(part: Mapping[str, Any], zone: str) -> Optional[float]:
    dimensions = part["dimensions"]
    normalized_zone = zone.lower()
    if "waist" in normalized_zone:
        names = ("top_circumference_cm", "circumference_cm",
                 "upper_circumference_cm", "width_cm")
    elif "crotch" in normalized_zone:
        names = ("length_cm", "width_cm", "circumference_cm")
    elif "neck" in normalized_zone:
        names = ("length_cm", "circumference_cm", "width_cm")
    elif "arm" in normalized_zone:
        names = ("upper_circumference_cm", "circumference_cm", "width_cm")
    else:
        names = ("attachment_width_cm", "width_cm", "length_cm",
                 "top_circumference_cm", "circumference_cm", "height_cm")
    for name in names:
        if name in dimensions and float(dimensions[name]) > 0.0:
            return float(dimensions[name])
    return None


class _ComposerInput:
    def __init__(self, parts: Sequence[Mapping[str, Any]]) -> None:
        self.parts = {str(part["part_id"]): copy.deepcopy(dict(part))
                      for part in parts}
        self.components: Dict[str, Dict[str, Any]] = {}
        for part_id in sorted(self.parts):
            part = self.parts[part_id]
            self.components[part_id] = {
                "component_id": part_id,
                "primitive_kind": part["kind"],
                "dimensions": copy.deepcopy(part["dimensions"]),
                "boundaries": [],
                "layer": part["layer"],
                "coverage_zones": list(part["coverage_zones"]),
                "semantic_role": (
                    f"{part['semantic_role']} (source kind {part['source_kind']})"
                ),
                "garment_unit": part["garment_unit"],
                "rear": copy.deepcopy(part["rear"]),
                "material": copy.deepcopy(part["material"]),
            }
        self.choices: List[Dict[str, Any]] = []
        self.choice_ids: Set[str] = set()
        self.related_pairs: Set[frozenset[str]] = set()

    def _port(self, part_id: str, boundary_id: str, interface: str,
              length: float, role: str, basis: str) -> Dict[str, Any]:
        part = self.parts[part_id]
        return {
            "boundary_id": boundary_id,
            "length_cm": length,
            "interface": interface,
            "role": role,
            "visibility": "UNKNOWN",
            "state": PROPOSED,
            "basis": basis,
            "breaks_when": (
                "a rear/side view, disassembly, or construction review changes "
                "the attachment topology"
            ),
            "source_part_visibility": part["visibility"],
        }

    def add_choice(self, choice_id: str,
                   alternatives: Sequence[Mapping[str, Any]]) -> None:
        choice_id = _identifier(choice_id, field="choice_id")
        if choice_id in self.choice_ids:
            raise _Refusal("UNKNOWN_DUPLICATE_ATTACHMENT_CHOICE",
                           "generated attachment choice ids must be unique",
                           choice_id=choice_id)
        normalized: List[Dict[str, Any]] = []
        for index, source in enumerate(sorted(
                (_plain(row) for row in alternatives),
                key=lambda row: (str(row.get("alternative_id", "")),
                                 stable_digest(row)))):
            alternative_id = _identifier(
                source.get("alternative_id", f"alternative-{index + 1}"),
                field=f"{choice_id}.alternative_id")
            relation = str(source.get("relation", "")).upper()
            if relation not in _RELATIONS:
                raise _Refusal("UNKNOWN_ATTACHMENT_RELATION",
                               "attachment alternatives need a supported relation",
                               choice_id=choice_id, relation=relation)
            state = str(source.get("state", source.get(
                "authority", PROPOSED))).upper()
            if state != PROPOSED:
                raise _Refusal(
                    "UNKNOWN_ATTACHMENT_AUTHORITY_ESCALATION",
                    "front-derived attachment alternatives must remain PROPOSED",
                    choice_id=choice_id, alternative_id=alternative_id,
                    claimed_state=state,
                )
            source_id = _identifier(source.get("source_part_id"),
                                    field=f"{choice_id}.source_part_id")
            target_id = _identifier(source.get("target_part_id"),
                                    field=f"{choice_id}.target_part_id")
            if source_id not in self.parts or target_id not in self.parts:
                raise _Refusal("UNKNOWN_ATTACHMENT_TARGET",
                               "attachment alternatives must reference candidate parts",
                               choice_id=choice_id, source_part_id=source_id,
                               target_part_id=target_id)
            if source_id == target_id:
                raise _Refusal("UNKNOWN_SELF_ATTACHMENT",
                               "an attachment needs two distinct parts",
                               choice_id=choice_id, part_id=source_id)
            zone = _text(source.get("contact_zone")) or "unspecified"
            basis = _text(source.get("basis")) or (
                "front geometry permits this candidate-specific topology"
            )
            breaks = _text(source.get("breaks_when")) or (
                "a rear/side view or construction review rejects this topology"
            )
            token = stable_digest({
                "choice_id": choice_id, "alternative_id": alternative_id,
                "source": source_id, "target": target_id, "relation": relation,
            })[:14]
            source_port = f"bridge-{token}-source"
            target_port = f"bridge-{token}-target"
            interface = f"bridge-interface-{token}"
            role = "edge" if relation in {"JOIN", "SEPARATE"} else "point"
            extents = [value for value in (
                _connection_extent(self.parts[source_id], zone),
                _connection_extent(self.parts[target_id], zone),
            ) if value is not None]
            length = min(extents) if extents and role == "edge" else 1.0
            self.components[source_id]["boundaries"].append(self._port(
                source_id, source_port, interface, length, role, basis))
            self.components[target_id]["boundaries"].append(self._port(
                target_id, target_port, interface, length, role, basis))
            normalized.append({
                "alternative_id": alternative_id,
                "relation": relation,
                "source": {"component_id": source_id,
                           "boundary_id": source_port},
                "target": {"component_id": target_id,
                           "boundary_id": target_port},
                "state": PROPOSED,
                "contact_zone": zone,
                "basis": basis,
                "breaks_when": breaks,
                "parameters": {
                    "bridge_generated": True,
                    "source_part_kind": self.parts[source_id]["source_kind"],
                    "target_part_kind": self.parts[target_id]["source_kind"],
                },
            })
            self.related_pairs.add(frozenset((source_id, target_id)))
        if not normalized:
            raise _Refusal("UNKNOWN_ATTACHMENT_ALTERNATIVES_REQUIRED",
                           f"{choice_id} needs at least one alternative")
        self.choice_ids.add(choice_id)
        self.choices.append({"choice_id": choice_id,
                             "alternatives": normalized})

    def has_relation(self, left: str, right: str) -> bool:
        return frozenset((left, right)) in self.related_pairs

    def request(self, source_id: str) -> Dict[str, Any]:
        return {
            "schema": LAYERED_REQUEST_SCHEMA,
            "source_id": source_id,
            "front_only": True,
            "components": [self.components[key]
                           for key in sorted(self.components)],
            "attachment_choices": sorted(
                self.choices, key=lambda row: row["choice_id"]),
        }


def _ref_part_id(value: Any, *, field: str) -> str:
    if isinstance(value, Mapping):
        value = value.get("part_id", value.get("component_id", value.get("node_id")))
    return _identifier(value, field=field)


def _explicit_choices(candidate: Mapping[str, Any], builder: _ComposerInput) -> None:
    raw = candidate.get("attachment_choices", [])
    if raw is None:
        return
    if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))
            or any(not isinstance(choice, Mapping) for choice in raw)):
        raise _Refusal("UNKNOWN_ATTACHMENT_CHOICES",
                       "candidate attachment_choices must be an array")
    for choice in sorted(raw, key=lambda row: str(row.get("choice_id", ""))):
        choice_id = _identifier(choice.get("choice_id"), field="choice_id")
        alternatives = choice.get("alternatives")
        if (not isinstance(alternatives, Sequence)
                or isinstance(alternatives, (str, bytes))
                or not alternatives
                or any(not isinstance(row, Mapping) for row in alternatives)):
            raise _Refusal("UNKNOWN_ATTACHMENT_ALTERNATIVES_REQUIRED",
                           f"{choice_id} needs alternatives")
        translated = []
        for index, alternative in enumerate(alternatives):
            source = alternative.get("source", alternative.get("source_part_id"))
            target = alternative.get("target", alternative.get("target_part_id"))
            translated.append({
                "alternative_id": alternative.get(
                    "alternative_id", f"alternative-{index + 1}"),
                "relation": alternative.get("relation"),
                "source_part_id": _ref_part_id(
                    source, field=f"{choice_id}.source_part_id"),
                "target_part_id": _ref_part_id(
                    target, field=f"{choice_id}.target_part_id"),
                "contact_zone": alternative.get("contact_zone", "unspecified"),
                "state": alternative.get(
                    "state", alternative.get("authority", PROPOSED)),
                "basis": alternative.get("basis"),
                "breaks_when": alternative.get("breaks_when"),
            })
        builder.add_choice(choice_id, translated)


def _default_relation(part: Mapping[str, Any], target: Mapping[str, Any]) -> str:
    if part["attachment_relation"]:
        return str(part["attachment_relation"])
    if (part["kind"] == "OVERLAY" and part["layer"] > target["layer"]
            and not part["is_ornament"]):
        return "LAYER"
    return "JOIN"


def _part_attachments(builder: _ComposerInput) -> None:
    for part_id in sorted(builder.parts):
        part = builder.parts[part_id]
        for target_id in part["attached_to"]:
            if target_id not in builder.parts:
                raise _Refusal("UNKNOWN_ATTACHMENT_TARGET",
                               f"{part_id} names an unknown attachment target",
                               part_id=part_id, target_part_id=target_id)
            if builder.has_relation(part_id, target_id):
                continue
            relations = part["relation_candidates"] or [
                _default_relation(part, builder.parts[target_id])]
            builder.add_choice(
                f"part-attachment:{part_id}:{target_id}",
                [{
                    "alternative_id": f"{relation.lower()}:{part_id}:{target_id}",
                    "relation": relation,
                    "source_part_id": part_id,
                    "target_part_id": target_id,
                    "contact_zone": sorted(
                        set(part["coverage_zones"])
                        & set(builder.parts[target_id]["coverage_zones"])
                    )[0] if (set(part["coverage_zones"])
                             & set(builder.parts[target_id]["coverage_zones"]))
                    else "attachment",
                    "basis": (
                        "the part declares this target, while the exact seam or "
                        "layer topology remains a front-only proposal"
                    ),
                    "breaks_when": (
                        "a rear/side view or construction review changes the target"
                    ),
                } for relation in relations],
            )


def _trouser_relations(builder: _ComposerInput) -> None:
    legs = [part for part in builder.parts.values()
            if part["kind"] == "TUBE"
            and (part["side"] in {"left", "right"}
                 or any(zone in {"left-lower", "right-lower"}
                        for zone in part["coverage_zones"]))]
    gussets = [part for part in builder.parts.values()
               if part["kind"] == "GUSSET"]
    if len(legs) < 2 or not gussets:
        return
    gusset = sorted(gussets, key=lambda row: row["part_id"])[0]
    for leg in sorted(legs, key=lambda row: row["part_id"]):
        if builder.has_relation(gusset["part_id"], leg["part_id"]):
            continue
        builder.add_choice(
            f"trouser-gusset:{gusset['part_id']}:{leg['part_id']}",
            [{
                "alternative_id": "joined-crotch",
                "relation": "JOIN",
                "source_part_id": gusset["part_id"],
                "target_part_id": leg["part_id"],
                "contact_zone": "crotch",
                "basis": "two leg volumes require an explicit proposed crotch bridge",
                "breaks_when": "construction review replaces the gusset topology",
            }],
        )
    uppers = [part for part in builder.parts.values()
              if part["kind"] in _UPPER_KINDS]
    if not uppers:
        return
    upper = sorted(uppers, key=lambda row: (row["layer"], row["part_id"]))[0]
    for leg in sorted(legs, key=lambda row: row["part_id"]):
        if builder.has_relation(upper["part_id"], leg["part_id"]):
            continue
        if upper["garment_unit"] != leg["garment_unit"]:
            continue
        builder.add_choice(
            f"trouser-waist:{upper['part_id']}:{leg['part_id']}",
            [{
                "alternative_id": "joined-waist",
                "relation": "JOIN",
                "source_part_id": upper["part_id"],
                "target_part_id": leg["part_id"],
                "contact_zone": "waist",
                "basis": "the shared garment unit proposes a continuous split lower volume",
                "breaks_when": "construction review separates the upper and lower units",
            }],
        )


def _upper_lower_relations(candidate: Mapping[str, Any],
                           builder: _ComposerInput) -> None:
    uppers = [part for part in builder.parts.values()
              if part["kind"] in _UPPER_KINDS]
    legs = {part["part_id"] for part in builder.parts.values()
            if part["kind"] == "TUBE"
            and (part["side"] in {"left", "right"}
                 or any(zone in {"left-lower", "right-lower"}
                        for zone in part["coverage_zones"]))}
    lowers = [part for part in builder.parts.values()
              if part["kind"] in _LOWER_KINDS and part["part_id"] not in legs]
    if not uppers or not lowers:
        return
    global_assembly = _text(candidate.get("assembly", candidate.get(
        "construction"))).upper()
    for upper in sorted(uppers, key=lambda row: (row["layer"], row["part_id"])):
        for lower in sorted(lowers, key=lambda row: (row["layer"], row["part_id"])):
            if builder.has_relation(upper["part_id"], lower["part_id"]):
                continue
            assembly = lower["assembly"] or upper["assembly"] or global_assembly
            if upper["garment_unit"] != lower["garment_unit"]:
                relations = ["SEPARATE"]
            elif assembly in _ONE_PIECE_TOKENS:
                relations = ["JOIN"]
            elif assembly in _SEPARATE_TOKENS:
                relations = ["SEPARATE"]
            else:
                relations = ["JOIN", "SEPARATE"]
            builder.add_choice(
                f"upper-lower:{upper['part_id']}:{lower['part_id']}",
                [{
                    "alternative_id": (
                        "continuous-one-piece" if relation == "JOIN"
                        else "independent-units"
                    ),
                    "relation": relation,
                    "source_part_id": upper["part_id"],
                    "target_part_id": lower["part_id"],
                    "contact_zone": "waist",
                    "basis": (
                        "candidate part units and front geometry permit this waist topology"
                    ),
                    "breaks_when": (
                        "a rear view or construction review establishes a different waist topology"
                    ),
                } for relation in relations],
            )


def _layer_relations(builder: _ComposerInput) -> None:
    parts = [builder.parts[key] for key in sorted(builder.parts)]
    for index, left in enumerate(parts):
        for right in parts[index + 1:]:
            if builder.has_relation(left["part_id"], right["part_id"]):
                continue
            shared = sorted(set(left["coverage_zones"])
                            & set(right["coverage_zones"]))
            if not shared or left["layer"] == right["layer"]:
                continue
            outer, inner = ((left, right) if left["layer"] > right["layer"]
                            else (right, left))
            if (outer["kind"] != "OVERLAY"
                    and "overlay" not in outer["semantic_role"].lower()
                    and "underlayer" not in inner["semantic_role"].lower()):
                continue
            builder.add_choice(
                f"layer-order:{outer['part_id']}:{inner['part_id']}",
                [{
                    "alternative_id": "outer-over-inner",
                    "relation": "LAYER",
                    "source_part_id": outer["part_id"],
                    "target_part_id": inner["part_id"],
                    "contact_zone": shared[0],
                    "basis": "explicit layer indices and shared coverage propose this order",
                    "breaks_when": "a side/rear view or human layer edit reverses the order",
                }],
            )


def _unattached_ornaments(builder: _ComposerInput) -> None:
    for ornament in sorted(
            (part for part in builder.parts.values() if part["is_ornament"]),
            key=lambda row: row["part_id"]):
        if any(ornament["part_id"] in pair for pair in builder.related_pairs):
            continue
        targets = [part for part in builder.parts.values()
                   if part["part_id"] != ornament["part_id"]
                   and not part["is_ornament"]
                   and part["layer"] <= ornament["layer"]
                   and set(part["coverage_zones"])
                   & set(ornament["coverage_zones"])]
        if not targets:
            raise _Refusal(
                "UNKNOWN_ORNAMENT_ATTACHMENT_TARGET",
                "an ornament needs at least one geometry-compatible proposed target",
                part_id=ornament["part_id"],
            )
        builder.add_choice(
            f"ornament-target:{ornament['part_id']}",
            [{
                "alternative_id": f"attach-to:{target['part_id']}",
                "relation": "JOIN",
                "source_part_id": ornament["part_id"],
                "target_part_id": target["part_id"],
                "contact_zone": sorted(
                    set(target["coverage_zones"])
                    & set(ornament["coverage_zones"]))[0],
                "basis": "front placement permits this ornament attachment target",
                "breaks_when": "construction review or another view identifies another target",
            } for target in sorted(targets, key=lambda row: row["part_id"])],
        )


def _candidate_parts(candidate: Mapping[str, Any]) -> Sequence[Any]:
    direct = candidate.get("parts")
    structure = candidate.get("structure")
    nested = structure.get("parts") if isinstance(structure, Mapping) else None
    if direct is not None and nested is not None:
        raise _Refusal("UNKNOWN_CANDIDATE_PARTS_SHAPE",
                       "provide candidate parts directly or under structure, not both")
    parts = direct if direct is not None else nested
    if (not isinstance(parts, Sequence) or isinstance(parts, (str, bytes))
            or not parts):
        raise _Refusal("UNKNOWN_CANDIDATE_PARTS_REQUIRED",
                       "every front candidate needs a non-empty parts array")
    return parts


def _compose_candidate(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    candidate_id = _identifier(candidate.get("candidate_id"), field="candidate_id")
    state = _authority(candidate)
    if state != PROPOSED:
        raise _Refusal("UNKNOWN_FRONT_CANDIDATE_AUTHORITY",
                       "front-only candidates must remain PROPOSED",
                       candidate_id=candidate_id, claimed_state=state)
    rear = _proposal_claim(
        candidate.get("rear_hypothesis"),
        field=f"{candidate_id}.rear_hypothesis",
        default_value="unknown rear construction",
        default_basis="the rear is absent from the source image",
        default_breaks_when="a rear or side view is supplied",
    )
    material = _proposal_claim(
        candidate.get("material_hypothesis"),
        field=f"{candidate_id}.material_hypothesis",
        default_value="unknown material mechanics",
        default_basis="appearance cannot determine material mechanics",
        default_breaks_when="a swatch or material measurement is supplied",
    )
    digest, digest_supplied = _candidate_digest(candidate)
    parts = [_normalize_part(part, candidate_id=candidate_id,
                             rear=rear, material=material)
             for part in _candidate_parts(candidate)]
    part_ids = [part["part_id"] for part in parts]
    if len(part_ids) != len(set(part_ids)):
        raise _Refusal("UNKNOWN_DUPLICATE_PART_ID",
                       "part ids must be unique within a source candidate",
                       candidate_id=candidate_id)
    parts.sort(key=lambda row: row["part_id"])
    builder = _ComposerInput(parts)
    _explicit_choices(candidate, builder)
    _part_attachments(builder)
    _trouser_relations(builder)
    _upper_lower_relations(candidate, builder)
    _layer_relations(builder)
    _unattached_ornaments(builder)
    source_id = f"front-candidate:{candidate_id}:{digest}"
    layered_request = builder.request(source_id)
    composed = compose_layered_garment(layered_request)
    if composed.get("verdict") not in {PROPOSED, REVIEW}:
        return {
            "source_candidate_id": candidate_id,
            "source_candidate_digest": digest,
            "source_candidate_digest_supplied": digest_supplied,
            "verdict": composed.get("verdict", "UNKNOWN_LAYERED_COMPOSITION"),
            "why": composed.get("why", "layered composition failed"),
            "layered_result": composed,
            "manufacturing_ready": False,
            "manufacturing_certified": False,
        }
    alternatives: List[Dict[str, Any]] = []
    for row in composed["candidates"]:
        binding = {
            "source_candidate_id": candidate_id,
            "source_candidate_digest": digest,
            "layered_candidate_id": row["candidate_id"],
            "structure_digest": row["structure_digest"],
        }
        alternative_id = "front-layered-" + stable_digest(binding)[:18]
        alternative = copy.deepcopy(row)
        alternative["candidate_id"] = alternative_id
        alternative["layered_candidate_id"] = row["candidate_id"]
        alternative["source_candidate_id"] = candidate_id
        alternative["source_candidate_digest"] = digest
        alternative["source_binding"] = binding
        alternative["source_binding_digest"] = stable_digest(binding)
        alternative["state"] = PROPOSED
        alternative["manufacturing_ready"] = False
        alternative["manufacturing_certified"] = False
        alternative["candidate_digest"] = stable_digest({
            key: value for key, value in alternative.items()
            if key != "candidate_digest"
        })
        alternatives.append(alternative)
    alternatives.sort(key=lambda row: row["candidate_id"])
    return {
        "source_candidate_id": candidate_id,
        "source_candidate_digest": digest,
        "source_candidate_digest_supplied": digest_supplied,
        "verdict": composed["verdict"],
        "reason_code": composed["reason_code"],
        "source_alternative_count": len(alternatives),
        "alternatives": alternatives,
        "human_choice": copy.deepcopy(composed["human_choice"]),
        "translator_input": layered_request,
        "authority": {
            "rear": PROPOSED,
            "material": PROPOSED,
            "hidden_parts": PROPOSED,
            "attachments": PROPOSED,
            "layer_order": PROPOSED,
        },
        "manufacturing_ready": False,
        "manufacturing_certified": False,
    }


def compose(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Translate candidate parts and emit bound structure graph alternatives."""
    if not isinstance(request, Mapping):
        return _unknown(request, "UNKNOWN_FRONT_LAYERED_REQUEST",
                        "request must be an object")
    original = copy.deepcopy(dict(request))
    try:
        if request.get("schema") != REQUEST_SCHEMA:
            raise _Refusal("UNKNOWN_FRONT_LAYERED_SCHEMA",
                           f"expected schema {REQUEST_SCHEMA}")
        if request.get("front_only") is not True:
            raise _Refusal("UNKNOWN_FRONT_ONLY_SOURCE_REQUIRED",
                           "the bridge accepts one front-view source")
        raw_candidates = request.get("candidates")
        if (not isinstance(raw_candidates, Sequence)
                or isinstance(raw_candidates, (str, bytes))
                or not raw_candidates
                or any(not isinstance(row, Mapping) for row in raw_candidates)):
            raise _Refusal("UNKNOWN_FRONT_CANDIDATES_REQUIRED",
                           "candidates must be a non-empty array")
        ids = [_identifier(row.get("candidate_id"), field="candidate_id")
               for row in raw_candidates]
        if len(ids) != len(set(ids)):
            raise _Refusal("UNKNOWN_DUPLICATE_CANDIDATE_ID",
                           "source candidate ids must be unique")
        rows: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []
        for candidate in sorted(raw_candidates,
                                key=lambda row: str(row.get("candidate_id", ""))):
            try:
                result = _compose_candidate(candidate)
            except _Refusal as exc:
                try:
                    digest, supplied = _candidate_digest(candidate)
                except _Refusal:
                    fallback = {
                        key: copy.deepcopy(value)
                        for key, value in candidate.items()
                        if key not in {"candidate_digest",
                                       "approval_target_digest"}
                    }
                    digest, supplied = stable_digest(fallback), False
                failures.append({
                    "source_candidate_id": str(candidate.get("candidate_id", "")),
                    "source_candidate_digest": digest,
                    "source_candidate_digest_supplied": supplied,
                    "verdict": exc.code,
                    "why": exc.why,
                    "detail": copy.deepcopy(exc.detail),
                    "manufacturing_ready": False,
                    "manufacturing_certified": False,
                })
                continue
            if "alternatives" in result:
                rows.append(result)
            else:
                failures.append(result)
        alternatives = [copy.deepcopy(alternative)
                        for row in rows for alternative in row["alternatives"]]
        alternatives.sort(key=lambda row: row["candidate_id"])
        failures.sort(key=lambda row: (row["source_candidate_id"],
                                      row["source_candidate_digest"]))
        if not alternatives:
            return _unknown(
                original, "UNKNOWN_NO_LAYERED_STRUCTURE_ALTERNATIVE",
                "no source candidate produced a valid garment.structure.v1 alternative",
                source_candidate_failures=failures,
            )
        needs_choice = (len(alternatives) > 1
                        or any(row["human_choice"]["required"] for row in rows)
                        or bool(failures))
        result = {
            "schema": SCHEMA,
            "verdict": REVIEW if needs_choice else PROPOSED,
            "state": PROPOSED,
            "reason_code": (
                "REVIEW_BOUND_STRUCTURE_ALTERNATIVES" if needs_choice
                else "PROPOSED_BOUND_STRUCTURE_COMPOSED"
            ),
            "why": (
                "candidate-specific structure alternatives require human review"
                if needs_choice else
                "one candidate-specific structure graph was composed deterministically"
            ),
            "source_candidate_count": len(raw_candidates),
            "successful_source_candidate_count": len(rows),
            "failed_source_candidate_count": len(failures),
            "candidate_count": len(alternatives),
            "candidates": alternatives,
            "source_results": rows,
            "source_candidate_failures": failures,
            "human_choice": {
                "required": needs_choice,
                "candidate_ids": [row["candidate_id"] for row in alternatives],
                "selected_candidate_id": None,
            },
            "authority": {
                "rear": PROPOSED,
                "material": PROPOSED,
                "hidden_parts": PROPOSED,
                "attachments": PROPOSED,
                "layer_order": PROPOSED,
            },
            "claims": {
                "vision_or_ml_executed_here": False,
                "garment_class_enum_added": False,
                "garment_name_classification_used": False,
                "candidate_auto_selected": False,
                "rear_observed_from_front": False,
                "material_observed_from_front": False,
                "attachment_observed_from_front": False,
                "all_outputs_source_bound": True,
            },
            "manufacturing_ready": False,
            "manufacturing_certified": False,
            "provenance": {
                "method": (
                    "deterministic front candidate part translation followed by "
                    "layered primitive composition"
                ),
                "structure_schema": "garment.structure.v1",
            },
        }
        result["digest"] = stable_digest(result)
        return result
    except _Refusal as exc:
        return _unknown(original, exc.code, exc.why, **exc.detail)
    except (TypeError, ValueError, OverflowError) as exc:
        return _unknown(original, "UNKNOWN_FRONT_LAYERED_MALFORMED", str(exc))


compose_front_layered = compose
generate = compose
