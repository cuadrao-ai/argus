import SwiftUI
import CuadraoBook

/// The shared account form, filled from and saved to the book. Creating starts in the preferred currency; editing keeps
/// the currency and type fixed once the account has a recorded balance.
struct GuestAccountSheet: View {
    enum Mode: Identifiable, Equatable {
        case create
        case edit(UUID)
        var id: String {
            switch self {
            case .create: "create"
            case .edit(let id): "edit." + id.uuidString
            }
        }
    }

    @ObservedObject var model: GuestBookModel
    let mode: Mode
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var entry: CanvasAccountEntry
    @State private var status: String?

    init(model: GuestBookModel, mode: Mode, spanish: Bool) {
        self.model = model
        self.mode = mode
        self.spanish = spanish
        switch mode {
        case .create:
            var fresh = CanvasAccountEntry()
            fresh.currency = model.book.settings.primaryCurrency ?? CurrencyTable.priority[0]
            _entry = State(initialValue: fresh)
        case .edit(let id):
            _entry = State(initialValue: model.book.account(id).map { GuestAccountPresentation.entry($0, in: model.book) } ?? CanvasAccountEntry())
        }
    }

    private var editedID: UUID? {
        if case .edit(let id) = mode { return id }
        return nil
    }

    private var locked: Bool { editedID.map { model.book.hasRecords($0) } ?? false }

    var body: some View {
        CuadraoAccountEntryForm(entry: $entry, spaceTitle: spanish ? "Este iPhone" : "This iPhone", spanish: spanish,
            editing: editedID != nil, ids: .guest, status: status, statusIdentifier: "guest.account.error",
            currencySelectable: !locked, kindLocked: locked,
            lockNote: locked ? (spanish ? "La moneda y el tipo se conservan con el balance registrado."
                                : "The currency and type are kept with the recorded balance.") : nil,
            cancel: { dismiss() }) { save() }
            .onChange(of: entry) { _, _ in status = nil }
    }

    private func save() {
        guard let draft = GuestAccountPresentation.draft(entry) else { return }
        do {
            try model.apply { book in
                if let id = editedID { return try book.editingAccount(id, with: draft) }
                return try book.addingAccount(draft)
            }
            dismiss()
        } catch let error as BookRuleError {
            status = GuestAccountPresentation.message(error, currency: draft.currency, spanish: spanish)
        } catch {
            status = GuestAccountPresentation.message(.accountNotFound, currency: draft.currency, spanish: spanish)
        }
    }
}

private extension CanvasAccountEntryIDs {
    static var guest: CanvasAccountEntryIDs {
        CanvasAccountEntryIDs(type: { "guest.account.type." + GuestAccountPresentation.kind($0).rawValue },
            typeChange: "guest.account.type.change", otherAssets: "guest.account.otherAssets", name: "guest.account.name",
            amount: "guest.account.amount", currency: "guest.account.currency", share: "guest.account.share",
            save: "guest.account.save", cancel: "guest.account.cancel")
    }
}
