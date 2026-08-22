"""MCP server — hallucination-free memory & knowledge tools over stdio.

Exposes the cross-structure store to MCP clients (Claude Code, Claude
Desktop, …). Every tool returns typed verdicts; `ask` refuses instead of
guessing, and `forget` really deletes (knowledge is not baked into weights).

Requires the official MCP Python SDK:  pip install "mcp[cli]"
Client setup: see docs/MCP.md.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import json
import re
from pathlib import Path

from . import boundary, domains
from .agent_tools import build_registry, fetch_url, git_clone_scratch, git_clone_scratch_dir, web_search
from .ai_ingest import AiFactQuarantine
from .consensus_store import consensus_over_store
from .cross_store import CrossStore
from .code_ingest import code_ask, ingest_python_repo
from .arc_env_adapter import find_transferable_matches, observe_transition
from .ui_transition import observe_ui_transition
from .gap_graph import GapGraph, gap_graph_path
from .structural_similarity import find_structural_matches
from .task_bootstrap import TaskDescriptor
from .task_bootstrap import bootstrap_unknown_task as _bootstrap_unknown_task
from .task_bootstrap import select_next_action as _select_next_action
from .tool_call_quarantine import ToolCallQuarantine, tool_call_quarantine_path
from .transfer_outcomes import (
    TransferOutcomeLog,
    infer_missing_outcomes,
    record_transfer_attempt,
    record_transfer_outcome,
    transfer_outcome_log_path,
)
from .growth_signals import GrowthSignals, growth_signals_path
from .llm_local import ollama_available
from .math_sim import math_ask
from .module_forge import build_test_queries, draft_module
from .compose_frame import Tables as _ComposeTables
from .compose_frame import compose as _compose
from .observation import Observation as _Observation
from .observation import facets as _obs_facets
from .observation import readings as _obs_readings
from .observation import report as _obs_report
from .module_ingest import DomainModuleQuarantine
from .module_verify import verify_module


def build(store_path: str):
    """扉を全部registerした FastMCP を**走らせずに**返す。

    2026-08-22: `serve` の中身をそのまま切り出しただけ(振る舞いは不変)。
    切り出した理由は、CLI から同じ126扉に届かせるため — 扉ごとに CLI の
    コマンドを書き写すと、二つの表面が必ずずれる。**扉は一つ、入口は
    二つ**にする。SDK が無い環境では None を返す。
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print('MCP SDK not installed. Run:  pip install "mcp[cli]"')
        return None

    path = Path(store_path)
    store = CrossStore.load(path) if path.is_file() else CrossStore()
    qpath = path.with_name(path.stem + ".ai_quarantine.json")
    quarantine = AiFactQuarantine.load(qpath)

    pkg_dir = Path(__file__).resolve().parent
    domains.register_builtins()
    domains.register_generated(pkg_dir)
    gpath = growth_signals_path(path)
    growth = GrowthSignals.load(gpath)
    mqpath = path.with_name(path.stem + ".module_quarantine.json")
    module_quarantine = DomainModuleQuarantine.load(mqpath)
    from .capacity_ingest import CapacityQuarantine
    cqpath = path.with_name(path.stem + ".capacity_quarantine.json")
    capacity_quarantine = CapacityQuarantine.load(cqpath)
    from .pack_ingest import PackQuarantine
    # Overlay lives beside the store, so an expert's corrections travel with
    # their data rather than with the app bundle (which a reinstall replaces).
    pack_overlay_dir = path.parent / "failure_packs"
    pkpath = path.with_name(path.stem + ".pack_quarantine.json")
    pack_quarantine = PackQuarantine.load(pkpath)
    from .failure_domains import BUILTIN_PACK_DIR as _BPD, reload_from as _reload
    if pack_overlay_dir.is_dir():
        _reload([_BPD, pack_overlay_dir])
    # ── Japanese grammar overlay ─────────────────────────────────────────
    # Same pattern as the failure packs: an expert's vocabulary lives
    # beside their store, not inside the app bundle a reinstall replaces.
    # An invalid overlay refuses to load with every problem named — running
    # with half a grammar is the silent version of the same failure.
    from . import ja_grammar as _jag
    _grammar_overlay = path.parent / "ja_grammar.json"
    _grammar_overlay_error = ""
    if _grammar_overlay.is_file():
        try:
            _jag.load_overlay(_grammar_overlay)
        except (ValueError, OSError) as exc:
            _grammar_overlay_error = str(exc)

    ggpath = gap_graph_path(path)
    gap_graph = GapGraph.load(ggpath)

    def _save_gap_graph() -> None:
        gap_graph.save(ggpath)

    #: Human review marks, held BESIDE the store. A person's approval is
    #: not testimony the corpus gave; writing it into the facets would
    #: forge the kind of evidence this engine exists to refuse.
    _review_path = Path(str(path) + ".review.json")

    def _review_marks() -> Dict[str, str]:
        try:
            return json.loads(_review_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_review_marks(marks: Dict[str, str]) -> None:
        _review_path.write_text(
            json.dumps(marks, ensure_ascii=False, indent=1), encoding="utf-8")

    xopath = transfer_outcome_log_path(path)
    transfer_log = TransferOutcomeLog.load(xopath)

    def _save_transfer_log() -> None:
        transfer_log.save(xopath)

    tcqpath = tool_call_quarantine_path(path)
    tool_call_quarantine = ToolCallQuarantine.load(tcqpath)

    def _save_tool_call_quarantine() -> None:
        tool_call_quarantine.save(tcqpath)

    mcp = FastMCP("verantyx-vera")

    # Grain band for `ask` — a lazily built staircase over THIS store,
    # invalidated on every mutation (every mutating tool funnels through
    # `_save`, including the registry tools that receive it as their save
    # hook). The band ANNOTATES the verdict and never votes: structure
    # (cut-varied settings agreeing) and evidence (the store's own
    # consensus) stay unpooled — see `graded.band_annotation`.
    _grain: Dict[str, Any] = {}

    def _grain_judge() -> Any:
        if "judge" not in _grain:
            from .graded import GradedJudge, settings_for

            probe = " ".join(sorted(store.crosses)[:8]) or "This is English."
            _grain["judge"] = GradedJudge(settings_for(probe)).build(store)
        return _grain["judge"]

    def _save() -> None:
        store.save(path)
        _grain.pop("judge", None)

    def _save_growth() -> None:
        growth.save(gpath)

    # Milestone R4: no browser_endpoint here (this is the headless MCP
    # process, not the IDE) -- jgen_reflect will just report its own
    # typed "no_jgen_endpoint_configured" if an accepted call happens to
    # be that tool. Every other tool works identically to how the agent
    # itself would have run it.
    tool_registry = build_registry(store, _save, browser_endpoint=None)

    @mcp.tool()
    def ask(query: str) -> str:
        """Ask the knowledge store. Returns a typed verdict — ANSWER with
        provenance-backed facets, or UNKNOWN_* (never a guess). When the
        staircase can count one, a `grain` band rides beside the verdict:
        {"agree": n, "of": m, ...} — how many cut-varied settings agreed
        on an item. The band annotates; it never votes (the verdict is
        the same with or without it)."""
        out = consensus_over_store(store, query)
        try:
            from .graded import band_annotation

            band = band_annotation(_grain_judge(), query)
        except Exception:
            # The band is an annotation — losing it must never cost the
            # verdict itself.
            band = None
        if band is not None:
            out["grain"] = band
        verdict = out.get("verdict")
        if isinstance(verdict, str) and verdict.startswith("UNKNOWN"):
            growth.record_unknown(query, verdict)
            _save_growth()
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def remember(sentence: str) -> str:
        """Teach one English sentence. It is classified into core + facets
        and accumulated deterministically (usable immediately)."""
        key = store.ingest_sentence(sentence)
        _save()
        return json.dumps(
            {"remembered": key, "facets": store.top_facets(key or "", 8)},
            ensure_ascii=False,
        )

    @mcp.tool()
    def record_asset_outcome(need: str, asset: str, worked: bool,
                             gap_id: str = "", command: str = "",
                             result: str = "") -> str:
        """What happened when an asset was used for a need — and, when
        it worked, the recipe that makes the second time cheap.

        This is the half that turns exploring into learning. Without it
        the loop finds the same asset by the same reasoning every time,
        which is not autonomy, it is amnesia with good manners.

        Three things are written, and only the first is unconditional:

            outcome   `recipe:<need>` gains `tried:<asset>` either way.
                      A failure is as much a fact as a success and is
                      the thing that stops the next run repeating it.
            witness   a successful run also lands via the tool-witness
                      shape (`verified:tool:<asset>`), so `assets_for`
                      returns it under `witnessed` from then on.
            gap       a named gap moves to RESOLVED with the asset in
                      its resolution, so the graph stops asking.

        A failure never writes `chose:` — the recipe records that it was
        tried and did not work, which is what a later planner needs, and
        recording a defeat as a choice would make the store recommend
        the thing that already broke.
        """
        n = (need or "").strip().casefold()
        a = (asset or "").strip().casefold()
        if not n or not a:
            return json.dumps({"verdict": "UNKNOWN_NEED_OR_ASSET"})

        facets = ["tried:" + a, ("worked:" + a) if worked else ("failed:" + a)]
        if worked:
            facets.append("chose:" + a)
        store.add("recipe:" + n, facets, source="outcome:" + a)

        if command.strip():
            mark = ("verified:tool:" + a) if worked else ("refuted:tool:" + a)
            wf = [mark, "command:" + command.strip()[:120], "for:" + n]
            for line in (result or "").splitlines()[:4]:
                if line.strip():
                    wf.append("said:" + line.strip()[:80])
            store.add("run:" + a + ":" + command.strip()[:80], wf,
                      source="tool:" + a)
        _save()

        resolved = None
        if worked and gap_id.strip():
            try:
                gap_graph.set_status(gap_id.strip(), "RESOLVED",
                                     resolution="closed by " + a)
                _save_gap_graph()
                resolved = gap_id.strip()
            except Exception:
                resolved = None

        return json.dumps({"verdict": "ANSWER", "need": n, "asset": a,
                           "worked": worked, "gap_resolved": resolved,
                           "recipe": "recipe:" + n}, ensure_ascii=False)

    @mcp.tool()
    def vera_domain(name: str, path: str) -> str:
        """Register one document's vocabulary as a domain. Words, not facts.

        `ingest_documents` adds facts that vote. This adds words that only
        speak — one fillers table and one patterns table, while `frames`,
        the shared grammar, is never written. Grammar transfers and
        vocabulary does not (0.735–0.857 agreement on a shared verb's
        dominant case across an encyclopedia, the Civil Code, the Labour
        Standards Act and a two-page brief, against a 0.28 shuffled
        control), so a domain costs its nouns and nothing else.

        The tables are LAYERED in front of the shared ones, never merged:
        merging stores whose notion of agreement differs invented an
        out-of-corpus quorum of 0→8 and dropped answers 284→208, six times
        out of six.

        `name` must be [a-z0-9_] and is refused rather than rewritten,
        because it becomes a table name. Registration is gated on the data
        — a document yielding fewer than five verbs or five slots is
        refused, since a domain that composes nothing looks exactly like
        one that had nothing to say.
        """
        from .domain_ingest import read_document, register
        p = Path(path).expanduser()
        if not p.is_file():
            return json.dumps({"verdict": "UNKNOWN_FILE_NOT_FOUND",
                               "path": str(p)}, ensure_ascii=False)
        try:
            text = read_document(p)
        except Exception as exc:
            return json.dumps({"verdict": "UNKNOWN_UNREADABLE",
                               "path": str(p), "error": str(exc)[:120]},
                              ensure_ascii=False)
        return json.dumps(register((name or "").strip().lower(), text),
                          ensure_ascii=False)

    @mcp.tool()
    def vera_domain_text(name: str, text: str) -> str:
        """Register pasted text as a domain's vocabulary. Same gates.

        For text that arrived without a file — a paste wrapped in
        ⟨verantyx⟩ tags in the composer. It runs the identical registration
        as `vera_domain` so a paste cannot enter on easier terms than a
        document: same five-verb / five-slot floor, same refusal of a name
        outside [a-z0-9_], same untouched `frames`.
        """
        from .domain_ingest import register
        return json.dumps(register((name or "").strip().lower(), text or ""),
                          ensure_ascii=False)

    @mcp.tool()
    def vera_domains() -> str:
        """Which document vocabularies are registered, and what is shared.

        A domain costs its NOUNS, not its grammar. Measured across an
        encyclopedia, the Civil Code, the Labour Standards Act and a
        two-page brief, a shared verb's dominant case agrees 0.735–0.857
        against a 0.28 shuffled control, so `frames` is one thin map for
        everyone and only the fillers are per-domain.
        """
        from .domain_ingest import domains as _domains
        return json.dumps({"verdict": "ANSWER", "domains": _domains(),
                           "shared": ["frames", "patterns", "fillers"],
                           "note": "分野は重ねる。合体はしない"},
                          ensure_ascii=False)

    @mcp.tool()
    def vera_compose(verb: str, subject: str = "", target: str = "",
                     object_: str = "", domain: str = "",
                     domain_only: bool = False) -> str:
        """Build one clause for a verb from its observed frame. No model.

        Three tables and no generation model: `frames` says which cases
        the verb takes, `patterns` says which of them occurred TOGETHER,
        and `fillers` says which nouns were seen in each slot. The
        pattern chooses the shape; the fillers only fill it.

        Composing from the frame alone with a threshold is what produced
        「父がそれぞれ当該各号に父と期間を定める。」 — the mean pattern
        holds 1.22 cases while the mean frame holds 3.20, so a threshold
        over the frame invents about two arguments per sentence.

        Grammar transfers and vocabulary does not. Measured across
        encyclopedia, civil code and labour law, the dominant case of a
        shared verb agrees 0.735–0.857 of the time against a 0.28
        shuffled control — so frames and patterns are a thin shared map
        while fillers belong to whatever corpus was read. Swap the
        fillers and the same grammar speaks another domain.

        `subject` / `target` / `object_` pin the が / に / を slots when
        the caller knows them; a pinned case the pattern lacks is added,
        because a person asking for it outweighs the corpus's silence.

        Every draft is marked `constructed: True`. 「権利を有する」 being
        well-formed is not a claim that anyone holds a right — this door
        writes sentences, it does not testify. Refusals are typed:
        UNKNOWN_VERB_NOT_IN_FRAMES / UNKNOWN_NO_OBSERVED_PATTERN /
        UNKNOWN_SLOT_UNFILLED.

        `domain` layers a registered document's vocabulary in FRONT of the
        shared one — never merged with it. A verb the domain never used
        still resolves through the shared tables, and every draft names the
        layer each slot came from (`layer`: the domain / shared / mixed).

        `domain_only` refuses instead of falling through. Layering is right
        for reach and wrong when a reader will take the sentence as the
        organisation's own: a firm asking about 担保 and getting an
        encyclopedia's sense of it is wrong in a way nothing on screen
        shows. Customising for an organisation means declining to leave
        their vocabulary, not editing the shared map — so this is the flag
        an enterprise deployment sets, and the refusal is
        UNKNOWN_NOT_IN_DOMAIN.
        """
        tables = _ComposeTables.indexed((domain or '').strip())
        if tables is None:
            return json.dumps({"verdict": "UNKNOWN_INDEX_ABSENT",
                               "note": "meaning_index.db が無い。"
                                       "tools/index_frames.py を先に走らせる"},
                              ensure_ascii=False)
        given = {k: v.strip() for k, v in
                 (("が", subject), ("に", target), ("を", object_)) if v.strip()}
        return json.dumps(_compose((verb or "").strip(), tables, given=given,
                                   domain_only=bool(domain_only)),
                          ensure_ascii=False)

    @mcp.tool()
    def observe(subject: str, passes: str = "", by: str = "",
                against: str = "", after: str = "", yielded: str = "",
                claim: str = "", items: str = "",
                items_closed: bool = False) -> str:
        """Place an observation on the six arms. This is not a gate.

        Anything a caller looked at — a window, a file, a command's
        stdout, a page — comes through here to become a cross instead of
        prose in a prompt. Prose in a prompt is where the 8/13 Teams run
        lost 「初めてのaijax」→"ajax" and where a 27B model loops: nothing
        in a paragraph can be asked whether it has support.

        The door never withholds and never adjudicates, because it does
        not need to. Facets are arm-tagged, so a role that was not
        established simply contributes nothing — an unsupported general
        claim is ABSENT from the store rather than present-and-flagged,
        and absence is what the existing arm verdicts already fire on.
        Adjudication stays where it already lives (`ArmIndex.gate`), at
        answer time, for observations and every other claim alike.

        Two ways in, and they compose:

            passes  {"pass name": "verbatim text", …} as JSON. Several
                    readings of one target. Agreement puts them on
                    support+; ANY disagreement puts every variant on
                    both support+ and support-, which is the contested
                    state the store already demotes. No majority wins
                    quietly and no tie empties the arm.
            roles   by / against / after / yielded / claim / items,
                    `|`-separated. Commas are not a separator here
                    because OCR text is full of them.

        `items_closed` is the one thing a caller must be honest about,
        and it is honest by default: having parts and having ALL the
        parts are different facts. While it is false the general claim
        is not placed at all — which is what an unread third tab, an
        unscrolled last row and a grep over half a repo all are.
        """
        subj = (subject or "").strip()
        if not subj:
            return json.dumps({"verdict": "UNKNOWN_SUBJECT_MISSING"})

        def _parts(s: str):
            return tuple(p.strip() for p in (s or "").split("|") if p.strip())

        read_by, read_against = _parts(by), _parts(against)
        if passes.strip():
            try:
                d = json.loads(passes)
            except Exception:
                return json.dumps({"verdict": "UNKNOWN_PASSES_NOT_JSON",
                                   "note": "passes must be a JSON object of "
                                           "pass name -> verbatim text"})
            if not isinstance(d, dict) or not d:
                return json.dumps({"verdict": "UNKNOWN_PASSES_NOT_OBJECT"})
            base = _obs_readings(subj, {str(k): str(v) for k, v in d.items()})
            # Explicit roles layer over the pass placement rather than
            # replacing it — 束ねず重ねる, on the smallest possible scale.
            read_by = base.by + read_by
            read_against = base.against + read_against

        obs = _Observation(
            subject=subj, by=read_by, against=read_against,
            after=(after or "").strip(), yielded=(yielded or "").strip(),
            claim=(claim or "").strip(), items=_parts(items),
            items_closed=bool(items_closed))

        rep = _obs_report(obs)
        placed = _obs_facets(obs)
        if placed:
            store.add("observed:" + subj, placed, source="observation")
            _save()

        return json.dumps({"verdict": "PLACED", "subject": subj,
                           "written": len(placed),
                           "filled": rep["filled"], "empty": rep["empty"],
                           "gap_verdicts": rep["gap_verdicts"],
                           "contested": rep["contested"],
                           "instances_open": rep["instances_open"]},
                          ensure_ascii=False)

    @mcp.tool()
    def assets_for(need: str) -> str:
        """Which assets on this machine could close a stated need.

        The plan side of the gap loop. A GapNode says what is missing;
        this says what is here that might close it, and it keeps the two
        kinds of answer apart on purpose:

            witnessed   a run already succeeded with this asset for this
                        kind of work (verified:tool:…). Repeatable.
            present     the asset exists. Nothing more is claimed — it
                        has never been tried for this, and calling it a
                        solution would be the model's belief about tools
                        entering as fact.

        The need→asset table is CLOSED, like the intent frames and the
        summon table, and for the same reason: a fuzzy match here would
        propose Blender for "run tests" with total confidence, and an
        agent acting on that wastes the user's machine and their trust.
        A need outside the table returns UNKNOWN_NEED_NOT_MAPPED with
        the mapped needs listed — a refusal that says how to ask again.
        """
        table = {
            "編集": ["code", "vscode", "visual studio code", "xcode", "vim",
                     "nova", "sublime text"],
            "実行": ["terminal", "iterm", "node", "npm", "python3", "swift",
                     "cargo", "docker"],
            "確認": ["safari", "google chrome", "firefox", "preview"],
            "検索": ["safari", "google chrome"],
            "版管理": ["git", "github desktop", "sourcetree", "fork"],
            "設計": ["figma", "sketch", "blender"],
            "文書": ["notes", "pages", "textedit", "typora"],
            "表計算": ["numbers", "microsoft excel"],
            "ビルド": ["xcodebuild", "swift", "npm", "cargo", "docker"],
        }
        aliases = {"edit": "編集", "run": "実行", "test": "実行",
                   "browse": "確認", "verify": "確認", "build": "ビルド",
                   "git": "版管理", "design": "設計", "write": "文書"}
        key = (need or "").strip().casefold()
        key = aliases.get(key, key)
        wanted = table.get(key)
        if wanted is None:
            for k in table:
                if k in (need or ""):
                    wanted, key = table[k], k
                    break
        if wanted is None:
            return json.dumps({"verdict": "UNKNOWN_NEED_NOT_MAPPED",
                               "need": need, "mapped": sorted(table),
                               "note": "closed table; a guess here would "
                                       "send an agent at the wrong app"},
                              ensure_ascii=False)

        # The remembered choice comes first. If a run already closed a
        # need with an asset, the second time is a lookup, not another
        # exploration — and assets that were tried and failed are named
        # so the planner does not walk into them again.
        chosen, failed = [], []
        for f in (store.crosses.get("recipe:" + key) or {}):
            t = str(f)
            if t.startswith("chose:"):
                chosen.append(t[6:])
            elif t.startswith("failed:"):
                failed.append(t[7:])

        witnessed, present = [], []
        for core, cross in store.crosses.items():
            facets = set(cross)
            if core.startswith("run:"):
                tool = core.split(":", 2)[1] if ":" in core else ""
                if tool in wanted and any(
                        str(f).startswith("verified:tool:") for f in facets):
                    witnessed.append({"asset": tool, "run": core})
                continue
            if not (core.startswith("app:") or core.startswith("cli:")):
                continue
            name = core.split(":", 1)[1]
            if name in wanted and "present:true" in facets:
                path = next((str(f)[5:] for f in facets
                             if str(f).startswith("path:")), "")
                present.append({"asset": name, "path": path})

        return json.dumps({
            "verdict": "ANSWER" if (chosen or witnessed or present)
                       else "UNKNOWN_NO_ASSET",
            "need": key,
            "chosen": chosen[:3],
            "failed_before": failed[:4],
            "witnessed": witnessed[:6],
            "present_untried": present[:8],
            "note": "witnessed = a run vouched for it; present = it "
                    "exists and nothing more is claimed",
        }, ensure_ascii=False)

    @mcp.tool()
    def survey_assets(extra_paths: str = "") -> str:
        """What this machine actually has — presence only, never ability.

        The exploring agent needs an inventory before it can ask "if I
        cannot do this here, what on this computer can". This builds it
        by looking, and it stores exactly one kind of claim:

            present:true / path:… / kind:app|cli

        and nothing about what any of them CAN DO. That line is the
        whole discipline. That `/Applications/Visual Studio Code.app`
        exists is a fact anyone can check by looking. That VS Code can
        edit code is a CLAIM — true, obvious, and still not something
        this store may hold until a run witnesses it, because the moment
        a model's general knowledge about tools is written in as fact,
        the store stops being able to tell what it verified from what it
        assumed, and that distinction is the only thing it sells.

        Ability arrives later and separately, through
        `record_tool_witness`, as `verified:tool:<name>` — earned by a
        run that happened on this machine. So an answer can always say
        which half it is standing on: 「あります」 from here, 「効きま
        した」 only from there.
        """
        import os
        import shutil

        # Three tiers, and they are never collapsed:
        #   present:   it exists — a fact anyone can check by looking
        #   declares:  the app's OWN bundle says it opens these types.
        #              Still not a run, but not a model's belief either:
        #              the claim is the vendor's, recorded as theirs.
        #   verified:  a run happened (record_tool_witness). Earned.
        import plistlib

        before = {c for c in store.crosses
                  if c.startswith("app:") or c.startswith("cli:")}
        found = 0
        for base in ("/Applications", "/System/Applications",
                     str(Path.home() / "Applications")):
            try:
                names = sorted(os.listdir(base))
            except OSError:
                continue
            for name in names:
                if not name.endswith(".app"):
                    continue
                label = name[:-4]
                full = os.path.join(base, name)
                facets = ["present:true", "kind:app",
                          "path:" + full, "name:" + label]
                # What the app declares about itself, read from its own
                # Info.plist. A declared document type is the vendor's
                # claim, kept as the vendor's — it tells the planner
                # which candidates are worth a first run without
                # pretending the run already happened.
                try:
                    with open(os.path.join(full, "Contents", "Info.plist"),
                              "rb") as fh:
                        info = plistlib.load(fh)
                    seen = set()
                    for doc in (info.get("CFBundleDocumentTypes") or [])[:12]:
                        for ext in (doc.get("CFBundleTypeExtensions") or [])[:6]:
                            e = str(ext).strip().lower()
                            if e and e != "*" and e not in seen:
                                seen.add(e)
                                facets.append("declares:doctype:" + e)
                    for url in (info.get("CFBundleURLTypes") or [])[:4]:
                        for sch in (url.get("CFBundleURLSchemes") or [])[:3]:
                            facets.append("declares:scheme:" + str(sch).lower())
                except Exception:
                    pass
                store.add("app:" + label.casefold(), facets,
                          source="survey:applications")
                found += 1

        clis = ["git", "node", "npm", "python3", "swift", "xcodebuild",
                "code", "cargo", "docker", "ffmpeg", "curl", "brew",
                "ollama", "lake", "lean"]
        for extra in (extra_paths or "").split():
            if extra and extra not in clis:
                clis.append(extra)
        for c in clis:
            where = shutil.which(c)
            if not where:
                continue
            store.add("cli:" + c,
                      ["present:true", "kind:cli", "path:" + where,
                       "name:" + c],
                      source="survey:path")
            found += 1

        # A change in the machine is a change in what Vera can reach, so
        # it opens gaps rather than passing silently. An arrival is an
        # untried capability; a departure invalidates anything that was
        # witnessed through it, which is the more urgent of the two
        # because a stored procedure now points at nothing.
        after = {c for c in store.crosses
                 if c.startswith("app:") or c.startswith("cli:")}
        opened = []
        for core in sorted(after - before):
            g = gap_graph.create(
                "ASSET_ARRIVED", core, "machine:assets", "OPTIONAL",
                acquisition_methods=["record_tool_witness"],
                required_for=["SELECT_ACTION"])
            opened.append({"gap": g.gap_id, "kind": "arrived", "asset": core})
        for core in sorted(before - after):
            g = gap_graph.create(
                "ASSET_GONE", core, "machine:assets", "QUALITY",
                required_for=["SELECT_ACTION"])
            opened.append({"gap": g.gap_id, "kind": "gone", "asset": core})
        if opened:
            _save_gap_graph()

        _save()
        return json.dumps({
            "verdict": "ANSWER", "recorded": found,
            "gaps_opened": opened[:12],
            "holds": "presence and the vendor's own declarations",
            "note": "ability is not stored here; a run must witness it "
                    "via record_tool_witness",
        }, ensure_ascii=False)

    @mcp.tool()
    def record_tool_witness(tool: str, command: str, result: str,
                            passed: bool = True, version: str = "") -> str:
        """An external tool's run, kept as a witness — not as a log line.

        This is what makes using another app different from launching
        it. `npm test` passing is not Vera's opinion and not the model's
        recollection: it is a run that happened, on this machine, with
        an exit state, and it belongs in the store the same way a Lean
        kernel run does. The facet is `verified:tool:<tool>[:<version>]`
        and it names the command, so a later answer can cite WHICH run
        vouched for it and a reader can re-run the same line.

        A failing run is recorded too, as `refuted:tool:<tool>`. Keeping
        only the passes would make the store a highlight reel — the
        exact shape of dishonesty this engine exists to refuse — and the
        failures are the more useful half, because they are what a gap
        is made of.

        Nothing here is a claim about the WORLD. It is a claim about a
        run: the tool said this, at this time, on this command. Whether
        the tool was right is the tool's business, and the citation
        makes that visible instead of laundering it into fact."""
        t = (tool or "").strip().casefold()
        if not t:
            return json.dumps({"verdict": "UNKNOWN_NO_TOOL"})
        core = "run:" + t + ":" + (command or "").strip()[:80]
        mark = ("verified:tool:" + t + (":" + version if version else "")
                if passed else "refuted:tool:" + t)
        facets = [mark, "command:" + (command or "").strip()[:120]]
        for line in (result or "").splitlines()[:6]:
            line = line.strip()
            if line:
                facets.append("said:" + line[:80])
        store.add(core, facets, source="tool:" + t)
        _save()
        return json.dumps({"verdict": "ANSWER", "core": core,
                           "witness": mark,
                           "kept": len(facets)}, ensure_ascii=False)

    @mcp.tool()
    def memory_ledger(limit: int = 12) -> str:
        """The memory as a LEDGER a person can read and act on.

        `recall` answers about one core; this lists what is actually
        held, newest-heaviest first, so a reader can see memory
        accumulate and act on individual entries. Each row carries its
        review state, because the state is the point: a fact the store
        ingested and a fact a person has checked are different kinds of
        thing, and merging them would lose the only distinction that
        makes an approval mean anything.

            証言           ingested, not yet reviewed by a person
            ユーザーの校正  a person approved or edited it — the label
                           that rides with it when an agent reads it

        Review state lives in a sidecar keyed by core, never inside the
        cross itself: a person's approval is not testimony the corpus
        gave, and writing it into the facets would forge exactly the
        kind of evidence this engine exists to refuse."""
        rows = []
        marks = _review_marks()
        for core in list(store.crosses)[-max(1, limit) * 3:]:
            facets = store.top_facets(core, 4)
            if not facets:
                continue
            rows.append({
                "core": core,
                "facets": [f for f, _ in facets] if facets and
                          isinstance(facets[0], (list, tuple)) else facets,
                "state": marks.get(core, "証言"),
            })
        rows.reverse()
        return json.dumps({"verdict": "ANSWER", "held": len(store.crosses),
                           "rows": rows[:limit]}, ensure_ascii=False)

    @mcp.tool()
    def memory_review(core: str, state: str = "ユーザーの校正",
                      text: str = "") -> str:
        """Mark a memory as reviewed by a person, or edit it.

        `state` is the label an agent will see. `text` (optional) adds
        the corrected sentence as new testimony under the same core —
        an edit is an addition with provenance, never a silent rewrite
        of what was already stored, because a memory that changes with
        no trace is the same shape of lie as an invisible ingest."""
        key = core.casefold().strip()
        if not key:
            return json.dumps({"verdict": "UNKNOWN_NO_CORE"})
        marks = _review_marks()
        marks[key] = state
        _write_review_marks(marks)
        added = None
        if text.strip():
            added = store.ingest_sentence(text.strip())
            _save()
        return json.dumps({"verdict": "ANSWER", "core": key,
                           "state": state, "added": added},
                          ensure_ascii=False)

    @mcp.tool()
    def record_code_change(file_path: str, description: str) -> str:
        """Record a code change (file path + what changed) as a structured
        fact — NOT run through sentence-splitting quarantine, unlike
        propose_ai_facts. This exists because AiFactQuarantine's sentence
        splitter (split on '.', '!', '?') mangles diff/patch syntax (e.g.
        splits mid-diff at every '.py' or decimal number). A file having
        been written/edited is an already-executed, verifiable action —
        not an unverified claim — so it goes straight into the store under
        a dedicated core, distinct from the trusted natural-language facts
        `remember` accumulates."""
        key = f"code_change:{file_path}".casefold()
        store.add(key, ["changed", f"desc:{description[:300]}"])
        _save()
        return json.dumps({"recorded": key}, ensure_ascii=False)

    @mcp.tool()
    def record_verified_url(name: str, url: str) -> str:
        """Register a human- or agent-confirmed URL for a named destination
        (e.g. name="Gemini", url="https://gemini.google.com/"). Stored
        directly as a facet, NOT run through the sentence-splitting
        quarantine `remember`/`propose_ai_facts` use — a URL's periods
        would get mangled the same way `record_code_change`'s docstring
        describes for diffs. Pair with `lookup_verified_url`, which reads
        it back deterministically (no consensus threshold), so an agent
        can check for a known-good URL before guessing one from its own
        training data."""
        key = f"verified_url:{name.strip().casefold()}"
        store.add(key, [f"url:{url.strip()}"])
        _save()
        return json.dumps({"recorded": key, "url": url.strip()}, ensure_ascii=False)

    @mcp.tool()
    def lookup_verified_url(name: str) -> str:
        """Deterministic lookup for a URL registered via
        `record_verified_url` -- bypasses `ask`'s consensus/agreement
        threshold entirely (a single registration is enough), so this
        never spuriously returns UNKNOWN just because there's only one
        piece of evidence. Returns {"verdict": "ANSWER", "url": ...} or
        {"verdict": "UNKNOWN_NO_EVIDENCE"}."""
        key = f"verified_url:{name.strip().casefold()}"
        if not store.has(key):
            return json.dumps({"verdict": "UNKNOWN_NO_EVIDENCE", "name": name}, ensure_ascii=False)
        facets = store.top_facets(key, 1)
        for facet, _ in facets:
            if facet.startswith("url:"):
                return json.dumps({"verdict": "ANSWER", "name": name, "url": facet[len("url:"):]}, ensure_ascii=False)
        return json.dumps({"verdict": "UNKNOWN_NO_EVIDENCE", "name": name}, ensure_ascii=False)

    @mcp.tool()
    def record_verified_ui_element(app: str, element: str, x: float, y: float, version: str = "") -> str:
        """Register a confirmed UI element location within `app`'s window,
        as (x, y) normalized to 0-1000 relative to the window's own bounds
        (matching HiddenWindowAutomation/DesktopVisionBridge's coordinate
        convention) -- so a repeat operation can click it directly instead
        of re-running screenshot + vision analysis every time. Same
        not-sentence-split reasoning as `record_verified_url`.

        `version` (optional) is the app's bundle/build version at
        registration time. A registration REPLACES any prior coord/version
        for this exact (app, element) rather than accumulating alongside
        it -- an element's location is current-state, not a frequency-
        weighted fact, so `top_facets` must never return a stale coord
        just because it was registered more times than a corrected one.
        The caller (Verantyx) compares this stored version against the
        app's current version on lookup to decide whether a cached
        location needs re-verification."""
        key = f"ui_element:{app.strip().casefold()}:{element.strip().casefold()}"
        if key in store.crosses:
            store.crosses[key] = {
                f: c for f, c in store.crosses[key].items()
                if not (f.startswith("coord:") or f.startswith("version:"))
            }
        facets = [f"coord:{x},{y}"]
        if version.strip():
            facets.append(f"version:{version.strip()}")
        store.add(key, facets)
        _save()
        return json.dumps({"recorded": key, "x": x, "y": y, "version": version.strip()}, ensure_ascii=False)

    @mcp.tool()
    def lookup_verified_ui_element(app: str, element: str) -> str:
        """Deterministic lookup for a UI element registered via
        `record_verified_ui_element`. Returns {"verdict": "ANSWER", "x":
        ..., "y": ..., "version": ...} (version is "" if none was
        recorded) or {"verdict": "UNKNOWN_NO_EVIDENCE"}."""
        key = f"ui_element:{app.strip().casefold()}:{element.strip().casefold()}"
        if not store.has(key):
            return json.dumps({"verdict": "UNKNOWN_NO_EVIDENCE", "app": app, "element": element}, ensure_ascii=False)
        x = y = None
        version = ""
        for facet, _ in store.top_facets(key, 8):
            if facet.startswith("coord:"):
                x_str, y_str = facet[len("coord:"):].split(",", 1)
                x, y = float(x_str), float(y_str)
            elif facet.startswith("version:"):
                version = facet[len("version:"):]
        if x is None:
            return json.dumps({"verdict": "UNKNOWN_NO_EVIDENCE", "app": app, "element": element}, ensure_ascii=False)
        return json.dumps(
            {"verdict": "ANSWER", "app": app, "element": element, "x": x, "y": y, "version": version},
            ensure_ascii=False,
        )

    @mcp.tool()
    def list_verified_ui_elements(app: str) -> str:
        """Lists every UI element registered for `app` via
        `record_verified_ui_element` -- used by a re-verification pass to
        know what to re-check for a given app, without needing the caller
        to already know each element's name. Each entry includes the
        version recorded at registration time (if any)."""
        prefix = f"ui_element:{app.strip().casefold()}:"
        elements = []
        for key in store.crosses:
            if not key.startswith(prefix):
                continue
            name = key[len(prefix):]
            x = y = None
            version = ""
            for facet, _ in store.top_facets(key, 8):
                if facet.startswith("coord:"):
                    x_str, y_str = facet[len("coord:"):].split(",", 1)
                    x, y = float(x_str), float(y_str)
                elif facet.startswith("version:"):
                    version = facet[len("version:"):]
            if x is not None:
                elements.append({"element": name, "x": x, "y": y, "version": version})
        return json.dumps({"app": app, "elements": elements}, ensure_ascii=False)

    @mcp.tool()
    def forget(core: str) -> str:
        """Delete a core cross entirely. Deletion is real and immediate —
        unlike model weights, nothing lingers."""
        removed = []
        for key in (core.casefold(), core.casefold() + "#p"):
            if key in store.crosses:
                del store.crosses[key]
                store.core_count.pop(key, None)
                removed.append(key)
        _save()
        return json.dumps({"forgot": removed}, ensure_ascii=False)

    @mcp.tool()
    def recall(core: str, k: int = 8) -> str:
        """Recall the accumulated facets (with counts) for a core."""
        hits = {}
        for key in (core.casefold(), core.casefold() + "#p"):
            if store.has(key):
                hits[key] = store.top_facets(key, k)
        if not hits:
            return json.dumps({"verdict": "UNKNOWN_NO_EVIDENCE", "core": core})
        return json.dumps({"verdict": "ANSWER", "crosses": hits}, ensure_ascii=False)

    @mcp.tool()
    def math(query: str) -> str:
        """Exact wire arithmetic / typed equation solving (never approximate:
        ANSWER, AMBIGUOUS, or UNKNOWN_*)."""
        return json.dumps(math_ask(query), ensure_ascii=False)

    @mcp.tool()
    def code_ingest(repo_path: str) -> str:
        """Ingest a Python repo (AST): one cross per function with
        file/class/args/calls facets."""
        rep = ingest_python_repo(store, Path(repo_path))
        _save()
        return json.dumps(rep, ensure_ascii=False)

    @mcp.tool()
    def code_query(query: str) -> str:
        """Code reasoning: 'who calls X' | 'what does X call' | 'impact of X'."""
        return json.dumps(code_ask(store, query), ensure_ascii=False)

    @mcp.tool()
    def stats() -> str:
        """Store statistics (cores, facet links, sentences ingested)."""
        return json.dumps(store.report(), ensure_ascii=False)

    from .covenant import Covenant as _Covenant, Register as _Register, collapse as _collapse
    _cov_path = path.with_name(path.stem + ".covenants.json")
    _register = _Register.load(_cov_path)

    @mcp.tool()
    def set_covenant(name: str, requires: str = "", forbids: str = "",
                     topic: str = "", quote: str = "", turn: int = -1) -> str:
        """Register something the user settled, so a later reply can be
        checked against it. Comma-separated lists.

        `topic` scopes it — the terms that put a reply in range. Leave it
        empty only for a rule that really is always on: a covenant with no
        scope fires on replies that were never about it, and a guard that
        cries every turn gets switched off.

        `quote` is what gets proposed for re-injection, so put the user's
        own sentence there rather than a paraphrase of it."""
        c = _Covenant(
            name=name,
            requires=[x.strip() for x in requires.split(",") if x.strip()],
            forbids=[x.strip() for x in forbids.split(",") if x.strip()],
            topic=[x.strip() for x in topic.split(",") if x.strip()],
            said_at_turn=turn, quote=quote or name)
        _register.add(c)
        _register.save(_cov_path)
        return json.dumps({"verdict": "ANSWER", "covenant": c.as_dict(),
                           "in_force": len(_register.covenants)},
                          ensure_ascii=False)

    @mcp.tool()
    def list_covenants() -> str:
        """Every covenant in force, with the turn it came from."""
        return json.dumps([c.as_dict() for c in _register.covenants],
                          ensure_ascii=False)

    @mcp.tool()
    def propose_covenant(name: str, requires: str = "", forbids: str = "",
                         topic: str = "", quote: str = "",
                         turn: int = -1) -> str:
        """Put a covenant CANDIDATE in quarantine. Meant for the LLM-handoff
        path: closed extraction rules cannot read paraphrase (「絵文字は
        控えめに」), and extending regexes never closes that gap (measured:
        645/661 negations fell outside a 39-word vocabulary). So the model
        may PROPOSE what it read; Vera shadow-checks the candidate on every
        reply — violations appear as shadow_violations, never in the
        verdict, and never block. adopt_covenant is the gate into
        enforcement. Selection is a gate, not a merge."""
        c = _Covenant(
            name=name,
            requires=[x.strip() for x in requires.split(",") if x.strip()],
            forbids=[x.strip() for x in forbids.split(",") if x.strip()],
            topic=[x.strip() for x in topic.split(",") if x.strip()],
            said_at_turn=turn, quote=quote or name)
        if not (c.forbids or c.requires):
            return json.dumps({"verdict": "UNKNOWN_EMPTY_CANDIDATE"},
                              ensure_ascii=False)
        _register.propose(c)
        _register.save(_cov_path)
        return json.dumps({"verdict": "ANSWER", "candidate": c.as_dict()},
                          ensure_ascii=False)

    @mcp.tool()
    def adopt_covenant(name: str, infer: bool = False) -> str:
        """Adopt a quarantined candidate into enforcement — the gate.
        With infer=True the store is read ONCE, here, and the siblings of
        each listed term are baked in as inferred_forbids (the prohibition
        nobody wrote: TypeScriptを使う catches JavaScript because the same
        cores hold both). check() then reports inferred hits under their
        own weaker type, at literal-match speed."""
        from .covenant import bake_inferred as _bake

        d = _register.adopt(name)
        if d is None:
            return json.dumps({"verdict": "UNKNOWN_NO_SUCH_CANDIDATE",
                               "name": name}, ensure_ascii=False)
        out = {"verdict": "ANSWER", "adopted": d}
        if infer:
            c = next(x for x in _register.covenants if x.name == name)
            out["inference"] = _bake(c, store, store_name=path.name)
            out["adopted"] = c.as_dict()
        _register.save(_cov_path)
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def review_candidates(min_checks: int = 8,
                          max_fire_rate: float = 0.5) -> str:
        """Which quarantined candidates have earned adoption — a
        RECOMMENDATION, never an adoption. Auto-adopting is the trap the
        field named (an over-firing guard gets switched off), so the gate
        stays with the caller. Criteria are pre-registered (PREREG3): under
        min_checks in-scope checks abstains with UNKNOWN_TOO_FEW_CHECKS and
        reports no rate; never fired is REFUSED_NEVER_FIRED (no evidence it
        is needed); above max_fire_rate is REFUSED_OVERFIRING."""
        return json.dumps(_register.promotion_review(
            min_checks=min_checks, max_fire_rate=max_fire_rate),
            ensure_ascii=False)

    @mcp.tool()
    def rebake_inference(dry_run: bool = False) -> str:
        """Re-read the store ONCE and refresh baked inferred_forbids,
        reporting what was added and what dropped. Inference is the
        corpus's suggestion, not the user's words, so a term the store no
        longer supports is dropped rather than kept. Covenants that were
        never baked stay unbaked — the caller chose that. Staleness itself
        is answered by stat alone (see the guard CLI's `stale`), because
        check must never read the store: that is the 0.04s fast path the
        hooks depend on."""
        from .covenant import _store_fingerprint  # noqa: F401

        out = _register.rebake(store, store_path=path, dry_run=dry_run)
        if not dry_run and out.get("verdict") == "ANSWER":
            _register.save(_cov_path)
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def audit_required(  # noqa: D401 — the ledger speaks
    ) -> str:
        """Required-side audit by WITNESS, not by wording. 「必ずテストを
        実行して」 cannot be enforced by reading the reply — the field
        deployment measured required_missing as mostly false positives.
        The ground for 'it was done' is the tool-execution record
        (same line as attest_claim's CLAIM_UNWITNESSED). Advisory only:
        whether this turn NEEDED the execution is context this layer
        cannot see, so it reports and never blocks. Two distinctions the
        substring era lacked: `echo pytest` is MENTIONED, not INVOKED, and
        only INVOKED counts; and a run that exited non-zero is
        REQUIRED_FAILED, which is different news from never having run.
        An execution with no exit status recorded is
        REQUIRED_WITNESSED_UNVERIFIED — absence is not denial."""
        return json.dumps(_register.audit(), ensure_ascii=False)

    @mcp.tool()
    def retire_covenant(name: str, quote: str = "", turn: int = -1) -> str:
        """Retire a covenant — not delete it. 「もう絵文字使っていいよ」
        releases the rule from check/fading, but what was promised, and
        when and with what words it was released, stays in the ledger:
        erasing it would make the audit lie. Found as a named limitation
        of the first field deployment (2026-08-21): covenants survived
        restarts but could never be taken back."""
        r = _register.retire(name, quote=quote, turn=turn)
        if r is None:
            return json.dumps({"verdict": "UNKNOWN_NO_SUCH_COVENANT",
                               "name": name}, ensure_ascii=False)
        _register.save(_cov_path)
        return json.dumps({"verdict": "ANSWER", "retired": r},
                          ensure_ascii=False)

    @mcp.tool()
    def extract_covenants(text: str, turn: int = -1) -> str:
        """Instruction text → covenant CANDIDATES, by closed surface rules
        (ja: 〜を使わないで / 必ず〜して; en: never use X / always run X).
        A sentence the rules cannot read yields nothing — no guessing,
        because putting an LLM here would hand the drifting device the job
        of writing its own leash.

        These candidates carry origin="regex" and belong in
        propose_covenant, NOT set_covenant. Measured 2026-08-21 over 20
        instructions people actually write: 3 read correctly, 13 yielded
        nothing, and 4 caught the wrong word — `No new dependencies` became
        forbids=["new"] and blocked the reply "I added a new helper
        function." Adding regexes does not close that gap (645/661
        negations fall outside the vocabulary), so what changed is
        enforcement: a rule a regex read is shadow-checked only, and
        adopt_covenant remains the gate."""
        from .covenant import extract_covenants as _extract

        return json.dumps({"candidates": _extract(text, turn=turn)},
                          ensure_ascii=False)

    @mcp.tool()
    def check_reply(reply: str, asked: str = "") -> str:
        """Does this reply still honour what the user settled?

        Pass `asked` — the question that prompted the reply — because scope
        is the EXCHANGE, not the reply's wording. A rule about the
        implementation language did not fire on the reply 「Python。」 until
        the question was checked too: one word, on topic, naming no scope
        term.

        Returns KEPT or BROKEN with, per violation, the missing requirement,
        the forbidden term used, and the exact sentence to re-inject. It is
        a PROPOSAL: the user may have changed the rule one turn ago and this
        cannot see intent, only text."""
        return json.dumps(_register.check(reply, asked=asked, store=store),
                          ensure_ascii=False)

    @mcp.tool()
    def fading_covenants(window: int = 5) -> str:
        """Which rules have STARTED being broken — the only ones worth
        re-injecting.

        Re-sending every rule every turn is what a system prompt already
        does, and long sessions drift anyway: a rule the model has seen a
        hundred times has stopped carrying information. A rule kept for
        twenty turns and broken twice just now has not.

        Each covenant is compared against ITS OWN history, never against the
        others. A hard rule that was always half-kept is not degrading; one
        broken from the very first check was never understood and needs
        rewriting rather than repeating — it is reported as stable, which is
        the honest reading, not a pass."""
        return json.dumps(_register.fading(window=window), ensure_ascii=False)

    @mcp.tool()
    def check_context_drift(reply: str) -> str:
        """Is the reply about something this conversation already settled,
        while using none of what was settled?

        The linkage test `attest_claim` uses, with the CONVERSATION as the
        corpus. Catches the quiet failure a sliding window produces: the
        model reverts to generic knowledge about a subject the user already
        pinned down, and nothing anywhere says so. Every layer is consulted,
        frozen ones included — that is why overflow freezes instead of
        dropping.

        Returns the turns to re-inject VERBATIM. Rebuilding a sentence from
        the store's facets produced 「プロジェクト: 使い」; the ingest keeps
        what a fact is about, not how it was put."""
        return json.dumps(_collapse(_conversation, reply), ensure_ascii=False)

    _vera_cache: Dict[str, Any] = {}
    _math_cache: Dict[str, Any] = {}

    def _vera() -> Any:
        """The full stack, loaded the way the 3D viewer loads it.

        Published sqlite first, pickle fallback — the published path is
        the only one that carries the sidecars (edges, origin, gaps), so
        loading the pickle here silently disarmed every organ that needs
        an edge licence. One loader, same as `serve_view3d.load`, so the
        MCP tools and the picture cannot answer from different builds.
        """
        if "v" not in _vera_cache:
            import os

            from .export_sqlite import vera as load_published
            from .vera import load as load_vera

            root = corpus_root()
            # VERA_PUBLISHED_DB lets a host pin WHICH stamped release
            # answers (the IDE's model picker sets it and restarts this
            # process). Sidecars are discovered beside the db by
            # filename, so a version directory carries its whole world.
            env_db = os.environ.get("VERA_PUBLISHED_DB", "")
            db = Path(env_db) if env_db else root / "build" / "vera.db"
            _vera_cache["v"] = (load_published(db) if db.exists()
                                else load_vera(root))
        return _vera_cache["v"]

    def _atlas() -> Dict[str, Any]:
        """The coverage shelves: the federation's witnesses plus the
        shallow jawiki shelf when it has been built.

        Atlas and witness only, never census — the pre-registered
        placement clause (docs/PREREGISTERED_2026-08-14_tree_and_shelf
        .md) is unchangeable, and this helper is the only door the
        shelf enters through. Measured on 200 stride probes: the shelf
        took the hole rate from 74.5% to 45.5%.
        """
        shelves = dict(_vera().witnesses)
        if "浅層wiki" not in _vera_cache:
            from .cross_store import CrossStore

            p = (corpus_root() / "build"
                 / "jawiki_shallow.json")
            _vera_cache["浅層wiki"] = (CrossStore.load(p) if p.exists()
                                       else None)
        if _vera_cache["浅層wiki"] is not None:
            shelves["浅層wiki"] = _vera_cache["浅層wiki"]
        return shelves

    def _aliases() -> Dict[str, str]:
        """The redirect sidecar (alias -> canonical title), when built.

        Lookup material only: an alias never becomes a core and never
        votes; it lets the atlas say 「この語は正題Xの別名で、Xなら棚が
        持つ」 with the hop named in the signal."""
        if "別名" not in _vera_cache:
            p = (corpus_root() / "build"
                 / "jawiki_aliases.json")
            try:
                _vera_cache["別名"] = (json.loads(p.read_text(encoding="utf-8"))
                                       if p.exists() else {})
            except Exception:
                _vera_cache["別名"] = {}
        return _vera_cache["別名"]

    @mcp.tool()
    def vera_ask(query: str, sentences: int = 3) -> str:
        """Ask the full stack: language, staircase, inference core, reach.

        The same entry the 3D viewer uses, so the picture and the tools
        cannot answer differently — a reader watching a query resolve is
        watching the thing that resolved it.

        Layered in the order the measurements put them. Language routes
        first, because mixing two in one store answered superconductivity
        with contract. A time deictic is settled before any lookup, because
        「今日の天気は」 has no answer in a store with no clock. The
        staircase seeds the core when the core cannot enter on the question
        as asked — 0 of 200 such questions answered before, 185 after. When
        nothing is held, the term is split into units the corpus attests
        (10.4% facet overlap) before falling back on a longer word that
        contains it (4.5%), and the two are reported apart.

        Every answer says how it was reached: ANSWER entered directly,
        SEEDED needed the staircase to name the subject, UNITS and
        CONTAINMENT landed near a word the store never held. The path is the
        citation; any sentence is a draft."""
        return json.dumps(_vera().ask(query, limit=sentences),
                          ensure_ascii=False, default=str)

    # ── The harness: the ENGINE owns the loop, not the model ─────────
    #
    # Measured, and the reason this exists: a 27B model handed the loop
    # produced forty paragraphs and no tool call. A tool list pasted into
    # a prompt asks the model to be the scheduler, and a weak model cannot
    # be one. So the schedule moves here — `intent_chain.Circulation`
    # decides what runs next, and the model is asked for language at named
    # points instead of being asked what to do.
    #
    # 1,143 lines of this machinery existed with no door at all, which
    # meant no caller could reach it. These five give it one.
    _circulations: Dict[str, Any] = {}

    def _circ_id(instruction: str) -> str:
        import hashlib
        return hashlib.sha256(
            instruction.strip().encode("utf-8")).hexdigest()[:16]

    @mcp.tool()
    def harness_begin(instruction: str, budget: int = 8) -> str:
        """Start a run. The engine reads the instruction and owns the loop.

        The instruction is framed by `vera_intent` first: it becomes an op
        the frame table covers, or it is refused as UNKNOWN_INTENT. A
        guessed intent is worse than a refused one — the whole point of
        moving the schedule here is that nothing downstream is built on a
        reading nobody vouched for.

        Returns the run id, the chain of stages, and the first stage. The
        id is a hash of the instruction, so the same instruction resumes
        the same run rather than starting a parallel one."""
        from .intent_chain import Circulation
        from .intent_frames import parse as _parse

        parsed = _parse(instruction)
        if parsed.get("verdict") != "INTENT":
            return json.dumps(
                {"verdict": parsed.get("verdict", "UNKNOWN_INTENT"),
                 "instruction": instruction,
                 "note": "枠表が覆っていない。推測した意図で段を組むことはしない"},
                ensure_ascii=False, default=str)
        rid = _circ_id(instruction)
        circ = Circulation(parsed, budget=budget)
        _circulations[rid] = circ
        nxt = circ.next_stage()
        return json.dumps(
            {"verdict": "RUNNING", "run": rid, "op": parsed.get("op"),
             "status": circ.status(), "state": circ.state(),
             "next": None if nxt is None else {
                 "n": nxt.n, "op": nxt.op, "args": nxt.args,
                 "cause_in": nxt.cause_in}},
            ensure_ascii=False, default=str)

    @mcp.tool()
    def harness_next(run: str) -> str:
        """What the engine wants done next. The model does not choose.

        An empty result never becomes the next stage's precondition —
        `cause_in` has to be satisfied by something actually observed, so
        a run stalls honestly instead of proceeding on nothing."""
        circ = _circulations.get(run)
        if circ is None:
            return json.dumps({"verdict": "UNKNOWN_RUN", "run": run},
                              ensure_ascii=False)
        nxt = circ.next_stage()
        return json.dumps(
            {"verdict": circ.status(), "run": run,
             "next": None if nxt is None else {
                 "n": nxt.n, "op": nxt.op, "args": nxt.args,
                 "cause_in": nxt.cause_in},
             "state": circ.state()},
            ensure_ascii=False, default=str)

    @mcp.tool()
    def harness_deliver(run: str, subject: str, passes: str = "",
                        by: str = "", against: str = "", after: str = "",
                        yielded: str = "", claim: str = "",
                        items: str = "", items_closed: bool = False) -> str:
        """Hand back what was actually seen. Progress is arms placed.

        Same shape as `observe`, because it is the same act: whatever a
        step looked at becomes a cross rather than prose in a prompt.
        Nothing in a paragraph can be asked whether it has support, which
        is how the 8/13 Teams run lost 「初めてのaijax」 to "ajax".

        A step that ran and saw nothing is delivered too. That is the
        record the run stalls on, and a stall with a named cause is the
        outcome this harness exists to produce instead of a loop."""
        from .observation import Observation
        circ = _circulations.get(run)
        if circ is None:
            return json.dumps({"verdict": "UNKNOWN_RUN", "run": run},
                              ensure_ascii=False)
        obs = Observation(
            subject=subject, by=by, against=against, after=after,
            yielded=yielded, claim=claim,
            items=[x for x in (items or "").split("\n") if x.strip()],
            items_closed=items_closed)
        out = circ.deliver(obs)
        return json.dumps(
            {"verdict": circ.status(), "run": run, "delivered": out,
             "state": circ.state()},
            ensure_ascii=False, default=str)

    @mcp.tool()
    def harness_ask_back(run: str, subject: str = "") -> str:
        """The run is underdetermined — the question to put to a PERSON.

        Not a prompt for the model. When the engine cannot settle
        something itself, the honest move is a typed question with the
        candidates it does hold, and the answer comes back marked
        `support+:human:` — testimony, never a measurement."""
        from .ask_back import from_circulation
        circ = _circulations.get(run)
        if circ is None:
            return json.dumps({"verdict": "UNKNOWN_RUN", "run": run},
                              ensure_ascii=False)
        q = from_circulation(circ, subject)
        if q is None:
            return json.dumps(
                {"verdict": "NOTHING_TO_ASK", "run": run,
                 "status": circ.status(),
                 "note": "この段は人に訊く形の未決ではない"},
                ensure_ascii=False, default=str)
        return json.dumps({"verdict": "ASK", "run": run, **q.as_dict()},
                          ensure_ascii=False, default=str)

    @mcp.tool()
    def harness_vary(procedure_json: str,
                     alternatives_json: str = "") -> str:
        """One success, several methods — by single change, for attribution.

        Every variant differs from the parent in exactly ONE step. That is
        not tidiness: if two things change and the variant fails, nothing
        was learned. The parent must already be VERIFIED or TRUSTED, so a
        procedure nobody has run cannot spawn ten more.

        Measured: a verified Teams route yielded 10 variants."""
        from .procedure_vary import Procedure, agenda, vary

        try:
            pd = json.loads(procedure_json)
            alts = json.loads(alternatives_json) if alternatives_json else None
        except ValueError as exc:
            return json.dumps({"verdict": "UNKNOWN_NOT_JSON",
                               "error": str(exc)[:120]}, ensure_ascii=False)
        parent = Procedure(**pd)
        return json.dumps(
            {"variants": [v.as_dict() for v in vary(parent, alts)],
             "agenda": agenda(parent, alts)},
            ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_fresh(query: str, sources_json: str) -> str:
        """検索で得た一般知識を、一時空間で引用し、毎回破棄する。

        第三の空間。店（連合）でも端末の文書でもない — 呼び出し元（IDE の
        検索実装）が取ってきた頁を、この関数の中だけに索引し、逐語引用で
        答え、関数と共に消える。**書き込み経路が存在しない**: 店にも
        文書側車にも会話空間にも一行も書かない。破棄は方針ではなく構造で、
        追試できる — 直後に同じ主題を vera_chat に聞けば ABSENT が返る。

        なぜ吸収しないか: 検索結果は出典つきの他人の文章であって、この
        端末の知識ではない。毎回取り直すから最新で、毎回捨てるから
        「いつの情報か分からない取り込み」が店を汚さない。二空間の
        不合流則がここでは時間方向に効いている。

        `sources_json` は [{"url":…, "title":…, "text":…}, …]。返答は
        逐語引用+出典URL。頁が主題を明記しないときは、支配する近傍の
        定めと「明記なし」の型（部分文字列検査で追試可能）。"""
        from .document_structure import (index as _dx, lookup as _dlook,
                                         rejoin as _rejoin, load as _dload)
        from .engine import _TOPIC_SUFFIXES

        try:
            sources = json.loads(sources_json or "[]")
        except Exception as e:
            return json.dumps({"verdict": "UNKNOWN_BAD_SOURCES",
                               "note": str(e)[:80]}, ensure_ascii=False)
        if not isinstance(sources, list) or not sources:
            return json.dumps({"verdict": "UNKNOWN_NO_SOURCES",
                               "note": "検索結果が渡されていない。この扉は自分では"
                                       "取得しない — 取得は呼び出し元の仕事"},
                              ensure_ascii=False)

        # 一時の本。ウェブ本文は番号見出しを持たないことが多いので、節が
        # 立たなければ本文全体を1節として行に展開する — 行が引用の最小単位。
        book: Dict[str, Any] = {"documents": []}
        for src in sources[:5]:
            text = str((src or {}).get("text") or "")[:20000]
            label = str((src or {}).get("url") or (src or {}).get("title") or "検索結果")
            if not text.strip():
                continue
            d = _dx(text, label)
            if not d.get("sections") and not d.get("labels"):
                lines = [ln for ln in _rejoin(text) if len(ln.strip()) >= 8][:200]
                d["sections"] = [{"heading": str((src or {}).get("title") or "本文"),
                                  "lines": lines, "ordinal": None}]
            book["documents"].append(d)
        if not book["documents"]:
            return json.dumps({"verdict": "UNKNOWN_EMPTY_SOURCES"}, ensure_ascii=False)

        subj = (query or "").strip()
        for suf in _TOPIC_SUFFIXES:
            if subj.endswith(suf) and len(subj) > len(suf):
                subj = subj[: -len(suf)]
                break
        r = _dlook(subj, book)
        out = {
            "verdict": r.get("verdict"),
            "reply": r.get("text") or "",
            "subject": r.get("subject"),
            "source": r.get("source"),
            "sources_offered": [str((s0 or {}).get("url") or (s0 or {}).get("title") or "?")
                                 for s0 in sources[:5]],
            "quoted": bool(r.get("quoted")),
            "discarded": True,
            "note": "一時知識。返答と同時に破棄済み — 店・文書・会話のどこにも残っていない",
        }
        # 比較のため、この端末が既に持つ文書側の答えも横に並べる。
        # 二空間の不合流則は守ったまま — 一つの verdict に混ぜず、
        # 読み手がその場で見比べられるよう別フィールドで返すだけ。
        # 文書側が既に答えを持つ主題でウェブへ聞き直した場合に、どちらが
        # 何を言っているかを読み手が自分で比較できる。
        try:
            doc_book = _dload(store_path)
            if doc_book.get("documents"):
                dr = _dlook(subj, doc_book)
                out["document_side"] = {
                    "verdict": dr.get("verdict"),
                    "text": dr.get("text") or "",
                    "source": dr.get("source"),
                    "quoted": bool(dr.get("quoted")),
                }
        except Exception:
            pass
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def vera_compare_spaces(topic: str) -> str:
        """この端末の文書と、公開連合（一般知識）が、同じ主題について何を
        言うかの差分。「この規程は一般的な考え方と比べて特殊か」の答えが
        立つ場所で、社内文書だけのモデルには構造的に作れない比較です。

        規律は structural_diff と同じ防御線に従う:
          ・語彙は「実測あり / 実測なし」のみ。否定文は組み立てない —
            「一般側に無い」は「一般ではそうでない」ではない
          ・両側の被覆数を必ず併記。薄い側が差分の信頼度を決める
          ・どちらかが3項目未満なら型付き棄権（どちらが薄いかを名指す）
          ・列挙は各束8件まで+数えた尻尾

        比較は合議ではない。二つの空間は今までどおり合流しない — 並べて
        読めるようにするだけで、票はどちらにも入らない。"""
        t = (topic or "").strip()
        if not t:
            return json.dumps({"verdict": "UNKNOWN_NO_SUBJECT"}, ensure_ascii=False)

        # 文書側: 個人ストアの facet + 構造側車の該当行
        doc_items: Dict[str, int] = {}
        cr = getattr(store, "crosses", {}).get(t)
        if cr:
            for f, n in cr.items():
                doc_items[f] = doc_items.get(f, 0) + int(n or 1)
        try:
            from .document_structure import load as _dl
            for doc in _dl(path).get("documents", []):
                for sec in doc.get("sections", []):
                    for ln in (sec.get("lines") or []):
                        if t in ln:
                            doc_items[ln[:48]] = doc_items.get(ln[:48], 0) + 1
        except Exception:
            pass

        # 一般側: 連合の facet
        base_items: Dict[str, int] = {}
        try:
            v = _vera()
            for lang in ("ja", "en"):
                st_ = getattr(v, "stores", {}).get(lang)
                c2 = getattr(st_, "crosses", {}).get(t) if st_ else None
                if c2:
                    for f, n in c2.items():
                        base_items[f] = base_items.get(f, 0) + int(n or 1)
        except Exception:
            pass

        nd, nb = len(doc_items), len(base_items)
        if nd < 3 or nb < 3:
            thin = []
            if nd < 3: thin.append("document")
            if nb < 3: thin.append("base")
            return json.dumps({
                "verdict": "INSUFFICIENT_PROFILE",
                "topic": t, "thin_side": thin,
                "coverage": {"document": nd, "base": nb},
                "note": "薄い側が差分の信頼度を決める。%s側の被覆が3未満 — "
                        "比較は基礎データ/文書の成長と共に立つ" % "・".join(thin),
            }, ensure_ascii=False)

        dset, bset = set(doc_items), set(base_items)
        cap = 8
        def bucket(keys, src):
            ks = sorted(keys, key=lambda k: (-src[k], k))
            return {"items": ks[:cap], "more": max(0, len(ks) - cap)}
        return json.dumps({
            "verdict": "SPACE_DIFF",
            "topic": t,
            "coverage": {"document": nd, "base": nb},
            "shared":    bucket(dset & bset, doc_items),
            "doc_only":  bucket(dset - bset, doc_items),
            "base_only": bucket(bset - dset, base_items),
            "note": "文書側に実測あり/一般側に実測なし、の対比のみ。可否や"
                    "優劣の判断はしていない。二空間は合流していない",
        }, ensure_ascii=False)

    # ── vera_chat: 会話そのものを扉にする ─────────────────────────────
    #
    # The IDE used to LOAD a model to hold a conversation, and used MCP only
    # for lookups. This door inverts that: the conversation lives HERE, the
    # client renders text, and no model exists on either side. MCP's
    # `sampling` capability — the server asking the client's LLM to generate
    # — is deliberately never invoked: the whole point of this engine is
    # that nothing needs to be sampled. A reply is composed, typed, and
    # sourced, or it is a typed refusal.
    #
    # State: the conversation is the SAME persistent one the other doors
    # read (`add_conversation_turn` / `check_context_drift`), so what is
    # said here is recallable there, and covenants set there bind replies
    # here. `last_core` rides per-server-process so 「その刑は」 resolves.
    # The conversation's terminal arrangements, per core. This is what makes
    # the chat door CIRCULATE instead of re-entering bare each turn: the
    # search resumes on each cross where the last turn's stable state left
    # it (rotation, widened view, locks). Kept OUTSIDE the store, like the
    # walker's trajectory — an arrangement is not knowledge, and a later
    # reader must not mistake footprints for facts. Persisted beside the
    # conversation so a restart resumes the same standing.
    _circ_path = path.with_name(path.stem + ".circulation.json")
    try:
        _circulation: Dict[str, Any] = json.loads(_circ_path.read_text("utf-8"))
    except Exception:
        _circulation = {}
    _chat_state: Dict[str, Any] = {"last_core": ""}

    @mcp.tool()
    def vera_chat(text: str, store_first: bool = False,
                  reset_topic: bool = False, observe: bool = True) -> str:
        """Talk with the whole engine — stateful, model-free, audited.

        One call = one turn. What happens inside, in the measured layering
        order (束ねず重ねる — each stage hands off, none votes twice):

          1. your words enter the conversation SPACE (content-addressed,
             no window, cannot silently overflow)
          2. `engine.ask` composes: intent, staging, typo repair,
             arithmetic, theorem witness, difference, census, context
             completion, meaning descent, arm placement, gap ledger,
             frame composition — with `last_core` carried from the
             previous turn, so 「その刑は」 resolves
          3. the reply is audited BESIDE the answer, never as a gate:
             covenant check (rules you set earlier) and context-drift
             check (is it ignoring what this conversation settled)
          4. the reply enters the conversation space too, so later turns
             can hold this one to account

        `store_first` prefers your loaded documents over the federation
        when both answer. `reset_topic` drops the carried subject (start a
        new thread without forgetting the conversation).

        Deterministic, and no model is called — not here, not via MCP
        sampling, not anywhere."""
        from .engine import ask as _engine_ask

        if reset_topic:
            _chat_state["last_core"] = ""
        q = (text or "").strip()
        if not q:
            return json.dumps({"verdict": "UNKNOWN_EMPTY_TURN"},
                              ensure_ascii=False)

        _conversation.add_turn("user", q)

        r = _engine_ask(q, _vera(), last_core=_chat_state["last_core"],
                        store_path=path, store=store,
                        store_first=store_first,
                        circulation=_circulation or None,
                        observe=observe)

        reply = (r.get("text") or "").strip()
        # A typed refusal is a real reply: name the verdict rather than
        # inventing prose around it.
        if not reply:
            reply = "（%s）" % (r.get("verdict") or "UNKNOWN")

        audits: Dict[str, Any] = {}
        try:
            audits["covenants"] = _register.check(reply, asked=q, store=store)
        except Exception as e:      # 監査の故障は答えを潰さず名指しする
            audits["covenants"] = {"error": str(e)}
        try:
            audits["context_drift"] = _collapse(_conversation, reply)
        except Exception as e:
            audits["context_drift"] = {"error": str(e)}

        _conversation.add_turn("vera", reply)
        _conversation.memory.save(_conv_path)
        if r.get("core"):
            _chat_state["last_core"] = str(r["core"])
        # The turn's terminal arrangement goes back into the map, keyed by
        # the core it settled on, and survives a server restart.
        if r.get("core") and r.get("carry_state"):
            _circulation[str(r["core"])] = r["carry_state"]
            try:
                _circ_path.write_text(
                    json.dumps(_circulation, ensure_ascii=False), "utf-8")
            except Exception:
                pass

        stages = r.get("stages")
        return json.dumps({
            "reply": reply,
            "verdict": r.get("verdict"),
            "door": r.get("door"),
            "core": r.get("core"),
            # 引用行の言葉だけで紡いだ constructed な下書き(文書側)と、
            # 連合側の written。返却のホワイトリストがこれを落としており、
            # IDE の 📝下書き行が沈黙していた(実測 2026-08-19)。
            "written": r.get("written"),
            "last_core": _chat_state["last_core"],
            "witnesses": r.get("witnesses"),
            "origins": r.get("origins"),
            "sections": r.get("sections"),
            "stages": stages,
            "audits": audits,
            "circulation": {
                "carried_in": bool(_circulation) ,
                "cores_held": len(_circulation),
                "this_turn": r.get("carry_state"),
            },
            "observation": {
                "enabled": observe,
                # placement-invariance downgrades announce themselves in the
                # verdict/note; surfaced here so a client can show 「観測で
                # 降格」 without parsing prose.
                "verdict": r.get("verdict"),
                "agree_frac": r.get("agree_frac"),
                "local_stable": r.get("local_stable"),
            },
            "conversation": _conversation.stats(),
        }, ensure_ascii=False)

    @mcp.tool()
    def vera_engine(query: str, last_core: str = "", domain: str = "",
                    store_first: bool = False) -> str:
        """Everything the engine knows how to bring, for one question.

        **Call this door, not the specific ones.** MCP puts the caller in
        charge of which door runs, and a caller that knows three doors gets
        a three-door engine: measured, the IDE knew 60 of the 99 and its
        answering path used three, leaving seventeen organs outside every
        question anyone asked. A different client picked a different three
        and the same engine looked like a different product.

        So this door carries the composition instead of the caller. One
        question goes in and the ordering — intent, staging, typo repair,
        arithmetic, theorem witness, difference, census, context
        completion, meaning descent, arm placement, gap ledger, frame
        composition — happens here, in the measured layering direction.
        The reply names the door that answered and lists every stage with
        what it did, so a caller can see which organs ran rather than
        having to know they exist.

        `last_core` supplies the previous answer's subject, which is what
        makes 「その刑は」 resolvable; `domain` restricts composition to a
        registered document.

        `store_first` decides which of the two spaces gets to be THE
        answer when both have one: this terminal's own documents
        (everything `load_documents` ingested) or the published
        federation. They are never merged — the door name in the reply
        says which space spoke, and when both answered the other one
        rides along under `local`. Default is the federation, because a
        loaded document should not silently take over general questions.

        Deterministic, and no model is called."""
        from .engine import ask as _engine_ask

        return json.dumps(
            _engine_ask(query, _vera(), last_core=last_core, domain=domain,
                        store_path=path, store=store,
                        store_first=store_first),
            ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_sovereigns() -> str:
        """Which sovereigns are loaded, and how big each is."""
        return json.dumps(_vera().report(), ensure_ascii=False)

    @mcp.tool()
    def vera_read_at(concept: str, limit: int = 6) -> str:
        """分野ごとの読みを、併合せずに並べて返す(2026-08-19配線)。

        `fusion.read_at` は「両側の言い分を、平均せずに見せる」ための器官
        だが、呼び出し元が一つも無かった(到達性の棚卸しで発覚)。二空間を
        絶対に併合しないという設計の看板機能に、出口が無かったことになる。

        何も選ばない。分野ごとに verdict と読みを並べるだけで、食い違いは
        食い違いのまま返す。実測(2026-08-19、時効): 百科=解・除斥期間 /
        法学=光州事件・制定 / 指名=援用・中断・完成 — 併合すれば消える差。
        「正当防衛」の辞書欄はテレビドラマで、これも語義の分かれ目。
        """
        from .fusion import read_at

        fields = {k: {"merged": v} for k, v in _vera().witnesses.items()}
        return json.dumps(read_at(fields, concept, limit=limit),
                          ensure_ascii=False, default=str)

    @mcp.tool()
    def list_gaps(status: str = "", limit: int = 50) -> str:
        """欠落台帳の一覧(2026-08-19)。拒否のたびに登録される「どの知識が
        不足か」の名指しを、人が見て埋められる形で返す。status で絞り込み
        (DETECTED/ACQUIRING/RESOLVED/BLOCKED_NO_SOURCE、空なら全部)。
        新しい順。"""
        rows = []
        for n in gap_graph.nodes.values():
            if status and getattr(n, "status", "") != status:
                continue
            rows.append({"gap_id": n.gap_id,
                         "subject": getattr(n, "subject", ""),
                         "status": getattr(n, "status", ""),
                         "failure_type": getattr(n, "failure_type", ""),
                         "scope": getattr(n, "scope", ""),
                         "created": getattr(n, "created_at", None) or
                                    getattr(n, "created", None)})
        rows.reverse()
        return json.dumps({"gaps": rows[:max(1, int(limit))],
                           "total": len(rows)}, ensure_ascii=False,
                          default=str)

    @mcp.tool()
    def resolve_gap(gap_id: str, resolution: str = "") -> str:
        """欠落を人手で解決済みにする(文書を入れた・不要と判断した等)。
        台帳から消さない — RESOLVED になって残る。"""
        try:
            gap_graph.set_status(gap_id.strip(), "RESOLVED",
                                 resolution=resolution or "人手で解決済みに")
            _save_gap_graph()
            return json.dumps({"ok": True, "gap_id": gap_id},
                              ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)[:80]},
                              ensure_ascii=False)

    @mcp.tool()
    def what_would_close(query: str, verdict: str = "UNKNOWN_NOT_PRESENT") -> str:
        """Which document, from which shelf, would close this refusal.

        The enterprise inversion of the growth loop: the system never
        fetches, it NAMES the missing document and a human supplies it.
        Ranks the federation's domains by recountable proximity (held as
        core / units held as cores), combines the winner with the
        refusal's own repair (how much to register), and when NO shelf
        holds anything nearby says coverage_hole instead of naming a
        wrong shelf — sending a human after the wrong document is worse
        than the honest hole. Ties are displayed, never broken."""
        from .coverage import document_needed

        return json.dumps(
            document_needed(_atlas(), query, verdict, aliases=_aliases()),
            ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_summarize(subjects: str, limit: int = 5) -> str:
        """Edge-licensed compression over n held subjects (space-separated).

        Each subject is a path; the crossing is every facet two or more
        subjects' crosses hold; a claim is a pair some sentence actually
        WROTE — the edge licence. No edges sidecar, or a crossing no
        sentence ever wrote a pair of, is UNKNOWN_NO_EDGE_LICENSE, never
        a co-presence claim. Drops at the limit fall in whole rank
        groups (crossing width, then subject mass); a tie never decides
        a drop, and dropped_at_cut says what the limit cost. Hand-over
        only — nothing here enters a verdict, a census, or the concord
        band. Measured numbers live in `summarize`'s docstring."""
        from .summarize import summarize as _summarize

        v = _vera()
        store = v.stores.get("ja")
        if store is None or v.writer is None:
            return json.dumps(
                {"verdict": "UNKNOWN_NOT_LOADED",
                 "note": "no Japanese sovereign or no writer in this "
                         "build; the word gate cannot open"},
                ensure_ascii=False)
        out = _summarize(store, subjects.split(), vocab=v.writer.vocab,
                         edges=v.edges, limit=limit)
        # Same connective skeleton the diff door gained; same tolerance.
        try:
            from .connective_render import render_summary as _render
            rendered = _render(out)
            if rendered:
                out["rendered"] = rendered
        except Exception:
            pass
        return json.dumps(out, ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_diff(a: str, b: str) -> str:
        """Structural difference of two subjects — shared / A-only / B-only.

        The six-layer diff (type, predicate profile, kin family, shelf
        mass, edge direction, definition tokens) with the two registered
        guards: "A-only" always means "attested for A, no attestation
        for B" — never a negative claim about B (that would be an
        unlicensed polarity assertion); and every layer that cannot meet
        the minimum profile on both sides abstains, with the imbalance
        reported in `coverage`. This door loads no shelf (912MB stays on
        disk), so the two shelf layers abstain here by design — the
        coverage field says so rather than hiding it. Hand-off only;
        nothing here votes."""
        from . import meaning_assets as ma
        from .structural_diff import diff as _diff

        out = _diff(a, b, profiles=ma.profiles(), aliases=ma.aliases(),
                    lattice=ma.lattice(), shelf=ma.empty_shelf(),
                    senses=ma.senses())
        out["extractor"] = ma.extractor()
        # Connective render: skeleton sentences over the three bundles,
        # every connective licensed by the diff's own structure (243/243
        # placements carried a reason in the acceptance run). Rendering
        # failure never breaks the diff — the bundles are the substance.
        try:
            from .connective_render import render_diff as _render
            rendered = _render(out)
            if rendered:
                out["rendered"] = rendered
        except Exception:
            pass
        return json.dumps(out, ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_intent(text: str) -> str:
        """Frame an instruction structurally, or refuse with UNKNOWN_INTENT.

        The measured share of instruction understanding: 48 verb lemmas
        by 28 operations plus case-particle arms (「geminiを開いて」 →
        開く(対象=gemini)). Anything outside the table refuses — the
        refusal is the signal that the LLM should take the utterance,
        so a caller wires this as: frame parsed -> verify/act on typed
        intent; UNKNOWN_INTENT -> hand the text to the model. Never a
        guessed intent."""
        from .intent_frames import parse as _parse

        return json.dumps(_parse(text), ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_math(name: str) -> str:
        """Is this theorem verified? The mathlib witness store answers.

        75,919 of mathlib's 77,242 theorems carry a
        `verified:lean4:4.34.0-rc1` facet earned by an actual kernel
        run — the hardest witness layer in the project. Lookup is by
        (case-folded) declaration name or its trailing segments
        (`semiconj` finds `addconstmapclass.semiconj` when unique;
        ambiguity lists the candidates instead of choosing). A name the
        store holds without the facet is UNVERIFIED_IN_STORE — present
        but no kernel run vouches here; a name it does not hold is
        UNKNOWN_NOT_IN_MATHLIB_STORE. This door answers about the
        STORE, never about mathematics: absence of a witness is not a
        claim of falsehood, and the sorry trap
        (lean_witness_forks) is why the wording stays this careful."""
        from .mathlib_witness import lookup as _lookup

        return json.dumps(_lookup(name), ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_prove(lhs: str, rhs: str) -> str:
        """Prove an equation, refute it with a counterexample, or refuse.

        Three outcomes, never two — that division is the whole point:

            PROVED    the rewriting kernel derived it (inventing the
                      lemmas it needed), and Lean checked the claim
                      independently. Carries the invented lemmas, the
                      mathlib/core rules it CITED instead of inventing,
                      and the Lean tactic that closed it
            REFUTED   a finite ground model makes the two sides differ —
                      the equation is false, and the **counterexample is
                      named** so a reader can recompute it
            REFUSED   this engine did not reach it. `needs` says what is
                      missing. **Never read as false**: no counterexample
                      was found, and absence is not negation

        Terms are written in the closed signature (`vera_prove` with an
        out-of-signature symbol answers UNKNOWN_ILL_TYPED and lists what
        it holds): naturals 0/s/add/mul/monus, the boolean-valued le
        (a ≤ b is the equation `le(a,b) = true`), lists nil/cons/app/
        rev/len. Variables come from a closed table — a,b,c,n are
        naturals, x,y,z,l,m are lists.

            vera_prove("rev(app(x, y))", "app(rev(y), rev(x))")  -> PROVED
            vera_prove("app(x, y)", "app(y, x)")                 -> REFUTED
                                       x=[0], y=[1]

        Measured 2026-08-20 (experiments/cross_energy_prover): 41 of 41
        goals proved with no lemmas given, 7 of 7 false ones refuted with
        counterexamples, every claim Lean-verified, unsound 0. The
        invention gate killed 2,265 false candidates before any of them
        could be promoted."""
        from .prover import prove_equation as _prove

        return json.dumps(_prove(lhs, rhs), ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_experience(state: str = "", limit: int = 20) -> str:
        """The experience ledger, read-only: everything this system has
        PROVED, REFUTED, failed at, refused, imported, or measured,
        compiled from its scattered stores into nine evidence states —
        CLAIM / EVIDENCE / GAP / FAILURE / COUNTEREXAMPLE / TRANSFER /
        RULE / PROCEDURE / WITNESS. これは Memory ではなく経験のコン
        パイル: 各行が出所ファイルを名指し、原本に辿れない行は台帳に
        居られない。The stores themselves are never modified — this is
        a view, not a merge (束ねない). Pass `state` to filter one
        state; empty returns the counts and sources. Measured at birth
        (2026-08-20): 1,509 rows from 27 sources, including 318
        counterexamples that previously had no first-class home."""
        from .experience import compile_view

        v = compile_view()
        if not state:
            return json.dumps({k: v[k] for k in
                               ("counts", "n_rows", "sources", "note")},
                              ensure_ascii=False, default=str)
        rows = [r for r in v["rows"] if r["state"] == state.upper()]
        return json.dumps({"state": state.upper(), "total": len(rows),
                           "rows": rows[:max(1, limit)]},
                          ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_transfer() -> str:
        """Which of this system's learned facts survived a change of
        context, and which were bound to the one they were learned in.

        The calibration step `transfer_outcomes` deliberately deferred
        ("no calibration analysis ... those need real accumulated data to
        be anything but a guess"), now that data exists. Measured
        2026-08-20 across three local models: 9 observations fold into 3
        facts — truncating input to 64 chars is HARMFUL in all three
        (TRANSFERRED), while retry×3 and truncate-to-400 help only the
        0.5B model (CONTEXT_BOUND).

        The machine reports WHETHER a fact transferred, never WHY. A
        dimension ("this is grounded in the task structure, so it should
        transfer") is a human hypothesis and needs its own evidence; the
        ledger carries hypotheses but does not invent them. A fact seen
        in one context only is UNKNOWN_SINGLE_CONTEXT — no prediction —
        and a dimension with too few observations returns
        UNKNOWN_TOO_FEW_CONTEXTS rather than a number."""
        from .transfer_reading import read as _read

        return json.dumps(_read(), ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_prove_sections(lhs: str, rhs: str) -> str:
        """The stereo cross reading of a proof: derive from each section.

        「複数の外に出ている断面から中心に向かってアクセスし、一致した
        時に探索終了」 — each induction variable is a section, and each
        one derives independently. What this buys is an oracle that needs
        no answer key: if one section PROVES what another REFUTES, the
        derivation depends on the order it was read, and that is a
        soundness alarm rather than an answer. `conflict: true` should
        never appear; `agree_proved` says how many sections reached the
        same conclusion."""
        from .prover import sections_agree as _sections

        return json.dumps(_sections(lhs, rhs), ensure_ascii=False,
                          default=str)

    @mcp.tool()
    def vera_explain(term: str) -> str:
        """Meaning descent: the term's units grounded in definition
        sentences, or a typed abstention. 電荷密度 → 電荷 (defined:
        its lead sentence, source named) + 密度 (likewise), every split
        licensed by the lattice (long window included), bare one-char
        heads refused at the split, ties abstained. The output is
        constructed — EXPLAINED_BY_UNIT_DEFS, never testimony about the
        term itself — and says so. First call loads the 250MB definition
        sidecar; it stays loaded."""
        from . import meaning_assets as ma
        from .meaning_descent import descend as _descend

        out = _descend(term, lattice=ma.lattice(), defs=ma.defs(),
                       aliases=ma.aliases())
        return json.dumps(out, ensure_ascii=False, default=str)

    @mcp.tool()
    def vera_typo(term: str) -> str:
        """Typed hand-off for an out-of-vocabulary term. Never rewrites.

        Recovery@5 84.8% with 0/500 false fires on in-vocabulary terms
        (typo_recovery's docstring holds the protocol). The answer is
        candidates with their evidence (shared positional units, edit
        distance), or IN_VOCABULARY, or UNKNOWN_NO_CANDIDATE — the
        caller decides; silent correction is the one thing this door
        can never do."""
        from . import meaning_assets as ma
        from .typo_recovery import recover as _recover

        out = _recover(term, lattice=ma.lattice(), vocab=ma.vocab())
        return json.dumps(out, ensure_ascii=False, default=str)

    @mcp.tool()
    def how_to_resolve(verdict: str, subject: str = "") -> str:
        """What an expert should register so a refusal becomes an answer.

        Every refusal here is typed and each type has a different repair.
        UNKNOWN_SUBJECT_TOO_THIN wants three more sentences;
        UNKNOWN_LANGUAGE_NOT_HELD wants a sovereign built from documents in
        that language. Without this the refusal says what happened and
        leaves the repair to be guessed.

        Measured end to end — register, rebuild, re-ask: NOT_PRESENT closed
        with three sentences in 1.4s on 54,244 cores; TOO_THIN was still
        NOT_HELD at one fact and answerable at four; NO_CITATION closed with
        one citing document; LANGUAGE_NOT_HELD closed by adding a sovereign.

        Three verdicts report `needs_registration: false` and say why.
        UNKNOWN_TIME_DEPENDENT does not move when the fact is added — 今日 is
        a property of the question and the store has no clock, so whoever
        knows the date resolves it first. UNKNOWN_NO_SUBJECT can be
        registered and should not be: a knowledge store answering こんにちは
        with 挨拶 is not an improvement. UNKNOWN_SUBJECT_NOT_A_WORD means the
        path is already the answer."""
        from .remedy import remedy

        r = {"verdict": verdict}
        if subject:
            r["subject"] = subject
        return json.dumps(remedy(r), ensure_ascii=False)

    @mcp.tool()
    def record_refusal_outcome(query: str, verdict: str, branch: str,
                               resolved: bool = False) -> str:
        """A typed refusal was handed to an action branch (gather-evidence,
        ask-user, resolve-time, record-gap) and this is what happened.

        The refusal's ledger entry is deliberately kept: a refusal an
        agent auto-resolved is a SUCCESS, not a refusal that never
        happened, and a ledger that loses auto-resolved entries tells the
        same shape of lie as an ingest that hides its failures. Call once
        with resolved=false at hand-off (so the hand-off itself can never
        become invisible), and once more after the branch with the one
        honest oracle for resolution: re-ask the same query, and resolved
        is whether the store now answers — never the agent's say-so.

        The gap graph rides the same call: an unresolved refusal creates
        (or reuses — dedup by scope/subject) a GapNode, so the frontier
        map accumulates from operation instead of by hand, and a later
        resolved=true moves that node to RESOLVED. The flow the design
        names — refusal -> gather -> evidence -> record -> gap ledger —
        closes here without the agent having to remember to file it."""
        growth.record_branch_outcome(query, verdict, branch, resolved)
        _save_growth()
        gap_id = None
        try:
            from .gap_graph import refusal_to_gap

            sources = None
            if not resolved:
                # Which shelf would close this — ranked domains ride the
                # node as allowed_sources so a human reading the gap map
                # sees WHAT DOCUMENT to prepare, not just that a hole
                # exists. Best-effort: the atlas needs the full stack.
                try:
                    from .coverage import closing_domains

                    where = closing_domains(_atlas(), query,
                                            aliases=_aliases())
                    if not where["coverage_hole"]:
                        sources = [d["domain"] for d in where["closest"]]
                except Exception:
                    pass
            gap_id = refusal_to_gap(gap_graph, query, verdict, branch,
                                    resolved, sources=sources)
            if gap_id is not None:
                _save_gap_graph()
        except Exception:
            # The ledger entry must survive a gap-graph hiccup; the two
            # records are beside each other, not dependent.
            pass
        return json.dumps(
            {"recorded": True, "open_refusals": len(growth.buckets),
             "outcomes": len(growth.branch_outcomes),
             "gap_id": gap_id}, ensure_ascii=False)

    @mcp.tool()
    def attest_claim(subject: str, text: str) -> str:
        """Judge whether THIS store supports what a claim says about a
        subject. Built for grading an LLM's output: paste the assistant's
        sentences and the subject they are about.

        Returns ANSWER or UNSUPPORTED_BY_CORPUS with the terms the
        subject's own cross does and does not hold.

        It measures the link to the SUBJECT, not the presence of words.
        Measured against a local 4B model over 14 subjects, checking mere
        presence ranked FREE generation ABOVE grounded (95.7% to 85.5%),
        because a fluent answer about Japanese law is built from words a
        legal corpus holds anyway. Subject linkage split them 64.1% to 6.4%
        and flagged 14 of 14 free-generated answers with no false alarm.

        It says "this corpus does not support that", NEVER "that is false".
        A subject the corpus never covered is unsupported and may be
        perfectly true.

        Polarity is judged separately from support, because support alone
        cannot see it: this path reads kanji/katakana runs and Japanese
        negation lives in the hiragana that follows them. Measured
        2026-08-20 (found independently by a blind evaluator and by the
        author): 「実費を支給する」 and 「実費を支給しない」 both scored
        support 1.0 and both returned ANSWER. Now the corpus's own poles
        decide: it answers CONTRADICTED_BY_CORPUS when the store holds the
        opposite pole as evidence (naming the facet), and
        UNKNOWN_POLARITY_UNJUDGED when the store holds the word but never
        recorded its polarity — a refusal, because a support figure that
        scores a claim and its negation identically cannot stand behind
        either. fork 170 pins all three outcomes."""
        from .attest_llm import check_all

        return json.dumps(check_all(store, subject, text), ensure_ascii=False)

    @mcp.tool()
    def record_baseline(label: str = "baseline", keep_cores: str = "") -> str:
        """Record what the store holds now, to compare against later.

        `keep_cores` is a comma-separated list of cores whose facets should
        be kept in FULL — name the ones the design depends on. Everything
        else is stored as a digest, which answers "did this change" without
        becoming a second copy of the store that drifts on its own."""
        from .drift import save, snapshot

        keep = [c.strip() for c in keep_cores.split(",") if c.strip()]
        snap = snapshot(store, label=label, keep=keep)
        return json.dumps(save(snap, path.with_name(
            path.stem + f".baseline.{label}.json")), ensure_ascii=False)

    @mcp.tool()
    def check_drift(label: str = "baseline") -> str:
        """Compare the store against a recorded baseline.

        Reports added / removed / changed cores, each listed rather than
        summed, plus what a named core gained and lost. DRIFTED is not a
        failure and STABLE is not a pass: a gain is usually a lesson and a
        loss is usually a correction, and only a reader knows which the
        design intended.

        The case a count hides is flagged explicitly — `replaced` marks a
        core whose facets were swapped wholesale while its size stayed the
        same, which no total would show."""
        from .drift import compare, load as load_snap

        f = path.with_name(path.stem + f".baseline.{label}.json")
        if not f.is_file():
            return json.dumps({"verdict": "UNKNOWN_NO_BASELINE",
                               "expected": str(f),
                               "advice": "call record_baseline first"},
                              ensure_ascii=False)
        return json.dumps(compare(load_snap(f), store), ensure_ascii=False)

    @mcp.tool()
    def list_baselines() -> str:
        """Every baseline recorded beside this store."""
        out = []
        for f in sorted(path.parent.glob(path.stem + ".baseline.*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                out.append({"label": d.get("label"), "recorded": d.get("recorded"),
                            "cores": d.get("cores"), "file": f.name})
            except Exception:
                continue
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def graph_snapshot(limit: int = 24, facets_per_core: int = 6, focus_cores: str = "") -> str:
        """Structural snapshot of the store for visualization -- NOT for
        grounded QA (that's `ask`). Returns the top `limit` cores ranked
        by pour count, each with up to `facets_per_core` of its top
        facets (with counts). Read-only; does not mutate the store.

        `focus_cores` is an optional comma-separated list of core keys
        (as returned by `remember`'s "remembered" field) that are always
        included even if their pour count is too low to make the top
        `limit` -- otherwise a just-taught fact, which starts at a pour
        count of 1, would never show up once the store has thousands of
        long-accumulated cores ranked above it."""
        ranked = sorted(
            store.core_count.items(), key=lambda kv: kv[1], reverse=True
        )[: max(0, limit)]
        ranked_keys = {core for core, _ in ranked}

        focus_keys = [c.strip().casefold() for c in focus_cores.split(",") if c.strip()]
        for key in focus_keys:
            if key in ranked_keys or key not in store.crosses:
                continue
            ranked.append((key, store.core_count.get(key, 0)))
            ranked_keys.add(key)

        nodes = []
        for core, count in ranked:
            facets = store.top_facets(core, facets_per_core)
            nodes.append({
                "core": core,
                "pour_count": count,
                "facets": [{"facet": f, "count": c} for f, c in facets],
            })
        return json.dumps(
            {"nodes": nodes, "total_cores": len(store.crosses)},
            ensure_ascii=False,
        )

    @mcp.tool()
    def propose_ai_facts(text: str, source: str = "ai_output") -> str:
        """Quarantine sentence-level fact candidates split out of an
        assistant's FINAL reply text — never pass a thinking/chain-of-
        thought block here. Hedge-worded ("might", "probably", "I think")
        and meta-commentary ("let me check") sentences are dropped before
        they even reach quarantine. Nothing proposed here is queryable via
        ask() until a human calls accept_ai_fact — this tool can never by
        itself put an unverified claim into the trusted store."""
        added = quarantine.propose(text, source=source)
        quarantine.save(qpath)
        return json.dumps(
            {"proposed": [e.text for e in added], "quarantine": str(qpath)},
            ensure_ascii=False,
        )

    @mcp.tool()
    def propose_web_evidence(text: str, source: str) -> str:
        """Quarantine ONE raw web-search excerpt, verbatim, for human review
        — the interactive counterpart of what `heartbeat(cognition_mode=
        "sleep")` already does automatically for gap-resolution nodes.

        `propose_ai_facts` runs the text through `candidate_sentences()`,
        which is tuned for an assistant's spoken reply (drops hedge words,
        meta-commentary, questions) — confirmed directly that running a
        real fetched excerpt through it produced ZERO surviving candidates,
        silently losing the evidence. This door instead calls
        `propose_raw()`, which keeps the excerpt whole so a reviewer sees
        exactly what was retrieved.

        Use this after `vera_fresh` (or any web_search + fetch_url pair)
        surfaced something worth keeping: `vera_fresh` itself has no write
        path by design (that is the point of it being a discardable third
        space) — this is the separate, explicit action that puts ONE
        excerpt up for review. Nothing here is queryable via `ask()` until
        a human calls `accept_ai_fact`; review with
        `list_pending_ai_facts` / `accept_ai_fact` / `reject_ai_fact` — the
        SAME queue `propose_ai_facts` already uses."""
        entry = quarantine.propose_raw(text, source=source)
        quarantine.save(qpath)
        return json.dumps(
            {"proposed": entry.text[:400], "source": entry.source,
             "quarantine": str(qpath),
             "note": "承認待ち。list_pending_ai_facts→accept_ai_fact/reject_ai_fact"
                     "で人が決めるまで、ask()からは見えない"},
            ensure_ascii=False,
        )

    @mcp.tool()
    def list_pending_ai_facts() -> str:
        """List AI-proposed facts awaiting human review (index, text,
        source, timestamp). Use the index with accept_ai_fact /
        reject_ai_fact."""
        pend = quarantine.pending()
        return json.dumps(
            [{"index": i, **e.as_dict()} for i, e in enumerate(pend)],
            ensure_ascii=False,
        )

    @mcp.tool()
    def accept_ai_fact(index: int) -> str:
        """Promote one pending AI-proposed fact (by index from
        list_pending_ai_facts) into the trusted, queryable store. This is
        the ONLY path from quarantine into real memory — a deliberate,
        explicit human action, never automatic."""
        pend = quarantine.pending()
        if not (0 <= index < len(pend)):
            return json.dumps({"ok": False, "error": "index_out_of_range"})
        key = quarantine.accept(pend[index], store)
        quarantine.save(qpath)
        store.save(path)
        return json.dumps({"ok": True, "core": key}, ensure_ascii=False)

    @mcp.tool()
    def reject_ai_fact(index: int) -> str:
        """Discard one pending AI-proposed fact (by index) — it is marked
        rejected and never enters the trusted store."""
        pend = quarantine.pending()
        if not (0 <= index < len(pend)):
            return json.dumps({"ok": False, "error": "index_out_of_range"})
        ok = quarantine.reject(pend[index])
        quarantine.save(qpath)
        return json.dumps({"ok": ok}, ensure_ascii=False)

    @mcp.tool()
    def heartbeat(llm_model: str = "", cognition_mode: str = "normal") -> str:
        """Milestone M's autonomous growth tick (closed-domain modules,
        unchanged) plus, when cognition_mode="sleep" (Milestone O), a
        second pass over gap_graph.json's open-domain GapNodes: attempts
        acquisition (web_search/fetch_url) for actionable nodes and
        proposes results into the SAME ai_quarantine.json queue
        propose_ai_facts already uses (see ai_ingest.AiFactQuarantine) --
        never writes directly to the trusted store. cognition_mode=
        "normal"/"experiment" skip this second pass entirely (no gap
        resolution attempted, matching router.py's own no-op guarantee
        for "normal" and "experiment"'s "detect only, don't resolve"
        contract)."""
        drifted = growth.record_mass_snapshot(store)
        candidates = []
        drafted = []
        for bucket in growth.buckets.values():
            verdict = boundary.classify(bucket)
            if verdict.classification != "growth_candidate":
                continue
            candidates.append({"normalized": bucket.normalized, "reason": verdict.reason})
            if not llm_model or not ollama_available():
                continue
            draft = draft_module(bucket, llm_model)
            if not draft["ok"]:
                drafted.append({"normalized": bucket.normalized, "ok": False, "error": draft["error"]})
                continue
            test_queries = build_test_queries(bucket)
            ok, reports = verify_module(draft["source"], test_queries, store, draft["name"])
            report_dicts = [r.as_dict() for r in reports]
            if ok:
                module_quarantine.propose(
                    draft["name"], draft["source"], bucket.normalized, report_dicts,
                )
                module_quarantine.save(mqpath)
                drafted.append({"normalized": bucket.normalized, "ok": True, "name": draft["name"], "queued": True})
            else:
                drafted.append({"normalized": bucket.normalized, "ok": False, "verify_reports": report_dicts})
        _save_growth()

        gap_results: list = []
        if cognition_mode == "sleep":
            from .config import VeraConfig

            cfg = VeraConfig.load()
            for node in gap_graph.actionable(limit=cfg.gap_max_new_nodes_per_run):
                if node.status == "BLOCKED_POLICY":
                    continue
                gap_graph.set_status(node.gap_id, "ACQUIRING")
                # Real-usage bug found live: this loop only ever knew how
                # to try web_search, so a repo-study gap (acquisition_
                # methods = ["vera_git_clone", "vera_code_ingest", ...])
                # always fell straight through to BLOCKED_NO_SOURCE, even
                # though vera_git_clone/vera_code_ingest are both perfectly
                # able to resolve it. Cloning is safe to run automatically
                # here (writes only to Vera's own scratch dir, no trust
                # implications) -- but ingestion writes directly into the
                # TRUSTED store, so Sleep mode does NOT call it itself;
                # it queues vera_code_ingest into the SAME tool_call_
                # quarantine a human already reviews via
                # list_pending_tool_calls/accept_tool_call, exactly the
                # same "never silently promote to trusted" rule every
                # other Sleep-mode resolution in this loop already follows.
                if "vera_git_clone" in node.acquisition_methods:
                    m = re.search(r"https://github\.com/[\w.-]+/[\w.-]+", node.subject)
                    if m:
                        clone = git_clone_scratch(m.group(0), scratch_dir=git_clone_scratch_dir())
                        if clone.get("ok"):
                            entry = tool_call_quarantine.propose(
                                "vera_code_ingest", {"path": clone["path"]},
                                reason="Sleep-mode heartbeat: repo cloned, ingestion queued for review",
                                task=node.subject,
                            )
                            _save_tool_call_quarantine()
                            gap_graph.set_status(
                                node.gap_id, "RESOLUTION_PLANNED",
                                resolution=f"cloned to {clone['path']}, queued vera_code_ingest as {entry.call_id}",
                            )
                            gap_results.append({
                                "gap_id": node.gap_id, "subject": node.subject,
                                "status": "RESOLUTION_PLANNED", "queued_tool_call": entry.call_id,
                            })
                            continue
                    gap_graph.set_status(node.gap_id, "BLOCKED_NO_SOURCE")
                    gap_results.append({"gap_id": node.gap_id, "subject": node.subject,
                                        "status": "BLOCKED_NO_SOURCE"})
                    continue
                evidence_text = None
                source_used = None
                if "web_search" in node.acquisition_methods:
                    sr = web_search(node.subject)
                    if sr.get("ok") and sr.get("results"):
                        top = sr["results"][0]
                        fr = fetch_url(top.get("url", ""))
                        if fr.get("ok"):
                            evidence_text = fr.get("text", "")[:2000]
                            source_used = top.get("url")
                if evidence_text:
                    gap_graph.set_status(node.gap_id, "EVIDENCE_COLLECTED")
                    quarantine.propose_raw(
                        f"[gap:{node.gap_id}] {node.subject}\n\n{evidence_text}",
                        source=f"sleep_mode_gap_resolution:{source_used or 'unknown'}",
                    )
                    quarantine.save(qpath)
                    gap_graph.set_status(node.gap_id, "RESOLVED",
                                          resolution=f"quarantined:{source_used}")
                    gap_results.append({"gap_id": node.gap_id, "subject": node.subject,
                                        "status": "RESOLVED", "queued_for_review": True})
                else:
                    gap_graph.set_status(node.gap_id, "BLOCKED_NO_SOURCE")
                    gap_results.append({"gap_id": node.gap_id, "subject": node.subject,
                                        "status": "BLOCKED_NO_SOURCE"})
            _save_gap_graph()

        # Milestone R3: close out any transfer-outcome records whose target
        # gap has since settled (RESOLVED/BLOCKED_*) without an explicit
        # human judgment — this is what keeps list_transfer_outcomes from
        # staying permanently full of "unjudged" entries when nobody calls
        # record_transfer_result by hand. Runs every heartbeat regardless
        # of cognition_mode (pure read of existing gap status, no new
        # action taken, so it's as safe as wake_summary's own read-only
        # scan).
        newly_judged = infer_missing_outcomes(transfer_log, gap_graph)
        if newly_judged:
            _save_transfer_log()

        # Capacity pass — the other half of the failure taxonomy. Buckets
        # whose dominant verdict says "a limit was hit" get their own failing
        # queries re-run at scaled limits; a limit that verifiably fixes them
        # is queued for human approval, never applied. The re-run doubles as
        # a check on the classification itself: a bucket a larger limit does
        # not fix comes back "reclassify", not as a bigger number.
        from .capacity_calibration import capacity_pass
        from .config import VeraConfig as _VC
        capacity = capacity_pass(
            list(growth.buckets.values()), _VC.load(), capacity_quarantine)
        if any(r.get("queued") for r in capacity):
            capacity_quarantine.save(cqpath)

        return json.dumps(
            {"drifted_cores": drifted, "growth_candidates": candidates, "drafted": drafted,
             "capacity": capacity,
             "gap_resolutions": gap_results,
             "transfer_outcomes_inferred": len(newly_judged)},
            ensure_ascii=False,
        )

    @mcp.tool()
    def record_build_failure(source: str, log_excerpt: str) -> str:
        """Classify a build/CI/conversion failure into a typed verdict
        (UNKNOWN_SIGNING / UNKNOWN_DEPENDENCY / UNKNOWN_MODEL_GEOMETRY /
        UNKNOWN_TEST / UNKNOWN_TIMEOUT / UNKNOWN_DISK / ...) and record it
        in the shared growth-signal store, bucketed by `source` (a stable
        pipeline label like "xcodebuild", "cargo", "jgen_convert").
        Recurrences then surface through failure_stats and the boundary
        classifier like every other typed unknown. Returns the verdict and
        the evidence line so the caller can display the diagnosis."""
        from .build_failure import record_build_failure as _record
        failure = _record(growth, source, log_excerpt)
        _save_growth()
        return json.dumps(
            {"verdict": failure.verdict, "evidence": failure.evidence,
             "note": failure.note},
            ensure_ascii=False,
        )

    # Conversation context as space. One Conversation per server process,
    # persisted beside the store — turns are knowledge, not a scrollback.
    from .conversation import Conversation as _Conv
    from .layer_stack import LayeredMemory as _LM
    _conv_path = path.with_name(path.stem + ".conversation")
    _conversation = _Conv(memory=_LM.load(_conv_path))

    @mcp.tool()
    def add_conversation_turn(speaker: str, text: str) -> str:
        """Ingest one utterance into the conversation's SPACE (not a window).
        Each sentence becomes a node tagged with speaker and turn index, so
        it is retrieved by relevance rather than recency and never falls out
        of a context window. Overflow, when it happens, freezes a layer —
        the turn stays consultable and is reported as FROZEN, never silently
        dropped. Returns which cores the turn touched and whether it caused
        a layer to freeze."""
        turn = _conversation.add_turn(speaker, text)
        _conversation.memory.save(_conv_path)
        return json.dumps(
            {"turn": turn.index, "speaker": turn.speaker, "cores": turn.cores,
             "stats": _conversation.stats()}, ensure_ascii=False)

    @mcp.tool()
    def locate_conversation_topic(topic: str) -> str:
        """Is a topic still in context? The typed answer an LLM cannot give:
        ACTIVE (top layer), FROZEN (overflowed to a lower layer but intact
        and answerable), or ABSENT (never discussed). FROZEN is not lost —
        that distinction is the point. Includes who mentioned it and in which
        turns."""
        return json.dumps(_conversation.locate(topic), ensure_ascii=False)

    @mcp.tool()
    def recall_conversation(query: str, carry: str = "A") -> str:
        """Answer from the conversation's own memory across every layer,
        oldest first (extended inference). `carry` controls whether the
        original query rides along to later layers: A full query, B previous
        answer only, C intent head only. B can drift and says so —
        UNKNOWN_DRIFT rather than a confident wrong answer."""
        return json.dumps(_conversation.recall(query, carry=carry),
                          ensure_ascii=False)

    @mcp.tool()
    def conversation_stats() -> str:
        """Turns, layers, total cores, speakers."""
        return json.dumps(_conversation.stats(), ensure_ascii=False)

    # Deep search over multiple sources. The arm index lives beside the
    # store so intent gating and gap-driven follow-up survive a restart.
    from .arm_schema import ArmIndex as _ArmIndex
    _arm_path = path.with_name(path.stem + ".arms.json")
    _arms = _ArmIndex.load(_arm_path)

    @mcp.tool()
    def ingest_documents(documents_json: str) -> str:
        """Ingest several source documents about one event and PRESERVE their
        disagreements. `documents_json` is a JSON list of
        {"source": "...", "text": "...", "published": "..."}.

        Each sentence is placed with its source attached and, where the
        wording is polar (open/closed, safe/dangerous, passable/blocked...),
        on the corresponding pole. Two sources that disagree therefore end
        up on opposite poles of one aspect, which the store detects on its
        own — unlike a summary, where the disagreement dissolves into
        fluency. Deterministic: no LLM is involved, so the same documents
        always yield the same report and a disputed claim stays citable."""
        from .document_ingest import Document, ingest_documents as _ingest
        try:
            raw = json.loads(documents_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"documents_json is not valid JSON: {e}"},
                              ensure_ascii=False)
        if not isinstance(raw, list):
            return json.dumps({"error": "documents_json must be a JSON list"},
                              ensure_ascii=False)
        docs = [Document(source=str(d.get("source", "unknown")),
                         text=str(d.get("text", "")),
                         published=str(d.get("published", "")))
                for d in raw if isinstance(d, dict)]
        if not store.track_provenance:
            # Attribution is the whole point here; without provenance the
            # report cannot say who claimed which side.
            store.track_provenance = True
        rep = _ingest(store, docs, arms=_arms)
        _save()
        _arms.save(_arm_path)
        return json.dumps(rep.as_dict(), ensure_ascii=False)

    @mcp.tool()
    def deep_report(topic: str) -> str:
        """What is actually known about a topic, in three UNBLENDED parts:

          settled    every source that spoke agrees (with citations)
          disputed   sources disagree — which source said which side
          missing    a question the arm schema says should have an answer
                     and no source gave one, each with `next_query`: the
                     search string that would close it

        `missing` is what makes this deep search rather than summarisation —
        a typed gap is the next round's query. `confidence` is contested /
        supported / unknown, the first thing a responder reads."""
        from .document_ingest import deep_report as _report
        return json.dumps(_report(store, topic, arms=_arms), ensure_ascii=False)

    @mcp.tool()
    def arm_completeness(topic: str) -> str:
        """The six-question checklist for a topic: which arms hold knowledge
        (support/oppose, cause/effect, general/instance) and which are empty.
        An empty arm is a typed gap — unverified, untestable, untransferable
        — ready to become a GapNode."""
        return json.dumps(_arms.report(topic), ensure_ascii=False)

    @mcp.tool()
    def list_failure_domains() -> str:
        """The registered failure-domain packs: name, maturity (verified =
        validated against confirmed incidents; seeded = taxonomy written,
        awaiting real incidents), the typed verdicts each can produce, and
        each verdict's remedy (kind / owner / how it is verified). This is
        the plugin surface of the typed-failure loop — the core is shared,
        packs supply classification and remedy knowledge per field."""
        from .failure_domains import all_domains, load_errors
        out = []
        for d in all_domains():
            out.append({
                "name": d.name, "maturity": d.maturity,
                "description": d.description,
                "editable": d.source_path is not None,
                "source_path": d.source_path,
                "verdicts": [
                    {"verdict": v, "note": note,
                     "provenance": d.provenance.get(v, "code"),
                     "remedy_kind": d.remedies[v].kind,
                     "remedy_owner": d.remedies[v].owner,
                     "verify": d.remedies[v].verify,
                     "auto_calibratable": d.remedies[v].auto_calibratable}
                    for v, _, note in d.patterns
                ],
            })
        # Load errors are part of the answer: a pack an expert edited into an
        # invalid state must be visible, not merely absent.
        return json.dumps({"packs": out, "load_errors": load_errors()},
                          ensure_ascii=False)

    @mcp.tool()
    def propose_failure_verdict(
        pack: str, verdict: str, note: str, positive_examples: str,
        negative_examples: str = "", remedy_kind: str = "fix_content",
        remedy_owner: str = "", verify: str = "rerun",
        remedy_note: str = "", author: str = "unknown",
    ) -> str:
        """Add a new typed verdict to a failure pack FROM EXAMPLES, not from
        a regular expression. Paste real failure lines (one per line in
        positive_examples; optional counter-examples in negative_examples)
        and a pattern is proposed from what they share.

        The proposal is refused, with the specific counter-example, if it
        matches a negative, misses a positive, or breaks the pack's
        maturity contract; existing fixtures it would also claim are
        reported as `shadowed_fixtures`. Nothing is written — the returned
        proposed_pack goes to review. `author` is stamped into provenance
        as human:<author>, which is how a claude-seeded taxonomy stops
        claiming to be mine once a domain expert has corrected it."""
        from .pack_authoring import propose_verdict
        pos = [l for l in positive_examples.split("\n") if l.strip()]
        neg = [l for l in negative_examples.split("\n") if l.strip()]
        out = propose_verdict(
            pack_name=pack, verdict=verdict, note=note,
            positives=pos, negatives=neg,
            remedy_kind=remedy_kind, remedy_owner=remedy_owner or pack,
            verify=verify, remedy_note=remedy_note, author=author)
        # Only a proposal that passes every check reaches the queue. A
        # refused one is returned with its counter-example so the author can
        # fix it, and is NOT queued -- a review queue that fills with things
        # a reviewer must reject is a queue a reviewer stops reading.
        if out.get("ok"):
            entry = pack_quarantine.propose(
                pack_name=pack, verdict=verdict, proposed=out["proposed_pack"],
                positives=pos, negatives=neg, author=author,
                report={"pattern": out["pattern"],
                        "pattern_was_generated": out["pattern_was_generated"],
                        "shadowed_fixtures": out["shadowed_fixtures"]})
            out["queued"] = entry is not None
            if entry is not None:
                pack_quarantine.save(pkpath)
            else:
                out["queued_note"] = "an identical proposal is already pending"
            out.pop("proposed_pack", None)  # the queue holds it; keep the reply small
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def list_pending_pack_verdicts() -> str:
        """Proposed failure-pack verdicts awaiting review. Each carries the
        real log examples the author pasted, the generated pattern, and any
        existing fixtures it would also claim -- the evidence a reviewer
        needs. Use the index with accept/reject_pack_verdict."""
        pend = pack_quarantine.pending()
        return json.dumps([
            {"index": i, "pack_name": e.pack_name, "verdict": e.verdict,
             "author": e.author, "positives": e.positives,
             "negatives": e.negatives, "report": e.report, "ts": e.ts}
            for i, e in enumerate(pend)
        ], ensure_ascii=False)

    @mcp.tool()
    def accept_pack_verdict(index: int) -> str:
        """Write one pending verdict into the overlay pack directory and
        reload the registry. The ONLY path from a proposal to a live
        classifier. Re-validates first: a proposal can go stale if the pack
        changed since, and writing one the loader would reject leaves the
        expert with a file that silently does nothing."""
        out = pack_quarantine.accept(index, pack_overlay_dir)
        pack_quarantine.save(pkpath)
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def reject_pack_verdict(index: int) -> str:
        """Discard one pending verdict proposal."""
        out = pack_quarantine.reject(index)
        pack_quarantine.save(pkpath)
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def test_failure_pack(pack: str, log_samples: str) -> str:
        """Run a pack over real log samples (one per line) and report what it
        typed, with example lines per verdict. The number that matters is
        `coverage`: a taxonomy that types 3 of 200 real failures is not yet
        a taxonomy of that field, however tidy it reads. Use before asking
        for a seeded pack to be trusted."""
        from .pack_authoring import test_pack_against_logs
        logs = [l for l in log_samples.split("\n") if l.strip()]
        return json.dumps(test_pack_against_logs(pack, logs), ensure_ascii=False)

    @mcp.tool()
    def export_failure_pack(pack: str) -> str:
        """The pack as editable JSON — the exact on-disk form. Edit it and
        save to the overlay directory (VERA_FAILURE_PACKS_DIR) to override
        the shipped version; invalid edits are refused at load and reported
        by list_failure_domains rather than silently dropped."""
        from .failure_domains import get, pack_to_dict
        dom = get(pack)
        if dom is None:
            return json.dumps({"error": f"unknown pack: {pack}"}, ensure_ascii=False)
        return json.dumps(pack_to_dict(dom), ensure_ascii=False, indent=1)

    @mcp.tool()
    def record_typed_failure(domain: str, source: str, evidence: str) -> str:
        """Classify failure evidence through the named domain pack (see
        list_failure_domains) and record the typed verdict in the shared
        growth-signal store, bucketed by domain:source. The generic sibling
        of record_build_failure — use that for build logs, this for any
        other registered field (game_qa, search_zero, data_pipeline,
        support_kb, soc_telemetry, decision_explain, math). Returns the
        verdict, its remedy, and the pack's maturity — a "seeded" verdict
        is a taxonomy match, not yet an incident-validated diagnosis."""
        from .failure_domains import get, record_typed_failure as _record
        out = _record(growth, domain, source, evidence)
        if "error" not in out:
            _save_growth()
            dom = get(domain)
            spec = dom.remedies.get(out["verdict"]) if dom else None
            if spec is not None:
                out["remedy_kind"] = spec.kind
                out["remedy_owner"] = spec.owner
                out["verify"] = spec.verify
        return json.dumps(out, ensure_ascii=False)

    # ── Settings help ─────────────────────────────────────────────────────
    # These back the in-app support bot. Deliberately deterministic: the bot
    # they replace was a language model holding a one-row lookup table, told
    # in its own prompt not to invent commands — an instruction a model cannot
    # keep when the table does not cover the question. Here "I do not have
    # that" is a return value rather than a hope.

    @mcp.tool()
    def settings_lookup(question: str) -> str:
        """Find which Verantyx setting a question is about.

        Returns one of ANSWER (with the exact Settings tab and field),
        UNKNOWN_NO_SETTING (no such setting — do not guess one),
        UNKNOWN_AMBIGUOUS (several match; ask the user which). An ANSWER for
        a GUI-only setting also carries cli_verdict=UNKNOWN_NO_CLI, which is
        the honest form of "there is no command for this"."""
        from .settings_registry import lookup
        return json.dumps(lookup(question), ensure_ascii=False)

    @mcp.tool()
    def settings_search(question: str, limit: int = 8) -> str:
        """Ranked near-matches for a settings question — use when
        settings_lookup returns UNKNOWN_AMBIGUOUS or UNKNOWN_NO_SETTING and
        you want to offer the user candidates instead of a dead end."""
        from .settings_registry import search
        return json.dumps(search(question, limit=limit), ensure_ascii=False)

    @mcp.tool()
    def list_modes() -> str:
        """Every mode family in the IDE, in one list.

        The interface shows six independent families on five screens, so each
        one looks like the only mode switch. Each option carries `when`: the
        situation it is the right choice for."""
        from .settings_registry import all_modes
        return json.dumps(all_modes(), ensure_ascii=False)

    @mcp.tool()
    def settings_guide(quickstart: bool = False) -> str:
        """The settings guide as Markdown, generated from the same registry
        the lookup tools read, so the document and the answers cannot drift
        apart. `quickstart=True` returns the short first-run path."""
        from .settings_guide import render_guide, render_quickstart
        return render_quickstart() if quickstart else render_guide()

    @mcp.tool()
    def vera_ask_documents(question: str) -> str:
        """Answer from the loaded documents only — quote, or say nothing.

        This is a different surface from `vera_chat`, not a restricted one,
        and the difference is the point. `vera_chat` runs the whole engine:
        when no store answers, a sentence is COMPOSED from frames and
        fillers and returned marked `constructed`. Measured on 2026-08-18,
        that stage is where every bad answer of the day came from —
        「こんにちは」 became "こんにちはは、格子の分解単位を持たない",
        「正当防衛とは」 produced the same hollow clause three times, and
        「通勤手当は」 returned the word list `通勤手当 合理的な 実費 支給 最`
        while the loaded document held a clean sentence for it.

        The same engine's document stage, on the same day, answered 4 of 4
        loaded-document questions with the exact line and its source, and
        refused 書留 rather than substituting 定形郵便's price.

        So this door runs the strong half and none of the weak one. There
        is no composer behind it: an answer is a quotation with a source,
        or a typed silence. A question this surface cannot answer is
        answered by saying so, never by building a sentence that reads like
        an answer.
        """
        from . import document_structure as _ds
        book = _ds.load(store_path)
        if not book.get("documents"):
            return json.dumps(
                {"verdict": "UNKNOWN_NO_DOCUMENTS", "question": question,
                 "note": "この面は取り込んだ文書だけを引く。まだ一つも無い"},
                ensure_ascii=False)
        out = dict(_ds.lookup(question, book))
        out["question"] = question
        out["surface"] = "documents_only"
        # 答えの本文(text/verdict)は引用のみで、構成段は入らない。この
        # 面の契約は変わらない。ただし 2026-08-19 から、引用行の言葉
        # **だけ**で紡いだ下書きが written として隣に乗ることがある —
        # constructed と明記され、licence は引用行そのもの(同じ行に
        # 書かれた語どうし=同一文共起)。実測: 断片0・汚染0・引用外の
        # 内容語0。8/18に却下した文書側生成の、門つき再挑戦。
        out["constructed"] = False
        try:
            from .stacked import quote_in_words
            _w = getattr(_vera(), "writer", None)
            if _w is not None:
                _qw = quote_in_words(out, _w)
                if _qw:
                    out["written"] = _qw
        except Exception:
            pass
        # 拒否には型(verdict)だけでなく、どの分野が薄いかも添える。
        # 「文書に無い」と「連合のどの棚にも近くが無い」は別の主張で、
        # 後者は薄く広げた federation を coverage.py で読んだだけの
        # 実測(投票ではない)。which_shelf/coverage_hole は既存の
        # what_would_close 扉と同じ経路 — 文書面にも同じ実測を渡す。
        v = str(out.get("verdict") or "")
        if v.startswith("UNKNOWN") or v == "DOCUMENT_NOT_SPECIFIED":
            try:
                from .coverage import document_needed as _document_needed
                out["domain_hint"] = _document_needed(
                    _atlas(), question, v, aliases=_aliases())
            except Exception as e:
                out["domain_hint"] = {"verdict": "UNKNOWN_COVERAGE_UNAVAILABLE",
                                      "note": str(e)[:120]}
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def vera_multi_party(sentence: str) -> str:
        """Split a multi-actor sentence into events, and look up each
        actor's act against the loaded documents independently.

        「AがBを脅してBがCを傷つけた場合、誰がどのような罪を犯したか」 is
        not one subject but two events, with the object of the first
        (B) becoming the actor of the second — feeding the whole sentence
        to `vera_ask_documents` either matches no heading at all or blends
        the two acts into one answer. This door splits on the closed
        surface form 「Xが Yを V(て/た/で/だ/る形)」 and calls the document
        lookup once per event, so each actor's act is answered from the
        document's own words for THAT act alone.

        No legal reasoning happens here — no culpability, intent, or
        justification is weighed. Each event's act is looked up on its
        own; if the document does not hold that word (even under a
        one-character stem fallback), that event stays a typed refusal
        rather than a guess. Pronouns, elided subjects, and non-conforming
        grammar are not decomposed — DECOMPOSE_NO_EVENTS says so honestly
        rather than guessing at structure."""
        from . import document_structure as _ds
        from .multi_party import analyze_multi_party

        book = _ds.load(store_path)
        if not book.get("documents"):
            return json.dumps(
                {"verdict": "UNKNOWN_NO_DOCUMENTS", "sentence": sentence,
                 "note": "この面は取り込んだ文書だけを引く。まだ一つも無い"},
                ensure_ascii=False)
        out = analyze_multi_party(sentence, book)
        if out.get("verdict") == "MULTI_PARTY_ANALYSIS" and out.get("unresolved_count"):
            # 未解決の行為が残るなら、その行為語についても domain_hint と
            # 同じ実測(薄く広げたfederation)を添える — 単一質問の拒否と
            # 同じ扱い。
            for ev in out["per_event"]:
                v = str(ev.get("crime_verdict") or "")
                if v.startswith("UNKNOWN"):
                    try:
                        from .coverage import document_needed as _document_needed
                        ev["domain_hint"] = _document_needed(
                            _atlas(), ev["verb"], v, aliases=_aliases())
                    except Exception as e:
                        ev["domain_hint"] = {"verdict": "UNKNOWN_COVERAGE_UNAVAILABLE",
                                             "note": str(e)[:120]}
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def vera_documents(forget: str = "", attach: str = "",
                       purge: str = "", priority_source: str = "",
                       priority: int = 0) -> str:
        """What documents this terminal has loaded, and a way to drop one.

        The domain shelf (`vera_domains`) and this one are different stores
        and neither one lists the other: a domain is vocabulary — the words
        of a field, so a sentence can be built in its register — while a
        document is text kept verbatim so a line can be quoted back. A
        person who loads a document and then looks for it on the domain
        shelf will not find it, which is a fault of the shelves, not of
        their memory. This is the missing shelf.

        `forget` drops one document by source name. Nothing is removed
        silently and nothing is merged: the sentences that ingest put into
        the federation are a separate act with its own record.
        """
        from . import document_structure as _ds
        book = _ds.load(store_path)
        docs = book.get("documents", [])
        # 「外す」は切断であって削除ではない(2026-08-19、ユーザ報告で
        # 変更): forget は detached:True を立てるだけで sidecar に残り、
        # attach で戻る。完全削除は purge だけが行う。優先度は高いほど
        # 先に照合される — 企業の複数文書で「これを優先して判断」の配線。
        if forget:
            r = _ds.set_document(store_path, forget, detached=True)
            if r.get("verdict") == "SET":
                r["note"] = "切断した(削除ではない)。attach で戻る"
            return json.dumps(r, ensure_ascii=False)
        if attach:
            r = _ds.set_document(store_path, attach, detached=False)
            if r.get("verdict") == "SET":
                r["note"] = "再接続した"
            return json.dumps(r, ensure_ascii=False)
        if priority_source:
            r = _ds.set_document(store_path, priority_source,
                                 priority=priority)
            return json.dumps(r, ensure_ascii=False)
        if purge:
            kept = [d for d in docs if d.get("source") != purge]
            if len(kept) == len(docs):
                return json.dumps({"verdict": "UNKNOWN_NO_SUCH_DOCUMENT",
                                   "source": purge,
                                   "have": [d.get("source") for d in docs]},
                                  ensure_ascii=False)
            book["documents"] = kept
            _ds.sidecar_path(store_path).write_text(
                json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
            return json.dumps({"verdict": "PURGED", "source": purge,
                               "documents": len(kept),
                               "note": "完全に削除した。取り込みの際に"
                                       "連合へ入った文はここでは消えない"},
                              ensure_ascii=False)
        return json.dumps(
            {"verdict": "ANSWER",
             "documents": [{"source": d.get("source"),
                            "sections": len(d.get("sections") or []),
                            "labels": len(d.get("labels") or {}),
                            "lines": d.get("lines"),
                            "detached": bool(d.get("detached")),
                            "priority": int(d.get("priority") or 0),
                            "tree": [{"heading": s.get("heading") or "(前文)",
                                      "lines": len(s.get("lines") or []),
                                      "edges": len(s.get("edges") or [])}
                                     for s in (d.get("sections") or [])[:24]]}
                           for d in docs],
             "note": "文書は逐語引用のための棚。分野(語彙)とは別で、"
                     "合体しない。detached は切断中(データは保持)"},
            ensure_ascii=False)

    @mcp.tool()
    def load_documents(paths: str, ingest: bool = True) -> str:
        """Read files (or a folder) into the store — PDF, Word, HTML, CSV,
        JSON, plain text.

        `paths` is comma-separated; a directory is walked. Files that cannot
        be read are reported by name with the reason (UNKNOWN_NO_PARSER for a
        format with no loader, UNKNOWN_EMPTY_DOCUMENT for a scanned PDF that
        holds only images) and the rest still load — a batch that drops what
        it could not read reports a smaller corpus as if it were the whole
        one. Japanese and English are both segmented correctly.

        Each document is ALSO indexed by its own structure — numbered
        headings and labelled values — into a sidecar beside the store.
        Measured on a contest PDF: sentence-level ingest kept 51 of 68
        lines and the 17 it dropped were the answer, because the
        requirements and the deadline are bullets under a heading and a
        bullet is not a sentence. The sidecar quotes; it never votes."""
        from .document_ingest import ingest_documents
        from .document_loaders import load_directory, load_paths
        from .document_structure import index as _structure
        from .document_structure import save as _save_structure

        items = [x.strip() for x in (paths or "").split(",") if x.strip()]
        docs, skipped = [], []
        for item in items:
            res = (load_directory(item) if Path(item).is_dir()
                   else load_paths([item]))
            docs.extend(res["documents"])
            skipped.extend(res["skipped"])
        out = {"loaded": len(docs), "skipped": skipped,
               "sources": [d.source for d in docs]}
        if ingest and docs:
            rep = ingest_documents(store, docs)
            _save()
            out["ingested"] = rep.as_dict()
            structured = []
            for d in docs:
                try:
                    structured.append(
                        _save_structure(path, _structure(d.text, d.source)))
                except Exception as exc:
                    structured.append({"verdict": "UNKNOWN_NOT_STRUCTURED",
                                       "source": d.source,
                                       "error": str(exc)[:80]})
            out["structure"] = structured
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def field_report_categories(lang: str = "ja") -> str:
        """The posting categories and their closed status sets, with how many
        minutes each takes to go stale.

        Statuses are CHOSEN, never typed: measured on ten realistic resident
        postings, free-text status yielded a usable state zero times, because
        residents write 「ここ給水やってる」 and the engine reads formal
        announcements. Choosing removes the parse instead of climbing it."""
        from .field_reports import category_list
        return json.dumps(category_list(lang), ensure_ascii=False)

    @mcp.tool()
    def field_report_needs(lang: str = "ja") -> str:
        """What someone might need, and which categories answer it.

        Keyed on NEED, never on who the person is. Asking whether someone is
        elderly or disabled classifies people in order to help them, and that
        fails three ways: some will not answer, some do not recognise
        themselves in the label, and holding the answer creates a duty to
        protect it."""
        from .field_reports import need_list
        return json.dumps(need_list(lang), ensure_ascii=False)

    @mcp.tool()
    def assess_field_reports(reports_json: str, now: int,
                             needs: str = "") -> str:
        """Turn structured field reports into typed findings.

        `reports_json` is a list of {place, category, status, at, reporter,
        note, official}; `now` and `at` are minutes on one shared clock.
        Pass `needs` (comma-separated) to select by what someone needs.

        Verdicts: CONFIRMED (several reporters, recently), REPORTED (one),
        CONFLICT (fresh reports disagree — no side preferred, none outvoted,
        including the official one), SUPERSEDED, EXPIRED (nothing recent
        enough to stand behind — NOT the same as closed), UNKNOWN_NO_REPORT.

        No confidence score is returned, deliberately: a number performs a
        precision nobody has and a reader takes it as permission."""
        from .field_reports import Report, assess, for_needs, validate
        try:
            raw = json.loads(reports_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"verdict": "UNKNOWN_BAD_INPUT",
                               "reason": str(exc)}, ensure_ascii=False)
        reports, errors = [], []
        for i, d in enumerate(raw if isinstance(raw, list) else []):
            r = Report(place=str(d.get("place", "")),
                       category=str(d.get("category", "")),
                       status=str(d.get("status", "")),
                       at=int(d.get("at", 0)),
                       reporter=str(d.get("reporter", "resident")),
                       note=str(d.get("note", "")),
                       official=bool(d.get("official", False)))
            errs = validate(r)
            if errs:
                errors.append({"index": i, "errors": errs})
            else:
                reports.append(r)
        want = [n.strip() for n in (needs or "").split(",") if n.strip()]
        if want:
            out = {"findings": for_needs(reports, int(now), want)}
        else:
            places = sorted({(r.place, r.category) for r in reports})
            out = {"findings": [assess(reports, int(now), p, c).as_dict()
                                for p, c in places]}
        # Rejected postings are named rather than dropped: a board that
        # silently ignores malformed input reports a smaller world as if it
        # were the whole one.
        if errors:
            out["rejected"] = errors
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def explain_placement(sentence: str) -> str:
        """Where would this sentence land, and why — core, facets, poles,
        the subject gate's verdict, and the arm, each with its reason.

        The adjustment interface for "arrange my data": placement is a pure
        function of text plus grammar data, so the way to change it is to
        see the decision, extend the grammar overlay, and explain again.
        There is deliberately no hand-reordering — hand-placed facts cannot
        be re-derived and would break reproducibility."""
        from .placement_explain import explain
        return json.dumps(explain(sentence), ensure_ascii=False)

    @mcp.tool()
    def grammar_status() -> str:
        """The Japanese grammar currently in force: bundled counts, which
        overlay (if any) loaded from beside the store, and any overlay error
        — an invalid overlay refuses to load with every problem named."""
        out = _jag.status()
        if _grammar_overlay_error:
            out["overlay_error"] = _grammar_overlay_error
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def own_ai_guide() -> str:
        """The build-your-own-AI guide: how placement works (core / facet /
        pole / arm), the explain→overlay→re-explain adjustment loop, the
        overlay file format with validation rules, and the traps the system
        guards against. Bilingual, rendered from code so it cannot drift."""
        from .own_ai_guide import render
        return render()

    @mcp.tool()
    def goal_recipe(question: str) -> str:
        """Turn "what I want to do" into the ordered settings that get there.

        Use this BEFORE settings_lookup when the user describes an outcome
        ("build my own AI", "keep everything offline", "run across two Macs")
        rather than naming a setting — a newcomer does not know the setting
        is called inference_mode, so they cannot ask for it by name.

        Returns ANSWER with numbered steps, each carrying the settings tab to
        open, the value to set, why it matters, and whether the app may set it
        for the user. Otherwise UNKNOWN_NO_RECIPE (with the list of goals) or
        UNKNOWN_AMBIGUOUS_GOAL."""
        from .task_recipes import match_goal
        return json.dumps(match_goal(question), ensure_ascii=False)

    @mcp.tool()
    def list_goals() -> str:
        """Every task recipe available — the "what can I actually do with
        this" list, for a first-run screen or when goal_recipe misses."""
        from .task_recipes import list_goals as _list
        return json.dumps(_list(), ensure_ascii=False)

    @mcp.tool()
    def failure_stats() -> str:
        """Histogram of typed failures across all recorded UNKNOWN buckets,
        plus what the boundary detector currently makes of each bucket.
        This is the 'which kind of failure dominates' view: verdict counts
        say what keeps going wrong, classifications say what the system
        thinks should be done about it (needs_more_facts /
        needs_more_capacity / growth_candidate / reject_open_domain)."""
        from . import boundary as _boundary
        verdict_hist: dict = {}
        class_hist: dict = {}
        rows = []
        for bucket in growth.buckets.values():
            for v, n in bucket.verdict_counts.items():
                verdict_hist[v] = verdict_hist.get(v, 0) + n
            cls = _boundary.classify(bucket).classification
            class_hist[cls] = class_hist.get(cls, 0) + 1
            rows.append({"normalized": bucket.normalized,
                         "total": bucket.total(),
                         "dominant": bucket.dominant_verdict(),
                         "classification": cls})
        rows.sort(key=lambda r: -r["total"])
        return json.dumps(
            {"verdicts": verdict_hist, "classifications": class_hist,
             "buckets": rows[:50]},
            ensure_ascii=False,
        )

    @mcp.tool()
    def list_pending_capacity_limits() -> str:
        """List calibrated limit increases awaiting human review. Each entry
        carries the probe evidence: which failing queries were re-run, at
        which multipliers, and that every one answered. Use the index with
        accept_capacity_limit / reject_capacity_limit."""
        pend = capacity_quarantine.pending()
        return json.dumps(
            [{"index": i, **e.as_dict()} for i, e in enumerate(pend)],
            ensure_ascii=False,
        )

    @mcp.tool()
    def accept_capacity_limit(index: int) -> str:
        """Apply one pending limit increase (by index) to VeraConfig. The
        ONLY path by which a proposed limit becomes a running limit — the
        math domain reads config per query, so it takes effect immediately,
        no restart."""
        out = capacity_quarantine.accept(index)
        capacity_quarantine.save(cqpath)
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def reject_capacity_limit(index: int) -> str:
        """Discard one pending limit increase (by index)."""
        out = capacity_quarantine.reject(index)
        capacity_quarantine.save(cqpath)
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def propose_domain_module(name: str, source_code: str, candidate_summary: str) -> str:
        """Manually quarantine a hand- or externally-drafted domain module
        (bypassing heartbeat's LLM step) — still runs through the same
        verification gates as heartbeat's auto-drafted candidates before
        it can be queued. Nothing here is live until accept_domain_module."""
        test_queries = [candidate_summary]
        ok, reports = verify_module(source_code, test_queries, store, name)
        report_dicts = [r.as_dict() for r in reports]
        if not ok:
            return json.dumps({"ok": False, "verify_reports": report_dicts}, ensure_ascii=False)
        module_quarantine.propose(name, source_code, candidate_summary, report_dicts)
        module_quarantine.save(mqpath)
        return json.dumps({"ok": True, "queued": True}, ensure_ascii=False)

    @mcp.tool()
    def list_pending_domain_modules() -> str:
        """List LLM-drafted domain modules awaiting human review (index,
        name, source code, verify test report, candidate summary). Use the
        index with accept_domain_module / reject_domain_module."""
        pend = module_quarantine.pending()
        return json.dumps(
            [{"index": i, **e.as_dict()} for i, e in enumerate(pend)],
            ensure_ascii=False,
        )

    @mcp.tool()
    def accept_domain_module(index: int) -> str:
        """Promote one pending domain module (by index from
        list_pending_domain_modules) into the live domain registry and
        write it to verantyx/domains/generated/. The ONLY path from
        quarantine to an active module — never automatic."""
        pend = module_quarantine.pending()
        if not (0 <= index < len(pend)):
            return json.dumps({"ok": False, "error": "index_out_of_range"})
        module_path = module_quarantine.accept(pend[index], pkg_dir)
        module_quarantine.save(mqpath)
        return json.dumps({"ok": module_path is not None, "path": module_path}, ensure_ascii=False)

    @mcp.tool()
    def reject_domain_module(index: int) -> str:
        """Discard one pending domain module (by index) — marked rejected,
        never written to disk or registered."""
        pend = module_quarantine.pending()
        if not (0 <= index < len(pend)):
            return json.dumps({"ok": False, "error": "index_out_of_range"})
        ok = module_quarantine.reject(pend[index])
        module_quarantine.save(mqpath)
        return json.dumps({"ok": ok}, ensure_ascii=False)

    @mcp.tool()
    def wake_summary(since_seconds: float = 43200.0) -> str:
        """Milestone O: 'what changed while you were away' — GapNodes whose
        status changed within the last `since_seconds` (default 12h),
        split by outcome, plus a reminder of how many items are sitting in
        the two existing review queues (list_pending_ai_facts /
        list_pending_domain_modules — this tool doesn't duplicate their
        content, just points at them)."""
        import time as _time

        cutoff = _time.time() - since_seconds
        changed = gap_graph.since(cutoff)
        resolved = [n.as_dict() for n in changed if n.status == "RESOLVED"]
        still_open = [n.as_dict() for n in changed if n.status not in ("RESOLVED",) and n.status not in
                      ("BLOCKED_POLICY", "BLOCKED_NO_SOURCE", "BLOCKED_PERMISSION",
                       "BLOCKED_BUDGET", "BLOCKED_CONTRADICTION", "STALE")]
        blocked = [n.as_dict() for n in changed if n.status.startswith("BLOCKED_") or n.status == "STALE"]
        return json.dumps({
            "resolved": resolved, "still_open": still_open, "blocked": blocked,
            "pending_fact_review": len(quarantine.pending()),
            "pending_module_review": len(module_quarantine.pending()),
        }, ensure_ascii=False)

    @mcp.tool()
    def find_similar_gaps(gap_id: str, limit: int = 5) -> str:
        """Structural (not text/vector) similarity against other GapNodes'
        role/failure_type/input_type/output_type/expected_transition/
        observed_transition fields — same shape, possibly totally
        different subject (e.g. a save-button bug and a 3D-export bug
        sharing "trigger fires, expected transition never observed").
        Requires the target and candidates to have these fields set (most
        gaps created by router.py/agent.py don't set them yet — this tool
        is useful once callers start populating them). NOT_COMPARABLE
        candidates are dropped entirely, not returned with a low score."""
        target = gap_graph.get(gap_id)
        if target is None:
            return json.dumps({"ok": False, "error": "unknown_gap_id"})
        matches = find_structural_matches(target, list(gap_graph.nodes.values()), limit=limit)
        return json.dumps({
            "ok": True,
            "matches": [
                {"gap_id": m.gap_id, "level": m.level, "scores": m.scores,
                 "matched_dimensions": m.matched_dimensions, "different_dimensions": m.different_dimensions,
                 "resolution": gap_graph.get(m.gap_id).resolution if gap_graph.get(m.gap_id) else None}
                for m in matches
            ],
        }, ensure_ascii=False)

    @mcp.tool()
    def log_transfer_attempt(source_gap_id: str, target_gap_id: str, resolution_applied: str) -> str:
        """Milestone R3: record that a structurally-matched resolution
        (from find_similar_gaps' source_gap_id) was actually tried on
        target_gap_id. `success` starts unset — call
        record_transfer_outcome once you know the result, or let
        heartbeat's automatic status-based inference fill it in later.
        This tool ONLY records; it never applies anything itself."""
        target = gap_graph.get(target_gap_id)
        source = gap_graph.get(source_gap_id)
        if target is None or source is None:
            return json.dumps({"ok": False, "error": "unknown_gap_id"})
        matches = find_structural_matches(target, [source], limit=1)
        if not matches:
            return json.dumps({"ok": False, "error": "not_structurally_comparable"})
        record = record_transfer_attempt(
            transfer_log, matches[0], target_gap_id=target_gap_id, resolution_applied=resolution_applied,
        )
        _save_transfer_log()
        return json.dumps({"ok": True, "outcome_id": record.outcome_id}, ensure_ascii=False)

    @mcp.tool()
    def record_transfer_result(outcome_id: str, success: bool, judged_by: str = "human") -> str:
        """Explicitly judge a previously-logged transfer attempt
        (log_transfer_attempt's outcome_id). Explicit judgment always
        takes priority over heartbeat's later automatic inference."""
        record = record_transfer_outcome(transfer_log, outcome_id, success=success, judged_by=judged_by)
        if record is None:
            return json.dumps({"ok": False, "error": "unknown_outcome_id"})
        _save_transfer_log()
        return json.dumps({"ok": True, **record.as_dict()}, ensure_ascii=False)

    @mcp.tool()
    def list_transfer_outcomes(only_unjudged: bool = False) -> str:
        """The raw log this milestone exists to build up — every recorded
        structural-match reuse attempt and whether it worked. Nothing
        analyzes this yet (deliberately not part of this pass); it's the
        evidence a future calibration step would need to tell "just needs
        more knowledge" apart from "the comparison shape itself is
        insufficient" (see this module's own docstring)."""
        records = transfer_log.unjudged() if only_unjudged else transfer_log.records
        return json.dumps([r.as_dict() for r in records], ensure_ascii=False)

    def _csv(s: str) -> list:
        return [x.strip() for x in s.split(",") if x.strip()] if s else []

    @mcp.tool()
    def bootstrap_unknown_task(
        name: str, description: str = "", user_goal: str = "",
        available_inputs: str = "", available_tools: str = "", known_affordances: str = "",
        success_criteria: str = "", allowed_sources: str = "", constraints: str = "",
        cognition_mode: str = "normal",
    ) -> str:
        """Milestone R2: turn an unfamiliar task (ARC-AGI-3, an unknown CLI/
        library, an unknown repository, or anything else — same entry point
        for all of them) into 6 structural slots (IDENTITY/GOAL/AFFORDANCES/
        INPUTS/SUCCESS_CRITERIA/CONSTRAINTS). Unknown slots become typed
        GapNodes; the result also surfaces past tasks with the same known/
        unknown SHAPE (structural_matches) and one recommended next
        acquisition action. List-shaped args are comma-separated (e.g.
        allowed_sources="web,local_repository"). This tool only structures
        the task — it never searches or acts on its own. Respects the same
        normal/experiment/sleep contract as record_ui_transition (Milestone
        S): "normal" is a guaranteed no-op, no GapNodes written."""
        if cognition_mode == "normal":
            return json.dumps({"ok": True, "skipped": "normal_mode"})
        descriptor = TaskDescriptor(
            name=name, description=description, user_goal=user_goal,
            available_inputs=_csv(available_inputs), available_tools=_csv(available_tools),
            known_affordances=_csv(known_affordances), success_criteria=_csv(success_criteria),
            allowed_sources=_csv(allowed_sources), constraints=_csv(constraints),
        )
        result = _bootstrap_unknown_task(gap_graph, descriptor)
        _save_gap_graph()
        action = _select_next_action(result, gap_graph)
        return json.dumps({
            "task_id": result.task_id, "known_slots": result.known_nodes,
            "gap_ids": result.gap_nodes, "executable": result.executable,
            "structural_matches": [
                {"gap_id": m.gap_id, "level": m.level} for m in result.structural_matches
            ],
            "next_action": {
                "intent_type": action.intent_type, "target_gap_id": action.target_gap_id,
                "preferred_tools": action.preferred_tools, "allowed_sources": action.allowed_sources,
                "query": action.required_evidence[0] if action.required_evidence else None,
            } if action else None,
        }, ensure_ascii=False)

    @mcp.tool()
    def arc_observe_transition(session_id: str, level_id: str, action: str,
                                frame_before: str, frame_after: str) -> str:
        """Milestone R1: feed one action->observation step from a 2D
        dynamic-puzzle environment (ARC-AGI-3 or similar). frame_before/
        frame_after are JSON 2D grids of ints (e.g. "[[0,0],[1,0]]"). If
        the naive "nothing changes" hypothesis was wrong, creates a typed
        GapNode and immediately checks it against every past environment
        gap for a structural match (same failure shape, possibly a
        totally different game)."""
        try:
            before = json.loads(frame_before)
            after = json.loads(frame_after)
        except json.JSONDecodeError as e:
            return json.dumps({"ok": False, "error": f"bad_json: {e}"})
        node = observe_transition(
            gap_graph, session_id=session_id, level_id=level_id, action=action,
            frame_before=before, frame_after=after,
        )
        if node is None:
            return json.dumps({"ok": True, "gap_created": False})
        _save_gap_graph()
        matches = find_transferable_matches(node, gap_graph)
        return json.dumps({
            "ok": True, "gap_created": True, "gap_id": node.gap_id,
            "transferable_matches": [{"gap_id": m.gap_id, "level": m.level} for m in matches],
        }, ensure_ascii=False)

    @mcp.tool()
    def record_ui_transition(session_id: str, action_label: str, changed: bool,
                              cognition_mode: str = "normal") -> str:
        """Milestone S: the IDE's Swift side calls this once per recorded
        UI-automation step (the same call site that already writes to
        UITestVectorTrace) to record a causal action -> observation pair
        into GapGraph -- model-independent, unlike UITestVectorTrace's own
        JGEN-embedding record. Respects the same normal/experiment/sleep
        contract as every other GapNode-creating path: "normal" is a
        guaranteed no-op, matching router.py's own guarantee. v1 only
        records what was observed (see ui_transition.py's own docstring
        for why expected_transition is deliberately left unset) --
        mismatch detection across accumulated observations is future
        work, not this tool's job."""
        if cognition_mode == "normal":
            return json.dumps({"ok": True, "skipped": "normal_mode"})
        node = observe_ui_transition(
            gap_graph, session_id=session_id, action_label=action_label, changed=changed,
        )
        _save_gap_graph()
        return json.dumps({"ok": True, "gap_id": node.gap_id, "status": node.status}, ensure_ascii=False)

    @mcp.tool()
    def list_pending_tool_calls() -> str:
        """Milestone R4: mutating tool calls the Vera-harness chat (IDE)
        proposed but could not run without a human — same shape as
        list_pending_ai_facts/list_pending_domain_modules. Use the index
        with accept_tool_call/reject_tool_call.

        Real bug found live: the Vera-harness chat runs as a SEPARATE OS
        process (`vera-memory ... serve`, launched by VeraAgentClient.swift)
        from this MCP server (`vera-memory ... mcp`, launched by
        MCPEngine.swift) -- two independent processes with their own
        memory, sharing state only through tool_call_quarantine.json on
        disk. Reading the in-memory `tool_call_quarantine` this function
        used to use was only ever a snapshot from whenever THIS process
        started, so a call queued by the other process was invisible
        forever. Reloading from disk on every call is the fix -- cheap
        (small JSON file, human-paced call frequency), and correct for
        two independent writers in a way an in-memory cache never can be."""
        nonlocal tool_call_quarantine
        tool_call_quarantine = ToolCallQuarantine.load(tcqpath)
        pend = tool_call_quarantine.pending()
        return json.dumps([{"index": i, **e.as_dict()} for i, e in enumerate(pend)], ensure_ascii=False)

    @mcp.tool()
    def accept_tool_call(index: int) -> str:
        """Actually RUN one pending tool call (by index from
        list_pending_tool_calls) now, with current state — not a replay
        of state from when it was proposed. The ONLY path from a queued
        proposal to an executed mutating action."""
        nonlocal tool_call_quarantine
        tool_call_quarantine = ToolCallQuarantine.load(tcqpath)
        pend = tool_call_quarantine.pending()
        if not (0 <= index < len(pend)):
            return json.dumps({"ok": False, "error": "index_out_of_range"})
        result = tool_call_quarantine.accept(pend[index], tool_registry)
        _save_tool_call_quarantine()
        return json.dumps({"executed": True, "result": result}, ensure_ascii=False)

    @mcp.tool()
    def reject_tool_call(index: int) -> str:
        """Discard one pending tool call (by index) — never runs."""
        nonlocal tool_call_quarantine
        tool_call_quarantine = ToolCallQuarantine.load(tcqpath)
        pend = tool_call_quarantine.pending()
        if not (0 <= index < len(pend)):
            return json.dumps({"ok": False, "error": "index_out_of_range"})
        ok = tool_call_quarantine.reject(pend[index])
        _save_tool_call_quarantine()
        return json.dumps({"ok": ok}, ensure_ascii=False)

    #: CLI にしか無い機能へ IDE を届かせる橋(2026-08-22、PREREG9)。
    #: **閉じた許可表**: 読むだけ・計算だけのものに限る。破壊的なもの
    #: (forget)と外へ出るもの(push-store)と対話式(setup/wizard)は
    #: 入れない — 扉は LLM が叩けるので、店を消す道と公開する道を
    #: 開けてはいけない。取り込み系は既に扉がある(load_documents /
    #: code_ingest / remember)ので写さない。
    _CLI_ALLOWED = {"doctor", "lab", "lexicon", "self-audit", "simplify",
                    "math", "stats", "placement", "audit"}

    @mcp.tool()
    def capability_index(query: str = "", limit: int = 12) -> str:
        """**Ask this before building anything.** Does the capability
        already exist here?

        One search across every door, CLI command, module, fork, prereg and
        result — derived from the source at call time, so it cannot go
        stale the way a hand-written list does. With no query it returns
        the counts.

        It exists because this repository is 67,145 lines, 129 doors, 89
        forks and 74 preregs: more than any context window holds, which is
        why capabilities kept getting rebuilt. Ranking is term overlap
        only, deterministic, no embeddings; a query that matches nothing
        returns UNKNOWN_NOT_FOUND rather than the nearest name, because
        telling someone a thing exists when it does not costs more than
        rebuilding it.
        """
        from .index import build, search

        if not query.strip():
            idx = build()
            return json.dumps({"verdict": "ANSWER", "counts": idx["counts"],
                               "total": idx["total"]}, ensure_ascii=False)
        return json.dumps(search(query, limit=limit), ensure_ascii=False)

    @mcp.tool()
    def vera_doctor() -> str:
        """この機械で今、保証が成り立つかを実演して答える。

        番人(G1〜G4)・単体の装置(S1〜S4)・配線(WIRED/PARTIAL/
        NOT_WIRED)。保証が壊れていれば BROKEN、配線だけなら DEGRADED。
        IDE はこれ一つで健康を描ける。
        """
        from .doctor import full_doctor

        return json.dumps(full_doctor(), ensure_ascii=False)

    @mcp.tool()
    def vera_cli(command: str, args_json: str = "[]") -> str:
        """CLI にしか無い機能を IDE から使う橋(閉じた許可表つき)。

        扉ごとに CLI を書き写すと二つの表面が必ずずれるので、写さずに
        呼ぶ。許可表は読むだけ・計算だけ: doctor / lab / lexicon /
        self-audit / simplify / math / stats / placement / audit。
        店を消すもの・外へ出るもの・対話式のものは**入れない**。
        """
        import subprocess
        import sys as _sys

        if command not in _CLI_ALLOWED:
            return json.dumps({"verdict": "UNKNOWN_NOT_ALLOWED",
                               "command": command,
                               "allowed": sorted(_CLI_ALLOWED),
                               "note": "破壊的・公開・対話式の命令は橋に"
                                       "載せない"}, ensure_ascii=False)
        try:
            extra = json.loads(args_json or "[]")
            extra = [str(x) for x in (extra if isinstance(extra, list)
                                      else [extra])]
        except Exception:
            return json.dumps({"verdict": "UNKNOWN_BAD_ARGS"},
                              ensure_ascii=False)
        head = ([_sys.executable] if getattr(_sys, "frozen", False)
                else [_sys.executable, "-m", "verantyx.cli"])
        r = subprocess.run(head + ["--store", str(path), command] + extra,
                           capture_output=True, text=True, timeout=1800)
        try:
            return json.dumps({"verdict": "ANSWER", "command": command,
                               "result": json.loads(r.stdout)},
                              ensure_ascii=False)
        except Exception:
            return json.dumps({"verdict": "ANSWER", "command": command,
                               "stdout": r.stdout[-4000:],
                               "stderr": r.stderr[-500:]},
                              ensure_ascii=False)

    @mcp.tool()
    def pending_decisions(limit: int = 20) -> str:
        """人の判断を待っているものを、**1つの窓**にまとめて返す。

        欠けを隠さずに見せるための読むだけの扉(2026-08-22、PREREG8)。
        待ち行列は既に22本の扉として在る — ここは**新しい待ち行列を
        作らない**。数えたものは全部、既存の扉から来る(別に持つと必ず
        ずれる)。閉じ方(どの扉を叩けばよいか)も一緒に返す。

        自動で埋めにいく経路も既に在る(`heartbeat(cognition_mode=
        "sleep")` が欠けの取得を試み、`propose_web_evidence` が
        ウェブ抜粋を逐語で隔離する)。**装置自身は決して取りに行かない** —
        提案は隔離席に入り、採用は人の行為のまま。オフラインの決定論は
        そのために守られる。
        """
        def _count(fn, *a):
            try:
                v = json.loads(fn(*a))
            except Exception as e:              # noqa: BLE001
                return None, repr(e)
            if isinstance(v, list):
                return len(v), v[:3]
            if isinstance(v, dict):
                for key in ("pending", "rows", "gaps", "list", "items",
                            "candidates", "modules"):
                    if isinstance(v.get(key), list):
                        return len(v[key]), v[key][:3]
                return (0, v) if not v else (len(v), v)
            return 0, v

        queues = [
            ("ai_facts", list_pending_ai_facts,
             ["accept_ai_fact", "reject_ai_fact"]),
            ("tool_calls", list_pending_tool_calls,
             ["accept_tool_call", "reject_tool_call"]),
            ("domain_modules", list_pending_domain_modules,
             ["accept_domain_module", "reject_domain_module"]),
            ("capacity_limits", list_pending_capacity_limits,
             ["accept_capacity_limit", "reject_capacity_limit"]),
            ("pack_verdicts", list_pending_pack_verdicts,
             ["accept_pack_verdict", "reject_pack_verdict"]),
            ("covenant_candidates", review_candidates,
             ["adopt_covenant", "retire_covenant"]),
            ("gaps", list_gaps, ["what_would_close", "resolve_gap"]),
        ]
        rows = []
        total = 0
        for name, fn, closers in queues:
            n, sample = _count(fn)
            if n is None:
                rows.append({"kind": name, "waiting": "UNKNOWN",
                             "error": sample, "close_with": closers})
                continue
            total += n
            rows.append({"kind": name, "waiting": n,
                         "close_with": closers,
                         "sample": sample if n else []})
        rows.sort(key=lambda r: (r["kind"],))
        return json.dumps({
            "verdict": "ANSWER",
            "waiting_total": total,
            "queues": rows,
            "acquire_modes": {
                "manual": "what_would_close(query) が、足りない文書を名指す",
                "assisted": "propose_web_evidence(text, source) — 外で拾った"
                            "抜粋を逐語で隔離。採用は人",
                "autonomous": 'heartbeat(cognition_mode="sleep") — 欠けの'
                              "取得を試みる。結果はやはり隔離席へ",
            },
            "note": "read-only: this window holds no state of its own; "
                    "every number here comes from the queue that owns it",
        }, ensure_ascii=False)

    return mcp


def serve(store_path: str) -> int:
    mcp = build(store_path)
    if mcp is None:
        return 2
    mcp.run()
    return 0
