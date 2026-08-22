# どこを触ればよいか(編集の地図)

この企ては二つの実装からできていて、**間は MCP だけ**でつながっている。
片方を触るときにもう片方を読む必要はない、が設計の狙い。

```
   ide/ (Swift)                        engine/ (Python)
   ┌──────────────┐   MCP (stdio)      ┌────────────────────┐
   │ 画面・操作   │ ─────────────────▶ │ 130 の扉           │
   │              │   扉を名前で呼ぶ    │ mcp_server.py      │
   └──────────────┘ ◀───────────────── │  ↓                 │
        JSON を描くだけ                 │ 判定・台帳・店     │
                                        └────────────────────┘
```

## やりたいこと → 触る場所

| やりたいこと | 触る場所 | 触らなくてよい場所 |
|---|---|---|
| 画面の見た目・操作を変える | `ide/VerantyxIDE/Sources/Verantyx/Views/` | engine 全部 |
| 画面に新しい情報を出す | まず `capability_index` でその扉を探す。あれば Views だけ | 扉があるなら engine |
| 扉の答えを変える・扉を足す | `engine/verantyx/mcp_server.py` | ide 全部 |
| 判定の中身を変える | `engine/verantyx/` の該当モジュール | `mcp_server.py`(扉は薄い) |
| 番人(フック)の挙動 | `engine/verantyx/covenant.py` と `engine/tools/guard/` | ide |
| CLI の入口 | `engine/verantyx/cli.py` | ide |
| 測定を足す | `engine/experiments/*/PREREG*.md` を**先に**書く | — |

## 守る線(破ると測定が落ちる)

* **測る前に事前登録**。数値は実行結果のみ、予想は書かない
* **同点は棄権**。決定的な同点崩しは信号を壊す(73.3% → 23.7% の実測)
* **不在と否定を混ぜない**。`UNKNOWN_*` を型で返す
* **削除しない**。退役は追記、間引きは書庫へ移動
* **配置は情報を増やせない**。配置を変えると消える答えは偽物
* 凍結は必ず `rm -f dist/vera-memory && pyinstaller --noconfirm --clean`
  (中身が古いまま「Build complete」と出る罠を実測済み)

## 変更したあと

```bash
python3.11 engine/experiments/guard/verify_all.py   # fork 89 + 測定 50、45秒
python3.11 -m verantyx.cli doctor                    # 保証と配線をこの機械で実演
```

IDE を変えたときは、エンジンを凍結し直してから Xcode でビルドする
(`ide/VerantyxIDE/Vendor/vera-memory` が app に埋め込まれる)。
