import SwiftUI

// MARK: - The licence book, and the record of what was done with it
//
// Two halves of one question. The top half is what Vera MAY do; the bottom
// is what it DID. They belong on one surface because a permission screen
// with no record beside it asks people to grant on faith, and a record with
// no permission screen beside it leaves them nowhere to go when they read
// something they did not want.
//
// The grants are per app AND per verb, and each one is written as its
// consequence rather than its mechanism — "run" tells a reader nothing they
// did not already know, so the row says what it costs them.

struct AppLicenceView: View {

    @ObservedObject private var licences = AppLicenceStore.shared
    @ObservedObject private var delegation = AppDelegation.shared
    @State private var showAll = false

    private func t(_ en: String, _ ja: String) -> String {
        AppLanguage.shared.t(en, ja)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.25)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let pending = delegation.pendingGrant { request(pending) }
                    licenceTable
                    Divider().opacity(0.2)
                    record
                }
                .padding(14)
            }
        }
        .frame(minWidth: 460, minHeight: 300)
    }

    // MARK: Header

    private var header: some View {
        HStack(spacing: 8) {
            JCrossGlyph(tint: Color(red: 0.55, green: 0.78, blue: 1.0), thickness: 1.6)
                .frame(width: 13, height: 13)
            Text(t("LICENCES", "免許"))
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .tracking(1.4)
            Text("\(licences.grantedCount)")
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(.tertiary)
            Spacer()
            if licences.grantedCount > 0 {
                Button(t("Revoke all", "すべて取り消す")) { licences.revokeAll() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundStyle(Color(red: 1.0, green: 0.5, blue: 0.45))
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 9)
    }

    // MARK: A refusal that is waiting for an answer

    private func request(_ r: DelegationRequest) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(t("Asked for, and refused", "要求があり、拒否しました"))
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Color(red: 1.0, green: 0.72, blue: 0.35))
            Text("\(r.app.displayName) / \(r.verb.displayName)")
                .font(.system(size: 12, weight: .semibold, design: .monospaced))
            Text(r.payload)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(.secondary)
                .lineLimit(3)
            Text(t("Requested by: ", "要求元: ") + r.origin.displayName)
                .font(.system(size: 10)).foregroundStyle(.tertiary)
            HStack(spacing: 8) {
                // Grants the verb, and nothing else. Not the app, not "this
                // once and then remember" — the row above is exactly what is
                // being agreed to.
                Button(t("Grant \(r.verb.displayName)", "「\(r.verb.displayName)」を許可")) {
                    licences.set(true, app: r.app, verb: r.verb)
                    delegation.pendingGrant = nil
                }
                .buttonStyle(.borderedProminent).controlSize(.small)
                Button(t("Leave refused", "拒否のまま")) {
                    delegation.pendingGrant = nil
                }
                .buttonStyle(.bordered).controlSize(.small)
            }
            // Granting does not re-run it. A permission dialog that also
            // performs the act turns "what is this?" into a decision made
            // before the question was understood.
            Text(t("Granting does not run it. Ask again when you mean to.",
                   "許可しても実行はしません。実行するときはもう一度言ってください。"))
                .font(.system(size: 10)).foregroundStyle(.tertiary)
        }
        .padding(11)
        .background(RoundedRectangle(cornerRadius: 8)
            .fill(Color(red: 1.0, green: 0.72, blue: 0.35).opacity(0.08)))
        .overlay(RoundedRectangle(cornerRadius: 8)
            .strokeBorder(Color(red: 1.0, green: 0.72, blue: 0.35).opacity(0.3), lineWidth: 1))
    }

    // MARK: What Vera may do

    private var licenceTable: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(t("What Vera may do, app by app and verb by verb",
                   "Veraが何をしてよいか（アプリごと・行為ごと）"))
                .font(.system(size: 11)).foregroundStyle(.secondary)

            ForEach(DelegatedApp.allCases) { app in
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 6) {
                        Text(app.displayName)
                            .font(.system(size: 12, weight: .semibold))
                        if !app.isInstalled {
                            Text(t("not installed", "未インストール"))
                                .font(.system(size: 10))
                                .foregroundStyle(.tertiary)
                        }
                        Spacer()
                    }
                    ForEach(app.verbs, id: \.rawValue) { verb in
                        Toggle(isOn: Binding(
                            get: { licences.isGranted(app, verb) },
                            set: { licences.set($0, app: app, verb: verb) })) {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(verb.displayName)
                                    .font(.system(size: 11.5))
                                Text(verb.consequence)
                                    .font(.system(size: 10))
                                    .foregroundStyle(.tertiary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .toggleStyle(.switch)
                        .controlSize(.mini)
                        .disabled(!app.isInstalled)
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }

    // MARK: What Vera did

    private var record: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(t("What was actually done", "実際に行われたこと"))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                Spacer()
                if delegation.log.count > 8 {
                    Button(showAll ? t("Show recent", "直近のみ")
                                   : t("Show all \(delegation.log.count)",
                                       "全\(delegation.log.count)件")) {
                        showAll.toggle()
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 10))
                    .foregroundStyle(Color(red: 0.55, green: 0.78, blue: 1.0))
                }
            }

            if delegation.log.isEmpty {
                Text(t("Nothing yet. This fills as Vera commands apps.",
                       "まだありません。Veraがアプリを動かすとここに溜まります。"))
                    .font(.system(size: 11)).foregroundStyle(.tertiary)
            } else {
                // Newest first for reading; the store keeps them in order.
                let rows = showAll ? delegation.log.reversed().map { $0 }
                                   : delegation.log.suffix(8).reversed().map { $0 }
                ForEach(rows) { EvidenceRow(evidence: $0) }
            }
        }
    }
}

// MARK: - One act, and what it established

struct EvidenceRow: View {
    let evidence: DelegationEvidence

    private var tint: Color {
        switch evidence.outcome {
        case .ok:        return Color(red: 0.35, green: 0.85, blue: 0.6)
        case .failed:    return Color(red: 1.0, green: 0.45, blue: 0.4)
        case .handedOff: return Color(red: 0.6, green: 0.65, blue: 0.8)
        case .refusedNoLicence, .refusedOrigin:
            return Color(red: 1.0, green: 0.72, blue: 0.35)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                Circle().fill(tint).frame(width: 5, height: 5)
                Text("\(evidence.app.displayName) / \(evidence.verb.displayName)")
                    .font(.system(size: 11, weight: .semibold))
                Text(evidence.rung.displayName)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.tertiary)
                Spacer()
                Text(evidence.at.formatted(date: .omitted, time: .standard))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }
            Text(evidence.payload)
                .font(.system(size: 10.5, design: .monospaced))
                .foregroundStyle(.secondary)
                .lineLimit(2)
            Text(evidence.verdict)
                .font(.system(size: 10.5))
                .foregroundStyle(tint)
            // The digest is what makes a later claim checkable against the
            // run it cites, without keeping the whole log.
            if !evidence.outputDigest.isEmpty {
                Text("sha256:\(evidence.outputDigest)… · \(evidence.outputBytes)B · "
                     + String(format: "%.2fs", evidence.duration))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
