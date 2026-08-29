# -*- coding: utf-8 -*-
"""The sewing-method search — **and the gate that stands in front of it.**

A method retrieved for the WRONG garment is worse than no method at all: it is
a plausible wrong answer, and plausible wrong answers reach cutting tables. So
the block is on the SEARCH, not on the display of its results, and it is
enforced by the ARGUMENT SURFACE rather than by discipline:

    methods_for(approval_id: str, corpus: str = "") -> dict

and nothing else. No public callable in this module, and no MCP tool that
reaches it, takes a draft, a part graph, a structure, an image path or a
json_text blob — :data:`FORBIDDEN_PARAMETERS` names the shapes that would be a
way in, and a check walks ``inspect.signature`` over this module and over the
tool schemas to hold it. Adding a convenience overload turns the suite red,
which is the point: a gate somebody can walk around is not a gate.

The module reconstructs the structure by reading the ADOPTED ledger entries
the approval names, recomposes it against the current measurements, and
refuses UNKNOWN_APPROVAL_STALE if the recomputed digest differs. That is what
kills an approval after ``zones.apply()`` moves a parameter — the person
approved a shape, not a session.

**Honestly: today this queries nothing.** photoloset has no dependencies and
ships no corpus, and there is no image-to-pattern corpus in this tree, so the
search's real answer right now is UNKNOWN_NO_SEWING_CORPUS naming what would
close it. That is the shipped behaviour rather than a stub returning ``[]``,
because an empty list says "there are no methods" and the true sentence is
"nothing was asked".

**What it queries when a backend is present**: the APPROVED STRUCTURE, per
part — never the image, never the embedding. One query record per part
instance: part, family, variant, ports, connected_to, params, panels,
seam_labels. That is the form the pattern corpora actually index, and it is
the form the approval gate has a digest of. ``register_corpus`` refuses a
backend declaring ``modality="image_embedding"`` outright: on this project's
own benchmark Marqo-FashionSigLIP beat Apple by dMRR +0.292 for same-garment
retrieval, but its material ranking flipped 8.5% under horizontal flip and
uniform noise was indistinguishable from real photographs by margin.
Similarity is usable for "which garment" and not as a ranking of construction,
and that measured finding is a type error here rather than a paragraph nobody
reads.

Corpora that would serve, named as TARGETS — this tree has none of them and
nothing about them has been measured here, so verify every count and licence
from the dataset card before any of it reaches an output: SewFactory (from the
Sewformer work on garment sewing-pattern reconstruction from a single image,
SIGGRAPH Asia 2023), GarmentCodeData (ECCV 2024), and GarmentCode itself as a
retrieval target rather than a dataset, since a hit that returns a parametric
program is checkable and ``compose`` already speaks parameters. NOT for this
stage: DeepFashion/DeepFashion2 (image similarity, no construction) and
CLOTH3D/4D-Dress (drape, not construction).

**The independence trap, closed before any corpus is wired.**
``cross._source_key`` normalises spelling but cannot see lineage, and its own
docstring concedes that independence is the writer's claim. GarmentCodeData is
GENERATED FROM GarmentCode; a second corpus built on the same generator would
be counted as a second independent source and would BUY a generic construction
claim on one root. So ``derived_from()`` is mandatory at registration and
:func:`methods_for` refuses UNKNOWN_SHARED_LINEAGE when two agreeing corpora
share a root, naming both.

This module's prose is English (like ``mcp.py``, the boundary it is read
through); ``tests/run_checks.py`` sweeps its outputs through ``i18n`` with the
rest, so "0 untranslated" keeps covering it.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

SHAPE_NOT_APPROVED = "UNKNOWN_SHAPE_NOT_APPROVED"
APPROVAL_STALE = "UNKNOWN_APPROVAL_STALE"
NO_SEWING_CORPUS = "UNKNOWN_NO_SEWING_CORPUS"
EMBEDDING_NOT_CONSTRUCTION = "UNKNOWN_EMBEDDING_IS_NOT_CONSTRUCTION"
SHARED_LINEAGE = "UNKNOWN_SHARED_LINEAGE"
NO_RECORDS = "UNKNOWN_NO_RECORDS_BOUND"
BAD_CORPUS = "UNKNOWN_BAD_CORPUS"
NO_SUCH_CORPUS = "UNKNOWN_NO_SUCH_CORPUS"

#: Parameter names that would be a way past the gate. **A shape must not be
#: expressible in this module's argument surface**: if a caller can hand the
#: search a draft, the approval is decoration.
FORBIDDEN_PARAMETERS = frozenset({
    "draft", "draft_json", "drafts", "graph", "graph_json", "part_graph",
    "structure", "structure_json", "parts", "pieces", "instances",
    "connections", "port_finish", "declaration", "shape", "spec", "sheet",
    "solid", "image", "image_path", "image_ref", "image_id", "photo",
    "json_text", "json", "payload", "blob", "body", "data", "text",
})

#: Modalities a construction corpus may declare. **An embedding is not one.**
CONSTRUCTION_MODALITIES = ("sewing_pattern", "parametric_program",
                           "panel_graph")

#: The corpora that would close UNKNOWN_NO_SEWING_CORPUS. Named as targets;
#: this tree ships none of them.
WOULD_SERVE = ("SewFactory (Sewformer, SIGGRAPH Asia 2023)",
               "GarmentCodeData (ECCV 2024)",
               "GarmentCode (the parametric program, as a retrieval target)")

#: Corpora that are SYNTHETIC: a retrieved method is a program that produced a
#: shape, not a record of how a tailor sewed one. The note rides every landed
#: claim.
SYNTHETIC_NOTE = ("this corpus is synthetic: a retrieved method is a program "
                  "that produced a shape, not a record of how a tailor sewed "
                  "one")

_CORPORA: Dict[str, Any] = {}
_BOUND: Dict[str, Any] = {"ledger": None, "measures": None,
                          "store": None, "rights": None}


# ---------------------------------------------------------------------------
# Registration and binding
# ---------------------------------------------------------------------------

class SewingCorpus:
    """The interface a construction corpus implements. **Standard library
    only, no model and no network client anywhere in this package.**"""

    def name(self) -> str:                       # pragma: no cover - contract
        raise NotImplementedError

    def licence(self) -> str:                    # pragma: no cover - contract
        raise NotImplementedError

    def derived_from(self):                      # pragma: no cover - contract
        raise NotImplementedError

    def modality(self) -> str:                   # pragma: no cover - contract
        raise NotImplementedError

    def find(self, query: Dict[str, Any]):       # pragma: no cover - contract
        raise NotImplementedError


def _call(obj: Any, attr: str, default: Any = None) -> Any:
    fn = getattr(obj, attr, None)
    if fn is None:
        return default
    try:
        return fn() if callable(fn) else fn
    except Exception:                                        # noqa: BLE001
        return default


def register_corpus(corpus: Any) -> Dict[str, Any]:
    """Register a construction corpus. **Refusals are return values.**

    ``modality`` is checked first and hardest: an image-embedding backend is
    refused by name, because this project measured its similarity flipping
    8.5% under a horizontal flip and will not let that be read as a ranking of
    construction. ``derived_from`` is mandatory even when empty of parents,
    because it is the only thing that can tell two corpora from one generator.
    """
    modality = _call(corpus, "modality", "")
    if modality == "image_embedding":
        return {"verdict": EMBEDDING_NOT_CONSTRUCTION,
                "modality": modality,
                "why": "an embedding answers 'which image is most similar'. "
                       "On this project's own benchmark that similarity was "
                       "good for same-garment retrieval (dMRR +0.292 over "
                       "Apple) and NOT trustworthy as a ranking of "
                       "construction: material ranking flipped 8.5% under a "
                       "horizontal flip and uniform noise was "
                       "indistinguishable from real photographs by margin",
                "how_to_close":
                    f"a construction corpus declares one of "
                    f"{list(CONSTRUCTION_MODALITIES)} and returns panels, "
                    f"seams and a stitch order. Use resemble.register() for "
                    f"the similarity question, which is a different stage"}
    if modality not in CONSTRUCTION_MODALITIES:
        return {"verdict": BAD_CORPUS, "which": modality,
                "known": list(CONSTRUCTION_MODALITIES),
                "how_to_close": f"declare modality() as one of "
                                f"{list(CONSTRUCTION_MODALITIES)}"}
    name = str(_call(corpus, "name", "") or "").strip()
    licence = str(_call(corpus, "licence", "") or "").strip()
    lineage = _call(corpus, "derived_from", None)
    if not name:
        return {"verdict": BAD_CORPUS, "field": "name",
                "how_to_close": "a corpus names itself; the name rides every "
                                "claim it lands"}
    if not licence:
        return {"verdict": BAD_CORPUS, "field": "licence", "corpus": name,
                "how_to_close": "a corpus states its licence. A method whose "
                                "terms nobody recorded reaches a cutting "
                                "table with no terms"}
    if lineage is None or not isinstance(lineage, (list, tuple)):
        return {"verdict": BAD_CORPUS, "field": "derived_from",
                "corpus": name,
                "why": "the store can see that two names differ; it cannot "
                       "see that they came from one generator",
                "how_to_close": "derived_from() returns the roots this corpus "
                                "was generated from — an empty tuple when it "
                                "has none, never nothing"}
    if not callable(getattr(corpus, "find", None)):
        return {"verdict": BAD_CORPUS, "field": "find", "corpus": name,
                "how_to_close": "find(query) -> {verdict, methods, searched}"}
    _CORPORA[name] = corpus
    return {"verdict": "ANSWER", "registered": name, "licence": licence,
            "modality": modality, "derived_from": list(lineage),
            "corpora": len(_CORPORA)}


def corpora() -> List[Dict[str, Any]]:
    """Every registered corpus, with its licence and its lineage."""
    return [{"name": n,
             "licence": _call(c, "licence", ""),
             "modality": _call(c, "modality", ""),
             "derived_from": list(_call(c, "derived_from", ()) or ()),
             "synthetic": bool(_call(c, "synthetic", True))}
            for n, c in sorted(_CORPORA.items())]


def bind(ledger: Any = None, measures: Any = None,
         store: Any = None, rights: Any = None) -> Dict[str, Any]:
    """Bind the RECORDS this module reads. **Not a shape — a ledger.**

    The approval lives in the ledger and the geometry is recomputed from the
    measurements, so those are what this module needs. It does not accept, and
    has no argument for, the shape itself.
    """
    if ledger is not None:
        _BOUND["ledger"] = ledger
    if measures is not None:
        _BOUND["measures"] = measures
    if store is not None:
        _BOUND["store"] = store
    if rights is not None:
        _BOUND["rights"] = rights
    return {"verdict": "ANSWER",
            "bound": sorted(k for k, v in _BOUND.items() if v is not None)}


def reset() -> Dict[str, Any]:
    """Forget every corpus and every binding."""
    n = len(_CORPORA)
    _CORPORA.clear()
    for k in _BOUND:
        _BOUND[k] = None
    return {"verdict": "ANSWER", "cleared": n}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def _adopted(ledger: Any, part: str, aspect: str,
             value: Optional[str] = None) -> Any:
    for e in getattr(ledger, "entries", []):
        if e.part != part or e.aspect != aspect:
            continue
        if value is not None and e.value != value:
            continue
        if e.kind == "observation" and str(e.adopted_by or "").strip():
            return e
    return None


def _approved(approval_id: str) -> Dict[str, Any]:
    """Is there an ADOPTED approval for this shape, and is it still true?

    Reads the ledger, rebuilds the approved structure from the entries the
    approval names, recomposes it against the current measurements, and
    compares digests. Nothing here takes a shape from the caller.
    """
    from . import compose as _compose
    from . import confirm as _confirm

    ledger = _BOUND["ledger"]
    measures = _BOUND["measures"]
    if ledger is None or measures is None:
        return {"verdict": NO_RECORDS,
                "how_to_close": "sewing_search.bind(ledger=..., "
                                "measures=...) with the records the approval "
                                "was written into"}
    key = str(approval_id or "").strip()
    if not key:
        return {"verdict": SHAPE_NOT_APPROVED,
                "why": "no approval was named. The sewing-method search is "
                       "not reachable without one: a method retrieved for the "
                       "wrong garment is a plausible wrong answer, and "
                       "plausible wrong answers reach cutting tables",
                "how_to_close": "confirm.approve(sheet, answers, by, ledger) "
                                "returns the approval id"}
    entry = _adopted(ledger, _confirm.APPROVAL_PART, _confirm.APPROVAL_ASPECT,
                     key)
    if entry is None:
        return {"verdict": SHAPE_NOT_APPROVED, "approval_id": key,
                "why": "no ADOPTED entry (part='garment', "
                       "aspect='shape_approved') carries this digest. An "
                       "unadopted proposal is not an approval",
                "how_to_close": "answer the confirmation sheet and approve it "
                                "with a name; Ledger.adopt refuses an empty "
                                "one"}
    structure_entry = _adopted(ledger, _confirm.APPROVAL_PART,
                               _confirm.STRUCTURE_ASPECT)
    if structure_entry is None:
        return {"verdict": SHAPE_NOT_APPROVED, "approval_id": key,
                "why": "the approval names no structure, so there is nothing "
                       "to recompose and nothing to compare",
                "how_to_close": "approve through confirm.approve(), which "
                                "adopts the structure beside the digest"}
    try:
        held = json.loads(structure_entry.value)
    except (json.JSONDecodeError, TypeError):
        return {"verdict": SHAPE_NOT_APPROVED, "approval_id": key,
                "why": "the adopted structure does not read back as JSON",
                "how_to_close": "approve again through confirm.approve()"}
    graph = (held or {}).get("graph")
    if not graph:
        return {"verdict": SHAPE_NOT_APPROVED, "approval_id": key,
                "why": "the adopted structure carries no part graph",
                "how_to_close": "approve again, passing graph= to "
                                "confirm.approve()"}

    draft = _compose.compose(graph, measures)
    if draft.get("verdict") != "ANSWER":
        return {"verdict": APPROVAL_STALE, "approval_id": key,
                "what_moved": "composition",
                "now": draft.get("verdict"),
                "why": "the approved structure no longer composes against the "
                       "current measurements",
                "how_to_close": draft.get("how_to_close")
                                or "recompose, confirm and approve again"}
    now = _confirm.shape_digest(draft, graph)
    if now.get("digest") != key:
        moved = ("structure"
                 if now.get("structure_digest") != held.get(
                     "structure_digest")
                 else "geometry")
        return {"verdict": APPROVAL_STALE, "approval_id": key,
                "what_moved": moved,
                "now": now.get("digest"),
                "structure_now": now.get("structure_digest"),
                "structure_then": held.get("structure_digest"),
                "why": f"the shape has moved since it was approved "
                       f"({moved}). A person approved a shape, not a session",
                "how_to_close": "show the new shape, get it confirmed and "
                                "approved again"}
    return {"verdict": "ANSWER", "approval_id": key,
            "by": entry.adopted_by, "graph": graph, "draft": draft,
            "digest": now["digest"],
            "structure_digest": now["structure_digest"]}


# ---------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------

def _queries(graph: Dict[str, Any], draft: Dict[str, Any]
             ) -> List[Dict[str, Any]]:
    """One query record per part instance.

    **The structure, never the image** — and never the embedding.
    """
    connected: Dict[str, List[str]] = {}
    ports: Dict[str, List[str]] = {}
    for c in graph.get("connections") or []:
        a, b = c.get("a"), c.get("b")
        if not a or not b:
            continue
        connected.setdefault(a[0], []).append(b[0])
        connected.setdefault(b[0], []).append(a[0])
        ports.setdefault(a[0], []).append(a[1])
        ports.setdefault(b[0], []).append(b[1])
    panels: Dict[str, List[str]] = {}
    for p in draft.get("pieces") or []:
        panels.setdefault(str(p.get("instance") or p["name"]), []).append(
            p["name"])
    seams: Dict[str, List[str]] = {}
    where = {p["name"]: str(p.get("instance") or p["name"])
             for p in (draft.get("pieces") or [])}
    for s in draft.get("seam_specs") or []:
        for end in (s.get("a"), s.get("b")):
            if end and end[0] in where:
                lst = seams.setdefault(where[end[0]], [])
                if s.get("label") and s["label"] not in lst:
                    lst.append(s["label"])
    out = []
    for inst in graph.get("parts") or []:
        iid = str(inst.get("instance"))
        params = dict(inst.get("params") or {})
        out.append({
            "part": inst.get("part"),
            "instance": iid,
            "family": inst.get("part"),
            "variant": params.get("variant"),
            "ports": sorted(set(ports.get(iid, []))),
            "connected_to": sorted(set(connected.get(iid, []))),
            "params": {k: params[k] for k in sorted(params)},
            "panels": sorted(panels.get(iid, [])),
            "seam_labels": sorted(seams.get(iid, [])),
        })
    return out


def _lineage_clash(names: Sequence[str]) -> Optional[Dict[str, Any]]:
    """Two corpora that agree but share a generator are ONE source.

    GarmentCodeData is generated from GarmentCode. Counting both as
    independent would buy a generic construction claim on one root, which is
    the one place the two-source rule can be paid in counterfeit currency.
    """
    roots = {n: set(_call(_CORPORA[n], "derived_from", ()) or ()) | {n}
             for n in names if n in _CORPORA}
    ordered = sorted(roots)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            shared = roots[a] & roots[b]
            if shared:
                return {"verdict": SHARED_LINEAGE,
                        "which": [a, b],
                        "shared_roots": sorted(shared),
                        "why": "these two corpora agree, but they are not two "
                               "sources: they share a root, so the agreement "
                               "is one generator agreeing with itself. "
                               "cross._source_key can see that two NAMES "
                               "differ and cannot see lineage",
                        "how_to_close": "count them as one source, or find a "
                                        "corpus with a different root"}
    return None


def _hybrid_query(factory_state: Dict[str, Any], candidate: Dict[str, Any]
                  ) -> Dict[str, Any]:
    """Typed construction query reconstructed from a verified approval."""
    structure = candidate.get("structure")
    structure = structure if isinstance(structure, dict) else {}
    nodes = [row for row in structure.get("nodes", ())
             if isinstance(row, dict)]
    operations = [row for row in structure.get("operations", ())
                  if isinstance(row, dict)]
    material = {}
    approval = factory_state.get("material_approval")
    sheet = factory_state.get("material_sheet")
    if isinstance(approval, dict) and isinstance(sheet, dict):
        selected = next((row for row in sheet.get("candidates", ())
                         if isinstance(row, dict)
                         and row.get("candidate_id") == approval.get("candidate_id")), None)
        if isinstance(selected, dict):
            material = selected.get("material_ranges", selected)
    return {
        "shape": candidate.get("shape", candidate.get("fit", {})),
        "parts": [str(row.get("kind")) for row in nodes if row.get("kind")],
        "layers": sorted({int(row.get("layer", 0)) for row in nodes
                          if isinstance(row.get("layer", 0), int)}),
        "openings": [row.get("attributes", {}) for row in nodes
                     if row.get("kind") == "OPENING"],
        "seam_topology": [{"kind": row.get("kind"),
                           "source": row.get("source"),
                           "target": row.get("target")}
                          for row in operations],
        "material_ranges": material if isinstance(material, dict) else {},
        "structure": structure,
        "pattern_digest": (factory_state.get("pattern", {}) or {}).get("digest")
                          if isinstance(factory_state.get("pattern"), dict) else None,
    }


def _procedural_methods(query: Dict[str, Any], approval_id: str
                        ) -> List[Dict[str, Any]]:
    """Two inspectable assembly hypotheses, never corpus evidence."""
    nodes = [row for row in query.get("structure", {}).get("nodes", ())
             if isinstance(row, dict)]
    ordered = sorted(nodes, key=lambda row: (int(row.get("layer", 0)),
                                             str(row.get("node_id", ""))))
    node_steps = [f"prepare primitive {row.get('node_id')} ({row.get('kind')})"
                  for row in ordered]
    openings = [row for row in ordered if row.get("kind") == "OPENING"]
    close = ([f"finish proposed opening {row.get('node_id')} last"
              for row in openings]
             or ["reserve a dressability opening; placement remains proposed"])
    common = {
        "state": "PROPOSED", "for_approval": approval_id,
        "origin": "BUILTIN_PROCEDURAL_CONSTRUCTION",
        "real_corpus_record": False,
        "manufacturing_validated": False,
        "requires_human_and_deterministic_validation": True,
        "provenance": {
            "kind": "PROCEDURAL_CONSTRUCTION_HYPOTHESIS",
            "engine": "photoloset.sewing-planner.v1",
            "corpus": None, "real_corpus_record": False,
            "note": "derived from approved topology; not a retrieved tailoring precedent",
        },
    }
    return [
        {**common, "method_id": "procedural:layer-inside-out",
         "strategy": "assemble lower layers before overlays",
         "steps": node_steps + close,
         "unknowns": ["stitch class", "seam allowance", "machine settings",
                      "empirical seam strength"]},
        {**common, "method_id": "procedural:opening-last",
         "strategy": "stabilise load paths and close the opening last",
         "steps": node_steps[:1] + ["join validated structural operations"]
                  + node_steps[1:] + close,
         "unknowns": ["edge finish", "notions", "interfacing",
                      "operator-feasible sewing order"]},
    ]


def _hybrid_search_factory_state(factory_state: Any, packages: Any = (), *,
                                 require_commercial: bool = True
                                 ) -> Dict[str, Any]:
    """Search local construction records after the factory approval gate.

    Private by design: the public sewing-search surface still accepts only an
    approval id.  The MCP wrapper passes a complete factory state, and this
    function recomputes its digest-bound approval before reading a structure.
    """
    from . import corpus_manifest
    from . import garment_factory
    from . import retrieval_hypothesis

    if (not isinstance(factory_state, dict)
            or factory_state.get("schema") != garment_factory.SCHEMA):
        return {"verdict": SHAPE_NOT_APPROVED,
                "why": "a persisted garment.factory.v1 state is required"}
    candidate = garment_factory._approval_candidate(factory_state)
    if not isinstance(candidate, dict):
        return {"verdict": SHAPE_NOT_APPROVED,
                "why": "named digest-bound structure approval is required"}
    approval = factory_state["shape_approval"]
    approval_id = str(approval["approval_id"])
    raw_packages = (list(packages) if isinstance(packages, (tuple, list))
                    else [])
    eligible, refused = [], []
    for index, package in enumerate(raw_packages):
        if not isinstance(package, dict):
            refused.append({"index": index,
                            "verdict": "UNKNOWN_BAD_CORPUS_PACKAGE"})
            continue
        checked = corpus_manifest.validate(
            package.get("manifest", {}),
            require_commercial=bool(require_commercial), purpose="sewing")
        records = package.get("records")
        if (checked.get("verdict") != "ANSWER"
                or not isinstance(records, (tuple, list))):
            refused.append({"index": index,
                            "verdict": checked.get("verdict",
                                                   "UNKNOWN_BAD_CORPUS_RECORDS"),
                            "manifest_check": checked})
            continue
        eligible.append({"manifest": checked["manifest"],
                         "manifest_digest": checked["digest"],
                         "records": [dict(row) for row in records
                                     if isinstance(row, dict)]})

    query = _hybrid_query(factory_state, candidate)
    query_features = {name: query.get(name)
                      for name in retrieval_hypothesis._FEATURE_AXES}
    corpus_methods = []
    for package in eligible:
        manifest = package["manifest"]
        for index, record in enumerate(package["records"]):
            method = record.get("method", record.get("construction"))
            if method is None and any(key in record for key in (
                    "steps", "seams", "stitches", "stitch_order")):
                method = {key: record[key] for key in (
                    "steps", "seams", "stitches", "stitch_order", "tools")
                          if key in record}
            if not isinstance(method, dict) or not method:
                continue
            scored = retrieval_hypothesis._score_features(
                query_features, retrieval_hypothesis._features(record))
            record_id = str(record.get("record_id") or record.get("asset_id")
                            or f"record-{index}")
            corpus_methods.append({
                **method,
                "method_id": str(method.get("method_id")
                                 or f"corpus:{manifest['name']}:{record_id}"),
                "state": "PROPOSED", "for_approval": approval_id,
                "fit": scored, "origin": "LOCAL_RIGHTS_GATED_CORPUS",
                "real_corpus_record": True,
                "manufacturing_validated": bool(
                    record.get("manufacturing_validated", False)),
                "provenance": {
                    "kind": "CONSTRUCTION_CORPUS",
                    "corpus": manifest["name"], "record": record_id,
                    "manifest_digest": package["manifest_digest"],
                    "license": manifest["license"],
                    "lineage": manifest["lineage"],
                    "real_corpus_record": True, "network_used": False,
                },
            })
    corpus_methods.sort(key=lambda row: (
        -row["fit"]["coverage"], -row["fit"]["mean_for_ordering_only"],
        row["method_id"]))
    procedural = _procedural_methods(query, approval_id)
    methods = corpus_methods + procedural
    status = {
        "received": len(raw_packages), "eligible": len(eligible),
        "refused": refused,
        "records_searched": sum(len(row["records"]) for row in eligible),
        "corpus_methods": len(corpus_methods),
        "procedural_methods": len(procedural),
        "real_corpus_search_performed": bool(eligible),
        "network_used": False,
        "mode": ("LOCAL_RIGHTS_GATED_PLUS_PROCEDURAL" if eligible
                 else "PROCEDURAL_ONLY"),
    }
    source = {
        "name": ("hybrid:local-sewing-corpus-plus-procedural"
                 if corpus_methods else "procedural:sewing-planner-no-corpus"),
        "real_corpus_records_present": bool(corpus_methods),
        "procedural_records_present": True,
    }
    lineage = [{"source": "photoloset:sewing-planner.v1"}]
    lineage.extend({"source": row["manifest"]["name"]}
                   for row in eligible)
    output_manifest = {
        "schema": "garment.corpus-manifest.v1",
        "name": "photoloset-hybrid-sewing-proposals",
        "version": "1",
        "license": {
            "url": "urn:photoloset:builtin-procedural-sewing:v1",
            "rights": {"commercial_use": "allowed",
                       "derivatives": "allowed",
                       "redistribution": "allowed"},
            "scope": "Photoloset-generated proposal records only; source corpus records retain per-method licences",
        },
        "lineage": lineage,
        "modalities": ["sewing_construction"],
        "record_format": {
            "units": "explicit_per_field",
            "schema_url": "urn:photoloset:hybrid-sewing-method:v1",
        },
        "generated": True,
        "real_corpus_records_present": bool(corpus_methods),
        "procedural_records_present": True,
    }
    factory_event = {
        "type": "SUBMIT_SEWING_METHODS",
        "manifest": output_manifest,
        "methods": methods,
        "require_commercial": bool(require_commercial),
    }
    return {
        "verdict": "PROPOSED", "source": source, "methods": methods,
        "manifest": output_manifest,
        "real_corpus_records_present": bool(corpus_methods),
        "route": {
            "shape_approval_id": approval_id,
            "query_basis": "approved structure, never image embedding",
            "next": "deterministic sewability/strength/comfort validation",
            "factory_event": factory_event,
        },
        "corpus_status": status,
    }


def methods_for(approval_id: str, corpus: str = "") -> Dict[str, Any]:
    """Sewing methods for an APPROVED shape. **The gate is the first line.**

    ``approval_id`` is the digest ``confirm.approve`` returned. This function
    has no other way in: it takes an approval and a corpus name and nothing
    else, and it reads the shape back out of the adopted ledger entries rather
    than from the caller.
    """
    gate = _approved(approval_id)
    if gate["verdict"] != "ANSWER":
        return gate

    chosen = [corpus] if corpus else sorted(_CORPORA)
    unknown = [c for c in chosen if c not in _CORPORA]
    if unknown and corpus:
        return {"verdict": NO_SUCH_CORPUS, "which": unknown,
                "registered": sorted(_CORPORA),
                "how_to_close": "register it with "
                                "sewing_search.register_corpus(corpus)"}
    if not chosen:
        return {
            "verdict": NO_SEWING_CORPUS,
            "approval_id": gate["approval_id"],
            "approved_by": gate["by"],
            "would_serve": list(WOULD_SERVE),
            "why": "the shape IS approved and the search still cannot run: "
                   "photoloset ships no corpus and there is no "
                   "image-to-pattern corpus in this tree. An empty list would "
                   "say 'there are no methods'; nothing was asked",
            "how_to_close":
                f"register one with sewing_search.register_corpus(corpus). "
                f"The corpora that would serve: {', '.join(WOULD_SERVE)}. "
                f"Verify every count and licence from the dataset card — "
                f"nothing about them has been measured in this tree",
        }

    queries = _queries(gate["graph"], gate["draft"])
    methods: List[Dict[str, Any]] = []
    trouble: List[Dict[str, Any]] = []
    for name in chosen:
        c = _CORPORA[name]
        licence = str(_call(c, "licence", ""))
        synthetic = bool(_call(c, "synthetic", True))
        for q in queries:
            try:
                raw = c.find(dict(q))
            except Exception as exc:                        # noqa: BLE001
                trouble.append({"corpus": name, "instance": q["instance"],
                                "verdict": "UNKNOWN_CORPUS_RAISED",
                                "why": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            if isinstance(raw, dict) and str(
                    raw.get("verdict", "ANSWER")).startswith(
                        ("UNKNOWN_", "CONTESTED_")):
                trouble.append({"corpus": name, "instance": q["instance"],
                                **{k: v for k, v in raw.items()
                                   if k != "methods"}})
                continue
            got = raw.get("methods") if isinstance(raw, dict) else raw
            for m in (got or []):
                if not isinstance(m, dict):
                    continue
                rec = dict(m)
                rec["corpus"] = name
                rec.setdefault("part", q["part"])
                rec.setdefault("instance", q["instance"])
                rec.setdefault("family", q["family"])
                rec.setdefault("variant", q["variant"])
                rec["licence"] = rec.get("licence") or licence
                rec["synthetic"] = bool(rec.get("synthetic", synthetic))
                if rec["synthetic"]:
                    rec["synthetic_note"] = SYNTHETIC_NOTE
                methods.append(rec)

    # **Agreement is checked for lineage BEFORE it is spent.**
    agreements: Dict[Any, List[str]] = {}
    for m in methods:
        key = (m.get("instance"), m.get("family"), m.get("variant"))
        who = agreements.setdefault(key, [])
        if m["corpus"] not in who:
            who.append(m["corpus"])
    for key, who in sorted(agreements.items(), key=repr):
        if len(who) < 2:
            continue
        clash = _lineage_clash(who)
        if clash is not None:
            return {**clash, "agreed_on": list(key),
                    "approval_id": gate["approval_id"],
                    "searched": {"corpora": chosen,
                                 "instances": [q["instance"]
                                               for q in queries]}}

    landed = _land(methods, agreements, chosen, queries, gate)
    return {"verdict": "ANSWER",
            "approval_id": gate["approval_id"],
            "approved_by": gate["by"],
            "methods": methods,
            "searched": {"corpora": chosen,
                         "instances": [q["instance"] for q in queries],
                         "queries": queries},
            "trouble": trouble,
            "landed": landed,
            "queried": "the approved structure, per part. Never the image and "
                       "never an embedding",
            "empty_is_an_answer":
                "methods == [] here means the corpora ran and found nothing "
                "within 'searched'. The record of having searched is on the "
                "rights ledger, with its scope"}


def _land(methods: Sequence[Dict[str, Any]], agreements: Dict[Any, List[str]],
          chosen: Sequence[str], queries: Sequence[Dict[str, Any]],
          gate: Dict[str, Any]) -> Dict[str, Any]:
    """Land the methods: ``cited`` on the cross, provenance on the rights
    ledger. **Two corpora from one root were already refused above.**"""
    store = _BOUND["store"]
    rights = _BOUND["rights"]
    seated: List[Dict[str, Any]] = []
    provenance: List[Dict[str, Any]] = []
    scope = ("corpora=" + "/".join(chosen) + "; instances="
             + "/".join(q["instance"] for q in queries))
    root = f'methods:{gate["digest"]}'
    linked: set = set()
    if store is not None and methods:
        store.put(root, "for_approval",
                  {"approval_id": gate["digest"], "by": gate["by"]},
                  "declared", "sewing_search")

    for m in methods:
        source = (f'{m["corpus"]}'
                  + (f'@{m["version"]}' if m.get("version") else "")
                  + (f'; id={m["id"]}' if m.get("id") else "")
                  + ("; SYNTHETIC" if m.get("synthetic") else ""))
        if store is not None:
            core = f'{root}:{m.get("instance")}'
            key = f'method:{m.get("step", m.get("id", "1"))}'
            r = store.put(core, key,
                          {"corpus": m["corpus"], "id": m.get("id"),
                           "panels": m.get("panels"),
                           "seams": m.get("seams"),
                           "stitch_order": m.get("stitch_order"),
                           "licence": m.get("licence"),
                           "synthetic": bool(m.get("synthetic"))},
                          "cited", source)
            # **Reachable from the approval it was retrieved for.** A method
            # core nobody can walk to is a method nobody can trace back to
            # the shape a person approved, which is the one thing this whole
            # gate exists to keep attached.
            seat = r.get("core")
            if seat and seat not in linked:
                linked.add(seat)
                store.link((seat, ""), (root, ""), "part_of")
            seated.append({"core": core, "key": key, "kind": "cited",
                           "source": source, "verdict": r.get("verdict"),
                           "seated_in": seat})
        if rights is not None:
            try:
                rights.generic(str(m.get("part") or m.get("instance")),
                               f'method:{m.get("id", "1")}',
                               source=str(m["corpus"]),
                               note=SYNTHETIC_NOTE if m.get("synthetic")
                               else "")
                provenance.append({"part": m.get("part"),
                                   "claim": "generic",
                                   "source": m["corpus"]})
            except ValueError as exc:
                provenance.append({"verdict": str(exc).split(":", 1)[0],
                                   "why": str(exc)})

    if not methods and rights is not None:
        for q in queries:
            try:
                rights.no_match(str(q["part"]), "method", scope=scope)
                provenance.append({"part": q["part"], "claim": "no_match",
                                   "scope": scope})
            except ValueError as exc:
                provenance.append({"verdict": str(exc).split(":", 1)[0],
                                   "why": str(exc)})
    return {"seated": seated, "provenance": provenance, "scope": scope,
            "agreements": [{"on": list(k), "corpora": v}
                           for k, v in sorted(agreements.items(), key=repr)],
            "note": "a method is cited (support+), never measured. Two "
                    "independent corpora agreeing buy a generic construction "
                    "claim on the rights ledger; one leaves it UNCHECKED"}
