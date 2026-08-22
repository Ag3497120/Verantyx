# 実測結果: 転置索引化で入れた回帰と、fork契約の更新(2026-08-19)

fork suite が 156/158 に落ちていたので機序を分解した。2本とも**別の理由**
で、片方は私が入れた回帰、片方は改善に古い契約が追いついていない形だった。

## ① COMPOUND_SENSE_CHANNELS — 索引化で入れた回帰

二分探索: 31dca42 では ANSWER sun、2ce9d28 以降 AMBIGUOUS。

機序: 候補追記の重なり判定は元々 `qset & set(cross)` で **facet しか
見ていなかった**。全核走査を語→core の転置索引に置き換えたとき、
direction_band が要求する「名前も引ける索引」を候補追記にも共有させて
しまい、`"what is the sun"` に `sun_tzu#p` が**名前の sun** で候補入り。
腕が2本になって断面が割れ AMBIGUOUS。

「head が店に居るなら非 head の単独語は候補にしない」(120問で
73/120 vs 33/120 の実測に基づく既存規則)を、追記が裏口から破っていた。

修理: `_word_index(store, names=)` を二本立てにする。
    direction_band  names=True  (core は自分の名前を facet に持たないので、
                                 名前を数えないと帯から自身が脱落する)
    候補追記         names=False (元の semantics — facet のみ)
実測: cands ['sun','sun_tzu#p'] → ['sun']、fork 復帰。

## ② DOCUMENT_DRAFT_IS_LICENSED — 契約が改善に追いついていない

この fork の固定具は否定行「精算の対象としない」で、下書きが出ることを
**合格**として守っていた。同日入れた「否定の行は黙る」(positive 形しか
無いので反転した主張しか作れない)によって沈黙し、fork が落ちた。

つまり守っていた契約の方が誤りだった。固定具を肯定行に替え、否定行の
沈黙を**4つ目の契約**として明記(silent_on_negation)。

## 結果
    forks 158/158 all_pass
    既知正答 正当防衛/時効/傷害罪/言語とは → ANSWER 不変
    エンジン端300探針: REVERSE_UNIQUE正 191 + REVERSE_SPECIFIC正 47
                      = **238/300 正解・誤答0**・棄権62(ANSWER は 0 のまま)
