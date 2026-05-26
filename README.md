<div align="center">
  <h1>🛡️ Verantyx IDE & Cortex Engine</h1>
  <p><b>The Zero-Leakage, Neuro-Symbolic AI Coding Gateway & Native macOS IDE</b></p>

  <p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Version 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README-en.md">English</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">简体中文</a> · <a href="README-zh-TW.md">繁體中文</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">日本語</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

## 📖 Verantyx について

このプロジェクトは以前ルールベースのシンボリックAIを作成しようとしていた際に個人では作るのは不可能であると思い、現在主流のAIのハーネスの部分など制御する部分を自作することで制御しようと考えました。（当時はopenclawが注目を集めていた時期）
そこからこのプロジェクトの主目的である、クラウドの高性能なAIに渡す前にソースコードやユーザーのリクエストを難読化してパズルのような状態にして渡すことで情報漏洩を防げるのではないかと思い開発を始めました。

このプロジェクトがスター0な理由について、このプロジェクトでセキュアなフォルダが含まれていたため急遽プライベートリポジトリにしたため、9あったスターが消滅しました。完全に復活しましたのでよろしくお願いします。そのほかのリポジトリと重複を起こしているような部分を整理しました。このリポジトリにおいてリリースを中心にプッシュしていましたが、ソースコードの更新が滞っていたのを見つけて更新しました。

これからは母国語である日本語を主力にして、英語は通常の翻訳ツールに翻訳させて一応載せるという運用で行こうと考えています。

## 🔐 難読化と6軸（Axis）の立体十字構造体

このプロジェクトの難読化において、考え方は以前データの渡し方のイメージとして初期に作ったverantyxの前身であるaxisなどで見つけた立体十字構造体を主としたデータ管理手法を採用しています。

### 🧩 6つの次元（Axis）の定義

| 軸 | 名称 | 役割 / 抽出される要素 |
| :--- | :--- | :--- |
| **X軸** | **Control Flow（制御フロー）** | 時間と順序の軸。`if`分岐、`for`ループ、例外処理など。 |
| **Y軸** | **Data Flow（データフロー）** | 依存関係の軸。変数の代入、引数の受け渡しなど。 |
| **Z軸** | **Type Constraints（型制約）** | 境界の軸。クラス定義、型アノテーション、ジェネリクスなど。 |
| **W軸** | **Memory Lifecycle（メモリライフサイクル）** | 寿命の軸。スコープの生存期間、メモリの確保・解放。 |
| **V軸** | **Scope Hierarchy（スコープ階層）** | 包含の軸。モジュール、クラスのネスト構造。 |
| **U軸** | **Semantics & Meaning（意味・意図）** | **★最重要★ 業務の意図の軸。具体的な変数名、関数名、生の文字列、数値。** |

この変換プロセスは、Verantyx の **Gatekeeper（ゲートキーパー）エンジン** によってローカル環境のMacBook上で瞬時に実行されます。

---

### 🔄 生コードから Opaque Topology への変換メカニズム

#### Step 1: AST（抽象構文木）へのパースと分解
まず、Gatekeeper エンジン（ルールベース推奨）が対象のソースコードを構文解析し、プログラムの構造を **AST（Abstract Syntax Tree）** という木構造のデータに変換します。
この時点では、まだ「どの関数が何を呼び出しているか」「変数名は何で、文字列として何が定義されているか」といった情報がすべて含まれています。

#### Step 2: セマンティクス（U軸）の「物理的剥離と隔離」
ここからが Verantyx の真骨頂です。AST の中から、**業務の意味（意図）を示す情報＝U軸** をすべて物理的に剥ぎ取ります。

*   **剥ぎ取られるもの（U軸）**: 変数名、関数名、文字列、固定の数値など。
*   **残されるもの（X,Y,Z,W,V軸）**: 「変数を代入した」「関数を呼び出した」「if文で分岐した」「for文でループした」という論理的な骨組み。

剥ぎ取られた具体的な名前や文字列のデータは、あなたのMacのローカルにある **`JCrossIRVault`（金庫）** に厳重に保管され、決して外部には送信されません。

#### Step 3: Opaque Node（不透明ノード）への完全暗号化
意味を剥ぎ取られた残りの「骨組み」を、クラウドLLMへ送るために完全に不透明な表現に変換します。

*   **`NODE[0x...]`（ノードID）**: すべての変数や構文要素はランダムなメモリアドレスのような識別子に置き換えられます。
*   **`ARITY`（アリティ/項数）**:
    *   `class.nullary`: 引数や中身を持たない要素（単なる値や終端ノード）。
    *   `class.standard`: 標準的な単項・二項演算（A + B や 代入など）。
    *   `class.multiway`: 複数の要素を持つ複雑な構造（forループ、if-else分岐、関数定義など）。
*   **`HASH`（構造ハッシュ）**: そのノードがグラフのどの位置にあり、周囲とどう繋がっているかを示すチェックサム。これにより、LLMがパズルを解いて返してきたときに、構造が壊れていないかをローカルで検証できます。

元のコードの文すら消滅し、「`class.multiway` なノードが子ノードを反復処理している」という純粋な数学的グラフになります。

#### Step 4: 統計的推測を防ぐ「デコイ（おとり）」の注入
コードをグラフ構造にして外部に送った場合、高度なAIや悪意のある攻撃者が「このグラフの形は、よくあるスクリプトの形だ」と統計的に推測（リバースエンジニアリング）してくるリスクがあります。

これを防ぐため、グラフの隙間に **偽のノード（デコイ）** をランダムに注入します。
```text
// _TOKEN_匶:0.2___jcross_BM_505__ [decoy-metadata]
```
この無意味な漢字のトークンやダミーのつながりを混ぜ込むことで、グラフの形そのものを歪ませ、外部のAIが元のソースコードの正体を推測することを数学的に不可能にしています。

---

### 🧩 LLMはどうやってこれを「修正」するのか？（復元プロセス）

1. **パズルとして解く**:
   LLM は元のコードを知らなくても、指示された文脈とグラフの形（ARITY と HASH の繋がり）からターゲットとなる変更箇所の値のはずだと推論します。
2. **構造パッチの返送**:
   LLM は内容を書き換える JSON形式の構造パッチ（GraphPatch）だけを返します。
3. **ローカルでの再結合（Reverse Transpilation）**:
   Macの Gatekeeper エンジンがそのパッチを受け取り、先ほど `JCrossIRVault` に隠しておいた本当の変数名や文字列（U軸）をパッチにガチャンと再注入します。

結果として、**「外部のAIは元のコードを1行も見ていないし理解もしていないのに、ローカルに戻ってくると正しくコードが書き換わっている」** という魔法のようで情報漏洩がないという開発体験が成立します。※まだ私が見落としている情報の漏洩があるかもしれないため気づいたらissueなどでお知らせください。

---

## ⚠️ 現在対応できない（苦手な）タスク

現在この構造において対応できないタスクについて、代表的な一番苦手なタスクは **SwiftからRust言語への書き換え** などのタスクには対応できていません。また下記のような１から４までが苦手なタスクです。

### 1. 「意味（ドメイン知識）」に依存するリファクタリングやバグ修正
外部のLLMには `NODE[0x...]` という骨組みしか見えていないため、**「コードの意味を理解しないと解けない問題」** には対処できません。
*   **❌ 苦手な指示の例**: 「認証（Authentication）に関係する変数の名前にすべて `auth_` というプレフィックスをつけて」
*   **理由**: LLMには「どれが認証の処理か」が全く見えません。

### 2. 外部ライブラリ（API）に強く依存した新規機能の追加
ソースコード内の `import` 文やライブラリ呼び出しもすべて `NODE` として暗号化されているため、特定のライブラリの知識が必要なタスクが困難になります。
*   **❌ 苦手な指示の例**: 「AWS S3 にファイルをアップロードする機能を追加して」
*   **理由**: LLMは、現在のコードがどの外部ライブラリを使用しているかを知りません。

### 3. 「ゼロから全く新しい機能全体」を書き起こすこと
Gatekeeperは「既存の構造（AST）をパッチ・修正する」ことには極めて強力ですが、「何もない白紙の状態から、意味（U軸）と構造の両方を持った巨大な新機能を作り出す」ことは苦手です。

### 4. LLM自体の「事前学習知識」の無力化による推論低下
GemmaやClaudeなどのLLMは世界中のソースコードを学習して賢くなっていますが、Verantyxが送る形式は**「この世のどの言語でもない、純粋な記号とハッシュのグラフ」**です。
*   **理由**: LLMが得意とする「コードの文脈からのパターン認識」を封じているため、見たことのない難解な数学のグラフパズルになってしまい、計算コストの増大を引き起こしています。

### 💡 どのように克服しているか？（今後の展望）
現在、これらの弱点を克服するために Verantyx 側で実装されているのが、**「Tri-Layer JCross Memory（3層メモリ）」** と **「Visual Anchors（視覚的アンカー）」** の組み合わせです。機密情報を含まない安全なメタデータだけを視覚的アンカーとしてLLMに部分的に提示し、セキュリティを保ったままヒントを与えるアプローチを取っています。

---

## 📽️ デモ動画とコード変換の実際

<p align="center">
  <img src="demo.gif" alt="Verantyx Gatekeeper Demo" width="49%" style="border-radius: 8px;">
  <video src="https://github.com/verantyx/verantyx/releases/download/v1.2.5/demo_skill_generation.mov" controls="controls" muted="muted" width="49%" style="border-radius: 8px;"></video>
</p>

### Before & After: 難読化の実際

**[Before] Raw Source Code (Local Environment)**
```python
import json
import os
import shutil
import requests
import subprocess
import re
from tqdm import tqdm
import sys

# Import our new parser
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from verantyx.cross_engine.jcross_extraction_parser import JCrossExtractionParser

ORACLE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v7"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/release/examples/query_jcross"
MODEL = "gemma4:e2b"
OLLAMA_URL = "http://localhost:11434/api/generate"

FINAL_REPORT = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/official_v7_1_accuracy_report.json"
```

**[After] Gatekeeper JCross Opaque Topology (Sent to Cloud LLM)**
```lisp
;;; 🛡️ GATEKEEPER MODE — JCross IR View
;;; Real identifiers have been replaced with node IDs.
;;; Schema: D59144D1-BE1
;;; Nodes: 124 | Secrets redacted: 3442
;;; Source: cortex/bench_v7_1_puzzle_runner.py
;;; 
// JCROSS_6AXIS_BEGIN
// lang:swift doc:0xD5E025

// ── TOP-LEVEL NODES
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xb4af0a52 ARITY:class.multiway
  NODE[0x9DB8] kind:opaque TYPE:opaque MEM:opaque HASH:0x504933fd ARITY:class.standard
  NODE[0x627F] kind:opaque TYPE:opaque MEM:opaque HASH:0x97b540cb ARITY:class.multiway
  NODE[0x7F4C] kind:opaque TYPE:opaque MEM:opaque HASH:0x86742e8c ARITY:class.standard
  NODE[0xC79E] kind:opaque TYPE:opaque MEM:opaque HASH:0xd42206c4 ARITY:class.standard
  NODE[0x510B] kind:opaque TYPE:opaque MEM:opaque HASH:0x14b9be4e ARITY:class.nullary
  NODE[0xB5C0] kind:opaque TYPE:opaque MEM:opaque HASH:0xcacb18a2 ARITY:class.standard
// _TOKEN_匶:0.2___jcross_BM_505__ [decoy-metadata]
  NODE[0xE3CF] kind:opaque TYPE:opaque MEM:opaque HASH:0x375a5480
```

---

## 💻 インストール方法 (ソースからのビルド)

**必須要件:**
- macOS 14.0以降 (Apple Siliconを強く推奨)
- Xcode 15.0以降

```bash
git clone https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
open Verantyx.xcodeproj
# Verantyxのスキームを選択し、Cmd+Rを押してビルド・実行します
```

*注意: Windows / Linuxへの移植（Rustコア + llama.cpp）は長期的なロードマップにありますが、現在はネイティブなmacOS / MLXアーキテクチャの完成に極度に注力しています。*

---

## 🔧 リポジトリの設定と履歴について

**Git設定に関するお知らせ:**
このリポジトリの初期のコミットは、開発者のmacOSのユーザー名に由来する `kofdai` というローカルのGit名で行われていました。2026年5月24日をもってこの問題は修正され、現在すべてのコミットは正しく `@Ag3497120` に帰属するように設定されています。これは開発環境のセットアップにおける一般的な問題であり、ボットや自動化ツールによるものではありません。今後のすべての貢献は正しい作者名で記録されます。

---

## 💡 Q&Aとアピール (Experimental Features)

現在、`Control` キーを3回押すことで **Verantyx Agent** を起動することができます。

<p align="center">
  <img src="assets/verantyx_agent_v2.png" alt="Verantyx Agent Interface" width="600" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
</p>

このモードは以前のアプリケーションにあったさまざまなIDEモードの実験場として作成されたものです。プロジェクト全体を見直し、本当に求められている「ゲートキーパーモード」に集中するために、これまで作り上げたエージェント動作の実験的な機能群をこの **Verantyx Agent** に集約しました。

これまでのリリースに含まれるエージェントの主な機能は以下の通りです：

*   **Dual Twin監査システム**: AIがツールを呼び出して怠慢になる問題を防ぐため、内部でJCrossを注入し、TwinAのツール呼び出しの妥当性をTwinBが監査する仕組みを導入しました。
*   **Visual Anchorの導入**: スキルや指示をプロンプトのみで制御していたものを、Visual Anchorによる画像注入とプロンプトのハイブリッド方式に変更しました。
*   **L3.5 OS Asset Mapの構築**: Control×3で起動するエージェントにおいて、「L3.5」というパソコン内部の地図をローカルのみで保持。エージェントに対し、パソコン内の資産が自分自身の知能と繋がっているという意識を植え付けました。
*   **AX APIを用いた高精度GUI操作**: 既存のスクリーンレコーディングによるGUI操作から、OSのAPIツリー（アクセシビリティAPI）を用いた確実かつ高精度な操作へ移行しました。
*   **漢字トポロジー圧縮**: L3.5地図をコンテキストに注入する際、画像を生成してプロンプトとして利用することでコンテキストの肥大化を防止。「漢字トポロジー」という独自の圧縮形式と実データを対応付け、適宜必要なデータのみが注入されるようにしました。
*   **エージェントモードの拡張**: 「自動モード」と「詳細モード」の2種類を追加しました。
*   **内部知識優先モード**: 制限解除モデルなどを使用するパワーユーザー向けに、ローカルAIを単なるオーケストレーターとしてではなく、メインの思考モデル・知識源としてフル活用するためのモードを実装しました。
*   **L3.5専用の記憶ライン整備**: L3.5地図の記憶が複雑かつ多量になるのを防ぐため、通常の会話記憶とは完全に別の記憶ラインを整備しました。
*   **ファインチューニングへの応用**: L1からL3.5までの記憶からユーザーのアイデンティティとなるデータを抽出し、任意のモデルに対してファインチューニングを実施できる足がかりとなる機能を実装しました（記憶システム単体では不可能な最適化を実現）。
*   **FARゾーン構造の採用**: 「記憶を削除せず整理する」という理念に基づき、タスク完了時にタスクのパッケージやタイトルなどの遷移プロセスを記録し、「FARゾーン」と呼ばれる新たな階層に落とし込む構造を採用しました。これにより、タスク終了後も作業プロセスなどの重要な記憶は保持されます。

これらは現在追加されている機能のごく一部です。
最近のアップデートでは、HuggingFaceに投稿した `talkie-1930:13b` の部分量子化バージョンを使ったオーケストレーション（Blind Commander Architecture）を導入しました。「1930年の知識しか持たない」という制限を逆手にとり、コマンドの実行にはルールベースの仲介者を挟み、ユーザーのメッセージを当時の比喩表現に直す役割を持たせています。この「実験的である」というプロジェクトの理念を体現するような機能の追加が行われています。

### 🔄 今後のロードマップと特大の試練

このエージェントとゲートキーパーモードは現在同じ記憶領域で繋がっていますが、将来的にはこれを分離・細かな調整ができるようにする機能を実装予定です。

現在、このエージェント開発は一時的な到達点に達しています。私自身が学生ということもあり、Teams等で出された課題（「最近出された〇〇の課題について作成して提出して」といったタスク）をこのエージェントが完全にこなせるようになった暁には、現在改善案を練っている「ゲートキーパーモード」の本格的な開発に着手したいと考えています。スターをつけてくださった皆様、ありがとうございます。もうしばらくお待ちください。

最後に、このプロジェクトの集大成として用意している特大の試練についてお話しします。

1. **Windows版への移植（Rustベース）**: 現在macOS向けにSwift言語で書かれている実装をRustベースに書き直し、同様のゲートキーパー機能をWindowsユーザーの皆様にも体験していただくためのタスクです。
2. **クラウド依存からの完全脱却**: 高額なAPI料金を払うことなく、ローカルのLLMのみで自律的に開発を続けられるエージェントへと成長させることです。MacBookで動く20Bクラスのモデル（最近の `qwen3.6:27b` など、特定条件下で最高峰モデルに匹敵すると言われるもの）を活用し、クラウドレベルに近いコーディングエージェントを稼働させ、自律的に改善を重ねてプロジェクトを進めていきたいと考えています。
