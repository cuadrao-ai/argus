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
    @State private var choosingCurrency = false
    @Environment(\.cuadraoCurrencyRules) private var rules

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                if currencySelectable {
                    Button { choosingCurrency = true } label: { CuadraoChoiceLabel(title: currency) }
                        .buttonStyle(.plain)
                        .accessibilityLabel(spanish ? "Moneda, \(currency)" : "Currency, \(currency)")
                        .accessibilityIdentifier(currencyIdentifier)
                } else {
                    CuadraoChoiceLabel(title: currency, selectable: false)
                        .accessibilityLabel(spanish ? "Moneda fija: \(currency)" : "Fixed currency: \(currency)")
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
        .onChange(of: currency) { _, _ in
            let fraction = raw.split(separator: ".", omittingEmptySubsequences: false).dropFirst().first?.count ?? 0
            error = fraction > rules.digits(currency)
                ? (spanish ? "Revisa los decimales para \(currency)." : "Check decimal places for \(currency).") : ""
        }
    }
}

private struct CanvasCurrencyPicker: View {
    @Binding var currency: String
    let spanish: Bool
    @State private var query = ""
    @Environment(\.dismiss) private var dismiss
    @Environment(\.cuadraoCurrencyRules) private var rules
    private var codes: [String] {
        let priority = ["DOP", "USD", "EUR"]
        let all = rules.pickerCodes?() ?? priority + Locale.commonISOCurrencyCodes.filter { !priority.contains($0) }.sorted()
        return all.filter { query.isEmpty || $0.localizedCaseInsensitiveContains(query) || name($0).localizedCaseInsensitiveContains(query) }
    }
    private func name(_ code: String) -> String {
        Locale(identifier: spanish ? "es_DO" : "en_US").localizedString(forCurrencyCode: code) ?? code
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
                .searchable(text: $query, prompt: spanish ? "Nombre o código" : "Name or code")
                .navigationTitle(spanish ? "Moneda" : "Currency").navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoDoneToolbar(title: spanish ? "Listo" : "Done") { dismiss() } }
        }.tint(WelcomePalette.pine)
    }
}
