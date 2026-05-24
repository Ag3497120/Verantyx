import SwiftUI

struct SwarmMonitorView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var swarm = SwarmEngine.shared
    @State private var flyingAirplanes: [UUID] = []
    @State private var fullDiveAgent: SwarmEngine.AgentState? = nil
    
    // For responsive layout (adaptive to vertical/horizontal)
    @Environment(\.horizontalSizeClass) var hSizeClass
    @Environment(\.verticalSizeClass) var vSizeClass
    
    var body: some View {
        ZStack {
            GeometryReader { geo in
                let isVertical = geo.size.height > geo.size.width
            
            if isVertical {
                VStack(spacing: 0) {
                    AgentChatView()
                        .frame(height: geo.size.height * 0.45)
                    Divider().background(Color.black)
                    agentsGridPanel
                }
                .background(Color(red: 0.08, green: 0.08, blue: 0.1))
            } else {
                HStack(spacing: 0) {
                    AgentChatView()
                        .frame(width: max(350, geo.size.width * 0.45))
                    Divider().background(Color.black)
                    agentsGridPanel
                }
                .background(Color(red: 0.08, green: 0.08, blue: 0.1))
            }
            }
            .blur(radius: fullDiveAgent != nil ? 10 : 0)
            .scaleEffect(fullDiveAgent != nil ? 0.95 : 1.0)
            .animation(.spring(response: 0.4, dampingFraction: 0.8), value: fullDiveAgent != nil)
            
            // L2 Full Dive Modal
            if let agent = fullDiveAgent {
                Color.black.opacity(0.6).edgesIgnoringSafeArea(.all)
                    .onTapGesture { fullDiveAgent = nil }
                    .zIndex(1)
                
                AgentFullIDEView(agent: agent, onClose: { fullDiveAgent = nil })
                    .frame(maxWidth: 1100, maxHeight: 750)
                    .background(Color(red: 0.1, green: 0.1, blue: 0.12))
                    .cornerRadius(12)
                    .shadow(radius: 20)
                    .zIndex(2)
                    .transition(.scale(scale: 0.8).combined(with: .opacity))
            }
        }
    }
    
    // MARK: - Router Panel removed in favor of standard AgentChatView
    
    // MARK: - Agents Grid Panel (BitNet Swarm)
    private var agentsGridPanel: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "cpu")
                    .foregroundColor(.green)
                Text("BitNet Swarm (\(swarm.maxWorkers) Agents)")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(.white)
                Spacer()
                
                let dist = swarm.getDistribution(for: swarm.maxWorkers)
                
                Text("E-Core: \(dist.totalEcore) | NPU: \(dist.totalNPU) | P-Core: \(dist.totalPcore)")
                    .font(.system(size: 11, weight: .bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.gray.opacity(0.2))
                    .cornerRadius(4)
            }
            .padding([.horizontal, .top])
            
            // Distributed Swarm Telemetry
            if app.cortexSwarmActive || app.swarmNodeCount > 0 {
                HStack {
                    Image(systemName: "network")
                        .foregroundColor(.purple)
                    Text("Distributed Swarm:")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.white)
                    Text("\(app.swarmNodeCount) nodes")
                        .font(.system(size: 12))
                        .foregroundColor(.blue)
                    Text("• \(app.swarmStatusText)")
                        .font(.system(size: 12))
                        .foregroundColor(.gray)
                    Spacer()
                }
                .padding(.horizontal)
                .padding(.top, 4)
                .padding(.bottom, 8)
            } else {
                Spacer().frame(height: 8)
            }
            
            if app.operationMode == .gatekeeper {
                HStack {
                    Text("Swarm Strategy:")
                        .font(.system(size: 12))
                        .foregroundColor(.gray)
                    
                    Picker("", selection: $swarm.currentStrategy) {
                        Text("Ultrawork").tag(SwarmEngine.SwarmStrategy.ultrawork)
                        Text("Ralph").tag(SwarmEngine.SwarmStrategy.ralph)
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 200)
                    
                    Spacer()
                }
                .padding(.horizontal)
                .padding(.bottom, 4)
            }
            
            // Provisioning Controls
            HStack {
                Text("Allocate Workers:")
                    .font(.system(size: 12))
                    .foregroundColor(.gray)
                
                Picker("", selection: $swarm.maxWorkers) {
                    Text("10").tag(10)
                    Text("20").tag(20)
                    Text("50").tag(50)
                }
                .pickerStyle(.segmented)
                .frame(width: 150)
                
                Button(action: {
                    Task {
                        await swarm.provisionSwarm(baseModel: app.activeOllamaModel, count: swarm.maxWorkers)
                    }
                }) {
                    HStack(spacing: 4) {
                        if swarm.isProvisioning {
                            ProgressView().controlSize(.small)
                        } else {
                            Image(systemName: "square.and.arrow.down.fill")
                        }
                        Text(swarm.provisionedWorkers > 0 ? "Re-Provision" : "Provision")
                    }
                    .font(.system(size: 11, weight: .bold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(swarm.isProvisioning ? Color.gray : Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(6)
                }
                .buttonStyle(.plain)
                .disabled(swarm.isProvisioning || app.activeOllamaModel.isEmpty)
                
                Spacer()
                
                if swarm.provisionedWorkers > 0 {
                    Text("\(swarm.provisionedWorkers) Ready")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.green)
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 8)
            .background(Color(red: 0.1, green: 0.12, blue: 0.1))
            
            ScrollView {
                // Adaptive grid for 50 agents
                let columns = [
                    GridItem(.adaptive(minimum: 120, maximum: 160), spacing: 12)
                ]
                
                ZStack {
                    LazyVGrid(columns: columns, spacing: 12) {
                        if swarm.activeAgents.isEmpty {
                            Text("No agents provisioned. Click Provision.")
                                .font(.system(size: 14))
                                .foregroundColor(.gray)
                                .padding()
                        } else {
                            ForEach(swarm.activeAgents) { agent in
                                AgentLiveStatusBox(agent: agent, fullDiveAgent: $fullDiveAgent)
                            }
                        }
                    }
                    .padding()
                    
                    // Paper airplane overlay
                    ForEach(flyingAirplanes, id: \.self) { id in
                        Image(systemName: "paperplane.fill")
                            .foregroundColor(.blue)
                            .font(.system(size: 24))
                            .modifier(PaperAirplaneFlightModifier(id: id) {
                                flyingAirplanes.removeAll(where: { $0 == id })
                            })
                    }
                }
            }
        }
        .onChange(of: swarm.completedTaskCount) { _ in
            // Spawn an airplane whenever a task completes
            flyingAirplanes.append(UUID())
        }
    }
}

// MARK: - Subcomponents

struct AgentLiveStatusBox: View {
    let agent: SwarmEngine.AgentState
    @Binding var fullDiveAgent: SwarmEngine.AgentState?
    @State private var isHovered = false
    @State private var isExpanded = false
    @State private var interruptionText = ""
    @State private var showFullIDE = false
    @State private var flashError = false
    
    var baseColor: Color {
        switch agent.role {
        case .microCoder: return .green
        case .linter: return .teal
        case .testGenerator: return .mint
        case .astValidator: return .orange
        case .securityChecker: return .red
        case .stealthScout: return .purple
        case .jcrossCompressor: return .indigo
        case .specBrainstormer: return .blue
        case .router: return .purple
        case .auditor: return .yellow
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Circle()
                    .fill(statusColor)
                    .frame(width: 8, height: 8)
                    .modifier(PulseEffect(isActive: agent.status == .inProgress || agent.status == .checking))
                
                Text(agent.id)
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                    .foregroundColor(baseColor)
                    .lineLimit(1)
                
                Spacer()
                
                if agent.hasAuditFlag {
                    Text("⚠️ AI Audit")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundColor(.black)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(Color.yellow)
                        .cornerRadius(4)
                } else if agent.status == .awaitingDiffApproval {
                    Text("Review Diff")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(Color.blue)
                        .cornerRadius(4)
                }
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.spring(response: 0.4, dampingFraction: 0.7)) {
                    isExpanded.toggle()
                }
            }
            
            Text(statusText)
                .font(.system(size: 10))
                .foregroundColor(.gray)
            
            if let task = agent.currentTask {
                Text(task)
                    .font(.system(size: 9))
                    .foregroundColor(.white.opacity(0.8))
                    .lineLimit(1)
            }
            
            if let output = agent.lastOutput, !output.isEmpty, agent.status == .inProgress || agent.status == .checking {
                Text(output.suffix(150).replacingOccurrences(of: "\n", with: " "))
                    .font(.system(size: 4, weight: .regular, design: .monospaced))
                    .foregroundColor(agent.status == .failed ? .red : baseColor.opacity(0.8))
                    .lineLimit(2)
                    .truncationMode(.tail)
                    .frame(height: 12, alignment: .bottomLeading)
                    .drawingGroup() // Helps with performance
            } else if agent.status == .awaitingRouter {
                Text("🔄 Retrying... (Gatekeeper Rejected)")
                    .font(.system(size: 6, weight: .bold))
                    .foregroundColor(.red)
                    .frame(height: 12, alignment: .leading)
            } else {
                Spacer().frame(height: 12)
            }
            
            // Mock memory usage bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Rectangle().fill(Color.black.opacity(0.5))
                    Rectangle().fill(baseColor.opacity(0.7))
                        .frame(width: geo.size.width * CGFloat.random(in: 0.3...0.9))
                }
                .cornerRadius(2)
            }
            .frame(height: 4)
        }
        .padding(10)
        .background(flashError ? Color.red.opacity(0.6) : Color(red: 0.15, green: 0.15, blue: 0.18))
        .cornerRadius(6)
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(flashError ? Color.red : statusColor.opacity(0.4), lineWidth: flashError ? 2 : 1)
        )
        .animation(.easeInOut(duration: 0.3), value: flashError)
        // Loupe Interaction
        .scaleEffect(isHovered ? 1.15 : 1.0)
        .zIndex(isHovered ? 50 : 0)
        .shadow(color: baseColor.opacity(isHovered ? 0.6 : 0), radius: 10)
        .onHover { hovering in
            withAnimation(.spring(response: 0.3, dampingFraction: 0.6)) {
                isHovered = hovering
            }
        }
        .onChange(of: agent.status) { newStatus in
            if newStatus == .awaitingRouter || newStatus == .failed {
                flashError = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                    flashError = false
                }
            }
        }
        .popover(isPresented: $isExpanded, arrowEdge: .bottom) {
            AgentL1PopoverView(agent: agent, isPresented: $isExpanded, fullDiveAgent: $fullDiveAgent)
        }
    }
    
    var statusColor: Color {
        switch agent.status {
        case .pending: return .gray
        case .inProgress: return .green
        case .checking: return .orange
        case .completed: return .blue
        case .failed: return .red
        case .awaitingRouter: return .yellow
        case .awaitingDiffApproval: return .cyan
        }
    }
    
    var statusText: String {
        switch agent.status {
        case .pending: return "Waiting..."
        case .inProgress: return "Processing..."
        case .checking: return "Validating..."
        case .completed: return "Done"
        case .failed: return "Rejected"
        case .awaitingRouter: return "Awaiting Router"
        case .awaitingDiffApproval: return "Awaiting Diff Approval"
        }
    }
}

// MARK: - L1 Quick Intercept View
struct StripePattern: View {
    var body: some View {
        GeometryReader { geometry in
            Path { path in
                let width = geometry.size.width * 2
                let height = geometry.size.height * 2
                let step: CGFloat = 20
                for i in stride(from: -height, to: width, by: step * 2) {
                    path.move(to: CGPoint(x: i, y: 0))
                    path.addLine(to: CGPoint(x: i + height, y: height))
                }
            }
            .stroke(Color.red.opacity(0.4), lineWidth: 10)
        }
        .clipped()
    }
}

struct AgentL1PopoverView: View {
    let agent: SwarmEngine.AgentState
    @Binding var isPresented: Bool
    @Binding var fullDiveAgent: SwarmEngine.AgentState?
    @State private var interruptionText = ""
    @State private var isAnimatingInterruption = false
    @State private var flyingText = ""
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Text("Command the Agent...")
                    .font(.headline)
                Spacer()
                Button(action: {
                    isPresented = false
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                        fullDiveAgent = agent
                    }
                }) {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.up.left.and.arrow.down.right")
                        Text("拡大")
                    }
                }
                .buttonStyle(.plain)
                .foregroundColor(.blue)
            }
            
            // Auditor Note
            if agent.hasAuditFlag, let comment = agent.auditComment {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("🤖 Auditor Note:")
                            .font(.caption).bold()
                        Spacer()
                        Button("Dismiss") {
                            SwarmEngine.shared.dismissAudit(agentId: agent.id)
                        }
                        .font(.caption)
                        .buttonStyle(.plain)
                        .foregroundColor(.blue)
                    }
                    Text(comment)
                        .font(.caption)
                }
                .padding(8)
                .background(Color.yellow.opacity(0.2))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.yellow, lineWidth: 1))
            }
            
            // Diff Approval vs Regular Output
            if agent.status == .awaitingDiffApproval, let diff = agent.proposedDiff {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Proposed Diff (Awaiting Approval):")
                        .font(.caption).bold()
                        .foregroundColor(.blue)
                    
                    ScrollView {
                        Text(diff)
                            .font(.system(size: 11, design: .monospaced))
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(height: 120)
                    .background(Color.black.opacity(0.8))
                    .cornerRadius(6)
                    
                    HStack {
                        Button("Approve") {
                            SwarmEngine.shared.approveDiff(agentId: agent.id)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.blue)
                        
                        Button("Reject") {
                            SwarmEngine.shared.rejectDiff(agentId: agent.id, reason: "User manually rejected the diff.")
                        }
                        .buttonStyle(.bordered)
                        
                        Button("ずっと承認") {
                            SwarmEngine.shared.approveDiffAlways(agentId: agent.id)
                        }
                        .buttonStyle(.bordered)
                        .tint(.green)
                    }
                }
            } else {
                // Output view (Read-only super lightweight editor)
                ScrollView {
                    Text(agent.lastOutput ?? "No code generated yet.")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(agent.status == .awaitingRouter ? .gray : .green)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(height: 150)
                .background(
                    ZStack {
                        Color.black.opacity(0.8)
                        if agent.status == .awaitingRouter {
                            StripePattern()
                            Rectangle()
                                .fill(Color.red.opacity(0.2))
                            Text("AWAITING ROUTER")
                                .font(.largeTitle).bold()
                                .foregroundColor(.red.opacity(0.5))
                                .rotationEffect(.degrees(-15))
                        }
                    }
                )
                .cornerRadius(6)
            }
            
            // Input Field
            HStack {
                TextField("ここから先はswitchで書いて...", text: $interruptionText)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { submitInterruption() }
                
                Button(action: submitInterruption) {
                    Image(systemName: "paperplane.fill")
                        .foregroundColor(.white)
                        .padding(6)
                        .background(Color.blue)
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
            }
            .overlay(
                Group {
                    if isAnimatingInterruption {
                        Text(flyingText)
                            .padding(8)
                            .background(Color.blue)
                            .foregroundColor(.white)
                            .cornerRadius(12)
                            .shadow(radius: 5)
                            .modifier(FlyingBubbleModifier(isActive: isAnimatingInterruption) {
                                isAnimatingInterruption = false
                            })
                    }
                }
                , alignment: .trailing
            )
        }
        .padding()
        .frame(width: 400)
    }
    
    private func submitInterruption() {
        guard !interruptionText.isEmpty else { return }
        
        flyingText = interruptionText
        let msgToRouter = interruptionText
        interruptionText = ""
        
        // Trigger flying animation
        withAnimation {
            isAnimatingInterruption = true
        }
        
        // Wait for animation to visually "fly" towards Gemma Router
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
            SwarmEngine.shared.interruptWorker(agentId: agent.id, message: msgToRouter)
        }
    }
}

struct FlyingBubbleModifier: ViewModifier {
    let isActive: Bool
    let onCompletion: () -> Void
    
    @State private var offset: CGSize = .zero
    @State private var scale: CGFloat = 1.0
    @State private var opacity: Double = 1.0
    
    func body(content: Content) -> some View {
        content
            .offset(offset)
            .scaleEffect(scale)
            .opacity(opacity)
            .onAppear {
                offset = .zero
                scale = 1.0
                opacity = 1.0
                withAnimation(.easeOut(duration: 0.6)) {
                    offset = CGSize(width: -300, height: -100) // Fly physically leftwards towards Gemma Panel
                    scale = 0.2
                    opacity = 0.0
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.65) {
                    onCompletion()
                }
            }
    }
}

struct PulseEffect: ViewModifier {
    let isActive: Bool
    @State private var isAnimating = false
    
    func body(content: Content) -> some View {
        content
            .scaleEffect(isAnimating ? 1.2 : 1.0)
            .opacity(isAnimating ? 0.7 : 1.0)
            .onAppear {
                if isActive {
                    withAnimation(Animation.easeInOut(duration: 0.6).repeatForever(autoreverses: true)) {
                        isAnimating = true
                    }
                }
            }
            .onChange(of: isActive) { _, active in
                if active {
                    withAnimation(Animation.easeInOut(duration: 0.6).repeatForever(autoreverses: true)) {
                        isAnimating = true
                    }
                } else {
                    withAnimation { isAnimating = false }
                }
            }
    }
}

// MARK: - Animations

struct PaperAirplaneFlightModifier: ViewModifier {
    let id: UUID
    let onCompletion: () -> Void
    
    @State private var offset: CGSize = CGSize(width: CGFloat.random(in: -300...300), height: CGFloat.random(in: 200...400))
    @State private var opacity: Double = 1.0
    @State private var scale: CGFloat = 1.0
    
    func body(content: Content) -> some View {
        content
            .offset(offset)
            .opacity(opacity)
            .scaleEffect(scale)
            .onAppear {
                withAnimation(.easeIn(duration: 0.8)) {
                    // Fly towards center (JCross/Vault)
                    offset = CGSize(width: 0, height: -150)
                    scale = 0.2
                    opacity = 0.0
                }
                
                // Cleanup after animation finishes
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.85) {
                    onCompletion()
                }
            }
    }
}

// MARK: - Full IDE View for Specific Agent
struct AgentFullIDEView: View {
    let agent: SwarmEngine.AgentState
    var onClose: () -> Void
    
    @State private var editableBuffer: String = ""
    @State private var escalationMessage: String = ""
    @State private var isEscalating: Bool = false
    @State private var lightningFlash: Double = 0.0
    
    init(agent: SwarmEngine.AgentState, onClose: @escaping () -> Void) {
        self.agent = agent
        self.onClose = onClose
        _editableBuffer = State(initialValue: agent.lastOutput ?? "")
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Image(systemName: "cpu.fill")
                    .foregroundColor(.purple)
                Text("L2 Full Dive: \(agent.id) (\(agent.role.rawValue))")
                    .font(.headline)
                    .foregroundColor(.white)
                Spacer()
                Button("Close") { onClose() }
                    .foregroundColor(.blue)
                    .buttonStyle(.plain)
            }
            .padding()
            .background(Color(red: 0.1, green: 0.1, blue: 0.12))
            
            // IDE Content: Split view
            HStack(spacing: 0) {
                // Left: Context Inspector
                VStack(alignment: .leading, spacing: 0) {
                    Text("Context Inspector")
                        .font(.headline)
                        .padding()
                    
                    Text("System Prompt (Absolute Command)")
                        .font(.caption).bold().foregroundColor(.gray)
                        .padding(.horizontal)
                    ScrollView {
                        Text(agent.systemPrompt ?? "Wait for Router to assign prompt...")
                            .font(.system(size: 11, design: .monospaced))
                            .padding()
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .background(Color.black.opacity(0.3))
                    .overlay(
                        Color.white.opacity(lightningFlash)
                            .allowsHitTesting(false)
                    )
                    
                    Divider().background(Color.gray)
                    
                    Text("Visible JCross AST (Topology)")
                        .font(.caption).bold().foregroundColor(.gray)
                        .padding([.horizontal, .top])
                    ScrollView {
                        Text(agent.visibleJCrossAST ?? "No AST scope available.")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundColor(.blue)
                            .padding()
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .background(Color.black.opacity(0.3))
                }
                .frame(width: 300)
                .background(Color(red: 0.12, green: 0.12, blue: 0.15))
                
                Divider().background(Color.gray)
                
                // Center: Full Editor (Editable)
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        Text("BitNet Buffer (Editable)")
                            .font(.caption).bold().foregroundColor(.gray)
                        Spacer()
                        if agent.status == .awaitingRouter {
                            Text("AWAITING ROUTER")
                                .font(.caption).bold()
                                .foregroundColor(.red)
                        }
                    }
                    .padding()
                    .background(Color(red: 0.15, green: 0.15, blue: 0.18))
                    
                    TextEditor(text: $editableBuffer)
                        .font(.system(size: 13, design: .monospaced))
                        .foregroundColor(.green)
                        .padding()
                        .background(Color.black)
                }
                .frame(maxWidth: .infinity)
                
                Divider().background(Color.gray)
                
                // Right: Escalation Chat
                VStack(spacing: 0) {
                    Text("Escalation (To Router & PM)")
                        .font(.headline)
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(red: 0.15, green: 0.15, blue: 0.18))
                    
                    ScrollView {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("When you send a message, your current edits and instruction will be packaged and sent to Gemma Router. The Router will then issue a new System Prompt to this BitNet worker.")
                                .font(.caption)
                                .foregroundColor(.gray)
                                .padding()
                            
                            if isEscalating {
                                HStack {
                                    ProgressView()
                                        .scaleEffect(0.5)
                                    Text("Gemma is re-evaluating...")
                                        .font(.caption)
                                        .foregroundColor(.orange)
                                }
                                .padding()
                            }
                        }
                    }
                    
                    HStack {
                        TextField("Instruct Gemma to fix...", text: $escalationMessage)
                            .textFieldStyle(.roundedBorder)
                            .onSubmit {
                                Task { await escalate() }
                            }
                        
                        Button(action: {
                            Task { await escalate() }
                        }) {
                            Image(systemName: "paperplane.fill")
                                .foregroundColor(.white)
                                .padding(6)
                                .background(Color.blue)
                                .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                        .disabled(escalationMessage.isEmpty || isEscalating)
                    }
                    .padding()
                    .background(Color(red: 0.12, green: 0.12, blue: 0.15))
                }
                .frame(width: 350)
                .background(Color(red: 0.1, green: 0.1, blue: 0.12))
            }
        }
        .frame(minWidth: 1000, minHeight: 650)
    }
    
    private func escalate() async {
        guard !escalationMessage.isEmpty else { return }
        isEscalating = true
        
        let msg = "Manual edits applied:\n```\n\(editableBuffer)\n```\nUser instruction: \(escalationMessage)"
        SwarmEngine.shared.interruptWorker(agentId: agent.id, message: msg)
        
        escalationMessage = ""
        
        // Simulate waiting for Gemma and then a lightning flash
        try? await Task.sleep(nanoseconds: 1_500_000_000)
        
        await MainActor.run {
            withAnimation(.easeIn(duration: 0.1)) {
                lightningFlash = 1.0
            }
            withAnimation(.easeOut(duration: 0.5).delay(0.1)) {
                lightningFlash = 0.0
            }
            isEscalating = false
        }
    }
}
