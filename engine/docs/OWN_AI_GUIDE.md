# 自分の AI を作る — データ配置ガイド / Build your own AI — data placement

このシステムは文章を「注ぎ込む」と、決定論的な規則で構造に配置します。
LLM と違い、配置には毎回同じ理由があり、その理由は必ず表示できます。
Pour text in and deterministic rules place it. Unlike an LLM, every
placement has a stateable reason, every time.

## 配置の仕組み / How placement works

1文はこう分解されます / One sentence decomposes as:

| 要素 | 何か | 例:「本町の避難所は閉鎖されました」 |
|---|---|---|
| コア core | 文の主題。索引キー | 避難所（は/が の前の句の最後の名詞） |
| ファセット facet | 主題について言われた内容語 | 本町, 閉鎖 |
| 極 pole | 状態の主張(開/閉など)。矛盾検出の単位 | 開設:閉鎖 (−) |
| アーム arm | 6方向の知識分類(原因/根拠/種類…) | 手掛かりなし=未タグ(正常) |

矛盾は「同じコアの同じアスペクトに両極が置かれた」ときに自動検出されます。
A contradiction is detected when both poles of one aspect land on one core.

## 調整ループ / The adjustment loop

配置を手で並べ替えるツールは**意図的にありません**。手置きの事実は文から
再導出できず、再現性(同じ入力→同じ図鑑)が壊れるためです。代わりに:

1. **explain_placement** に文を渡す → コア・極・門の判定と理由が返る
2. 語彙が足りなければ → 文法オーバーレイに対を追加(下記)
3. もう一度 explain → 配置が変わったことを確認

There is deliberately no hand-reordering tool: hand-placed facts cannot be
re-derived, and reproducibility rests on placement being a pure function of
text plus grammar data. Adjust the GRAMMAR, not the facts.

## 文法データは同梱 / Grammar ships with the system

日本語の文法データはコードではなくデータとして同梱されています:
ストップワード 50 語、対義対 12 対、
別名 8、述語形 26(lang_data/ja_grammar.json)。

## 語彙を足す / Adding vocabulary (no code)

ストアの隣に `ja_grammar.json` を置くと起動時に読み込まれます。
Place `ja_grammar.json` beside your store; it loads at startup.

```json
{
 "antonym_pairs": [["点灯", "消灯"]],
 "predicates": {"点灯": "は点灯しています。", "消灯": "は消灯しています。"},
 "aliases": {"点いています": "点灯"}
}
```

規則(検証器が強制 / enforced by the validator):

- 各語 **2文字以上** — 1字は部分一致で誤爆を量産する(開 は 開始・公開・展開の中にいる)
- 1語に**両極は不可** — それは語彙ではなく矛盾製造機
- 既存アスペクトと同じ実態なら `aspect_joins` で**合流**させる
  (開館/閉館 は 開設 に合流済み — 別鍵だと実在の矛盾が見えない)
- 無効なオーバーレイは**全部の問題を列挙して拒否**される。半分だけ
  読み込まれることはない

### 見本パック / Sample domain pack

`lang_data/ja_domain_disaster.json` は災害情報ドメインの見本です。
**自動では読み込まれません** — 語彙は精度への責任を伴うので、明示的に
ストア隣の `ja_grammar.json` へ写して有効化します。provenance は
seeded(暫定)で、現場での確認を経て信頼される、という失敗パックと
同じ成熟度の考え方です。

## 罠に注意 / Known traps the system guards for you

- 複合語: 「停止線」「危険物」は状態主張ではない → 直後が漢字なら不採用
- 主語: 「gateway surfaces one installer (brew when available)」の
  available は brew の話 → コアが主語のときだけ極を置く
- 否定: 「安全ではありません」は not_安全 — 述語直後の接尾辞から読む

## 品質の自己診断 / Intake self-assessment

注ぎ込んだ後、システム自身が理解度を型で報告します:
INTAKE_OK / UNKNOWN_LOW_COVERAGE / UNKNOWN_FRAGMENTED_CORES /
UNKNOWN_DOMINANT_SOURCE / UNKNOWN_HIGH_DUPLICATION。
数値付きなので、閾値に不服なら反論できます。

## 関連ツール / Related MCP tools

- `explain_placement(sentence)` — この文はどこへ・なぜ
- `grammar_status()` — 同梱+オーバーレイの現在の語彙量
- `load_documents(paths)` — PDF/Word/HTML/CSV/JSON/テキストの一括投入
- `goal_recipe("独自のAIを作る")` — 設定手順(7ステップ)
