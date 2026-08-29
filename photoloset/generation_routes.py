# -*- coding: utf-8 -*-
"""Auditable routing for garment generation with an honest model-free path.

The planner deliberately separates *evidence* from *proposals*.  A language
model may suggest alternatives, but its output is never copied into evidence
or into a deterministic stage result.  Promotion requires a later, explicit
human or deterministic callback outside the model call.

Callbacks receive a deep copy of the current context and return a mapping.
This makes the dependency boundary small enough to record and test.  The
module uses only the Python standard library and does not import an LLM SDK.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Mapping, Optional, Tuple


ANSWER = "ANSWER"
CONVERGED = "CONVERGED"
CONTINUE = "CONTINUE"
CONTESTED = "CONTESTED"
ESCALATE_HUMAN = "ESCALATE_HUMAN"


class Dependency(str, Enum):
    """The strongest dependency a stage is allowed to have."""

    DETERMINISTIC = "deterministic"
    OPTIONAL_MODEL = "optional-model"
    REQUIRES_EXTERNAL_CORPUS = "requires-external-corpus"


class Stage(str, Enum):
    IMAGE_EVIDENCE = "image evidence"
    GEOMETRIC_CONSTRUCTION = "geometric construction"
    MATERIAL_SIMULATION = "material simulation"
    SEAM_KNOWLEDGE = "seam knowledge"
    HUMAN_REVIEW = "human review"
    AGENT_ITERATION = "agent iteration"


@dataclass(frozen=True)
class StageDefinition:
    stage: Stage
    dependency: Dependency
    required: bool
    purpose: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "dependency": self.dependency.value,
            "required": self.required,
            "purpose": self.purpose,
        }


# Human review is deterministic in the narrow sense used here: the planner
# records an explicit person's answer and never asks a model to impersonate it.
STAGE_DEFINITIONS: Tuple[StageDefinition, ...] = (
    StageDefinition(Stage.IMAGE_EVIDENCE, Dependency.DETERMINISTIC, True,
                    "record supplied pixels, views, measurements, and provenance"),
    StageDefinition(Stage.GEOMETRIC_CONSTRUCTION, Dependency.DETERMINISTIC, True,
                    "construct surfaces, panels, and constraints from evidence"),
    StageDefinition(Stage.MATERIAL_SIMULATION, Dependency.DETERMINISTIC, True,
                    "simulate stated material parameters and geometry"),
    StageDefinition(Stage.SEAM_KNOWLEDGE,
                    Dependency.REQUIRES_EXTERNAL_CORPUS, True,
                    "retrieve sewing precedents without treating retrieval as evidence"),
    StageDefinition(Stage.HUMAN_REVIEW, Dependency.DETERMINISTIC, True,
                    "record an explicit approval, rejection, or contest"),
    StageDefinition(Stage.AGENT_ITERATION, Dependency.OPTIONAL_MODEL, False,
                    "iterate deterministically; a model may only propose alternatives"),
)


Callback = Callable[[Dict[str, Any]], Mapping[str, Any]]
ModelProposer = Callable[[Stage, Dict[str, Any]], Any]


@dataclass(frozen=True)
class ConvergenceBudget:
    """Hard stops for the closed loop; zero/negative budgets are invalid."""

    max_iterations: int = 8
    stagnation_limit: int = 3
    max_model_proposals: int = 6

    def __post_init__(self) -> None:
        for name in ("max_iterations", "stagnation_limit",
                     "max_model_proposals"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    def as_dict(self) -> Dict[str, int]:
        return {
            "max_iterations": self.max_iterations,
            "stagnation_limit": self.stagnation_limit,
            "max_model_proposals": self.max_model_proposals,
        }


def _stage(value: Any) -> Stage:
    if isinstance(value, Stage):
        return value
    return Stage(str(value))


def _normalise_callbacks(
        callbacks: Optional[Mapping[Any, Callback]]) -> Dict[Stage, Callback]:
    out: Dict[Stage, Callback] = {}
    for key, callback in (callbacks or {}).items():
        stage = _stage(key)
        if not callable(callback):
            raise TypeError(f"callback for {stage.value!r} is not callable")
        out[stage] = callback
    return out


def _jsonable(value: Any) -> Any:
    """Stable, non-authoritative representation used only for fingerprints."""
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(
            value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return {"python_type": type(value).__name__, "repr": repr(value)}


def _fingerprint(value: Any) -> str:
    payload = json.dumps(_jsonable(value), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _proposal_safe(value: Any) -> Any:
    """Remove evidence vocabulary from model output without hiding its claim."""
    if isinstance(value, Mapping):
        safe: Dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if name == "evidence":
                name = "claimed_evidence"
            if name in ("kind", "state") and item == "OBSERVED":
                safe[name] = "PROPOSED"
            else:
                safe[name] = _proposal_safe(item)
        return safe
    if isinstance(value, (list, tuple)):
        return [_proposal_safe(item) for item in value]
    return copy.deepcopy(value)


def _callback_result(callback: Callback, context: Dict[str, Any]) -> Dict[str, Any]:
    result = callback(copy.deepcopy(context))
    if not isinstance(result, Mapping):
        raise TypeError("stage callback must return a mapping")
    return copy.deepcopy(dict(result))


class RoutePlanner:
    """Execute and compare deterministic and model-assisted generation routes."""

    def __init__(
        self,
        callbacks: Optional[Mapping[Any, Callback]] = None,
        *,
        corpus_callbacks: Optional[Mapping[Any, Callback]] = None,
        model_proposer: Optional[ModelProposer] = None,
        budget: Optional[ConvergenceBudget] = None,
    ) -> None:
        self.callbacks = _normalise_callbacks(callbacks)
        self.corpus_callbacks = _normalise_callbacks(corpus_callbacks)
        self.model_proposer = model_proposer
        if model_proposer is not None and not callable(model_proposer):
            raise TypeError("model_proposer is not callable")
        self.budget = budget or ConvergenceBudget()

    def _propose(self, stage: Stage, context: Dict[str, Any],
                 proposals: list[Dict[str, Any]]) -> Optional[str]:
        if self.model_proposer is None:
            return None
        if len(proposals) >= self.budget.max_model_proposals:
            return "model proposal budget exhausted"
        raw = self.model_proposer(stage, copy.deepcopy(context))
        proposals.append({
            "stage": stage.value,
            "kind": "PROPOSED",
            "source": "optional-model",
            "may_promote_evidence": False,
            "alternatives": _proposal_safe(raw),
        })
        return None

    def _iterate(self, callback: Optional[Callback], context: Dict[str, Any],
                 use_model: bool, trace: list[Dict[str, Any]],
                 proposals: list[Dict[str, Any]]) -> Tuple[str, str]:
        if callback is None:
            if use_model:
                exhausted = self._propose(Stage.AGENT_ITERATION, context,
                                          proposals)
                if exhausted:
                    return ESCALATE_HUMAN, exhausted
            trace.append({"stage": Stage.AGENT_ITERATION.value,
                          "status": "SKIPPED_OPTIONAL"})
            return CONVERGED, "no deterministic iteration callback was required"

        previous: Optional[str] = None
        repeated = 0
        for iteration in range(1, self.budget.max_iterations + 1):
            call_context = copy.deepcopy(context)
            call_context["iteration"] = iteration
            result = _callback_result(callback, call_context)
            context["artifacts"][Stage.AGENT_ITERATION.value] = result
            verdict = str(result.get("verdict", CONTINUE))
            state = result.get("state", {
                key: value for key, value in result.items()
                if key not in ("verdict", "why", "how_to_close")
            })
            fingerprint = _fingerprint(state)
            repeated = repeated + 1 if fingerprint == previous else 1
            previous = fingerprint
            trace.append({"stage": Stage.AGENT_ITERATION.value,
                          "status": "EXECUTED", "iteration": iteration,
                          "callback": "deterministic",
                          "result_verdict": verdict,
                          "state_fingerprint": fingerprint})

            if use_model:
                exhausted = self._propose(Stage.AGENT_ITERATION, context,
                                          proposals)
                if exhausted:
                    return ESCALATE_HUMAN, exhausted
            if verdict in (ANSWER, CONVERGED):
                return CONVERGED, "deterministic fixed point accepted"
            if verdict == CONTESTED:
                return CONTESTED, str(result.get("why") or
                                      "iteration produced competing claims")
            if verdict == ESCALATE_HUMAN:
                return ESCALATE_HUMAN, str(result.get("why") or
                                           "iteration requested human review")
            if repeated >= self.budget.stagnation_limit:
                return ESCALATE_HUMAN, (
                    "deterministic state repeated for "
                    f"{repeated} iterations; Vera closed the loop")

        return ESCALATE_HUMAN, (
            f"iteration budget {self.budget.max_iterations} exhausted; "
            "Vera closed the loop")

    def run(self, evidence: Optional[Mapping[str, Any]] = None, *,
            use_model: bool = False) -> Dict[str, Any]:
        """Run one route.  ``use_model`` adds proposals, never capabilities."""
        if evidence is not None and not isinstance(evidence, Mapping):
            raise TypeError("evidence must be a mapping")
        original_evidence = copy.deepcopy(dict(evidence or {}))
        context: Dict[str, Any] = {
            "evidence": copy.deepcopy(original_evidence),
            "artifacts": {},
            "proposals": [],
        }
        trace: list[Dict[str, Any]] = []
        blockers: list[Dict[str, str]] = []
        proposals: list[Dict[str, Any]] = context["proposals"]

        for definition in STAGE_DEFINITIONS:
            stage = definition.stage
            if stage == Stage.AGENT_ITERATION:
                continue
            callback = self.callbacks.get(stage)
            callback_source = "deterministic"
            if definition.dependency == Dependency.REQUIRES_EXTERNAL_CORPUS:
                callback = self.corpus_callbacks.get(stage)
                callback_source = "external-corpus"

            if callback is None:
                status = ("BLOCKED_EXTERNAL_CORPUS" if
                          definition.dependency ==
                          Dependency.REQUIRES_EXTERNAL_CORPUS else
                          "MISSING_DETERMINISTIC_CALLBACK")
                trace.append({"stage": stage.value, "status": status})
                if definition.required:
                    blockers.append({"stage": stage.value, "reason": status})
            else:
                result = _callback_result(callback, context)
                context["artifacts"][stage.value] = result
                trace.append({"stage": stage.value, "status": "EXECUTED",
                              "callback": callback_source,
                              "result_verdict": result.get("verdict")})
                verdict = result.get("verdict")
                if isinstance(verdict, str) and verdict.startswith("UNKNOWN_"):
                    blockers.append({"stage": stage.value, "reason": verdict})
                elif verdict == CONTESTED:
                    blockers.append({"stage": stage.value, "reason": CONTESTED})

            # A model is deliberately not called for deterministic stages.
            # It may suggest alternatives only at the explicit optional-model
            # stage below, after the auditable deterministic pass is complete.

        if blockers:
            terminal = CONTESTED if any(
                b["reason"] == CONTESTED for b in blockers) else ESCALATE_HUMAN
            why = "required route dependencies are unresolved"
            trace.append({"stage": Stage.AGENT_ITERATION.value,
                          "status": "NOT_RUN_BLOCKED"})
            if use_model:
                self._propose(Stage.AGENT_ITERATION, context, proposals)
        else:
            terminal, why = self._iterate(
                self.callbacks.get(Stage.AGENT_ITERATION), context, use_model,
                trace, proposals)

        # Assert the central contract rather than merely documenting it.
        if context["evidence"] != original_evidence:
            raise RuntimeError("route mutated evidence")

        return {
            "verdict": ANSWER,
            "terminal_verdict": terminal,
            "why": why,
            "route": "llm-assisted" if use_model else "model-free",
            "model_used": bool(use_model and self.model_proposer is not None),
            "evidence": copy.deepcopy(original_evidence),
            "artifacts": copy.deepcopy(context["artifacts"]),
            "proposals": copy.deepcopy(proposals),
            "blockers": blockers,
            "trace": trace,
            "budget": self.budget.as_dict(),
        }

    def dependency_report(
            self, evidence: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Run both routes and emit a side-by-side, auditable dependency report."""
        model_free = self.run(evidence, use_model=False)
        assisted = self.run(evidence, use_model=True)
        stages = []
        for definition in STAGE_DEFINITIONS:
            stage = definition.stage
            deterministic_available = stage in self.callbacks
            corpus_available = stage in self.corpus_callbacks
            stages.append({
                **definition.as_dict(),
                "deterministic_callback_available": deterministic_available,
                "external_corpus_available": corpus_available,
                "model_can_propose": stage == Stage.AGENT_ITERATION,
                "model_can_promote_evidence": False,
            })
        return {
            "verdict": ANSWER,
            "stages": stages,
            "model_free": model_free,
            "llm_assisted": assisted,
            "comparison": {
                "same_evidence": model_free["evidence"] == assisted["evidence"],
                "same_deterministic_artifacts": (
                    model_free["artifacts"] == assisted["artifacts"]),
                "model_free_terminal": model_free["terminal_verdict"],
                "llm_assisted_terminal": assisted["terminal_verdict"],
                "assisted_proposal_count": len(assisted["proposals"]),
                "dependency_difference": "proposals only",
            },
        }


GenerationRoutePlanner = RoutePlanner


def execute_route(
    evidence: Optional[Mapping[str, Any]] = None,
    *,
    callbacks: Optional[Mapping[Any, Callback]] = None,
    corpus_callbacks: Optional[Mapping[Any, Callback]] = None,
    model_proposer: Optional[ModelProposer] = None,
    use_model: bool = False,
    budget: Optional[ConvergenceBudget] = None,
) -> Dict[str, Any]:
    """Functional wrapper around :class:`RoutePlanner`."""
    return RoutePlanner(callbacks, corpus_callbacks=corpus_callbacks,
                        model_proposer=model_proposer, budget=budget).run(
                            evidence, use_model=use_model)


def dependency_report(
    evidence: Optional[Mapping[str, Any]] = None,
    *,
    callbacks: Optional[Mapping[Any, Callback]] = None,
    corpus_callbacks: Optional[Mapping[Any, Callback]] = None,
    model_proposer: Optional[ModelProposer] = None,
    budget: Optional[ConvergenceBudget] = None,
) -> Dict[str, Any]:
    """Functional wrapper producing the two-route audit."""
    return RoutePlanner(callbacks, corpus_callbacks=corpus_callbacks,
                        model_proposer=model_proposer,
                        budget=budget).dependency_report(evidence)


__all__ = [
    "ANSWER", "CONVERGED", "CONTINUE", "CONTESTED", "ESCALATE_HUMAN",
    "Dependency", "Stage", "StageDefinition", "STAGE_DEFINITIONS",
    "ConvergenceBudget", "RoutePlanner", "GenerationRoutePlanner",
    "execute_route", "dependency_report",
]
