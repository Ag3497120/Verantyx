# 結果: 番人 — 実地試験の限界を塞いだあとの実測

日付: 2026-08-21。事前登録: PREREG.md(V1〜V5、測定前に確定)。
測定: run_confirm.py → results_confirm.json。**7/7 合格。**
fork 173(COVENANT_LIFECYCLE)追加、全 fork **86/86**。扉 **121**
(+retire_covenant / +extract_covenants)。

## V1 — 抽出(ja+en)と退役(限界1・3の修理)

- 混在文「絵文字を使わないで。今後は必ずテストを実行して。
  Never use TODO comments. Always run pytest before commit.」
  → 候補4本: ja禁止(絵文字)・ja要求(テスト)・en禁止(TODO)・
  en要求(pytest)。**英語からも約束が立つ。**
- 退役: TODO の約束を retire → 同じ違反文で hits 4→3、TODO は
  もう報じられない。**席は残る**(covenants 数は不変、list に
  retired 印つきで見える)。削除ではない — 履歴が provenance。

## V2 — 文字クラス(限界2の修理)

「絵文字を使わないで」だけの約束が、語ではなく **🎉 と ⭐ そのもの**を
捕まえ、見つけた文字を class_hits で名指す。絵文字の無い通常文
(「表情記号の話をしています」)は素通し — 停止条件(平文での誤検知)
は踏まなかった。クラス表は絵文字1項のみの閉じた表。「日本語を
使わないで」は文字クラスにしない(日本語の返答すべてが違反になる)—
正直な限界として残す。

## V3 — 推測しない・退役は風化からも消える

- 「なんかいい感じでよろしく」→ 候補0(読めない指示から約束を
  捏造しない)。
- 破られつつある約束 a は fading に出る、退役済みの b は出ない
  (解かれた約束の風化を報せても雑音)。

## V4 — 登録順不変(憲法)

3約束×4文×順列6通り、判定と違反集合が全順列で一致。

## V5 — 速い道の実時間(限界5の修理)

| 経路 | check 1回 | 判定 |
|---|---|---|
| ソース直呼び(python3.11 -m verantyx.cli guard check) | **0.044〜0.050s** | BROKEN/KEPT 正 |
| 凍結バイナリ(onefile) | 3.63〜3.81s | BROKEN/KEPT 正 |

- フック(tools/guard/_common.py)は**ソース直呼びを優先**し、
  リポジトリ不在時のみ凍結バイナリに落ちる。橋(常駐)は不要 —
  15〜45秒 fail-open の窓は消えた。
- **正直な記録**: 凍結バイナリ単体は 2秒基準を超える(onefile の
  展開が毎回かかる)。リポジトリの無いマシンで 2秒を切るには
  onedir 凍結か常駐が要る — 未解決のまま名指しする。

## 同梱フック(tools/guard/)

- hook_prompt.py: UserPromptSubmit — extract→set、解除の定型
  (「もう〜使っていいよ」)→retire、**薄れた約束だけ**再注入。
- hook_stop.py: Stop — 返答照合、BROKEN(禁止側のみ)で遮断。
  required_missing は記録のみ(実地試験が誤検知を実測済み)。
  stop_hook_active で二度は止めない。
- hook_posttool.py: **PostToolUse(Write|Edit)— 限界4の覆い**。
  ファイル内容を同じ check に通す。書き込みは既に起きているので
  遮断ではなく additionalContext で報せる(取り消せない block は嘘)。
- CLI 不在/故障時は素通し(Vera の都合で作業は止めない)。

## 器官側の変更

- Covenant: retired / retired_quote / retired_at_turn。退役済みは
  check・履歴・fading から外れ、list には残る。
- Register.retire(name, quote, turn) — 同名は最初の未退役だけ。
- Register.save/load が**履歴も運ぶ**(guard CLI は毎回プロセスが
  死ぬので、履歴が残らないと風化が測れない)。旧形式(素のリスト)も
  読める。
- extract_covenants: 閉じた規則 ja+en。ja捕獲は名詞連続のみ
  (「では絵文字」の助詞混入を再現して修理 — 実地試験と同じ罠)。
- cli.py `guard` {extract,set,check,fading,retire,list}: 連邦を
  読まず covenants.json だけ。check は履歴保存(風化の材料)。
