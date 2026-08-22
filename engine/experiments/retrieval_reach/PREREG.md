# 事前登録: 候補到達の補完(facet重なりの追記)

日付: 2026-08-19 / 実測前に登録

## 背景(実測済み)
中頻度facet 3語の問い300本で reachable 27/300 — 正解核が候補6件に
入らない。candidates_for_query の facet 重なり補完は「直接ヒット0の
場合のみ」動く(tokyo vs film: 質量の大きい core が本命を押し出した教訓)。
facet語自体が別 core 名に当たると seen が埋まり、補完が封じられる。

## 仮説
重なり補完を「直接ヒットの後ろに追記」(pri 9、直接候補は不動、残枠のみ)
すれば、到達は上がり、直接候補の順位は変わらないので押し出しは起きない。
ただし腕が増えると割れて AMBIGUOUS が増える教訓(120問実測)があるため、
到達だけでなく回答の質も測る。

## 方法
run_recheck_real.py と同一ハーネス(300探針・seed同じ・読み取り専用)。
基準: 現行 candidates_for_query。変分: 補完を if qset: で常時追記。
測るもの: n_reachable / simulated 腕の correct・wrong・refusal。

## 判定(事前)
採用条件: reachable が増え、かつ wrong が増えず、correct が減らない。
refusal の増加は許容(棄権は誤答ではない)が、correct 減と交換なら棄却。
