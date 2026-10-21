import SwiftUI
import UIKit

struct CuadraoAmountField: View {
    @Binding var raw: String
    @Binding var currency: String
    @Binding var error: String
    let spanish: Bool
    var allowNegative = false
    var currencySelectable = true
    var identifier = "cuadrao-amount"
    var currencyIdentifier = "account-edit-currency"
    /// Amount-first layout: a centered, unboxed number under the currency code.
    var hero = false
    var autofocus = false
    @State private var choosingCurrency = false
    @Environment(\.cuadraoCurrencyRules) private var rules

    var body: some View {
        if hero { heroBody } else { boxedBody }
    }

    private var heroBody: some View {
        VStack(spacing: 4) {
            if currencySelectable {
                Button { choosingCurrency = true } label: { CuadraoChoiceLabel(title: currency) }
                    .buttonStyle(.plain).accessibilityIdentifier(currencyIdentifier)
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoAmountField.06c028f17d", spanish: spanish, String(describing: currency)))
            } else {
                Text(currency).font(CuadraoTypography.supporting).foregroundStyle(WelcomePalette.ink.opacity(0.6))
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoAmountField.579ad15d4c", spanish: spanish, String(describing: currency)))
            }
            CanvasDecimalInput(raw: $raw, error: $error, currency: currency, spanish: spanish, allowNegative: allowNegative,
                               identifier: identifier, alignment: .center, autofocus: autofocus)
                .frame(minHeight: 64)
            if !error.isEmpty { Text(error).font(.footnote).foregroundStyle(.red).accessibilityIdentifier("amount-error") }
        }
        .frame(maxWidth: .infinity)
        .sheet(isPresented: $choosingCurrency) { CanvasCurrencyPicker(currency: $currency, spanish: spanish) }
        .onChange(of: currency) { _, _ in recheckDecimals() }
    }

    private var boxedBody: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                if currencySelectable {
                    Button { choosingCurrency = true } label: { CuadraoChoiceLabel(title: currency) }
                        .buttonStyle(.plain)
                        .accessibilityLabel(CuadraoCopy.text("copy.cuadraoAmountField.06c028f17d", spanish: spanish, String(describing: currency)))
                        .accessibilityIdentifier(currencyIdentifier)
                } else {
                    CuadraoChoiceLabel(title: currency, selectable: false)
                        .accessibilityLabel(CuadraoCopy.text("copy.cuadraoAmountField.579ad15d4c", spanish: spanish, String(describing: currency)))
                }
                CanvasDecimalInput(raw: $raw, error: $error, currency: currency,
                    spanish: spanish, allowNegative: allowNegative, identifier: identifier)
                    .frame(minHeight: 60)
            }
            .padding(.horizontal, 18).padding(.vertical, 4)
            .background(WelcomePalette.background, in: RoundedRectangle(cornerRadius: 18))
            .overlay { RoundedRectangle(cornerRadius: 18).stroke(error.isEmpty ? WelcomePalette.border : .red.opacity(0.7)) }
            if !error.isEmpty { Text(error).font(.footnote).foregroundStyle(.red).accessibilityIdentifier("amount-error") }
        }
        .sheet(isPresented: $choosingCurrency) {
            CanvasCurrencyPicker(currency: $currency, spanish: spanish)
        }
        .onChange(of: currency) { _, _ in recheckDecimals() }
    }

    private func recheckDecimals() {
        let fraction = raw.split(separator: ".", omittingEmptySubsequences: false).dropFirst().first?.count ?? 0
        error = fraction > rules.digits(currency)
            ? (CuadraoCopy.text("copy.canvasDecimalInput.fb945d8969", spanish: spanish, String(describing: currency))) : ""
    }
}

private struct CanvasCurrencyPicker: View {
    @Binding var currency: String
    let spanish: Bool
    @State private var query = ""
    @Environment(\.dismiss) private var dismiss
    @Environment(\.cuadraoCurrencyRules) private var rules
    private var codes: [String] {
        let all = rules.pickerCodes?() ?? PlanCurrency.supported
        return all.filter { query.isEmpty || $0.localizedCaseInsensitiveContains(query) || name($0).localizedCaseInsensitiveContains(query) }
    }
    private func name(_ code: String) -> String {
        Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)).localizedString(forCurrencyCode: code) ?? code
    }
    var body: some View {
        NavigationStack {
            List(codes, id: \.self) { code in
                Button {
                    currency = code; dismiss()
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(code).foregroundStyle(.primary)
                            Text(name(code)).font(.subheadline).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if code == currency { Image(systemName: "checkmark") }
                    }.padding(.vertical, 4)
                }
            }.listStyle(.plain)
                .searchable(text: $query, prompt: CuadraoCopy.text("copy.cuadraoAmountField.d8f1c7193a", spanish: spanish))
                .navigationTitle(CuadraoCopy.text("copy.connectedTransactionSheet.9b96ad5816", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoDoneToolbar(title: CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish)) { dismiss() } }
        }.tint(WelcomePalette.pine)
    }
}
