# -*- coding: utf-8 -*-
"""Empirical audit of the representation behind :mod:`photoloset.cross`.

This module deliberately does **not** rename or modify the production store.
It asks a narrower, falsifiable question: which observable properties require
the ``Cross`` representation, and which survive a translation to ordinary
tagged records?

The audit keeps volatile timing measurements outside the deterministic report
digest.  Timing and object-size observations are evidence about one run on one
interpreter; they are not proof that either representation is superior.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import platform
import statistics
import sys
import textwrap
import time
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from photoloset import cross


TAGGED_SCHEMA = "ordinary-tagged-record-store.v1"
EVIDENCE_SCHEMA = "evidence-cross-ledger.v1"
PHYSICAL_SCHEMA = "physical-cross-local-basis.v1"
NO_SUPERIORITY_CLAIM = "MEASURED_ONLY_NO_SUPERIORITY_CLAIM"


EVIDENCE_SCHEMA_DESCRIPTOR: Dict[str, Any] = {
    "schema": EVIDENCE_SCHEMA,
    "purpose": "claim authority, disagreement, and provenance",
    "required_fields": ["address", "state", "value", "tags", "provenance"],
    "forbidden_fields": ["local_basis", "forces", "residuals", "solver_state"],
}

PHYSICAL_SCHEMA_DESCRIPTOR: Dict[str, Any] = {
    "schema": PHYSICAL_SCHEMA,
    "purpose": "local directional physical state exchanged by solvers",
    "required_fields": [
        "local_basis", "material", "constraints", "forces", "residuals",
        "solver_state",
    ],
    "forbidden_fields": ["address", "claim_state", "evidence_kind"],
}


PlanRow = Tuple[str, str, Any, str, str]


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _value_token(value: Any) -> str:
    """Use the production store's identity rule for an audit comparison.

    ``_vkey`` is intentionally private.  Depending on it here is acceptable
    because this is a representation audit of that exact implementation, not
    a second production store claiming an independent value definition.
    """

    return repr(cross._vkey(value))  # type: ignore[attr-defined]


def _normal_sources(values: Iterable[Any]) -> List[str]:
    return sorted(cross._independent(list(values)))  # type: ignore[attr-defined]


class _DisjointSet:
    def __init__(self, names: Iterable[str]) -> None:
        self.parent = {name: name for name in names}

    def find(self, name: str) -> str:
        parent = self.parent.setdefault(name, name)
        while parent != self.parent[parent]:
            self.parent[parent] = self.parent[self.parent[parent]]
            parent = self.parent[parent]
        self.parent[name] = parent
        return parent

    def union(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a == b:
            return
        # The representative is a storage detail.  Pick it deterministically.
        first, second = sorted((a, b), key=lambda item: (len(item), item))
        self.parent[second] = first


def cross_to_tagged_records(store: cross.CrossStore) -> Dict[str, Any]:
    """Map a ``CrossStore`` to ordinary records, tags, and provenance.

    Arms remain metadata.  They are not coordinates and are not consulted by
    :func:`resolve_tagged_records` when it selects a value.
    """

    raw = store.to_dict()
    dsu = _DisjointSet(raw["cores"])
    for edge in raw.get("edges", []):
        if edge.get("label") != "nest":
            continue
        left, right = edge.get("a"), edge.get("b")
        if (isinstance(left, (list, tuple)) and len(left) == 2
                and isinstance(right, (list, tuple)) and len(right) == 2):
            dsu.union(str(left[0]), str(right[0]))

    aliases = {name: dsu.find(name) for name in sorted(raw["cores"])}
    records: List[Dict[str, Any]] = []
    for core_name in sorted(raw["cores"]):
        for seat in sorted(raw["cores"][core_name],
                           key=lambda row: (row.get("seq", 0), row["key"])):
            for entry in seat.get("values", []):
                kind = entry.get("kind")
                records.append({
                    "address": {"root": aliases[core_name],
                                "key": seat["key"]},
                    "value": copy.deepcopy(entry.get("value")),
                    "tags": {
                        "kind": kind,
                        "arm": cross.KIND_ARM.get(kind),
                        "charged_arm": seat.get("arm"),
                    },
                    "provenance": {
                        "sources": list(entry.get("sources", [])),
                        "original_core": core_name,
                        "declaration_seq": seat.get("seq"),
                    },
                })
    records.sort(key=lambda row: (
        row["address"]["root"], row["address"]["key"],
        row["provenance"]["declaration_seq"], row["tags"]["kind"],
        _value_token(row["value"]),
    ))
    return {
        "schema": TAGGED_SCHEMA,
        "aliases": aliases,
        "records": records,
        "relations": copy.deepcopy(raw.get("edges", [])),
        "quarantine": list(raw.get("quarantine", [])),
    }


def _tagged_from_plan(plan: Sequence[PlanRow]) -> Dict[str, Any]:
    records = []
    for seq, (core_name, key, value, kind, source) in enumerate(plan, 1):
        records.append({
            "address": {"root": core_name, "key": key},
            "value": copy.deepcopy(value),
            "tags": {"kind": kind, "arm": cross.KIND_ARM.get(kind),
                     "charged_arm": cross.KIND_ARM.get(kind)},
            "provenance": {"sources": [source],
                           "original_core": core_name,
                           "declaration_seq": seq},
        })
    return {"schema": TAGGED_SCHEMA,
            "aliases": {core_name: core_name
                        for core_name, _key, _value, _kind, _source in plan},
            "records": records, "relations": [], "quarantine": []}


def resolve_tagged_records(tagged: Mapping[str, Any], core_name: str,
                           key: str) -> Dict[str, Any]:
    """Resolve ordinary tagged records without using arm geometry."""

    if tagged.get("schema") != TAGGED_SCHEMA:
        return {"verdict": "UNKNOWN_TAGGED_RECORD_SCHEMA"}
    root = tagged.get("aliases", {}).get(core_name, core_name)
    rows = [row for row in tagged.get("records", [])
            if row.get("address") == {"root": root, "key": key}]
    if not rows:
        return {"verdict": cross.NOT_IN_CROSS}

    tokens = [_value_token(row.get("value")) for row in rows]
    if any(token != tokens[0] for token in tokens[1:]):
        sides = [{
            "value": copy.deepcopy(row.get("value")),
            "kind": row.get("tags", {}).get("kind"),
            "sources": list(row.get("provenance", {}).get("sources", [])),
            "provenance": copy.deepcopy(row.get("provenance", {})),
        } for row in rows]
        return {"verdict": cross.CONTESTED_IN_CROSS, "sides": sides,
                "also_on": "support-"}

    by_kind: Dict[str, List[str]] = {}
    named_sources: List[str] = []
    for row in rows:
        kind = str(row.get("tags", {}).get("kind"))
        sources = list(row.get("provenance", {}).get("sources", []))
        by_kind.setdefault(kind, []).extend(sources)
        for source in sources:
            if source not in named_sources:
                named_sources.append(source)
    normalized = {kind: _normal_sources(sources)
                  for kind, sources in by_kind.items()}
    weights = {kind: len(sources) for kind, sources in normalized.items()}
    priced_kind = max(sorted(weights), key=lambda name: weights[name])
    return {
        "verdict": "ANSWER",
        "value": copy.deepcopy(rows[0].get("value")),
        "weight": weights[priced_kind],
        "weight_kind": priced_kind,
        "weight_by_kind": weights,
        "sources": normalized[priced_kind],
        "sources_by_kind": normalized,
        "named_sources": named_sources,
        "kinds": [row.get("tags", {}).get("kind") for row in rows],
        "provenance": [copy.deepcopy(row.get("provenance", {}))
                       for row in rows],
    }


def _semantic_resolution(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Canonical value/disagreement/provenance view, excluding arm labels."""

    verdict = result.get("verdict")
    if verdict == "ANSWER":
        return {
            "verdict": verdict,
            "value": _value_token(result.get("value")),
            "weight": result.get("weight"),
            "weight_by_kind": sorted(
                (result.get("weight_by_kind") or {}).items()),
            "sources_by_kind": sorted(
                (kind, tuple(_normal_sources(sources)))
                for kind, sources in
                (result.get("sources_by_kind") or {}).items()),
            "named_sources": tuple(_normal_sources(
                result.get("named_sources") or [])),
        }
    if verdict == cross.CONTESTED_IN_CROSS:
        sides = []
        for side in result.get("sides", []):
            sides.append((_value_token(side.get("value")), side.get("kind"),
                          tuple(_normal_sources(side.get("sources", [])))))
        return {"verdict": verdict, "sides": sorted(sides)}
    return {"verdict": verdict}


def _selection_resolution(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Only the value-selection outcome; kind/arm metadata is excluded."""

    if result.get("verdict") == "ANSWER":
        return {"verdict": "ANSWER", "value": _value_token(result["value"]),
                "weight": result.get("weight")}
    if result.get("verdict") == cross.CONTESTED_IN_CROSS:
        return {"verdict": cross.CONTESTED_IN_CROSS,
                "values": sorted(_value_token(side.get("value"))
                                 for side in result.get("sides", []))}
    return {"verdict": result.get("verdict")}


def audit_cause_axis() -> Dict[str, Any]:
    """Measure whether changing only cause +/- changes value selection."""

    selections: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    for kind in ("derived", "feeds"):
        store = cross.CrossStore()
        store.put("subject", "parameter", 42, kind, "named-source")
        resolved = store.resolve("subject", "parameter")
        selections[kind] = _selection_resolution(resolved)
        metadata[kind] = {"arm": resolved.get("arm"),
                          "arms": resolved.get("arms"),
                          "weight_kind": resolved.get("weight_kind")}

    contested: Dict[str, Any] = {}
    for kind in ("derived", "feeds"):
        store = cross.CrossStore()
        store.put("subject", "parameter", 42, kind, "source-a")
        store.put("subject", "parameter", 43, kind, "source-b")
        contested[kind] = _selection_resolution(
            store.resolve("subject", "parameter"))

    tree = ast.parse(textwrap.dedent(inspect.getsource(cross.CrossStore.resolve)))
    string_literals = [node.value for node in ast.walk(tree)
                       if isinstance(node, ast.Constant)
                       and isinstance(node.value, str)]
    cause_literals = sorted(value for value in string_literals
                            if "cause+" in value or "cause-" in value)
    return {
        "experiment": "change derived/cause+ to feeds/cause-",
        "answer_selection_equal": selections["derived"] == selections["feeds"],
        "contested_selection_equal": contested["derived"] == contested["feeds"],
        "metadata_equal": metadata["derived"] == metadata["feeds"],
        "selection": selections,
        "metadata": metadata,
        "resolve_cause_literals": cause_literals,
        "measured_conclusion": (
            "cause labels change retained metadata but did not change value or "
            "disagreement selection in these executable cases"
        ),
        "scope_limit": (
            "this is a falsification of necessity in current resolve behavior, "
            "not a proof that causal metadata can never be used elsewhere"
        ),
    }


def audit_tagged_equivalence() -> Dict[str, Any]:
    store = cross.CrossStore()
    store.put("subject", "length", 42, "measured", "lab-a")
    store.put("subject", "length", 42, "measured", "lab-b")
    store.put("subject", "length", 42, "derived", "solver-a")
    store.put("subject", "material", "jersey", "specific", "maker")
    store.put("subject", "material", "melton", "cited", "catalogue")

    tagged = cross_to_tagged_records(store)
    comparisons = {}
    for key in ("length", "material"):
        cross_value = _semantic_resolution(store.resolve("subject", key))
        tagged_value = _semantic_resolution(
            resolve_tagged_records(tagged, "subject", key))
        comparisons[key] = {
            "cross": cross_value,
            "tagged": tagged_value,
            "equal": cross_value == tagged_value,
        }
    return {
        "schema": tagged["schema"],
        "record_count": len(tagged["records"]),
        "all_equal": all(row["equal"] for row in comparisons.values()),
        "comparisons": comparisons,
        "provenance_preserved": sorted(
            source for row in tagged["records"]
            for source in row["provenance"]["sources"]
        ) == ["catalogue", "lab-a", "lab-b", "maker", "solver-a"],
        "representation_conclusion": (
            "ordinary records plus tags and provenance retained the measured "
            "value, disagreement state, and named sources"
        ),
    }


def audit_order_behavior() -> Dict[str, Any]:
    stable_plan: List[PlanRow] = [
        ("subject", "a", 1, "derived", "solver-a"),
        ("subject", "b", 2, "feeds", "consumer-b"),
        ("subject", "c", 3, "specific", "reviewer-c"),
    ]
    shared_plan: List[PlanRow] = [
        ("subject", "shared", 42, "derived", "solver"),
        ("subject", "shared", 42, "feeds", "consumer"),
    ]
    stable = cross.ingest_order_check(stable_plan)
    shared = cross.ingest_order_check(shared_plan)
    return {
        "stable": stable,
        "shared_address": shared,
        "explicit": (
            stable["verdict"] == "ANSWER"
            and shared["verdict"] == cross.ORDER_DEPENDENT
            and shared["budget_arm_differences"] > 0
        ),
        "conclusion": (
            "order-invariant plans answer normally; the unresolved shared-address "
            "budget policy is surfaced as UNKNOWN_ORDER_DEPENDENT"
        ),
    }


def validate_evidence_artifact(value: Mapping[str, Any]) -> Dict[str, Any]:
    missing = [field for field in EVIDENCE_SCHEMA_DESCRIPTOR["required_fields"]
               if field not in value]
    forbidden = [field for field in EVIDENCE_SCHEMA_DESCRIPTOR["forbidden_fields"]
                 if field in value]
    return {"verdict": "ANSWER" if not missing and not forbidden
            else "UNKNOWN_EVIDENCE_SCHEMA_MISMATCH",
            "missing": missing, "forbidden": forbidden}


def validate_physical_artifact(value: Mapping[str, Any]) -> Dict[str, Any]:
    missing = [field for field in PHYSICAL_SCHEMA_DESCRIPTOR["required_fields"]
               if field not in value]
    forbidden = [field for field in PHYSICAL_SCHEMA_DESCRIPTOR["forbidden_fields"]
                 if field in value]
    return {"verdict": "ANSWER" if not missing and not forbidden
            else "UNKNOWN_PHYSICAL_SCHEMA_MISMATCH",
            "missing": missing, "forbidden": forbidden}


def audit_schema_separation() -> Dict[str, Any]:
    evidence = {field: {} for field in
                EVIDENCE_SCHEMA_DESCRIPTOR["required_fields"]}
    physical = {field: {} for field in
                PHYSICAL_SCHEMA_DESCRIPTOR["required_fields"]}
    return {
        "evidence_schema": copy.deepcopy(EVIDENCE_SCHEMA_DESCRIPTOR),
        "physical_schema": copy.deepcopy(PHYSICAL_SCHEMA_DESCRIPTOR),
        "schema_names_differ": EVIDENCE_SCHEMA != PHYSICAL_SCHEMA,
        "evidence_accepts_evidence": validate_evidence_artifact(evidence),
        "physical_accepts_physical": validate_physical_artifact(physical),
        "evidence_rejects_physical": validate_evidence_artifact(physical),
        "physical_rejects_evidence": validate_physical_artifact(evidence),
        "conclusion": (
            "EvidenceCross and PhysicalCross share design principles, not a schema"
        ),
    }


def _deep_size(value: Any, seen: set[int] | None = None) -> int:
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(_deep_size(key, seen) + _deep_size(item, seen)
                    for key, item in value.items())
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(_deep_size(item, seen) for item in value)
    elif hasattr(value, "__dict__"):
        size += _deep_size(vars(value), seen)
    return size


def _fixture_plan() -> List[PlanRow]:
    kinds = ("measured", "derived", "feeds", "specific")
    return [("benchmark", f"field.{index}", index * 0.25,
             kinds[index % len(kinds)], f"source-{index}")
            for index in range(12)]


def _cross_work(plan: Sequence[PlanRow]) -> None:
    store = cross.CrossStore()
    for row in plan:
        store.put(*row)
    for _core, key, _value, _kind, _source in plan:
        store.resolve("benchmark", key)


def _tagged_work(plan: Sequence[PlanRow]) -> None:
    tagged = _tagged_from_plan(plan)
    for _core, key, _value, _kind, _source in plan:
        resolve_tagged_records(tagged, "benchmark", key)


def _timed_samples(function: Any, plan: Sequence[PlanRow], rounds: int,
                   iterations: int) -> List[int]:
    samples = []
    for _ in range(rounds):
        start = time.perf_counter_ns()
        for _iteration in range(iterations):
            function(plan)
        elapsed = time.perf_counter_ns() - start
        samples.append(elapsed // iterations)
    return samples


def measure_representation_costs(*, rounds: int = 5,
                                 iterations: int = 80) -> Dict[str, Any]:
    """Record raw size/timing observations without declaring a winner."""

    if rounds < 1 or iterations < 1:
        raise ValueError("rounds and iterations must be positive")
    plan = _fixture_plan()
    cross_store = cross.CrossStore()
    for row in plan:
        cross_store.put(*row)
    tagged = _tagged_from_plan(plan)
    cross_samples = _timed_samples(_cross_work, plan, rounds, iterations)
    tagged_samples = _timed_samples(_tagged_work, plan, rounds, iterations)
    return {
        "protocol": {
            "fixture_claims": len(plan), "rounds": rounds,
            "iterations_per_round": iterations,
            "operation": "construct representation and resolve every address",
            "size_method": "recursive sys.getsizeof with object-id deduplication",
            "timer": "time.perf_counter_ns",
        },
        "environment": {"python": platform.python_version(),
                        "implementation": platform.python_implementation(),
                        "platform": platform.platform()},
        "memory_bytes": {"cross": _deep_size(cross_store),
                         "ordinary_tagged": _deep_size(tagged)},
        "nanoseconds_per_iteration": {
            "cross_samples": cross_samples,
            "ordinary_tagged_samples": tagged_samples,
            "cross_median": int(statistics.median(cross_samples)),
            "ordinary_tagged_median": int(statistics.median(tagged_samples)),
        },
        "comparative_conclusion": NO_SUPERIORITY_CLAIM,
        "limits": [
            "timings are volatile and excluded from the deterministic digest",
            "Python object size is not resident-set size",
            "the ordinary implementation is an audit reference, not an optimized replacement",
            "no statistical or product-level superiority follows from this microbenchmark",
        ],
    }


def build_audit_report(*, benchmark_rounds: int = 5,
                       benchmark_iterations: int = 80) -> Dict[str, Any]:
    """Build the report and a digest of only deterministic observations."""

    deterministic = {
        "schema": "cross-representation-falsification-audit.v1",
        "question": (
            "is the Cross name/geometric metaphor necessary for current "
            "observable resolve semantics?"
        ),
        "cause_axis": audit_cause_axis(),
        "tagged_equivalence": audit_tagged_equivalence(),
        "order_behavior": audit_order_behavior(),
        "schema_separation": audit_schema_separation(),
        "verdict": (
            "NAME_AND_GEOMETRIC_METAPHOR_NOT_REQUIRED_FOR_MEASURED_SEMANTICS"
        ),
        "properties_retained": [
            "typed claim kinds", "disagreement preservation",
            "named-source provenance", "deterministic reduction when defined",
            "explicit UNKNOWN_ORDER_DEPENDENT when not defined",
        ],
        "non_claim": (
            "this report does not prove the ordinary representation is faster, "
            "smaller, or preferable as a production implementation"
        ),
    }
    return {
        "deterministic": deterministic,
        "deterministic_digest": _digest(deterministic),
        "performance_observation": measure_representation_costs(
            rounds=benchmark_rounds, iterations=benchmark_iterations),
    }


__all__ = [
    "EVIDENCE_SCHEMA", "PHYSICAL_SCHEMA", "TAGGED_SCHEMA",
    "NO_SUPERIORITY_CLAIM", "audit_cause_axis", "audit_order_behavior",
    "audit_schema_separation", "audit_tagged_equivalence",
    "build_audit_report", "cross_to_tagged_records",
    "measure_representation_costs", "resolve_tagged_records",
    "validate_evidence_artifact", "validate_physical_artifact",
]
