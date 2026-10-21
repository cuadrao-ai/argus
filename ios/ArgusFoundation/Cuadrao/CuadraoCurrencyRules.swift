import SwiftUI

/// What the shared money fields need to know about currencies. The default is the device's own currency data,
/// exactly as before; a host that owns a stricter table (the on-device book) supplies its own through the environment.
struct CuadraoCurrencyRules {
    var digits: (String) -> Int
    var maximum: (String) -> Decimal
    var maximumMessage: (_ currency: String, _ spanish: Bool) -> String
    var format: (Decimal, String) -> String
    /// Codes the currency picker offers, in order.
    var pickerCodes: (() -> [String])?

    static let system = CuadraoCurrencyRules(
        digits: { CanvasMoney.digits($0) },
        maximum: { _ in CanvasMoney.maximum },
        maximumMessage: { _, spanish in CuadraoCopy.text("copy.cuadraoCurrencyRules.cbf6d72372", spanish: spanish) },
        format: { CanvasMoney.format($0, currency: $1) },
        pickerCodes: { PlanCurrency.supported })
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
