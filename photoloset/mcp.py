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
import base64
import hashlib
import json
import json as _json
import sys
import traceback
import typing
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

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

#: 置き場の根。既定は ``~/.photoloset`` で、``PHOTOLOSET_HOME`` が立って
#: いればそちらを使う。
#:
#: **切り替え口が無いことが、一度実害を出した。** 2026-08-27、この道具を
#: 試していた作業者が ``PHOTOLOSET_HOME=$(mktemp -d)`` で隔離したつもりで
#: ``measure_taken`` を呼び、持ち主の実測6件が入った本物の帳面に、試験用の
#: 数字8件(chest 88 / waist 68 / hip 94 / body_length 140 を二巡)を書いた。
#: 実測の chest 108 が試験の 88 に上書きされて見える状態になっていた。
#: 読み取りは ``Path.home()`` を決め打ちしていて、環境変数を一度も見て
#: いなかった — **隔離したつもりが隔離になっていなかった。**
#:
#: 取り込み時に一度だけ読む。動作中に差し替わらないのは意図で、
#: 同じ処理の途中で置き場が変わるほうが危ない。
_OS_HOME = Path(os.environ.get("HOME") or Path.home())
HOME = Path(os.environ.get("PHOTOLOSET_HOME") or (_OS_HOME / ".photoloset"))
PROTOCOL = "2024-11-05"

# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------

#: 置き場をプロジェクトごとに分ける。
#:
#: **以前は全部が一つの平らな置き場だった。** UI に「プロジェクト」の一覧が
#: 出ていて、別の服を選ぶと行の色は変わるのに、開いている服も台帳も変わら
#: なかった — **分離されているように見えて、されていない**という、見えて
#: 動かないより悪い状態。ここがその根。
PROJECTS = HOME / "projects"
#: いま開いているプロジェクトの名前を持つ一行のファイル。
CURRENT = HOME / "current_project"
DEFAULT_PROJECT = "default"

#: **この服のものではなく、世界のもの。** 生地の帳面は「あなたが持っている
#: 材料」の記録で、どの服を作っていても同じ。だから共有に残す。
_SHARED = ("fabrics.json",)


def _safe_project(name: str) -> Optional[str]:
    """プロジェクト名として使えるか。**使えない名前は経路になる前に断る。**

    名前はそのままディレクトリ名になるので、``..`` や区切り文字が通ると
    置き場の外へ書ける。
    """
    n = (name or "").strip()
    if not n or n in (".", ".."):
        return None
    if any(c in n for c in "/\\\0") or n.startswith("."):
        return None
    return n


def _migrate_once() -> Optional[Dict[str, Any]]:
    """平らな置き場を ``projects/default/`` へ一度だけ移す。

    **べき等。** ``projects/`` が既にあれば何もしない。移すのは名前の
    付け替え(rename)で、同じファイルシステム内では原子的。共有は動かさない。
    """
    if PROJECTS.exists():
        return None
    movable = [f for f in HOME.glob("*.json") if f.name not in _SHARED]
    if not movable:
        return None
    dest = PROJECTS / DEFAULT_PROJECT
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for f in movable:
        f.rename(dest / f.name)
        moved.append(f.name)
    return {"migrated_to": DEFAULT_PROJECT, "files": sorted(moved)}


def _project() -> str:
    """いま開いているプロジェクト。無ければ ``default``。"""
    try:
        n = _safe_project(CURRENT.read_text(encoding="utf-8"))
        if n:
            return n
    except OSError:
        pass
    return DEFAULT_PROJECT


def _p(name: str) -> Path:
    HOME.mkdir(parents=True, exist_ok=True)
    if name in _SHARED:
        return HOME / name
    _migrate_once()
    d = PROJECTS / _project()
    d.mkdir(parents=True, exist_ok=True)
    return d / name


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


def _json_safe_export_package(package: Mapping[str, Any]) -> Dict[str, Any]:
    """Carry exact in-memory artifacts over JSON without writing files."""
    out = dict(package)
    files = package.get("files")
    if not isinstance(files, Mapping):
        return out
    encoded: Dict[str, Any] = {}
    for filename, content in files.items():
        if isinstance(content, bytes):
            encoded[str(filename)] = {
                "representation": "base64",
                "data": base64.b64encode(content).decode("ascii"),
                "bytes": len(content),
            }
        else:
            text = str(content)
            encoded[str(filename)] = {
                "representation": "text", "text": text,
                "bytes": len(text.encode("utf-8")),
            }
    out["files"] = encoded
    out["transport"] = "JSON text or base64; no filesystem write performed"
    return out


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
    # A source selected for the first time has no clips, so ``s.__dict__``
    # happened to serialize.  Selecting the same image again returns the
    # existing Source, whose nested ``clips`` are Clip dataclass instances;
    # the entire MCP answer then became UNKNOWN_UNIDENTIFIABLE_VALUE and the
    # Swift composer never published the selection.  Recursively lower the
    # provenance record to JSON instead of making reselection depend on
    # whether the source already has clips.
    return _ok({"verdict": "ANSWER", "source": asdict(s)})


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


def _surface_edges(faces):
    """Unique undirected mesh edges in deterministic first-seen order."""
    seen = set()
    edges = []
    for face in faces:
        if not isinstance(face, (list, tuple)) or len(face) < 3:
            continue
        for index, start in enumerate(face):
            end = face[(index + 1) % len(face)]
            if not isinstance(start, int) or not isinstance(end, int):
                continue
            if start == end:
                continue
            key = (min(start, end), max(start, end))
            if key not in seen:
                seen.add(key)
                edges.append([start, end])
    return edges


def _dress_photo_surface(surface, gap_cm: float):
    """Preserve a photo-derived silhouette while adding a radial air gap."""
    if not isinstance(surface, dict) or surface.get("verdict") != "ANSWER":
        return {"verdict": "UNKNOWN_PHOTO_SURFACE_NOT_ANSWER",
                "how_to_close": "pass garment_surface from an ANSWER photo_pattern result"}
    verts = surface.get("verts")
    faces = surface.get("faces")
    if not isinstance(verts, list) or not isinstance(faces, list):
        return {"verdict": "UNKNOWN_PHOTO_SURFACE_GEOMETRY_MISSING",
                "how_to_close": "photo surface must contain verts and faces"}
    points = []
    for point in verts:
        if not isinstance(point, (list, tuple)) or len(point) != 3:
            return {"verdict": "UNKNOWN_PHOTO_SURFACE_VERTEX_INVALID"}
        x, y, z = (float(point[0]), float(point[1]), float(point[2]))
        radial = (x * x + z * z) ** 0.5
        if radial > 1e-12:
            scale = (radial + float(gap_cm)) / radial
            x, z = x * scale, z * scale
        points.append([x, y, z])
    edges = _surface_edges(faces)
    return {
        "verdict": "ANSWER",
        "points": points,
        "edges": edges,
        "owner": ["photo_pattern"] * len(points),
        "gap_cm": float(gap_cm),
        "source": "photo_pattern.garment_surface",
        "generated_not_evidence": (
            "写真由来の投影幅から生成した面です。奥行、背面、素材挙動は"
            "観測ではなく、photo_pattern が明示した仮定を保ちます"),
    }


@tool
def mannequin_dress(fabric: str = "wool melton",
                    iterations: int = 400, gap_cm: float = 1.0,
                    garment_json: str = "") -> str:
    """Place the garment on the form. **This is a picture, not a fit.**

    Every point is pushed out to the form's surface plus an air gap, so the
    clearance of the result is that gap everywhere by construction. Reading
    fit off this output would be a measurement that cannot come out wrong.
    Use `mannequin_clearance` for the fit reading.

    If ``garment_json`` contains ``photo_pattern.garment_surface``, that exact
    image-derived geometry is used.  An empty value retains the legacy current
    project pattern route.
    """
    if garment_json.strip():
        req, err = _json_arg(garment_json,
                             '{"garment_surface": photo_pattern surface}')
        if err:
            return _ok(err)
        surface = req.get("garment_surface") if isinstance(req, dict) else None
        return _ok(_dress_photo_surface(surface, float(gap_cm)))
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
def project_current() -> str:
    """Which garment project is open, and where its store sits."""
    _p("ledger.json")
    d = PROJECTS / _project()
    return _ok({"verdict": "ANSWER", "project": _project(), "path": str(d),
                "files": sorted(f.name for f in d.glob("*.json")),
                "shared": {n: str(HOME / n) for n in _SHARED},
                "shared_why": ("生地の帳面は「持っている材料」の記録で、"
                               "どの服を作っていても同じなので共有です")})


@tool
def project_list() -> str:
    """Every garment project, and which one is open."""
    _p("ledger.json")
    rows = []
    if PROJECTS.exists():
        for d in sorted(PROJECTS.iterdir()):
            if d.is_dir():
                rows.append({"project": d.name,
                             "files": sorted(f.name for f in d.glob("*.json")),
                             "open": d.name == _project()})
    return _ok({"verdict": "ANSWER", "projects": rows,
                "current": _project(), "count": len(rows)})


@tool
def project_new(name: str) -> str:
    """Start a garment project with its own store. **Empty, not a copy.**

    A new project begins with no measurements and no ledger, so the first
    thing it does is refuse — which is correct: nothing has been observed
    about this garment yet.
    """
    n = _safe_project(name)
    if n is None:
        return _ok({"verdict": "UNKNOWN_PROJECT_NAME_UNUSABLE", "name": name,
                    "how_to_close": ("名前はそのまま置き場のディレクトリに"
                                     "なります。区切り文字・.. ・先頭の . は"
                                     "使えません")})
    _p("ledger.json")
    d = PROJECTS / n
    if d.exists():
        return _ok({"verdict": "UNKNOWN_PROJECT_EXISTS", "project": n,
                    "how_to_close": "project_open で開いてください"})
    d.mkdir(parents=True)
    CURRENT.write_text(n, encoding="utf-8")
    return _ok({"verdict": "ANSWER", "project": n, "path": str(d),
                "opened": True,
                "starts_empty": ("実測も台帳もありません。最初の問いは"
                                 "拒否で返ります — この服についてはまだ"
                                 "何も観測されていないので")})


@tool
def project_open(name: str) -> str:
    """Open an existing garment project. Refuses one that does not exist."""
    n = _safe_project(name)
    if n is None:
        return _ok({"verdict": "UNKNOWN_PROJECT_NAME_UNUSABLE", "name": name})
    _p("ledger.json")
    d = PROJECTS / n
    if not d.is_dir():
        known = sorted(x.name for x in PROJECTS.iterdir()
                       if x.is_dir()) if PROJECTS.exists() else []
        return _ok({"verdict": "UNKNOWN_NO_SUCH_PROJECT", "project": n,
                    "known": known,
                    "how_to_close": "project_new で作るか、既存の名前を"})
    CURRENT.write_text(n, encoding="utf-8")
    return _ok({"verdict": "ANSWER", "project": n, "path": str(d),
                "files": sorted(f.name for f in d.glob("*.json"))})


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
    # **`drape_validate` does not require `bending`.** Its whole call chain
    # (`garment_drape.validate` -> `solve`) never reads `material["bending"]`
    # — confirmed by reading both, `bending` is not implemented for this
    # path (see `garment_sew.py`'s docstring). Requiring it here anyway
    # would refuse a real, already-answering fabric ledger entry for a
    # field with zero effect on this tool's own output — caught 2026-08-27
    # in an outside check, on the earlier version of this function that
    # required `bending` unconditionally for every caller.
    mat = _fabric(fabric, require_bending=False)
    if mat.get("verdict") != "ANSWER":
        return _ok(mat)
    from . import garment_drape
    return _ok(garment_drape.validate(width, height, mat, iterations=iterations))


def _fabric(name: str, *, require_bending: bool = True) -> Dict[str, Any]:
    """Fabric properties, read from ~/.photoloset/fabrics.json.

    The parent project keeps these on the coordinate memory, which is not part
    of this package. Here it is a plain file, and an absent or incomplete entry
    refuses rather than being filled in with a default — a guessed gsm changes
    how the whole garment hangs.

    `require_bending` defaults to True for the tools that actually feed
    `garment_sew.sew_and_drape` (bending is required there the same way
    weight and thickness already are, matching `garment_drape.material_from`'s
    own contract). Callers whose downstream computation never reads
    `bending` — currently only `drape_validate` — pass False, so a fabric
    missing only `bending` is not refused for a reason that does not apply
    to what that tool computes.
    """
    path = _p("fabrics.json")
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        table = {}
    row = table.get(name)
    required = ("gsm", "thickness", "stiffness",
               *(("bending",) if require_bending else ()))
    if not isinstance(row, dict):
        return {"verdict": "UNKNOWN_NO_MATERIAL", "fabric": name,
                "how_to_close": f'add "{name}" to {path} with '
                                f'{", ".join(required)}, each with a source'}
    # `bending` is required the same way the other three are, for callers
    # that actually consume it: no formula fills it in from gsm or
    # thickness, because that is the one axis a guessed number cannot
    # stand in for (it is what tells jersey from melton). Added
    # 2026-08-27, alongside garment_drape.material_from; scoped to the
    # callers that read it 2026-08-27 after an outside check found it
    # was refusing `drape_validate` calls for a field that tool never
    # uses (see the comment at that call site).
    missing = [k for k in required if k not in row]
    if missing:
        return {"verdict": "UNKNOWN_NO_MATERIAL", "fabric": name,
                "missing": missing,
                "how_to_close": f'add {", ".join(missing)} for "{name}" in {path}'}
    out = {"verdict": "ANSWER", "fabric": name}
    out.update(row)
    return out


# ---------------------------------------------------------------------------
# The geometric route: no corpus, no draft — mannequin.build -> flatten /
# curvature -> panels -> silhouette. Each of these reads the same skin-tight
# base as `mannequin_form` / `mannequin_dress` (`_mq.build(_measures())`),
# built fresh per call the same way those two already do it.
#
# `sewing_order_plan` sits apart from that chain: it reads the SEWN mesh from
# the DRAFTED pattern (`garment_sew.build` on the marked draft), the same
# `built` `_fallen` above already constructs for draping — not the geometric
# panels. It takes that built mesh, never the raw draft: a draft has named
# edges but no seams sewn yet, and `sewing_order.plan` answers
# UNKNOWN_NO_SEAMS on it rather than seam one silently.
# ---------------------------------------------------------------------------

@tool
def sewing_order_plan() -> str:
    """A sewing order for the drafted pattern, and whether it is minimal.

    Reports which seams sew FLAT (both sides still separate pieces) and
    which close IN_THE_ROUND, in an order that sews flat whenever it still
    can. The count that must be IN_THE_ROUND has a floor — seams minus
    pieces plus connected components — that no ordering can beat; the
    answer names it and says whether this order reached it
    (`at_the_minimum`). What it cannot say: whether a needle can physically
    reach a given seam once the round is closed — this only has pieces and
    which seams join them, not which side is inside.
    """
    from . import sewing_order as _so
    draft = _pattern.draft(_measures())
    if draft.get("verdict") != "ANSWER":
        return _ok(draft)
    built = _sew.build(_marks.apply(draft))
    return _ok(_so.plan(built))


@tool
def flatten_build(segments: int = 24, height_steps: int = 16,
                  gap_cm: float = 1.0, iterations: int = 3000) -> str:
    """Cut the skin-tight base open along one meridian and flatten it.

    The body is not developable (Gauss's Theorema Egregium: no surface with
    curvature can be flattened without stretching), so this never claims a
    good flattening — it relaxes a spring mesh toward each edge's 3D length
    and reports, triangle by triangle, how far the 2D result is off: area
    ratio and angle error. This is the whole tube cut along ONE seam, the
    worst case before any further division; `panels_cut` divides it into
    several pieces and measures how much distortion that buys back.
    """
    from . import flatten as _flat
    man = _mq.build(_measures())
    return _ok(_flat.build(man, gap=float(gap_cm), segments=int(segments),
                           height_steps=int(height_steps),
                           iterations=int(iterations)))


@tool
def curvature_mesh(segments: int = 24, height_steps: int = 16) -> str:
    """The mannequin surface as a triangle grid: vertices and faces.

    Coordinates come straight from the radius function, not from a second
    approximation on top of one. Feeds `curvature_angle_sums` directly —
    that tool takes any verts/faces in this shape, not only this mesh.
    """
    from . import curvature as _cv
    man = _mq.build(_measures())
    return _ok(_cv.mesh(man, int(segments), int(height_steps)))


@tool
def curvature_angle_sums(json_text: str = "") -> str:
    """Angle defect per vertex: 2*pi minus the summed triangle-fan corner angles.

    `json_text` is `{"verts": [[x, y, z], ...], "faces": [[i, j, k], ...]}`
    — the shape `curvature_mesh` returns, so the two chain directly. This is
    the actual discrete Gaussian curvature (triangle-fan angle defect); the
    four-neighbour grid sum some other flattening code uses is NOT the same
    quantity and does not converge to the right value on a closed surface.
    """
    req, err = _json_arg(json_text, '{"verts": [[x, y, z], ...], '
                                     '"faces": [[i, j, k], ...]}')
    if err:
        return _ok(err)
    verts = req.get("verts")
    faces = req.get("faces")
    if not isinstance(verts, list) or not isinstance(faces, list):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text needs both verts and faces, as lists"})
    from . import curvature as _cv
    try:
        sums = _cv.angle_sums([tuple(v) for v in verts],
                              [tuple(f) for f in faces])
    except (TypeError, ValueError, IndexError) as e:
        return _refused(ValueError(f"UNKNOWN_BAD_ARGUMENTS: {e}"))
    return _ok({"verdict": "ANSWER",
                "angle_sum_rad": sums,
                "angle_defect_rad": [_cv.TWO_PI - s for s in sums],
                "count": len(sums)})


@tool
def curvature_defect(segments: int = 24, height_steps: int = 16) -> str:
    """Total angle defect at ONE resolution, over interior vertices only.

    The neck and hip rings are the boundary, not interior vertices — their
    share of Gauss-Bonnet's total (2*pi per disc) is the boundary term
    (geodesic curvature), which this does not compute. One resolution alone
    does not say whether the number has converged; `curvature_report` does.
    """
    from . import curvature as _cv
    man = _mq.build(_measures())
    return _ok(_cv.curvature(man, int(segments), int(height_steps)))


def _resolutions_arg(resolutions_json: str):
    """``[[segments, height_steps], ...]`` or empty for the module's own
    refinement series. Returns ``(kwargs, error)`` — ``kwargs`` is ``{}``
    when empty, so the callee's own default (not a guess made here) applies.
    """
    if not resolutions_json.strip():
        return {}, None
    try:
        parsed = json.loads(resolutions_json)
    except json.JSONDecodeError as e:
        return None, _refused(e)
    if not isinstance(parsed, list) or not parsed:
        return None, _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                          "why": "resolutions_json is "
                                 "[[segments, height_steps], ...]"})
    try:
        return {"resolutions": [tuple(r) for r in parsed]}, None
    except TypeError as e:
        return None, _refused(ValueError(f"UNKNOWN_BAD_ARGUMENTS: {e}"))


@tool
def curvature_report(resolutions_json: str = "") -> str:
    """Total curvature, its per-band distribution, and whether refining agrees.

    `resolutions_json` is `[[segments, height_steps], ...]` with at least
    two steps (refinement is how convergence is shown at all); left empty,
    curvature.py's own series runs (20x12 up to 160x96 — well under a second
    on the reference body). Never converts the total into a dart size in cm
    — splitting it between outline curvature and darts is a pattern-making
    decision this makes on purpose, not a computation.
    """
    from . import curvature as _cv
    kwargs, err = _resolutions_arg(resolutions_json)
    if err:
        return err
    man = _mq.build(_measures())
    return _ok(_cv.report(man, **kwargs))


@tool
def curvature_compare_interpolation(resolutions_json: str = "") -> str:
    """Linear vs. smooth (spline) body interpolation, same grid series, side by side.

    Same `resolutions_json` shape as `curvature_report`. Left empty, this
    runs curvature.py's own comparison series up to a 640x384 grid — real
    on the reference body (measured: ~50s) — so pass a coarser
    `resolutions_json` (e.g. `[[20,12],[80,48]]`, ANSWERs in under a second)
    for a quick look. Says only whether the total agrees and whether the
    per-band distribution settles; never claims the smooth body is correct.
    """
    from . import curvature as _cv
    kwargs, err = _resolutions_arg(resolutions_json)
    if err:
        return err
    man = _mq.build(_measures())
    return _ok(_cv.compare_interpolation(man, **kwargs))


@tool
def panels_cut(n_panels: int = 4, segments: int = 24, height_steps: int = 16,
               iterations: int = 3000, dart_depth_ratio: float = 0.30) -> str:
    """Cut the flattened tube into `n_panels` pattern panels, worst distortion first.

    Each cut goes through the currently-worst panel's currently-worst
    internal grid line, then both sides are re-flattened independently and
    the distortion index is reported before and after — a measured drop,
    not an assumed one. Gauss-Bonnet's 360 degrees per panel is split into
    an interior share (handed to `darts.dart`) and a boundary share (the
    outline's own, free) and checked to sum back to exactly 360.
    Distortion never reaches zero — Theorema Egregium holds for any number
    of panels — only `distortion_bought_total_pct` says how much less.
    """
    from . import panels as _pn
    man = _mq.build(_measures())
    return _ok(_pn.cut(man, n_panels=int(n_panels), segments=int(segments),
                       height_steps=int(height_steps),
                       iterations=int(iterations),
                       dart_depth_ratio=float(dart_depth_ratio)))


@tool
def panels_to_pieces(json_text: str = "") -> str:
    """Turn a `panels_cut` result into the same `pieces` shape `pattern_dxf` etc. use.

    `json_text` is the WHOLE object `panels_cut` returned. The ring's
    closing seam (back to the original meridian cut) is declared here too,
    not left implicit — every panel's right edge meets the next panel's
    left edge, including the last back to the first.
    """
    req, err = _json_arg(json_text, "the object panels_cut returned")
    if err:
        return _ok(err)
    from . import panels as _pn
    return _ok(_pn.to_pieces(req))


@tool
def panels_compare_to_draft(json_text: str = "") -> str:
    """Panels next to the formula-drafted pattern. **Not a similarity claim.**

    `json_text` is the WHOLE object `panels_cut` returned; the draft is
    drawn fresh from the current ledger's measurements (the same call
    `pattern_dxf` makes), not passed in. The two routes start from the same
    measurements and are expected to land on visibly different piece counts
    and shapes — one carries drafting formulas, the other only a distortion
    measurement and no notion of "front" or "back".
    """
    req, err = _json_arg(json_text, "the object panels_cut returned")
    if err:
        return _ok(err)
    from . import panels as _pn
    return _ok(_pn.compare_to_draft(req, _pattern.draft(_measures())))


def _outline_arg(json_text: str):
    """``{"outline": [[x, y], ...]}`` — a closed 2D polygon, at least 3 points."""
    req, err = _json_arg(json_text, '{"outline": [[x, y], ...]}')
    if err:
        return None, _ok(err)
    outline = req.get("outline")
    if not isinstance(outline, list) or len(outline) < 3:
        return None, _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                          "why": "json_text needs \"outline\": a closed "
                                 "polygon of at least 3 [x, y] points"})
    try:
        return [tuple(p) for p in outline], None
    except TypeError as e:
        return None, _refused(ValueError(f"UNKNOWN_BAD_ARGUMENTS: {e}"))


@tool
def silhouette_match(json_text: str = "", segments: int = 24,
                     height_steps: int = 16, y_top: float = 0.0,
                     y_bottom: float = 0.0) -> str:
    """Fit the skin-tight base's radius, as a function of height, to a photo's outline.

    `json_text` is `{"outline": [[x, y], ...]}` — a closed 2D polygon, no
    image decoding involved (this package imports nothing that could). A
    front-view outline constrains projected WIDTH only; depth is not
    observed from one view, and this says so in the answer rather than
    inventing depth. `y_top`/`y_bottom` narrow the height range (0 for
    both uses the mannequin's full range). Refuses by name, with the worst
    offending height, when the outline cannot fit this one-parameter-per-
    height radial model — narrower than the body, or wider than the model
    can honestly represent.
    """
    outline, err = _outline_arg(json_text)
    if err:
        return err
    from . import silhouette as _sil
    man = _mq.build(_measures())
    return _ok(_sil.match(man, outline, segments=int(segments),
                          height_steps=int(height_steps),
                          y_top=(float(y_top) if y_top else None),
                          y_bottom=(float(y_bottom) if y_bottom else None)))


@tool
def silhouette_width_at(json_text: str = "", y: float = 0.0) -> str:
    """The outline's left/right x at one height — the primitive `silhouette_match` scans with.

    `json_text` is `{"outline": [[x, y], ...]}`. Only the outer two
    intersections are used, even if the polygon crosses this height more
    than twice — an inner crossing is evidence of a concavity, and this
    (like the visual hull it is part of) discards concavity evidence by
    construction rather than guessing which pair is the true edge.
    """
    outline, err = _outline_arg(json_text)
    if err:
        return err
    from . import silhouette as _sil
    w = _sil.outline_width_at(outline, float(y))
    if w is None:
        return _ok({"verdict": "UNKNOWN_NO_INTERSECTION_AT_HEIGHT", "y": float(y),
                    "how_to_close": "this outline has fewer than two "
                                    "crossings at this height — pass a y "
                                    "the polygon actually spans"})
    return _ok({"verdict": "ANSWER", "y": float(y),
                "left_x": w[0], "right_x": w[1], "width": w[1] - w[0]})


@tool
def silhouette_to_surface(json_text: str = "", segments: int = 24,
                          height_steps: int = 16, y_top: float = 0.0,
                          y_bottom: float = 0.0, gap_cm: float = 0.0) -> str:
    """`silhouette_match`, wired straight into a mesh. No new mesh code — this
    is `base_garment.build` fed the radius function `silhouette_match`'s
    result implies. Same `json_text` shape as `silhouette_match`; refuses
    the same way if the outline does not fit. `gap_cm` adds a further
    constant radial gap on top of the already-fitted ease (0 means the
    surface sits exactly on the fitted silhouette).
    """
    outline, err = _outline_arg(json_text)
    if err:
        return err
    from . import silhouette as _sil
    man = _mq.build(_measures())
    res = _sil.match(man, outline, segments=int(segments),
                     height_steps=int(height_steps),
                     y_top=(float(y_top) if y_top else None),
                     y_bottom=(float(y_bottom) if y_bottom else None))
    if res.get("verdict") != "ANSWER":
        return _ok(res)
    return _ok(_sil.to_surface(res, man, gap=float(gap_cm)))


@tool
def structure_from_outline(json_text: str = "") -> str:
    """Turn a front-view outline into garment STRUCTURE (parts and how they join).

    `json_text` is `{"outline": [[x, y], ...]}` — the same shape
    `silhouette_match` takes. Geometric route, not retrieval: unlike
    `garment_resemble` -> `resemble.structure_from`, this reads no image
    embedding, only the outline's own shape.

    TODO(when `photoloset/structure.py` lands): this calls
    `structure.from_outline(outline)` as its guess at that module's entry
    point — a sibling agent is writing that file separately and the real
    name may differ. Whoever wires it up for real: confirm the symbol name
    against what `structure.py` actually exports and fix the two lines
    below (the `getattr` name and this docstring) to match; the shape
    contract ("takes an outline, returns structure") is what was agreed,
    the symbol name is not.
    """
    outline, err = _outline_arg(json_text)
    if err:
        return err
    try:
        from . import structure as _structure
    except ImportError:
        return _absent("photoloset.structure",
                       "structure.py has not landed in this checkout yet — "
                       "a sibling agent is writing it; re-run once it has")
    fn = getattr(_structure, "from_outline", None)
    if fn is None:
        return _ok({"verdict": "UNKNOWN_NOT_IN_THIS_BUILD",
                    "why": "structure.py exists but has no from_outline(outline)",
                    "how_to_close": "TODO left in structure_from_outline: "
                                    "point the getattr(...) call at the real "
                                    "entry point structure.py landed with"})
    return _ok(fn(outline))


def _outline_record_arg(json_text: str):
    """THE OUTLINE CONTRACT, the whole thing — not just the bare polygon
    `_outline_arg` above extracts. `structure.from_outline` (and therefore
    `photo_to_pattern.run`) reads `width_px`/`height_px`/`source`/`fixture`
    too, so this keeps the whole object instead of throwing the rest away.
    """
    req, err = _json_arg(json_text, 'THE OUTLINE CONTRACT: {"outline": '
                                     '[[x, y], ...], "width_px":, '
                                     '"height_px":, "source":, "fixture":}')
    if err:
        return None, _ok(err)
    if not isinstance(req, dict) or "outline" not in req:
        return None, _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                          "why": "json_text needs the whole outline "
                                 "contract object, not a bare point list"})
    return req, None


@tool
def photo_pattern(json_text: str = "", n_panels: int = 4, segments: int = 24,
                  height_steps: int = 16, iterations: int = 3000,
                  dart_depth_ratio: float = 0.30, image_id: str = "",
                  preview_mannequin: bool = False) -> str:
    """One call: a photographed outline -> a cut pattern (`panels.to_pieces` shape).

    `json_text` is THE OUTLINE CONTRACT, the whole object: `{"outline":
    [[x, y], ...], "width_px":, "height_px":, "source":, "fixture":}` — px,
    image coordinates, the same thing `GarmentOutline.extract` on the Swift
    side produces. Measurements come from the current project's ledger
    (`_measures()`), the same store `pattern_dxf` and the other draft tools
    read — a single photo cannot supply real-world scale on its own.

    Runs `structure.from_outline` -> `mannequin.build` -> a px-to-cm
    calibration (this tool's own job; see `photo_to_pattern.py`'s module
    docstring for the assumption it makes and the measured ceiling on how
    much of the photo actually reaches the returned pieces) ->
    `silhouette.match` -> `silhouette.to_surface` -> `flatten.build` ->
    `panels.cut` -> `panels.to_pieces`. The answer always carries `hops`
    (verdict/count/seconds per stage) even on refusal, and `failed_hop`
    names where it stopped; every refusal is one of the six modules'
    already-typed verdicts, not a new name invented here.
    """
    record, err = _outline_record_arg(json_text)
    if err:
        return err
    from . import photo_to_pattern as _p2p
    measures = _measures()
    proposed = []
    if bool(preview_mannequin):
        # A preview body is an explicitly typed proposal, never persisted and
        # never promoted into the measurement ledger. These values merely let
        # a beginner inspect geometry before choosing/entering a mannequin.
        defaults = {"chest": 88.0, "waist": 68.0, "hip": 94.0,
                    "body_length": 140.0}
        preview = Measures(entries=list(measures.entries))
        measured_spots = {entry.spot for entry in preview.entries
                          if entry.kind == "measured"}
        for spot, value in defaults.items():
            if spot in measured_spots:
                continue
            preview.measured(spot, value, "cm",
                             source="PROPOSED_PREVIEW_MANNEQUIN")
            proposed.append({
                "spot": spot, "assumed": {"value": value, "unit": "cm"},
                "kind": "PROPOSED",
                "basis": "temporary standard preview mannequin; not measured and not saved",
                "how_to_close": "choose a mannequin size or enter measured body dimensions",
            })
        measures = preview
    result = _p2p.run(record, measures, n_panels=int(n_panels),
                      segments=int(segments),
                      height_steps=int(height_steps),
                      iterations=int(iterations),
                      dart_depth_ratio=float(dart_depth_ratio),
                      image_id=image_id)
    if proposed:
        result["preview_mannequin"] = {
            "state": "PROPOSED", "not_measurement": True,
            "values": proposed,
            "must_be_replaced_before_manufacturing": True,
        }
        result.setdefault("assumptions_used", []).extend(proposed)
        # photo_to_pattern collected decisions before this MCP-only preview
        # proposal existed. Re-collect without recursively walking its old
        # decision report.
        result.pop("decisions", None)
        from . import decisions as _decisions
        result["decisions"] = _decisions.collect(result)
    return _ok(result)


@tool
def photo_pattern_repair(json_text: str = "", budget: int = 8) -> str:
    """Run the bounded deterministic repair catalogue on one photo pattern.

    The transcript preserves every applied/refused repair and its cost. It is
    a geometry/sewability loop, not a strength or comfort certification.
    """
    pattern, err = _json_arg(json_text, "ANSWER photo_pattern result")
    if err:
        return _ok(err)
    if not isinstance(pattern, dict) or pattern.get("verdict") != "ANSWER":
        return _ok({"verdict": "UNKNOWN_PHOTO_PATTERN_NOT_READY",
                    "how_to_close": "generate an ANSWER photo_pattern first"})
    from . import repairs as _repairs
    out = _repairs.make_sewable(pattern, budget=max(1, int(budget)))
    out["verdict"] = "ANSWER"
    out["scope"] = "geometric sewability repair; not strength/comfort certification"
    return _ok(out)


@tool
def geometric_second_skin(json_text: str = "", garment: str = "dress",
                          ease_cm: float = 0.0, stretch: float = 0.0,
                          segments: int = 24, height_steps: int = 16) -> str:
    """Generate the model-free second-skin garment base on the current mannequin.

    ``json_text`` may contain ``calibrated_views``: front/side polygons with
    explicit azimuth and scale.  One view is refused rather than inventing
    depth.  With no views, the measured mannequin plus ``ease_cm`` and
    ``stretch`` deterministically define the base shell.  ``garment`` is one
    of dress, skirt, trousers, or leggings; it names shell topology, not a
    fashion class inferred from an image.
    """
    req: Dict[str, Any] = {}
    if json_text.strip():
        parsed, err = _json_arg(json_text, "{calibrated_views?: [...]}")
        if err:
            return _ok(err)
        if not isinstance(parsed, dict):
            return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                        "why": "json_text must be an object"})
        req = parsed
    from . import second_skin as _second_skin
    man = _mq.build(_measures())
    if man.get("verdict") != "ANSWER":
        return _ok(man)
    return _ok(_second_skin.build(
        man, garment=garment, ease=float(ease_cm), stretch=float(stretch),
        segments=int(segments), height_steps=int(height_steps),
        calibrated_views=req.get("calibrated_views")))


@tool
def generation_dependency_report(json_text: str = "") -> str:
    """Compare the model-free and optional-model generation routes.

    The supplied JSON is evidence only.  This door deliberately installs no
    LLM and no sewing corpus, so the report shows exactly which deterministic
    stages can run in this build and which external evidence still blocks a
    claim.  LLM output, when a caller installs one through the Python API,
    remains PROPOSED and can never promote itself to OBSERVED evidence.
    """
    evidence: Dict[str, Any] = {}
    if json_text.strip():
        parsed, err = _json_arg(json_text, "{evidence fields...}")
        if err:
            return _ok(err)
        if not isinstance(parsed, dict):
            return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                        "why": "json_text must be an object"})
        evidence = parsed
    from . import generation_routes as _routes
    return _ok(_routes.dependency_report(evidence))


@tool
def geometric_garment_overlay(json_text: str = "") -> str:
    """Run second-skin -> triangle overlay -> structure proposals.

    ``json_text`` supplies ``garment`` and one or more calibrated ``views``.
    The mannequin always comes from the current measured project; callers
    cannot replace it with an untracked body. Single-view depth and invisible
    backs remain typed UNKNOWN/PROPOSED rather than being auto-confirmed.
    """
    req, err = _json_arg(json_text, "{garment, views, ease?, stretch?}")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text must be an object"})
    man = _mq.build(_measures())
    if man.get("verdict") != "ANSWER":
        return _ok(man)
    from . import geometric_overlay as _overlay
    request = dict(req)
    request["mannequin"] = man
    return _ok(_overlay.build(request))


@tool
def garment_command(text: str = "", command_id: str = "",
                    provenance: str = "HUMAN_INPUT") -> str:
    """Parse beginner natural language into ``garment.command.v1``.

    This is a closed deterministic grammar. Unknown words, missing units and
    ambiguous targets are typed refusals; no LLM or nearest-intent fallback is
    used.  Returned commands are previews by default (``commit=false``).
    """
    from . import garment_ir as _garment_ir
    return _ok(_garment_ir.parse(
        text, command_id=(command_id.strip() or None), provenance=provenance))


def _save_generation_job(job: Mapping[str, Any]) -> None:
    path = _p("generation_job.json")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(_json.dumps(job, ensure_ascii=False, indent=1,
                                     sort_keys=True), encoding="utf-8")
    temporary.replace(path)


@tool
def garment_job(json_text: str = "", job_id: str = "") -> str:
    """Create, inspect, or advance the append-only garment generation job.

    Empty JSON creates a job when none exists and otherwise returns the active
    job.  An object with ``event`` applies one typed transition/preview/
    approval/rejection/Undo.  Callers may supply a full ``job`` for a detached
    calculation; only ANSWER results become the active persisted snapshot.
    """
    from . import generation_job as _job
    path = _p("generation_job.json")
    if not json_text.strip():
        if path.exists():
            try:
                return _ok(_json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                return _ok({"verdict": "UNKNOWN_INVALID_JOB_DOCUMENT",
                            "reason": str(exc)})
        created = _job.new_job(job_id.strip() or None)
        _save_generation_job(created)
        return _ok({"verdict": "ANSWER", **created})
    req, err = _json_arg(json_text, "{event: {...}, job?: garment.job.v1}")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text must be an object"})
    base = req.get("job")
    if base is None:
        if path.exists():
            try:
                base = _json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                return _ok({"verdict": "UNKNOWN_INVALID_JOB_DOCUMENT",
                            "reason": str(exc)})
        else:
            base = _job.new_job(job_id.strip() or None)
    if "event" not in req:
        return _ok({"verdict": "ANSWER", **base})
    result = _job.apply(base, req["event"])
    if result.get("verdict") == "ANSWER":
        _save_generation_job({key: value for key, value in result.items()
                              if key not in ("verdict", "result")})
    return _ok(result)


def _active_generation_job(job_id: str = "") -> Dict[str, Any]:
    path = _p("generation_job.json")
    if path.exists():
        return _json.loads(path.read_text(encoding="utf-8"))
    from . import generation_job as _job
    return _job.new_job(job_id or None)


@tool
def garment_workflow(json_text: str = "", approver: str = "") -> str:
    """Execute one typed garment command through the shared job/preview gate.

    This is the beginner UI integration door. It currently performs typed
    span/ease/length/material edits against job IR, approval/rejection/Undo,
    and read-only span inspection. Commands requiring an image outline,
    structure graph, candidate evidence, material calibration or cloth mesh
    return the exact missing typed context and the MCP door that consumes it.
    """
    req, err = _json_arg(json_text, "garment.command.v1 object")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text must be an object"})
    command = req.get("command", req)
    context = req.get("context", {}) if isinstance(req, dict) else {}
    if not isinstance(command, dict) or command.get("schema") != "garment.command.v1":
        return _ok({"verdict": "UNKNOWN_INVALID_GARMENT_COMMAND",
                    "why": "a garment.command.v1 object is required"})
    intent = str(command.get("intent", "")).upper()
    target = command.get("target") or {}
    operation = command.get("operation") or {}
    command_id = str(command.get("command_id", ""))
    if not command_id or not isinstance(target, dict) or not isinstance(operation, dict):
        return _ok({"verdict": "UNKNOWN_INVALID_GARMENT_COMMAND",
                    "why": "command_id, target and operation must be typed objects"})
    from . import garment_ir as _garment_ir
    validated = _garment_ir.validate_command_envelope(command)
    if isinstance(validated, _garment_ir.CommandRefusal):
        return _ok(validated.as_dict())
    from . import generation_job as _job
    try:
        job = _active_generation_job(str(command.get("job_id", "")))
    except (OSError, ValueError) as exc:
        return _ok({"verdict": "UNKNOWN_INVALID_JOB_DOCUMENT", "why": str(exc)})

    pending = job.get("pending_previews", {})
    preview_digest = str(operation.get("preview_digest",
                                       operation.get("previewDigest", "")))
    if intent in {"APPROVE", "REJECT"}:
        match = next((value for value in pending.values()
                      if isinstance(value, dict)
                      and value.get("digest") == preview_digest), None)
        if match is None:
            return _ok({"verdict": "UNKNOWN_PREVIEW_APPROVAL_STALE",
                        "why": "the digest does not identify a pending preview"})
        event = {"kind": intent, "preview_id": match["preview_id"],
                 "digest": preview_digest}
        if intent == "APPROVE":
            event["approver"] = approver.strip()
        else:
            event["reason"] = "rejected in beginner UI"
        result = _job.apply(job, event)
    elif intent == "UNDO":
        result = _job.apply(job, {"kind": "UNDO", "command_id": command_id})
    elif intent in {"ADJUST_PATTERN_SPAN", "ADD_EASE", "CHANGE_LENGTH",
                    "CHANGE_MATERIAL"}:
        value = operation.get("value")
        unit = operation.get("unit")
        if intent != "CHANGE_MATERIAL":
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or unit not in {"mm", "cm", "m"}):
                return _ok({"verdict": "UNKNOWN_DIMENSION_UNIT_REQUIRED",
                            "why": "the edit needs a numeric mm, cm or m value"})
        first, last = target.get("first"), target.get("last")
        if intent == "ADJUST_PATTERN_SPAN" and (not isinstance(first, int)
                                                  or not isinstance(last, int)
                                                  or first > last):
            return _ok({"verdict": "UNKNOWN_AMBIGUOUS_GARMENT_TARGET",
                        "why": "an ordered integer pattern span is required"})
        scale = {"mm": 0.1, "cm": 1.0, "m": 100.0}.get(unit, 1.0)
        edit = {"command_id": command_id, "intent": intent,
                "target": target, "operation": operation}
        if value is not None:
            edit["normalized_value_cm"] = float(value) * scale
        data = dict(job.get("snapshot", {}).get("data", {}))
        data["pattern_edits"] = list(data.get("pattern_edits", ())) + [edit]
        address = (f"pattern.{first}:{last}" if intent == "ADJUST_PATTERN_SPAN"
                   else str(target.get("kind", "ACTIVE_GARMENT")))
        result = _job.apply(job, {"kind": "PREVIEW",
                                  "command_id": command_id,
                                  "after_data": data,
                                  "changed_addresses": [address],
                                  "validation_results": [{"verdict": "PASS",
                                                          "check": "typed_ir"}],
                                  "provenance": {"source": command.get("provenance",
                                                                         "HUMAN_INPUT")}})
    elif intent == "SET_REQUIREMENTS":
        requirements = operation.get("requirements", [])
        # validate_command_envelope above has already bounded the vocabulary,
        # item count, target strings and units. Store a detached copy in the
        # preview; approval is still a separate human event.
        normalized = [dict(item) for item in requirements]
        data = dict(job.get("snapshot", {}).get("data", {}))
        data["design_requirements"] = normalized
        validations = [
            {"verdict": "PASS", "check": "typed_requirement_ir"},
            {"verdict": "PASS", "check": "model_has_no_commit_authority"},
        ]
        if any(item.get("kind") == "STANDARD_SIZE" for item in normalized):
            validations.append({
                "verdict": "REVIEW", "check": "standard_size_chart_required",
                "why": "S/M/L is a requested label until a size chart or body measurements bind it",
            })
        addresses = [
            "requirements.%s.%s" % (
                str(item.get("kind", "unknown")).lower(),
                str(item.get("target", "garment"))[:80])
            for item in normalized
        ]
        result = _job.apply(job, {
            "kind": "PREVIEW", "command_id": command_id,
            "after_data": data, "changed_addresses": addresses,
            "validation_results": validations,
            "provenance": {
                "source": command.get("provenance", "MODEL_PROPOSAL"),
                "proposal_only": True,
            },
        })
    elif intent == "GENERATE_FROM_IMAGE":
        outline = context.get("confirmed_outline") if isinstance(context, dict) else None
        if not isinstance(outline, dict):
            return _ok({
                "verdict": "UNKNOWN_GARMENT_REGION_CONFIRMATION_REQUIRED",
                "why": "a human-confirmed clothing outline is not attached",
                "how_to_close": "confirm Clothing with 3-5 points in Pattern run",
                "next_tool": "photo_pattern",
            })
        from . import photo_to_pattern as _p2p
        pattern = _p2p.run(
            outline, _measures(), image_id=str(target.get("reference", "")))
        if pattern.get("verdict") != "ANSWER":
            return _ok(pattern)
        data = dict(job.get("snapshot", {}).get("data", {}))
        data["photo_pattern"] = pattern
        data["source_image"] = target.get("reference")
        result = _job.apply(job, {
            "kind": "PREVIEW",
            "command_id": command_id,
            "after_data": data,
            "changed_addresses": ["image.confirmed_clothing", "pattern.generated"],
            "validation_results": [
                {"verdict": "PASS", "check": "human_confirmed_clothing_region"},
                {"verdict": "PASS", "check": "deterministic_photo_pattern"},
            ],
            "provenance": {
                "source": command.get("provenance", "HUMAN_INPUT"),
                "image": target.get("reference"),
                "outline_source": outline.get("source"),
            },
        })
    elif intent == "INSPECT" and target.get("kind") == "PATTERN_SPAN":
        return pattern_span(int(target.get("first", -1)), int(target.get("last", -1)))
    else:
        requirements = {
            "PROPOSE_STRUCTURE": ("UNKNOWN_STRUCTURE_SPEC_REQUIRED", "garment_structure"),
            "RUN_SIMULATION": ("UNKNOWN_HIGH_FIDELITY_CONTEXT_REQUIRED",
                               "high_fidelity_workflow"),
            "COMPARE_SIMULATIONS": ("UNKNOWN_CANDIDATE_EVIDENCE", "garment_candidates"),
            "INSPECT": ("UNKNOWN_CANDIDATE_EVIDENCE", "garment_candidates"),
        }
        code, door = requirements.get(intent, ("UNKNOWN_UNSUPPORTED_GARMENT_OPERATION",
                                                "garment_command"))
        return _ok({"verdict": code, "why": "typed context is not attached to the command",
                    "how_to_close": f"supply its typed payload to {door}",
                    "next_tool": door})
    if result.get("verdict") == "ANSWER":
        _save_generation_job({key: value for key, value in result.items()
                              if key not in ("verdict", "result")})
    return _ok(result)


@tool
def garment_structure(json_text: str = "") -> str:
    """Build and validate a corpus-free ``garment.structure.v1`` graph.

    Nodes are geometric primitives such as shells, tubes, gores and gussets;
    edges are typed construction operations. Missing dimensions, incompatible
    ports and cyclic construction plans are refused instead of repaired.
    """
    req, err = _json_arg(json_text, "garment.structure.v1 object")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text must be an object"})
    from . import garment_structure as _structure
    return _ok(_structure.build(req))


@tool
def garment_construction_route(json_text: str = "") -> str:
    """Route one typed garment instance graph by construction evidence.

    ``json_text`` must be a ``garment.instance-graph.v1`` object.  This MCP
    boundary delegates only to the deterministic construction router: garment
    names remain display metadata, model claims stay PROPOSED/UNKNOWN, and the
    result never grants manufacturing readiness, certification, or a fact
    promotion.  Invalid or insufficient graphs return a typed UNKNOWN value.
    """
    req, err = _json_arg(json_text, "a garment.instance-graph.v1 object")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": "json_text must be a garment.instance-graph.v1 object",
        })
    from . import construction_regime as _construction_regime
    return _ok(_construction_regime.route_construction(req))


@tool
def garment_image_analysis_ensemble(json_text: str = "") -> str:
    """Merge bounded VLM and Marqo/FashionSigLIP garment proposals.

    ``json_text`` is a ``garment.image-analysis-ensemble.request.v1`` object
    containing precomputed ``vision.result`` and/or ``retrieval.result``.
    Provider model IDs and licenses are configuration metadata only.  Model
    claims remain PROPOSED, disagreements remain CONTESTED, unavailable
    providers return typed capability failures, and rear/hidden structure is
    never promoted to OBSERVED.  Live adapters are injected through the
    Python API rather than loaded or downloaded by this stdio server.
    """
    req, err = _json_arg(
        json_text, "a garment.image-analysis-ensemble.request.v1 object")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": (
                "json_text must be a "
                "garment.image-analysis-ensemble.request.v1 object"
            ),
        })
    from . import garment_analysis_ensemble as _analysis_ensemble
    return _ok(_analysis_ensemble.analyze_garment_image(req))


@tool
def marqo_fashion_siglip_runtime(json_text: str = "") -> str:
    """Probe or run the bounded Marqo/FashionSigLIP retrieval adapter.

    ``json_text`` is ``{action: capability|run, ...adapter request...}``.
    Capability probing performs no network request, model import, model load,
    or download.  Inference supports precomputed results/embeddings, an
    explicitly enabled loopback HTTP endpoint with a bounded timeout, or an
    existing explicitly configured local model path.  No configured search
    corpus returns ``UNKNOWN_NO_FASHION_RETRIEVAL_INDEX``.  Every successful
    nearest item remains ``PROPOSED_RETRIEVAL`` with source, asset, license,
    rights-review, and provenance metadata; scores/model metadata are never
    correctness evidence.  The local Python API additionally accepts injected
    transport/embedder/index implementations.
    """
    req, err = _json_arg(
        json_text, "{action: capability|run, mode?, config?, query?, index?}")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": "json_text must be a Marqo/FashionSigLIP adapter object",
        })
    action = req.get("action", "capability")
    from . import marqo_fashion_siglip_adapter as _fashion_siglip
    if action == "capability":
        return _ok(_fashion_siglip.capability_probe(req))
    if action == "run":
        return _ok(_fashion_siglip.run_retrieval(req))
    return _ok({
        "verdict": "UNKNOWN_BAD_ARGUMENTS",
        "why": "action must be capability or run",
    })


@tool
def garment_parts_ir_complete(json_text: str = "") -> str:
    """Complete a vision model's small parts IR into typed structure candidates.

    Input is ``{parts_ir, target_measurements?, preview_profile?,
    use_bounded_preview_profile?, candidate_count?}``.  Selecting the bounded
    preview profile is explicit: it produces mannequin-relative PROPOSED
    geometry, never measurements inferred from image pixels or approval to cut.
    At least two alternatives are retained so a front-only interpretation is
    not silently collapsed to one asserted garment.
    """
    req, err = _json_arg(
        json_text,
        "{parts_ir, target_measurements?, preview_profile?, "
        "use_bounded_preview_profile?, candidate_count?}",
    )
    if err:
        return _ok(err)
    if not isinstance(req, dict) or not isinstance(req.get("parts_ir"), dict):
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": "parts_ir is required and must be an object",
        })
    use_preview = req.get("use_bounded_preview_profile", False)
    if not isinstance(use_preview, bool):
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": "use_bounded_preview_profile must be a boolean",
        })
    if use_preview and req.get("preview_profile") is not None:
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": (
                "choose either preview_profile or "
                "use_bounded_preview_profile, not both"
            ),
        })
    candidate_count = req.get("candidate_count")
    if candidate_count is not None and (
            isinstance(candidate_count, bool)
            or not isinstance(candidate_count, int)):
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": "candidate_count must be an integer when supplied",
        })
    from . import parts_ir_completion as _parts_completion
    preview_profile = req.get("preview_profile")
    if use_preview:
        preview_profile = _parts_completion.bounded_preview_profile()
    return _ok(_parts_completion.complete_parts_ir(
        req["parts_ir"],
        target_measurements=req.get("target_measurements"),
        preview_profile=preview_profile,
        candidate_count=candidate_count,
    ))


@tool
def garment_parts_ir_topology(json_text: str = "") -> str:
    """Turn completed parts IR candidates into typed PROPOSED topology.

    Input is ``{completion}``, where ``completion`` is an unchanged successful
    result from :func:`garment_parts_ir_complete`.  The boundary adds ports and
    construction operations only from explicit ``attached_to`` relations plus
    the deterministic garment rules.  It never upgrades an image proposal to
    OBSERVED/APPROVED/ANSWER, and unsupported relations fail closed.
    """
    req, err = _json_arg(json_text, "{completion}")
    if err:
        return _ok(err)
    if not isinstance(req, dict) or not isinstance(req.get("completion"), dict):
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": "completion is required and must be an object",
        })
    from . import parts_ir_topology as _parts_topology
    return _ok(_parts_topology.apply_parts_ir_topology(req["completion"]))


@tool
def garment_parts_ir_pipeline(json_text: str = "") -> str:
    """Run parts completion, typed topology, 3D, and flat patterns as one gate.

    Input is ``{parts_ir, target_measurements?, preview_profile?,
    use_bounded_preview_profile?, candidate_count?, radial_segments?,
    layer_spacing_cm?}``. Every candidate remains PROPOSED and its 3D preview
    and flat pattern are bound to one structure digest. Any failed candidate
    makes the aggregate UNRESOLVED instead of being hidden.
    """
    req, err = _json_arg(
        json_text,
        "{parts_ir, target_measurements?, preview_profile?, "
        "use_bounded_preview_profile?, candidate_count?, radial_segments?, "
        "layer_spacing_cm?}",
    )
    if err:
        return _ok(err)
    if not isinstance(req, dict) or not isinstance(req.get("parts_ir"), dict):
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": "parts_ir is required and must be an object",
        })
    use_preview = req.get("use_bounded_preview_profile", False)
    if not isinstance(use_preview, bool):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "use_bounded_preview_profile must be a boolean"})
    if use_preview and req.get("preview_profile") is not None:
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": "choose either preview_profile or use_bounded_preview_profile, not both",
        })
    candidate_count = req.get("candidate_count")
    radial_segments = req.get("radial_segments", 16)
    layer_spacing = req.get("layer_spacing_cm", 0.6)
    if candidate_count is not None and (
            isinstance(candidate_count, bool)
            or not isinstance(candidate_count, int)):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "candidate_count must be an integer when supplied"})
    if (isinstance(radial_segments, bool)
            or not isinstance(radial_segments, int)
            or not 8 <= radial_segments <= 128):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "radial_segments must be an integer from 8 through 128"})
    if (isinstance(layer_spacing, bool)
            or not isinstance(layer_spacing, (int, float))
            or not 0.0 < float(layer_spacing) <= 20.0):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "layer_spacing_cm must be a number above 0 and at most 20"})
    from . import parts_ir_completion as _parts_completion
    from . import parts_ir_pipeline as _parts_pipeline
    preview_profile = req.get("preview_profile")
    if use_preview:
        preview_profile = _parts_completion.bounded_preview_profile()
    return _ok(_parts_pipeline.run_parts_ir_pipeline(
        req["parts_ir"],
        target_measurements=req.get("target_measurements"),
        preview_profile=preview_profile,
        candidate_count=candidate_count,
        radial_segments=radial_segments,
        layer_spacing_cm=float(layer_spacing),
    ))


@tool
def garment_structure_preview(json_text: str = "") -> str:
    """Build a candidate-specific PROPOSED 3D mesh from a structure graph.

    Input is ``{candidate_id, structure}``.  The result is deterministic and
    explicitly preview-only; it never establishes fit or manufacturability.
    """
    req, err = _json_arg(json_text, "{candidate_id, structure}")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text must be an object"})
    from . import structure_preview as _preview
    return _ok(_preview.generate_candidate_preview(req))


@tool
def garment_structure_pattern(json_text: str = "") -> str:
    """Compile a typed structure graph into candidate-specific flat pieces.

    Input is ``{candidate_id, structure}`` for a PROPOSED preview.  An
    ``APPROVED`` request additionally needs ``approval: {by, digest}``.
    Output remains a geometric prototype until the listed manufacturing gates
    are closed.
    """
    req, err = _json_arg(json_text, "{candidate_id, structure, candidate_state?, approval?}")
    if err:
        return _ok(err)
    if not isinstance(req, dict) or not isinstance(req.get("structure"), dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "candidate_id and structure are required"})
    from . import structure_to_pattern as _compiler
    return _ok(_compiler.compile(
        req["structure"], candidate_id=str(req.get("candidate_id", "")),
        candidate_state=str(req.get("candidate_state", "PROPOSED")),
        approval=req.get("approval")))


@tool
def garment_front_outline_hypotheses(json_text: str = "") -> str:
    """Open three falsifiable structures from one confirmed front outline.

    This is the model-free geometric fallback.  It measures only normalized
    outline ratios; garment composition, sleeves, layers, decoration, back and
    all centimetre dimensions remain explicit PROPOSED alternatives.
    """
    req, err = _json_arg(json_text, "{outline, source_id?}")
    if err:
        return _ok(err)
    if not isinstance(req, dict) or "outline" not in req:
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "outline is required"})
    outline = req["outline"]
    embedded_regions = (outline.get("regions") if isinstance(outline, Mapping)
                        else None)
    regions = req.get("regions", embedded_regions)
    if isinstance(regions, list) and regions:
        from . import front_region_structure_cues as _region_front
        result = _region_front.hypothesize(
            outline, regions, source_id=str(req.get("source_id", "confirmed-front")))
        if result.get("verdict") == "PROPOSED":
            # front_structure_hypotheses returns complete structure graphs.
            # The resumable factory uses an explicit envelope around each
            # graph so proposal metadata cannot be mistaken for graph fields.
            factory_rows = []
            for candidate in result.get("hypotheses", []):
                back = candidate.get("back_alternative", {})
                factory_rows.append({
                    "candidate_id": candidate.get("candidate_id", ""),
                    "back_design": back.get("alternative_id", "proposed-back"),
                    "structure": {
                        "schema": candidate.get("schema"),
                        "nodes": candidate.get("nodes", []),
                        "operations": candidate.get("operations", []),
                    },
                    "state": "PROPOSED",
                    "assumptions": list(candidate.get("basis", [])) + [
                        str(back.get("basis", "back is not observed"))],
                    "breaks_when": list(candidate.get("breaks_when", [])) + [
                        str(back.get("breaks_when", "a rear observation changes the proposal"))],
                    "front_region_evidence_digest": candidate.get(
                        "front_region_evidence_digest"),
                    "front_geometry_digest": candidate.get(
                        "front_geometry_digest"),
                    "typed_cue_digest": candidate.get("typed_cue_digest"),
                    "unobserved": candidate.get("unobserved", {}),
                    "provenance": candidate.get("provenance", {}),
                })
            result["structure_hypotheses"] = result["hypotheses"]
            result["hypotheses"] = factory_rows
            result["factory_envelope"] = True
        return _ok(result)
    from . import front_geometry_cues as _front
    return _ok(_front.hypothesize(
        outline, source_id=str(req.get("source_id", "confirmed-front"))))


_FRONT_CANDIDATE_REQUEST_SCHEMA = (
    "garment.front-candidate-evaluation.request.v1"
)
_FRONT_IMAGE_GENERATION_REQUEST_SCHEMA = (
    "garment.front-image-generation.request.v1"
)


def _front_candidate_review_boundary(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep front-only evaluation below approval and manufacturing authority."""
    from . import front_candidate_evaluator as _evaluator
    bounded = dict(result)
    bounded.setdefault("schema", _evaluator.SCHEMA)
    bounded["state"] = "REVIEW"
    bounded["selected_candidate_id"] = None
    bounded["requires_human_approval"] = True
    bounded["rear_authority"] = "PROPOSED"
    bounded["material_authority"] = "PROPOSED"
    bounded["manufacturing_ready"] = False
    bounded["manufacturing_certified"] = False
    return bounded


def _front_candidate_refusal(verdict: str, why: str, **details: Any) -> str:
    from . import front_candidate_evaluator as _evaluator
    result: Dict[str, Any] = {
        "schema": _evaluator.SCHEMA,
        "verdict": verdict,
        "why": why,
        "pareto_frontier": [],
    }
    result.update(details)
    return _ok(_front_candidate_review_boundary(result))


def _front_candidate_artifact_identity_error(
        artifacts: Any, *, kind: str,
        candidate_ids: set[str]) -> Optional[Dict[str, Any]]:
    if artifacts is None:
        return None
    if not isinstance(artifacts, Mapping):
        return {
            "verdict": "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_MAP_REQUIRED",
            "why": f"{kind} must be an object keyed by candidate_id",
            "artifact_kind": kind,
        }
    for key in sorted(artifacts, key=str):
        artifact = artifacts[key]
        if not isinstance(key, str) or not key:
            return {
                "verdict": "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_ID_REQUIRED",
                "why": f"every supplied {kind} needs a non-empty candidate-id key",
                "artifact_kind": kind,
            }
        if key not in candidate_ids:
            return {
                "verdict": "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_ORPHANED",
                "why": f"supplied {kind} belongs to no candidate in this request",
                "artifact_kind": kind,
                "artifact_candidate_id": key,
            }
        if not isinstance(artifact, Mapping):
            return {
                "verdict": "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_REQUIRED",
                "why": f"{kind}[{key}] must be an artifact object",
                "artifact_kind": kind,
                "artifact_candidate_id": key,
            }
        embedded = artifact.get("candidate_id")
        if embedded != key:
            return {
                "verdict": "UNKNOWN_FRONT_CANDIDATE_ARTIFACT_ID_MISMATCH",
                "why": (
                    f"{kind}[{key}] must carry that exact candidate_id; "
                    "artifacts are never matched by position"
                ),
                "artifact_kind": kind,
                "map_candidate_id": key,
                "artifact_candidate_id": embedded,
            }
    return None


@tool
def garment_front_candidate_evaluate(json_text: str = "") -> str:
    """Pareto-evaluate typed front-only candidates without selecting one.

    ``json_text`` is a
    ``garment.front-candidate-evaluation.request.v1`` object containing
    ``candidates`` and optional ``front_evidence``, candidate-id-keyed
    ``previews``, and candidate-id-keyed ``patterns``. Rear and material
    claims remain PROPOSED. Every result requires human approval and keeps
    ``manufacturing_ready`` and ``manufacturing_certified`` false.
    """
    req, err = _json_arg(
        json_text, f"{_FRONT_CANDIDATE_REQUEST_SCHEMA} object")
    if err:
        return _front_candidate_refusal(
            "UNKNOWN_BAD_ARGUMENTS", str(err.get("why", "invalid JSON")))
    if not isinstance(req, Mapping):
        return _front_candidate_refusal(
            "UNKNOWN_FRONT_CANDIDATE_EVALUATION_REQUEST",
            "request must be an object with schema "
            f"{_FRONT_CANDIDATE_REQUEST_SCHEMA}")
    if req.get("schema") != _FRONT_CANDIDATE_REQUEST_SCHEMA:
        return _front_candidate_refusal(
            "UNKNOWN_FRONT_CANDIDATE_EVALUATION_SCHEMA",
            f"schema must be exactly {_FRONT_CANDIDATE_REQUEST_SCHEMA}",
            received_schema=req.get("schema"))

    candidates = req.get("candidates")
    if (not isinstance(candidates, typing.Sequence)
            or isinstance(candidates, (str, bytes))
            or not candidates
            or any(not isinstance(candidate, Mapping)
                   for candidate in candidates)):
        return _front_candidate_refusal(
            "UNKNOWN_FRONT_CANDIDATES_REQUIRED",
            "candidates must be a non-empty array of candidate objects")
    ids = [candidate.get("candidate_id") for candidate in candidates]
    candidate_ids = {
        value for value in ids if isinstance(value, str) and value.strip()
    }
    if len(candidate_ids) != len(candidates):
        verdict = (
            "UNKNOWN_DUPLICATE_FRONT_CANDIDATE_ID"
            if (len(candidate_ids) < len(candidates)
                and all(isinstance(value, str) and value.strip()
                        for value in ids))
            else "UNKNOWN_FRONT_CANDIDATE_ID_REQUIRED"
        )
        return _front_candidate_refusal(
            verdict,
            "every candidate needs a unique, non-empty candidate_id")

    front_evidence = req.get("front_evidence", {})
    if not isinstance(front_evidence, Mapping):
        return _front_candidate_refusal(
            "UNKNOWN_FRONT_EVIDENCE_OBJECT_REQUIRED",
            "front_evidence must be an object")
    for key in ("previews", "patterns"):
        identity_error = _front_candidate_artifact_identity_error(
            req.get(key), kind=key, candidate_ids=candidate_ids)
        if identity_error is not None:
            details = dict(identity_error)
            verdict = str(details.pop("verdict"))
            why = str(details.pop("why"))
            return _front_candidate_refusal(verdict, why, **details)

    from . import front_candidate_evaluator as _evaluator
    result = _evaluator.evaluate_candidates(
        candidates,
        front_evidence=front_evidence,
        previews=req.get("previews"),
        patterns=req.get("patterns"),
    )
    if (result.get("requires_human_approval") is not True
            or result.get("selected_candidate_id") is not None
            or result.get("manufacturing_ready") is not False
            or result.get("manufacturing_certified") is not False):
        return _front_candidate_refusal(
            "UNKNOWN_FRONT_CANDIDATE_AUTHORITY_BOUNDARY",
            "the evaluator attempted to cross the MCP approval or "
            "manufacturing boundary")
    return _ok(_front_candidate_review_boundary(result))


@tool
def garment_front_image_generation_contract(json_text: str = "") -> str:
    """Advance the deterministic Vera contract for one front garment image.

    ``json_text`` is a
    ``garment.front-image-generation.request.v1`` object.  Upstream vision or
    an LLM may propose typed observations, candidates, and artifacts, but this
    tool alone owns the deterministic ReAct transition.  Candidate-specific
    3D, pattern, and manufacturing artifacts remain bound by stable digests;
    rear and material hypotheses remain PROPOSED; wearer measurements and
    exact digest-bound human approvals are mandatory gates.  The result never
    grants manufacturing certification.
    """
    req, err = _json_arg(
        json_text, f"{_FRONT_IMAGE_GENERATION_REQUEST_SCHEMA} object")
    if err:
        return _ok(err)
    from . import front_image_generation_contract as _contract
    return _ok(_contract.orchestrate(req))


@tool
def garment_wearer_measurement_contract(json_text: str = "") -> str:
    """Validate the typed target-wearer measurement and ease contract.

    ``json_text`` is a ``garment.wearer-measurement.request.v1`` object.
    Real wearer dimensions must remain explicit MEASURED values with typed
    sources; a bounded PROPOSED preview mannequin can never satisfy that gate.
    The tool normalizes supported lengths to centimetres and does not infer
    body measurements from a front garment photograph.  READY means only that
    the typed measurement gate is complete, never manufacturing readiness.
    """
    req, err = _json_arg(
        json_text, "garment.wearer-measurement.request.v1 object")
    if err:
        return _ok(err)
    from . import wearer_measurement_contract as _wearer_measurements
    return _ok(_wearer_measurements.compile_contract(req))


@tool
def garment_body_proxy_propose(json_text: str = "") -> str:
    """Propose typed body proxies beneath clothing in one image.

    ``json_text`` must be a ``garment.body-proxy.request.v1`` object with
    typed measured/requested dimensions and optional camera, 2D pose,
    exposed-skin contours, and BODY/GARMENT mask candidates.  It returns
    multiple ``PROPOSED_BODY_PROXY`` alternatives, rear-generation dimension
    ranges, and preview-avatar bindings.  Clothed-image chest/waist estimates
    never become measurements.  HUMAN_APPROVAL and AUTO_PROPOSED selection are
    supported, but neither opens fit, manufacturing, or certification gates.
    No external model or network access is used by the deterministic fallback.
    """
    req, err = _json_arg(json_text, "garment.body-proxy.request.v1 object")
    if err:
        return _ok(err)
    if not isinstance(req, Mapping):
        return _ok({
            "verdict": "UNKNOWN_BODY_PROXY_REQUEST",
            "why": "json_text must be a garment.body-proxy.request.v1 object",
            "fact_promotions": [],
        })
    from . import body_proxy as _body_proxy
    result = _body_proxy.propose_body_proxy(req)
    result["mcp_request_schema"] = "garment.body-proxy.request.v1"
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_body_image_separation_propose(json_text: str = "") -> str:
    """Propose typed body/garment separation for one clothed-person image.

    ``json_text`` must be a
    ``garment.body-image-separation.request.v1`` object.  Supplied external
    vision output or the local deterministic fallback is normalized into
    reviewable separation candidates.  The MCP boundary accepts only
    ``PROPOSED_BODY_GARMENT_SEPARATION`` candidates, keeps the rear
    ``UNKNOWN_UNOBSERVED``, and never grants manufacturing readiness,
    certification, or fact promotion.
    """
    request_schema = "garment.body-image-separation.request.v1"

    def stopped(verdict: str, why: str) -> str:
        return _ok({
            "verdict": verdict,
            "state": "UNKNOWN",
            "why": why,
            "mcp_request_schema": request_schema,
            "rear_state": "UNKNOWN_UNOBSERVED",
            "manufacturing_ready": False,
            "manufacturing_certified": False,
            "fact_promotions": [],
        })

    req, err = _json_arg(json_text, f"{request_schema} object")
    if err:
        return stopped(err["verdict"], err["why"])
    if not isinstance(req, Mapping):
        return stopped(
            "UNKNOWN_BODY_IMAGE_SEPARATION_REQUEST",
            f"json_text must be a {request_schema} object",
        )

    from . import body_image_separation as _body_image_separation
    raw_result = _body_image_separation.separate_body_image(req)
    if not isinstance(raw_result, Mapping):
        return stopped(
            "UNKNOWN_BODY_IMAGE_SEPARATION_AUTHORITY_BOUNDARY",
            "body-image separation returned a non-object result",
        )
    result = dict(raw_result)

    if result.get("verdict") == (
            "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES"):
        candidates = result.get("candidates")
        valid_candidates = isinstance(candidates, list) and bool(candidates)
        bounded_candidates = []
        if valid_candidates:
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    valid_candidates = False
                    break
                conditioning = candidate.get("back_generation_conditioning")
                if (candidate.get("state") !=
                        "PROPOSED_BODY_GARMENT_SEPARATION"
                        or candidate.get("authority") !=
                        "PROPOSED_BODY_GARMENT_SEPARATION"
                        or candidate.get("manufacturing_ready") is not False
                        or candidate.get("manufacturing_certified") is not False
                        or candidate.get("fact_promotions") != []
                        or not isinstance(conditioning, Mapping)
                        or conditioning.get("rear_state") !=
                        "UNKNOWN_UNOBSERVED"):
                    valid_candidates = False
                    break
                bounded_candidate = dict(candidate)
                bounded_candidate["back_generation_conditioning"] = dict(
                    conditioning)
                bounded_candidates.append(bounded_candidate)
        if (not valid_candidates
                or result.get("state") !=
                "PROPOSED_BODY_GARMENT_SEPARATION"
                or result.get("rear_state") != "UNKNOWN_UNOBSERVED"
                or result.get("manufacturing_ready") is not False
                or result.get("manufacturing_certified") is not False
                or result.get("fact_promotions") != []):
            return stopped(
                "UNKNOWN_BODY_IMAGE_SEPARATION_AUTHORITY_BOUNDARY",
                "body-image separation attempted to cross the proposal, "
                "rear-observation, manufacturing, or fact-promotion boundary",
            )
        result["candidates"] = bounded_candidates

    result["mcp_request_schema"] = request_schema
    result["rear_state"] = "UNKNOWN_UNOBSERVED"
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_body_avatar_fit(json_text: str = "") -> str:
    """Fit one of ten bounded preview bodies to typed image evidence.

    ``json_text`` is a ``garment.body-avatar-fit.request.v1`` object.  Image
    evidence controls only same-camera scale, translation and pose anchors;
    it never becomes wearer measurements, hidden body, or rear observation.
    Only dimensions explicitly listed in ``interpolation.allowed_dimensions``
    may modify the selected preview profile.
    """
    req, err = _json_arg(json_text, "garment.body-avatar-fit.request.v1 object")
    if err:
        return _ok(err)
    from . import body_avatar_fit as _fit
    result = _fit.fit_body_avatar(req)
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_second_skin_triangle_build(json_text: str = "") -> str:
    """Build a primitive-neutral triangulated second skin on a body proxy.

    Geometry is selected by typed domains, components, layers, sides and
    ownership relations, not garment names.  All six-arm Cross proposals read
    the same old state before deterministic reduction.  Rear surfaces and
    boundary/seam candidates remain PROPOSED; sewability is not claimed.
    """
    req, err = _json_arg(json_text, "second-skin triangle request object")
    if err:
        return _ok(err)
    from . import second_skin_triangle_engine as _second_skin
    result = _second_skin.build(req)
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_rear_candidate_ensemble(json_text: str = "") -> str:
    """Generate separate PROPOSED rear alternatives for a visible-part graph.

    FashionSigLIP retrieval and multimodal proposals are scored per structure,
    parts, seams and material axis and are never averaged into one authority.
    With no corpus the tool still produces two geometry-only alternatives.
    Sewing search stays closed until a named human approves one exact digest.
    """
    req, err = _json_arg(json_text, "garment.rear-candidate-ensemble.request.v1 object")
    if err:
        return _ok(err)
    from . import rear_candidate_ensemble as _rear
    result = _rear.generate_rear_candidates(req)
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_candidate_3d_repair_loop(json_text: str = "") -> str:
    """Run a bounded candidate-specific same-camera 3D repair loop.

    Each candidate owns a distinct mesh.  The deterministic loop performs
    propose -> project/simulate -> compare -> repair while EvidenceCross and
    PhysicalCross retain separate residuals and provenance.  Non-convergence,
    generic fallback, stale approval and unobserved authority promotion stop
    typed; only an exact final-digest approval can emit a pattern hand-off.
    """
    req, err = _json_arg(json_text, "garment.candidate-3d-repair-loop.request.v1 object")
    if err:
        return _ok(err)
    from . import candidate_3d_repair_loop as _repair
    result = _repair.run(req)
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_geometric_atelier_workflow(json_text: str = "") -> str:
    """Run image evidence through the geometry-first Vera Atelier harness.

    ``json_text`` is ``garment.geometric-atelier-workflow.request.v1``.  The
    tool composes bounded body fitting, typed front regions, second-skin
    triangles, independent FashionSigLIP/multimodal rear evidence, distinct
    rear candidate meshes and a finite same-camera repair loop.  It supports
    HUMAN_AUDIT and AUTO_PROPOSED preview modes.  Names never select a garment
    generator; hidden rear/material remain proposals and manufacturing is
    never certified by this orchestration boundary.
    """
    req, err = _json_arg(
        json_text, "garment.geometric-atelier-workflow.request.v1 object")
    if err:
        return _ok(err)
    from . import geometric_atelier_workflow as _workflow
    result = _workflow.run(req)
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_body_image_separation_precomputed(json_text: str = "") -> str:
    """Probe, normalise, or execute an offline semantic-mask adapter.

    ``json_text`` is ``{action: capability|build|run, ...}``. ``build`` and
    ``run`` otherwise use
    ``garment.body-image-separation.precomputed-adapter.request.v1``. The
    adapter accepts already-produced local polygon/class-mask and pose output
    from Apple Vision, CoreML, a local VLM, or a human labelling tool. It never
    downloads a model or opens a network connection. BODY means visible image
    support beneath/around clothing, never a body measurement; every semantic
    channel remains proposed, the rear remains unknown, and manufacturing
    authority is always denied.
    """
    req, err = _json_arg(
        json_text,
        "{action: capability|build|run, schema?, source?, masks?, pose?}",
    )
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": "json_text must be an offline precomputed adapter object",
            "rear_state": "UNKNOWN_UNOBSERVED",
            "manufacturing_ready": False,
            "manufacturing_certified": False,
            "fact_promotions": [],
        })
    from . import body_image_separation_precomputed_adapter as _adapter
    action = str(req.get("action", "capability")).lower()
    payload = dict(req)
    payload.pop("action", None)
    if action == "capability":
        result = _adapter.capability_probe(
            segmentation_path=payload.get("segmentation_path"))
    elif action == "build":
        result = _adapter.build_provider_output(payload)
    elif action == "run":
        result = _adapter.adapt_and_separate(payload)
    else:
        result = {
            "verdict": "UNKNOWN_BAD_ARGUMENTS",
            "why": "action must be capability, build, or run",
        }

    if not isinstance(result, Mapping):
        result = {
            "verdict": "UNKNOWN_PRECOMPUTED_SEPARATION_AUTHORITY_BOUNDARY",
            "why": "precomputed adapter returned a non-object result",
        }
    result = dict(result)
    unsafe = (
        result.get("rear_state", "UNKNOWN_UNOBSERVED")
            != "UNKNOWN_UNOBSERVED"
        or result.get("manufacturing_ready") is True
        or result.get("manufacturing_certified") is True
        or bool(result.get("fact_promotions"))
    )
    if action == "run" and isinstance(result.get("separation"), Mapping):
        separation = result["separation"]
        unsafe = unsafe or (
            separation.get("rear_state") != "UNKNOWN_UNOBSERVED"
            or separation.get("manufacturing_ready") is True
            or separation.get("manufacturing_certified") is True
            or bool(separation.get("fact_promotions"))
        )
    if unsafe:
        result = {
            "verdict": "UNKNOWN_PRECOMPUTED_SEPARATION_AUTHORITY_BOUNDARY",
            "why": "precomputed evidence attempted to cross rear or manufacturing authority",
        }
    result["mcp_adapter_schema"] = (
        "garment.body-image-separation.precomputed-adapter.request.v1")
    result["rear_state"] = "UNKNOWN_UNOBSERVED"
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_design_requirement_profile(json_text: str = "") -> str:
    """Lower validated chat requirements to proposal-only preview dimensions.

    ``json_text`` is a
    ``garment.design-requirement-profile.request.v1`` object containing the
    typed requirements already accepted by Vera's language boundary.  Explicit
    units are normalized and specifically targeted body/ease/garment values
    are mapped to existing geometry primitive fields.  Standard-size labels do
    not create measurements without a named chart, generic ease is not spread
    silently, and the result never satisfies manufacturing measurement gates.
    """
    req, err = _json_arg(
        json_text, "garment.design-requirement-profile.request.v1 object")
    if err:
        return _ok(err)
    from . import design_requirement_profile as _requirement_profile
    return _ok(_requirement_profile.compile_profile(req))


@tool
def garment_front_layered_compose(json_text: str = "") -> str:
    """Bind front-image candidate parts to layered structure alternatives.

    ``json_text`` is a
    ``garment.front-layered-composition.request.v1`` object.  The bridge maps
    typed candidate parts onto existing geometric primitives, preserves
    ambiguous JOIN/SEPARATE/LAYER/CONTACT/OVERLAP alternatives, and binds each
    ``garment.structure.v1`` result to its source candidate id and digest.
    Rear geometry, material, hidden parts, and attachments remain PROPOSED;
    no result is manufacturing-ready or certified.
    """
    req, err = _json_arg(
        json_text, "garment.front-layered-composition.request.v1 object")
    if err:
        return _ok(err)
    from . import front_layered_composition as _front_layered
    return _ok(_front_layered.compose(req))


@tool
def garment_front_candidate_artifact_pipeline(json_text: str = "") -> str:
    """Compile every front-image candidate into bound structure/pattern artifacts.

    ``json_text`` is a
    ``garment.front-candidate-artifact-pipeline.request.v1`` object.  The
    deterministic pipeline runs the existing front-image contract, layered
    geometric composition, and structure-to-pattern compiler independently
    for every candidate.  Candidate ids and digests remain source-bound; a
    typed STOPPED alternative remains beside successful siblings.  Selection
    always requires a human, and no result is manufacturing-ready or
    manufacturing-certified.
    """
    req, err = _json_arg(
        json_text,
        "garment.front-candidate-artifact-pipeline.request.v1 object",
    )
    if err:
        return _ok(err)
    from . import front_candidate_artifact_pipeline as _artifact_pipeline
    return _ok(_artifact_pipeline.assemble(req))


@tool
def garment_same_camera_projection_prepare(json_text: str = "") -> str:
    """Bind one cleaned front target and proposed mesh to the same camera.

    ``json_text`` must be a
    ``garment.same-camera-projection.request.v1`` object.  The deterministic
    bridge rasterises the target outline and candidate front triangles, then
    delegates to the independent-axis front projection evaluator.  Alignment
    remains ``PROPOSED_PREVIEW`` and the result never adopts a design or
    promotes hidden geometry to fact.
    """
    request_schema = "garment.same-camera-projection.request.v1"
    req, err = _json_arg(json_text, f"{request_schema} object")
    if err:
        return _ok(err)
    if not isinstance(req, Mapping):
        return _ok({
            "verdict": "UNKNOWN_SAME_CAMERA_PROJECTION_REQUEST",
            "why": f"request must be an object with schema {request_schema}",
            "fact_promotions": [],
        })
    from . import same_camera_projection as _same_camera
    return _ok(_same_camera.prepare_same_camera_projection(req))


@tool
def garment_front_projection_compare(json_text: str = "") -> str:
    """Compare an OBSERVED front raster with one same-camera 3D render.

    ``json_text`` must be a
    ``garment.front-projection-compare.request.v1`` object containing
    ``observation`` and ``candidate_projection`` plus optional
    ``round_index``, digest-bound ``previous``, and independent-axis
    ``config`` bounds.  The evaluator never emits an aggregate similarity
    score: silhouette, typed parts, visible boundaries, colour and front
    layer/occlusion relations remain separate.  Rear and UNKNOWN pixels are
    excluded, a converged result remains PROPOSED, and human approval is
    always required before the garment workflow may adopt it.
    """
    request_schema = "garment.front-projection-compare.request.v1"
    req, err = _json_arg(json_text, f"{request_schema} object")
    if err:
        return _ok(err)
    if not isinstance(req, Mapping):
        return _ok({
            "verdict": "UNKNOWN_FRONT_PROJECTION_COMPARE_REQUEST",
            "why": f"request must be an object with schema {request_schema}",
            "fact_promotions": [],
        })
    if req.get("schema") != request_schema:
        return _ok({
            "verdict": "UNKNOWN_FRONT_PROJECTION_COMPARE_SCHEMA",
            "why": f"schema must be exactly {request_schema}",
            "received_schema": req.get("schema"),
            "fact_promotions": [],
        })
    observation = req.get("observation")
    candidate_projection = req.get("candidate_projection")
    if not isinstance(observation, Mapping) or not isinstance(
            candidate_projection, Mapping):
        return _ok({
            "verdict": "UNKNOWN_FRONT_PROJECTION_RASTERS_REQUIRED",
            "why": (
                "observation and candidate_projection must both be typed "
                "front-raster objects"
            ),
            "fact_promotions": [],
        })
    from . import front_projection_compare as _front_projection
    result = _front_projection.compare_front_projection(
        observation,
        candidate_projection,
        round_index=req.get("round_index", 1),
        previous=req.get("previous"),
        config=req.get("config"),
    )
    # Belt-and-suspenders authority guard at the MCP boundary.  The numerical
    # module already emits these values, but an MCP caller must never infer
    # manufacturing or fact authority from a passing reprojection bound.
    result["mcp_request_schema"] = request_schema
    result["human_approval_required"] = True
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_target_reconstruction_prepare(json_text: str = "") -> str:
    """Prepare a provider-neutral fused person/garment target for cleanup.

    ``json_text`` must be a
    ``garment.target-reconstruction.request.v1`` object.  An external
    single-view mesh is accepted only as a PROPOSED visual target; without
    one, the same contract carries a deterministic front-silhouette fallback.
    A digest-bound base avatar and its typed body dimensions must be selected
    before composition. Background, hair, body and accessory regions can be reversibly excluded.
    Removing an occluder creates an UNKNOWN hole and a separately labelled
    PROPOSED backfill, never an observed garment surface.  The result is bound
    to one camera for later reprojection and is never manufacturing-ready.
    """
    request_schema = "garment.target-reconstruction.request.v1"
    req, err = _json_arg(json_text, f"{request_schema} object")
    if err:
        return _ok(err)
    if not isinstance(req, Mapping):
        return _ok({
            "verdict": "UNKNOWN_TARGET_RECONSTRUCTION_REQUEST",
            "why": f"request must be an object with schema {request_schema}",
            "fact_promotions": [],
        })
    from . import target_reconstruction as _target_reconstruction
    result = _target_reconstruction.prepare_target_reconstruction(req)
    result["mcp_request_schema"] = request_schema
    result["human_approval_required"] = True
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_target_bound_candidate_preview(json_text: str = "") -> str:
    """Bind a selected source-view front to one candidate-specific rear.

    ``json_text`` must be a
    ``garment.target-bound-candidate-preview.request.v1`` object containing a
    cleaned target surface, one deterministic structure preview, and the
    selected avatar.  Front triangles are preserved exactly; only the hidden
    rear/rim are generated from the candidate geometry and body envelope.
    Rear, depth, body fit and all manufacturing claims remain PROPOSED or
    UNKNOWN.
    """
    request_schema = "garment.target-bound-candidate-preview.request.v1"
    req, err = _json_arg(json_text, f"{request_schema} object")
    if err:
        return _ok(err)
    if not isinstance(req, Mapping):
        return _ok({
            "verdict": "UNKNOWN_TARGET_BOUND_PREVIEW_REQUEST",
            "why": f"request must be an object with schema {request_schema}",
            "fact_promotions": [],
        })
    from . import target_reconstruction as _target_reconstruction
    result = _target_reconstruction.build_target_bound_candidate_preview(req)
    result["mcp_request_schema"] = request_schema
    result["human_approval_required"] = True
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_target_sculpt_clearance_simulate(json_text: str = "") -> str:
    """Project an edited fused target outside a selected avatar envelope.

    This deterministic tool checks the retained target faces against an
    avatar envelope derived only from the selected body measurements and the
    requested cloth thickness.  It returns moved vertices, collision faces
    and clearance diagnostics as a PROPOSED geometric preview.  It does not
    claim drape, ease, pressure, comfort, material or manufacturing accuracy.
    """
    request_schema = "garment.target-sculpt-clearance.request.v1"
    req, err = _json_arg(json_text, f"{request_schema} object")
    if err:
        return _ok(err)
    if not isinstance(req, Mapping):
        return _ok({
            "verdict": "UNKNOWN_TARGET_SCULPT_CLEARANCE_REQUEST",
            "why": f"request must be an object with schema {request_schema}",
            "fact_promotions": [],
        })
    from . import target_sculpt_clearance as _target_clearance
    result = _target_clearance.solve_target_sculpt_clearance(req)
    result["mcp_request_schema"] = request_schema
    result["human_approval_required"] = True
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_target_sculpt_modifier(json_text: str = "") -> str:
    """Apply one bounded, revision-linked fused-target CAD modifier.

    ``json_text`` must be a
    ``garment.target-sculpt-modifier.request.v1`` object.  PULL moves a named
    face/vertex selection along deterministic local normals or an explicit
    vector; STRETCH scales that selection along one axis from a named anchor;
    WIND_PREVIEW creates a uniform low-fidelity visual displacement candidate.
    The input mesh is immutable and every accepted edit returns a new revision,
    digest, and undo-parent digest.  These are PROPOSED CAD edits only: the
    tool makes no pressure, material, cloth, seam, fit, or manufacturing claim.
    """
    request_schema = "garment.target-sculpt-modifier.request.v1"
    req, err = _json_arg(json_text, f"{request_schema} object")
    if err:
        return _ok(err)
    if not isinstance(req, Mapping):
        return _ok({
            "verdict": "UNKNOWN_TARGET_SCULPT_MODIFIER_REQUEST",
            "why": f"request must be an object with schema {request_schema}",
            "fact_promotions": [],
        })
    from . import target_sculpt_modifiers as _target_modifiers
    result = _target_modifiers.apply_target_sculpt_modifier(req)
    result["mcp_request_schema"] = request_schema
    result["human_approval_required"] = True
    result["manufacturing_ready"] = False
    result["manufacturing_certified"] = False
    result["fact_promotions"] = []
    return _ok(result)


@tool
def garment_candidate_pattern_sewing_assemble(json_text: str = "") -> str:
    """Build digest-bound cutting and topology sewing artifacts per candidate.

    ``json_text`` is the existing
    ``garment.front-candidate-artifact-pipeline.request.v1`` input.  Every
    front-derived structure alternative is compiled independently through the
    candidate pattern, cutting bundle, and topology-derived sewing order.
    Missing closure, seam method, layer attachment, material or operator
    choices remain REVIEW; a failed candidate remains as a typed STOPPED
    sibling.  This route uses no corpus and cannot claim manufacturing
    readiness or certification.
    """
    req, err = _json_arg(
        json_text,
        "garment.front-candidate-artifact-pipeline.request.v1 object",
    )
    if err:
        return _ok(err)
    from . import candidate_pattern_sewing_pipeline as _cut_sew_pipeline
    return _ok(_cut_sew_pipeline.assemble(req))


@tool
def garment_layered_compose(json_text: str = "") -> str:
    """Compose front-derived geometric components into layered candidates.

    ``json_text`` is a ``garment.layered-vision.v1`` object.  This tool does
    not classify the garment by name: it delegates to the deterministic
    geometry composer and preserves every feasible JOIN, SEPARATE, LAYER,
    CONTACT, and OVERLAP alternative.  Hidden rear geometry, materials, and
    attachment topology remain PROPOSED; ambiguous valid topologies require
    human choice.  No result is manufacturing-ready or certified.
    """
    req, err = _json_arg(
        json_text, "garment.layered-vision.v1 object")
    if err:
        return _ok(err)
    from . import layered_garment_composer as _layered
    return _ok(_layered.compose(req))


@tool
def garment_candidates(json_text: str = "", action: str = "propose",
                       digest: str = "", by: str = "") -> str:
    """Propose or approve back/material alternatives without inventing facts.

    ``action=propose`` accepts ``kind``, shared ``evidence`` and at least two
    explicit ``candidates``. ``action=approve`` accepts the returned ``sheet``
    plus a candidate digest and named human approver. Approval is immutable
    and digest-bound; it does not rewrite a proposal as observed evidence.
    """
    req, err = _json_arg(json_text, "candidate request object")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text must be an object"})
    from . import candidate_compare as _candidates
    selected_action = str(action or req.get("action", "propose")).lower()
    if selected_action == "propose":
        return _ok(_candidates.propose(req.get("kind"),
                                       req.get("evidence", {}),
                                       req.get("candidates", ())))
    if selected_action == "approve":
        sheet = req.get("sheet", req)
        return _ok(_candidates.approve(
            sheet, digest or str(req.get("digest", "")),
            by or str(req.get("by", ""))))
    return _ok({"verdict": "UNKNOWN_CANDIDATE_ACTION",
                "why": "action must be propose or approve"})


def _factory_path() -> Path:
    return _p("garment_factory.json")


def _load_factory(job_id: str = "") -> Dict[str, Any]:
    from . import garment_factory as _factory
    path = _factory_path()
    if path.exists():
        try:
            value = _json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("schema") == _factory.SCHEMA:
                return value
        except (OSError, ValueError):
            pass
    return _factory.new_job(job_id or f"{_project()}-garment")


def _save_factory(state: Mapping[str, Any]) -> None:
    _factory_path().write_text(
        _json.dumps(dict(state), ensure_ascii=False, indent=1, allow_nan=False),
        encoding="utf-8")


@tool
def garment_hybrid_retrieve(json_text: str = "") -> str:
    """Create multi-stage structure candidates from confirmed image evidence.

    Input may be ``{image_evidence, request, corpora}``, a saved factory
    ``{state, request, corpora}``, or ``{outline, regions, request, corpora}``.
    Each local corpus must carry a ``garment.corpus-manifest.v1`` manifest and
    records.  Shape, part, layer, opening, topology, and material-range scores
    remain separate.  With no eligible corpus the tool still returns at least
    two ``procedural:`` hits and multiple proposed back structures, explicitly
    marked as generated geometry rather than an existing-garment search.
    """
    req, err = _json_arg(json_text, "hybrid garment retrieval request")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "request must be an object"})
    state = req.get("state")
    payload = dict(req)
    if isinstance(state, Mapping):
        payload["image_evidence"] = state.get("image_evidence")
    from . import retrieval_hypothesis as _hybrid
    return _ok(_hybrid.multi_stage_retrieve(payload))


@tool
def garment_factory(json_text: str = "", action: str = "advance") -> str:
    """Run the resumable image -> candidates -> pattern -> validation loop.

    ``action=start`` creates a fresh per-project ``garment.factory.v1`` job;
    ``action=inspect`` returns it.  ``action=advance`` accepts one typed
    ``event`` (or the event object directly).  External SigLIP/multimodal/LLM
    output enters only through ``SUBMIT_RETRIEVAL`` and
    ``SUBMIT_HYPOTHESES`` and is forcibly kept ``PROPOSED``.
    ``HYBRID_RETRIEVE`` runs the same two events using the local rights-gated
    multi-stage retriever. ``HYBRID_SEWING_SEARCH`` is reachable only after a
    named digest approval and distinguishes corpus methods from built-in
    procedural assembly hypotheses. A named human and exact candidate digest
    are required before pattern, sewing or physics.

    The pattern runner compiles the exact approved ``garment.structure.v1``
    candidate into candidate-specific pieces and seams.  The old
    outline-derived second-skin/body-block remains attached only as a visual
    and calibration baseline; it is no longer the authoritative flat pattern.
    """
    from . import garment_factory as _factory
    req, err = _json_arg(json_text, "garment factory request")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS", "why": "request must be an object"})
    selected = str(action or req.get("action", "advance")).lower()
    if selected == "start":
        try:
            state = _factory.new_job(str(req.get("job_id") or f"{_project()}-garment"),
                                     int(req.get("max_iterations", 8)))
        except (TypeError, ValueError) as exc:
            return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS", "why": str(exc)})
        _save_factory(state)
        return _ok({"verdict": "ANSWER", "state": state})
    state = _load_factory(str(req.get("job_id", "")))
    if selected == "inspect":
        return _ok({"verdict": "ANSWER", "state": state})
    if selected != "advance":
        return _ok({"verdict": "UNKNOWN_FACTORY_ACTION",
                    "why": "action must be start, inspect or advance"})
    event = req.get("event", req)

    def pattern_runner(current: Dict[str, Any], stage_event: Dict[str, Any]) -> Mapping[str, Any]:
        from . import garment_export_package as _export_package
        from . import garment_export_verifier as _export_verifier
        from . import garment_engineering_review as _engineering_review
        from . import pattern_manufacturing_bundle as _manufacturing
        from . import structure_preview as _structure_preview
        from . import structure_sewing_plan as _sewing_plan
        from . import structure_to_pattern as _structure_pattern
        from . import photo_to_pattern as _p2p
        selected_id = current["shape_approval"]["candidate_id"]
        selected_candidate = next(row for row in current["hypothesis_sheet"]["candidates"]
                                  if row["candidate_id"] == selected_id)
        structure = selected_candidate.get("structure")
        if not isinstance(structure, Mapping):
            return {"verdict": "UNKNOWN_APPROVED_STRUCTURE_REQUIRED",
                    "why": "the approved candidate has no garment.structure.v1 graph",
                    "candidate_id": selected_id}
        approval = current["shape_approval"]
        result = _structure_pattern.compile(
            structure, candidate_state="APPROVED", candidate_id=selected_id,
            approval={"by": approval["by"],
                      "digest": approval["candidate_digest"],
                      "approval_id": approval["approval_id"]})
        if result.get("verdict") != "ANSWER":
            return result
        # A vision model may name an accessory or construction role for which
        # no deterministic primitive compiler exists.  The candidate can still
        # be previewed, but the represented subset must never be exported as if
        # it covered the whole visible outfit.
        result["uncompiled_visual_parts"] = _json.loads(_json.dumps(
            selected_candidate.get("uncompiled_visual_parts", []),
            ensure_ascii=False, allow_nan=False))
        result["representation_complete"] = bool(
            selected_candidate.get("representation_complete", True))
        options = stage_event.get("options", {})
        if not isinstance(options, Mapping):
            options = {}

        # Topology supplies a deterministic dependency order even when no
        # construction corpus is installed.  Unknown stitch/closure choices
        # remain typed REVIEW records rather than stopping the whole preview.
        result["topology_sewing_plan"] = _sewing_plan.plan(result)

        # A front-only beginner run still needs an inspectable cut-line
        # preview.  When no allowance was supplied we deliberately opt in to
        # a PROPOSED default; this never promotes manufacturing_ready.
        seam_allowance = stage_event.get(
            "seam_allowance_cm", options.get("seam_allowance_cm"))
        result["manufacturing_preview"] = _manufacturing.build(
            result,
            seam_allowance_cm=seam_allowance,
            allow_proposed_default=seam_allowance is None,
            proposed_default_cm=options.get("proposed_seam_allowance_cm", 1.0))
        result["engineering_review"] = _engineering_review.review(
            result, manufacturing=result["manufacturing_preview"],
            sewing_plan=result["topology_sewing_plan"])
        export_package = _export_package.build(
            result["manufacturing_preview"],
            result["engineering_review"],
            result["topology_sewing_plan"])
        result["export_verification"] = _export_verifier.verify(export_package)
        result["export_package"] = _json_safe_export_package(export_package)
        candidate_preview = _structure_preview.generate_preview(
            structure, candidate_id=selected_id)
        result["candidate_preview"] = candidate_preview
        if candidate_preview.get("verdict") == "ANSWER":
            mesh = candidate_preview["mesh"]
            result["garment_surface"] = {
                "verdict": "ANSWER", "units": mesh["units"],
                "verts": mesh["vertices"], "faces": mesh["faces"],
                "source": "approved garment.structure.v1 candidate preview",
                "preview_only": True,
            }

        # The image-outline path remains useful as an independent body-block
        # and dressed-surface reference.  It must not replace the candidate
        # structure that the person actually approved.
        measures = _measures()
        proposed = []
        if bool(stage_event.get("preview_mannequin")):
            defaults = {"chest": 88.0, "waist": 68.0, "hip": 94.0,
                        "body_length": 140.0}
            preview = Measures(entries=list(measures.entries))
            measured = {entry.spot for entry in preview.entries if entry.kind == "measured"}
            for spot, value in defaults.items():
                if spot not in measured:
                    preview.measured(spot, value, "cm", source="PROPOSED_PREVIEW_MANNEQUIN")
                    proposed.append({"spot": spot, "value": value, "unit": "cm",
                                     "state": "PROPOSED", "persisted": False})
            measures = preview
        baseline = _p2p.run(
            current["image_evidence"]["outline"], measures,
            n_panels=int(options.get("n_panels", 4)),
            segments=int(options.get("segments", 24)),
            height_steps=int(options.get("height_steps", 16)),
            iterations=int(options.get("iterations", 3000)),
            dart_depth_ratio=float(options.get("dart_depth_ratio", 0.30)),
            image_id=str(options.get("image_id", "")))
        result["outline_body_block_baseline"] = baseline
        if baseline.get("verdict") == "ANSWER":
            # These fields feed the current mannequin/simulation UI.  Their
            # provenance remains visibly separate from the compiled pieces.
            if "garment_surface" in baseline and "garment_surface" not in result:
                result["garment_surface"] = baseline["garment_surface"]
            result["outline_baseline_digest"] = hashlib.sha256(
                _json.dumps(baseline, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode("utf-8")
            ).hexdigest()
        result["approved_hypothesis_binding"] = {
            "approval_id": approval["approval_id"],
            "candidate_id": selected_id,
            "candidate_digest": selected_candidate["digest"],
            "structure_digest": result["structure_digest"],
            "structure": structure,
        }
        result["pattern_scope"] = {
            "implemented": ("approved structure graph primitives -> candidate-specific "
                            "sewing-line pieces, seam topology, dependency-safe sewing order, and "
                            "validated topology-changing geometry where the compiler returns ANSWER, "
                            "plus a PROPOSED cut-line/SVG/DXF preview; outline body block is a "
                            "separate baseline"),
            "not_yet_claimed": ("manufacturing certification, wearer fit, measured material behaviour, "
                                "or topology operations outside the exact limits and lineage reported "
                                "by the compiled-pattern artifact"),
        }
        if proposed:
            result["preview_mannequin"] = {"state": "PROPOSED", "values": proposed,
                                             "must_be_replaced_before_manufacturing": True}
        return result

    def repair_runner(current: Dict[str, Any], stage_event: Dict[str, Any]) -> Mapping[str, Any]:
        from . import garment_export_package as _export_package
        from . import garment_export_verifier as _export_verifier
        from . import garment_engineering_review as _engineering_review
        from . import pattern_manufacturing_bundle as _manufacturing
        from . import repairs as _repairs
        from . import structure_sewing_plan as _sewing_plan
        result = _repairs.make_sewable(current["pattern"],
                                       budget=max(1, int(stage_event.get("budget", 8))))
        repaired_pattern = result.get("pattern")
        if isinstance(repaired_pattern, Mapping):
            result["topology_sewing_plan"] = _sewing_plan.plan(repaired_pattern)
            result["manufacturing_preview"] = _manufacturing.build(
                repaired_pattern,
                seam_allowance_cm=stage_event.get("seam_allowance_cm"),
                allow_proposed_default=stage_event.get("seam_allowance_cm") is None,
                proposed_default_cm=stage_event.get("proposed_seam_allowance_cm", 1.0))
            result["engineering_review"] = _engineering_review.review(
                repaired_pattern, repair=result,
                manufacturing=result["manufacturing_preview"],
                sewing_plan=result["topology_sewing_plan"])
            export_package = _export_package.build(
                result["manufacturing_preview"],
                result["engineering_review"],
                result["topology_sewing_plan"])
            result["export_verification"] = _export_verifier.verify(export_package)
            result["export_package"] = _json_safe_export_package(export_package)
        result["verdict"] = ("ANSWER" if bool(result.get("sewable"))
                             else "UNKNOWN_PATTERN_REPAIR_INCOMPLETE")
        result["scope"] = "geometric sewability repair; not strength/comfort certification"
        return result

    def simulation_runner(current: Dict[str, Any], stage_event: Dict[str, Any]) -> Mapping[str, Any]:
        from . import garment_engineering_review as _engineering_review
        from . import industrial_solver as _industrial
        payload = stage_event.get("input")
        if not isinstance(payload, Mapping):
            return {"verdict": "UNKNOWN_SIMULATION_INPUT",
                    "why": "SIMULATE requires a typed industrial solver input"}
        result = _industrial.simulate(dict(payload))
        if result.get("verdict") == "ANSWER":
            repair = current.get("repair")
            repair_pattern = (repair.get("pattern") if isinstance(repair, Mapping)
                              else None)
            pattern = (repair_pattern if isinstance(repair_pattern, Mapping)
                       else current.get("pattern"))
            if isinstance(pattern, Mapping):
                result["engineering_review"] = _engineering_review.review(
                    pattern,
                    repair=repair if isinstance(repair, Mapping) else None,
                    manufacturing=(repair.get("manufacturing_preview")
                                   if isinstance(repair, Mapping) else None),
                    sewing_plan=(repair.get("topology_sewing_plan")
                                 if isinstance(repair, Mapping) else None),
                    simulation=result)
        return result

    result = _factory.advance(state, event,
                              pattern_runner=pattern_runner,
                              repair_runner=repair_runner,
                              simulation_runner=simulation_runner)
    next_state = result.get("state")
    if isinstance(next_state, Mapping) and next_state.get("schema") == _factory.SCHEMA:
        _save_factory(next_state)
    return _ok(result)


@tool
def garment_export_package(json_text: str = "") -> str:
    """Build an exact, JSON-safe candidate hand-off without writing files.

    Input is ``{manufacturing_bundle, engineering_review, sewing_plan}``.
    Text files remain text and binary DXF bytes are base64 wrapped.  Candidate,
    structure and source-pattern digests must agree or the operation refuses.
    """
    req, err = _json_arg(json_text, "garment export package request")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "request must be an object"})
    from . import garment_export_package as _export_package
    result = _export_package.build(
        req.get("manufacturing_bundle", {}),
        req.get("engineering_review", {}),
        req.get("sewing_plan", {}),
        filenames=req.get("filenames"))
    return _ok(_json_safe_export_package(result))


@tool
def garment_verify_export_package(json_text: str = "") -> str:
    """Verify exact files and candidate lineage after package transport.

    Input is the JSON-safe result of ``garment_export_package``.  Text and
    base64 DXF are decoded in memory, every manifest/wrapper hash is checked,
    and lineage embedded in SVG, DXF and JSON artifacts must agree.  An
    ``ANSWER`` proves transport integrity only, never manufacturing quality.
    """
    req, err = _json_arg(json_text, "garment.export-package.v1 object")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "request must be an object"})
    from . import garment_export_verifier as _export_verifier
    return _ok(_export_verifier.verify(req))


@tool
def garment_pattern_transform(json_text: str = "") -> str:
    """Apply one deterministic pleat, gather, dart or fold operation.

    Input is ``{pattern: {...}, operation: {...}}``. Stable piece/edge
    addresses and before/after digests make previews and Undo auditable.
    """
    req, err = _json_arg(json_text, "{pattern: {...}, operation: {...}}")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text must be an object"})
    from . import pattern_transforms as _transforms
    return _ok(_transforms.apply(req.get("pattern", {}),
                                 req.get("operation", {})))


@tool
def corpus_manifest_check(json_text: str = "", purpose: str = "retrieval",
                          require_commercial: bool = True) -> str:
    """Validate a future corpus manifest without downloading the corpus.

    Free access is not treated as commercial permission.  The manifest must
    cite controlling licence text, record commercial/derivative/redistribution
    rights, preserve generator lineage, and declare construction-bearing
    modalities before ``purpose=sewing`` can answer.  This is a machine gate,
    not a legal opinion.
    """
    req, err = _json_arg(json_text, "garment.corpus-manifest.v1 object")
    if err:
        return _ok(err)
    from . import corpus_manifest as _manifest
    return _ok(_manifest.validate(
        req, require_commercial=bool(require_commercial), purpose=purpose))


@tool
def corpus_record_format(modality: str = "") -> str:
    """Return the required typed fields for one optional corpus modality."""
    from . import corpus_manifest as _manifest
    return _ok(_manifest.expected_record_fields(modality))


@tool
def cross_cloth_simulate(json_text: str = "") -> str:
    """Run the six-arm cross cloth solver (SI units).

    ``json_text`` requires ``vertices``, ``faces``, ``face_material_ids`` and
    explicit ``materials``; optional fields include ``fixed_vertices``,
    ``vertex_layers``, ``constraints``, ``environment``, ``time_step_s``,
    ``steps``, ``constraint_iterations``, ``speed_tolerance_m_s`` and
    ``stable_steps_required``. The stages are typed hand-offs: lattice ->
    forces/wind -> contact/seams/self-collision. No LLM is used.
    """
    req, err = _json_arg(json_text, "{vertices, faces, face_material_ids, materials}")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text must be an object"})
    required = ("vertices", "faces", "face_material_ids", "materials")
    missing = [key for key in required if key not in req]
    if missing:
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS", "missing": missing})
    solver = str(req.get("solver", "legacy")).strip().lower()
    if solver == "xpbd":
        from . import cross_xpbd as _xpbd
        optional = {key: req[key] for key in (
            "face_warp_directions", "initial_positions", "initial_velocities",
            "fixed_vertices", "seams", "gravity_m_s2", "time_step_s", "steps",
            "solver_iterations", "jacobi_relaxation",
            "max_displacement_fraction", "max_substeps",
            "convergence_tolerance", "speed_tolerance_m_s",
            "stable_steps_required") if key in req}
        return _ok(_xpbd.simulate(
            req["vertices"], req["faces"],
            face_material_ids=req["face_material_ids"],
            materials=req["materials"], **optional))
    if solver not in ("legacy", "cross"):
        return _ok({"verdict": "UNKNOWN_CROSS_SOLVER_BACKEND",
                    "why": "solver must be legacy or xpbd",
                    "available": ["legacy", "xpbd"]})
    from . import cross_cloth_solver as _cross_cloth
    optional = {key: req[key] for key in (
        "fixed_vertices", "vertex_layers", "constraints", "environment",
        "time_step_s", "steps", "constraint_iterations",
        "speed_tolerance_m_s", "stable_steps_required") if key in req}
    return _ok(_cross_cloth.simulate(
        req["vertices"], req["faces"],
        face_material_ids=req["face_material_ids"],
        materials=req["materials"], **optional))


@tool
def cross_cloth_capabilities() -> str:
    """Report implemented CPU XPBD features and honest GPU availability."""
    from . import cross_xpbd as _xpbd
    report = _xpbd.capabilities()
    report["metal_app_backend"] = {
        "implemented": True,
        "wired_to_python_mcp": False,
        "why": "the optional Metal backend runs in the macOS app and must "
               "complete a command buffer before it can claim GPU execution",
    }
    return _ok(report)


@tool
def industrial_cloth_simulate(json_text: str = "") -> str:
    """Run one typed high-fidelity reference workflow without an LLM.

    The request schema is ``garment.industrial-cloth-step.v1``. Numerical
    layers remain separate: optional measured-material calibration and fluid
    impulse, XPBD time integration, optional shell residual/correction, CCD
    contact/seam projection, and optional REVIEW-only comfort screening.
    This is an inspectable reference workflow, not an industrial-validation
    claim.
    """
    req, err = _json_arg(json_text, "garment.industrial-cloth-step.v1 object")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text must be an object"})
    from . import industrial_solver as _industrial
    return _ok(_industrial.simulate(req))


@tool
def industrial_cloth_capabilities() -> str:
    """Report integrated numerical kernels and all known industrial gaps."""
    from . import industrial_solver as _industrial
    return _ok(_industrial.capabilities())


@tool
def high_fidelity_workflow(json_text: str = "") -> str:
    """Run requested high-fidelity stages under one verdict-preserving gate.

    The input is ``garment.high-fidelity-workflow.v1``.  Global shell,
    bounded broad-phase/CCD, incompressible flow, yarn/needle topology,
    measured seam calibration and wearer-specific comfort stages remain
    independent: a refusal in one stage is never averaged into another.
    """
    req, err = _json_arg(json_text, "garment.high-fidelity-workflow.v1 object")
    if err:
        return _ok(err)
    if not isinstance(req, dict):
        return _ok({"verdict": "UNKNOWN_BAD_ARGUMENTS",
                    "why": "json_text must be an object"})
    from . import high_fidelity_workflow as _workflow
    return _ok(_workflow.run(req))


@tool
def high_fidelity_capabilities() -> str:
    """Report implemented kernels, GPU boundary and validation exclusions."""
    from . import high_fidelity_workflow as _workflow
    return _ok(_workflow.capabilities())


@tool
def proof_cross_verify(json_text: str = "") -> str:
    """Verify exact/bounded obligations and land evidence on the six-arm cross."""
    req, err = _json_arg(json_text, "solver.proof-cross.v1 object")
    if err:
        return _ok(err)
    from . import physics_proof_cross as _proof
    return _ok(_proof.verify(req))


@tool
def proof_cross_capabilities() -> str:
    """Report what the proof cross can certify and what it cannot solve."""
    from . import physics_proof_cross as _proof
    return _ok(_proof.capabilities())


@tool
def certified_collision_solve(json_text: str = "") -> str:
    """Run exact predicates and conservative linear-motion CCD certificates."""
    req, err = _json_arg(json_text, "certified collision request object")
    if err:
        return _ok(err)
    from . import certified_collision as _collision
    return _ok(_collision.solve(req))


@tool
def implicit_shell_dynamics_solve(json_text: str = "") -> str:
    """Run implicit Newmark shell dynamics with a numerical residual tangent."""
    req, err = _json_arg(json_text, "implicit shell dynamics request object")
    if err:
        return _ok(err)
    from . import implicit_shell_dynamics as _shell
    return _ok(_shell.solve(req))


@tool
def turbulence_validate(json_text: str = "") -> str:
    """Run manufactured-flow checks and evidence-gated turbulence validation."""
    req, err = _json_arg(json_text, "turbulence validation request object")
    if err:
        return _ok(err)
    from . import turbulence_validation as _validation
    return _ok(_validation.validate(req))


@tool
def sewing_topology_simulate(json_text: str = "") -> str:
    """Run reference yarn torsion, friction, cutting and remeshing events."""
    req, err = _json_arg(json_text, "sewing topology request object")
    if err:
        return _ok(err)
    from . import sewing_topology as _topology
    return _ok(_topology.simulate(req))


@tool
def nonlinear_shell_solve(json_text: str = "") -> str:
    """Solve one deterministic global quasi-Newton shell equilibrium case."""
    req, err = _json_arg(json_text, "nonlinear shell request object")
    if err:
        return _ok(err)
    from . import nonlinear_shell_fem as _shell
    return _ok(_shell.solve(req))


@tool
def production_collision_solve(json_text: str = "") -> str:
    """Run swept broad phase and bounded floating-point CCD checks."""
    req, err = _json_arg(json_text, "production collision request object")
    if err:
        return _ok(err)
    from . import production_collision as _collision
    return _ok(_collision.solve(req))


@tool
def incompressible_fluid_step(json_text: str = "") -> str:
    """Advance one pressure-projected incompressible-grid reference step."""
    req, err = _json_arg(json_text, "incompressible fluid request object")
    if err:
        return _ok(err)
    from . import incompressible_fluid as _fluid
    return _ok(_fluid.step(req))


@tool
def yarn_needle_simulate(json_text: str = "") -> str:
    """Simulate discrete yarn, needle motion and reversible stitch topology."""
    req, err = _json_arg(json_text, "yarn and needle request object")
    if err:
        return _ok(err)
    from . import yarn_needle as _yarn
    return _ok(_yarn.simulate(req))


@tool
def seam_calibrate(json_text: str = "") -> str:
    """Fit seam coefficients only from complete measured seam channels."""
    req, err = _json_arg(json_text, "measured seam calibration object")
    if err:
        return _ok(err)
    from . import seam_calibration as _seam
    return _ok(_seam.calibrate(req))


@tool
def wearer_comfort_evaluate(json_text: str = "") -> str:
    """Evaluate wearer-bound observations as REVIEW, never medical truth."""
    req, err = _json_arg(json_text, "wearer comfort observation object")
    if err:
        return _ok(err)
    from . import wearer_comfort as _comfort
    return _ok(_comfort.evaluate(req))


@tool
def material_calibrate(json_text: str = "") -> str:
    """Calibrate six observed textile channels; never fill missing channels."""
    req, err = _json_arg(json_text, "material.measurements.v1 object")
    if err:
        return _ok(err)
    from . import material_calibration as _calibration
    return _ok(_calibration.calibrate(req))


@tool
def comfort_evaluate(json_text: str = "") -> str:
    """Return a REVIEW-only engineering comfort comparison from observations."""
    req, err = _json_arg(json_text, "garment.comfort-observations.v1 object")
    if err:
        return _ok(err)
    from . import comfort_model as _comfort
    return _ok(_comfort.evaluate(req))


@tool
def corpus_catalog_ingest(catalog_path: str = "", index_path: str = "",
                          commit: bool = False) -> str:
    """Rights-gate and content-address a local commercial candidate catalog.

    The bundled default catalog contains metadata only. It does not download
    repositories, images, meshes, GarmentCodeData or generated patterns. Code
    licences are not transferred to data rights.
    """
    from . import corpus_ingest as _ingest
    catalog = (Path(catalog_path) if catalog_path.strip() else
               Path(__file__).resolve().parent.parent / "docs" / "corpora" /
               "candidate-catalog.json")
    index = (Path(index_path) if index_path.strip() else
             _p("corpus-content-index"))
    try:
        loaded = _ingest.load_catalog(catalog)
        return _ok(_ingest.ingest(loaded, index, commit=bool(commit)))
    except (OSError, ValueError) as exc:
        return _ok({"verdict": "UNKNOWN_CORPUS_INGEST_IO", "why": str(exc),
                    "catalog_path": str(catalog), "index_path": str(index)})


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
