#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# rebuild.sh — verantyx-browser (Rust) をビルドし、
#              VerantyxIDE をビルドして再起動する
# 使い方: bash rebuild.sh [--release]
# ─────────────────────────────────────────────────────────────────

set -e
export PATH="$PATH:/opt/homebrew/bin:$HOME/.cargo/bin"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BROWSER_DIR="$SCRIPT_DIR/verantyx-browser"
RESOURCES_DIR="$SCRIPT_DIR/Resources"

CONFIGURATION="Debug"
CARGO_FLAGS=""
if [[ "$1" == "--release" ]]; then
  CONFIGURATION="Release"
  CARGO_FLAGS="--release"
fi

APP_PATH="/Users/motonishikoudai/Library/Developer/Xcode/DerivedData/Verantyx-bpyayjzaotjnfcehmawblbjjzwdn/Build/Products/$CONFIGURATION/Verantyx.app"

# ── Step 1: verantyx-browser (Rust) ────────────────────────────────────────
echo "🦀 verantyx-browser をビルド中 ($CONFIGURATION)..."
cargo build $CARGO_FLAGS \
  --manifest-path "$BROWSER_DIR/Cargo.toml" \
  -p vx-browser

if [[ "$CONFIGURATION" == "Release" ]]; then
  BUILT_BIN="$BROWSER_DIR/target/release/verantyx-browser"
else
  BUILT_BIN="$BROWSER_DIR/target/debug/verantyx-browser"
fi

# Resources/ にコピー（Xcode がバンドルに取り込む）
mkdir -p "$RESOURCES_DIR"
cp -f "$BUILT_BIN" "$RESOURCES_DIR/verantyx-browser"
echo "✅ verantyx-browser → Resources/verantyx-browser"

# ── Step 2: Swift アプリ ──────────────────────────────────────────────────
echo "🔨 Verantyx をビルド中..."
xcodebuild \
  -project "$SCRIPT_DIR/Verantyx.xcodeproj" \
  -scheme Verantyx \
  -configuration "$CONFIGURATION" \
  -destination 'platform=macOS,arch=arm64' \
  CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO \
  build 2>&1 | grep -E "error:|warning:|BUILD SUCCEEDED|BUILD FAILED" \
            | grep -v "objc\|deprecated" || true

echo "✅ ビルド完了 ($CONFIGURATION)"

# ── Step 3: 再起動 ────────────────────────────────────────────────────────
echo "🔄 旧プロセスを終了中..."
pkill -x Verantyx 2>/dev/null || true
sleep 0.5

echo "🚀 起動中..."
open "$APP_PATH"
echo "✨ Verantyx が再起動しました"
