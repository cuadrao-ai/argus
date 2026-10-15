import SwiftUI

/// Presentation bridge for existing numeric preview models; editing stays decimal text.
struct CanvasMoneyValueInput: View {
    @Binding var value: Double
    @Binding var error: String
    let currency: String
    let spanish: Bool
    let identifier: String
    let title: String
    var size: CuadraoTypography.MoneySize = .prominent
    var alignment: NSTextAlignment = .left
    var onFocus: (Bool) -> Void = { _ in }
    @State private var raw = ""
    @Environment(\.cuadraoCurrencyRules) private var rules

    var body: some View {
        CanvasDecimalInput(raw: $raw, error: $error, currency: currency, spanish: spanish,
                           identifier: identifier, title: title, size: size, alignment: alignment, onFocus: onFocus)
            .onAppear { syncValue() }
            .onChange(of: value) { _, _ in
                if numericValue != value { syncValue() }
            }
            .onChange(of: raw) { _, _ in value = numericValue }
    }
    private var numericValue: Double { NSDecimalNumber(decimal: Decimal(string: raw) ?? 0).doubleValue }
    private func syncValue() {
        raw = value.isFinite && value != 0 ? rules.format(Decimal(string: String(value)) ?? 0, currency).replacingOccurrences(of: ",", with: "") : ""
    }
}

extension Binding where Value == [String: String] {
    func message(for identifier: String) -> Binding<String> {
        Binding<String>(get: { wrappedValue[identifier] ?? "" }, set: { wrappedValue[identifier] = $0 })
    }
}
