"""The staircase feeds the inference core. Layered, never pooled.

`consensus` is the original conception and it works: sections enter at the
rim, an edge query changes each node\'s energy, moves rearrange the cross,
and agreement at a stable state ends the search — then the axis words along
the agreed paths are concatenated into an answer with no language model
anywhere. Measured on the 626MB federation, 「過失 故意」 comes back ANSWER
with 「過失 法学 結果的加重犯 引 故意」.

What fails is getting there. `candidates_for_query` returned nothing at all
for 「殺人罪の刑は」, 「傷害罪とは」 and 「相続の順位は」 — three total
failures where the store holds the subject and the entry could not name it.
The staircase can: it reaches 傷害罪 and 相続順位 by coarsening, which is
what it was measured to do.

Seeding the core with what the staircase found turned two of those three
into ANSWER, generated paths included:

    傷害罪とは    -> 傷害罪 傷害 傷害致死罪 死 法学
    相続の順位は   -> 相続順位 法学 相続

## Layered, and that word is doing work

Every combination measured this session divides cleanly:

    POOLED — two signals into one vote, index or store:
      cut-varied sovereigns beside data-varied   out-of-corpus 0 -> 8 wrong
      two languages in one store                 false answers in both
      eleven grain settings instead of six       reach 464 -> 450, false 2 -> 7
      three domain sovereigns instead of one     answered 284 -> 208
      citations merged into the core ladder      0 of 387 gold links
      units and links added to a core\'s terms    385 -> 351 answers

    LAYERED — one stage\'s typed output is the next stage\'s input:
      vocabulary before composition              73% -> 100% attested words
      licence before composition                 49 -> 0 unlicensed norms
      seam test at fill time                     18% -> 0% broken joins
      coverage beside the verdict                bad answers became legible
      staircase before the inference core        3 dead questions -> 2 answers

Six pooled combinations, all worse. Five layered ones, all better. The rule
is not about which parts are good — every part above was measured good on
its own — it is that pooling asks two structures that mean different things
by "agreement" to vote in one election, and layering asks one to hand the
other something it can use.

## What this does not do

Promote. A seeded answer says it was seeded, because the entry was widened
by coarsening and that is exactly the fact a reader needs in order to
discount it. `SEEDED` is not `ANSWER`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def in_words(
    store: Any,
    result: Dict[str, Any],
    writer: Any,
    *,
    limit: int = 2,
    edge_partners: Any = None,
) -> Dict[str, Any]:
    """Put the answer into sentences, using the PATH as the content.

    The inference core already generates: on agreement it concatenates the
    axis words along the converged section paths, natural language
    rearranged with no model anywhere. 「過失 故意」 comes back as
    「過失 法学 結果的加重犯 引 故意」 — the answer, in the query\'s own
    terms, and not a sentence.

    `writer` composes sentences and, on its own, ignores the question: given
    the seed 過失 it walked and produced 「法律ではほとんどストーカーを規定
    している」 as its second sentence. The walk is what drifted, not the
    composition.

    So the path replaces the walk. The centre becomes the subject, the rest
    of the path becomes the available content, and the writer supplies only
    the FORM:

        過失 故意     -> 過失は故意となっている。
        正当防衛とは    -> 正当防衛は行為の成立である。
        遺言 方式     -> 遺言は法律をもつてこれをしなければならない。

    Layered, not pooled: the core decides what the answer is about and the
    writer decides only how to say it. Every draft still carries its content
    source and its form source separately, and a sentence built this way is
    still a draft — it is not the citation, which is the path.
    """
    text = result.get("text")
    if not text:
        return {"verdict": result.get("verdict"), "sentences": [],
                "note": "no converged path to speak from"}
    # A sentence asserts a RELATION between its words — 「時効は光州事件と
    # 制定である」 claims a connection the way a path never does. When the
    # facet order carries no evidence (all counts tied, sequence is a
    # lexicographic accident), composing those facets into a copula is
    # upgrading an artifact into an assertion. The path is still shown; it
    # just is not spoken. Measured before this gate, the sampled sentence
    # stream mixed real relations (地形図は地形断面図ではない) with accidents
    # of the tie-break, and nothing marked which was which.
    if result.get("order_evidence") == "arbitrary":
        # An EDGE re-licences speech: two facets one sentence actually wrote
        # together may be composed, because the relation asserted is one the
        # corpus asserted first. Everything outside an edge stays silent —
        # the order is still an accident, only the attested pairs speak.
        pairs = result.get("edge_pairs") or []
        if not pairs:
            return {"verdict": result.get("verdict"), "sentences": [],
                    "path": [w for w in text.split() if w],
                    "note": "the facets are evidence-tied — an unordered "
                            "set; composing them into a sentence would "
                            "assert relations the corpus never ranked"}
        licensed = sorted({f for pr in pairs for f in pr})
        path0 = [w for w in text.split() if w]
        result = dict(result)
        result["text"] = " ".join(path0[:1] + [f for f in path0[1:]
                                               if f in licensed])
        text = result["text"]
    path = [w for w in text.split() if w]
    if not path:
        return {"verdict": result.get("verdict"), "sentences": []}
    subject, rest = path[0], path[1:]
    if subject not in writer.vocab:
        # Surface conduction: the key centre cannot speak, but activation
        # can flow across arms — every word-core sharing the path's facets
        # is one surface step away, and the word the flow converges on
        # becomes the SPEAKING centre. The key stays the citation.
        from .surface import word_center

        wc = word_center(store, subject, rest, writer.vocab)
        if wc is None:
            return {"verdict": "UNKNOWN_SUBJECT_NOT_A_WORD",
                    "subject": subject, "path": path,
                    "note": "the centre is a retrieval key and not a word "
                            "the corpus writes on its own, and the surface "
                            "flow did not converge on a word; the path "
                            "stands as the answer"}
        subject = wc["word"]
        rest = [f for f in wc["shared"] if f != subject] or rest
        spoken_via = wc
    from .compose_ja import compose

    # Content words are sifted through the vocabulary when enough survive.
    # 「法律　ｃｍは、規定の目的とする。」 put a full-width unit fragment in
    # a sentence because the SUBJECT was vocabulary-gated and the content
    # slots were not. Filtering all content to words would silence most
    # answers (facets are 7.4% words), so the sieve historically applied
    # only when at least two words remained — otherwise the unfiltered
    # rest stood, and the fragment risk was preferred to the silence.
    # 「窃盗罪とは」→「窃盗罪とともに使用の不法領得つである。」 is that
    # fallback speaking: 不法領得つ is a facet clipped mid-word.
    #
    # 2026-08-19: the two-way trade (fragments or silence) dissolves when
    # the word supply grows, so two closed supplies are consulted first:
    #
    #   repair   a non-word facet is trimmed to the LONGEST vocabulary
    #            word it contains (不法領得つ → 不法領得, ≥2 chars).
    #            The unit-decomposition direction, applied at the mouth:
    #            nothing is invented, a clipped word is unclipped.
    #   edges    the core's edge endpoints — pairs some sentence actually
    #            wrote (窃盗罪: 他人/財物/使用/故意/不法領得…) — vocab-
    #            gated. Corpus-derived, so "placement cannot add
    #            information" is not violated; and unlike the facet bag
    #            (7.4% words) the endpoints are overwhelmingly words.
    #
    # Path words still come first — the path is the citation and the
    # edge supply only ever appends. With ≥1 word in hand the fragments
    # are dropped; with none, the old fallback stands unchanged.
    edge_supply: List[str] = []
    if rest:
        worded = [f for f in rest if f in writer.vocab]
        for f in rest:
            if f in writer.vocab:
                continue
            best = ""
            for i in range(len(f)):
                for j in range(len(f), i + 1, -1):
                    if j - i >= 2 and j - i > len(best) and f[i:j] in writer.vocab:
                        best = f[i:j]
            if best and best not in worded:
                worded.append(best)
        if edge_partners is not None and len(worded) < 4:
            try:
                for w in (edge_partners(path[0]) or []):
                    if w in writer.vocab and w not in worded and w != subject:
                        worded.append(w)
                        edge_supply.append(w)
                    if len(worded) >= 8:
                        break
            except Exception:
                pass
        if worded:
            rest = worded[:8]

    # Path-driven speech carries PRESENCE evidence only — counts, edges,
    # co-occurrence — and presence licenses neither negation nor a norm.
    # The form supplies the shape, and the shape was quietly supplying a
    # sign: 「殺人罪は法定刑加重ではありません」 negated an attested pair,
    # 「時効と期間を援用してはならない」 prohibited what nobody prohibits.
    # Same move as the modality licence (unlicensed norms 49 -> 0), one
    # gate further in: descriptive, positive forms only.
    from .compose_ja import slot_boundary_ok
    speakable = {k: f for k, f in writer.forms.items()
                 if f.modality == "none" and f.polarity == "positive"
                 and slot_boundary_ok(f.template)}
    drafts = compose(speakable, subject, rest, limit=limit,
                     content_from=[subject], vocab=writer.vocab,
                     licence=writer.licence(subject))
    out = {
        "verdict": result.get("verdict"),
        "path": path,
        "sentences": [d.as_dict() for d in drafts],
        "note": "content from the converged path, form from a harvested "
                "template; neither makes it true",
    }
    if edge_supply:
        # 辺から補われた語は名指しで見える — 経路(引用)と供給(辺)を
        # 読み手が区別できるように。
        out["edge_supply"] = edge_supply
    if "spoken_via" in dict(locals()):
        out["surface_center"] = locals()["spoken_via"]
    return out


def quote_in_words(result: Dict[str, Any], writer: Any,
                   *, limit: int = 1) -> Optional[Dict[str, Any]]:
    """引用された行の言葉だけで、一文を紡ぐ。8/18に却下した文書側生成の
    門つき再挑戦 (experiments/document_writing/DOC_WRITING.md が事前登録)。

    8/18、一般Writerを文書語彙に当てたら「精算は、グリーンをグリーン車
    さない。」「（がいしょくほう）」が出て却下した。原因は後日3つに分解
    され、それぞれ門で塞がれた: スロット境界(slot_boundary_ok)・語彙の門・
    選択制限の順位。この関数はその門の内側でだけ動く。

    ライセンスは引用行そのもの: 内容は**引用された行1本の内容連だけ**で、
    同じ行に書かれた語どうしは同一文共起そのもの — 連合の辺ライセンスの
    最強形が構成上ただで手に入る。行の外の語は主語にすら使わない。
    語彙を通った語が2つ(主語+内容1)無ければ黙って None — 断片より沈黙。

    返る下書きは constructed であり、引用の隣に置かれる。verdict にも
    引用にも触れない。票に入らない。
    """
    verdict = str(result.get("verdict") or "")
    if verdict not in ("DOCUMENT_LINE", "DOCUMENT_SECTION"):
        return None
    lines = [str(x).strip() for x in (result.get("lines") or []) if str(x).strip()]
    if not lines:
        line0 = str(result.get("text") or "").strip().split("\n")[0]
        lines = [line0] if line0 else []
    if not lines:
        return None
    from .compose_ja import compose, slot_boundary_ok
    from .lang import ja_content_runs
    import re as _re

    speakable = {k: f for k, f in writer.forms.items()
                 if f.modality == "none" and f.polarity == "positive"
                 and slot_boundary_ok(f.template)}
    subj_cand = [str(result.get("subject") or ""),
                 str(result.get("section") or "")]

    def draft_of(line: str):
        # 否定の行は黙る(2026-08-19実測)。speakable は positive 形のみ
        # (presence 証拠は ない を許可しない)なので、「対象としない」の
        # 行から下書きを作ると「対象する」— 行の主張の反転 — しか出せない。
        # 引用がそのまま立っている; 反転した下書きより沈黙。
        if _re.search(r"(しない|されない|できない|ではない|はない|認めない"
                      r"|ならない|ません)(。|$)", line.rstrip()):
            return None
        runs = [r for r in (ja_content_runs(line) or []) if 2 <= len(r) <= 10]
        words = [r for r in runs if r in writer.vocab]
        # 係り受けの搬送: 行の中で各語の直後に立つ助詞を読む。閉じた
        # 1文字集合のみ — 解析器ではなく、行が書いた役割の写し。
        roles: Dict[str, str] = {}
        order: Dict[str, int] = {}
        for w in words:
            m = _re.search(_re.escape(w) + r"([のをにがはとでへ])", line)
            if m:
                roles[w] = m.group(1)
            i = line.find(w)
            if i >= 0:
                order[w] = i
        # 行の末尾形(閉集合、長い順) — 行が選んだ言い方を文型の順位へ。
        tail = ""
        _stripped = line.rstrip("。")
        # 最長一致だが、文型側に一本も無い末尾は選ばない(2026-08-19実測:
        # 「を必要とする」は行に合致するが該当文型0で、ライセンスが空振り
        # した)。行にも文型にも合う最長の末尾へ — 「を必要とする」の行なら
        # 「とする」に落ち、「<0>を<1>とする」が候補に入る。
        for t_ in ("を必要とする", "に限り認める", "とみなされる", "とされる",
                   "とみなす", "をいう", "を指す", "とする", "である",
                   "認める", "支給する"):
            if _stripped.endswith(t_) and any(
                    k.rstrip("。").endswith(t_) for k in speakable):
                tail = t_
                break
        # 主語は問いの主題を優先。無ければ「〜を<Y>とする」型(定義)の Y —
        # この形の行では Y が定義される側で、左の列挙は Y の中身。次に
        # 行が は/が を付けた語。それも無ければ先頭の語彙語。
        subject = ""
        for s in subj_cand:
            s = s.strip()
            if s and s in writer.vocab and len(s) <= 10:
                subject = s
                break
        if not subject:
            # 定義形2種: 「XをYとする」と「「X」とは、…をいう」。
            qm = _re.search(r"「([^「」]{2,10})」とは", _stripped)
            if qm and qm.group(1) in writer.vocab:
                subject = qm.group(1)
            dm = None if subject else _re.search(
                r"([^、。をはがのにとでへ]{2,8})を([^、。]{2,8})とする$",
                _stripped)
            if dm:
                # 定義形「XをYとする」: 主語(穴0)は X — 文型「<0>を<1>と
                # する」で X が を穴、Y が と穴に立つと、行の核がそのまま
                # 継がれる(「利用を原則とする」)。Y を主語にした旧規則は
                # Y を穴0へ強制し「原則に利用があつたときも…」型の逆転を
                # 生んでいた(2026-08-19実測)。Y は rest に残り、roles が
                # Y→「と」を写すので と穴へ導かれる。
                if dm.group(1) in writer.vocab:
                    subject = dm.group(1)
                elif dm.group(2) in writer.vocab:
                    subject = dm.group(2)
        if not subject:
            marked = [w for w in words if roles.get(w) in ("は", "が")]
            subject = marked[0] if marked else (words[0] if words else "")
        if not subject:
            return None
        rest = [w for w in words if w != subject]
        if not rest:
            return None
        # ライセンスは行の登録から(2026-08-19)。文書の全「とする/ものと
        # する」文型は register="norm" で、licence="unknown" では一本も
        # 候補に入れなかった — 定義形が出ない実測の根はここ。引用行自身が
        # norm 登録(その行が定めを主張している)なら、その行の言葉で紡ぐ
        # 下書きも norm 形を継いでよい: 内容源が主張した登録だけを形が
        # 主張する、という一方向の規則そのまま。modality の門(義務・禁止・
        # 許可の形)は speakable の段で従来どおり閉じたまま。
        # 文体を行に従わせる(2026-08-19)。speakable 594本のうち25本が
        # 丁寧体で、法文の引用の隣で「新幹線は利用が移動にありました。」が
        # 勝っていた。文体の混合は束ねる操作なので、**行が選んだ文体**を
        # 継ぐ — 層であって併合ではない。行が丁寧体(です/ます)なら丁寧体の
        # 文型を先に、常体なら常体を先に。順位であって門ではないので、
        # 一致する文型が無ければ従来の並びのまま。
        _POLITE_TAIL = ("です", "ます", "ました", "でした", "ません",
                        "ください", "ですね", "でしょう")
        _line_polite = _stripped.endswith(_POLITE_TAIL)

        def _is_polite(tpl: str) -> bool:
            return tpl.rstrip("。").endswith(_POLITE_TAIL)

        speakable_r = {k: f for k, f in speakable.items()
                       if _is_polite(k) == _line_polite}
        if not speakable_r:
            speakable_r = speakable

        from .fusion import register_of
        _lic = register_of(line)
        drafts = compose(speakable_r, subject, rest, limit=limit,
                         content_from=[subject], vocab=writer.vocab,
                         licence=("norm" if _lic == "norm" else "unknown"),
                         roles=roles, order=order, tail=tail)
        return [dict(d.as_dict(), line=line) for d in drafts] or None

    # 文量は内容に応じて可変(2026-08-19): 引用行が多ければ文も増える —
    # 行ごとに1文・最大4文。1行しか無い引用は1文のまま。量を決めるのは
    # ライセンス(引用行の数)であって設定ではない。
    sentences: List[Dict[str, Any]] = []
    for ln in lines[:4]:
        ds = draft_of(ln)
        if ds:
            sentences.extend(ds[:1])
    if not sentences:
        return None
    return {
        "sentences": sentences,
        "constructed": True,
        "licence": "quoted_line",
        "line": lines[0],
        "note": "引用行の言葉だけで紡いだ下書き(行ごとに1文)。内容の"
                "出典は各引用行、形の出典は文型 — どちらも文を真にはしない",
    }


#: English stopwords for shape extraction only — not retrieval, which
#: already handles English. Kept minimal and closed: shape rules should
#: fail silent, never guess.
_EN_STOP = frozenset(
    "the a an of in on at for to with by is are was were be been does do "
    "did can could may must have has had what which who whom whose how "
    "why when where and or not no it its this that these those".split())


def en_shape(query: str) -> Optional[Dict[str, Any]]:
    """Subject / aspects / yes-no for an English question, by fixed rules.

    The Japanese side earned its gates one measurement at a time; English
    had none of them — not for lack of data but for lack of SHAPE
    extraction, since 「XのY」 rules read kana. These rules are the English
    mirror, additive and closed:

        what is X            subject X
        X of Y / Y's X       subject Y, aspect X
        does/can/is Y X ?    yes-no: subject Y, conditions X

    Anything that does not match returns None and the pipeline behaves
    exactly as before — the second-class fix must not create new ways to
    be wrong.
    """
    import re as _re

    q = query.strip().rstrip("?？ ").lower()
    if _re.search(r"[぀-ゟ゠-ヺ㐀-䶿一-鿿]", q):
        return None
    words = [w for w in _re.findall(r"[a-z][a-z0-9'-]*", q)]
    content = [w for w in words if w not in _EN_STOP]
    if not content:
        return None
    yn = bool(words) and words[0] in ("does", "can", "is", "are", "do",
                                      "must", "may", "has", "have")
    m = _re.match(r"^(?:what\s+is\s+|what\s+are\s+)(?:the\s+)?(.+)$", q)
    if m and not yn:
        rest = m.group(1)
        mo = _re.match(r"^(?:the\s+)?([a-z0-9' -]+?)\s+of\s+(?:the\s+)?"
                       r"([a-z0-9' -]+)$", rest)
        if mo:
            aspect = [w for w in mo.group(1).split() if w not in _EN_STOP]
            subj = [w for w in mo.group(2).split() if w not in _EN_STOP]
            if subj:
                return {"kind": "aspect", "subject": " ".join(subj),
                        "aspects": aspect}
        subj = [w for w in rest.split() if w not in _EN_STOP]
        return {"kind": "definition", "subject": " ".join(subj), "aspects": []}
    mo = _re.match(r"^([a-z0-9' -]+?)'s\s+([a-z0-9' -]+)$", q)
    if mo:
        subj = [w for w in mo.group(1).split() if w not in _EN_STOP]
        aspect = [w for w in mo.group(2).split() if w not in _EN_STOP]
        if subj and aspect:
            return {"kind": "aspect", "subject": " ".join(subj),
                    "aspects": aspect}
    if yn and len(content) >= 2:
        return {"kind": "yesno", "subject": content[0],
                "conditions": content[1:]}
    return None


def yes_no_en(store: Any, query: str) -> Optional[Dict[str, Any]]:
    """English yes/no as attestation — same verdicts, same closure."""
    sh = en_shape(query)
    if not sh or sh["kind"] != "yesno":
        return None
    subject = sh["subject"]
    if subject not in store.crosses:
        return {"verdict": "UNKNOWN_NOT_PRESENT", "core": None, "text": "",
                "subject": subject}
    cross = store.crosses.get(subject) or {}
    hits: Dict[str, List[str]] = {}
    gaps: List[str] = []
    for c in sh["conditions"]:
        m = sorted((f for f in cross if c in f or f in c),
                   key=lambda f: (-cross[f], f))[:4]
        if not m:
            other = store.crosses.get(c) or {}
            if any(subject in f for f in other):
                m = [c]
        if m:
            hits[c] = m
        else:
            gaps.append(c)
    if gaps:
        return {"verdict": "NOT_ATTESTED", "core": subject, "text": "",
                "subject": subject, "conditions": sh["conditions"],
                "attested": hits, "unattested": gaps}
    shown = [f for c in sh["conditions"] for f in hits[c][:2]]
    return {"verdict": "ATTESTED", "core": subject, "core_key": subject,
            "text": " ".join([subject] + shown[:4]),
            "subject": subject, "conditions": sh["conditions"],
            "attested": hits, "order_evidence": "aspect"}


def subject_check(store: Any, query: str, seed: str) -> Dict[str, Any]:
    """Does the staircase's seed actually cover what the question asked about?

    The staircase names a subject by coarsening, and coarsening has a failure
    mode that the verdict never showed: it keeps whatever part of the term it
    recognises and drops the rest without a word. Measured on 200 invented
    compounds, 77% came back answered, and in every answered case the seed
    was a substring — ヒュペリオン数人 answered about 数人, ズミルノフ環礁の面積
    about 面積. The reader is told about a different thing than the one they
    asked about, in the shape of a real answer.

    The subject is the LEFTMOST content run of the question. Japanese noun
    phrases are head-final inside a compound but topic-first across の:
    in 殺人罪の刑は the specific thing is 殺人罪 and 刑 is the aspect asked
    about it, so a seed that keeps the leftmost run and drops later ones is
    the measured-good case (subject alone, 113/120), while a seed that keeps
    a LATER run and drops the leftmost is the theft this exists to catch —
    相殺の効果は seeded on 効果 answered with the Meissner effect.

    The seed covers the subject when any of these holds:

      * the seed IS the subject, or contains it as a substring —
        相続の順位は seeded on 相続順位 stays a success
      * the subject is a facet of the seed's own cross — 背任罪とは seeded
        on 利得罪 stays, because crosses[利得罪] holds 背任罪: the arm the
        answer reads actually mentions the asked subject

    When none holds but the subject is itself a held core, the seed is
    REPLACED by the subject rather than refused — the staircase picked a
    worse entry than the question already contained.

    Otherwise the honest verdict is the one that already exists for a term
    the store does not hold: UNKNOWN_NOT_PRESENT, carrying the missing
    subject by name and the nearest held thing the staircase reached. That
    is a refusal with a pointer, not an answer about something else.
    """
    import re as _re

    from .lang import ja_content_runs

    # Japanese questions only. `ja_content_runs` returns Latin words too —
    # 「TypeScriptの型は」 must see TypeScript — so on a PURE-English query
    # it returns ['what', 'is', 'consideration'] and the leftmost-run rule
    # would make 'what' the subject of every English question. The gate is
    # a claim about Japanese topic structure; outside it, it stays silent.
    if not _re.search(r"[぀-ゟ゠-ヺ㐀-䶿一-鿿]", query):
        return {"ok": True, "subject": None}

    runs = ja_content_runs(query)
    if not runs:
        # Contentless — the gate has nothing to anchor on and an anchorless
        # gate would fire on noise. Inert by design.
        return {"ok": True, "subject": None}
    # The subject is the leftmost content PHRASE, not the leftmost run.
    # `ja_content_runs` splits on script boundaries, so ヴォルフガング粒子 is
    # two runs — and taking only the first made the subject equal the seed
    # by construction, which let every katakana-headed invented compound
    # straight through the gate it was built for. Adjacent runs (no gap in
    # the query between them) are one phrase; a particle like の ends it.
    subject = runs[0]
    consumed = 1
    pos = query.find(subject)
    if pos >= 0:
        end = pos + len(subject)
        for nxt in runs[1:]:
            if query.startswith(nxt, end):
                subject += nxt
                end += len(nxt)
                consumed += 1
            else:
                break
    #: The content runs AFTER the subject phrase are the asked ASPECT —
    #: 殺人罪の刑は asks the subject 殺人罪 about the aspect 刑. Entry stays
    #: subject-alone (adding terms to the seed was measured to dilute it,
    #: 113/120 -> 53), but the READ can honour them: see `aspect_read`.
    aspects = [r for r in runs[consumed:] if r and r not in subject]
    #: True when the whole question is one phrase plus grammar — no second
    #: content phrase after a particle. A caller gating the DIRECT path needs
    #: this: a multi-phrase query (「過失 故意」) legitimately lands on a core
    #: that is neither phrase, because intersection is the original
    #: conception working, and gating it would break puzzle inference.
    single = consumed == len(runs)
    if subject == seed or subject in seed:
        return {"ok": True, "subject": subject, "single": single, "aspects": aspects}
    cross = store.crosses.get(seed) or {}
    if subject in cross:
        return {"ok": True, "subject": subject, "single": single, "aspects": aspects,
                "via": "facet_of_seed"}
    if subject in store.crosses:
        return {"ok": True, "subject": subject, "single": single, "aspects": aspects,
                "reseed": subject}
    return {"ok": False, "subject": subject, "single": single, "aspects": aspects}


#: A question whose answer would be yes or no. The verbs are hiragana, so
#: `ja_content_runs` already excludes them — 「未成年者は契約できるか」 yields
#: the runs [未成年者, 契約] and the modality stays out of the condition set.
_YESNO = None


def _yesno_re():
    global _YESNO
    if _YESNO is None:
        import re as _re
        _YESNO = _re.compile(
            r"(?:できますか|できるか|必要ですか|必要か|可能ですか|可能か|"
            r"ありますか|あるか|ですか|ますか|されるか|するか|なるか)[?？]?$")
    return _YESNO


def yes_no(store: Any, query: str) -> Optional[Dict[str, Any]]:
    """「XはYできるか」— answered as attestation, never as yes or no.

    A store under closure cannot say いいえ: the absence of a facet is the
    absence of evidence, not a negation the corpus wrote. What it CAN say is
    typed and citable both ways:

        ATTESTED       every condition appears on the subject's own cross,
                       and the matching facets are shown with their counts
        NOT_ATTESTED   the subject is held and some condition has nothing
                       on the cross — a gap, closable by registration, and
                       explicitly NOT a "no"

    The mechanics are `puzzle.eliminate` turned inward: instead of asking
    which candidate holds a condition, ask which conditions this subject
    holds. Same filter, one subject. Anything else routes back to the
    ordinary path by returning None.
    """
    from .lang import ja_content_runs

    if not _yesno_re().search(query or ""):
        return None
    cov = subject_check(store, query, "")
    subject = cov.get("reseed") or (cov.get("subject")
                                    if cov.get("subject") in store.crosses
                                    else None)
    conditions = [c for c in (cov.get("aspects") or [])]
    if not conditions:
        # 「塩はしょっぱいですか」 yields only [塩]: しょっぱい is hiragana
        # and never a content run. Falling through used to dump the
        # subject's census (SEEDED) and assert クロイツ/タウブ — or, after
        # those were removed, アンモニア/イオン — as if they answered the
        # property. A yes/no with no extractable property is a gap.
        if subject is None:
            return {"verdict": "UNKNOWN_NOT_PRESENT", "core": None,
                    "text": "", "subject": cov.get("subject"),
                    "note": "a yes/no question about a subject the store "
                            "does not hold cannot be attested either way"}
        return {"verdict": "NOT_ATTESTED", "core": subject, "text": "",
                "subject": subject, "conditions": [], "unattested": [],
                "note": "the question is yes/no and no content-run "
                        "property was extracted; answering with the "
                        "subject's census would answer a different "
                        "question"}
    if subject is None:
        return {"verdict": "UNKNOWN_NOT_PRESENT", "core": None, "text": "",
                "subject": cov.get("subject"),
                "note": "a yes/no question about a subject the store does "
                        "not hold cannot be attested either way"}
    cross = store.crosses.get(subject) or {}
    hits: Dict[str, List[str]] = {}
    gaps: List[str] = []
    for c in conditions:
        m = sorted((f for f in cross if c in f or f in c),
                   key=lambda f: (-cross[f], f))[:4]
        if not m:
            # The connection can be written from either side: 時効's cross
            # holding 援用, or 援用's cross holding 時効. Both are the same
            # sentence read from a different topic, and a store whose faces
            # are capped at the cross capacity (the browser build) may keep
            # one side and not the other. Checked second because the
            # subject's own cross is the closer citation.
            # Containment one way only: a facet CONTAINING the subject is
            # the subject mentioned; a facet contained BY it is any shard —
            # 登記's cross holds the one-character facet 効, and 効 ⊂ 時効
            # turned 時効は登記が必要か into a false ATTESTED before this
            # arm was tightened.
            other = store.crosses.get(c) or {}
            if any(subject in f for f in other):
                m = [c]
        if m:
            hits[c] = m
        else:
            gaps.append(c)
    if gaps:
        return {"verdict": "NOT_ATTESTED", "core": subject, "text": "",
                "subject": subject, "conditions": conditions,
                "attested": hits, "unattested": gaps,
                "note": "the subject is held and nothing on its cross "
                        "attests these conditions — a coverage gap, not a "
                        "denial; the corpus never wrote the negative either"}
    shown = [f for c in conditions for f in hits[c][:2]]
    return {"verdict": "ATTESTED", "core": subject,
            "core_key": subject,
            "text": " ".join([subject] + shown[:4]),
            "subject": subject, "conditions": conditions, "attested": hits,
            "order_evidence": "aspect",
            "note": "every asked condition appears on the subject's own "
                    "cross; the matching facets are the citation, and this "
                    "is attestation, not assent"}


_COMPARE = None


def compare_shape(store: Any, query: str) -> Optional[Dict[str, Any]]:
    """「AとBの違いは」— the comparison the materials always allowed.

    `eliminate` and `siblings` could compute facet differences for months;
    no question SHAPE was wired to them. The verdict is COMPARISON, and it
    only fires when BOTH subjects are held — comparing a held thing to an
    unheld one would present absence as difference, which is the closure
    violation wearing a table. Shared facets first (what the corpus says
    they have in common), then each side's strongest own facets.
    """
    global _COMPARE
    if _COMPARE is None:
        import re as _re
        _COMPARE = _re.compile(
            r"^(.+?)と(.+?)の(?:違い|相違|差)(?:は|とは)?[?？]?$")
    m = _COMPARE.match(query.strip())
    if not m:
        return None
    a, b = m.group(1).strip(), m.group(2).strip()
    ca, cb = store.crosses.get(a), store.crosses.get(b)
    if ca is None or cb is None:
        missing = [t for t, c in ((a, ca), (b, cb)) if c is None]
        return {"verdict": "UNKNOWN_NOT_PRESENT", "core": None, "text": "",
                "subject": missing[0], "compare": [a, b],
                "note": "comparison needs both subjects held; absence "
                        "shown as difference would be fabrication"}
    shared = sorted(set(ca) & set(cb),
                    key=lambda f: (-(ca[f] + cb[f]), f))[:4]
    only_a = sorted(set(ca) - set(cb), key=lambda f: (-ca[f], f))[:4]
    only_b = sorted(set(cb) - set(ca), key=lambda f: (-cb[f], f))[:4]
    return {"verdict": "COMPARISON", "core": a, "core_key": a,
            "compare": [a, b],
            "shared": shared, "only_a": only_a, "only_b": only_b,
            "text": " ".join([a, b] + shared[:3]),
            "note": "shared facets, then each side's own — all held, "
                    "nothing inferred"}


def intersect(store: Any, query: str) -> Optional[Dict[str, Any]]:
    """Three or more conditions: narrow, never chain.

    The half of the early conception that measured out alive. A chain decays
    (41.5% -> 19.3% over five steps) because each step conditions on the
    previous answer; an intersection holds (100% answer retention, 93 -> 1
    candidates over four conditions) because every condition reads the same
    store. So a question carrying several content phrases is treated as a
    puzzle: the phrases are conditions, the candidates shrink monotonically,
    and the verdicts are the ones `puzzle` already types — a unique survivor
    is ANSWER_BY_INTERSECTION, several are UNKNOWN_UNDERDETERMINED with the
    survivors listed, none is UNKNOWN_CONDITIONS_CONFLICT, which is a
    statement about the question rather than the coverage.
    """
    from .lang import ja_content_runs
    from .puzzle import Puzzle, solve

    runs = ja_content_runs(query)
    if len(runs) < 3:
        return None
    # CONFLICT is a claim about the QUESTION — every condition individually
    # holds somewhere and they cannot hold together. A condition nothing
    # holds is a different fact (an absent term), and reporting it as
    # conflict misdirects the reader: ズミルノフ環礁の面積は came back
    # CONDITIONS_CONFLICT because no core holds ズミルノフ, when the honest
    # verdict — the subject gate's UNKNOWN_NOT_PRESENT naming the missing
    # phrase — was one branch further down. Empty-holder conditions hand
    # the question back.
    probe = Puzzle(store=store)
    if any(not probe._holders(t) for t in runs):
        return None
    sol = solve(store, runs)
    v = sol.get("verdict")
    if v == "ANSWER":
        core = sol["item"]
        cross = store.crosses.get(core) or {}
        shown = sorted(cross, key=lambda f: (-cross[f], f))[:4]
        return {"verdict": "ANSWER_BY_INTERSECTION", "core": core,
                "core_key": core, "text": " ".join([core] + shown),
                "conditions": sol.get("conditions"),
                "trail": sol.get("trail"),
                "note": "the conditions leave exactly one core standing; "
                        "the trail shows how each one narrowed the set"}
    if v == "UNKNOWN_UNDERDETERMINED" and sol.get("remaining", 0) <= 12:
        return {"verdict": "UNKNOWN_UNDERDETERMINED", "core": None,
                "text": "", "candidates": sol.get("candidates"),
                "remaining": sol.get("remaining"),
                "conditions": sol.get("conditions"), "trail": sol.get("trail")}
    if v == "UNKNOWN_CONDITIONS_CONFLICT":
        return {"verdict": "UNKNOWN_CONDITIONS_CONFLICT", "core": None,
                "text": "", "conditions": sol.get("conditions"),
                "trail": sol.get("trail")}
    return None


def staged(store: Any, query: str) -> Optional[Dict[str, Any]]:
    """Multi-step by staged intersection: 「条件… → 条件… → 条件…」.

    The chain that decays (41.5% -> 19.3%) walks facet edges; the stage
    that holds re-INTERSECTS at every step. Stage one narrows as usual;
    its SURVIVORS become a membership condition for the next stage — a
    candidate there must hold its own conditions AND touch a survivor
    (hold it as a facet, or be held on its cross). Any number of arrows
    chains the same way: each intermediate stage hands its linked set
    forward under the same width guard stage one always had (a stage
    that narrows too little abstains rather than handing a crowd on),
    and only the FINAL stage elects — link strength, strict lead, ties
    abstain. Every stage's trail rides the answer, so a reader can see
    where each cut.

    The arrow is explicit on purpose. 背任罪の刑の上限を科された者の
    再審請求先は hides its stage boundary in case grammar this reader
    does not parse; guessing the boundary would stage the wrong cut and
    answer a different chain. 「背任罪 刑 → 再審」 states it, and the
    typed UNKNOWNs say which stage failed.

    Measured on the 89,369-core federation: the recorded two-stage
    example still answers (時効 援用 → 期間 -> 時効), and a three-stage
    chain lands — 殺人罪 → 時効 期間 → 停止 answers 時効 at 26 links,
    survivors 33 -> 27 across the hand-offs. The original target
    背任罪 → 刑 上限 → 再審請求 ends UNKNOWN_UNDERDETERMINED: its
    final-stage candidates tie, and ties abstain here like everywhere.
    Broad middles die at the guard by name (時効 援用 → 期間 → 中断 is
    UNKNOWN_STAGE2_TOO_WIDE with 624 linked) — the guard is the system
    telling the asker which stage needs another condition, not a wall.
    """
    if "→" not in query and "->" not in query:
        return None
    from .lang import ja_content_runs
    from .puzzle import Puzzle

    parts = [p2.strip() for p2 in
             query.replace("->", "→").split("→") if p2.strip()]
    if len(parts) < 2:
        return None
    stage_terms = [ja_content_runs(p) for p in parts]
    if not all(stage_terms):
        return None

    def _touches(candidate: str, members: set) -> int:
        cr = store.crosses.get(candidate) or {}
        return sum(1 for m in members
                   if m in cr or candidate in (store.crosses.get(m) or {}))

    pz1 = Puzzle(store=store).narrow(*stage_terms[0])
    s1 = pz1.answer()
    survivors = (set(pz1.candidates or ())
                 if s1["verdict"] in ("ANSWER", "UNKNOWN_UNDERDETERMINED")
                 else set())
    if not survivors:
        return {"verdict": "UNKNOWN_STAGE1_EMPTY", "core": None, "text": "",
                "stage1": s1, "note": "the first stage left nothing to "
                "hand the second; the chain stops where the evidence does"}
    if len(survivors) > 40:
        return {"verdict": "UNKNOWN_STAGE1_TOO_WIDE", "core": None,
                "text": "", "remaining": len(survivors), "stage1": s1,
                "note": "stage one narrowed too little to hand on; add a "
                        "condition before the arrow"}

    trail: List[Dict[str, Any]] = [
        {"stage": 1, "conditions": stage_terms[0],
         "survivors": sorted(survivors)[:8], "remaining": len(survivors)}]

    for i in range(1, len(parts)):
        n_stage = i + 1
        final = i == len(parts) - 1
        terms = stage_terms[i]
        pz = Puzzle(store=store).narrow(*terms)
        out: Dict[str, Any] = {"stages": trail + [
            {"stage": n_stage, "conditions": terms,
             "candidates": len(pz.candidates or ())}]}
        if len(parts) == 2:
            # The shape the two-stage reader always got.
            out["stage1"] = trail[0]
            out["stage2"] = {"conditions": terms,
                             "candidates": len(pz.candidates or ())}
        if not pz.candidates:
            return {**out, "verdict": "UNKNOWN_STAGE%d_EMPTY" % n_stage,
                    "core": None, "text": "", "stage1": s1,
                    "note": "no core holds stage %d's conditions at all"
                            % n_stage}
        # Link STRENGTH, not link existence: touching one survivor out of
        # thirty is background, touching five is the chain. Measured with
        # existence alone, 時効 援用 → 期間 left 236 standing; counting
        # touches and demanding a strict lead is the same abstention
        # discipline every other tie in this engine obeys.
        linked: Dict[str, int] = {}
        for c in pz.candidates:
            n = _touches(c, survivors)
            if n:
                linked[c] = n
        if not linked:
            return {**out, "verdict": "UNKNOWN_STAGES_DISCONNECTED",
                    "core": None, "text": "", "at_stage": n_stage,
                    "note": "both stages hold, but no stage-%d core "
                            "touches a stage-%d survivor — the chain the "
                            "question asserts is not written in this "
                            "corpus" % (n_stage, n_stage - 1)}
        if not final:
            # Intermediate stages hand FORWARD, they do not elect: an
            # election in the middle would discard chains the last stage
            # could still tell apart. The width guard is the same one
            # stage one obeys.
            if len(linked) > 40:
                return {**out,
                        "verdict": "UNKNOWN_STAGE%d_TOO_WIDE" % n_stage,
                        "core": None, "text": "",
                        "remaining": len(linked),
                        "note": "stage %d narrowed too little to hand "
                                "on; add a condition" % n_stage}
            survivors = set(linked)
            trail.append({"stage": n_stage, "conditions": terms,
                          "survivors": sorted(survivors)[:8],
                          "remaining": len(survivors)})
            continue
        ranked = sorted(linked.items(), key=lambda kv: (-kv[1], kv[0]))
        strict = (len(ranked) == 1
                  or ranked[0][1] > ranked[1][1])
        if strict:
            core = ranked[0][0]
            cross = store.crosses.get(core) or {}
            shown = sorted(cross, key=lambda f: (-cross[f], f))[:4]
            return {**out, "verdict": "ANSWER_BY_STAGES", "core": core,
                    "core_key": core, "links": ranked[0][1],
                    "text": " ".join([core] + shown)}
        top = ranked[0][1]
        tied = [c for c, n in ranked if n == top]
        return {**out, "verdict": "UNKNOWN_UNDERDETERMINED", "core": None,
                "text": "", "candidates": tied[:12], "remaining": len(tied),
                "note": "the strongest final-stage candidates touch the "
                        "same number of survivors; ties abstain"}
    return None


def aspect_read(store: Any, out: Dict[str, Any],
                aspects: Sequence[str]) -> Dict[str, Any]:
    """Re-read the answered core's faces through the asked aspect.

    Entry and read are different jobs and were conflated: seeding with the
    subject ALONE is measured right for entry (113/120 against 53 with terms
    added), but the read then showed the subject's generic top facets and
    ignored what was asked about it. 殺人罪の刑は entered on 殺人罪 —
    correctly — and showed 一定 人 例, while crosses[殺人罪] held 法定刑加重
    the whole time. Measured across ten core×aspect pairs whose aspect the
    store attests: the aspect reached the shown faces 1 of 10 times.

    So the aspect SELECTS at read time: facets of the answered core that
    contain an asked aspect run come first, ordered by count then
    lexicographically — the same tie rule as everywhere else. Facets the
    core does not hold are never invented (closure is untouched; this only
    reorders within one cross), and when no held facet matches, the read is
    left exactly as it was rather than pretending the aspect was addressed.

    The selection is declared: `order_evidence` becomes "aspect", because
    the sequence is now query-anchored — neither corpus-ranked nor
    arbitrary, and a reader weighing the answer needs to know which of the
    three it is.
    """
    core_key = out.get("core_key") or out.get("core")
    if not (core_key and out.get("text") and aspects):
        return out
    cross = store.crosses.get(str(core_key)) or {}
    matched = sorted(
        (f for f in cross if any(a in f for a in aspects)),
        key=lambda f: (-cross[f], f))
    if not matched:
        return out
    shown = [t for t in str(out["text"]).split() if t]
    head, tail = shown[:1], [t for t in shown[1:] if t not in matched]
    n_facets = max(len(shown) - 1, 1)
    out = dict(out)
    out["text"] = " ".join(head + (matched + tail)[:n_facets])
    out["aspect"] = list(aspects)
    out["aspect_facets"] = matched[:n_facets]
    out["order_evidence"] = "aspect"
    return out


def ask(
    store: Any,
    query: str,
    *,
    judge: Optional[Any] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Ask the inference core; if it cannot enter, let the staircase in.

    ``judge`` is a built `graded.GradedJudge` over the same store. Building
    one per call would re-index 54,244 cores for a question.
    """
    from .consensus_store import candidates_for_query, consensus_over_store

    # Yes/no questions never reach the census: the census answers "what",
    # and forcing 「〜できるか」 through it either refuses or answers about
    # the subject as if とは had been asked. Attestation is its own shape.
    st_ = staged(store, query)
    if st_ is None:
        # Arrow-free multi-stage: the deterministic splitter proposes the
        # cuts (closed surface tables, 0/18 missplits in its regression)
        # and the SAME staged machinery runs them — the splitter stages,
        # it never elects. The derived chain rides the answer so a reader
        # can audit every cut; a query the splitter cannot stage falls
        # through silently, because a guessed cut answers a different
        # chain (staged's own docstring, now with the guessing removed).
        from .stage_split import as_staged_query, split as _stage_split
        arrow = as_staged_query(_stage_split(query))
        if arrow is not None:
            st_ = staged(store, arrow)
            if st_ is not None:
                st_["stage_split"] = {"chain": arrow, "derived": True}
    if st_ is not None:
        return st_
    cmp_ = compare_shape(store, query)
    if cmp_ is not None:
        return cmp_
    yn = yes_no(store, query)
    if yn is not None:
        return yn
    yn = yes_no_en(store, query)
    if yn is not None:
        return yn

    direct = consensus_over_store(store, query, **kwargs)
    # The same subject gate, on the direct path — but ONLY for single-phrase
    # questions. After the staircase gate landed, the residual 4% of invented
    # compounds still answered were all entering here: ヒュペリオンesa retrieves
    # the core `esa` by Latin substring and never touches the staircase. A
    # multi-phrase query is exempt because intersection landing on a core
    # that is neither phrase (「過失 故意」 → 結果的加重犯) is the original
    # conception working, not a theft.
    if str(direct.get("verdict", "")).startswith("ANSWER"):
        seed0 = str(direct.get("core_key") or direct.get("core") or "")
        cov0 = subject_check(store, query, seed0)
        if cov0.get("ok") and cov0.get("aspects"):
            direct = aspect_read(store, direct, cov0["aspects"])
        else:
            sh = en_shape(query)
            if sh and sh.get("subject"):
                # The English subject gate — found the same day the aspect
                # rules landed: "what is the penalty of murder" answered
                # about PENALTY, the exact theft the Japanese gate closed
                # months of measurements ago. Same rules, mirrored: the
                # core must be the subject, contain it, or hold it on its
                # cross; a held subject displaces the wrong core; else
                # refuse by name.
                subj = sh["subject"]
                core0 = str(direct.get("core_key") or "")
                cross0 = store.crosses.get(core0) or {}
                if not (subj == core0 or subj in core0 or subj in cross0):
                    if subj in store.crosses:
                        direct = consensus_over_store(store, subj, **kwargs)
                        if str(direct.get("verdict", "")).startswith("ANSWER"):
                            direct = dict(direct)
                            direct["subject"] = subj
                    else:
                        return {"verdict": "UNKNOWN_NOT_PRESENT",
                                "core": None, "text": "", "subject": subj,
                                "nearest_held": direct.get("core")}
            if sh and sh.get("aspects"):
                direct = aspect_read(store, direct, sh["aspects"])
        if cov0.get("single") and not cov0["ok"]:
            return {
                "verdict": "UNKNOWN_NOT_PRESENT",
                "core": None,
                "text": "",
                "subject": cov0["subject"],
                "nearest_held": direct.get("core"),
                "note": ("retrieval reached only a part of the question's "
                         "subject; answering about the part would answer a "
                         "different question"),
            }
    # Any refusal from the census is a chance for intersection first:
    # 「時効 援用 中断」 came back UNKNOWN_INSUFFICIENT_EVIDENCE from the
    # direct read while 時効 was the unique core holding 援用 AND 中断 —
    # the conditions cut where the census could not converge. The puzzle's
    # own refusals (UNDERDETERMINED with survivors named, CONFLICT) are
    # more informative than a bare insufficiency, so they replace it.
    if str(direct.get("verdict", "")).startswith("UNKNOWN"):
        px = intersect(store, query)
        if px is not None:
            return px
    if direct.get("verdict") != "UNKNOWN_NO_EVIDENCE" or judge is None:
        return direct

    g = judge.ask(query)
    if not str(g.get("verdict", "")).startswith("ANSWER"):
        # The staircase abstained — often CORRECTLY, because two held cores
        # tie: 相続の効果は holds both 相続 and 効果, the rungs cannot pick
        # one, and ties must abstain. But the tie is between subject and
        # ASPECT, and the question itself says which is which: the leftmost
        # phrase is the subject. If that subject is a held core, enter
        # there, exactly as the reseed branch does when the staircase named
        # the wrong thing. Measured: 相続の効果は, 時効の期間は, 契約の解除は
        # and 窃盗罪の刑は all went UNKNOWN_NO_EVIDENCE through this branch
        # while the store held every one of their subjects.
        cov = subject_check(store, query, "")
        if not cov.get("reseed"):
            # No held subject to enter on. The core\'s own refusal stands —
            # a second reader that also found nothing is not a reason to
            # widen further.
            return {**direct, "staircase": g.get("verdict")}
        g = {"item": cov["reseed"], "verdict": g.get("verdict"),
             "via": "subject_entry"}

    # The subject alone. Adding its facets to the seeded query DILUTES it:
    # measured over 120 questions the core could not enter, where the
    # staircase did name a subject —
    #
    #     subject alone        113 of 120 answered   94%
    #     + 4 by frequency      53                   44%
    #     + 4 alphabetically    57                   48%
    #     + every facet         35                   29%
    #     + 4 rarest            24                   20%
    #
    # Extra terms pull the sections apart, which is the same reason a
    # one-word question makes every rung abstain: the core is looking for a
    # centre several sections agree on, and each added term is another
    # section that has to agree. It also removes an arbitrary choice — there
    # is no ordering left to pick, so nothing here decides the answer by
    # how a list happened to be sorted.
    seed = g["item"]
    # The seed must cover the asked subject, or say that it cannot. Without
    # this check, 77% of invented compounds were answered about a substring.
    cov = subject_check(store, query, seed)
    if not cov["ok"]:
        return {
            "verdict": "UNKNOWN_NOT_PRESENT",
            "core": None,
            "text": "",
            "subject": cov["subject"],
            "nearest_held": seed,
            "staircase": g.get("verdict"),
            "note": ("the question's subject is not held; the staircase "
                     "reached only a part of it, and answering about the "
                     "part would answer a different question"),
        }
    if cov.get("reseed"):
        seed = cov["reseed"]
    seeded_query = seed
    out = consensus_over_store(store, seeded_query, **kwargs)
    if out.get("verdict") == "ANSWER":
        out = dict(out)
        # Typed apart on purpose. The entry was widened; a reader deciding
        # whether to rely on this needs to see that it was.
        out["verdict"] = "SEEDED"
        out["seeded_from"] = {"subject": seed,
                              "staircase_verdict": g.get("verdict"),
                              "agreeing": g.get("agreeing"),
                              "query": seeded_query}
        out["note"] = ("the inference core could not enter on the question as "
                       "asked; the staircase named a subject by coarsening "
                       "and the core was re-entered there")
        if cov.get("aspects"):
            out = aspect_read(store, out, cov["aspects"])
        return out
    return {**out, "seeded_from": {"subject": seed, "query": seeded_query}}
