import SwiftUI

struct PlanCurrencyChoice: View {
    @Binding var currency: String
    let locked: Bool
    let spanish: Bool
    var showLock = true
    var identifier = "plan-edit-currency"
    @Environment(\.cuadraoCurrencyRules) private var rules
    var body: some View {
        if locked {
            CuadraoChoiceLabel(title: currency, selectable: false, locked: showLock)
                .foregroundStyle(.secondary)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(CuadraoCopy.text("copy.cuadraoAmountField.579ad15d4c", spanish: spanish, String(describing: currency)))
                .accessibilityIdentifier(showLock ? "plan-currency-fixed" : "plan-currency-inherited")
        } else {
            CuadraoChoiceMenu(title: CuadraoCopy.text("copy.connectedTransactionSheet.9b96ad5816", spanish: spanish), selection: $currency,
                values: rules.pickerCodes?() ?? PlanCurrency.supported, valueTitle: { $0 })
                .buttonStyle(.plain).foregroundStyle(WelcomePalette.pine)
                .accessibilityLabel(CuadraoCopy.text("copy.cuadraoAmountField.06c028f17d", spanish: spanish, String(describing: currency)))
                .accessibilityIdentifier(identifier)
        }
    }
}
