<div align="center">
  <h1>🛡️ Verantyx (Verifiable & Auditable AI Engine)</h1>
  <p><b>The Zero-Leakage, Neuro-Symbolic AI Coding Gateway & Native macOS IDE</b></p>

  <p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Version 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square"></a>
  </p>
  <p>
    <a href="README-en.md">English</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">简体中文</a> · <a href="README-zh-TW.md">繁體中文</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">日本語</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

## これは何?

Verantyxは、ローカルファーストでmacOSネイティブなコーディングエージェントです。LLMによる生成と、不一致を検知する構造推論エンジン(JCross)を組み合わせています。ソースコードを意味を持たない数学的パズルに難読化してからクラウドLLMに渡すので、実際のコードを漏らさずにフロンティアモデルの力を借りられます。

## 30秒でわかる動作例

```text
$ verantyx gatekeeper ./my_secret_repo
→ ソースコードが不透明トポロジーのパズルに変換される
→ (実コードではなく)パズルがクラウドLLMに送信される
→ LLMの提案が復元され、diffとして表示される
→ ディスクに反映される前に、承認/却下を選べる
```

## 現時点で実際に動く機能

- **Gatekeeperモード**: 難読化 → クラウドLLM → 復元 → diffレビュー、が一気通貫で動作。
- **Agentモード**: ローカルモデル(Ollama/MLX)による自律ループ、3回キー押下での起動、ツール呼び出し、ファイルの読み書き・パッチ適用。
- **Vera-α記憶ブリッジ**: LLM自身の作業記憶とは別に、ハルシネーションしない検証済みの事実ストアを併用。
- **立体十字構造体3Dグラフ**: 記憶に実際に何が蓄積されているかをSceneKitでライブ可視化。

まだ粗い/開発中の部分: Windows/Linux移植、VR Bridgeの完全没入対応 — 詳細は下部の[Verantyxについて](#-verantyx-について)を参照。

## 今いちばん助けてほしいこと

**上の30秒デモを、まっさらなmacOSマシンで実際に試して、動いたかどうか教えてください。** それだけで十分です — コードレビューでも共同開発の約束でもありません。時間の目安ごとの参加方法は下記にまとめています。

---

## 🙋 協力方法(時間の目安ごと)

### 10分でできること
- このREADMEを読んで、「これは何のプロダクトに見えるか」を一文で教えてください。
- インストール手順で分かりにくかった点を報告してください。
- クローンしてXcodeで開き、あなたの環境(macOSバージョン、Apple SiliconかIntelか)でビルドできるか教えてください。

### 30分でできること
- 上のGatekeeperモードの例を、自分の小さなリポジトリで1つ試してみてください。
- Agentモードの3回キー押下を試して、何が起きたか教えてください。
- 既知のバグが1つあるファイルを渡して、正しい原因箇所を特定できるか試してください。

### 技術的貢献
- `good first issue` / `help wanted`ラベルの付いたIssueで、対象ファイル・完了条件・確認用コマンドが書かれているものを探してください。
- まだラベル付きのものがなければ、やりたいことをIssueに書いてください。1ファイル・1条件くらいの粒度に切り分けます。

もしこのリポジトリにスターを付けてくださっていて5分だけ時間があれば、「このプロジェクトが何に見えたか」を一文返信いただくだけでも、スターそのものより価値があります。

---

Verantyxは、AIによるソフトウェア開発を完全に制御可能で安全なものにするための、次世代のNeuro-Symbolicロジックエンジンです。
私たちは、1つの強力なコアエンジン（JCross/L3.5 Memory）の上に、**2つの異なるフロントエンド**を提供しています。あなたの目的に合わせて選択してください。

---

## 1. 🖥️ Verantyx Gatekeeper (IDE Mode)
**「会社の機密コードを、安全にクラウドLLMに読ませたい」**

Gatekeeperモードは、あなたのソースコードを意味を持たない数学的パズル（Opaque Topology）に難読化してからAIに渡す、究極のセキュアIDEです。
👉 [Gatekeeperモードの詳細と難読化の仕組み（README-Gatekeeper.md）はこちら](./docs/README-Gatekeeper.md)

## 2. ⚡ Verantyx Agent (Spotlight Mode)
**「最強のローカルAIを、脳の拡張として完全に使いこなしたい」**

`Control`キーを3回押すだけで起動する、超自律型のエージェントです。Dual Twinによる内部監査、1930年メタファによるハルシネーションの物理遮断、そしてPCの資産を「自分の記憶（L3.5）」として認識する次世代の思考エンジンを搭載しています。
👉 [Agentモードの詳細とアーキテクチャ（README-Agent.md）はこちら](./docs/README-Agent.md)

## 3. 🥽 Verantyx VR Bridge (PCVR Streaming)
**「MacでHalf-Life: Alyxを動かし、Vision Proで遊ぶ」**

Verantyxの新たなサブプロジェクトとして、MacのD3DMetal(GPTK)上で動くSteamVRゲームを直接Apple Vision Proへストリーミングする超低遅延VRブリッジ機能が追加されました。
- **Mac側 (HardwareEncoder)**: 独自のOpenVRエミュレータ（`openvr_emulator.cpp`）がゲームエンジン(Source 2)からDirectX 11のテクスチャを横取りし、macOSのVideoToolboxを用いてHEVC (H.265) ハードウェアエンコードを実行。UDPでVision Proへ直接送信します。
- **入力マッピング**: Joy-Conなどのゲームパッド入力をPythonスクリプト(`joycon_mapper.py`)で仮想VRコントローラーに変換し、ゲームにフィードバックします。
👉 現在、Vision Pro上で平面への描画（2Dウィンドウ）まで成功しており、今後はCompositorServices (Metal) を用いた完全なフルイマーシブVR対応を目指しています。

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

## 📖 Verantyx について

このプロジェクトは以前ルールベースのシンボリックAIを作成しようとしていた際に個人では作るのは不可能であると思い、現在主流のAIのハーネスの部分など制御する部分を自作することで制御しようと考えました。（当時はopenclawが注目を集めていた時期）
そこからこのプロジェクトの主目的である、クラウドの高性能なAIに渡す前にソースコードやユーザーのリクエストを難読化してパズルのような状態にして渡すことで情報漏洩を防げるのではないかと思い開発を始めました。

このプロジェクトがスター0な理由について、このプロジェクトでセキュアなフォルダが含まれていたため急遽プライベートリポジトリにしたため、9あったスターが消滅しました。完全に復活しましたのでよろしくお願いします。そのほかのリポジトリと重複を起こしているような部分を整理しました。このリポジトリにおいてリリースを中心にプッシュしていましたが、ソースコードの更新が滞っていたのを見つけて更新しました。

これからは母国語である日本語を主力にして、英語は通常の翻訳ツールに翻訳させて一応載せるという運用で行こうと考えています。

---

## 🔧 リポジトリの設定と履歴について

**Git設定に関するお知らせ:**
このリポジトリの初期のコミットは、開発者のmacOSのユーザー名に由来する `kofdai` というローカルのGit名で行われていました。2026年5月24日をもってこの問題は修正され、現在すべてのコミットは正しく `@Ag3497120` に帰属するように設定されています。これは開発環境のセットアップにおける一般的な問題であり、ボットや自動化ツールによるものではありません。今後のすべての貢献は正しい作者名で記録されます。
