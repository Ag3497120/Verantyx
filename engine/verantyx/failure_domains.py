"""Failure-domain packs — the plugin boundary of the typed-failure loop.

The core of the loop is field-independent: typed verdicts accumulate in
growth signals, the boundary classifier decides what a recurrence means,
remedies go through quarantine, and a human accept is the only path to an
applied change. What changes per field is exactly two things, and this
module makes that boundary explicit:

    1. the CLASSIFIER   evidence text  -> typed UNKNOWN_* verdict
    2. the REMEDY MAP   verdict        -> what kind of fix, owned by whom,
                                          verified how

The first two packs (math, build) are extracted from code that already
existed and was validated against failures that really happened in this
project. The rest are SEEDED: their taxonomies and remedy maps encode
public, well-documented failure shapes of their fields, but no confirmed
incident from this project backs them yet. That difference is not a
footnote — it is enforced:

  - `maturity="verified"` requires at least one fixture whose provenance is
    "confirmed" (checked by failure_domains_eval).
  - Only verified packs may mark a remedy `auto_calibratable=True`, i.e.
    allowed to feed the capacity-calibration loop that proposes limit
    changes. A seeded pack classifies and counts; it does not get to
    suggest numbers. A pattern with no confirmed example is a guess wearing
    a regex, and guesses do not calibrate anything.

Promotion is by evidence, not by edit: when a seeded pack's verdict is
confirmed against a real incident, the incident excerpt becomes a
provenance="confirmed" fixture, and only then may the pack graduate.

Classification runs patterns-outer / lines-inner — priority means priority
across the whole log. That ordering is a lesson paid for: dyld prints the
dependency-shaped symptom on line one and the signing-shaped cause on line
two, and a line-outer scan misdiagnosed it exactly the way a person did
when it first happened (see build_failure.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

#: What kind of action fixes this verdict. A closed vocabulary on purpose:
#: downstream tooling groups and routes on these, and a free-text kind would
#: put us back at "failed: (prose)".
REMEDY_KINDS = frozenset({
    "add_facts",          # knowledge is missing; a human/system adds it
    "add_rule_or_module", # a capability is missing; draft -> verify -> quarantine
    "raise_limit",        # a numeric capacity binds; calibrate -> quarantine
    "add_data_source",    # observability gap; wire a new source in
    "fix_content",        # an artifact (article/synonym/level) needs editing
    "fix_upstream",       # the cause is in a system we call, not in us
    "request_input",      # the counterparty must supply something
    "human_judgment",     # permanently out of automation's scope
    "fix_code",           # a defect in our own code
})

VERIFY_METHODS = frozenset({
    "rerun",              # run the same thing again, verdict should change
    "rerun_larger_limit", # capacity_calibration's ladder
    "replay",             # deterministic replay (game QA's free ground truth)
    "manual",             # a person checks
})


@dataclass(frozen=True)
class RemedySpec:
    kind: str
    owner: str            # which role/subsystem acts on it
    verify: str
    #: May this verdict feed automatic limit calibration? Only meaningful
    #: for kind="raise_limit", and only permitted in verified packs.
    auto_calibratable: bool = False
    note: str = ""


@dataclass(frozen=True)
class Fixture:
    name: str
    expect: str
    evidence: str
    #: "confirmed" = a real incident, diagnosis confirmed at the time.
    #: "synthetic" = written to specify intended behaviour. Both are eval
    #: inputs; only "confirmed" counts toward verified maturity.
    provenance: str


@dataclass
class FailureDomain:
    name: str
    maturity: str  # "verified" | "seeded"
    description: str
    #: (verdict, compiled pattern, note) — order IS priority.
    patterns: List[Tuple[str, "re.Pattern[str]", str]]
    remedies: Dict[str, RemedySpec]
    fixtures: List[Fixture] = field(default_factory=list)
    fallback: str = "UNKNOWN_UNCLASSIFIED"
    #: Where each verdict's knowledge came from. "incident_confirmed" |
    #: "claude_seeded" | "llm:<model>" | "human:<name>". Correctness is NOT
    #: what this field asserts — it asserts accountability: who to ask, and
    #: whether an expert has looked at it yet. A claude_seeded entry a domain
    #: expert edits becomes human:<name>, and that transition is the whole
    #: correction workflow.
    provenance: Dict[str, str] = field(default_factory=dict)
    #: File this pack was loaded from, if data-defined. None = built in code.
    source_path: Optional[str] = None

    def classify(self, evidence: str) -> Tuple[str, str, str]:
        """(verdict, evidence_line, note). Patterns outer, lines inner."""
        lines = [ln.strip() for ln in (evidence or "").splitlines() if ln.strip()]
        for verdict, pattern, note in self.patterns:
            for line in lines:
                if pattern.search(line):
                    return verdict, line[:240], note
        return self.fallback, "", "no pattern matched"


_registry: Dict[str, FailureDomain] = {}
_load_errors: List[str] = []


def register(domain: FailureDomain) -> None:
    if domain.name in _registry:
        raise ValueError(f"failure domain already registered: {domain.name}")
    _registry[domain.name] = domain


def load_errors() -> List[str]:
    """Packs that failed validation at load time, with why. A broken expert
    edit must be loud and inspectable, never a silent absence."""
    return list(_load_errors)


# ---------------------------------------------------------------------------
# Validation — the maturity contract as a callable, shared by the eval and
# by every load path. A pack that a human or an LLM writes goes through the
# SAME checks as one written here; the research platform is exactly this:
# the knowledge is editable data, and the contract is not.
# ---------------------------------------------------------------------------

def validate(dom: FailureDomain) -> List[str]:
    errs: List[str] = []
    pattern_verdicts = {v for v, _, _ in dom.patterns}
    if dom.maturity not in ("verified", "seeded"):
        errs.append(f"maturity {dom.maturity!r} invalid")
    if not dom.patterns:
        errs.append("no patterns")
    for v in pattern_verdicts:
        if v not in dom.remedies:
            errs.append(f"R1: verdict {v} has no remedy")
    for v in dom.remedies:
        if v not in pattern_verdicts:
            errs.append(f"R1: remedy for {v} matches no pattern")
    for v, spec in dom.remedies.items():
        if spec.kind not in REMEDY_KINDS:
            errs.append(f"R2: {v} remedy kind {spec.kind!r} not in vocabulary")
        if spec.verify not in VERIFY_METHODS:
            errs.append(f"R2: {v} verify {spec.verify!r} not in vocabulary")
        if spec.auto_calibratable:
            if spec.kind != "raise_limit":
                errs.append(f"R3: {v} auto_calibratable but kind={spec.kind}")
            if dom.maturity != "verified":
                errs.append(f"R3: {v} auto_calibratable in a SEEDED pack")
    if dom.maturity == "verified":
        if not any(f.provenance == "confirmed" for f in dom.fixtures):
            errs.append("R4: verified pack with no confirmed fixture")
    for f in dom.fixtures:
        if f.provenance not in ("confirmed", "synthetic"):
            errs.append(f"R4: fixture {f.name!r} provenance {f.provenance!r}")
        else:
            got, _, _ = dom.classify(f.evidence)
            if got != f.expect:
                errs.append(f"R5: fixture {f.name!r} expected {f.expect}, got {got}")
    if dom.fallback in pattern_verdicts:
        errs.append("R6: fallback collides with a pattern verdict")
    return errs


# ---------------------------------------------------------------------------
# JSON serialisation — the editable form. Order of `verdicts` in the file IS
# classification priority, exactly as pattern order is in code.
# ---------------------------------------------------------------------------

def pack_to_dict(dom: FailureDomain) -> Dict:
    return {
        "name": dom.name,
        "maturity": dom.maturity,
        "description": dom.description,
        "fallback": dom.fallback,
        "verdicts": [
            {
                "verdict": v,
                "pattern": pat.pattern,
                "note": note,
                "provenance": dom.provenance.get(v, "claude_seeded"),
                "remedy": {
                    "kind": dom.remedies[v].kind,
                    "owner": dom.remedies[v].owner,
                    "verify": dom.remedies[v].verify,
                    "auto_calibratable": dom.remedies[v].auto_calibratable,
                    "note": dom.remedies[v].note,
                },
            }
            for v, pat, note in dom.patterns
        ],
        "fixtures": [
            {"name": f.name, "expect": f.expect, "evidence": f.evidence,
             "provenance": f.provenance}
            for f in dom.fixtures
        ],
    }


def pack_from_dict(d: Dict, source_path: Optional[str] = None) -> FailureDomain:
    patterns = []
    remedies = {}
    provenance = {}
    for entry in d.get("verdicts", []):
        v = entry["verdict"]
        patterns.append((v, re.compile(entry["pattern"], re.IGNORECASE),
                         entry.get("note", "")))
        r = entry.get("remedy", {})
        remedies[v] = RemedySpec(
            kind=r.get("kind", ""), owner=r.get("owner", ""),
            verify=r.get("verify", ""),
            auto_calibratable=bool(r.get("auto_calibratable", False)),
            note=r.get("note", ""))
        provenance[v] = entry.get("provenance", "claude_seeded")
    fixtures = [
        Fixture(f["name"], f["expect"], f["evidence"],
                f.get("provenance", "synthetic"))
        for f in d.get("fixtures", [])
    ]
    return FailureDomain(
        name=d["name"], maturity=d.get("maturity", "seeded"),
        description=d.get("description", ""), patterns=patterns,
        remedies=remedies, fixtures=fixtures,
        fallback=d.get("fallback", "UNKNOWN_UNCLASSIFIED"),
        provenance=provenance, source_path=source_path)


def load_pack_dir(dir_path, override: bool = False) -> List[str]:
    """Loads every *.json in `dir_path` as a pack. Invalid packs are skipped
    and recorded in load_errors(); one bad file must not take down the
    registry. With override=True an existing pack of the same name is
    replaced — the overlay path an expert's edit takes."""
    import json as _json
    from pathlib import Path as _Path

    loaded: List[str] = []
    p = _Path(dir_path)
    if not p.is_dir():
        return loaded
    for f in sorted(p.glob("*.json")):
        try:
            dom = pack_from_dict(_json.loads(f.read_text()), source_path=str(f))
        except Exception as e:  # noqa: BLE001 — a data file may be arbitrarily broken
            _load_errors.append(f"{f.name}: unparseable ({e})")
            continue
        errs = validate(dom)
        if errs:
            _load_errors.append(f"{f.name}: {'; '.join(errs[:4])}")
            continue
        if dom.name in _registry:
            if not override:
                _load_errors.append(f"{f.name}: pack {dom.name!r} already registered")
                continue
            del _registry[dom.name]
        register(dom)
        loaded.append(dom.name)
    return loaded


def reload_from(dir_paths: List) -> Dict[str, List[str]]:
    """Rebuilds the data-defined portion of the registry from disk. Built-in
    packs (source_path=None) survive; everything data-defined is dropped and
    re-loaded, later directories overriding earlier ones."""
    _load_errors.clear()
    for name in [n for n, d in _registry.items() if d.source_path is not None]:
        del _registry[name]
    loaded: List[str] = []
    for d in dir_paths:
        loaded += load_pack_dir(d, override=True)
    return {"loaded": loaded, "errors": load_errors()}


def get(name: str) -> Optional[FailureDomain]:
    return _registry.get(name)


def all_domains() -> List[FailureDomain]:
    return list(_registry.values())


def record_typed_failure(growth, domain_name: str, source: str,
                         evidence: str) -> Dict[str, str]:
    """Classify through the named pack and feed the SHARED growth store.

    Bucket key is `{domain}:{source}` — stable pipeline labels, never raw
    evidence, for the same reason build_failure buckets by source: evidence
    text is too volatile for normalize_query to bucket usefully.
    """
    dom = get(domain_name)
    if dom is None:
        return {"error": f"unknown failure domain: {domain_name}",
                "known": ", ".join(sorted(_registry))}
    verdict, evidence_line, note = dom.classify(evidence)
    growth.record_unknown(f"{domain_name}:{source}", verdict)
    return {"domain": domain_name, "maturity": dom.maturity,
            "verdict": verdict, "evidence": evidence_line, "note": note}


# ---------------------------------------------------------------------------
# Pack 1: math (verified) — extracted from _math_parameter_for's knowledge.
# Evidence here is the `reason` string of a typed math verdict, which is why
# the patterns look like reason fragments rather than log lines.
# ---------------------------------------------------------------------------

def _rx(p: str) -> "re.Pattern[str]":
    return re.compile(p, re.IGNORECASE)


register(FailureDomain(
    name="math",
    maturity="verified",
    description="Typed failures of the deterministic math domain "
                "(wire arithmetic, equation enumeration, rewriting).",
    patterns=[
        ("UNKNOWN_BUDGET_MUL", _rx(r"repeat>\d+"),
         "wire_mul's step budget binds"),
        ("UNKNOWN_BUDGET_SOLVE", _rx(r"no_solution_in_0\.\.\d+"),
         "solve_equation's enumeration range binds"),
        ("UNKNOWN_OVERFLOW_ARMS", _rx(r"needs>\d+_arms|carry_out_of_last_arm"),
         "the cross has six arms; digits exceed the geometry"),
        ("UNKNOWN_NO_RULE", _rx(r"no rule applies"),
         "rewriting stuck: a rule is missing, not a budget"),
    ],
    remedies={
        "UNKNOWN_BUDGET_MUL": RemedySpec(
            kind="raise_limit", owner="config:math_mul_steps",
            verify="rerun_larger_limit", auto_calibratable=True),
        "UNKNOWN_BUDGET_SOLVE": RemedySpec(
            kind="raise_limit", owner="config:math_solve_limit",
            verify="rerun_larger_limit", auto_calibratable=True),
        "UNKNOWN_OVERFLOW_ARMS": RemedySpec(
            kind="human_judgment", owner="design",
            verify="manual",
            note="N_ARMS is the cross geometry itself — a design decision, "
                 "never a number a loop may raise"),
        "UNKNOWN_NO_RULE": RemedySpec(
            kind="add_rule_or_module", owner="rewrite ruleset",
            verify="rerun",
            note="draft the missing rule; the stuck term says which shape"),
    },
    fixtures=[
        Fixture("mul budget", "UNKNOWN_BUDGET_MUL", "repeat>500", "confirmed"),
        Fixture("solve range", "UNKNOWN_BUDGET_SOLVE",
                "no_solution_in_0..200", "confirmed"),
        Fixture("seven digits", "UNKNOWN_OVERFLOW_ARMS",
                "needs>6_arms", "confirmed"),
        Fixture("stuck rewrite", "UNKNOWN_NO_RULE",
                "no rule applies to non-result term: ('add', 0, 'nil', 'nil', ...)",
                "confirmed"),
    ],
))


# ---------------------------------------------------------------------------
# Pack 2: build (verified) — delegates to build_failure's patterns, which
# were validated against this project's own incidents. Kept in
# build_failure.py (with its eval) as the source of truth; the pack adds
# the remedy map that file never had.
# ---------------------------------------------------------------------------

from .build_failure import _PATTERNS as _BUILD_PATTERNS  # noqa: E402

register(FailureDomain(
    name="build",
    maturity="verified",
    description="Build / CI / model-conversion failures "
                "(xcodebuild, cargo, jgen_forge, dyld).",
    patterns=list(_BUILD_PATTERNS),
    remedies={
        "UNKNOWN_ENTITLEMENTS": RemedySpec(
            kind="fix_content", owner="entitlements plist", verify="rerun",
            note="AMFI parses the raw XML while Xcode normalises it first, so "
                 "this reproduces only in the packaging path — check the plist "
                 "is well-formed, including no double hyphen inside a comment"),
        "UNKNOWN_SIGNING": RemedySpec(
            kind="fix_code", owner="release pipeline", verify="rerun",
            note="re-sign after any binary swap; ditto does not preserve "
                 "ad-hoc signature validity across machines"),
        "UNKNOWN_MODEL_GEOMETRY": RemedySpec(
            kind="fix_upstream", owner="jgen_forge conversion", verify="rerun",
            note="re-convert with a forge that emits GDN geometry"),
        "UNKNOWN_MODEL_TOKENIZER": RemedySpec(
            kind="fix_content", owner="model sidecar", verify="rerun"),
        "UNKNOWN_DISK": RemedySpec(
            kind="request_input", owner="operator", verify="rerun",
            note="free space; the transfer path already refuses below 1.05x"),
        "UNKNOWN_PERMISSION": RemedySpec(
            kind="request_input", owner="operator", verify="rerun"),
        "UNKNOWN_TIMEOUT": RemedySpec(
            kind="raise_limit", owner="harness timeout",
            verify="rerun_larger_limit", auto_calibratable=False,
            note="calibratable in principle, but no config knob exists yet — "
                 "flag stays False until one does"),
        "UNKNOWN_DEPENDENCY": RemedySpec(
            kind="request_input", owner="environment", verify="rerun"),
        "UNKNOWN_TEST": RemedySpec(
            kind="fix_code", owner="the change under test", verify="rerun"),
        "UNKNOWN_COMPILE": RemedySpec(
            kind="fix_code", owner="the change under test", verify="rerun"),
    },
    fixtures=[
        # The full confirmed set lives in build_failure_eval; two anchors
        # here keep the pack's own eval meaningful without duplication.
        Fixture("codesign LFS pointer", "UNKNOWN_SIGNING",
                "code object is not signed at all\n"
                "In subcomponent: .../Contents/MacOS/verantyx-browser",
                "confirmed"),
        Fixture("GDN geometry refusal", "UNKNOWN_MODEL_GEOMETRY",
                "refusing to load — this is a hybrid (Gated DeltaNet) model, "
                "but the sidecar names none of ssm_dt_rank / ssm_n_group",
                "confirmed"),
        # Third anchor because this verdict is the newest and the one the
        # classifier itself asked for: it returned UNKNOWN_BUILD_UNCLASSIFIED
        # on the real log before the pattern existed.
        Fixture("AMFI entitlements parse", "UNKNOWN_ENTITLEMENTS",
                "Failed to parse entitlements: AMFIUnserializeXML: "
                "syntax error near line 20",
                "confirmed"),
    ],
))


# ---------------------------------------------------------------------------
# Every other pack is DATA, not code: verantyx/failure_packs/*.json, loaded
# and validated here at import. That is the research-platform decision made
# explicit — a domain expert edits a JSON file (and stamps their name into
# `provenance`), never this module. The two packs that stay in code (math,
# build) stay because their patterns are anchored to code in this repo and
# their fixtures to confirmed incidents; everything claude-seeded lives
# where it can be corrected without a programmer.
#
# An optional overlay directory (VERA_FAILURE_PACKS_DIR, or the store-
# adjacent dir the MCP server passes) loads AFTER the builtin dir and may
# override builtin packs by name — the expert's correction wins.
# ---------------------------------------------------------------------------

import os as _os
from pathlib import Path as _Path

# Under PyInstaller `__file__` points into a throwaway extraction dir whose
# layout differs from the source tree, so the bundled data root is asked for
# first. Same shape of fix jgen_forge needed for JGEN_BASE_DIR, and for the
# same reason: a frozen binary does not live where its source did.
import sys as _sys
_bundle = getattr(_sys, "_MEIPASS", None)
BUILTIN_PACK_DIR = (_Path(_bundle) / "verantyx" / "failure_packs" if _bundle
                    else _Path(__file__).resolve().parent / "failure_packs")
load_pack_dir(BUILTIN_PACK_DIR)
_overlay = _os.environ.get("VERA_FAILURE_PACKS_DIR", "")
if _overlay:
    load_pack_dir(_overlay, override=True)
