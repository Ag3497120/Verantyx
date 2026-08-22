#!/usr/bin/env bash
# =============================================================================
# package_dmg.sh — Verantyx IDE DMG パッケージ作成スクリプト
#
# 使い方: bash package_dmg.sh [version] [apple-id] [team-id] [notarytool-password]
#   例 (ad-hoc):     bash package_dmg.sh 1.0.0
#   例 (Developer ID): bash package_dmg.sh 1.0.0 you@example.com XXXXXXXXXX "app-specific-password"
#
# Developer ID 署名 + 公証を行うと Gatekeeper 警告が出なくなります。
# Apple ID のアプリ専用パスワードは https://appleid.apple.com で発行してください。
# =============================================================================
set -euo pipefail

VERSION="${1:-1.0.0}"
APPLE_ID="${2:-}"
TEAM_ID="${3:-}"
NOTARY_PASS="${4:-}"

SCHEME="Verantyx"
CONFIGURATION="Release"
APP_NAME="Verantyx"
DMG_NAME="VerantyxIDE-${VERSION}"
DIST_DIR="$(pwd)/dist"
STAGING_DIR="$(pwd)/dist/.staging"

echo "▶ Verantyx IDE パッケージ作成 v${VERSION}"
echo "================================================"

# ── Detect signing mode ─────────────────────────────────────────────────────
DEV_ID_CERT=$(security find-identity -v -p codesigning 2>/dev/null | grep "Developer ID Application" | head -1 | grep -oE '"Developer ID Application: [^"]+?"' | tr -d '"' || echo "")

if [ -n "$DEV_ID_CERT" ]; then
  echo "✓ Developer ID cert: $DEV_ID_CERT"
  SIGN_MODE="developer_id"
  SIGN_IDENTITY="$DEV_ID_CERT"
else
  echo "⚠️  No Developer ID cert found — using ad-hoc signing"
  SIGN_MODE="adhoc"
  SIGN_IDENTITY="-"
fi

# ── 1. Clean ────────────────────────────────────────────────────────────────
echo "[1/7] クリーンアップ..."
rm -rf "$STAGING_DIR" "$DIST_DIR/${DMG_NAME}.dmg"
mkdir -p "$STAGING_DIR"

# ── 2. Build Release ────────────────────────────────────────────────────────
echo "[2/7] Release ビルド中..."

# LaunchServices のキャッシュバグ（古いアプリが起動する問題）を回避するため、
# ビルドごとに CFBundleVersion (ビルド番号) を一意のタイムスタンプに更新する
BUILD_NUMBER=$(date +%s)
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NUMBER" "$(pwd)/Sources/Verantyx/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString ${VERSION}" "$(pwd)/Sources/Verantyx/Info.plist"
echo "   Version (CFBundleShortVersionString) set to: ${VERSION}"
echo "   Build Number (CFBundleVersion) set to: $BUILD_NUMBER"

if [ "$SIGN_MODE" = "developer_id" ]; then
  # Extract team ID directly from the Developer ID cert
  DEV_ID_TEAM=$(echo "$DEV_ID_CERT" | grep -oE '\([A-Z0-9]{10}\)' | tr -d '()')
  echo "   Team ID (from cert): $DEV_ID_TEAM"
  xcodebuild \
    -scheme "$SCHEME" \
    -configuration "$CONFIGURATION" \
    -destination "platform=macOS" \
    MARKETING_VERSION="${VERSION}" \
    CURRENT_PROJECT_VERSION="$BUILD_NUMBER" \
    CODE_SIGN_STYLE="Manual" \
    CODE_SIGN_IDENTITY="$DEV_ID_CERT" \
    DEVELOPMENT_TEAM="$DEV_ID_TEAM" \
    CODE_SIGNING_REQUIRED=YES \
    OTHER_CODE_SIGN_FLAGS="--timestamp" \
    SYMROOT="$(pwd)/build" \
    build 2>&1 | grep -E "error:|warning:|SUCCEEDED|FAILED" | tail -10
else
  xcodebuild \
    -scheme "$SCHEME" \
    -configuration "$CONFIGURATION" \
    -destination "platform=macOS" \
    MARKETING_VERSION="${VERSION}" \
    CURRENT_PROJECT_VERSION="$BUILD_NUMBER" \
    CODE_SIGN_STYLE="Manual" \
    CODE_SIGN_IDENTITY="-" \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGNING_ALLOWED=NO \
    SYMROOT="$(pwd)/build" \
    build 2>&1 | grep -E "error:|warning:|SUCCEEDED|FAILED" | tail -10
fi

# ── 3. Find .app ────────────────────────────────────────────────────────────
echo "[3/7] .app バンドルを探索..."
APP_PATH="$(pwd)/build/${CONFIGURATION}/${APP_NAME}.app"
if [ ! -d "$APP_PATH" ]; then
  echo "❌ Error: ${APP_PATH} が見つかりません"
  exit 1
fi
echo "   Found: $APP_PATH"

# Verify icon is present
if [ -f "$APP_PATH/Contents/Resources/AppIcon.icns" ]; then
  echo "   ✓ AppIcon.icns included"
else
  echo "   ⚠️  AppIcon.icns not found in bundle"
fi

# ── 4. Copy to staging ──────────────────────────────────────────────────────
echo "[4/7] ステージングにコピー..."
cp -R "$APP_PATH" "$STAGING_DIR/${APP_NAME}.app"
xattr -cr "$STAGING_DIR/${APP_NAME}.app" 2>/dev/null || true

# Portable DMG: refuse to ship without a real vera-memory Mach-O.
VERA_MEMORY_BIN="$STAGING_DIR/${APP_NAME}.app/Contents/MacOS/vera-memory"
if [ ! -f "$VERA_MEMORY_BIN" ] || ! file "$VERA_MEMORY_BIN" | grep -q "Mach-O"; then
  echo "❌ vera-memory missing or not Mach-O in staged app ($VERA_MEMORY_BIN)"
  echo "   Ensure Vendor/vera-memory exists and the embed build phase ran."
  exit 1
fi
echo "   ✓ vera-memory embedded ($(du -h "$VERA_MEMORY_BIN" | awk '{print $1}'))"

# ── 5. Sign ─────────────────────────────────────────────────────────────────
echo "[5/7] 署名中 (${SIGN_MODE})..."
ENTITLEMENTS="$(pwd)/Sources/Verantyx/Verantyx.entitlements"
PYI_ENTITLEMENTS="$(pwd)/Sources/Verantyx/PyInstallerHelper.entitlements"
sign_nested() {
  local identity="$1"
  local runtime_opts=()
  if [ "$identity" != "-" ]; then
    runtime_opts=(--options runtime --timestamp)
  fi
  while IFS= read -r bin; do
    local base ents=()
    base="$(basename "$bin")"
    case "$base" in
      vera-memory|jgen_forge)
        if [ -f "$PYI_ENTITLEMENTS" ]; then
          ents=(--entitlements "$PYI_ENTITLEMENTS")
        fi
        ;;
      *)
        if [ -f "$ENTITLEMENTS" ] && [ "$identity" != "-" ]; then
          ents=(--entitlements "$ENTITLEMENTS")
        fi
        ;;
    esac
    codesign --force --sign "$identity" "${runtime_opts[@]}" "${ents[@]}" "$bin" 2>/dev/null || \
      codesign --force --sign "$identity" "${runtime_opts[@]}" "$bin" 2>/dev/null || true
  done < <(find "$STAGING_DIR/${APP_NAME}.app/Contents" -type f \( -perm -111 -o -name "*.dylib" -o -name "*.so" \) 2>/dev/null)
}

if [ "$SIGN_MODE" = "developer_id" ]; then
  if [ ! -f "$PYI_ENTITLEMENTS" ]; then
    echo "❌ PyInstallerHelper.entitlements missing — notarized vera-memory would fail to launch"
    exit 1
  fi
  # Sign nested first (no --deep) so PyInstaller helpers keep disable-library-validation.
  sign_nested "$SIGN_IDENTITY"
  codesign --force --sign "$SIGN_IDENTITY" \
    --options runtime \
    --timestamp \
    --entitlements "$ENTITLEMENTS" \
    "$STAGING_DIR/${APP_NAME}.app"
  if ! codesign -d --entitlements :- "$VERA_MEMORY_BIN" 2>/dev/null | grep -q "disable-library-validation"; then
    echo "❌ vera-memory missing disable-library-validation after signing"
    exit 1
  fi
  echo "   ✓ Developer ID 署名完了 (vera-memory/jgen_forge: PyInstaller entitlements)"
else
  sign_nested "-"
  codesign --force --sign "-" \
    "$STAGING_DIR/${APP_NAME}.app" 2>/dev/null || true
  echo "   ✓ Ad-hoc 署名完了 (初回起動時に右クリック→開く が必要)"
fi

# ── 6. Notarize (Developer ID only) ─────────────────────────────────────────
if [ "$SIGN_MODE" = "developer_id" ] && [ -n "$APPLE_ID" ] && [ -n "$NOTARY_PASS" ]; then
  echo "[6/7] Apple への公証（Notarization）中..."
  # Create a temp zip for notarization
  ditto -c -k --keepParent "$STAGING_DIR/${APP_NAME}.app" "/tmp/${APP_NAME}_notarize.zip"
  
  xcrun notarytool submit "/tmp/${APP_NAME}_notarize.zip" \
    --apple-id "$APPLE_ID" \
    --team-id "${TEAM_ID:-NC46WGQVFP}" \
    --password "$NOTARY_PASS" \
    --wait
  
  # Staple the ticket
  xcrun stapler staple "$STAGING_DIR/${APP_NAME}.app"
  rm -f "/tmp/${APP_NAME}_notarize.zip"
  echo "   ✓ 公証完了 — Gatekeeper 警告なしで起動できます"
else
  echo "[6/7] 公証スキップ (Developer ID + Apple ID が必要)"
fi

# ── 7. Create DMG Installer ────────────────────────────────────────────────
echo "[7/7] DMG インストーラーを作成中..."
mkdir -p "$DIST_DIR"
DMG_FINAL_NAME="VerantyxIDE-${VERSION}.dmg"

# Create a temporary source folder for hdiutil
mkdir -p "$STAGING_DIR/dmg_root"
mv "$STAGING_DIR/${APP_NAME}.app" "$STAGING_DIR/dmg_root/"
ln -s /Applications "$STAGING_DIR/dmg_root/Applications"

hdiutil create -volname "${APP_NAME}" \
               -srcfolder "$STAGING_DIR/dmg_root" \
               -ov \
               -format UDZO \
               "$DIST_DIR/$DMG_FINAL_NAME" > /dev/null

rm -rf "$STAGING_DIR"

# ── Done ────────────────────────────────────────────────────────────────────
PKG_SIZE=$(du -sh "$DIST_DIR/${DMG_FINAL_NAME}" | cut -f1)
echo ""
echo "================================================"
echo "✅ 完了!"
echo "   出力: dist/${DMG_FINAL_NAME} (${PKG_SIZE})"
echo "   署名: ${SIGN_MODE}"
echo ""

if [ "$SIGN_MODE" = "adhoc" ]; then
  echo "📌 Gatekeeper を回避するには（ユーザー側の操作）:"
  echo "   初回起動: Finder で右クリック → 「開く」"
  echo "   または: xattr -d com.apple.quarantine /Applications/${APP_NAME}.app"
  echo ""
  echo "💡 Gatekeeper 警告を完全になくすには:"
  echo "   Developer ID 証明書が必要です:"
  echo "   1. https://developer.apple.com/account/ → Certificates"
  echo "   2. 「Developer ID Application」証明書を作成・インストール"
  echo "   3. アプリ専用パスワードを https://appleid.apple.com で発行"
  echo "   4. bash package_dmg.sh ${VERSION} you@apple.com TEAMID app-specific-pass"
fi

echo ""
echo "📌 GitHub Release に添付:"
echo "   gh release create v${VERSION} dist/${DMG_FINAL_NAME} --repo verantyx/verantyx"
echo "================================================"
