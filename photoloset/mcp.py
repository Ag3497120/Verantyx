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
import sys
import traceback
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


def _ok(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _refused(exc: BaseException) -> str:
    """A raised refusal, turned back into the typed value it should have been."""
    text = str(exc)
    code = text.split(":", 1)[0] if ":" in text else "UNKNOWN_REFUSED"
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
    """Derive the input schema from the signature — one source of truth."""
    props: Dict[str, Any] = {}
    required: List[str] = []
    for name, par in inspect.signature(fn).parameters.items():
        kind = _SCHEMA_TYPE.get(par.annotation, "string")
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
                "serverInfo": {"name": "photoloset", "version": "0.1.0"}}
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
