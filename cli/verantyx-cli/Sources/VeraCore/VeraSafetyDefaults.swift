import Foundation

/// Memory / sense safety defaults mirrored from IDE `PromptBudget` +
/// `CouncilSettingsStore.vectorOnlySense` / `JGenGPUSafety`.
/// CLI defaults to the same safe posture (vector-only sense, prompt caps).
public enum VeraSafetyDefaults {
    public static let vectorOnlySense = true
    public static let maxQuestionChars = 1_600
    public static let maxEncodeChars = 1_200
    public static let maxEncodeTokens = 768
    public static let maxMemoryPrefixChars = 2_400
    public static let maxPayloadChars = 50_000

    public static var policyDetail: [String: String] {
        [
            "vector_only_sense": vectorOnlySense ? "true" : "false",
            "max_question_chars": "\(maxQuestionChars)",
            "max_encode_chars": "\(maxEncodeChars)",
            "max_encode_tokens": "\(maxEncodeTokens)",
            "max_memory_prefix_chars": "\(maxMemoryPrefixChars)",
            "max_payload_chars": "\(maxPayloadChars)",
            "gpu_safety": "prefer_cpu_on_low_ram; pause_capture_during_jgen",
            "sense_mode": "ax_map_preferred; no_model_pixel_inject",
        ]
    }
}
