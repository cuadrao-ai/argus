import SwiftUI
import UIKit

/// UIKit arbitrates direction before recognition, so vertical drags remain page scrolls.
struct HorizontalScrubber: UIViewRepresentable {
    var event: (UIGestureRecognizer.State, CGFloat) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(event: event) }
    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        view.backgroundColor = .clear
        view.accessibilityIdentifier = "scrubSurface"
        view.isAccessibilityElement = false
        let pan = UIPanGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.pan(_:)))
        pan.delegate = context.coordinator
        view.addGestureRecognizer(pan)
        return view
    }
    func updateUIView(_ view: UIView, context: Context) { context.coordinator.event = event }
    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var event: (UIGestureRecognizer.State, CGFloat) -> Void
        init(event: @escaping (UIGestureRecognizer.State, CGFloat) -> Void) { self.event = event }
        func gestureRecognizerShouldBegin(_ gesture: UIGestureRecognizer) -> Bool {
            guard let pan = gesture as? UIPanGestureRecognizer else { return false }
            let velocity = pan.velocity(in: pan.view)
            return abs(velocity.x) > abs(velocity.y)
        }
        @objc func pan(_ pan: UIPanGestureRecognizer) {
            event(pan.state, pan.location(in: pan.view).x)
            // Standalone UI-test hook: UIKit itself sends .cancelled while a real drag is active.
            if pan.state == .changed && ProcessInfo.processInfo.environment["CHART_CANCEL_DRAG"] == "1" {
                pan.isEnabled = false
                DispatchQueue.main.async { pan.isEnabled = true }
            }
        }
    }
}
