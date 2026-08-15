# Handoff → Cursor (Fable 5) — 2026-08-13

Claude Code側のセッション文脈をここに固定する。このファイルはコミット不要(作業メモ)。

## 作業場所の正
- **IDE**: `~/Projects/Verantyx` (main追従の恒久クローン、HEAD `bdcd21817`)。
  `~/Verantyx`(=Cursorで開きがちな方)は128コミット古い別ブランチ — 編集禁止。
- **Veraエンジン**: `~/Projects/Verantyx-Vera-alpha` (branch feat/structural-properties-and-deep-search)
- **測定相手**: `~/Projects/vera-corpus/build/vera.db` (89,369核)
- **Rustエンジン/変換器**: `~/Projects/verantyx-cli` (branch cursor/moe-gpu-batched-64b8)
- モデル実体: `~/Library/Application Support/Verantyx/jgen/converted_models/`

## 絶対規則
- `xcodegen generate` 厳禁(手書きpbxprojを破壊)。新規Swiftファイルはpbxprojへ手動登録。
- ビルド: `xcodebuild -project Verantyx.xcodeproj -scheme Verantyx -configuration Debug`
- 束ねず重ねる / 同点は棄権 / データ違い=証人・区切り違い=供給(censusに入れない)。
- 実測なしの数値をdocstring/コミットに書かない。

## 直近の状態
- f16版50GB jgenは削除済み(ユーザー承認)。正は `qwen3.6-27b-q4k.jgen` 16GB(検証済み)。
  復元 = HFからq4_k_m GGUF再取得 → jgen_forgeパススルー変換(ビット同一)。
- 空き53GB。DerivedDataは削除済み(次ビルドで再生成)。
- AgentLoop逸脱タグ改修(署名別予算)は `~/Projects/Verantyx` に適用済み・未コミdate。
  バックアップ: `~/Projects/UNCOMMITTED-agentloop-straytag.patch`
- 保留判断: 旧checkout唯一の先行コミット `0018c4df4`(UI文字列36個のi18n)を
  cherry-pickするか — AgentLoop分のpush後に `git cherry-pick -n` で検証。

## 未完了タスク(優先順)
1. AgentLoop改修のビルド→コミット→push
2. Q4: qwen3.6-35b-a3b end-to-end — 材料はLM Studioの UD-Q2_K_XL 13GB。
   IDEの設定→JGENで変換(ログに `(quant passthrough)` が出ることを確認)。
   MoE+hybridの経路はエンジンに実装済み・実GGUFでは未検証。
3. ハーネス配線: `ModelTier.fixedHarness` は宣言のみ(enabledToolCategoriesは未消費)。
   JGEN=自由ハーネス(全ツール)/他=固定、をツール組み立てに実配線。
4. Vera側: 判定=帯の全配線(concord階調をask/監査チャット/3Dへ)、
   創作=語彙の門(「中心が語でない」69%。表面伝導の第二歩+独立出現3回篩)。

## 今週の主要コミット(文脈はコミットメッセージが一次資料)
- IDE main: bdcd21817(Veraエンジンパス設定) ← 02fdf736(別セッション群) ← c0a9d453(2画面+ステージ)
  ← 8da244ce(effectiveModelName) ← 3bbe7eb9(Max tokens上限撤廃) ← 17824c9f(LM Studio推論診断+エディタ)
- Vera-alpha: 305880e(木の証人帯: 正解143/誤0/棄権260・捏造ゼロ)
- verantyx-cli: ab3cd7a05(QuantBlocks+requant+パススルー)
