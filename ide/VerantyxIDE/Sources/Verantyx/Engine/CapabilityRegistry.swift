import Foundation

/// Named capabilities the Web module host can invoke. Thin wrappers over
/// VeraMemoryBridge / JGEN / council settings — no second business-logic layer.
///
/// Growth substrate = Milestone M (closed) + O (gaps) + quarantine + JGEN
/// actuator status. Not a “level 1–3” classifier.
@MainActor
enum CapabilityRegistry {

    enum CapError: Error, LocalizedError {
        case unknown(String)
        case badArgs(String)
        var errorDescription: String? {
            switch self {
            case .unknown(let n): return "Unknown capability: \(n)"
            case .badArgs(let m): return m
            }
        }
    }

    /// Dispatch `name` with JSON-compatible `args`. Returns JSON-serializable map.
    static func invoke(_ name: String, args: [String: Any] = [:]) async throws -> [String: Any] {
        switch name {
        case "vera.heartbeat":
            let llm = (args["llm_model"] as? String) ?? ""
            let mode = cognitionModeArg(args)
            let raw = await VeraMemoryBridge.triggerHeartbeat(llmModel: llm, cognitionMode: mode)
            return ["ok": true, "result": raw]

        case "vera.wake_summary":
            let since = (args["since_seconds"] as? Double) ?? 43200
            let raw = await EternalVeraBridge.wakeMerged(sinceSeconds: since)
            return ["ok": true, "result": raw]

        case "vera.list_pending_domain_modules":
            let items = await VeraMemoryBridge.listPendingDomainModules()
            return [
                "ok": true,
                "items": items.map { m -> [String: Any] in
                    [
                        "index": m.index,
                        "name": m.name,
                        "source_code": m.sourceCode,
                        "candidate_summary": m.candidateSummary,
                        "test_report": m.testReport,
                    ]
                },
            ]

        case "vera.accept_domain_module":
            guard let index = intArg(args, "index") else {
                throw CapError.badArgs("index required")
            }
            let ok = await VeraMemoryBridge.acceptDomainModule(index: index)
            if ok {
                VectorGrowthHooks.shared.noteQuarantineAccepted(kind: .domainModule, index: index)
            }
            return ["ok": ok]

        case "vera.reject_domain_module":
            guard let index = intArg(args, "index") else {
                throw CapError.badArgs("index required")
            }
            let ok = await VeraMemoryBridge.rejectDomainModule(index: index)
            return ["ok": ok]

        case "vera.list_pending_ai_facts":
            let items = await VeraMemoryBridge.listPendingAiFacts()
            return [
                "ok": true,
                "items": items.map { f -> [String: Any] in
                    ["index": f.index, "text": f.text, "source": f.source, "timestamp": f.timestamp]
                },
            ]

        case "vera.accept_ai_fact":
            guard let index = intArg(args, "index") else {
                throw CapError.badArgs("index required")
            }
            let ok = await VeraMemoryBridge.acceptAiFact(index: index)
            if ok {
                VectorGrowthHooks.shared.noteQuarantineAccepted(kind: .aiFact, index: index)
            }
            return ["ok": ok]

        case "vera.reject_ai_fact":
            guard let index = intArg(args, "index") else {
                throw CapError.badArgs("index required")
            }
            let ok = await VeraMemoryBridge.rejectAiFact(index: index)
            return ["ok": ok]

        case "vera.list_pending_tool_calls":
            let items = await VeraMemoryBridge.listPendingToolCalls()
            return [
                "ok": true,
                "items": items.map { t -> [String: Any] in
                    [
                        "index": t.index,
                        "call_id": t.callId,
                        "tool_name": t.toolName,
                        "args_text": t.argsText,
                        "reason": t.reason,
                        "task": t.task,
                    ]
                },
            ]

        case "vera.accept_tool_call":
            guard let index = intArg(args, "index") else {
                throw CapError.badArgs("index required")
            }
            let result = await VeraMemoryBridge.acceptToolCall(index: index)
            return ["ok": result != nil, "result": result ?? ""]

        case "vera.reject_tool_call":
            guard let index = intArg(args, "index") else {
                throw CapError.badArgs("index required")
            }
            let ok = await VeraMemoryBridge.rejectToolCall(index: index)
            return ["ok": ok]

        case "council.get_cognition_mode":
            let mode = CouncilSettingsStore.shared.cognitionMode.rawValue
            let harness = CouncilSettingsStore.shared.useVeraHarnessForChat
            return ["ok": true, "cognition_mode": mode, "use_vera_harness": harness]

        case "council.set_cognition_mode":
            guard let raw = args["cognition_mode"] as? String,
                  let mode = CouncilSettingsStore.CognitionMode(rawValue: raw) else {
                throw CapError.badArgs("cognition_mode must be normal|experiment|sleep")
            }
            CouncilSettingsStore.shared.cognitionMode = mode
            return ["ok": true, "cognition_mode": mode.rawValue]

        case "council.set_vera_harness":
            let on = (args["enabled"] as? Bool) ?? false
            CouncilSettingsStore.shared.useVeraHarnessForChat = on
            return ["ok": true, "use_vera_harness": on]

        case "jgen.status":
            return await VectorGrowthHooks.shared.statusMap()

        case "multimodal.status":
            return await JGenVectorBusMemory.multimodalStatus()

        case "jgen.ensure_agent_server":
            do {
                try await JGenAgentServer.shared.start()
            } catch {
                return ["ok": false, "error": error.localizedDescription]
            }
            let running = await JGenAgentServer.shared.isRunning
            let port = await JGenAgentServer.shared.port
            return ["ok": running, "jgen_agent_server_running": running, "jgen_agent_server_port": Int(port)]

        case "growth.explain":
            // Honest glossary for the web UI — never claims level 1–3 evolution.
            return [
                "ok": true,
                "loops": [
                    [
                        "id": "M",
                        "name": "Closed-domain growth",
                        "classify": ["reject_open_domain", "needs_more_facts", "growth_candidate"],
                        "promotion": "quarantine → human accept_domain_module only",
                    ],
                    [
                        "id": "O",
                        "name": "Open-domain gaps",
                        "modes": ["normal", "experiment", "sleep"],
                        "promotion": "quarantine only; never auto-trusted",
                    ],
                ],
                "not_implemented": "level_1_to_3_self_evolution_classifier",
                "actuator": "jgen_hidden_state_inject_and_vector_bus",
                "multimodal": [
                    "AX_text_aligned_encode_inject",
                    "VisualMemoryStore_feature_print_text_recall",
                    "UITestVectorTrace_jgen_space",
                    "GapGraph_record_ui_transition",
                    "VisualHiddenStateBridge_experimental_unaligned",
                ],
            ]

        default:
            throw CapError.unknown(name)
        }
    }

    private static func cognitionModeArg(_ args: [String: Any]) -> String {
        if let m = args["cognition_mode"] as? String,
           ["normal", "experiment", "sleep"].contains(m) {
            return m
        }
        return CouncilSettingsStore.shared.cognitionMode.rawValue
    }

    private static func intArg(_ args: [String: Any], _ key: String) -> Int? {
        if let i = args[key] as? Int { return i }
        if let n = args[key] as? NSNumber { return n.intValue }
        if let d = args[key] as? Double { return Int(d) }
        return nil
    }
}
