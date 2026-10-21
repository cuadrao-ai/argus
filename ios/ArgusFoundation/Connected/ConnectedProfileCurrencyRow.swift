import SwiftUI

struct ConnectedProfileCurrencyRow: View {
    @ObservedObject var model: ProfileAuthModel
    let spanish: Bool
    private var title: String { CuadraoCopy.text("copy.connectedProfileCurrencyRow.8ceb934024", spanish: spanish) }
    private var value: String { model.profile?.currency ?? (CuadraoCopy.text("copy.connectedProfileCurrencyRow.8f6645049d", spanish: spanish)) }

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            CuadraoChoiceMenu(title: title,
                selection: Binding(
                    get: { value },
                    set: { value in Task { await model.setPrimaryCurrency(value) } }),
                values: PlanCurrency.supported, valueTitle: { $0 })
                .buttonStyle(.borderless)
                .disabled(model.busy)
                .accessibilityLabel(title)
                .accessibilityValue(value)
                .accessibilityIdentifier("profile.primaryCurrency")
        }
        .accessibilityElement(children: .contain)
        if let key = model.errorKey {
            Text(LocalizedStringKey(key)).foregroundStyle(.red)
                .accessibilityIdentifier("profile.primaryCurrency.error")
        }
    }
}
