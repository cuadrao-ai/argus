import SwiftUI
import CuadraoBook

/// A row of the book's Accounts section, shared by Home and the archived list.
struct GuestAccountRow: View {
    let account: BookAccount
    let book: DeviceBook
    let spanish: Bool
    @Environment(\.locale) private var locale

    var body: some View {
        CanvasAccountRowContent(value: GuestAccountPresentation.row(account, in: book, spanish: spanish, locale: locale))
    }
}

/// Home's Accounts section: the shared ordered collection over the book's active accounts. Order is saved in the book.
struct GuestAccountsSection: View {
    @ObservedObject var model: GuestBookModel
    let spanish: Bool
    let open: (UUID) -> Void
    let add: () -> Void
    let edit: (UUID) -> Void
    let archive: (UUID) -> Void
    let showArchived: () -> Void

    private var active: [BookAccount] { model.book.activeAccounts }
    private var archivedCount: Int { model.book.archivedAccounts.count }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if active.isEmpty {
                CuadraoPersonalAccountsEmpty(spanish: spanish, addAccount: add)
                    .accessibilityElement(children: .contain).accessibilityIdentifier("guest.home.empty")
            } else {
                HStack(spacing: 0) {
                    Text(CuadraoCopy.text("copy.connectedCuadraoHome.8cce5d02a3", spanish: spanish)).font(CuadraoTypography.section).accessibilityAddTraits(.isHeader)
                    Spacer()
                    CuadraoSectionAddButton(title: CuadraoCopy.text("copy.connectedCuadraoHome.10d1d9ce3f", spanish: spanish), action: add)
                        .accessibilityIdentifier("accounts.add")
                }
                CuadraoOrderedCollection(items: active, spanish: spanish, spacing: 0,
                    identifier: { "guest.account.row." + $0.id.uuidString },
                    open: { open($0.id) }, edit: { edit($0.id) }, archive: { archive($0.id) },
                    reorder: { ids in _ = try? model.apply { try $0.reorderingActive(ids) } }) { account in
                    GuestAccountRow(account: account, book: model.book, spanish: spanish)
                        .overlay(alignment: .bottom) { Rectangle().fill(WelcomePalette.separator).frame(height: 1).padding(.leading, 54) }
                }
            }
            if archivedCount > 0 {
                Button(action: showArchived) {
                    HStack {
                        Text(CuadraoCopy.text("copy.connectedCuadraoHome.4ab8767f26", spanish: spanish))
                        Text("\(archivedCount)").foregroundStyle(.secondary)
                        Spacer()
                        Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.secondary).accessibilityHidden(true)
                    }.font(.subheadline).frame(minHeight: 44).contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityIdentifier("guest.accounts.archived")
            }
        }
    }
}

/// One account: the shared detail header, with the actions the book can do offline.
struct GuestAccountDetail: View {
    @ObservedObject var model: GuestBookModel
    let id: UUID
    let spanish: Bool
    let add: () -> Void
    let open: (UUID) -> Void
    let editMovement: (UUID) -> Void
    let deleteMovement: (UUID) -> Void
    let edit: () -> Void
    let archive: () -> Void
    let restore: () -> Void
    @Environment(\.locale) private var locale

    var body: some View {
        if let account = model.book.account(id) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    CanvasAccountDetailHeader(value: GuestAccountPresentation.detail(account, in: model.book, spanish: spanish, locale: locale))
                    if !account.archived {
                        RegistrationButton(title: CuadraoCopy.text("copy.canvasAccountPresentation.ef0cf39904", spanish: spanish), action: add)
                            .accessibilityIdentifier("guest.account.record")
                    }
                    history(account)
                    VStack(spacing: 0) {
                        CanvasActionRow(title: CuadraoCopy.text("copy.cuadraoFirstAccountSheet.4df1187ce2", spanish: spanish), symbol: "pencil", action: edit)
                            .accessibilityIdentifier("guest.account.edit")
                        Divider()
                        if account.archived {
                            CanvasActionRow(title: CuadraoCopy.text("copy.guestAccounts.8a6d09afdd", spanish: spanish),
                                            symbol: "arrow.uturn.backward", action: restore)
                                .foregroundStyle(WelcomePalette.pine).accessibilityIdentifier("guest.account.restore")
                        } else {
                            CanvasActionRow(title: CuadraoCopy.text("copy.guestAccounts.13baae182c", spanish: spanish), symbol: "archivebox", action: archive)
                                .accessibilityIdentifier("guest.account.archive")
                        }
                    }
                }.padding(24)
            }
            .accessibilityIdentifier("guest.account.detail")
            .background(WelcomePalette.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar)
        }
    }
}

extension GuestAccountDetail {
    /// The account's own movements, newest first.
    @ViewBuilder fileprivate func history(_ account: BookAccount) -> some View {
        let movements = model.book.liveMovements(of: account.id)
        if movements.isEmpty {
            CuadraoEmptyView(title: CuadraoCopy.text("copy.accountActivityView.8e6c47416d", spanish: spanish),
                             detail: account.archived ? nil : (CuadraoCopy.text("copy.guestAccounts.c1c6f87f41", spanish: spanish)),
                             identifier: "guest.account.empty")
        } else {
            VStack(alignment: .leading, spacing: 12) {
                Text(CuadraoCopy.text("copy.accountActivityView.f7d6ac01ad", spanish: spanish)).font(CuadraoTypography.section).accessibilityAddTraits(.isHeader)
                VStack(spacing: 0) {
                    ForEach(movements) { movement in
                        GuestMovementRow(movement: movement, book: model.book, perspective: account.id, spanish: spanish,
                            open: { open(movement.id) }, edit: { editMovement(movement.id) }, delete: { deleteMovement(movement.id) })
                    }
                }
            }
        }
    }
}

/// Archived accounts, each with Restore. History and balances are kept.
struct GuestArchivedAccounts: View {
    @ObservedObject var model: GuestBookModel
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(CuadraoCopy.text("copy.connectedCuadraoHome.d433d35ac8", spanish: spanish))
                        .font(.subheadline).foregroundStyle(.secondary)
                    if model.book.archivedAccounts.isEmpty {
                        ContentUnavailableView(CuadraoCopy.text("copy.connectedCuadraoHome.63cbd4a9dc", spanish: spanish), systemImage: "archivebox")
                    }
                    ForEach(model.book.archivedAccounts) { account in
                        VStack(alignment: .leading, spacing: 0) {
                            GuestAccountRow(account: account, book: model.book, spanish: spanish)
                            CanvasActionRow(title: CuadraoCopy.text("copy.connectedCuadraoHome.e203d01b16", spanish: spanish), symbol: "arrow.uturn.backward") {
                                _ = try? model.apply { try $0.settingArchived(account.id, false) }
                            }.foregroundStyle(WelcomePalette.pine).accessibilityIdentifier("guest.account.restore." + account.id.uuidString)
                            Divider()
                        }
                    }
                }.padding(24)
            }
            .background(WelcomePalette.background)
            .navigationTitle(CuadraoCopy.text("copy.connectedCuadraoHome.4ab8767f26", spanish: spanish))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { CuadraoDoneToolbar(title: CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish)) { dismiss() } }
        }.tint(WelcomePalette.pine).accessibilityIdentifier("guest.archived")
    }
}
