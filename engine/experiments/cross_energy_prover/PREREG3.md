# 事前登録3: 同時抽象(極小異質項の一括変数化)+ 目標台帳のバッテリー

日付: 2026-08-20。**この文書を書き終えてから run_confirm3.py を走らせる。**

## 変更1(抽象化 — 追加のみ、既存の生成は不変)

_abstract に決定論の変分を2つ**追加**する:
  (a) 極小異質項(自分の真部分項に異質項を含まない異質項)を全て同時に
      変数化した1本
  (b) 極大異質項(他の異質項に含まれない異質項)を全て同時に変数化した1本

診断(確認2): 一般結合律 app(app(?x,?y),?z)→app(?x,app(?y,?z)) は3箇所の
同時抽象が要るが、従来のマスク列挙は先頭3異質項に限られ、走査順で
cons(h0,nil) が届かなかった。(a) がこれを構造的に生成する。

## 変更2(配線 — 器官への永続、票なし)

verantyx/proof_ledger.py(新規ネイティブモジュール、MCP 不経由):
証明済み補題(lean 証人つき)・試行台帳(プロセス跨ぎの failed_before)・
未証明目標(gap_graph.GapNode、failure_type と needs つき)。
エネルギーへの影響は failed_before の減点のみ(実測済みの形)。

## 確認測定3

C1..C4 + R1..R8(確認2と同一)に加え、**目標台帳バッテリー B1..B12**
(この文書で固定、開発に未使用):

    B1  len(app(x, y)) = len(app(y, x))
    B2  rev(app(x, y)) = app(rev(y), rev(x))     (= C1)
    B3  len(rev(x)) = len(x)                      (= C2)
    B4  app(rev(x), nil) = rev(x)
    B5  rev(app(rev(x), nil)) = x
    B6  len(app(x, cons(a, nil))) = s(len(x))
    B7  mul(a, s(0)) = a
    B8  mul(s(0), a) = a
    B9  mul(add(a, b), c) = add(mul(a, c), mul(b, c))
    B10 len(app(app(x, y), z)) = add(add(len(x), len(y)), len(z))
    B11 rev(cons(a, nil)) = cons(a, nil)
    B12 mul(a, mul(b, c)) = mul(mul(a, b), c)

## 採択基準

- S1 健全性: 証明したと主張した全目標が Lean VERIFIED・不健全0
- S2: C1 が自動発明の補題 ≥1 本で証明される(前2回の未達がこれで閉じる)
- S3: 確認2で通った11本に退行なし
- S4: 台帳: バッテリー後に proof_ledger.json / gaps に、証明済み補題
  (lean 証人つき)と未証明目標(failure_type つき)が実在する — cat で
  検査できること
- バッテリーの証明数そのものは採否に使わない(在庫の実測が目的)。
  未証明は gap 台帳に failure_type つきで刻まれることが成果

## 停止条件

S1 違反 → 器の欠陥、棚上げして記録。S2 未達 → 同時抽象でも届かない
ことの記録を残し、C1 は OPEN のまま台帳に置く(それ自体が正しい動作)。
