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
# Branch workflow_dispatch passes names like fix/jgen-act-compile-ci; those
# must not become path components in dist/VerantyxIDE-fix/....dmg.
VERSION="$(printf '%s' "$VERSION" | tr '/ ' '--' | tr -cd 'A-Za-z0-9._-')"
if [ -z "$VERSION" ]; then
  VERSION="0.0.0-dev"
fi
# Prefer CLI args; fall back to env so passwords are not required on argv.
APPLE_ID="${2:-${APPLE_ID:-}}"
TEAM_ID="${3:-${APPLE_TEAM_ID:-}}"
NOTARY_PASS="${4:-${APPLE_APP_SPECIFIC_PASSWORD:-}}"

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
  DEV_ID_TEAM=$(echo "$DEV_ID_CERT" | grep -oE '\([A-Z0-9]{10}\)' | tr -d '()')
  echo "   Team ID (from cert): $DEV_ID_TEAM"
else
  echo "⚠️  No Developer ID cert found — using ad-hoc signing"
  SIGN_MODE="adhoc"
  SIGN_IDENTITY="-"
  DEV_ID_TEAM=""
fi

# ── 1. Clean ────────────────────────────────────────────────────────────────
echo "[1/7] クリーンアップ..."
rm -rf "$STAGING_DIR" "$DIST_DIR/${DMG_NAME}.dmg"
mkdir -p "$STAGING_DIR"

# ── 2. Build Release ────────────────────────────────────────────────────────
echo "[2/7] Release ビルド中..."
# Always build without Xcode codesign, then apply Developer ID / ad-hoc in
# step 5. Manual Xcode signing often fails on CI/local without profiles.
BUILD_LOG="$(mktemp -t verantyx-xcodebuild)"
set +e
xcodebuild \
  -project "VerantyxIDE/Verantyx.xcodeproj" \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -destination "platform=macOS,arch=arm64" \
  CODE_SIGN_STYLE="Manual" \
  CODE_SIGN_IDENTITY="-" \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGNING_ALLOWED=NO \
  MARKETING_VERSION="${VERSION}" \
  CURRENT_PROJECT_VERSION="${VERSION}" \
  BUILD_DIR="$(pwd)/build" \
  build >"$BUILD_LOG" 2>&1
BUILD_STATUS=$?
set -e
grep -E "error:|warning:|SUCCEEDED|FAILED" "$BUILD_LOG" | tail -40 || true
if [ "$BUILD_STATUS" -ne 0 ]; then
  echo "──── xcodebuild errors ────"
  grep -E "error:" "$BUILD_LOG" || true
  tail -60 "$BUILD_LOG" || true
  rm -f "$BUILD_LOG"
  exit "$BUILD_STATUS"
fi
rm -f "$BUILD_LOG"

# ── 3. Find .app ────────────────────────────────────────────────────────────
echo "[3/7] .app バンドルを探索..."
APP_PATH=$(find "$(pwd)/build" -name "${APP_NAME}.app" -maxdepth 8 | head -1)
if [ -z "$APP_PATH" ]; then
  echo "❌ Error: ${APP_NAME}.app が見つかりません"
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

# git-lfs pointer / text stubs break deep codesign + Gatekeeper.
BROWSER_BIN="$STAGING_DIR/${APP_NAME}.app/Contents/MacOS/verantyx-browser"
if [ -f "$BROWSER_BIN" ] && ! file "$BROWSER_BIN" | grep -q "Mach-O"; then
  echo "   ⚠️  Removing non-Mach-O verantyx-browser ($(wc -c < "$BROWSER_BIN") bytes) — rebuild browser binary later"
  rm -f "$BROWSER_BIN"
fi

# Portable DMG requirement: vera-memory must be a real Mach-O inside the
# shipped .app. Missing / LFS-pointer stubs make MCP fail on every fresh Mac.
VERA_MEMORY_BIN="$STAGING_DIR/${APP_NAME}.app/Contents/MacOS/vera-memory"
if [ ! -f "$VERA_MEMORY_BIN" ]; then
  echo "❌ vera-memory missing from app bundle ($VERA_MEMORY_BIN)"
  echo "   Ensure VerantyxIDE/Vendor/vera-memory exists and the Xcode"
  echo "   'Embed vera-memory into App Bundle' build phase ran."
  exit 1
fi
if ! file "$VERA_MEMORY_BIN" | grep -q "Mach-O"; then
  echo "❌ vera-memory is not a Mach-O binary ($(wc -c < "$VERA_MEMORY_BIN") bytes)"
  echo "   Refusing to ship a non-runnable stub in the DMG."
  exit 1
fi
echo "   ✓ vera-memory embedded ($(du -h "$VERA_MEMORY_BIN" | awk '{print $1}'))"

# Stamp a discoverable version so users can tell which CI DMG they installed
# (xcodebuild MARKETING_VERSION alone often leaves Info.plist at the scheme default).
INFO_PLIST="$STAGING_DIR/${APP_NAME}.app/Contents/Info.plist"
if [ -f "$INFO_PLIST" ]; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString ${VERSION}" "$INFO_PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string ${VERSION}" "$INFO_PLIST"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${VERSION}" "$INFO_PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string ${VERSION}" "$INFO_PLIST"
  echo "   ✓ Info.plist version → ${VERSION}"
fi

# ── 5. Sign ─────────────────────────────────────────────────────────────────
echo "[5/7] 署名中 (${SIGN_MODE})..."
ENTITLEMENTS="$(pwd)/VerantyxIDE/Sources/Verantyx/Verantyx.entitlements"
PYI_ENTITLEMENTS="$(pwd)/VerantyxIDE/Sources/Verantyx/PyInstallerHelper.entitlements"
if [ ! -f "$ENTITLEMENTS" ]; then
  ENTITLEMENTS="$(pwd)/Sources/Verantyx/Verantyx.entitlements"
fi
if [ ! -f "$PYI_ENTITLEMENTS" ]; then
  PYI_ENTITLEMENTS="$(pwd)/Sources/Verantyx/PyInstallerHelper.entitlements"
fi
# PyInstaller onefile helpers need disable-library-validation under Hardened
# Runtime; applying the main app entitlements alone breaks them on every Mac.
sign_one() {
  local bin="$1"
  local ents="$2"
  local base
  base="$(basename "$bin")"
  if [ -z "$ents" ] || [ ! -f "$ents" ]; then
    codesign --force --sign "$SIGN_IDENTITY" --options runtime --timestamp "$bin"
    return
  fi
  if codesign --force --sign "$SIGN_IDENTITY" \
      --options runtime \
      --timestamp \
      --entitlements "$ents" \
      "$bin"; then
    echo "   signed $base (+ $(basename "$ents"))"
  else
    echo "   ⚠️  entitlements sign failed for $base — retrying without entitlements"
    codesign --force --sign "$SIGN_IDENTITY" --options runtime --timestamp "$bin"
  fi
}

if [ "$SIGN_MODE" = "developer_id" ]; then
  if [ ! -f "$ENTITLEMENTS" ]; then
    echo "❌ entitlements not found (looked under VerantyxIDE/Sources and Sources)"
    exit 1
  fi
  if [ ! -f "$PYI_ENTITLEMENTS" ]; then
    echo "❌ PyInstallerHelper.entitlements not found — vera-memory would fail on notarized installs"
    exit 1
  fi
  # Sign nested Mach-Os first (helpers with PyInstaller entitlements), then the bundle.
  while IFS= read -r bin; do
    base="$(basename "$bin")"
    case "$base" in
      vera-memory|jgen_forge)
        sign_one "$bin" "$PYI_ENTITLEMENTS"
        ;;
      *)
        sign_one "$bin" "$ENTITLEMENTS"
        ;;
    esac
  done < <(find "$STAGING_DIR/${APP_NAME}.app/Contents" -type f \( -perm -111 -o -name "*.dylib" -o -name "*.so" \) 2>/dev/null)
  codesign --force --sign "$SIGN_IDENTITY" \
    --options runtime \
    --timestamp \
    --entitlements "$ENTITLEMENTS" \
    "$STAGING_DIR/${APP_NAME}.app"
  codesign --verify --deep --strict --verbose=2 "$STAGING_DIR/${APP_NAME}.app"
  # Confirm the helper kept the library-validation entitlement (catches regressions).
  if ! codesign -d --entitlements :- "$VERA_MEMORY_BIN" 2>/dev/null | grep -q "disable-library-validation"; then
    echo "❌ vera-memory missing com.apple.security.cs.disable-library-validation after signing"
    codesign -d --entitlements :- "$VERA_MEMORY_BIN" 2>&1 || true
    exit 1
  fi
  echo "   ✓ Developer ID 署名完了 (vera-memory/jgen_forge: PyInstaller entitlements)"
else
  # Ad-hoc: sign nested binaries first (no --deep), then seal the bundle so
  # helper entitlements are not overwritten / leave the outer seal stale.
  while IFS= read -r bin; do
    base="$(basename "$bin")"
    case "$base" in
      vera-memory|jgen_forge)
        if [ -f "$PYI_ENTITLEMENTS" ]; then
          codesign --force --sign "-" --entitlements "$PYI_ENTITLEMENTS" "$bin" 2>/dev/null || \
            codesign --force --sign "-" "$bin" 2>/dev/null || true
        else
          codesign --force --sign "-" "$bin" 2>/dev/null || true
        fi
        ;;
      *)
        codesign --force --sign "-" "$bin" 2>/dev/null || true
        ;;
    esac
  done < <(find "$STAGING_DIR/${APP_NAME}.app/Contents" -type f \( -perm -111 -o -name "*.dylib" -o -name "*.so" \) 2>/dev/null)
  codesign --force --sign "-" "$STAGING_DIR/${APP_NAME}.app" 2>/dev/null || true
  echo "   ✓ Ad-hoc 署名完了 (初回起動時に右クリック→開く が必要)"
fi

# ── 6. Notarize (Developer ID only) ─────────────────────────────────────────
if [ "$SIGN_MODE" = "developer_id" ] && [ -n "$APPLE_ID" ] && [ -n "$NOTARY_PASS" ]; then
  echo "[6/7] Apple への公証（Notarization）中..."
  # Create a temp zip for notarization
  ditto -c -k --keepParent "$STAGING_DIR/${APP_NAME}.app" "/tmp/${APP_NAME}_notarize.zip"
  
  xcrun notarytool submit "/tmp/${APP_NAME}_notarize.zip" \
    --apple-id "$APPLE_ID" \
    --team-id "${TEAM_ID:-$DEV_ID_TEAM}" \
    --password "$NOTARY_PASS" \
    --wait
  
  # Staple the ticket
  xcrun stapler staple "$STAGING_DIR/${APP_NAME}.app"
  rm -f "/tmp/${APP_NAME}_notarize.zip"
  echo "   ✓ 公証完了 — Gatekeeper 警告なしで起動できます"
else
  echo "[6/7] 公証スキップ (Developer ID + Apple ID が必要)"
fi

# ── 7. Create DMG ───────────────────────────────────────────────────────────
echo "[7/7] DMG を作成中..."
mkdir -p "$DIST_DIR"
rm -f "$DIST_DIR/${DMG_NAME}.dmg" "$DIST_DIR/${DMG_NAME}.zip"

DMG_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/verantyx-dmg.XXXXXX")"
cp -R "$STAGING_DIR/${APP_NAME}.app" "$DMG_ROOT/${APP_NAME}.app"
ln -sf /Applications "$DMG_ROOT/Applications"
# Sonoma+: immutable flags inside the bundle can make hdiutil fail oddly.
chflags -R nouchg "$DMG_ROOT" 2>/dev/null || true
xattr -cr "$DMG_ROOT" 2>/dev/null || true
sync

# Write the image under TMPDIR first (more reliable on GHA runners than
# creating straight into the workspace), then move into dist/.
TMP_DMG="$(mktemp "${TMPDIR:-/tmp}/verantyx-out.XXXXXX").dmg"
rm -f "$TMP_DMG"
DMG_OK=0
for attempt in 1 2 3 4 5; do
  echo "   hdiutil create attempt ${attempt}/5..."
  if hdiutil create \
    -volname "Verantyx IDE ${VERSION}" \
    -srcfolder "$DMG_ROOT" \
    -ov \
    -format UDZO \
    -imagekey zlib-level=9 \
    "$TMP_DMG"
  then
    DMG_OK=1
    break
  fi
  echo "   ⚠️  hdiutil failed (attempt ${attempt}); sync + backoff..."
  sync
  sleep $((attempt * 3))
done

if [ "$DMG_OK" -eq 1 ]; then
  mv -f "$TMP_DMG" "$DIST_DIR/${DMG_NAME}.dmg"
else
  rm -f "$TMP_DMG"
  echo "⚠️  DMG creation failed after retries — falling back to ZIP artifact"
  ditto -c -k --keepParent "$STAGING_DIR/${APP_NAME}.app" "$DIST_DIR/${DMG_NAME}.zip"
  if [ ! -f "$DIST_DIR/${DMG_NAME}.zip" ]; then
    echo "❌ ZIP fallback also failed"
    ls -la "$DMG_ROOT" || true
    ls -la "$DIST_DIR" || true
    rm -rf "$DMG_ROOT" "$STAGING_DIR"
    exit 1
  fi
fi

rm -rf "$DMG_ROOT" "$STAGING_DIR"

# ── Done ────────────────────────────────────────────────────────────────────
if [ -f "$DIST_DIR/${DMG_NAME}.dmg" ]; then
  OUT_FILE="$DIST_DIR/${DMG_NAME}.dmg"
elif [ -f "$DIST_DIR/${DMG_NAME}.zip" ]; then
  OUT_FILE="$DIST_DIR/${DMG_NAME}.zip"
else
  echo "❌ No package artifact produced"
  exit 1
fi
DMG_SIZE=$(du -sh "$OUT_FILE" | cut -f1)
echo ""
echo "================================================"
echo "✅ 完了!"
echo "   出力: $(basename "$OUT_FILE") (${DMG_SIZE})"
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
echo "   gh release create v${VERSION} dist/${DMG_NAME}.dmg --repo Ag3497120/Verantyx"
echo "================================================"
