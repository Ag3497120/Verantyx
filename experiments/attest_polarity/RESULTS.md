# 実測結果: attest_claim の否定盲を修理(5点全合格)

日付: 2026-08-20。事前登録 docs/PREREGISTERED_2026-08-20_attest_polarity.md、
生データ results.json。

## 直した欠陥(二者独立に発見)

隔離環境のブラインド評価者と、私の再現測定が、独立に同じ穴を見つけた:

    「実費を支給する」   -> ANSWER support=1.0
    「実費を支給しない」 -> ANSWER support=1.0   ← **完全同点**

機序は構成上のもの: `attest_llm._RUN` は漢字・カタカナの連しか抽出せず、
日本語の否定は**その後ろのひらがな**に居る。極性の器官(polarity.py、
否定53,885件、apply_polarity_gate は合意経路に配線済み)は在るのに、
この扉だけが呼んでいなかった — 「実装済み未到達」の型。

## 直し方(新しい賢さを持ち込まない)

過去4回の極性の失敗は全て「品詞ラベルを、それが答えられない問いに
使った」型で、唯一成功した修理は**位置を見る**ことだった。そのまま使う:
語の直後の接尾を読む(`polarity._JA_NEG_AFTER`)。

三つの結果を混ぜない:

| verdict | 意味 |
|---|---|
| `CONTRADICTED_BY_CORPUS` | 店が**反対の極を証拠として持つ** — facet を名指す |
| `UNKNOWN_POLARITY_UNJUDGED` | 店は語を持つが極性を記録していない — **黙って同点にしない拒否** |
| `ANSWER` / `UNSUPPORTED_BY_CORPUS` | 極性の争点が無いときのみ従来どおり |

## 測定(完了基準5点、全合格)

    K1 正   「支給する」ANSWER(1.0) vs 「支給しない」
            UNKNOWN_POLARITY_UNJUDGED — **肯定と否定が分かれた**(2組とも)
    K2 反証 店=否定/主張=肯定 -> CONTRADICTED、facet `復旧:not_復旧` を名指し
            店=肯定/主張=否定 -> CONTRADICTED、facet `開設:開設`
            一致(肯定) -> ANSWER(誤検出なし)
    K3 拒否 極性の争点が無い主張は ANSWER のまま。否定は UNJUDGED
    K4 順序 文の並びを反転しても verdict 一致
    K5 退行 未保持の主題 -> UNKNOWN_SUBJECT_NOT_HELD 不変。
            **fork 170本目 ATTEST_POLARITY で3点固定、forks 83/83**

## 途中で見つけた本物の欠陥(記録)

共有の `polarity._JA_NEG_AFTER` は「〜していない」を覆うが、**サ変の
辞書形否定「〜しない / 〜しません」を覆っていない**(「支給しない」が
素通りした)。共有側は取り込み経路(否定53,885件の実測履歴)に効くため
**触らず**、主張を読む側にだけ閉じた補足 `_JA_NEG_AFTER_SUPPL` を置いた。
共有側の拡張は独自の事前登録が要る — **未着手の穴として残す**。
(「支給しなければならない」を否定と誤読しないことは実測で確認)

治具の誤りも1件記録: 最初 `ingest_sentence` で店を作り、会社が核に
ならず K1/K3 が主題不在で落ちた。**測ったものと同じ経路**
(`document_ingest.ingest_documents`)で作り直して合格 — 器の欠陥では
なく治具の誤り。fork の治具も一度薄すぎて TOO_THIN で落ちた(同型)。
