# 経験のコンパイル — 棚卸し(2026-08-20)

方針(操作者・同日): 5つの空白地帯を別々に売らず、**AIの知識・行動に
対する証拠つき状態管理 = 経験のコンパイル**として統合する。統合は
**束ねない** — 各器官は住処に残り、読み出し層(コンパイラ)が型を与える。

## 9状態型 × 既存器官の対応(実地検査済み)

| 状態型 | 器官 | 配線 | 永続 | 穴 |
|---|---|---|---|---|
| CLAIM | attest_claim / polar_claims | 扉 | 文書ストア | **否定盲**(実測・修理チップ済) |
| CLAIM(行動規約) | check_reply / covenants | 扉 | covenants.json | 削除の扉が無い |
| EVIDENCE | facet witnesses `verified:*` | 全域 | 各ストア | — (lean4/tool/run/url/ui の5種) |
| GAP | gap_graph + what_would_close | 扉 | gap_graph.json ほか | **再評価ループ未配線**(新証拠→再判定→証人つき閉鎖) |
| FAILURE | failure_domains / refusals / TrialLedger | 扉+器官 | packs / refusals.jsonl / proof_ledger | 数学・ハーネス・本体で**別在庫** |
| COUNTEREXAMPLE | ground_check REFUTED / 輸入拒否 | 器官内 | **実験JSONに散在** | **一級の永続台帳が無い** |
| TRANSFER | transfer_log(3扉) / harness_facts | 扉+実験 | vera_store系 / 実験dir | docstring自認「分析する段が無い」 |
| RULE | RuleStore / COND_RULES / ml断片 | 器官内 | mathlib_*_rules.json | 証人つき — 最も整っている |
| PROCEDURE | procedure.py / procedure_vary / intent_chain | **未配線** | — | ハーネス項抽出の席(既知) |
| WITNESS | lean/tool/run/url/ui の記録扉 | 扉 | 各ストア | earn の規律は統一済み |

## 物理ストアの散在(経験が住んでいる8箇所)

vera_store.json / gap_graph.json / covenants.json /
proof_ledger*.json(実験) / harness_facts.json(実験) /
mathlib_eq_rules.json / mathlib_list_rules.json / refusals.jsonl

## 構造的な穴 3つ(棚卸しの結論)

1. **COUNTEREXAMPLE に一級の家が無い** — 反例は今日いちばん働いた器官
   (133万候補反駁・偽束の反例名指し・輸入拒否273本)なのに、住処が
   実験JSONの rejected 配列に散在。状態機械の「反例→一般化禁止」を
   跨いで効かせるには台帳が要る。
2. **GAPの再評価ループが無い** — Gapは開くが、「新しい証拠が入ったら
   再評価→閉じたことを証人つきで記録」の後半が未配線(操作者の構想の
   核心部分)。
3. **転移が分析されないまま3箇所に散在** — transfer_log(空)・
   harness_facts(今日初の実データ)・数学の手渡し引用。「モデルAで
   効いたがBで効かず」の一般形は今日実測で出たのに、読む層が無い。

## 最初の一手

読み出し層(コンパイラ)を**読み取り専用**で建て、8ストアを9型に写して
一覧できることを実測する。束ねない: 元の在庫は不動、写像だけが新しい。
