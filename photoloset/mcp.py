# -*- coding: utf-8 -*-
"""An MCP server for the garment tools — standard library only.

    python3 -m photoloset.mcp

Speaks JSON-RPC 2.0 over stdin/stdout: `initialize`, `tools/list`, `tools/call`.
There is no MCP SDK here on purpose. The whole package promises no
dependencies, and the three methods a tool server actually needs are about a
hundred lines of `json` and a loop — an SDK would cost more than it carries.

Every tool returns a JSON string. A refusal is a normal return value with a
verdict beginning `UNKNOWN_` or `CONTESTED_`, never an exception across the
wire, so a caller reading the result cannot mistake "it declined" for "it
crashed".

Five tools that exist in the parent project are absent here and say so rather
than failing: `garment_cross` and the four `fabric_*` tools need the coordinate
memory and its language engine, roughly 15,700 lines that are not part of this
package. They return UNKNOWN_NOT_IN_THIS_BUILD with what would close it.
"""
from __future__ import annotations

import inspect
import json
import json as _json
import sys
import traceback
import typing
from pathlib import Path
from typing import Any, Callable, Dict, List

# Aliased on purpose: several tools are named after the module they call
# (`garment_draw`, `garment_solid`), and a bare import would be shadowed by the
# tool definition — the module would silently become the function.
from . import garment_body as _body
from . import garment_draw as _draw
from . import garment_marks as _marks
from . import garment_pattern as _pattern
from . import garment_rights as _rights_mod
from . import garment_sew as _sew
from . import garment_solid as _solid
from . import bom as _bom
from . import convergence as _convergence
from . import cross as _cross
from . import darts as _darts
from . import dxf as _dxf
from . import mannequin as _mq
from . import marker as _marker
from . import points as _points
from .garment import Intake, Ledger
from .garment_measure import Measures

HOME = Path.home() / ".photoloset"
PROTOCOL = "2024-11-05"

# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------

def _p(name: str) -> Path:
    HOME.mkdir(parents=True, exist_ok=True)
    return HOME / name


def _ledger() -> Ledger:      return Ledger.load(_p("ledger.json"))
def _measures() -> Measures:  return Measures.load(_p("measures.json"))
def _intake() -> Intake:      return Intake.load(_p("intake.json"))
def _design():                return _rights_mod.Design.load(_p("design.json"))
def _rights():                return _rights_mod.RightsLedger.load(_p("rights.json"))


def _revision_store() -> _cross.CrossStore:
    """``convergence.loop`` の住所空間。**周をまたいで同じ店を使う** —
    毎回新しく建てると「既にある値」がその周にしか見えなくなる。
    """
    f = _p("revision_cross.json")
    if f.exists():
        return _cross.CrossStore.from_dict(
            _json.loads(f.read_text(encoding="utf-8")))
    return _cross.CrossStore()


def _save_revision_store(st: _cross.CrossStore) -> None:
    _p("revision_cross.json").write_text(
        _json.dumps(st.to_dict(), ensure_ascii=False, indent=1),
        encoding="utf-8")


def _revision_history() -> List[Dict[str, Any]]:
    """``convergence.check`` の停滞カウンタが読む履歴。呼び側(ここ)が持つ。"""
    f = _p("revision_history.json")
    if f.exists():
        return _json.loads(f.read_text(encoding="utf-8"))
    return []


def _save_revision_history(history: List[Dict[str, Any]]) -> None:
    _p("revision_history.json").write_text(
        _json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")


def _dart_store():
    f = _p("darts.json")
    if f.exists():
        return _json.loads(f.read_text(encoding="utf-8"))
    return []


def _dart_call(new):
    """Apply the stored darts (plus ``new``) to the current draft.

    A dart that the geometry refuses is **not stored** — an overlapping or
    escaping dart kept on the list would come back and be refused again on
    every later call, and the refusal would look like a property of the
    pattern rather than of that one dart.
    """
    draft = _pattern.draft(_measures())
    if draft.get("verdict") != "ANSWER":
        return _ok(draft)
    kept = _dart_store()
    out = _darts.apply(draft, kept + ([new] if new else []))
    if new is not None and out.get("verdict") == "ANSWER":
        fresh = [d for d in out.get("darts") or []
                 if (d["piece"], d["edge"], round(d["t"], 9))
                 == (new["piece"], new["edge"], round(float(new["t"]), 9))
                 or d.get("trued")]
        if len(out.get("darts") or []) > len(kept):
            kept = kept + [new]
            _p("darts.json").write_text(
                _json.dumps(kept, ensure_ascii=False, indent=2),
                encoding="utf-8")
        else:
            out["not_stored"] = ("この一本は幾何に断られたので保存しません。"
                                 "残すと以後ずっと同じ拒否を返し続け、それが"
                                 "型紙そのものの性質に見えます")
    out["stored"] = len(kept)
    return _ok(out)


def _fallen(fabric: str, iterations: int):
    """The garment as the solver left it. Returns the points, or a refusal."""
    draft = _pattern.draft(_measures())
    if draft.get("verdict") != "ANSWER":
        return _ok(draft)
    built = _sew.build(_marks.apply(draft))
    mat = _fabric(fabric)
    if mat.get("verdict") != "ANSWER":
        return _ok(mat)
    return _sew.sew_and_drape(built, mat, iterations=iterations)["points"]


def _numbering():
    """The point-number registry. **Append-only across sessions** — a fresh
    one every call would renumber the pattern behind the user's back, which
    is the exact failure ``points.py`` exists to prevent."""
    f = _p("numbers.json")
    if f.exists():
        return _points.Registry.from_json(_json.loads(
            f.read_text(encoding="utf-8")))
    return _points.Registry()


def _ok(obj: Any) -> str:
    """One reply, as JSON. **``allow_nan=False`` because NaN is not JSON.**

    Without it ``json.dumps`` writes the bare tokens ``NaN`` / ``Infinity``,
    which RFC 8259 has no room for: the reply line this server prints
    becomes unreadable to any conforming client (Swift's JSONSerialization
    in ``app/``, or anything not written in Python), and it is the WHOLE
    line that fails, not the one number. Measured before this: a measurement
    written as the string "nan" came back as
    ``{"verdict": "ANSWER", "entry": {... "value": NaN ...}}``.

    A value that cannot be written is a refusal, not a crash.
    """
    try:
        return json.dumps(obj, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as e:
        return json.dumps({"verdict": "UNKNOWN_UNIDENTIFIABLE_VALUE",
                           "why": f"this answer does not survive JSON: {e}",
                           "how_to_close": "the value is not JSON (NaN, "
                                           "Infinity or an object) — fix it "
                                           "at the writer"},
                          ensure_ascii=False)


def _refused(exc: BaseException) -> str:
    """A raised refusal, turned back into the typed value it should have been.

    **Only a typed verdict may pose as one.** This used to take everything
    before the first colon, so a stdlib message became the verdict:
    ``float("abc")`` answered with ``"verdict": "could not convert string to
    float"``, which contradicts this module's own promise that a refusal
    reads ``UNKNOWN_`` or ``CONTESTED_``. Anything else is
    ``UNKNOWN_REFUSED`` with the text kept in ``why``.
    """
    text = str(exc)
    code = text.split(":", 1)[0] if ":" in text else ""
    if not (code.startswith("UNKNOWN_") or code.startswith("CONTESTED_")):
        code = "UNKNOWN_REFUSED"
    return json.dumps({"verdict": code, "why": text}, ensure_ascii=False)


def _absent(what: str, needs: str) -> str:
    return json.dumps({
        "verdict": "UNKNOWN_NOT_IN_THIS_BUILD",
        "why": f"{what} is not part of photoloset.",
        "how_to_close": needs,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOLS: Dict[str, Callable[..., str]] = {}
_SCHEMA_TYPE = {str: "string", float: "number", int: "integer", bool: "boolean"}


def tool(fn: Callable[..., str]) -> Callable[..., str]:
    TOOLS[fn.__name__] = fn
    return fn


def _schema(fn: Callable[..., str]) -> Dict[str, Any]:
    """Derive the input schema from the signature — one source of truth.

    **The annotations are strings.** This module carries
    ``from __future__ import annotations``, so ``par.annotation`` is the
    TEXT ``"float"``, never the type, and the lookup fell through to the
    default for every one of them: 8 numeric parameters across the 42 tools
    published ``{"type": "string"}``, two of them beside a numeric default
    (``{"type": "string", "default": 2000}``). A client that honours the
    schema then sends "2000" and the tool refuses it. The check that pins
    this asserted only that a schema is an object with properties, so it
    stayed green — the derivation it is named for was never measured.

    ``typing.get_type_hints`` resolves the strings against the module's own
    namespace, which is what the annotation means.
    """
    try:
        hints = typing.get_type_hints(fn)
    except Exception:                                        # noqa: BLE001
        # A hint that cannot be resolved is not a reason to serve nothing;
        # the parameter falls back to "string" as before, and says so by
        # being absent from the resolved map.
        hints = {}
    props: Dict[str, Any] = {}
    required: List[str] = []
    for name, par in inspect.signature(fn).parameters.items():
        kind = _SCHEMA_TYPE.get(hints.get(name, par.annotation), "string")
        props[name] = {"type": kind}
        if par.default is inspect.Parameter.empty:
            required.append(name)
        else:
            props[name]["default"] = par.default
    return {"type": "object", "properties": props, "required": required}


# ---------------------------------------------------------------------------
# Intake — where a source came from
# ---------------------------------------------------------------------------

@tool
def intake_register(path: str, kind: str = "video", at: str = "",
                    note: str = "") -> str:
    """Register a source file. Nothing may point at a source not registered here."""
    i = _intake()
    try:
        s = i.register(path, kind, at=at, note=note)
    except (ValueError, FileNotFoundError) as e:
        return _refused(e)
    i.save(_p("intake.json"))
    return _ok({"verdict": "ANSWER", "source": s.__dict__})


@tool
def intake_add_clip(source_path: str, clip_path: str, mark: str,
                    seconds: float = 0.0) -> str:
    """Record a frame cut from a registered source, with its mark in the clip."""
    i = _intake()
    try:
        c = i.add_clip(source_path, clip_path, mark, seconds)
    except (ValueError, KeyError, FileNotFoundError) as e:
        return _refused(e)
    i.save(_p("intake.json"))
    return _ok({"verdict": "ANSWER", "clip": c.__dict__})


@tool
def intake_origin(clip_path: str) -> str:
    """Where a frame came from. A frame whose source is unknown says so."""
    o = _intake().origin_of(clip_path)
    if o is None:
        return _ok({"verdict": "UNKNOWN_CLIP_NOT_REGISTERED",
                    "how_to_close": "link the frame to its source with "
                                    "intake_add_clip"})
    return _ok({"verdict": "ANSWER", "origin": o})


@tool
def intake_report() -> str:
    """Every registered source and the frames cut from it."""
    return _ok(_intake().report())


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------

@tool
def garment_spec() -> str:
    """The ledger split into settled / contested / inferred / not-observed.

    They are never merged, because merged you can no longer read whether it
    is safe to cut.
    """
    return _ok(_ledger().spec())


@tool
def garment_observe(part: str, aspect: str, value: str, source: str,
                    note: str = "", ref_path: str = "", ref_mark: str = "",
                    ref_url: str = "") -> str:
    """Record something observed, with the frame or document it was seen in."""
    l = _ledger()
    try:
        e = l.observe(part, aspect, value, source, note=note,
                      ref_path=ref_path, ref_mark=ref_mark, ref_url=ref_url)
    except ValueError as ex:
        return _refused(ex)
    l.save(_p("ledger.json"))
    return _ok({"verdict": "ANSWER", "entry": e.__dict__})


@tool
def garment_infer(part: str, aspect: str, value: str, basis: str) -> str:
    """Record something derived from other entries. Never silently an observation."""
    l = _ledger()
    try:
        e = l.infer(part, aspect, value, basis)
    except ValueError as ex:
        return _refused(ex)
    l.save(_p("ledger.json"))
    return _ok({"verdict": "ANSWER", "entry": e.__dict__})


@tool
def garment_propose(part: str, aspect: str, value: str, source: str,
                    note: str = "", ref_path: str = "", ref_mark: str = "",
                    ref_url: str = "") -> str:
    """Record a suggestion. A proposal is not a fact and cannot reach a pattern."""
    l = _ledger()
    try:
        e = l.propose(part, aspect, value, source, note=note,
                      ref_path=ref_path, ref_mark=ref_mark, ref_url=ref_url)
    except ValueError as ex:
        return _refused(ex)
    l.save(_p("ledger.json"))
    return _ok({"verdict": "ANSWER", "entry": e.__dict__})


@tool
def garment_adopt(part: str, aspect: str, value: str, by: str) -> str:
    """Turn a proposal into a fact. **Requires the name of the person doing it.**"""
    l = _ledger()
    try:
        e = l.adopt(part, aspect, value, by=by)
    except ValueError as ex:
        return _refused(ex)
    if e is None:
        return _ok({"verdict": "UNKNOWN_NO_SUCH_PROPOSAL",
                    "how_to_close": "propose it first, then adopt that value"})
    l.save(_p("ledger.json"))
    return _ok({"verdict": "ANSWER", "entry": e.__dict__})


@tool
def garment_revision_loop(json_text: str = "") -> str:
    """Run one round of revisions through the address store. **AI loops don't
    stop on their own; this decides whether the round does.**

    `json_text` is `{"revisions": [{"core", "key", "value", "kind", "source",
    "by", "id"}, ...]}`. Each revision lands on the store the same ledger
    `garment_adopt` writes to, so an address adopted there needs a named `by`
    here to reopen with a different value — an empty one is refused by the
    ledger itself, not by this door, and that stays true past the first
    reopen: a second differing value does not retire the adoption.

    Returns CONVERGED (nothing moved), CONTESTED (two values now sit at one
    address, kept — this is terminal, not a retry), UNKNOWN_ORDER_DEPENDENT
    (the store's own answers moved when re-ingested in a different order), or
    CONTINUE, plus the counters `convergence.check` uses to escalate a claim
    that keeps getting rejected round after round. A round whose own write
    matches an address that is still contested with a DIFFERENT value is
    CONTESTED too, not a false fixed point — matching one side of an
    existing dispute does not settle it. The store and the round history
    persist across calls the way the ledger does.
    """
    req, err = _json_arg(json_text, '{"revisions": [...]}')
    if err:
        return _ok(err)
    revisions = req.get("revisions")
    if not isinstance(revisions, list):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": 'json_text の "revisions" は配列です',
                    "how_to_close": 'pass {"revisions": [{"core", "key", '
                                    '"value", "kind", "source"}, ...]}'})
    store = _revision_store()
    ledger = _ledger()
    history = _revision_history()
    result = _convergence.loop(revisions, store, ledger=ledger, history=history)
    _save_revision_store(store)
    ledger.save(_p("ledger.json"))
    _save_revision_history(history)
    return _ok(result)


@tool
def garment_worklist() -> str:
    """What has not been observed yet, each with the action that would close it."""
    return _ok({"verdict": "ANSWER", "worklist": _ledger().worklist()})


@tool
def garment_timeline() -> str:
    """Every entry in the order it was recorded."""
    return _ok({"verdict": "ANSWER", "timeline": _ledger().timeline()})


@tool
def garment_techpack() -> str:
    """The tech pack: settled fields, contested ones, and the open unknowns."""
    return _ok(_ledger().techpack(_measures(), _rights()))


@tool
def garment_parts() -> str:
    """The parts and aspects the ledger knows how to hold."""
    from .garment import PARTS
    return _ok({"verdict": "ANSWER", "parts": PARTS})


# ---------------------------------------------------------------------------
# Drawing and the solid
# ---------------------------------------------------------------------------

@tool
def garment_draw() -> str:
    """A flat drawing of the ledger. Colour is state, never decoration."""
    return _ok(_draw.draw(_ledger(), _measures()))


@tool
def garment_draw_save(path: str) -> str:
    """Write that drawing to an SVG file, marked as generated."""
    return _ok(_draw.save(_ledger(), path, _measures()))


@tool
def garment_solid() -> str:
    """Build the solid. **This is not a fit simulation.**

    It is a proportion block raised from measurements; it makes no claim at
    all about how cloth falls. Depth is an assumed ratio and the assumption
    is returned with it.
    """
    return _ok(_solid.build(_ledger(), _measures()))


@tool
def garment_solid_save(path: str) -> str:
    """Write the solid to an OBJ file."""
    return _ok(_solid.save(_ledger(), path, _measures()))


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------

@tool
def measure_taken(spot: str, value: float, unit: str, source: str,
                  by: str = "") -> str:
    """Record a measured length. **A number with no unit is not accepted.**"""
    m = _measures()
    try:
        e = m.measured(spot, value, unit, source, by)
    except ValueError as ex:
        return _refused(ex)
    m.save(_p("measures.json"))
    return _ok({"verdict": "ANSWER", "entry": e.__dict__})


@tool
def measure_ratio(spot: str, value: float, basis: str, source: str = "") -> str:
    """Record a ratio against another measurement. Calculated, never measured."""
    m = _measures()
    try:
        e = m.ratio(spot, value, basis, source)
    except ValueError as ex:
        return _refused(ex)
    m.save(_p("measures.json"))
    return _ok({"verdict": "ANSWER", "entry": e.__dict__})


@tool
def measure_sheet() -> str:
    """Every measurement, with two readings of one spot reported as contested."""
    return _ok(_measures().sheet())


# ---------------------------------------------------------------------------
# Pattern, marks, sewing
# ---------------------------------------------------------------------------

@tool
def pattern_save(path: str) -> str:
    """Draft the pattern and write it to SVG at 1:1."""
    try:
        return _ok(_pattern.save(_measures(), path))
    except ValueError as e:
        return _refused(e)


@tool
def pattern_dxf(path: str) -> str:
    """Write the pattern to a DXF R12 file a real CAD system can open.

    The sewing line and the cut line (sewing line plus seam allowance) are
    different curves on separate layers; notches and grain lines become real
    geometry. No ASTM D6673 / DXF-AAMA conformance is claimed — that standard
    was withdrawn in 2019 with no replacement.
    """
    try:
        return _ok(_dxf.save(_measures(), path))
    except ValueError as e:
        return _refused(e)


@tool
def pattern_marks() -> str:
    """Notches, seam allowance and grain lines.

    Edge lengths matching does not tell you what to align with what. A notch
    is a promise between two pieces, and one with no partner is not passed
    through. Seam allowance is not stored: it is the difference between the
    sewing line and the cut line.
    """
    draft = _pattern.draft(_measures())
    if draft.get("verdict") != "ANSWER":
        return _ok(draft)
    return _ok(_marks.apply(draft))


@tool
def pattern_numbers() -> str:
    """Number every place on the pattern so an adjustment can be pointed at.

    "Loosen 30 to 35" only works if 35 is the same place next time round. The
    number is derived from the address (piece, edge, position along it), not
    handed out by walking a list, so adding a piece never moves an existing
    number. The registry is append-only and persisted beside the measures.
    """
    draft = _pattern.draft(_measures())
    if draft.get("verdict") != "ANSWER":
        return _ok(draft)
    reg = _numbering()
    out = _points.label(draft, reg)
    if out.get("verdict") == "ANSWER":
        _p("numbers.json").write_text(
            _json.dumps(reg.to_json(), ensure_ascii=False, indent=2),
            encoding="utf-8")
    return _ok(out)


@tool
def pattern_where(number: int) -> str:
    """What place a number points at. A number nobody registered is refused."""
    return _ok(_points.resolve(_numbering(), int(number)))


@tool
def pattern_span(first: int, last: int) -> str:
    """Turn "30 to 35" into a stretch of one edge.

    A span whose ends sit on two different edges is refused rather than
    guessed: nobody can say what "loosen it" would mean across the gap.
    """
    return _ok(_points.span(_numbering(), int(first), int(last)))


@tool
def pattern_dart_add(piece: str, edge: str, t: float, intake_cm: float,
                     length_cm: float = 0.0, role: str = "") -> str:
    """Add a dart taken perpendicular to its edge, and open it.

    A dart is a wedge cut out so its two legs can be sewn together and the
    flat panel becomes a cone. Taken perpendicular, both legs are equal by
    construction. Darts are stored beside the pattern, never written into
    the outline: inserting their legs as vertices would move every number
    on that piece.
    """
    return _dart_call(_darts.dart(piece, edge, float(t), float(intake_cm),
                                  float(length_cm), role))


@tool
def pattern_dart_toward(piece: str, edge: str, t: float, intake_cm: float,
                        toward_x: float, toward_y: float,
                        role: str = "") -> str:
    """Add a dart aimed at a point — how real drafting places one.

    A shoulder dart points at the bust apex, which is not perpendicular to
    its edge, so its legs start out unequal. The dart is TRUED: its centre
    slides along the edge until the legs match, keeping the intake. The
    answer reports the t it moved from.
    """
    return _dart_call(_darts.dart(piece, edge, float(t), float(intake_cm),
                                  0.0, role,
                                  toward=(float(toward_x), float(toward_y))))


@tool
def pattern_darts() -> str:
    """Every dart on the current pattern, opened, with what each one refuses."""
    return _dart_call(None)


@tool
def mannequin_form() -> str:
    """The dress form built from the measurements, with its assumptions named.

    It is a torso: hip at y=0 up to the neckline. There is no body above or
    below that, and the tool says so rather than pretending. The depth of
    each cross-section is an ASSUMPTION (a ratio of the width) — a girth is
    a circumference, not a width, and separating them needs somebody to
    measure.
    """
    return _ok(_mq.build(_measures()))


@tool
def mannequin_dress(fabric: str = "wool melton",
                    iterations: int = 400, gap_cm: float = 1.0) -> str:
    """Place the garment on the form. **This is a picture, not a fit.**

    Every point is pushed out to the form's surface plus an air gap, so the
    clearance of the result is that gap everywhere by construction. Reading
    fit off this output would be a measurement that cannot come out wrong.
    Use `mannequin_clearance` for the fit reading.
    """
    pts = _fallen(fabric, int(iterations))
    if isinstance(pts, str):
        return pts
    return _ok(_mq.dress(_mq.build(_measures()), pts, gap=float(gap_cm)))


@tool
def mannequin_clearance(fabric: str = "wool melton",
                        iterations: int = 400,
                        cling_cm: float = 1.5) -> str:
    """Distance from the garment **as it fell** to the form. The fit reading.

    Negative means the cloth is inside the body. That is not a defect report
    — the drape does not compute collision, so it falls through. It is the
    only number that says where, and by how much, before contact physics
    exists. On the reference coat: 101 of 297 points inside the body, worst
    -14.4256 cm.
    """
    pts = _fallen(fabric, int(iterations))
    if isinstance(pts, str):
        return pts
    return _ok(_mq.clearance(_mq.build(_measures()), pts,
                             cling_cm=float(cling_cm)))


@tool
def marker_lay(fabric_width_cm: float, cut_json: str,
               seam_allowance_cm: float, nap: str = "") -> str:
    """How much cloth to buy, and where each piece sits on it.

    Three things the pattern does not carry are refused rather than guessed:
    how many of each piece to cut, the seam allowance (the draft is the
    SEWING line, so a figure taken from it always comes up short), and the
    fabric width. `cut_json` is like {"後身頃": 1, "前身頃": 2, "袖": 2}.

    The length is an UPPER bound: pieces are laid as bounding rectangles on
    shelves, and a real marker interlocks their concave shapes. Safe in the
    direction of buying cloth; not the minimum.
    """
    try:
        cut = _json.loads(cut_json) if cut_json else {}
    except ValueError as e:
        return _refused(e)
    if not isinstance(cut, dict):
        return _ok({"verdict": _marker.NO_COUNT,
                    "how_to_close": 'cut_json は {"裁片名": 枚数} の形で'})
    return _ok(_marker.lay(_pattern.draft(_measures()),
                           float(fabric_width_cm),
                           {str(k): int(v) for k, v in cut.items()},
                           float(seam_allowance_cm),
                           nap=(nap or None)))


@tool
def bom_estimate(fabric_width_cm: float, cut_json: str,
                 seam_allowance_cm: float, thread_ratio: float = 0.0,
                 notions_json: str = "", interfacing_json: str = "",
                 nap: str = "") -> str:
    """What to buy to make this garment once — known lines and refused lines.

    Fabric comes straight from `marker_lay` (not recomputed here). Thread
    needs a consumption ratio this project does not record — pass
    `thread_ratio` (seam length x ratio) or get
    UNKNOWN_THREAD_RATIO_NOT_STATED naming the seam length anyway. Notions
    and interfacing are not in the pattern at all; declare them as JSON
    objects (`notions_json`, e.g. `{"ボタン": 6}`) or get a named refusal.
    There is no total: fabric is metres, thread is metres, notions are a
    count, and none of it has a price.
    """
    try:
        cut = _json.loads(cut_json) if cut_json else {}
        notions = _json.loads(notions_json) if notions_json else {}
        interfacing = _json.loads(interfacing_json) if interfacing_json else {}
    except ValueError as e:
        return _refused(e)
    if not isinstance(cut, dict):
        return _ok({"verdict": _marker.NO_COUNT,
                    "how_to_close": 'cut_json は {"裁片名": 枚数} の形で'})
    if not isinstance(notions, dict) or not isinstance(interfacing, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "how_to_close": "notions_json / interfacing_json は"
                                    "オブジェクトの形で"})
    return _ok(_bom.estimate(_pattern.draft(_measures()),
                             float(fabric_width_cm),
                             {str(k): int(v) for k, v in cut.items()},
                             float(seam_allowance_cm),
                             thread_ratio=(float(thread_ratio)
                                          if thread_ratio else None),
                             notions=(notions or None),
                             interfacing=(interfacing or None),
                             nap=(nap or None)))


@tool
def sew_and_drape(fabric: str, iterations: int = 2000, cell: float = 6.0) -> str:
    """Sew the pieces along their named edges and let the cloth fall.

    Seams come from the pattern's named edges, never from what happened to be
    nearby. Judged by the worst stitch, never the mean.
    """
    mat = _fabric(fabric)
    if mat.get("verdict") != "ANSWER":
        return _ok(mat)
    return _ok(_sew.validate(_measures(), mat, cell=cell,
                                    iterations=iterations))


@tool
def drape_validate(fabric: str, width: float = 40.0, height: float = 40.0,
                   iterations: int = 300) -> str:
    """Run the five drape checks on a plain square of the fabric.

    If one fails, no shape is returned — a wrinkle decided by update order or
    by the starting positions must not be shown as physics.
    """
    mat = _fabric(fabric)
    if mat.get("verdict") != "ANSWER":
        return _ok(mat)
    from . import garment_drape
    return _ok(garment_drape.validate(width, height, mat, iterations=iterations))


def _fabric(name: str) -> Dict[str, Any]:
    """Fabric properties, read from ~/.photoloset/fabrics.json.

    The parent project keeps these on the coordinate memory, which is not part
    of this package. Here it is a plain file, and an absent or incomplete entry
    refuses rather than being filled in with a default — a guessed gsm changes
    how the whole garment hangs.
    """
    path = _p("fabrics.json")
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        table = {}
    row = table.get(name)
    if not isinstance(row, dict):
        return {"verdict": "UNKNOWN_NO_MATERIAL", "fabric": name,
                "how_to_close": f'add "{name}" to {path} with gsm, thickness '
                                f'and stiffness, each with a source'}
    missing = [k for k in ("gsm", "thickness", "stiffness") if k not in row]
    if missing:
        return {"verdict": "UNKNOWN_NO_MATERIAL", "fabric": name,
                "missing": missing,
                "how_to_close": f'add {", ".join(missing)} for "{name}" in {path}'}
    out = {"verdict": "ANSWER", "fabric": name}
    out.update(row)
    return out


# ---------------------------------------------------------------------------
# The reference body
# ---------------------------------------------------------------------------

@tool
def body_reference(size: str = "M") -> str:
    """Reference body measurements. **This is not the wearer.**

    It is what the garment is compared against. Nobody has observed the
    person who will wear this.
    """
    try:
        return _ok(_body.body(size))
    except ValueError as e:
        return _refused(e)


@tool
def body_grade(base_size: str = "M", sizes: str = "") -> str:
    """The reference body across sizes."""
    try:
        want = [x.strip() for x in sizes.split(",") if x.strip()] or None
        return _ok(_body.grade(_measures(), base_size, want))
    except (ValueError, TypeError) as e:
        return _refused(e)


@tool
def body_ease(size: str = "M") -> str:
    """Garment minus body, per measurement. Arithmetic, not a fit judgement."""
    try:
        return _ok(_body.ease(_measures(), size))
    except ValueError as e:
        return _refused(e)


# ---------------------------------------------------------------------------
# Design and rights
# ---------------------------------------------------------------------------

@tool
def design_sheet() -> str:
    """Design changes, and what each was derived from."""
    return _ok(_design().sheet())


@tool
def design_history(part: str, aspect: str) -> str:
    """How one aspect got to where it is."""
    return _ok({"verdict": "ANSWER",
                "history": _design().history(part, aspect)})


@tool
def rights_intent(intent: str) -> str:
    """Declare what this is for. The answer to "may I make this" depends on it."""
    r = _rights()
    try:
        r.intent = intent
    except ValueError as e:
        return _refused(e)
    r.save(_p("rights.json"))
    return _ok({"verdict": "ANSWER", "intent": r.intent})


@tool
def rights_report() -> str:
    """Where each claim about this garment came from."""
    from .garment import PARTS
    return _ok(_rights().report(PARTS))


@tool
def rights_may_i_make_this() -> str:
    """Whether the recorded provenance supports the declared intent.

    It reports what was recorded. It is not legal advice and does not pretend
    to be a clearance.
    """
    return _ok(_rights().may_i_make_this(_design()))


# ---------------------------------------------------------------------------
# Prompts — per-model, for the agent loop
# ---------------------------------------------------------------------------

@tool
def garment_prompt_for_model(model_id: str = "") -> str:
    """The decomposition prompt for a model. Switching models switches prompts."""
    from . import prompts as _prompts
    return _ok(_prompts.for_model(model_id))


@tool
def garment_parse_decomposition(json_text: str = "", model_id: str = "") -> str:
    """Validate a model's part decomposition. Refusals are values; nothing guessed."""
    from . import prompts as _prompts
    r = _prompts.parse_decomposition(model_id or "default", json_text)
    if r.get("verdict") == "ANSWER":
        r["proposals"] = _prompts.to_proposals(r)
        r["siglip_queries"] = _prompts.siglip_queries(r)
    return _ok(r)


@tool
def garment_siglip_queries(families: str = "") -> str:
    """The always-on similarity model's query bank (optionally per family)."""
    from . import prompts as _prompts
    fams = [f.strip() for f in families.split(",") if f.strip()] or None
    return _ok({"verdict": "ANSWER",
                "queries": _prompts.siglip_queries(families=fams)})


@tool
def garment_adjust(json_text: str = "") -> str:
    """Adjust zones by number ("2": +1.5, "6-9": -1.0) and re-compose."""
    from . import compose as _compose
    from . import zones as _zones
    try:
        req = json.loads(json_text) if json_text.strip() else {}
    except json.JSONDecodeError:
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text は {graph, adjustments} の JSON です"})
    a = _zones.apply(req.get("graph") or {},
                     req.get("adjustments") or {})
    if a.get("verdict") != "ANSWER":
        return _ok(a)
    r = _compose.compose(a["graph"], _measures())
    return _ok({"verdict": r.get("verdict", "ERROR"),
                "applied": a["applied"],
                "note": a["note"],
                "draft": {k: v for k, v in r.items()
                          if k in ("verdict", "label", "pieces",
                                   "seam_checks", "total_area_cm2"
                                   if "total_area_cm2" in r else "seam_specs",
                                   "zones")}})


@tool
def garment_compose(json_text: str = "") -> str:
    """Compose a garment from a parts graph. Open ports are named, never filled."""
    from . import compose as _compose
    try:
        graph = json.loads(json_text) if json_text.strip() else {}
    except json.JSONDecodeError:
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text は部品グラフの JSON です"})
    # 台帳から読む。他の寸法依存の道具と同じ台帳でなければ、
    # measure_sheet に見えている寸法を compose が「欠けている」と言う。
    # 台帳が空のままでも、欠けている寸法の名前を型付きで返す。
    # 勝手に既定値で引かない。
    return _ok(_compose.compose(graph, _measures()))


# ---------------------------------------------------------------------------
# The look loop: resemble -> construct -> confirm -> approve -> search
#
# The ORDER is load-bearing. Approval comes BEFORE the sewing-method search,
# never after: a method retrieved for the wrong garment is a plausible wrong
# answer, and plausible wrong answers reach cutting tables. `sewing_methods`
# below therefore takes an approval id and a corpus name and NOTHING ELSE —
# no draft, no graph, no structure, no image, no json_text — and a check walks
# these signatures against `sewing_search.FORBIDDEN_PARAMETERS` so a
# convenience overload turns the suite red instead of opening the gate.
# ---------------------------------------------------------------------------

def _json_arg(json_text: str, what: str):
    try:
        return (json.loads(json_text) if json_text.strip() else {}), None
    except json.JSONDecodeError as e:
        return None, {"verdict": "UNKNOWN_BAD_ARGUMENTS",
                      "why": f"json_text is {what}: {e}"}


@tool
def garment_resemble(json_text: str = "") -> str:
    """Ask what each PART resembles. Refuses by name when nothing is registered.

    `json_text` is `{"image": ..., "image_id": ..., "parts": [{"instance",
    "part"}], "queries": [...], "whole": false}`. photoloset ships no model, so
    without a registered backend this answers UNKNOWN_NO_RETRIEVAL_BACKEND
    with what would close it — never an empty list, which would say "nothing
    is similar" when the true sentence is "nothing was asked".
    """
    from . import resemble as _resemble
    req, err = _json_arg(json_text, '{image, image_id, parts, queries}')
    if err:
        return _ok(err)
    if req.get("whole"):
        return _ok(_resemble.whole(req.get("image"),
                                   queries=req.get("queries") or [],
                                   image_id=str(req.get("image_id") or "")))
    return _ok(_resemble.per_part(req.get("image"),
                                  req.get("parts") or [],
                                  regions=req.get("regions"),
                                  queries=req.get("queries") or [],
                                  image_id=str(req.get("image_id") or "")))


@tool
def garment_construct(json_text: str = "") -> str:
    """Build the garment a retrieval implies. Refuses the WHOLE construction.

    `json_text` is the structure from `resemble.structure_from`. A retrieved
    part the library cannot draft refuses everything and lists every offender:
    a garment silently missing its cape collects approval for the wrong
    garment.
    """
    from . import compose as _compose
    req, err = _json_arg(json_text, "the retrieved structure")
    if err:
        return _ok(err)
    g = _compose.graph_from(req)
    if g["verdict"] != "ANSWER":
        return _ok(g)
    draft = _compose.compose(g["graph"], _measures())
    return _ok({"verdict": draft.get("verdict", "ERROR"),
                "graph": g["graph"], "named": g["named"],
                "renamed": g["renamed"], "draft": draft})


@tool
def garment_confirm_sheet(json_text: str = "") -> str:
    """The confirmation sheet: a claim list and a solid, never a verdict.

    `json_text` is `{"graph": ..., "retrieval": ..., "image_ref": ...}`. The
    3D is the falsifier for the retrieval — "cosine 0.83 to garment A" cannot
    be checked by a human and "here is the garment that implies" can.
    """
    from . import compose as _compose
    from . import confirm as _confirm
    req, err = _json_arg(json_text, "{graph, retrieval, image_ref}")
    if err:
        return _ok(err)
    graph = req.get("graph") or {}
    if not graph:
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "a sheet is about a part graph",
                    "how_to_close": "pass {graph: ...} from garment_construct"})
    draft = _compose.compose(graph, _measures())
    return _ok(_confirm.sheet(draft, image_ref=str(req.get("image_ref") or ""),
                              retrieval=req.get("retrieval"),
                              intake=_intake(), graph=graph,
                              renamed=req.get("renamed")))


@tool
def garment_approve_shape(json_text: str = "", by: str = "") -> str:
    """Approve the shape. **An adoption, with a name on it, and it opens the gate.**

    `json_text` is `{"sheet": ..., "answers": {claim_id: yes|no|cannot_tell},
    "graph": ...}`. An empty `by` is refused by the ledger itself
    (UNKNOWN_NO_ADOPTER), not by this door — an earlier version put that check
    in the door and measurement V60 walked around it.
    """
    from . import confirm as _confirm
    req, err = _json_arg(json_text, "{sheet, answers, graph}")
    if err:
        return _ok(err)
    sheet_obj = req.get("sheet") or {}
    if not sheet_obj:
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "an approval is of a confirmation sheet",
                    "how_to_close": "pass {sheet: ...} from "
                                    "garment_confirm_sheet"})
    led = _ledger()
    r = _confirm.approve(sheet_obj, req.get("answers") or {}, by, led,
                         graph=req.get("graph"))
    if r.get("verdict") == "ANSWER":
        led.save(_p("ledger.json"))
    return _ok(r)


@tool
def garment_reject_shape(json_text: str = "", which: str = "", by: str = "",
                         note: str = "") -> str:
    """Reject NAMED claims. There is no field here for "the mesh looks bad".

    `which` is a comma-separated list of claim ids from the sheet. An empty
    one is UNKNOWN_UNNAMED_REJECTION and an unknown one is
    UNKNOWN_NO_SUCH_CLAIM, so a correct retrieval cannot be killed by an ugly
    render.
    """
    from . import confirm as _confirm
    req, err = _json_arg(json_text, "{sheet: ...}")
    if err:
        return _ok(err)
    ids = [x.strip() for x in which.split(",") if x.strip()]
    return _ok(_confirm.reject(req.get("sheet") or {}, ids, by, note))


@tool
def sewing_methods(approval_id: str = "", corpus: str = "") -> str:
    """Sewing methods for an APPROVED shape. **No other argument exists.**

    The block is on the SEARCH, not on the display of its results. Without an
    adopted approval this answers UNKNOWN_SHAPE_NOT_APPROVED; with one whose
    shape has since moved, UNKNOWN_APPROVAL_STALE; and with an approval and no
    corpus, UNKNOWN_NO_SEWING_CORPUS naming the corpora that would close it —
    this tree ships none.
    """
    from . import sewing_search as _search
    _search.bind(ledger=_ledger(), measures=_measures(), rights=_rights())
    return _ok(_search.methods_for(approval_id, corpus))


# ---------------------------------------------------------------------------
# Present in the parent project, absent here
# ---------------------------------------------------------------------------

@tool
def garment_cross() -> str:
    """Absent: the ledger as coordinates on the stereo cross."""
    return _absent("The coordinate-memory view",
                   "use the Verantyx engine, which carries the cross store")


for _name, _what in [
    ("fabric_record", "Recording fabric properties on the coordinate memory"),
    ("fabric_report", "The fabric report"),
    ("fabric_layer_fit", "Layering as subtraction"),
    ("fabric_cloth_estimate", "Cloth quantity estimation"),
]:
    def _make(what: str) -> Callable[..., str]:
        def _absent_tool() -> str:
            return _absent(what, "use the Verantyx engine; here, put fabric "
                                 "properties in ~/.photoloset/fabrics.json")
        return _absent_tool
    _fn = _make(_what)
    _fn.__name__ = _name
    _fn.__doc__ = f"Absent: {_what.lower()}."
    TOOLS[_name] = _fn


# ---------------------------------------------------------------------------
# The protocol
# ---------------------------------------------------------------------------

def _list() -> Dict[str, Any]:
    out = []
    for name, fn in sorted(TOOLS.items()):
        doc = inspect.getdoc(fn) or ""
        out.append({"name": name, "description": doc,
                    "inputSchema": _schema(fn)})
    return {"tools": out}


def _call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    fn = TOOLS.get(name)
    if fn is None:
        return {"content": [{"type": "text", "text": _ok(
            {"verdict": "UNKNOWN_NO_SUCH_TOOL", "tool": name})}],
            "isError": True}
    try:
        text = fn(**(args or {}))
    except TypeError as e:
        text = _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS", "why": str(e)})
    except Exception as e:                                   # noqa: BLE001
        # A crash is not a refusal, and must not be dressed up as one.
        text = _ok({"verdict": "ERROR", "why": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc()[-1200:]})
    return {"content": [{"type": "text", "text": text}]}


def handle(req: Dict[str, Any]) -> Any:
    method = req.get("method")
    if method == "initialize":
        return {"protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "photoloset", "version": "0.0.0"}}
    if method in ("notifications/initialized", "initialized"):
        return None                                          # a notification
    if method == "tools/list":
        return _list()
    if method == "tools/call":
        p = req.get("params") or {}
        return _call(p.get("name", ""), p.get("arguments") or {})
    if method == "ping":
        return {}
    raise LookupError(f"unknown method: {method}")


def serve() -> int:
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        try:
            result = handle(req)
        except LookupError as e:
            if rid is not None:
                out.write(json.dumps({"jsonrpc": "2.0", "id": rid,
                                      "error": {"code": -32601,
                                                "message": str(e)}}) + "\n")
                out.flush()
            continue
        if rid is None:                     # notification: no reply, ever
            continue
        out.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result},
                             ensure_ascii=False) + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
