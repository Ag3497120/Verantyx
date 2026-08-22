# 事前登録3: 番人の第三段 — RESULTS2 が名指した残り3つの限界

日付: 2026-08-21。**この文書を確定してから測定する。**
前段: PREREG.md(7/7)/ PREREG2.md(5/5)/ 言語対称(3/3)。

RESULTS2 の「残る限界(正直に)」3項をそのまま課題にする。

## ⑤ 証人が「実行のふり」と実走を区別できない

現状の照合は部分文字列なので `echo pytest` が pytest の証人になる。
二段で直す。**どちらも推測を増やさない方向**(閉じた表と、あるなら
使う事実だけ)。

1. **呼ばれた道具か、字の中の語か** — コマンドを区切り(`|` `&&` `||`
   `;` 改行)で割り、各区画の先頭語=呼ばれた道具とする。閉じた包み表
   (npx/uv/poetry/npm/yarn/pnpm/bunx/pipenv/pdm/hatch/rye/cargo/go/
   dotnet/sudo/env/time/nice/xargs + run/exec)と `-m <module>` だけ
   一段めくる。版番号の尾(python3.11→python)は閉じた正規化で落とす。
   一致の型: **INVOKED**(呼ばれた) / **MENTIONED**(字の中にあるだけ)。
   audit が証人として数えるのは INVOKED のみ。MENTIONED は別の弱い型で
   報じる(黙って捨てない)。
2. **終了状態** — フックが渡せるときだけ ok(True/False)を記録する。
   渡せないときは None のまま。**不在と否定を混ぜない**:
   - INVOKED かつ ok=True → REQUIRED_WITNESSED
   - INVOKED かつ ok=False → **REQUIRED_FAILED**(やって落ちたは、
     やっていないとは違う知らせ)
   - INVOKED かつ ok=None → **REQUIRED_WITNESSED_UNVERIFIED**
     (黙って合格に格上げしない)
   - INVOKED なし → REQUIRED_UNWITNESSED
   台帳の verdict 優先順(決定的): FAILED > UNWITNESSED > UNVERIFIED >
   WITNESSED。行は常に全部返す(要約が証拠を隠さない)。

## ⑥ shadow 実績からの昇格が未設計

**自動採用はしない**。過検出の番人は切られる、が実地の教訓で、
候補を勝手に執行へ入れるのはその罠そのもの。機械がやるのは
**推薦と棄権**だけで、adopt(門)は別の行為のまま。基準は測る前に
ここで固定する:

- 圏内照合(in_scope)が **8回未満** → `UNKNOWN_TOO_FEW_CHECKS`
  (率を出さない。回数だけ報せる)
- 一度も発火していない → `REFUSED_NEVER_FIRED`(必要の証拠がない)
- 発火率が **50%超** → `REFUSED_OVERFIRING`(過検出の疑い)
- 8回以上・1回以上発火・50%以下 → `PROMOTABLE`(**推薦であって採用
  ではない**。status は candidate のまま)

## ⑦ 焼き込みが登録時のスナップショット

店が育っても古い約束の inferred は古いまま。**再焼き込みの時機**を
決める。線: **check の速い道(0.04s)では絶対に店を読まない**。

- 焼き込み時に店ファイルの指紋(mtime・size・名)を残す
- `guard stale` は **stat だけ**で陳腐化を答える(店を読まない)。
  基準: 100ms 以内
- `guard rebake` のときだけ店を1回読み、adopted の焼き込みを更新して
  **差分(足された語・落ちた語)を報せる**。`dry_run` は保存しない
- 落ちた語は消す — 推論は利用者の言葉ではなく店の示唆で、店がもう
  示さない語を持ち続けるのは「本文が許す以上を主張する」側の誤り

## 測定(V14〜V18)

- V14 ふり: `echo pytest` は MENTIONED 止まりで UNWITNESSED。
  `python3 -m pytest -q` / `npx eslint src` / `uv run pytest` は INVOKED
- V15 終了状態: ok=True→WITNESSED / ok=False→FAILED / ok=None→
  UNVERIFIED。3値が混ざらない
- V16 昇格: 4つの結末(PROMOTABLE / OVERFIRING / NEVER_FIRED /
  TOO_FEW)が事前登録の帯で分かれ、**推薦後も status は candidate**
- V17 陳腐化: 焼き込み→店の成長→stale が STALE と言う(stat のみ・
  100ms以内)→ rebake で語が増える。dry_run は保存しない。
  店に無い語は増えないまま
- V18 順序不変: 証人の記録順・約束の登録順を入れ替えても audit の
  verdict と行集合、昇格の行、rebake の差分が同一

## 停止条件

- V14 で素の `pytest -q` や `./scripts/test.sh` 形の呼び出しを
  MENTIONED に落とす(実走を見逃す)→ 語り分けを棄却し部分文字列に戻す
- V17 で stale が 100ms を超える、または check が店を読み始める →
  再焼き込みごと棄却(速い道が製品の芯)
