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
        /// A rear-to-front edge exists only when a person explicitly records
        /// it in the RegionPicker.  An empty array is the legacy single-region
        /// contract and carries no layer observation.
        let layerRelations: [[String: Any]]
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

        let regionIDs = regions.compactMap { row -> String? in
            guard let value = row["region_id"] as? String,
                  !value.isEmpty else { return nil }
            return value
        }
        guard regionIDs.count == regions.count,
              Set(regionIDs).count == regionIDs.count else { return nil }
        if regions.count > 1 {
            guard regions.allSatisfy({ row in
                guard let outline = row["outline"] as? [[Double]] else {
                    return false
                }
                return outline.count >= 3
            }) else { return nil }
        }

        let layerRelations: [[String: Any]]
        if let rawRelations = outline["human_layer_relations"] {
            guard let relations = rawRelations as? [[String: Any]],
                  validateLayerRelations(relations,
                                         regionIDs: Set(regionIDs)) else {
                return nil
            }
            layerRelations = relations
        } else {
            // Backwards compatibility: one confirmed region predates the
            // explicit layer contract and observes no front/back ordering.
            layerRelations = []
        }
        return Evidence(regions: regions, seeds: seeds,
                        layerRelations: layerRelations)
    }

    private static func validateLayerRelations(
        _ relations: [[String: Any]], regionIDs: Set<String>
    ) -> Bool {
        var relationIDs = Set<String>()
        var directedPairs = Set<String>()
        var behindByFront: [String: String] = [:]

        for row in relations {
            guard let relationID = row["relation_id"] as? String,
                  !relationID.isEmpty,
                  relationIDs.insert(relationID).inserted,
                  (row["kind"] as? String)?.uppercased() == "LAYER",
                  (row["state"] as? String)?.uppercased() == "OBSERVED",
                  (row["source"] as? String)?.uppercased()
                    == "HUMAN_EXPLICIT_FRONT_ORDER",
                  let behind = row["behind_region_id"] as? String,
                  let front = row["front_region_id"] as? String,
                  behind != front,
                  regionIDs.contains(behind), regionIDs.contains(front),
                  directedPairs.insert("\(behind)->\(front)").inserted,
                  behindByFront[front] == nil else { return false }
            behindByFront[front] = behind
        }

        // Each front region has at most one directly observed predecessor.
        // That makes the current second-skin ownership ABI a forest while
        // still allowing several independent layer stacks in one image.
        for start in regionIDs {
            var seen = Set<String>()
            var cursor: String? = start
            while let current = cursor {
                guard seen.insert(current).inserted else { return false }
                cursor = behindByFront[current]
            }
        }
        return true
    }
}
