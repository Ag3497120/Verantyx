<div对齐=“中心”>
  <h1>🛡️ Verantyx IDE 和 Cortex 引擎</h1>
  <p><b>零泄漏、神经符号 AI 编码网关和原生 macOS IDE</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="版本 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README-en.md">英语</a> · <a href="README-es.md">西班牙语</a> · <a href="README-pt-BR.md">葡萄牙语（巴西）</a> · <a href="README-de.md">德语</a> · <a href="README-fr.md">法语</a> · <a href="README-zh-CN.md">简体中文</a> · <a href="README-zh-TW.md">繁体中文</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">日文</a> · <a href="README-ar.md">阿拉伯语</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">土耳其</a>
  </p>
</div>

---

## 📖 关于 Verantyx

对于这个项目，当我之前尝试创建一个基于规则的符号AI时，我意识到自己不可能创建它，所以我决定通过创建自己控制的部分来控制它，比如目前主流AI的harness部分。 （当时openclaw很受关注）
从那时起，我开始开发这个项目，因为我认为通过在将源代码和用户请求传递给云中的高性能人工智能之前以类似谜题的状态对其进行混淆，可以防止信息泄露。

这个项目之所以有0星，是因为它包含一个安全文件夹，而我突然将其设为私人存储库，所以9星消失了。感谢您一直以来的支持，因为我已经完全康复了。我已经整理了似乎与其他存储库重叠的部分。我主要是在这个存储库中推送版本，但是我发现源代码更新被延迟并更新了它。

从现在开始，我考虑专注于我的母语日语，并使用常规翻译工具翻译英语并发布以防万一。

## 🔐 混淆和 6 轴 3D 交叉结构

混淆这个项目背后的想法是使用基于 Axis 中的三维交叉结构的数据管理方法，Axis 是 verantyx 的前身，它是早期作为如何传递数据的图像而创建的。

### 🧩 6 个维度（轴）的定义

|轴|名称 |角色/提取元素|
| :--- | :--- | :--- |
| **X 轴** | **控制流程** |时间轴和顺序轴。 `if` 分支、`for` 循环、异常处理等 |
| **Y 轴** | **数据流** |依赖轴。变量赋值、参数传递等 |
| **Z 轴** | **类型约束** |边界轴。类定义、类型注释、泛型等 |
| **W轴** | **内存生命周期** |生命轴。作用域生命周期、内存分配/释放。 |
| **V 轴** | **范围层次结构** |包含轴。模块、类嵌套结构。 |
| **U轴** | **语义和含义** | **★最重要★ 商业意图轴。具体变量名称、函数名称、原始字符串和数字。 ** |

Verantyx 的 **Gatekeeper Engine** 在您的 MacBook 上立即执行转换过程。

---

### 🔄 原始代码到不透明拓扑转换机制

#### 步骤一：解析分解为AST（抽象语法树）
首先，Gatekeeper引擎（推荐基于规则）解析目标源代码，并将程序结构转换为树形结构数据，称为AST（抽象语法树）。
此时，所有信息仍然包括在内，例如“哪个函数正在调用什么”，“变量名是什么，以及什么被定义为字符串？”

####第二步：语义的“物理分离和隔离”（U轴）
这就是 Verantyx 的闪光点。从 AST 中物理剥离所有指示业务含义（意图）的信息 = U 轴**。

* **剥离掉的东西（U轴）**：变量名、函数名、字符串、固定数字等。
* **剩下的（X、Y、Z、W、V 轴）**：“分配变量”、“调用函数”、“用 if 语句分支”和“用 for 语句循环”的逻辑框架。

剥离的特定名称和字符串数据安全地存储在 Mac 的 **`JCrossIRVault`（保管库）** 中，并且永远不会发送到外部。

#### 步骤3：完全加密到不透明节点
剩下的“骨头”，被剥夺了意义，被转换成完全不透明的表示形式，以发送到云法学硕士。

* **`NODE[0x...]`（节点 ID）**：所有变量和语法元素都替换为标识符，例如随机内存地址。
* **`ARITY`（数量/项数）**：
    * `class.nullary`：没有参数或内容的元素（只是一个值或终端节点）。
    * `class.standard`：标准一元和二元运算（A + B、赋值等）。
    * `class.multiway`：具有多个元素的复杂结构（for 循环、if-else 分支、函数定义等）。
* **`HASH`（结构哈希）**：一种校验和，显示节点在图中的位置以及它如何与其周围环境连接。这允许您在 LLM 解决难题并返回它时本地验证结构没有被破坏。

甚至原始代码语句也消失了，变成了纯粹的数学图：“class.multiway”节点迭代其子节点。”

#### 步骤 4：注入“诱饵”以防止统计推断
如果您将图结构中的代码发送给外部方，则存在高级人工智能或恶意攻击者通过统计推断（逆向工程）该图的形状是通用脚本的形状的风险。

为了防止这种情况，我们将**假节点（诱饵）**随机注入到图中的间隙中。
````文本
// _TOKEN_匶:0.2___jcross_BM_505__ [诱饵元数据]
````
通过混合这些无意义的汉字标记和虚拟连接，图表的形状被扭曲，使得外部人工智能在数学上不可能推断出原始源代码的真实身份。

---

### 🧩 LLM 如何“解决”这个问题？ （恢复过程）

1. **作为谜题解决**：
   在不知道原始代码的情况下，LLM 会根据指示的上下文和图形的形状（ARITY 和 HASH 连接）推断目标更改的值。
2. **返回结构补丁**：
   LLM 仅返回 JSON 格式的结构补丁（GraphPatch），重写内容。
3. **本地反编译**：
   Mac 的 Gatekeeper 引擎接收补丁并将之前隐藏在“JCrossIRVault”中的真实变量名称和字符串（U 轴）重新注入到补丁中。

从而实现了一种神奇的无信息泄露的开发体验，“即使外部AI没有看到或理解一行原始代码，但当它返回到本地代码时，代码已经被正确重写。”** *可能存在我忽略的信息泄露，所以如果您发现任何信息泄露，请通过issue告诉我们。

---

## ⚠️ 我目前无法处理的任务（我不擅长）

目前，此结构无法处理诸如**从 Swift 重写为 Rust** 等任务，这通常是最弱的任务。另外，下面的任务 1 到 4 对我来说也很困难。

### 1.依赖于“语义（领域知识）”的重构和错误修复
由于外部LLM只看到`NODE[0x...]`的骨架，它无法处理“不理解代码含义就无法解决的问题”。
* **❌弱指令示例**：“将前缀‘auth_’添加到所有与身份验证相关的变量的名称中。”
* **原因**：LLM 无法了解“哪个身份验证过程”。

### 2.添加强烈依赖外部库（API）的新功能
源代码中的所有“import”语句和库调用也被加密为“NODE”，这使得需要了解特定库的任务变得困难。
* **❌ 弱指令示例**：“添加将文件上传到 AWS S3 的功能”
* **原因**：LLM 不知道当前代码正在使用哪些外部库。

### 3.“从头开始编写一个全新的功能”
Gatekeeper 在“修补和修改现有结构（AST）”方面非常强大，但在“从白纸开始创建具有意义（U 轴）和结构的巨大新功能”方面却很弱。

### 4. 由于LLM本身的“先验知识”无效而导致推理能力下降
像 Gemma 和 Claude 这样的法学硕士通过研究世界各地的源代码变得更加聪明，但 Verantyx 发送的格式是“与世界上任何其他语言不同的纯符号和哈希图”。
* **原因**：因为LLM的专业“从代码上下文进行模式识别”被屏蔽，所以它变成了一个你从未见过的困难的数学图谜题，导致计算成本增加。

### 💡你是如何克服的？ （未来展望）
目前，Verantyx 正在实施“三层 JCross Memory”和 **Visual Anchors 的组合来克服这些弱点。我们采取的方法是，仅将不包含敏感信息的安全元数据部分呈现给 LLM 作为视觉锚点，在保持安全性的同时提供提示。

---

## 📽️ 演示视频和代码转换实际操作

<p对齐=“中心”>
  <img src="demo.gif" alt="Verantyx Gatekeeper 演示" width="49%" style="border-radius: 8px;">
  <video src="https://github.com/verantyx/verantyx/releases/download/v1.2.5/demo_skill_ Generation.mov"controls="controls" muted="muted" width="49%" style="border-radius: 8px;"></video>
</p>

### 之前和之后：混淆操作

**[之前]原始源代码（本地环境）**
````蟒蛇
导入 json
导入操作系统
进口舒蒂尔
导入请求
导入子流程
进口再
从 tqdm 导入 tqdm
导入系统

# 导入我们的新解析器
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
从 verantyx.cross_engine.jcross_extraction_parser 导入 JCrossExtractionParser

ORACLE_FILE =“/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json”
TARGET_DIR =“/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v7”
QUERY_BIN =“/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/release/examples/query_jcross”
模型=“gemma4：e2b”
OLLAMA_URL =“http://localhost:11434/api/generate”

FINAL_REPORT =“/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/official_v7_1_accuracy_report.json”
````

**[之后] Gatekeeper JCross 不透明拓扑（发送至 Cloud LLM）**
````口齿不清
;;; 🛡️ 守门者模式 — JCross IR 视图
;;;真实标识符已替换为节点 ID。
;;;架构：D59144D1-BE1
;;;节点：124 |秘密编辑：3442
;;;来源：cortex/bench_v7_1_puzzle_runner.py
;;;
// JCROSS_6AXIS_BEGIN
// lang:swift 文档:0xD5E025

// ── 顶层节点
  NODE[0x7995] 种类：不透明 类型：不透明 MEM：不透明 哈希：0xb4af0a52 ARITY：class.multiway
  NODE[0x9DB8] 种类：不透明 类型：不透明 MEM：不透明 哈希：0x504933fd ARITY：class.standard
  NODE[0x627F] 种类：不透明 类型：不透明 MEM：不透明 哈希：0x97b540cb ARITY：class.multiway
  NODE[0x7F4C] 种类：不透明 类型：不透明 MEM：不透明 哈希：0x86742e8c ARITY：class.standard
  NODE[0xC79E] 种类：不透明 类型：不透明 MEM：不透明 哈希：0xd42206c4 ARITY：class.standard
  NODE[0x510B] 种类：不透明 类型：不透明 MEM：不透明 哈希：0x14b9be4e ARITY：class.nullary
  NODE[0xB5C0] 种类：不透明 类型：不透明 MEM：不透明 HASH：0xcacb18a2 ARITY：class.standard
// _TOKEN_匶:0.2___jcross_BM_505__ [诱饵元数据]
  NODE[0xE3CF] 种类：不透明 类型：不透明 MEM：不透明 哈希：0x375a5480
````

---

## 💻 安装方法（从源码构建）

**要求：**
- macOS 14.0 或更高版本（强烈推荐 Apple Silicon）
- Xcode 15.0 或更高版本

````重击
git 克隆 https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
打开 Verantyx.xcodeproj
# 选择 Verantyx 方案并按 Cmd+R 构建并运行
````

*注：Windows/Linux 移植（Rust core + llama.cpp）处于长期路线图上，但我们目前非常专注于完成本机 macOS/MLX 架构。 *

---

## 🔧 关于存储库设置和历史记录

**有关 Git 设置的注意事项：**
对该存储库的早期提交是在本地 Git 名称“kofdai”下进行的，该名称源自开发人员的 macOS 用户名。此问题已于 2026 年 5 月 24 日修复，所有提交现在都正确归因于“@Ag3497120”。这是设置开发环境时的常见问题，不是由机器人或自动化工具引起的。所有未来的贡献都将用正确的作者姓名记录。

---

## 💡 问答和申诉（实验功能）

目前，您可以通过按三次“Control”键来启动 **Verantyx Agent**。

<p对齐=“中心”>
  <img src="assets/verantyx_agent_v2.png" alt="Verantyx 代理接口" width="600" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
</p>

创建此模式是为了测试以前应用程序中的各种 IDE 模式。为了回顾整个项目并关注真正需要的“看门人模式”，我们将迄今为止创建的代理行为的实验功能整合到**Verantyx Agent**中。

先前版本中包含的主要代理功能包括：

* **Dual Twin审核系统**：为了防止AI调用工具出现疏忽的问题，我们引入了TwinB通过内部注入JCross来审核TwinA工具调用有效性的机制。
* **Visual Anchor介绍**：我们从仅通过提示来控制技能和指令，改为使用Visual Anchor进行图像注入和提示的混合方法。
* **L3.5 OS 资产映射的构建**：在以 Control×3 启动的代理中，称为“L3.5”的内部计算机映射仅在本地维护。我们向特工灌输这样的意识：他们计算机上的资产与他们自己的情报相关。
* **使用 AX API 的高精度 GUI 操作**：我们已从使用屏幕录制的现有 GUI 操作转向使用 OS API 树（辅助功能 API）的可靠且高精度的操作。
* **汉字拓扑压缩**：将L3.5图注入上下文时，生成图像并将其用作提示，以防止上下文变得臃肿。通过将一种称为“汉字拓扑”的独特压缩格式与实际数据相关联，我们确保只适当地注入必要的数据。
* **代理模式扩展**：添加了“自动模式”和“高级模式”两种类型。
* **内部知识优先模式**：对于使用限制消除模型的高级用户，我们实现了一种模式，使他们能够充分利用本地人工智能，不仅作为编排者，而且作为主要思维模型和知识源。
* **L3.5专用内存行**：为了防止L3.5地图内存变得复杂和庞大，我们创建了一个与正常会话内存完全分离的内存行。
* **应用于微调**：我们实现了一个功能，可以作为立足点，从L1到L3.5的内存中提取用户身份数据，并对任何模型进行微调（达到仅靠内存系统无法实现的优化）。
* **采用FAR区域结构**：基于“组织记忆而不删除它们”的理念，我们采用了一种结构，记录任务完成时的任务包和标题等过渡过程，并将其放入名为“FAR区域”的新层中。这确保了即使在任务完成后也保留了重要的记忆，例如工作流程。

这些只是当前添加的一些功能。
最近的更新引入了使用 HuggingFace 上发布的“talkie-1930:13b”的部分量化版本的编排（Blind Commander Architecture）。利用“只有1930年以来的知识”的限制，我们使用基于规则的中介来执行命令，并具有将用户的消息转换为当时的比喻表达的作用。正在添加体现该项目“实验”理念的其他功能。

### 🔄 未来路线图和巨大的挑战

这种代理和网守模式目前连接在同一个存储区域中，但将来我们计划实现一个功能，允许它们分开并进行微调。

目前，该制剂的开发已达到暂时的里程碑。由于我自己也是一名学生，一旦这个代理能够完全处理Teams等中给出的任务（诸如“创建并提交最近的〇〇作业”之类的任务），我想开始全面开发“Gatekeeper模式”，目前我正在将其作为改进计划。感谢所有给予星星的人。请稍等。

最后，我想谈谈我们为这个项目的高潮而准备的特大挑战。

1. **移植到Windows版本（基于Rust）**：此任务是将目前针对macOS使用Swift语言编写的实现重写为基于Rust，以便Windows用户也可以体验相同的gatekeeper功能。
2. **完全脱离云依赖**：成长为仅使用本地LLM即可自主继续开发的代理，无需支付昂贵的API费用。我们希望利用在MacBook上运行的20B级模型（例如最近的“qwen3.6:27b”，据说在某些条件下可以与最高端模型相媲美），运行接近云级别的编码代理，并通过自主改进来进行项目。