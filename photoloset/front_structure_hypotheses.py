# -*- coding: utf-8 -*-
"""Deterministic front-view garment structure hypotheses.

This module consumes already interpreted, typed cues.  It does not inspect
pixels and it never promotes an unobserved back, depth, construction detail or
the semantic meaning of an internal front line to observation.  Its output is
deliberately bounded: two candidates for a simple front and three when
separation, layering, ambiguity, or decorative geometry needs an additional
alternative.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .garment_structure import (
    ANSWER,
    BoundaryPort,
    OperationKind,
    PortRef,
    PrimitiveKind,
    PrimitiveNode,
    StructureGraph,
    StructureOperation,
    validate_structure,
)


class CueState(str, Enum):
    """Evidence state accepted at the image-interpretation boundary."""

    OBSERVED = "OBSERVED"
    PROPOSED = "PROPOSED"


@dataclass(frozen=True)
class TypedCue:
    """One explicit image interpretation with its falsification boundary."""

    value: Any
    state: CueState
    basis: str
    breaks_when: str

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "state", CueState(self.state))
        except ValueError as exc:
            raise ValueError("cue state must be OBSERVED or PROPOSED") from exc
        if not isinstance(self.basis, str) or not self.basis.strip():
            raise ValueError("every cue needs a non-empty basis")
        if not isinstance(self.breaks_when, str) or not self.breaks_when.strip():
            raise ValueError("every cue needs a non-empty breaks_when")

    def as_dict(self) -> Dict[str, Any]:
        value = list(self.value) if isinstance(self.value, tuple) else self.value
        return {
            "value": value,
            "state": self.state.value,
            "basis": self.basis,
            "breaks_when": self.breaks_when,
        }


_COMPOSITIONS = {"one_piece", "separates", "ambiguous"}
_SILHOUETTES = {
    "close", "straight", "flared", "split_lower", "anime_exaggerated",
}
_LOWER_SHAPES = {"none", "tube", "flare", "split", "ambiguous"}
_SLEEVE_SHAPES = {"none", "short", "long", "bell", "puff", "detached",
                  "ambiguous"}
_DETAILS = {
    "overlay", "cape", "ruffle", "peplum", "tail_panel", "asymmetry",
    "decorative_ambiguous",
}
_MEASUREMENTS = {
    "upper_height_cm", "body_circumference_cm", "waist_circumference_cm",
    "lower_length_cm", "hem_circumference_cm", "sleeve_length_cm",
    "upper_arm_circumference_cm", "cuff_circumference_cm",
}


@dataclass(frozen=True)
class FrontStructureCues:
    """Typed cues from one front view; raw contours and pixels are excluded."""

    source_id: str
    composition: TypedCue
    silhouette: TypedCue
    lower_shape: TypedCue
    sleeve_shape: TypedCue
    layer_count: TypedCue
    details: TypedCue
    measurements_cm: Mapping[str, TypedCue] = field(default_factory=dict)
    front_only: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be a non-empty stable identifier")
        if self.front_only is not True:
            raise ValueError("this module accepts front-only cue sets")
        cue_fields = (
            self.composition, self.silhouette, self.lower_shape,
            self.sleeve_shape, self.layer_count, self.details,
        )
        if any(not isinstance(cue, TypedCue) for cue in cue_fields):
            raise TypeError("all image cues must be TypedCue values")
        _require_choice("composition", self.composition.value, _COMPOSITIONS)
        _require_choice("silhouette", self.silhouette.value, _SILHOUETTES)
        _require_choice("lower_shape", self.lower_shape.value, _LOWER_SHAPES)
        _require_choice("sleeve_shape", self.sleeve_shape.value,
                        _SLEEVE_SHAPES)
        count = self.layer_count.value
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 4:
            raise ValueError("layer_count must be an integer from 1 through 4")
        details = self.details.value
        if (not isinstance(details, Sequence)
                or isinstance(details, (str, bytes))):
            raise TypeError("details must be a sequence of bounded detail names")
        unknown_details = set(details) - _DETAILS
        if unknown_details:
            raise ValueError("unknown details: " + ", ".join(sorted(unknown_details)))
        for name, cue in self.measurements_cm.items():
            if name not in _MEASUREMENTS:
                raise ValueError(f"unknown measurement: {name}")
            if not isinstance(cue, TypedCue):
                raise TypeError("every measurement must be a TypedCue")
            value = cue.value
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or float(value) <= 0.0):
                raise ValueError(f"{name} must be a positive number")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "front_only": True,
            "composition": self.composition.as_dict(),
            "silhouette": self.silhouette.as_dict(),
            "lower_shape": self.lower_shape.as_dict(),
            "sleeve_shape": self.sleeve_shape.as_dict(),
            "layer_count": self.layer_count.as_dict(),
            "details": self.details.as_dict(),
            "measurements_cm": {
                name: self.measurements_cm[name].as_dict()
                for name in sorted(self.measurements_cm)
            },
        }


def _require_choice(name: str, value: Any, choices: set[str]) -> None:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{name} must be one of {sorted(choices)}")


_DEFAULT_MEASUREMENTS = {
    "upper_height_cm": 42.0,
    "body_circumference_cm": 92.0,
    "waist_circumference_cm": 74.0,
    "lower_length_cm": 62.0,
    "hem_circumference_cm": 156.0,
    "sleeve_length_cm": 58.0,
    "upper_arm_circumference_cm": 34.0,
    "cuff_circumference_cm": 20.0,
}


def _dimensions(cues: FrontStructureCues) -> Tuple[Dict[str, float], Dict[str, Dict[str, Any]]]:
    values: Dict[str, float] = {}
    evidence: Dict[str, Dict[str, Any]] = {}
    for name, default in _DEFAULT_MEASUREMENTS.items():
        supplied = cues.measurements_cm.get(name)
        if supplied is None:
            values[name] = default
            evidence[name] = {
                "state": "PROPOSED",
                "basis": "bounded preview-mannequin default; not measured from the front image",
                "breaks_when": "a calibrated measurement or target wearer measurement is supplied",
            }
        else:
            values[name] = float(supplied.value)
            evidence[name] = supplied.as_dict()
    return values, evidence


def _back_alternatives(count: int) -> Tuple[Dict[str, Any], ...]:
    rows = (
        {
            "alternative_id": "center_back_opening",
            "state": "PROPOSED",
            "value": {"back_surface": "continuous_except_opening",
                      "closure": "center_back_opening"},
            "basis": "the back is absent; a centre opening is a construction-feasible hypothesis",
            "breaks_when": "a rear or side view shows no centre opening or shows a different closure",
        },
        {
            "alternative_id": "side_opening_closed_back",
            "state": "PROPOSED",
            "value": {"back_surface": "closed", "closure": "side_opening"},
            "basis": "the front does not locate the closure; a closed back with side access preserves the front",
            "breaks_when": "a rear/side view or dressability test identifies another opening topology",
        },
        {
            "alternative_id": "closed_back_stretch",
            "state": "PROPOSED",
            "value": {"back_surface": "closed", "closure": "pull_on_stretch"},
            "basis": "a closure-free back is geometrically possible only as a stretch-dependent alternative",
            "breaks_when": "material stretch or neck/hip clearance is insufficient for pull-on dressing",
        },
    )
    return (rows[0], rows[2]) if count == 2 else rows


def _candidate_count(cues: FrontStructureCues) -> int:
    details = set(cues.details.value)
    complex_front = (
        cues.composition.value in {"separates", "ambiguous"}
        or cues.lower_shape.value == "ambiguous"
        or cues.silhouette.value in {"split_lower", "anime_exaggerated"}
        or cues.layer_count.value > 1
        or bool(details)
    )
    return 3 if complex_front else 2


def _resolved_composition(cues: FrontStructureCues, variant: int) -> str:
    if cues.composition.value == "ambiguous":
        return "separates" if variant == 1 else "one_piece"
    return str(cues.composition.value)


def _resolved_lower(cues: FrontStructureCues, variant: int) -> str:
    if cues.lower_shape.value == "ambiguous":
        return ("flare", "split", "tube")[variant]
    if cues.silhouette.value == "split_lower":
        return "split"
    return str(cues.lower_shape.value)


def _resolved_sleeve(cues: FrontStructureCues, variant: int) -> str:
    if cues.sleeve_shape.value == "ambiguous":
        return ("none", "long", "bell")[variant]
    return str(cues.sleeve_shape.value)


def _resolved_details(cues: FrontStructureCues, variant: int) -> set[str]:
    details = set(cues.details.value)
    if "decorative_ambiguous" not in details:
        return details
    details.remove("decorative_ambiguous")
    if variant == 1:
        details.add("overlay")
    elif variant == 2:
        details.update(("overlay", "ruffle"))
    return details


def _graph_for(cues: FrontStructureCues, variant: int,
               back: Mapping[str, Any]) -> StructureGraph:
    dims, dimension_evidence = _dimensions(cues)
    details = _resolved_details(cues, variant)
    composition = _resolved_composition(cues, variant)
    lower_shape = _resolved_lower(cues, variant)
    overlay_count = max(
        cues.layer_count.value - 1,
        1 if details & {"overlay", "cape", "peplum", "tail_panel", "asymmetry"} else 0,
    )
    overlay_count = min(3, overlay_count)

    upper_ports: List[BoundaryPort] = []
    if lower_shape in {"tube", "flare"} and composition == "one_piece":
        upper_ports.append(BoundaryPort(
            "waist", dims["waist_circumference_cm"], "waist", role="loop"))
    for layer in range(overlay_count):
        upper_ports.append(BoundaryPort(
            f"layer-anchor-{layer + 1}", 1.0, "layer-anchor", role="point"))
    # A lower garment, when present, owns the visible outer hem.  Bind a
    # ruffle candidate there instead of to the primitive BODY_SHELL: a gather
    # on the body circumference would block the bodice/sleeve expansion and
    # would describe a waist flounce rather than the observed outer contour.
    ruffle_on_lower = "ruffle" in details and lower_shape in {"tube", "flare"}
    if "ruffle" in details and not ruffle_on_lower:
        upper_ports.append(BoundaryPort(
            "ruffle-target", dims["body_circumference_cm"], "ruffle-line"))

    nodes: List[PrimitiveNode] = [PrimitiveNode(
        "upper-shell", PrimitiveKind.BODY_SHELL,
        {"height_cm": dims["upper_height_cm"],
         "circumference_cm": dims["body_circumference_cm"],
         # The lower boundary is the waist join, not the maximum torso
         # circumference.  Keeping both dimensions prevents a visually valid
         # bodice from compiling to an 18cm seam mismatch by construction.
         "bottom_circumference_cm": dims["waist_circumference_cm"]},
        tuple(upper_ports), 0,
        {
            "garment_unit": "upper" if composition == "separates" else "base",
            "front_silhouette": cues.silhouette.value,
            "front_silhouette_state": cues.silhouette.state.value,
            "dimension_evidence": dimension_evidence,
            "back_claim_state": "PROPOSED",
            "back_alternative_id": back["alternative_id"],
        },
    )]
    operations: List[StructureOperation] = []

    if lower_shape == "flare":
        hem = dims["hem_circumference_cm"]
        if cues.silhouette.value == "anime_exaggerated":
            hem *= (1.3, 1.55, 1.8)[variant]
        waist_port = BoundaryPort(
            "waist", dims["waist_circumference_cm"], "waist", role="loop")
        lower_ports = [waist_port]
        if ruffle_on_lower:
            lower_ports.append(BoundaryPort(
                "ruffle-target", hem, "ruffle-line", role="loop"))
        nodes.append(PrimitiveNode(
            "lower-flare", PrimitiveKind.FLARE,
            {"height_cm": dims["lower_length_cm"],
             "top_circumference_cm": dims["waist_circumference_cm"],
             "bottom_circumference_cm": hem},
            tuple(lower_ports), 0,
            {"garment_unit": "lower" if composition == "separates" else "base",
             "geometry_state": "PROPOSED"},
        ))
    elif lower_shape == "tube":
        waist_port = BoundaryPort(
            "waist", dims["waist_circumference_cm"], "waist", role="loop")
        lower_ports = [waist_port]
        if ruffle_on_lower:
            lower_ports.append(BoundaryPort(
                "ruffle-target", dims["waist_circumference_cm"],
                "ruffle-line", role="loop"))
        nodes.append(PrimitiveNode(
            "lower-tube", PrimitiveKind.TUBE,
            {"length_cm": dims["lower_length_cm"],
             "circumference_cm": dims["waist_circumference_cm"]},
            tuple(lower_ports), 0,
            {"garment_unit": "lower" if composition == "separates" else "base",
             "geometry_state": "PROPOSED"},
        ))
    elif lower_shape == "split":
        leg_circumference = dims["waist_circumference_cm"] * 0.56
        gusset_length = 18.0
        for side in ("left", "right"):
            leg_id = f"lower-{side}"
            nodes.append(PrimitiveNode(
                leg_id, PrimitiveKind.TUBE,
                {"length_cm": dims["lower_length_cm"],
                 "circumference_cm": leg_circumference},
                (BoundaryPort(
                    f"crotch-to-crotch-gusset-{side}", gusset_length,
                    "crotch", role="edge"),), 0,
                {"garment_unit": "lower", "side": side,
                 "shape": "trouser_leg", "detail_role": "trouser_leg",
                 "quantity": 1, "attached_to": [],
                 "geometry_state": "PROPOSED",
                 "pair_topology": "two-leg lower hypothesis"},
            ))
        nodes.append(PrimitiveNode(
            "crotch-gusset", PrimitiveKind.GUSSET,
            {"length_cm": gusset_length, "width_cm": 8.0},
            (BoundaryPort("crotch-to-lower-left", gusset_length,
                          "crotch", role="edge"),
             BoundaryPort("crotch-to-lower-right", gusset_length,
                          "crotch", role="edge")), 0,
            {"garment_unit": "lower", "side": "center",
             "shape": "trouser_gusset", "detail_role": "trouser_gusset",
             "quantity": 1, "attached_to": ["lower-left", "lower-right"],
             "geometry_state": "PROPOSED",
             "basis": "split lower requires a joinable crotch region",
             "breaks_when": "the front shape is a slit skirt rather than two leg volumes"},
        ))
        for side in ("left", "right"):
            operations.append(StructureOperation(
                f"join-crotch-lower-{side}", OperationKind.JOIN,
                PortRef("crotch-gusset", f"crotch-to-lower-{side}"),
                PortRef(f"lower-{side}",
                        f"crotch-to-crotch-gusset-{side}"),
                {
                    "state": "PROPOSED",
                    "basis": "two-leg lower hypothesis requires an explicit crotch join",
                    "breaks_when": "the front split is a skirt slit rather than two leg volumes",
                }))

    if composition == "one_piece" and lower_shape in {"tube", "flare"}:
        lower_id = "lower-flare" if lower_shape == "flare" else "lower-tube"
        operations.append(StructureOperation(
            "join-upper-lower", OperationKind.JOIN,
            PortRef("upper-shell", "waist"), PortRef(lower_id, "waist")))

    sleeve_shape = _resolved_sleeve(cues, variant)
    if sleeve_shape != "none":
        sleeve_length = dims["sleeve_length_cm"]
        if sleeve_shape == "short":
            sleeve_length *= 0.38
        cuff = dims["cuff_circumference_cm"]
        if sleeve_shape in {"bell", "puff"}:
            cuff *= 1.8 if sleeve_shape == "bell" else 1.35
        nodes.append(PrimitiveNode(
            "sleeve-pair", PrimitiveKind.SLEEVE,
            {"length_cm": sleeve_length,
             "upper_circumference_cm": dims["upper_arm_circumference_cm"],
             "cuff_circumference_cm": cuff}, (),
            1 if sleeve_shape == "detached" else 0,
            {"garment_unit": ("upper" if composition == "separates" else "base"),
             "bilateral": True, "shape": sleeve_shape,
             "geometry_state": "PROPOSED"},
        ))

    for layer in range(overlay_count):
        layer_number = layer + 1
        node_id = f"overlay-{layer_number}"
        nodes.append(PrimitiveNode(
            node_id, PrimitiveKind.OVERLAY,
            {"height_cm": dims["upper_height_cm"] * (0.75 + 0.12 * layer),
             "width_cm": dims["body_circumference_cm"] * (0.52 + 0.05 * variant)},
            (BoundaryPort("anchor", 1.0, "layer-anchor", role="point",
                          layer=layer_number),),
            layer_number,
            {"detail_roles": sorted(details & {
                "overlay", "cape", "peplum", "tail_panel", "asymmetry"}),
             "garment_unit": ("upper" if composition == "separates" else "base"),
             "geometry_state": "PROPOSED"},
        ))
        operations.append(StructureOperation(
            f"layer-{layer_number}", OperationKind.LAYER,
            PortRef(node_id, "anchor"),
            PortRef("upper-shell", f"layer-anchor-{layer_number}")))

    if "ruffle" in details:
        if lower_shape == "flare":
            target = next(
                float(node.dimensions["bottom_circumference_cm"])
                for node in nodes if node.node_id == "lower-flare")
            target_node = "lower-flare"
        elif lower_shape == "tube":
            target = dims["waist_circumference_cm"]
            target_node = "lower-tube"
        else:
            target = dims["body_circumference_cm"]
            target_node = "upper-shell"
        ratio = (1.5, 1.75, 2.0)[variant]
        target_unit = "lower" if (
            composition == "separates" and target_node != "upper-shell"
        ) else ("upper" if composition == "separates" else "base")
        nodes.append(PrimitiveNode(
            "ruffle-band", PrimitiveKind.BAND,
            {"length_cm": target * ratio, "width_cm": 12.0},
            (BoundaryPort("gather-edge", target * ratio, "ruffle-line"),),
            max(1, overlay_count),
            {"garment_unit": target_unit,
             "geometry_state": "PROPOSED", "gather_ratio": ratio},
        ))
        operations.append(StructureOperation(
            "gather-ruffle", OperationKind.GATHER,
            PortRef("ruffle-band", "gather-edge"),
            PortRef(target_node, "ruffle-target"),
            {"ratio": ratio}))

    closure = back["value"]["closure"]
    if closure != "pull_on_stretch":
        nodes.append(PrimitiveNode(
            "back-opening", PrimitiveKind.OPENING,
            {"length_cm": dims["upper_height_cm"] * 0.72}, (), 0,
            {"garment_unit": ("upper" if composition == "separates" else "base"),
             "placement": closure, "state": "PROPOSED",
             "basis": back["basis"], "breaks_when": back["breaks_when"]},
        ))

    return StructureGraph(tuple(nodes), tuple(operations))


def _candidate_id(cues: FrontStructureCues, variant: int,
                  back_id: str) -> str:
    payload = {
        "cues": cues.as_dict(), "variant": variant, "back": back_id,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return "front-" + hashlib.sha256(encoded).hexdigest()[:16]


def hypothesize_front_structure(cues: FrontStructureCues) -> List[Dict[str, Any]]:
    """Return two or three deterministic, validation-ready structure proposals."""
    if not isinstance(cues, FrontStructureCues):
        raise TypeError("cues must be FrontStructureCues, not raw CV data")
    count = _candidate_count(cues)
    results: List[Dict[str, Any]] = []
    for variant, back in enumerate(_back_alternatives(count)):
        graph = _graph_for(cues, variant, back)
        checked = validate_structure(graph)
        if checked.get("verdict") != ANSWER:
            raise RuntimeError(f"generated invalid structure: {checked}")
        candidate = graph.as_dict()
        candidate.update({
            "candidate_id": _candidate_id(
                cues, variant, str(back["alternative_id"])),
            "state": "PROPOSED",
            "structure_digest": graph.digest,
            "front_cues": cues.as_dict(),
            "back_alternative": dict(back),
            "basis": [
                "typed front-view cues preserved with their original evidence state",
                "geometry composed from garment.structure.v1 primitives without corpus retrieval",
                "back alternative introduced only as a falsifiable proposal",
                "front internal-line semantics remain typed proposals even when their geometry is observed",
            ],
            "breaks_when": [
                "a rear or side observation contradicts the proposed topology",
                "target measurements make its ports or dressing clearance infeasible",
                "a sewing or simulation check rejects the proposed construction",
            ],
            "unobserved": {
                "back": "PROPOSED",
                "depth": "PROPOSED",
                "internal_construction": "PROPOSED",
            },
            "provenance": {
                "method": "deterministic front-cue geometry composition",
                "source_id": cues.source_id,
                "corpus_used": False,
                "raw_cv_consumed": False,
            },
        })
        results.append(candidate)
    return results


generate = hypothesize_front_structure
