<div對齊=“中心”>
  <h1>🛡️ Verantyx IDE 和 Cortex 引擎</h1>
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

## 📖 關於 Verantyx

對於這個項目，當我之前嘗試創建一個基於規則的符號AI時，我意識到自己不可能創建它，所以我決定透過創建自己控制的部分來控制它，例如目前主流AI的harness部分。 （當時openclaw很受關注）
從那時起，我開始開發這個項目，因為我認為透過在將原始碼和用戶請求傳遞給雲端中的高效能人工智慧之前以類似謎題的狀態對其進行混淆，可以防止資訊外洩。

這個專案之所以有0顆星，是因為它包含一個安全資料夾，而我突然將其設為私人儲存庫，所以9顆星消失了。感謝您一直以來的支持，因為我已經完全康復了。我已經整理了似乎與其他存儲庫重疊的部分。我主要是在這個存儲庫中推送版本，但是我發現原始程式碼更新被延遲並更新了它。

從現在開始，我考慮專注於我的母語日語，並使用常規翻譯工具翻譯英語並發布以防萬一。

## 🔐 混淆與 6 軸 3D 交叉結構

混淆這個專案背後的想法是使用基於 Axis 中的三維交叉結構的資料管理方法，Axis 是 verantyx 的前身，它是早期作為如何傳遞資料的圖像而創建的。

### 🧩 6 個維度（軸）的定義

|軸|名稱 |角色/提取元素|
| :--- | :--- | :--- |
| **X 軸** | **控制流程** |時間軸與順序軸。 `if` 分支、`for` 循環、異常處理等 |
| **Y 軸** | **資料流** |依賴軸。變數賦值、參數傳遞等 |
| **Z 軸** | **類型約束** |邊界軸。類別定義、型別註解、泛型等 |
| **W軸** | **記憶體生命週期** |生命軸。作用域生命週期、記憶體分配/釋放。 |
| **V 軸** | **範圍層次結構** |包含軸。模組、類別嵌套結構。 |
| **U軸** | **語意與意義** | **★最重要★ 商業意圖軸。具體變數名稱、函數名稱、原始字串和數字。 ** |

Verantyx 的 **Gatekeeper Engine** 在您的 MacBook 上立即執行轉換程序。

---

### 🔄 原始程式碼到不透明拓撲轉換機制

#### 步驟一：解析分解為AST（抽象語法樹）
首先，Gatekeeper引擎（建議基於規則）解析目標原始碼，並將程式結構轉換為樹形結構數據，稱為AST（抽象語法樹）。
此時，所有資訊仍然包括在內，例如“哪個函數正在呼叫什麼”，“變數名稱是什麼，以及什麼被定義為字串？”

####第二步：語意的「物理分離與隔離」（U軸）
這就是 Verantyx 的閃光點。從 AST 中物理剝離所有指示業務含義（意圖）的資訊 = U 軸**。

* **剝離掉的東西（U軸）**：變數名、函數名、字串、固定數字等。
* **剩下的（X、Y、Z、W、V 軸）**：「分配變數」、「呼叫函數」、「用 if 語句分支」和「用 for 語句循環」的邏輯框架。

剝離的特定名稱和字串資料安全地儲存在 Mac 的 **`JCrossIRVault`（保管庫）** 中，並且永遠不會發送到外部。

#### 步驟3：完全加密到不透明節點
剩下的“骨頭”，被剝奪了意義，被轉換成完全不透明的表示形式，以發送到雲法學碩士。

* **`NODE[0x...]`（節點 ID）**：所有變數和語法元素都會替換為標識符，例如隨機記憶體位址。
* **`ARITY`（數量/項數）**：
    * `class.nullary`：沒有參數或內容的元素（只是一個值或終端節點）。
    * `class.standard`：標準一元與二元運算（A + B、賦值等）。
    * `class.multiway`：具有多個元素的複雜結構（for 循環、if-else 分支、函數定義等）。
* **`HASH`（結構雜湊）**：一種校驗和，顯示節點在圖中的位置以及它如何與其周圍環境連接。這允許您在 LLM 解決難題並返回它時本地驗證結構沒有被破壞。

甚至原始程式碼語句也消失了，變成了純粹的數學圖：「class.multiway」節點迭代其子節點。 」

#### 步驟 4：注入「誘餌」以防止統計推斷
如果您將圖結構中的程式碼傳送給外部方，則存在高階人工智慧或惡意攻擊者透過統計推斷（逆向工程）該圖的形狀是通用腳本的形狀的風險。

為了防止這種情況，我們將**假節點（誘餌）**隨機注入到圖中的間隙。
````文本
// _TOKEN_匶:0.2___jcross_BM_505__ [誘餌元資料]
````
透過混合這些無意義的漢字標記和虛擬連接，圖表的形狀被扭曲，使得外部人工智慧在數學上不可能推斷出原始原始碼的真實身份。

---

### 🧩 LLM 如何「解決」這個問題？ （恢復過程）

1. **作為謎題解決**：
   在不知道原始程式碼的情況下，LLM 會根據指示的上下文和圖形的形狀（ARITY 和 HASH 連接）推斷目標更改的值。
2. **返回結構補丁**：
   LLM 僅傳回 JSON 格式的結構補丁（GraphPatch），重寫內容。
3. **本地反編譯**：
   Mac 的 Gatekeeper 引擎接收補丁並將先前隱藏在「JCrossIRVault」中的真實變數名稱和字串（U 軸）重新註入到補丁中。

從而實現了一種神奇的無資訊洩露的開發體驗，「即使外部AI沒有看到或理解一行原始程式碼，但當它返回到本地程式碼時，程式碼已經被正確重寫。」** *可能存在我忽略的資訊洩露，所以如果您發現任何資訊洩露，請透過issue告訴我們。

---

## ⚠️ 我目前無法處理的任務（我不擅長）

目前，此結構無法處理諸如**從 Swift 重寫為 Rust** 等任務，這通常是最弱的任務。另外，以下的任務 1 到 4 對我來說也很困難。

### 1.依賴「語意（領域知識）」的重構與錯誤修復
由於外部LLM只看到`NODE[0x...]`的骨架，它無法處理「不理解程式碼意義就無法解決的問題」。
* **❌弱指令範例**：“將前綴‘auth_’新增到所有與身份驗證相關的變數的名稱中。”
* **原因**：LLM 無法了解「哪個身份驗證過程」。

### 2.新增強烈依賴外部函式庫（API）的新功能
原始程式碼中的所有“import”語句和函式庫呼叫也被加密為“NODE”，這使得需要了解特定函式庫的任務變得困難。
* **❌ 弱指令範例**：“新增將檔案上傳到 AWS S3 的功能”
* **原因**：LLM 不知道目前程式碼正在使用哪些外部程式庫。

### 3.“從頭開始寫一個全新的功能”
Gatekeeper 在「修補和修改現有結構（AST）」方面非常強大，但在「從白紙開始創建具有意義（U 軸）和結構的巨大新功能」方面卻很弱。

### 4. 由於LLM本身的「先驗知識」無效而導致推理能力下降
像 Gemma 和 Claude 這樣的法學碩士透過研究世界各地的源代碼變得更加聰明，但 Verantyx 發送的格式是「與世界上任何其他語言不同的純符號和哈希圖」。
* **原因**：因為LLM的專業「從程式碼上下文進行模式識別」被屏蔽，所以它變成了一個你從未見過的困難的數學圖謎題，導致計算成本增加。

### 💡你是如何克服的？ （未來展望）
目前，Verantyx 正在實施「三層 JCross Memory」和 **Visual Anchors 的組合來克服這些弱點。我們採取的方法是，僅將不包含敏感資訊的安全元資料部分呈現給 LLM 作為視覺錨點，在保持安全性的同時提供提示。

---

## 📽️ 示範影片和程式碼轉換實際操作

<p對齊=“中心”>
  <img src="demo.gif" alt="Verantyx Gatekeeper 示範" width="49%" style="border-radius: 8px;">
  <video src="https://github.com/verantyx/verantyx/releases/download/v1.2.5/demo_skill_ Generation.mov"controls="controls" muted="muted" width="49%" style="border-radius: 8px;"></vidvideo>
</p>

### 之前和之後：混淆操作

**[之前]原始原始碼（本地環境）**
````蟒蛇
導入 json
導入作業系統
進口舒蒂爾
導入請求
導入子流程
進口再
從 tqdm 導入 tqdm
導入系統

# 匯入我們的新解析器
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
從 verantyx.cross_engine.jcross_extraction_parser 導入 JCrossExtractionParser

ORACLE_FILE =“/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json”
TARGET_DIR =“/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v7”
QUERY_BIN =“/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/release/examples/query_jcross”
模型=“gemma4：e2b”
OLLAMA_URL =“http://localhost:11434/api/generate”

FINAL_REPORT =“/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/official_v7_1_accuracy_report.json”
````

**[之後] Gatekeeper JCross 不透明拓撲（發送至 Cloud LLM）**
````口齒不清
;;; 🛡️ 守門者模式 — JCross IR 視圖
;;;真實識別碼已替換為節點 ID。
;;;架構：D59144D1-BE1
;;;節點：124 |秘密編輯：3442
;;;來源：cortex/bench_v7_1_puzzle_runner.py
;;;
// JCROSS_6AXIS_BEGIN
// lang:swift 文件:0xD5E025

// ── 頂層節點
  NODE[0x7995] 種類：不透明 類型：不透明 MEM：不透明 雜湊：0xb4af0a52 ARITY：class.multiway
  NODE[0x9DB8] 種類：不透明 類型：不透明 MEM：不透明 雜湊：0x504933fd ARITY：class.standard
  NODE[0x627F] 種類：不透明 類型：不透明 MEM：不透明 雜湊：0x97b540cb ARITY：class.multiway
  NODE[0x7F4C] 種類：不透明 類型：不透明 MEM：不透明 雜湊：0x86742e8c ARITY：class.standard
  NODE[0xC79E] 種類：不透明 類型：不透明 MEM：不透明 雜湊：0xd42206c4 ARITY：class.standard
  NODE[0x510B] 種類：不透明 類型：不透明 MEM：不透明 雜湊：0x14b9be4e ARITY：class.nullary
  NODE[0xB5C0] 種類：不透明 類型：不透明 MEM：不透明 HASH：0xcacb18a2 ARITY：class.standard
// _TOKEN_匶:0.2___jcross_BM_505__ [誘餌元資料]
  NODE[0xE3CF] 種類：不透明 類型：不透明 MEM：不透明 雜湊：0x375a5480
````

---

## 💻 安裝方法（從原始碼建置）

**要求：**
- macOS 14.0 或更高版本（強烈推薦 Apple Silicon）
- Xcode 15.0 或更高版本

````重擊
git 克隆 https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
開啟 Verantyx.xcodeproj
# 選擇 Verantyx 方案並按 Cmd+R 建置並執行
````

*註：Windows/Linux 移植（Rust core + llama.cpp）處於長期路線圖上，但我們目前非常專注於完成本機 macOS/MLX 架構。 *

---

## 🔧 關於儲存庫設定和歷史記錄

**有關 Git 設定的注意事項：**
對該儲存庫的早期提交是在本地 Git 名稱“kofdai”下進行的，該名稱源自開發人員的 macOS 使用者名稱。此問題已於 2026 年 5 月 24 日修復，所有提交現在都正確歸因於“@Ag3497120”。這是設定開發環境時的常見問題，不是由機器人或自動化工具引起的。所有未來的貢獻都將以正確的作者姓名記錄。

---

## 💡 問答與申訴（實驗功能）

目前，您可以按三次「Control」鍵來啟動 **Verantyx Agent**。

<p對齊=“中心”>
  <img src="assets/verantyx_agent_v2.png" alt="Verantyx 代理介面" width="600" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
</p>

建立此模式是為了測試先前應用程式中的各種 IDE 模式。為了回顧整個專案並專注於真正需要的“看門人模式”，我們將迄今為止創建的代理行為的實驗功能整合到**Verantyx Agent**中。

先前版本中包含的主要代理功能包括：

* **Dual Twin審核系統**：為了防止AI呼叫工具出現疏忽的問題，我們引入了TwinB透過內部注入JCross來審核TwinA工具呼叫有效性的機制。
* **Visual Anchor介紹**：我們從僅透過提示來控制技能和指令，改為使用Visual Anchor進行影像注入和提示的混合方法。
* **L3.5 OS 資產映射的建置**：在以 Control×3 啟動的代理程式中，稱為「L3.5」的內部電腦映射僅在本地維護。我們向特工灌輸這樣的意識：他們電腦上的資產與他們自己的情報相關。
* **使用 AX API 的高精度 GUI 操作**：我們已從使用螢幕錄製的現有 GUI 操作轉向使用 OS API 樹（輔助功能 API）的可靠且高精度的操作。
* **漢字拓撲壓縮**：將L3.5圖注入上下文時，生成圖像並將其用作提示，以防止上下文變得臃腫。透過將一種稱為「漢字拓撲」的獨特壓縮格式與實際資料相關聯，我們確保只適當地註入必要的資料。
* **代理模式擴充**：新增了兩種類型：「自動模式」和「進階模式」。
* **內部知識優先模式**：對於使用限制消除模型的高級用戶，我們實現了一種模式，使他們能夠充分利用本地人工智慧，不僅作為編排者，而且作為主要思維模型和知識來源。
* **L3.5專用記憶體行**：為了防止L3.5地圖記憶體變得複雜和龐大，我們創建了一個與正常會話記憶體完全分離的記憶體行。
* **應用於微調**：我們實現了一個功能，可以作為立足點，從L1到L3.5的內存中提取用戶身份數據，並對任何模型進行微調（達到僅靠內存系統無法實現的優化）。
* **採用FAR區域結構**：基於「組織記憶而不刪除它們」的理念，我們採用了一種結構，記錄任務完成時的任務包和標題等過渡過程，並將其放入名為「FAR區域」的新圖層中。這確保了即使在任務完成後也保留了重要的記憶，例如工作流程。

這些只是目前新增的一些功能。
最近的更新引入了使用 HuggingFace 上發布的“talkie-1930:13b”的部分量化版本的編排（Blind Commander Architecture）。利用「只有1930年以來的知識」的限制，我們使用基於規則的中介來執行命令，並具有將用戶的消息轉換為當時的比喻表達的作用。正在添加體現該專案「實驗」理念的其他功能。

### 🔄 未來路線圖與巨大的挑戰

這種代理和網守模式目前連接在同一個儲存區域中，但將來我們計劃實現一個功能，允許它們分開並進行微調。

目前，該製劑的開發已達到暫時的里程碑。由於我自己也是一名學生，一旦這個代理能夠完全處理Teams等中給出的任務（諸如“創建並提交最近的〇〇作業”之類的任務），我想開始全面開發“Gatekeeper模式”，目前我正在將其作為改進計劃。感謝所有給予星星的人。請稍等。

最後，我想談談我們為這個計畫的高潮而準備的特大挑戰。

1. **移植到Windows版本（基於Rust）**：此任務是將目前針對macOS使用Swift語言編寫的實作重寫為基於Rust，以便Windows使用者也可以體驗相同的gatekeeper功能。
2. **完全脫離雲端依賴**：成長為僅使用本地LLM即可自主繼續開發的代理，無需支付昂貴的API費用。我們希望利用在MacBook上運行的20B級模型（例如最近的“qwen3.6:27b”，據說在某些條件下可以與最高端模型相媲美），運行接近雲級別的編碼代理，並通過自主改進來進行項目。