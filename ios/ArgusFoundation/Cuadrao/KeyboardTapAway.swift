import SwiftUI
import UIKit

/// Tapping anywhere that is not a text input closes the keyboard, in every sheet and screen. This is the one place
/// that does it, so no screen needs a Done button above the keyboard. It never cancels or delays the tap itself, and
/// it leaves the keyboard alone when the tap handed focus to another field.
struct KeyboardTapAway: UIViewRepresentable {
    func makeUIView(context: Context) -> InstallerView { InstallerView() }
    func updateUIView(_ view: InstallerView, context: Context) {}

    final class InstallerView: UIView {
        private let recognizer = UITapGestureRecognizer()
        private let delegate = TapDelegate()

        override init(frame: CGRect) {
            super.init(frame: frame)
            isUserInteractionEnabled = false
            recognizer.cancelsTouchesInView = false
            recognizer.delaysTouchesBegan = false
            recognizer.delaysTouchesEnded = false
            recognizer.delegate = delegate
            recognizer.addTarget(delegate, action: #selector(TapDelegate.tapped))
        }
        required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

        override func didMoveToWindow() {
            super.didMoveToWindow()
            guard let window else { return }
            if recognizer.view !== window { window.addGestureRecognizer(recognizer) }
        }
    }

    final class TapDelegate: NSObject, UIGestureRecognizerDelegate {
        private weak var editingAtTouch: UIResponder?

        @objc func tapped() {
            guard let editing = editingAtTouch else { return }
            // Let the tap finish first: a row that forwards the tap to its field moves focus, and then nothing closes.
            DispatchQueue.main.async {
                guard UIResponder.currentFirstResponder === editing else { return }
                editing.resignFirstResponder()
            }
        }

        func gestureRecognizer(_ recognizer: UIGestureRecognizer, shouldReceive touch: UITouch) -> Bool {
            editingAtTouch = nil
            var view = touch.view
            while let current = view {
                if current is UITextField || current is UITextView || current is UISearchBar { return false }
                view = current.superview
            }
            guard let editing = UIResponder.currentFirstResponder, editing is UIKeyInput else { return false }
            // A tap on the field, or on a control right beside it (a sign or currency button), is not a tap away.
            if let field = editing as? UIView, let window = field.window {
                let area = field.convert(field.bounds, to: window).insetBy(dx: -64, dy: -16)
                if area.contains(touch.location(in: window)) { return false }
            }
            editingAtTouch = editing
            return true
        }

        func gestureRecognizer(_ recognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool { true }
    }
}

extension UIResponder {
    private static weak var found: UIResponder?

    /// The view that currently has the keyboard, if any.
    static var currentFirstResponder: UIResponder? {
        found = nil
        UIApplication.shared.sendAction(#selector(UIResponder.reportAsFirstResponder), to: nil, from: nil, for: nil)
        return found
    }

    @objc private func reportAsFirstResponder() { UIResponder.found = self }
}
