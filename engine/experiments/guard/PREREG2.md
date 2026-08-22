# 事前登録2: 番人の第二段 — 証人・隔離席・書かれていない禁止

日付: 2026-08-21。**この文書を確定してから測定する。** 前段: PREREG.md(7/7)。
承認済みの順: ④required の証人配線 → ①LLM手渡し抽出(隔離席) → ③siblings 事前展開。

## ④ required は字面でなく証人で見る

「必ずテストを実行して」は返答の字面をいくら読んでも執行できない
(実地試験: required_missing は誤検知だらけ)。attest_claim の
CLAIM_UNWITNESSED と同じ線に置く: **やったの根拠は tool 実行の記録**。

- covenants.json に witnesses(ts/turn/tool/detail)を追記保存
- `guard witness` = 記録、`guard boundary` = ターン境界、
  `guard audit` = 境界以降の証人と requires を突き合わせ
- 判定は三値: REQUIRED_WITNESSED / REQUIRED_UNWITNESSED / NO_REQUIREMENTS
- **遮断はしない**(このターンにテストが要ったかは文脈で、この層には
  見えない — 過検出の番人は切られる)。報せるだけ
- 照合は部分文字列(requires の語が tool 名 or detail に現れる)のみ。
  意味の一致は主張しない

## ① 抽出は LLM に手渡し、執行と履歴は Vera が持つ

閉じた規則の外(婉曲・言い換え)は追いかけない(極性regexの教訓:
645/661 が語彙の外)。代わりに **隔離席**: LLM が候補を propose し、
Vera は shadow で照合だけして遮断はしない。採用(adopt)して初めて
執行に入る。淘汰は門。

- Covenant に status: adopted | candidate。candidate の違反は
  shadow_violations に分離され verdict に混ざらない
- `guard propose` / `guard adopt` / (棄却は既存 retire)
- list が shadow の履歴(何回照合し何回引っかかったか)を見せる

## ③ 書かれていない禁止 — siblings を登録時に事前展開

check 時に店を読むと 0.04s が死ぬ。**登録・採用の時だけ**店を読み、
siblings を inferred_forbids として焼き込む(provenance つき)。
check は字面と同じ速さで、推論由来のヒットは inferred と型を分けて
報じる(弱い主張は弱い型で)。

## 測定(V6〜V10)

- V6 証人: requires=[pytest] + witness(pytest 実行) → WITNESSED。
  witness なし → UNWITNESSED。boundary 後の witness だけが数えられる
- V7 隔離席: candidate の違反が verdict を BROKEN にしない(shadow に
  出る)。adopt 後は同じ文で BROKEN。retire で棄却できる
- V8 拒否: 空の requires での audit は NO_REQUIREMENTS(証人ゼロを
  違反と呼ばない)。propose の壊れた JSON からは何も立てない
- V9 順序: witness の記録順・約束の登録順を入れ替えても audit/check
  の判定不変
- V10 推論: 店に姉妹語がある語を forbids で登録 → inferred_forbids に
  姉妹語が焼き込まれ、姉妹語の使用が inferred 型で報じられる。
  店に無い語 → inferred_forbids 空(推測しない)。check の実時間が
  素の字面と同桁(≤2倍)に留まる

## 停止条件

- V6 で境界外の証人が数えられる(ターンを跨いだ「やった」の混入)→
  witnesses ごと棄却
- V10 で inferred が平文誤検知を出す → 事前展開を棄却し fork 172 の
  check 時 store 渡しに戻す
