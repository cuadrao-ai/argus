import SwiftUI
import CuadraoBook

/// Records or edits one movement in the shared transaction sheet: kind, account, amount in that account's exact digits,
/// a date that cannot be in the future, a category for expenses and a short description. One step, one Save.
struct GuestMovementSheet: View {
    enum Mode: Identifiable, Equatable {
        case create(account: UUID?)
        case edit(UUID)
        var id: String {
            switch self {
            case .create(let account): "create." + (account?.uuidString ?? "any")
            case .edit(let id): "edit." + id.uuidString
            }
        }
    }

    @ObservedObject var model: GuestBookModel
    let mode: Mode
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var kind: MovementKind
    @State private var accountID: UUID
    @State private var counterpartID: UUID?
    @State private var amount: String
    @State private var amountError = ""
    @State private var date: Date
    @State private var note: String
    @State private var category: ExpenseCategory
    @State private var status: String?
    @FocusState private var noteFocused: Bool

    init(model: GuestBookModel, mode: Mode, spanish: Bool) {
        self.model = model
        self.mode = mode
        self.spanish = spanish
        let book = model.book
        switch mode {
        case .create(let preferred):
            let first = preferred.flatMap { book.account($0) }.flatMap { $0.archived ? nil : $0 } ?? book.activeAccounts.first
            _kind = State(initialValue: .expense)
            _accountID = State(initialValue: first?.id ?? UUID())
            _counterpartID = State(initialValue: nil)
            _amount = State(initialValue: "")
            _date = State(initialValue: Date())
            _note = State(initialValue: "")
            _category = State(initialValue: .other)
        case .edit(let id):
            let movement = book.movement(id)
            let digits = movement.flatMap { book.account($0.accountID)?.digits } ?? 2
            _kind = State(initialValue: movement?.kind ?? .expense)
            _accountID = State(initialValue: movement?.accountID ?? UUID())
            _counterpartID = State(initialValue: movement?.counterpartID)
            _amount = State(initialValue: movement.map { MoneyFormatter.plain($0.amountMinor, digits: digits) } ?? "")
            _date = State(initialValue: movement?.occurredAt ?? Date())
            _note = State(initialValue: movement?.note ?? "")
            _category = State(initialValue: movement?.category ?? .other)
        }
    }

    private var editedID: UUID? {
        if case .edit(let id) = mode { return id }
        return nil
    }

    private var book: DeviceBook { model.book }
    private var account: BookAccount? { book.account(accountID) }

    /// Accounts the person can pick: active ones, plus the movement's own account when editing so it never vanishes.
    private var choices: [BookAccount] {
        book.accounts.filter { !$0.archived || $0.id == accountID }
    }

    private var destinations: [BookAccount] {
        book.activeAccounts.filter { $0.id != accountID && $0.currency == account?.currency }
    }

    private var tracking: Date? {
        [account?.opening?.asOf, kind == .transfer ? counterpartID.flatMap { book.account($0)?.opening?.asOf } : nil].compactMap { $0 }.max()
    }

    private var valid: Bool {
        guard let account, !amount.isEmpty, amountError.isEmpty,
              case .success(let minor) = MoneyParser.parseTyped(amount, digits: account.digits), minor > 0 else { return false }
        return kind != .transfer || counterpartID != nil
    }

    var body: some View {
        CuadraoTransactionSheet(
            account: CuadraoTransactionAccount(title: account.map { GuestAccountPresentation.title($0, spanish: spanish) } ?? "",
                                               artwork: account.map { GuestAccountPresentation.artwork($0.kind) }),
            spanish: spanish, reviewing: false,
            title: editedID == nil ? (spanish ? "Añadir movimiento" : "Add transaction") : (spanish ? "Editar movimiento" : "Edit transaction"),
            primaryTitle: spanish ? "Guardar" : "Save", primaryEnabled: valid, primaryIdentifier: "guest.movement.save",
            back: {}, primary: save) {
            content
        }
        .cuadraoFormKeyboard()
        .onChange(of: accountID) { _, _ in fixDestination() }
        .onChange(of: kind) { _, _ in fixDestination(); status = nil }
        .onChange(of: amount) { _, _ in status = nil }
        .onAppear { fixDestination() }
    }

    private func fixDestination() {
        guard kind == .transfer else { return }
        if let current = counterpartID, destinations.contains(where: { $0.id == current }) { return }
        counterpartID = destinations.first?.id
    }

    @ViewBuilder private var content: some View {
        kindRow
        choice(kind == .transfer ? (spanish ? "Desde" : "From") : (spanish ? "Cuenta" : "Account"),
               selection: $accountID, values: choices.map(\.id), id: "guest.movement.account") {
            GuestMovementPresentation.accountTitle($0, in: book, spanish: spanish)
        }
        if kind == .transfer {
            if destinations.isEmpty {
                Text(spanish ? "Necesitas otra cuenta en \(account?.currency ?? "") para transferir."
                     : "You need another \(account?.currency ?? "") account to transfer.")
                    .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("guest.movement.noDestination")
            } else {
                choice(spanish ? "Hacia" : "To", selection: Binding(get: { counterpartID ?? destinations[0].id }, set: { counterpartID = $0 }),
                       values: destinations.map(\.id), id: "guest.movement.destination") {
                    GuestMovementPresentation.accountTitle($0, in: book, spanish: spanish)
                }
            }
        }
        CuadraoAmountField(raw: $amount, currency: .constant(account?.currency ?? "DOP"), error: $amountError, spanish: spanish,
                           currencySelectable: false, identifier: "guest.movement.amount")
        DatePicker(spanish ? "Fecha" : "Date", selection: $date, in: (tracking ?? .distantPast)...Date(), displayedComponents: .date)
            .accessibilityIdentifier("guest.movement.date")
        if kind == .expense {
            choice(spanish ? "Categoría" : "Category", selection: $category, values: ExpenseCategory.allCases,
                   id: "guest.movement.category") { GuestMovementPresentation.categoryTitle($0, spanish: spanish) }
        }
        VStack(alignment: .leading, spacing: 8) {
            TextField(spanish ? "Concepto (opcional)" : "Description (optional)", text: $note, axis: .vertical)
                .focused($noteFocused).lineLimit(1...4).modifier(RegistrationField())
                .accessibilityIdentifier("guest.movement.note")
            Text("\(note.unicodeScalars.count)/\(Limits.note)").font(.caption)
                .foregroundStyle(note.unicodeScalars.count > Limits.note ? .red : .secondary)
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
        if let status {
            Text(status).font(.subheadline).foregroundStyle(.red).accessibilityIdentifier("guest.movement.error")
        }
    }

    private var kindRow: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 8) {
                ForEach(MovementKind.allCases, id: \.self) { item in
                    Button { kind = item } label: {
                        Text(GuestMovementPresentation.kindTitle(item, spanish: spanish)).font(.subheadline)
                            .padding(.horizontal, 14).frame(minHeight: 44)
                            .foregroundStyle(kind == item ? WelcomePalette.onAccent : WelcomePalette.ink)
                            .background(kind == item ? WelcomePalette.pine : WelcomePalette.surface, in: Capsule())
                    }.accessibilityIdentifier("guest.movement.kind." + item.rawValue)
                        .accessibilityAddTraits(kind == item ? .isSelected : [])
                }
            }
        }.scrollIndicators(.hidden)
    }

    private func choice<Value: Hashable>(_ caption: String, selection: Binding<Value>, values: [Value], id: String,
                                         title: @escaping (Value) -> String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(caption).font(.caption).foregroundStyle(.secondary)
            CuadraoChoiceMenu(title: caption, selection: selection, values: values, valueTitle: title)
                .accessibilityIdentifier(id)
        }
    }

    private func save() {
        noteFocused = false
        let draft = MovementDraft(kind: kind, accountID: accountID, counterpartID: kind == .transfer ? counterpartID : nil,
                                  amountText: amount, occurredAt: date, note: note, category: category)
        do {
            try model.apply { book in
                if let id = editedID { return try book.editingMovement(id, with: draft) }
                return try book.recordingMovement(draft)
            }
            dismiss()
        } catch let error as BookRuleError {
            status = GuestAccountPresentation.message(error, currency: account?.currency ?? "", spanish: spanish)
        } catch {
            status = GuestAccountPresentation.message(.movementNotFound, currency: "", spanish: spanish)
        }
    }
}
