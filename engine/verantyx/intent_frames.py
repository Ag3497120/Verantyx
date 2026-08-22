"""Closed intent frames — verb→operation table plus case-particle arms.

SPEC_2026-08-14_eight_gaps W1b. Instruction understanding is a finite
lookup, not an open-vocabulary guess. A Japanese verb that sits in
VERB_TABLE folds through a closed conjugation table onto a typed
operation; を/に/で/から/まで mark argument arms. Anything outside
those two tables is UNKNOWN_INTENT. No LLM, no morphological invention
beyond the conjugation suffixes listed here.

Output is one of

    {"verdict": "INTENT", "op": <str>, "args": {…}}
    {"verdict": "INTENT", "op": [<str>, …], "args": [{…}, …]}
    {"verdict": "UNKNOWN_INTENT"}

The list form is only for a clearly sequential 〜して、〜する chain.
Two in-table verbs joined by または/か, a verbless fragment, or a
verb the table does not name, all refuse. Alias resolution of the
literal noun phrases is the caller's job.

## Measured — intent_bank_2026-08-14 (see tools/measure_intent_frames.py)

    exact 50/50   op-only 50/50   refusal 15/15 (pass line)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Closed verb inventory. (dict_form, op, class). 48 entries, 28 ops.
# class is the conjugation row — never inferred from the ending.
# ---------------------------------------------------------------------------

#: ichidan = drop る; suru = drop する; ku/su/mu/ru/bu = godan row.
VERBS: Tuple[Tuple[str, str, str], ...] = (
    ("開く", "OPEN", "ku"),
    ("開ける", "OPEN", "ichidan"),
    ("起動する", "OPEN", "suru"),
    ("閉じる", "CLOSE", "ichidan"),
    ("閉める", "CLOSE", "ichidan"),
    ("終了する", "CLOSE", "suru"),
    ("探す", "SEARCH", "su"),
    ("検索する", "SEARCH", "suru"),
    ("調べる", "SEARCH", "ichidan"),
    ("覚える", "REMEMBER", "ichidan"),
    ("記録する", "REMEMBER", "suru"),
    ("忘れる", "FORGET", "ichidan"),
    ("削除する", "FORGET", "suru"),
    ("消す", "FORGET", "su"),
    ("まとめる", "SUMMARIZE", "ichidan"),
    ("要約する", "SUMMARIZE", "suru"),
    ("読む", "READ", "mu"),
    # 「見る」→ READ, not CHECK. 確認する(CHECK) asks whether something
    # holds; 「課題を見て」 asks for the contents to come back. The
    # downstream act is the same one 読む names — read the thing and
    # report it — so they share an op rather than splitting the frame
    # over a distinction the caller never makes.
    ("見る", "READ", "ichidan"),
    ("書く", "WRITE", "ku"),
    ("実行する", "RUN", "suru"),
    ("止める", "STOP", "ichidan"),
    ("停止する", "STOP", "suru"),
    ("やめる", "STOP", "ichidan"),
    ("送る", "SEND", "ru"),
    ("送信する", "SEND", "suru"),
    ("コミットする", "COMMIT", "suru"),
    ("プッシュする", "PUSH", "suru"),
    ("測る", "MEASURE", "ru"),
    ("測定する", "MEASURE", "suru"),
    ("比べる", "COMPARE", "ichidan"),
    ("比較する", "COMPARE", "suru"),
    ("作る", "CREATE", "ru"),
    ("作成する", "CREATE", "suru"),
    ("保存する", "SAVE", "suru"),
    ("表示する", "SHOW", "suru"),
    ("見せる", "SHOW", "ichidan"),
    ("選ぶ", "SELECT", "bu"),
    ("選択する", "SELECT", "suru"),
    ("追加する", "ADD", "suru"),
    ("更新する", "UPDATE", "suru"),
    ("変える", "CHANGE", "ichidan"),
    ("変更する", "CHANGE", "suru"),
    ("確認する", "CHECK", "suru"),
    ("説明する", "EXPLAIN", "suru"),
    ("コピーする", "COPY", "suru"),
    ("移動する", "MOVE", "suru"),
    ("開始する", "START", "suru"),
    ("インストールする", "INSTALL", "suru"),
)

OPS: Tuple[str, ...] = tuple(dict.fromkeys(op for _d, op, _c in VERBS))

# Closed conjugation suffixes per class. Positive / request / polite /
# desiderative / imperative / volitional / conditional only. Negatives
# (〜ない) and passives (〜られる) are absent: those forms refuse.
_SUFFIX: Dict[str, Tuple[str, ...]] = {
    "ichidan": (
        "てください", "て下さい", "たいです", "ました",
        "る", "ます", "たい", "て", "た", "ろ", "よ", "よう", "れば",
    ),
    "suru": (
        "してください", "して下さい", "したいです", "しました",
        "する", "します", "したい", "して", "した",
        "しろ", "せよ", "しよう", "すれば",
    ),
    "ku": (
        "いてください", "いて下さい", "きたいです", "きました",
        "く", "きます", "きたい", "いて", "いた", "け", "こう", "けば",
    ),
    "su": (
        "してください", "して下さい", "したいです", "しました",
        "す", "します", "したい", "して", "した", "せ", "そう", "せば",
    ),
    "mu": (
        "んでください", "んで下さい", "みたいです", "みました",
        "む", "みます", "みたい", "んで", "んだ", "め", "もう", "めば",
    ),
    "ru": (
        "ってください", "って下さい", "りたいです", "りました",
        "る", "ります", "りたい", "って", "った", "れ", "ろう", "れば",
    ),
    "bu": (
        "んでください", "んで下さい", "びたいです", "びました",
        "ぶ", "びます", "びたい", "んで", "んだ", "べ", "ぼう", "べば",
    ),
}

_TE_ENDS: Tuple[str, ...] = (
    "てください", "でください", "て下さい", "で下さい",
    "て", "で",
)


def _stem(dict_form: str, cls: str) -> str:
    if cls == "suru":
        if not dict_form.endswith("する"):
            raise ValueError(f"suru verb without する: {dict_form}")
        return dict_form[:-2]
    if cls == "ichidan":
        if not dict_form.endswith("る"):
            raise ValueError(f"ichidan verb without る: {dict_form}")
        return dict_form[:-1]
    return dict_form[:-1]


def _build_conj() -> Tuple[Dict[str, Tuple[str, str]], Tuple[str, ...]]:
    """form → (dict_form, op). A form that would map to two ops is dropped."""
    table: Dict[str, Tuple[str, str]] = {}
    clash: set = set()
    for dict_form, op, cls in VERBS:
        stem = _stem(dict_form, cls)
        if not stem:
            continue
        for suf in _SUFFIX[cls]:
            form = stem + suf
            prev = table.get(form)
            if prev is None:
                table[form] = (dict_form, op)
            elif prev[1] != op:
                clash.add(form)
            # same op, two dicts (開け → 開く / 開ける): keep the first.
    for form in clash:
        table.pop(form, None)
    order = tuple(sorted(table, key=lambda s: (-len(s), s)))
    return table, order


CONJ_TABLE, CONJ_FORMS = _build_conj()

# ---------------------------------------------------------------------------
# Surface cleanup — closed lists only.
# ---------------------------------------------------------------------------

_FILLERS: Tuple[str, ...] = (
    "すみませんが", "すみません", "お願いします", "お願いだから",
    "ちょっと", "ねえ", "じゃあ", "それでは", "さて", "まず",
)

_COMPOUND: Tuple[str, ...] = (
    "について", "に対して", "によって", "において", "に関して",
    "に従って", "に応じて", "として",
)

_ALT: Tuple[str, ...] = ("または", "あるいは", "もしくは", "それとも")

_IDLE_TAIL = re.compile(
    r"^(?:よ|ね|な|ぞ|わ|さ|か|の|かな|よね|ほしい|欲しい|くれ|ちょうだい)*"
    r"[。．.！!？?、，,・]*$"
)

_WS = re.compile(r"[\s　]+")

# Case particles that produce an arg, longest first, then topic bounds.
_CASE: Tuple[Tuple[str, Optional[str]], ...] = (
    ("から", "from"),
    ("まで", "to"),
    ("を", "object"),
    ("に", "target"),
    ("で", "means"),
    ("は", None),
    ("が", None),
)


def _normalize(text: str) -> str:
    s = _WS.sub("", (text or "").strip())
    changed = True
    while changed:
        changed = False
        for f in _FILLERS:
            if s.startswith(f):
                s = s[len(f):]
                changed = True
    return s


def fold_verb(form: str) -> Optional[str]:
    """Dictionary form for a conjugated surface, or None if out of table."""
    hit = CONJ_TABLE.get(form)
    return hit[0] if hit else None


def _find_verbs(text: str) -> List[Tuple[int, int, str, str, str]]:
    """Non-overlapping longest-first hits: (start, end, form, dict, op)."""
    n = len(text)
    used = [False] * n
    hits: List[Tuple[int, int, str, str, str]] = []
    for form in CONJ_FORMS:
        start = 0
        flen = len(form)
        while True:
            i = text.find(form, start)
            if i < 0:
                break
            if not any(used[i:i + flen]):
                dict_form, op = CONJ_TABLE[form]
                hits.append((i, i + flen, form, dict_form, op))
                for j in range(i, i + flen):
                    used[j] = True
            start = i + 1
    hits.sort(key=lambda h: h[0])
    return hits


def _is_te_form(form: str) -> bool:
    return any(form.endswith(end) for end in _TE_ENDS)


def _is_sequential(text: str, hits: List[Tuple[int, int, str, str, str]]) -> bool:
    if len(hits) < 2:
        return False
    mid = text[hits[0][0]:hits[-1][0]]
    if any(a in mid for a in _ALT):
        return False
    for i in range(len(hits) - 1):
        gap = text[hits[i][1]:hits[i + 1][0]]
        if "か" in gap:
            return False
        if not _is_te_form(hits[i][2]):
            return False
    return True


def _mask_compounds(span: str) -> str:
    out = span
    for c in _COMPOUND:
        if c in out:
            out = out.replace(c, "\u3000" * len(c))
    return out


def extract_args(span: str) -> Dict[str, str]:
    """Literal NPs marked by を/に/で/から/まで. No alias folding."""
    text = _WS.sub("", (span or "").strip())
    text = text.lstrip("。．.！!？?、，,・")
    if not text:
        return {}
    masked = _mask_compounds(text)
    cuts: List[Tuple[int, int, Optional[str]]] = []
    i = 0
    while i < len(masked):
        hit = None
        for particle, slot in _CASE:
            if masked.startswith(particle, i):
                hit = (i, i + len(particle), slot)
                break
        if hit is None:
            i += 1
            continue
        cuts.append(hit)
        i = hit[1]
    args: Dict[str, str] = {}
    prev = 0
    for start, end, slot in cuts:
        np = _WS.sub("", text[prev:start]).strip()
        prev = end
        if slot and np:
            args[slot] = np
    return args


def parse(text: str) -> Dict[str, Any]:
    """Frame an instruction, or refuse with UNKNOWN_INTENT."""
    unknown: Dict[str, Any] = {"verdict": "UNKNOWN_INTENT"}
    surface = _normalize(text)
    if not surface:
        return unknown
    hits = _find_verbs(surface)
    if not hits:
        return unknown
    tail = surface[hits[-1][1]:]
    if not _IDLE_TAIL.match(tail):
        return unknown
    if len(hits) > 1:
        if not _is_sequential(surface, hits):
            return unknown
        ops: List[str] = []
        arg_list: List[Dict[str, str]] = []
        prev = 0
        for start, end, _form, _d, op in hits:
            ops.append(op)
            arg_list.append(extract_args(surface[prev:start]))
            prev = end
        return {"verdict": "INTENT", "op": ops, "args": arg_list}
    start, _end, _form, _d, op = hits[0]
    return {"verdict": "INTENT", "op": op, "args": extract_args(surface[:start])}
