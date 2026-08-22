import SwiftUI

struct ExpertBotFloatingView: View {
    @EnvironmentObject var app: AppState
    @StateObject private var engine = VerantyxExpertEngine.shared
    @State private var isOpen = false
    @State private var inputText = ""
    /// Per-step outcome of the last Apply, keyed by step number. Shown inline
    /// so "I pressed it and nothing visible happened" cannot occur — including
    /// when the answer is that the app declined to set it.
    @State private var stepResults: [Int: String] = [:]
    
    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            HStack(spacing: 0) {
                Spacer()
                
                VStack(alignment: .trailing, spacing: 12) {
                    if isOpen {
                        // Chat window
                        VStack(spacing: 0) {
                            HStack {
                                Text("🤖 Verantyx System Support")
                                    .font(.system(size: 13, weight: .bold))
                                    .foregroundStyle(Color.blue)
                                Spacer()
                                Button {
                                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                                        isOpen = false
                                    }
                                } label: {
                                    Image(systemName: "xmark")
                                        .font(.system(size: 12, weight: .semibold))
                                        .foregroundStyle(.secondary)
                                }
                                .buttonStyle(.plain)
                            }
                            .padding()
                            .background(Color(red: 0.1, green: 0.1, blue: 0.13))
                            
                            Divider().opacity(0.3)
                            
                            ScrollViewReader { proxy in
                                ScrollView {
                                    VStack(alignment: .leading, spacing: 12) {
                                        ForEach(engine.messages.indices, id: \.self) { i in
                                            let msg = engine.messages[i]
                                            if msg.role != .system {
                                                ChatBubble(message: msg)
                                                    .id(i)
                                            }
                                        }
                                        if engine.isGenerating {
                                            HStack {
                                                ProgressView()
                                                    .scaleEffect(0.6)
                                                Text("Thinking...")
                                                    .font(.system(size: 11))
                                                    .foregroundStyle(.secondary)
                                            }
                                            .padding(.horizontal)
                                            .id("generating")
                                        }
                                        if let recipe = engine.activeRecipe {
                                            recipeSteps(recipe)
                                        }
                                    }
                                    .padding()
                                }
                                .onChange(of: engine.messages.count) { _ in
                                    withAnimation {
                                        proxy.scrollTo(engine.messages.count - 1, anchor: .bottom)
                                    }
                                }
                                .onChange(of: engine.isGenerating) { isGen in
                                    if isGen {
                                        withAnimation {
                                            proxy.scrollTo("generating", anchor: .bottom)
                                        }
                                    }
                                }
                            }
                            
                            Divider().opacity(0.3)
                            
                            HStack {
                                TextField("Ask about Setup, CLI...", text: $inputText)
                                    .textFieldStyle(.plain)
                                    .font(.system(size: 12))
                                    .padding(8)
                                    .background(Color.black.opacity(0.3))
                                    .cornerRadius(6)
                                    .onSubmit {
                                        sendMessage()
                                    }
                                
                                Button(action: {
                                    sendMessage()
                                }) {
                                    Image(systemName: "arrow.up.circle.fill")
                                        .font(.system(size: 20))
                                        .foregroundStyle(inputText.isEmpty ? Color.secondary : Color.blue)
                                }
                                .buttonStyle(.plain)
                                .disabled(inputText.isEmpty || engine.isGenerating)
                            }
                            .padding()
                            .background(Color(red: 0.1, green: 0.1, blue: 0.13))
                        }
                        .frame(width: 380, height: 520)
                        .background(Color(red: 0.12, green: 0.12, blue: 0.15))
                        .cornerRadius(12)
                        .shadow(color: Color.black.opacity(0.5), radius: 10, x: 0, y: 5)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Color.white.opacity(0.1), lineWidth: 1)
                        )
                        .transition(.scale(scale: 0.8, anchor: .bottomTrailing).combined(with: .opacity))
                    }
                    
                    // Floating Action Button
                    Button {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                            isOpen.toggle()
                        }
                    } label: {
                        ZStack {
                            Circle()
                                .fill(LinearGradient(
                                    colors: [Color(red: 0.2, green: 0.4, blue: 0.9), Color(red: 0.1, green: 0.2, blue: 0.6)],
                                    startPoint: .topLeading, endPoint: .bottomTrailing
                                ))
                                .frame(width: 50, height: 50)
                                .shadow(color: Color.blue.opacity(0.3), radius: 8, x: 0, y: 4)
                            
                            VXMarkView(size: 20, color: .white)
                                .offset(x: -1, y: 0) // Optical alignment
                        }
                    }
                    .buttonStyle(.plain)
                }
                .padding(.trailing, 24)
                .padding(.bottom, 24)
            }
        }
    }
    
    /// A recipe rendered as things you can do, not things to read. Each row
    /// carries why it matters, a button to the screen, and — only where the
    /// app can set it correctly — a button that sets it.
    @ViewBuilder
    private func recipeSteps(_ recipe: RecipeDTO) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(recipe.steps) { step in
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(step.n). " + app.t(step.title, step.title_ja))
                        .font(.system(size: 11, weight: .semibold))
                    Text(step.why)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let v = step.value {
                        Text(app.t("Set to: ", "設定値: ") + v)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color.accentColor)
                    }
                    HStack(spacing: 6) {
                        Button(app.t("Open", "開く")) {
                            engine.openScreen(for: step, app: app)
                        }
                        .controlSize(.mini)
                        if step.canApply {
                            Button(app.t("Apply", "設定する")) {
                                stepResults[step.n] = engine.applyStep(step, app: app)
                            }
                            .controlSize(.mini)
                        }
                        Text("Settings › \(step.tab)")
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.tertiary)
                    }
                    if let result = stepResults[step.n] {
                        Text(result)
                            .font(.system(size: 10))
                            .foregroundStyle(result.hasPrefix("✓") ? Color.green : Color.orange)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(0.05))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }
        }
    }

    private func sendMessage() {
        guard !inputText.isEmpty else { return }
        let query = inputText
        inputText = ""
        stepResults.removeAll()
        Task {
            await engine.sendQuery(query)
        }
    }
}

fileprivate struct ChatBubble: View {
    let message: ChatMessage
    
    var body: some View {
        HStack {
            if message.role == .user {
                Spacer()
                Text(message.content)
                    .font(.system(size: 12))
                    .padding(10)
                    .background(Color(red: 0.2, green: 0.4, blue: 0.8))
                    .foregroundStyle(.white)
                    .clipShape(
                        .rect(
                            topLeadingRadius: 12,
                            bottomLeadingRadius: 12,
                            bottomTrailingRadius: 0,
                            topTrailingRadius: 12
                        )
                    )
            } else {
                Text(message.content)
                    .font(.system(size: 12))
                    .padding(10)
                    .background(Color(red: 0.18, green: 0.18, blue: 0.22))
                    .foregroundStyle(.white)
                    .clipShape(
                        .rect(
                            topLeadingRadius: 12,
                            bottomLeadingRadius: 12,
                            bottomTrailingRadius: 12,
                            topTrailingRadius: 0
                        )
                    )
                Spacer()
            }
        }
    }
}
