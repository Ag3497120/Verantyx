<div对齐=“中心”>
  <h1>🛡️ Verantyx（可验证和可审计的人工智能引擎）</h1>
  <p><b>零泄漏、神经符号 AI 编码网关和原生 macOS IDE</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="版本 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README.md">英语</a> · <a href="README-es.md">西班牙语</a> · <a href="README-pt-BR.md">葡萄牙语（巴西）</a> · <a href="README-de.md">德语</a> · <a href="README-fr.md">法语</a> · <a href="README-zh-CN.md">简体中文</a> · <a href="README-zh-TW.md">繁体中文</a> · <a href="README-ko.md">한국어</a> · <a href="README-ja.md">日文</a> · <a href="README-ar.md">阿拉伯语</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">土耳其</a>
  </p>
</div>

---

Verantyx 是下一代神经符号逻辑引擎，使人工智能驱动的软件开发完全可控且安全。
我们在一个强大的核心引擎（JCross/L3.5 内存）之上提供两个不同的前端。请根据您的目的进行选择。

---

## 1. 🖥️ Verantyx Gatekeeper（IDE 模式）
**“我想让云法学硕士安全地读取我公司的机密代码”**

Gatekeeper 模式是终极安全 IDE，可在将源代码传递给 AI 之前将其混淆为无意义的数学难题（不透明拓扑）。
👉 [Gatekeeper模式及混淆机制详情请点击这里（README-Gatekeeper.md）](./docs/README-Gatekeeper.md)

## 2. ⚡ Verantyx Agent（聚光灯模式）
**“我想充分利用本地最强大的人工智能作为我大脑的延伸”**

它是一个超自主代理，只需按三次“Control”键即可激活。它配备了使用 Dual Twin 的内部审计、使用 1930 年隐喻的物理屏蔽幻觉以及将 PC 资产识别为“你自己的记忆（L3.5）”的下一代思维引擎。
👉 [Agent模式详情及架构请点击这里（README-Agent.md）](./docs/README-Agent.md)

---

## 💻 安装方法（从源码构建）

**要求：**
- macOS 14.0 或更高版本（强烈推荐 Apple Silicon）
- Xcode 15.0 或更高版本

````bash
git 克隆 https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
打开 Verantyx.xcodeproj
# 选择 Verantyx 方案并按 Cmd+R 构建并运行
````

*注：Windows/Linux 移植（Rust core + llama.cpp）处于长期路线图上，但我们目前非常专注于完成本机 macOS/MLX 架构。 *

---

## 📖 关于 Verantyx

对于这个项目，当我之前尝试创建一个基于规则的符号AI时，我意识到自己不可能创建它，所以我决定通过创建自己控制的部分来控制它，比如目前主流AI的harness部分。 （当时openclaw很受关注）
从那时起，我开始开发这个项目，因为我认为通过在将源代码和用户请求传递给云中的高性能人工智能之前以类似谜题的状态对其进行混淆，可以防止信息泄露。

这个项目之所以有0星，是因为它包含一个安全文件夹，而我突然将其设为私人存储库，所以9星消失了。感谢您一直以来的支持，因为我已经完全康复了。我已经整理了似乎与其他存储库重叠的部分。我主要是在这个存储库中推送版本，但是我发现源代码更新被延迟并更新了它。

从现在开始，我考虑专注于我的母语日语，并使用常规翻译工具翻译英语并发布以防万一。

---

## 🔧 关于存储库设置和历史记录

**有关 Git 设置的注意事项：**
对该存储库的早期提交是在本地 Git 名称“kofdai”下进行的，该名称源自开发人员的 macOS 用户名。此问题已于 2026 年 5 月 24 日修复，所有提交现在都正确归因于“@Ag3497120”。这是设置开发环境时的常见问题，不是由机器人或自动化工具引起的。所有未来的贡献都将用正确的作者姓名记录。