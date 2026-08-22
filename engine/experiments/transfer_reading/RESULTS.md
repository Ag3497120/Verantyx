# 実測結果: 転移の読む層 — 保留されていた較正段が埋まった(5点全合格)

日付: 2026-08-20。事前登録 PREREG.md、生データ results.json。

## 埋めた穴(モジュール自身が名指していた)

`transfer_outcomes.py` の docstring:「記録だけをする。較正の分析は
しない — 実データが溜まるまでは推測にしかならない」。棚卸しの穴3つ目。
今日、実データが出た(3モデル×3変分の採否)ので埋めた。

## 設計の線 — 機械は転移を報告し、理由は主張しない

    機械が言える   転移したか(全文脈一致=TRANSFERRED / 割れた=CONTEXT_BOUND
                   / 1文脈のみ=UNKNOWN_SINGLE_CONTEXT — 予測しない)
    機械が言わない 「なぜ転移したか」。次元は**人の仮説**で、それ自体が
                   証拠を要する主張。台帳は運ぶが生成しない
                   (record first, judge later を判断の側でも守る)

## 測定(5点全合格)

    L1 正   9観測 → **3事実に畳まれ**、機械の判定が実測と一致:
              htrunc(f,64)  TRANSFERRED   (3モデルとも harm)
              hretry(f,3)   CONTEXT_BOUND (0.5Bのみ adopt)
              htrunc(f,400) CONTEXT_BOUND (同上)
            事実名の揺れ(「hretry(f,3) が成功を増やす」と「hretry(f,3)」)は
            閉じた規則で正規化し、元の名前も残す(写像が読者に見える)
    L2 反証 合成の偽転移主張を **CONTRADICTED** で検出(どの文脈が割れたかを
            名指す)。一致する主張は CONSISTENT、未観測は
            UNKNOWN_NOT_OBSERVED
    L3 拒否 1文脈の事実は予測せず、閾値未満の次元は**数字を出さない**
    L4 順序 読み込み順を反転しても較正が完全一致
    L5 独立 出力が harness_facts.json の生データと一致(手で数えられる)
    fork 171本目 TRANSFER_READING で4点固定。**forks 84/84**
    扉 `vera_transfer`(118→119扉)

## 較正が私の仮説に忖度しなかった記録

人の仮説として「情報構造由来は転移する / モデル能力由来は転移しない」を
渡したところ:

    モデル能力由来   COUNTED — 2観測、CONTEXT_BOUND 2/2
    情報構造由来     **UNKNOWN_TOO_FEW_CONTEXTS** — 事実が1本しかない

**私の仮説の「効いている方」が、観測不足で数字を拒否された。** 設計
どおりの動作で、ここが Optuna/DSPy 系との差(向こうは必ず数字を返す)。
