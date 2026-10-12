import SwiftUI

/// What a person sees after a save, an archive or a delete: a success haptic, a short notice and, for a new or
/// changed row, a brief highlight. A host view owns one and puts it on the environment.
@MainActor
final class CuadraoSaveResult: ObservableObject {
    @Published var toast: CuadraoToastMessage?
    @Published private(set) var highlighted: UUID?
    private var clearing: Task<Void, Never>?

    /// A save that landed. `action` is "Ver" for a create, or Undo where an authorized delete exists.
    func saved(_ text: String, highlight id: UUID? = nil, actionTitle: String? = nil, actionIdentifier: String = "toast.action",
               action: (() -> Void)? = nil) {
        CuadraoHaptics.success()
        show(text, actionTitle: actionTitle, actionIdentifier: actionIdentifier, action: action)
        highlight(id)
    }

    /// A delete or archive the person confirmed, with its Undo.
    func removed(_ text: String, undoTitle: String, undoIdentifier: String, undo: @escaping () -> Void) {
        CuadraoHaptics.impact()
        show(text, actionTitle: undoTitle, actionIdentifier: undoIdentifier) { [weak self] in undo(); self?.toast = nil }
    }

    func failed() { CuadraoHaptics.warning() }

    func dismiss() { toast = nil }

    private func show(_ text: String, actionTitle: String?, actionIdentifier: String, action: (() -> Void)?) {
        toast = CuadraoToastMessage(text: text, actionTitle: actionTitle, actionIdentifier: actionIdentifier, action: action)
    }

    private func highlight(_ id: UUID?) {
        clearing?.cancel()
        highlighted = id
        guard id != nil else { return }
        clearing = Task {
            try? await Task.sleep(for: .seconds(1.8))
            if !Task.isCancelled { highlighted = nil }
        }
    }
}

private struct CuadraoHighlightedRowKey: EnvironmentKey { static let defaultValue: UUID? = nil }

extension EnvironmentValues {
    var cuadraoHighlightedRow: UUID? {
        get { self[CuadraoHighlightedRowKey.self] }
        set { self[CuadraoHighlightedRowKey.self] = newValue }
    }
}

extension View {
    /// Shows the result's notice at the bottom and tells rows which one just changed.
    func cuadraoSaveResult(_ result: CuadraoSaveResult, spanish: Bool) -> some View {
        modifier(CuadraoSaveResultHost(result: result, spanish: spanish))
    }

    /// A short soft tint behind the row that just saved. Reduce Motion shows it without the fade.
    func cuadraoRowHighlight(_ id: UUID) -> some View { modifier(CuadraoRowHighlight(id: id)) }
}

private struct CuadraoSaveResultHost: ViewModifier {
    @ObservedObject var result: CuadraoSaveResult
    let spanish: Bool

    func body(content: Content) -> some View {
        content
            .cuadraoToast($result.toast, spanish: spanish)
            .environment(\.cuadraoHighlightedRow, result.highlighted)
    }
}

private struct CuadraoRowHighlight: ViewModifier {
    let id: UUID
    @Environment(\.cuadraoHighlightedRow) private var highlighted
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            .background(RoundedRectangle(cornerRadius: 12).fill(WelcomePalette.pine.opacity(highlighted == id ? 0.14 : 0)).padding(.horizontal, -8))
            .animation(reduceMotion ? nil : .easeOut(duration: 0.6), value: highlighted == id)
    }
}
