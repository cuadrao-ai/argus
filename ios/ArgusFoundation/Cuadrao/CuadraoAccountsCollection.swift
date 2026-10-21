import SwiftUI

/// Account management owns ordering and archive recovery; Home remains a shortcut.
struct CuadraoAccountsCollection: View {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    @State private var mode: EditMode
    @State private var path: [UUID] = []
    @State private var selection: CanvasAccountSheet?
    @Environment(\.dismiss) private var dismiss

    init(data: CuadraoAccountsPreview, spanish: Bool, editing: Bool = false) {
        self.data = data; self.spanish = spanish
        _mode = State(initialValue: editing ? .active : .inactive)
    }
    var body: some View {
        NavigationStack(path: $path) {
            List {
                Section {
                    ForEach(data.active) { account in
                        Button { path.append(account.id) } label: {
                            CanvasAccountRow(account: account, spanish: spanish)
                        }.buttonStyle(.plain).disabled(mode.isEditing)
                            .accessibilityIdentifier("accounts-row-" + account.id.uuidString)
                    }.onMove { data.move(from: $0, to: $1) }
                } header: { Text(data.selectedSpace.title(spanish)) }
                Section {
                    Button { selection = .archived } label: {
                        HStack {
                            Label(spanish ? "Cuentas archivadas" : "Archived accounts", systemImage: "archivebox")
                            Spacer()
                            Text(data.archived.count.formatted()).foregroundStyle(.secondary)
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.secondary)
                        }.frame(minHeight: 44)
                    }.accessibilityIdentifier("accounts-archives")
                }
            }.environment(\.editMode, $mode).scrollContentBackground(.hidden)
                .background(WelcomePalette.background)
                .navigationTitle(spanish ? "Cuentas" : "Accounts").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: spanish ? "Cerrar" : "Close") { dismiss() }
                    ToolbarItem(placement: .primaryAction) {
                        Button(mode.isEditing ? (spanish ? "Listo" : "Done") : (spanish ? "Ordenar" : "Reorder")) {
                            withAnimation { mode = mode.isEditing ? .inactive : .active }
                        }.disabled(!mode.isEditing && data.active.count < 2)
                            .accessibilityIdentifier("accounts-order-toggle")
                    }
                }
                .navigationDestination(for: UUID.self) { id in
                    CuadraoAccountCanvas(data: data, accountID: id, spanish: spanish,
                        actions: { selection = $0 }, record: { selection = .record($0) })
                }
        }.tint(WelcomePalette.pine)
            .sheet(item: $selection) { item in
                CuadraoAccountModal(data: data, selection: item, spanish: spanish, show: { next in
                    if case .manageAccounts = next { selection = nil; path = []; mode = .active }
                    else { selection = next }
                }, archived: { _ in selection = nil; path = [] })
            }
    }
}
