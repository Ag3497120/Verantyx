import SwiftUI

// MARK: - ToastView
// A lightweight, auto-dismissing toast notification.
// Replaces noisy system/log messages in chat for model-load events.

struct ToastView: View {
    let message: String
    let icon: String
    let color: Color

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(color)

            Text(message)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Color.white)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color(red: 0.14, green: 0.14, blue: 0.18))
                .shadow(color: Color.black.opacity(0.45), radius: 12, x: 0, y: 4)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .strokeBorder(color.opacity(0.35), lineWidth: 0.8)
        )
    }
}

// MARK: - ToastManager

@MainActor
final class ToastManager: ObservableObject {
    static let shared = ToastManager()

    @Published var currentToast: ToastPayload?

    struct ToastPayload: Identifiable {
        let id = UUID()
        let message: String
        let icon: String
        let color: Color
        let duration: Double
    }

    func show(_ message: String, icon: String = "checkmark.circle.fill", color: Color = .green, duration: Double = 2.5) {
        currentToast = ToastPayload(message: message, icon: icon, color: color, duration: duration)
        Task {
            try? await Task.sleep(nanoseconds: UInt64(duration * 1_000_000_000))
            withAnimation(.easeOut(duration: 0.25)) {
                if currentToast?.message == message {
                    currentToast = nil
                }
            }
        }
    }
}

// MARK: - ToastOverlay modifier

extension View {
    func toastOverlay() -> some View {
        self.overlay(alignment: .top) {
            ToastContainerView()
        }
    }
}

struct ToastContainerView: View {
    @ObservedObject private var manager = ToastManager.shared

    var body: some View {
        Group {
            if let toast = manager.currentToast {
                ToastView(message: toast.message, icon: toast.icon, color: toast.color)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .padding(.top, 8)
                    .zIndex(999)
            }
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.75), value: manager.currentToast?.id)
    }
}
