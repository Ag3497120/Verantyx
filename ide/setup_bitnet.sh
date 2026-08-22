#!/bin/bash
# ============================================================
# setup_bitnet.sh — Verantyx IDE BitNet b1.58 セットアップ
# ============================================================

set -e

SUPPORT_DIR="$HOME/Library/Application Support/VerantyxIDE"
BITNET_DIR="$SUPPORT_DIR/bitnet.cpp"
MODELS_DIR="$SUPPORT_DIR/models"
BINARY_DIR="$SUPPORT_DIR/bin"
VENV_DIR="$SUPPORT_DIR/bitnet_venv"

echo "╔══════════════════════════════════════════════════════╗"
echo "║   Verantyx IDE — BitNet b1.58 セットアップ          ║"
echo "╚══════════════════════════════════════════════════════╝"
mkdir -p "$SUPPORT_DIR" "$MODELS_DIR" "$BINARY_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# ─── Step 1: cmake ────────────────────────────────────────
echo "▶ Step 1/5: cmake を確認..."
if ! command -v cmake &>/dev/null; then
    /opt/homebrew/bin/brew install cmake
fi
echo "  ✓ cmake: $(cmake --version | head -1)"

# ─── Step 2: Python venv ──────────────────────────────────
echo "▶ Step 2/5: Python venv を確認..."
PYTHON=$(/opt/homebrew/bin/brew --prefix)/bin/python3.11
if [ ! -f "$PYTHON" ]; then /opt/homebrew/bin/brew install python@3.11; fi
if [ ! -d "$VENV_DIR" ]; then $PYTHON -m venv "$VENV_DIR"; fi
source "$VENV_DIR/bin/activate"
pip install --quiet huggingface_hub numpy 2>&1 | tail -1
echo "  ✓ venv: $VENV_DIR"

# ─── Step 3: BitNet.cpp クローン & ビルド ────────────────
echo "▶ Step 3/5: BitNet.cpp ビルド..."
if [ -f "$BINARY_DIR/llama-cli" ]; then
    echo "  ✓ 既存バイナリ: $(ls -lh "$BINARY_DIR/llama-cli" | awk '{print $5}')"
else
    if [ ! -d "$BITNET_DIR" ]; then
        git clone --recursive --depth=1 https://github.com/microsoft/BitNet.git "$BITNET_DIR"
    fi
    cd "$BITNET_DIR"
    # CPU-only: Metal/Accelerate/BLAS をすべて無効化（Metal シェーダーコンパイルエラー回避）
    cmake -B build -DCMAKE_BUILD_TYPE=Release \
        -DGGML_METAL=OFF -DGGML_ACCELERATE=OFF -DGGML_BLAS=OFF 2>&1 | tail -2
    cmake --build build -j$(sysctl -n hw.ncpu) --target llama-cli 2>&1 | tail -3
    cp build/bin/llama-cli "$BINARY_DIR/llama-cli"
    chmod +x "$BINARY_DIR/llama-cli"
    echo "  ✓ llama-cli: $(ls -lh "$BINARY_DIR/llama-cli" | awk '{print $5}')"
fi

# ─── Step 4: モデルダウンロード & GGUF 変換 ─────────────
MODEL_HF_DIR="$MODELS_DIR/bitnet_b1_58-large/bitnet_b1_58-large"
MODEL_GGUF="$MODELS_DIR/bitnet_b1_58-large.gguf"

echo "▶ Step 4/5: BitNet b1.58-large モデル..."
if [ -f "$MODEL_GGUF" ]; then
    echo "  ✓ GGUF 存在: $(du -sh "$MODEL_GGUF" | cut -f1)"
else
    source "$VENV_DIR/bin/activate"
    if [ ! -d "$MODEL_HF_DIR" ] || [ -z "$(ls -A "$MODEL_HF_DIR" 2>/dev/null)" ]; then
        echo "  HuggingFace からダウンロード中 (~3GB)..."
        python3 -c "
from huggingface_hub import snapshot_download
import os
path = snapshot_download(
    repo_id='1bitLLM/bitnet_b1_58-large',
    local_dir='$MODEL_HF_DIR',
    ignore_patterns=['*.md','*.txt','*.gitattributes']
)
print(f'Downloaded to: {path}')
"
    fi
    echo "  GGUF 変換用依存ライブラリをインストール中..."
    pip install --quiet sentencepiece protobuf transformers 2>&1 | tail -1
    # torch が必要（convert_hf_to_gguf.py の依存）
    pip show torch &>/dev/null || pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
    echo "  GGUF 変換中..."
    python3 "$BITNET_DIR/3rdparty/llama.cpp/convert_hf_to_gguf.py" \
        "$MODEL_HF_DIR" --outfile "$MODEL_GGUF" --outtype f16 2>&1 | tail -5
    echo "  ✓ GGUF: $(du -sh "$MODEL_GGUF" | cut -f1)"
fi

# ─── Step 5: 設定保存 ─────────────────────────────────────
echo "▶ Step 5/5: 設定ファイル保存..."
cat > "$SUPPORT_DIR/bitnet_config.json" << CONFIGEOF
{
    "binary_path": "$BINARY_DIR/llama-cli",
    "model_path": "$MODEL_GGUF",
    "max_tokens": 256,
    "temperature": 0.05,
    "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "model_name": "bitnet_b1_58-large",
    "ner_prompt_template": "Output ONLY a JSON array of strings that are sensitive identifiers (API keys, passwords, secrets, IP addresses, tokens, credentials) in this code. No explanation.\n\nCODE:\n{CODE}\n\nJSON array:"
}
CONFIGEOF

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✅ BitNet b1.58 セットアップ完了!                  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "  バイナリ: $BINARY_DIR/llama-cli"
echo "  モデル:   $MODEL_GGUF"
