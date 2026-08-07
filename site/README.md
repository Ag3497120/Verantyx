# site/ — Verantyx 紹介サイト / project site

日本語と英語を1ファイルで切り替えます(`data-ja` / `data-en` 属性 + `<html lang>`)。
2つのファイルに分けると、片方が必ず古くなるためです。

## スクリーンショットの追加

`site/img/growth.png` を置くと、Growth セクションの差し込み口が自動で画像に
差し替わります(画像が無い間は「差し込み口」と表示され、空の枠にはなりません)。

撮り方: Verantyx.app → チャット下部の緑バッジで Vera-a モード →「成長」タブ。

## 公開

静的 HTML 1枚なので、GitHub Pages ならこのディレクトリを Pages のソースに
指定するだけです。ビルド手順はありません。

---

Bilingual in one file on purpose: two files is how one of them goes stale.
Drop `site/img/growth.png` and the slot fills itself. Static HTML, no build.

## サイト内ボット / In-page bot

`vera.js` はエンジンの判定部分をブラウザへ移植したものです。語彙・設定・
手順は `data/vera.json` に **エンジンから書き出し**ており、手で写していません。
移植の等価性は 15 件の検査で確認済み(設定検索・型付き拒否・曖昧判定・
主辞コア・複合語ガード・否定反転・矛盾検出と出典)。

再書き出し:

```
cd /path/to/Verantyx-Vera-alpha && python3 - <<'PY'
# site/data/vera.json を再生成(手順は site の commit を参照)
PY
```

`fetch` を使うため、`file://` ではなくローカルサーバで開いてください:

```
cd site && python3 -m http.server 8899
```

## 災害板 / The disaster board

`field.js` は `verantyx/field_reports.py` の移植で、カテゴリと鮮度は
`data/field.json` にエンジンから書き出しています。移植の等価性は11件で確認済み
(CONFIRMED / CONFLICT / EXPIRED / SUPERSEDED / 古い報告は投票しない /
公式は一方の側 / 必要の展開 / 不正 status の拒否)。

板の投稿データは**架空**です。公開ページに実在の場所を載せると、デモが
実データとしてスクリーンショットされて共有されるためです。

Ported from the Python engine; categories and TTLs are exported, not retyped.
Equivalence checked on 11 cases. The sample posts are fictional on purpose.
