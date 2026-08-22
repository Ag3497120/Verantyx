"""Goals, not settings — the path from "what I want" to "which switches".

The settings registry answers "where does X live". That is the wrong question
for someone new: they do not know that what they want is called
`inference_mode`, so they cannot ask. They know they want to build their own
AI, or keep everything on this machine, or run a big model across two Macs.

A recipe turns one of those sentences into an ordered list of concrete steps,
each naming a real setting from the registry and the value it should hold.
Every step carries `why`, because a list of switches to flip teaches nothing
and the next question will be the same question.

Two properties this deliberately keeps:

  * Every step's `setting` must exist in the registry. `validate_recipes()`
    checks it, so a recipe cannot send someone to a screen that was renamed.
  * A step declares whether it can be applied for the user or only navigated
    to. Writing a value the running app will not notice is worse than saying
    "open this and change it yourself" — the setting reads as changed and
    behaves as unchanged, which is the hardest kind of bug to see.

No LLM. Matching a sentence to a goal is keyword scoring over the same
bilingual scheme the registry uses, and an unmatched sentence returns
UNKNOWN_NO_RECIPE rather than the nearest goal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .settings_registry import (MODE_FAMILIES, SETTINGS, _min_name_len,
                                _tokens, mode_family)


@dataclass(frozen=True)
class Step:
    """One move in a recipe.

    `setting` is a registry key, or "mode:<group>" for a mode family.
    `value` is what it should be set to; None means "you choose, here is what
    the options mean".
    `applicable` is False when the app cannot safely set it from outside —
    API keys are the clear case, and anything the running app caches in
    memory rather than re-reading.
    """

    setting: str
    value: Optional[str]
    why: str
    applicable: bool = True


@dataclass(frozen=True)
class Recipe:
    goal: str                 # stable id
    title_en: str
    title_ja: str
    summary: str
    steps: Tuple[Step, ...]
    keywords: Tuple[str, ...] = ()


RECIPES: Tuple[Recipe, ...] = (
    Recipe(
        goal="own_ai",
        title_en="Build your own AI",
        title_ja="独自の AI を作る",
        summary=("Run a local model, give it a memory that survives restarts, "
                 "and let it act on its own between your messages."),
        keywords=("own ai", "my own", "独自", "自分の", "作る", "build", "create",
                  "オリジナル", "自前"),
        steps=(
            Step("mode:inference", "localOnly",
                 "Start local. Nothing leaves the machine while you are still "
                 "deciding what this assistant is for."),
            Step("model.ollama", None,
                 "Pick the model that will do the thinking. This is the one "
                 "choice that changes how it feels more than any other."),
            Step("model.ollama_endpoint", None,
                 "Point at where Ollama is running. Default is fine unless you "
                 "moved it."),
            Step("memory.cortex", "true",
                 "Turn on memory. Without this the assistant starts from "
                 "nothing every session, which is the difference between a "
                 "chat window and something that is yours."),
            Step("agent.system_prompt", None,
                 "Say what it is for. This text goes in front of every "
                 "request and is what makes it your assistant rather than a "
                 "generic one."),
            Step("agent.loop", "true",
                 "Let it keep working between your messages instead of "
                 "stopping after each reply."),
            Step("mode:operation", "detailed",
                 "While you are still shaping it, have it ask rather than "
                 "guess. Switch to Automatic once you trust it."),
        ),
    ),
    Recipe(
        goal="fully_offline",
        title_en="Keep everything on this machine",
        title_ja="すべてこの端末だけで使う",
        summary="No text leaves the machine, at any point, for any reason.",
        keywords=("offline", "local", "ローカル", "オフライン", "外に出さない",
                  "送信しない", "private", "社外", "持ち出"),
        steps=(
            Step("mode:inference", "localOnly",
                 "The switch that actually decides it. Everything below is "
                 "defence in depth."),
            Step("model.ollama", None,
                 "A local model has to do the work now, so this choice is no "
                 "longer optional."),
            Step("memory.external_llm", "false",
                 "Stop the commander model from reaching for a cloud model."),
            Step("memory.cortex", "true",
                 "Local memory replaces what the cloud's long context was "
                 "doing for you."),
        ),
    ),
    Recipe(
        goal="cloud_with_masking",
        title_en="Use the cloud without shipping your names",
        title_ja="クラウドを使いつつ固有名詞を出さない",
        summary=("Cloud capability on code you would rather not send verbatim: "
                 "identifiers are masked before the request leaves."),
        keywords=("cloud", "クラウド", "マスク", "mask", "秘匿", "匿名",
                  "privacy shield", "隠して"),
        steps=(
            Step("mode:inference", "privacyShield",
                 "Masks identifiers on the way out. Paranoia Mode is the "
                 "stricter version if this is not enough."),
            Step("privacy.masking", "true",
                 "The masking pass itself."),
            Step("api.anthropic", None,
                 "A cloud provider needs a key. Type it in the GUI — it is "
                 "never printed back, and nothing else can enter it for you.",
                 applicable=False),
            Step("model.cloud_provider", None,
                 "Which provider the masked request goes to."),
        ),
    ),
    Recipe(
        goal="two_macs",
        title_en="Run a large model across two Macs",
        title_ja="2台の Mac で大きいモデルを動かす",
        summary=("Split a model that does not fit in one machine's memory "
                 "across a Thunderbolt link."),
        keywords=("two macs", "2台", "二台", "分散", "distributed", "pipe",
                  "thunderbolt", "大きいモデル"),
        steps=(
            Step("mode:inference", "localOnly",
                 "Distributed inference is a local arrangement; the cloud "
                 "routes do not apply."),
            Step("model.context_window", None,
                 "Set this deliberately. Splitting a model makes it easy to "
                 "ask for a context neither half can hold."),
            Step("mode:memory_layer", "L1-L3 Full",
                 "The commander reads across the link, so shallow memory "
                 "costs more here than it saves."),
        ),
    ),
    Recipe(
        goal="team_review",
        title_en="Work on shared code safely",
        title_ja="共有コードで安全に作業する",
        summary="Nothing lands without passing a review gate first.",
        keywords=("team", "review", "チーム", "レビュー", "共有", "本番",
                  "production", "gatekeeper", "ゲートキーパー"),
        steps=(
            Step("mode:operation", "gatekeeper",
                 "Every change passes the gate. This is the whole recipe; the "
                 "rest is making the gate informative."),
            Step("agent.gatekeeper", "true",
                 "Turns the gate on."),
            Step("mode:vera_save_approval", "batched",
                 "Review what went into memory in bulk. Per-turn approval "
                 "stops the agent constantly, and prompts that interrupt "
                 "constantly stop being read."),
            Step("tools.diff", "true",
                 "See changes as diffs before they land."),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Matching a sentence to a goal
# ---------------------------------------------------------------------------

_STOP = {"how", "do", "i", "to", "the", "a", "an", "my", "want", "would",
         "like", "can", "what", "is", "for", "make", "get", "use", "please"}


def _score(recipe: Recipe, query: str) -> int:
    q = (query or "").lower()
    score = 0
    for kw in recipe.keywords:
        k = kw.lower()
        if len(k) >= _min_name_len(k) and k in q:
            score += 3
    for name in (recipe.title_en.lower(), recipe.title_ja.lower()):
        if name in q:
            score += 3
    for t in _tokens(q):
        if len(t) < 3 or t in _STOP:
            continue
        if t in {k.lower() for k in recipe.keywords}:
            score += 2
    return score


def match_goal(query: str) -> Dict[str, Any]:
    """Which recipe a sentence is asking for, or a typed miss.

    A near-match is not returned as the answer. Walking someone through
    "keep everything local" when they asked about two Macs wastes more of
    their time than saying no and listing the goals.
    """
    if not (query or "").strip():
        return {"verdict": "UNKNOWN_NO_RECIPE", "reason": "empty query",
                "goals": [r.goal for r in RECIPES]}
    scored = sorted(((_score(r, query), r) for r in RECIPES), key=lambda p: -p[0])
    best = scored[0][0]
    if best == 0:
        return {"verdict": "UNKNOWN_NO_RECIPE", "query": query,
                "reason": "no goal matches this",
                "goals": [{"goal": r.goal, "title": r.title_en,
                           "title_ja": r.title_ja} for r in RECIPES]}
    tied = [r for sc, r in scored if sc == best]
    if len(tied) > 1:
        return {"verdict": "UNKNOWN_AMBIGUOUS_GOAL", "query": query,
                "candidates": [{"goal": r.goal, "title": r.title_en,
                                "title_ja": r.title_ja} for r in tied]}
    return render(tied[0].goal)


def render(goal: str) -> Dict[str, Any]:
    """A recipe expanded into steps a UI can act on.

    Each step carries where to go (`tab`), what to set, and whether the app
    may set it on the user's behalf. `options` is filled for mode steps with
    no fixed value, so the screen can explain the choice instead of just
    naming it.
    """
    recipe = next((r for r in RECIPES if r.goal == goal), None)
    if recipe is None:
        return {"verdict": "UNKNOWN_NO_RECIPE", "goal": goal,
                "reason": "no recipe with that id",
                "goals": [r.goal for r in RECIPES]}

    by_key = {s.key: s for s in SETTINGS}
    steps: List[Dict[str, Any]] = []
    for i, st in enumerate(recipe.steps, start=1):
        row: Dict[str, Any] = {"n": i, "why": st.why, "value": st.value,
                               "applicable": st.applicable}
        if st.setting.startswith("mode:"):
            fam = mode_family(st.setting.split(":", 1)[1])
            if fam is None:          # caught by validate_recipes
                continue
            row.update({
                "kind": "mode", "setting": st.setting, "tab": fam.tab,
                "title": fam.title_en, "title_ja": fam.title_ja,
                "defaults_key": fam.defaults_key,
                "options": [{"key": o.key, "label": o.label_en,
                             "label_ja": o.label_ja, "when": o.when}
                            for o in fam.options],
            })
        else:
            s = by_key.get(st.setting)
            if s is None:
                continue
            row.update({
                "kind": "setting", "setting": s.key, "tab": s.tab,
                "title": s.title_en, "title_ja": s.title_ja,
                "defaults_key": s.defaults_key, "what": s.what,
                "values": list(s.values),
            })
        steps.append(row)

    return {"verdict": "ANSWER", "goal": recipe.goal,
            "title": {"en": recipe.title_en, "ja": recipe.title_ja},
            "summary": recipe.summary, "steps": steps}


def list_goals() -> List[Dict[str, Any]]:
    return [{"goal": r.goal, "title": r.title_en, "title_ja": r.title_ja,
             "summary": r.summary, "steps": len(r.steps)} for r in RECIPES]


def validate_recipes() -> List[str]:
    """Every step must point at something that exists. Run by the eval, so a
    renamed setting breaks the recipe loudly instead of sending a new user to
    a screen that is no longer there."""
    keys = {s.key for s in SETTINGS}
    groups = {f.group for f in MODE_FAMILIES}
    errs: List[str] = []
    for r in RECIPES:
        if not r.steps:
            errs.append(f"{r.goal}: no steps")
        for st in r.steps:
            if st.setting.startswith("mode:"):
                g = st.setting.split(":", 1)[1]
                if g not in groups:
                    errs.append(f"{r.goal}: unknown mode family '{g}'")
                    continue
                fam = mode_family(g)
                if st.value is not None and fam is not None:
                    if st.value not in {o.key for o in fam.options}:
                        errs.append(f"{r.goal}: '{st.value}' is not an option "
                                    f"of mode family '{g}'")
            elif st.setting not in keys:
                errs.append(f"{r.goal}: unknown setting '{st.setting}'")
    return errs
