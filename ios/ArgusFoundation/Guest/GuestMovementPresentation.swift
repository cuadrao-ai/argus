import SwiftUI
import CuadraoBook

/// How the book's movements read on screen. Pure, with no view and no server model.
enum GuestMovementPresentation {
    static func kindTitle(_ kind: MovementKind, spanish: Bool) -> String {
        switch kind {
        case .expense: spanish ? "Gasto" : "Expense"
        case .income: spanish ? "Ingreso" : "Income"
        case .transfer: spanish ? "Transferencia" : "Transfer"
        }
    }

    static func symbol(_ kind: MovementKind) -> String {
        switch kind {
        case .expense: "arrow.up.right"
        case .income: "arrow.down.left"
        case .transfer: "arrow.left.arrow.right"
        }
    }

    static func categoryTitle(_ category: ExpenseCategory, spanish: Bool) -> String {
        switch category {
        case .other: spanish ? "Otros" : "Other"
        case .groceries: spanish ? "Supermercado" : "Groceries"
        case .dining: spanish ? "Comida fuera" : "Dining out"
        case .transport: spanish ? "Transporte" : "Transport"
        case .housing: spanish ? "Vivienda" : "Housing"
        case .health: spanish ? "Salud" : "Health"
        case .shopping: spanish ? "Compras" : "Shopping"
        case .interestFees: spanish ? "Intereses y cargos" : "Interest and fees"
        }
    }

    static func categoryColor(_ category: ExpenseCategory) -> Color {
        switch category {
        case .other: WelcomePalette.ink.opacity(0.5)
        case .groceries: WelcomePalette.pine
        case .dining: WelcomePalette.clay
        case .transport: WelcomePalette.sunshine
        case .housing: WelcomePalette.bloom
        case .health: WelcomePalette.overlap
        case .shopping: WelcomePalette.moneyInput
        case .interestFees: WelcomePalette.owedNegative
        }
    }

    static func accountTitle(_ id: UUID?, in book: DeviceBook, spanish: Bool) -> String {
        guard let id, let account = book.account(id) else { return spanish ? "Cuenta" : "Account" }
        return GuestAccountPresentation.title(account, spanish: spanish)
    }

    static func title(_ movement: Movement, spanish: Bool) -> String {
        movement.note ?? movement.category.map { categoryTitle($0, spanish: spanish) } ?? kindTitle(movement.kind, spanish: spanish)
    }

    static func date(_ movement: Movement, locale: Locale, style: DateFormatter.Style = .medium) -> String {
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = TimeZone(identifier: movement.timeZone) ?? .current
        formatter.dateStyle = style
        formatter.timeStyle = .none
        return formatter.string(from: movement.occurredAt)
    }

    /// The sign is how the money moved for the account the row is shown for; Home shows a transfer without one.
    static func sign(_ movement: Movement, perspective account: UUID?) -> String {
        switch movement.kind {
        case .expense: return "\u{2212}"
        case .income: return "+"
        case .transfer:
            guard let account else { return "" }
            return movement.accountID == account ? "\u{2212}" : "+"
        }
    }

    static func amount(_ movement: Movement, in book: DeviceBook, locale: Locale) -> String {
        let digits = book.account(movement.accountID)?.digits ?? 2
        return MoneyFormatter.grouped(movement.amountMinor, digits: digits,
                                      grouping: locale.groupingSeparator ?? ",", decimal: locale.decimalSeparator ?? ".")
    }

    /// One feed row: what it was, where and when, and the signed amount with its currency.
    static func row(_ movement: Movement, in book: DeviceBook, perspective account: UUID? = nil, spanish: Bool, locale: Locale)
        -> (title: String, detail: String, amount: String, icon: String) {
        let currency = book.account(movement.accountID)?.currency ?? ""
        var place = accountTitle(movement.accountID, in: book, spanish: spanish)
        if movement.kind == .transfer {
            place += " \u{2192} " + accountTitle(movement.counterpartID, in: book, spanish: spanish)
        }
        return (title(movement, spanish: spanish), place + " \u{00B7} " + date(movement, locale: locale),
                sign(movement, perspective: account) + amount(movement, in: book, locale: locale) + " " + currency, symbol(movement.kind))
    }
}

/// What a closed sheet changed in the book, read from the book before and after. Pure.
struct GuestSaveNotice: Equatable {
    enum Subject: Equatable { case movement, account, plan, contribution }
    let subject: Subject
    let id: UUID
    let created: Bool

    static func between(_ before: DeviceBook, _ after: DeviceBook, subject: Subject, planID: UUID? = nil) -> GuestSaveNotice? {
        switch subject {
        case .movement: change(before.movements, after.movements, subject)
        case .account: change(before.accounts, after.accounts, subject)
        case .plan: change(before.plans, after.plans, subject)
        case .contribution:
            planID.flatMap { id in
                guard let new = change(before.plan(id)?.contributions ?? [], after.plan(id)?.contributions ?? [], subject) else { return nil }
                return GuestSaveNotice(subject: .contribution, id: new.id, created: new.created)
            }
        }
    }

    private static func change<T: Identifiable & Equatable>(_ before: [T], _ after: [T], _ subject: Subject) -> GuestSaveNotice? where T.ID == UUID {
        let known = Dictionary(uniqueKeysWithValues: before.map { ($0.id, $0) })
        if let new = after.first(where: { known[$0.id] == nil }) { return GuestSaveNotice(subject: subject, id: new.id, created: true) }
        if let edited = after.first(where: { item in known[item.id].map { $0 != item } ?? false }) {
            return GuestSaveNotice(subject: subject, id: edited.id, created: false)
        }
        return nil
    }

    func text(spanish: Bool) -> String {
        switch (subject, created) {
        case (.movement, true): spanish ? "Movimiento guardado" : "Transaction saved"
        case (.account, true): spanish ? "Cuenta añadida" : "Account added"
        case (.plan, true): spanish ? "Plan creado" : "Plan created"
        case (.contribution, _): spanish ? "Aporte guardado" : "Contribution saved"
        default: spanish ? "Cambios guardados" : "Changes saved"
        }
    }
}
