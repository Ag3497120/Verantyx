import Foundation

// Vector index for the audit screen — jgen's own encoder, ranking gaps.
//
// Two questions the audit screen could not answer without vectors, both
// asked by a human deciding whether to approve:
//
//   * "This document just arrived. WHICH of the pending gaps does it
//     actually resolve?" — embed the document, embed every pending
//     subject, rank by cosine. A fetch that resolves three requests at
//     once is worth approving before one that resolves none.
//   * "Is this gap really missing, or is it a phrasing of something the
//     store already holds?" — embed the subject against held cores. 返済
//     landing next to 弁済 is a naming variant, not a hole, and
//     approving an article for it thickens a duplicate.
//
// Embedding comes from JGEN itself (`JCrossChatManager.encodeText` — the
// final hidden state, the same "thought vector" the rest of the Lab uses).
// When no model is loaded the index falls back to deterministic character
// n-grams and SAYS SO on every result: a similarity number whose basis is
// unknown is worse than none, and the two bases rank differently — surface
// overlap is not meaning.
//
// The index is persisted, because embedding 2,000 gap subjects through a
// 4B model is minutes of work that must not repeat every launch.

struct VectorHit: Identifiable {
    var id: String { subject }
    let subject: String
    let score: Float
}

enum EmbedBasis: String, Codable {
    case jgen          // JGEN encodeText — meaning-bearing
    case ngram         // deterministic character n-grams — surface only

    var label: String {
        switch self {
        case .jgen:  return "jgen"
        case .ngram: return "n-gram (surface)"
        }
    }
}

actor AuditVectorIndex {
    static let shared = AuditVectorIndex()

    private var vectors: [String: [Float]] = [:]
    private var basis: EmbedBasis = .ngram
    private var dirty = false

    // MARK: Persistence

    private struct Payload: Codable {
        var basis: EmbedBasis
        var vectors: [String: [Float]]
    }

    private static var url: URL {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Verantyx/audit-vectors",
                                    isDirectory: true)
        try? FileManager.default.createDirectory(at: dir,
                                                 withIntermediateDirectories: true)
        return dir.appendingPathComponent("index.json")
    }

    func load() {
        guard let d = try? Data(contentsOf: Self.url),
              let p = try? JSONDecoder().decode(Payload.self, from: d)
        else { return }
        // A stored n-gram index must not be silently reused once a model is
        // available: the two bases are different spaces and mixing them
        // would compare a meaning vector to a spelling vector.
        basis = p.basis
        vectors = p.vectors
    }

    func save() {
        guard dirty else { return }
        if let d = try? JSONEncoder().encode(Payload(basis: basis,
                                                     vectors: vectors)) {
            try? d.write(to: Self.url, options: .atomic)
            dirty = false
        }
    }

    func currentBasis() -> EmbedBasis { basis }
    func count() -> Int { vectors.count }

    /// Drop everything when the basis changes — see `load`.
    func reset(to newBasis: EmbedBasis) {
        if basis != newBasis {
            vectors.removeAll()
            basis = newBasis
            dirty = true
        }
    }

    // MARK: Embedding

    /// Deterministic character-trigram vector. Not meaning — spelling. Used
    /// only when JGEN is not loaded, and always reported as such.
    nonisolated static func ngramVector(_ text: String, dim: Int = 256) -> [Float] {
        var v = [Float](repeating: 0, count: dim)
        let chars = Array(text)
        guard !chars.isEmpty else { return v }
        for n in 1...min(3, chars.count) {
            for i in 0...(chars.count - n) {
                let gram = String(chars[i..<(i + n)])
                var h: UInt64 = 1469598103934665603
                for b in gram.utf8 {
                    h = (h ^ UInt64(b)) &* 1099511628211
                }
                v[Int(h % UInt64(dim))] += 1
            }
        }
        let norm = sqrt(v.reduce(0) { $0 + $1 * $1 })
        return norm > 0 ? v.map { $0 / norm } : v
    }

    /// Embed through JGEN when a model is loaded, else n-grams. Returns the
    /// basis alongside so callers can label what they are showing.
    nonisolated static func embed(_ text: String,
                                  preferJGen: Bool) async -> ([Float], EmbedBasis) {
        if preferJGen {
            let mgr = JCrossChatManager.shared
            if let v = try? await mgr.encodeText(text), !v.isEmpty {
                return (v, .jgen)
            }
        }
        return (ngramVector(text), .ngram)
    }

    // MARK: Index building and query

    /// Embed subjects that are not indexed yet. Returns how many were added.
    @discardableResult
    func index(subjects: [String], preferJGen: Bool) async -> Int {
        var added = 0
        for s in subjects where vectors[s] == nil {
            let (v, b) = await Self.embed(s, preferJGen: preferJGen)
            if b != basis {
                reset(to: b)
            }
            vectors[s] = v
            dirty = true
            added += 1
        }
        save()
        return added
    }

    /// Rank indexed subjects by similarity to a document or phrase.
    func nearest(to text: String, limit: Int = 8,
                 preferJGen: Bool) async -> (hits: [VectorHit], basis: EmbedBasis) {
        let (q, b) = await Self.embed(text, preferJGen: preferJGen)
        guard b == basis else {
            // Query and index in different spaces — refuse rather than
            // return numbers that compare spelling to meaning.
            return ([], b)
        }
        let hits = vectors.map { VectorHit(subject: $0.key,
                                           score: DivergenceExchange.cosine(q, $0.value)) }
            .filter { $0.score > 0 }
            .sorted { ($0.score, $1.subject) > ($1.score, $0.subject) }
            .prefix(limit)
        return (Array(hits), basis)
    }
}
