import SwiftUI

// MARK: - MCPView
// MCP management: server list, add/edit, connect, and KILL SWITCH dashboard.
// Layout: single-column vertical (no HSplitView) — designed to fit inside
// the IDE's left sidebar pane which has limited horizontal space.

struct MCPView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var mcp = MCPEngine.shared
    @State private var showAddSheet       = false
    @State private var editingServer: MCPServerConfig? = nil
    @State private var selectedServerId: UUID? = nil
    @State private var showCatalogPicker  = false
    @State private var apiKeyTargetServer: MCPServerConfig? = nil

    var body: some View {
        VStack(spacing: 0) {
            killSwitchBanner   // top priority — always visible when something is running

            // ── Server list (top section) ──────────────────────────
            serverListHeader
            Divider().opacity(0.3)

            // ── Scrollable content: server rows + inline detail ────
            if mcp.servers.isEmpty {
                emptyServerList
            } else {
                ScrollView {
                    VStack(spacing: 0) {
                        // Server rows
                        LazyVStack(spacing: 1) {
                            ForEach(mcp.servers) { server in
                                ServerRow(
                                    server: server,
                                    status: mcp.connectionStatus[server.id] ?? .disconnected,
                                    isSelected: selectedServerId == server.id
                                )
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    withAnimation(.easeInOut(duration: 0.15)) {
                                        selectedServerId = selectedServerId == server.id ? nil : server.id
                                    }
                                }
                                .contextMenu {
                                    Button("Edit") { editingServer = server }
                                    Button("Connect") { Task { await mcp.connect(server: server) } }
                                    Button("Disconnect") { mcp.disconnect(serverId: server.id) }
                                    Divider()
                                    Button("Delete", role: .destructive) { mcp.removeServer(id: server.id) }
                                }
                            }
                        }
                        .padding(.vertical, 6)

                        // ── Inline server detail ─────────────────────
                        if let id = selectedServerId,
                           let server = mcp.servers.first(where: { $0.id == id }) {
                            Divider().opacity(0.3)
                            serverDetailInline(server)
                        }
                    }
                }
            }

            Divider().opacity(0.3)

            // Quick templates
            HStack(spacing: 0) {
                Menu {
                    ForEach(MCPServerConfig.examples) { example in
                        Button(example.name) {
                            mcp.addServer(example)
                        }
                    }
                } label: {
                    Label("Add from template", systemImage: "square.on.square")
                        .font(.system(size: 10))
                }
                .menuStyle(.borderlessButton)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                Spacer()
            }
            .background(Color(red: 0.09, green: 0.09, blue: 0.12))
        }
        .sheet(isPresented: $showAddSheet) {
            MCPServerEditSheet(config: .init(name: "", transport: .stdio, command: "", mode: .ai)) { saved in
                mcp.addServer(saved)
                showAddSheet = false
            }
            .frame(width: 500, height: 560)
        }
        .sheet(item: $editingServer) { server in
            MCPServerEditSheet(config: server) { saved in
                mcp.updateServer(saved)
                editingServer = nil
            }
            .frame(width: 500, height: 560)
        }
        // カタログ選択シート
        .sheet(isPresented: $showCatalogPicker) {
            MCPCatalogPickerSheet { entry in
                let config = MCPServerConfig(
                    name: entry.displayName,
                    command: entry.defaultCommand,
                    envVars: Dictionary(uniqueKeysWithValues: entry.requiredEnv.map { ($0.key, "") }),
                    mode: .ai
                )
                mcp.addServer(config)
                showCatalogPicker = false
                // 必須環境変数があれば直後に API キー入力シートを開く
                if !entry.requiredEnv.isEmpty {
                    apiKeyTargetServer = config
                }
            }
            .frame(width: 420, height: 480)
        }
        // API キー入力シート
        .sheet(item: $apiKeyTargetServer) { server in
            MCPApiKeySheet(server: server) {
                apiKeyTargetServer = nil
                // 保存後に自動再接続
                Task { await mcp.restartServer(id: server.id) }
            }
            .frame(width: 440, height: 360)
        }
    }

    // MARK: - Kill Switch Banner

    @ViewBuilder
    private var killSwitchBanner: some View {
        if let call = mcp.activeCall, case .running = call.status {
            HStack(spacing: 10) {
                Circle()
                    .fill(Color.red)
                    .frame(width: 8, height: 8)
                    .opacity(0.9)

                VStack(alignment: .leading, spacing: 1) {
                    Text("MCP RUNNING")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(Color(red: 1.0, green: 0.4, blue: 0.4))
                    Text("\(call.serverName) → \(call.toolName)  [\(call.elapsedSeconds)s]")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)

                Button {
                    mcp.killActiveCall()
                    app.logProcess("KILL SWITCH — '\(call.toolName)' forcibly cancelled", kind: .system)
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "xmark.octagon.fill")
                            .foregroundStyle(.red)
                        Text("KILL")
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .foregroundStyle(.red)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.red.opacity(0.15), in: RoundedRectangle(cornerRadius: 5))
                    .overlay(
                        RoundedRectangle(cornerRadius: 5)
                            .strokeBorder(Color.red.opacity(0.6), lineWidth: 1)
                    )
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .keyboardShortcut(.escape, modifiers: [.command, .shift])
                .help("Force cancel the running MCP tool call (⌘⇧Esc)")
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(Color(red: 0.25, green: 0.08, blue: 0.08))
            .overlay(alignment: .bottom) {
                Rectangle().fill(Color.red.opacity(0.3)).frame(height: 1)
            }
        }
    }

    // MARK: - Server List Header

    private var serverListHeader: some View {
        HStack {
            Text("MCP SERVERS")
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundStyle(.secondary)
            Spacer()
            // 全サーバーリロード（途中で追加した MCP を再認識）
            Button {
                Task { await mcp.reloadAll() }
            } label: {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .font(.system(size: 10))
                    .foregroundStyle(Color(red: 0.4, green: 0.75, blue: 1.0))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .help(AppLanguage.shared.t("Reconnect all MCP servers (includes newly added)", "全 MCP サーバーを再接続（途中で追加したものも認識）"))

            Button {
                Task { await mcp.connectAll() }
            } label: {
                Image(systemName: "bolt.fill")
                    .font(.system(size: 10))
                    .foregroundStyle(Color(red: 0.4, green: 0.9, blue: 0.5))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .help(AppLanguage.shared.t("Connect all enabled servers", "全有効サーバーに接続"))

            // カタログから追加
            Button { showCatalogPicker = true } label: {
                Image(systemName: "square.grid.2x2.fill")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .help(AppLanguage.shared.t("Add from MCP catalog", "既知 MCP カタログから追加"))

            Button { showAddSheet = true } label: {
                Image(systemName: "plus")
                    .font(.system(size: 11))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color(red: 0.09, green: 0.09, blue: 0.12))
    }

    // MARK: - Server detail (inline, stacked vertically under list)

    private func serverDetailInline(_ server: MCPServerConfig) -> some View {
        VStack(alignment: .leading, spacing: 10) {

            // Server info header
            HStack(spacing: 8) {
                Image(systemName: transportIcon(server.transport))
                    .font(.system(size: 14))
                    .foregroundStyle(statusColor(for: server.id))
                VStack(alignment: .leading, spacing: 2) {
                    Text(server.name)
                        .font(.system(size: 12, weight: .bold))
                    Text(server.transport == .stdio ? server.command : server.url)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Spacer(minLength: 0)
                modeBadge(server.mode)
            }

            // Connection controls
            HStack(spacing: 6) {
                Button {
                    Task { await mcp.connect(server: server) }
                } label: {
                    Label("Connect", systemImage: "bolt")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.mini)
                .disabled(isConnecting(server.id))

                // 再起動ボタン — プロセスを即座にキルして再接続
                Button {
                    Task { await mcp.restartServer(id: server.id) }
                } label: {
                    Label(AppLanguage.shared.t("Restart", "再起動"), systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .controlSize(.mini)
                .tint(Color(red: 0.4, green: 0.75, blue: 1.0))

                Button {
                    mcp.disconnect(serverId: server.id)
                } label: {
                    Label("Disconnect", systemImage: "eject")
                }
                .buttonStyle(.bordered)
                .controlSize(.mini)

                Button("Edit") { editingServer = server }
                    .buttonStyle(.bordered)
                    .controlSize(.mini)
            }

            // Keychain API キー欠子警告
            let catalogEntry = MCPCatalog.find(byName: server.name)
            if let entry = catalogEntry, !entry.requiredEnv.isEmpty {
                let missingKeys = entry.requiredEnv.filter { spec in
                    let stored = MCPKeychainStore.load(key: "\(server.id).\(spec.key)")
                    return (stored ?? "").isEmpty && (server.envVars[spec.key] ?? "").isEmpty
                }
                if !missingKeys.isEmpty {
                    Button {
                        apiKeyTargetServer = server
                    } label: {
                        Label(AppLanguage.shared.t("⚠️ Set API Key...", "⚠️ API キーを設定…"), systemImage: "key.fill")
                            .font(.system(size: 10))
                            .foregroundStyle(Color(red: 1.0, green: 0.75, blue: 0.2))
                    }
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
                }
            }

            let status = mcp.connectionStatus[server.id] ?? .disconnected
            Text(statusLabel(status))
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(statusColor(for: server.id))

            Divider().opacity(0.3)

            // Available tools
            let tools = mcp.connectedTools.filter { $0.serverName == server.name }
            if tools.isEmpty {
                Text("No tools discovered.\nConnect the server first.")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    Text("TOOLS (\(tools.count))")
                        .font(.system(size: 9, weight: .semibold, design: .monospaced))
                        .foregroundStyle(.tertiary)
                    ForEach(tools) { tool in
                        ToolRow(tool: tool, serverMode: server.mode) { args in
                            Task {
                                let result = await mcp.callTool(
                                    serverName: server.name, toolName: tool.name,
                                    arguments: args, mode: server.mode
                                )
                                app.addSystemMessage("[\(tool.name)] \(result.prefix(300))")
                            }
                        }
                    }
                }
            }

            // Call history for this server
            let history = mcp.callHistory.filter { $0.serverName == server.name }
            if !history.isEmpty {
                Divider().opacity(0.3)
                VStack(alignment: .leading, spacing: 4) {
                    Text("CALL HISTORY")
                        .font(.system(size: 9, weight: .semibold, design: .monospaced))
                        .foregroundStyle(.tertiary)
                    ForEach(history.prefix(10)) { record in
                        HStack(spacing: 6) {
                            Circle().fill(record.statusColor).frame(width: 6, height: 6)
                            Text(record.toolName)
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                            Spacer(minLength: 0)
                            Text(record.statusLabel)
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(record.statusColor)
                        }
                    }
                }
            }
        }
        .padding(10)
        .background(Color(red: 0.10, green: 0.10, blue: 0.14))
    }

    private var emptyServerList: some View {
        VStack(spacing: 10) {
            Spacer()
            Image(systemName: "plus.circle.dashed")
                .font(.system(size: 24))
                .foregroundStyle(.tertiary)
            Text("No MCP servers")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
            Button("Add server") { showAddSheet = true }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Helpers

    private func modeBadge(_ mode: MCPServerConfig.ExecutionMode) -> some View {
        HStack(spacing: 3) {
            Image(systemName: mode == .ai ? "infinity" : "timer")
                .font(.system(size: 7))
            Text(mode == .ai ? "AI" : "60s")
                .font(.system(size: 8, weight: .bold, design: .monospaced))
        }
        .foregroundStyle(mode == .ai
                         ? Color(red: 0.3, green: 1.0, blue: 0.5)
                         : Color(red: 0.9, green: 0.7, blue: 0.3))
        .padding(.horizontal, 5)
        .padding(.vertical, 2)
        .background((mode == .ai
                     ? Color(red: 0.3, green: 1.0, blue: 0.5)
                     : Color(red: 0.9, green: 0.7, blue: 0.3)).opacity(0.12),
                    in: RoundedRectangle(cornerRadius: 4))
    }

    private func transportIcon(_ t: MCPServerConfig.Transport) -> String {
        t == .stdio ? "terminal" : "network"
    }

    private func statusColor(for id: UUID) -> Color {
        switch mcp.connectionStatus[id] ?? .disconnected {
        case .connected:   return Color(red: 0.3, green: 0.9, blue: 0.5)
        case .connecting:  return Color(red: 0.9, green: 0.7, blue: 0.3)
        case .error:       return Color(red: 0.9, green: 0.4, blue: 0.4)
        case .disconnected: return Color(red: 0.5, green: 0.5, blue: 0.6)
        }
    }

    private func statusLabel(_ s: MCPEngine.ConnectionStatus) -> String {
        switch s {
        case .connected:      return "● connected"
        case .connecting:     return "○ connecting…"
        case .disconnected:   return "○ disconnected"
        case .error(let e):   return "✗ \(e.prefix(30))"
        }
    }

    private func isConnecting(_ id: UUID) -> Bool {
        if case .connecting = mcp.connectionStatus[id] ?? .disconnected { return true }
        return false
    }
}

// MARK: - ServerRow

struct ServerRow: View {
    let server: MCPServerConfig
    let status: MCPEngine.ConnectionStatus
    var isSelected: Bool = false

    private var statusDot: Color {
        switch status {
        case .connected:    return Color(red: 0.3, green: 0.9, blue: 0.5)
        case .connecting:   return Color(red: 0.9, green: 0.7, blue: 0.3)
        case .error:        return Color(red: 0.9, green: 0.4, blue: 0.4)
        case .disconnected: return Color(red: 0.4, green: 0.4, blue: 0.5)
        }
    }

    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(statusDot).frame(width: 7, height: 7)

            VStack(alignment: .leading, spacing: 2) {
                Text(server.name)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(isSelected ? .white : Color(red: 0.88, green: 0.88, blue: 0.95))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Text(server.transport.rawValue)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(isSelected ? Color.white.opacity(0.6) : Color(white: 0.5))
                    .lineLimit(1)
            }
            .layoutPriority(1)

            Spacer(minLength: 4)

            // Mode badge
            Text(server.mode == .ai ? "AI" : "60s")
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundStyle(server.mode == .ai
                                 ? Color(red: 0.3, green: 0.9, blue: 0.5)
                                 : Color(red: 0.9, green: 0.7, blue: 0.3))
                .padding(.horizontal, 5)
                .padding(.vertical, 2)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 3))
                .fixedSize()

            // Enabled indicator
            Circle()
                .fill(server.isEnabled ? Color(red: 0.3, green: 0.7, blue: 1.0) : Color.secondary.opacity(0.5))
                .frame(width: 5, height: 5)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(
            RoundedRectangle(cornerRadius: 5)
                .fill(isSelected
                      ? Color(red: 0.25, green: 0.35, blue: 0.55).opacity(0.5)
                      : Color.clear)
        )
        .padding(.horizontal, 4)
    }
}

// MARK: - ToolRow

struct ToolRow: View {
    let tool: MCPTool
    let serverMode: MCPServerConfig.ExecutionMode
    let onCall: ([String: Any]) -> Void
    @State private var showCallSheet = false

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "function")
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .frame(width: 12)
            VStack(alignment: .leading, spacing: 1) {
                Text(tool.name)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                if !tool.description.isEmpty {
                    Text(tool.description)
                        .font(.system(size: 9))
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
            .layoutPriority(1)
            Spacer(minLength: 0)

            Button("Run") { onCall([:]) }
                .buttonStyle(.bordered)
                .controlSize(.mini)
                .font(.system(size: 9))
        }
        .padding(.vertical, 3)
        .padding(.horizontal, 6)
        .background(Color.white.opacity(0.03), in: RoundedRectangle(cornerRadius: 4))
    }
}

// MARK: - MCPServerEditSheet

struct MCPServerEditSheet: View {
    @State var config: MCPServerConfig
    let onSave: (MCPServerConfig) -> Void
    @Environment(\.dismiss) var dismiss

    @State private var newEnvKey = ""
    @State private var newEnvVal = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(config.id == UUID() ? "New MCP Server" : "Edit: \(config.name)")
                .font(.system(size: 14, weight: .bold))

            Divider()

            // Name
            FormRow("Name") {
                TextField("e.g. Filesystem, GitHub, Brave Search", text: $config.name)
                    .textFieldStyle(.roundedBorder)
            }

            // Transport
            FormRow("Transport") {
                Picker("", selection: $config.transport) {
                    ForEach(MCPServerConfig.Transport.allCases, id: \.self) { t in
                        Text(t.rawValue).tag(t)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 160)
            }

            // Command / URL
            if config.transport == .stdio {
                FormRow("Command") {
                    TextField("npx -y @modelcontextprotocol/server-filesystem /", text: $config.command)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(size: 11, design: .monospaced))
                }
            } else {
                FormRow("URL") {
                    TextField("http://localhost:3000", text: $config.url)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(size: 11, design: .monospaced))
                }
            }

            // Execution mode
            FormRow("Mode") {
                VStack(alignment: .leading, spacing: 6) {
                    Picker("", selection: $config.mode) {
                        ForEach(MCPServerConfig.ExecutionMode.allCases, id: \.self) { m in
                            Text(m.rawValue).tag(m)
                        }
                    }
                    .pickerStyle(.segmented)

                    Group {
                        if config.mode == .ai {
                            Label("No timeout. Kill switch available. Suitable for AI agent use.",
                                  systemImage: "infinity")
                                .foregroundStyle(Color(red: 0.3, green: 0.9, blue: 0.5))
                        } else {
                            Label("60-second timeout per tool call. Safe for interactive use.",
                                  systemImage: "timer")
                                .foregroundStyle(Color(red: 0.9, green: 0.7, blue: 0.3))
                        }
                    }
                    .font(.system(size: 10))
                }
            }

            // Enabled
            FormRow("Enabled") {
                Toggle("", isOn: $config.isEnabled)
                    .toggleStyle(.switch)
                    .scaleEffect(0.8)
            }

            // Environment variables
            if !config.envVars.isEmpty || !newEnvKey.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Environment Variables")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.secondary)

                    ForEach(Array(config.envVars.keys.sorted()), id: \.self) { key in
                        HStack {
                            Text(key)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(.secondary)
                                .frame(width: 160, alignment: .leading)
                            SecureField("value", text: Binding(
                                get: { config.envVars[key] ?? "" },
                                set: { config.envVars[key] = $0 }
                            ))
                            .textFieldStyle(.roundedBorder)
                            .font(.system(size: 10, design: .monospaced))
                            Button { config.envVars.removeValue(forKey: key) } label: {
                                Image(systemName: "minus.circle")
                                    .foregroundStyle(.red)
                            }
                            .contentShape(Rectangle())
                            .buttonStyle(.plain)
                        }
                    }
                }
            }

            // Add env var
            HStack(spacing: 6) {
                TextField("KEY", text: $newEnvKey)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 10, design: .monospaced))
                    .frame(width: 130)
                TextField("value", text: $newEnvVal)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 10, design: .monospaced))
                Button("Add Env Var") {
                    guard !newEnvKey.isEmpty else { return }
                    config.envVars[newEnvKey] = newEnvVal
                    newEnvKey = ""; newEnvVal = ""
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(newEnvKey.isEmpty)
            }

            Spacer()

            Divider()

            HStack {
                Button("Cancel") { dismiss() }
                    .buttonStyle(.bordered)
                Spacer()
                Button("Save") {
                    onSave(config)
                    dismiss()
                }
                .buttonStyle(.borderedProminent)
                .disabled(config.name.isEmpty)
            }
        }
        .padding(20)
        .background(Color(red: 0.10, green: 0.10, blue: 0.14))
    }
}

// MARK: - FormRow helper

struct FormRow<Content: View>: View {
    let label: String
    let content: Content

    init(_ label: String, @ViewBuilder content: () -> Content) {
        self.label = label
        self.content = content()
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(label)
                .font(.system(size: 12))
                .foregroundStyle(Color(red: 0.72, green: 0.72, blue: 0.85))
                .frame(width: 90, alignment: .trailing)
            content
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

// MARK: - MCPCatalogPickerSheet
// カタログから既知の MCP サーバーをワンクリックで追加する

struct MCPCatalogPickerSheet: View {
    let onSelect: (MCPCatalogEntry) -> Void
    @Environment(\.dismiss) var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Image(systemName: "square.grid.2x2.fill")
                    .foregroundStyle(Color(red: 0.4, green: 0.75, blue: 1.0))
                Text(AppLanguage.shared.t("Add from MCP Catalog", "MCP カタログから追加"))
                    .font(.system(size: 14, weight: .bold))
                Spacer()
                Button(AppLanguage.shared.t("Close", "閉じる")) { dismiss() }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
            .padding(16)

            Divider().opacity(0.3)

            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(MCPCatalog.all) { entry in
                        HStack(spacing: 12) {
                            Image(systemName: entry.icon)
                                .font(.system(size: 18))
                                .foregroundStyle(Color(red: 0.4, green: 0.75, blue: 1.0))
                                .frame(width: 32)

                            VStack(alignment: .leading, spacing: 3) {
                                Text(entry.displayName)
                                    .font(.system(size: 13, weight: .semibold))
                                Text(entry.defaultCommand)
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                if !entry.requiredEnv.isEmpty {
                                    HStack(spacing: 4) {
                                        Image(systemName: "key.fill")
                                            .font(.system(size: 8))
                                            .foregroundStyle(Color(red: 1.0, green: 0.75, blue: 0.2))
                                        Text(entry.requiredEnv.map(\.key).joined(separator: ", "))
                                            .font(.system(size: 9, design: .monospaced))
                                            .foregroundStyle(Color(red: 1.0, green: 0.75, blue: 0.2))
                                    }
                                }
                            }

                            Spacer()

                            Button(AppLanguage.shared.t("Add", "追加")) { onSelect(entry) }
                                .buttonStyle(.borderedProminent)
                                .controlSize(.small)
                        }
                        .padding(12)
                        .background(Color(red: 0.12, green: 0.12, blue: 0.16),
                                    in: RoundedRectangle(cornerRadius: 8))
                    }
                }
                .padding(12)
            }
        }
        .background(Color(red: 0.10, green: 0.10, blue: 0.14))
    }
}

// MARK: - MCPApiKeySheet
// API キーを Keychain に安全に保存する入力フォーム

struct MCPApiKeySheet: View {
    let server: MCPServerConfig
    let onSave: () -> Void
    @Environment(\.dismiss) var dismiss

    // カタログエントリ
    private var entry: MCPCatalogEntry? { MCPCatalog.find(byName: server.name) }
    // 入力値を一時保持（SecureField は @State で管理）
    @State private var values: [String: String] = [:]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack(spacing: 8) {
                Image(systemName: "key.fill")
                    .foregroundStyle(Color(red: 1.0, green: 0.75, blue: 0.2))
                VStack(alignment: .leading, spacing: 2) {
                    Text(AppLanguage.shared.t("\(server.name) — Set API Key", "\(server.name) — API キーを設定"))
                        .font(.system(size: 13, weight: .bold))
                    Text(AppLanguage.shared.t("Input values are securely saved in macOS Keychain", "入力値は macOS Keychain に暗号化保存されます"))
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(16)

            Divider().opacity(0.3)

            if let e = entry {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        ForEach(e.requiredEnv, id: \.key) { spec in
                            VStack(alignment: .leading, spacing: 5) {
                                HStack(spacing: 6) {
                                    Text(spec.key)
                                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                                    Text(AppLanguage.shared.t("Required", "必須"))
                                        .font(.system(size: 9, weight: .bold))
                                        .foregroundStyle(.white)
                                        .padding(.horizontal, 5).padding(.vertical, 2)
                                        .background(Color(red: 0.9, green: 0.3, blue: 0.3),
                                                    in: RoundedRectangle(cornerRadius: 3))
                                    Spacer()
                                    if !spec.helpURL.isEmpty {
                                        Link(AppLanguage.shared.t("Get Key →", "取得する →"), destination: URL(string: spec.helpURL)!)
                                            .font(.system(size: 9))
                                    }
                                }
                                SecureField(spec.hint, text: Binding(
                                    get: {
                                        values[spec.key]
                                        ?? MCPKeychainStore.load(key: "\(server.id).\(spec.key)")
                                        ?? ""
                                    },
                                    set: { values[spec.key] = $0 }
                                ))
                                .textFieldStyle(.roundedBorder)
                                .font(.system(size: 11, design: .monospaced))
                            }
                        }
                        ForEach(e.optionalEnv, id: \.key) { spec in
                            VStack(alignment: .leading, spacing: 5) {
                                HStack(spacing: 6) {
                                    Text(spec.key)
                                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                                    Text(AppLanguage.shared.t("Optional", "任意"))
                                        .font(.system(size: 9))
                                        .foregroundStyle(.secondary)
                                        .padding(.horizontal, 4).padding(.vertical, 2)
                                        .background(.quaternary,
                                                    in: RoundedRectangle(cornerRadius: 3))
                                }
                                SecureField(spec.hint, text: Binding(
                                    get: {
                                        values[spec.key]
                                        ?? MCPKeychainStore.load(key: "\(server.id).\(spec.key)")
                                        ?? ""
                                    },
                                    set: { values[spec.key] = $0 }
                                ))
                                .textFieldStyle(.roundedBorder)
                                .font(.system(size: 11, design: .monospaced))
                            }
                        }
                    }
                    .padding(16)
                }
            } else {
                Text(AppLanguage.shared.t("This server is not in the catalog. Configure manually via Edit.", "このサーバーはカタログに未登録です。Edit から手動で設定してください。"))
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .padding(16)
            }

            Divider().opacity(0.3)

            HStack {
                Button(AppLanguage.shared.t("Cancel", "キャンセル")) { dismiss() }
                    .buttonStyle(.bordered)
                Spacer()
                Button(AppLanguage.shared.t("Save to Keychain & Reconnect", "Keychain に保存して再接続")) {
                    // 入力値を Keychain に書き込む
                    for (key, val) in values where !val.isEmpty {
                        MCPKeychainStore.save(key: "\(server.id).\(key)", value: val)
                    }
                    onSave()
                    dismiss()
                }
                .buttonStyle(.borderedProminent)
                .disabled(values.values.allSatisfy { $0.isEmpty })
            }
            .padding(16)
        }
        .background(Color(red: 0.10, green: 0.10, blue: 0.14))
    }
}
