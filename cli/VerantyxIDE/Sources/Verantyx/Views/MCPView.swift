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
    @State private var copiedVeraConfig   = false

    var body: some View {
        VStack(spacing: 0) {
            killSwitchBanner   // top priority — always visible when something is running

            // ── Server list (top section) ──────────────────────────
            serverListHeader
            Divider().opacity(0.3)
            veraExternalExportBanner

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

    // ── Vera memory → other IDEs ────────────────────────────────────────
    // The IDE runs Vera-a natively (loaded model + bundled store), so this
    // MCP row needs nothing configured here anymore — it is auto-managed by
    // MCPEngine.loadServers(). What remains useful is the outward direction:
    // one paste connects Claude Code / Claude Desktop / Cursor to the same
    // binary and the same store.
    @ViewBuilder
    private var veraExternalExportBanner: some View {
        if let json = VeraMemoryPaths.externalMCPConfigJSON() {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Image(systemName: "square.and.arrow.up")
                        .font(.system(size: 10))
                        .foregroundStyle(Color(red: 0.5, green: 0.85, blue: 0.6))
                    Text(app.t("Use Vera memory in other IDEs", "Veraの記憶を他のIDEで使う"))
                        .font(.system(size: 10, weight: .semibold))
                    Spacer()
                    Button {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(json, forType: .string)
                        copiedVeraConfig = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            copiedVeraConfig = false
                        }
                    } label: {
                        Label(copiedVeraConfig
                                ? app.t("Copied", "コピーしました")
                                : app.t("Copy MCP config", "MCP設定をコピー"),
                              systemImage: copiedVeraConfig ? "checkmark" : "doc.on.doc")
                            .font(.system(size: 10))
                    }
                    .buttonStyle(.borderless)
                }
                Text(app.t(
                    "Vera-a runs natively inside this IDE — nothing to configure here. Paste the copied snippet into Claude Code (.mcp.json), Claude Desktop (claude_desktop_config.json) or Cursor (.cursor/mcp.json) to point them at the same vera-memory binary and the same store.",
                    "このIDE内のVera-aはネイティブ動作なので、ここでの設定は不要です。コピーした設定を Claude Code (.mcp.json)、Claude Desktop (claude_desktop_config.json)、Cursor (.cursor/mcp.json) に貼ると、同じ vera-memory バイナリ・同じ記憶ストアに繋がります。"
                ))
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(Color(red: 0.10, green: 0.13, blue: 0.11))
            Divider().opacity(0.3)
        }
    }

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
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)

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
        case .error(let e):   return "✗ \(e)"
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

// MARK: - ExternalOpsView
//
// The full-window "run Vera outside this IDE" hub — what the Gatekeeper
// menu's MCP pick opens. Not the server-management list (that stays
// available below as an advanced disclosure): this screen is for the
// OUTWARD direction, complete in one place with no trip to Settings:
//
//   1. connection — the two-server config other tools paste
//   2. memory stores — create a new memory, mark one as 普段の参照
//      (the active store both MCP and the IDE read), switch any time
//   3. the memory-organ JGEN — select/convert/quantize/load, embedded
//
struct ExternalOpsView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var mcp = MCPEngine.shared
    @State private var profiles: [String] = VeraMemoryPaths.listProfiles()
    @State private var active: String = VeraMemoryPaths.activeProfile
    @State private var newStoreName = ""
    @State private var copiedConfig = false
    @State private var showAdvanced = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {

                // ── 1. Connection ────────────────────────────────────
                sectionHeader(app.t("Connection for other tools", "他ツールからの接続"))
                VStack(alignment: .leading, spacing: 6) {
                    Text(app.t(
                        "Paste this into OpenCode / Claude Code (.mcp.json), Claude Desktop or Cursor. It carries both servers: vera-memory (truth store, stdio) and vera-jgen-memory (eternal recall over http://127.0.0.1:8766/mcp — the IDE must be running).",
                        "OpenCode / Claude Code (.mcp.json)、Claude Desktop、Cursor に貼り付けてください。2サーバー入りです: vera-memory（正のストア・stdio）と vera-jgen-memory（永遠記憶・http://127.0.0.1:8766/mcp — IDE起動中のみ）。"
                    ))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    Button {
                        if let json = VeraMemoryPaths.externalMCPConfigJSON() {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(json, forType: .string)
                            copiedConfig = true
                            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copiedConfig = false }
                        }
                    } label: {
                        Label(copiedConfig ? app.t("Copied", "コピーしました")
                                           : app.t("Copy MCP config", "MCP設定をコピー"),
                              systemImage: copiedConfig ? "checkmark" : "doc.on.doc")
                            .font(.system(size: 11))
                    }
                }

                Divider().opacity(0.3)

                // ── 2. Memory stores ─────────────────────────────────
                sectionHeader(app.t("Memory stores", "記憶ストア"))
                Text(app.t(
                    "The checked store is 普段の参照 — what MCP clients and this IDE both read and write. Switching re-points vera-memory and the eternal store together; each store carries its own JGEN pin.",
                    "チェックの付いたストアが「普段の参照」— MCPクライアントとこのIDEの両方が読み書きする先です。切り替えると vera-memory と永遠記憶が一緒に切り替わります。ストアごとに独自のJGENピンを持ちます。"
                ))
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

                VStack(spacing: 4) {
                    ForEach(profiles, id: \.self) { name in
                        HStack(spacing: 8) {
                            Button {
                                activate(name)
                            } label: {
                                Image(systemName: active == name
                                      ? "checkmark.circle.fill" : "circle")
                                    .foregroundStyle(active == name ? Color.green : .secondary)
                            }
                            .buttonStyle(.plain)
                            .help(app.t("Use as the everyday store", "普段の参照にする"))
                            Text(name == "default" ? app.t("default (original)", "default（従来の記憶）") : name)
                                .font(.system(size: 11, weight: active == name ? .bold : .regular))
                            if active == name {
                                Text(app.t("in use", "使用中"))
                                    .font(.system(size: 9))
                                    .foregroundStyle(Color.green)
                            }
                            Spacer()
                        }
                        .padding(.horizontal, 10).padding(.vertical, 6)
                        .background(RoundedRectangle(cornerRadius: 6)
                            .fill(Color.white.opacity(active == name ? 0.06 : 0.02)))
                    }
                }

                HStack(spacing: 8) {
                    TextField(app.t("new memory name…", "新しい記憶の名前…"), text: $newStoreName)
                        .textFieldStyle(.roundedBorder)
                        .frame(maxWidth: 240)
                        .font(.system(size: 11))
                    Button(app.t("Create", "新規メモリ作成")) {
                        guard let created = VeraMemoryPaths.createProfile(newStoreName) else { return }
                        newStoreName = ""
                        profiles = VeraMemoryPaths.listProfiles()
                        // Created, not yet activated — the 普段の参照 check
                        // is the explicit second step, as specified.
                        _ = created
                    }
                    .disabled(newStoreName.trimmingCharacters(in: .whitespaces).isEmpty)
                }

                Divider().opacity(0.3)

                // ── 3. The memory-organ JGEN ─────────────────────────
                sectionHeader(app.t("Memory-organ JGEN (select / convert)", "記憶器官のJGEN（選択・変換）"))
                Text(app.t(
                    "Convert and load here — no Settings trip. The first save through a loaded JGEN pins the ACTIVE store's vector space to it; it then autoloads at launch.",
                    "変換もロードもここで完結します（設定画面は不要）。ロード中のJGENで最初の保存が走ると、アクティブなストアの意味空間がそのJGENにピン留めされ、以後は起動時に自動ロードされます。"
                ))
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                JGenSettingsSection()
                    .environmentObject(app)

                Divider().opacity(0.3)

                // ── Advanced: raw server list ────────────────────────
                DisclosureGroup(isExpanded: $showAdvanced) {
                    MCPView()
                        .environmentObject(app)
                        .frame(minHeight: 420)
                } label: {
                    Text(app.t("MCP servers (advanced)", "MCPサーバー一覧（上級）"))
                        .font(.system(size: 11, weight: .semibold))
                }
            }
            .padding(16)
            .frame(maxWidth: 760, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .background(Color(red: 0.10, green: 0.10, blue: 0.13))
        .onAppear {
            profiles = VeraMemoryPaths.listProfiles()
            active = VeraMemoryPaths.activeProfile
        }
    }

    /// The 普段の参照 switch: persist the choice, live-switch the eternal
    /// store, and re-point + reconnect the vera-memory MCP server.
    private func activate(_ name: String) {
        guard name != active else { return }
        UserDefaults.standard.set(name, forKey: VeraMemoryPaths.profileDefaultsKey)
        active = name
        Task {
            await EternalMemoryStore.shared.switchToActiveProfile()
            if let binary = VeraMemoryPaths.resolveBundledBinary(),
               let idx = MCPEngine.shared.servers.firstIndex(where: { $0.name == "vera-memory" }) {
                var server = MCPEngine.shared.servers[idx]
                server.command = VeraMemoryPaths.bundledMCPCommand(binary: binary)
                MCPEngine.shared.updateServer(server)
                await MCPEngine.shared.connect(server: server)
            }
            await MainActor.run {
                app.addSystemMessage(app.t(
                    "🗂 Everyday memory store switched to '\(name)' (vera-memory + eternal store)",
                    "🗂 普段の参照を『\(name)』に切り替えました（vera-memory＋永遠記憶）"))
            }
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 12, weight: .bold))
            .foregroundStyle(Color(red: 0.55, green: 0.8, blue: 1.0))
    }
}
