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
