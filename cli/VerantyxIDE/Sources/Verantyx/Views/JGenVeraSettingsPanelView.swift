import SwiftUI

/// The JGEN/Council 4-layer settings UI, extracted from
/// `ModelSelectorBarView.jgenOptionsPopover` so the exact same ~250 lines
/// of settings can be shown two ways: as the existing popover (unchanged
/// behavior) and, new in Milestone T, embedded full-size as a tab inside
/// Vera-a mode's side panel. No settings logic was duplicated or
/// rewritten -- this is a straight move, `jgenOptionsPopover` is now a
/// thin wrapper around this view.
struct JGenVeraSettingsPanelView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var council = CouncilSettingsStore.shared
    @ObservedObject private var keyframePump = VisualKeyframePump.shared
    @State private var includeWebRecommendations = true
    @State private var showKeyframePrivacyAlert = false
    @Binding var showPendingToolCalls: Bool
    @Binding var showReasoningTimeline: Bool

    /// Called when a template is picked, so the popover usage can dismiss
    /// itself. The side-panel usage (nothing to dismiss) passes nil.
    var onDismiss: (() -> Void)?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Text(app.t("JGEN Options", "JGENオプション"))
                        .font(.system(size: 13, weight: .bold))
                    Spacer()
                    Text(council.templateId == "custom"
                         ? app.t("Custom", "カスタム")
                         : council.templateId)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.tertiary)
                }

                layerBlock(
                    "Layer 0 — " + app.t("Memory", "記憶"),
                    color: Color(red: 0.5, green: 0.85, blue: 0.6)
                ) {
                    Toggle(app.t("Vera-α verified facts", "Vera-α 確定事実"), isOn: Binding(
                        get: { council.config.useVeraMemory },
                        set: { council.config.useVeraMemory = $0; council.markCustom() }
                    )).toggleStyle(.checkbox)

                    Toggle(app.t("Eternal (vector) memory", "永遠記憶(ベクトル)"), isOn: Binding(
                        get: { council.config.useEternalMemory },
                        set: { council.config.useEternalMemory = $0; council.markCustom() }
                    )).toggleStyle(.checkbox)

                    Toggle(app.t("Visual memory (screen recall)", "視覚記憶(画面リコール)"), isOn: Binding(
                        get: { council.useVisualMemory },
                        set: { council.useVisualMemory = $0 }
                    )).toggleStyle(.checkbox)

                    keyframeEyePermissionBlock()

                    Toggle(app.t("Vera as harness (Vera drives the turn)", "Veraをハーネスにする(Veraが主導)"), isOn: Binding(
                        get: { council.useVeraHarnessForChat },
                        set: { council.useVeraHarnessForChat = $0 }
                    )).toggleStyle(.checkbox)

                    if council.useVeraHarnessForChat {
                        Picker(app.t("Cognition mode", "認知モード"), selection: Binding(
                            get: { council.cognitionMode },
                            set: { council.cognitionMode = $0 }
                        )) {
                            ForEach(CouncilSettingsStore.CognitionMode.allCases) { mode in
                                Text(app.t(mode.title, mode.titleJA)).tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)
                        .font(.system(size: 10))

                        if council.cognitionMode != .normal {
                            Text(app.t(
                                "Open-domain gap mode (Milestone O): experiment records GapNodes; sleep may add quarantine candidates via heartbeat. Closed-domain growth (M) still requires human accept. Not a level 1–3 evolution system.",
                                "開いた領域のギャップモード(Milestone O): experimentはGapNodeを記録、sleepはheartbeatで検疫候補を追加し得ます。閉じた領域の成長(M)も人間の承認が必要です。レベル1〜3の自己進化システムではありません。"
                            ))
                            .font(.system(size: 9))
                            .foregroundStyle(.orange)
                            .fixedSize(horizontal: false, vertical: true)
                        }

                        // Milestone R4: mutating tool calls (write_file,
                        // run_command, vera_remember, vera_code_ingest, ...)
                        // the Vera-harness chat proposed but couldn't run
                        // without a human -- review queue, same button
                        // regardless of cognition mode since normal-mode
                        // chat can propose these too.
                        Button {
                            showPendingToolCalls = true
                        } label: {
                            Label(app.t("Pending tool-call approvals…", "承認待ちのツール呼び出し…"),
                                  systemImage: "checkmark.shield")
                                .font(.system(size: 10))
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(Color.orange)

                        // A Council/L1-L4 run can genuinely take 10+ minutes;
                        // this is the "why" behind that wait, not just a
                        // spinner -- see ReasoningTimelineView.
                        Button {
                            showReasoningTimeline = true
                        } label: {
                            Label(app.t("Reasoning timeline…", "推論タイムライン…"),
                                  systemImage: "timeline.selection")
                                .font(.system(size: 10))
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(Color.indigo)
                    }

                    Text(app.t("Zone memory layers", "ゾーン記憶レイヤ"))
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                    HStack(spacing: 6) {
                        ForEach(JCrossLayer.allCases) { layer in
                            let on = council.config.zoneLayers.contains(layer)
                            Button(layer.rawValue.uppercased()) {
                                if on { council.config.zoneLayers.remove(layer) }
                                else { council.config.zoneLayers.insert(layer) }
                                council.markCustom()
                            }
                            .buttonStyle(.plain)
                            .font(.system(size: 9, weight: .semibold, design: .monospaced))
                            .padding(.horizontal, 6).padding(.vertical, 3)
                            .background(
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(on ? Color(red: 0.5, green: 0.85, blue: 0.6).opacity(0.25)
                                             : Color.white.opacity(0.06))
                            )
                        }
                    }
                }

                layerBlock(
                    "Layer 1 — " + app.t("Council core (same-arch JGEN)", "合議核(同型JGEN)"),
                    color: Color(red: 1.0, green: 0.72, blue: 0.35)
                ) {
                    Stepper(app.t("Roles: \(council.config.roleCount)", "役割数: \(council.config.roleCount)"),
                            value: Binding(
                                get: { council.config.roleCount },
                                set: { council.config.roleCount = $0; council.markCustom() }
                            ), in: 2...5)
                        .font(.system(size: 10))
                    Stepper(app.t("Rounds cap: \(council.config.roundsCap)", "最大ラウンド: \(council.config.roundsCap)"),
                            value: Binding(
                                get: { council.config.roundsCap },
                                set: { council.config.roundsCap = $0; council.markCustom() }
                            ), in: 1...8)
                        .font(.system(size: 10))
                    Picker(app.t("Injection", "注入方針"), selection: Binding(
                        get: { council.config.injectionPolicy },
                        set: { council.config.injectionPolicy = $0; council.markCustom() }
                    )) {
                        ForEach(CouncilOrchestrator.InjectionPolicy.allCases) { p in
                            Text(p.displayName).tag(p)
                        }
                    }
                    .font(.system(size: 10))
                }

                layerBlock(
                    "Layer 2 — " + app.t("Execution agent (tools)", "実行エージェント(ツール)"),
                    color: Color(red: 0.5, green: 0.7, blue: 1.0)
                ) {
                    Toggle(isOn: Binding(
                        get: { council.executionUseJGEN },
                        set: { council.executionUseJGEN = $0 }
                    )) {
                        HStack(spacing: 4) {
                            Text("BETA")
                                .font(.system(size: 8, weight: .bold))
                                .padding(.horizontal, 4).padding(.vertical, 1)
                                .background(Color.orange.opacity(0.25))
                                .foregroundStyle(.orange)
                                .clipShape(Capsule())
                            Text(app.t("Run Layer 2 on JGEN too (same model as council)",
                                       "Layer 2もJGENで実行(合議と同一モデル)"))
                                .font(.system(size: 10))
                        }
                    }
                    .toggleStyle(.checkbox)

                    if council.executionUseJGEN {
                        Text(app.t(
                            "Uses JGenSpeakAgent / JGenActAgent on the same JGEN as the council: eternal + UI-trace recall, soft-token steer, optional desktop/AX act loop. Skips AgentLoop (no MEM/CTRL tag collapse) and Layer-3 escalation. Screen understanding prefers AX encode→inject; Vision feature-print inject is experimental fallback only.",
                            "合議と同一JGEN上のJGenSpeak / JGenAct: 永遠記憶＋UIトレース想起、ソフトトークン誘導、必要ならデスクトップ/AX操作。AgentLoopを通さないためMEM/CTRLタグ崩壊を避け、L3エスカレーションもしません。画面理解はAXのencode→注入を優先し、Vision特徴量の直接注入は実験的フォールバックのみです。"))
                            .font(.system(size: 9)).foregroundStyle(.orange)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    ollamaModelPicker(
                        label: app.t("Execution model", "実行モデル"),
                        selection: Binding(
                            get: { council.executionModel },
                            set: { council.executionModel = $0; council.markCustom() }
                        )
                    )
                    .disabled(council.executionUseJGEN)
                    .opacity(council.executionUseJGEN ? 0.4 : 1.0)
                    Text(app.t("Receives one short structured handoff (conclusion / evidence / next action / confidence) and runs tools on it.",
                               "短い構造化ハンドオフ(結論・根拠・次アクション・confidence)を受け取り、ツールを実行します。"))
                        .font(.system(size: 9)).foregroundStyle(.tertiary)
                }

                layerBlock(
                    "Layer 3 — " + app.t("Escalation", "エスカレーション"),
                    color: Color(red: 1.0, green: 0.55, blue: 0.75)
                ) {
                    Toggle(app.t("Escalate on low confidence", "低確信度でエスカレート"), isOn: Binding(
                        get: { council.config.escalateOnLowConfidence },
                        set: { council.config.escalateOnLowConfidence = $0; council.markCustom() }
                    )).toggleStyle(.checkbox)

                    if council.config.escalateOnLowConfidence {
                        HStack {
                            Text(app.t("Threshold", "閾値")).font(.system(size: 10))
                            Slider(value: Binding(
                                get: { Double(council.config.escalationConfidenceThreshold) },
                                set: { council.config.escalationConfidenceThreshold = Float($0); council.markCustom() }
                            ), in: 0.3...0.95)
                            Text(String(format: "%.2f", council.config.escalationConfidenceThreshold))
                                .font(.system(size: 9, design: .monospaced)).foregroundStyle(.secondary)
                        }
                        ollamaModelPicker(
                            label: app.t("Escalation model", "エスカレ先モデル"),
                            selection: Binding(
                                get: { council.config.escalationModel },
                                set: { council.config.escalationModel = $0; council.markCustom() }
                            )
                        )
                    }
                }

                Divider().opacity(0.2)

                Toggle(app.t("Use the council for normal chat turns",
                             "通常のチャットでも合議を使う"),
                       isOn: $council.useCouncilForChat)
                    .toggleStyle(.checkbox)
                    .font(.system(size: 10))
                Text(app.t("Otherwise the council only runs via /council. Requires a loaded JGEN model.",
                           "オフの場合、合議は /council でのみ実行されます。JGENモデルのロードが必要です。"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)

                Divider().opacity(0.2)

                // Whole-architecture templates: picking one inspects this
                // Mac and the installed models, then shows a plan to approve
                // rather than silently rewriting the settings.
                Text(app.t("Architecture template", "アーキテクチャ構成"))
                    .font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                Menu {
                    ForEach(ArchitectureTemplate.builtins) { template in
                        Button(AppLanguage.shared.isJapanese ? template.nameJA : template.name) {
                            onDismiss?()
                            app.proposeSetup(template: template, allowWeb: includeWebRecommendations)
                        }
                    }
                } label: {
                    Label(app.t("Choose a template…", "構成を選ぶ…"), systemImage: "square.3.layers.3d")
                        .font(.system(size: 10))
                }
                .menuStyle(.borderlessButton)

                Toggle(app.t("Include web recommendations", "Webの推奨も参照する"),
                       isOn: $includeWebRecommendations)
                    .toggleStyle(.checkbox)
                    .font(.system(size: 9))
                Text(app.t("Checks this Mac's RAM and free disk plus your installed models first; the web lookup only fills gaps and is skipped if it can't complete.",
                           "まずこのMacのRAM・空き容量とインストール済みモデルを確認します。Web検索は不足分の補足のみで、失敗しても処理は続行します。"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
            .padding(14)
        }
        .alert(
            app.t("Allow 1fps screen monitoring?", "1fps画面監視を許可しますか？"),
            isPresented: $showKeyframePrivacyAlert
        ) {
            Button(app.t("Allow", "許可"), role: .none) {
                council.keyframeEyePrivacyAcknowledged = true
                council.allowKeyframeEye = true
                VisualKeyframePump.shared.reconcile()
            }
            Button(app.t("Cancel", "キャンセル"), role: .cancel) {}
        } message: {
            Text(app.t(
                "While an agent run is active and a target app window is set, Verantyx will capture that window about once per second to detect loading/screen changes.\n\n• Only the target automation window — not always-on desktop monitoring.\n• Raw pixels are not saved to disk (summaries / AX text only).\n• You can turn this off anytime; capture stops immediately.\n• Screen Recording and Accessibility permissions may still be required by macOS.",
                "エージェント実行中かつ対象アプリウィンドウがあるときだけ、約1秒間隔でそのウィンドウを取得し、読み込みや画面変化を検知します。\n\n• 対象の自動化ウィンドウのみ（常時デスクトップ監視ではありません）\n• 生ピクセルはディスクに保存しません（要約・AX由来テキストのみ）\n• いつでもOFFでき、即座に停止します\n• macOSの画面収録／アクセシビリティ権限が別途必要な場合があります"
            ))
        }
    }

    @ViewBuilder
    private func keyframeEyePermissionBlock() -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Button {
                    if council.allowKeyframeEye {
                        council.allowKeyframeEye = false
                        VisualKeyframePump.shared.reconcile()
                    } else if council.keyframeEyePrivacyAcknowledged {
                        council.allowKeyframeEye = true
                        VisualKeyframePump.shared.reconcile()
                    } else {
                        showKeyframePrivacyAlert = true
                    }
                } label: {
                    Text(council.allowKeyframeEye
                         ? app.t("Disable 1fps screen eye", "1fps画面監視を無効化")
                         : app.t("Allow 1fps screen eye…", "1fps画面監視を許可…"))
                        .font(.system(size: 10, weight: .semibold))
                }
                .buttonStyle(.borderedProminent)
                .tint(council.allowKeyframeEye ? .orange : .accentColor)

                if council.allowKeyframeEye {
                    Text(app.t("Permitted", "許可済み"))
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.green)
                }
            }

            Text(app.t(
                "Runs only during an agent session with a HiddenWindow target. Event-driven click traces stay separate.",
                "エージェント実行中かつ HiddenWindow 対象があるときだけ動作します。クリック時のイベント記録とは別経路です。"
            ))
            .font(.system(size: 9))
            .foregroundStyle(.tertiary)
            .fixedSize(horizontal: false, vertical: true)

            if keyframePump.isActivelyMonitoring {
                Text(app.t("Monitoring: \(keyframePump.monitoredAppName ?? "—")",
                           "監視中: \(keyframePump.monitoredAppName ?? "—")"))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.orange)
            }
        }
    }

    @ViewBuilder
    private func layerBlock<Content: View>(_ title: String, color: Color,
                                           @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 3, height: 11)
                Text(title).font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
            }
            content()
        }
    }

    /// Layers 2 and 3 both call Ollama, so both pick from the same live list.
    @ViewBuilder
    private func ollamaModelPicker(label: String, selection: Binding<String>) -> some View {
        if app.ollamaModels.isEmpty {
            TextField(label, text: selection)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 10, design: .monospaced))
        } else {
            Picker(label, selection: selection) {
                Text(app.t("(none)", "(なし)")).tag("")
                ForEach(app.ollamaModels, id: \.self) { m in Text(m).tag(m) }
            }
            .font(.system(size: 10))
        }
    }
}
