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
