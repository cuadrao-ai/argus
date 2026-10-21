import SwiftUI
import UIKit

/// The one input for a typed percentage: decimal keypad, a "%" suffix and its own message under the field.
/// The parent reads the accepted value through PercentInput; this view never changes the text it was given.
struct PercentField: View {
    let title: String
    @Binding var text: String
    let bounds: PercentInput.Bounds
    let spanish: Bool
    var identifier: String
    var placeholder = "0"

    private var problem: PercentInput.Problem? { PercentInput.problem(text, bounds) }
    private var message: String? { problem.map { PercentInput.message($0, bounds, spanish: spanish) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(title)
                TextField(placeholder, text: $text).keyboardType(.decimalPad).multilineTextAlignment(.trailing)
                    .accessibilityLabel(title + " %")
                    .accessibilityHint(message ?? "")
                    .accessibilityIdentifier(identifier)
                Text(verbatim: "%").foregroundStyle(.secondary).accessibilityHidden(true)
            }
            if let message {
                Text(message).font(CuadraoTypography.caption).foregroundStyle(.red)
                    .accessibilityIdentifier(identifier + ".error")
            }
        }
        .onChange(of: message) { _, next in
            if let next { UIAccessibility.post(notification: .announcement, argument: next) }
        }
    }
}
