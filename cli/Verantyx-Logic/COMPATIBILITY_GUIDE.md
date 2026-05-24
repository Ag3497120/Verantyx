# Verantyx Compatibility & Hardware Guide

Verantyx is designed to be **lightweight, portable, and GPU-free**.
Unlike Large Language Models (LLMs) that require massive VRAM and expensive GPUs, Verantyx runs efficiently on standard CPUs.

---

## 🚀 Key Advantage: CPU-Only Inference

**Verantyx does NOT require a GPU.**

Because Verantyx uses **Symbolic Reasoning** (Truth Tables, Kripke Semantics, Logic Puzzles) rather than Neural Networks, it operates entirely on the CPU. This makes it accessible on:

- ✅ Standard Laptops (MacBook Air, Surface, etc.)
- ✅ Cheap Cloud Instances (AWS t2.micro, Google Colab CPU tier)
- ✅ Edge Devices (Raspberry Pi 4/5, Jetson)
- ✅ Legacy Hardware (Older PCs)

---

## 🖥 System Requirements

| Component | Minimum Requirement | Recommended |
| :--- | :--- | :--- |
| **OS** | Windows, macOS, Linux | Linux (Ubuntu 20.04+) or macOS |
| **CPU** | Any x86_64 or ARM64 CPU | Multi-core (4+ cores) for parallel solving |
| **RAM** | 2 GB | 8 GB+ (for large Knowledge Base loading) |
| **Disk** | 500 MB | 1 GB (SSD recommended for DB access) |
| **GPU** | **None** | **None** (Not used) |
| **Python** | 3.10 | 3.13 |

---

## 🌍 Verified Platforms

We have confirmed Verantyx runs successfully on the following environments:

### 🍎 macOS
- **Apple Silicon (M1/M2/M3)**: Native support. Extremely fast due to high single-core performance.
- **Intel Mac**: Supported.

### 🪟 Windows
- **Windows 10/11**: Supported via standard Python installation or WSL2.
- **PowerShell / CMD**: Fully supported.

### 🐧 Linux
- **Ubuntu / Debian**: Native support. Ideal for servers.
- **Google Colab (Free Tier)**: Works perfectly without connecting to a GPU runtime.

---

## ⚡ Performance Characteristics

- **Startup Time**: < 1 second (Instant DB mapping).
- **Inference Speed**: Milliseconds for propositional logic; < 10 seconds for complex modal logic searches.
- **Memory Footprint**: The binary model (`verantyx_model.bin`) is ~120MB. Runtime memory usage depends on the size of the loaded Knowledge Base but typically stays under 1GB.

---

## ❓ FAQ

**Q: Can I use a GPU to speed it up?**
A: No. Since the logic is symbolic (discrete mathematics), GPUs do not provide an advantage. Verantyx is optimized for CPU logic operations.

**Q: Does it work offline?**
A: **Yes.** Once installed, Verantyx requires no internet connection. All logic solvers and the Knowledge Base are embedded locally.

**Q: Can I run it on a Raspberry Pi?**
A: Yes. As long as you can install Python 3.10+, Verantyx will run. It's perfect for offline logic verification on edge devices.

---
---

# 対応機種・動作環境ガイド

Verantyx は **軽量・ポータブル・GPU不要** を設計思想としています。
大量の VRAM を必要とする大規模言語モデル（LLM）とは異なり、Verantyx は一般的な CPU 環境で効率的に動作します。

---

## 🚀 最大の利点：CPU のみで推論可能

**Verantyx は GPU を一切必要としません。**

Verantyx はニューラルネットワークではなく、**記号推論（Symbolic Reasoning）**（真理値表、クリプケ意味論、論理パズル）を使用するため、すべての計算は CPU 上で行われます。
そのため、以下の環境でも快適に動作します。

- ✅ 一般的なノートPC（MacBook Air, Surface など）
- ✅ 安価なクラウドインスタンス（AWS t2.micro, Google Colab CPU枠）
- ✅ エッジデバイス（Raspberry Pi 4/5, Jetson）
- ✅ 古いPCハードウェア

---

## 🖥 システム要件

| コンポーネント | 最小要件 | 推奨環境 |
| :--- | :--- | :--- |
| **OS** | Windows, macOS, Linux | Linux (Ubuntu 20.04+) または macOS |
| **CPU** | 任意の x86_64 / ARM64 | 並列ソルバー用のマルチコア (4コア以上) |
| **メモリ (RAM)** | 2 GB | 8 GB以上 (大規模な知識ベース展開用) |
| **ディスク** | 500 MB | 1 GB (DBアクセスのためSSD推奨) |
| **GPU** | **不要** | **不要** (使用しません) |
| **Python** | 3.10 | 3.13 |

---

## 🌍 動作確認済みプラットフォーム

以下の環境での動作を確認しています。

### 🍎 macOS
- **Apple Silicon (M1/M2/M3)**: ネイティブ動作。シングルコア性能が高いため非常に高速です。
- **Intel Mac**: 動作確認済み。

### 🪟 Windows
- **Windows 10/11**: 標準の Python または WSL2 で動作します。
- **PowerShell / CMD**: 完全対応。

### 🐧 Linux
- **Ubuntu / Debian**: ネイティブ動作。サーバー用途に最適です。
- **Google Colab (無料枠)**: GPU ランタイムに接続せずに動作します。

---

## ⚡ パフォーマンス特性

- **起動時間**: 1秒未満（DBマッピングは一瞬です）。
- **推論速度**: 命題論理ならミリ秒単位。複雑な様相論理探索でも数秒以内。
- **メモリ使用量**: バイナリモデル (`verantyx_model.bin`) は約 120MB です。実行時のメモリ消費は通常 1GB 未満に収まります。

---

## ❓ よくある質問 (FAQ)

**Q: GPU を使えば速くなりますか？**
A: いいえ。論理演算は離散数学的な処理であり、GPU の並列演算の恩恵を受けにくいため、CPU 向けに最適化されています。

**Q: オフラインで動きますか？**
A: **はい。** インストール後はインターネット接続を必要としません。すべてのソルバーと知識ベースはローカルに内蔵されています。

**Q: Raspberry Pi で動きますか？**
A: はい。Python 3.10 以上が動く環境であれば動作します。オフラインでの論理検証デバイスとしても最適です。
