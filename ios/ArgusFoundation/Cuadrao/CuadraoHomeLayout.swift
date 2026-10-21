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
        case .overview: CuadraoCopy.text("copy.cuadraoHomeLayout.4906bf4f96", spanish: es)
        case .upcoming: CuadraoCopy.text("copy.cuadraoHomeLayout.101b77b57c", spanish: es)
        case .accounts: CuadraoCopy.text("copy.cuadraoHomeLayout.8cce5d02a3", spanish: es)
        case .activity: CuadraoCopy.text("copy.cuadraoHomeLayout.f7d6ac01ad", spanish: es)
        }
    }
    func detail(_ es: Bool) -> String {
        switch self {
        case .overview: CuadraoCopy.text("copy.cuadraoHomeLayout.54267846a0", spanish: es)
        case .upcoming: CuadraoCopy.text("copy.cuadraoHomeLayout.407f9183d7", spanish: es)
        case .accounts: CuadraoCopy.text("copy.cuadraoHomeLayout.68f1fc2cbe", spanish: es)
        case .activity: CuadraoCopy.text("copy.cuadraoHomeLayout.5f0fe2685a", spanish: es)
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
                            .accessibilityAction(named: Text(CuadraoCopy.text("copy.cuadraoHomeLayout.e37bbfcb44", spanish: spanish))) { move(section, by: -1) }
                            .accessibilityAction(named: Text(CuadraoCopy.text("copy.cuadraoHomeLayout.9f16cae174", spanish: spanish))) { move(section, by: 1) }
                    }.onMove { sections.move(fromOffsets: $0, toOffset: $1) }
                } header: {
                    Text(CuadraoCopy.text("copy.cuadraoHomeLayout.33c3fd3322", spanish: spanish))
                        .textCase(nil).padding(.bottom, 8)
                } footer: {
                    Text(CuadraoCopy.text("copy.cuadraoHomeLayout.8b8acf23e5", spanish: spanish))
                }
                Section {
                    Button(CuadraoCopy.text("copy.cuadraoHomeLayout.f93184560a", spanish: spanish)) { sections = CuadraoHomeSection.allCases }
                        .frame(minHeight: 44)
                }
            }.environment(\.editMode, .constant(.active))
                .navigationTitle(CuadraoCopy.text("copy.cuadraoHomeLayout.01b6a79dd0", spanish: spanish))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish)) { dismiss() }
                    CuadraoConfirmToolbar(title: CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish)) {
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
