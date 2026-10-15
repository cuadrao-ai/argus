import SwiftUI
import CuadraoBook

/// Lists the currencies the server accepts, from the book's own table, with names from the device language.
struct GuestCurrencyPicker: View {
    let selection: String?
    let spanish: Bool
    let choose: (String) -> Void
    @State private var query = ""
    @Environment(\.dismiss) private var dismiss

    private var codes: [String] {
        CurrencyTable.pickerCodes.filter {
            query.isEmpty || $0.localizedCaseInsensitiveContains(query) || name($0).localizedCaseInsensitiveContains(query)
        }
    }

    private func name(_ code: String) -> String {
        Locale(identifier: spanish ? "es_419" : "en_US").localizedString(forCurrencyCode: code) ?? code
    }

    var body: some View {
        NavigationStack {
            List(codes, id: \.self) { code in
                Button {
                    choose(code)
                    dismiss()
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(code).foregroundStyle(.primary)
                            Text(name(code)).font(.subheadline).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if code == selection { Image(systemName: "checkmark").accessibilityHidden(true) }
                    }.padding(.vertical, 4).frame(minHeight: 44).contentShape(Rectangle())
                }
                .accessibilityIdentifier("guest.currency." + code)
                .accessibilityAddTraits(code == selection ? .isSelected : [])
            }
            .listStyle(.plain)
            .searchable(text: $query, prompt: spanish ? "Nombre o código" : "Name or code")
            .navigationTitle(spanish ? "Moneda" : "Currency").navigationBarTitleDisplayMode(.inline)
            .toolbar { CuadraoDoneToolbar(title: spanish ? "Listo" : "Done") { dismiss() } }
        }.tint(WelcomePalette.pine)
    }
}
