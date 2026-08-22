# 統合台帳 — 177器官はどこに立っているか（2026-08-18）

**測定**: import 到達可能性（AST、推移的）。根は2つ — `engine.py`
（合成の単一境界）と `mcp_server.py`（106扉）。

```
全器官 177
  MCP から到達      103   ← 扉として、または扉の部品として生きている
  engine から到達    51   ← 一問ごとの合成に乗っている
  どの根からも不達    74   （器官37 / fork・eval 22 / 道具・配布 15）
```

## 一つの境界、という答え

「全部を見て一つにまとめる」の答えは**新しい統合器を書くことではない**。
それは既に2回行われている:

1. `assembled.py`（旧） — 「全器官を一本の道に」。docstring が今回と同じ
   診断を先に書いている: *測った扉を開けた者が、それを「エンジン」と呼ぶ*。
2. `engine.py`（現行） — assembled の後継。MCP の `vera_engine` が呼ぶのは
   こちらで、intent→typo→段分割→math→mathlib→文書→store→diff→ask→
   文脈→降下→腕→gap→構成、の実測順を持つ。

**統合とは、この一つの境界に「乗せるべきで乗っていないもの」を数え、
「乗せてはならないもの」を名指しし続けることである。** 本日の追加:

- `vera_chat`（MCP扉106本目） — 会話そのものを境界に乗せた。engine.ask +
  会話空間（内容アドレス・窓なし）+ covenant/文脈監査 + last_core をサーバ側
  で持つ。**IDEはモデルを一切ロードせず、MCP samplingも呼ばれない** —
  サンプルするものが存在しないから。
- math段の修正 — 「3たす4は」が ANSWER 3 を返す捏造を、閉じた演算語表と
  「演算子なしは渡さない」門で閉鎖（`3013047`）。
- conversation の2欠陥修正 — 識別子内の `.` での文分割（`7e95d2d`）、
  核索引にない言及の偽ABSENT（`27a65e6`）。

## 乗せてはならないもの（測定が禁じた。配線したら停止条件違反）

| 器官 | 判定 | 記録 |
|---|---|---|
| `placement` | P1 REJECTED — held-out で頻度規則に勝てず | PREREGISTERED_2026-08-16_bake_placement |
| `ingest_coherence` | 検出66% vs 偽陽性60%、分離せず。台帳のみ・非配線 | 納品3 検収 `6b6267e` |
| `jgen_lexicon`（見出し辞書用途） | L1 FAIL — 文の負例で床が引けず撤回 | PREREGISTERED_2026-08-17_lexicon_heading_alias |
| `cognitive_interventions`（隠れ状態介入） | 2026-08-17/18 に null 4本 + 運用者指示で LLM系凍結 | verantyx-cli 側の登録4本 |

## 壊れている / 置き換え済み（残すが、読む者への注意）

| 器官 | 状態 |
|---|---|
| `dialogue_context` | **構文エラー**（docstring未終端）。import不能。`conversation.py` が後継。削除候補 |
| `assembled` | `engine.py` に置き換え済み。歴史として残す |
| `hierarchy` | `conduct_tree` が併存後継（8/14に上書き事故→原本復元の経緯つき） |

## 測定済みだが未配線（価値の待ち行列 — 乗せるなら測定つきで）

| 器官 | 実測 | 乗る場所 |
|---|---|---|
| `conduct_tree` | 降下95%・誤0、経路 0/52→52/52 | ask の前段（分野降下）。8/14から未配線のまま |
| `store_sqlite` | 増分保存 | 規模の天井外し |
| `gapnode`/`defect_gaps`/`gap_severity`/`self_audit`/`self_evolve`/`rule_synthesis` | 進化ループ（負債3,164→2,761） | 拒否ログ→待ち行列の常設化 |
| `procedure_exec`/`rewrite_core`/`rewrite_math` | 閉命令セット、桁加算実証 | math_sim の除算穴はここで埋めるのが筋 |
| `agent`/`router` | ReAct制御 | 凍結中（LLM系）だが設計はVera側 |
| `polyglot`/`constellation`/`sovereign`/`full_sovereign` | ソブリン並列（上に統括を置かない） | 構築系。CLI経由で生存 |
| `lean_witness`/`tree_witness` | mathlib 75,919定理の証人 | engine は `mathlib_witness` 経由で読む |
| `links`/`axis_summary`/`vocab_growth`/`proposal`/`proposal_verify` | 引用リンク74.5%等 | 取り込み側 |
| `kripke`/`rotation_signature`/`card_numbers`/`field_session`/`polyglot` ほか | 各docstringに実測あり | 個別に事前登録して判断 |

fork/eval 22本は回帰資産（配線対象ではない）。道具・配布15本は運用資産。

## 会話扉の検収記録（2026-08-18）

凍結バイナリ（`vera-memory.spec` 再凍結、81.2MB）を MCP stdio で直接検収:

```
tools/list        106扉、vera_chat あり
正当防衛とは       SEEDED  core=正当防衛
その成立要件は     SEEDED  last_core=成立要件   ← 照応がサーバ側で解決
3たす4は          ANSWER  7                    ← 修正済みmath
監査              covenants ok / context_drift ok（返答の隣、門ではない）
```

IDE側は `veraModelTurn` が `vera_chat` を呼ぶ（旧バイナリには `vera_engine`
へ後退）。BUILD SUCCEEDED。`Vendor/vera-memory` 差し替え済み。
