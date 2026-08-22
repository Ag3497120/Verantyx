import SwiftUI

// MARK: - PrivacyShieldBadge
// Shows in the toolbar/chat indicating which mode is active

struct PrivacyShieldBadge: View {
    let mode: InferenceMode
    let stats: MaskingStats?

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: mode.icon)
                .font(.system(size: 11))
            Text(mode.rawValue)
                .font(.system(size: 11, weight: .semibold))

            if let stats = stats, (mode == .privacyShield || mode == .paranoiaMode) {
                Text("·")
                Text("\(stats.total) masked")
                    .font(.system(size: 10, design: .monospaced))
            }
        }
        .foregroundStyle(modeColor)
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .background(modeColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(modeColor.opacity(0.3), lineWidth: 0.5))
    }

    private var modeColor: Color {
        let c = mode.color
        return Color(red: c.r, green: c.g, blue: c.b)
    }
}

// MARK: - ModeSelectorView
// Compact bar for switching between Local / Cloud / Privacy Shield

struct ModeSelectorView: View {
    @EnvironmentObject var app: AppState
    @State private var showProviderPicker = false

    var body: some View {
        HStack(spacing: 0) {
            ForEach(InferenceMode.allCases, id: \.rawValue) { mode in
                modeButton(mode)
            }

            Divider().frame(height: 20).opacity(0.3).padding(.horizontal, 6)

            // Cloud provider (shown when not local-only)
            if app.inferenceMode != .localOnly {
                providerButton
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color(red: 0.14, green: 0.14, blue: 0.18))
    }

    private func modeButton(_ mode: InferenceMode) -> some View {
        let c = mode.color
        let color = Color(red: c.r, green: c.g, blue: c.b)
        let isActive = app.inferenceMode == mode

        return Button {
            withAnimation(.easeInOut(duration: 0.2)) {
                app.inferenceMode = mode
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: mode.icon)
                    .font(.system(size: 10))
                Text(mode.rawValue)
                    .font(.system(size: 11, weight: isActive ? .semibold : .regular))
            }
            .foregroundStyle(isActive ? color : Color(red: 0.45, green: 0.45, blue: 0.6))
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                isActive
                    ? color.opacity(0.12)
                    : Color.clear,
                in: RoundedRectangle(cornerRadius: 5)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 5)
                    .strokeBorder(isActive ? color.opacity(0.35) : Color.clear, lineWidth: 0.5)
            )
        }
        .contentShape(Rectangle())
        .buttonStyle(.plain)
        .help(mode.description)
    }

    private var providerButton: some View {
        Button {
            showProviderPicker.toggle()
        } label: {
            HStack(spacing: 5) {
                Image(systemName: app.cloudProvider.icon)
                    .font(.system(size: 10))
                Text(app.cloudProvider.rawValue)
                    .font(.system(size: 11))
                Image(systemName: "chevron.down")
                    .font(.system(size: 8))
            }
            .foregroundStyle(Color(red: 0.7, green: 0.7, blue: 0.85))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 5))
        }
        .contentShape(Rectangle())
        .buttonStyle(.plain)
        .popover(isPresented: $showProviderPicker, arrowEdge: .bottom) {
            providerPopover
        }
    }

    private var providerPopover: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Cloud Provider")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.7))
                .padding(.bottom, 4)

            ForEach(CloudProvider.allCases, id: \.rawValue) { provider in
                Button {
                    app.cloudProvider = provider
                    showProviderPicker = false
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: provider.icon)
                            .font(.system(size: 12))
                            .foregroundStyle(Color(red: 0.5, green: 0.7, blue: 1.0))
                        Text(provider.rawValue)
                            .font(.system(size: 12))
                            .foregroundStyle(Color.white)
                        Spacer()
                        if app.cloudProvider == provider {
                            Image(systemName: "checkmark").font(.caption).foregroundStyle(.green)
                        }
                        // API key status
                        apiKeyIndicator(provider)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        app.cloudProvider == provider ? Color.white.opacity(0.07) : Color.clear,
                        in: RoundedRectangle(cornerRadius: 6)
                    )
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
            }
        }
        .padding(12)
        .frame(width: 240)
        .background(Color(red: 0.14, green: 0.14, blue: 0.18))
    }

    private func apiKeyIndicator(_ provider: CloudProvider) -> some View {
        let hasKey = UserDefaults.standard.string(forKey: "api_key_\(provider.rawValue)").map { !$0.isEmpty } ?? false
        return Group {
            if hasKey {
                Text("Key ✓")
                    .font(.system(size: 9))
                    .foregroundStyle(Color.green.opacity(0.8))
            } else {
                Text("No key")
                    .font(.system(size: 9))
                    .foregroundStyle(Color(red: 0.9, green: 0.4, blue: 0.4).opacity(0.8))
            }
        }
    }
}

// MARK: - PrivacyShieldStepsView
// Real-time visualization of the masking pipeline in chat

struct PrivacyShieldStepsView: View {
    let steps: [String]
    @EnvironmentObject var app: AppState
    @State private var appear = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Header — adapts to Privacy Shield vs Paranoia Mode
            HStack(spacing: 6) {
                Image(systemName: app.inferenceMode == .paranoiaMode ? "eye.slash.circle.fill" : "lock.shield.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(headerColor)
                Text(app.inferenceMode == .paranoiaMode ? "Paranoia Mode Active" : "Privacy Shield Active")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(headerColor)
                Spacer()
            }

            // Steps
            ForEach(Array(steps.enumerated()), id: \.offset) { i, step in
                HStack(spacing: 8) {
                    Text(step)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(Color(red: 0.75, green: 0.75, blue: 0.88))
                }
                .padding(.leading, 8)
                .opacity(appear ? 1 : 0)
                .animation(.easeIn(duration: 0.3).delay(Double(i) * 0.15), value: appear)
            }

            // Paranoia Mode — inject live terminal log below steps
            if app.inferenceMode == .paranoiaMode {
                Divider().opacity(0.3).padding(.vertical, 4)
                ParanoiaModeView()
                    .environmentObject(app)
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(backgroundFill)
                .overlay(RoundedRectangle(cornerRadius: 8)
                    .strokeBorder(borderColor, lineWidth: 0.5))
        )
        .onAppear { appear = true }
    }

    private var headerColor: Color {
        app.inferenceMode == .paranoiaMode
            ? Color(red: 1.0, green: 0.35, blue: 0.35)
            : Color(red: 0.8, green: 0.5, blue: 1.0)
    }

    private var backgroundFill: Color {
        app.inferenceMode == .paranoiaMode
            ? Color(red: 0.2, green: 0.06, blue: 0.06).opacity(0.8)
            : Color(red: 0.18, green: 0.12, blue: 0.25).opacity(0.8)
    }

    private var borderColor: Color {
        app.inferenceMode == .paranoiaMode
            ? Color(red: 0.9, green: 0.2, blue: 0.2).opacity(0.3)
            : Color(red: 0.6, green: 0.3, blue: 0.9).opacity(0.3)
    }
}

// MARK: - AssistantText (reusable Markdown-style renderer)
// キャッシュ: 同一コンテンツの再パースを防いでレンダリングコストを削減
private let assistantTextCache = NSCache<NSString, NSArray>()

struct AssistantText: View {
    let content: String

    var body: some View {
        let parts = cachedParse(content)
        return parts.reduce(Text("")) { acc, part in
            acc + (part.isBold
                ? Text(part.text).bold().foregroundColor(Color.white)
                : Text(part.text).foregroundColor(Color(red: 0.88, green: 0.88, blue: 0.92))
            )
        }
        .textSelection(.enabled)
    }

    private struct TextPart { let text: String; let isBold: Bool }

    // Regex はファイル起動時に1回だけコンパイル
    private static let boldRegex = try? NSRegularExpression(pattern: #"\*\*(.+?)\*\*"#)

    private func cachedParse(_ text: String) -> [TextPart] {
        let key = text as NSString
        if let cached = assistantTextCache.object(forKey: key) as? [TextPart] {
            return cached
        }
        let result = parseMarkdownBold(text)
        assistantTextCache.setObject(result as NSArray, forKey: key)
        return result
    }

    private func parseMarkdownBold(_ text: String) -> [TextPart] {
        var parts: [TextPart] = []
        guard let regex = Self.boldRegex else {
            return [TextPart(text: text, isBold: false)]
        }
        var cursor = text.startIndex
        let matches = regex.matches(in: text, range: NSRange(text.startIndex..., in: text))
        for match in matches {
            if let fullRange = Range(match.range, in: text) {
                if fullRange.lowerBound > cursor {
                    parts.append(TextPart(text: String(text[cursor..<fullRange.lowerBound]), isBold: false))
                }
                if let innerRange = Range(match.range(at: 1), in: text) {
                    parts.append(TextPart(text: String(text[innerRange]), isBold: true))
                }
                cursor = fullRange.upperBound
            }
        }
        if cursor < text.endIndex {
            parts.append(TextPart(text: String(text[cursor...]), isBold: false))
        }
        return parts.isEmpty ? [TextPart(text: text, isBold: false)] : parts
    }
}
