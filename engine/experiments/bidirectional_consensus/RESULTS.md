# 実測結果: 双方向の重ね(向き不変の門)

日付: 2026-08-19 / PREREG.md の判定基準どおり / results_bidir.json が生データ
発案は操作者:「逆からやったものを重ねて、まとめて投入することで相殺する」

vera.db ja、300探針(retrieval_reach と同一ハーネス):

|          | 正答 | 誤答 | 棄権 |
|----------|------|------|------|
| 順方向   | 5    | 206  | 89   |
| 逆方向   | **158** | **0** | 142 |
| 重ね(門) | 5    | **26** | 269  |

判定: layered 採用(誤答206→26、正答無傷)。

## 発見(事前の予想を超えた分)
1. **逆方向は答えた158問で誤答ゼロ**(被覆最大帯が一意の時のみ回答、
   帯の中央値1)。順方向とは誤りの出方が完全に別種 — 順方向は名前一致に
   騙され、逆方向は被覆で騙されない(この探針の類では)。
2. 名前の被覆を数え忘れると門が正当な当選を全滅させる — core は自分の
   名前を facet に持たないので、「正当防衛とは」の帯に core 正当防衛が
   構造的に入れない(実測で発見→修理: 名前∪facet で覆いを数える)。
3. 残る誤答26は「順方向の誤答 core がたまたま巨大な同点帯(最大181)に
   入る」形 — 帯の大きさで締める余地があるが、事前登録外につき今回は
   触らない。

## 配線
- consensus_store.direction_band / _apply_direction_invariance
- ja_consensus_ask: placement_invariant(=engine の observe)の傘の下で適用
  — 単一ソブリン(同じ門を全扉で)
- consensus_over_store: direction_invariant パラメータ(EN 側の入口)
- fork 155本目 DIRECTION_INVARIANCE(降格・生存・名前被覆の3点固定)

既知正答のスモーク: 正当防衛とは/時効とは/傷害罪とは → ANSWER のまま、
direction_invariant: True の証明書つき。過失 故意 の AMBIGUOUS は本変更
以前からで無関係(コミット境界で確認)。forks 155/155。

## 逆方向の昇格は保留(正直に)
逆方向単独 158/0 はこの探針(問い=core の facet 3語)に有利な形。自然文の
問いでの単独精度は未測定なので、回答チャネルへの昇格は別の事前登録で。
今回は門(相殺)だけを本体に入れた。

## 追補: REVERSE_UNIQUE 昇格(PREREG_PROMOTION/2、2026-08-19)

3族探針(results_promotion.json):
  (a) 裸3語:      REVERSE_UNIQUE 163正答/誤答0(沈黙137)
  (b) 自然文包装: 初回は誤答23/97で**棄却** — 原因は枠語(〜に関係する)の
      qset混入。枠剥がし(閉パターン、パターン外出現は残す)を事前登録2で
      変分 → **163/0、裸3語と完全一致**
  (c) 名前形100本: 順方向ANSWER 100/100不変

発火規則(AND): 順方向非ANSWER ∧ 被覆最大帯が唯一 ∧ 被覆≥2語。
verdict=REVERSE_UNIQUE(ANSWERではない、SEEDEDと同じ非昇格の型)、
覆った語を名乗る。帯が割れれば沈黙(時効/消滅時効/対立の3すくみ等 —
規則どおりの正直な棄権)。

配線: consensus_store.frame_stripped(向き門の被覆にも適用)+
ja_consensus_ask末尾の昇格、engine.askに door=reverse_coverage の座席
(censusへ落とさない — 逆方向が到達経路ごと名乗っており二重投票になる)。
エンジン端実測3/3正解。fork 156本目 REVERSE_UNIQUE(枠剥がし・発火3条件・
順方向不可侵)。forks 156/156。
