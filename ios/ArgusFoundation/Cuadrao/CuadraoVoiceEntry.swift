import SwiftUI
import UIKit

/// UIKit recognizers make tap and press/drag/release mutually exclusive, including cancellation.
struct CuadraoVoiceEntry: UIViewRepresentable {
    let spanish: Bool
    let cancelArmed: Bool
    var composer = false
    let tap: () -> Void
    let beginHold: () -> Void
    let drag: (Double, Double) -> CuadraoVoiceMessagePreview.DragFeedback
    let release: () -> Void
    let cancel: () -> Void
    let accessibleRecord: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> VoiceTouchSurface {
        let view = VoiceTouchSurface()
        if composer {
            let label = UILabel()
            label.text = CuadraoCopy.text("copy.cuadraoVoiceEntry.678688ec61", spanish: spanish)
            label.font = .preferredFont(forTextStyle: .body)
            label.adjustsFontForContentSizeCategory = true
            label.textColor = .placeholderText; label.numberOfLines = 2
            label.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview(label)
            NSLayoutConstraint.activate([
                label.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 6),
                label.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -6),
                label.centerYAnchor.constraint(equalTo: view.centerYAnchor)
            ])
        } else {
            let image = UIImageView(image: UIImage(systemName: "waveform",
                withConfiguration: UIImage.SymbolConfiguration(pointSize: 19, weight: .semibold)))
            image.tintColor = UIColor(WelcomePalette.onAccent)
            image.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview(image)
            NSLayoutConstraint.activate([
                image.centerXAnchor.constraint(equalTo: view.centerXAnchor),
                image.centerYAnchor.constraint(equalTo: view.centerYAnchor)
            ])
        }
        let hold = UILongPressGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.hold(_:)))
        hold.minimumPressDuration = CuadraoVoiceMessagePreview.holdDelay
        hold.allowableMovement = 18
        let tap = UITapGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.tap(_:)))
        tap.require(toFail: hold)
        view.addGestureRecognizer(hold); view.addGestureRecognizer(tap)
        view.layer.cornerRadius = 22
        view.isAccessibilityElement = true; view.accessibilityTraits = .button
        view.accessibilityIdentifier = composer ? "chat-composer-entry" : "chat-voice-entry"
        return view
    }
    func updateUIView(_ view: VoiceTouchSurface, context: Context) {
        context.coordinator.parent = self
        view.backgroundColor = composer ? .clear : UIColor(cancelArmed ? .red : WelcomePalette.pine)
        view.accessibilityLabel = composer ? (CuadraoCopy.text("copy.cuadraoVoiceEntry.678688ec61", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoVoiceEntry.dd673e8d1c", spanish: spanish))
        view.accessibilityHint = composer ? (CuadraoCopy.text("copy.cuadraoVoiceEntry.e24d685b7b", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoVoiceEntry.a6a492770f", spanish: spanish))
        view.activate = tap
        view.accessibilityCustomActions = [UIAccessibilityCustomAction(
            name: CuadraoCopy.text("copy.cuadraoVoiceEntry.f988b56925", spanish: spanish),
            target: context.coordinator, selector: #selector(Coordinator.recordAccessibly))]
    }
    static func dismantleUIView(_ uiView: VoiceTouchSurface, coordinator: Coordinator) {
        if coordinator.holding { coordinator.parent.cancel() }
    }

    final class Coordinator: NSObject {
        var parent: CuadraoVoiceEntry
        var holding = false
        private var origin = CGPoint.zero
        init(_ parent: CuadraoVoiceEntry) { self.parent = parent }
        @objc func tap(_ gesture: UITapGestureRecognizer) {
            guard gesture.state == .ended, !holding else { return }
            parent.tap()
        }
        @objc func recordAccessibly() -> Bool { parent.accessibleRecord(); return true }
        @objc func hold(_ gesture: UILongPressGestureRecognizer) {
            switch gesture.state {
            case .began:
                holding = true
                origin = gesture.location(in: gesture.view?.window)
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
                parent.beginHold()
            case .changed:
                let point = gesture.location(in: gesture.view?.window)
                switch parent.drag(Double(origin.x - point.x), Double(origin.y - point.y)) {
                case .none: break
                case .cancelChanged: UISelectionFeedbackGenerator().selectionChanged()
                case .locked: UINotificationFeedbackGenerator().notificationOccurred(.success)
                }
            case .ended:
                holding = false; parent.release()
            case .cancelled, .failed:
                if holding { parent.cancel() }
                holding = false
            default: break
            }
        }
    }
}

final class VoiceTouchSurface: UIView {
    var activate: (() -> Void)?
    override func accessibilityActivate() -> Bool { activate?(); return true }
}
