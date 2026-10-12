import SwiftUI

/// What the shared money fields need to know about currencies. The default is the device's own currency data,
/// exactly as before; a host that owns a stricter table (the on-device book) supplies its own through the environment.
struct CuadraoCurrencyRules {
    var digits: (String) -> Int
    var maximum: (String) -> Decimal
    var maximumMessage: (_ currency: String, _ spanish: Bool) -> String
    var format: (Decimal, String) -> String
    /// Codes the currency picker offers, in order; nil keeps the device's list.
    var pickerCodes: (() -> [String])?

    static let system = CuadraoCurrencyRules(
        digits: { CanvasMoney.digits($0) },
        maximum: { _ in CanvasMoney.maximum },
        maximumMessage: { _, spanish in spanish ? "Máximo: 9,999,999.99" : "Maximum: 9,999,999.99" },
        format: { CanvasMoney.format($0, currency: $1) },
        pickerCodes: nil)
}

private struct CuadraoCurrencyRulesKey: EnvironmentKey {
    static let defaultValue = CuadraoCurrencyRules.system
}

extension EnvironmentValues {
    var cuadraoCurrencyRules: CuadraoCurrencyRules {
        get { self[CuadraoCurrencyRulesKey.self] }
        set { self[CuadraoCurrencyRulesKey.self] = newValue }
    }
}
