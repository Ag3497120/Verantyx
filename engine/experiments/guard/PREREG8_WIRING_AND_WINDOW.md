# 事前登録8: 静かに壊れないこと(①配線)と、欠けを1つの窓に出すこと

日付: 2026-08-22。**この文書を確定してから作る。** 提出直前のため、
**新しい機構は作らない** — 既にあるものを繋ぎ、見えるようにするだけ。

## 棚卸し(先に実測した。作り直さないため)

保留・承認の扉は**既に22本**ある: ai_facts / tool_calls / domain_modules /
capacity_limits / pack_verdicts の各 list_pending・accept・reject、
covenant の propose・review_candidates、memory_review、
`propose_web_evidence`(ウェブ抜粋を逐語で隔離 = 人が見る受け口)。
欠けの側も**既に7本**: `list_gaps`(DETECTED/ACQUIRING/RESOLVED/
BLOCKED_NO_SOURCE)、`what_would_close`(**装置は取りに行かない。
足りない文書を名指しし、人が供給する**)、`how_to_resolve`、
`resolve_gap`、`find_similar_gaps`、`record_refusal_outcome`、
`bootstrap_unknown_task`。自動で閉じにいく経路も既にある
(`heartbeat` の睡眠モードが欠け解決を回す)。

**足りないのは2つだけ**: ①配線が壊れたことに気づく手段 ②それら
29本の中身を**1つの窓**にまとめて人に出す扉。

## ① 静かに壊れないこと(W1〜W4)

番人は CLI が落ちたら素通しする(作業を止めない設計)。つまり
**配線が死んでも画面は正常に見える**。ここが恒久性の最大の穴。

W1. フックが設定されているか(settings の hooks が実在する台本を指すか)
W2. 呼ばれるバイナリ/ソースが実在するか。**凍結が repo より古ければ
    STALE と言う**(この罠は過去に実測済み: 中身の古い dist が
    「Build complete」と出る)
W3. MCP 設定が実在する command と store を指しているか
W4. 台帳に書けるか

判定は三値: `WIRED` / `PARTIAL` / `NOT_WIRED`。**未導入は故障ではない**
(単体だけ使う人がいる)ので BROKEN にしない。保証(G/S)が壊れたときだけ
BROKEN。

## ② 欠けを1つの窓に(D1〜D3)

D1. `pending_decisions` は**読むだけ**の扉。既存の待ち行列と欠け台帳を
    集めて、種類ごとに「何が保留か・どの扉で閉じるか」を返す
D2. **数えたものは必ず既存の扉から来る**。新しい待ち行列を作らない
    (作れば必ずずれる)
D3. 自動で埋める側は**提案しかしない** — ウェブ抜粋は
    `propose_web_evidence` の隔離席に入り、採用は人の行為のまま。
    **装置自身は決して取りに行かない**(オフライン決定論を壊さない)

## 測定(V35〜V38)

- V35 配線検査が、壊した配線を名指しする: 台本が無い/バイナリが無い/
    凍結が古い/設定が存在しないパスを指す、の4つを注入して型が出る
- V36 未導入の機械で `NOT_WIRED` を返し、**BROKEN にしない**
- V37 `pending_decisions` が、実際に保留を作ったとき(候補の約束・
    欠け・ウェブ抜粋)に、その3つを数え、閉じ方(扉名)を挙げる
- V38 `pending_decisions` は**何も変えない**(呼ぶ前後で台帳の sha 一致)

## 停止条件

- 配線検査が誤って「壊れている」と言ったら(健全な環境で PARTIAL 未満)
  検査ごと棄却 — 狼少年の番人は切られる
- `pending_decisions` が独自に状態を持ったら棄却(窓は窓であって台帳
  ではない)
