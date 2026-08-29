# -*- coding: utf-8 -*-
"""Deterministic, model-free natural-language IR for garment commands.

The grammar is intentionally small.  A sentence outside it is refused rather
than guessed.  Structured envelopes pass through the same closed validators.
"""
from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple, Union


SCHEMA = "garment.command.v1"


class Intent(str, Enum):
    NAVIGATE = "NAVIGATE"
    INSPECT = "INSPECT"
    ADJUST_PATTERN_SPAN = "ADJUST_PATTERN_SPAN"
    ADD_EASE = "ADD_EASE"
    CHANGE_LENGTH = "CHANGE_LENGTH"
    CHANGE_MATERIAL = "CHANGE_MATERIAL"
    SET_REQUIREMENTS = "SET_REQUIREMENTS"
    GENERATE_FROM_IMAGE = "GENERATE_FROM_IMAGE"
    PROPOSE_STRUCTURE = "PROPOSE_STRUCTURE"
    RUN_SIMULATION = "RUN_SIMULATION"
    COMPARE_SIMULATIONS = "COMPARE_SIMULATIONS"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    UNDO = "UNDO"


class Provenance(str, Enum):
    DETERMINISTIC_PARSE = "DETERMINISTIC_PARSE"
    MODEL_PROPOSAL = "MODEL_PROPOSAL"
    HUMAN_INPUT = "HUMAN_INPUT"


class Unit(str, Enum):
    CM = "cm"
    MM = "mm"
    M = "m"


class RefusalCode(str, Enum):
    UNKNOWN_WORDS = "UNKNOWN_GARMENT_COMMAND_WORDS"
    MISSING_UNIT = "UNKNOWN_DIMENSION_UNIT_REQUIRED"
    AMBIGUOUS_TARGET = "UNKNOWN_AMBIGUOUS_GARMENT_TARGET"
    UNSUPPORTED_OPERATION = "UNKNOWN_UNSUPPORTED_GARMENT_OPERATION"
    INVALID_ENVELOPE = "UNKNOWN_INVALID_GARMENT_COMMAND"
    INVALID_PROVENANCE = "UNKNOWN_INVALID_COMMAND_PROVENANCE"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return copy.deepcopy(value)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return copy.deepcopy(value)


@dataclass(frozen=True)
class GarmentCommand:
    command_id: str
    intent: Intent
    target: Mapping[str, Any]
    operation: Mapping[str, Any]
    job_id: Optional[str] = None
    commit: bool = False
    provenance: Provenance = Provenance.DETERMINISTIC_PARSE
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise ValueError("schema must be garment.command.v1")
        if not isinstance(self.command_id, str) or not self.command_id.strip():
            raise ValueError("command_id must be non-empty")
        if self.job_id is not None and (not isinstance(self.job_id, str)
                                        or not self.job_id.strip()):
            raise ValueError("job_id must be non-empty when supplied")
        if not isinstance(self.commit, bool):
            raise ValueError("commit must be boolean")
        object.__setattr__(self, "intent", Intent(self.intent))
        object.__setattr__(self, "provenance", Provenance(self.provenance))
        object.__setattr__(self, "target", _freeze(self.target))
        object.__setattr__(self, "operation", _freeze(self.operation))

    def as_dict(self) -> Dict[str, Any]:
        out = {"schema": self.schema, "command_id": self.command_id,
               "intent": self.intent.value, "target": _thaw(self.target),
               "operation": _thaw(self.operation), "commit": self.commit,
               "provenance": self.provenance.value}
        if self.job_id is not None:
            out["job_id"] = self.job_id
        return out


@dataclass(frozen=True)
class CommandRefusal:
    verdict: RefusalCode
    reason: str
    command_id: str = ""
    details: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", RefusalCode(self.verdict))
        object.__setattr__(self, "details", _freeze(self.details))

    @property
    def accepted(self) -> bool:
        return False

    def as_dict(self) -> Dict[str, Any]:
        return {"schema": "garment.refusal.v1", "verdict": self.verdict.value,
                "reason": self.reason, "command_id": self.command_id,
                "details": _thaw(self.details)}


ParseResult = Union[GarmentCommand, CommandRefusal]


_SPAN = re.compile(r"(?P<first>\d+)\s*(?:番)?\s*(?:から|[-–—~〜～]|to)\s*"
                   r"(?P<last>\d+)\s*(?:番)?", re.IGNORECASE)
_DIMENSION = re.compile(r"(?P<value>[+-]?\d+(?:\.\d+)?)\s*"
                        r"(?P<unit>mm|cm|m|ミリ(?:メートル)?|センチ(?:メートル)?|メートル)",
                        re.IGNORECASE)
_NUMBER_WITHOUT_UNIT = re.compile(r"[+-]?\d+(?:\.\d+)?\s*(?:広|狭|長|短|ゆとり|ease|widen|length)",
                                  re.IGNORECASE)


def _unit(raw: str) -> Unit:
    value = raw.lower()
    if value.startswith("ミリ"):
        return Unit.MM
    if value.startswith("センチ"):
        return Unit.CM
    if value.startswith("メートル"):
        return Unit.M
    return Unit(value)


def _command(command_id: str, intent: Intent, target: Mapping[str, Any],
             operation: Mapping[str, Any], job_id: Optional[str],
             provenance: Provenance) -> GarmentCommand:
    return GarmentCommand(command_id, intent, target, operation, job_id,
                          False, provenance)


def parse_garment_command(text: str, command_id: str, *,
                          job_id: Optional[str] = None,
                          provenance: Provenance = Provenance.DETERMINISTIC_PARSE
                          ) -> ParseResult:
    """Parse only closed, auditable command forms; never call an LLM."""
    try:
        source = Provenance(provenance)
    except (ValueError, TypeError):
        return CommandRefusal(RefusalCode.INVALID_PROVENANCE,
                              "provenance is outside the closed vocabulary",
                              command_id)
    if not isinstance(text, str) or not text.strip():
        return CommandRefusal(RefusalCode.UNKNOWN_WORDS,
                              "no supported garment command was supplied",
                              command_id)
    s = text.strip()
    lower = s.lower()
    span = _SPAN.search(s)
    dimensional = any(word in lower for word in
                      ("広げ", "狭め", "ゆとり", "長く", "短く", "widen",
                       "narrow", "ease", "lengthen", "shorten"))
    measure = _DIMENSION.search(s)

    if dimensional and measure is None:
        return CommandRefusal(RefusalCode.MISSING_UNIT,
                              "a dimensional edit requires mm, cm, or m",
                              command_id)
    if span and dimensional:
        first, last = int(span.group("first")), int(span.group("last"))
        if first > last:
            return CommandRefusal(RefusalCode.AMBIGUOUS_TARGET,
                                  "pattern span must be ordered first to last",
                                  command_id, {"first": first, "last": last})
        value = float(measure.group("value"))
        unit = _unit(measure.group("unit"))
        if value < 0:
            return CommandRefusal(RefusalCode.UNSUPPORTED_OPERATION,
                                  "use widen/narrow or lengthen/shorten, not a signed value",
                                  command_id)
        if any(w in lower for w in ("狭め", "短く", "narrow", "shorten")):
            value = -value
        if any(w in lower for w in ("長く", "短く", "lengthen", "shorten")):
            kind = "CHANGE_LENGTH"
        else:
            kind = "ADD_EASE"
        return _command(command_id, Intent.ADJUST_PATTERN_SPAN,
                        {"kind": "PATTERN_SPAN", "first": first, "last": last},
                        {"kind": kind, "value": value, "unit": unit.value},
                        job_id, source)
    if dimensional and not span:
        return CommandRefusal(RefusalCode.AMBIGUOUS_TARGET,
                              "dimensional edit requires an explicit pattern span",
                              command_id)

    simple: Tuple[Tuple[Tuple[str, ...], Intent, str], ...] = (
        (("シミュレーション比較", "compare simulations"),
         Intent.COMPARE_SIMULATIONS, "SIMULATIONS"),
        (("シミュレーション", "simulate", "run simulation"),
         Intent.RUN_SIMULATION, "CURRENT_GARMENT"),
        (("画像から服", "写真から服", "generate from image"),
         Intent.GENERATE_FROM_IMAGE, "SUPPLIED_IMAGE"),
        (("構成案", "構造案", "propose structure"),
         Intent.PROPOSE_STRUCTURE, "CURRENT_GARMENT"),
        (("承認", "approve"), Intent.APPROVE, "CURRENT_PREVIEW"),
        (("却下", "reject"), Intent.REJECT, "CURRENT_PREVIEW"),
        (("元に戻", "取り消", "undo"), Intent.UNDO, "CURRENT_JOB"),
    )
    matched = [(intent, target) for words, intent, target in simple
               if any(word in lower for word in words)]
    if len(matched) > 1:
        return CommandRefusal(RefusalCode.AMBIGUOUS_TARGET,
                              "more than one command intent was present",
                              command_id)
    if matched:
        intent, target = matched[0]
        return _command(command_id, intent, {"kind": target},
                        {"kind": intent.value}, job_id, source)
    if span:
        return _command(command_id, Intent.INSPECT,
                        {"kind": "PATTERN_SPAN",
                         "first": int(span.group("first")),
                         "last": int(span.group("last"))},
                        {"kind": "INSPECT"}, job_id, source)
    return CommandRefusal(RefusalCode.UNKNOWN_WORDS,
                          "sentence is outside the deterministic garment grammar",
                          command_id, {"input": s})


def validate_command_envelope(value: Mapping[str, Any]) -> ParseResult:
    """Validate a JSON-like command without repairing or defaulting fields."""
    command_id = str(value.get("command_id", "")) if isinstance(value, Mapping) else ""
    if not isinstance(value, Mapping):
        return CommandRefusal(RefusalCode.INVALID_ENVELOPE,
                              "command envelope must be an object")
    required = {"schema", "command_id", "intent", "target", "operation",
                "commit", "provenance"}
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - {"job_id"})
    if missing or unknown:
        return CommandRefusal(RefusalCode.INVALID_ENVELOPE,
                              "command fields must exactly match the v1 contract",
                              command_id, {"missing": missing, "unknown": unknown})
    try:
        command = GarmentCommand(
            command_id=value["command_id"], intent=Intent(value["intent"]),
            target=value["target"], operation=value["operation"],
            job_id=value.get("job_id"), commit=value["commit"],
            provenance=Provenance(value["provenance"]), schema=value["schema"])
    except (ValueError, TypeError, KeyError) as exc:
        return CommandRefusal(RefusalCode.INVALID_ENVELOPE, str(exc), command_id)
    if not isinstance(command.target, Mapping) or not isinstance(command.operation, Mapping):
        return CommandRefusal(RefusalCode.INVALID_ENVELOPE,
                              "target and operation must be objects", command_id)
    op = command.operation
    if "value" in op:
        if op.get("unit") not in {u.value for u in Unit}:
            return CommandRefusal(RefusalCode.MISSING_UNIT,
                                  "dimensional value requires mm, cm, or m",
                                  command_id)
        if isinstance(op.get("value"), bool) or not isinstance(op.get("value"), (int, float)):
            return CommandRefusal(RefusalCode.INVALID_ENVELOPE,
                                  "operation.value must be numeric", command_id)
    if command.intent == Intent.ADJUST_PATTERN_SPAN:
        first, last = command.target.get("first"), command.target.get("last")
        if (isinstance(first, bool) or isinstance(last, bool)
                or not isinstance(first, int) or not isinstance(last, int)
                or first > last):
            return CommandRefusal(RefusalCode.AMBIGUOUS_TARGET,
                                  "pattern span requires ordered integer first and last",
                                  command_id)
        if "value" not in op or "unit" not in op:
            return CommandRefusal(RefusalCode.MISSING_UNIT,
                                  "pattern adjustment requires value and explicit unit",
                                  command_id)
    if command.intent == Intent.SET_REQUIREMENTS:
        requirements = op.get("requirements")
        if (not isinstance(requirements, (list, tuple))
                or not 1 <= len(requirements) <= 24):
            return CommandRefusal(RefusalCode.INVALID_ENVELOPE,
                                  "SET_REQUIREMENTS needs 1 to 24 typed requirements",
                                  command_id)
        allowed = {"STANDARD_SIZE", "BODY_MEASUREMENT",
                   "GARMENT_MEASUREMENT", "EASE", "LENGTH", "FIT",
                   "MATERIAL", "STRUCTURE", "DETAIL", "CONSTRUCTION",
                   "COMFORT"}
        fields = {"kind", "target", "text", "value", "unit", "note"}
        for item in requirements:
            if not isinstance(item, Mapping) or set(item) - fields:
                return CommandRefusal(RefusalCode.INVALID_ENVELOPE,
                                      "requirement fields are outside the typed contract",
                                      command_id)
            if item.get("kind") not in allowed:
                return CommandRefusal(RefusalCode.UNSUPPORTED_OPERATION,
                                      "unsupported requirement kind",
                                      command_id, {"kind": item.get("kind")})
            target = item.get("target")
            if not isinstance(target, str) or not target.strip() or len(target) > 80:
                return CommandRefusal(RefusalCode.AMBIGUOUS_TARGET,
                                      "requirement target must be a short non-empty string",
                                      command_id)
            value, text = item.get("value"), item.get("text")
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return CommandRefusal(RefusalCode.INVALID_ENVELOPE,
                                          "requirement value must be numeric",
                                          command_id)
                if item.get("unit") not in {u.value for u in Unit}:
                    return CommandRefusal(RefusalCode.MISSING_UNIT,
                                          "numeric requirement needs mm, cm, or m",
                                          command_id)
            elif not isinstance(text, str) or not text.strip():
                return CommandRefusal(RefusalCode.INVALID_ENVELOPE,
                                      "requirement needs text or a dimensional value",
                                      command_id)
    return command


# Short aliases for callers that already know they are in the garment module.
parse_command = parse_garment_command
validate_command = validate_command_envelope


def parse(text: str, *, command_id: Optional[str] = None,
          provenance: str = "HUMAN_INPUT") -> Dict[str, Any]:
    """Stable JSON API for deterministic natural-language parsing.

    When an integration does not supply an id, the id is derived from the
    exact input and provenance.  Repeating the same parse therefore produces
    byte-for-byte equivalent JSON rather than a random identifier.
    """
    if command_id is None:
        material = json_bytes = (str(text) + "\0" + str(provenance)).encode("utf-8")
        del json_bytes  # keep the digest input deliberately simple and visible
        command_id = "cmd-" + hashlib.sha256(material).hexdigest()[:20]
    result = parse_garment_command(text, command_id,
                                   provenance=provenance)
    return result.as_dict()


def validate(command: Mapping[str, Any]) -> Dict[str, Any]:
    """Stable JSON API for a proposed command envelope."""
    return validate_command_envelope(command).as_dict()
