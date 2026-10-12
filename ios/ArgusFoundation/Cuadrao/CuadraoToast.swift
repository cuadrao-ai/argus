import SwiftUI

/// What a toast says and the one action it offers. The id restarts the timer for a new message.
struct CuadraoToastMessage: Identifiable, Equatable {
    let id = UUID()
    var text: String
    var actionTitle: String?
    var actionIdentifier = "toast.action"
    var action: (() -> Void)?

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.id == rhs.id }
}

/// One line, an optional action, five seconds. VoiceOver hears the line when it appears and gets more time.
struct CuadraoToast: View {
    let text: String
    var actionTitle: String?
    var actionIdentifier = "toast.action"
    var action: (() -> Void)?
    let spanish: Bool
    var closeIdentifier = "toast.close"
    /// A new token restarts the timer for a new message with the same words.
    var token: AnyHashable?
    let close: () -> Void

    static func autoDismissSeconds(voiceOver: Bool) -> Double { voiceOver ? 10 : 5 }

    /// Journeys that enumerate every button cannot cope with one that leaves mid-query, so they ask the notice to stay.
    private static var staysForUITests: Bool {
        #if DEBUG
        ProcessInfo.processInfo.arguments.contains("--toasts-stay")
        #else
        false
        #endif
    }

    var body: some View {
        HStack {
            Text(text)
            Spacer()
            if let actionTitle, let action {
                Button(actionTitle, action: action).frame(minHeight: 44).accessibilityIdentifier(actionIdentifier)
            }
            Button(action: close) { Image(systemName: "xmark").frame(width: 44, height: 44) }
                .accessibilityLabel(spanish ? "Cerrar" : "Close")
                .accessibilityIdentifier(closeIdentifier)
        }.font(.subheadline).padding(.leading, 20).padding(.trailing, 6)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18))
            .padding(.horizontal, 20).padding(.bottom, 90)
            .task(id: token ?? AnyHashable(text)) {
                // Keyed like the timer, so a second message in the same view is announced too.
                UIAccessibility.post(notification: .announcement, argument: text)
                guard !Self.staysForUITests else { return }
                let seconds = Self.autoDismissSeconds(voiceOver: UIAccessibility.isVoiceOverRunning)
                try? await Task.sleep(for: .seconds(seconds))
                if !Task.isCancelled { close() }
            }
    }
}

extension View {
    /// Shows the message at the bottom of this view and clears the binding when it closes.
    func cuadraoToast(_ message: Binding<CuadraoToastMessage?>, spanish: Bool) -> some View {
        modifier(CuadraoToastHost(message: message, spanish: spanish))
    }
}

private struct CuadraoToastHost: ViewModifier {
    @Binding var message: CuadraoToastMessage?
    let spanish: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content.overlay(alignment: .bottom) {
            if let current = message {
                CuadraoToast(text: current.text, actionTitle: current.actionTitle, actionIdentifier: current.actionIdentifier,
                             action: current.action, spanish: spanish, token: current.id) { message = nil }
                    .transition(reduceMotion ? .opacity : .move(edge: .bottom).combined(with: .opacity))
            }
        }.animation(reduceMotion ? nil : .snappy(duration: 0.3), value: message?.id)
    }
}
