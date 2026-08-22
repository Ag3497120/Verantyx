# 結果3: 番人の第三段 — RESULTS2 の残り3限界を塞いだ実測

日付: 2026-08-21。事前登録: PREREG3.md(V14〜V18、測定前に確定)。
測定: run_confirm3.py → results_confirm3.json。**5/5 合格。**
fork 175(A_WITNESS_MUST_HAVE_BEEN_INVOKED)追加、全 fork **88/88**。
扉 **126**(+review_candidates / +rebake_inference)。
全段の再実行: 7/7・5/5・5/5・3/3(**20/20**)。

## ⑤ 実行のふりと実走(V14/V15)

**呼ばれた道具か、字の中の語か。** コマンドを区切りで割り、区画の
先頭語(+閉じた包み表 npx/uv/poetry/npm/… と `-m <module>` の一段)を
INVOKED とし、それ以外は MENTIONED。audit が数えるのは INVOKED のみ。

| 証人 | 型 | audit |
|---|---|---|
| `echo pytest` | MENTIONED | REQUIRED_UNWITNESSED |
| `echo 'run pytest later' > notes.txt` | MENTIONED | REQUIRED_UNWITNESSED |
| `pytest -q` / `python3 -m pytest -q` / `uv run pytest` / `cd /tmp && python3.11 -m pytest tests/` | INVOKED | 通る |
| `npx eslint src/ --fix`(en の約束) | INVOKED | 通る |

MENTIONED は捨てずに行へ載せる(黙って数えないが、黙って消しもしない)。
停止条件(素の `pytest` や `./scripts/test.sh` を取りこぼす)は踏まず。

**終了状態は三値**(不在と否定を混ぜない):
ok=True→REQUIRED_WITNESSED / ok=False→**REQUIRED_FAILED**(やって落ちた
は、やっていないとは別の知らせ)/ 記録なし→**REQUIRED_WITNESSED_
UNVERIFIED**(黙って合格に格上げしない)。台帳の優先順は
FAILED > UNWITNESSED > UNVERIFIED > WITNESSED で、行は常に全部返す。

### fork が捕まえた法の誤り(記録)

最初の順位は「落ちた < 不明 < 通った」で、**1回不明・1回成功**の
ターンを UNVERIFIED と呼んでいた。fork 174 が落として気づいた:
それは情報の不在を否定として数えることだった。順位を
**落ちた < 確かめた成功 < 不明** に直した — 上書きするのは落ちた回
だけで、それは実際の否定の証拠だから。この変更で以前の測定3本
(fork 174・V6・V13)を新法へ張り替え(終了状態を伴わない実行は
UNVERIFIED)、全て再実行して緑。

## ⑥ 昇格は推薦であって採用ではない(V16)

自動採用はしない — 候補を勝手に執行へ入れるのは「過検出の番人は
切られる」の罠そのもの。機械は**推薦と棄権**だけを返し、adopt(門)は
別の行為のまま。基準は測る前に固定(min_checks=8、max_fire_rate=0.5):

| 候補 | 実測 | 判定 |
|---|---|---|
| `!` 禁止 | 10回中1発火(0.1) | **PROMOTABLE** |
| `ました` 禁止 | 10回中7発火(0.7) | REFUSED_OVERFIRING |
| 出現しない語 | 10回中0発火 | REFUSED_NEVER_FIRED |
| 後から提案 | 3回 | UNKNOWN_TOO_FEW_CHECKS(**率を出さない**) |

推薦後も全候補の status は candidate のまま(実測)。

**治具の誤りを1つ踏んだ**: 過検出役に「の」を選んだが本文に一度も
現れず NEVER_FIRED になった。過検出は**本文に実際に現れる語**でしか
起きない — 測って気づいた(治具は測るものと同じ経路で作る、の再来)。

## ⑦ 焼き込みの陳腐化と焼き直し(V17)

線: **check の速い道(0.04s)では絶対に店を読まない**。

- 焼き込み時に店ファイルの指紋(名・mtime・size)を残す
- `guard stale` は **stat だけ**で答える — 実測 **0.00001s**(基準100ms)。
  店は読まない。答えるのは「焼き直せる」まで(ファイルが変わったのは
  事実、姉妹語が変わったかは推測)
- `guard rebake` のときだけ店を1回読む。実測: 店に科料の条文を足す →
  FRESH → STALE → 焼き直しで `[罰金]` → `[科料, 罰金]`。
  **dry_run は保存しない**(実測で焼き込みが変わらないことを確認)
- 落ちた語は落とす — 推論は利用者の言葉ではなく店の示唆で、店がもう
  示さない語を持ち続けるのは本文が許す以上を主張すること
- 一度も焼いていない約束は焼き直さない(利用者が推論を選ばなかった
  ものを、こちらの都合で足さない)
- フックは STALE を**報せるだけ**(焼き直しは執行を変える行為なので
  フックからは決してやらない)

## V18 順序不変

証人の記録順(3!)×約束の登録順(3!)=36通りで、audit の verdict と
行(covenant/requires/state/match)が全一致。混在ターン
(通った・不明・落ちた)でも同一。

## 凍結バイナリ端到端

`echo pytest`→UNWITNESSED(MENTIONED)/ `python3 -m pytest -q` ok=true
→WITNESSED / `pytest tests/` ok=false→FAILED / promote→ANSWER /
店の無い台帳の stale→UNKNOWN_NO_STORE(型つきの拒否)。

## 残る限界(正直に)

- **日本語の一般語の required は執行できない**。「必ずテストを実行して」
  は requires=[テスト] になるが、テストという名の道具は無い(pytest が
  走っても一致しない)。道具名を含む指示(「必ずpytestを実行して」)は
  通る。店の姉妹語で テスト↔pytest を橋渡しする案はあるが、過剰主張の
  危険があるので事前登録してから
- シェルの完全な解釈はしない。`eval`、シェル関数、`make test` の
  中身は INVOKED に見えない(見逃す側ではなく「まだ確かめられて
  いない」側に倒れる)
- 終了状態はフックが渡せるときだけ。Claude Code の tool_response が
  終了コードを持たない形の場合は UNVERIFIED のまま(推測しない)
- 昇格の帯(8回・50%)は**設計の選択**で、実運用の標本から較正した
  数字ではない。標本が溜まったら較正し直す対象
