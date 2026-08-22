"""Retrieval → consensus bridge: CrossStore の候補十字を殻に載せて合意探索.

クエリ分解 → 候補 core を k 個引く → 各 core の腕 (tip + 上位 facets) を
殻に載せる → run_consensus / matryoshka_consensus。未ヒットは型付き
UNKNOWN のまま (捏造しない)。

候補ランキング (決定論):
  1. クエリ内容語と core の一致 (head 一致を最優先)
  2. facet がクエリ語に重なる core
  3. 同点は mass (出現回数) 降順 → アルファベット順
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .consensus import (
    ConsensusConfig,
    settled_axes,
    matryoshka_consensus,
    query_content,
    run_consensus,
)
from .cross import AXES, ShellCross
from .cross_store import CrossStore
from .en_decompose import decompose
from .face_roles import FACET_FACES
from .lex_filters import PROPER_SUFFIX, display_sym

MAX_ARMS = len(AXES)

# "contest:2026h1" (structured key:value core) — the generic tokenizer
# strips ":" before this ever reaches decompose(), which is why a hand-
# structured record couldn't be found by a natural-language question even
# though recall(exact_name) worked. Scanned against the RAW query text,
# before tokenization, so the colon survives.
_NAMESPACED_ID = re.compile(r"[a-z0-9_]+(?::[a-z0-9_]+)+", re.I)


class _MassView:
    """masses adapter for consensus.axis_energy (log-damped counts)."""

    def __init__(self, store: CrossStore):
        self._store = store

    def get(self, sym: str) -> float:
        import math

        return 1.0 + math.log1p(self._store.mass(sym))


def candidates_for_query(
    store: CrossStore,
    query: str,
    *,
    k: int = MAX_ARMS,
) -> List[str]:
    qset, head = query_content(query)
    rec = decompose(query)
    ordered = list(rec.content_tokens)
    # who/where → 固有名チャネル優先; what/define → common 優先
    proper_first = rec.pattern in ("who_is", "where_is")

    def variants(tok: str) -> List[str]:
        both = [tok + PROPER_SUFFIX, tok] if proper_first else [tok, tok + PROPER_SUFFIX]
        return [v for v in both if store.has(v)]

    scored: List[Tuple[int, float, str]] = []
    seen: set = set()
    # 名前空間付きID ("contest:2026h1") をクエリの生テキストから直接拾う —
    # 最優先 (rank -1): これは曖昧さのない exact レコード参照なので、
    # 語のオーバーラップよりも先に候補にする
    for m in _NAMESPACED_ID.finditer(query or ""):
        key = m.group(0).casefold()
        for v in (key, key + PROPER_SUFFIX):
            if store.has(v) and v not in seen:
                seen.add(v)
                scored.append((-1, -store.mass(v), v))
    # 隣接内容語の複合 ("sun tzu" → sun_tzu#p) を最優先で引く
    for i in range(len(ordered) - 1):
        joined = f"{ordered[i]}_{ordered[i + 1]}"
        for v in (joined + PROPER_SUFFIX, joined):
            if store.has(v) and v not in seen:
                seen.add(v)
                scored.append((0, -store.mass(v), v))
    # head が store に居るなら、非 head の単独語は core 候補にしない —
    # それらは語義選択の指定語 ("sun newspaper" の newspaper)。巨大質量の
    # 汎用 core が head を押し出す事故を防ぐ。
    # A non-head token is DROPPED when the head is in the store, on the
    # reading that it is a sense-selector — the "newspaper" in "sun
    # newspaper" — and that a high-mass generic core would push the head
    # out. That looked like the reason generation stayed short: 「過失 故意」
    # retrieves one core, so the shell fills ONE arm of six and the path is
    # that arm's five slots (tip + four faces), which is why eight generated
    # sentences were the same two words rearranged.
    #
    # Ranking them below the head instead of dropping them was measured and
    # was WORSE. Over 120 two-term questions:
    #
    #     dropped (k=1 equivalent)   73 of 120 ANSWER, 100% the right core
    #     ranked below the head      33 of 120,         94%
    #
    # and the paths did not grow — 76 questions became AMBIGUOUS instead.
    # A second arm did not add content; it gave the sections something else
    # to converge on, and they split. The path is short because one subject
    # has one arm, and more subjects is not more of one subject.
    head_in_store = bool(head and variants(head))
    for tok in ordered:
        if head_in_store and tok != head:
            continue
        for rank, v in enumerate(variants(tok)):
            if v in seen:
                continue
            seen.add(v)
            pri = 1 if tok == head else 2
            scored.append((pri + rank, -store.mass(v), v))
    # facet 重なりで引く — 直接ヒットが1つも無い場合のみの補完。
    # (直接 core があるのに高頻度 core を facet 経由で足すと、質量で
    #  本命を押し出す — tokyo vs film の教訓)
    if not seen and qset:
        for core, cross in store.crosses.items():
            if core in seen:
                continue
            overlap = len(qset & set(cross))
            if overlap > 0:
                scored.append((9, -(overlap * 1000 + store.mass(core)), core))
    scored.sort()
    out = [c for _, _, c in scored]

    # 包摂: クエリの隣接2語を覆う複合語があれば、その部分語候補を落とす
    #   ("sun_tzu#p" が居るとき "sun" / "sun#p" / "tzu" は退場)
    from .lex_filters import norm_words

    compounds = [c for c in out if len(norm_words(c)) >= 2 and norm_words(c) <= qset]
    covered: set = set()
    for c in compounds:
        covered |= norm_words(c)
    if compounds:
        out = [
            c
            for c in out
            if len(norm_words(c)) >= 2 or not (norm_words(c) <= covered)
        ]

    # 同名双子の選別: 同じ単語に common と proper 両チャネルがあるとき、
    # what/define は common、who/where は proper を残す (片方しか無ければ維持)
    bases: Dict[str, set] = {}
    for c in out:
        if len(norm_words(c)) == 1:
            base = next(iter(norm_words(c)))
            bases.setdefault(base, set()).add(c)
    drop: set = set()
    for base, group in bases.items():
        common = base in group
        proper = (base + PROPER_SUFFIX) in group
        if common and proper:
            drop.add(base if proper_first else base + PROPER_SUFFIX)
    out = [c for c in out if c not in drop]
    # facet 重なりの追記(2026-08-19、experiments/retrieval_reach)。従来の
    # 補完は「直接ヒット0の時だけ」で、facet 語が別 core 名に当たると
    # 封じられ、中頻度 facet 3語の到達は 27/300 だった。直接候補は不動の
    # まま残枠だけを重なり順で埋める — tokyo vs film の「質量が本命を
    # 押し出す」は起きない(押し出す席がない)。実測(300探針、同一
    # ハーネス): 到達 27→196、誤答 278→190、正答 2→2 無傷、棄権 20→108。
    # 正解が届かない時に consensus は棄権せず誤答していた — 追記の腕は
    # 割れを起こし、その誤答を棄権に変える。
    if len(out) < k and qset:
        from collections import Counter as _Counter
        _cnt: Dict[str, int] = _Counter()
        for w in qset:
            for c in _word_index(store, names=False).get(w, ()):
                _cnt[c] += 1
        # 同じ重なり数の中は**特定性**で並べる(2026-08-19、PREREG3)。
        # 質量順は 89k/740k 核では効いたが、jawiki 本文で 1.19M 核になると
        # overlap=3 の核が数千あり、その中で汎用核の巨大質量が正解の中頻度
        # 核を6枠から押し出した — 同一300問で reachable 171→15、
        # wrong 206→223。docstring が警告していた "tokyo vs film" が規模で
        # 顕在化した形。特定性 = 重なり / その核の面数 は「自分の面のうち
        # 何割がこの問いに当たるか」で、店が持つ実測だけで決まる。
        # 直接ヒット(名前一致)の順位はここでは一切触らない。
        extra = sorted(
            (-ov, -(ov / max(1, len(store.crosses.get(c) or ()))),
             -store.mass(c), c)
            for c, ov in _cnt.items() if c not in out)
        out = out + [t[-1] for t in extra[:k - len(out)]]
    return out[:k]


def build_shell_from_store(
    store: CrossStore,
    cores: List[str],
    *,
    facets_per_arm: int = len(FACET_FACES),
    tie: str = "asc",
) -> ShellCross:
    """Place each core's facts on its arm's faces.

    ``tie`` decides only how EQUALLY-SCORED facts are ordered. "asc" is the
    historical rule (lexicographic ascending, what `top_facets` does) and is
    the default, so nothing changes unless a caller asks. "desc" reverses
    each run of ties and leaves genuinely different scores where they are.

    That distinction is the whole point. Among facts the store cannot tell
    apart, the order is arbitrary — so an answer that depends on which
    arbitrary order was chosen is an artifact of the placement rather than
    of the evidence. `placement_invariant` in `consensus_over_store` uses
    this to refuse such answers. See docs/PLACEMENT.md.
    """
    shell = ShellCross()
    placement = getattr(store, "placement", None) or {}
    for axis, core in zip(AXES, cores[:MAX_ARMS]):
        shell.faces[axis]["tip"] = core
        shell.reflections[axis] = core
        # A baked placement, if this store has one for this core; otherwise
        # the historical frequency rule. Which four facets occupy the faces
        # was measured to change the answer text on 120 of 120 real queries,
        # so this is the choice, not a detail — see verantyx/placement.py.
        picks = placement.get(core)
        if picks is None:
            picks = _ranked_facets(store, core, tie=tie)
        elif tie == "desc":
            # A baked placement is already ordered; the only arbitrary part
            # left is which of the equally-scored tail entries made the cut,
            # so reverse the whole list rather than pretending to know which
            # of them tied. Coarser than the unbaked path, and honest about it.
            picks = list(reversed(picks))
        for face, facet in zip(FACET_FACES, picks[:facets_per_arm]):
            shell.faces[axis][face] = facet
    return shell


def _ranked_facets(store: CrossStore, core: str, *, tie: str = "asc") -> List[str]:
    """A core's facets, by count desc, with ties broken as ``tie`` says."""
    cross = store.crosses.get(str(core).casefold().strip()) or {}
    if not cross:
        return []
    # The citation is provenance, not a fact about the subject, and an arm
    # has four faces. A reified event with 主体/対象/行為/原因 needs all four
    # and got three because "(reported by X)" had taken one. It stays in the
    # store; it just does not occupy a face.
    labels = {str(s).casefold().strip() for s in getattr(store, "source_labels", ()) or ()}
    if labels:
        cross = {f: c for f, c in cross.items() if f not in labels}
        if not cross:
            return []
    if tie == "asc":
        return [f for f, _c in sorted(cross.items(), key=lambda kv: (-kv[1], kv[0]))]
    if tie != "desc":
        raise ValueError(f"tie must be 'asc' or 'desc', got {tie!r}")
    items = sorted(cross.items(), key=lambda kv: (-kv[1], kv[0]))
    out: List[str] = []
    i = 0
    while i < len(items):
        j = i
        while j < len(items) and items[j][1] == items[i][1]:
            j += 1
        out += [f for f, _c in sorted(items[i:j], key=lambda kv: kv[0], reverse=True)]
        i = j
    return out


def consensus_over_store(
    store: CrossStore,
    query: str,
    *,
    k: int = MAX_ARMS,
    cfg: Optional[ConsensusConfig] = None,
    matryoshka: bool = False,
    carry: str = "A",
    n_layers: int = 3,
    placement_invariant: bool = False,
    direction_invariant: bool = False,
    circulation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """End-to-end: retrieve → shell → consensus (typed verdicts).

    ``placement_invariant`` re-asks with the arbitrary part of the placement
    reversed and downgrades any ANSWER the two readings disagree about. Off
    by default: it trades recall for calibration, and that is the caller's
    decision. See `_apply_placement_invariance`.
    """
    cores = candidates_for_query(store, query, k=k)
    if not cores:
        return {
            "verdict": "UNKNOWN_NO_EVIDENCE",
            "core": None,
            "text": "",
            "retrieved": [],
            "reason": "no_candidate_cross",
        }
    shell = build_shell_from_store(store, cores)
    masses = _MassView(store)
    if matryoshka:
        out = matryoshka_consensus(
            shell, query, carry=carry, n_layers=n_layers, masses=masses
        )
    else:
        _seed = (circulation or {}).get(shell.center)
        out = run_consensus(shell, query, cfg=cfg, masses=masses,
                            seed_state=_seed).as_dict()
    out["retrieved"] = cores
    out["core_key"] = out.get("core")
    if out.get("core"):
        out["core"] = display_sym(out["core"])
    if out.get("text"):
        out["text"] = " ".join(
            display_sym(t) for t in out["text"].split()
        )
        # Does the evidence rank the facets this path shows, or is the order
        # an artifact of a tie-break? Measured on this store, 84% of answered
        # cores carry all-tied facet counts, so the sequence a reader sees is
        # lexicographic accident — 時効 leading with 18民主化運動等 because
        # digits sort first. Nothing here reorders anything; the answer just
        # stops CLAIMING an order it does not have, and a renderer can show
        # an unordered set instead of an arrow chain. Reads counts at answer
        # time, so a merge that starts summing cross-leaf attestation will
        # flip cores to "ranked" with no change here.
        ck = out.get("core_key")
        cross = store.crosses.get(ck) or {} if ck else {}
        shown = [t for t in out["text"].split() if t in cross]
        counts = {cross[t] for t in shown}
        if len(shown) >= 2:
            out["order_evidence"] = "ranked" if len(counts) > 1 else "arbitrary"
    _apply_sense_selection(store, out, query)
    _apply_coverage_gate(out, query)
    # Polarity gate — inert by construction on stores that never ingested
    # polar keyed facets (every store before polarity.ingest_polar existed),
    # so wiring it unconditionally preserves historical behaviour while any
    # store that DOES carry poles gets contradiction honesty for free.
    from .polarity import apply_polarity_gate
    apply_polarity_gate(store, out, query)
    if placement_invariant:
        _apply_placement_invariance(store, out, query, k=k, cfg=cfg,
                                    circulation=circulation)
        # 軸のロック(2026-08-21、これまで.pdf の中核・未到達だった機構)。
        # 配置不変を生き延びた答えの腕のうち、facet の counts が割れている
        # ものだけを settled とする — 同点崩しで勝った腕はロックできない。
        # ここでは**報告するだけ**で、効かせるのは次の問い(循環)と上層。
        if out.get("verdict") == "ANSWER" and out.get("placement_invariant"):
            out["locks"] = settled_axes(shell, store, out.get("core_key"))
            # 循環が渡されていれば、この核の配置に locks を書き戻す —
            # 次の問いが同じ核に触れたとき initial_locks として効く。
            if circulation is not None and out.get("core_key"):
                slot = circulation.setdefault(out["core_key"], {})
                if isinstance(slot, dict) and out["locks"]:
                    slot["locks"] = sorted(set(slot.get("locks", []))
                                           | set(out["locks"]))
    if direction_invariant:
        _qset, _h = query_content(query)
        _apply_direction_invariance(store, out, _qset)
    return out


_FRAME = re.compile(r"(に関係する|に関する|について|とは何|は何|を教えて"
                    r"|ですか|でしょうか|ってなに|って何)")


def frame_stripped(query: str, runs: List[str]) -> Set[str]:
    """問いの枠パターンの中にしか現れない run を主題から外す(閉じた規則)。

    実測(2026-08-19、PREREG_PROMOTION): 「〜に関係するのは何ですか」の
    関係 が内容語として被覆に入り、逆方向の誤答が 0→23.7% に跳ねた。
    枠組み語は問いの装置であって主題ではない。パターン外にも現れる語
    (「親子関係の解消」の 関係)は残る — 位置が枠か主題かを分ける。
    枠剥がし後の再測: 自然文包装 163正答/誤答0(裸3語と完全一致)。
    """
    spans = [m.span() for m in _FRAME.finditer(query or "")]
    out: Set[str] = set()
    for r in runs:
        for m in re.finditer(re.escape(r), query or ""):
            if not any(a <= m.start() and m.end() <= b for a, b in spans):
                out.add(r)
                break
    return out


def _word_index(store: CrossStore, *, names: bool = True) -> Dict[str, List[str]]:
    """語→core の転置索引。store に一度だけ築く(89k核0.2秒/740k核9秒)。

    核が増えても照会は増えない — 遅かったのは全核走査という実装の欠陥で
    あって構造ではない(操作者指摘 2026-08-19)。

    ``names`` は**名前語を引けるか**。二つの読み手が別のものを要る:

      direction_band  名前も要る。core は自分の名前を facet に持たないので、
                      名前を数えないと「正当防衛とは」の帯から core 正当防衛
                      自身が構造的に脱落する(実測で門が正当な当選を全滅)。
      候補追記         facet だけ。元の実装は `qset & set(cross)` で
                      **facet しか見ていなかった**。索引化のとき名前を混ぜて
                      しまい、"what is the sun" に sun_tzu#p が名前の sun で
                      入り、腕が2本になって AMBIGUOUS に割れた
                      (COMPOUND_SENSE_CHANNELS が落ちて発覚、2026-08-19)。
                      「head が店に居るなら非 head の単独語は候補にしない」
                      という既存規則を、追記が裏口から破っていた。
    """
    from .lex_filters import norm_words
    attr = "_word_to_cores" if names else "_facet_to_cores"
    idx = getattr(store, attr, None)
    if idx is None:
        idx = {}
        for core, cross in store.crosses.items():
            keys = (set(cross) | norm_words(core)) if names else set(cross)
            for w in keys:
                idx.setdefault(w, []).append(core)
        setattr(store, attr, idx)
    return idx


def direction_band(store: CrossStore, qset: Set[str]) -> Tuple[Set[str], int]:
    """逆方向の読み: 問いの内容語を最も多く覆う core の同点帯。

    順方向(問い→名前で core を引く)と誤りの出方が別種の、もう一つの
    読み。core の側から「この問いを自分の facet 集合がどれだけ覆うか」
    だけを見る — 名前一致・質量・エネルギーは一切見ない。
    """
    from collections import Counter

    from .lex_filters import norm_words

    # 転置索引(2026-08-19、辞書1.4M投入後)。全core走査は89k核で0.2秒、
    # 740k核で数秒に伸びた — 語→core の索引を store に一度だけ築く。
    # 名前も被覆に数える(core は自分の名前を facet に持たない — 索引が
    # 無かった頃、名前を数え忘れて「正当防衛とは」の帯から core 自身が
    # 構造的に脱落し、門が正当な当選を殺した実測がある)。意味は走査版と
    # 同一で、速さだけが変わる。
    idx = _word_index(store)
    cnt: Counter = Counter()
    for w in qset:
        for c in idx.get(w, ()):
            cnt[c] += 1
    if not cnt:
        return set(), 0
    best = max(cnt.values())
    return ({c for c, ov in cnt.items() if ov == best}, best)


def _apply_direction_invariance(
    store: CrossStore, out: Dict[str, Any], qset: Set[str]
) -> None:
    """向きの不変性(2026-08-19、experiments/bidirectional_consensus)。

    発案は操作者:「一方からしか見ていない。逆からやったものを重ねて、
    まとめて投入することで相殺する」。同点換え(配置という単一変更)と
    同型の変分 — **読む向きという単一変更**に不変な当選だけが本物。

    実測(vera.db ja、300探針、事前登録): 順方向は正解が候補に居ないと
    棄権せず誤答する(誤答206)。逆方向(被覆最大帯)は同点帯が一意の159問
    で誤答0。重ね=順方向の当選が逆方向の帯に入る時だけ ANSWER:
    誤答206→24、正答無傷。票は混ぜない — 門であって加点ではない。
    """
    if out.get("verdict") != "ANSWER" or not qset:
        return
    band, best = direction_band(store, qset)
    ck = out.get("core_key") or out.get("core")
    if not band or ck in band:
        out["direction_invariant"] = True
        return
    rev = sorted(band, key=lambda c: store.mass(c))[:4]
    out["verdict"] = "UNKNOWN_DIRECTION_DISAGREEMENT"
    out["forward_core"] = out.get("core")
    out["reverse_band"] = [display_sym(c) for c in rev]
    out["reverse_coverage"] = best
    out["core"] = None
    out["text"] = ""
    out["note"] = ("順方向(名前で引く)の当選が、逆方向(問いを最も覆う核の帯"
                   ")に入らない。向きを変えると消える当選は向きの産物であって"
                   "証拠の産物ではない — 両方の言い分を並べて棄権する")


def _apply_placement_invariance(
    store: CrossStore,
    out: Dict[str, Any],
    query: str,
    *,
    k: int,
    cfg: Optional[ConsensusConfig],
    ja: bool = False,
    circulation: Optional[Dict[str, Any]] = None,
) -> None:
    """Refuse an ANSWER that a different arbitrary placement would not give.

    **Placement cannot add information.** The store holds the same facts
    either way; all that changes is which four occupy the faces and in what
    order. So a core that wins under one arbitrary tie-break and loses under
    another won on the tie-break, not on the evidence.

    This is the same argument shape as "layout cannot add information" in
    docs/METAMORPHIC.md, and it has the same property that makes it worth
    having: it needs no answer key, no human and no model. Both readings run
    in this process against this store.

    Measured on a planted-answer store, 68 held-out descriptive questions:

        frequency placement     manufacture rate 30.9% -> 0.0%  (justified 1 -> 0)
        simulated placement     manufacture rate 13.2% -> 7.4%  (justified 3 -> 1)

    The asymmetry is the useful part. Every facet in that store had count 1,
    so the frequency rule's whole ordering WAS a tie-break and none of its
    answers survived — correctly. Demand-scored facets are not tied, so they
    survive, and simulated placement keeps some of its answers.

    Real-store confirmation, 2026-08-19 (this was the open question when the
    gate landed — all earlier numbers were synthetic). vera.db ja, 89,369
    cores, 300 mid-frequency facet probes with planted source cores
    (experiments/placement_matryoshka_recheck/):

        demotions fired          4 of 546 ANSWERs (~0.7%)
        of those, wrong answers  4 / 4
        correct answers demoted  0

    Two honest notes travel with that. Real mass distributions rarely tie,
    so the gate fires far less often than on the all-counts-equal synthetic
    store — it is cheap insurance, not a large effect. And an independent
    synthetic replication the same day (n=62, different store) found the
    same shape: fabrications 4 -> 0 with the single justified answer
    untouched, while AXIS rearrangement (rotation/reversal) caught nothing
    — the search is already axis-robust; the arbitrariness lives in the
    tie-break, exactly where this gate looks.

    It costs recall, and the cost is real: justified answers fall too. This
    is a dial, and it is off by default, because a caller who has not decided
    that refusal beats a wrong answer should not have it decided for them.
    """
    if out.get("verdict") != "ANSWER":
        return
    cores = out.get("retrieved") or []
    if not cores:
        return
    shell = build_shell_from_store(store, list(cores), tie="desc")
    if ja:
        from .lang import ja_content_runs
        alt = run_consensus(shell, query, cfg=cfg, masses=_MassView(store),
                            seed_state=(circulation or {}).get(shell.center),
                            qset_override=set(ja_content_runs(query))).as_dict()
        alt_core = alt.get("core")
    else:
        alt = run_consensus(shell, query, cfg=cfg, masses=_MassView(store),
                            seed_state=(circulation or {}).get(shell.center)).as_dict()
        alt_core = display_sym(alt["core"]) if alt.get("core") else None
    if alt.get("verdict") == "ANSWER" and alt_core == out.get("core"):
        out["placement_invariant"] = True
        return
    out["placement_invariant"] = False
    out["verdict"] = "AMBIGUOUS"
    out["reason"] = "placement_dependent_answer"
    out["placement_alternative"] = {"verdict": alt.get("verdict"), "core": alt_core}
    out["core"] = None
    out["text"] = ""


def _apply_sense_selection(
    store: CrossStore, out: Dict[str, Any], query: str
) -> None:
    """指定語 (core 以外の内容語) があれば語義クラスタで読み出しを差し替え."""
    if out.get("verdict") != "ANSWER" or not out.get("core_key"):
        return
    from .sense_split import sense_facets

    qset, _head = query_content(query)
    core_key = out["core_key"]
    from .lex_filters import norm_words

    specifiers = qset - norm_words(core_key)
    if not specifiers:
        return
    sel = sense_facets(store, core_key, specifiers)
    if sel["selected"] is None:
        return
    facets = sel["facets"]
    out["sense_cluster"] = {
        "selected": sel["selected"],
        "n_clusters": len(sel["clusters"]),
        "members": sel["clusters"][sel["selected"]],
    }
    out["text"] = " ".join(
        [display_sym(core_key)] + [display_sym(f) for f in facets]
    )


def _apply_coverage_gate(out: Dict[str, Any], query: str) -> None:
    """部分接地の検査: 勝ち腕が覆わないクエリ内容語を報告し、
    未被覆語が core 語と原文で隣接する場合（複合の意図: "quantum
    chromodynamics"）は、その複合を知らないので ANSWER を降格する."""
    if out.get("verdict") != "ANSWER" or not out.get("core"):
        return
    from .en_decompose import tokenize
    from .lex_filters import norm_words

    qset, _head = query_content(query)
    # namespaced core ("contest:2026h1") の構成語をここでも展開する —
    # そうしないと自分自身の core 名の一部が「未被覆」と誤報告される
    covered: Set[str] = set()
    for tok in out["core"].split():
        covered |= norm_words(tok)
    for tok in out.get("text", "").split():
        covered |= norm_words(tok)
    uncovered = sorted(qset - covered)
    out["uncovered_terms"] = uncovered
    if not uncovered:
        return
    raw_toks = tokenize(query)
    core_words: Set[str] = set()
    for tok in out["core"].split():
        core_words |= norm_words(tok)
    for i, t in enumerate(raw_toks):
        if t in core_words:
            neighbors = {
                raw_toks[j] for j in (i - 1, i + 1) if 0 <= j < len(raw_toks)
            }
            if neighbors & set(uncovered):
                out["verdict"] = "UNKNOWN_INSUFFICIENT_EVIDENCE"
                out["reason"] = f"compound_not_known:{'_'.join(sorted(neighbors & set(uncovered)))}"
                out["core"] = None
                out["text"] = ""
                return


#: 閉じた機能語尾。内容連の隣接に数えない — 時効とは の とは、
#: 殺人罪の刑は の の・は。開いた賢さは持ち込まない。
_JA_FUNC_TAILS = ("の", "とは", "は", "が", "を", "に", "で", "へ", "と",
                  "や", "も", "から", "まで", "より", "です", "ですか",
                  "について", "ますか", "でしょうか")


def ja_whole_subject(query: str, r: str) -> bool:
    """この連は問いの主題として独立に立っているか。

    ja_content_runs は文字種の境界で割るので、店に無い複合語の問いは
    「店に在る一片」に化ける(クワンタムフラックス炉 → 炉)。独立とは、
    元の問いの中でこの連の両隣が 空白か機能語尾 であること。内容字が
    隣接していれば、それは複合語の途中 — 主題ではなく盗まれた部品。
    """
    i = query.find(r)
    while i != -1:
        left_ok = True
        j = i - 1
        if j >= 0 and not query[j].isspace():
            left_ok = any(query[max(0, i - len(f)):i] == f
                          for f in _JA_FUNC_TAILS)
        right_ok = True
        j = i + len(r)
        if j < len(query) and not query[j].isspace():
            c = query[j]
            if "ぁ" <= c <= "ん":
                right_ok = any(query[j:j + len(f)] == f
                               for f in _JA_FUNC_TAILS)
            else:
                right_ok = False
        if left_ok and right_ok:
            return True
        i = query.find(r, i + 1)
    return False


def ja_subject_runs(store: CrossStore, query: str) -> List[str]:
    """店に在り、かつ問いの主題として独立に立つ連。空なら、この問いの
    主題は店に無い — 一片で選挙を開いてはならない、という合図。"""
    from .lang import ja_content_runs
    out = []
    for r in ja_content_runs(query):
        if ja_whole_subject(query, r) and (
                store.has(r) or store.has(r + PROPER_SUFFIX)):
            out.append(r)
    return out


def ja_consensus_ask(
    store: CrossStore,
    query: str,
    *,
    k: int = MAX_ARMS,
    cfg: Optional[ConsensusConfig] = None,
    placement_invariant: bool = False,
) -> Dict[str, Any]:
    """日本語の合意分解経路: 文字種 run → qset → 多断面合意 (ゲート共通).

    英語と同じ三段ゲート (合意・根拠・接地) が run ベースの qset で動く。
    候補ゼロは型付き拒否。文書は選ばれた腕の core+facets を「は/、」で連結。
    """
    from .lang import ja_content_runs

    runs = ja_content_runs(query)
    if not runs:
        return {"verdict": "UNKNOWN_UNPARSED", "lang": "ja"}
    qset = set(runs)
    # 複合語の一片を核にしない — 取り込み側 (ja_chosen_core, 2026-08-14 の
    # 連邦修理 103,599件) と同じ規則族を、問い側に。
    #
    # ja_content_runs は文字種の境界で割るので、店に無い複合語の問いは
    # 「店に在る一片」に化ける。実測 2026-08-18、蔵書外8語の探針で:
    #
    #     クワンタムフラックス炉 → 核 炉   → ANSWER 炉はd-d、ev、m3
    #     ヴァンデルグラーフ猫   → 核 猫   → ANSWER 猫は元プロレスラー
    #     ぷにゃぷにゃ理論       → 核 理論 → ANSWER 理論は説明、xバー
    #
    # 8件中6件が捏造。取り込み側は「核は同定可能な単一名詞主題のみ、
    # それ以外は型付き穴」で直した。ここも同じに引く: 元の問いの中で
    # 別の内容連と直接隣接している連 (間に助詞が無い) は、結合した
    # 複合語そのものが店に在るときだけ核になれる。無ければその一片は
    # 問いの主題ではなく、盗まれた部品である。
    #
    # 時効とは / 殺人罪の刑は が通り続けるのは、とは・の・は が閉じた
    # 機能語尾で、内容連の隣接に数えないから。過失 故意 は空白で切れて
    # いるので両方立つ。
    cores: List[str] = []
    for r in runs:
        for v in (r, r + PROPER_SUFFIX):
            if store.has(v) and v not in cores and ja_whole_subject(query, r):
                cores.append(v)
    # Facet-overlap fallback — English has had this since candidates_for_query
    # was written and Japanese never did, so the most natural legal question
    # was unanswerable: 「過失」 is a facet of many articles and a core of
    # none, and 「過失について定める条文は」 returned UNKNOWN_NO_EVIDENCE on a
    # store holding six statutes that all provide for it.
    #
    # Same guard as the English path, for the same reason: consulted ONLY
    # when nothing hit directly. Adding facet matches alongside a direct hit
    # lets a high-mass generic core displace the thing actually asked about.
    if not cores and qset:
        from .lex_filters import is_junk_core

        scored: List[Tuple[int, float, str]] = []
        for core, cross in store.crosses.items():
            # 「二」 arrived as a core carrying 1,015 facets on the six-statute
            # store — a numeral that collected content belonging to real
            # articles. Landing it on an arm gave every question a candidate
            # with almost no evidence of its own, and the shell's minimum
            # evidence went to zero, so 「過失」 refused despite having
            # 刑法第二百九条 and 民法第七百九条 right there in the list.
            if is_junk_core(core):
                continue
            overlap = len(qset & set(cross))
            if overlap:
                scored.append((-overlap, -store.mass(core), core))
        scored.sort()
        cores = [c for _o, _m, c in scored]
    if not cores:
        return {
            "verdict": "UNKNOWN_NO_EVIDENCE",
            "lang": "ja",
            "queried": runs,
            "retrieved": [],
        }
    shell = build_shell_from_store(store, cores[:k])
    out = run_consensus(
        shell, query, cfg=cfg, masses=_MassView(store), qset_override=qset
    ).as_dict()
    out["lang"] = "ja"
    out["retrieved"] = cores[:k]
    if out.get("verdict") == "ANSWER" and out.get("core"):
        core = out["core"]
        facets = [t for t in out.get("tokens", []) if t != core]
        out["text"] = core + ("は" + "、".join(facets) if facets else "")
    _apply_ja_coverage_gate(store, out, runs)
    if placement_invariant:
        _apply_placement_invariance(store, out, query, k=k, cfg=cfg, ja=True)
        if out.get("verdict") == "ANSWER" and out.get("placement_invariant"):
            # ja 経路は core_key を持たず、鍵は core に入る(EN 経路と
            # フィールドが違う)。core_key だけを読んで locks が常に空に
            # なる書き方を一度した — 店の性質ではなく配線の誤りだった。
            out["locks"] = settled_axes(shell, store,
                                        out.get("core_key") or out.get("core"))
        # 向きの不変性も同じ observe 傘の下(単一ソブリン: 同じ門を全扉で)。
        # 被覆は枠剥がし後の主題で数える — 枠語(〜に関係する)混入は
        # 逆方向の誤答を 0→23.7% に跳ねさせた実測がある。
        _apply_direction_invariance(store, out, frame_stripped(query, runs))
    # 逆方向の唯一候補(REVERSE_UNIQUE、2026-08-19)。順方向が棄権した
    # 問いに限り、被覆最大帯が唯一で被覆≥2語なら、型付き回答として出す。
    # ANSWER ではない — SEEDED と同じ非昇格の型で、到達経路(覆った語)を
    # 名乗る。実測(PREREG_PROMOTION/2): 裸3語 163/0、自然文包装 163/0
    # (枠剥がし後)、名前形100本の順方向 ANSWER は不変。
    if out.get("verdict") != "ANSWER":
        from .lex_filters import norm_words as _nw
        _q2 = frame_stripped(query, runs)
        if _q2:
            _band, _best = direction_band(store, _q2)
            # 帯割れの特定性裁定(REVERSE_SPECIFIC、2026-08-19)。順方向の
            # 敗因は証拠の不到達ではなく axis_energy の 質量×名前一致 が
            # 被覆信号を溺れさせること(実測: 正解は候補に92%居るのに
            # 236敗、全facet重なりの反実仮想でも8勝のみ)。分離する信号は
            # 特定性 = 被覆語数/面数 の孤立度: 正解時のマージン中央値21.3
            # vs 誤答時1.14。しきい値5.0は第三の核集合で確認(46/0×2族、
            # PREREG2)。3.0は確認集合で誤答1が出て事前登録どおり棄却した。
            # 僅差の帯は問いが核を特定していない — 棄権が正しい。
            if len(_band) > 1 and _best >= 2:
                _sp = sorted(
                    ((len([w for w in _q2
                           if w in (store.crosses.get(c) or {})
                           or w in _nw(c)])
                      / max(1, len(store.crosses.get(c) or {})), c)
                     for c in _band), reverse=True)
                if _sp[0][0] != _sp[1][0] and _sp[0][0] / _sp[1][0] >= 5.0:
                    _c = _sp[0][1]
                    _cov = sorted(_q2 & (set(store.crosses.get(_c) or {})
                                         | _nw(_c)))
                    out = dict(out)
                    out["forward_verdict"] = out.get("verdict")
                    out["verdict"] = "REVERSE_SPECIFIC"
                    out["core"] = display_sym(_c)
                    out["core_key"] = _c
                    out["reverse_coverage"] = _best
                    out["covered"] = _cov
                    out["specificity_margin"] = round(_sp[0][0] / _sp[1][0], 2)
                    out["runner_up"] = display_sym(_sp[1][1])
                    _fs = [t for t, _n in store.top_facets(_c, k=4)]
                    out["text"] = display_sym(_c) + (
                        "は" + "、".join(display_sym(x) for x in _fs)
                        if _fs else "")
                    out["note"] = ("順方向は棄権。逆方向の被覆最大帯は割れて"
                                   "いるが、特定性(被覆/面数)が次点の"
                                   f"{out['specificity_margin']}倍で孤立 — "
                                   "覆った語: " + "、".join(_cov)
                                   + "。次点: " + out["runner_up"]
                                   + "。ANSWERではなく、裁定根拠ごと示す"
                                     "型付き回答")
                    return out
            if len(_band) == 1 and _best >= 2:
                _c = next(iter(_band))
                _cov = sorted(_q2 & (set(store.crosses.get(_c) or {})
                                     | _nw(_c)))
                out = dict(out)
                out["forward_verdict"] = out.get("verdict")
                out["verdict"] = "REVERSE_UNIQUE"
                out["core"] = display_sym(_c)
                out["core_key"] = _c
                out["reverse_coverage"] = _best
                out["covered"] = _cov
                _fs = [t for t, _n in store.top_facets(_c, k=4)]
                out["text"] = display_sym(_c) + (
                    "は" + "、".join(display_sym(x) for x in _fs) if _fs else "")
                out["note"] = ("順方向は棄権。逆方向(問いを最も覆う核)の"
                               "唯一候補 — 覆った語: " + "、".join(_cov)
                               + "。ANSWERではなく、被覆という到達経路ごと"
                                 "示す型付き回答")
    return out


def _apply_ja_coverage_gate(
    store: CrossStore, out: Dict[str, Any], runs: List[str],
) -> None:
    """The Japanese path must not answer a question it did not address.

    This gate did not exist. `consensus_over_store` ran three — sense
    selection, coverage, polarity — and `ja_consensus_ask` ran none, so on
    the language this engine was built for, a question naming two parties
    came back as a confident ANSWER about one of them:

        「甲は乙を脅迫した。乙は丙を傷害した。」
        ask 「甲 丙」  ->  ANSWER  「甲は主犯、乙、脅迫」

    Nothing in that answer is false, and it is still a fabrication: 丙 was
    asked about and silently dropped. For a system whose entire claim is
    that it refuses rather than guesses, an open channel like this on the
    primary language is the defect that matters most.

    The downgrade fires only for a term the store KNOWS — as a core or as
    anyone's facet. A term it has never seen is a vocabulary gap, which is
    reported and left to the approval queue rather than treated as a reading
    failure; that division is the same one the rest of the package makes.
    """
    if out.get("verdict") != "ANSWER":
        return
    covered = {out.get("core") or ""}
    covered |= {t for t in (out.get("tokens") or [])}
    for tok in str(out.get("text", "")).replace("は", "、").split("、"):
        if tok:
            covered.add(tok)
    uncovered = [r for r in runs if r not in covered]
    if not uncovered:
        out["uncovered_terms"] = []
        return
    out["uncovered_terms"] = uncovered

    # A role-tagged token is a composite, and for composites "never seen"
    # means the OPPOSITE of what it means for a plain word. Asked 「事象二
    # 対象甲」 against a store holding 対象丙, the token 対象甲 is unseen —
    # and treating that as a vocabulary gap answers a question the store
    # positively refutes. Checked before the unknown-term branch for exactly
    # that reason. See verantyx/events.py.
    from .events import role_refutation

    from .events import split_role

    core_key = out.get("core_key") or out.get("core")
    refutations = [r for r in (role_refutation(store, core_key, t)
                               for t in uncovered) if r] if core_key else []

    # A role claim has three outcomes, never two: the store confirms it, the
    # store fills that role differently (refutation, below), or the role is
    # absent and the store does not know. The third was answering ANSWER —
    # asked 「事象2 場所東京」 against an event with no 場所, it returned the
    # whole event and said nothing about where. That is the same shape as the
    # 甲/丙 fabrication this gate exists to stop, one level down.
    unfilled = [t for t in uncovered if split_role(t)[0] is not None
                and not any(r["asked"] == split_role(t)[1]
                            and r["role"] == split_role(t)[0] for r in refutations)]
    if unfilled and not refutations:
        out["verdict"] = "UNKNOWN_INSUFFICIENT_EVIDENCE"
        out["reason"] = "role_not_recorded:" + ",".join(unfilled)
        out["unfilled_roles"] = unfilled
        out["core"] = None
        out["text"] = ""
        return

    if refutations:
        out["verdict"] = "UNKNOWN_ROLE_MISMATCH"
        out["reason"] = "role_filled_differently:" + ",".join(
            f"{r['role']}={'/'.join(r['held'])}≠{r['asked']}" for r in refutations)
        out["role_refutations"] = refutations
        out["core"] = None
        out["text"] = ""
        return

    known = [r for r in uncovered
             if store.has(r) or any(r in c for c in store.crosses.values())]
    if not known:
        out["unknown_terms"] = uncovered
        return
    out["verdict"] = "UNKNOWN_INSUFFICIENT_EVIDENCE"
    out["reason"] = "query_terms_not_addressed:" + "_".join(known)
    out["core"] = None
    out["text"] = ""


def probe_coverage(
    store: CrossStore,
    queries: List[str],
    *,
    k: int = MAX_ARMS,
) -> Dict[str, Any]:
    """クエリ集合に対する verdict 内訳 (coverage 測定)."""
    breakdown: Dict[str, int] = {}
    answers: List[Dict[str, Any]] = []
    for q in queries:
        out = consensus_over_store(store, q, k=k)
        v = out["verdict"]
        breakdown[v] = breakdown.get(v, 0) + 1
        answers.append(
            {"query": q, "verdict": v, "core": out.get("core"), "text": out.get("text", "")}
        )
    n = max(1, len(queries))
    return {
        "n_queries": len(queries),
        "breakdown": breakdown,
        "answer_rate": round(breakdown.get("ANSWER", 0) / n, 4),
        "samples": answers,
    }
