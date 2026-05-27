import Foundation
import MLXLLM

let url = URL(fileURLWithPath: "/Users/motonishikoudai/.cache/verantyx/mlx-patched/kofdai--talkie-1930-13b-it-mlx-8bit")
do {
    let config = try ModelConfiguration(directory: url)
    print("Success: \(config)")
} catch {
    print("Error: \(error)")
}
