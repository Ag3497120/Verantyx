# -*- coding: utf-8 -*-
"""Retrieval — **per part, and never readable at the part's own address.**

A single front-facing photograph can say a garment RESEMBLES A and B. It can
also mislead, and the two are indistinguishable from the outside. So this
module does the smallest honest thing: it asks the question per part, it lands
what comes back as a PROPOSAL in the store's quarantine, and it refuses — by
name, with how_to_close — every question it has no equipment to answer.

**Why per part.** An embedding model produces ONE global vector for the whole
image, and one vector answers one question: which image is most similar. An
unclassifiable garment is COMPOSITIONAL — cape + bodice + high-low skirt +
sleeve — and a global embedding cannot say "the cape resembles A while the
skirt resembles B". Per-part retrieval therefore needs segmentation BEFORE
embedding, so ``per_part`` refuses a whole-image-only stack by name rather
than answering the easier question and calling it the harder one.

**Why the results are not rankings.** On this project's own earlier benchmark
Marqo-FashionSigLIP beat Apple by dMRR +0.292 for same-garment retrieval, but
its material ranking flipped 8.5% under horizontal flip and uniform noise was
indistinguishable from real photographs by margin. Similarity is usable for
"which garment" and is NOT trustworthy as a ranking of construction. The
structural expression of that finding is :func:`land`: the key is derived from
the ASPECT alone, so two backends that disagree collide at ONE address and
come back CONTESTED with both sides carried and neither chosen. Put the source
in the key and they become two addresses, both ANSWER, and somebody downstream
sorts them by score. That mutation is pinned by a falsifier.

**Nothing is registered here.** photoloset has no dependencies and ships no
model, no weights and no network client. ``backends()`` is empty on a fresh
import and a check measures that rather than asserting it. The only thing in
this file that answers anything is :func:`install_fixture`, which is named
``fixture:`` at every level it can be seen from — see its docstring for why a
fixture that could pass for a backend is how a demo becomes a claim.

This module's prose is English (like ``mcp.py``, the boundary it is read
through); ``tests/run_checks.py`` sweeps its outputs through ``i18n`` with the
rest, so "0 untranslated" keeps covering it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import cross as _cross

NO_BACKEND = "UNKNOWN_NO_RETRIEVAL_BACKEND"
WHOLE_IMAGE_ONLY = "UNKNOWN_WHOLE_IMAGE_ONLY"
NO_SEGMENTER = "UNKNOWN_NO_SEGMENTER"
NO_SUCH_ASPECT = "UNKNOWN_NO_SUCH_ASPECT"
BAD_BACKEND = "UNKNOWN_BAD_BACKEND"
FIXTURE_UNDECLARED = "UNKNOWN_FIXTURE_NOT_DECLARED"
NO_SCOPE = "UNKNOWN_NO_SCOPE"
UNNAMED_SOURCE = "UNKNOWN_UNNAMED_SOURCE"

#: What a backend can see. **The modality is the whole argument of this
#: module**: ``image_embedding`` is one vector for one image and can answer
#: :func:`whole` only.
MODALITIES: Tuple[str, ...] = (
    "image_embedding",     # one global vector per image — whole garment only
    "region_embedding",    # one vector per supplied region — per part
    "structure",           # a model that returns parts, not vectors
)

#: Roles, the same two ``prompts.py`` registers: a centre model that
#: decomposes, a parallel model whose "prompt" is a query bank.
ROLES: Tuple[str, ...] = ("center", "parallel")

#: The aspects a retrieval hit may claim, closed. **The source never enters
#: this set** — that is the rule the contest depends on.
ASPECTS: Tuple[str, ...] = ("resembles", "family", "variant")
ASPECT_PREFIXES: Tuple[str, ...] = ("param:", "port:")

# Similarity is not a single whole-garment class.  These axes remain separate
# all the way to rear/construction candidate review.
FEATURE_AXES: Tuple[str, ...] = ("part", "structure", "seam", "material")
CANDIDATE_USE_SCOPE: Tuple[str, ...] = (
    "PROPOSE_REAR_CANDIDATE", "PROPOSE_CONSTRUCTION_CANDIDATE")

#: Every model id a fixture may be registered under starts with this.
FIXTURE_PREFIX = "fixture:"

#: Registered backends, by model id. **Empty at import, and a check in
#: ``tests/run_checks.py`` starts a fresh interpreter to measure that.**
_BACKENDS: Dict[str, Dict[str, Any]] = {}
_SEGMENTERS: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(model_id: str, role: str, modality: str,
             fn: Callable[[Dict[str, Any]], Dict[str, Any]],
             *, version: str = "", fixture: bool = False) -> Dict[str, Any]:
    """Register a retrieval backend. **Refusals are return values.**

    ``fn`` is called with one query record and returns
    ``{"hits": [...]}`` or a list of hits. It is never called at import and
    never by this module unless somebody registered it.

    The ``fixture`` flag and the ``fixture:`` prefix must agree. A fixture
    that could be mistaken for a real backend is how a demo becomes a claim,
    so the mistake is a refusal in both directions rather than a convention.
    """
    if not isinstance(model_id, str) or not model_id.strip():
        return {"verdict": BAD_BACKEND, "why": "a backend needs a model id",
                "how_to_close": "register(model_id, role, modality, fn)"}
    if role not in ROLES:
        return {"verdict": BAD_BACKEND, "which": role,
                "known": list(ROLES),
                "how_to_close": f"role is one of {'/'.join(ROLES)}"}
    if modality not in MODALITIES:
        return {"verdict": BAD_BACKEND, "which": modality,
                "known": list(MODALITIES),
                "how_to_close": f"modality is one of {'/'.join(MODALITIES)}"}
    if not callable(fn):
        return {"verdict": BAD_BACKEND, "why": "fn is not callable",
                "how_to_close": "pass the function that runs the query"}
    named_fixture = model_id.startswith(FIXTURE_PREFIX)
    if named_fixture != bool(fixture):
        return {"verdict": FIXTURE_UNDECLARED,
                "model_id": model_id, "fixture": bool(fixture),
                "why": "a fixture answers from a table and measured nothing; "
                       "if it can be mistaken for a model, its answers can be "
                       "mistaken for measurements",
                "how_to_close": f"a fixture is registered with fixture=True "
                                f"AND a model id starting {FIXTURE_PREFIX!r}; "
                                f"a real backend with neither"}
    _BACKENDS[model_id] = {"model_id": model_id, "role": role,
                           "modality": modality, "fn": fn,
                           "version": version or "unversioned",
                           "fixture": bool(fixture)}
    return {"verdict": "ANSWER", "registered": model_id,
            "modality": modality, "fixture": bool(fixture),
            "backends": len(_BACKENDS)}


def register_segmenter(name: str,
                       fn: Callable[[Any, Sequence[Dict[str, Any]]],
                                    Dict[str, Any]],
                       *, fixture: bool = False) -> Dict[str, Any]:
    """Register the stage that turns one image into a region per part."""
    if not isinstance(name, str) or not name.strip() or not callable(fn):
        return {"verdict": BAD_BACKEND,
                "why": "a segmenter needs a name and a callable",
                "how_to_close": "register_segmenter(name, fn)"}
    named_fixture = name.startswith(FIXTURE_PREFIX)
    if named_fixture != bool(fixture):
        return {"verdict": FIXTURE_UNDECLARED, "model_id": name,
                "fixture": bool(fixture),
                "how_to_close": f"a fixture segmenter is registered with "
                                f"fixture=True AND a name starting "
                                f"{FIXTURE_PREFIX!r}"}
    _SEGMENTERS[name] = {"name": name, "fn": fn, "fixture": bool(fixture)}
    return {"verdict": "ANSWER", "registered": name,
            "fixture": bool(fixture), "segmenters": len(_SEGMENTERS)}


def backends() -> List[Dict[str, Any]]:
    """Every registered backend, without its callable. Sorted by model id."""
    return [{k: v for k, v in b.items() if k != "fn"}
            for _id, b in sorted(_BACKENDS.items())]


def segmenters() -> List[Dict[str, Any]]:
    return [{"name": s["name"], "fixture": s["fixture"]}
            for _n, s in sorted(_SEGMENTERS.items())]


def reset() -> Dict[str, Any]:
    """Forget every registration. For the checks, and for a caller who wants
    to prove to itself that nothing is registered."""
    n = len(_BACKENDS) + len(_SEGMENTERS)
    _BACKENDS.clear()
    _SEGMENTERS.clear()
    return {"verdict": "ANSWER", "cleared": n}


# ---------------------------------------------------------------------------
# The fixture. **Loudly a fixture.**
# ---------------------------------------------------------------------------

def install_fixture(table: Dict[str, List[Dict[str, Any]]],
                    *, model_id: str = "fixture:table",
                    segmenter: bool = True) -> Dict[str, Any]:
    """A backend that answers from ``table``. **It measured nothing.**

    This exists so the loop can be driven end to end without a model. It is
    marked in four places that a caller cannot miss: the model id starts
    ``fixture:``, ``register`` refuses it under any other name, every hit it
    returns carries ``"fixture": True``, and the source string it stamps onto
    every landed claim begins with the same prefix — so a claim that reaches
    the cross from here says so at its own address, forever.

    ``table`` is keyed by part instance (``"cape:1"``) and holds hit records
    ``{"aspect": ..., "value": {...}}``. A missing key is not an error: it is
    a search that found nothing, which is a positive answer with a scope.
    """
    def _fn(query: Dict[str, Any]) -> Dict[str, Any]:
        inst = query.get("instance") or ""
        out = []
        for hit in table.get(inst, []):
            rec = copy.deepcopy(hit)
            rec["instance"] = inst
            rec["part"] = query.get("part")
            rec["fixture"] = True
            out.append(rec)
        return {"hits": out}

    r = register(model_id, "parallel", "region_embedding", _fn,
                 version="fixture", fixture=True)
    if r["verdict"] != "ANSWER" or not segmenter:
        return r

    def _seg(image_ref: Any, parts: Sequence[Dict[str, Any]]
             ) -> Dict[str, Any]:
        return {"regions": {p.get("instance"):
                            f"fixture-region:{p.get('instance')}"
                            for p in parts}}

    s = register_segmenter("fixture:boxes", _seg, fixture=True)
    return {"verdict": "ANSWER", "backend": r, "segmenter": s,
            "warning": "a fixture answers from a table and measured nothing"}


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------

def _no_backend(question: str) -> Dict[str, Any]:
    return {
        "verdict": NO_BACKEND,
        "question": question,
        "backends": [],
        "why": "nothing was asked. An empty result would say 'nothing is "
               "similar', which is a different sentence and this module does "
               "not have the equipment to say it",
        "how_to_close":
            "register one with resemble.register(model_id, role, modality, "
            "fn); photoloset has no dependencies and ships no model. "
            "prompts.for_model() already holds the prompt/query-bank side for "
            "lmstudio:qwen3.6:35b-a3b and siglip:marqo-fashionSigLIP",
    }


def _run(chosen: Sequence[Dict[str, Any]], queries: Sequence[Dict[str, Any]]
         ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Call each backend once per query. A backend that raises is a refusal
    record, not an exception crossing this boundary."""
    hits: List[Dict[str, Any]] = []
    trouble: List[Dict[str, Any]] = []
    for b in chosen:
        for q in queries:
            try:
                raw = b["fn"](dict(q))
            except Exception as exc:                        # noqa: BLE001
                trouble.append({"backend": b["model_id"],
                                "query": dict(q),
                                "verdict": "UNKNOWN_BACKEND_RAISED",
                                "why": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            got = raw.get("hits") if isinstance(raw, dict) else raw
            for h in (got or []):
                if not isinstance(h, dict):
                    trouble.append({"backend": b["model_id"],
                                    "verdict": "UNKNOWN_MALFORMED_HIT",
                                    "why": f"a hit is {type(h).__name__}, "
                                           f"not an object"})
                    continue
                rec = dict(h)
                rec.setdefault("instance", q.get("instance"))
                rec.setdefault("part", q.get("part"))
                rec["model_id"] = b["model_id"]
                rec["model_version"] = b["version"]
                rec["fixture"] = bool(rec.get("fixture") or b["fixture"])
                hits.append(rec)
    return hits, trouble


def _candidate_proposals(hits: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Project per-part hits into bounded rear/construction proposals only."""
    proposals: List[Dict[str, Any]] = []
    feature_keys = {
        "part": ("part_features", "target_part", "part"),
        "structure": ("structure_features", "construction_features",
                      "structure", "construction_regime", "rear_structure"),
        "seam": ("seam_features", "seam_topology", "seams", "openings"),
        "material": ("material_features", "material", "materials"),
    }
    for hit in hits:
        instance = str(hit.get("instance") or "")
        if not instance:
            continue
        raw_scores = hit.get("axis_scores", hit.get("similarity_axes", {}))
        raw_scores = raw_scores if isinstance(raw_scores, dict) else {}
        scores: Dict[str, float] = {}
        for axis in FEATURE_AXES:
            value = raw_scores.get(axis)
            if (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(float(value))):
                scores[axis] = float(value)
        profile = {
            axis: {key: copy.deepcopy(hit[key]) for key in feature_keys[axis]
                   if key in hit and hit[key] is not None}
            for axis in FEATURE_AXES
        }
        identity = {
            "instance": instance,
            "part": hit.get("part"),
            "ref": hit.get("ref"),
            "model_id": hit.get("model_id"),
            "axis_scores": scores,
            "feature_profile": profile,
        }
        digest = hashlib.sha256(json.dumps(
            identity, ensure_ascii=False, sort_keys=True, default=str,
            separators=(",", ":")).encode("utf-8")).hexdigest()[:16]
        proposals.append({
            "candidate_id": f"retrieval-candidate-{digest}",
            "instance": instance,
            "part": hit.get("part"),
            "reference": hit.get("ref"),
            "state": "PROPOSED_RETRIEVAL_UNCONFIRMED",
            "axis_scores": scores,
            "feature_profile": profile,
            "missing_feature_axes": [
                axis for axis in FEATURE_AXES
                if axis not in scores and not profile[axis]],
            "use_scope": list(CANDIDATE_USE_SCOPE),
            "requires_candidate_3d_and_named_human_approval": True,
            "not_a_pattern_sewing_or_manufacturing_fact": True,
            "source": source_of(hit),
        })
    return sorted(proposals, key=lambda row: (
        str(row["instance"]), str(row.get("part")), row["candidate_id"]))


def whole(image_ref: Any, *, queries: Sequence[str] = (),
          image_id: str = "") -> Dict[str, Any]:
    """The whole-garment question: which garment is this like.

    **This is the question the owner said cannot carry the loop**, and it is
    kept here so the refusal in :func:`per_part` has somewhere to point. Its
    answer is never the input to construction.
    """
    if not _BACKENDS:
        return _no_backend("whole")
    chosen = [b for _id, b in sorted(_BACKENDS.items())]
    q = [{"scope": "whole", "image": image_ref, "image_id": image_id,
          "queries": list(queries), "instance": "", "part": ""}]
    hits, trouble = _run(chosen, q)
    return {"verdict": "ANSWER", "hits": hits,
            "searched": {"scope": "whole",
                         "backends": [b["model_id"] for b in chosen],
                         "model_versions": {b["model_id"]: b["version"]
                                            for b in chosen},
                         "queries": list(queries),
                         "image_id": image_id,
                         "corpora": sorted({str(h.get("corpus"))
                                            for h in hits
                                            if h.get("corpus")})},
            "trouble": trouble,
            "not_a_ranking": "these hits are not ordered and carry no score. "
                             "Similarity is usable for 'which garment' and "
                             "not as a ranking of construction",
            "note": "a whole-image answer cannot say which PART resembles "
                    "what. For that, ask per_part()"}


def per_part(image_ref: Any, parts: Sequence[Dict[str, Any]], *,
             regions: Optional[Dict[str, Any]] = None,
             queries: Sequence[str] = (),
             image_id: str = "") -> Dict[str, Any]:
    """The compositional question: what does EACH part resemble.

    ``parts`` is the centre model's decomposition — records carrying at least
    ``instance`` and ``part``. ``regions`` maps instance -> whatever the
    embedding side needs to look at only that part; without it a registered
    segmenter is asked, and without one of those this refuses by name.
    """
    if not _BACKENDS:
        return _no_backend("per_part")
    ordered = [b for _id, b in sorted(_BACKENDS.items())]
    # **The modality test.** One global vector cannot answer a per-part
    # question; answering it anyway with the whole-image number is exactly
    # the mistake this module exists to make impossible.
    per_part_capable = [b for b in ordered
                        if b["modality"] != "image_embedding"]
    if not per_part_capable:
        return {
            "verdict": WHOLE_IMAGE_ONLY,
            "backends": [b["model_id"] for b in ordered],
            "missing_stage": NO_SEGMENTER,
            "why": "every registered backend emits ONE global embedding of "
                   "the whole image. One vector answers one question — which "
                   "image is most similar. An unclassifiable garment is "
                   "compositional (cape + bodice + high-low skirt + sleeve) "
                   "and a global embedding cannot say the cape resembles A "
                   "while the skirt resembles B",
            "how_to_close":
                "register a segmenter that returns a region per part "
                "instance, or ask the whole-garment question instead with "
                "resemble.whole()",
        }

    want = [p for p in parts if p.get("instance")]
    have = dict(regions or {})
    if not have and want:
        for _n, seg in sorted(_SEGMENTERS.items()):
            try:
                got = seg["fn"](image_ref, list(want))
            except Exception:                               # noqa: BLE001
                continue
            have.update((got or {}).get("regions") or {})
            if have:
                break
    unregioned = [p["instance"] for p in want if p["instance"] not in have]
    if unregioned:
        return {
            "verdict": NO_SEGMENTER,
            "which": sorted(unregioned),
            "segmenters": segmenters(),
            "why": "per-part retrieval is segmentation BEFORE embedding. "
                   "Without a region per part instance the only thing that "
                   "can be embedded is the whole image, which answers a "
                   "different question",
            "how_to_close":
                "register a segmenter that returns a region per part "
                "instance, or ask the whole-garment question instead with "
                "resemble.whole()",
        }

    qs = [{"scope": "part", "image": image_ref, "image_id": image_id,
           "instance": p["instance"], "part": p.get("part"),
           "region": have.get(p["instance"]),
           "queries": list(queries), "feature_axes": list(FEATURE_AXES),
           "candidate_use_scope": list(CANDIDATE_USE_SCOPE)} for p in want]
    hits, trouble = _run(per_part_capable, qs)
    return {"verdict": "ANSWER", "hits": hits,
            "candidate_proposals": _candidate_proposals(hits),
            "candidate_contract": {
                "feature_axes": list(FEATURE_AXES),
                "use_scope": list(CANDIDATE_USE_SCOPE),
                "single_embedding_winner": False,
                "manufacturing_authority": False,
            },
            "searched": {"scope": "part",
                         "backends": [b["model_id"]
                                      for b in per_part_capable],
                         "model_versions": {b["model_id"]: b["version"]
                                            for b in per_part_capable},
                         "instances": [p["instance"] for p in want],
                         "parts": {p["instance"]: p.get("part")
                                   for p in want},
                         "queries": list(queries),
                         "image_id": image_id,
                         "regions": sorted(have),
                         "corpora": sorted({str(h.get("corpus"))
                                            for h in hits
                                            if h.get("corpus")})},
            "trouble": trouble,
            "not_a_ranking": "these hits are not ordered and carry no score",
            "empty_is_an_answer":
                "hits == [] here means the backends ran and found nothing "
                "within 'searched'. That is a positive answer with a scope, "
                "not a refusal"}


# ---------------------------------------------------------------------------
# Landing
# ---------------------------------------------------------------------------

def _aspect_ok(aspect: str) -> bool:
    return (aspect in ASPECTS
            or any(aspect.startswith(p) for p in ASPECT_PREFIXES))


def _key(hit: Dict[str, Any]) -> str:
    """**The address is the aspect. The source never enters it.**

    If two backends write ``resembles:marqo`` and ``resembles:openclip`` the
    store sees two different addresses, both resolve ANSWER, and somebody
    downstream sorts them by score — a ranking, which is the one thing this
    loop forbids. Written to the SAME address they collide and come back
    CONTESTED with both sides carried and neither chosen.
    """
    aspect = str(hit.get("aspect") or "")
    return aspect


def source_of(hit: Dict[str, Any]) -> str:
    """model id + prompt version + corpus + evidence region, in the format
    ``prompts.parse_decomposition`` already emits."""
    bits = [str(hit.get("model_id") or "unnamed-model")]
    version = hit.get("prompt_version") or hit.get("model_version")
    if version:
        bits.append(f"prompt={version}")
    if hit.get("corpus"):
        bits.append(f"corpus={hit['corpus']}")
    region = hit.get("evidence") or hit.get("region")
    if region:
        bits.append(f"evidence={region}")
    return "; ".join(bits)


def core_of(image_id: str, instance: str) -> str:
    """``look:<image_id>:<part>:<n>`` — the part instance in THIS look."""
    return f"look:{image_id}:{instance}"


def look_core(image_id: str) -> str:
    return f"look:{image_id}"


def land(store: Any, rights: Any, result: Dict[str, Any], *,
         image_id: str = "", subject: str = "garment") -> Dict[str, Any]:
    """Land a retrieval answer. **Every hit is kind="proposed".**

    ``proposed`` is the only kind whose ``KIND_ARM`` entry is ``None``: it
    carries no mass into any arm, it lands in the quarantine the store mints
    for it, and ``store.resolve(part_address, aspect)`` answers
    UNKNOWN_NOT_IN_CROSS until a person adopts it. No other kind is correct
    here — ``measured``/``cited`` are support+ and would let a cosine score
    buy the same seat as a tape measure; ``specific``/``declared`` are kind-
    and would make the machine's guess "what this declaration decided";
    ``generic`` is kind+ and is the thing two sources are supposed to BUY,
    not the thing one search returns.

    A search that found NOTHING writes nothing to the cross — it offers the
    store ``kind="no_match"``, which the store refuses with
    UNKNOWN_ABSENCE_IS_NOT_A_CLAIM — and the record of having searched goes
    to ``rights.no_match(scope=...)`` instead, which refuses a blank scope.
    "We looked in these places and found nothing" is writable; "found
    nothing" alone is not.
    """
    if not isinstance(result, dict):
        return {"verdict": "UNKNOWN_BAD_ARGUMENTS",
                "why": "land() takes the object whole() or per_part() "
                       "returned, so the scope of the search rides with it"}
    if result.get("verdict") != "ANSWER":
        return {"verdict": "UNKNOWN_NOTHING_TO_LAND",
                "carried": result.get("verdict"),
                "why": "a refusal is not a result. Landing it would seat the "
                       "absence of equipment as a claim about the garment",
                "how_to_close": result.get("how_to_close", "")}

    searched = dict(result.get("searched") or {})
    image_id = image_id or str(searched.get("image_id") or "")
    scope = _scope_text(searched)
    hits = list(result.get("hits") or [])

    landed: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    rights_rows: List[Dict[str, Any]] = []

    root = look_core(image_id)
    linked: set = set()
    if hits:
        store.put(root, "look", {"image_id": image_id}, "declared",
                  "resemble:land")
        # **A refused edge is a fact, not a shrug.** A look whose part_of
        # edge did not land is a core nobody can reach from the garment, and
        # a store that drops it silently reads as if the landing worked.
        up = store.link((root, ""), (subject, ""), "part_of")
        if up.get("verdict") != "ANSWER":
            refused.append({"verdict": up.get("verdict"), "core": root,
                            "to": subject, "why": up.get("why"),
                            "how_to_close": up.get("how_to_close")})

    for hit in hits:
        aspect = str(hit.get("aspect") or "")
        if not _aspect_ok(aspect):
            refused.append({"verdict": NO_SUCH_ASPECT, "which": aspect,
                            "known": list(ASPECTS) + [p + "<name>"
                                                      for p in
                                                      ASPECT_PREFIXES],
                            "how_to_close": "a hit claims one of the closed "
                                            "aspects; a new one is a change "
                                            "to resemble.ASPECTS, in a diff"})
            continue
        instance = str(hit.get("instance") or "")
        if not instance:
            refused.append({"verdict": "UNKNOWN_NO_PART_INSTANCE",
                            "aspect": aspect,
                            "how_to_close": "a per-part hit names the part "
                                            "instance it is about"})
            continue
        core = core_of(image_id, instance)
        key = _key(hit)
        source = source_of(hit)
        if not source.strip():
            refused.append({"verdict": UNNAMED_SOURCE, "core": core,
                            "key": key,
                            "how_to_close": "a hit names the model that "
                                            "produced it"})
            continue
        value = _value_of(hit)
        r = store.put(core, key, value, "proposed", source)
        # **Link the core the store actually seated into**, which for a
        # proposal is the quarantine it minted (``…#proposed``) and never the
        # part's own address — ``put`` creates a core only together with a
        # seat, so ``look:img1:cape:1`` does not exist at all and an edge to
        # it is refused UNKNOWN_DANGLING_EDGE. Measured: four such refusals
        # per landing, discarded, while the quarantine sat reachable from
        # nobody.
        #
        # ``part_of`` is safe to follow here because ``_closure`` does not:
        # the landing becomes navigable from the look without becoming
        # READABLE at the look's address or at the part's.
        seated = r.get("core")
        if seated and seated not in linked:
            linked.add(seated)
            down = store.link((seated, ""), (root, ""), "part_of")
            if down.get("verdict") != "ANSWER":
                refused.append({"verdict": down.get("verdict"),
                                "core": seated, "to": root,
                                "why": down.get("why")})
        rec = {"core": core, "key": key, "kind": "proposed",
               "instance": instance, "part": hit.get("part") or instance,
               "value": value,
               "source": source, "verdict": r.get("verdict"),
               "seated_in": r.get("core"), "arm": r.get("arm"),
               "fixture": bool(hit.get("fixture"))}
        if r.get("verdict") == "ANSWER":
            landed.append(rec)
        else:
            refused.append(rec)
        # **The provenance claim rides the rights ledger, not the cross.**
        # One corpus saying "garments of this family are built this way" is
        # "traceable to a source", not "general knowledge"; the ledger prices
        # that at GENERIC_MIN_SOURCES = 2 exactly as the cross does.
        if rights is not None and hit.get("corpus"):
            try:
                rights.generic(str(hit.get("part") or instance), aspect,
                               source=str(hit["corpus"]),
                               note="proposed by retrieval; not adopted")
                rights_rows.append({"part": hit.get("part") or instance,
                                    "aspect": aspect,
                                    "claim": "generic",
                                    "source": hit["corpus"]})
            except ValueError as exc:
                refused.append({"verdict": str(exc).split(":", 1)[0],
                                "why": str(exc)})

    not_seated: List[Dict[str, Any]] = []
    if not hits:
        # **The searched-and-found-nothing path.** It offers the store the
        # one kind that carries no arm and is not a claim at all, so the
        # refusal comes from the store rather than from a convention here.
        for instance, part in sorted((searched.get("parts") or {}).items()):
            core = core_of(image_id, instance)
            r = store.put(core, "resembles",
                          {"ref": None, "searched": scope},
                          "no_match", _searched_source(searched))
            not_seated.append({"core": core, "key": "resembles",
                               "verdict": r.get("verdict"),
                               "stored": bool(r.get("stored"))})
            if rights is not None:
                try:
                    rights.no_match(str(part or instance), "resembles",
                                    scope=scope)
                    rights_rows.append({"part": part or instance,
                                        "aspect": "resembles",
                                        "claim": "no_match", "scope": scope})
                except ValueError as exc:
                    return {"verdict": NO_SCOPE, "why": str(exc),
                            "how_to_close": "name what was searched — a "
                                            "'found nothing' with no scope "
                                            "says nothing at all"}
        if not searched.get("parts") and rights is not None:
            try:
                rights.no_match(subject, "resembles", scope=scope)
                rights_rows.append({"part": subject, "aspect": "resembles",
                                    "claim": "no_match", "scope": scope})
            except ValueError as exc:
                return {"verdict": NO_SCOPE, "why": str(exc),
                        "how_to_close": "name what was searched"}

    return {"verdict": "ANSWER",
            "state": "PROPOSED_RETRIEVAL_UNCONFIRMED",
            "landed": landed,
            "refused": refused,
            "not_seated": not_seated,
            "rights": rights_rows,
            "searched": searched,
            "scope": scope,
            "unreadable_at_the_part_address":
                "every landed claim is kind='proposed' and sits in the "
                "quarantine the store minted for it. resolve() at the part's "
                "own address answers UNKNOWN_NOT_IN_CROSS until a person "
                "adopts it",
            "contested": [c for c in store.contested()
                          if str(c.get("core", "")).startswith(
                              f"look:{image_id}:")]}


def _value_of(hit: Dict[str, Any]) -> Dict[str, Any]:
    """The claim's value: ref, corpus, family, variant, params. **Nothing
    that could be read as a score.**"""
    out: Dict[str, Any] = {}
    for field in ("ref", "corpus", "family", "variant"):
        if hit.get(field) is not None:
            out[field] = hit[field]
    params = hit.get("params")
    if isinstance(params, dict) and params:
        out["params"] = {str(k): params[k] for k in sorted(params)}
    if hit.get("fixture"):
        out["fixture"] = True
    return out


def _searched_source(searched: Dict[str, Any]) -> str:
    who = ", ".join(searched.get("backends") or []) or "unnamed-backend"
    return f"{who}; scope={_scope_text(searched)}"


def _scope_text(searched: Dict[str, Any]) -> str:
    """What was searched, as one line.

    **A blank scope is refused upstream** — "found nothing" with no scope
    says nothing at all.
    """
    bits = []
    if searched.get("backends"):
        bits.append("backends=" + "/".join(searched["backends"]))
    if searched.get("corpora"):
        bits.append("corpora=" + "/".join(searched["corpora"]))
    if searched.get("queries"):
        bits.append(f'queries={len(searched["queries"])}')
    if searched.get("instances"):
        bits.append("instances=" + "/".join(searched["instances"]))
    return "; ".join(bits)


def structure_from(result: Dict[str, Any], *, image_id: str = ""
                   ) -> Dict[str, Any]:
    """The retrieved STRUCTURE, per part instance, ready for
    ``compose.graph_from``. **Read off the hits, never off the pixels.**

    Contested aspects are carried as contests, not resolved: an instance
    whose family or variant is claimed two ways comes back with both and a
    typed note, and ``compose.graph_from`` will refuse it.
    """
    if result.get("verdict") != "ANSWER":
        return {"verdict": "UNKNOWN_NOTHING_TO_CONSTRUCT",
                "carried": result.get("verdict"),
                "how_to_close": result.get("how_to_close", "")}
    searched = dict(result.get("searched") or {})
    by_inst: Dict[str, Dict[str, Any]] = {}
    contested: List[Dict[str, Any]] = []
    for hit in result.get("hits") or []:
        inst = str(hit.get("instance") or "")
        if not inst:
            continue
        rec = by_inst.setdefault(inst, {
            "instance": inst,
            "part": hit.get("part") or (searched.get("parts") or {}).get(inst),
            "params": {}, "sources": [], "refs": []})
        aspect = str(hit.get("aspect") or "")
        src = source_of(hit)
        if src not in rec["sources"]:
            rec["sources"].append(src)
        if aspect == "resembles" and hit.get("ref"):
            rec["refs"].append({"ref": hit["ref"], "corpus": hit.get("corpus"),
                                "source": src})
        for field in ("family", "variant"):
            if aspect != field or hit.get(field) is None:
                continue
            if field in rec and rec[field] != hit[field]:
                contested.append({"instance": inst, "aspect": field,
                                  "sides": [rec[field], hit[field]]})
            rec[field] = hit[field]
        if aspect.startswith("param:"):
            name = aspect.split(":", 1)[1]
            val = hit.get("value", hit.get("params", {}).get(name))
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                rec["params"][name] = float(val)
    return {"verdict": "ANSWER",
            "label": "",
            "image_id": image_id or str(searched.get("image_id") or ""),
            "instances": [by_inst[k] for k in sorted(by_inst)],
            "connections": [],
            "port_finish": {},
            "contested": contested,
            "from": "retrieved structure, not pixels",
            "authority": {
                "rear_or_construction_candidate_only": True,
                "requires_candidate_3d_digest_and_named_human_approval": True,
                "manufacturing_ready": False,
            },
            "searched": searched}
