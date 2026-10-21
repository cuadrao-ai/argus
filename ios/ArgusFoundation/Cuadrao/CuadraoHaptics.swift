import UIKit

/// One owner for haptics. Success on a saved change, warning on an error, selection on a chip or tab,
/// impact on a delete the person confirmed. Nothing on scroll.
@MainActor
enum CuadraoHaptics {
    static func success() { UINotificationFeedbackGenerator().notificationOccurred(.success) }
    static func warning() { UINotificationFeedbackGenerator().notificationOccurred(.warning) }
    static func selection() { UISelectionFeedbackGenerator().selectionChanged() }
    static func impact() { UIImpactFeedbackGenerator(style: .medium).impactOccurred() }
}
