// swift-tools-version: 5.9
import PackageDescription

/// verantyx-cli — research / repro runtime for Verantyx.
///
/// Architecture (dual-track; GUI stays intact):
///   vera-core     — state, Gap, evidence, skills, safety event surface
///   verantyx-cli  — formal research/repro interface (`vera run`)
///   verantyx-gui  — Verantyx IDE (unchanged this pass); later visualizes CLI/core events
///
/// Event flow: GUI|CLI → task → Core Runtime → structured events → JSONL / stdout
///             (GUI may keep AppState paths today; CLI is the reproducible log source of truth.)
let package = Package(
    name: "verantyx-cli",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "VeraCore", targets: ["VeraCore"]),
        .executable(name: "vera", targets: ["verantyx-cli"]),
    ],
    targets: [
        .target(
            name: "VeraCore",
            path: "Sources/VeraCore"
        ),
        .executableTarget(
            name: "verantyx-cli",
            dependencies: ["VeraCore"],
            path: "Sources/verantyx-cli"
        ),
        .testTarget(
            name: "VeraCoreTests",
            dependencies: ["VeraCore"],
            path: "Tests/VeraCoreTests"
        ),
    ]
)
