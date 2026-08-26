# -*- coding: utf-8 -*-
"""Confirmation — **the 3D is the falsifier for the retrieval.**

"cosine 0.83 to garment A" cannot be checked by a human. "Here is the garment
that similarity implies" can be checked in two seconds. That is the whole
reason this stage exists: it converts an unverifiable claim into a verifiable
one, which is what this project is for.

So the sheet does NOT ask "does this look right". It asks one structural claim
at a time — part, aspect, value, and the retrieval source that proposed it —
and takes yes / no / cannot_tell. :func:`reject` requires ``which`` to name
claim ids from the sheet; free text is only ever a note beside a named claim.
**There is no field in which "the mesh looks bad" can be recorded**, so a
correct retrieval cannot be killed by an ugly render.

And the render says what it does not claim, by quoting the objects themselves
rather than by a sentence written here: ``solid["not_a_simulation"]``,
``solid["assumed"]`` (an ellipse depth ratio, an assumption and not a
measurement), ``draft["seam_allowance"]``, ``draft["not_a_published_system"]``
— plus one line this module adds, that the surface is a fixed number of facets
of an assumed ellipse and its smoothness carries no information about the
pattern.

**The gate.** :func:`approve` writes through ``garment.Ledger.propose()`` +
``.adopt()``, which is the adoption path the rest of the project already
uses. ``Ledger.adopt`` raises UNKNOWN_NO_ADOPTER on an empty name, and that
check lives in the ledger rather than in the door or the UI precisely because
an earlier version put it in the door and measurement V60 walked around it.
Nothing raises out of this module: the ledger's refusal is caught and returned
as the typed value it should have been.

This module's prose is English (like ``mcp.py``, the boundary it is read
through); ``tests/run_checks.py`` sweeps its outputs through ``i18n`` with the
rest, so "0 untranslated" keeps covering it.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from typing import Any, Dict, List, Optional, Sequence

from . import convergence as _convergence
from .garment_solid import ASSUMED_DEPTH_RATIO, SEGMENTS, _ellipse, _tube

NO_CLAIM = "UNKNOWN_NO_SUCH_CLAIM"
UNNAMED_REJECTION = "UNKNOWN_UNNAMED_REJECTION"
NO_ADOPTER = "UNKNOWN_NO_ADOPTER"
NO_LEDGER = "UNKNOWN_NO_LEDGER"
UNANSWERED = "UNKNOWN_UNANSWERED_CLAIM"
REJECTED = "UNKNOWN_CLAIM_REJECTED"
NOT_COMPOSED = "UNKNOWN_SHAPE_NOT_COMPOSED"
NO_SOLID = "UNKNOWN_NO_SOLID_YET"
NO_REJECTER = "UNKNOWN_NO_REJECTER"

ANSWERS = ("yes", "no", "cannot_tell")

#: A piece that declares a FOLD port is drawn as one half of the body
#: (わ裁ち), so the edges on it are half of their circumference. A piece with
#: no fold port — a sleeve, drawn whole — is not doubled. **The factor is read
#: off the piece's own ports**, not off a table of part names.
HALF_BODY_FACTOR = 2.0

#: Ports that are folds. A fold is not a circumference.
FOLD_PORTS = ("center_front", "center_back")

#: Ports that are seams rather than girths. A shoulder line joins two panels.
SEAM_PORTS = ("shoulder_l", "shoulder_r")

#: An armhole is the TOP OF A TUBE on a sleeve and a HOLE CUT IN ONE on a
#: torso panel. The two are told apart by the fold: a piece drawn against a
#: fold is a torso half, and its armhole is a hole rather than a girth.
ARMHOLE_PORTS = ("armhole_l", "armhole_r")

#: The declared top-to-bottom order of the girth ports. **This order is
#: declared, not measured**: a neckline is above a waist because that is what
#: those words mean, and no part of the draft says so.
PORT_ORDER = ("neck", "armhole_l", "armhole_r", "waist",
              "cuff_l", "cuff_r", "hem")


# ---------------------------------------------------------------------------
# Canonical form. The same function as tests/coat_digest.canon, and a check
# pins that it IS the same — a digest computed two ways is two digests.
# ---------------------------------------------------------------------------

def canon(o: Any) -> Any:
    """Total, type-preserving canonical form. Floats -> exact bit pattern.

    No tolerance and no rounding: a change in the last bit of the last
    coordinate is a different number here. That is the point — an approval
    that survives a moved shape is an approval for a different garment.
    """
    if isinstance(o, float):
        return ["f64", struct.pack(">d", o).hex()]
    if isinstance(o, bool):
        return ["bool", o]
    if isinstance(o, int):
        return ["int", str(o)]
    if o is None:
        return ["null"]
    if isinstance(o, str):
        return ["str", o]
    if isinstance(o, (list, tuple)):
        return [type(o).__name__, [canon(x) for x in o]]
    if isinstance(o, dict):
        return ["dict", [[canon(k), canon(v)] for k, v in
                         sorted(o.items(), key=lambda kv: repr(kv[0]))]]
    if isinstance(o, set):
        return ["set", sorted(repr(x) for x in o)]
    if hasattr(o, "__dict__"):
        return ["obj:" + type(o).__name__, canon(dict(vars(o)))]
    return ["repr:" + type(o).__name__, repr(o)]


def _md5(o: Any) -> str:
    return hashlib.md5(json.dumps(canon(o), sort_keys=True,
                                  separators=(",", ":")).encode()).hexdigest()


def _instances_of(draft: Dict[str, Any],
                  graph: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The part instances and their design parameters, sorted.

    From the graph when there is one; otherwise from the draft's own zone
    catalogue, which is the numbered list of design parameters compose()
    returns and is derived from the same instances.
    """
    if graph:
        out = []
        for i in graph.get("parts") or []:
            params = {str(k): v for k, v in sorted(
                (i.get("params") or {}).items())}
            out.append({"instance": i.get("instance"), "part": i.get("part"),
                        "params": params})
        return sorted(out, key=lambda r: str(r["instance"]))
    by: Dict[str, Dict[str, Any]] = {}
    for z in draft.get("zones") or []:
        rec = by.setdefault(str(z.get("instance")), {
            "instance": z.get("instance"), "part": z.get("part"),
            "params": {}})
        if z.get("current") is not None:
            rec["params"][str(z.get("param"))] = z["current"]
    for rec in by.values():
        rec["params"] = {k: rec["params"][k] for k in sorted(rec["params"])}
    return sorted(by.values(), key=lambda r: str(r["instance"]))


def shape_digest(draft: Dict[str, Any],
                 graph: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The digest an approval is FOR. **Two of them, so a stale refusal can
    say what moved.**

    ``digest`` covers the structure AND the geometry: label, sorted instances
    with part and params, sorted connections, sorted port_finish, and each
    piece's named edges with their exact IEEE-754 lengths.
    ``structure_digest`` covers only the first four, so an approval that dies
    can say whether the retrieval changed or only a parameter moved.
    """
    if draft.get("verdict") != "ANSWER":
        return {"verdict": NOT_COMPOSED, "carried": draft.get("verdict"),
                "how_to_close": "compose the graph first; a refusal has no "
                                "shape to approve"}
    structure = {
        "label": draft.get("label") or "",
        "instances": _instances_of(draft, graph),
        "connections": sorted(
            [[list(c.get("a") or []), list(c.get("b") or [])]
             for c in ((graph or {}).get("connections") or [])],
            key=repr),
        "port_finish": {str(k): {str(p): v for p, v in sorted(
            (fin or {}).items())}
            for k, fin in sorted(((graph or {}).get("port_finish")
                                  or {}).items())},
    }
    geometry = []
    for p in sorted(draft.get("pieces") or [], key=lambda x: str(x["name"])):
        geometry.append({
            "name": p["name"], "instance": p.get("instance"),
            "edges": {name: float(e["length"])
                      for name, e in sorted((p.get("edges") or {}).items())},
        })
    return {"verdict": "ANSWER",
            "digest": _md5({"structure": structure, "geometry": geometry}),
            "structure_digest": _md5(structure),
            "pieces": len(geometry),
            "instances": [i["instance"] for i in structure["instances"]],
            "exact": "floats are canonicalised to their IEEE-754 bit "
                     "patterns; there is no tolerance here"}


# ---------------------------------------------------------------------------
# The solid, built from the composed pieces' own edges
# ---------------------------------------------------------------------------

def _girth(edge, factor):
    """A ring's girth: **the draft's own edge length**, times the half-body
    factor. There is no other source for this number, and that is the whole
    property — a girth taken from a body ratio would not move when the pattern
    does, and the confirmation would stop being a falsifier for the retrieval.
    """
    return float(edge["length"]) * factor


def _centroid(points):
    xs = [float(q[0]) for q in points]
    ys = [float(q[1]) for q in points]
    if not xs:
        return 0.0, 0.0
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _edge_names(value: Any) -> List[str]:
    return [value] if isinstance(value, str) else list(value or [])


def _intra_instance_seams(draft: Dict[str, Any]) -> List[Any]:
    """(piece, edge) pairs consumed by a seam whose two ends are the SAME
    part instance. Those edges join panels; they are not girths."""
    where = {p["name"]: str(p.get("instance") or p["name"])
             for p in (draft.get("pieces") or [])}
    out = []
    for s in draft.get("seam_specs") or []:
        a, b = s.get("a"), s.get("b")
        if not a or not b:
            continue
        if where.get(a[0]) != where.get(b[0]):
            continue
        out.append((a[0], a[1]))
        out.append((b[0], b[1]))
    return out


def _levels_for(pieces: Sequence[Dict[str, Any]],
                joined: Sequence[Any]) -> List[Dict[str, Any]]:
    """The rings of one instance, read entirely off its own pieces.

    A ring is either an edge a GIRTH PORT names — the closed vocabulary
    ``PORT_ORDER``, minus the folds and the shoulder seam — or an edge that no
    port names and no seam inside this instance consumes, which is how the
    skirt's hem gets a ring although ``draft_skirt_panel`` publishes no
    ``hem`` port.

    The girth is the sum of the ``length`` fields of those edges across the
    instance's pieces, doubled for a piece that declares a fold port because
    such a piece draws one half of the body. **Every girth here is a number
    the draft computed**: nothing falls back to a body ratio, and an instance
    this cannot read two levels for is reported skipped rather than invented.
    """
    ported: Dict[str, Dict[str, Any]] = {}
    named: set = set()
    folded = {p["name"]: any(port in FOLD_PORTS
                             for port in (p.get("ports") or {}))
              for p in pieces}
    for p in pieces:
        edges = p.get("edges") or {}
        factor = HALF_BODY_FACTOR if folded[p["name"]] else 1.0
        for port, value in (p.get("ports") or {}).items():
            for name in _edge_names(value):
                named.add((p["name"], name))
                if port in FOLD_PORTS or port in SEAM_PORTS:
                    continue
                if port in ARMHOLE_PORTS and folded[p["name"]]:
                    continue                 # a hole in a torso, not a girth
                if port not in PORT_ORDER or name not in edges:
                    continue
                rec = ported.setdefault(port, {"girth": 0.0, "pts": [],
                                               "from": []})
                rec["girth"] += _girth(edges[name], factor)
                rec["pts"] += list(edges[name].get("points") or [])
                rec["from"].append(f'{p["name"]}/{name}')

    extras: Dict[str, Dict[str, Any]] = {}
    for p in pieces:
        factor = HALF_BODY_FACTOR if folded[p["name"]] else 1.0
        for name, e in (p.get("edges") or {}).items():
            if (p["name"], name) in named or (p["name"], name) in joined:
                continue
            rec = extras.setdefault(name, {"girth": 0.0, "pts": [],
                                           "from": []})
            rec["girth"] += _girth(e, factor)
            rec["pts"] += list(e.get("points") or [])
            rec["from"].append(f'{p["name"]}/{name}')

    out: List[Dict[str, Any]] = []
    for port in PORT_ORDER:
        if port in ported:
            rec = ported[port]
            out.append({"level": port, "girth": rec["girth"],
                        "centroid": _centroid(rec["pts"]),
                        "from": sorted(rec["from"])})
    for name in sorted(extras):
        rec = extras[name]
        out.append({"level": name, "girth": rec["girth"],
                    "centroid": _centroid(rec["pts"]),
                    "from": sorted(rec["from"])})
    return out


def _cartesian(pieces: Sequence[Dict[str, Any]]) -> bool:
    """Is this instance drawn in a plain body frame, y increasing downward?

    The test is the fold line itself: a fold drawn at constant x is a centre
    front or centre back, so the piece's y IS height. A cape is drawn in polar
    coordinates about the neck point and its fold lines are radial, so this
    answers False and the caller spaces the rings instead of pretending to
    read heights out of a frame that does not carry them. This is the
    coordinate-frame confusion that breaks ``mannequin.dress()``, refused here
    rather than repeated.
    """
    seen = False
    for p in pieces:
        edges = p.get("edges") or {}
        for port, value in (p.get("ports") or {}).items():
            if port not in FOLD_PORTS:
                continue
            for name in _edge_names(value):
                e = edges.get(name)
                if not e:
                    continue
                xs = [float(q[0]) for q in (e.get("points") or [])]
                if not xs:
                    continue
                seen = True
                if max(xs) - min(xs) > 1e-6:
                    return False
    return seen


def _height_of(pieces: Sequence[Dict[str, Any]],
               joined: Sequence[Any]) -> float:
    """The instance's own height: the longest of its fold lines and of the
    seams inside it. Those are the edges that run DOWN the piece."""
    best = 0.0
    for p in pieces:
        edges = p.get("edges") or {}
        for port, value in (p.get("ports") or {}).items():
            if port not in FOLD_PORTS:
                continue
            for name in _edge_names(value):
                if name in edges:
                    best = max(best, float(edges[name]["length"]))
        for name, e in edges.items():
            if (p["name"], name) in joined:
                best = max(best, float(e["length"]))
    return best


def _depths(levels: Sequence[Dict[str, Any]],
            pieces: Sequence[Dict[str, Any]],
            joined: Sequence[Any]) -> List[float]:
    """How far below the top ring each ring sits.

    In a plain body frame the depth is the difference of the levels' own mean
    y — a measured number. In a frame this cannot read (a cape's polar one)
    the rings are spread EVENLY over the instance's own height, which is a
    declared spacing over a measured span; ``solid_from_draft`` reports which
    instances got which.
    """
    if not levels:
        return []
    if _cartesian(pieces):
        top = levels[0]["centroid"][1]
        return [lv["centroid"][1] - top for lv in levels]
    h = _height_of(pieces, joined)
    n = len(levels) - 1
    if n <= 0:
        return [0.0] * len(levels)
    return [h * i / n for i in range(len(levels))]


def solid_from_draft(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Build the confirmation solid **out of the composed draft's own edges.**

    Reuses ``garment_solid._ellipse`` / ``_tube``, so this carries exactly the
    same assumption as the ledger-built solid and states it the same way: the
    cross-section is an ellipse at an assumed depth ratio, because girth is a
    circumference and nobody measured a depth.

    It is a PROPORTION BLOCK, not a fit simulation. The question this stage
    asks is "is this my garment", which is about structure; how cloth falls is
    a different question and this makes no claim about it.
    """
    if draft.get("verdict") != "ANSWER":
        return {"verdict": NO_SOLID, "carried": draft.get("verdict"),
                "why": "there is no composed shape yet, so there is nothing "
                       "to raise. The claims below still stand on their own",
                "how_to_close": draft.get("how_to_close")
                                or "close the composition first"}

    by_inst: Dict[str, List[Dict[str, Any]]] = {}
    for p in draft.get("pieces") or []:
        by_inst.setdefault(str(p.get("instance") or p["name"]), []).append(p)
    placement = draft.get("placement") or {}

    verts: List[Any] = []
    faces: List[Any] = []
    groups: List[Dict[str, Any]] = []
    read: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    no_placement: List[str] = []

    joined = _intra_instance_seams(draft)
    spaced: List[str] = []
    for inst in sorted(by_inst):
        pieces = by_inst[inst]
        levels = _levels_for(pieces, joined)
        if len(levels) < 2:
            skipped.append({"instance": inst,
                            "why": "fewer than two ring levels could be read "
                                   "from this part's own edges, and a tube "
                                   "needs two rings"})
            continue
        offsets = [placement.get(p["name"]) for p in pieces
                   if placement.get(p["name"])]
        if offsets:
            y0 = sum(float(o[1]) for o in offsets) / len(offsets)
        else:
            y0 = 0.0
            no_placement.append(inst)
        depths = _depths(levels, pieces, joined)
        how = "measured y" if _cartesian(pieces) else "evenly spaced"
        if how != "measured y":
            spaced.append(inst)
        rings = []
        for lv, depth in zip(levels, depths):
            y = y0 - depth
            rings.append(_ellipse(0.0, 0.0, lv["girth"], y,
                                  ASSUMED_DEPTH_RATIO))
            read.append({"instance": inst, "level": lv["level"],
                         "girth_cm": round(lv["girth"], 4),
                         "y": round(y, 4), "height_from": how,
                         "from": lv["from"]})
        base = len(verts)
        for ring in rings:
            verts.extend(ring)
        f = _tube(rings, base)
        groups.append({"instance": inst, "first_face": len(faces),
                       "faces": len(f), "rings": len(rings)})
        faces.extend(f)

    return {
        "verdict": "ANSWER",
        "vertices": [[round(x, 4), round(y, 4), round(z, 4)]
                     for x, y, z in verts],
        "faces": [list(t) for t in faces],
        "groups": groups,
        "rings": read,
        "skipped": skipped,
        "defaulted": sorted(no_placement),
        "evenly_spaced": sorted(spaced),
        "built_from": "the composed draft's own edge lengths and points. No "
                      "body ratio is consulted anywhere in this function",
        "assumed": {
            "depth_ratio": ASSUMED_DEPTH_RATIO,
            "half_body_factor": HALF_BODY_FACTOR,
            "ring_order": list(PORT_ORDER),
            "why": "a girth is a circumference, not a width. Splitting it "
                   "into width and depth needs a ratio and no depth was ever "
                   "measured, so the ratio is an assumption. A piece drawn "
                   "against a fold is one half of the body and doubles. The "
                   "top-to-bottom ORDER of the rings is declared — a neckline "
                   "is above a waist because that is what the words mean — "
                   "and the instances listed under evenly_spaced had their "
                   "ring heights spread evenly over their own height because "
                   "their frame is polar and carries no height to read",
        },
        "not_a_simulation":
            "This is a proportion block. It is not a fit simulation, it "
            "makes no claim at all about how cloth falls, and you are being "
            "asked to judge SHAPE, not fit.",
        "surface_carries_no_information":
            f"the surface is {SEGMENTS} facets of an assumed ellipse. Its "
            f"smoothness carries no information about the pattern",
    }


def to_obj(solid: Dict[str, Any]) -> str:
    """OBJ, with the disclaimers at the top of the file — a shape handed on
    without them is read as a measurement."""
    if solid.get("verdict") != "ANSWER":
        return f"# {solid.get('verdict')}: {solid.get('why', '')}\n"
    out = ["# photoloset — confirmation solid, built from a composed draft",
           "# Generated. It cannot be the source of an observation.",
           f"# {solid['not_a_simulation']}",
           f"# {solid['surface_carries_no_information']}",
           f"# depth ratio {solid['assumed']['depth_ratio']} (assumed)"]
    for v in solid["vertices"]:
        out.append(f"v {v[0]} {v[1]} {v[2]}")
    for g in solid["groups"]:
        out.append(f'g {g["instance"]}')
        for f in solid["faces"][g["first_face"]:
                                g["first_face"] + g["faces"]]:
            out.append(f"f {f[0] + 1} {f[1] + 1} {f[2] + 1}")
    return "\n".join(out) + "\n"


def silhouette_svg(solid: Dict[str, Any], height_cm: float = 0.0) -> str:
    """A front-on outline at matched height, to lay beside the source frame.

    An outline, not a rendering: the widest point of each ring, joined. It is
    the same numbers the solid carries and no others.
    """
    if solid.get("verdict") != "ANSWER" or not solid.get("rings"):
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="10" '
                'height="10"><!-- no shape yet --></svg>')
    rings = sorted(solid["rings"], key=lambda r: -r["y"])
    half = [(r["girth_cm"] / (math.pi * (1.0 + ASSUMED_DEPTH_RATIO)), r["y"])
            for r in rings]
    ys = [y for _a, y in half]
    top, bottom = max(ys), min(ys)
    span = (top - bottom) or 1.0
    scale = (height_cm / span) if height_cm > 0 else 1.0
    w = max(a for a, _y in half) * scale * 2.0 + 20.0
    h = span * scale + 20.0
    right = " ".join(f"{w / 2 + a * scale:.2f},{10 + (top - y) * scale:.2f}"
                     for a, y in half)
    left = " ".join(f"{w / 2 - a * scale:.2f},{10 + (top - y) * scale:.2f}"
                    for a, y in reversed(half))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
            f'height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">'
            f'<polyline points="{right} {left}" fill="none" '
            f'stroke="#333" stroke-width="1"/>'
            f'<!-- outline of an assumed ellipse stack, not a rendering -->'
            f'</svg>')


# ---------------------------------------------------------------------------
# The sheet
# ---------------------------------------------------------------------------

def _claim_id(n: int) -> str:
    return f"c{n}"


def _part_of_core(core: Any) -> str:
    """``look:<image_id>:<part>:<n>`` -> ``<part>:<n>``. The part instance in
    this look, without the look."""
    bits = str(core or "").split(":")
    return ":".join(bits[2:]) if len(bits) > 2 else str(core or "")


def sheet(draft: Dict[str, Any], solid: Optional[Dict[str, Any]] = None, *,
          image_ref: str = "", retrieval: Optional[Dict[str, Any]] = None,
          intake: Any = None, graph: Optional[Dict[str, Any]] = None,
          renamed: Optional[Dict[str, str]] = None,
          measures: Any = None, sew: Optional[Dict[str, Any]] = None,
          rejected: Optional[Sequence[str]] = None,
          history: Optional[List[Dict[str, Any]]] = None,
          height_cm: float = 0.0) -> Dict[str, Any]:
    """The confirmation sheet. **A claim list, never a verdict.**

    Every retrieval proposal becomes one claim the human answers yes / no /
    cannot_tell. Every OPEN PORT becomes one claim pre-answered
    ``cannot_tell`` — on a single front-facing photograph an open port is the
    EXPECTED first state ("the back is not visible in this photo"), and it is
    put to the human rather than filled in with a default that nobody chose.
    """
    if solid is None:
        solid = solid_from_draft(draft)

    rename = dict(renamed or (graph or {}).get("renamed") or {})
    claims: List[Dict[str, Any]] = []
    n = 0
    for hit in ((retrieval or {}).get("landed") or []):
        n += 1
        part = hit.get("instance") or _part_of_core(hit.get("core"))
        claims.append({
            "id": _claim_id(n),
            "kind": "retrieved",
            "part": part,
            "composed_as": rename.get(part, part),
            "aspect": hit.get("key"),
            "value": hit.get("value"),
            "source": hit.get("source"),
            "seated_in": hit.get("seated_in"),
            "answer": "unanswered",
            "ask": "is this claim about the garment you had in mind?",
        })
    for hit in ((retrieval or {}).get("contested") or []):
        n += 1
        claims.append({
            "id": _claim_id(n),
            "kind": "contested",
            "part": hit.get("core"),
            "aspect": hit.get("key"),
            "value": hit.get("sides"),
            "source": "two retrieval sources at one address",
            "answer": "unanswered",
            "ask": "two sources disagree here and neither was chosen. Which "
                   "one is your garment?",
        })
    for op in (draft.get("open") or []):
        n += 1
        claims.append({
            "id": _claim_id(n),
            "kind": "open_port",
            "part": op.get("instance"),
            "aspect": f'port:{op.get("port")}',
            "value": None,
            "source": "compose: UNKNOWN_OPEN_PORT",
            "answer": "cannot_tell",
            "ask": "this port is neither connected nor finished — on a "
                   "single front-facing photograph that is expected. How is "
                   "it finished?",
            "how_to_close": op.get("how_to_close"),
        })

    origin = None
    if intake is not None and image_ref:
        try:
            origin = intake.origin_of(image_ref)
        except Exception:                                   # noqa: BLE001
            origin = None

    digest = shape_digest(draft, graph)
    does_not_claim = [
        solid.get("not_a_simulation"),
        solid.get("surface_carries_no_information"),
        draft.get("seam_allowance"),
        draft.get("not_a_published_system"),
    ]
    assumed = solid.get("assumed")
    if assumed:
        does_not_claim.append(
            f'depth ratio {assumed.get("depth_ratio")}: '
            f'{assumed.get("why")}')

    # **Is the loop ending?** open ports + contested measurements +
    # unresolved refusals + unsewable seams + failed physical checks + claims
    # the human keeps rejecting. This is convergence.py's first caller: it
    # existed, worked by hand, and nothing in the tree would have noticed if
    # it had stopped working. The sheet is where the question belongs,
    # because the sheet is what a person is about to answer.
    ending = _convergence.check(draft, measures=measures, sew=sew,
                                rejected=list(rejected or []),
                                history=history)

    return {
        "verdict": "ANSWER",
        "claims": claims,
        "answers_allowed": list(ANSWERS),
        "convergence": ending,
        "solid": solid,
        "silhouette_svg": silhouette_svg(solid, height_cm),
        "image_ref": image_ref,
        "traceable_to": origin,
        "traceable": origin is not None,
        "shape": digest,
        "defaulted": sorted(solid.get("defaulted") or []),
        "does_not_claim": [s for s in does_not_claim if s],
        "the_question":
            "answer the claims one at a time. You are being asked whether "
            "this is the garment you had in mind — not whether the render is "
            "pretty. There is no field here for that, on purpose",
        "not_a_verdict":
            "this sheet decides nothing. Approval is an adoption with a name "
            "on it, and it is what opens the sewing-method search",
    }


def reject(sheet_obj: Dict[str, Any], which: Sequence[str], by: str,
           note: str = "") -> Dict[str, Any]:
    """Reject NAMED claims. **Free text is only ever a note beside one.**

    An empty ``which`` is UNKNOWN_UNNAMED_REJECTION and an unknown id is
    UNKNOWN_NO_SUCH_CLAIM, so "it looks wrong" cannot be recorded as a
    rejection of anything. That is deliberate: a correct retrieval must not
    be killed by an ugly render.
    """
    ids = [str(x) for x in (which or []) if str(x).strip()]
    known = {c["id"]: c for c in (sheet_obj.get("claims") or [])}
    if not ids:
        return {"verdict": UNNAMED_REJECTION,
                "claims": sorted(known),
                "why": "a rejection has to say WHAT is wrong. 'It looks "
                       "wrong' is not about any claim, and the next round "
                       "would have nothing to change",
                "how_to_close": "name one or more claim ids from the sheet; "
                                "a note rides beside them"}
    if not str(by or "").strip():
        return {"verdict": NO_REJECTER,
                "how_to_close": "a rejection carries the name of the person "
                                "making it, like an adoption does"}
    missing = [i for i in ids if i not in known]
    if missing:
        return {"verdict": NO_CLAIM, "which": missing,
                "claims": sorted(known),
                "how_to_close": "reject claims that are on this sheet"}
    return {"verdict": "ANSWER",
            "rejected": [{"id": i, "part": known[i].get("part"),
                          "aspect": known[i].get("aspect"),
                          "value": known[i].get("value"),
                          "source": known[i].get("source"),
                          "note": str(note or "")} for i in ids],
            "by": str(by).strip(),
            "shape": sheet_obj.get("shape", {}).get("digest"),
            "note_is_not_a_claim":
                "the note is recorded beside the named claims and is not "
                "itself a rejection of anything",
            "next": "correct the structure and compose again; convergence "
                    "counts a claim rejected round after round"}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

APPROVAL_PART = "garment"
APPROVAL_ASPECT = "shape_approved"
STRUCTURE_ASPECT = "shape_structure"


def approve(sheet_obj: Dict[str, Any], answers: Dict[str, str], by: str,
            ledger: Any = None, *,
            graph: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Approve the shape. **This is an adoption, with a name on it.**

    It writes through ``Ledger.propose()`` + ``Ledger.adopt()`` — one adopted
    entry per claim answered ``yes``, so the approval is not one opaque token
    but a record of which structural claims a named person accepted, each
    still carrying the retrieval source that proposed it — plus a summary
    entry (part=``garment``, aspect=``shape_approved``, value=the shape
    digest) which is the key ``sewing_search.methods_for`` takes.

    ``Ledger.adopt`` refuses an empty name. That check is in the ledger, not
    here and not in the UI, because an earlier version put it in the door and
    measurement V60 walked around it by calling the ledger directly.
    """
    if ledger is None:
        return {"verdict": NO_LEDGER,
                "how_to_close": "pass the garment.Ledger the approval is to "
                                "be written into. An approval nobody recorded "
                                "cannot open anything"}
    shape = sheet_obj.get("shape") or {}
    if shape.get("verdict") != "ANSWER" or not shape.get("digest"):
        return {"verdict": NOT_COMPOSED,
                "carried": shape.get("verdict"),
                "why": "there is no composed shape on this sheet, so there "
                       "is nothing an approval could be FOR",
                "how_to_close": shape.get("how_to_close")
                                or "close the open ports and compose again"}

    claims = list(sheet_obj.get("claims") or [])
    given = {str(k): str(v) for k, v in (answers or {}).items()}
    bad = sorted({v for v in given.values() if v not in ANSWERS})
    if bad:
        return {"verdict": "UNKNOWN_BAD_ANSWER", "which": bad,
                "allowed": list(ANSWERS),
                "how_to_close": f"every answer is one of {list(ANSWERS)}"}
    unknown = sorted(set(given) - {c["id"] for c in claims})
    if unknown:
        return {"verdict": NO_CLAIM, "which": unknown,
                "how_to_close": "answer claims that are on this sheet"}
    unanswered = [c["id"] for c in claims
                  if given.get(c["id"], c.get("answer")) == "unanswered"]
    if unanswered:
        return {"verdict": UNANSWERED, "which": unanswered,
                "why": "an approval that skipped a claim says the human "
                       "accepted something nobody showed them",
                "how_to_close": "answer every claim yes / no / cannot_tell"}
    said_no = [c["id"] for c in claims
               if given.get(c["id"], c.get("answer")) == "no"]
    if said_no:
        return {"verdict": REJECTED, "which": said_no,
                "why": "a claim was rejected, so this is not the garment. "
                       "Approving it anyway would carry the rejection past "
                       "the gate as if it were an acceptance",
                "how_to_close": "record it with confirm.reject(), correct "
                                "the structure and compose again"}

    accepted = [c for c in claims
                if given.get(c["id"], c.get("answer")) == "yes"]
    cannot_tell = [c["id"] for c in claims
                   if given.get(c["id"], c.get("answer")) == "cannot_tell"]

    adopted: List[Dict[str, Any]] = []
    try:
        for c in accepted:
            value = json.dumps(c.get("value"), ensure_ascii=False,
                               sort_keys=True, default=repr)
            source = str(c.get("source") or "retrieval")
            ledger.propose(str(c.get("part")), str(c.get("aspect")), value,
                           source=source,
                           note=f'confirmation claim {c["id"]}')
            e = ledger.adopt(str(c.get("part")), str(c.get("aspect")), value,
                             by=by)
            if e is None:
                # ``Ledger.propose`` returns the EXISTING entry for an
                # identical (part, aspect, value, source) — the same frame
                # read twice does not raise the confidence — so a second
                # claim carrying the same four fields finds its proposal
                # already adopted and ``adopt`` answers None. Recording that
                # as an adoption with an empty adopter is how an
                # unattributed row gets into a ledger whose whole point is
                # attribution.
                return {"verdict": "UNKNOWN_NO_SUCH_PROPOSAL",
                        "which": c["id"], "part": c.get("part"),
                        "aspect": c.get("aspect"),
                        "why": "two claims on this sheet carry the same part, "
                               "aspect, value and source, so the second has "
                               "no proposal of its own to adopt",
                        "how_to_close": "give the claims distinct addresses, "
                                        "or answer only one of them"}
            adopted.append({"id": c["id"], "part": c.get("part"),
                            "aspect": c.get("aspect"), "value": value,
                            "source": source,
                            "adopted_by": e.adopted_by})
        structure = json.dumps(
            {"graph": graph, "instances": shape.get("instances"),
             "structure_digest": shape.get("structure_digest"),
             "digest": shape.get("digest")},
            ensure_ascii=False, sort_keys=True, default=repr)
        ledger.propose(APPROVAL_PART, STRUCTURE_ASPECT, structure,
                       source="confirm.approve",
                       note="the structure this approval is for")
        ledger.adopt(APPROVAL_PART, STRUCTURE_ASPECT, structure, by=by)
        ledger.propose(APPROVAL_PART, APPROVAL_ASPECT, shape["digest"],
                       source="confirm.approve",
                       note=f'{len(accepted)} claims accepted, '
                            f'{len(cannot_tell)} not visible')
        entry = ledger.adopt(APPROVAL_PART, APPROVAL_ASPECT, shape["digest"],
                             by=by)
    except ValueError as exc:
        # The ledger's refusal, returned as the typed value it should have
        # been. Nothing raises across this boundary.
        code = str(exc).split(":", 1)[0]
        return {"verdict": code if code.startswith("UNKNOWN_")
                else "UNKNOWN_REFUSED",
                "why": str(exc),
                "how_to_close": "an adoption carries the name of the person "
                                "making it"}
    if entry is None:
        return {"verdict": "UNKNOWN_NO_SUCH_PROPOSAL",
                "how_to_close": "the summary proposal did not survive to be "
                                "adopted; the ledger was written to "
                                "concurrently"}

    return {"verdict": "ANSWER",
            "approval_id": shape["digest"],
            "digest": shape["digest"],
            "structure_digest": shape["structure_digest"],
            "by": getattr(entry, "adopted_by", str(by).strip()),
            "adopted": adopted,
            "accepted": [c["id"] for c in accepted],
            "cannot_tell": cannot_tell,
            "opens": "sewing_search.methods_for(approval_id)",
            "note": "the approval names the claims a person accepted, each "
                    "still carrying the source that proposed it. It dies the "
                    "moment the shape moves"}
