import CryptoKit
import Foundation

/// The only command shape accepted from the beginner garment composer.
/// Natural language never reaches a garment tool directly: it must first
/// become this closed, unit-bearing envelope through `GarmentCommandParser`.
struct GarmentCommandIR: Codable, Equatable, Sendable {
    static let schema = "garment.command.v1"

    enum Intent: String, Codable, CaseIterable, Sendable {
        case navigate = "NAVIGATE"
        case inspect = "INSPECT"
        case adjustPatternSpan = "ADJUST_PATTERN_SPAN"
        case addEase = "ADD_EASE"
        case changeLength = "CHANGE_LENGTH"
        case changeMaterial = "CHANGE_MATERIAL"
        case setRequirements = "SET_REQUIREMENTS"
        case generateFromImage = "GENERATE_FROM_IMAGE"
        case proposeStructure = "PROPOSE_STRUCTURE"
        case runSimulation = "RUN_SIMULATION"
        case compareSimulations = "COMPARE_SIMULATIONS"
        case approve = "APPROVE"
        case reject = "REJECT"
        case undo = "UNDO"
    }

    enum Provenance: String, Codable, Sendable {
        case deterministicParse = "DETERMINISTIC_PARSE"
        case modelProposal = "MODEL_PROPOSAL"
        case humanInput = "HUMAN_INPUT"
    }

    enum Unit: String, Codable, Sendable { case cm, mm, m }

    struct Target: Codable, Equatable, Sendable {
        var kind: String
        var first: Int?
        var last: Int?
        var reference: String?
        var candidateKind: String?

        static func pattern(first: Int, last: Int) -> Self {
            .init(kind: "PATTERN_SPAN", first: first, last: last)
        }
    }

    struct Operation: Codable, Equatable, Sendable {
        var kind: String
        var value: Double?
        var unit: Unit?
        var material: String?
        var previewDigest: String?
        var note: String?
        var requirements: [Requirement]?
    }

    /// A user's open-ended request after it has passed through the selected
    /// model and Vera's closed validator.  This is deliberately richer than
    /// the old fixed phrase grammar: names, fit goals and construction wishes
    /// can remain text, while every dimensional value still carries a unit.
    struct Requirement: Codable, Equatable, Sendable {
        enum Kind: String, Codable, CaseIterable, Sendable {
            case standardSize = "STANDARD_SIZE"
            case bodyMeasurement = "BODY_MEASUREMENT"
            case garmentMeasurement = "GARMENT_MEASUREMENT"
            case ease = "EASE"
            case length = "LENGTH"
            case fit = "FIT"
            case material = "MATERIAL"
            case structure = "STRUCTURE"
            case detail = "DETAIL"
            case construction = "CONSTRUCTION"
            case comfort = "COMFORT"
        }

        let kind: Kind
        let target: String
        let text: String?
        let value: Double?
        let unit: Unit?
        let note: String?
    }

    let schema: String
    let commandID: String
    let intent: Intent
    var target: Target?
    var operation: Operation?
    var jobID: String?
    let commit: Bool
    let provenance: Provenance

    enum CodingKeys: String, CodingKey {
        case schema, intent, target, operation, commit, provenance
        case commandID = "command_id"
        case jobID = "job_id"
    }

    init(commandID: String, intent: Intent, target: Target? = nil,
         operation: Operation? = nil, jobID: String? = nil,
         commit: Bool = false,
         provenance: Provenance = .deterministicParse) {
        self.schema = Self.schema
        self.commandID = commandID
        self.intent = intent
        self.target = target
        self.operation = operation
        self.jobID = jobID
        self.commit = commit
        self.provenance = provenance
    }

    var jsonString: String? {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        guard let data = try? encoder.encode(self) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    var requiresPreview: Bool {
        switch intent {
        case .adjustPatternSpan, .addEase, .changeLength, .changeMaterial,
             .setRequirements,
             .generateFromImage, .proposeStructure, .runSimulation:
            return true
        default:
            return false
        }
    }

    var suggestedStep: String? {
        switch intent {
        case .adjustPatternSpan, .addEase, .changeLength, .setRequirements:
            return "Pattern"
        case .changeMaterial, .compareSimulations: return "Materials"
        case .generateFromImage: return "Sources"
        case .proposeStructure: return "Structure"
        case .runSimulation: return "Solid"
        default: return nil
        }
    }
}

struct GarmentCommandRefusal: Error, Equatable, Sendable {
    let verdict: String
    let why: String
    let howToClose: String
}

/// Closed deterministic grammar for beginner commands. It intentionally does
/// not "best effort" an unrecognised phrase into a nearby operation.
enum GarmentCommandParser {
    enum Result: Equatable {
        case command(GarmentCommandIR)
        /// The line is not a garment mutation; legacy navigation may inspect it.
        case notACommand
        /// It names a supported mutation but omits a required typed field.
        case refused(GarmentCommandRefusal)
    }

    private struct Dimension {
        let value: Double
        let unit: GarmentCommandIR.Unit
    }

    static func parse(_ raw: String, jobID: String? = nil) -> Result {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return .notACommand }
        let lower = text.lowercased()
        let commandID = stableID(for: lower)

        if lower == "undo" || lower == "元に戻す" || lower == "取り消す" {
            return .command(.init(commandID: commandID, intent: .undo,
                                  jobID: jobID, provenance: .humanInput))
        }
        if hasAny(lower, ["承認", "approve"]) {
            guard let digest = digestToken(in: text) else {
                return .refused(.init(
                    verdict: "UNKNOWN_APPROVAL_DIGEST_REQUIRED",
                    why: "承認対象のpreview digestが指定されていません",
                    howToClose: "プレビューに表示された承認ボタンを使ってください"))
            }
            return .command(.init(
                commandID: commandID, intent: .approve,
                operation: .init(kind: "APPROVE_PREVIEW", previewDigest: digest),
                jobID: jobID, commit: true, provenance: .humanInput))
        }
        if hasAny(lower, ["却下", "reject"]) {
            guard let digest = digestToken(in: text) else {
                return .refused(.init(
                    verdict: "UNKNOWN_REJECTION_DIGEST_REQUIRED",
                    why: "却下対象のpreview digestが指定されていません",
                    howToClose: "プレビューに表示された却下ボタンを使ってください"))
            }
            return .command(.init(
                commandID: commandID, intent: .reject,
                operation: .init(kind: "REJECT_PREVIEW", previewDigest: digest),
                jobID: jobID, provenance: .humanInput))
        }

        if hasAny(lower, ["シミュレーション比較", "比較シミュレーション",
                          "compare simulations", "素材候補を比較", "揺れ方を比較"]) {
            return .command(.init(
                commandID: commandID, intent: .compareSimulations,
                target: .init(kind: "SIMULATION_CANDIDATES",
                              candidateKind: "MATERIAL"), jobID: jobID))
        }
        if hasAny(lower, ["シミュレーション", "simulation", "風を当て", "揺らして"]) {
            return .command(.init(commandID: commandID, intent: .runSimulation,
                                  target: .init(kind: "ACTIVE_GARMENT"), jobID: jobID))
        }
        if isImageGenerationRequest(lower) {
            return .command(.init(commandID: commandID, intent: .generateFromImage,
                                  target: .init(kind: "SELECTED_IMAGE"), jobID: jobID))
        }
        if hasAny(lower, ["背面候補", "後ろの候補", "背面を推論", "素材候補",
                          "素材を推論", "back candidates", "material candidates"]) {
            let candidate = hasAny(lower, ["背面", "後ろ", "back"]) ? "BACK" : "MATERIAL"
            return .command(.init(
                commandID: commandID, intent: .inspect,
                target: .init(kind: "CANDIDATES", candidateKind: candidate), jobID: jobID))
        }
        if hasAny(lower, ["構成案", "構造案", "新しい服を構成", "服を構成",
                          "propose structure", "structure proposal"]) {
            return .command(.init(commandID: commandID, intent: .proposeStructure,
                                  target: .init(kind: "ACTIVE_GARMENT"), jobID: jobID))
        }

        if hasAny(lower, ["素材を", "material to", "change material"]) &&
            hasAny(lower, ["変更", "替え", "変え", "にして", "change", " to "]) {
            guard let material = materialName(in: text), !material.isEmpty else {
                return .refused(.init(
                    verdict: "UNKNOWN_MATERIAL_REQUIRED",
                    why: "変更後の素材名が一意に読めません",
                    howToClose: "例: 素材をジャージーに変更"))
            }
            return .command(.init(
                commandID: commandID, intent: .changeMaterial,
                target: .init(kind: "ACTIVE_GARMENT"),
                operation: .init(kind: "SET_MATERIAL", material: material), jobID: jobID))
        }

        let span = numberSpan(in: text)
        let mutationWords = ["広げ", "狭め", "ゆとり", "長く", "短く", "丈を",
                             "loosen", "widen", "narrow", "longer", "shorter", "ease"]
        if span != nil && hasAny(lower, mutationWords) {
            guard let dimension = dimension(in: text) else {
                return .refused(.init(
                    verdict: "UNKNOWN_EXPLICIT_UNIT_REQUIRED",
                    why: "変更量と単位を一意に読めません",
                    howToClose: "例: 30番から35番を3cm広げて"))
            }
            let (first, last) = span!
            let isLength = hasAny(lower, ["長く", "短く", "丈", "longer", "shorter"])
            let negative = hasAny(lower, ["狭め", "短く", "narrow", "shorter"])
            let operation = GarmentCommandIR.Operation(
                kind: isLength ? "CHANGE_LENGTH" : "ADD_EASE",
                value: negative ? -dimension.value : dimension.value,
                unit: dimension.unit)
            return .command(.init(
                commandID: commandID, intent: .adjustPatternSpan,
                target: .pattern(first: min(first, last), last: max(first, last)),
                operation: operation, jobID: jobID))
        }

        if hasAny(lower, ["ゆとりを", "add ease", "ease by"]) {
            guard let dimension = dimension(in: text) else {
                return .refused(.init(
                    verdict: "UNKNOWN_EXPLICIT_UNIT_REQUIRED",
                    why: "ゆとり量と単位を一意に読めません",
                    howToClose: "例: 全体に2cmのゆとりを追加"))
            }
            return .command(.init(
                commandID: commandID, intent: .addEase,
                target: .init(kind: "ACTIVE_GARMENT"),
                operation: .init(kind: "ADD_EASE", value: dimension.value,
                                 unit: dimension.unit), jobID: jobID))
        }

        return .notACommand
    }

    static func approval(previewDigest: String, jobID: String) -> GarmentCommandIR {
        .init(commandID: stableID(for: "approve:\(previewDigest)"), intent: .approve,
              operation: .init(kind: "APPROVE_PREVIEW", previewDigest: previewDigest),
              jobID: jobID, commit: true, provenance: .humanInput)
    }

    static func rejection(previewDigest: String, jobID: String) -> GarmentCommandIR {
        .init(commandID: stableID(for: "reject:\(previewDigest)"), intent: .reject,
              operation: .init(kind: "REJECT_PREVIEW", previewDigest: previewDigest),
              jobID: jobID, provenance: .humanInput)
    }

    private static func hasAny(_ text: String, _ words: [String]) -> Bool {
        words.contains { text.contains($0.lowercased()) }
    }

    /// Referential photo commands are deterministic when an image is already
    /// selected.  Word order varies naturally in Japanese ("この画像で服を作る"
    /// vs. "この画像を服にして"), so matching only one full phrase needlessly
    /// routed the latter through an LLM and could stop on malformed JSON.
    private static func isImageGenerationRequest(_ text: String) -> Bool {
        if hasAny(text, ["この画像で服", "この写真で服", "写真から服", "画像から服",
                         "generate from image", "make this garment", "make clothes from"]) {
            return true
        }
        let hasImage = hasAny(text, ["この画像", "この写真", "添付画像", "添付写真",
                                       "選択した画像", "選択した写真"])
        let hasGarmentAction = hasAny(text, ["服にして", "衣装にして", "服を作", "衣装を作",
                                               "型紙にして", "服として再現", "衣装として再現"])
        return hasImage && hasGarmentAction
    }

    private static func matches(_ pattern: String, in text: String) -> NSTextCheckingResult? {
        guard let expression = try? NSRegularExpression(
            pattern: pattern, options: [.caseInsensitive]) else { return nil }
        let ns = text as NSString
        return expression.firstMatch(in: text, range: NSRange(location: 0, length: ns.length))
    }

    private static func numberSpan(in text: String) -> (Int, Int)? {
        let pattern = #"(\d+)\s*番?\s*(?:から|〜|~|-|–|to)\s*(\d+)\s*番?"#
        guard let match = matches(pattern, in: text) else { return nil }
        let ns = text as NSString
        guard let first = Int(ns.substring(with: match.range(at: 1))),
              let last = Int(ns.substring(with: match.range(at: 2))) else { return nil }
        return (first, last)
    }

    private static func dimension(in text: String) -> Dimension? {
        let pattern = #"([0-9]+(?:\.[0-9]+)?)\s*(cm|mm|m|センチ(?:メートル)?|ミリ(?:メートル)?|メートル)"#
        guard let match = matches(pattern, in: text) else { return nil }
        let ns = text as NSString
        guard let value = Double(ns.substring(with: match.range(at: 1))), value > 0 else { return nil }
        let token = ns.substring(with: match.range(at: 2)).lowercased()
        let unit: GarmentCommandIR.Unit
        if token == "mm" || token.hasPrefix("ミリ") { unit = .mm }
        else if token == "m" || token == "メートル" { unit = .m }
        else { unit = .cm }
        return Dimension(value: value, unit: unit)
    }

    private static func materialName(in text: String) -> String? {
        let patterns = [
            #"素材を\s*([^\s、。]+?)\s*(?:に変更|に替え|に変え|にして)"#,
            #"(?:change material to|material to)\s+([A-Za-z][A-Za-z0-9 _-]{0,48})"#,
        ]
        let ns = text as NSString
        for pattern in patterns {
            if let match = matches(pattern, in: text), match.numberOfRanges > 1 {
                return ns.substring(with: match.range(at: 1))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return nil
    }

    private static func digestToken(in text: String) -> String? {
        let pattern = #"\b([0-9a-f]{12,64})\b"#
        guard let match = matches(pattern, in: text) else { return nil }
        return (text as NSString).substring(with: match.range(at: 1)).lowercased()
    }

    private static func stableID(for text: String) -> String {
        let digest = SHA256.hash(data: Data(text.utf8))
            .map { String(format: "%02x", $0) }.joined()
        return "cmd-\(digest.prefix(20))"
    }
}
