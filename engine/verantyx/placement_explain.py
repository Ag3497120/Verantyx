"""Where would this sentence land, and why — the placement inspector.

"Adjust the arrangement of your data" is only possible for someone who can
SEE the arrangement. The ingestion pipeline is deterministic, which means
every placement has a stateable reason — which language route fired, which
rule chose the core, which facets survived, whether a pole was placed and
whether the subject gate let it through. This module states those reasons.

The loop it enables needs no programmer:

    1. explain your sentence          → see core / facets / pole / arm
    2. wrong vocabulary missing?      → add a pair to the grammar overlay
    3. explain again                  → confirm the placement changed

That is the whole adjustment interface. There is no knob that reorders
facts by hand, on purpose: hand-placed facts cannot be re-derived from
their sentences, and everything downstream — audits, reproducibility, the
"same corpus, same catalogue" guarantee — rests on placement being a pure
function of text plus grammar data.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from . import ja_grammar
from .arm_schema import classify_arm
from .cross_store import CrossStore
from .lang import detect, ja_chosen_core, ja_content_runs, ja_topic_match
from .polarity import detect as detect_en
from .polarity import detect_ja, subject_is_core


def explain(sentence: str) -> Dict[str, Any]:
    """The full placement decision for one sentence, with reasons."""
    s = (sentence or "").strip()
    if not s:
        return {"verdict": "UNKNOWN_EMPTY", "reason": "no sentence given"}

    lang = detect(s)
    out: Dict[str, Any] = {"verdict": "ANSWER", "sentence": s, "lang": lang}

    if lang in ("ja", "zh"):
        runs = ja_content_runs(s)
        core = ja_chosen_core(s)
        hit = ja_topic_match(s)
        if not runs:
            rule = "none"
        elif core is None:
            rule = "no_identifiable_topic"
        elif hit and not hit[1]:
            rule = "head_of_topic_phrase"
        else:
            rule = "first_content_run"
        out.update({
            "core": core,
            "core_rule": rule,
            "core_rule_note": {
                "head_of_topic_phrase":
                    "は/が の前の句の最後の名詞（主辞後置）。「本町の避難所は」なら 避難所。",
                "first_content_run":
                    "主題標識が無いので最初の内容語。係り先の判断材料が文中に無い。",
                "no_identifiable_topic":
                    "主題が複合語の一部にしか切れない、または括弧内の語義なので格納しない。",
                "none": "内容語が見つからない。この文は格納されない。",
            }[rule],
            "facets": [r for r in runs if r and r != core],
        })
        if lang == "zh":
            out["note"] = ("中国語判定: 分割のみ適用、日本語の極性語彙は適用されない"
                           "（漢字が共通でも文法が別言語のため）")
            out["poles"] = []
            return out
        poles = []
        for aspect, value, pol in detect_ja(s):
            word = value.replace("not_", "")
            gate = subject_is_core(s, core or "", word, "ja")
            poles.append({
                "aspect": aspect, "value": value, "polarity": pol,
                "negated": value.startswith("not_"),
                "subject_gate": gate,
                "placed": gate,
                "gate_note": ("コアが主語なので配置される" if gate else
                              "この極性語の主語がコアではないため配置されない"
                              "（別の名詞への言及と判断）"),
            })
        out["poles"] = poles

    else:
        store = CrossStore()
        core = store.ingest_sentence(s)
        out.update({
            "core": core,
            "core_rule": "en_grammar_pipeline",
            "facets": [f for f, _ in store.top_facets(core or "", k=12)],
        })
        poles = []
        for aspect, value, pol in detect_en(s):
            word = value.replace("not_", "")
            gate = subject_is_core(s, core or "", word, "en")
            poles.append({
                "aspect": aspect, "value": value, "polarity": pol,
                "negated": value.startswith("not_"),
                "subject_gate": gate,
                "placed": gate,
                "gate_note": ("core is the subject of this predicate"
                              if gate else
                              "the polar word predicates something else in "
                              "the sentence, so no pole is placed"),
            })
        out["poles"] = poles

    arm = classify_arm(s)
    out["arm"] = arm
    out["arm_note"] = (f"表層手掛かりにより {arm} アームへ" if arm else
                       "アーム手掛かりなし（because/therefore/is a 等が無い）— "
                       "未タグは正常な状態")

    if out.get("core") and not out["poles"]:
        # The commonest question a user will bring here: "why was no
        # contradiction found". Say which of the two causes applies.
        words = set(ja_grammar.TERMS)
        present = [t for t in words if t in s]
        if present:
            out["pole_note"] = (f"語彙 {present} は文中にあるが門を通らなかった "
                                f"— 複合語の一部か、コア以外の主語")
        else:
            out["pole_note"] = ("既知の対義語彙が文中に無い。矛盾検出の対象に"
                                "するには文法オーバーレイに対を追加する")
    return out
