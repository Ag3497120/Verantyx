import SwiftUI

/// Text-in/text-out exploration of JCrossEngine's raw hidden-state
/// operations, independent of the normal chat/generate path:
///   - encode: text -> a "thought vector" (the model's final hidden state)
///   - resynthesize: vector -> nearest token, via lm_head's token manifold
///   - puzzle_inference: vector -> (nearest token, confidence/entropy)
///   - optimize_thought_in_place: refine a vector via latent gradient
///     descent to lower its entropy (a more confident "thought"), without
///     ever sampling a token
///
/// Requires a JGEN model loaded via Settings → JGEN (app.modelStatus ==
/// .jcrossReady) -- these operations only exist for models running
/// through JCrossEngine; Ollama/MLX-served models have no hidden-state
/// access at all.
struct VectorLabView: View {
    @EnvironmentObject var app: AppState

    private enum LabMode: String, CaseIterable, Identifiable {
        case single, council
        var id: String { rawValue }
    }
    @State private var mode: LabMode = .single

    @State private var inputText: String = ""
    @State private var vector: [Float]?
    @State private var layerName: String = "lm_head"
    @State private var isBusy = false
    @State private var errorText: String?

    @State private var resynthesizedText: String?
    @State private var puzzleText: String?
    @State private var puzzleEntropy: Float?

    @State private var optimizeSteps: Double = 20
    @State private var optimizeLR: Double = 0.05
    @State private var optimizedText: String?
    @State private var optimizedEntropy: Float?

    // ── Council mode state ──
    @State private var councilQuestion: String = ""
    @State private var councilRoleCount: Double = 3
    @State private var councilRoundsCap: Double = 4
    @State private var councilPolicy: CouncilOrchestrator.InjectionPolicy = .none
    @State private var councilUseVera: Bool = true
    /// Multi-select L1/L1.5/L2/L3 zone-memory sources (Council mode only,
    /// per scope decision -- plain JGEN chat keeps its existing behavior).
    @State private var councilZoneLayers: Set<JCrossLayer> = []
    @State private var councilUseEternal: Bool = false
    @State private var councilEscalate: Bool = true
    @State private var councilThreshold: Double = 0.6
    @State private var councilEscalationModel: String = ""
    @State private var councilResult: CouncilOrchestrator.Result?
    @State private var councilBusy = false
    @State private var councilError: String?
    @State private var councilPreset: CouncilPreset.ID = "custom"
    /// Suppresses the per-field `markCustom()` onChange handlers while
    /// `applyPreset` bulk-sets state, so picking a preset doesn't
    /// immediately flip itself back to "Custom".
    @State private var isApplyingPreset = false

    private var modelLoaded: Bool {
        if case .jcrossReady = app.modelStatus { return true }
        return false
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            if !modelLoaded {
                emptyState
            } else {
                Picker("", selection: $mode) {
                    Text(app.t("Single Vector", "単一ベクトル")).tag(LabMode.single)
                    Text(app.t("Council", "評議会")).tag(LabMode.council)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .padding(.horizontal, 16)
                .padding(.top, 10)

                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        if mode == .single {
                            encodeSection
                            if vector != nil {
                                Divider().opacity(0.2)
                                resynthesizeSection
                                Divider().opacity(0.2)
                                optimizeSection
                            }
                            if let errorText {
                                Text(errorText)
                                    .font(.system(size: 11))
                                    .foregroundStyle(Theme.bad)
                            }
                        } else {
                            councilSection
                        }
                    }
                    .padding(16)
                }
            }
        }
        .background(Theme.bg)
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "atom")
                .font(.system(size: 13))
                .foregroundStyle(Color(red: 0.6, green: 0.85, blue: 1.0))
            Text(app.t("Vector Lab", "ベクトルラボ"))
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(Color(red: 0.85, green: 0.9, blue: 1.0))
            if case .jcrossReady(let m) = app.modelStatus {
                Text("· \(m)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.dim)
            }
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.black.opacity(0.4))
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Text(app.t(
                "No JGEN model loaded. Load one in Settings → JGEN first.",
                "JGENモデルが読み込まれていません。まずSettings → JGENで読み込んでください。"
            ))
            .font(.system(size: 11))
            .foregroundStyle(Theme.dim)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var encodeSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(app.t("1. Encode text → thought vector", "1. テキストを思考ベクトルへ変換"))
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.white)
            TextEditor(text: $inputText)
                .font(.system(size: 12))
                .frame(height: 70)
                .padding(4)
                .background(Color.white.opacity(0.03), in: RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Color.white.opacity(0.08)))
            HStack {
                Button(app.t("Encode", "エンコード")) {
                    encode()
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.sel)
                .disabled(isBusy || inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if isBusy { ProgressView().controlSize(.small) }
                if let vector {
                    Text(app.t("Vector ready (\(vector.count) dims)", "ベクトル準備完了(\(vector.count)次元)"))
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.ok)
                }
            }
        }
    }

    private var resynthesizeSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(app.t("2. Decode the vector back", "2. ベクトルをデコードして戻す"))
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.white)
            HStack(spacing: 8) {
                Text(app.t("Layer:", "層:"))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                TextField("lm_head", text: $layerName)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 140)
                    .font(.system(size: 11, design: .monospaced))
            }
            HStack(spacing: 8) {
                Button(app.t("Resynthesize", "再合成")) { resynthesize() }
                    .buttonStyle(.bordered)
                    .disabled(isBusy)
                Button(app.t("Puzzle Inference (entropy)", "パズル推論(エントロピー)")) { puzzleInference() }
                    .buttonStyle(.bordered)
                    .disabled(isBusy)
            }
            if let resynthesizedText {
                resultRow(label: app.t("Resynthesized token:", "再合成トークン:"), value: resynthesizedText)
            }
            if let puzzleText, let puzzleEntropy {
                resultRow(label: app.t("Most-confident token:", "最も確信度の高いトークン:"), value: "\"\(puzzleText)\"")
                resultRow(label: app.t("Entropy (lower = more confident):", "エントロピー(低いほど確信度が高い):"), value: String(format: "%.4f", puzzleEntropy))
            }
        }
    }

    private var optimizeSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(app.t("3. Optimize in vector space (latent gradient descent)", "3. ベクトル空間内で最適化(潜在勾配降下法)"))
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.white)
            Text(app.t(
                "Refines the vector directly, without sampling any tokens, to lower its entropy at the chosen layer.",
                "トークンを一切サンプリングせず、選択した層でのエントロピーが下がるようベクトルそのものを直接精錬します。"
            ))
            .font(.system(size: 9))
            .foregroundStyle(Theme.dim)

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(app.t("Steps: \(Int(optimizeSteps))", "ステップ数: \(Int(optimizeSteps))"))
                        .font(.system(size: 9)).foregroundStyle(.secondary)
                    Slider(value: $optimizeSteps, in: 1...100, step: 1).frame(width: 140)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(app.t("Learning rate: \(String(format: "%.3f", optimizeLR))", "学習率: \(String(format: "%.3f", optimizeLR))"))
                        .font(.system(size: 9)).foregroundStyle(.secondary)
                    Slider(value: $optimizeLR, in: 0.001...0.5).frame(width: 140)
                }
            }
            Button(app.t("Optimize", "最適化")) { optimize() }
                .buttonStyle(.borderedProminent)
                .tint(Theme.bad)
                .disabled(isBusy)

            if let optimizedText, let optimizedEntropy {
                resultRow(label: app.t("Optimized token:", "最適化後のトークン:"), value: "\"\(optimizedText)\"")
                resultRow(label: app.t("Optimized entropy:", "最適化後のエントロピー:"), value: String(format: "%.4f", optimizedEntropy))
            }
        }
    }

    // MARK: - Council mode

    private var councilSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(app.t(
                "Full Council port: 5-role divergence-packet scoring (S = A·C+B·E−C·R+D·N), multi-token soft-sequence injection, and a perturb-test fragility probe before accepting convergence. See code comments in CouncilOrchestrator.swift for the remaining simplifications vs. verantyx_council.py.",
                "Councilフル移植: 5役割のダイバージェンス・パケット・スコアリング(S = A·C+B·E−C·R+D·N)、マルチトークンのソフトシーケンス注入、収束を受け入れる前の摂動テスト(perturb-test)による頑健性確認。verantyx_council.pyとの残存する簡略化点はCouncilOrchestrator.swiftのコードコメントを参照。"
            ))
            .font(.system(size: 9))
            .foregroundStyle(Theme.dim)

            VStack(alignment: .leading, spacing: 4) {
                Text(app.t("Template", "テンプレート"))
                    .font(.system(size: 9)).foregroundStyle(.secondary)
                Picker("", selection: $councilPreset) {
                    ForEach(CouncilPreset.builtins) { preset in
                        Text(app.appLanguage == .japanese ? preset.nameJA : preset.name).tag(preset.id)
                    }
                    Text(app.t("Custom", "カスタム")).tag("custom")
                }
                .pickerStyle(.menu)
                .frame(width: 220)
                .onChange(of: councilPreset) { newValue in
                    guard let preset = CouncilPreset.builtins.first(where: { $0.id == newValue }) else { return }
                    applyPreset(preset)
                }
                if let preset = CouncilPreset.builtins.first(where: { $0.id == councilPreset }) {
                    Text(app.appLanguage == .japanese ? preset.descriptionJA : preset.description)
                        .font(.system(size: 9))
                        .foregroundStyle(Theme.dim)
                }
            }

            TextEditor(text: $councilQuestion)
                .font(.system(size: 12))
                .frame(height: 60)
                .padding(4)
                .background(Color.white.opacity(0.03), in: RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Color.white.opacity(0.08)))

            HStack(spacing: 16) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(app.t("Roles: \(Int(councilRoleCount))", "役割数: \(Int(councilRoleCount))"))
                        .font(.system(size: 9)).foregroundStyle(.secondary)
                    Slider(value: $councilRoleCount, in: 2...5, step: 1).frame(width: 120)
                        .onChange(of: councilRoleCount) { _ in markCustom() }
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(app.t("Rounds cap: \(Int(councilRoundsCap))", "ラウンド上限: \(Int(councilRoundsCap))"))
                        .font(.system(size: 9)).foregroundStyle(.secondary)
                    Slider(value: $councilRoundsCap, in: 1...8, step: 1).frame(width: 120)
                        .onChange(of: councilRoundsCap) { _ in markCustom() }
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(app.t("Injection policy", "注入ポリシー"))
                    .font(.system(size: 9)).foregroundStyle(.secondary)
                Picker("", selection: $councilPolicy) {
                    ForEach(CouncilOrchestrator.InjectionPolicy.allCases) { p in
                        Text(p.displayName).tag(p)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 340)
                .onChange(of: councilPolicy) { _ in markCustom() }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(app.t("Memory sources (independently selectable)", "記憶ソース(個別選択可能)"))
                    .font(.system(size: 9)).foregroundStyle(.secondary)
                Toggle(app.t("Vera-α (verified facts)", "Vera-α(検証済み事実)"), isOn: $councilUseVera)
                    .toggleStyle(.checkbox)
                    .font(.system(size: 11))
                    .onChange(of: councilUseVera) { _ in markCustom() }
                HStack(spacing: 12) {
                    ForEach([JCrossLayer.l1, .l1_5, .l2, .l3]) { layer in
                        Toggle(layer.rawValue, isOn: Binding(
                            get: { councilZoneLayers.contains(layer) },
                            set: { isOn in
                                if isOn { councilZoneLayers.insert(layer) } else { councilZoneLayers.remove(layer) }
                                markCustom()
                            }
                        ))
                        .toggleStyle(.checkbox)
                        .font(.system(size: 11))
                    }
                }
                Toggle(app.t("Eternal Memory (JGEN hidden-state recall)", "永遠記憶(JGEN隠れ状態リコール)"), isOn: $councilUseEternal)
                    .toggleStyle(.checkbox)
                    .font(.system(size: 11))
                    .onChange(of: councilUseEternal) { _ in markCustom() }
            }

            VStack(alignment: .leading, spacing: 6) {
                Toggle(app.t("Escalate on low confidence", "確信度が低い場合はエスカレーション"), isOn: $councilEscalate)
                    .toggleStyle(.checkbox)
                    .font(.system(size: 11))
                    .onChange(of: councilEscalate) { _ in markCustom() }
                if councilEscalate {
                    HStack(spacing: 8) {
                        Text(app.t("Threshold:", "閾値:"))
                            .font(.system(size: 9)).foregroundStyle(.secondary)
                        Slider(value: $councilThreshold, in: 0.1...0.95).frame(width: 120)
                            .onChange(of: councilThreshold) { _ in markCustom() }
                        Text(String(format: "%.2f", councilThreshold))
                            .font(.system(size: 9, design: .monospaced)).foregroundStyle(.secondary)
                    }
                    HStack(spacing: 8) {
                        Text(app.t("Escalate to (Ollama model):", "エスカレーション先(Ollamaモデル):"))
                            .font(.system(size: 9)).foregroundStyle(.secondary)
                        TextField(app.t("empty = report only, no call", "空欄=報告のみ、呼び出しなし"), text: $councilEscalationModel)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 180)
                            .font(.system(size: 10, design: .monospaced))
                            .onChange(of: councilEscalationModel) { _ in markCustom() }
                    }
                }
            }

            HStack(spacing: 8) {
                Button(app.t("Run Council", "評議会を実行")) { runCouncil() }
                    .buttonStyle(.borderedProminent)
                    .tint(Theme.accent)
                    .disabled(councilBusy || councilQuestion.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if councilBusy { ProgressView().controlSize(.small) }
            }

            if let councilError {
                Text(councilError)
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.bad)
            }

            if let councilResult {
                councilResultView(councilResult)
            }
        }
    }

    private func councilResultView(_ result: CouncilOrchestrator.Result) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider().opacity(0.2)
            Text(app.t("Result", "結果"))
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.white)

            resultRow(label: app.t("Conclusion:", "結論:"), value: result.handoff.conclusion)
            resultRow(label: app.t("Confidence:", "確信度:"), value: String(format: "%.2f", result.handoff.confidence))
            resultRow(label: app.t("Next action:", "次アクション:"), value: result.handoff.nextAction)
            VStack(alignment: .leading, spacing: 2) {
                Text(app.t("Evidence:", "根拠:"))
                    .font(.system(size: 10)).foregroundStyle(Theme.dim)
                ForEach(result.handoff.evidence, id: \.self) { line in
                    Text("· \(line)")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Color(red: 0.8, green: 0.8, blue: 0.85))
                }
            }

            if result.escalated {
                Divider().opacity(0.2)
                Label(app.t("Escalated", "エスカレーション済み"), systemImage: "arrow.up.circle.fill")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.warn)
                if let finalAnswer = result.finalAnswer {
                    Text(finalAnswer)
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.fg)
                        .textSelection(.enabled)
                } else {
                    Text(app.t("No escalation model configured -- reporting only.", "エスカレーション先モデル未設定 — 報告のみ。"))
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.dim)
                }
            }

            Divider().opacity(0.2)
            DisclosureGroup(app.t("Round-by-round trace (\(result.roundTraces.count) rounds)", "ラウンド別トレース(\(result.roundTraces.count)ラウンド)")) {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(result.roundTraces, id: \.round) { rt in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(app.t("Round \(rt.round)\(rt.converged ? " (converged)" : "")", "ラウンド \(rt.round)\(rt.converged ? "(収束)" : "")"))
                                .font(.system(size: 9, weight: .semibold))
                                .foregroundStyle(rt.converged ? Theme.ok : Theme.dim)
                            ForEach(rt.roles, id: \.role) { role in
                                Text("\(role.role): \"\(role.answer)\" (entropy \(String(format: "%.3f", role.entropy)))")
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundStyle(Color(red: 0.7, green: 0.7, blue: 0.78))
                            }
                        }
                    }
                }
                .padding(.top, 6)
            }
            .font(.system(size: 10))
        }
    }

    private func resultRow(label: String, value: String) -> some View {
        HStack(spacing: 6) {
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(Theme.dim)
            Text(value)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(Theme.fg)
                .textSelection(.enabled)
        }
    }

    // MARK: - Actions

    private func encode() {
        isBusy = true
        errorText = nil
        let text = inputText
        Task {
            do {
                let v = try await JCrossChatManager.shared.encodeText(text)
                await MainActor.run {
                    vector = v
                    resynthesizedText = nil
                    puzzleText = nil
                    puzzleEntropy = nil
                    optimizedText = nil
                    optimizedEntropy = nil
                    isBusy = false
                }
            } catch {
                await MainActor.run { errorText = error.localizedDescription; isBusy = false }
            }
        }
    }

    private func resynthesize() {
        guard let vector else { return }
        isBusy = true
        errorText = nil
        let layer = layerName
        Task {
            do {
                let text = try await JCrossChatManager.shared.resynthesizeToText(vector: vector, layerName: layer)
                await MainActor.run { resynthesizedText = text; isBusy = false }
            } catch {
                await MainActor.run { errorText = error.localizedDescription; isBusy = false }
            }
        }
    }

    private func puzzleInference() {
        guard let vector else { return }
        isBusy = true
        errorText = nil
        let layer = layerName
        Task {
            do {
                let (text, entropy) = try await JCrossChatManager.shared.puzzleInferenceText(vector: vector, layerName: layer)
                await MainActor.run { puzzleText = text; puzzleEntropy = entropy; isBusy = false }
            } catch {
                await MainActor.run { errorText = error.localizedDescription; isBusy = false }
            }
        }
    }

    private func optimize() {
        guard let vector else { return }
        isBusy = true
        errorText = nil
        let layer = layerName
        let steps = Int(optimizeSteps)
        let lr = Float(optimizeLR)
        Task {
            do {
                let (_, text, entropy) = try await JCrossChatManager.shared.optimizeVector(vector, layerName: layer, maxSteps: steps, lr: lr)
                await MainActor.run { optimizedText = text; optimizedEntropy = entropy; isBusy = false }
            } catch {
                await MainActor.run { errorText = error.localizedDescription; isBusy = false }
            }
        }
    }

    private func runCouncil() {
        councilBusy = true
        councilError = nil
        let question = councilQuestion
        let config = CouncilOrchestrator.Config(
            roleCount: Int(councilRoleCount),
            roundsCap: Int(councilRoundsCap),
            injectionPolicy: councilPolicy,
            useVeraMemory: councilUseVera,
            zoneLayers: councilZoneLayers,
            useEternalMemory: councilUseEternal,
            escalateOnLowConfidence: councilEscalate,
            escalationConfidenceThreshold: Float(councilThreshold),
            escalationModel: councilEscalationModel
        )
        Task {
            do {
                let result = try await CouncilOrchestrator.shared.deliberate(question: question, config: config)
                await MainActor.run { councilResult = result; councilBusy = false }
            } catch {
                await MainActor.run { councilError = error.localizedDescription; councilBusy = false }
            }
        }
    }

    /// Overwrites the Council @State config vars from `preset.config` --
    /// picking a template is just a bulk-set of the same fields manual
    /// editing touches, not a locked mode.
    private func applyPreset(_ preset: CouncilPreset) {
        isApplyingPreset = true
        let c = preset.config
        councilRoleCount = Double(c.roleCount)
        councilRoundsCap = Double(c.roundsCap)
        councilPolicy = c.injectionPolicy
        councilUseVera = c.useVeraMemory
        councilZoneLayers = c.zoneLayers
        councilUseEternal = c.useEternalMemory
        councilEscalate = c.escalateOnLowConfidence
        councilThreshold = Double(c.escalationConfidenceThreshold)
        councilEscalationModel = c.escalationModel
        DispatchQueue.main.async { isApplyingPreset = false }
    }

    /// Any manual edit to a Council field flips the template picker to
    /// "Custom" -- picking a preset just seeds initial values, it doesn't
    /// lock the form. Suppressed while `applyPreset` itself is bulk-setting
    /// those same fields.
    private func markCustom() {
        guard !isApplyingPreset else { return }
        if councilPreset != "custom" { councilPreset = "custom" }
    }
}
