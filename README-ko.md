<div align="center">
  <h1>🛡️ Verantyx (Verifiable & Auditable AI Engine)</h1>
  <p><b>The Zero-Leakage, Neuro-Symbolic AI Coding Gateway & Native macOS IDE</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Version 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README-en.md">English</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Deutsch</a> href="README-fr.md">Français</a> · <a href="README-zh-CN.md">简体中文</a> · <a href="README-zh-TW.md">번체중문</a> · <a href="README-ko.md">한국 href="README.md">한국어</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="REA
  </p>
</div>

---

Verantyx는 AI의 소프트웨어 개발을 완벽하게 제어하고 안전하게 만드는 차세대 Neuro-Symbolic 로직 엔진입니다.
우리는 하나의 강력한 코어 엔진(JCross/L3.5 Memory) 위에 **2개의 다른 프런트 엔드**를 제공합니다. 귀하의 목적에 맞게 선택하십시오.

---

## 1. 🖥️ Verantyx Gatekeeper (IDE Mode)
** "회사의 기밀 코드를 클라우드 LLM에 안전하게 읽고 싶습니다"**

Gatekeeper 모드는 소스 코드를 의미가 없는 수학적 퍼즐(Opaque Topology)로 난독화한 다음 AI로 전달하는 궁극의 보안 IDE입니다.
👉 [Gatekeeper 모드의 상세와 난독화의 구조(README-Gatekeeper.md)는 이쪽](./docs/README-Gatekeeper.md)

## 2. ⚡ Verantyx Agent (Spotlight Mode)
** "최강의 로컬 AI를 뇌의 확장으로 완전히 다루고 싶다"**

`Control` 키를 세 번 누르면 시작하는 초자율 에이전트입니다. Dual Twin에 의한 내부 감사, 1930년 메타파에 의한 할시네이션의 물리 차단, 그리고 PC의 자산을 「자신의 기억(L3.5)」으로서 인식하는 차세대 사고 엔진을 탑재하고 있습니다.
👉 [Agent 모드의 상세 및 아키텍처(README-Agent.md)는 이쪽](./docs/README-Agent.md)

---

## 💻 설치 방법(소스에서 빌드)

** 필수 요구 사항 : **
- macOS 14.0 이상 (Apple Silicon 권장)
- Xcode 15.0 이상

``bash
git clone https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
open Verantyx.xcodeproj
# Verantyx 체계를 선택하고 Cmd + R을 눌러 빌드하고 실행합니다.
``

*주의: Windows/Linux로의 이식(Rust 코어 + llama.cpp)은 장기적인 로드맵에 있지만, 현재는 네이티브 macOS/MLX 아키텍처의 완성에 극도로 주력하고 있습니다. *

---

## 📖 Verantyx 정보

이 프로젝트는 이전에 룰 베이스의 심볼릭 AI를 작성하려고 했을 때에 개인에서는 만드는 것은 불가능하다고 생각해, 현재 주류의 AI의 하네스의 부분 등 제어하는 부분을 자작하는 것으로 제어하려고 생각했습니다. (당시는 openclaw가 주목을 받고 있었던 시기)
거기서 이 프로젝트의 주목적인 클라우드의 고성능 AI에 전달하기 전에 소스 코드나 사용자의 요청을 난독화하여 퍼즐과 같은 상태로 전달함으로써 정보 유출을 막는 것이 아닐까 생각해 개발을 시작했습니다.

이 프로젝트가 스타 0인 이유에 대해, 이 프로젝트에 보안 폴더가 포함되어 있었기 때문에 갑자기 개인 리포지토리로 했기 때문에, 9 있던 스타가 소멸했습니다. 완전히 부활했으므로 잘 부탁드립니다. 다른 리포지토리와 중복을 일으키는 부분을 정리했습니다. 이 리포지토리에서 릴리스를 중심으로 푸시하고 있었지만 소스 코드 업데이트가 멈추었던 것을 발견하고 업데이트했습니다.

앞으로는 모국어인 일본어를 주력으로 하고, 영어는 통상의 번역 툴에 번역시켜 일단 적재한다고 하는 운용으로 가자고 생각하고 있습니다.

---

## 🔧 리포지토리 설정 및 기록 정보

**Git 설정에 대한 알림:**
이 리포지토리의 초기 커밋은 개발자의 macOS 사용자 이름에서 파생 된 `kofdai`라는 로컬 Git 이름으로 이루어졌습니다. 2026년 5월 24일로 이 문제는 수정되었으며 현재 모든 커밋이 올바르게 `@Ag3497120`에 귀속되도록 설정되어 있습니다. 이것은 개발 환경을 설정하는 일반적인 문제이며 봇이나 자동화 도구로 인한 것이 아닙니다. 미래의 모든 기여는 올바른 저자 이름으로 기록됩니다.