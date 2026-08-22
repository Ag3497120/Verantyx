"""One place that knows what every setting and mode is — and can prove it.

The problem this exists for: the IDE grew six separate mode families and
sixty-odd persisted settings, each with its own screen, and the support bot
meant to explain them was an LLM holding a one-row lookup table. That bot's
own prompt told it "do NOT hallucinate commands", which is not a property a
language model can be instructed into — when the table has one row and the
question is about the other fifty-nine, inventing a plausible answer is the
only thing left for it to do.

So the knowledge lives here instead, and answers are typed:

    ANSWER                  the setting is known
    UNKNOWN_NO_SETTING      no such setting — say so, do not guess a path
    UNKNOWN_AMBIGUOUS       several match; the caller must narrow it
    UNKNOWN_NO_CLI          the setting exists but has no CLI command

That last verdict is the one that matters most. "This is GUI-only" is a real
answer a user can act on; a fabricated `verantyx ide config set ...` line
costs them a support round-trip and their trust in every other answer.

Every entry names the Swift symbol it was read from, and
`verify_against_source()` re-checks those against a real checkout. That is
what keeps this from becoming the usual stale wiki: the documentation and the
check that the documentation is still true are the same object. When someone
renames a UserDefaults key, the verifier fails and names the row.

No LLM is involved anywhere in this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: Settings screen tabs, read from SettingsView.SettingsTab. GUI paths below
#: are only allowed to name one of these, so a path can never point at a
#: screen that does not exist.
TABS: Tuple[str, ...] = ("General", "Model", "API Keys", "Tools", "Agent",
                         "Memory", "Privacy", "MCP", "BitNet", "JGEN")


@dataclass(frozen=True)
class Setting:
    """One persisted preference.

    `defaults_key` is the UserDefaults key as it appears in the Swift source;
    it is the anchor the verifier greps for. `cli` is None when the setting is
    genuinely GUI-only — None is a fact to report, not a gap to fill in.
    """

    key: str                 # stable id used by callers, e.g. "model.ollama"
    tab: str                 # one of TABS
    title_en: str
    title_ja: str
    what: str                # one line: what changing it does
    defaults_key: str        # UserDefaults key in the Swift source
    cli: Optional[str] = None
    values: Tuple[str, ...] = ()      # empty = free-form
    aliases: Tuple[str, ...] = ()     # words a user might search by
    note: str = ""


@dataclass(frozen=True)
class ModeOption:
    key: str
    label_en: str
    label_ja: str
    what: str
    when: str                # when a user should pick this one


@dataclass(frozen=True)
class ModeFamily:
    """A group of mutually exclusive modes.

    Separated by family because the IDE's difficulty is not that modes exist
    but that six independent families each look like "the" mode selector. A
    reader who knows which family a switch belongs to can reason about what it
    cannot affect.
    """

    group: str
    title_en: str
    title_ja: str
    what: str
    source: str              # Swift file:line the cases were read from
    defaults_key: Optional[str]
    options: Tuple[ModeOption, ...]
    tab: str = "General"


# ---------------------------------------------------------------------------
# Mode families — cases read from the Swift enums, not invented.
# ---------------------------------------------------------------------------

MODE_FAMILIES: Tuple[ModeFamily, ...] = (
    ModeFamily(
        group="operation",
        title_en="Operation mode", title_ja="動作モード",
        what="How much the agent asks before it acts.",
        source="Engine/ArtifactEngine.swift:11 (OperationMode)",
        defaults_key="operation_mode", tab="Agent",
        options=(
            ModeOption("gatekeeper", "Gatekeeper", "ゲートキーパー",
                       "Every change passes a review gate before it lands.",
                       "Shared or production code, where an unreviewed edit is expensive."),
            ModeOption("automatic", "Automatic", "自動",
                       "Runs to completion without stopping to ask.",
                       "A task you have already scoped and want finished unattended."),
            ModeOption("detailed", "Detailed", "詳細",
                       "Asks questions and gathers context as it goes.",
                       "An unclear task, where the first answer is likely to be the wrong one."),
        ),
    ),
    ModeFamily(
        group="inference",
        title_en="Inference route", title_ja="推論経路",
        what="Where your text goes: local machine, cloud, or masked before sending.",
        source="Engine/HybridEngine.swift:20 (InferenceMode)",
        defaults_key="inference_mode", tab="Privacy",
        options=(
            ModeOption("localOnly", "Local Only", "ローカルのみ",
                       "Nothing leaves the machine.",
                       "Anything you cannot send to a third party."),
            ModeOption("cloudDirect", "Cloud Direct", "クラウド直送",
                       "Text is sent to the cloud provider unmodified.",
                       "Public code, where capability matters more than exposure."),
            ModeOption("privacyShield", "Privacy Shield", "プライバシーシールド",
                       "Identifiers are masked before the request is sent.",
                       "Cloud capability on code with names you would rather not ship."),
            ModeOption("paranoiaMode", "Paranoia Mode", "パラノイアモード",
                       "AST-level surgical masking before sending.",
                       "The strictest option that still uses the cloud."),
        ),
    ),
    ModeFamily(
        group="mcp_execution",
        title_en="MCP execution mode", title_ja="MCP 実行モード",
        what="Whether an MCP tool call has a deadline.",
        source="Engine/MCPEngine.swift:140 (MCPServerConfig.ExecutionMode)",
        defaults_key=None, tab="MCP",
        options=(
            ModeOption("ai", "AI Priority", "AI 優先",
                       "No automatic timeout; runs until it finishes or you stop it.",
                       "Long tool calls you intend to wait for."),
            ModeOption("human", "Human Mode", "人間モード",
                       "A 60-second outer deadline.",
                       "Interactive work, where a hung tool should give up rather than block you."),
        ),
    ),
    ModeFamily(
        group="memory_layer",
        title_en="BitNet memory depth", title_ja="BitNet 記憶の深さ",
        what="How many memory layers the commander model reads.",
        source="Gatekeeper/GatekeeperModeState.swift:44 (MemoryLayerMode)",
        defaults_key="gkBitnetMemoryMode", tab="Memory",
        options=(
            ModeOption("L1 Only", "L1 Only", "L1 のみ",
                       "Only the shallowest layer is read.",
                       "Faster, when deep context is not paying for itself."),
            ModeOption("L1-L3 Full", "L1-L3 Full", "L1〜L3 全層",
                       "All three layers are read.",
                       "The default; richer context per call."),
        ),
    ),
    ModeFamily(
        group="cognition",
        title_en="Cognition mode", title_ja="思考モード",
        what="What the council does between requests.",
        source="Engine/CouncilSettingsStore.swift:140 (CognitionMode)",
        defaults_key=None, tab="Memory",
        options=(
            ModeOption("normal", "Normal", "通常",
                       "Ordinary operation.", "The default."),
            ModeOption("experiment", "Experiment", "実験",
                       "Runs experimental paths.", "Evaluating a change before trusting it."),
            ModeOption("sleep", "Sleep", "Sleep",
                       "Background consolidation rather than answering.",
                       "While you are away and want accumulated state tidied."),
        ),
    ),
    ModeFamily(
        group="vera_save_approval",
        title_en="Vera save approval", title_ja="Vera 保存の承認",
        what="When you are asked to approve what Vera writes to memory.",
        source="Engine/VeraSaveApprovalRequest.swift:6 (VeraSaveApprovalMode)",
        defaults_key=None, tab="Memory",
        options=(
            ModeOption("per_turn", "Ask every turn", "毎ターン確認",
                       "The agent waits for your decision each turn.",
                       "When you want to see everything entering memory."),
            ModeOption("batched", "Queue and review later", "まとめて後で確認",
                       "Requests queue while the agent keeps working.",
                       "Long sessions, where stopping every turn costs more than it catches."),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Settings. `defaults_key` values are the real UserDefaults keys; the verifier
# below greps the Swift tree for each one, so a rename fails loudly here.
# `cli=None` means GUI-only and is reported as UNKNOWN_NO_CLI.
# ---------------------------------------------------------------------------

SETTINGS: Tuple[Setting, ...] = (
    Setting("language", "General", "Interface language", "表示言語",
            "Switches the interface between English and Japanese.",
            "app_language", values=("en", "ja"), aliases=("language", "言語", "日本語")),
    Setting("workspace", "General", "Last workspace", "最後のワークスペース",
            "The folder reopened at launch.",
            "last_workspace_path", aliases=("workspace", "folder", "ワークスペース")),
    Setting("font_size", "General", "Editor font size", "エディタ文字サイズ",
            "Point size of the code editor.",
            "code_font_size", aliases=("font", "文字", "サイズ")),

    Setting("model.ollama", "Model", "Ollama model", "Ollama モデル",
            "Which Ollama model local requests use.",
            "active_ollama_model", aliases=("ollama", "local model", "ローカルモデル", "モデル")),
    Setting("model.mlx", "Model", "MLX model", "MLX モデル",
            "Which MLX model local requests use.",
            "active_mlx_model", aliases=("mlx", "apple silicon")),
    Setting("model.lmstudio", "Model", "LM Studio model", "LM Studio モデル",
            "Which LM Studio model local requests use.",
            "active_lmstudio_model", aliases=("lmstudio", "lm studio")),
    Setting("model.ollama_endpoint", "Model", "Ollama endpoint", "Ollama エンドポイント",
            "URL the Ollama client connects to.",
            "ollama_endpoint", aliases=("endpoint", "url", "port", "ポート", "エンドポイント", "接続先")),
    Setting("model.lmstudio_endpoint", "Model", "LM Studio endpoint", "LM Studio エンドポイント",
            "URL the LM Studio client connects to.",
            "lmstudio_endpoint", aliases=("endpoint", "url")),
    Setting("model.temperature", "Model", "Temperature", "温度",
            "Sampling temperature for generation.",
            "model_temperature", aliases=("temperature", "温度", "randomness")),
    Setting("model.context_window", "Model", "Context window override",
            "コンテキスト長の上書き",
            "Forces a context length instead of the model's own.",
            "context_window_override", aliases=("context", "window", "コンテキスト")),
    Setting("model.cloud_provider", "Model", "Cloud provider", "クラウド提供元",
            "Which cloud provider cloud requests go to.",
            "cloud_provider", aliases=("provider", "cloud", "クラウド")),
    Setting("model.streaming", "Model", "Streaming", "ストリーミング",
            "Whether responses stream token by token.",
            "streaming_enabled", values=("true", "false"), aliases=("stream", "ストリーミング")),

    Setting("api.anthropic", "API Keys", "Anthropic API key", "Anthropic API キー",
            "Credential for Anthropic requests.",
            "anthropic_api_key", aliases=("anthropic", "claude", "api", "api key", "キー", "apiキー"),
            note="Entered in the GUI only; it is never printed back."),
    Setting("api.openai", "API Keys", "OpenAI API key", "OpenAI API キー",
            "Credential for OpenAI requests.", "openai_api_key",
            aliases=("openai", "gpt", "api", "キー", "apiキー")),
    Setting("api.gemini", "API Keys", "Gemini API key", "Gemini API キー",
            "Credential for Gemini requests.", "gemini_api_key",
            aliases=("gemini", "google", "api", "キー", "apiキー")),

    Setting("tools.terminal", "Tools", "Terminal tool", "ターミナルツール",
            "Lets the agent run shell commands.",
            "tool_terminal", values=("true", "false"), aliases=("terminal", "shell", "ターミナル")),
    Setting("tools.browser", "Tools", "Browser tool", "ブラウザツール",
            "Lets the agent drive the browser.",
            "tool_browser", values=("true", "false"), aliases=("browser", "ブラウザ")),
    Setting("tools.diff", "Tools", "Diff tool", "差分ツール",
            "Lets the agent propose file diffs.",
            "tool_diff", values=("true", "false"), aliases=("diff", "差分")),

    Setting("agent.loop", "Agent", "Agent loop", "エージェントループ",
            "Whether the agent keeps working across turns on its own.",
            "agent_loop_enabled", values=("true", "false"),
            aliases=("agent", "loop", "autonomous", "自動")),
    Setting("agent.system_prompt", "Agent", "System prompt", "システムプロンプト",
            "Text prepended to every request.",
            "system_prompt", aliases=("prompt", "instructions", "プロンプト")),
    Setting("agent.gatekeeper", "Agent", "Gatekeeper enabled", "ゲートキーパー有効",
            "Turns the review gate on.",
            "gatekeeperModeEnabled", values=("true", "false"),
            aliases=("gatekeeper", "review", "ゲートキーパー")),

    Setting("memory.cortex", "Memory", "Cortex enabled", "Cortex 有効",
            "Turns the Cortex memory layer on.",
            "cortex_enabled", values=("true", "false"), aliases=("cortex", "記憶")),
    Setting("memory.cortex_threshold", "Memory", "Cortex threshold", "Cortex しきい値",
            "How readily Cortex recalls stored context.",
            "cortex_threshold", aliases=("threshold", "しきい値")),
    Setting("memory.external_llm", "Memory", "Allow external LLM for commander",
            "コマンダーで外部 LLM を許可",
            "Whether the commander model may be a cloud model.",
            "gkAllowExternalLLM", values=("true", "false"),
            aliases=("external", "cloud", "commander")),

    Setting("privacy.masking", "Privacy", "Semantic masking", "セマンティックマスキング",
            "Masks identifiers before cloud requests.",
            "gemma_semantic_masking", values=("true", "false"),
            aliases=("mask", "masking", "マスク", "privacy")),
)


# ---------------------------------------------------------------------------
# Lookup — typed, never guessing
# ---------------------------------------------------------------------------

VERDICTS = ("ANSWER", "UNKNOWN_NO_SETTING", "UNKNOWN_AMBIGUOUS", "UNKNOWN_NO_CLI")

_BY_KEY: Dict[str, Setting] = {s.key: s for s in SETTINGS}


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"[^\w.]+", (text or "").lower()) if t]


#: Words that carry no signal about WHICH setting is meant. Without this the
#: scorer ranked "how do I change the language" as the context-window setting,
#: because every short word matched something somewhere.
_STOP = {
    "how", "do", "does", "did", "i", "you", "the", "a", "an", "to", "of", "in",
    "on", "is", "are", "can", "want", "would", "like", "please", "my", "me",
    "it", "this", "that", "what", "where", "which", "and", "or", "for",
    "change", "set", "setting", "settings", "option", "enable", "disable",
    "turn", "make", "use", "using", "verantyx", "ide", "app",
}


_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")


def _min_name_len(name: str) -> int:
    """Shortest name allowed to match by substring, by script.

    Three characters for Latin text, because "api" is a word and "ap" is
    noise. Two for CJK, because "温度" and "言語" are whole words — holding
    Japanese to the Latin threshold silently dropped every two-character
    term, which is most of the useful ones.
    """
    return 2 if _CJK.search(name) else 3


def _score(setting: Setting, query: str) -> int:
    """How well one setting matches a question, in either language.

    Two directions, because the two languages need different ones:

      * name-in-query — does a known name appear inside the text? Japanese has
        no spaces to split on, so a query like "ollamaのモデルを変えたい" is one
        token and word matching finds nothing. Substring matching in this
        direction is what makes Japanese questions work at all.
      * query-word-in-entry — English questions split cleanly, so their words
        are matched against the entry, with stop words dropped.

    Both use whole names rather than loose substrings. An earlier version
    tested every query token as a substring of the entry text, which let "i"
    and "do" match nearly everything and produced a confident wrong answer.
    Being crude is fine here; being noisy is not, because each wrong row sends
    someone to the wrong screen.
    """
    q = (query or "").lower()
    score = 0

    strong = {setting.key.lower(), *(a.lower() for a in setting.aliases)}
    weak = {setting.title_en.lower(), setting.title_ja.lower()}

    for name in strong:
        if len(name) >= _min_name_len(name) and name in q:
            score += 3
    for name in weak:
        if len(name) >= _min_name_len(name) and name in q:
            score += 2

    entry_words = set(_tokens(setting.title_en)) | set(_tokens(setting.what))
    for t in _tokens(q):
        if len(t) < 3 or t in _STOP:
            continue
        if t in strong:
            score += 3
        elif t in entry_words:
            score += 1
    return score


def lookup(query: str) -> Dict[str, Any]:
    """Find the setting a question is about, or refuse with a reason.

    Ambiguity is reported rather than broken by picking the top hit. A tie
    between "Ollama model" and "Ollama endpoint" is genuinely two different
    screens, and choosing silently is how a support answer becomes confidently
    wrong.
    """
    terms = _tokens(query)
    if not terms:
        return {"verdict": "UNKNOWN_NO_SETTING", "query": query,
                "reason": "empty query"}

    if query.strip() in _BY_KEY:
        return _answer(_BY_KEY[query.strip()])

    scored = sorted(((_score(s, query), s) for s in SETTINGS),
                    key=lambda p: -p[0])
    best = scored[0][0]
    if best == 0:
        return {"verdict": "UNKNOWN_NO_SETTING", "query": query,
                "reason": "no setting matches these words",
                "next_step": "search() lists near matches; the settings screens "
                             "are " + ", ".join(TABS)}
    tied = [s for score, s in scored if score == best]
    if len(tied) > 1:
        return {"verdict": "UNKNOWN_AMBIGUOUS", "query": query,
                "candidates": [{"key": s.key, "title": s.title_en, "tab": s.tab}
                               for s in tied],
                "reason": f"{len(tied)} settings match equally well"}
    return _answer(tied[0])


def _answer(s: Setting) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "verdict": "ANSWER",
        "key": s.key,
        "title": {"en": s.title_en, "ja": s.title_ja},
        "what": s.what,
        "where": f"Settings > {s.tab} > {s.title_en}",
        "tab": s.tab,
        "defaults_key": s.defaults_key,
        "values": list(s.values),
        "note": s.note,
    }
    if s.cli:
        out["cli"] = s.cli
    else:
        # Not a failure of the answer — a fact about the setting, and the one
        # the old LLM bot was structurally unable to say.
        out["cli_verdict"] = "UNKNOWN_NO_CLI"
        out["cli_reason"] = "this setting is changed in the GUI; no CLI command exists"
    return out


def search(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Ranked near-matches, for a UI that wants to show options."""
    hits = [(_score(s, query), s) for s in SETTINGS]
    return [{"key": s.key, "title": s.title_en, "title_ja": s.title_ja,
             "tab": s.tab, "score": sc}
            for sc, s in sorted(hits, key=lambda p: -p[0]) if sc > 0][:limit]


def mode_family(group: str) -> Optional[ModeFamily]:
    for fam in MODE_FAMILIES:
        if fam.group == group:
            return fam
    return None


def all_modes() -> List[Dict[str, Any]]:
    """Every mode family in one list — the consolidated view the settings
    screens do not currently give, where six families each look like the
    only one."""
    return [{
        "group": f.group, "title": {"en": f.title_en, "ja": f.title_ja},
        "what": f.what, "tab": f.tab, "source": f.source,
        "defaults_key": f.defaults_key,
        "options": [{"key": o.key, "label": {"en": o.label_en, "ja": o.label_ja},
                     "what": o.what, "when": o.when} for o in f.options],
    } for f in MODE_FAMILIES]


# ---------------------------------------------------------------------------
# The property that keeps this honest
# ---------------------------------------------------------------------------

def verify_against_source(source_root: str) -> Dict[str, Any]:
    """Re-check every claim against a real checkout of the IDE.

    Two checks, both cheap and both re-runnable:

      * every `defaults_key` still appears in the Swift sources
      * every mode family's `source` file still exists

    A registry that cannot be checked against the code is a wiki, and wikis
    drift silently. This is the difference between documentation that is
    believed and documentation that is verified — and it is the same check a
    human would do by hand, just not skipped.

    Missing source tree returns UNKNOWN_NO_SOURCE rather than passing
    vacuously: "I could not check" must never read like "I checked".
    """
    root = Path(source_root)
    if not root.is_dir():
        return {"verdict": "UNKNOWN_NO_SOURCE", "root": str(root),
                "reason": "source tree not found — nothing was verified"}

    swift = list(root.rglob("*.swift"))
    if not swift:
        return {"verdict": "UNKNOWN_NO_SOURCE", "root": str(root),
                "reason": "no .swift files under this root"}
    blob = "\n".join(p.read_text(errors="ignore") for p in swift)

    missing_keys = [s.key for s in SETTINGS
                    if f'"{s.defaults_key}"' not in blob]
    missing_modes = [f.group for f in MODE_FAMILIES
                     if not (root / f.source.split(":")[0]).is_file()]
    bad_tabs = [s.key for s in SETTINGS if s.tab not in TABS]

    ok = not (missing_keys or missing_modes or bad_tabs)
    return {
        "verdict": "ANSWER" if ok else "UNKNOWN_STALE_REGISTRY",
        "checked_settings": len(SETTINGS),
        "checked_mode_families": len(MODE_FAMILIES),
        "swift_files": len(swift),
        "missing_defaults_keys": missing_keys,
        "missing_mode_sources": missing_modes,
        "invalid_tabs": bad_tabs,
    }
