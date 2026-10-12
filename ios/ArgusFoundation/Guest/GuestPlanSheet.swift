import SwiftUI
import CuadraoBook

/// The shared plan editor, offering only the two kinds the book has and the currencies of its own accounts. It saves to the
/// book; a budget's account and category scope are extra fields beside the shared ones.
struct GuestPlanSheet: View {
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
    @State private var accountScope: [UUID]
    @State private var categoryScope: [ExpenseCategory]
    @State private var status: String?
    private let initial: CanvasPlan

    init(model: GuestBookModel, mode: Mode, spanish: Bool) {
        self.model = model
        self.mode = mode
        self.spanish = spanish
        switch mode {
        case .create:
            var fresh = CanvasPlan(name: "", spaceID: CanvasSpace.personalID)
            fresh.currency = model.book.currencies.first ?? CurrencyTable.priority[0]
            initial = fresh
            _accountScope = State(initialValue: [])
            _categoryScope = State(initialValue: [])
        case .edit(let id):
            let plan = model.book.plan(id)
            initial = plan.map(GuestPlanPresentation.canvas) ?? CanvasPlan(name: "", spaceID: CanvasSpace.personalID)
            _accountScope = State(initialValue: plan?.accountScope ?? [])
            _categoryScope = State(initialValue: plan?.categoryScope ?? [])
        }
    }

    private var editedID: UUID? {
        if case .edit(let id) = mode { return id }
        return nil
    }

    private var host: CuadraoPlanEditorHost {
        var host = CuadraoPlanEditorHost(
            spaces: [CuadraoPlanEditorSpace(id: CanvasSpace.personalID, title: spanish ? "Este iPhone" : "This iPhone")],
            editing: editedID != nil, save: { plan in save(plan) })
        host.allowedKinds = [.goal, .budget]
        host.showsRecorded = false
        host.showsRate = false
        host.dismissesOnSave = false
        host.identifiers = CuadraoPlanEditorIdentifiers(name: "guest.plan.name", target: "guest.plan.target", monthly: "guest.plan.monthly",
            rate: "guest.plan.rate", currency: "guest.plan.currency", save: "guest.plan.save",
            kind: { "guest.plan.kind." + $0.rawValue })
        host.monthlyTitle = spanish ? "Aporte mensual previsto" : "Planned monthly contribution"
        return host
    }

    var body: some View {
        CuadraoPlanEditor(host: host, initial: initial, spanish: spanish) { draft in
            GuestPlanScope(book: model.book, kind: draft.wrappedValue.kind, currency: draft.wrappedValue.currency, spanish: spanish,
                           accounts: $accountScope, categories: $categoryScope)
        } footer: {
            if let status {
                Text(status).font(.subheadline).foregroundStyle(.red).accessibilityIdentifier("guest.plan.error")
            }
        }
        .environment(\.cuadraoCurrencyRules, GuestCurrencyRules.make(pickerCodes: model.book.currencies))
    }

    private func save(_ plan: CanvasPlan) {
        let draft = GuestPlanPresentation.draft(plan, accountScope: plan.kind == .budget ? accountScope : [],
                                                categoryScope: plan.kind == .budget ? categoryScope : [])
        do {
            try model.apply { book in
                if let id = editedID { return try book.editingPlan(id, with: draft) }
                return try book.addingPlan(draft)
            }
            dismiss()
        } catch let error as BookRuleError {
            status = GuestPlanPresentation.message(error, currency: plan.currency, spanish: spanish)
        } catch {
            status = GuestPlanPresentation.message(.planNotFound, currency: plan.currency, spanish: spanish)
        }
    }
}

/// A budget's scope: which accounts and which categories it counts. Empty means all of them.
private struct GuestPlanScope: View {
    let book: DeviceBook
    let kind: CanvasPlanKind
    let currency: String
    let spanish: Bool
    @Binding var accounts: [UUID]
    @Binding var categories: [ExpenseCategory]

    private var choices: [BookAccount] { book.activeAccounts.filter { $0.currency == currency } }

    var body: some View {
        if kind == .budget {
            VStack(alignment: .leading, spacing: 12) {
                DisclosureGroup {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(choices) { account in
                            toggle(GuestAccountPresentation.title(account, spanish: spanish), on: accounts.contains(account.id),
                                   id: "guest.plan.scope.account." + account.id.uuidString) {
                                if let index = accounts.firstIndex(of: account.id) { accounts.remove(at: index) } else { accounts.append(account.id) }
                            }
                        }
                    }.padding(.top, 8)
                } label: {
                    summary(spanish ? "Cuentas" : "Accounts", count: accounts.count, all: spanish ? "Todas en \(currency)" : "All in \(currency)")
                        .accessibilityIdentifier("guest.plan.scope.accounts")
                }
                DisclosureGroup {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(ExpenseCategory.allCases, id: \.self) { category in
                            toggle(GuestMovementPresentation.categoryTitle(category, spanish: spanish), on: categories.contains(category),
                                   id: "guest.plan.scope.category." + category.rawValue) {
                                if let index = categories.firstIndex(of: category) { categories.remove(at: index) } else { categories.append(category) }
                            }
                        }
                    }.padding(.top, 8)
                } label: {
                    summary(spanish ? "Categorías" : "Categories", count: categories.count, all: spanish ? "Todas" : "All")
                        .accessibilityIdentifier("guest.plan.scope.categories")
                }
                Text(spanish ? "Cuenta los gastos que registres en estas cuentas y categorías este mes. Sin elegir, cuenta todos."
                     : "Counts the expenses you record in these accounts and categories this month. With none chosen, it counts all of them.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func summary(_ title: String, count: Int, all: String) -> some View {
        HStack {
            Text(title).font(.subheadline.weight(.medium))
            Spacer()
            Text(count == 0 ? all : (spanish ? "\(count) elegidas" : "\(count) chosen")).font(.subheadline).foregroundStyle(.secondary)
        }.frame(minHeight: 44)
    }

    private func toggle(_ title: String, on: Bool, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack {
                Text(title).foregroundStyle(.primary)
                Spacer()
                if on { Image(systemName: "checkmark").foregroundStyle(WelcomePalette.pine).accessibilityHidden(true) }
            }.frame(minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier(id).accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// Records money set aside toward a goal, in the shared sheet container.
struct GuestContributionSheet: View {
    @ObservedObject var model: GuestBookModel
    let planID: UUID
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var amount = ""
    @State private var amountError = ""
    @State private var date = Date()
    @State private var note = ""
    @State private var status: String?

    private var plan: BookPlan? { model.book.plan(planID) }

    private var valid: Bool {
        guard let plan, !amount.isEmpty, amountError.isEmpty,
              case .success(let minor) = MoneyParser.parseTyped(amount, digits: plan.digits), minor > 0 else { return false }
        return true
    }

    var body: some View {
        CuadraoTransactionSheet(
            account: CuadraoTransactionAccount(title: plan?.name ?? "", artwork: nil, symbol: "flag"),
            spanish: spanish, reviewing: false, title: spanish ? "Añadir aporte" : "Add contribution",
            primaryTitle: spanish ? "Guardar" : "Save", primaryEnabled: valid, primaryIdentifier: "guest.contribution.save",
            back: {}, primary: save) {
            CuadraoAmountField(raw: $amount, currency: .constant(plan?.currency ?? "DOP"), error: $amountError, spanish: spanish,
                               currencySelectable: false, identifier: "guest.contribution.amount")
            DatePicker(spanish ? "Fecha" : "Date", selection: $date, in: ...Date(), displayedComponents: .date)
                .accessibilityIdentifier("guest.contribution.date")
            VStack(alignment: .leading, spacing: 8) {
                TextField(spanish ? "Nota (opcional)" : "Note (optional)", text: $note, axis: .vertical)
                    .lineLimit(1...3).modifier(RegistrationField()).accessibilityIdentifier("guest.contribution.note")
            }
            if let status {
                Text(status).font(.subheadline).foregroundStyle(.red).accessibilityIdentifier("guest.contribution.error")
            }
        }.onChange(of: amount) { _, _ in status = nil }
    }

    private func save() {
        do {
            try model.apply { try $0.addingContribution(to: planID, amountText: amount, occurredAt: date, note: note) }
            dismiss()
        } catch let error as BookRuleError {
            status = GuestPlanPresentation.message(error, currency: plan?.currency ?? "", spanish: spanish)
        } catch {
            status = GuestPlanPresentation.message(.planNotFound, currency: "", spanish: spanish)
        }
    }
}
