import Foundation

/// One reversible change a screen hands to the shell, which shows the single bottom Undo notice on whatever tab the person is on.
struct GuestUndoOffer {
    let text: String
    let identifier: String
    let restore: () -> Void
}
