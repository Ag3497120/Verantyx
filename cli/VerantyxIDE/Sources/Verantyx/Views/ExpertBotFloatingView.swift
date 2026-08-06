import SwiftUI

struct ExpertBotFloatingView: View {
    @StateObject private var engine = VerantyxExpertEngine.shared
    @State private var isOpen = false
    @State private var inputText = ""
    
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
                        .frame(width: 340, height: 420)
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
    
    private func sendMessage() {
        guard !inputText.isEmpty else { return }
        let query = inputText
        inputText = ""
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
