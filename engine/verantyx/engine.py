"""One boundary. The composition lives here, not in whoever is calling.

Why
---
The composition used to live in the caller. `veraModelTurn` in the IDE's
Swift decides — in Swift — whether a question is a difference, when to
re-ask with the last core as context, and which of the payload's thirty-one
fields become the reply. Measured today: the IDE knows 60 of the 99 doors
and its answering path uses three, so seventeen organs and about six
thousand lines are outside every question anyone asks. A different client
picks a different three and the same engine looks like a different
product — which is exactly what happened when one session measured the
CLI's v0 door and reported it as "the engine".

So the order moves here. A caller asks one thing and gets everything the
engine knows how to bring, and a new binding inherits the whole
composition instead of re-deriving a worse one.

Layered, never pooled
---------------------
Each stage hands the next a better question or annotates the answer.
Nothing here merges two notions of agreement into one vote — that
direction is measured at 6 failures out of 6, against 5 improvements out
of 5 for layering. `ask` still does the answering; this arranges what
reaches it and what is said about what comes back.

What is deliberately absent
---------------------------
No model is called. Nothing is written to the store. Both are properties
worth more than the reach they cost: the first keeps the same question
answering the same way forever, and the second keeps this file from ever
becoming a place where a claim quietly enters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Two subjects and a request to compare them. Closed, because a fuzzy
#: match here sends an ordinary question down the diff path and it comes
#: back as an abstention about the wrong thing.
_DIFF_MARKS = ("の違い", "の差", "と の違い", "はどう違う", "の違いは")
#: A follow-up shaped like it is about the last answer.
_DEICTIC = ("その", "それ", "この", "あの")

#: What a Japanese question puts after its subject. Longest first, so
#: 「とは」 is taken before 「は」 — stripping the shorter one first leaves
#: a stray 「と」 on the subject.
_TOPIC_SUFFIXES = ("とは何ですか", "とは何", "とは", "って何", "って",
                   "は？", "は", "？", "?")


@dataclass
class Turn:
    """One question, and the record of what each stage did with it."""

    query: str
    verdict: str = ""
    text: str = ""
    core: str = ""
    door: str = ""
    tokens: List[str] = field(default_factory=list)
    origins: List[str] = field(default_factory=list)
    readings: Dict[str, Any] = field(default_factory=dict)
    remedy: str = ""
    stages: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def note(self, stage: str, fired: bool, note: str = "",
             changed: bool = False) -> None:
        self.stages.append({"stage": stage, "fired": fired,
                            "changed": changed, "note": note})

    def as_dict(self) -> Dict[str, Any]:
        out = dict(self.raw)
        out.update({"verdict": self.verdict, "text": self.text,
                    "core": self.core, "door": self.door,
                    "tokens": self.tokens, "origins": self.origins,
                    "readings": self.readings, "remedy": self.remedy,
                    "stages": self.stages})
        return out


def _looks_like_diff(q: str) -> Optional[Tuple[str, str]]:
    """(a, b) when the question compares two named things, else None."""
    if not any(m in q for m in _DIFF_MARKS):
        return None
    head = q
    for m in _DIFF_MARKS:
        head = head.split(m)[0]
    for sep in ("と", "、", "vs", "対"):
        if sep in head:
            a, _, b = head.partition(sep)
            a, b = a.strip(), b.strip()
            if a and b:
                return a, b
    return None


def _render(obj: Dict[str, Any]) -> str:
    """The readable answer, from the field that actually carries one.

    `text` alone is a token list — 「傷害罪 傷害 故意犯 狭義 204条」. The
    composed skeletons live under `written.sentences` and a descent's
    prose lives under `units[].definition`; a reply built from `text` was
    showing the reader the index instead of the answer.
    """
    units = obj.get("units")
    if isinstance(units, list):
        defs = [u.get("definition") for u in units
                if isinstance(u, dict) and u.get("definition")]
        if defs:
            return " ".join(defs)
    written = obj.get("written")
    if isinstance(written, dict):
        sents = written.get("sentences")
        if isinstance(sents, list):
            lines = [s.get("text") for s in sents[:3]
                     if isinstance(s, dict) and s.get("text")]
            if lines:
                return " ".join(lines)
    rendered = obj.get("rendered")
    if isinstance(rendered, dict) and rendered.get("text"):
        return str(rendered["text"])
    return str(obj.get("text") or "")


def _origins(obj: Dict[str, Any]) -> List[str]:
    """Sources, from wherever this door keeps them.

    `vera_ask` uses `facet_origin`; `vera_explain` keeps a source per unit.
    Reading only the first is why a console showed 「出典の記録なし」 over
    an answer that named 「jawiki:リンゴ ← りんご」.
    """
    out: List[str] = []
    fo = obj.get("facet_origin")
    if isinstance(fo, dict):
        for v in fo.values():
            if isinstance(v, list):
                out.extend(str(x) for x in v)
    units = obj.get("units")
    if isinstance(units, list):
        out.extend(str(u.get("source")) for u in units
                   if isinstance(u, dict) and u.get("source"))
    seen, uniq = set(), []
    for o in out:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    return uniq


def _readings(obj: Dict[str, Any]) -> Dict[str, Any]:
    """The numbers beside a verdict. A high agreement over thin evidence
    is a different thing from the same number over thick, so both travel."""
    r: Dict[str, Any] = {}
    if obj.get("agree_frac") is not None:
        r["agree"] = obj["agree_frac"]
    if obj.get("e_min") is not None:
        r["evidence_min"] = obj["e_min"]
    g = obj.get("grain")
    if isinstance(g, dict) and g.get("agree") is not None:
        r["grain"] = "%s/%s" % (g.get("agree"), g.get("of"))
    w = obj.get("witnesses")
    if isinstance(w, dict) and w.get("agree") is not None:
        r["witnesses"] = w["agree"]
    if obj.get("tier"):
        r["tier"] = obj["tier"]
    return r


def ask(query: str, vera: Any, *, last_core: str = "",
        domain: str = "", store_path: Any = None, store: Any = None,
        store_first: bool = False, _retry: bool = False,
        circulation: Any = None, observe: bool = True) -> Dict[str, Any]:
    """Everything the engine knows how to bring, for one question.

    `vera` is the loaded stack, passed in rather than loaded here: which
    store answers is the host's decision, and a module that chose for
    itself is how a probe measures the default store and reports it as the
    engine.

    Two spaces, never pooled
    ------------------------
    `vera` is the published federation (ja 89,369 cores, en 15,268).
    `store` is what THIS person put in — every document that arrived
    through `load_documents` lands there and nowhere else. Measured
    2026-08-16 on a contest PDF: 「必須要件」 answered ANSWER from the
    store and UNGROUNDED_UNITS from the federation, because the question
    was being asked of a space the document had never entered.

    Both are asked, and their verdicts are reported side by side. They are
    NOT merged into one vote — that direction is measured at 6 failures
    out of 6. `store_first` says which one gets to be THE answer when both
    have one; it is the person's choice, because "my document is more
    relevant than the encyclopaedia" is a fact about their intent and not
    something this module can measure.
    """
    t = Turn(query=query.strip())
    q = t.query

    # ── before the store is asked ────────────────────────────────────

    from .intent_frames import parse as _intent
    framed = _intent(q)
    if framed.get("verdict") == "INTENT":
        t.note("intent", True, "op=%s" % framed["op"], changed=True)
        t.verdict, t.door = "INTENT", "intent_frames"
        t.raw = framed
        t.text = "指示として読みました。"
        return t.as_dict()
    t.note("intent", True, "問いとして扱う")

    # A repair candidate is COMPUTED here and deliberately NOT applied.
    #
    # It used to be applied, on the reasoning that a misspelt subject
    # fails every later stage identically to an unknown one. Measured, the
    # cost is worse than the disease: 「提出物は」 was repaired to
    # 「提出物件」 and the question stopped reaching a document that had a
    # 提出物 section — a good question rewritten into a different one. The
    # organ's zero-false-fire figure was measured on in-vocabulary words,
    # and a word with a topic particle stuck to it is not one.
    #
    # So repair became a LAST resort. Every stage answers the question as
    # asked, and only when all of them refuse is the candidate tried —
    # once, with the door and the substitution both on the record.
    typo_candidate = ""
    try:
        from .meaning_assets import lattice as _lat
        from .meaning_assets import vocab as _voc
        from .typo_recovery import recover
        core_term = q
        for suf in _TOPIC_SUFFIXES:
            if core_term.endswith(suf) and len(core_term) > len(suf):
                core_term = core_term[: -len(suf)]
                break
        tr = recover(core_term, lattice=_lat(), vocab=_voc())
        if tr.get("verdict") == "TYPO_CANDIDATE" and tr.get("candidates"):
            typo_candidate = q.replace(core_term,
                                       tr["candidates"][0]["word"])
            t.note("typo", True, "候補 %s（まだ使わない）" % typo_candidate)
        else:
            t.note("typo", True, str(tr.get("verdict")))
    except Exception as exc:
        t.note("typo", False, "%s: %s" % (type(exc).__name__, str(exc)[:50]))

    # Arithmetic is a different kind of question, answered by an exact
    # organ rather than by a census. It is asked first because a census
    # asked about 「3+4は」 would return whatever core happens to share a
    # character with it.
    try:
        import re as _re
        from .math_sim import math_ask
        # 「3+4は」 parses as UNKNOWN_UNPARSED with the particle attached.
        # Cut to the expression itself before handing over — a hand-off
        # normalisation, not an interpretation: if no run of arithmetic
        # characters is present, nothing is passed and nothing is claimed.
        # Closed operator words, normalised BEFORE the expression is cut.
        # Measured 2026-08-18 over the chat door: 「3たす4は」 matched only
        # the leading 「3」 (たす breaks the character class), math_ask("3")
        # answered ANSWER 3, and the engine asserted a wrong number with a
        # straight face. Two rules close the class:
        #   1. たす/ひく/かける/わる (and kanji forms) become +-*/ first —
        #      a hand-off normalisation from a closed table, no parsing.
        #   2. an expression with NO operator is not an arithmetic question.
        #      A lone number is what the old regex fabricated from; nothing
        #      is passed and the stages below get their turn.
        _qm = q
        for _w, _op in (("たす", "+"), ("足す", "+"), ("プラス", "+"),
                        ("ひく", "-"), ("引く", "-"), ("マイナス", "-"),
                        ("かける", "*"), ("掛ける", "*"),
                        ("わる", "/"), ("割る", "/")):
            _qm = _qm.replace(_w, _op)
        _mx = _re.search(r"[0-9０-９][-+*/^=()0-9０-９xX\s.,]*", _qm)
        _expr = _mx.group(0).strip() if _mx else ""
        if _expr and not _re.search(r"[-+*/^=]", _expr):
            _expr = ""
        m = math_ask(_expr) if _expr else {"verdict": "UNKNOWN_NO_EXPR"}
        if not str(m.get("verdict", "UNKNOWN")).startswith("UNKNOWN"):
            t.note("math", True, str(m.get("verdict")), changed=True)
            t.raw, t.door = m, "math_sim"
            t.verdict = str(m.get("verdict"))
            # math_ask answers in `value`; an empty text made the chat
            # door print the verdict name instead of the number.
            _val = m.get("text") or m.get("answer")
            if _val in (None, "") and m.get("value") is not None:
                _val = m.get("value")
            t.text = str(_val if _val is not None else "")
            return t.as_dict()
        t.note("math", True, str(m.get("verdict")))
    except Exception as exc:
        t.note("math", False, "%s: %s" % (type(exc).__name__, str(exc)[:50]))

    # A theorem's proof status is not a census question either: the
    # answer is a Lean kernel run that happened, and 73,881 of them are
    # recorded. Absence of a witness is never a claim of falsehood.
    try:
        from .mathlib_witness import looks_like_declaration
        from .mathlib_witness import lookup as _ml
        _cand = q.replace("とは", "").replace("は証明済みですか", "").strip()
        if looks_like_declaration(_cand):
            w = _ml(_cand)
            if not str(w.get("verdict", "")).startswith("UNKNOWN"):
                t.note("mathlib", True, str(w.get("verdict")), changed=True)
                t.raw, t.door = w, "mathlib_witness"
                t.verdict = str(w.get("verdict"))
                return t.as_dict()
            t.note("mathlib", True, str(w.get("verdict")))
        else:
            t.note("mathlib", True, "宣言名ではない")
    except Exception as exc:
        t.note("mathlib", False,
               "%s: %s" % (type(exc).__name__, str(exc)[:50]))

    # What a loaded document literally says. Asked FIRST, and before the
    # store's own index, because this is the only stage that can quote —
    # everything after it answers with words it selected, and a question
    # about a document the person just handed over should get the
    # document's own sentence when the document has one.
    if store_path is not None:
        try:
            from .document_structure import load as _docs_load
            from .document_structure import lookup as _docs_lookup
            book = _docs_load(store_path)
            # 多者間の複合文は単一主題の経路では扱えない — 事象分解が先。
            # 実測 2026-08-19: 「aがbを脅してbがcを傷つけたbに科される
            # 罪名は」が meaning_descent へ落ち、「…罪名はは、格子の分解
            # 単位を持たない」という無意味な出力になっていた。2事象以上を
            # 検出したらここで引き受け、当事者の名指し(bに科される)にも
            # 応じる。文書が無ければ各事象が型付き拒否のまま並ぶ — それが
            # 「刑法等を投入すれば答わる」という正直な案内になる。
            try:
                from .multi_party import analyze_for_engine as _mp
                _m = _mp(q, book)
            except Exception:
                _m = None
            if _m is not None:
                t.note("multi_party", True,
                       "%d事象%s" % (len(_m.get("events") or []),
                                    "・%s名指し" % _m["asked_actor"]
                                    if _m.get("asked_actor") else ""),
                       changed=True)
                t.raw, t.door = _m, "multi_party"
                t.verdict = str(_m.get("verdict"))
                t.core = str(_m.get("asked_actor") or "")
                t.text = str(_m.get("text") or "")
                t.origins = sorted({str(e.get("source"))
                                    for e in _m.get("per_event") or []
                                    if e.get("source")}) or []
                t.readings = {"quoted": True}
                return t.as_dict()
            if book.get("documents"):
                subj = q
                for suf in _TOPIC_SUFFIXES:
                    if subj.endswith(suf) and len(subj) > len(suf):
                        subj = subj[: -len(suf)]
                        break
                dr = _docs_lookup(subj, book)
                dv = str(dr.get("verdict", ""))
                if dv in ("DOCUMENT_SECTION", "DOCUMENT_LABEL",
                          "DOCUMENT_LINE", "DOCUMENT_NOT_SPECIFIED"):
                    t.note("document", True,
                           "%s ← %s" % (dv, dr.get("source")), changed=True)
                    # 引用行の言葉だけで紡いだ下書きを、引用の隣に。
                    # 8/18に却下した文書側生成の門つき再挑戦 — 実測
                    # 2026-08-19: 断片0・汚染0・引用外の内容語0(7問)。
                    # verdict にも引用にも触れない。
                    if getattr(vera, "writer", None) is not None:
                        try:
                            from .stacked import quote_in_words
                            _qw = quote_in_words(dr, vera.writer)
                            if _qw:
                                dr["written"] = _qw
                        except Exception:
                            pass
                    t.raw, t.door = dr, "document"
                    t.verdict = dv
                    t.core = str(dr.get("subject") or "")
                    t.text = str(dr.get("text") or "")
                    t.origins = [str(dr.get("source") or "読み込んだ文書")]
                    t.readings = {"quoted": True}
                    t.remedy = ""
                    if dv == "DOCUMENT_NOT_SPECIFIED":
                        # 文書の型付き「明記なし」は不足知識の名指しそのもの
                        # (2026-08-19、操作者検収)。この扉は早期returnで、
                        # 末尾の gaps 段に届かず台帳が空回りしていた —
                        # ここで登録する。create は重複を再利用する。
                        try:
                            from .gap_graph import (GapGraph, gap_graph_path,
                                                    refusal_to_gap)
                            _gp = gap_graph_path(store_path)
                            _g = GapGraph.load(_gp)
                            _gid = refusal_to_gap(
                                _g, str(dr.get("subject") or q), dv,
                                branch="engine.document", resolved=False)
                            _g.save(_gp)
                            t.note("gaps", True, "欠落を台帳へ登録 %s" % _gid)
                        except Exception as _ge:
                            t.note("gaps", False, type(_ge).__name__)
                    return t.as_dict()
                t.note("document", True, dv)
            else:
                t.note("document", True, "読み込んだ文書は無い")
        except Exception as exc:
            t.note("document", False,
                   "%s: %s" % (type(exc).__name__, str(exc)[:50]))

    # The person's own documents. Asked as its own stage with its own
    # door name, so an answer that came from a PDF someone loaded can
    # never be mistaken for one the federation vouched for.
    local: Optional[Dict[str, Any]] = None
    if store is not None:
        try:
            from .consensus_store import consensus_over_store
            # The store indexes subjects, not sentences: measured, 「必須要件」
            # answers ANSWER and 「必須要件は」 answers UNKNOWN_NO_EVIDENCE —
            # the same question, one topic particle apart. The federation
            # path strips 「とは」 in its descent and the store path never
            # did, which is the whole reason a loaded document looked
            # unreachable. A hand-off normalisation, not an interpretation.
            forms = [q]
            bare = q
            for suf in _TOPIC_SUFFIXES:
                if bare.endswith(suf) and len(bare) > len(suf):
                    bare = bare[: -len(suf)]
                    break
            if bare != q:
                forms.append(bare)
            lo, lv, used = None, "", q
            for form in forms:
                cand = consensus_over_store(store, form)
                cv = str(cand.get("verdict", ""))
                lo, lv, used = cand, cv, form
                if not cv.startswith(("UNKNOWN", "ABSTAIN", "AMBIGUOUS")):
                    break
            if used != q:
                t.note("store_form", True, "%s → %s" % (q, used))
            if lo is not None and not lv.startswith(
                    ("UNKNOWN", "ABSTAIN", "AMBIGUOUS")):
                local = lo
                t.note("store", True, "%s core:%s" % (lv, lo.get("core")),
                       changed=store_first)
                if store_first:
                    t.raw, t.door = lo, "store"
                    t.verdict, t.core = lv, str(lo.get("core") or "")
                    t.text = _render(lo)
                    t.tokens = list(lo.get("tokens") or [])
                    t.origins = _origins(lo) or ["この端末に入れた文書"]
                    t.readings = _readings(lo)
                    return t.as_dict()
            else:
                t.note("store", True, lv)
        except Exception as exc:
            t.note("store", False,
                   "%s: %s" % (type(exc).__name__, str(exc)[:50]))

    pair = _looks_like_diff(q)
    if pair:
        try:
            from .meaning_assets import aliases, empty_shelf, profiles, senses
            from .structural_diff import diff as _diff
            from .meaning_assets import lattice as _lat
            d = _diff(pair[0], pair[1], profiles=profiles(),
                      aliases=aliases(), lattice=_lat(),
                      shelf=empty_shelf(), senses=senses())
            t.note("diff", True, "%s / %s" % pair, changed=True)
            t.raw, t.door = d, "structural_diff"
            t.verdict = str(d.get("verdict", "UNKNOWN"))
            t.text = _render(d)
            # DIFF の payload は shared/only_a/only_b に層・辺つきの
            # トークンを持つのに、_render がこの形を知らず「（DIFF）」と
            # だけ出ていた(実測 2026-08-19: 傷害罪と窃盗罪の違いは)。
            # 中身をそのまま行に並べる — 「Aのみ」は Bについて実測が
            # 無いという意味であって、Bに無いという否定の主張ではない。
            if t.verdict == "DIFF" and (not t.text or t.text == "（DIFF）"):
                def _toks(key):
                    seen, out = set(), []
                    for it in d.get(key) or []:
                        tok = str(it.get("token") or "")
                        if tok and tok not in seen:
                            seen.add(tok)
                            out.append(tok)
                    return out
                a, b = str(d.get("a") or pair[0]), str(d.get("b") or pair[1])
                sh, oa, ob = _toks("shared"), _toks("only_a"), _toks("only_b")
                lines = ["%s と %s の構造差分" % (a, b)]
                if sh:
                    lines.append("共有: " + "・".join(sh[:8])
                                 + ("（+%d）" % (len(sh) - 8) if len(sh) > 8 else ""))
                if oa:
                    lines.append("%s のみ: " % a + "・".join(oa[:8])
                                 + ("（+%d）" % (len(oa) - 8) if len(oa) > 8 else ""))
                if ob:
                    lines.append("%s のみ: " % b + "・".join(ob[:8])
                                 + ("（+%d）" % (len(ob) - 8) if len(ob) > 8 else ""))
                lines.append("（「のみ」は相手側に実測が無いという意味で、"
                             "無いという主張ではない）")
                t.text = "\n".join(lines)
            return t.as_dict()
        except Exception as exc:
            # Recorded, never swallowed: a stage that failed silently is
            # indistinguishable from one that was never built, and that
            # is how organs stay dead.
            t.note("diff", False, "%s: %s" % (type(exc).__name__, str(exc)[:60]))
    else:
        t.note("diff", True, "比較の形ではない")

    # ── the census ───────────────────────────────────────────────────

    # ── 巡回と観測 ────────────────────────────────────────────────────
    # `circulation` is the conversation's terminal arrangements, per core —
    # the search re-enters the structure where the last turn left it instead
    # of bare. `observe` turns on the placement-invariance re-ask that had
    # been implemented and dormant since 8/14: the arbitrary half of the
    # placement is reversed and an ANSWER the two readings disagree about is
    # downgraded. Both are inputs; determinism holds.
    #
    # Default ON since 2026-08-19. It was off pending a real-store
    # measurement, and that measurement now exists (experiments/
    # placement_matryoshka_recheck/): on vera.db ja (89,369 cores, 300
    # planted probes) the gate demoted 4 of 546 ANSWERs, all four wrong,
    # zero correct answers lost. Real mass distributions rarely tie, so it
    # fires ~0.7% of the time — cheap insurance, not a large effect. What
    # the flip actually fixes is a split brain: vera_chat passed
    # observe=True while vera_engine and the CLI ran the old default False,
    # so the same engine was more honest through one door than another.
    # One sovereign means the same gates at every door.
    _ck: Dict[str, Any] = {}
    if circulation:
        _ck["circulation"] = circulation
        # 軸のロックは循環に載って**次の問い**で効く(2026-08-21)。
        # seed_state は既に locks の席を持っていたが、誰も埋めていな
        # かった — 構想(これまで.pdf)の中核が席だけあった状態。
        # 埋めるのは「配置不変を生き延び、facet が同点でない」腕だけ。
    if observe:
        _ck["placement_invariant"] = True

    # ── 推論核が主席に座る ────────────────────────────────────────────
    # 断面が縁から入り、エネルギー比率が経路を決め、安定状態で一致した
    # 断面の軸語が連結される — consensus.py。この器官は 2026-08-18 まで
    # engine.ask から一度も呼ばれていなかった。実装から到達可能なのに、
    # 主経路は census(stacked) を通り、SEEDED は同じ節の言い直しを3つ
    # 並べていた。「未接続だと書いたのは私です」の同じ形。
    #
    # 配線の前に二つ測った。① 本番連合(ja 89,369核)で核は 0.03秒で動き、
    # census より濃い: 正当防衛とは → 「行為、防衛、成立、他人」(4断面)
    # 対 census「行為の成立です/となる/をもたらした」(1節×3)。② ただし
    # 問い側に取り込み側と同じ複合語の盗みが残っており、蔵書外8語で
    # 6件捏造した(クワンタムフラックス炉 → 核 炉 → ANSWER)。門を先に
    # 立て(捏造 6→0、蔵書内 6/7 不変、forks 153/153)、それからここに
    # 座らせた。順序が逆なら、103,599件の修理で回復した「連邦は嘘を
    # つかない」を問い側から壊すところだった。
    #
    # 束ねず重ねる: 核が ANSWER のときだけ主席。型付き沈黙なら census
    # (階段の種・SEEDED)が従来どおり受ける — 「殺人罪の刑は」は核が
    # 二主題の不収束で正直に棄権し、階段が 殺人罪 を種に SEEDED で
    # 答える。二つの器官は同じ選挙で投票しない。
    obj: Dict[str, Any] = {}
    t.door = "vera_ask"
    try:
        _ja = getattr(vera, "stores", {}).get("ja") if hasattr(vera, "stores") else None
        if _ja is not None:
            from .consensus_store import ja_consensus_ask as _core_ask
            _c = _core_ask(_ja, q, placement_invariant=bool(observe))
            if str(_c.get("verdict")) == "ANSWER":
                obj = dict(_c)
                t.door = "consensus_core"
                t.note("core", True, "断面収束 " + str(_c.get("retrieved"))[:40],
                       changed=True)

                # Writer は census 経路(vera.py の Vera.ask)には既に繋がって
                # いた(in_words)。核をここに座らせた時点でそこを迂回して
                # おり、核の答えは文にならないまま出ていた。
                #
                # in_words は text.split() で空白区切りのトークン列を前提に
                # する — census の text は元々そう作られている。核の text
                # は「核+は+読点区切り」の完成文字列("正当防衛は行為、防衛、
                # 成立、他人")で、split() すると全体が1トークンになり
                # UNKNOWN_SUBJECT_NOT_A_WORD で毎回沈黙していた(実測5問中
                # 5問)。核は既に tokens を持つので、それを空白区切りにした
                # 一時コピーだけを in_words に渡す — obj["text"] 自体は
                # 変えない。
                #
                # 実測: 5/6 が文になった(1件は元の核が AMBIGUOUS で対象外)。
                #   正当防衛は行為、防衛、成立、他人
                #     → 正当防衛は、行為の成立です。
                #   超伝導は発見、現象、オンネス、カメルリング
                #     → 超伝導も発見されている。
                # 「時効、成立とよばれることもある」のような不自然な文も
                # 混じる — 文型と語彙のミスマッチという Writer 既知の限界
                # で、ここで直すものではない。verdict と text はそのまま。
                # written は隣に添えるだけで、票にも判定にも入らない。
                if getattr(vera, "writer", None) is not None and obj.get("tokens"):
                    try:
                        from .stacked import in_words as _in_words
                        _sp = dict(obj)
                        _sp["text"] = " ".join(obj["tokens"])
                        # 文量は経路の語数に応じて可変: 語2つなら1文、
                        # 5語以上なら3文まで。量を決めるのは内容の供給。
                        _lim = max(1, min(3, len(obj["tokens"]) - 2))
                        _w = _in_words(_ja, _sp, vera.writer, limit=_lim,
                                       edge_partners=getattr(
                                           vera, "edge_partners", None))
                        if _w.get("sentences"):
                            obj["written"] = _w
                    except Exception:
                        pass
            elif str(_c.get("verdict")) in ("REVERSE_UNIQUE",
                                            "REVERSE_SPECIFIC"):
                # 逆方向の唯一候補(2026-08-19)。順方向は棄権したが、
                # 問いを最も覆う核が唯一で被覆≥2語 — SEEDED と同じ
                # 非昇格の型付き回答として座る。census には落とさない:
                # 逆方向が既に到達経路(覆った語)ごと答えを名乗っており、
                # 後段が同じ語で別の答えを作れば二重投票になる。
                # REVERSE_SPECIFIC は帯割れの特定性裁定(次点の5倍以上で
                # 孤立)— 同じ座席、同じ非昇格、裁定根拠(margin/次点)持参。
                obj = dict(_c)
                t.door = "reverse_coverage"
                t.note("core", True, "%s 被覆%s" %
                       ("逆方向唯一" if _c.get("verdict") == "REVERSE_UNIQUE"
                        else "逆方向特定 margin%s" % _c.get("specificity_margin"),
                        _c.get("reverse_coverage")), changed=True)
    except Exception as _e:  # 核の障害は沈黙ではなく後段へ渡す
        t.note("core", False, type(_e).__name__)
    if not obj:
        # 盗まれた部品で選挙を開かない。核の門が「この問いの主題は店に
        # 無い」と言ったのに census へ落とすと、census が同じ一片を種に
        # して答えを作る。実測: ぷにゃぷにゃ理論とは で核は正しく棄権し、
        # 後退路が SEEDED「理論や問題が説明である」を返した — 捏造が
        # 門の下をくぐった。主題が一つも立たない日本語の問いは census を
        # 飛ばし、型付き沈黙のまま降下段(単位・棚定義)へ渡す。
        _skip_census = False
        if _ja is not None:
            try:
                from .consensus_store import ja_subject_runs as _jsr
                from .lang import ja_content_runs as _jcr
                if _jcr(q) and not _jsr(_ja, q):
                    _skip_census = True
            except Exception:
                pass
        if _skip_census:
            obj = {"verdict": "UNKNOWN_NO_EVIDENCE",
                   "note": "問いの主題として独立に立つ連が店に無い。"
                           "複合語の一片では選挙を開かない"}
        else:
            obj = dict(vera.ask(q, **_ck))
    t.note("ask", True, str(obj.get("verdict")))

    # Context as a VISIBLE operation. A short follow-up, or one opening
    # with a deictic, is re-asked with the last answered core added — and
    # the completion is printed, because an invisible context resolution
    # is the same shape of lie as an invisible ingest.
    if str(obj.get("verdict", "")).startswith("UNKNOWN") and last_core and (
            len(q) <= 10 or q.startswith(_DEICTIC)):
        stripped = q
        for d in _DEICTIC:
            if stripped.startswith(d):
                stripped = stripped[len(d):]
        retry = dict(vera.ask("%s %s" % (last_core, stripped), **_ck))
        if not str(retry.get("verdict", "")).startswith("UNKNOWN"):
            obj = retry
            t.note("context", True,
                   "直近の核「%s」を条件に補完" % last_core, changed=True)
        else:
            t.note("context", True, "補完しても届かない")

    # Descent when the census has nothing. Constructed, and it says so in
    # its own payload — this is the only route by which 「りんごとは」 has
    # ever answered.
    if str(obj.get("verdict", "")).startswith("UNKNOWN"):
        try:
            from .meaning_assets import aliases as _al
            from .meaning_assets import defs as _defs
            from .meaning_assets import lattice as _lat
            from .meaning_descent import descend
            term = q.replace("とは", "").replace("？", "").strip()
            d = descend(term, lattice=_lat(), defs=_defs(), aliases=_al())
            if d and not str(d.get("verdict", "")).startswith("UNKNOWN"):
                obj, t.door = d, "meaning_descent"
                t.note("descend", True, str(d.get("verdict")), changed=True)
            else:
                t.note("descend", True, "届かない")
        except Exception as exc:
            t.note("descend", False,
                   "%s: %s" % (type(exc).__name__, str(exc)[:60]))
    else:
        t.note("descend", True, "不要")

    # ── what is said about what came back ────────────────────────────

    t.raw = obj
    t.verdict = str(obj.get("verdict", "UNKNOWN"))
    t.core = str(obj.get("core") or "")
    t.text = _render(obj)
    t.tokens = list(obj.get("tokens") or [])
    t.origins = _origins(obj)
    t.readings = _readings(obj)
    t.remedy = str(obj.get("remedy") or "")

    # Facets become claims where a cue licenses it, and stay facets where
    # none does. Annotation only — nothing here changes the verdict.
    try:
        from .arm_schema import classify_arm
        claims = []
        for f in t.tokens[:8]:
            arm = classify_arm("%sは%sである" % (t.core, f)) if t.core else None
            if arm:
                claims.append("%s --%s--> %s" % (t.core, arm, f))
        t.note("arms", True, " / ".join(claims[:3]) if claims
               else "手がかり無し — 面のまま")
    except Exception as exc:
        t.note("arms", False, str(exc)[:60])

    # The federation had nothing and the person's own documents did. This
    # is a fall-through between two spaces, not a merge: the door changes
    # to `store`, so the reader always knows which space spoke.
    if local is not None and t.verdict.startswith(
            ("UNKNOWN", "ABSTAIN", "AMBIGUOUS", "UNGROUNDED")):
        t.note("store", True, "連合は答えず、端末の文書が答えた", changed=True)
        if getattr(vera, "writer", None) is not None:
            try:
                from .stacked import quote_in_words
                _qw = quote_in_words(local, vera.writer)
                if _qw:
                    local["written"] = _qw
            except Exception:
                pass
        t.raw, t.door = local, "store"
        t.verdict = str(local.get("verdict"))
        t.core = str(local.get("core") or "")
        t.text = _render(local)
        t.tokens = list(local.get("tokens") or [])
        t.origins = _origins(local) or ["この端末に入れた文書"]
        t.readings = _readings(local)
        return t.as_dict()
    if local is not None:
        # Both answered. The federation's verdict stands, and the store's
        # is carried BESIDE it rather than folded in — a reader deciding
        # between an encyclopaedia and their own PDF should see both.
        t.raw["local"] = {"verdict": local.get("verdict"),
                          "core": local.get("core"),
                          "text": _render(local),
                          "note": "この端末に入れた文書。連合とは別の空間"}

    # Everything refused and a repair candidate exists. Asked once, with
    # the substitution named — never silently, because an answer about a
    # word the person did not type is a different answer.
    if (typo_candidate and not _retry
            and t.verdict.startswith(("UNKNOWN", "ABSTAIN", "AMBIGUOUS",
                                      "UNGROUNDED"))):
        again = ask(typo_candidate, vera, last_core=last_core,
                    domain=domain, store_path=store_path, store=store,
                    store_first=store_first, _retry=True)
        av = str(again.get("verdict", ""))
        if not av.startswith(("UNKNOWN", "ABSTAIN", "AMBIGUOUS",
                              "UNGROUNDED")):
            again["stages"] = t.stages + [
                {"stage": "typo", "fired": True, "changed": True,
                 "note": "%s → %s で聞き直した" % (q, typo_candidate)}
            ] + list(again.get("stages") or [])
            again["repaired_from"] = q
            return again

    # A refusal says what is missing; the gap graph may already hold a
    # named ticket for it. Annotation only — a gap does not become a fact
    # by being mentioned beside one.
    if t.verdict.startswith(("UNKNOWN", "ABSTAIN", "AMBIGUOUS",
                             "NOT_", "UNGROUNDED")) or \
            t.verdict == "DOCUMENT_NOT_SPECIFIED":
        # DOCUMENT_NOT_SPECIFIED も欠落(2026-08-19、操作者検収): 文書に
        # 「その語が無い」という型付き拒否は、まさに不足知識の名指し。
        try:
            if store_path is None:
                raise ValueError("store_path 未指定（欠落台帳は店に紐づく）")
            from .gap_graph import GapGraph, gap_graph_path, refusal_to_gap
            _gp = gap_graph_path(store_path)
            g = GapGraph.load(_gp)
            hit = g.find_by_scope_subject("meaning", t.core) if t.core else None
            # 台帳への書き込み(2026-08-19)。refusal_to_gap は agent_forks
            # にしか配線されておらず、ask 経路の拒否は一度も台帳に届いて
            # いなかった — 「unknown時にどの知識が不足かを見れる」の
            # 蓄積側の欠落。名指しの主題は、不足語(明記なしの subject /
            # ungrounded_units)を問いより優先する。create は重複を再利用
            # するので同じ穴は一枚のまま。
            _missing = ""
            _d = t.data if isinstance(getattr(t, "data", None), dict) else {}
            if obj.get("verdict") == "DOCUMENT_NOT_SPECIFIED":
                _missing = str(obj.get("subject") or "")
            elif obj.get("ungrounded_units"):
                _missing = "、".join(map(str, obj["ungrounded_units"][:3]))
            gid = refusal_to_gap(g, _missing or q, t.verdict,
                                 branch="engine.ask", resolved=False)
            g.save(_gp)
            t.note("gaps", True,
                   ("既知の欠落 %s (%s)" % (hit.gap_id, hit.status)) if hit
                   else ("欠落を台帳へ登録 %s" % gid))
        except Exception as exc:
            t.note("gaps", False,
                   "%s: %s" % (type(exc).__name__, str(exc)[:50]))

    # Nothing readable came back but the store holds the subject: compose
    # one clause from its observed frame rather than showing the reader a
    # token list. Marked `constructed`, never testimony.
    if not t.text and t.core:
        try:
            from .compose_frame import Tables, compose
            tab = Tables.indexed(domain)
            if tab is not None:
                c = compose(t.core, tab)
                if c.get("text"):
                    t.text = c["text"]
                    t.raw["constructed"] = True
                    t.note("compose", True, c["text"][:60], changed=True)
                else:
                    t.note("compose", True, str(c.get("verdict")))
        except Exception as exc:
            t.note("compose", False,
                   "%s: %s" % (type(exc).__name__, str(exc)[:50]))

    if t.remedy:
        t.note("remedy", True, t.remedy[:80])
    return t.as_dict()
