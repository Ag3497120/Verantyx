import Foundation

/// External compatibility contract between replaceable LLMs and Vera.
///
/// A model is never trusted because its name is familiar. Qualified entries
/// are combinations exercised against this exact protocol. Every other model
/// starts in probation and may propose output, but only canonical typed IR that
/// passes the same deterministic validators can affect the garment job.
enum GarmentModelCompatibility {
    enum Qualification: String {
        case deterministic = "DETERMINISTIC_NO_MODEL"
        case qualified = "QUALIFIED"
        case probation = "PROBATION"
        case unsupported = "UNSUPPORTED"
    }

    enum Operation: String {
        case languageRoute = "ATELIER_LANGUAGE_ROUTE_V1"
        case visionStructure = "ATELIER_VISION_STRUCTURE_V1"
        case factoryProposal = "GARMENT_FACTORY_PROPOSAL_V1"
    }

    struct Profile: Equatable {
        let sourceName: String
        let qualification: Qualification
        let languageEnvelope: Bool
        let visionInput: Bool
        let strictSchemaTransport: Bool
        let boundedRepairAttempts: Int
        let reason: String

        var displayLabel: String {
            switch qualification {
            case .deterministic: return "Vera deterministic"
            case .qualified: return "Qualified"
            case .probation: return "Probation"
            case .unsupported: return "Unsupported"
            }
        }
    }

    /// This is deliberately an allow-list of *tested provider/model pairs*,
    /// not a claim that related model families behave identically.
    private static let qualifiedSignatures: Set<String> = [
        "lmstudio:qwen/qwen3.6-35b-a3b",
    ]

    static func profile(sourceName raw: String) -> Profile {
        let source = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalized = source.lowercased()
        if normalized == "vera-structure" {
            return Profile(
                sourceName: source, qualification: .deterministic,
                languageEnvelope: false, visionInput: false,
                strictSchemaTransport: true, boundedRepairAttempts: 0,
                reason: "Vera structure mode does not call an LLM")
        }
        if qualifiedSignatures.contains(normalized) {
            return Profile(
                sourceName: source, qualification: .qualified,
                languageEnvelope: true, visionInput: true,
                strictSchemaTransport: true, boundedRepairAttempts: 1,
                reason: "provider/model pair passed the Atelier envelope and pixel proposal path")
        }
        if normalized.hasPrefix("jgen:") {
            return Profile(
                sourceName: source, qualification: .probation,
                languageEnvelope: true, visionInput: false,
                strictSchemaTransport: false, boundedRepairAttempts: 1,
                reason: "text proposal transport is available; pixel input is not connected")
        }
        if normalized.hasPrefix("ollama:")
            || normalized.hasPrefix("lmstudio:")
            || normalized.hasPrefix("cloud:") {
            return Profile(
                sourceName: source, qualification: .probation,
                languageEnvelope: true, visionInput: true,
                strictSchemaTransport: normalized.hasPrefix("lmstudio:"),
                boundedRepairAttempts: 1,
                reason: "unknown model may attempt the protocol but has not passed the compatibility suite")
        }
        return Profile(
            sourceName: source, qualification: .unsupported,
            languageEnvelope: false, visionInput: false,
            strictSchemaTransport: false, boundedRepairAttempts: 0,
            reason: "no Atelier model transport is registered for this source")
    }

    static func harnessPrefix(sourceName: String, operation: Operation) -> String {
        let profile = profile(sourceName: sourceName)
        return """
        VERA_EXTERNAL_MODEL_HARNESS
        protocol=garment.model.compatibility.v1
        operation=\(operation.rawValue)
        qualification=\(profile.qualification.rawValue)
        minimum_gate=typed_schema+closed_vocabulary+provenance+deterministic_validation
        authority=PROPOSED_ONLY
        The model may interpret and propose. It may not emit human approval,
        OBSERVED evidence, manufacturing readiness, or a Vera success verdict.
        Different prose is allowed; accepted typed IR is canonicalized before
        any deterministic garment action.
        """
    }

    /// One bounded normalization retry absorbs common provider formatting
    /// drift. It does not ask the model to change intent or invent missing
    /// facts. A second failure becomes a typed compatibility refusal.
    static func plannerRepairPrompt(
        sourceName: String, userRequest: String, rawResponse: String
    ) -> String {
        let clipped = String(rawResponse.prefix(8_000))
        return """
        \(harnessPrefix(sourceName: sourceName, operation: .languageRoute))
        NORMALIZATION_RETRY 1/1
        Your previous response did not satisfy the Atelier transport envelope.
        Preserve its intended natural-language answer and semantic decision.
        Return exactly one JSON object with non-null `speech` and `command`.
        `command.action` must be one of CONVERSATION, SET_REQUIREMENTS,
        GENERATE_FROM_IMAGE, PROPOSE_STRUCTURE, RUN_SIMULATION. Use
        CONVERSATION rather than inventing an action. Do not add measurements
        absent from the user's request.

        USER_REQUEST:
        \(userRequest)

        PREVIOUS_MODEL_RESPONSE:
        \(clipped)
        """
    }
}
