import SwiftUI
import UIKit

/// Native editable text keeps selection and the caret while adding grouping separators.
struct CanvasDecimalInput: UIViewRepresentable {
    @Binding var raw: String
    @Binding var error: String
    let currency: String
    let spanish: Bool
    var allowNegative = false
    var identifier = "cuadrao-amount"
    var title: String? = nil
    var size: CuadraoTypography.MoneySize = .prominent
    var alignment: NSTextAlignment = .right
    var autofocus = false
    var onFocus: (Bool) -> Void = { _ in }
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.cuadraoCurrencyRules) private var rules

    private var contentSizeCategory: UIContentSizeCategory {
        switch dynamicTypeSize {
        case .xSmall: return .extraSmall
        case .small: return .small
        case .medium: return .medium
        case .large: return .large
        case .xLarge: return .extraLarge
        case .xxLarge: return .extraExtraLarge
        case .xxxLarge: return .extraExtraExtraLarge
        case .accessibility1: return .accessibilityMedium
        case .accessibility2: return .accessibilityLarge
        case .accessibility3: return .accessibilityExtraLarge
        case .accessibility4: return .accessibilityExtraExtraLarge
        case .accessibility5: return .accessibilityExtraExtraExtraLarge
        @unknown default: return .large
        }
    }
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> UITextField {
        let field = UITextField()
        field.delegate = context.coordinator
        field.keyboardType = .decimalPad
        field.textAlignment = alignment
        field.font = CuadraoTypography.moneyFont(size, category: field.traitCollection.preferredContentSizeCategory)
        field.adjustsFontForContentSizeCategory = true
        field.adjustsFontSizeToFitWidth = true; field.minimumFontSize = 17
        field.backgroundColor = .clear
        field.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        context.coordinator.field = field
        if autofocus { DispatchQueue.main.async { field.becomeFirstResponder() } }
        return field
    }
    func updateUIView(_ field: UITextField, context: Context) {
        context.coordinator.parent = self
        field.accessibilityIdentifier = identifier
        field.font = CuadraoTypography.moneyFont(size, category: contentSizeCategory)
        field.textAlignment = alignment
        if context.coordinator.pending == 0 && raw != context.coordinator.raw {
            context.coordinator.raw = raw
            if (field.text ?? "").replacingOccurrences(of: ",", with: "") != raw { field.text = Coordinator.group(raw) }
        }
        field.placeholder = rules.format(0, currency)
        field.accessibilityLabel = title ?? (CuadraoCopy.text("copy.canvasDecimalInput.69f09a95c5", spanish: spanish))
        field.textColor = (Decimal(string: raw) ?? 0) > 0
            ? UIColor(WelcomePalette.moneyInput) : .secondaryLabel
    }
    final class Coordinator: NSObject, UITextFieldDelegate {
        var parent: CanvasDecimalInput
        weak var field: UITextField?
        /// The field's text without grouping; the binding catches up through `commit`.
        var raw = ""
        /// While writes are in flight the binding can lag the field, so updates must not rewrite it.
        var pending = 0
        init(_ parent: CanvasDecimalInput) { self.parent = parent }
        func textField(_ textField: UITextField, shouldChangeCharactersIn range: NSRange, replacementString string: String) -> Bool {
            let old = textField.text ?? ""
            guard let r = Range(range, in: old) else { return false }
            var proposed = old.replacingCharacters(in: r, with: string)
            var logical = old[..<r.lowerBound].filter { $0 != "," }.count + string.filter { $0 != "," }.count
            if string.isEmpty, old[r] == ",", range.location > 0 {
                let deletion = NSRange(location: range.location - 1, length: range.length + 1)
                if let deletionRange = Range(deletion, in: old) {
                    proposed = old.replacingCharacters(in: deletionRange, with: ""); logical -= 1
                }
            }
            if string.count > 1 && string.contains(",") &&
                string.range(of: #"^-?(?:[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]*)?$"#, options: .regularExpression) == nil {
                commit(error: CuadraoCopy.text("copy.canvasDecimalInput.ae26ecf511", spanish: parent.spanish)); return false
            }
            var normalized = proposed.replacingOccurrences(of: ",", with: "")
            let pattern = parent.allowNegative ? #"^-?[0-9]*(?:\.[0-9]*)?$"# : #"^[0-9]*(?:\.[0-9]*)?$"#
            guard normalized.range(of: pattern, options: .regularExpression) != nil else {
                commit(error: CuadraoCopy.text("copy.canvasDecimalInput.a1483982c8", spanish: parent.spanish)); return false
            }
            if normalized.hasPrefix(".") { normalized = "0" + normalized; logical += 1 }
            let fraction = normalized.split(separator: ".", omittingEmptySubsequences: false).dropFirst().first?.count ?? 0
            guard fraction <= parent.rules.digits(parent.currency) else {
                commit(error: CuadraoCopy.text("copy.canvasDecimalInput.fb945d8969", spanish: parent.spanish, String(describing: parent.currency))); return false
            }
            guard abs(Decimal(string: normalized) ?? 0) <= parent.rules.maximum(parent.currency), normalized.count <= 24 else {
                commit(error: parent.rules.maximumMessage(parent.currency, parent.spanish)); return false
            }
            raw = normalized
            commit(raw: normalized, error: "")
            let grouped = Self.group(normalized)
            textField.text = grouped
            var location = 0, count = 0
            for char in grouped {
                if count >= logical { break }
                location += 1; if char != "," { count += 1 }
            }
            if let position = textField.position(from: textField.beginningOfDocument, offset: location) {
                textField.selectedTextRange = textField.textRange(from: position, to: position)
            }
            if old.filter({ $0 == "," }).count != grouped.filter({ $0 == "," }).count && !UIAccessibility.isReduceMotionEnabled {
                let transition = CATransition(); transition.type = .fade; transition.duration = 0.12
                textField.layer.add(transition, forKey: "grouping")
            }
            return false
        }
        func textFieldDidBeginEditing(_ textField: UITextField) { parent.onFocus(true) }
        func textFieldDidEndEditing(_ textField: UITextField) {
            parent.onFocus(false)
            guard let value = Decimal(string: raw), !raw.isEmpty else { return }
            let fraction = raw.split(separator: ".", omittingEmptySubsequences: false).dropFirst().first?.count ?? 0
            guard fraction <= parent.rules.digits(parent.currency) else { return }
            let formatted = parent.rules.format(value, parent.currency)
            raw = formatted.replacingOccurrences(of: ",", with: "")
            commit(raw: raw)
            textField.text = formatted
        }
        /// Keyboard input can arrive while SwiftUI is updating; deferring keeps each write from being dropped.
        private func commit(raw: String? = nil, error: String? = nil) {
            let parent = parent
            pending += 1
            DispatchQueue.main.async { [self] in
                if let raw { parent.raw = raw }
                if let error { parent.error = error }
                pending -= 1
            }
        }
        static func group(_ raw: String) -> String {
            let parts = raw.split(separator: ".", omittingEmptySubsequences: false)
            guard let first = parts.first else { return "" }
            let negative = first.hasPrefix("-")
            let digits = negative ? String(first.dropFirst()) : String(first)
            let grouped = String(digits.reversed().enumerated().map { i, ch in
                (i > 0 && i % 3 == 0 ? "," : "") + String(ch)
            }.joined().reversed())
            return (negative ? "-" : "") + grouped + (parts.count > 1 ? "." + parts[1] : "")
        }
    }
}
