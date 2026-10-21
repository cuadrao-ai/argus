import SwiftUI

struct CuadraoArchiveAccountReview: View {
    let spanish: Bool
    let archive: () -> Void
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text(CuadraoCopy.text("copy.cuadraoAccountManagement.5c34dcf7f8", spanish: spanish)).font(CuadraoTypography.feature)
            Text(CuadraoCopy.text("copy.cuadraoAccountManagement.7a4a4cb485", spanish: spanish))
            Button(CuadraoCopy.text("copy.connectedCuadraoHome.0960027352", spanish: spanish)) { archive(); dismiss() }
                .buttonStyle(.borderedProminent).tint(WelcomePalette.pine)
                .accessibilityIdentifier("accounts.archive.confirm")
            Button(CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish)) { dismiss() }
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
                    Text(CuadraoCopy.text("copy.connectedCuadraoHome.d433d35ac8", spanish: spanish))
                        .font(.subheadline).foregroundStyle(.secondary)
                    if data.archived.isEmpty {
                        ContentUnavailableView(CuadraoCopy.text("copy.connectedCuadraoHome.63cbd4a9dc", spanish: spanish), systemImage: "archivebox")
                    }
                    ForEach(data.archived) { account in
                        VStack(alignment: .leading, spacing: 0) {
                            CanvasAccountRow(account: account, spanish: spanish)
                            CanvasActionRow(title: CuadraoCopy.text("copy.connectedCuadraoHome.e203d01b16", spanish: spanish), symbol: "arrow.uturn.backward") {
                                data.archive(account.id, false)
                            }.foregroundStyle(WelcomePalette.pine)
                            Divider()
                        }
                    }
                }.padding(24)
            }.background(WelcomePalette.background)
                .navigationTitle(CuadraoCopy.text("copy.connectedCuadraoHome.4ab8767f26", spanish: spanish))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoDoneToolbar(title: CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish)) { dismiss() } }
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
                Text(CuadraoCopy.text("copy.cuadraoAccountManagement.9d191b79fb", spanish: spanish)).font(.subheadline)
                TextField(placeholder, text: $name)
                    .autocorrectionDisabled().focused($focused).modifier(RegistrationField(focused: focused))
                    .onChange(of: name) { _, value in if value.count > 60 { name = String(value.prefix(60)) } }
                    .disabled(busy).accessibilityIdentifier(nameIdentifier)
                if let status {
                    Text(status).font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier(statusIdentifier)
                }
                RegistrationButton(title: primaryTitle ?? (CuadraoCopy.text("copy.cuadraoAccountManagement.553ab1bf1a", spanish: spanish)),
                                   enabled: !busy && !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, action: save)
                    .accessibilityIdentifier(saveIdentifier)
                Spacer(minLength: 0)
            }.padding(24).background(WelcomePalette.background)
                .navigationTitle(CuadraoCopy.text("copy.cuadraoAccountCanvas.e59e534133", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish), disabled: busy, identifier: cancelIdentifier, action: cancel)
                }
        }.tint(WelcomePalette.pine).presentationDetents([.medium, .large])
    }
}
