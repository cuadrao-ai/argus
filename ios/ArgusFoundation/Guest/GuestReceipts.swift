import SwiftUI
import CuadraoBook

/// The on-device book's receipt words, Spanish first. All are pending the founder's approval.
struct GuestReceiptCopy {
    let spanish: Bool
    var savedTitle: String { CuadraoCopy.text("copy.guestReceipts.06c88d7345", spanish: spanish) }
    var savedDetail: String {
        CuadraoCopy.text("copy.guestReceipts.96e136d15f", spanish: spanish)
    }
    var attachTo: String { CuadraoCopy.text("copy.guestReceipts.1a42559a88", spanish: spanish) }
    var noMovements: String { CuadraoCopy.text("copy.guestReceipts.58ec8e6fdf", spanish: spanish) }
    var attachTitle: String { CuadraoCopy.text("copy.guestReceipts.ee6b11210c", spanish: spanish) }
    var noReceipts: String {
        CuadraoCopy.text("copy.guestReceipts.e3b9850da9", spanish: spanish)
    }
    var view: String { CuadraoCopy.text("copy.receiptJourneyCopy.176bc5563c", spanish: spanish) }
    var remove: String { CuadraoCopy.text("copy.guestReceipts.5b409df865", spanish: spanish) }
    var later: String { CuadraoCopy.text("copy.receiptJourneyCopy.fb09b69c44", spanish: spanish) }
    var cancel: String { CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish) }
    var delete: String { CuadraoCopy.text("copy.savedReceiptCopy.534547cf82", spanish: spanish) }
    var listEmpty: String {
        CuadraoCopy.text("copy.guestReceipts.12c4e254b5", spanish: spanish)
    }
    var attachedTo: String { CuadraoCopy.text("copy.guestReceipts.3345777fd4", spanish: spanish) }
    var deleteTitle: String { CuadraoCopy.text("copy.savedReceiptCopy.4ca1494b4d", spanish: spanish) }
    var deleteMessage: String {
        CuadraoCopy.text("copy.guestReceipts.db66631642", spanish: spanish)
    }
    var emptyTitle: String { CuadraoCopy.text("copy.guestReceipts.afcc90c7b0", spanish: spanish) }
    var emptyDetail: String {
        CuadraoCopy.text("copy.guestReceipts.b897319a4b", spanish: spanish)
    }
    var add: String { CuadraoCopy.text("copy.guestReceipts.8cd37d53b1", spanish: spanish) }
    var scan: String { CuadraoCopy.text("copy.guestReceipts.c9002dc430", spanish: spanish) }
    var choosePhoto: String { CuadraoCopy.text("copy.cuadraoAddTray.1e4b004482", spanish: spanish) }
    var chooseFile: String { CuadraoCopy.text("copy.cuadraoAddTray.9d649f3046", spanish: spanish) }
    var couldNotSave: String { CuadraoCopy.text("copy.guestReceipts.f333141bff", spanish: spanish) }
}

private struct GuestReceiptsKey: EnvironmentKey {
    static let defaultValue: GuestReceiptStore? = nil
}

private struct GuestAddReceiptKey: EnvironmentKey {
    static let defaultValue: ((ReceiptSourceChoice) -> Void)? = nil
}

extension EnvironmentValues {
    /// Starts saving a receipt from the chosen source, set by the guest shell.
    var guestAddReceipt: ((ReceiptSourceChoice) -> Void)? {
        get { self[GuestAddReceiptKey.self] }
        set { self[GuestAddReceiptKey.self] = newValue }
    }

    /// The book's receipts, set by the guest shell.
    var guestReceipts: GuestReceiptStore? {
        get { self[GuestReceiptsKey.self] }
        set { self[GuestReceiptsKey.self] = newValue }
    }
}

/// After a capture: the receipt stays on this iPhone, and the person may attach it to a recent movement.
struct GuestReceiptSavedSheet: View {
    @ObservedObject var store: GuestReceiptStore
    @ObservedObject var model: GuestBookModel
    let receiptID: UUID
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    @Environment(\.locale) private var locale

    private var copy: GuestReceiptCopy { GuestReceiptCopy(spanish: spanish) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    RegistrationHeading(title: copy.savedTitle, detail: copy.savedDetail)
                        .accessibilityIdentifier("guest.receipt.saved")
                    Text(copy.attachTo).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                    GuestMovementChoices(model: model, spanish: spanish) { movementID in
                        try? store.attach(receiptID, to: movementID)
                        dismiss()
                    }
                }.padding(24)
            }
            .background(WelcomePalette.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { CuadraoCancelToolbar(title: copy.later, identifier: "guest.receipt.later") { dismiss() } }
        }.tint(WelcomePalette.pine)
    }
}

/// From a movement: choose one of the receipts saved on this iPhone that is not attached yet.
struct GuestAttachReceiptSheet: View {
    @ObservedObject var store: GuestReceiptStore
    @ObservedObject var model: GuestBookModel
    let movementID: UUID
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    @Environment(\.locale) private var locale

    private var copy: GuestReceiptCopy { GuestReceiptCopy(spanish: spanish) }
    private var choices: [GuestReceipt] { store.unattached(liveMovements: Set(model.book.liveMovements().map(\.id))) }

    var body: some View {
        NavigationStack {
            Group {
                if choices.isEmpty {
                    Text(copy.noReceipts).font(CuadraoTypography.body).padding(24)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                        .accessibilityIdentifier("guest.receipt.attach.empty")
                } else {
                    List {
                        ForEach(choices) { receipt in
                            Button {
                                try? store.attach(receipt.id, to: movementID)
                                dismiss()
                            } label: { GuestReceiptRow(receipt: receipt, locale: locale) }
                                .buttonStyle(.plain)
                                .accessibilityIdentifier("guest.receipt.choice." + receipt.id.uuidString)
                                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                                    Button(role: .destructive) { try? store.delete(receipt.id) } label: { Label(copy.delete, systemImage: "trash") }
                                        .tint(.red)
                                }
                        }
                    }.listStyle(.plain)
                }
            }
            .background(WelcomePalette.background)
            .navigationTitle(copy.attachTitle)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { CuadraoCancelToolbar(title: copy.cancel, identifier: "guest.receipt.attach.cancel") { dismiss() } }
        }.tint(WelcomePalette.pine)
    }
}

/// In a movement's detail: view or remove its receipt, or attach one.
struct GuestMovementReceiptActions: View {
    @ObservedObject var store: GuestReceiptStore
    let movementID: UUID
    let spanish: Bool
    let attach: () -> Void
    @State private var viewing: ViewedReceipt?

    private var copy: GuestReceiptCopy { GuestReceiptCopy(spanish: spanish) }

    var body: some View {
        VStack(spacing: 0) {
            if let receipt = store.receipt(for: movementID) {
                CanvasActionRow(title: copy.view, symbol: "doc.text.magnifyingglass") { view(receipt) }
                    .accessibilityIdentifier("guest.movement.receipt.view")
                Divider()
                CanvasActionRow(title: copy.remove, symbol: "minus.circle") { try? store.attach(receipt.id, to: nil) }
                    .accessibilityIdentifier("guest.movement.receipt.remove")
            } else {
                CanvasActionRow(title: copy.attachTitle, symbol: "paperclip", action: attach)
                    .accessibilityIdentifier("guest.movement.receipt.attach")
            }
        }
        .sheet(item: $viewing) { SavedReceiptViewer(receipt: $0, copy: SavedReceiptCopy(spanish: spanish)) }
    }

    private func view(_ receipt: GuestReceipt) {
        guard let data = store.data(receipt) else { return }
        viewing = ViewedReceipt(id: receipt.id.uuidString, filename: receipt.name, mediaType: receipt.mediaType, data: data)
    }
}

/// The most recent live movements, newest first, as choices.
struct GuestMovementChoices: View {
    @ObservedObject var model: GuestBookModel
    let spanish: Bool
    let choose: (UUID) -> Void
    @Environment(\.locale) private var locale

    var body: some View {
        let movements = Array(model.book.liveMovements().prefix(20))
        if movements.isEmpty {
            Text(GuestReceiptCopy(spanish: spanish).noMovements).font(CuadraoTypography.body)
        } else {
            VStack(spacing: 0) {
                ForEach(movements, id: \.id) { movement in
                    Button { choose(movement.id) } label: {
                        HStack(alignment: .firstTextBaseline) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(GuestMovementPresentation.title(movement, spanish: spanish)).font(CuadraoTypography.body)
                                Text(GuestMovementPresentation.date(movement, locale: locale, style: .medium))
                                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(GuestMovementPresentation.amount(movement, in: model.book, locale: locale)).monospacedDigit()
                        }.frame(minHeight: 56).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("guest.receipt.movement." + movement.id.uuidString)
                    Divider()
                }
            }
        }
    }
}

struct GuestReceiptRow: View {
    let receipt: GuestReceipt
    let locale: Locale
    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: receipt.pdf ? "doc.text" : "photo")
                .font(.title3).foregroundStyle(WelcomePalette.pine)
                .frame(width: 40, height: 40).background(WelcomePalette.pine.opacity(0.1), in: Circle())
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(receipt.name).font(CuadraoTypography.body).lineLimit(2)
                Text(receipt.createdAt.formatted(.dateTime.day().month(.abbreviated).year().locale(locale)))
                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
        }.frame(minHeight: 56).contentShape(Rectangle())
    }
}

/// Profile › Receipts on this iPhone: every receipt the book keeps, to view, attach to a movement, remove from it, or delete.
struct GuestReceiptsList: View {
    @ObservedObject var store: GuestReceiptStore
    @ObservedObject var model: GuestBookModel
    let spanish: Bool
    @Environment(\.locale) private var locale
    @State private var viewing: ViewedReceipt?
    @State private var attaching: GuestReceipt?
    @State private var deleting: GuestReceipt?
    @State private var choosingSource = false
    @Environment(\.guestAddReceipt) private var addReceipt

    private var copy: GuestReceiptCopy { GuestReceiptCopy(spanish: spanish) }

    var body: some View {
        Group {
            if store.receipts.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 28) {
                        CuadraoChartState(title: copy.emptyTitle, detail: copy.emptyDetail)
                        if addReceipt != nil {
                            RegistrationButton(title: copy.add) { choosingSource = true }
                                .accessibilityIdentifier("guest.receipts.add")
                        }
                    }.padding(.horizontal, 24).padding(.top, 16).frame(maxWidth: .infinity, alignment: .leading)
                }
                .accessibilityIdentifier("guest.receipts.empty")
            } else {
                List {
                    ForEach(store.receipts) { receipt in
                        Button { view(receipt) } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                GuestReceiptRow(receipt: receipt, locale: locale)
                                if let title = movementTitle(receipt) {
                                    Text(copy.attachedTo + " " + title).font(CuadraoTypography.caption).foregroundStyle(.secondary)
                                        .padding(.leading, 54)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("guest.receipts.row." + receipt.id.uuidString)
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button(role: .destructive) { deleting = receipt } label: { Label(copy.delete, systemImage: "trash") }
                                .tint(.red)
                        }
                        .contextMenu {
                            Button { view(receipt) } label: { Label(copy.view, systemImage: "doc.text.magnifyingglass") }
                            if movementTitle(receipt) == nil {
                                Button { attaching = receipt } label: { Label(copy.attachTo, systemImage: "paperclip") }
                            } else {
                                Button { try? store.attach(receipt.id, to: nil) } label: { Label(copy.remove, systemImage: "minus.circle") }
                            }
                            Button(role: .destructive) { deleting = receipt } label: { Label(copy.delete, systemImage: "trash") }
                        }
                    }
                }.listStyle(.plain).accessibilityIdentifier("guest.receipts.list")
            }
        }
        .background(WelcomePalette.background)
        .navigationTitle(GuestProfileRoute.receipts.title(spanish))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .sheet(item: $viewing) { SavedReceiptViewer(receipt: $0, copy: SavedReceiptCopy(spanish: spanish)) }
        .sheet(item: $attaching) { receipt in
            NavigationStack {
                ScrollView {
                    GuestMovementChoices(model: model, spanish: spanish) { movementID in
                        try? store.attach(receipt.id, to: movementID)
                        attaching = nil
                    }.padding(24)
                }
                .background(WelcomePalette.background)
                .navigationTitle(copy.attachTo).navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoCancelToolbar(title: copy.cancel, identifier: "guest.receipts.attach.cancel") { attaching = nil } }
            }.tint(WelcomePalette.pine)
        }
        .confirmationDialog(copy.add, isPresented: $choosingSource, titleVisibility: .visible) {
            Button(copy.scan) { addReceipt?(.scan) }.accessibilityIdentifier("guest.receipts.add.scan")
            Button(copy.choosePhoto) { addReceipt?(.photos) }.accessibilityIdentifier("guest.receipts.add.photos")
            Button(copy.chooseFile) { addReceipt?(.file) }.accessibilityIdentifier("guest.receipts.add.file")
            Button(copy.cancel, role: .cancel) {}
        }
        .confirmationDialog(copy.deleteTitle, isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }),
                            titleVisibility: .visible, presenting: deleting) { receipt in
            Button(copy.delete, role: .destructive) { try? store.delete(receipt.id) }
                .accessibilityIdentifier("guest.receipts.delete.confirm")
            Button(copy.cancel, role: .cancel) {}
        } message: { _ in Text(copy.deleteMessage) }
    }

    private func movementTitle(_ receipt: GuestReceipt) -> String? {
        guard let id = receipt.movementID, let movement = model.book.movement(id), !movement.deleted else { return nil }
        return GuestMovementPresentation.title(movement, spanish: spanish)
    }

    private func view(_ receipt: GuestReceipt) {
        guard let data = store.data(receipt) else { return }
        viewing = ViewedReceipt(id: receipt.id.uuidString, filename: receipt.name, mediaType: receipt.mediaType, data: data)
    }
}
