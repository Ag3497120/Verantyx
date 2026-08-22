# 未到達38本の分類(2026-08-19)

到達性の棚卸し(RESULTS.md)で出た57本から、枠組み override(HTTPハンドラ・
ast visitor・HTMLParser)19本を除いた**38本**を、一本ずつ分類した。
**「archive か死か」の区別が付いていないこと自体が欠陥**だったので、
ここで確定させる。

## Ⅰ. 凍結による未接続 — 1本(正しく切ってある)
| 器官 | 状態 |
|---|---|
| `document_structure.propose_heading` | jgen 埋め込み表(`lex.nearest`)に依存。**jgen 系は 2026-08-18 に凍結**しており、切れているのは方針どおり。実測値は docstring に残る(言い換え8本中4本到達・4本拒否・誤り0)。**同日の `def_edges`(辞書辺)が jgen 抜きの代替**であり、重複ではなく置き換え。 |

## Ⅱ. 本日接続したもの — 2本
| 器官 | 接続先 | 荷重 |
|---|---|---|
| `document_structure.verify_quoted` | — (構造で既に成立、独立監査として) | fork 159 `QUOTE_IS_SUBSTRING` |
| `fusion.read_at` | MCP扉 `vera_read_at` | fork 160 `READ_AT_SHOWS_BOTH_SIDES` |

`read_at` は接続直後に価値を示した。実店の「時効」:
```
[百科] 時効は解、除斥期間
[法学] 時効は18民主化運動等、光州事件、制定
[指名] 時効は援用、中断、完成、成立
```
併合すれば消える食い違い。「正当防衛」の辞書欄はテレビドラマで、これも
語義の分かれ目 — **平均しないことが価値**という設計の看板に、出口が付いた。

接続時に判明した限界: `read_at` の絞り込みは「概念が **facet として**
現れる分野」だけを見る。core 名だけでは通らない — `direction_band` で
名前を数え忘れて帯から core 自身が脱落したのと**同じ罠**が此処にも在る。
fork の固定具にその条件を明記した。

## Ⅲ. 扉が要る器官(価値はあるが未着手) — 9本
| 器官 | 何をするか | 要るもの |
|---|---|---|
| `procedure_exec.execute_procedure` 他2 | 閉じた命令集合での手順実行、型付き拒否つき | MCP扉 + fork |
| `kripke.kripke_ask` 他2 | 様相論理の領域アダプタ | 領域登録 + fork |
| `resolution.ask_stack` | 解像度梯子の全段投票 | 扉 + 測定 |
| `granularity.discover` / `discover_units` | 粒度の発見と検証 | ビルド側の呼び出し |
| `gapnode.gap_store` / `enqueue` | 欠落を十字の店として持つ / 成長待ち行列への投入 | 成長ループとの接続 |

## Ⅳ. ビルド/コーパス側(ツール経由で使う想定) — 8本
`corpus_en.iter_english_tokens` / `load_english_corpus` / `count_tokens`、
`egov.ingest_laws`、`corpus_audit.load_marked`、
`catalog.reproducibility_check`、`vocabulary.from_cuts`、
`covenant.infer_forbidden`。
これらは**再構築時にだけ走る**種類で、常時経路に居ないのは異常ではない。
ただし「いつ誰が呼ぶか」がどこにも書かれていないのは欠陥なので、
build_ja / tools 側の手順書に位置を書くのが次の一手。

## Ⅴ. 後継があるか、部品として小さい — 18本
`compose_ja.compose_walk`(→ `stacked.in_words` が後継の可能性、要判定)、
`en_decompose.decompose_sentences` / `classify_texts` / `content_head`、
`trace.export_view`、`face_roles.is_core_face` / `is_facet_face` /
`facet_read_path`、`cross.clear_wires` / `dump_volume`×2、
`conduct_tree.is_leaf_arm`、`lex_filters.is_proper_key`、
`intent_frames.fold_verb`、`proposal_verify.triage`、
`meaning_descent.grounding_of`、`procedure_exec.registered_procedures`、
`kripke.register_kripke_world` / `register_kripke_edge`。

`compose_walk` だけは判定が要る(後継があるなら archive と明記、無いなら
Ⅲへ)。他は補助部品で、単独で扉を持つ性質のものではない。

## この分類を維持する方法
`audit.py` を回帰に入れ、**数(57)が増えたら気づける**ようにする。
増えた分だけを見れば済むので、二度と38本溜めずに済む。
