# Verantyx Setup Guide

This document provides detailed instructions on how to download, install, and run the Verantyx Symbolic Logic Reasoner.

---

## English Guide

### 1. Prerequisites
Before setting up Verantyx, ensure your system meets the following requirements:
- **Python 3.10 or higher** (Python 3.13 is highly recommended).
- **pip** (Python package manager).
- Basic knowledge of command-line interfaces.

### 2. Download Methods
You can obtain Verantyx and its model weights (Knowledge Base) from our Hugging Face repository.

#### Method A: Git Clone (Recommended)
This method clones the entire repository including the source code and configuration.
```bash
git clone https://huggingface.co/your-id/verantyx
cd verantyx
```

#### Method B: Manual Download
If you prefer not to use Git, manually download the following essential files:
- `verantyx_model.bin`: The core binary-packed Knowledge Base.
- `verantyx_engine.py`: The model loader script.
- `config.json`: Hugging Face model configuration.
- `phase17_ui_server.py`: The web interface server.
- The `avh_math/` directory: Contains the internal reasoning logic.
- The `phase17_static/` directory: Contains the web UI assets.

### 3. Installation
Navigate to the root directory of the project and install the necessary Python dependencies:
```bash
pip install fastapi uvicorn anyio
```
*Note: If you plan to use the database export tools, you may also need `pip install torch safetensors`.*

### 4. Starting the Web UI Server
Verantyx provides a powerful 3D visualization and solver interface. To start the server, execute the following command in your terminal:

```bash
python3 phase17_ui_server.py \
  --kb avh_math/db/foundation_kb.jsonl \
  --offsets avh_math/db/kb_offsets.json \
  --index avh_math/db/kb_index.json \
  --graph avh_math/db/boundary_graph.json \
  --meta avh_math/db/kb_meta.json \
  --static-dir phase17_static \
  --port 8787
```

Once the server is running, open your web browser and go to:
**http://127.0.0.1:8787**

### 5. Programmatic Usage
You can also integrate the Verantyx engine directly into your Python projects as a library:

```python
from verantyx_engine import VerantyxModel

# Load the model from the local directory
model = VerantyxModel.from_pretrained("./")

# Solve a logical problem
# The engine will structurally analyze the sentence and perform verification
result = model.solve("Is []p -> [][]p always true in transitive frames?")
print(result)
```

---

## 日本語ガイド

### 1. 必要条件
Verantyx をセットアップする前に、システムが以下の要件を満たしていることを確認してください。
- **Python 3.10 以上** (Python 3.13 を強く推奨)。
- **pip** (Python パッケージマネージャー)。
- コマンドライン操作の基礎知識。

### 2. ダウンロード方法
Verantyx とそのモデル重み（知識ベース）は、Hugging Face リポジトリから取得できます。

#### 方法 A: Git Clone (推奨)
この方法では、ソースコードと設定を含むリポジトリ全体を複製します。
```bash
git clone https://huggingface.co/your-id/verantyx
cd verantyx
```

#### 方法 B: 手動ダウンロード
Git を使用しない場合は、以下の必須ファイルを手動でダウンロードしてください。
- `verantyx_model.bin`: バイナリパックされたコア知識ベース。
- `verantyx_engine.py`: モデルロード用スクリプト。
- `config.json`: Hugging Face モデル設定ファイル。
- `phase17_ui_server.py`: ウェブインターフェースサーバー。
- `avh_math/` ディレクトリ: 内部の推論ロジックが含まれます。
- `phase17_static/` ディレクトリ: ウェブUIの資産が含まれます。

### 3. インストール
プロジェクトのルートディレクトリに移動し、必要な Python 依存関係をインストールします。
```bash
pip install fastapi uvicorn anyio
```
*注意: データベースのエクスポートツールを使用する場合は、`pip install torch safetensors` も必要になる場合があります。*

### 4. ウェブ UI サーバーの起動
Verantyx は強力な 3D 可視化およびソルバーインターフェースを提供します。サーバーを起動するには、ターミナルで以下のコマンドを実行してください。

```bash
python3 phase17_ui_server.py \
  --kb avh_math/db/foundation_kb.jsonl \
  --offsets avh_math/db/kb_offsets.json \
  --index avh_math/db/kb_index.json \
  --graph avh_math/db/boundary_graph.json \
  --meta avh_math/db/kb_meta.json \
  --static-dir phase17_static \
  --port 8787
```

サーバーが起動したら、ブラウザを開いて以下のURLにアクセスしてください。
**http://127.0.0.1:8787**

### 5. プログラムからの利用
Verantyx エンジンをライブラリとして Python プロジェクトに直接組み込むことも可能です。

```python
from verantyx_engine import VerantyxModel

# ローカルディレクトリからモデルをロード
model = VerantyxModel.from_pretrained("./")

# 論理問題を解く
# エンジンが文章を構造的に解析し、検証を実行します
result = model.solve("Is []p -> [][]p always true in transitive frames?")
print(result)
```

---

## Support / サポート
If you encounter any issues, please open an issue on our Hugging Face or GitHub repository.
問題が発生した場合は、Hugging Face または GitHub リポジトリの Issue を作成してください。