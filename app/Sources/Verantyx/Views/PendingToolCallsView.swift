import SwiftUI

/// Milestone R4: review queue for mutating tool calls the Vera-harness
/// chat proposed but could not run without a human (write_file,
/// run_command, vera_remember, vera_code_ingest, ...). Same shape as
/// Vera's own fact/module quarantine -- nothing here ever executes
/// automatically; "Accept" is the only path from a queued proposal to an
/// actually-run tool call, and it runs the tool with Vera's CURRENT
/// state, not a replay of whatever state existed when it was proposed.
struct PendingToolCallsView: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var calls: [VeraMemoryBridge.PendingToolCall] = []
    @State private var isLoading = true
    @State private var busyIndex: Int? = nil
    @State private var lastResult: String? = nil

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.25)
            content
            Divider().opacity(0.25)
            footer
        }
        .frame(width: 560, height: 560)
        .task { await reload() }
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "checkmark.shield")
                .font(.system(size: 20))
                .foregroundStyle(Color(red: 0.95, green: 0.6, blue: 0.25))
                .frame(width: 34, height: 34)
                .background(Color(red: 0.95, green: 0.6, blue: 0.25).opacity(0.12),
                            in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 2) {
                Text(app.t("Pending tool-call approvals", "承認待ちのツール呼び出し"))
                    .font(.system(size: 14, weight: .bold))
                Text(app.t(
                    "Queued by the Vera-harness chat -- nothing here has run yet.",
                    "Veraハーネスのチャットが提案したもの -- まだ何も実行されていません。"
                ))
                .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                Task { await reload() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .disabled(isLoading)
        }
        .padding(16)
    }

    @ViewBuilder
    private var content: some View {
        if isLoading {
            Spacer()
            ProgressView()
            Spacer()
        } else if calls.isEmpty {
            Spacer()
            VStack(spacing: 6) {
                Image(systemName: "tray")
                    .font(.system(size: 24))
                    .foregroundStyle(.tertiary)
                Text(app.t("No pending tool calls", "承認待ちのツール呼び出しはありません"))
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
            Spacer()
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(calls) { call in
                        callCard(call)
                    }
                }
                .padding(16)
            }
        }
    }

    private func callCard(_ call: VeraMemoryBridge.PendingToolCall) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(call.toolName)
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                Spacer()
                Text(call.callId)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }

            if !call.task.isEmpty {
                Text(app.t("Task: ", "タスク: ") + call.task)
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            if !call.reason.isEmpty {
                Text(app.t("Reason: ", "理由: ") + call.reason)
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }

            ScrollView(.horizontal) {
                Text(call.argsText)
                    .font(.system(size: 10, design: .monospaced))
                    .padding(6)
            }
            .frame(maxHeight: 90)
            .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 6))

            HStack(spacing: 8) {
                Spacer()
                Button(app.t("Reject", "却下")) {
                    Task { await act(call, accept: false) }
                }
                .buttonStyle(.plain)
                .foregroundStyle(.red)
                Button(app.t("Accept & Run", "承認して実行")) {
                    Task { await act(call, accept: true) }
                }
                .buttonStyle(.borderedProminent)
                .tint(.orange)
            }
            .disabled(busyIndex != nil)
            .overlay(alignment: .trailing) {
                if busyIndex == call.index {
                    ProgressView().scaleEffect(0.6)
                }
            }
        }
        .padding(10)
        .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.orange.opacity(0.25), lineWidth: 1)
        )
    }

    private var footer: some View {
        HStack {
            if let lastResult {
                Text(lastResult)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .truncationMode(.tail)
            }
            Spacer()
            Button(app.t("Close", "閉じる")) { dismiss() }
                .keyboardShortcut(.cancelAction)
        }
        .padding(12)
    }

    private func reload() async {
        isLoading = true
        calls = await VeraMemoryBridge.listPendingToolCalls()
        isLoading = false
    }

    private func act(_ call: VeraMemoryBridge.PendingToolCall, accept: Bool) async {
        busyIndex = call.index
        if accept {
            let result = await VeraMemoryBridge.acceptToolCall(index: call.index)
            lastResult = result.map { "\(call.toolName): \($0.prefix(200))" }
        } else {
            let ok = await VeraMemoryBridge.rejectToolCall(index: call.index)
            lastResult = ok ? app.t("Rejected \(call.toolName).", "\(call.toolName) を却下しました。") : nil
        }
        busyIndex = nil
        // Indices shift once an entry leaves "pending" -- always refetch
        // rather than mutating the local array by index.
        await reload()
    }
}
