import CryptoKit
import Foundation
import SwiftUI

struct GarmentMeshPreview: Codable, Equatable, Sendable {
    let vertices: [[Double]]
    let faces: [[Int]]

    var isRenderable: Bool {
        vertices.count >= 3 && !faces.isEmpty &&
        vertices.allSatisfy { $0.count == 3 && $0.allSatisfy(\.isFinite) } &&
        faces.allSatisfy { face in
            face.count >= 3 && face.allSatisfy { $0 >= 0 && $0 < vertices.count }
        }
    }
}

struct GarmentJobSnapshot: Codable, Equatable, Sendable {
    var state: GarmentGenerationJob.State?
    var artifactDigest: String?
    var resultJSON: String
    var mesh: GarmentMeshPreview?

    static let empty = Self(state: nil, artifactDigest: nil,
                            resultJSON: "{}", mesh: nil)
}

struct GarmentPreview: Codable, Equatable, Identifiable, Sendable {
    static let schema = "garment.preview.v1"
    var id: String { digest }

    let schema: String
    let jobID: String
    let previewID: String
    let command: GarmentCommandIR
    let before: GarmentJobSnapshot
    let after: GarmentJobSnapshot
    let changedAddresses: [String]
    let validationResults: [String]
    let digest: String

    enum CodingKeys: String, CodingKey {
        case schema, command, before, after, digest
        case jobID = "job_id"
        case previewID = "preview_id"
        case changedAddresses = "changed_addresses"
        case validationResults = "validation_results"
    }
}

struct GarmentAnswerEnvelope: Equatable, Sendable {
    static let schema = "garment.answer.v1"
    let verdict: String
    let facts: [String]
    let allowedSuggestions: [String]
    let forbiddenClaims: [String]
    let artifacts: [String]
    let provenance: String

    var deterministicText: String {
        let body = facts.isEmpty ? verdict : facts.joined(separator: "\n")
        guard let suggestion = allowedSuggestions.first, !suggestion.isEmpty else { return body }
        return body + "\n" + suggestion
    }
}

/// Swift mirror of the append-only Python garment job. The Python tool remains
/// authoritative; this object only mirrors accepted snapshots for immediate UI
/// feedback. Preview staging never changes `activeSnapshot`.
@MainActor
final class GarmentGenerationJob: ObservableObject {
    static let shared = GarmentGenerationJob()

    enum State: String, Codable, CaseIterable, Sendable {
        case imageReceived = "IMAGE_RECEIVED"
        case regionsConfirmed = "REGIONS_CONFIRMED"
        case geometryContested = "GEOMETRY_CONTESTED"
        case backCandidatesReady = "BACK_CANDIDATES_READY"
        case structureApproved = "STRUCTURE_APPROVED"
        case materialContested = "MATERIAL_CONTESTED"
        case simulationReady = "SIMULATION_READY"
        case shapeApproved = "SHAPE_APPROVED"
        case patternValidated = "PATTERN_VALIDATED"
        case sewingBlockedNoCorpus = "SEWING_BLOCKED_NO_CORPUS"
        case complete = "COMPLETE"
    }

    struct Event: Identifiable, Equatable {
        enum Kind: String { case previewed, approved, rejected, undo }
        let id = UUID()
        let kind: Kind
        let at: Date
        let digest: String
        let snapshot: GarmentJobSnapshot
    }

    let jobID: String
    @Published private(set) var activeSnapshot: GarmentJobSnapshot = .empty
    @Published private(set) var pendingPreview: GarmentPreview?
    @Published private(set) var history: [Event] = []
    @Published private(set) var lastAnswer: GarmentAnswerEnvelope?

    private var committedSnapshots: [GarmentJobSnapshot] = [.empty]
    private var consumedImageSelectionRevision: UInt64?

    private init(jobID: String = UUID().uuidString.lowercased()) {
        self.jobID = jobID
    }

    var canUndo: Bool { committedSnapshots.count > 1 }

    /// A newly selected image starts a new local analysis base even when its
    /// path is byte-for-byte equal to the previous selection. This clears UI
    /// previews only; AtelierIntake retains one source/evidence identity.
    func consumeImageSelection(revision: UInt64) {
        consumedImageSelectionRevision = revision
        activeSnapshot = .empty
        pendingPreview = nil
        history.removeAll()
        lastAnswer = nil
        committedSnapshots = [.empty]
    }

    /// Approved design requirements for the factory model's proposal prompt.
    /// This is read from the committed snapshot only; a pending model-parsed
    /// requirement preview is intentionally invisible here until a person
    /// approves it.
    func approvedRequirementsContext() -> String? {
        guard let data = activeSnapshot.resultJSON.data(using: .utf8),
              let root = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return nil }
        for dictionary in Self.nestedDictionaries(root) {
            guard let requirements = dictionary["design_requirements"] as? [[String: Any]],
                  !requirements.isEmpty,
                  JSONSerialization.isValidJSONObject(requirements),
                  let encoded = try? JSONSerialization.data(
                    withJSONObject: requirements, options: [.sortedKeys]),
                  let json = String(data: encoded, encoding: .utf8) else { continue }
            return json
        }
        return nil
    }

    /// Builds the existing `cross_cloth_simulate` input without inventing a
    /// material. Geometry alone is insufficient: face material ids and every
    /// explicit material coefficient must already be present in an approved
    /// artifact (normally under `simulation_input`).
    func simulationRequestJSON(command: GarmentCommandIR) -> Result<String, GarmentCommandRefusal> {
        guard let data = activeSnapshot.resultJSON.data(using: .utf8),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return .failure(.init(verdict: "UNKNOWN_NO_ACTIVE_GARMENT",
                                  why: "承認済みの服飾artifactがありません",
                                  howToClose: "先に形状と素材をプレビューして承認してください"))
        }
        let candidates = Self.nestedDictionaries(root)
        let input = candidates.compactMap { dictionary -> [String: Any]? in
            if let explicit = dictionary["simulation_input"] as? [String: Any] {
                return explicit
            }
            let required = ["vertices", "faces", "face_material_ids", "materials"]
            return required.allSatisfy { dictionary[$0] != nil } ? dictionary : nil
        }.first
        guard var input else {
            return .failure(.init(
                verdict: "UNKNOWN_SIMULATION_INPUT_REQUIRED",
                why: "承認済みartifactにvertices, faces, face_material_ids, materialsが揃っていません",
                howToClose: "素材係数を確定し、simulation_inputを持つ構造プレビューを承認してください"))
        }
        input["job_id"] = jobID
        input["command"] = commandDictionary(command)
        guard JSONSerialization.isValidJSONObject(input) else {
            return .failure(.init(verdict: "UNKNOWN_SIMULATION_INPUT_ENCODING",
                                  why: "simulation inputをJSONへ変換できません",
                                  howToClose: "artifactの数値と配列形式を確認してください"))
        }
        return .success(Self.canonicalJSONString(input))
    }

    func stage(command: GarmentCommandIR, response: [String: Any]) -> Result<GarmentPreview, GarmentCommandRefusal> {
        let verdict = response["verdict"] as? String ?? "UNKNOWN_ENGINE_RESPONSE"
        guard verdict == "ANSWER" else { return .failure(refusal(from: response)) }

        // Prefer the authoritative append-only job preview when garment_job
        // returned one. Its digest is the only value later accepted by the
        // Python approval gate; recomputing a look-alike digest in Swift would
        // create two sources of truth.
        if let remote = response["result"] as? [String: Any],
           (remote["schema"] as? String) == GarmentPreview.schema,
           let previewID = remote["preview_id"] as? String,
           let remoteDigest = remote["digest"] as? String,
           let beforeRaw = remote["before"] as? [String: Any],
           let afterRaw = remote["after"] as? [String: Any] {
            let before = Self.snapshot(in: beforeRaw)
            let after = Self.snapshot(in: afterRaw)
            guard before.state == activeSnapshot.state else {
                return .failure(.init(
                    verdict: "UNKNOWN_STALE_REMOTE_PREVIEW_BASE",
                    why: "remote previewのbefore stateが現在の承認済み状態と一致しません",
                    howToClose: "現在のjob snapshotからプレビューを作り直してください"))
            }
            if let nextState = after.state,
               nextState != activeSnapshot.state {
                guard Self.canTransition(from: activeSnapshot.state, to: nextState) else {
                    return .failure(.init(
                        verdict: "UNKNOWN_INVALID_JOB_TRANSITION",
                        why: "remote previewが許可されていない状態遷移を要求しました",
                        howToClose: "不足している前段の状態を先に承認してください"))
                }
                guard after.artifactDigest != nil else {
                    return .failure(.init(
                        verdict: "UNKNOWN_JOB_EVIDENCE_REQUIRED",
                        why: "remote previewの状態遷移にartifact digestがありません",
                        howToClose: "遷移根拠のartifact digestを添付してください"))
                }
            }
            let addresses = Self.stringArray(remote["changed_addresses"])
            let validations = Self.validationVerdicts(remote["validation_results"])
            let preview = GarmentPreview(
                schema: GarmentPreview.schema,
                jobID: response["job_id"] as? String ?? jobID,
                previewID: previewID, command: command,
                before: before, after: after,
                changedAddresses: addresses,
                validationResults: validations,
                digest: remoteDigest)
            pendingPreview = preview
            history.append(Event(kind: .previewed, at: Date(),
                                 digest: remoteDigest, snapshot: after))
            return .success(preview)
        }

        let responseJSON = Self.canonicalJSONString(response)
        let nextState = Self.state(in: response)
        if let nextState, !Self.canTransition(from: activeSnapshot.state, to: nextState) {
            return .failure(.init(
                verdict: "UNKNOWN_INVALID_JOB_TRANSITION",
                why: "\(activeSnapshot.state?.rawValue ?? "EMPTY") から \(nextState.rawValue) へは遷移できません",
                howToClose: "不足している前段の証拠またはartifactを先に作成してください"))
        }

        let artifactDigest = Self.artifactDigest(in: response)
        if let nextState, nextState != activeSnapshot.state, artifactDigest == nil {
            return .failure(.init(
                verdict: "UNKNOWN_JOB_EVIDENCE_REQUIRED",
                why: "状態遷移 \(nextState.rawValue) にartifact digestがありません",
                howToClose: "engine responseへevidence_digestまたはartifact digestを含めてください"))
        }

        let after = GarmentJobSnapshot(
            state: nextState ?? activeSnapshot.state,
            artifactDigest: artifactDigest ?? activeSnapshot.artifactDigest,
            resultJSON: responseJSON,
            mesh: Self.mesh(in: response) ?? activeSnapshot.mesh)
        let engineAddresses = Self.resultDictionary(in: response)
            .flatMap { Self.stringArray($0["changed_addresses"]) } ?? []
        let addresses = engineAddresses.isEmpty
            ? Self.changedAddresses(before: activeSnapshot, after: after)
            : engineAddresses
        let engineValidations = Self.resultDictionary(in: response)
            .map { Self.validationVerdicts($0["validation_results"]) } ?? []
        let validations = Self.validationVerdicts(response["validation_results"])
            + engineValidations + ["ANSWER"]
        // The persisted Python job is authoritative. Reuse its preview digest
        // so the button approves the same immutable object across the MCP
        // boundary; only fall back for old engines that do not return one.
        let digest = Self.previewDigest(in: response) ?? Self.digest(strings: [
            command.jsonString ?? "", activeSnapshot.resultJSON,
            after.resultJSON, addresses.joined(separator: "|")])
        let preview = GarmentPreview(
            schema: GarmentPreview.schema, jobID: jobID,
            previewID: "local-\(digest.prefix(24))", command: command,
            before: activeSnapshot, after: after, changedAddresses: addresses,
            validationResults: Array(Set(validations)).sorted(), digest: digest)
        pendingPreview = preview
        history.append(Event(kind: .previewed, at: Date(), digest: digest, snapshot: after))
        return .success(preview)
    }

    func mirrorAnswer(_ response: [String: Any]) -> GarmentAnswerEnvelope {
        let provenance = response["provenance"] as? String ?? "DETERMINISTIC_ENGINE"
        let forbidden = Self.stringArray(response["forbidden_claims"])
        let rawFacts = Self.stringArray(response["facts"]).isEmpty
            ? Self.fallbackFacts(response) : Self.stringArray(response["facts"])
        let isModelProposal = provenance.uppercased().contains("MODEL_PROPOSAL")
        let safeFacts = isModelProposal
            ? [] : rawFacts.filter { !forbidden.contains($0) }
        var suggestions = Self.stringArray(response["allowed_suggestions"])
        if suggestions.isEmpty,
           let close = Self.optionalString(response["how_to_close"]) {
            suggestions = [close]
        }
        if isModelProposal { suggestions = rawFacts + suggestions }
        let answer = GarmentAnswerEnvelope(
            verdict: isModelProposal ? "PROPOSED" :
                (response["verdict"] as? String ?? "UNKNOWN_ENGINE_RESPONSE"),
            facts: safeFacts,
            allowedSuggestions: suggestions,
            forbiddenClaims: forbidden,
            artifacts: Self.stringArray(response["artifacts"]),
            provenance: provenance)
        lastAnswer = answer
        return answer
    }

    func approve(digest: String) -> Result<GarmentJobSnapshot, GarmentCommandRefusal> {
        guard let preview = pendingPreview else {
            return .failure(.init(verdict: "UNKNOWN_NO_PENDING_PREVIEW",
                                  why: "承認待ちのプレビューがありません",
                                  howToClose: "先に変更命令を実行してください"))
        }
        guard preview.digest == digest else {
            return .failure(.init(verdict: "UNKNOWN_STALE_PREVIEW_DIGEST",
                                  why: "指定されたdigestは現在のプレビューと一致しません",
                                  howToClose: "最新のプレビューを確認して承認してください"))
        }
        activeSnapshot = preview.after
        committedSnapshots.append(preview.after)
        pendingPreview = nil
        history.append(Event(kind: .approved, at: Date(), digest: digest, snapshot: activeSnapshot))
        return .success(activeSnapshot)
    }

    func reject(digest: String) -> Result<GarmentJobSnapshot, GarmentCommandRefusal> {
        guard let preview = pendingPreview else {
            return .failure(.init(verdict: "UNKNOWN_NO_PENDING_PREVIEW",
                                  why: "却下するプレビューがありません",
                                  howToClose: "先に変更命令を実行してください"))
        }
        guard preview.digest == digest else {
            return .failure(.init(verdict: "UNKNOWN_STALE_PREVIEW_DIGEST",
                                  why: "指定されたdigestは現在のプレビューと一致しません",
                                  howToClose: "最新のプレビューを確認してください"))
        }
        pendingPreview = nil
        history.append(Event(kind: .rejected, at: Date(), digest: digest, snapshot: activeSnapshot))
        return .success(activeSnapshot)
    }

    func undo() -> Result<GarmentJobSnapshot, GarmentCommandRefusal> {
        guard committedSnapshots.count > 1 else {
            return .failure(.init(verdict: "UNKNOWN_NOTHING_TO_UNDO",
                                  why: "戻せる承認済み変更がありません",
                                  howToClose: "変更をプレビューし、承認してからUndoしてください"))
        }
        let removed = committedSnapshots.removeLast()
        activeSnapshot = committedSnapshots.last ?? .empty
        pendingPreview = nil
        history.append(Event(kind: .undo, at: Date(),
                             digest: removed.artifactDigest ?? "no-artifact",
                             snapshot: activeSnapshot))
        return .success(activeSnapshot)
    }

    private static func canTransition(from: State?, to: State) -> Bool {
        guard let from else { return to == .imageReceived }
        if from == to { return true }
        let allowed: [State: Set<State>] = [
            .imageReceived: [.regionsConfirmed, .geometryContested],
            .regionsConfirmed: [.geometryContested, .backCandidatesReady],
            .geometryContested: [.backCandidatesReady],
            .backCandidatesReady: [.structureApproved],
            .structureApproved: [.materialContested, .simulationReady],
            .materialContested: [.simulationReady],
            .simulationReady: [.shapeApproved],
            .shapeApproved: [.patternValidated],
            .patternValidated: [.sewingBlockedNoCorpus, .complete],
            .sewingBlockedNoCorpus: [.complete],
            .complete: [],
        ]
        return allowed[from]?.contains(to) == true
    }

    private static func state(in response: [String: Any]) -> State? {
        let candidates: [Any?] = [response["job_state"], response["state"],
                                  (response["job"] as? [String: Any])?["state"],
                                  (response["preview"] as? [String: Any])?["state"]]
        return candidates.compactMap { $0 as? String }.compactMap(State.init(rawValue:)).first
    }

    private static func snapshot(in raw: [String: Any]) -> GarmentJobSnapshot {
        let state = (raw["state"] as? String).flatMap(State.init(rawValue:))
        let artifacts = raw["artifacts"] as? [String: Any] ?? [:]
        let artifactDigest = artifacts.keys.sorted().compactMap { artifacts[$0] as? String }.first
        let data = raw["data"] as? [String: Any] ?? [:]
        return GarmentJobSnapshot(
            state: state, artifactDigest: artifactDigest,
            resultJSON: canonicalJSONString(data), mesh: mesh(in: data))
    }

    private static func artifactDigest(in response: [String: Any]) -> String? {
        if let value = response["evidence_digest"] as? String { return value }
        if let value = response["artifact_digest"] as? String { return value }
        if let artifact = response["artifact"] as? [String: Any],
           let value = artifact["digest"] as? String { return value }
        if let preview = response["preview"] as? [String: Any],
           let value = preview["digest"] as? String { return value }
        return nil
    }

    private static func previewDigest(in response: [String: Any]) -> String? {
        if let result = resultDictionary(in: response),
           result["schema"] as? String == GarmentPreview.schema,
           let digest = result["digest"] as? String { return digest }
        if response["schema"] as? String == GarmentPreview.schema,
           let digest = response["digest"] as? String { return digest }
        return nil
    }

    private static func resultDictionary(in response: [String: Any]) -> [String: Any]? {
        response["result"] as? [String: Any]
    }

    private static func mesh(in root: [String: Any]) -> GarmentMeshPreview? {
        let dictionaries = nestedDictionaries(root)
        for dictionary in dictionaries {
            if let vertices = vectors(dictionary["verts"] ?? dictionary["vertices"]),
               let faces = indices(dictionary["faces"]),
               GarmentMeshPreview(vertices: vertices, faces: faces).isRenderable {
                return GarmentMeshPreview(vertices: vertices, faces: faces)
            }
            if let lattice = dictionary["lattice"] as? [String: Any],
               let mesh = latticeMesh(lattice) { return mesh }
        }
        return nil
    }

    private static func latticeMesh(_ lattice: [String: Any]) -> GarmentMeshPreview? {
        guard let nodes = lattice["nodes"] as? [String: Any],
              let facesRaw = lattice["faces"] as? [[String: Any]] else { return nil }
        let ordered = nodes.compactMap { key, value -> (Int, [Double])? in
            guard let index = Int(key), let node = value as? [String: Any],
                  let position = vectors([node["position_m"] ?? node["position"]]).flatMap(\.first)
            else { return nil }
            return (index, position)
        }.sorted { $0.0 < $1.0 }
        guard ordered.enumerated().allSatisfy({ $0.offset == $0.element.0 }) else { return nil }
        let faces = facesRaw.compactMap { face in
            if let raw = face["nodes"] as? [String] { return raw.compactMap(Int.init) }
            return indices([face["vertices"] ?? []])?.first
        }
        let mesh = GarmentMeshPreview(vertices: ordered.map(\.1), faces: faces)
        return mesh.isRenderable ? mesh : nil
    }

    private static func nestedDictionaries(_ root: [String: Any]) -> [[String: Any]] {
        var result = [root]
        for key in ["preview", "after", "artifact", "result", "draft", "simulation",
                    "data", "snapshot", "simulation_input"] {
            if let child = root[key] as? [String: Any] { result.append(contentsOf: nestedDictionaries(child)) }
        }
        return result
    }

    private static func vectors(_ raw: Any?) -> [[Double]]? {
        guard let rows = raw as? [Any] else { return nil }
        let result = rows.compactMap { row -> [Double]? in
            guard let values = row as? [Any], values.count == 3 else { return nil }
            let doubles = values.compactMap { value -> Double? in
                if let value = value as? Double { return value }
                if let value = value as? Int { return Double(value) }
                if let value = value as? NSNumber { return value.doubleValue }
                return nil
            }
            return doubles.count == 3 ? doubles : nil
        }
        return result.count == rows.count ? result : nil
    }

    private static func indices(_ raw: Any?) -> [[Int]]? {
        guard let rows = raw as? [Any] else { return nil }
        let result = rows.compactMap { row -> [Int]? in
            guard let values = row as? [Any], values.count >= 3 else { return nil }
            let ints = values.compactMap { value -> Int? in
                if let value = value as? Int { return value }
                if let value = value as? NSNumber { return value.intValue }
                if let value = value as? String { return Int(value) }
                return nil
            }
            return ints.count == values.count ? ints : nil
        }
        return result.count == rows.count ? result : nil
    }

    private static func changedAddresses(before: GarmentJobSnapshot,
                                         after: GarmentJobSnapshot) -> [String] {
        var changes: [String] = []
        if before.state != after.state { changes.append("/job/state") }
        if before.artifactDigest != after.artifactDigest { changes.append("/artifacts/active") }
        if before.mesh != after.mesh { changes.append("/preview/mesh") }
        if before.resultJSON != after.resultJSON { changes.append("/engine/result") }
        return changes
    }

    private static func canonicalJSONString(_ value: Any) -> String {
        guard JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value,
                                                     options: [.sortedKeys, .withoutEscapingSlashes])
        else { return "{}" }
        return String(data: data, encoding: .utf8) ?? "{}"
    }

    private func commandDictionary(_ command: GarmentCommandIR) -> [String: Any] {
        guard let json = command.jsonString,
              let data = json.data(using: .utf8),
              let dictionary = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return [:] }
        return dictionary
    }

    private static func digest(strings: [String]) -> String {
        SHA256.hash(data: Data(strings.joined(separator: "\u{1f}").utf8))
            .map { String(format: "%02x", $0) }.joined()
    }

    private static func stringArray(_ raw: Any?) -> [String] {
        if let values = raw as? [String] { return values.filter { !$0.isEmpty } }
        if let values = raw as? [Any] { return values.compactMap { $0 as? String }.filter { !$0.isEmpty } }
        return []
    }

    private static func validationVerdicts(_ raw: Any?) -> [String] {
        if let strings = raw as? [String] { return strings }
        guard let values = raw as? [[String: Any]] else { return [] }
        return values.compactMap {
            ($0["verdict"] ?? $0["status"]) as? String
        }
    }

    private static func optionalString(_ raw: Any?) -> String? {
        guard let value = raw as? String, !value.isEmpty else { return nil }
        return value
    }

    private static func fallbackFacts(_ response: [String: Any]) -> [String] {
        if let what = optionalString(response["what"]) { return [what] }
        if let why = optionalString(response["why"]) { return [why] }
        return [response["verdict"] as? String ?? "UNKNOWN_ENGINE_RESPONSE"]
    }

    private func refusal(from response: [String: Any]) -> GarmentCommandRefusal {
        .init(verdict: response["verdict"] as? String ?? "UNKNOWN_ENGINE_RESPONSE",
              why: response["why"] as? String ?? "engineが型付き結果を返しませんでした",
              howToClose: response["how_to_close"] as? String ?? "MCP接続と入力契約を確認してください")
    }
}
