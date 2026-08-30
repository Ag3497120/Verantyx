import CryptoKit
import Foundation

/// Converts an unrestricted beginner request into a proposal-only garment IR.
///
/// The selected LLM is allowed to interpret language, but it never chooses a
/// tool, changes factory phase, approves a preview, or writes a measurement.
/// Vera accepts only this small JSON vocabulary and then sends the resulting
/// `GarmentCommandIR` through the same preview/approval door as hand-parsed
/// commands.
@MainActor
enum AtelierGarmentRequestPlanner {
    enum Outcome {
        /// Natural model speech is always preserved. `command` is only the
        /// optional machine-readable proposal found in a dedicated block.
        case response(text: String, command: GarmentCommandIR?)
        case refused(String)
    }

    private struct Proposal: Decodable {
        let action: String
        let requirements: [RequirementProposal]?
        let reason: String?
    }

    /// Transport envelope only. `speech` is unrestricted user-facing prose;
    /// `command` is a separate proposal which Vera may reject. Keeping both in
    /// one response avoids relying on a model to remember a trailing tag after
    /// it has finished a long natural-language answer.
    private struct ModelEnvelope: Decodable {
        let speech: String
        let command: Proposal?
    }

    private struct RequirementProposal: Decodable {
        let kind: String
        let target: String
        let text: String?
        let value: Double?
        let unit: String?
        let note: String?
    }

    private struct RequirementValidationError: Error {
        let message: String
    }

    static func plan(_ request: String, pick: AtelierAnalyst.Pick,
                     jobID: String) async -> Outcome {
        guard let proposer = GarmentFactoryModelMouth.proposer(
            for: pick, responseFormat: plannerResponseFormat) else {
            return .refused(
                "UNKNOWN_GARMENT_LANGUAGE_MODEL_REQUIRED\n"
                + "AtelierチャットはLLM主導です。制作モデルを選択してください。")
        }
        let compatibility = GarmentModelCompatibility.profile(
            sourceName: pick.sourceName)
        guard let raw = await proposer(prompt(
            for: request, compatibility: compatibility)) else {
            return .refused(
                "UNKNOWN_GARMENT_MODEL_UNREACHABLE\n制作モデルから応答を受信できませんでした。")
        }
        var turn = decodeTurn(raw)
        if turn.transport == .unstructured,
           compatibility.boundedRepairAttempts > 0,
           let repairedRaw = await proposer(
                GarmentModelCompatibility.plannerRepairPrompt(
                    sourceName: pick.sourceName,
                    userRequest: request, rawResponse: raw)) {
            let repaired = decodeTurn(repairedRaw)
            if repaired.transport != .unstructured {
                turn = repaired
            }
        }
        guard let proposal = turn.proposal else {
            let warning = "UNKNOWN_MODEL_CAPABILITY_ENVELOPE — "
                + "このモデルの自由応答は表示しますが、型付き制作提案を1回の正規化再試行後も取得できなかったため実行しません。"
            return .response(text: turn.text + "\n\nVera検証: " + warning,
                             command: nil)
        }
        let commandID = stableID(request + "\0" + pick.sourceName)
        switch proposal.action.uppercased() {
        case "CONVERSATION":
            // The model must make an explicit semantic routing decision.  A
            // conversational turn remains free speech and carries no engine
            // authority, but it can no longer evade an actionable request by
            // silently returning a null command beside speech that promises a
            // later action.
            return .response(text: turn.text, command: nil)
        case "GENERATE_FROM_IMAGE":
            let requirements: [GarmentCommandIR.Requirement]?
            do {
                requirements = try validatedRequirements(
                    proposal.requirements, required: false,
                    explicitUserRequest: request)
            } catch let error as RequirementValidationError {
                return rejectedSpeech(turn.text, error.message)
            } catch {
                return rejectedSpeech(turn.text,
                    "UNKNOWN_TYPED_REQUIREMENTS_REQUIRED — 制作条件を検証できませんでした。")
            }
            return .response(text: turn.text, command: .init(
                commandID: commandID, intent: .generateFromImage,
                target: .init(kind: "SELECTED_IMAGE"),
                operation: .init(kind: "GENERATE_FROM_IMAGE",
                                 note: limited(proposal.reason, 240),
                                 requirements: requirements),
                jobID: jobID, provenance: .modelProposal))
        case "INSPECT_BACK_3D":
            return .response(text: turn.text, command: .init(
                commandID: commandID, intent: .inspect,
                target: .init(kind: "CANDIDATES", candidateKind: "BACK"),
                operation: .init(kind: "REQUEST_BACK_3D",
                                 note: limited(proposal.reason, 240)),
                jobID: jobID, provenance: .modelProposal))
        case "PROPOSE_STRUCTURE":
            return .response(text: turn.text, command: .init(
                commandID: commandID, intent: .proposeStructure,
                target: .init(kind: "ACTIVE_GARMENT"),
                operation: .init(kind: "PROPOSE_STRUCTURE",
                                 note: limited(proposal.reason, 240)),
                jobID: jobID, provenance: .modelProposal))
        case "RUN_SIMULATION":
            return .response(text: turn.text, command: .init(
                commandID: commandID, intent: .runSimulation,
                target: .init(kind: "ACTIVE_GARMENT"),
                operation: .init(kind: "RUN_SIMULATION",
                                 note: limited(proposal.reason, 240)),
                jobID: jobID, provenance: .modelProposal))
        case "SET_REQUIREMENTS":
            let accepted: [GarmentCommandIR.Requirement]
            do {
                accepted = try validatedRequirements(
                    proposal.requirements, required: true,
                    explicitUserRequest: request) ?? []
            } catch let error as RequirementValidationError {
                return rejectedSpeech(turn.text, error.message)
            } catch {
                return rejectedSpeech(turn.text,
                    "UNKNOWN_TYPED_REQUIREMENTS_REQUIRED — 制作条件を検証できませんでした。")
            }
            return .response(text: turn.text, command: .init(
                commandID: commandID, intent: .setRequirements,
                target: .init(kind: "ACTIVE_GARMENT"),
                operation: .init(kind: "SET_REQUIREMENTS",
                                 note: limited(proposal.reason, 240),
                                 requirements: accepted),
                jobID: jobID, provenance: .modelProposal))
        default:
            return rejectedSpeech(turn.text,
                "UNKNOWN_GARMENT_REQUEST_ACTION — 制作モデルの動作提案は許可外なので実行していません。")
        }
    }

    /// LM Studio supports grammar-backed JSON Schema output. Natural speech
    /// remains model-authored in `speech`; only the separate proposal mouth is
    /// constrained to the vocabulary Vera can validate. Other model providers
    /// still pass through the same decoder and fail closed when they drift.
    private static var plannerResponseFormat: [String: Any] {
        let nullableString: [String: Any] = [
            "anyOf": [["type": "string"], ["type": "null"]]
        ]
        let nullableNumber: [String: Any] = [
            "anyOf": [["type": "number"], ["type": "null"]]
        ]
        let nullableUnit: [String: Any] = [
            "anyOf": [
                ["type": "string", "enum": ["mm", "cm", "m"]],
                ["type": "null"],
            ]
        ]
        let requirement: [String: Any] = [
            "type": "object",
            "additionalProperties": false,
            "properties": [
                "kind": [
                    "type": "string",
                    "enum": [
                        "STANDARD_SIZE", "BODY_MEASUREMENT",
                        "GARMENT_MEASUREMENT", "EASE", "LENGTH", "FIT",
                        "MATERIAL", "STRUCTURE", "DETAIL", "CONSTRUCTION",
                        "COMFORT",
                    ],
                ],
                "target": ["type": "string"],
                "text": nullableString,
                "value": nullableNumber,
                "unit": nullableUnit,
                "note": nullableString,
            ],
            "required": ["kind", "target", "text", "value", "unit", "note"],
        ]
        let command: [String: Any] = [
            "type": "object",
            "additionalProperties": false,
            "properties": [
                "action": [
                    "type": "string",
                    "enum": [
                        "CONVERSATION", "SET_REQUIREMENTS", "GENERATE_FROM_IMAGE",
                        "INSPECT_BACK_3D",
                        "PROPOSE_STRUCTURE", "RUN_SIMULATION",
                    ],
                ],
                "requirements": [
                    "anyOf": [
                        [
                            "type": "array", "items": requirement,
                            "minItems": 1, "maxItems": 24,
                        ],
                        ["type": "null"],
                    ],
                ],
                "reason": nullableString,
            ],
            "required": ["action", "requirements", "reason"],
        ]
        return [
            "type": "json_schema",
            "json_schema": [
                "name": "atelier_garment_turn",
                "strict": true,
                "schema": [
                    "type": "object",
                    "additionalProperties": false,
                    "properties": [
                        "speech": ["type": "string"],
                        // A route decision is mandatory. CONVERSATION is the
                        // explicit no-action choice; null is not a semantic
                        // decision and previously let clear image-generation
                        // requests fall through as chat-only replies.
                        "command": command,
                    ],
                    "required": ["speech", "command"],
                ],
            ],
        ]
    }

    private static func prompt(
        for request: String,
        compatibility: GarmentModelCompatibility.Profile
    ) -> String {
        let imageContext = AtelierIntake.shared.selectedClip == nil
            ? "No garment image is currently selected."
            : "A garment image is currently selected. You may propose GENERATE_FROM_IMAGE, but do not claim you inspected pixels; Vera's image engine will do that after validation."
        return """
        \(GarmentModelCompatibility.harnessPrefix(
            sourceName: compatibility.sourceName,
            operation: .languageRoute))
        model_compatibility=\(compatibility.qualification.rawValue)
        model_capability_reason=\(compatibility.reason)

        You are a garment-making conversational agent. Return exactly one JSON
        object with this transport shape:
        {"speech":"your natural answer in the user's language",
         "command":{"action":"GENERATE_FROM_IMAGE","reason":"short",
         "requirements":[{"kind":"STANDARD_SIZE","target":"wearer_size",
         "text":"M","value":null,"unit":null,"note":"explicit user request"}]}}
        `speech` is free natural language, not a menu or fixed reply. Keep it
        under 1200 characters, but discuss design intent, uncertainty,
        alternatives and next steps naturally. It will be displayed with an
        explicit "AI generated / unverified" label, so never claim that a tool
        ran, a fact was observed, a design was approved, or an artifact was
        generated. Your `speech` is a proposed plan, not a progress or success
        report. Do not say "作成します", "生成を開始しました", "縫製可能な状態で出力します",
        or an equivalent promise as though work is underway or complete. State
        what the request asks for and what Vera must validate next. If no typed
        tool result exists, say explicitly that no 3D, pattern, or sewing output
        has been generated yet.

        `command` is a separate mandatory semantic route proposal for Vera.
        Use action CONVERSATION with null requirements for ordinary
        conversation; never use a null command. When the user asks to create,
        change or initially analyse the currently selected garment image, it MUST be GENERATE_FROM_IMAGE.
        If that image is already active and the user asks
        to infer, compare, rotate to, or show its hidden back/rear as 3D, use
        INSPECT_BACK_3D instead. That action continues the existing audited
        factory job; it must not restart image intake or claim the rear was seen.
        do not merely promise a later action in `speech`. Vera, not you, decides
        whether the proposal is valid and executable.

        Allowed action: CONVERSATION, SET_REQUIREMENTS, GENERATE_FROM_IMAGE,
        INSPECT_BACK_3D, PROPOSE_STRUCTURE, RUN_SIMULATION.

        For SET_REQUIREMENTS, and for GENERATE_FROM_IMAGE when the user gives
        size/style/fit/construction constraints, return 1-24 requirements.
        Requirements are optional only when GENERATE_FROM_IMAGE has no explicit
        constraints. Allowed kind:
        STANDARD_SIZE, BODY_MEASUREMENT, GARMENT_MEASUREMENT, EASE, LENGTH,
        FIT, MATERIAL, STRUCTURE, DETAIL, CONSTRUCTION, COMFORT.
        Each requirement is:
        {"kind":"...","target":"...","text":"optional",
         "value":number_or_null,"unit":"mm|cm|m|optional","note":"optional"}
        Every numeric value MUST have a unit. Standard sizes such as S/M/L,
        fit, material, structure and details belong in text, not a fake number.
        Keep distinct wishes as distinct requirements. Copy dimensional values
        only when the user explicitly supplied them; never infer measurements
        from the selected image, a standard size label, or appearance. Unknowns
        may be noted; never invent body measurements or invisible garment facts.
        If the user asks to generate from an image and also gives size/style/fit
        constraints, choose GENERATE_FROM_IMAGE and preserve every distinct
        constraint in `requirements`; do not flatten them into `reason`. For
        example, M is STANDARD_SIZE text, waist 72 cm is BODY_MEASUREMENT with
        value 72 and unit cm, and ease 4 cm is EASE with value 4 and unit cm.
        Vera will validate them and open requirement/measurement gates rather
        than inventing missing values.

        Current application context:
        \(imageContext)

        User request:
        \(request)
        """
    }

    private struct DecodedTurn {
        enum Transport: Equatable {
            case canonicalEnvelope
            case legacyCompatible
            case unstructured
        }
        let text: String
        let proposal: Proposal?
        let transport: Transport
    }

    private static func decodeTurn(_ raw: String) -> DecodedTurn {
        let withoutThinking = raw.replacingOccurrences(
            of: #"(?s)<think>.*?</think>"#, with: "",
            options: .regularExpression)

        // Preferred LLM-led protocol: free prose and the action proposal are
        // siblings. A model can speak naturally without needing to append a
        // fragile command tag after finishing a long answer.
        for object in balancedJSONObjects(in: withoutThinking) {
            guard let data = object.data(using: .utf8),
                  let envelope = try? JSONDecoder().decode(
                    ModelEnvelope.self, from: data),
                  let command = envelope.command else { continue }
            return DecodedTurn(
                text: displayText(envelope.speech), proposal: command,
                transport: .canonicalEnvelope)
        }

        // Compatibility with models that still use the previous free-text +
        // tagged proposal protocol.
        let pattern = #"(?s)<vera_command>\s*(.*?)\s*</vera_command>"#
        if let expression = try? NSRegularExpression(pattern: pattern),
           let match = expression.firstMatch(
            in: withoutThinking,
            range: NSRange(withoutThinking.startIndex..., in: withoutThinking)),
           let blockRange = Range(match.range(at: 1), in: withoutThinking),
           let wholeRange = Range(match.range(at: 0), in: withoutThinking) {
            let block = String(withoutThinking[blockRange])
            var speech = withoutThinking
            speech.removeSubrange(wholeRange)
            let clean = displayText(speech)
            if let proposal = decode(block) {
                return DecodedTurn(text: clean, proposal: proposal,
                                   transport: .legacyCompatible)
            }
            return DecodedTurn(
                text: clean + "\n\nVera検証: 型付き提案を読み取れなかったため、発言だけを表示しています。",
                proposal: nil, transport: .unstructured)
        }

        // Compatibility with models that still return the former JSON-only
        // contract. It is treated as a proposal, never as user-facing prose.
        let trimmed = withoutThinking.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.hasPrefix("{"), trimmed.hasSuffix("}"),
           let proposal = decode(trimmed) {
            return DecodedTurn(
                text: proposal.reason ?? "制作モデルが操作候補を提案しました。",
                proposal: proposal, transport: .legacyCompatible)
        }
        return DecodedTurn(text: displayText(withoutThinking), proposal: nil,
                           transport: .unstructured)
    }

    private static func displayText(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "制作モデルから説明文はありません。" : String(trimmed.prefix(6000))
    }

    private static func rejectedSpeech(_ speech: String, _ why: String) -> Outcome {
        .response(text: speech + "\n\nVera検証: \(why)", command: nil)
    }

    private static func decode(_ raw: String) -> Proposal? {
        // Reasoning models may wrap the answer in <think> or markdown and may
        // even mention an example object before the final answer.  Decode each
        // balanced JSON object independently instead of slicing from the first
        // opening brace to the last closing brace, which joins unrelated
        // objects into invalid JSON.
        for object in balancedJSONObjects(in: raw) {
            guard let data = object.data(using: .utf8) else { continue }
            if let proposal = try? JSONDecoder().decode(Proposal.self, from: data) {
                return proposal
            }
        }
        return nil
    }

    private static func balancedJSONObjects(in raw: String) -> [String] {
        var objects: [String] = []
        var start: String.Index?
        var depth = 0
        var inString = false
        var escaped = false

        for index in raw.indices {
            let character = raw[index]
            if inString {
                if escaped {
                    escaped = false
                } else if character == "\\" {
                    escaped = true
                } else if character == "\"" {
                    inString = false
                }
                continue
            }
            if character == "\"" {
                if depth > 0 { inString = true }
            } else if character == "{" {
                if depth == 0 { start = index }
                depth += 1
            } else if character == "}", depth > 0 {
                depth -= 1
                if depth == 0, let objectStart = start {
                    objects.append(String(raw[objectStart...index]))
                    start = nil
                }
            }
        }
        return objects
    }

    private static func limited(_ text: String?, _ limit: Int) -> String? {
        guard let text else { return nil }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return String(trimmed.prefix(limit))
    }

    private static func valueOrText(value: Double?, text: String?) -> Bool {
        value != nil || !(text ?? "").isEmpty
    }

    /// Both image generation and standalone requirement updates pass through
    /// this one validator. Image requirements may be omitted, but once the
    /// model includes the field it has exactly the same closed kinds, count,
    /// target and dimensional-unit rules as SET_REQUIREMENTS.
    private static func validatedRequirements(
        _ proposed: [RequirementProposal]?, required: Bool,
        explicitUserRequest: String
    ) throws -> [GarmentCommandIR.Requirement]? {
        guard let proposed else {
            if required {
                throw RequirementValidationError(message:
                    "UNKNOWN_TYPED_REQUIREMENTS_REQUIRED — 制作条件が空か、24件の上限を超えています。")
            }
            return nil
        }
        guard !proposed.isEmpty, proposed.count <= 24 else {
            throw RequirementValidationError(message:
                "UNKNOWN_TYPED_REQUIREMENTS_REQUIRED — 制作条件が空か、24件の上限を超えています。")
        }

        var accepted: [GarmentCommandIR.Requirement] = []
        accepted.reserveCapacity(proposed.count)
        for item in proposed {
            guard let kind = GarmentCommandIR.Requirement.Kind(
                rawValue: item.kind.uppercased()) else {
                throw RequirementValidationError(message:
                    "UNKNOWN_REQUIREMENT_KIND — 未対応の制作条件: \(item.kind)")
            }
            let target = item.target.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !target.isEmpty, target.count <= 80 else {
                throw RequirementValidationError(message:
                    "UNKNOWN_REQUIREMENT_TARGET — 制作条件の対象が空か長すぎます。")
            }
            let unit = item.unit.flatMap {
                GarmentCommandIR.Unit(rawValue: $0.lowercased())
            }
            if let value = item.value {
                guard value.isFinite, unit != nil else {
                    throw RequirementValidationError(message:
                        "UNKNOWN_DIMENSION_UNIT_REQUIRED — 数値 \(target) には mm / cm / m の単位が必要です。")
                }
                guard let unit,
                      containsExplicitDimension(
                        value: value, unit: unit, in: explicitUserRequest) else {
                    throw RequirementValidationError(message:
                        "UNKNOWN_MEASUREMENT_NOT_EXPLICIT — \(target) の数値はユーザー入力に単位付きで明示されていないため採用できません。")
                }
            } else if item.unit != nil {
                throw RequirementValidationError(message:
                    "UNKNOWN_DIMENSION_VALUE_REQUIRED — 単位だけの制作条件は採用できません。")
            }
            let text = limited(item.text, 160)
            guard valueOrText(value: item.value, text: text) else {
                throw RequirementValidationError(message:
                    "UNKNOWN_REQUIREMENT_VALUE — \(target) の値がありません。")
            }
            accepted.append(.init(kind: kind, target: target, text: text,
                                  value: item.value, unit: unit,
                                  note: limited(item.note, 240)))
        }
        return accepted
    }

    /// A model proposal may normalize units, but it may not manufacture a
    /// dimension from image appearance or a standard-size label. Compare all
    /// dimensions explicitly written by the user in metres so 0.72 m and
    /// 72 cm are equivalent without trusting the model's provenance note.
    private static func containsExplicitDimension(
        value: Double, unit: GarmentCommandIR.Unit, in request: String
    ) -> Bool {
        let normalized = request.precomposedStringWithCompatibilityMapping
        let pattern = #"(?i)(?<![A-Za-z0-9_.])([+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))\s*(mm|millimeters?|millimetres?|ミリ(?:メートル)?|cm|centimeters?|centimetres?|センチ(?:メートル)?|m|meters?|metres?|メートル)(?![A-Za-z])"#
        guard let expression = try? NSRegularExpression(pattern: pattern) else {
            return false
        }
        let wholeRange = NSRange(normalized.startIndex..., in: normalized)
        let proposedMetres = metres(value, unit: unit)
        for match in expression.matches(in: normalized, range: wholeRange) {
            guard let numberRange = Range(match.range(at: 1), in: normalized),
                  let unitRange = Range(match.range(at: 2), in: normalized),
                  let explicitValue = Double(normalized[numberRange]),
                  let explicitUnit = explicitUnit(String(normalized[unitRange]))
            else { continue }
            let explicitMetres = metres(explicitValue, unit: explicitUnit)
            let tolerance = max(1e-9, abs(proposedMetres) * 1e-9)
            if abs(explicitMetres - proposedMetres) <= tolerance {
                return true
            }
        }
        return false
    }

    private static func explicitUnit(_ raw: String) -> GarmentCommandIR.Unit? {
        let lowered = raw.lowercased()
        if lowered == "mm" || lowered.hasPrefix("millimet") ||
            lowered.hasPrefix("ミリ") { return .mm }
        if lowered == "cm" || lowered.hasPrefix("centimet") ||
            lowered.hasPrefix("センチ") { return .cm }
        if lowered == "m" || lowered.hasPrefix("meter") ||
            lowered.hasPrefix("metre") || lowered == "メートル" { return .m }
        return nil
    }

    private static func metres(
        _ value: Double, unit: GarmentCommandIR.Unit
    ) -> Double {
        switch unit {
        case .mm: return value / 1_000
        case .cm: return value / 100
        case .m: return value
        }
    }

    private static func stableID(_ text: String) -> String {
        let digest = SHA256.hash(data: Data(text.utf8))
            .map { String(format: "%02x", $0) }.joined()
        return "cmd-\(digest.prefix(20))"
    }
}
