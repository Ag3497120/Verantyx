# -*- coding: utf-8 -*-
"""Honest retrieval for garments that do not fit a named clothing class.

Image similarity is used to *propose ingredients*, never to assert panels,
seams, or a sewing order.  The only route to sewing-method retrieval is:

    per-region retrieval -> fused part proposals -> geometry hypotheses
    -> digest-bound, named human approval -> construction-corpus search

The module is deliberately model-agnostic.  Callbacks can be real adapters or
small fixtures; their provenance says which.  All state is held by
``RetrievalHypothesisGate`` so a caller cannot search by handing an unapproved
geometry directly to the final function.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping
from typing import Optional, Sequence, Tuple


class Verdict(str, Enum):
    """Closed result vocabulary; UNKNOWN values are hard stops."""

    ANSWER = "ANSWER"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    NO_SOURCE = "UNKNOWN_NO_RETRIEVAL_SOURCE"
    WHOLE_IMAGE_ONLY = "UNKNOWN_WHOLE_IMAGE_ONLY"
    BAD_SOURCE = "UNKNOWN_BAD_SOURCE"
    BAD_CANDIDATE = "UNKNOWN_BAD_CANDIDATE"
    SIMILARITY_NOT_CONSTRUCTION = "UNKNOWN_SIMILARITY_IS_NOT_CONSTRUCTION"
    NO_PART_CANDIDATES = "UNKNOWN_NO_PART_CANDIDATES"
    NO_CONSTRUCTOR = "UNKNOWN_NO_GEOMETRY_CONSTRUCTOR"
    BAD_GEOMETRY = "UNKNOWN_BAD_GEOMETRY_HYPOTHESIS"
    BACK_AMBIGUITY = "UNKNOWN_BACK_DESIGN_AMBIGUITY_NOT_PRESERVED"
    NO_HYPOTHESIS = "UNKNOWN_NO_GEOMETRY_HYPOTHESIS"
    APPROVER_REQUIRED = "UNKNOWN_NAMED_HUMAN_APPROVER_REQUIRED"
    APPROVAL_REQUIRED = "UNKNOWN_GEOMETRY_APPROVAL_REQUIRED"
    APPROVAL_STALE = "UNKNOWN_GEOMETRY_APPROVAL_STALE"
    NO_SEWING_CORPUS = "UNKNOWN_NO_SEWING_CORPUS"
    RIGHTS = "UNKNOWN_CORPUS_RIGHTS"
    CALLBACK_FAILED = "UNKNOWN_CALLBACK_FAILED"


class Modality(str, Enum):
    WHOLE_IMAGE_EMBEDDING = "image_embedding"
    REGION_EMBEDDING = "region_embedding"
    PART_EMBEDDING = "part_embedding"
    STRUCTURE = "structure"
    CONSTRUCTION = "construction"


class Rights(str, Enum):
    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"
    DENIED = "denied"


class EvidenceKind(str, Enum):
    VISUAL_SIMILARITY = "VISUAL_SIMILARITY"
    GEOMETRY_HYPOTHESIS = "GEOMETRY_HYPOTHESIS"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    CONSTRUCTION_CORPUS = "CONSTRUCTION_CORPUS"


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(_plain(value), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CorpusProvenance:
    """Identity, lineage, licence, and use rights for one source."""

    corpus: str
    record: str = ""
    licence: str = ""
    rights: Rights = Rights.UNKNOWN
    lineage: Tuple[str, ...] = ()
    version: str = "unversioned"
    fixture: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "rights", Rights(self.rights))
        object.__setattr__(self, "lineage", tuple(str(x) for x in self.lineage))

    def as_dict(self) -> Dict[str, Any]:
        return _plain(self.__dict__)


@dataclass(frozen=True)
class Provenance:
    kind: EvidenceKind
    source: str
    corpus: CorpusProvenance
    region_id: str = ""
    part_id: str = ""
    candidate_ids: Tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", EvidenceKind(self.kind))
        object.__setattr__(self, "candidate_ids",
                           tuple(str(x) for x in self.candidate_ids))

    def as_dict(self) -> Dict[str, Any]:
        out = _plain(self.__dict__)
        out["corpus"] = self.corpus.as_dict()
        return out


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    part_id: str
    region_id: str
    reference: str
    score: Optional[float]
    visual_cues: Mapping[str, Any]
    provenance: Provenance

    def as_dict(self) -> Dict[str, Any]:
        return {"candidate_id": self.candidate_id, "part_id": self.part_id,
                "region_id": self.region_id, "reference": self.reference,
                "score": self.score,
                "visual_cues": copy.deepcopy(dict(self.visual_cues)),
                "state": Verdict.PROPOSED.value,
                "provenance": self.provenance.as_dict()}


@dataclass(frozen=True)
class FusedPart:
    part_id: str
    regions: Tuple[str, ...]
    candidates: Tuple[Candidate, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {"part_id": self.part_id, "regions": list(self.regions),
                "state": Verdict.PROPOSED.value,
                "candidates": [c.as_dict() for c in self.candidates],
                "note": "alternatives, not construction truth"}


@dataclass(frozen=True)
class GeometryHypothesis:
    hypothesis_id: str
    digest: str
    geometry: Mapping[str, Any]
    selected_back_design: str
    back_design_alternatives: Tuple[str, ...]
    front_only: bool
    provenance: Provenance

    def digest_now(self) -> str:
        return hypothesis_digest(self.geometry, self.selected_back_design,
                                 self.back_design_alternatives,
                                 self.front_only)

    def as_dict(self) -> Dict[str, Any]:
        return {"hypothesis_id": self.hypothesis_id, "digest": self.digest,
                "geometry": copy.deepcopy(dict(self.geometry)),
                "selected_back_design": self.selected_back_design,
                "back_design_alternatives":
                    list(self.back_design_alternatives),
                "front_only": self.front_only,
                "state": Verdict.PROPOSED.value,
                "provenance": self.provenance.as_dict()}


@dataclass(frozen=True)
class HumanApproval:
    approval_id: str
    approver: str
    geometry_digest: str
    hypothesis_id: str
    provenance: Provenance

    def as_dict(self) -> Dict[str, Any]:
        return {"approval_id": self.approval_id, "approver": self.approver,
                "geometry_digest": self.geometry_digest,
                "hypothesis_id": self.hypothesis_id,
                "state": Verdict.APPROVED.value,
                "provenance": self.provenance.as_dict()}


@dataclass(frozen=True)
class Result(Mapping[str, Any]):
    """Typed verdict with a dict-compatible surface for app boundaries."""

    verdict: Verdict
    values: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"verdict": self.verdict.value,
                **{k: _plain(v) for k, v in self.values.items()}}

    def __getitem__(self, key: str) -> Any:
        if key == "verdict":
            return self.verdict.value
        return self.values[key]

    def __iter__(self) -> Iterator[str]:
        yield "verdict"
        yield from self.values

    def __len__(self) -> int:
        return 1 + len(self.values)


@dataclass(frozen=True)
class _Source:
    name: str
    modality: Modality
    callback: Callable[[Dict[str, Any]], Any]
    provenance: CorpusProvenance


_CONSTRUCTION_KEYS = frozenset({
    "construction", "construction_claims", "geometry", "panels", "panel",
    "pattern", "pattern_pieces", "seams", "sewing_order", "stitches",
})


def hypothesis_digest(geometry: Mapping[str, Any], selected_back_design: str,
                      alternatives: Sequence[str], front_only: bool) -> str:
    """Digest exactly what a person sees and approves in 3D."""
    return _digest({"geometry": geometry,
                    "selected_back_design": selected_back_design,
                    "back_design_alternatives": list(alternatives),
                    "front_only": bool(front_only)})


def _hits(value: Any) -> Optional[List[Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        value = value.get("hits")
    if not isinstance(value, (list, tuple)):
        return None
    if not all(isinstance(x, Mapping) for x in value):
        return None
    return list(value)


class RetrievalHypothesisGate:
    """Stateful gate whose final search accepts only an approval id."""

    def __init__(self) -> None:
        self._retrieval: Dict[str, _Source] = {}
        self._sewing: Dict[str, _Source] = {}
        self._hypotheses: Dict[str, GeometryHypothesis] = {}
        self._approvals: Dict[str, HumanApproval] = {}

    @staticmethod
    def _source(name: str, modality: Any,
                callback: Callable[[Dict[str, Any]], Any],
                provenance: CorpusProvenance) -> Result:
        try:
            mode = Modality(modality)
        except (TypeError, ValueError):
            return Result(Verdict.BAD_SOURCE, {"which": str(modality)})
        if not str(name).strip() or not callable(callback):
            return Result(Verdict.BAD_SOURCE,
                          {"why": "a source needs a name and callback"})
        if not isinstance(provenance, CorpusProvenance):
            return Result(Verdict.BAD_SOURCE,
                          {"why": "typed CorpusProvenance is required"})
        if not provenance.corpus.strip() or not provenance.licence.strip():
            return Result(Verdict.BAD_SOURCE,
                          {"why": "corpus and licence are required"})
        return Result(Verdict.ANSWER, {"source": _Source(
            str(name).strip(), mode, callback, provenance)})

    def register_retrieval_source(
            self, name: str, modality: Any,
            callback: Callable[[Dict[str, Any]], Any], *,
            provenance: CorpusProvenance) -> Result:
        made = self._source(name, modality, callback, provenance)
        if made.verdict is not Verdict.ANSWER:
            return made
        source = made.values["source"]
        if source.modality is Modality.CONSTRUCTION:
            return Result(Verdict.BAD_SOURCE,
                          {"why": "construction belongs after approval"})
        self._retrieval[source.name] = source
        return Result(Verdict.ANSWER,
                      {"registered": source.name,
                       "modality": source.modality.value,
                       "provenance": source.provenance.as_dict()})

    def register_sewing_corpus(
            self, name: str, callback: Callable[[Dict[str, Any]], Any], *,
            provenance: CorpusProvenance) -> Result:
        made = self._source(name, Modality.CONSTRUCTION, callback, provenance)
        if made.verdict is not Verdict.ANSWER:
            return made
        source = made.values["source"]
        self._sewing[source.name] = source
        return Result(Verdict.ANSWER,
                      {"registered": source.name,
                       "provenance": source.provenance.as_dict()})

    def retrieve_parts(self, image_ref: Any,
                       regions: Sequence[Mapping[str, Any]], *,
                       source_names: Sequence[str] = ()) -> Result:
        """Retrieve each supplied region/part independently.

        A whole-image embedding is rejected even if a caller supplies part
        labels beside it: one global vector did not measure those parts.
        """
        names = list(source_names) if source_names else sorted(self._retrieval)
        if not names:
            return Result(Verdict.NO_SOURCE)
        missing = [n for n in names if n not in self._retrieval]
        if missing:
            return Result(Verdict.NO_SOURCE, {"missing": missing})
        sources = [self._retrieval[n] for n in names]
        whole = [s.name for s in sources
                 if s.modality is Modality.WHOLE_IMAGE_EMBEDDING]
        if whole:
            return Result(Verdict.WHOLE_IMAGE_ONLY, {
                "sources": whole,
                "why": "a whole-image vector cannot support a per-part claim",
                "how_to_close": "use region_embedding, part_embedding, or "
                                "a structure source with explicit regions"})
        candidates: List[Candidate] = []
        for region in regions:
            part_id = str(region.get("part_id") or "").strip()
            region_id = str(region.get("region_id") or "").strip()
            if not part_id or not region_id:
                return Result(Verdict.BAD_CANDIDATE,
                              {"why": "every region names part_id and region_id"})
            for source in sources:
                query = {"image_ref": image_ref,
                         "region": copy.deepcopy(dict(region)),
                         "part_id": part_id, "region_id": region_id,
                         "question": "visual alternatives, not construction"}
                try:
                    raw = source.callback(query)
                except Exception as exc:  # callback boundary
                    return Result(Verdict.CALLBACK_FAILED,
                                  {"source": source.name,
                                   "error": f"{type(exc).__name__}: {exc}"})
                found = _hits(raw)
                if found is None:
                    return Result(Verdict.BAD_CANDIDATE,
                                  {"source": source.name,
                                   "why": "callback returns a hit list"})
                for index, hit in enumerate(found):
                    forbidden = sorted(_CONSTRUCTION_KEYS.intersection(hit))
                    if forbidden and source.modality in {
                            Modality.REGION_EMBEDDING,
                            Modality.PART_EMBEDDING}:
                        return Result(Verdict.SIMILARITY_NOT_CONSTRUCTION, {
                            "source": source.name, "fields": forbidden,
                            "why": "embedding hits may propose references and "
                                   "visual cues, not construction"})
                    reference = str(hit.get("reference") or hit.get("id") or "").strip()
                    if not reference:
                        return Result(Verdict.BAD_CANDIDATE,
                                      {"source": source.name,
                                       "why": "a hit needs reference or id"})
                    score = hit.get("score")
                    if score is not None:
                        try:
                            score = float(score)
                        except (TypeError, ValueError):
                            return Result(Verdict.BAD_CANDIDATE,
                                          {"source": source.name,
                                           "why": "score is numeric or absent"})
                    visual = hit.get("visual_cues", hit.get("cues", {}))
                    if not isinstance(visual, Mapping):
                        visual = {"description": str(visual)}
                    cid = _digest({"source": source.name, "part": part_id,
                                   "region": region_id, "reference": reference,
                                   "index": index})[:20]
                    corpus = CorpusProvenance(
                        source.provenance.corpus,
                        str(hit.get("record") or reference),
                        source.provenance.licence, source.provenance.rights,
                        source.provenance.lineage, source.provenance.version,
                        source.provenance.fixture)
                    candidates.append(Candidate(
                        cid, part_id, region_id, reference, score,
                        copy.deepcopy(dict(visual)),
                        Provenance(EvidenceKind.VISUAL_SIMILARITY, source.name,
                                   corpus, region_id, part_id,
                                   note="proposal only; score is not construction truth")))
        return Result(Verdict.PROPOSED, {
            "candidates": tuple(candidates),
            "provenance": [c.provenance.as_dict() for c in candidates]})

    def fuse_per_part(self, candidates: Sequence[Candidate]) -> Result:
        """Group alternatives by part without averaging them into a truth."""
        grouped: Dict[str, List[Candidate]] = {}
        for candidate in candidates:
            if not isinstance(candidate, Candidate):
                return Result(Verdict.BAD_CANDIDATE,
                              {"why": "fuse_per_part accepts Candidate values"})
            grouped.setdefault(candidate.part_id, []).append(candidate)
        if not grouped:
            return Result(Verdict.NO_PART_CANDIDATES)
        fused = []
        for part_id in sorted(grouped):
            items = sorted(grouped[part_id],
                           key=lambda c: (c.region_id, c.provenance.source,
                                          c.reference, c.candidate_id))
            fused.append(FusedPart(part_id,
                                   tuple(sorted({c.region_id for c in items})),
                                   tuple(items)))
        return Result(Verdict.PROPOSED, {"parts": tuple(fused)})

    def construct(self, fused_parts: Sequence[FusedPart], *, front_only: bool,
                  constructor: Callable[[Dict[str, Any]], Any],
                  constructor_name: str = "fixture:constructor",
                  back_design_alternatives: Sequence[str] = ()) -> Result:
        """Build inspectable geometry; one hypothesis per back alternative."""
        if not callable(constructor):
            return Result(Verdict.NO_CONSTRUCTOR)
        alternatives = tuple(dict.fromkeys(
            str(x).strip() for x in back_design_alternatives if str(x).strip()))
        if front_only and len(alternatives) < 2:
            return Result(Verdict.BACK_AMBIGUITY, {
                "why": "a front view does not determine one back design",
                "how_to_close": "supply at least two named back alternatives"})
        if not fused_parts or not all(isinstance(x, FusedPart)
                                      for x in fused_parts):
            return Result(Verdict.NO_PART_CANDIDATES)
        query = {"parts": [p.as_dict() for p in fused_parts],
                 "front_only": bool(front_only),
                 "back_design_alternatives": list(alternatives),
                 "instruction": "construct geometry hypotheses; do not copy "
                                "similarity scores as construction facts"}
        try:
            raw = constructor(copy.deepcopy(query))
        except Exception as exc:
            return Result(Verdict.CALLBACK_FAILED, {
                "source": constructor_name,
                "error": f"{type(exc).__name__}: {exc}"})
        if isinstance(raw, Mapping):
            raw = raw.get("hypotheses")
        if not isinstance(raw, (list, tuple)) or not raw:
            return Result(Verdict.BAD_GEOMETRY,
                          {"why": "constructor returns hypotheses"})
        by_back: Dict[str, Mapping[str, Any]] = {}
        for item in raw:
            if not isinstance(item, Mapping):
                return Result(Verdict.BAD_GEOMETRY)
            geometry = item.get("geometry")
            back = str(item.get("back_design") or "").strip()
            if not isinstance(geometry, Mapping) or not geometry or not back:
                return Result(Verdict.BAD_GEOMETRY, {
                    "why": "each hypothesis needs geometry and back_design"})
            if alternatives and back not in alternatives:
                return Result(Verdict.BAD_GEOMETRY,
                              {"back_design": back,
                               "known": list(alternatives)})
            by_back[back] = geometry
        required = set(alternatives) if front_only else set(by_back)
        if front_only and set(by_back) != required:
            return Result(Verdict.BACK_AMBIGUITY, {
                "missing": sorted(required - set(by_back)),
                "unexpected": sorted(set(by_back) - required)})
        candidate_ids = tuple(sorted(
            c.candidate_id for p in fused_parts for c in p.candidates))
        hypotheses: List[GeometryHypothesis] = []
        corpus = CorpusProvenance(constructor_name, licence="caller supplied",
                                  rights=Rights.ALLOWED,
                                  lineage=(constructor_name,),
                                  fixture=constructor_name.startswith("fixture:"))
        for back in sorted(by_back):
            geometry = copy.deepcopy(dict(by_back[back]))
            digest = hypothesis_digest(geometry, back, alternatives, front_only)
            hypothesis = GeometryHypothesis(
                digest[:20], digest, geometry, back, alternatives,
                bool(front_only),
                Provenance(EvidenceKind.GEOMETRY_HYPOTHESIS,
                           constructor_name, corpus,
                           candidate_ids=candidate_ids,
                           note="constructed for 3D inspection; not yet approved"))
            self._hypotheses[hypothesis.hypothesis_id] = hypothesis
            hypotheses.append(hypothesis)
        return Result(Verdict.PROPOSED,
                      {"hypotheses": tuple(hypotheses),
                       "requires": "named human approval of one geometry digest"})

    def approve(self, hypothesis_id: str, *, approver: str,
                expected_digest: str) -> Result:
        """Record a human's name against the exact displayed geometry."""
        name = str(approver or "").strip()
        if not name:
            return Result(Verdict.APPROVER_REQUIRED)
        hypothesis = self._hypotheses.get(str(hypothesis_id))
        if hypothesis is None:
            return Result(Verdict.NO_HYPOTHESIS,
                          {"hypothesis_id": str(hypothesis_id)})
        now = hypothesis.digest_now()
        if not expected_digest or expected_digest != hypothesis.digest or now != hypothesis.digest:
            return Result(Verdict.APPROVAL_STALE, {
                "expected": expected_digest, "recorded": hypothesis.digest,
                "now": now})
        approval_id = _digest({"geometry_digest": now, "approver": name,
                               "hypothesis_id": hypothesis.hypothesis_id})
        provenance = Provenance(
            EvidenceKind.HUMAN_APPROVAL, name,
            CorpusProvenance("human", record=approval_id,
                             licence="human decision record",
                             rights=Rights.ALLOWED, lineage=("human",)),
            candidate_ids=hypothesis.provenance.candidate_ids,
            note="named human approved the digest shown in 3D")
        approval = HumanApproval(approval_id, name, now,
                                 hypothesis.hypothesis_id, provenance)
        self._approvals[approval_id] = approval
        return Result(Verdict.APPROVED, {"approval": approval})

    def sewing_methods(self, approval_id: str, *,
                       corpus_names: Sequence[str] = ()) -> Result:
        """Search only by approval id; no geometry argument exists here."""
        approval = self._approvals.get(str(approval_id))
        if approval is None:
            return Result(Verdict.APPROVAL_REQUIRED,
                          {"approval_id": str(approval_id)})
        hypothesis = self._hypotheses.get(approval.hypothesis_id)
        if (hypothesis is None or hypothesis.digest_now() != approval.geometry_digest
                or hypothesis.digest != approval.geometry_digest):
            return Result(Verdict.APPROVAL_STALE,
                          {"approval_id": approval.approval_id})
        names = list(corpus_names) if corpus_names else sorted(self._sewing)
        if not names:
            return Result(Verdict.NO_SEWING_CORPUS,
                          {"approval_id": approval.approval_id})
        missing = [n for n in names if n not in self._sewing]
        if missing:
            return Result(Verdict.NO_SEWING_CORPUS, {"missing": missing})
        refused = [self._sewing[n].provenance.as_dict() for n in names
                   if self._sewing[n].provenance.rights
                   in {Rights.UNKNOWN, Rights.DENIED}]
        if refused:
            return Result(Verdict.RIGHTS, {
                "corpora": refused,
                "why": "unknown or denied rights cannot reach a sewing output"})
        methods: List[Dict[str, Any]] = []
        searched: List[Dict[str, Any]] = []
        for name in names:
            source = self._sewing[name]
            query = {"approval_id": approval.approval_id,
                     "geometry_digest": approval.geometry_digest,
                     "geometry": copy.deepcopy(dict(hypothesis.geometry)),
                     "selected_back_design": hypothesis.selected_back_design,
                     "approver": approval.approver}
            try:
                raw = source.callback(query)
            except Exception as exc:
                return Result(Verdict.CALLBACK_FAILED, {
                    "source": name, "error": f"{type(exc).__name__}: {exc}"})
            if isinstance(raw, Mapping):
                raw = raw.get("methods")
            if not isinstance(raw, (list, tuple)):
                return Result(Verdict.BAD_SOURCE,
                              {"source": name,
                               "why": "sewing callback returns methods"})
            searched.append(source.provenance.as_dict())
            for index, method in enumerate(raw):
                if not isinstance(method, Mapping):
                    return Result(Verdict.BAD_SOURCE, {"source": name})
                landed = copy.deepcopy(dict(method))
                landed["state"] = Verdict.PROPOSED.value
                landed["for_approval"] = approval.approval_id
                landed["geometry_digest"] = approval.geometry_digest
                landed["provenance"] = Provenance(
                    EvidenceKind.CONSTRUCTION_CORPUS, name,
                    CorpusProvenance(
                        source.provenance.corpus,
                        str(method.get("record") or f"method:{index}"),
                        source.provenance.licence,
                        source.provenance.rights,
                        source.provenance.lineage,
                        source.provenance.version,
                        source.provenance.fixture),
                    candidate_ids=hypothesis.provenance.candidate_ids,
                    note="retrieved only after digest-bound human approval"
                ).as_dict()
                methods.append(landed)
        lineage_groups: Dict[str, List[str]] = {}
        for name in names:
            provenance = self._sewing[name].provenance
            roots = provenance.lineage or (provenance.corpus,)
            for root in roots:
                lineage_groups.setdefault(root, []).append(name)
        return Result(Verdict.ANSWER, {
            "approval": approval.as_dict(), "methods": methods,
            "searched": searched,
            "lineage_groups": {k: sorted(set(v))
                               for k, v in sorted(lineage_groups.items())},
            "note": "sources sharing a lineage root are not independent evidence"})


# Short alias for callers that prefer the architectural term.
Gate = RetrievalHypothesisGate


def fuse_candidates(candidates: Sequence[Candidate]) -> Result:
    """Stateless convenience for candidate fusion."""
    return RetrievalHypothesisGate().fuse_per_part(candidates)


# ---------------------------------------------------------------------------
# Local, rights-gated hybrid retrieval
# ---------------------------------------------------------------------------

_FEATURE_AXES = ("shape", "parts", "layers", "openings",
                 "seam_topology", "material_ranges")
_DEFAULT_BACKS = ("center_back_opening", "closed_back_side_opening",
                  "layered_cape_back")


def _tokens(value: Any) -> Tuple[str, ...]:
    """Canonical tokens without pretending free text is a taxonomy."""
    if isinstance(value, Mapping):
        out = []
        for key, item in sorted(value.items()):
            if isinstance(item, (str, int, float, bool)):
                out.append(f"{str(key).lower()}={str(item).lower()}")
            else:
                out.extend(f"{str(key).lower()}:{x}" for x in _tokens(item))
        return tuple(sorted(set(out)))
    if isinstance(value, (list, tuple, set)):
        return tuple(sorted(set(x for item in value for x in _tokens(item))))
    if value is None:
        return ()
    return (str(value).strip().lower(),) if str(value).strip() else ()


def _set_match(observed: Any, candidate: Any) -> Tuple[Optional[float], List[str]]:
    left, right = set(_tokens(observed)), set(_tokens(candidate))
    if not left:
        return None, []
    if not right:
        return 0.0, ["candidate has no value for an observed axis"]
    overlap = left & right
    return len(overlap) / len(left | right), sorted(left - right)


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _interval(value: Any) -> Optional[Tuple[float, float]]:
    if isinstance(value, Mapping):
        lo = _finite_number(value.get("min", value.get("low")))
        hi = _finite_number(value.get("max", value.get("high")))
    elif isinstance(value, (tuple, list)) and len(value) == 2:
        lo, hi = _finite_number(value[0]), _finite_number(value[1])
    else:
        lo = hi = _finite_number(value)
    if lo is None or hi is None or lo > hi:
        return None
    return lo, hi


def _material_match(observed: Any, candidate: Any) -> Tuple[Optional[float], List[str]]:
    if not isinstance(observed, Mapping) or not observed:
        return None, []
    right = candidate if isinstance(candidate, Mapping) else {}
    scores, conflicts = [], []
    for name, raw in sorted(observed.items()):
        wanted, offered = _interval(raw), _interval(right.get(name))
        if wanted is None:
            conflicts.append(f"invalid observed range: {name}")
            continue
        if offered is None:
            scores.append(0.0)
            conflicts.append(f"candidate has no material range: {name}")
            continue
        overlap = max(0.0, min(wanted[1], offered[1])
                      - max(wanted[0], offered[0]))
        union = max(wanted[1], offered[1]) - min(wanted[0], offered[0])
        score = 1.0 if union == 0.0 and wanted == offered else (
            overlap / union if union > 0.0 else 0.0)
        scores.append(score)
        if score == 0.0:
            conflicts.append(f"material ranges do not overlap: {name}")
    return (sum(scores) / len(scores) if scores else 0.0), conflicts


def _features(value: Mapping[str, Any]) -> Dict[str, Any]:
    nested = value.get("features", value.get("observation", value))
    nested = nested if isinstance(nested, Mapping) else {}
    return {name: copy.deepcopy(nested.get(name, {} if name in {
        "shape", "material_ranges"} else [])) for name in _FEATURE_AXES}


def _score_features(observed: Mapping[str, Any], candidate: Mapping[str, Any]
                    ) -> Dict[str, Any]:
    scores: Dict[str, Optional[float]] = {}
    contradictions: Dict[str, List[str]] = {}
    for axis in _FEATURE_AXES:
        if axis == "material_ranges":
            score, conflict = _material_match(observed.get(axis),
                                               candidate.get(axis))
        else:
            score, conflict = _set_match(observed.get(axis),
                                         candidate.get(axis))
        scores[axis] = None if score is None else round(score, 6)
        if conflict:
            contradictions[axis] = conflict
    measured = [score for score in scores.values() if score is not None]
    return {
        "axis_scores": scores,
        "coverage": round(len(measured) / len(_FEATURE_AXES), 6),
        "mean_for_ordering_only": (round(sum(measured) / len(measured), 6)
                                   if measured else 0.0),
        "contradictions": contradictions,
        "single_embedding_winner": False,
    }


def _normalise_observation(payload: Mapping[str, Any]) -> Dict[str, Any]:
    evidence = payload.get("image_evidence", payload.get("evidence", payload))
    evidence = evidence if isinstance(evidence, Mapping) else {}
    request = payload.get("request", {})
    request = request if isinstance(request, Mapping) else {}
    regions = evidence.get("regions", payload.get("regions", ()))
    regions = list(regions) if isinstance(regions, Sequence) and not isinstance(
        regions, (str, bytes)) else []
    requested = _features(request)
    region_parts = [str(row.get("part_id")) for row in regions
                    if isinstance(row, Mapping) and row.get("part_id")]
    if not requested["parts"]:
        requested["parts"] = region_parts
    return {
        **requested,
        "regions": copy.deepcopy(regions),
        "outline": copy.deepcopy(evidence.get("outline", payload.get("outline"))),
        "front_only": bool(evidence.get("front_only",
                                        payload.get("front_only", True))),
        "measurements": copy.deepcopy(request.get("measurements", {})),
    }


def _dimension(measures: Mapping[str, Any], name: str, fallback: float
               ) -> Tuple[float, str]:
    number = _finite_number(measures.get(name)) if isinstance(measures, Mapping) else None
    if number is not None and number > 0.0:
        return number, "request.measurements"
    return fallback, "PROPOSED_PREVIEW_MANNEQUIN"


def _outline_metrics(value: Any) -> Dict[str, float]:
    if isinstance(value, Mapping):
        value = value.get("outline")
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))):
        return {}
    points = []
    for row in value:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or len(row) < 2:
            continue
        x, y = _finite_number(row[0]), _finite_number(row[1])
        if x is not None and y is not None:
            points.append((x, y))
    if len(points) < 3:
        return {}
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    if width <= 0.0 or height <= 0.0:
        return {}
    low, high = min(ys), max(ys)

    def span(start: float, end: float) -> Optional[float]:
        band = [x for x, y in points
                if low + height * start <= y <= low + height * end]
        return (max(band) - min(band)) if len(band) >= 2 else None

    middle, lower = span(.33, .67), span(.67, 1.0)
    expansion = ((lower / middle) if middle and lower and middle > 0.0
                 else 1.0)
    return {"width_units": round(width, 6),
            "height_units": round(height, 6),
            "width_height_ratio": round(width / height, 6),
            "lower_to_middle_width_ratio": round(expansion, 6)}


def _procedural_structure(observed: Mapping[str, Any], back: str,
                          variant: int) -> Dict[str, Any]:
    """Build a valid primitive graph, explicitly as a proposal.

    Defaults are preview dimensions, never measurements.  They allow a 3D
    candidate to be shown while preserving the requirement to replace them
    before a manufacturing claim.
    """
    measures = observed.get("measurements", {})
    height, height_source = _dimension(measures, "body_length_cm", 90.0)
    circumference, circumference_source = _dimension(
        measures, "body_circumference_cm", 96.0)
    outline_metrics = _outline_metrics(observed.get("outline"))
    outline_expansion = max(.8, min(2.5, outline_metrics.get(
        "lower_to_middle_width_ratio", 1.0)))
    nodes = [{
        "node_id": "body-shell",
        "kind": "BODY_SHELL",
        "dimensions": {"height_cm": height,
                       "circumference_cm": circumference},
        "attributes": {
            "dimension_source": {"height_cm": height_source,
                                 "circumference_cm": circumference_source},
            "observed_shape": copy.deepcopy(observed.get("shape", {})),
            "observed_outline_metrics": outline_metrics,
            "outline_units_are_not_centimetres": True,
            "back_design": back,
            "proposal_only": True,
        },
    }]
    parts = set(_tokens(observed.get("parts")))
    layer_count = max(1, len(_tokens(observed.get("layers"))))
    if any("skirt" in part or "dress" in part for part in parts):
        nodes.append({
            "node_id": "lower-flare", "kind": "FLARE", "layer": 0,
            "dimensions": {"height_cm": max(45.0, height * 0.62),
                           "top_circumference_cm": circumference,
                           "bottom_circumference_cm": circumference * max(
                               1.1, outline_expansion * (1.25 + .1 * variant))},
            "attributes": {"proposal_only": True,
                           "shape_source": "dimensionless observed outline ratios + geometry",
                           "observed_outline_metrics": outline_metrics},
        })
    if any("sleeve" in part or "arm" in part for part in parts):
        nodes.append({
            "node_id": "sleeves", "kind": "SLEEVE", "layer": 0,
            "dimensions": {"length_cm": 58.0,
                           "upper_circumference_cm": 34.0,
                           "cuff_circumference_cm": 20.0},
            "attributes": {"bilateral": True, "proposal_only": True,
                           "dimension_source": "PROPOSED_PREVIEW_MANNEQUIN"},
        })
    if (layer_count > 1 or any("cape" in part or "overlay" in part
                               for part in parts)):
        nodes.append({
            "node_id": "overlay", "kind": "OVERLAY", "layer": 1,
            "dimensions": {"height_cm": max(35.0, height * .55),
                           "width_cm": circumference * .55},
            "attributes": {"proposal_only": True,
                           "layer_count_observed": layer_count},
        })
    if "opening" in back or _tokens(observed.get("openings")):
        nodes.append({
            "node_id": "opening", "kind": "OPENING", "layer": 0,
            "dimensions": {"length_cm": max(20.0, height * .55)},
            "attributes": {"placement": back, "proposal_only": True},
        })
    return {"schema": "garment.structure.v1", "nodes": nodes,
            "operations": []}


def _corpus_packages(payload: Mapping[str, Any], *, purpose: str,
                     require_commercial: bool) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from . import corpus_manifest

    raw = payload.get("corpora", ())
    packages = list(raw) if isinstance(raw, Sequence) and not isinstance(
        raw, (str, bytes)) else []
    eligible, refused = [], []
    for index, package in enumerate(packages):
        if not isinstance(package, Mapping):
            refused.append({"index": index, "verdict": "UNKNOWN_BAD_CORPUS_PACKAGE"})
            continue
        checked = corpus_manifest.validate(
            package.get("manifest", {}), require_commercial=require_commercial,
            purpose=purpose)
        records = package.get("records")
        if (checked.get("verdict") != "ANSWER"
                or not isinstance(records, Sequence)
                or isinstance(records, (str, bytes))):
            refused.append({"index": index, "manifest_check": checked,
                            "verdict": checked.get("verdict",
                                                   "UNKNOWN_BAD_CORPUS_RECORDS")})
            continue
        eligible.append({"manifest": checked["manifest"],
                         "manifest_digest": checked["digest"],
                         "records": [copy.deepcopy(dict(row)) for row in records
                                     if isinstance(row, Mapping)]})
    status = {
        "received": len(packages), "eligible": len(eligible),
        "refused": refused,
        "mode": "LOCAL_RIGHTS_GATED" if eligible else "PROCEDURAL_ONLY",
        "network_used": False,
    }
    return eligible, status


def multi_stage_retrieve(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Retrieve ingredients, then construct inspectable 3D hypotheses.

    This is intentionally not a FashionSigLIP wrapper.  Each record is
    compared independently on shape, parts, layers, openings, seam topology,
    and material ranges.  A scalar mean exists only as a stable ordering tie
    breaker; every axis and contradiction remains in the result.
    """
    if not isinstance(payload, Mapping):
        return {"verdict": "UNKNOWN_BAD_HYBRID_RETRIEVAL_REQUEST",
                "why": "request must be an object"}
    observed = _normalise_observation(payload)
    regions = observed["regions"]
    if not regions or any(not isinstance(row, Mapping)
                          or not row.get("region_id") or not row.get("part_id")
                          for row in regions):
        return {"verdict": "UNKNOWN_GARMENT_REGIONS_REQUIRED",
                "why": "at least one typed region_id/part_id pair is required"}
    require_commercial = bool(payload.get("require_commercial", True))
    packages, corpus_status = _corpus_packages(
        payload, purpose="retrieval", require_commercial=require_commercial)
    ranked = []
    for package in packages:
        manifest = package["manifest"]
        for index, record in enumerate(package["records"]):
            record_id = str(record.get("record_id") or record.get("asset_id")
                            or f"record-{index}")
            scored = _score_features(observed, _features(record))
            structure = record.get("structure", record.get("structure_graph"))
            validation = None
            if isinstance(structure, Mapping):
                from . import garment_structure
                validation = garment_structure.build(structure)
            ranked.append({
                "record_id": record_id, "record": record,
                "score": scored, "manifest": manifest,
                "manifest_digest": package["manifest_digest"],
                "valid_structure": (copy.deepcopy(dict(structure))
                                    if isinstance(validation, Mapping)
                                    and validation.get("verdict") == "ANSWER"
                                    else None),
                "structure_validation": validation,
            })
    ranked.sort(key=lambda row: (
        -row["score"]["coverage"],
        -row["score"]["mean_for_ordering_only"],
        row["manifest"]["name"], row["record_id"]))
    max_records = payload.get("max_corpus_candidates", 6)
    if isinstance(max_records, bool) or not isinstance(max_records, int):
        max_records = 6
    ranked = ranked[:max(0, max_records)]

    first_region = regions[0]
    hits, hypotheses, corpus_structure_proposals = [], [], []
    used_backs = set()
    for row in ranked:
        corpus_name = row["manifest"]["name"]
        reference = f"corpus:{corpus_name}:{row['record_id']}"
        provenance = {
            "origin": "LOCAL_RIGHTS_GATED_CORPUS",
            "real_corpus_record": True,
            "corpus": corpus_name,
            "record": row["record_id"],
            "manifest_digest": row["manifest_digest"],
            "license": copy.deepcopy(row["manifest"]["license"]),
            "lineage": copy.deepcopy(row["manifest"]["lineage"]),
            "network_used": False,
        }
        hits.append({
            "part_id": str(first_region["part_id"]),
            "region_id": str(first_region["region_id"]),
            "reference": reference,
            "score": row["score"]["mean_for_ordering_only"],
            # SUBMIT_RETRIEVAL correctly rejects a literal seam_topology
            # field as a construction claim.  The full axis record remains
            # in route.multi_stage_ranking; this visual hit carries only a
            # non-authoritative topology relation score.
            "visual_cues": {"multi_stage": {
                **row["score"],
                "axis_scores": {
                    ("topology_relation" if key == "seam_topology" else key): value
                    for key, value in row["score"]["axis_scores"].items()
                },
                "contradictions": {
                    ("topology_relation" if key == "seam_topology" else key): value
                    for key, value in row["score"]["contradictions"].items()
                },
            }},
            "provenance": provenance, "state": "PROPOSED",
        })
        if row["valid_structure"] is not None:
            back = str(row["record"].get("back_design") or "corpus_back_unspecified")
            if not any(item["back_design"] == back
                       for item in corpus_structure_proposals):
                corpus_structure_proposals.append({
                    "candidate_id": _digest({"reference": reference,
                                             "structure": row["valid_structure"]})[:20],
                    "back_design": back,
                    "structure": row["valid_structure"],
                    "fit": row["score"], "state": "PROPOSED",
                    "provenance": provenance,
                    "assumptions": (["back design supplied by corpus record"]
                                    if row["record"].get("back_design") else
                                    ["corpus did not specify the back design"]),
                })

    # Geometry remains available even with no dataset.  It is never labelled
    # as a corpus hit and always contributes two distinct back alternatives.
    requested_count = payload.get("procedural_candidates", 2)
    if (isinstance(requested_count, bool)
            or not isinstance(requested_count, int)):
        requested_count = 2
    procedural_count = max(2, min(requested_count, 12))
    for index in range(procedural_count):
        available = next((name for name in _DEFAULT_BACKS
                          if name not in used_backs), None)
        back = available or f"procedural_back_alternative_{index + 1}"
        used_backs.add(back)
        structure = _procedural_structure(observed, back, index)
        candidate_id = "geo-" + _digest({"back": back, "structure": structure})[:16]
        reference = f"procedural:{candidate_id}"
        provenance = {
            "origin": "PROCEDURAL_GEOMETRY_COMPOSITION",
            "real_corpus_record": False,
            "corpus": None,
            "engine": "photoloset.geometry-hybrid.v1",
            "network_used": False,
            "note": "constructed from typed observations; not an existing garment search result",
        }
        hits.append({
            "part_id": str(first_region["part_id"]),
            "region_id": str(first_region["region_id"]),
            "reference": reference, "score": 0.0,
            "visual_cues": {"route": "geometry-first", "back_design": back,
                            "single_embedding_winner": False},
            "provenance": provenance, "state": "PROPOSED",
        })
        hypotheses.append({
            "candidate_id": candidate_id, "back_design": back,
            "structure": structure, "state": "PROPOSED",
            "provenance": provenance,
            "assumptions": [
                "back is unobserved and is presented as an alternative",
                "preview mannequin dimensions are not body measurements",
                "seam topology is not a sewing instruction before approval",
            ],
        })

    front_only = bool(observed["front_only"])
    source = {
        "name": ("hybrid:local-rights-corpus-plus-procedural"
                 if ranked else "procedural:geometry-hybrid-no-corpus"),
        "modality": "structure_embedding",
        "license": ("per-hit rights metadata; procedural candidates are generated by Photoloset"
                    if ranked else "Photoloset procedural geometry; no corpus asset"),
        "lineage": (["photoloset:geometry-hybrid.v1"]
                    + sorted({row["manifest"]["name"] for row in ranked})),
        "rights": {"commercial": True, "derivatives": True,
                   "per_hit_manifest_controls_corpus_records": True},
    }
    retrieve_event = {"type": "SUBMIT_RETRIEVAL", "source": source,
                      "hits": hits}
    hypothesis_event = {"type": "SUBMIT_HYPOTHESES",
                        "front_only": front_only,
                        "hypotheses": hypotheses}
    corpus_status.update({
        "records_searched": sum(len(package["records"])
                                for package in packages),
        "corpus_hits": len(ranked),
        "procedural_hits": procedural_count,
        "real_corpus_search_performed": bool(packages),
    })
    return {
        "verdict": "PROPOSED", "source": source, "hits": hits,
        "hypotheses": hypotheses,
        "route": {
            "factory_events": [retrieve_event, hypothesis_event],
            "hypotheses": hypotheses,
            "corpus_structure_proposals": corpus_structure_proposals,
            "multi_stage_ranking": [{
                "corpus": row["manifest"]["name"],
                "record_id": row["record_id"], "fit": row["score"],
                "structure_validation": row["structure_validation"],
            } for row in ranked],
            "next": "render every hypothesis in 3D, then require named digest approval",
            "sewing_search_before_approval": False,
        },
        "corpus_status": corpus_status,
    }
