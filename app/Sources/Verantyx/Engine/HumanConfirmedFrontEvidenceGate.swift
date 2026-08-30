import Foundation

/// Deterministic boundary between an automatic RegionPicker proposal and a
/// front target explicitly confirmed by a person.
///
/// This gate accepts only evidence exported from the same source image after
/// 3–5 human clothing seeds. It deliberately says nothing about the rear,
/// depth, material, measurements, or sewing construction.
enum HumanConfirmedFrontEvidenceGate {
    struct Evidence {
        let regions: [[String: Any]]
        let seeds: [[String: Any]]
    }

    static func humanConfirmedFrontEvidence(
        _ outline: [String: Any],
        activeImagePath: String?,
        submittedImagePath: String
    ) -> Evidence? {
        guard let activeImagePath,
              URL(fileURLWithPath: activeImagePath).standardizedFileURL.path
                == URL(fileURLWithPath: submittedImagePath)
                    .standardizedFileURL.path,
              let polygon = outline["outline"] as? [[Double]],
              polygon.count >= 3,
              let regions = outline["regions"] as? [[String: Any]],
              !regions.isEmpty,
              regions.allSatisfy({ row in
                  (row["state"] as? String)?.uppercased() == "OBSERVED"
                    && (row["semantic_label"] as? String)?.lowercased()
                        == "clothing"
              }),
              let provenance = outline["provenance"] as? [String: Any],
              (provenance["kind"] as? String)?.uppercased() == "OBSERVED",
              let seeds = provenance["human_seeds"] as? [[String: Any]],
              (3...5).contains(seeds.count),
              seeds.allSatisfy({
                  ($0["kind"] as? String)?.uppercased() == "OBSERVED"
              }),
              seeds.contains(where: {
                  ($0["label"] as? String)?.lowercased() == "clothing"
              }) else { return nil }
        return Evidence(regions: regions, seeds: seeds)
    }
}
