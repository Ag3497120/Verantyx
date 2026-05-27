<div對齊=“中心”>
  <h1>🛡️ Verantyx（可驗證且可審計的人工智慧引擎）</h1>
  <p><b>零洩漏、神經符號 AI 編碼閘道和原生 macOS IDE</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="版本 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README-en.md">英語</a> · <a href="README-es.md">西班牙語</a> · <a href="README-pt-BR.md">葡萄牙語（巴西）</a> · <a href="README-de.md">德語</a> · <a href="RE">ADMEa <md; href="README-zh-CN.md">簡體中文</a> · <a href="README-zh-TW.md">繁體中文</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">日</md</a> 阿拉伯文</a="JD.RE="CD; href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">土耳其</a>
  </p>
</div>

---

Verantyx 是下一代神經符號邏輯引擎，使人工智慧驅動的軟體開發完全可控且安全。
我們在一個強大的核心引擎（JCross/L3.5 記憶體）之上提供兩個不同的前端。請根據您的目的進行選擇。

---

## 1. 🖥️ Verantyx Gatekeeper（IDE 模式）
**「我想讓雲端法學碩士安全地讀取我公司的機密代碼」**

Gatekeeper 模式是終極安全 IDE，可在將原始程式碼傳遞給 AI 之前將其混淆為無意義的數學難題（不透明拓撲）。
👉 [Gatekeeper模式及混淆機制詳情請點這裡（README-Gatekeeper.md）](./docs/README-Gatekeeper.md)

## 2. ⚡ Verantyx Agent（聚光燈模式）
**「我想充分利用本地最強大的人工智慧作為我大腦的延伸」**

它是一個超自主代理，只需按三次“Control”鍵即可啟動。它配備了使用 Dual Twin 的內部審計、使用 1930 年隱喻的物理屏蔽幻覺以及將 PC 資產識別為「你自己的記憶（L3.5）」的下一代思維引擎。
👉 [Agent模式詳情及架構請點這裡（README-Agent.md）](./docs/README-Agent.md)

---

## 💻 安裝方法（從原始碼建置）

**要求：**
- macOS 14.0 或更高版本（強烈推薦 Apple Silicon）
- Xcode 15.0 或更高版本

````bash
git 克隆 https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
開啟 Verantyx.xcodeproj
# 選擇 Verantyx 方案並按 Cmd+R 建置並執行
````

*註：Windows/Linux 移植（Rust core + llama.cpp）處於長期路線圖上，但我們目前非常專注於完成本機 macOS/MLX 架構。 *

---

## 📖 關於 Verantyx

對於這個項目，當我之前嘗試創建一個基於規則的符號AI時，我意識到自己不可能創建它，所以我決定透過創建自己控制的部分來控制它，例如目前主流AI的harness部分。 （當時openclaw很受關注）
從那時起，我開始開發這個項目，因為我認為透過在將原始碼和用戶請求傳遞給雲端中的高效能人工智慧之前以類似謎題的狀態對其進行混淆，可以防止資訊外洩。

這個專案之所以有0顆星，是因為它包含一個安全資料夾，而我突然將其設為私人儲存庫，所以9顆星消失了。感謝您一直以來的支持，因為我已經完全康復了。我已經整理了似乎與其他存儲庫重疊的部分。我主要是在這個存儲庫中推送版本，但是我發現原始程式碼更新被延遲並更新了它。

從現在開始，我考慮專注於我的母語日語，並使用常規翻譯工具翻譯英語並發布以防萬一。

---

## 🔧 關於儲存庫設定和歷史記錄

**有關 Git 設定的注意事項：**
對該儲存庫的早期提交是在本地 Git 名稱“kofdai”下進行的，該名稱源自開發人員的 macOS 使用者名稱。此問題已於 2026 年 5 月 24 日修復，所有提交現在都正確歸因於“@Ag3497120”。這是設定開發環境時的常見問題，不是由機器人或自動化工具引起的。所有未來的貢獻都將以正確的作者姓名記錄。