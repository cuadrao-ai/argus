import SwiftUI

struct CuadraoArchiveAccountReview: View {
    let spanish: Bool
    let archive: () -> Void
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text(spanish ? "¿Archivar esta cuenta?" : "Archive this account?").font(CuadraoTypography.feature)
            Text(spanish ? "El historial se conserva. Puedes recuperarla en Cuentas archivadas." : "Its history stays intact. Restore it from Archived accounts.")
            Button(spanish ? "Archivar" : "Archive") { archive(); dismiss() }
                .buttonStyle(.borderedProminent).tint(WelcomePalette.pine)
                .accessibilityIdentifier("accounts.archive.confirm")
            Button(spanish ? "Cancelar" : "Cancel") { dismiss() }
                .accessibilityIdentifier("accounts.archive.cancel")
        }.padding(28).presentationDetents([.medium, .large])
    }
}

struct CuadraoArchivedAccounts: View {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(spanish ? "Sus balances e historial se conservan." : "Balances and history are kept.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    if data.archived.isEmpty {
                        ContentUnavailableView(spanish ? "No hay cuentas archivadas" : "No archived accounts", systemImage: "archivebox")
                    }
                    ForEach(data.archived) { account in
                        VStack(alignment: .leading, spacing: 0) {
                            CanvasAccountRow(account: account, spanish: spanish)
                            CanvasActionRow(title: spanish ? "Restaurar" : "Restore", symbol: "arrow.uturn.backward") {
                                data.archive(account.id, false)
                            }.foregroundStyle(WelcomePalette.pine)
                            Divider()
                        }
                    }
                }.padding(24)
            }.background(WelcomePalette.background)
                .navigationTitle(spanish ? "Cuentas archivadas" : "Archived accounts")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoDoneToolbar(title: spanish ? "Listo" : "Done") { dismiss() } }
        }.tint(WelcomePalette.pine)
    }
}

struct CuadraoRenameAccount: View {
    let data: CuadraoAccountsPreview
    let account: CanvasAccount
    let spanish: Bool
    @State private var name = ""
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        CuadraoRenameAccountForm(name: $name, placeholder: account.kind.title(spanish), spanish: spanish,
            cancel: { dismiss() }) {
            var updated = account
            updated.name = name.trimmingCharacters(in: .whitespacesAndNewlines)
            data.replace(updated); dismiss()
        }
        .onAppear { name = account.displayName(spanish) }
    }
}

struct CuadraoRenameAccountForm: View {
    @Binding var name: String
    let placeholder: String
    let spanish: Bool
    var nameIdentifier = "account-rename-name"
    var saveIdentifier = "account-rename-save"
    var cancelIdentifier = "account-rename-cancel"
    /// A connected save reports progress or a server answer under the field.
    var status: String? = nil
    var statusIdentifier = "account-rename-status"
    var primaryTitle: String? = nil
    var busy = false
    let cancel: () -> Void
    let save: () -> Void
    @FocusState private var focused: Bool
    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 20) {
                Text(spanish ? "Nombre" : "Name").font(.subheadline)
                TextField(placeholder, text: $name)
                    .autocorrectionDisabled().focused($focused).modifier(RegistrationField(focused: focused))
                    .onChange(of: name) { _, value in if value.count > 60 { name = String(value.prefix(60)) } }
                    .disabled(busy).accessibilityIdentifier(nameIdentifier)
                if let status {
                    Text(status).font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier(statusIdentifier)
                }
                RegistrationButton(title: primaryTitle ?? (spanish ? "Guardar" : "Save"),
                                   enabled: !busy && !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, action: save)
                    .accessibilityIdentifier(saveIdentifier)
                Spacer(minLength: 0)
            }.padding(24).background(WelcomePalette.background)
                .navigationTitle(spanish ? "Cambiar nombre" : "Rename account").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel", disabled: busy, identifier: cancelIdentifier, action: cancel)
                }
        }.tint(WelcomePalette.pine).presentationDetents([.medium, .large])
    }
}
