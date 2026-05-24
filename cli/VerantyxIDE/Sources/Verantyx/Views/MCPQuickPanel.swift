import SwiftUI

// MARK: - MCPQuickPanel
//
// Spotlight-style floating overlay for instant MCP management.
// Triggered via ⌘⇧M from anywhere in the IDE.
//
// Features:
//   • Fuzzy search across servers AND tools in one unified list
//   • One-step server add via templates or custom command
//   • Inline tool invocation with argument editor
//   • Keyboard-navigable (↑↓ arrow, Enter, Esc)

struct MCPQuickPanel: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var mcp = MCPEngine.shared
    @Binding var isPresented: Bool

    @State private var query = ""
    @State private var selectedIndex = 0     // keyboard-driven selection
    @State private var hoveredIndex: Int? = nil  // mouse-hover highlight (no scroll)
    @State private var mode: PanelMode = .browse
    @State private var toolArgText = ""         // JSON args editor for quick invoke
    @State private var invokeResult: String?
    @State private var isInvoking = false
    @FocusState private var searchFocused: Bool

    enum PanelMode {
        case browse             // search servers & tools
        case addCustom          // add custom stdio server
        case addTemplate        // pick from template list
        case invoking(MCPTool, MCPServerConfig)  // tool argument editor
    }

    // MARK: - Unified result items

    enum ResultItem: Identifiable {
        case server(MCPServerConfig, MCPEngine.ConnectionStatus)
        case tool(MCPTool, MCPServerConfig)
        case template(MCPServerConfig)
        case action(ActionItem)

        var id: String {
            switch self {
            case .server(let s, _):  return "srv_\(s.id)"
            case .tool(let t, _):   return "tool_\(t.id)"
            case .template(let t):  return "tpl_\(t.id)"
            case .action(let a):    return "act_\(a.label)"
            }
        }

        var icon: String {
            switch self {
            case .server(let s, let st):
                switch st {
                case .connected:   return "circle.fill"
                case .connecting:  return "circle.dotted"
                case .error:       return "exclamationmark.circle.fill"
                case .disconnected: return "circle"
                }
            case .tool:     return "function"
            case .template: return "square.on.square"
            case .action:   return "plus.circle.fill"
            }
        }

        var iconColor: Color {
            switch self {
            case .server(_, let st):
                switch st {
                case .connected:    return Color(red: 0.3, green: 0.9, blue: 0.5)
                case .connecting:   return Color(red: 0.9, green: 0.7, blue: 0.3)
                case .error:        return Color(red: 0.9, green: 0.4, blue: 0.4)
                case .disconnected: return Color(red: 0.4, green: 0.4, blue: 0.55)
                }
            case .tool:     return Color(red: 0.5, green: 0.75, blue: 1.0)
            case .template: return Color(red: 0.7, green: 0.5, blue: 1.0)
            case .action:   return Color(red: 0.3, green: 0.9, blue: 0.5)
            }
        }

        var title: String {
            switch self {
            case .server(let s, _):  return s.name
            case .tool(let t, let s): return "\(s.name)  /  \(t.name)"
            case .template(let t):   return t.name
            case .action(let a):     return a.label
            }
        }

        var subtitle: String {
            switch self {
            case .server(let s, let st):
                let stText: String
                switch st {
                case .connected:   stText = "● connected"
                case .connecting:  stText = "○ connecting"
                case .disconnected: stText = "○ disconnected"
                case .error(let e): stText = "✗ \(e)"
                }
                return "\(s.transport.rawValue)  \(stText)"
            case .tool(let t, _):   return t.description.isEmpty ? "(no description)" : t.description
            case .template(let t):  return t.command
            case .action(let a):    return a.subtitle
            }
        }

        var badge: String? {
            switch self {
            case .tool:     return "TOOL"
            case .server:   return "SERVER"
            case .template: return "TEMPLATE"
            case .action:   return nil
            }
        }
    }

    struct ActionItem {
        let label: String
        let subtitle: String
        let action: () -> Void
    }

    // MARK: - Computed results

    private var results: [ResultItem] {
        var items: [ResultItem] = []
        let q = query.lowercased()

        if q.isEmpty {
            // ── Top actions ────────────────────────────────────────────
            items.append(.action(.init(
                label: "Add Custom MCP Server…",
                subtitle: "Configure a new stdio or HTTP server",
                action: { mode = .addCustom }
            )))
            items.append(.action(.init(
                label: "Add from Template…",
                subtitle: "Filesystem · GitHub · Brave Search · etc.",
                action: { mode = .addTemplate }
            )))
            if !mcp.servers.isEmpty {
                items.append(.action(.init(
                    label: "Connect All Servers",
                    subtitle: "Connect all enabled MCP servers at once",
                    action: {
                        Task { await mcp.connectAll() }
                        dismiss()
                    }
                )))
            }
            // ── All servers ───────────────────────────────────────────
            for s in mcp.servers {
                items.append(.server(s, mcp.connectionStatus[s.id] ?? .disconnected))
            }
            // ── Connected tools ────────────────────────────────────────
            for t in mcp.connectedTools {
                if let srv = mcp.servers.first(where: { $0.name == t.serverName }) {
                    items.append(.tool(t, srv))
                }
            }
        } else {
            // ── Fuzzy filter ─────────────────────────────────────────
            for s in mcp.servers where s.name.lowercased().contains(q) || s.command.lowercased().contains(q) {
                items.append(.server(s, mcp.connectionStatus[s.id] ?? .disconnected))
            }
            for t in mcp.connectedTools where t.name.lowercased().contains(q) || t.description.lowercased().contains(q) {
                if let srv = mcp.servers.first(where: { $0.name == t.serverName }) {
                    items.append(.tool(t, srv))
                }
            }
            // Template search
            for tmpl in MCPServerConfig.examples where tmpl.name.lowercased().contains(q) {
                items.append(.template(tmpl))
            }
            if items.isEmpty {
                items.append(.action(.init(
                    label: "Add \"\(query)\" as Custom Server…",
                    subtitle: "Create a new MCP server with this name",
                    action: { mode = .addCustom }
                )))
            }
        }
        return items
    }

    private func clampedIndex(_ i: Int) -> Int {
        max(0, min(i, results.count - 1))
    }

    // MARK: - Body

    var body: some View {
        ZStack {
            // ── Backdrop click-to-dismiss ──────────────────────────────
            Color.black.opacity(0.5)
                .ignoresSafeArea()
                .onTapGesture { dismiss() }

            // ── Panel ──────────────────────────────────────────────────
            VStack(spacing: 0) {
                switch mode {
                case .browse:
                    browsePanel
                case .addCustom:
                    AddCustomServerPanel(onSave: { config in
                        mcp.addServer(config)
                        Task { await mcp.connect(server: config) }
                        dismiss()
                    }, onCancel: { mode = .browse })
                case .addTemplate:
                    TemplatePickerPanel(onPick: { config in
                        mcp.addServer(config)
                        Task { await mcp.connect(server: config) }
                        dismiss()
                    }, onCancel: { mode = .browse })
                case .invoking(let tool, let server):
                    InvokeToolPanel(
                        tool: tool, server: server,
                        onInvoke: { args in
                            Task {
                                isInvoking = true
                                let res = await mcp.callTool(
                                    serverName: server.name,
                                    toolName: tool.name,
                                    arguments: args,
                                    mode: server.mode
                                )
                                app.addSystemMessage("[MCP \(tool.name)] \(res.prefix(500))")
                                isInvoking = false
                                dismiss()
                            }
                        },
                        onCancel: { mode = .browse }
                    )
                }
            }
            .frame(width: 600)
            .background(Color(red: 0.12, green: 0.12, blue: 0.16), in: RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.6), radius: 30, y: 10)
            .transition(.scale(scale: 0.96).combined(with: .opacity))
        }
        .animation(.easeOut(duration: 0.18), value: mode.id)
        .onAppear { searchFocused = true }
    }

    // MARK: - Browse panel (main mode)

    private var browsePanel: some View {
        VStack(spacing: 0) {
            // Search bar
            HStack(spacing: 10) {
                Image(systemName: "puzzlepiece.extension")
                    .font(.system(size: 14))
                    .foregroundStyle(Color(red: 0.4, green: 0.7, blue: 1.0))
                TextField("Search servers, tools, or type a name to add…", text: $query)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14))
                    .focused($searchFocused)
                    .onSubmit { activateSelected() }

                if !query.isEmpty {
                    Button { query = "" } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
                }

                // Close
                Button { dismiss() } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(.secondary)
                        .padding(4)
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 4))
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .keyboardShortcut(.escape, modifiers: [])
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)

            Divider().opacity(0.2)

            // Results list
            if results.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 22))
                        .foregroundStyle(.tertiary)
                    Text("No results for \"\(query)\"")
                        .foregroundStyle(.secondary)
                }
                .frame(height: 100)
                .frame(maxWidth: .infinity)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(Array(results.enumerated()), id: \.element.id) { i, item in
                                ResultRow(
                                    item: item,
                                    isSelected: i == selectedIndex,
                                    isHovered: hoveredIndex == i
                                )
                                .id(i)
                                .onTapGesture { selectedIndex = i; activateSelected() }
                                // onHover updates visual highlight only — does NOT touch selectedIndex
                                // so the ScrollViewReader.onChange never fires on mouse movement.
                                .onHover { entered in
                                    hoveredIndex = entered ? i : nil
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .frame(maxHeight: 380)
                    .onChange(of: selectedIndex) { _, idx in
                        // Only keyboard navigation triggers auto-scroll
                        withAnimation { proxy.scrollTo(idx, anchor: .center) }
                    }
                }
            }

            // Footer hints
            HStack(spacing: 16) {
                hintChip("↑↓", "navigate")
                hintChip("↩", "select")
                hintChip("⌘⇧M", "close")
                Spacer()

                // Active call indicator
                if let call = mcp.activeCall, case .running = call.status {
                    HStack(spacing: 5) {
                        Circle().fill(.red).frame(width: 6, height: 6)
                        Text("\(call.toolName) running…")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color(red: 1.0, green: 0.4, blue: 0.4))
                        Button("KILL") { mcp.killActiveCall() }
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .foregroundStyle(.red)
                            .contentShape(Rectangle())
                            .buttonStyle(.plain)
                    }
                }

                Text("\(mcp.servers.count) server\(mcp.servers.count == 1 ? "" : "s")  ·  \(mcp.connectedTools.count) tool\(mcp.connectedTools.count == 1 ? "" : "s")")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(Color(red: 0.1, green: 0.1, blue: 0.13))
            .overlay(Rectangle().fill(Color.white.opacity(0.07)).frame(height: 1), alignment: .top)
        }
        .background(Color.clear)
        .onKeyPress(.upArrow) { selectedIndex = clampedIndex(selectedIndex - 1); return .handled }
        .onKeyPress(.downArrow) { selectedIndex = clampedIndex(selectedIndex + 1); return .handled }
        .onKeyPress(.return) { activateSelected(); return .handled }
    }

    // MARK: - Activate selected item

    private func activateSelected() {
        guard selectedIndex < results.count else { return }
        let item = results[selectedIndex]
        switch item {
        case .action(let a):
            a.action()
        case .server(let s, _):
            // Connect / show server
            Task { await mcp.connect(server: s) }
            dismiss()
        case .template(let t):
            mcp.addServer(t)
            Task { await mcp.connect(server: t) }
            dismiss()
        case .tool(let t, let s):
            mode = .invoking(t, s)
        }
    }

    private func dismiss() {
        withAnimation(.easeOut(duration: 0.15)) { isPresented = false }
    }

    // MARK: - Helpers

    private func hintChip(_ key: String, _ label: String) -> some View {
        HStack(spacing: 4) {
            Text(key)
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .padding(.horizontal, 4).padding(.vertical, 2)
                .background(Color.white.opacity(0.1), in: RoundedRectangle(cornerRadius: 3))
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(.tertiary)
        }
    }
}

// MARK: - PanelMode Equatable helper

extension MCPQuickPanel.PanelMode {
    var id: String {
        switch self {
        case .browse:     return "browse"
        case .addCustom:  return "addCustom"
        case .addTemplate: return "addTemplate"
        case .invoking(let t, _): return "invoke_\(t.id)"
        }
    }
}

// MARK: - ResultRow

private struct ResultRow: View {
    let item: MCPQuickPanel.ResultItem
    let isSelected: Bool    // keyboard selection (↑↓ Enter)
    var isHovered: Bool = false  // mouse hover (visual only — no scroll side-effect)

    private var bgColor: Color {
        if isSelected {
            return Color(red: 0.25, green: 0.35, blue: 0.55).opacity(0.45)
        } else if isHovered {
            return Color(red: 0.22, green: 0.28, blue: 0.38).opacity(0.30)
        }
        return Color.clear
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: item.icon)
                .font(.system(size: 12))
                .foregroundStyle(item.iconColor)
                .frame(width: 18)

            VStack(alignment: .leading, spacing: 2) {
                Text(item.title)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(isSelected ? .white : Color(red: 0.85, green: 0.85, blue: 0.92))
                Text(item.subtitle)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(isSelected ? Color(red: 0.7, green: 0.7, blue: 0.8) : Color.secondary.opacity(0.6))
                    .lineLimit(1)
            }

            Spacer()

            if let badge = item.badge {
                Text(badge)
                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                    .foregroundStyle(item.iconColor.opacity(0.9))
                    .padding(.horizontal, 5).padding(.vertical, 2)
                    .background(item.iconColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
            }

            if isSelected {
                Image(systemName: "return")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .background(bgColor, in: RoundedRectangle(cornerRadius: 6))
        .padding(.horizontal, 4)
        .contentShape(RoundedRectangle(cornerRadius: 6))
        .animation(.easeOut(duration: 0.08), value: isSelected)
        .animation(.easeOut(duration: 0.06), value: isHovered)
    }
}

// MARK: - AddCustomServerPanel

private struct AddCustomServerPanel: View {
    let onSave: (MCPServerConfig) -> Void
    let onCancel: () -> Void

    @State private var name = ""
    @State private var transport: MCPServerConfig.Transport = .stdio
    @State private var command = ""
    @State private var url = ""
    @State private var mode: MCPServerConfig.ExecutionMode = .ai
    @State private var envKey = ""
    @State private var envVal = ""
    @State private var envVars: [String: String] = [:]
    @FocusState private var nameFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Button { onCancel() } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 11, weight: .medium))
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                Text("Add Custom MCP Server")
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)

            Divider().opacity(0.2)

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    // Name
                    QPanelFormRow("Name") {
                        TextField("e.g. Filesystem, GitHub…", text: $name)
                            .textFieldStyle(.roundedBorder)
                            .focused($nameFocused)
                    }

                    // Transport
                    QPanelFormRow("Transport") {
                        Picker("", selection: $transport) {
                            ForEach(MCPServerConfig.Transport.allCases, id: \.self) { t in
                                Text(t.rawValue).tag(t)
                            }
                        }
                        .pickerStyle(.segmented)
                        .frame(width: 160)
                    }

                    // Command / URL
                    if transport == .stdio {
                        QPanelFormRow("Command") {
                            TextField("npx -y @modelcontextprotocol/server-filesystem /",
                                      text: $command)
                                .textFieldStyle(.roundedBorder)
                                .font(.system(size: 11, design: .monospaced))
                        }
                    } else {
                        QPanelFormRow("URL") {
                            TextField("http://localhost:3000", text: $url)
                                .textFieldStyle(.roundedBorder)
                                .font(.system(size: 11, design: .monospaced))
                        }
                    }

                    // Mode
                    QPanelFormRow("Mode") {
                        Picker("", selection: $mode) {
                            ForEach(MCPServerConfig.ExecutionMode.allCases, id: \.self) { m in
                                Text(m.rawValue).tag(m)
                            }
                        }
                        .pickerStyle(.segmented)
                        .frame(width: 200)
                    }

                    // Env vars
                    if !envVars.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Environment Variables")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(.secondary)
                            ForEach(envVars.keys.sorted(), id: \.self) { k in
                                HStack {
                                    Text(k)
                                        .font(.system(size: 10, design: .monospaced))
                                        .foregroundStyle(.secondary)
                                        .frame(width: 130, alignment: .leading)
                                    SecureField("value", text: Binding(
                                        get: { envVars[k] ?? "" },
                                        set: { envVars[k] = $0 }
                                    ))
                                    .textFieldStyle(.roundedBorder)
                                    .font(.system(size: 10, design: .monospaced))
                                    Button { envVars.removeValue(forKey: k) } label: {
                                        Image(systemName: "minus.circle").foregroundStyle(.red)
                                    }
                                    .contentShape(Rectangle())
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }

                    // Add env var row
                    HStack(spacing: 6) {
                        TextField("KEY", text: $envKey)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(size: 10, design: .monospaced))
                            .frame(width: 120)
                        TextField("value", text: $envVal)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(size: 10, design: .monospaced))
                        Button("+ Env") {
                            guard !envKey.isEmpty else { return }
                            envVars[envKey] = envVal
                            envKey = ""; envVal = ""
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(envKey.isEmpty)
                    }
                }
                .padding(16)
            }
            .frame(maxHeight: 340)

            Divider().opacity(0.2)

            // Actions
            HStack {
                Button("Cancel") { onCancel() }
                    .buttonStyle(.bordered)
                Spacer()
                Button("Add & Connect") {
                    var cfg = MCPServerConfig(
                        name: name, transport: transport,
                        command: command, url: url,
                        envVars: envVars, mode: mode
                    )
                    onSave(cfg)
                }
                .buttonStyle(.borderedProminent)
                .disabled(name.isEmpty || (transport == .stdio && command.isEmpty) || (transport == .http && url.isEmpty))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color(red: 0.1, green: 0.1, blue: 0.13))
        }
        .onAppear { nameFocused = true }
    }
}

// MARK: - TemplatePickerPanel

private struct TemplatePickerPanel: View {
    let onPick: (MCPServerConfig) -> Void
    let onCancel: () -> Void

    // Extended template list
    private static let templates: [MCPServerConfig] = [
        MCPServerConfig(name: "Filesystem", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-filesystem /", mode: .ai),
        MCPServerConfig(name: "GitHub", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-github",
                        envVars: ["GITHUB_PERSONAL_ACCESS_TOKEN": ""], mode: .ai),
        MCPServerConfig(name: "Brave Search", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-brave-search",
                        envVars: ["BRAVE_API_KEY": ""], mode: .human),
        MCPServerConfig(name: "Slack", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-slack",
                        envVars: ["SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""], mode: .ai),
        MCPServerConfig(name: "PostgreSQL", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-postgres",
                        envVars: ["POSTGRES_URL": ""], mode: .human),
        MCPServerConfig(name: "Puppeteer (Browser)", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-puppeteer", mode: .ai),
        MCPServerConfig(name: "Memory (KV Store)", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-memory", mode: .ai),
        MCPServerConfig(name: "Fetch (Web Scraper)", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-fetch", mode: .human),
        MCPServerConfig(name: "Local HTTP", transport: .http,
                        url: "http://localhost:3000", mode: .human),
        MCPServerConfig(name: "Verantyx Cortex (Local)", transport: .http,
                        url: "http://localhost:7331", mode: .ai),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Button { onCancel() } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 11, weight: .medium))
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                Text("Add from Template")
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
                Text("\(Self.templates.count) templates")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)

            Divider().opacity(0.2)

            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(Self.templates) { tmpl in
                        Button {
                            onPick(tmpl)
                        } label: {
                            HStack(spacing: 12) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 7)
                                        .fill(Color(red: 0.2, green: 0.3, blue: 0.5).opacity(0.4))
                                        .frame(width: 32, height: 32)
                                    Image(systemName: tmpl.transport == .stdio ? "terminal" : "network")
                                        .font(.system(size: 14))
                                        .foregroundStyle(Color(red: 0.4, green: 0.75, blue: 1.0))
                                }

                                VStack(alignment: .leading, spacing: 2) {
                                    Text(tmpl.name)
                                        .font(.system(size: 12, weight: .semibold))
                                        .foregroundStyle(Color(red: 0.9, green: 0.9, blue: 0.95))
                                    Text(tmpl.transport == .stdio
                                         ? tmpl.command.components(separatedBy: " ").dropFirst(3).joined(separator: " ")
                                         : tmpl.url)
                                        .font(.system(size: 10, design: .monospaced))
                                        .foregroundStyle(.tertiary)
                                        .lineLimit(1)
                                    if !tmpl.envVars.isEmpty {
                                        HStack(spacing: 4) {
                                            Image(systemName: "key.fill")
                                                .font(.system(size: 8))
                                            Text(tmpl.envVars.keys.joined(separator: ", "))
                                                .font(.system(size: 9))
                                        }
                                        .foregroundStyle(Color(red: 0.9, green: 0.75, blue: 0.3))
                                    }
                                }
                                Spacer()

                                // Mode badge
                                Text(tmpl.mode == .ai ? "AI" : "60s")
                                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                                    .foregroundStyle(tmpl.mode == .ai
                                                     ? Color(red: 0.3, green: 0.9, blue: 0.5)
                                                     : Color(red: 0.9, green: 0.7, blue: 0.3))
                                    .padding(.horizontal, 5).padding(.vertical, 2)
                                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 3))

                                Image(systemName: "plus.circle")
                                    .font(.system(size: 14))
                                    .foregroundStyle(Color(red: 0.4, green: 0.8, blue: 0.5))
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                        }
                        .contentShape(Rectangle())
                        .buttonStyle(.plain)
                        .background(Color.white.opacity(0.0))
                        .hoverEffect { isHovered in
                            isHovered
                                ? Color(red: 0.22, green: 0.32, blue: 0.50).opacity(0.3)
                                : Color.clear
                        }
                    }
                }
                .padding(.vertical, 4)
            }
            .frame(maxHeight: 360)
        }
    }
}

// MARK: - InvokeToolPanel

private struct InvokeToolPanel: View {
    let tool: MCPTool
    let server: MCPServerConfig
    let onInvoke: ([String: Any]) -> Void
    let onCancel: () -> Void

    @State private var argsText = "{}"
    @State private var parseError: String?
    @FocusState private var argsFocused: Bool

    private var parsedArgs: [String: Any]? {
        guard let data = argsText.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return obj
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack(spacing: 10) {
                Button { onCancel() } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 11, weight: .medium))
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 2) {
                    Text(tool.name)
                        .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    Text(server.name)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(server.mode == .ai ? "AI mode · no timeout" : "Human mode · 60s")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(server.mode == .ai
                                     ? Color(red: 0.3, green: 0.9, blue: 0.5)
                                     : Color(red: 0.9, green: 0.7, blue: 0.3))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)

            Divider().opacity(0.2)

            // Tool description
            if !tool.description.isEmpty {
                Text(tool.description)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
            }

            // Args editor
            VStack(alignment: .leading, spacing: 6) {
                Text("ARGUMENTS (JSON)")
                    .font(.system(size: 9, weight: .semibold, design: .monospaced))
                    .foregroundStyle(.tertiary)
                    .padding(.horizontal, 16)
                    .padding(.top, 10)

                TextEditor(text: $argsText)
                    .font(.system(size: 12, design: .monospaced))
                    .frame(height: 120)
                    .padding(8)
                    .background(Color(red: 0.07, green: 0.07, blue: 0.10),
                                in: RoundedRectangle(cornerRadius: 6))
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .strokeBorder(
                                parseError != nil
                                    ? Color.red.opacity(0.5)
                                    : Color.white.opacity(0.08),
                                lineWidth: 1
                            )
                    )
                    .padding(.horizontal, 16)
                    .focused($argsFocused)
                    .onChange(of: argsText) { _, _ in
                        parseError = parsedArgs == nil && argsText != "{}" ? "Invalid JSON" : nil
                    }

                if let err = parseError {
                    Text(err)
                        .font(.system(size: 10))
                        .foregroundStyle(.red)
                        .padding(.horizontal, 16)
                }
            }

            Divider().opacity(0.2).padding(.top, 12)

            // Action buttons
            HStack {
                Button("Cancel") { onCancel() }
                    .buttonStyle(.bordered)
                Spacer()
                Button {
                    if let args = parsedArgs {
                        onInvoke(args)
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "play.fill").font(.system(size: 10))
                        Text("Run Tool")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(parsedArgs == nil)
                .keyboardShortcut(.return, modifiers: .command)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color(red: 0.1, green: 0.1, blue: 0.13))
        }
        .onAppear { argsFocused = true }
    }
}

// MARK: - Hover effect extension helper

private extension View {
    @ViewBuilder
    func hoverEffect(background: @escaping (Bool) -> Color) -> some View {
        self.modifier(HoverBackgroundModifier(background: background))
    }
}

private struct HoverBackgroundModifier: ViewModifier {
    @State private var hovering = false
    let background: (Bool) -> Color

    func body(content: Content) -> some View {
        content
            .background(background(hovering), in: RoundedRectangle(cornerRadius: 6))
            .onHover { hovering = $0 }
            .animation(.easeOut(duration: 0.1), value: hovering)
    }
}

// MARK: - QPanelFormRow

private struct QPanelFormRow<Content: View>: View {
    let label: String
    let content: Content

    init(_ label: String, @ViewBuilder content: () -> Content) {
        self.label = label
        self.content = content()
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text(label)
                .font(.system(size: 11))
                .foregroundStyle(Color(red: 0.65, green: 0.65, blue: 0.80))
                .frame(width: 80, alignment: .trailing)
            content.frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

// MARK: - MCPQuickPanel host modifier
// Apply this to any view to attach the overlay + keyboard shortcut.

struct MCPQuickPanelHost: ViewModifier {
    @State private var show = false
    @EnvironmentObject var app: AppState

    func body(content: Content) -> some View {
        ZStack {
            content
            if show {
                MCPQuickPanel(isPresented: $show)
                    .environmentObject(app)
                    .zIndex(99)
            }
        }
        // ⌘⇧M — open Quick Panel (handled via toolbar button's keyboardShortcut)
    }
}

extension View {
    func mcpQuickPanel() -> some View {
        self.modifier(MCPQuickPanelHost())
    }
}
