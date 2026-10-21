import SwiftUI

enum CuadraoHomeSection: String, CaseIterable, Identifiable {
    case overview, upcoming, accounts, activity
    var id: String { rawValue }
    static let defaultOrder = allCases.map(\.rawValue).joined(separator: ",")
    static func decode(_ value: String) -> [Self] {
        var result: [Self] = []
        for raw in value.split(separator: ",") {
            if let section = Self(rawValue: String(raw)), !result.contains(section) { result.append(section) }
        }
        return result + allCases.filter { !result.contains($0) }
    }
    func title(_ es: Bool) -> String {
        switch self {
        case .overview: es ? "Panorama" : "Overview"
        case .upcoming: es ? "Próximamente" : "Coming up"
        case .accounts: es ? "Cuentas" : "Accounts"
        case .activity: es ? "Movimientos" : "Activity"
        }
    }
    func detail(_ es: Bool) -> String {
        switch self {
        case .overview: es ? "Tu resumen financiero" : "Your financial summary"
        case .upcoming: es ? "Lo que viene" : "What’s ahead"
        case .accounts: es ? "Dónde está tu dinero" : "Where your money is"
        case .activity: es ? "Lo que ya pasó" : "What already happened"
        }
    }
}

struct CuadraoHomeLayoutSheet: View {
    @Binding var savedOrder: String
    let spanish: Bool
    @State private var sections: [CuadraoHomeSection]
    @Environment(\.dismiss) private var dismiss

    init(savedOrder: Binding<String>, spanish: Bool) {
        _savedOrder = savedOrder
        self.spanish = spanish
        _sections = State(initialValue: CuadraoHomeSection.decode(savedOrder.wrappedValue))
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(sections) { section in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(section.title(spanish)).font(CuadraoTypography.action)
                            Text(section.detail(spanish)).font(.subheadline).foregroundStyle(.secondary)
                        }.padding(.vertical, 12).padding(.trailing, 16)
                            .accessibilityElement(children: .combine)
                            .accessibilityIdentifier("home-order-" + section.rawValue)
                            .accessibilityAction(named: Text(spanish ? "Subir" : "Move up")) { move(section, by: -1) }
                            .accessibilityAction(named: Text(spanish ? "Bajar" : "Move down")) { move(section, by: 1) }
                    }.onMove { sections.move(fromOffsets: $0, toOffset: $1) }
                } header: {
                    Text(spanish ? "Arrastra las secciones a tu gusto." : "Drag sections into your preferred order.")
                        .textCase(nil).padding(.bottom, 8)
                } footer: {
                    Text(spanish ? "El orden se aplica a todos tus espacios. Las secciones vacías aparecen cuando hay contenido."
                         : "This order applies to all your spaces. Empty sections appear when there is content.")
                }
                Section {
                    Button(spanish ? "Restablecer orden" : "Reset order") { sections = CuadraoHomeSection.allCases }
                        .frame(minHeight: 44)
                }
            }.environment(\.editMode, .constant(.active))
                .navigationTitle(spanish ? "Ordenar Inicio" : "Reorder Home")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel") { dismiss() }
                    CuadraoConfirmToolbar(title: spanish ? "Listo" : "Done") {
                        savedOrder = sections.map(\.rawValue).joined(separator: ","); dismiss()
                    }
                }
        }.tint(WelcomePalette.pine).presentationDragIndicator(.visible)
    }
    private func move(_ section: CuadraoHomeSection, by offset: Int) {
        guard let index = sections.firstIndex(of: section), sections.indices.contains(index + offset) else { return }
        sections.swapAt(index, index + offset)
    }
}
