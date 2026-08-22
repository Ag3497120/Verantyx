# 結果2: 番人の第二段 — 証人・隔離席・書かれていない禁止

日付: 2026-08-21。事前登録: PREREG2.md(V6〜V10、測定前に確定)。
測定: run_confirm2.py → results_confirm2.json。**5/5 合格。**
fork 174(A_PROMISE_TO_ACT_NEEDS_A_WITNESS)追加、全 fork **87/87**。
扉 **124**(+propose_covenant / +adopt_covenant / +audit_required)。

## ④ V6 — required は証人で見る(承認済みの順の1番)

「必ずpytestを実行して」に対し:
- 証人なし → REQUIRED_UNWITNESSED / pytest 実行の記録
  (Bash: `python3 -m pytest -q`)あり → REQUIRED_WITNESSED
- **境界(ターン区切り)後は UNWITNESSED に戻る** — ターンを跨いだ
  「やった」の混入(停止条件)は起きない
- 無関係の tool(git status)だけでは WITNESSED にならない
- requires の無い台帳は NO_REQUIREMENTS — 証人ゼロを違反と呼ばない
- 照合は部分文字列のみで意味の一致は主張しない。**遮断はしない**
  (このターンに実行が要ったかは文脈で、この層には見えない)。
  フックは前ターンの UNWITNESSED を次ターン冒頭で報せてから境界を切る

## ① V7/V8 — 抽出は LLM に手渡し、執行と履歴は Vera(2番)

- candidate の違反は shadow_violations に分離され verdict は KEPT —
  **候補は一度も遮断せずに実績を積む**。adopt 後は同じ文で BROKEN。
  retire で棄却。淘汰は門
- 空の候補(禁止も要求も無い)は UNKNOWN_EMPTY_CANDIDATE で拒否
- 婉曲を regex で追いかける道は採らない(実測済みの壁: 645/661 が
  語彙の外)。扉 propose_covenant の docstring に理由を焼き込み済み

## ③ V10 — 書かれていない禁止の焼き込み(3番)

- 「拘禁刑の話はしないで」を店(刑法治具)つきで登録 →
  inferred_forbids=[罰金] が焼き込まれ、「この刑は罰金である」が
  **inferred 型で BROKEN**(字面の forbids とは型が分かれる —
  登録は利用者の言葉、推論は店の示唆)
- 平文(「規定について述べる」)は KEPT — 停止条件は踏まず
- 店に無い語(ゾルタクスゼイアン)→ inferred_forbids 空(推測しない)
- **check の実時間: 字面のみ比 1.08倍**(200回実測)— 登録時に一度だけ
  店を読む設計で、0.04s の速い道は死ななかった

## V9 — 順序不変(憲法)

証人の記録順(3!)×約束の登録順(3!)= 36通り、audit の行集合と
check の判定・違反集合が全て一致。

## 器官側の変更

- Covenant: status(adopted|candidate)、inferred_forbids、inferred_from
- Register: witnesses(境界方式・save/load で持ち越し)、audit()、
  propose()/adopt()。fading は candidate を数えない
- bake_inferred(): 登録・採用時に一度だけ siblings を焼き込む
- cli guard に propose/adopt/witness/boundary/audit(+set/adopt の
  infer オプション)
- フック: hook_posttool が**全 tool** を証人記録(matcher "*")、
  hook_prompt が前ターン監査→境界→薄れ再注入の順

## 残る限界(正直に)

- 証人照合は部分文字列 — 「pytest を走らせたふり」(echo pytest)と
  実走の区別はない。区別には終了コードの記録が要る(次の配線候補)
- 隔離席の採否は人が門 — shadow 実績からの自動昇格はまだ設計して
  いない(自動化は「過検出の番人は切られる」との緊張があり、事前登録
  してから)
- 焼き込みは登録時の店のスナップショット — 店が育っても古い約束の
  inferred は自動では育たない(再焼き込みの時機は未設計)

## 追記: verdict の分離(凍結後の実測が炙り出した濁り)

凍結バイナリの端到端で、隔離席の確認中に verdict が BROKEN になった —
原因は候補ではなく、採用済み「必ずpytestを実行して」の required_missing
が**字面で** verdict を汚していたこと(実地試験が名指した誤検知の構造
そのもの)。法を直した: **violation は禁止側の証拠(字面・文字クラス・
焼き込み推論・置換の実使用)だけ**。required の字面欠落は advisories に
分離され verdict に触れない — 行為の required は audit(証人)が見る。
履歴(風化)は advisory も破りに数える — 誤検知が問題なのは遮断であって
観測ではない(「TypeScriptと書かなくなってきた」は報せる価値がある)。

これに伴い既存 fork 2本を新しい法に張り替え:
- A_COVENANT_BINDS_THE_EXCHANGE… — terse な逸脱は advisory。fork 自身の
  docstring が言っていた「所見は提案であって判定ではない」に法が追いついた
- THE_STORE_INFERS_THE_PROHIBITION… — 手登録だけなら advisory、店が
  置換の**実使用**を示して初めて violation(推論が証拠を持ち込む、は不変)

再測定: forks 87/87、V1〜V5 7/7、V6〜V10 5/5(全て法の変更後に再実行)。

## 追記2: 言語対称(ja+en)の実測 — run_confirm_lang.py 3/3

- V11 抽出: 同じ意味の指示3組が ja/en 両方で候補1本ずつ
  (Stop using / avoid using を EN 禁止形に追加)。読めない文は両言語で0
- V12 解除: 解除の言葉も器官の閉じた表に一元化(extract_releases、
  フックの独自regexを廃止)。ja「もう絵文字使っていいよ」/
  en "you can use emojis again" / "TODO is fine now" /
  "go ahead and use print" が対象語を返し退役まで通る。
  読めない解除は解除しない(両言語で空)
- V13 執行の言語中立: en 約束の emoji クラスが 🎉 を捕まえ、en の
  requires が en の証人(npx eslint)で WITNESSED、en 候補の隔離席→
  採用→BROKEN も通る
- 凍結バイナリ端到端: 混在文から candidates 1 + releases [絵文字, TODO]

言語を選ぶのは閉じた表(抽出・解除・クラス)だけで、執行・証人・
隔離席・焼き込み・風化は字面照合なので言語中立 — その主張も en の
実データで確認した上で書いている。
