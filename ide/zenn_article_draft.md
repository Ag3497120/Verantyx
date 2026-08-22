---
title: "AI自律エージェントのWAF回避戦略：CGEventによる生体エントロピー注入とブラウザ制御"
emoji: "🛡️"
type: "tech" # tech: 技術記事 / idea: アイデア
topics: ["AI", "macOS", "Swift", "Rust", "BotGuard"]
published: false
---

## はじめに

自律型AIエージェント（Autonomous Agent）が自律的にWebをブラウジングしてコーディングのためのリサーチを行う際、最大の壁となるのが**WAF（Web Application Firewall）やBotGuardによる遮断**です。PuppeteerやPlaywright、あるいはSeleniumのようなヘッドレスブラウザは、その自動化の性質上、Cloudflareなどの高度なBot対策システムによって即座にブロックされます。

Verantyx v0.4.0 では、この問題を解決するために、**OSレベルでのHID（Human Interface Device）エミュレーションと生体エントロピー注入**というアプローチを採用しました。本記事では、そのアーキテクチャと実装の詳細について解説します。

## アーキテクチャの概要 (v1.3.6)

Verantyx の Web グラウンディング（SearchGate）パイプラインは、これまでの Rust 製 `verantyx-browser` に依存する設計から脱却し、v1.3.6 にて完全に macOS ネイティブな **AppleScriptBridge と ReAct 型リトライシステム** へと進化しました。

1. **生体エントロピー取得層 (Swift / SwiftUI)**
   - ユーザーが「Human Verification Needed」パズルを解く際の**マウスの軌跡 (Mouse Trajectories)** と **動画フレーム (Video Frames)** を収集します。
   - 収集されたデータは `AppState.lastEntropy` として保持され、Bot 検知を回避する際の「人間の証」として活用されます。
2. **ReAct 型 SearchGate とフォールバック (Swift)**
   - Agent が Web 検索（`[SEARCH_MULTI]` 等）を要求した際、検索プロバイダー（DuckDuckGo など）のレートリミットに直面することがあります。
   - Verantyx v1.3.6 では、単純に失敗して停止するのではなく、`AgentLoop` に **ReAct (Reasoning and Acting) サイクル** を導入しました。検索が失敗した場合は、プロバイダーを切り替えるか、別のクエリで再試行する自律的なエラー復旧を行います。
3. **AppleScriptBridge を用いたブラウザ自動化 (Swift)**
   - これまで Rust の `CGEvent` に依存していたステルス制御を廃止し、より安定した macOS 標準の **AppleScript (NSAppleScript)** を直接駆動するアーキテクチャ `AppleScriptBridge` に刷新しました。
   - `WebSearchEngine` が直接 Safari や Chrome を AppleScript 経由で操作することで、バックグラウンドでのサイレントなデータ抽出 (`.fetch`) と、生体認証が必要な際の GUI 制御 (`.safari`) をシームレスに切り替えます。

## ReAct リトライと AgentLoop の安定化

従来の設計では、Web ブラウザの自動操作が何らかの理由でフリーズした際、IDE 全体の AgentLoop が停止（ストール）してしまう問題（Terminal-based auto-termination failures）がありました。

v1.3.6 では、AgentLoop のツール実行器 (`AgentToolExecutor`) に厳密なタイムアウトとエラーリカバリのサンドボックスを実装。ブラウザが応答しなくなった場合は、自動的に `.fetch` ベースの HTTP スクレイピングに切り替わるか、ユーザーに対して「Self-Fix Mode」での介入を求めるよう設計されています。また、パージングロジック (`AgentToolParser`) も改善され、LLM がインラインでツールを出力した際のパース落ちを完全に防止しました。

## 自動アップデートサイクルのシームレス化

Verantyx のような自律進化型 IDE にとって、アップデートプロセス自体も自動化されている必要があります。
これまでのバージョンでは、Sparkle などのサードパーティフレームワークがない環境下において、ダウンローダーが DMG をマウントした後にアプリのシャットダウンがブロックされる問題がありました（特に `applicationShouldTerminate` のセッション保存ダイアログとの競合）。

v1.3.6 では、`SelfUpdater` がバックグラウンドのシェルスクリプト (`nohup`) を起動し、自身 (`PID`) の終了を監視する方式を採用。アプリが完全に終了した直後に、シェルスクリプトが `/Applications/Verantyx.app` を安全に上書きし、再起動する仕組みを実現しました。

## まとめ

Verantyx v1.3.6 は、外部のコンパイル済み Rust バイナリへの依存を断ち切り、macOS のエコシステム（Swift / AppleScript）内で完結する堅牢な Web グラウンディング機構を手に入れました。

ReAct 型のエラー復旧機能と、AgentLoop のストール防止策により、LLM はこれまで以上に安定して長期的なリサーチとコーディングを自律的に遂行できるようになりました。自律型 AI エージェントは、単なる「ツール」から「粘り強く問題を解決するパートナー」へと確実に進化を遂げています。
