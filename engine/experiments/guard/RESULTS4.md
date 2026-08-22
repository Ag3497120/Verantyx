# 結果4: 規則が読んだ約束を執行に入れない — 誤遮断が止まった実測

日付: 2026-08-21。事前登録: PREREG4.md(V19〜V24、測定前に確定)。
測定: run_confirm4.py → results_confirm4.json。**6/6 合格。**
fork 176(A_RULE_A_REGEX_READ_IS_A_CANDIDATE)追加、全 fork **89/89**。
既存4本の再実行: 7/7・5/5・5/5・3/3(**20/20、張り替え無しで緑**)。

## 欠陥は実在した(直る前を測ってから直った後を測る)

`No new dependencies` → `forbids=["new"]` → 返答
「I added a new helper function.」→ **BROKEN**(V19 の `before_fix` で
再現)。同じ経路で読まれた他の2本も誤読のまま:

| 指示 | 立った約束 |
|---|---|
| `No new dependencies` | forbids=`["new"]` |
| `Always run the tests before committing` | requires=`["the"]` |
| `Stop using console.log` | forbids=`["console"]`(名前は `Stop using console`) |

規則を足す道は取らない(否定 645/661 が語彙の外、実測済み)。
**直したのは執行の側**で、隔離席は PREREG3 で既に器官にあった。

## V19 誤遮断が止まり、しかも見えなくなっていない

同じ指示・同じ返答で `BROKEN` → **`KEPT`**。`violations` は 0、
`in_force` は 0。ただし `shadow_violations` にちょうど1件出て、
`covenant="No new dependencies"` / `forbidden_used=["new"]` と
**名指されている** — 誤遮断を「見えなくする」ことで消すのは番人を
壊すのと同じなので、そこは基準に入れてある。

欠陥3本を全部通しても**執行に入った約束は 0 本**(全 status が
`candidate`)。3本まとめた台帳の shadow は2件で、内訳は:

| 候補 | forbidden_used | required_missing |
|---|---|---|
| `No new dependencies` | `["new"]` | `[]` |
| `Always run the tests before committing` | `[]` | `["the"]` |
| `Stop using console` | (発火せず) | — |

2本目は**禁止側の証拠が無い助言止まり**で、フックは知らせない
(字面の `required_missing` は誤検知が多い、という既定の線をそのまま
使った)。つまり `requires=["the"]` の誤読は、遮断もせず雑音も出さない。

## V20 人が明示登録したものは今まで通り遮断する

同じ `forbids=["new"]` を**出所の無い**登録で置くと `BROKEN`、
`violations` 1件、`in_force` 1、`shadow` 空。実運用形(絵文字クラス)も
`対応しました🎉`→BROKEN / `対応しました。`→KEPT のまま。
利用者自身の行為を番人が勝手に弱める理由は無い。

## V21 採用は門

候補のまま: `KEPT` / `in_force` 0 → `adopt` 後: **`BROKEN`** /
`in_force` 1 / `violations` に `["new"]`、`shadow` 空。
**出所は採用後も `"regex"` のまま残る** — 誰が何を根拠に執行を許したかを
消すと監査が嘘になる(retire が席を残すのと同じ線)。

## V22 順序不変

adopted 1本 + candidate 2本を 3!=6 通りの登録順で登録し、
`verdict`(BROKEN)・`in_force`(1)・`violations` の集合(1件)・
`shadow_violations` の集合(2件)が**全一致**。

## V23 配管の端到端(フックを実プロセスで走らせた)

- `hook_prompt.py` に `{"prompt": "No new dependencies"}` → 台帳の席は
  1つ、status は `candidate`、**adopted は 0**
- `hook_stop.py` に誤遮断された返答 → 出力に `decision` は**無い**。
  代わりに非遮断の知らせが出た:
  `Vera 隔離席(遮断していない): 「No new dependencies」の禁止語 ['new'] を使っている — 良ければ `guard adopt`、誤読なら `guard retire``
- `guard adopt` 後の同じ `hook_stop.py` → `decision: "block"`
- **戻り止め**: `guard set` に `origin="regex"` 付き payload を渡しても
  `routed_to_quarantine: true` で隔離席へ(status は candidate)。
  出所の無い `guard set` は今まで通り `in_force` 1 で執行に入る
- **推薦は見せるだけ**: 圏内照合10回・1回発火の候補で `hook_prompt.py`
  を走らせると「規則が読んだ候補『No new dependencies』が実績を積んだ
  (10回中1回発火)…(こちらでは採用しない)」と出し、走らせた後も
  status は `candidate` のまま — **自動採用はしない**

## V24 回帰

`run_confirm.py` 7/7・`run_confirm2.py` 5/5・`run_confirm3.py` 5/5・
`run_confirm_lang.py` 3/3・fork **89/89**(落ちた fork 0)。

**意図的に張り替えた既存測定は無い。** 既存4本と既存 fork 88本は一行も
書き換えずに緑のまま通った。理由: 変えたのは「規則が読んだ約束が執行に
入る」という**配線**だけで、既存の測定はどれも約束を直接
`Register.add`(= 人が明示した側)で置いているため、法の変更が届かない。
届いていたら張り替えが必要だったので、届かなかったこと自体が
「利用者の明示登録は変えていない」の傍証になっている。

## 自分が踏んだ治具の誤り(記録)

測定は2回落ちた。どちらも法ではなく**私の治具**の誤り:

1. V19 を「欠陥3本を1つの台帳に入れて shadow がちょうど1件」と書いて
   落ちた。PREREG4 は(a)誤遮断した1本の台帳で shadow 1件、(b)3本
   通して adopted 0本、と**二つに分けて**事前登録していたのに、実装で
   混ぜた。事前登録どおり分けて直した(基準を緩めたのではない)。
   落ちたおかげで `requires=["the"]` が助言止まりで知らせに出ないことが
   分かり、上表に載せられた
2. V24 で `"7/7"` と `"7/7 passed"` を比較して落ちた。文字列の比較を
   分数だけにした

## 残る限界(正直に)

- **抽出の誤読そのものは直っていない**。`Always run the tests before
  committing` の requires は `["the"]` のままで、隔離席に入るだけ。
  直ったのは「それが遮断に化ける」ことだけ
- **被覆も直っていない**。20本中13本が何も立たないのはそのまま
- **推薦が誤読を推薦しうる**。`promotion_review` の発火数は履歴の
  真偽値だけを見ており、`required_missing` 止まりの助言も「発火」として
  数える。`requires=["the"]` のような誤読が帯に入って PROMOTABLE として
  出る筋は塞げていない。緩和は二つだけ: 行に `origin: "regex"` を載せて
  門に立つ人に「規則が読んだ語だ」と見せること、そして採用が人の行為の
  ままであること。**根治には履歴が「どちら側の証拠で発火したか」を
  持つ必要があり、それは fading の意味も変えるので事前登録してから**
- **隔離席は溜まる**。淘汰(retire)は人の行為のままで、この段では
  自動化していない。毎ターンの知らせが淘汰の材料になる設計だが、
  「何ターンで人が実際に片付けるか」は測っていない
- **凍結バイナリは古いまま**(実測): `~/Projects/Verantyx/cli/
  VerantyxIDE/Vendor/vera-memory` に `origin="regex"` 付きで `guard set`
  すると `in_force: 1` を返す = 今日の変更を含まない。フックは
  リポジトリがあればソース直呼びを選ぶので実害は出ないが、**リポジトリ
  不在の環境では誤遮断が残る**。再凍結は私の担当ではないので触っていない
- 知らせの経路は Stop フックの `systemMessage`。遮断しないことは
  端到端で実測したが、**利用者の画面での見え方は測っていない**
