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

## アーキテクチャの概要

Verantyx の Web グラウンディング（SearchGate）パイプラインは、以下の3層アーキテクチャで構成されています。

1. **生体エントロピー取得層 (Swift / SwiftUI)**
   - ユーザーが「Human Verification Needed」パズルを解く際の**マウスの軌跡 (Mouse Trajectories)** と **動画フレーム (Video Frames)** を収集します。
   - 収集されたデータは `AppState.lastEntropy` として保持されます。
2. **AgentLoop オーケストレーション (Swift)**
   - Agent が Web 検索（または `[SEARCH_MULTI]`）を要求した際、エントロピーが不足している場合はスレッドを停止し、ユーザーにパズルを要求します。
   - 取得されたエントロピーを `WebSearchEngine` に渡し、ブラウザブリッジへ転送します。
3. **ブラウザ制御・インジェクション層 (Rust / stealth_bridge.rs)**
   - `CGEvent` を用いて、OS レベルのマウス移動・クリックイベントをシミュレートします。
   - `CGEventTapLocation::Session` を経由することで、入力フィルタリングをバイパスし、実際の物理デバイスからの入力と見分けがつかないトラフィックを生成します。

## CGEvent による OS レベルのエミュレーション

JavaScript 経由の `HTMLElement.click()` や、WebDriver プロトコル経由のクリックは、WAF のフィンガープリント（`navigator.webdriver` やイベントの `isTrusted` フラグ）によって容易に検知されます。

Verantyx では、macOS ネイティブの CoreGraphics (`CGEvent`) を利用して、OSの最下層から入力イベントを注入します。

```rust
// stealth_bridge.rs での CGEvent マウス移動の実装例
let point = CGPoint::new(x, y);
let event = CGEvent::new_mouse_event(
    CGEventSourceStateID::HIDSystemState,
    CGEventType::MouseMoved,
    point,
    CGMouseButton::Left
).unwrap();
event.post(CGEventTapLocation::Session);
```

この方法の最大の利点は、ブラウザ側からは「本物のユーザーが物理マウスを動かしてクリックした」ようにしか見えないことです。`isTrusted` は常に `true` となり、Bot 検知をすり抜けます。

## 生体エントロピーの再生 (Biometric Entropy Playback)

単に直線的にマウスを動かすだけでは、ヒューリスティックな軌跡分析（Mouse Dynamics Analysis）によって Bot と判定されます。そのため、Verantyx は SwiftUI ベースのパズル UI で収集した**実際の人間のマウス軌跡**を再生します。

```swift
// HumanProofPuzzleView.swift
.onChanged { value in
    mousePath.append(value.location) // 軌跡をサンプリング
}
```

この `mousePath` の配列を Rust 側に渡し、ベジェ曲線やスプライン補間を用いて、目的の座標（リンクや検索ボックス）までの軌跡としてスケーリング・再構築します。これにより、手の震え、わずかなオーバーシュート、速度の非線形変化など、人間特有の「エントロピー」が入力に付与されます。

## Qwen アーキテクチャと動画フレームエントロピー

さらに高度な WAF を回避するため、Verantyx は視覚的なエントロピーも活用します。`VideoClipManager` を通じてパズル解答中の画面録画フレームを取得し、これをマルチモーダルモデル（Qwen-VL など）のコンテキストに含めることで、モデル自身が現在の画面状態を認識し、より人間らしいタイミングでのインタラクションを決定します。

## まとめ

Web を自律的に探索する AI エージェントにとって、WAF の回避は必須の課題です。Verantyx は、OS レベルの `CGEvent` エミュレーションと人間由来の生体エントロピーを組み合わせることで、Puppeteer 等では不可能なレベルのステルス性を実現しました。

このアーキテクチャにより、LLM はハルシネーションを起こすことなく、最新のドキュメントやリポジトリの状況を安全にリサーチ（グラウンディング）することが可能になります。
