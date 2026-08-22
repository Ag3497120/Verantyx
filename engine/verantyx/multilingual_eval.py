"""Does the Japanese path actually carry a claim from a file to a verdict?

Written after measuring that it did not. Before the fixes this suite locks
in, a two-source Japanese corpus ingested as **zero sentences** — silently,
with a cheerful report — and the disaster-information path that exists for
Japanese readers was the one path that did not work in Japanese.

Six defects are pinned here, each a regression case:

  1. `_SENT` required whitespace after the full stop; Japanese writes 。 with
     none, so an article was one enormous "sentence".
  2. The minimum-sentence length was tuned for Latin text, where twelve
     characters is two words. Twelve characters of Japanese is a whole claim.
  3. `CrossStore.ingest_sentence` decomposes with `[A-Za-z0-9']+`, so Japanese
     produced one core, the entire sentence, and zero facets. The Japanese
     segmenter existed in `lang` and simply was not on this path.
  4. `ja_ingest_sentence` never passed `source=`, so provenance was empty and
     every "which source said this" came back blank.
  5. `CrossStore.track_provenance` defaults to False, so attribution was
     empty even in English unless the caller happened to know the flag.
  6. Language detection ran on the sentence AFTER the "(reported by X)"
     suffix was appended, and the Latin in that suffix outvoted a short
     Japanese sentence — routing it back to the English decomposer.

Plus the one that matters most for trust: the Japanese polarity vocabulary
must not manufacture contradictions. 停止線 (a painted stop line) and 危険物
(hazardous materials) both produced poles in the first version, and a report
that invents a disagreement is worse than one that misses it.

Run:  python3 -m verantyx.multilingual_eval
"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List

from .cross_store import CrossStore
from .document_ingest import Document, deep_report, ingest_documents
from .document_loaders import SUPPORTED, load_directory, load_path
from .lang import detect
from .polarity import detect_ja, ingest_polar_ja

#: Sentences that must NOT produce a pole. Every one contains a polar term as
#: part of a compound noun, which is the shape that fooled the first version.
CONTROLS: List[str] = [
    "会議を開始します。",
    "資料を公開しました。",
    "事業を展開しています。",
    "受付時間は9時からです。",
    "停止線で止まってください。",
    "復旧作業の説明会を開催します。",
    "危険物取扱者の資格が必要です。",
    "通行止標識を設置。",
    # The reliability-vocabulary pairs ride the same guard; each of these
    # contains a pair member inside a compound and must stay silent.
    "運行状況を確認してください。",
    "有効期限は明日までです。",
    "無効化の手順を説明します。",
    "開館時間は9時です。",
    # A trap for a future vocabulary addition rather than for the code.
    # Measured on 内閣府's 令和8年熊本地震 reports: 370 occurrences of state
    # words the vocabulary does NOT hold, led by 障害 at 133 — the obvious
    # partner for 稼働, and the one that must never be added. The compound
    # guard rejects 障害者 and 障害物 because the next character is kanji, and
    # lets 「障害のある方」 through, because の is a particle. Adding 障害 would
    # read the evacuation of people with disabilities as a system failure, in
    # the documents written for them. If a later change puts 障害 in the
    # vocabulary, this line fails first.
    "障害のある方の避難について",
    "障害者への配慮が必要です。",
]

#: (sentence, expected aspect, expected value)
POLAR: List[tuple] = [
    ("避難所は開設されました。", "開設", "開設"),
    ("避難所は閉鎖されました。", "開設", "閉鎖"),
    ("国道4号は通行止です。", "通行可能", "通行止"),
    ("国道4号は通行可能になりました。", "通行可能", "通行可能"),
    ("この区域は危険です。", "安全", "危険"),
    ("水道は復旧しました。", "復旧", "復旧"),
    ("受付終了しました。", "受付中", "受付終了"),
    ("山手線は運休です。", "運行", "運休"),
    ("このパスは無効です。", "有効", "無効"),
    ("当館は閉館しております。", "開設", "閉館"),
    # Humble-register negation: 〜しておりません flips the pole.
    ("当館は開館しておりません。", "開設", "not_開館"),
]


def main() -> int:
    print("multilingual — Japanese ingestion, polarity, and file loaders\n")
    failures: List[str] = []

    # -- 1. No manufactured contradictions ---------------------------------
    bad = [(s, detect_ja(s)) for s in CONTROLS if detect_ja(s)]
    ok = not bad
    print(f"[{'ok  ' if ok else 'FAIL'}] {len(CONTROLS)} compound-noun controls "
          f"produce no pole")
    for s, hit in bad:
        print(f"        invented: {s} -> {hit}")
    if not ok:
        failures.append("false-positive polarity")
    print()

    # -- 2. Real oppositions are found -------------------------------------
    for sentence, aspect, value in POLAR:
        hits = detect_ja(sentence)
        got = [(a, v) for a, v, _ in hits]
        ok = (aspect, value) in got
        print(f"[{'ok  ' if ok else 'FAIL'}] {sentence} -> {got or 'nothing'}")
        if not ok:
            failures.append(f"polarity: {sentence}")
    print()

    # -- 3. Script routing -------------------------------------------------
    cases = [("避難所は開設されました。", "ja"),
             ("The shelter is open.", "en"),
             # The suffix ingestion appends must not flip the vote.
             ("避難所は開設されました。 (reported by f.docx)", "ja")]
    for text, expect in cases:
        got = detect(text)
        ok = got == expect
        # The third case is the interesting one and is allowed to be wrong
        # here — what matters is that ingestion detects on the ORIGINAL, which
        # the end-to-end check below proves.
        if text.endswith("(reported by f.docx)"):
            print(f"[note] detect on a tagged sentence returns '{got}' — this "
                  f"is why ingestion detects on the untagged text")
            continue
        print(f"[{'ok  ' if ok else 'FAIL'}] detect({text[:24]}…) = {got}")
        if not ok:
            failures.append(f"detect: {text}")
    print()

    # -- 4. End to end: two Japanese sources that disagree -----------------
    store = CrossStore()
    docs = [
        Document("A新聞", "国道4号は土砂崩れで通行止です。"
                          "本町の避難所は開設されました。毛布を配布しています。"),
        Document("B放送", "国道4号は通行可能になりました。"
                          "本町の避難所は閉鎖されました。"),
    ]
    rep = ingest_documents(store, docs)
    ok = rep.sentences == 5
    print(f"[{'ok  ' if ok else 'FAIL'}] 5 Japanese sentences ingested "
          f"(got {rep.sentences}; was 0 before the splitter and router fixes)")
    if not ok:
        failures.append(f"ingest count {rep.sentences}")

    ok = rep.polar_claims > 0
    print(f"[{'ok  ' if ok else 'FAIL'}] polar claims counted: {rep.polar_claims}")
    if not ok:
        failures.append("polar_claims counted with the English detector only")

    # The core is 国道4号 with the digits INTACT — the first segmenter
    # split it into 国道+号 and dropped the 4, which in a legal or medical
    # corpus is the difference between citing the right article and citing
    # nothing. The old key is asserted absent so a regression cannot pass by
    # filing facts under both.
    ok = "国道" not in store.crosses
    print(f"[{'ok  ' if ok else 'FAIL'}] digits survive: the core is 国道4号, "
          f"and the digit-stripped 国道 does not exist")
    if not ok:
        failures.append("digit-stripped core resurfaced")

    road = deep_report(store, "国道4号")
    contested = road["confidence"] == "contested"
    print(f"[{'ok  ' if contested else 'FAIL'}] 国道4号 is contested, not blended "
          f"into one story")
    if not contested:
        failures.append("contradiction not detected in Japanese")

    # Attribution: the point of ingesting several sources.
    attributed = all(side.get("sources")
                     for d in road["disputed"] for side in d["sides"])
    print(f"[{'ok  ' if attributed else 'FAIL'}] every contested side names "
          f"which source said it")
    if not attributed:
        failures.append("source attribution empty")

    # The outlet's own name must not become a fact about the road.
    leaked = [s["claim"] for s in road["settled"]
              if s["claim"] in {"新聞", "放送", "A新聞", "B放送"}]
    ok = not leaked
    print(f"[{'ok  ' if ok else 'FAIL'}] source labels stay out of the facts "
          f"{('(leaked: ' + str(leaked) + ')') if leaked else ''}")
    if not ok:
        failures.append("attribution vocabulary leak")
    print()

    # -- 4b. Composition: long, grammatical, and never invented -------------
    from .arm_schema import ArmIndex
    from .compose import compose_digest, compose_report, unsupported_sentences

    arms = ArmIndex()
    store2 = CrossStore()
    ingest_documents(store2, docs, arms)
    road = compose_report(store2, "国道4号", arms=arms)

    # The two defects the first version produced, kept as regressions.
    # 「通行可能しています」came from inferring the predicate form from kanji
    # count; the polar vocabulary is closed, so the form is stated per term.
    ok = "通行可能です" in road.text and "しています" not in road.text.split("通行")[0]
    print(f"[{'ok  ' if ok else 'FAIL'}] polar terms take their real predicate "
          f"form, not one inferred from shape")
    if not ok:
        failures.append("ja predicate form")

    # A claim cannot be settled and contested in the same report. Replaying a
    # source sentence reintroduced this, because the sentence carrying the
    # disputed word is itself a real sentence.
    ok = not ("以下は確認された情報です。以下は" in road.text)
    print(f"[{'ok  ' if ok else 'FAIL'}] no empty 'settled' heading when "
          f"everything under it is contested")
    if not ok:
        failures.append("empty settled heading")

    digest = compose_digest(store2, ["国道", "本町", "毛布", "水道"], arms=arms)
    bad = unsupported_sentences(store2, digest)
    ok = not bad
    print(f"[{'ok  ' if ok else 'FAIL'}] {len(digest.text)} characters composed, "
          f"none unsupported by the store")
    for b in bad[:3]:
        print(f"        invented: {b}")
    if not ok:
        failures.append("composed sentence with no stored backing")
    print()

    # -- 4b2. Head-final cores and negation ---------------------------------
    # 「本町の避難所」is about the shelter, not the neighbourhood: Japanese is
    # head-final, so the topic's LAST noun is the core. Before this rule the
    # shelter's open/closed status was filed under 本町 and a query about
    # 避難所 found nothing.
    ok = "避難所" in store.crosses
    shelter = deep_report(store, "避難所")
    ok = ok and shelter["confidence"] == "contested"
    print(f"[{'ok  ' if ok else 'FAIL'}] head-final: the shelter's dispute is "
          f"filed under 避難所, not under its neighbourhood")
    if not ok:
        failures.append("head-final core")

    # 「安全ではありません」 was stored as 安全(+) — the pole inverted, a safety
    # claim manufactured from its own denial. The worst single defect found
    # in this module, pinned hardest.
    neg_cases = [
        ("この道は安全ではありません。", "not_安全", "-"),
        ("設備は稼働していません。", "not_稼働", "-"),
        ("この道は安全です。", "安全", "+"),
        ("設備は稼働しています。", "稼働", "+"),
    ]
    for sentence, value, pol in neg_cases:
        hits = detect_ja(sentence)
        ok = any(v == value and p == pol for _a, v, p in hits)
        print(f"[{'ok  ' if ok else 'FAIL'}] negation: {sentence} -> "
              f"{[(v, p) for _a, v, p in hits]}")
        if not ok:
            failures.append(f"negation: {sentence}")

    # Chinese routes away from the Japanese path. Before: 如果 and 配置
    # appeared as catalogue topics with Chinese facets under a "ja" label.
    zh_ok = detect("如果配置错误，网关将无法启动。") == "zh"
    ja_ok = detect("交通情報") == "ja"          # short han-only is normal Japanese
    ok = zh_ok and ja_ok
    print(f"[{'ok  ' if ok else 'FAIL'}] script split: han-without-kana prose "
          f"is zh, a short han label stays ja")
    if not ok:
        failures.append("zh/ja detection")
    print()

    # -- 4b3. Enumerated subjects, from a real miss -------------------------
    # 「九州自動車道、南九州自動車道など通行止めが発生しております」— the one
    # government release in the live-disaster corpus that actually reported a
    # closure, and the gate placed nothing: the road names sit in a list and
    # 通行止め itself carries が. A person reads it as the road being closed.
    #
    # The pair below is the whole point: the polar term INSIDE a list is being
    # named (「開設、運営等については」), the polar term AFTER a list closed by
    # など/等 is predicated of the items. Both must keep working.
    from .polarity import subject_of
    enum_cases = [
        ("九州自動車道、南九州自動車道など通行止めが発生しております。",
         "通行止", "九州自動車道"),
        ("国道4号、県道7号など通行止が続いています。", "通行止", "国道4号"),
        ("避難所の開設、運営等については留意事項を発出しています。", "開設", None),
        ("避難所が閉鎖した後にPCR検査を実施した。", "閉鎖", None),
    ]
    for sentence, word, expect in enum_cases:
        got = subject_of(sentence, word, "ja")
        ok = got == expect
        print(f"[{'ok  ' if ok else 'FAIL'}] enumerated subject: {sentence[:26]}… "
              f"-> {got}")
        if not ok:
            failures.append(f"enumerated subject: {sentence[:20]}")
    print()

    # -- 4b4. ・ is punctuation that lives in the katakana block -------------
    # The four-revision 内閣府 corpus produced exactly one contradiction and it
    # was false: every line of a government damage report is bulleted with ・,
    # the block range took it as a katakana word, and it became a CORE — so an
    # unrelated 復旧 sentence and an unrelated 断水 table were filed as opposing
    # claims about the same subject.
    #
    # ー (U+30FC) sits in the same block and IS a letter. Dropping it would
    # shred every loanword, so both directions are pinned here.
    from .lang import ja_content_runs
    dot_cases = [
        ("・今後、施設の復旧を進める。", "・", False),
        ("福岡県 大川市 断水あり・漏水あり", "・", False),
        ("データセンターのラーメン構造をチェックする", "データセンター", True),
        ("・避難所は閉鎖されました", "避難所", True),
        # 水洗トイレ is one noun. Splitting at the script change filed it and
        # 汲み取り式のトイレ under the same トイレ, and the guidance's own
        # distinction between two kinds of toilet became a contradiction.
        ("水洗トイレが使用可能になった", "水洗トイレ", True),
        ("仮設トイレを設置", "仮設トイレ", True),
        ("水洗トイレが使用可能になった", "トイレ", False),
    ]
    for sentence, token, want in dot_cases:
        got = token in ja_content_runs(sentence)
        ok = got == want
        print(f"[{'ok  ' if ok else 'FAIL'}] katakana-block punctuation: "
              f"{token!r} in {sentence[:18]}… -> {got}")
        if not ok:
            failures.append(f"katakana-block punctuation: {token}")
    print()

    # -- 4b5. A polar term is a predicate and never a core -------------------
    # 「４県において断水が発生」 puts 断水 before が, so the head-final rule made
    # 断水 the core — and a core of 断水 makes `subject_is_core` ask whether the
    # claim is about 断水, which is trivially true. Every guard downstream
    # becomes a no-op, which is how the one detection 内閣府's damage reports
    # produced got through: 復旧 and 断水 on the core 断水, from two sentences
    # about different places.
    #
    # 開設準備 is the control. The vocabulary lists stems (通行止, not 通行止め),
    # so the test strips one trailing hiragana — and must not strip its way
    # into demoting a real topic that merely starts with a state word.
    from .cross_store import CrossStore as _CS
    from .lang import ja_ingest_sentence as _ingest
    core_cases = [
        ("○４県（15 自治体）において断水が発生（最大断水戸数約 108,100 戸）。", "断水"),
        ("九州自動車道、南九州自動車道など通行止めが発生しております。", "通行止め"),
        ("本町の避難所は開設されました。", None),
        ("開設準備が進んでいます。", None),
    ]
    for sentence, forbidden in core_cases:
        got = _ingest(_CS(), sentence)
        ok = got is not None and got != forbidden
        print(f"[{'ok  ' if ok else 'FAIL'}] core is a topic, not a state: "
              f"{sentence[:24]}… -> {got}")
        if not ok:
            failures.append(f"polar core: {sentence[:20]}")
    # The road case is the one a person can check by reading: 「九州自動車道…など
    # 通行止め」 must file under the road, because that is what it says.
    road = _ingest(_CS(), "九州自動車道、南九州自動車道など通行止めが発生しております。")
    ok = road == "九州自動車道"
    print(f"[{'ok  ' if ok else 'FAIL'}] the closure is filed under the road -> {road}")
    if not ok:
        failures.append("closure filed under the road")
    print()

    # -- 4b6. Table rows, and the two ways they lie ------------------------
    # Official damage reports keep their per-place facts in tables, and a row
    # has no particle: nothing marks a subject, so every row's claim used to
    # be dropped. Japanese tabular notation reads head-final like the rest of
    # the language — the state in the last column belongs to the noun before
    # it — and turning that on is what finally produced a true positive on
    # real documents (熊本市 断水 on 7/29, 復旧済 on 8/6, one agency, both
    # published).
    #
    # It also admitted two errors that this block exists to keep out.
    #
    # A HEADER is the same shape as a row. 「建物被害 停電 断水」 names three
    # columns and asserts nothing; a data cell marks its value (断水あり,
    # 復旧済), a header does not.
    #
    # A cell can NEGATE. 「ア 被災による通行止め：なし」 says there are no
    # closures, and reading it as 通行止 inverts the claim while attaching a
    # government citation to it — worse, by this module's standing terms, than
    # reporting nothing at all.
    from .polarity import detect_ja as detect_polar_ja
    row_cases = [
        ("熊本県  熊本市 断水あり", "断水", "熊本市"),
        ("太良町 断水あり", "断水", "太良町"),
        ("熊本市 約20,970 0 7/28～8/3 ・復旧済", "復旧", "熊本市"),
        ("建物被害 停電 断水", "断水", None),
        ("害、 停電、 断水、", "断水", None),
        # Compound cell values: 断水あり・漏水あり is ONE cell holding two
        # values, and requiring nothing after the term cost 3 of 6
        # restorations against a water table read by hand.
        ("天草市 断水あり・漏水あり", "断水", "天草市"),
        ("御船町 断水あり・漏水あり", "断水", "御船町"),
        ("合志市 断水あり（復旧済）", "復旧", "合志市"),
        # A cause is not a subject, and an enumerator is not a noun. These two
        # rows are different road networks in ONE 8/6 report, headed the same
        # way; taking 被災 for the subject made the document contradict itself.
        ("ア 被災による通行止め：なし", "通行止", None),
        ("ア 被災による通行止め：２県６区間", "通行止", None),
        ("停止 断水", "停止", None),
        ("避難所の開設、運営等について", "開設", None),
        ("開設状況一覧", "開設", None),
        ("使用不可の場合は連絡すること", "使用不可", None),
    ]
    for sentence, word, expect in row_cases:
        got = subject_of(sentence, word, "ja")
        ok = got == expect
        print(f"[{'ok  ' if ok else 'FAIL'}] table row: {sentence[:24]:26s} -> {got}")
        if not ok:
            failures.append(f"table row: {sentence[:18]}")
    for sentence, want in [("ア 被災による通行止め：なし", "not_通行止"),
                           ("通行止めなし", "not_通行止"),
                           ("通行止め：あり", "通行止"),
                           ("熊本市 約20,970 0 7/28～8/3 ・復旧済", "復旧")]:
        hits = detect_polar_ja(sentence)
        ok = any(v == want for _, v, _ in hits)
        print(f"[{'ok  ' if ok else 'FAIL'}] cell value: {sentence[:24]:26s} -> {hits}")
        if not ok:
            failures.append(f"cell value: {sentence[:18]}")
    print()

    # -- 4b7. The subject in the heading, the state in the row --------------
    # 内閣府 reports road closures as 「①高速道路」 followed by 「ア 被災による
    # 通行止め：２路線１３区間」. The row cannot say which network it is about,
    # and two of the five genuinely changed polarity across the four
    # revisions — 有料道路 gained a closure on 8/6, 直轄国道 cleared after 7/29.
    # They were the entire remaining recall gap on that corpus.
    #
    # The dangerous half is the heading being WRONG rather than missing. PDF
    # extraction glues a heading to the line above it — 「…隣接区間被災②有料
    # 道路」 — and with the heading hidden, 有料道路's row was filed under
    # 高速道路: a network with thirteen closed sections reported as having
    # none. A circled numeral always begins an item, so the splitter cuts
    # before it, and that false positive is what this block pins.
    from .polarity import heading_subject_ja
    for text, expect in [("①高速道路", "高速道路"),
                         ("③直轄国道（直轄高速除く）", "直轄国道"),
                         ("【福岡県】", "福岡県"),
                         ("ア 被災による通行止め：なし", None),
                         ("7 0 7/28 ・復旧済", None),
                         ("建物被害 停電 断水", None),
                         ("①通行止め", None)]:
        got = heading_subject_ja(text)
        ok = got == expect
        print(f"[{'ok  ' if ok else 'FAIL'}] heading: {text[:22]:24s} -> {got}")
        if not ok:
            failures.append(f"heading: {text[:18]}")

    road = CrossStore()
    road.track_provenance = True
    ingest_documents(road, [
        Document("内閣府 7/29",
                 "①高速道路\nア 被災による通行止め：２路線１３区間\n"
                 "・E77 九州中央道（嘉島 ICT～小池高山 IC）：１区間：隣接区間被災②有料道路\n"
                 "ア 被災による通行止め：なし\n"),
        Document("内閣府 8/6",
                 "①高速道路\nア 被災による通行止め：２路線９区間\n"
                 "②有料道路\nア 被災による通行止め：１路線１区間\n")])
    fast = {k for k in road.crosses.get("高速道路", {}) if ":" in k}
    toll = {k for k in road.crosses.get("有料道路", {}) if ":" in k}
    ok = fast == {"通行可能:通行止"}
    print(f"[{'ok  ' if ok else 'FAIL'}] 高速道路 is closed in both revisions -> {fast}")
    if not ok:
        failures.append("glued heading leaked into the previous section")
    ok = toll == {"通行可能:not_通行止", "通行可能:通行止"}
    print(f"[{'ok  ' if ok else 'FAIL'}] 有料道路 opens then closes -> {toll}")
    if not ok:
        failures.append("heading context not reaching its rows")
    print()

    # -- 4b8. Two suffixes that are grammar, not compounds ------------------
    # The compound guard rejects any kanji after a polar term, which is right
    # for 停止線 and 危険物 and wrong for two forms that carry the claim.
    #
    # 〜解除 NEGATES. 「滑走路閉鎖解除済」 says the runway reopened, and it was
    # being dropped as a compound — the guard was right that 閉鎖解 is not 閉鎖
    # and wrong about why. Reading it as 閉鎖 would have been far worse.
    #
    # 〜中 says the state is still running, and it is safe on exactly ONE side.
    # 「操業停止中」 is stopped; 「復旧中」 is being restored and is NOT restored.
    # Restricting 中 to the negative pole makes that inversion impossible by
    # construction, and 復旧中 is here so it stays impossible.
    for sentence, want in [("滑走路閉鎖解除済", "not_閉鎖"),
                           ("通行止め解除", "not_通行止"),
                           ("・パン製造工場では、操業停止中。", "停止"),
                           ("４自治体において約 37,600 戸が断水中。", "断水")]:
        hits = detect_ja(sentence)
        ok = any(v == want for _, v, _ in hits)
        print(f"[{'ok  ' if ok else 'FAIL'}] suffix is grammar: {sentence[:22]:24s}"
              f" -> {hits}")
        if not ok:
            failures.append(f"suffix: {sentence[:18]}")
    ok = not detect_ja("復旧中")
    print(f"[{'ok  ' if ok else 'FAIL'}] 復旧中 is NOT 復旧 -> {detect_ja('復旧中')}")
    if not ok:
        failures.append("中 inverted a transition into its completed state")
    print()

    # -- 4b9. Vocabulary added from a measured gap, and what stayed out -----
    # Measured on the four 内閣府 revisions: 308 segments held a state word and
    # produced no pole at all. 欠航 (22 of them) and 休止 (19) were the two
    # biggest that are unambiguous, and both are aspect joins onto pairs that
    # already exist rather than new pairs. The gap is now 249.
    #
    # 障害 is the largest single entry at 114 and is deliberately absent; the
    # control sentences at the top of this file are what keep it that way.
    for sentence, want in [("【7 月 28 日】欠航：29 便", "欠航"),
                           ("６金融機関 15 店舗が営業休止", "休止"),
                           ("（八代市：44 カ所）営業中 42 カ所", "営業中")]:
        hits = detect_ja(sentence)
        ok = any(v == want for _, v, _ in hits)
        print(f"[{'ok  ' if ok else 'FAIL'}] vocabulary: {sentence[:24]:26s} -> {hits}")
        if not ok:
            failures.append(f"vocabulary: {want}")
    # Placement is the real gate: a plan and a possibility must reach nobody,
    # however clearly the word is detected.
    for sentence in ["通常営業に戻る予定です", "運休の可能性", "休止符を打つ"]:
        one = CrossStore()
        ingest_polar_ja(one, sentence)
        placed = {k for f in one.crosses.values() for k in f if ":" in k}
        ok = not placed
        print(f"[{'ok  ' if ok else 'FAIL'}] not a claim: {sentence[:20]:22s} -> "
              f"{placed or 'nothing placed'}")
        if not ok:
            failures.append(f"placed from a non-claim: {sentence[:16]}")
    print()

    # -- 4b10. English periods that do not end sentences --------------------
    # The Japanese side spent this whole file learning that a page's layout is
    # not the author's punctuation. English has the same problem in one
    # character: a period inside an abbreviation. Measured across 600
    # documents and 82,813 segments of this author's repositories, 189
    # segments end at an abbreviation (etc. 83, al. 75) and e.g./i.e. are cut
    # in the middle of themselves — 「Your channels are still connected (e.」
    # was the whole sentence the store kept, and the worksheet showed a person
    # that fragment to judge.
    #
    # A sentence can lose its NEGATION the same way, which is why this is a
    # correctness fix and not a tidiness one.
    #
    # The abbreviation must match as a whole TOKEN. As a bare suffix, "ed."
    # matched every word ending in -ed. — 「The aquarium is closed.」 was
    # joined to the sentence after it and two planted contradictions vanished.
    # The generalization eval caught that, and both directions are pinned.
    from .document_ingest import _SENT as _SENT_RE
    from .document_ingest import _rejoin_abbreviations
    split_cases = [
        ("Your channels are still connected (e.g. Telegram). Next thing.", 2),
        ("Supports Telegram, Discord, etc. The following applies.", 2),
        ("Supports water, food, etc. and blankets are available.", 1),
        ("Smith et al. showed that the valve is closed.", 1),
        ("The aquarium is closed. The greenhouse is closed.", 2),
        ("The road is safe. It is not closed.", 2),
    ]
    for text, want in split_cases:
        parts = [x.strip() for x in _rejoin_abbreviations(_SENT_RE.split(text))
                 if x.strip()]
        ok = len(parts) == want
        print(f"[{'ok  ' if ok else 'FAIL'}] abbreviation: {text[:40]:42s} -> "
              f"{len(parts)} sentence(s)")
        if not ok:
            failures.append(f"abbreviation split: {text[:24]}")
    print()

    # -- 4b11. Table rows are line-atomic, found blind on a second agency ----
    # The generalization test this whole effort needed: 国交省's 第N報 series,
    # ingested with no code changes and read only afterwards. Five of six
    # restorations were found; the sixth, 天草市, was lost to a chain of two
    # layout defects that only this second corpus exposed:
    #
    #   「宇城市 約18,000 約9.900 7/28～ ・管破損に伴う漏水」 fills its column and
    #   ends in no punctuation, so unwrap read it as WRAPPED PROSE and glued
    #   天草市's row onto it with the CJK no-space join — the corpus then
    #   contained the word 漏水天草市, and the restoration was a claim about
    #   that non-word. A table row is line-atomic: prose never carries two
    #   whitespace-separated fields of bare digits and data punctuation.
    #
    #   約9.900 is a thousands comma typed as a period, and the splitter cut
    #   it into 約9. / 900. A period between digits is numeric.
    from .document_loaders import _is_table_row, unwrap_layout
    for line, want in [("宇城市 約18,000 約9.900 7/28～ ・管破損に伴う漏水", True),
                       ("天草市 約1,100 0 7/28～8/1 ・復旧済", True),
                       ("・熊本県では６日（木）、7 日（金）は高気圧に覆われて概ね晴れるが、"
                        "暖かく湿った空気の影", False),
                       ("①高速道路", False)]:
        got = _is_table_row(line)
        ok = got == want
        print(f"[{'ok  ' if ok else 'FAIL'}] table row is atomic: {line[:28]:30s}"
              f" -> {got}")
        if not ok:
            failures.append(f"table-row atomicity: {line[:20]}")
    glued = unwrap_layout(
        "宇城市 約18,000 約9.900 7/28～ ・管破損に伴う漏水\n"
        "天草市 約1,100 0 7/28～8/1 ・復旧済\n" + ("参考情報あ" * 8 + "\n") * 8)
    ok = "漏水天草市" not in glued
    print(f"[{'ok  ' if ok else 'FAIL'}] two rows never merge into 漏水天草市")
    if not ok:
        failures.append("adjacent table rows merged")
    parts = [x.strip() for x in _rejoin_abbreviations(
        _SENT_RE.split("宇城市 約18,000 約9.900 7/28～ ・管破損に伴う漏水"))
        if x.strip()]
    ok = len(parts) == 1
    print(f"[{'ok  ' if ok else 'FAIL'}] a period between digits is numeric -> "
          f"{len(parts)} segment(s)")
    if not ok:
        failures.append("decimal period split a data row")
    print()

    # -- 4b12. Conversation memory routes by script too ---------------------
    # `LayeredMemory.ingest_sentence` goes straight to the English decomposer,
    # so a Japanese turn produced ONE core — the whole sentence — and
    # 「避難所は本町に開設されました」 was stored under itself. `locate('避難所')`
    # then answered ABSENT about a topic the conversation had just discussed.
    #
    # ABSENT is the one verdict this module must never get wrong: it is the
    # answer to "did we talk about that", and a false ABSENT is exactly the
    # silent context loss the design exists to prevent. The document path
    # learned this months ago; the conversation path had not.
    from .conversation import Conversation as _Conversation
    from .layer_stack import LayeredMemory as _LayeredMemory
    conv = _Conversation(memory=_LayeredMemory())
    for speaker, said in [("user", "国道4号は土砂崩れで通行止です。"),
                          ("bot", "了解しました。"),
                          ("user", "避難所は本町に開設されました。"),
                          ("user", "毛布を配布しています。"),
                          ("user", "The bridge is closed.")]:
        conv.add_turn(speaker, said)
    for topic, want in [("国道4号", "ACTIVE"), ("避難所", "ACTIVE"),
                        ("毛布", "ACTIVE"), ("bridge", "ACTIVE"),
                        ("橋", "ABSENT"), ("給水所", "ABSENT")]:
        got = conv.locate(topic)["status"]
        ok = got == want
        print(f"[{'ok  ' if ok else 'FAIL'}] conversation locate({topic}) -> {got}")
        if not ok:
            failures.append(f"conversation locate: {topic}")
    # locate() and recall() must agree. `layered_ask` runs the English
    # consensus decomposer at every level, so a Japanese query returned
    # UNKNOWN_NO_EVIDENCE about a core sitting in the store while locate()
    # answered ACTIVE on the same word. Two APIs disagreeing about one memory
    # is worse than either being wrong alone — the caller cannot tell which to
    # believe, and the typed verdict stops meaning anything.
    for topic in ("国道4号", "避難所", "毛布", "bridge", "橋", "給水所"):
        loc = conv.locate(topic)["status"]
        rec = conv.recall(topic).get("verdict")
        agree = (loc == "ABSENT") == (rec == "UNKNOWN_NO_EVIDENCE")
        print(f"[{'ok  ' if agree else 'FAIL'}] locate/recall agree on {topic}: "
              f"{loc} / {rec}")
        if not agree:
            failures.append(f"locate/recall disagree: {topic}")
    print()

    # -- 4b13. Statutes: a third genre, read blind --------------------------
    # The first two blind corpora were both government DISASTER reports. This
    # one is 災害対策基本法, 消防法 and their enforcement orders — 334,330
    # characters of a genre with entirely different grammar. It produced two
    # detections and both were false, in two ways neither disaster corpus
    # could have shown:
    #
    #   Legal Japanese joins parties with 又は・若しくは・及び・並びに, and the
    #   ideograph run swallowed the head: 「消防長又は消防署長」 became 消防長又,
    #   a word that does not exist, and the first party to a provision was
    #   stored under it.
    #
    #   A statute DEFINES when something counts as dangerous; it does not say
    #   anything is. 「火災の予防に危険であると認める物件」 is a category, and
    #   reading it as a claim inverts what a regulation is for.
    #
    #   And 「に対して」 wraps one kanji in kana. 対 is the middle of a
    #   grammatical unit, and it was chosen as the SUBJECT of a fire-code
    #   provision.
    from .lang import _JA_RUN as _RUN
    for text, want, absent in [
        ("消防長又は消防署長", "消防長", "消防長又"),
        ("所有者、管理者又は占有者", "管理者", "管理者又"),
        ("消火若しくは避難", "消火", "消火若"),
        ("市町村及び都道府県", "市町村", "市町村及"),
        ("知事並びに市長", "知事", "知事並"),
        ("及第点を取る", "及第点", "及"),
        ("並木道を歩く", "並木道", "並"),
    ]:
        runs = _RUN.findall(text)
        ok = want in runs and absent not in runs
        print(f"[{'ok  ' if ok else 'FAIL'}] conjunction head: {text:16s} -> {runs}")
        if not ok:
            failures.append(f"conjunction head: {text}")

    for sentence, want in [
        ("火災の予防に危険であると認める物件の所有者に命ずる。", False),
        ("人命に危険であると認める場合には、改修を命ずる。", False),
        ("危険とみなす区域を指定する。", False),
        ("この区域は危険です。", True),
        ("避難所は閉鎖されました。", True),
    ]:
        one = CrossStore()
        ingest_polar_ja(one, sentence)
        placed = {k for f in one.crosses.values() for k in f if ":" in k}
        ok = bool(placed) == want
        print(f"[{'ok  ' if ok else 'FAIL'}] deeming clause: {sentence[:24]:26s} -> "
              f"{placed or 'nothing placed'}")
        if not ok:
            failures.append(f"deeming clause: {sentence[:20]}")

    for text, ch, want in [("当該現象に対して安全な構造", "対", False),
                           ("災害に関する情報", "関", False),
                           ("法令に基づく措置", "基", False),
                           ("水は使用できません", "水", True),
                           ("火に強い建物", "火", True)]:
        got = ch in ja_content_runs(text)
        ok = got == want
        print(f"[{'ok  ' if ok else 'FAIL'}] compound particle: {ch} in "
              f"{text[:16]:18s} -> {got}")
        if not ok:
            failures.append(f"compound particle: {ch}")
    print()

    # -- 4b14. The audit app is the pipeline, not a second one --------------
    # The tool exists so somebody OTHER than the person who wrote the fixes
    # can read the output — every "true by reading" judgement so far was made
    # by the party that then changed the code. It must therefore run the same
    # pipeline: a second ingestion path is a second thing that can disagree
    # with the first, which is the class of defect this file keeps recording.
    import base64 as _b64
    from .audit_app import analyse as _analyse
    _pair = [
        {"name": "A新聞.txt",
         "b64": _b64.b64encode("国道4号は土砂崩れで通行止です。"
                               "本町の避難所は開設されました。".encode()).decode()},
        {"name": "B放送.txt",
         "b64": _b64.b64encode("国道4号は通行可能になりました。"
                               "本町の避難所は閉鎖されました。".encode()).decode()},
    ]
    got = _analyse(_pair)
    topics = {d["topic"] for d in got.get("detections", [])}
    ok = got.get("verdict") == "ANSWER" and topics == {"国道4号", "避難所"}
    print(f"[{'ok  ' if ok else 'FAIL'}] audit app finds what the engine finds -> "
          f"{sorted(topics)}")
    if not ok:
        failures.append("audit app diverged from the engine")

    # A format with no loader is a TYPED refusal naming the file, never an
    # empty document — an empty document is indistinguishable from one that
    # genuinely said nothing.
    refused = _analyse([{"name": "x.exe", "b64": "AA=="}])
    ok = refused.get("verdict") == "UNKNOWN_NO_READABLE_DOCUMENTS"
    print(f"[{'ok  ' if ok else 'FAIL'}] audit app refuses by type -> "
          f"{refused.get('verdict')}")
    if not ok:
        failures.append("audit app did not refuse an unreadable format")

    ok = _analyse([]).get("verdict") == "UNKNOWN_NO_DOCUMENTS"
    print(f"[{'ok  ' if ok else 'FAIL'}] audit app refuses an empty request")
    if not ok:
        failures.append("audit app accepted an empty request")
    print()

    # -- 4b15. Municipal HTML: a fourth genre, read blind --------------------
    # Nine 熊本市 pages, three 熊本県, one 宇城市 — 44,540 characters of the
    # documents a resident actually reads, in the week-two register of
    # rebuilding rather than the first-days register of road closures. One
    # detection, and it was false in two independent ways.
    #
    # 〜されるまで is a period whose ENDPOINT is the state, so the state has
    # not arrived. 熊本県 offers hotel rooms 「避難所が閉鎖されるまでの間」 —
    # until your shelter closes — and reading it as "the shelter is closed"
    # tells someone their shelter is gone while it is open. An inversion: the
    # engine said the opposite of the source.
    #
    # And two DIFFERENT values are not a disagreement unless they sit on
    # opposite POLES. 開設 and 開館 are both the positive side of one aspect,
    # so 宇城市 saying 「避難所を開設しています」 and 熊本市 saying 「避難所として
    # 開館」 is two municipalities AGREEING. A contradiction report whose
    # contradictions are not contradictions is worse than no report.
    for sentence, want in [
        ("お住まいの市町村の避難所が閉鎖されるまでの間", False),
        ("避難所が閉鎖されるまで利用できます。", False),
        ("工事が完了するまで通行止めです。", True),   # まで BEFORE the term
        ("8月3日まで閉鎖します。", False),
        ("避難所は閉鎖されました。", True),
        ("避難所を開設しています", True),
    ]:
        one = CrossStore()
        ingest_polar_ja(one, sentence)
        placed = {k for f in one.crosses.values() for k in f if ":" in k}
        ok = bool(placed) == want
        print(f"[{'ok  ' if ok else 'FAIL'}] until-clause: {sentence[:26]:28s} -> "
              f"{placed or 'nothing placed'}")
        if not ok:
            failures.append(f"until clause: {sentence[:20]}")

    for label, values, want in [
        ("開設/開館 both +", ["開設:開設", "開設:開館"], False),
        ("閉鎖/閉館 both -", ["開設:閉鎖", "開設:閉館"], False),
        ("通行可能/not_通行止 both +",
         ["通行可能:通行可能", "通行可能:not_通行止"], False),
        ("開設/閉鎖 opposite", ["開設:開設", "開設:閉鎖"], True),
        ("復旧/断水 opposite", ["復旧:復旧", "復旧:断水"], True),
        ("通行止/not_通行止 opposite",
         ["通行可能:通行止", "通行可能:not_通行止"], True),
        ("open/closed opposite", ["open:open", "open:closed"], True),
    ]:
        one = CrossStore()
        one.track_provenance = True
        for v in values:
            one.add("x", {v: None}, source="s")
        got = bool(one.contradictions("x"))
        ok = got == want
        print(f"[{'ok  ' if ok else 'FAIL'}] same pole is agreement: {label:26s} -> "
              f"{'conflict' if got else 'agree'}")
        if not ok:
            failures.append(f"pole agreement: {label}")
    print()

    # -- 4b16. Operator announcements: a fifth genre, read blind -------------
    # NTT West, 九州電力, 熊本市上下水道局 — the utilities' own releases, which
    # is what a municipal officer checks their page against. Three dated NTT
    # releases of one notice (7/29, 7/30, 8/5) made the self-consistency case
    # explicit, and the 8/5 one announces the END of free payphone access.
    #
    # 終了 was not in the vocabulary. 実施/中止 covers a measure cancelled
    # before it ran; this is one that ran and then stopped, and across five
    # corpora 終了 appears 35 times and 再開 50 — the vocabulary of rebuilding
    # rather than of the first days. Both are joins onto the existing 実施
    # aspect, and 終了時刻 / 再開発 stay silent through the compound guard.
    for sentence, want in [("無料化を終了いたします。", "終了"),
                           ("窓口業務を再開しました。", "再開"),
                           ("公衆電話の無料化を実施しております。", "実施")]:
        hits = detect_ja(sentence)
        ok = any(v == want for _, v, _ in hits)
        print(f"[{'ok  ' if ok else 'FAIL'}] rebuilding vocabulary: {sentence[:20]:22s}"
              f" -> {hits}")
        if not ok:
            failures.append(f"rebuilding vocabulary: {want}")
    for sentence in ("終了時刻を確認する", "再開発事業の計画", "業務終了時間の変更"):
        ok = not detect_ja(sentence)
        print(f"[{'ok  ' if ok else 'FAIL'}] control stays silent: {sentence[:16]:18s}"
              f" -> {detect_ja(sentence)}")
        if not ok:
            failures.append(f"rebuilding control: {sentence}")

    # A polar core demoted itself back. The fallback used the TOPIC phrase,
    # and when that phrase was entirely the polar term —
    # 「断水が発生していましたが、復旧しました」 — the list came back empty and
    # the core fell back to the same word. A sentence with no identifiable
    # subject is better left out than filed under the word for its state.
    from .lang import ja_ingest_sentence
    for sentence, forbidden in [("断水が発生していましたが、復旧しました。", "断水"),
                                ("避難所を開設していましたが、閉鎖しました。", "開設")]:
        core = ja_ingest_sentence(CrossStore(), sentence)
        ok = core != forbidden
        print(f"[{'ok  ' if ok else 'FAIL'}] polar core demotion holds: "
              f"{sentence[:22]:24s} -> {core}")
        if not ok:
            failures.append(f"polar core demotion: {sentence[:18]}")
    ok = ja_ingest_sentence(CrossStore(), "断水。") is None
    print(f"[{'ok  ' if ok else 'FAIL'}] a fragment with no subject stores nothing")
    if not ok:
        failures.append("subjectless fragment stored")
    # A run stolen from a compound is not a topic. クロイツ-タウブ塩 is one
    # name; レモン果汁 is one noun; ウマ (麻雀) is a sense. Filing them
    # under 塩 / レモン / ウマ manufactured the federation's two W3b lies.
    for sentence, forbidden in [
        ("クロイツ-タウブ塩が代表例。", "塩"),
        ("レモン果汁20%使用し、クエン酸を機能性表示成分として配合した"
         "155ml瓶入り（炭酸ガス入り）。", "レモン"),
        ("ウマ (麻雀)は、麻雀の牌の一つである。", "ウマ"),
    ]:
        got = ja_ingest_sentence(CrossStore(), sentence)
        ok = got != forbidden
        print(f"[{'ok  ' if ok else 'FAIL'}] compound/paren is not a stolen run: "
              f"{sentence[:22]:24s} -> {got}")
        if not ok:
            failures.append(f"stolen run: {sentence[:18]}")
    ok = ja_ingest_sentence(CrossStore(), "本町の避難所は開設されました。") == "避難所"
    print(f"[{'ok  ' if ok else 'FAIL'}] の-headed topic still files under the head")
    if not ok:
        failures.append("head-final の-phrase")

    # A date the LAYOUT broke apart. 「７月 30 日」 spaces the digits from their
    # unit, so 日 survived alone and became the CORE — 内閣府's ferry table
    # filed 7/29 and 7/30 under one topic called 日 and reported them as a
    # contradiction. Two different days, read as one thing disagreeing with
    # itself.
    for text, token, want in [("【７月 30 日～】欠航：なし", "日", False),
                              ("16 時 27 分に発生", "時", False),
                              ("日程を確認する", "日程", True),
                              ("本日は晴れ", "本日", True)]:
        got = token in ja_content_runs(text)
        ok = got == want
        print(f"[{'ok  ' if ok else 'FAIL'}] split date piece: {token!r} in "
              f"{text[:18]:20s} -> {got}")
        if not ok:
            failures.append(f"split date piece: {token}")

    # An HTML table row is the unit, not a cell. Each <td> arrives as its own
    # text node, so 熊本市's closure table gave the dates and the facility
    # names as separate fragments — 244 rows of a state with no subject and a
    # subject with no state. The header row says which column is the subject,
    # because an HTML table's column ORDER is set by whoever built the page.
    from .document_loaders import _from_html as _html
    _table = ("<table><tbody>"
              "<tr><td>NO</td><td>閉鎖期間</td><td>施設名</td></tr>"
              "<tr><td>1</td><td>7/28(火)～7/31(金) ※8/1～開館</td>"
              "<td>熊本市職業訓練センター</td></tr></tbody></table>")
    lines = [ln for ln in _html(_table).splitlines() if ln.strip()]
    ok = len(lines) == 1 and lines[0].startswith("熊本市職業訓練センター")
    print(f"[{'ok  ' if ok else 'FAIL'}] html row is one line, subject first -> "
          f"{lines}")
    if not ok:
        failures.append("html table row not assembled")
    print()

    # -- 4b17. A defect report carries no document ---------------------------
    # Five genres read blind, three defects each, and the rate is not falling.
    # A release therefore has to assume defects keep arriving — which means
    # the people who find them must be able to report them, in documents that
    # are municipal drafts and evacuee registers.
    #
    # Every defect found so far is a grammatical SHAPE, not a fact about any
    # document, so a report keeps the function words, the punctuation and the
    # polar term (public vocabulary) and redacts everything else. The property
    # is asserted here rather than trusted: a claim about privacy that is not
    # tested is a hope.
    from .defect_report import build as _build_defect
    from .defect_report import leaks as _leaks
    from .defect_report import skeleton as _skeleton

    _private = [
        "中央公民館の避難所は閉鎖されました。 (reported by 宇城市_避難所名簿.pdf)",
        "熊本県  熊本市 断水あり (reported by 20260729.pdf)",
        "お住まいの市町村の避難所が閉鎖されるまでの間で、各ホテル等が受け入れ可能",
        "消防長又は消防署長は、火災の予防に危険であると認める物件の所有者に命ずる。",
        "山田太郎さん宅は断水しています。電話 096-123-4567。",
    ]
    for sentence in _private:
        shape = _skeleton(sentence)
        found = _leaks(sentence, shape)
        ok = not found
        print(f"[{'ok  ' if ok else 'FAIL'}] redaction leaks nothing: "
              f"{sentence[:22]:24s} -> {shape[:34]}")
        if not ok:
            failures.append(f"redaction leak: {found}")

    # The shape must SURVIVE — a report that redacts the defect too is a
    # report of nothing.
    keeps = [("お住まいの市町村の避難所が閉鎖されるまでの間で", "閉鎖されるまで"),
             ("消防長又は消防署長は、危険であると認める物件", "又は"),
             ("公衆電話の無料化を実施しておりましたが、終了いたします。",
              "しておりましたが")]
    for sentence, fragment in keeps:
        shape = _skeleton(sentence)
        ok = fragment in shape
        print(f"[{'ok  ' if ok else 'FAIL'}] the defect shape survives: "
              f"{fragment} -> {shape[:34]}")
        if not ok:
            failures.append(f"shape lost: {fragment}")

    # And the builder REFUSES rather than emitting something it cannot
    # guarantee.
    try:
        _build_defect("false_positive", ["熊本市は断水しています。"],
                      aspect="復旧", value="断水")
        built = True
    except ValueError:
        built = False
    print(f"[{'ok  ' if built else 'FAIL'}] a clean report builds")
    if not built:
        failures.append("defect report failed to build")
    print()

    # -- 4b18. A report becomes a gap, and the same defect twice becomes one --
    # The loop this closes: a person marks a finding false, the report carries
    # no document, and the report is a typed failure — which `gap_graph` was
    # built for. What a report has that a growth bucket does not is the name
    # of the RULE that decided it, and that makes aggregation a lookup.
    #
    # Two earlier keys failed the same way: a fixed character window and a
    # cut-at-the-first-noun both split one defect into three, because
    # 「閉鎖されるまでの間で」 and 「閉鎖されるまで利用できます」 differ in what
    # follows the grammar — and what follows the grammar is not the defect.
    from .defect_gaps import classify as _classify
    from .defect_gaps import proposal as _proposal
    from .defect_gaps import record as _record
    from .defect_report import build as _bd
    from .defect_report import frame as _frame
    from .gap_graph import GapGraph as _GapGraph

    _same = [("お住まいの市町村の避難所が閉鎖されるまでの間で", "閉鎖"),
             ("受付が閉鎖されるまで利用できます", "閉鎖"),
             ("工事完了まで避難所が閉鎖されるまでの期間", "閉鎖")]
    keys = {_frame(sent, term) for sent, term in _same}
    ok = len(keys) == 1
    print(f"[{'ok  ' if ok else 'FAIL'}] one defect, one key -> {sorted(keys)}")
    if not ok:
        failures.append(f"defect key split: {keys}")

    # The key must carry no text from the document — a rule name is this
    # repository's own vocabulary.
    key = next(iter(keys))
    leaked = [w for w in ("避難所", "受付", "工事", "市町村") if w in key]
    ok = not leaked
    print(f"[{'ok  ' if ok else 'FAIL'}] the key carries no document text -> {key}")
    if not ok:
        failures.append(f"defect key leaked: {leaked}")

    _g = _GapGraph()
    _seen = []
    for sent, term in _same:
        _d = _bd("false_positive", [sent], aspect="開設", value=term)
        _seen.append(_record(_g, _d, [sent]))
    ok = ([r["status"] for r in _seen] == ["created", "reinforced", "reinforced"]
          and _seen[-1]["seen"] == 3)
    print(f"[{'ok  ' if ok else 'FAIL'}] three reports, one gap -> "
          f"{[(r['status'], r['seen']) for r in _seen]}")
    if not ok:
        failures.append("defect gaps did not aggregate")

    # Only a missing-vocabulary gap gets a proposal. For a rule defect the
    # report does not contain enough — deciding what a guard should admit
    # from one sentence is how a guard becomes too wide.
    _vocab = _bd("false_negative", ["給水所の運営を打ち切りました。"],
                 aspect="実施", value="打ち切り")
    ok = (_classify(_vocab, ["給水所の運営を打ち切りました。"])
          == "vocabulary_missing" and _proposal(_vocab) is not None)
    print(f"[{'ok  ' if ok else 'FAIL'}] a missing term proposes an overlay")
    if not ok:
        failures.append("vocabulary gap did not propose")

    _rule = _bd("false_positive", ["避難所が閉鎖されるまで"],
                aspect="開設", value="閉鎖")
    ok = _proposal(_rule) is None
    print(f"[{'ok  ' if ok else 'FAIL'}] a rule defect proposes nothing")
    if not ok:
        failures.append("rule defect produced a proposal")
    print()

    # -- 4b19. A gap becomes a rule, and the rule is measured ---------------
    # The loop was open at the far end: a defect became a GapNode and a person
    # still had to write the rule, which makes the growth loop one only its
    # authors can be in.
    #
    # Two facts close it without a model. Every reading rule this engine has
    # is the same shape — a pattern matched after a polar term, where a match
    # means the term asserts nothing — so it is derivable from examples. And
    # a candidate can be MEASURED against everything already confirmed true.
    #
    # The boundary the module will not cross: it can say a pattern breaks
    # nothing measured, and it cannot say the pattern is right.
    from .rule_synthesis import derive as _derive
    from .rule_synthesis import verify as _verify
    from . import ja_grammar as _grammar

    cand = _derive(["お住まいの市町村の避難所が閉鎖されるまでの間で",
                    "受付が閉鎖されるまで利用できます"], "閉鎖",
                   provenance="eval")
    ok = cand is not None and cand.pattern == "^されるまで"
    print(f"[{'ok  ' if ok else 'FAIL'}] a rule is derived from reports -> "
          f"{cand.pattern if cand else None}")
    if not ok:
        failures.append("rule derivation")

    # One report is not evidence for a rule, and a first attempt that cut at
    # the first content run anywhere threw away 「の方向で」 — where 方向 is
    # part of the construction, not the noun the sentence is about.
    ok = _derive(["本館は閉鎖の方向で検討しています。"], "閉鎖") is None
    print(f"[{'ok  ' if ok else 'FAIL'}] one report derives nothing")
    if not ok:
        failures.append("derived a rule from one report")
    c2 = _derive(["本館は閉鎖の方向で検討しています。",
                  "受付は閉鎖の方向で調整中です。"], "閉鎖")
    ok = c2 is not None and c2.pattern == "^の方向で"
    print(f"[{'ok  ' if ok else 'FAIL'}] grammar inside the prefix survives -> "
          f"{c2.pattern if c2 else None}")
    if not ok:
        failures.append("prefix trimmed into the grammar")

    # A suppression must be DATA, or the loop needs a source edit to run.
    one = CrossStore()
    ingest_polar_ja(one, "本館は閉鎖の方向で検討しています。")
    before = {k for f in one.crosses.values() for k in f if ":" in k}
    _grammar.SUPPRESSIONS.append(("^の方向で", "eval"))
    try:
        two = CrossStore()
        ingest_polar_ja(two, "本館は閉鎖の方向で検討しています。")
        after = {k for f in two.crosses.values() for k in f if ":" in k}
        three = CrossStore()
        ingest_polar_ja(three, "本館は閉鎖されました。")
        intact = {k for f in three.crosses.values() for k in f if ":" in k}
    finally:
        _grammar.SUPPRESSIONS.remove(("^の方向で", "eval"))
    ok = before and not after and intact
    print(f"[{'ok  ' if ok else 'FAIL'}] a data rule changes behaviour and "
          f"spares real claims -> {before} / {after} / {intact}")
    if not ok:
        failures.append("data suppression did not apply")

    # And it must be REMOVABLE, or a candidate cannot be tried.
    four = CrossStore()
    ingest_polar_ja(four, "本館は閉鎖の方向で検討しています。")
    ok = {k for f in four.crosses.values() for k in f if ":" in k} == before
    print(f"[{'ok  ' if ok else 'FAIL'}] removing the rule restores the engine")
    if not ok:
        failures.append("suppression left residue")

    # An invalid or unanchored pattern is refused by the validator, because a
    # suppression that matches mid-sentence is not a reading rule at all.
    errs = _grammar.validate({"suppressions": [["されるまで", "x"]]})
    ok = any("anchor" in e for e in errs)
    print(f"[{'ok  ' if ok else 'FAIL'}] an unanchored suppression is refused")
    if not ok:
        failures.append("unanchored suppression accepted")
    errs = _grammar.validate({"suppressions": [["^(unclosed", "x"]]})
    ok = any("regex" in e for e in errs)
    print(f"[{'ok  ' if ok else 'FAIL'}] an invalid regex is refused")
    if not ok:
        failures.append("invalid suppression accepted")
    print()

    # -- 4b20. Gaps from structure alone, with nobody reading ----------------
    # The loop already ran entirely on one machine. What it still needed was a
    # person to say "this finding is wrong" — and a person is an external
    # connection of a different kind: the loop stops the moment nobody looks.
    #
    # Structure can raise the gap instead. Not by judging its own findings
    # correct, which it cannot do, but by noticing the shapes a defect leaves
    # in the store even when the output is never read.
    from .self_audit import scan as _self_scan
    from .self_audit import summary as _self_summary
    from . import lang as _lang

    _broken = CrossStore()
    _broken.track_provenance = True
    ingest_documents(_broken, [
        Document("A新聞", "国道4号は通行止です。"),
        Document("B放送", "国道4号は通行可能になりました。"),
    ])
    _sig = {s.signal for s in _self_scan(_broken)}
    ok = not _sig
    print(f"[{'ok  ' if ok else 'FAIL'}] a clean store raises nothing -> {_sig}")
    if not ok:
        failures.append(f"self-audit fired on clean output: {_sig}")

    # Disabling the polar-core demotion is exactly the defect this project
    # fixed twice, and it must be visible from structure alone.
    _saved = _lang._is_polar_ja
    _lang._is_polar_ja = lambda w: False
    try:
        _bad = CrossStore()
        _bad.track_provenance = True
        ingest_documents(_bad, [
            Document("A", "断水が発生しています。"),
            Document("B", "断水は復旧しました。"),
        ])
        _sig = {s.signal for s in _self_scan(_bad)}
    finally:
        _lang._is_polar_ja = _saved
    ok = "polar_core" in _sig
    print(f"[{'ok  ' if ok else 'FAIL'}] a polar core is visible without a "
          f"reader -> {_sig}")
    if not ok:
        failures.append("self-audit missed a polar core")

    # One source holding both poles is the shape of a misread, not of a
    # document arguing with itself.
    _self = CrossStore()
    _self.track_provenance = True
    ingest_documents(_self, [
        Document("同一出典", "本町の避難所は開設されました。"
                             "本町の避難所は閉鎖されました。"),
    ])
    _sig = {s.signal for s in _self_scan(_self)}
    ok = "self_conflict" in _sig
    print(f"[{'ok  ' if ok else 'FAIL'}] one source, both poles -> {_sig}")
    if not ok:
        failures.append("self-audit missed a self conflict")

    # And it must never call anything wrong. Everything it raises is QUALITY
    # and marked suspected, because the ranges overlap with correct output —
    # the measured false positive ran 117 characters and a confirmed-true one
    # ran 53.
    from .gap_graph import GapGraph as _GG
    from .self_audit import to_gaps as _to_gaps
    _g = _GG()
    _filed = _to_gaps(_g, _self_scan(_self))
    nodes = [_g.get(f["gap_id"]) for f in _filed]
    ok = all(n.severity == "QUALITY" and n.observed_transition == "suspected"
             for n in nodes)
    print(f"[{'ok  ' if ok else 'FAIL'}] a structural gap is suspected, never "
          f"a verdict -> {[(n.severity, n.observed_transition) for n in nodes]}")
    if not ok:
        failures.append("self-audit filed a verdict")
    print()

    # -- 4b21. A defect PROVEN from inside, and repaired without a person ----
    # 4b20 stops at a suspicion on purpose: no procedure inside the engine can
    # decide whether its own reading of a sentence is right, because that
    # needs the world. A different question is decidable without it — do two
    # readings of the SAME CONTENT agree? — and where the transform between
    # them is layout, the direction is decidable too, because layout cannot
    # add information.
    from pathlib import Path as _P
    from .metamorphic import probe, split_counter
    from .self_evolve import Repair, apply as _apply_repair

    _clean = [Document("A", "天草市は断水しています。"),
              Document("B", "天草市の断水は解消しました。")]
    _divs = probe(_clean)
    ok = not [d for d in _divs if d.proven]
    print(f"[{'ok  ' if ok else 'FAIL'}] clean text proves nothing -> "
          f"{[d.core for d in _divs if d.proven]}")
    if not ok:
        failures.append("metamorphic fired on clean text")

    # The defect that started this: a PDF's column alignment between a numeral
    # and its counter, leaving a fragment carrying the pole.
    _noisy = [Document("PDF", "宇城市では 12 戸が断水しています。")]
    _proven = [d for d in probe(_noisy) if d.proven and d.kind == "manufactured"]
    ok = bool(_proven)
    print(f"[{'ok  ' if ok else 'FAIL'}] an extractor's space is proven, not "
          f"guessed -> {[(d.core, d.facet) for d in _proven]}")
    if not ok:
        failures.append("metamorphic missed a manufactured claim")

    ok = split_counter("うち 15 炉が復旧") == "うち 15炉が復旧"
    print(f"[{'ok  ' if ok else 'FAIL'}] a numeral rejoins its counter -> "
          f"{split_counter('うち 15 炉が復旧')!r}")
    if not ok:
        failures.append("split_counter did not rejoin a counter")

    # A table row's single spaces are column separators, and collapsing them
    # would change meaning rather than restore it. Found the hard way: the
    # wide probe turned 「日時 開催場所 担当部署」 into one word on municipal
    # HTML, and reported four defects that were its own damage.
    _row = "宇城市 約18,000 約9.900 7/28～ ・管破損"
    ok = split_counter(_row) == _row
    print(f"[{'ok  ' if ok else 'FAIL'}] a table row is left alone -> "
          f"{split_counter(_row) == _row}")
    if not ok:
        failures.append("split_counter touched a table row")

    # And an unattended loop must not be able to keep a repair it measured as
    # too costly. `layout_space` is exactly that: 8 real defects proven, 71
    # sentences' cores lost.
    try:
        _apply_repair(Repair("layout_space", targets=["x"], accepted=False,
                             reason="coverage falls"),
                      _P("/tmp/never-written.json"))
        ok = False
    except ValueError:
        ok = True
    print(f"[{'ok  ' if ok else 'FAIL'}] a rejected repair cannot be applied")
    if not ok:
        failures.append("a rejected repair was applied")
    print()

    # -- 4b22. The engine's rules and its output must agree with each other -
    # The second internal oracle. The first compares two readings of the same
    # content; this one compares the OUTPUT against the engine's own no-assert
    # guards, and both live in this process, so the conflict is decidable
    # without the world. It is also the four-times defect class — enumeration,
    # deeming, until, のため — every one a guard applied on one path and
    # skipped on another.
    from .metamorphic import rule_conflicts as _conflicts
    from .self_evolve import propose_suppressions as _prop_sup
    from . import ja_grammar as _g
    import tempfile as _tf

    with _tf.TemporaryDirectory() as _td:
        _f = _P(_td) / "law.txt"
        _f.write_text("災害派遣手当は、災害復旧のため派遣された職員に支給される。",
                      encoding="utf-8")
        _found = _conflicts([_td])
    ok = any(c.detail == "のため" for c in _found)
    print(f"[{'ok  ' if ok else 'FAIL'}] a placed pole its own guard refuses "
          f"is a conflict -> {[(c.core, c.detail) for c in _found]}")
    if not ok:
        failures.append("rule_conflicts missed a guard-refused placement")

    # The repair candidate is the exact grammar the guard matched, never the
    # guard's whole alternation: のため (purpose — the state has not happened)
    # and により (cause — it did) sit in one guard, and only splitting them
    # lets measurement keep one and drop the other.
    with _tf.TemporaryDirectory() as _td:
        _f = _P(_td) / "law.txt"
        _f.write_text("災害派遣手当は、災害復旧のため派遣された職員に支給される。",
                      encoding="utf-8")
        _cands = _prop_sup([_td])
    ok = _cands == ["^のため"]
    print(f"[{'ok  ' if ok else 'FAIL'}] the candidate is the match, not the "
          f"guard -> {_cands}")
    if not ok:
        failures.append(f"suppression candidate wrong: {_cands}")

    # And a suppression holds at the placement choke point, where every pole
    # passes — the structural close of the guard-skipped class. The same
    # sentence, the same overlay entry, no pole on any path.
    _g.SUPPRESSIONS.append(("^のため", "eval"))
    try:
        _st = CrossStore()
        _st.track_provenance = True
        ingest_documents(_st, [Document(
            "法令", "災害派遣手当は、災害復旧のため派遣された職員に支給される。")])
        _polar = [(c, f) for c in _st.crosses for f in _st.crosses[c] if ":" in f]
    finally:
        _g.SUPPRESSIONS.remove(("^のため", "eval"))
    ok = not _polar
    print(f"[{'ok  ' if ok else 'FAIL'}] a suppression holds on every path "
          f"at once -> {_polar}")
    if not ok:
        failures.append(f"suppression skipped at placement: {_polar}")
    print()

    # -- 4b23. Vocabulary grows from succession — and only ever as proposals -
    # The seed line was the last one the loop could not reach: which words
    # oppose which. A document series narrates states ENDING, and the closing
    # sentence anchors an unknown word to a known one. Found live before it
    # was planted here: the vocabulary that read five corpora does not know
    # 停電, and 「停電は復旧済み」 is in 内閣府's own reports.
    import verantyx.vocab_growth as _vg

    with _tf.TemporaryDirectory() as _td:
        (_P(_td) / "series.txt").write_text(
            "宇城市の断水は解消しました。\n停電は復旧済み。\n",
            encoding="utf-8")
        _props = {(p.word, p.aspect, p.polarity, p.slot)
                  for p in _vg.successions([_td])}
    ok = ("解消", "復旧", "+", "A") in _props
    print(f"[{'ok  ' if ok else 'FAIL'}] slot A: an unknown predicate of a "
          f"known state -> {sorted(_props)}")
    if not ok:
        failures.append(f"slot A missed 解消: {_props}")
    ok = ("停電", "復旧", "-", "B") in _props
    print(f"[{'ok  ' if ok else 'FAIL'}] slot B: an unknown state with a "
          f"known completion")
    if not ok:
        failures.append(f"slot B missed 停電: {_props}")

    # The asymmetry is structural, not stylistic: this module has no way to
    # write an overlay. The gate can reject a candidate by measurement; only
    # a person can accept one, because 「断水は限界です」 fits the slot grammar
    # and 限界 is not a restoration — the corpus cannot testify about itself.
    ok = not hasattr(_vg, "apply")
    print(f"[{'ok  ' if ok else 'FAIL'}] vocab_growth cannot write an overlay")
    if not ok:
        failures.append("vocab_growth grew an apply()")
    print()

    # -- 4b24. A model's embed table is a dictionary — for the measured range
    # Measured on qwen3.5:4b before the module existed: state-likeness
    # separated the real queue's true candidates from its false ones
    # (停電 +0.163, 舗装損傷 +0.124 vs 八代支店 −0.159, 地区 −0.277); nearest-
    # known worked as search (冠水→断水 0.50); polarity was 54.8% — a coin
    # flip — so it is absent from the API, and this eval pins the absence.
    import struct as _struct
    import verantyx.jgen_lexicon as _jl

    with _tf.TemporaryDirectory() as _td:
        _fake = _P(_td) / "fake_lexicon.jgen"
        _vecs = {"断水": [1, 0, 0, 0], "復旧": [0.9, 0.1, 0, 0],
                 "市役所": [0, 1, 0, 0], "支店": [0.1, 0.9, 0, 0],
                 "停電": [0.8, 0.2, 0, 0], "地区": [0, 0.95, 0, 0]}
        _ids = {w: i for i, w in enumerate(_vecs)}
        with _fake.open("wb") as _f:
            _f.write(b"JGEN"); _f.write(_struct.pack("<II", 3, 1))
            _nm = b"embed_tokens"
            _f.write(_struct.pack("<H", len(_nm))); _f.write(_nm)
            _f.write(_struct.pack("<B", 2))
            _f.write(_struct.pack("<II", len(_vecs), 4))
            for _v in _vecs.values():
                _f.write(_struct.pack("<4e", *_v))
        _lex = _jl.LexiconDict(
            _fake, lambda w: [_ids[w]] if w in _ids else [])

        _known = ["断水", "復旧"]
        _sl_state = _lex.state_likeness("停電", _known)
        _sl_place = _lex.state_likeness("地区", _known)
        ok = (_sl_state is not None and _sl_place is not None
              and _sl_state > 0 > _sl_place)
        print(f"[{'ok  ' if ok else 'FAIL'}] state-likeness separates a state "
              f"from a place -> 停電 {_sl_state}, 地区 {_sl_place}")
        if not ok:
            failures.append("lexicon state-likeness failed to separate")

        # The annotation sorts the queue and decides nothing: statuses are
        # untouched, and the probably-real candidate reads first.
        _rows = [{"word": "地区", "status": "proposed"},
                 {"word": "停電", "status": "proposed"}]
        _saved = _jl.open_configured
        _jl.open_configured = lambda home: _lex
        try:
            _jl.annotate(_rows, _P("/tmp"))
        finally:
            _jl.open_configured = _saved
        ok = ([r["word"] for r in _rows] == ["停電", "地区"]
              and all(r["status"] == "proposed" for r in _rows))
        print(f"[{'ok  ' if ok else 'FAIL'}] annotation sorts and decides "
              f"nothing -> {[r['word'] for r in _rows]}")
        if not ok:
            failures.append(f"lexicon annotation misbehaved: {_rows}")

        # And the measured prohibition is structural: 54.8% on polarity means
        # no API surface returns one.
        _api = [a for a in dir(_jl) + dir(_jl.LexiconDict)
                if "polar" in a.lower() or "pole" in a.lower()]
        ok = not _api
        print(f"[{'ok  ' if ok else 'FAIL'}] the dictionary has no polarity "
              f"API -> {_api}")
        if not ok:
            failures.append(f"lexicon grew a polarity API: {_api}")
    print()

    # -- 4b25. Three states for a proposal, so a person reads fewer of them --
    # Ported from the IDE's IRVerificationEngine, which returns verified /
    # unverified / contradicts instead of a score. Reading it first turned up
    # that its `contradicts` case is declared and NEVER returned — only two
    # states are reachable — so the third had to be built rather than
    # translated, and Vera can build it because it has an internal answer key
    # a chat loop does not.
    import verantyx.proposal_verify as _pv
    from .vocab_growth import Proposal as _Prop

    with _tf.TemporaryDirectory() as _td:
        # Two sources putting the same unknown word in the same completion
        # slot is the corpus agreeing with itself.
        (_P(_td) / "a.txt").write_text("停電は復旧済み。", encoding="utf-8")
        (_P(_td) / "b.txt").write_text("停電は復旧しました。", encoding="utf-8")
        _v = _pv.check(_Prop("停電", "復旧", "-", "B", "復旧"), [_td])
    ok = _v.state == "verified" and len(_v.sources) >= _pv.MIN_SOURCES
    print(f"[{'ok  ' if ok else 'FAIL'}] two sources corroborate -> "
          f"{_v.state} {_v.sources}")
    if not ok:
        failures.append(f"corroboration missed: {_v.as_dict()}")

    with _tf.TemporaryDirectory() as _td:
        (_P(_td) / "one.txt").write_text("停電は復旧済み。", encoding="utf-8")
        _v = _pv.check(_Prop("停電", "復旧", "-", "B", "復旧"), [_td])
    ok = _v.state == "unverified"
    print(f"[{'ok  ' if ok else 'FAIL'}] one source stays unverified -> "
          f"{_v.state}")
    if not ok:
        failures.append(f"single source not unverified: {_v.as_dict()}")

    # The refutation. A join that makes ONE source hold both poles of an
    # aspect about one core is far likelier wrong than the document is, so it
    # drops without a reader — the only automatic rejection in the vocabulary
    # path, and it is a refutation rather than a judgement of meaning.
    with _tf.TemporaryDirectory() as _td:
        (_P(_td) / "one.txt").write_text(
            "本町の給水は復旧しました。本町の給水は途絶しています。",
            encoding="utf-8")
        _v = _pv.check(_Prop("途絶", "復旧", "-", "B", "復旧"), [_td])
    ok = _v.state == "contradicts" and bool(_v.collision)
    print(f"[{'ok  ' if ok else 'FAIL'}] a self-contradicting join is refuted "
          f"-> {_v.state} {_v.collision}")
    if not ok:
        failures.append(f"contradiction not caught: {_v.as_dict()}")

    # Corroboration is not proof, so this module cannot accept either.
    ok = not hasattr(_pv, "apply") and not hasattr(_pv, "accept")
    print(f"[{'ok  ' if ok else 'FAIL'}] verification cannot write an overlay")
    if not ok:
        failures.append("proposal_verify grew an accept path")
    print()

    # -- 4b26. The field app: one write path, and it needs a person ---------
    # Everything else in the vocabulary chain refuses to write an overlay, and
    # the evals above assert that. Something has to write one eventually or a
    # judgement cannot be recorded, so there is exactly ONE such function and
    # it is behind a button that says what it does.
    import verantyx.field_app as _fa

    with _tf.TemporaryDirectory() as _td:
        _home = _P(_td)
        # Both candidates in ONE file, because that is how the app writes it —
        # a first version replaced the file per word and lost the earlier
        # verdict, which made the test fail on a bug the code did not have.
        (_home / "vocab_proposals.json").write_text(
            '[{"word":"停電","aspect":"復旧","polarity":"-","status":"proposed"},'
            ' {"word":"滞留","aspect":"復旧","polarity":"-","status":"proposed"}]',
            encoding="utf-8")
        _r = _fa.decide("停電", "accept", home=_home)
        _overlay = _home / "grammar.json"
        ok = (_r["status"] == "accepted" and _overlay.exists()
              and "停電" in _overlay.read_text(encoding="utf-8"))
        print(f"[{'ok  ' if ok else 'FAIL'}] approving writes the overlay -> "
              f"{_r.get('status')}")
        if not ok:
            failures.append(f"decide did not write the overlay: {_r}")

        # Refusing must not. A queue that quietly accepted on either button
        # would be worse than no queue.
        _fa.decide("滞留", "refuse", home=_home)
        ok = "滞留" not in _overlay.read_text(encoding="utf-8")
        print(f"[{'ok  ' if ok else 'FAIL'}] refusing writes nothing")
        if not ok:
            failures.append("refusing wrote to the overlay")

        # And a decided word never comes back. A queue that re-asks settled
        # questions is a queue people stop reading.
        ok = set(_fa._decided(_home)) == {"停電", "滞留"}
        print(f"[{'ok  ' if ok else 'FAIL'}] decided words are remembered -> "
              f"{sorted(_fa._decided(_home))}")
        if not ok:
            failures.append("decisions were not remembered")

    # The field app answers in the operator's language, and the SERVER never
    # sends prose. It used to return Japanese remedy text, which made the app
    # monolingual from the API outward: English chrome with a Japanese
    # explanation of the failure is worse than either language alone.
    import re as _re2
    _srv = "\n".join(_P(m.__file__).read_text(encoding="utf-8")
                      for m in (_fa, __import__("verantyx.field_session",
                                                fromlist=["x"])))
    # The terminal banner is exempt and prints BOTH languages side by side:
    # it appears before any browser has said which language it wants, so
    # picking one there would be picking for somebody who has not arrived.
    # A JSON response is not exempt — that is what the screen renders.
    # Only strings that reach a JSON response count. The module docstring
    # quotes 「読み取り中 (12/40)」 as an EXAMPLE of a named state, and the
    # terminal banner prints both languages side by side because it appears
    # before any browser has said which one it wants — picking there would be
    # picking for somebody who has not arrived yet.
    _prose = []
    for _blkm in _re2.finditer(r'self\._json\((.*?)\)\s*(?:$|\n)', _srv,
                               _re2.S):
        if _re2.search(r'"[^"]*[ぁ-んァ-ヶ]', _blkm.group(1)):
            _prose.append(_blkm.group(1).strip()[:60])
    for _ln in _srv.splitlines():
        _st = _ln.strip()
        if _st.startswith(("#", "print(", '"')):
            continue
        if _re2.search(r'return\s*\{.*"[^"]*[ぁ-んァ-ヶ]', _ln):
            _prose.append(_st[:60])
    ok = not _prose
    print(f"[{'ok  ' if ok else 'FAIL'}] the field server sends codes, never "
          f"prose -> {len(_prose)} line(s)")
    if not ok:
        failures.append(f"field server carries Japanese prose: {_prose[:2]}")

    # Both languages, and every key present in both — a half-translated screen
    # is worse than an untranslated one, because the gap is invisible until
    # somebody hits it.
    _html = _fa._PAGE_PATH.read_text(encoding="utf-8")
    _keys = {}
    for _lang in ("ja", "en"):
        _blk = _html.split(f"\n  {_lang}: {{", 1)
        _keys[_lang] = set(_re2.findall(r"^    ([A-Za-z_][A-Za-z0-9_]*)\s*:",
                                        _blk[1], _re2.M)) if len(_blk) > 1 else set()
    _missing = (_keys["ja"] ^ _keys["en"])
    ok = bool(_keys["ja"]) and not _missing
    print(f"[{'ok  ' if ok else 'FAIL'}] both languages carry the same keys -> "
          f"{len(_keys['ja'])} keys, {len(_missing)} missing")
    if not ok:
        failures.append(f"field app translation gap: {sorted(_missing)[:5]}")

    # The page must not reach outside the machine — the promise the whole
    # local app exists to make. Checked against the file that ships.
    _out = [x for x in ("http://", "https://", "//cdn", "<img", "@import")
            if x in _html]
    ok = not _out
    print(f"[{'ok  ' if ok else 'FAIL'}] the field page loads nothing remote "
          f"-> {_out}")
    if not ok:
        failures.append(f"field page reaches outside: {_out}")
    print()

    # -- 4b27. The shift log: records by recency, and a note that cannot ----
    # overwrite what it annotates. A read saves its RESULT automatically,
    # because at 14:00 nobody knows that today will need handing over — by the
    # time they know, the moment to press "save" has passed.
    import json as _json
    import time as _time
    from .field_session import Session as _Sess
    from .field_session import listing as _listing
    from .field_session import load as _sload
    from .field_session import save as _ssave

    with _tf.TemporaryDirectory() as _td:
        _home = _P(_td)
        _now = _Sess("b-now", label="今")
        _ssave(_now, _home)
        _old = _Sess("a-old", label="先月")
        _ssave(_old, _home)
        _old.updated = _time.strftime(
            "%Y-%m-%dT%H:%M:%S", _time.localtime(_time.time() - 40 * 86400))
        (_home / "sessions" / "a-old.json").write_text(
            _json.dumps(_old.__dict__, ensure_ascii=False), encoding="utf-8")

        _rows = _listing(_home)
        ok = ([r["session_id"] for r in _rows] == ["b-now", "a-old"]
              and _rows[0]["zone"] == "front" and _rows[1]["zone"] == "archive")
        print(f"[{'ok  ' if ok else 'FAIL'}] newest first, zones by age -> "
              f"{[(r['session_id'], r['zone']) for r in _rows]}")
        if not ok:
            failures.append(f"shift log ordering/zones wrong: {_rows}")

        # The note round-trips through load-modify-save, and the findings it
        # annotates survive it.
        _now.detections = [{"topic": "国道9号", "aspect": "通行可能"}]
        _ssave(_now, _home)
        _got = _sload("b-now", _home)
        _got.note = "県道路課に確認中"
        _ssave(_got, _home)
        _back = _sload("b-now", _home)
        ok = (_back.note == "県道路課に確認中"
              and _back.detections and _back.detections[0]["topic"] == "国道9号")
        print(f"[{'ok  ' if ok else 'FAIL'}] a note never overwrites the "
              f"findings it is a note about")
        if not ok:
            failures.append("handover note clobbered the record")
    print()

    # -- 4b28. Install instructions must name something that exists ---------
    # The site, the Space, and the app's own screens all said
    # `pip install verantyx-vera`. That name has never been on PyPI, so every
    # one of those instructions failed — for an audience that cannot debug a
    # packaging error. Nothing tested it because instructions are prose.
    import verantyx.document_loaders as _dl
    import verantyx.obfuscate_forks as _of

    _sources = [_P(_dl.__file__).read_text(encoding="utf-8"),
                _P(_of.__file__).read_text(encoding="utf-8"),
                _fa._PAGE_PATH.read_text(encoding="utf-8")]
    # verantyx-vera 0.1.0a1 is on PyPI now, so `pip install verantyx-vera` is
    # true again and the git URL is no longer needed. What still has to hold is
    # that an instruction names a REAL extra: `[docs]` and `[obfuscate]` exist
    # in pyproject, and a typo there fails the same way an unpublished name did.
    import re as _re

    # Read the extras with a regex rather than tomllib: the package declares
    # `requires-python = ">=3.9"` and tomllib arrives in 3.11, so an eval that
    # needs it would only run on the interpreters the package does not have to
    # support. The block it reads is small and flat.
    _extras = set()
    try:
        _pp = (_P(__file__).resolve().parent.parent
               / "pyproject.toml").read_text(encoding="utf-8")
        _blk = _pp.split("[project.optional-dependencies]", 1)
        if len(_blk) > 1:
            _extras = set(_re.findall(r"^\s*([A-Za-z][\w-]*)\s*=",
                                      _blk[1].split("\n[", 1)[0], _re.M))
    except OSError:
        _extras = set()
    _named = set()
    for _src in _sources:
        _named |= set(_re.findall(r"verantyx-vera\[([a-z]+)\]", _src))
    _bad = sorted(_named - _extras) if _extras else []
    ok = not _bad
    print(f"[{'ok  ' if ok else 'FAIL'}] every install instruction names a "
          f"real extra -> {sorted(_named) or 'none'}")
    if not ok:
        failures.append(f"install instruction names a missing extra: {_bad}")
    print()

    # -- 4b29. A corpus you cannot reconstruct is a number nobody can check --
    # The corpus every published figure was measured on lived in a session
    # temp directory and was lost when that directory was cleaned. What
    # survived was the figures, in commit messages, with no way to re-derive
    # them. The manifest is the fix; drift has to be LOUD, because the
    # interesting failure is not a broken download, it is a publisher issuing
    # a correction while the numbers still claim to describe the old text.
    import verantyx.corpus_fetch as _cf

    with _tf.TemporaryDirectory() as _td:
        _docs = _P(_td) / "docs"
        _docs.mkdir()
        (_docs / "a.txt").write_text("国道9号は通行止です。", encoding="utf-8")
        (_docs / "b.txt").write_text("国道9号は通行可能。", encoding="utf-8")
        (_P(_td) / "u.tsv").write_text(
            "a.txt\thttps://example.gov/a\nb.txt\thttps://example.gov/b\n",
            encoding="utf-8")
        _m = _cf.record(_docs, _P(_td) / "m.json",
                        source_map=_P(_td) / "u.tsv", label="t")
        ok = _m["reproducible"] and len(_m["files"]) == 2 and all(
            f["url"] and f["sha256"] for f in _m["files"])
        print(f"[{'ok  ' if ok else 'FAIL'}] a manifest carries url + checksum "
              f"per file -> {len(_m['files'])} files")
        if not ok:
            failures.append(f"manifest incomplete: {_m}")

        ok = _cf.verify(_m, _docs)["verdict"] == "ANSWER"
        print(f"[{'ok  ' if ok else 'FAIL'}] an unchanged corpus verifies")
        if not ok:
            failures.append("verify failed on an unchanged corpus")

        (_docs / "a.txt").write_text("国道9号は依然통行止です。", encoding="utf-8")
        _v = _cf.verify(_m, _docs)
        ok = _v["verdict"] == "UNKNOWN_CORPUS_DRIFT" and _v["changed"] == ["a.txt"]
        print(f"[{'ok  ' if ok else 'FAIL'}] a changed document is named, not "
              f"summarised -> {_v['changed']}")
        if not ok:
            failures.append(f"drift not detected: {_v}")

        # Non-zero exit, or this cannot gate anything. A first version
        # substring-matched the rendered JSON and returned 0 on drift, because
        # the word ANSWER appears inside the explanation.
        import contextlib as _ctx
        import io as _io
        with _ctx.redirect_stdout(_io.StringIO()):
            _code = _cf.main(["--manifest", str(_P(_td) / "m.json"),
                              "--out", str(_docs), "--verify"])
        ok = _code == 1
        print(f"[{'ok  ' if ok else 'FAIL'}] drift exits non-zero")
        if not ok:
            failures.append("corpus drift exited 0")

        # A manifest with no URLs must admit it rather than look complete.
        _m2 = _cf.record(_docs, _P(_td) / "m2.json")
        ok = _m2["reproducible"] is False and "cannot reconstruct" in _m2["note"]
        print(f"[{'ok  ' if ok else 'FAIL'}] a URL-less manifest says so")
        if not ok:
            failures.append("URL-less manifest claimed to be reproducible")
    print()

    # -- 4c. English prepositions must not read as state claims -------------
    # From the first real-corpus run: this project's own 12 documents produced
    # one contradiction across 251 cores and it was false — "corpus ON top"
    # against "trade-OFF". Precision 0 of 1 on the only hit there was.
    from .polarity import detect as detect_en
    prepositions = ["pour a second corpus on top and counts merge",
                    "same trade-off as any personal-secret scheme",
                    "based on the store contents"]
    bad = [t for t in prepositions if detect_en(t)]
    ok = not bad
    print(f"[{'ok  ' if ok else 'FAIL'}] on/off as prepositions produce no pole")
    for b in bad:
        print(f"        invented: {b} -> {detect_en(b)}")
    if not ok:
        failures.append("english preposition false positive")

    states = [("the switch is on", "on"), ("the light was off", "off"),
              ("turned off the feature", "off")]
    missed = [t for t, v in states
              if not any(val == v for _a, val, _p in detect_en(t))]
    ok = not missed
    print(f"[{'ok  ' if ok else 'FAIL'}] real on/off state claims still detected")
    if not ok:
        failures.append(f"english copula recall: {missed}")
    print()

    # -- 4d. A pole must belong to the core, not to whatever else the ------
    # sentence mentions. Measured on 2,633 real documents: without this gate
    # the catalogue reported 24 contested topics and the four inspected were
    # all false, every one the same way — the polar word described some other
    # noun in the sentence. With it, zero, while the Japanese disaster case
    # above still detects. Zero on a corpus with no real disputes is the
    # right answer; 24 was confidently wrong.
    from .polarity import subject_is_core
    gate = [
        # (sentence, core, word, lang, should the pole be placed)
        ("If sandbox mode is enabled but Docker is unavailable, doctor reports.",
         "sandbox", "unavailable", "en", False),
        ("The gateway surfaces one installer (brew when available).",
         "gateway", "available", "en", False),
        ("The service, which we deployed, is broken.",
         "service", "broken", "en", False),
        ("The shelter is open until midnight.", "shelter", "open", "en", True),
        ("The gateway is unavailable right now.",
         "gateway", "unavailable", "en", True),
        ("国道4号は通行止です。", "国道", "通行止", "ja", True),
        ("避難所は閉鎖されました。", "避難所", "閉鎖", "ja", True),
    ]
    for sentence, core, word, lg, expect in gate:
        got = subject_is_core(sentence, core, word, lg)
        ok = got == expect
        print(f"[{'ok  ' if ok else 'FAIL'}] subject gate {core}/{word} = {got}")
        if not ok:
            failures.append(f"subject gate: {core}/{word}")
    print()

    # -- 4e. Topics carry the language their sentences voted for ------------
    # A topic string cannot name its own language — 如果 and 結論 are both
    # two-ideograph words — but the sentences that produced it were already
    # routed per-script, so the label comes from that vote, not from a guess.
    from .catalog import build_catalog

    with tempfile.TemporaryDirectory() as td2:
        root2 = Path(td2)
        (root2 / "ja.txt").write_text(
            "国道4号は通行止です。避難所は開設されました。", encoding="utf-8")
        (root2 / "en.txt").write_text(
            "The bridge is closed for repairs. The bridge spans the river.",
            encoding="utf-8")
        (root2 / "zh.txt").write_text(
            "如果配置错误，网关将无法启动。建议使用默认设置以保证稳定运行。",
            encoding="utf-8")
        cat = build_catalog([str(root2 / n) for n in
                             ("ja.txt", "en.txt", "zh.txt")])
        got = {e.topic: e.lang for e in cat.entries}
        expect = {"国道4号": "ja", "避難所": "ja", "bridge": "en"}
        wrong = {t: (got.get(t), lg) for t, lg in expect.items()
                 if got.get(t) != lg}
        zh_ok = any(lg == "zh" for lg in got.values())
        ok = not wrong and zh_ok
        print(f"[{'ok  ' if ok else 'FAIL'}] catalogue entries labeled by their "
              f"sentences' language (ja/en/zh all present)")
        if wrong:
            print(f"        wrong: {wrong}")
        if not ok:
            failures.append("entry language labels")
    print()

    # -- 4f. Duplicates count once; .txt gets the same cleaning as .md ------
    # Measured: 1,588 of 2,633 files in the real corpus were byte-identical
    # copies living in a second repository checkout, doubling every ranking
    # signal. And a 107,752-line .txt notes file read raw contributed `py`
    # (1,471 mentions) as its top topic — the file is nominally plain text
    # and actually full of markdown and pasted code.
    with tempfile.TemporaryDirectory() as td3:
        root3 = Path(td3)
        (root3 / "a.txt").write_text(
            "設計の方針を説明します。\n```python\nimport json\n"
            "def parse(x):\n    return json.loads(x)\n```\n"
            "構造は決定論的であるべきです。", encoding="utf-8")
        (root3 / "b.txt").write_text(  # byte-identical copy of a
            (root3 / "a.txt").read_text(), encoding="utf-8")
        cat3 = build_catalog([str(root3 / "a.txt"), str(root3 / "b.txt")])
        dups = [x for x in cat3.manifest.skipped
                if x.get("verdict") == "DUPLICATE"]
        ok = len(dups) == 1 and cat3.manifest.files == 2
        print(f"[{'ok  ' if ok else 'FAIL'}] identical files count once, and "
              f"the duplicate is named in the manifest")
        if not ok:
            failures.append("dedupe")
        topics3 = {e.topic for e in cat3.entries}
        ok = "json" not in topics3 and "parse" not in topics3
        print(f"[{'ok  ' if ok else 'FAIL'}] pasted code inside a .txt file "
              f"does not become a topic")
        if not ok:
            print(f"        topics: {sorted(topics3)}")
            failures.append("txt cleaning")
    print()

    # -- 4g. Grammar as data: bundled, overlayable, loudly validated --------
    # The Japanese vocabulary ships as lang_data/ja_grammar.json and a user
    # extends it with a file beside their store — no code. The validator
    # enforces the rules this project paid for on real corpora (2-char
    # floor, one pole per term, no dangling references), and an invalid
    # overlay refuses to load with every problem named.
    from . import ja_grammar
    from .placement_explain import explain

    base = ja_grammar.status()
    ok = (base["pairs"] >= 12 and base["stopwords"] >= 50
          and base["overlay"] is None)
    print(f"[{'ok  ' if ok else 'FAIL'}] bundled grammar loads from data: "
          f"{base['pairs']} pairs, {base['stopwords']} stopwords")
    if not ok:
        failures.append("bundled grammar")

    with tempfile.TemporaryDirectory() as tdg:
        ov = Path(tdg) / "ja_grammar.json"
        ov.write_text('{"antonym_pairs": [["点灯", "消灯"]], '
                      '"predicates": {"点灯": "は点灯しています。"}}',
                      encoding="utf-8")
        info = ja_grammar.load_overlay(ov)
        hits = detect_ja("非常灯は点灯しています。")
        ok = any(v == "点灯" for _a, v, _p in hits) and info["added_pairs"] == 1
        print(f"[{'ok  ' if ok else 'FAIL'}] overlay adds a pair without code "
              f"and detection picks it up: {hits}")
        if not ok:
            failures.append("overlay round-trip")
        # The compound guard applies to overlay vocabulary too.
        ok = not detect_ja("点灯確認の手順を説明します。")
        print(f"[{'ok  ' if ok else 'FAIL'}] overlay vocabulary rides the same "
              f"compound guard (点灯確認 stays silent)")
        if not ok:
            failures.append("overlay compound guard")

        bad = Path(tdg) / "bad.json"
        bad.write_text('{"antonym_pairs": [["開", "閉"]]}', encoding="utf-8")
        try:
            ja_grammar.load_overlay(bad)
            ok = False
        except ValueError as exc:
            ok = "2 chars" in str(exc)
        print(f"[{'ok  ' if ok else 'FAIL'}] a 1-char pair is refused loudly "
              f"(開 lives inside 開始, 公開, 展開)")
        if not ok:
            failures.append("invalid overlay accepted")
    # The shipped sample domain pack must stay valid against the bundled
    # grammar — it is the document's worked example, and a worked example
    # that no longer loads is worse than none.
    import json as _json
    sample = Path(ja_grammar.BUILTIN_GRAMMAR).parent / "ja_domain_disaster.json"
    raw_sample = _json.loads(sample.read_text(encoding="utf-8"))
    raw_sample.pop("_comment", None)
    merged_sample = {
        "stopwords": sorted(ja_grammar.STOPWORDS),
        "antonym_pairs": [list(x) for x in ja_grammar.ANTONYM_PAIRS]
                         + raw_sample.get("antonym_pairs", []),
        "aspect_joins": [list(x) for x in ja_grammar.ASPECT_JOINS],
        "aliases": dict(ja_grammar.ALIASES),
        "predicates": {**ja_grammar.PREDICATES,
                       **raw_sample.get("predicates", {})},
    }
    errs2 = ja_grammar.validate(merged_sample)
    ok = not errs2
    print(f"[{'ok  ' if ok else 'FAIL'}] the shipped sample domain pack "
          f"validates against the bundled grammar")
    for e in errs2:
        print(f"        {e}")
    if not ok:
        failures.append("sample pack invalid")

    ja_grammar.load()   # restore pristine bundled state for later checks

    # The placement explainer: the adjustment loop's first step.
    exp = explain("本町の避難所は閉鎖されました。")
    ok = (exp["core"] == "避難所" and exp["core_rule"] == "head_of_topic_phrase"
          and any(p["placed"] for p in exp["poles"]))
    print(f"[{'ok  ' if ok else 'FAIL'}] explain_placement states core, rule "
          f"and pole for a Japanese sentence")
    if not ok:
        failures.append("placement explain")
    exp2 = explain("停止線の位置を確認してください。")
    ok = not exp2["poles"] and "pole_note" in exp2
    print(f"[{'ok  ' if ok else 'FAIL'}] explain_placement names WHY no pole "
          f"was placed on a compound-noun sentence")
    if not ok:
        failures.append("placement explain notes")
    print()

    # -- 4h. SQLite checkpoint: identical contents, crash-safe format -------
    # Chosen for the failure mode, not the speed: the JSON checkpoint
    # rewrites the whole store as one string (208 MB measured on an
    # accumulated store) and a crash mid-write parses as nothing. WAL rolls
    # back instead. Same store, either suffix, equal contents — asserted.
    with tempfile.TemporaryDirectory() as tds:
        pj, ps = Path(tds) / "s.json", Path(tds) / "s.sqlite"
        store.save(pj); store.save(ps)
        a, b = CrossStore.load(pj), CrossStore.load(ps)
        ok = (a.crosses == b.crosses == store.crosses
              and a.provenance == b.provenance == store.provenance
              and a.core_count == b.core_count
              and a.n_sentences == b.n_sentences)
        print(f"[{'ok  ' if ok else 'FAIL'}] JSON and SQLite checkpoints "
              f"round-trip to identical stores")
        if not ok:
            failures.append("sqlite round-trip")
    print()

    # -- 4i. Update vs dispute: time orders a story, absence keeps a fight --
    # The recognition prerequisite named by the analysis: a road closed at
    # 9:00 and reopened at 15:00 is a supersession, and rendering it as a
    # conflict is how an information officer stops trusting the board. The
    # bar for "update" is deliberately high — every side stamped, stamps
    # comparable, ordering strict — because demoting a real conflict to an
    # update hides exactly what the report exists to surface.
    def _road(pub_a, pub_b):
        st_ = CrossStore()
        ingest_documents(st_, [
            Document("A新聞", "国道4号は通行止です。", pub_a),
            Document("B放送", "国道4号は通行可能になりました。", pub_b)])
        return deep_report(st_, "国道4号")

    cases_t = [
        (("2026-08-06 09:00", "2026年8月6日 15時"), "updated",
         "both stamped and ordered → update"),
        (("", ""), "contested", "no stamps → the dispute stands"),
        (("2026-08-06", ""), "contested", "one side unstamped → dispute stands"),
        (("8月6日", "2026-08-07"), "contested",
         "yearless vs dated are incomparable → dispute stands"),
    ]
    for (pa, pb), expect, why in cases_t:
        got = _road(pa, pb)["confidence"]
        ok = got == expect
        print(f"[{'ok  ' if ok else 'FAIL'}] temporal: {why} (got {got})")
        if not ok:
            failures.append(f"temporal: {why}")
    up = _road("2026-08-06 09:00", "2026-08-06 15:00")["updated"][0]
    ok = (up["current"]["claim"] == "通行可能"
          and up["superseded"][0]["claim"] == "通行止"
          and up["current"]["sources"] == ["B放送"])
    print(f"[{'ok  ' if ok else 'FAIL'}] the newer side is current, the older "
          f"superseded, each with its source")
    if not ok:
        failures.append("temporal ordering direction")
    print()

    # -- 4j. The MVP demo's pipeline is the pinned pipeline -----------------
    # demo/app.py is what a first-time user actually runs. Its analysis half
    # imports without gradio, so CI exercises the exact code path of the
    # public demo — the shipped-drift lesson applied before shipping.
    import importlib.util as _ilu
    demo_py = Path(__file__).resolve().parent.parent / "demo" / "app.py"
    spec = _ilu.spec_from_file_location("vera_demo_app", demo_py)
    demo_app = _ilu.module_from_spec(spec)
    spec.loader.exec_module(demo_app)
    board = demo_app.analyze_texts(
        demo_app.SAMPLE_A, "架空新聞", "2026-08-06 09:00",
        demo_app.SAMPLE_B, "架空放送", "2026-08-06 15:00")
    ok = ("INTAKE_OK" in board and "🔄" in board and "通行可能" in board
          and "架空放送" in board)
    print(f"[{'ok  ' if ok else 'FAIL'}] the demo app's board shows the "
          f"update with its source, from the sample corpus")
    if not ok:
        failures.append("demo board")
    print()

    # -- 4k. HTML: prose kept, navigation dropped ---------------------------
    # From five real government pages. Two structural attempts failed first
    # — nesting counters broke on void elements, same-name counters broke on
    # the mismatched <div>s real pages ship — so the split is drawn on what
    # the text IS: navigation is short link labels, body is sentences.
    from .document_loaders import _from_html
    page = ("<html><head><title>T</title><style>.a{}</style></head><body>"
            "<div id=headerArea><ul><li><a href=#>サイトマップ</a>"
            "<li><a href=#>English</a><li><a href=#>内閣府ホーム</a></ul></div>"
            "<div id=main><p>指定緊急避難場所は、災害の危険から命を守るために"
            "緊急的に避難をする場所です。<br><p>内閣府では手引きを作成しています。"
            "</div></body></html>")
    got = _from_html(page)
    ok = ("指定緊急避難場所" in got and "手引き" in got
          and "サイトマップ" not in got and "English" not in got
          and "T" not in got.split("\n")[0])
    print(f"[{'ok  ' if ok else 'FAIL'}] HTML keeps the paragraphs and drops "
          f"the navigation, on unclosed <li> and <p>")
    if not ok:
        print(f"        got: {got!r}")
        failures.append("html chrome")
    # A link whose text is a whole sentence is a sentence, not a label.
    got2 = _from_html("<p><a href=#>この道路は現在通行止めです。</a></p>")
    ok = "通行止め" in got2
    print(f"[{'ok  ' if ok else 'FAIL'}] a link whose text is a full sentence "
          f"is kept")
    if not ok:
        failures.append("sentence link dropped")
    print()

    # -- 5. File loaders ---------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "a.txt").write_text("国道4号は通行止です。\n", encoding="utf-8")
        (root / "b.html").write_text(
            "<html><head><style>p{color:red}</style></head><body>"
            "<p>本町の避難所は閉鎖されました。</p><script>var x=1</script>"
            "</body></html>", encoding="utf-8")
        (root / "c.csv").write_text("name,status\n本町避難所,開設\n", encoding="utf-8")
        (root / "d.json").write_text('{"road":{"state":"通行可能"}}', encoding="utf-8")
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        with zipfile.ZipFile(root / "e.docx", "w") as zf:
            zf.writestr("word/document.xml",
                        f'<?xml version="1.0"?><w:document xmlns:w="{ns}"><w:body>'
                        f"<w:p><w:r><w:t>南町の避難所は</w:t></w:r>"
                        f"<w:r><w:t>開設されました。</w:t></w:r></w:p>"
                        f"</w:body></w:document>")
        (root / "f.pdf").write_bytes(b"%PDF-1.4 not really")

        res = load_directory(str(root))
        ok = res["loaded"] == 5
        print(f"[{'ok  ' if ok else 'FAIL'}] 5 of 6 files loaded "
              f"(got {res['loaded']})")
        if not ok:
            failures.append(f"loaders: {res['loaded']} loaded")

        # A missing optional parser must not take the batch down with it.
        pdf_skips = [s for s in res["skipped"]
                     if s["verdict"] in {"UNKNOWN_NO_PARSER", "UNKNOWN_UNREADABLE",
                                         "UNKNOWN_EMPTY_DOCUMENT"}]
        ok = len(pdf_skips) == 1
        print(f"[{'ok  ' if ok else 'FAIL'}] the PDF is reported by name, and "
              f"the other five still load")
        if not ok:
            failures.append("pdf skip")

        # Word runs must join without separators — Word splits a sentence
        # across runs whenever formatting changes, and spaces would land
        # inside words.
        docx = [d for d in res["documents"] if d.source == "e.docx"]
        ok = bool(docx) and "南町の避難所は開設されました。" in docx[0].text
        print(f"[{'ok  ' if ok else 'FAIL'}] .docx runs join without inserting "
              f"separators inside a sentence")
        if not ok:
            failures.append("docx run joining")

        # A corrupt file must not take the batch down with it. Measured:
        # installing pypdf turned the fake PDF above from "no parser" into a
        # real parse that raised PdfStreamError, outside the exception tuple
        # being caught, and the whole run died. One bad file must never cost
        # the other nine hundred.
        good = load_path(str(root / "a.txt"))
        ok = good["verdict"] == "ANSWER" and res["loaded"] >= 5
        print(f"[{'ok  ' if ok else 'FAIL'}] a file that fails to parse is "
              f"skipped by name while the rest still load")
        if not ok:
            failures.append("corrupt file killed the batch")

        # An unreadable file is a typed refusal, not an empty Document.
        missing = load_path(str(root / "nope.txt"))
        ok = missing["verdict"] == "UNKNOWN_UNREADABLE"
        print(f"[{'ok  ' if ok else 'FAIL'}] a missing file refuses by type "
              f"rather than returning an empty document")
        if not ok:
            failures.append("missing file verdict")
    print()

    print(f"formats supported: {', '.join(sorted(SUPPORTED))}")
    print()
    if failures:
        print(f"{len(failures)} failed: {', '.join(failures)}")
        return 1
    print("Japanese documents reach typed, attributed, contested verdicts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
