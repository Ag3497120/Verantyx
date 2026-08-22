import SwiftUI

/// "Here is the setup I propose — approve it?"
///
/// Shown after picking an architecture template. The plan is already complete
/// when this appears (the planner runs before presentation, so no spinner or
/// network wait happens behind a modal), and every layer stays editable until
/// the user approves.
struct TemplateSetupApprovalSheet: View {
    @EnvironmentObject var app: AppState
    let proposal: SetupProposal

    @State private var edited: SetupProposal
    @State private var isCustom = false

    init(proposal: SetupProposal) {
        self.proposal = proposal
        _edited = State(initialValue: proposal)
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.25)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    machineCard
                    templateCard
                    ForEach(edited.assignments) { assignment in
                        layerCard(assignment)
                    }
                    if !edited.warnings.isEmpty { warningsCard }
                    webCard
                }
                .padding(16)
            }
            Divider().opacity(0.25)
            footer
        }
        .frame(width: 620, height: 720)
    }

    // MARK: - Bands

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "square.3.layers.3d")
                .font(.system(size: 20))
                .foregroundStyle(Color(red: 1.0, green: 0.72, blue: 0.35))
                .frame(width: 34, height: 34)
                .background(Color(red: 1.0, green: 0.72, blue: 0.35).opacity(0.12),
                            in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 2) {
                Text(app.t("Proposed setup", "提案する構成"))
                    .font(.system(size: 14, weight: .bold))
                Text(AppLanguage.shared.isJapanese ? edited.template.nameJA : edited.template.name)
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer()
            if isCustom {
                Text(app.t("Custom", "カスタム"))
                    .font(.system(size: 9, weight: .semibold))
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(Color.white.opacity(0.1), in: Capsule())
            }
        }
        .padding(16)
    }

    private var machineCard: some View {
        card(app.t("This Mac", "このMac"), icon: "cpu") {
            Text(edited.machine.summary)
                .font(.system(size: 11, design: .monospaced))
            let need = edited.template.requirements.minFreeDiskGB
            if edited.machine.freeDiskGB < need {
                Label(String(format: app.t("Only %.1f GB free — this template wants %.0f GB. Free space before converting or downloading models.",
                                           "空きが %.1f GB しかありません — この構成は %.0f GB を想定しています。モデルの変換・ダウンロード前に容量を確保してください。"),
                             edited.machine.freeDiskGB, need),
                      systemImage: "externaldrive.badge.exclamationmark")
                    .font(.system(size: 10))
                    .foregroundStyle(Color(red: 1.0, green: 0.45, blue: 0.45))
            }
            if edited.machine.totalRAMGB < edited.template.requirements.minRAMGB {
                Label(String(format: app.t("%.0f GB RAM vs ~%.0f GB expected — expect swapping.",
                                           "RAM %.0f GB(想定 約%.0f GB) — スワップの可能性があります。"),
                             edited.machine.totalRAMGB, edited.template.requirements.minRAMGB),
                      systemImage: "memorychip")
                    .font(.system(size: 10))
                    .foregroundStyle(Color(red: 1.0, green: 0.75, blue: 0.3))
            }
        }
    }

    private var templateCard: some View {
        card(app.t("Template", "テンプレート"), icon: "rectangle.3.group") {
            Text(AppLanguage.shared.isJapanese ? edited.template.descriptionJA : edited.template.description)
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func layerCard(_ a: LayerAssignment) -> some View {
        let spec = edited.template.layer(a.role)
        return card(AppLanguage.shared.isJapanese ? a.role.titleJA : a.role.title,
                    icon: icon(for: a.role)) {
            if case .notApplicable = a.source {
                if a.role == .memory {
                    memorySummary
                } else {
                    Text(app.t("Disabled in this template.", "この構成では無効です。"))
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                }
            } else {
                HStack(spacing: 8) {
                    Text(a.backend.displayName)
                        .font(.system(size: 9, weight: .semibold))
                        .padding(.horizontal, 5).padding(.vertical, 2)
                        .background(Color.white.opacity(0.1), in: RoundedRectangle(cornerRadius: 3))

                    // Editable: pick any installed model for this layer.
                    if a.backend == .ollama && !app.ollamaModels.isEmpty {
                        Picker("", selection: bindingForModel(a.role)) {
                            ForEach(app.ollamaModels, id: \.self) { Text($0).tag($0) }
                            if !app.ollamaModels.contains(a.model) {
                                Text(a.model + app.t(" (not installed)", "(未インストール)")).tag(a.model)
                            }
                        }
                        .labelsHidden()
                        .frame(maxWidth: 260)
                    } else {
                        Text(a.model).font(.system(size: 11, design: .monospaced))
                    }
                    Spacer()
                    if let gb = a.sizeGB {
                        Text(String(format: "~%.1f GB", gb))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.tertiary)
                    }
                }

                if let note = spec.map({ AppLanguage.shared.isJapanese ? $0.noteJA : $0.note }), !note.isEmpty {
                    Text(note).font(.system(size: 9)).foregroundStyle(.tertiary)
                }
                if let message = a.status.message {
                    Label(message, systemImage: a.status.isBlocked
                          ? "xmark.octagon.fill" : "exclamationmark.triangle.fill")
                        .font(.system(size: 10))
                        .foregroundStyle(a.status.isBlocked
                                         ? Color(red: 1.0, green: 0.45, blue: 0.45)
                                         : Color(red: 1.0, green: 0.75, blue: 0.3))
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let hint = a.installHint {
                    Text(hint)
                        .font(.system(size: 9, design: .monospaced))
                        .textSelection(.enabled)
                        .padding(6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.black.opacity(0.25), in: RoundedRectangle(cornerRadius: 4))
                }
            }
        }
    }

    private var memorySummary: some View {
        let c = edited.template.councilConfig
        var parts: [String] = []
        if c.useVeraMemory { parts.append("Vera-α") }
        if !c.zoneLayers.isEmpty {
            parts.append(c.zoneLayers.map { $0.rawValue.uppercased() }.sorted().joined(separator: "/"))
        }
        if c.useEternalMemory { parts.append(app.t("eternal vectors", "永遠ベクトル")) }
        return Text(parts.isEmpty ? app.t("No memory sources enabled.", "記憶ソースなし")
                                  : parts.joined(separator: " · "))
            .font(.system(size: 10, design: .monospaced))
            .foregroundStyle(.secondary)
    }

    private var warningsCard: some View {
        card(app.t("Notes", "注意"), icon: "exclamationmark.triangle") {
            ForEach(edited.warnings, id: \.self) { w in
                Text("• " + w).font(.system(size: 10))
                    .foregroundStyle(Color(red: 1.0, green: 0.75, blue: 0.3))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder
    private var webCard: some View {
        if edited.webSearchAttempted {
            card(app.t("Web recommendations", "Webからの推奨"), icon: "globe") {
                if edited.webSearchFailed {
                    Text(app.t("Unavailable — using the local inventory only.",
                               "取得できませんでした — ローカルの在庫のみで判断しています。"))
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                } else {
                    ForEach(edited.webNotes, id: \.self) { note in
                        Text("• " + note).font(.system(size: 9))
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Text(app.t("Advisory only — nothing here is selected automatically.",
                               "参考情報です — ここから自動でモデルが選ばれることはありません。"))
                        .font(.system(size: 9)).foregroundStyle(.tertiary)
                }
            }
        }
    }

    private var footer: some View {
        HStack {
            if !edited.isApplicable {
                Label(app.t("Some layers are blocked — resolve them or pick another template.",
                            "ブロックされた層があります — 解消するか別の構成を選んでください。"),
                      systemImage: "xmark.octagon.fill")
                    .font(.system(size: 10))
                    .foregroundStyle(Color(red: 1.0, green: 0.45, blue: 0.45))
            }
            Spacer()
            Button(app.t("Cancel", "キャンセル")) { app.pendingSetupProposal = nil }
                .buttonStyle(.bordered)
            Button(app.t("Apply setup", "この構成を適用")) {
                app.applySetupProposal(edited)
            }
            .buttonStyle(.borderedProminent)
            .tint(Color(red: 1.0, green: 0.6, blue: 0.3))
            .disabled(!edited.isApplicable)
        }
        .padding(16)
    }

    // MARK: - Helpers

    private func bindingForModel(_ role: LayerSpec.Role) -> Binding<String> {
        Binding(
            get: { edited.assignment(role)?.model ?? "" },
            set: { newValue in
                guard let idx = edited.assignments.firstIndex(where: { $0.role == role }) else { return }
                edited.assignments[idx].model = newValue
                edited.assignments[idx].source = .local
                edited.assignments[idx].status = .ok
                edited.assignments[idx].installHint = nil
                isCustom = true
            }
        )
    }

    private func icon(for role: LayerSpec.Role) -> String {
        switch role {
        case .memory:      return "externaldrive.connected.to.line.below"
        case .councilCore: return "brain"
        case .execution:   return "wrench.and.screwdriver"
        case .escalation:  return "arrow.up.circle"
        }
    }

    @ViewBuilder
    private func card<Content: View>(_ title: String, icon: String,
                                     @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: icon)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.secondary)
            content()
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
    }
}
