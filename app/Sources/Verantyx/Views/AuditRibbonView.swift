import SwiftUI

// MARK: - The audit layer, made visible
//
// Every other agent IDE has two states for a turn: it worked, or it errored.
// This one has four, and they are the product:
//
//   接地   a claim that a witness backs — a test run, a grep, a page actually read
//   未検証  a claim with no witness. NOT an error: an absence of evidence is not
//          evidence of fabrication, which is the one inference this architecture
//          forbids. Amber, never red.
//   係争   a claim a witness CONTRADICTS. The only red on the surface, and the
//          only thing here a competitor cannot show, because showing it requires
//          having kept the witness.
//   無知   a typed refusal — the store said UNKNOWN and named which kind, which
//          is what routes the next move. A state, not a failure. Violet.
//
// Until now all four arrived as one grey line of `<think>` text — "🧾 接地: Vera
// 0件・証拠 0件 / 未検証 1件" — inside an NSTextView, indistinguishable from
// debug output. The information was already being computed and thrown away
// visually.
//
// The transcript itself stays an NSTextView on purpose (per-bubble SwiftUI
// Text was measured slower), so this rides beside it rather than inside it.

struct AuditSummary: Equatable {
    struct Claim: Equatable, Identifiable {
        enum State: Equatable { case grounded, unverified, disputed }
        let id = UUID()
        let text: String
        let state: State
        /// What backs — or contradicts — the claim. The witness, in its own words.
        let witness: String?
    }

    struct Refusal: Equatable {
        /// UNKNOWN_NO_EVIDENCE, UNKNOWN_INSUFFICIENT_EVIDENCE, …
        let verdict: String
        /// The branch the refusal routed the agent onto.
        let branch: String
    }

    var claims: [Claim] = []
    var refusal: Refusal?

    var grounded: Int { claims.filter { $0.state == .grounded }.count }
    var unverified: Int { claims.filter { $0.state == .unverified }.count }
    var disputed: Int { claims.filter { $0.state == .disputed }.count }

    var isEmpty: Bool { claims.isEmpty && refusal == nil }
}

// MARK: - Palette
//
// Colour carries the epistemic state, not success or failure. That is the whole
// point: a run with three unverified claims is not "failing", and a run with one
// dispute is not merely "warning" — it is the single most important thing on the
// screen.

private enum AuditPalette {
    static let grounded = Theme.ok
    static let unverified = Theme.warn
    static let disputed = Theme.bad
    static let refusal = Theme.accent
    static let hairline = Color.white.opacity(0.09)
    static let surface = Color.white.opacity(0.035)
}

private extension AuditSummary.Claim.State {
    var tint: Color {
        switch self {
        case .grounded:   return AuditPalette.grounded
        case .unverified: return AuditPalette.unverified
        case .disputed:   return AuditPalette.disputed
        }
    }
    var glyph: String {
        switch self {
        case .grounded:   return "checkmark.seal.fill"
        case .unverified: return "questionmark.circle"
        case .disputed:   return "exclamationmark.triangle.fill"
        }
    }
}

// MARK: - The ribbon

struct AuditRibbonView: View {

    let summary: AuditSummary
    var japanese: Bool = true

    @State private var expanded = false
    @State private var appeared = false
    /// One pulse when a dispute arrives. A dispute is the rarest and most
    /// consequential state; it earns exactly one moment of motion and then
    /// stops moving, so it reads as an alert rather than an animation.
    @State private var disputePulse = false

    private func t(_ en: String, _ ja: String) -> String { japanese ? ja : en }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            if expanded {
                Divider().overlay(AuditPalette.hairline)
                detail
                    .transition(.asymmetric(
                        insertion: .move(edge: .top).combined(with: .opacity),
                        removal: .opacity))
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .fill(AuditPalette.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .strokeBorder(
                    summary.disputed > 0
                        ? AuditPalette.disputed.opacity(disputePulse ? 0.55 : 0.22)
                        : AuditPalette.hairline,
                    lineWidth: 1)
        )
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : -6)
        .onAppear {
            withAnimation(.spring(response: 0.42, dampingFraction: 0.86)) { appeared = true }
            guard summary.disputed > 0 else { return }
            withAnimation(.easeOut(duration: 0.5)) { disputePulse = true }
            withAnimation(.easeInOut(duration: 1.1).delay(0.5)) { disputePulse = false }
        }
        .animation(.spring(response: 0.38, dampingFraction: 0.85), value: expanded)
    }

    // MARK: Header — the four states at a glance

    private var header: some View {
        HStack(spacing: 9) {
            Image(systemName: "scalemass")
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(.secondary)

            if summary.grounded > 0 {
                chip(count: summary.grounded,
                     label: t("witnessed", "接地"),
                     tint: AuditPalette.grounded,
                     glyph: "checkmark.seal.fill")
            }
            if summary.unverified > 0 {
                chip(count: summary.unverified,
                     label: t("unverified", "未検証"),
                     tint: AuditPalette.unverified,
                     glyph: "questionmark.circle")
            }
            if summary.disputed > 0 {
                chip(count: summary.disputed,
                     label: t("disputed", "係争"),
                     tint: AuditPalette.disputed,
                     glyph: "exclamationmark.triangle.fill")
            }
            if let refusal = summary.refusal {
                refusalChip(refusal)
            }

            Spacer(minLength: 4)

            if !summary.claims.isEmpty {
                Image(systemName: "chevron.down")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.tertiary)
                    .rotationEffect(.degrees(expanded ? 180 : 0))
            }
        }
        .padding(.horizontal, 11)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
        .onTapGesture {
            guard !summary.claims.isEmpty else { return }
            expanded.toggle()
        }
    }

    private func chip(count: Int, label: String, tint: Color, glyph: String) -> some View {
        HStack(spacing: 4) {
            Image(systemName: glyph).font(.system(size: 9, weight: .semibold))
            Text("\(count)")
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                // Counts land during streaming, so they change in place rather
                // than appearing fully formed.
                .contentTransition(.numericText())
            Text(label).font(.system(size: 10.5))
        }
        .foregroundStyle(tint)
        .padding(.horizontal, 7)
        .padding(.vertical, 3)
        .background(Capsule().fill(tint.opacity(0.12)))
        .overlay(Capsule().strokeBorder(tint.opacity(0.22), lineWidth: 0.5))
    }

    /// The refusal chip names the KIND of not-knowing and the branch it chose.
    /// "I don't know" is what every other agent says silently before guessing;
    /// naming which kind is what turns it into a routing decision.
    private func refusalChip(_ refusal: AuditSummary.Refusal) -> some View {
        HStack(spacing: 4) {
            Image(systemName: "circle.dotted").font(.system(size: 9, weight: .semibold))
            Text(shortVerdict(refusal.verdict))
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
            Text("→ \(refusal.branch)").font(.system(size: 10.5))
        }
        .foregroundStyle(AuditPalette.refusal)
        .padding(.horizontal, 7)
        .padding(.vertical, 3)
        .background(Capsule().fill(AuditPalette.refusal.opacity(0.12)))
        .overlay(Capsule().strokeBorder(AuditPalette.refusal.opacity(0.22), lineWidth: 0.5))
    }

    /// UNKNOWN_INSUFFICIENT_EVIDENCE reads as noise at chip size; the part that
    /// distinguishes one refusal from another is the tail.
    private func shortVerdict(_ v: String) -> String {
        v.replacingOccurrences(of: "UNKNOWN_", with: "")
    }

    // MARK: Detail — the claim, next to what backs it

    private var detail: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(summary.claims.enumerated()), id: \.element.id) { index, claim in
                claimRow(claim)
                if index < summary.claims.count - 1 {
                    Divider().overlay(AuditPalette.hairline.opacity(0.6))
                        .padding(.leading, 30)
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func claimRow(_ claim: AuditSummary.Claim) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: claim.state.glyph)
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(claim.state.tint)
                .frame(width: 14, alignment: .center)
                .padding(.top, 1)

            VStack(alignment: .leading, spacing: 3) {
                Text(claim.text)
                    .font(.system(size: 11.5))
                    .foregroundStyle(.primary.opacity(0.9))
                    .fixedSize(horizontal: false, vertical: true)

                // The witness in its own words, quoted rather than summarised —
                // a summary of a witness is another claim, and would need its
                // own witness.
                if let witness = claim.witness, !witness.isEmpty {
                    HStack(alignment: .top, spacing: 5) {
                        Rectangle()
                            .fill(claim.state.tint.opacity(0.5))
                            .frame(width: 2)
                        Text(witness)
                            .font(.system(size: 10.5, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.leading, 1)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 11)
        .padding(.vertical, 7)
    }
}
