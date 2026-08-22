# 事前登録4: 規則が読んだ約束を執行に入れない — 誤遮断を止める

日付: 2026-08-21。**この文書を確定してから測定コードを書く。**
前段: PREREG.md(7/7)/ PREREG2.md(5/5)/ PREREG3.md(5/5)/ 言語対称(3/3)。
現況: fork 88/88、guard の測定 20/20。

## 今日見つかった欠陥(実測、再現済み)

`verantyx/covenant.py` の `extract_covenants()`(閉じた正規表現)が
指示文から約束を作り、それが**即座に執行(遮断)に入る**。人が実際に
書く指示20本で測ったところ、正しく読めたのは実質3本、13本は何も立たず、
**4本は間違った語を捕まえた**。本日この場で再現した3本:

| 指示 | 立つ約束 | 結果 |
|---|---|---|
| `No new dependencies` | forbids=["new"] | 返答 "I added a new helper function." が **BROKEN(誤遮断)** |
| `Always run the tests before committing` | requires=["the"] | 冠詞を要求語にする |
| `Stop using console.log` | forbids=["console"] | `.log` が落ちる |

## 方針: 規則を増やさない

過去の実測(`docs/MEASURED_2026-08-21_polarity_regex_not_the_wall.md`)より、
正規表現を足して被覆を上げる道は閉じない(否定 645/661 が語彙の外)。
したがって**規則を増やすのではなく、規則が読んだものを執行に入れない**。
隔離席(`Register.propose` / `adopt` / shadow_violations /
`promotion_review`)は PREREG3 で既に器官にある。**新しい機構は作らない** —
配線を替えるだけ。

## 変更(5点、すべて既存機構の配線)

1. **出所を候補自身が持つ** — `extract_covenants()` の返す候補に
   `origin="regex"` を付け、`Covenant` に `origin` 欄を足す(既定は空 =
   「人が明示した」)。**なぜ配線ではなく候補に持たせるか**: フックを一つ
   書き換えるだけだと、別の配管が `guard set` を呼んだ瞬間に法が破れる。
   出所が候補に付いていれば、どの入口から入っても隔離席へ落ちる。
2. **`guard set` は origin="regex" を隔離席へ回す**(法が配管に依存しない
   ための戻り止め)。origin の無い payload は今まで通り執行に入る。
3. **`guard propose` が正規の入口** — フック `tools/guard/hook_prompt.py`
   は `guard set` ではなく `guard propose` を呼ぶ。
4. **`tools/guard/hook_stop.py` は隔離席の違反を遮断せず知らせる** —
   `decision: block` は adopted の `violations` のときだけ。
   `shadow_violations` は非遮断の知らせ(`systemMessage`)で出す。
   知らせるのは**禁止側の証拠がある行だけ**(`forbidden_used` /
   `class_hits`)— 字面の `required_missing` が誤検知だらけなのは
   実地で実測済みで、そこは今回も報せない。
5. **推薦は見せるが採用はしない** — `hook_prompt.py` が
   `promotion_review`(既存)の PROMOTABLE 行を利用者に見せる。
   **自動採用は絶対にしない**。基準は PREREG3 で固定済み
   (min_checks=8 / max_fire_rate=0.5)を流用し、変えない。

## 人が明示登録したものは変えない

`guard set`(origin 無し)と MCP `set_covenant` は**今まで通り執行(遮断)
する**。これは利用者自身の行為で、番人が勝手に弱めてよいものではない。

## 測定(V19〜V24)— run_confirm4.py

- **V19 誤遮断が止まる**: `No new dependencies` を `extract_covenants` →
  配線どおり隔離席へ登録 → 返答 "I added a new helper function." が
  - `verdict == "KEPT"`(遮断されない)
  - `violations == []`
  - `shadow_violations` に**1件**出て、`forbidden_used == ["new"]`、
    covenant 名が元の指示文(= **見えなくなっていない**)
  - 候補の `status == "candidate"`
  さらに欠陥3本(`No new dependencies` / `Always run the tests before
  committing` / `Stop using console.log`)を全部通して、
  **執行に入った(adopted)約束が 0 本**
- **V20 人の明示登録は今まで通り遮断**: 同じ内容を origin 無しで
  `guard set` 相当に登録 → `verdict == "BROKEN"`、`violations` 1件、
  `shadow_violations` 無し。既存の実運用形(絵文字クラス)も BROKEN のまま
- **V21 採用したら執行に入る**: V19 の候補を `adopt` → 同じ返答が
  `BROKEN`、`shadow_violations` 無し、`in_force` が 0 → 1
- **V22 順序不変**: adopted 1本 + candidate 2本を 3!=6 通りの登録順で
  登録し、`verdict`・`violations` の集合・`shadow_violations` の集合が
  全一致
- **V23 配管(端到端)**: 一時台帳を使い、フックを実プロセスで走らせる
  - `hook_prompt.py` に `{"prompt": "No new dependencies"}` →
    台帳に1本、`status == "candidate"`、adopted は **0**
  - `hook_stop.py` に `{"last_assistant_message": "I added a new helper
    function."}` → 出力に `decision` が**無い**、かつ知らせ
    (`systemMessage`)が**在る**
  - `adopt` 後の同じ `hook_stop.py` → `decision == "block"`
  - 戻り止め: `guard set` に `origin="regex"` 付き payload を渡しても
    adopted にならない
  - 端到端は**ソース CLI**(`python3.11 -m verantyx.cli`)で測る。凍結
    バイナリは今日の変更を含まないので、そこに基準を置かない(再凍結は
    しない — 私の担当ではない)
- **V24 回帰**: `run_confirm.py` 7/7・`run_confirm2.py` 5/5・
  `run_confirm3.py` 5/5・`run_confirm_lang.py` 3/3 と
  `all_cross_geometry_forks()` が**全て緑**。fork は1本足すので 89/89

fork を1本足す(176本目): 規則が読んだ約束は候補であって執行ではない、
人が明示した約束は執行のまま、採用は門、という三点を性質として釘打つ。

## 停止条件

- V19 で `verdict` が `BROKEN` のまま → 隔離席への配線が効いていない。
  **規則を足す方向へは行かない**(その道は閉じないと実測済み)。設計を
  やり直す
- 隔離席の知らせが `decision: block` を1件でも出す → 裏口からの執行なので
  この段ごと棄却
- V20 が `KEPT` になる → 人の明示登録まで弱めた。差し戻す
- V19 で shadow に何も出ない(候補が黙って消える)→ 棄却。誤遮断を
  「見えなくする」ことで消すのは、番人を壊すのと同じ
- 既存4本のどれかが赤で、それが法の意図した変更として説明できない →
  差し戻す

## この段が直さないこと(先に書いておく)

- **抽出の誤読そのものは直らない**。`Always run the tests before
  committing` の requires は `["the"]` のままで、隔離席に入るだけ。
  直るのは「それが遮断に化ける」ことだけ
- **被覆も直らない**。20本中13本が何も立たないのはそのまま
- 隔離席が溜まると雑音になる。淘汰(retire)は人の行為のままで、
  この段では自動化しない
