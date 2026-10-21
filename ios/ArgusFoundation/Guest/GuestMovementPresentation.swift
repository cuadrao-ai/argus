import SwiftUI
import CuadraoBook

/// How the book's movements read on screen. Pure, with no view and no server model.
enum GuestMovementPresentation {
    static func kindTitle(_ kind: MovementKind, spanish: Bool) -> String {
        switch kind {
        case .expense: CuadraoCopy.text("copy.cuadraoAccountCanvas.705df72a66", spanish: spanish)
        case .income: CuadraoCopy.text("copy.cuadraoAccountCanvas.68048ec6e6", spanish: spanish)
        case .transfer: CuadraoCopy.text("copy.guestMovementPresentation.f860210241", spanish: spanish)
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
        case .other: CuadraoCopy.text("copy.guestMovementPresentation.08ceb8c09d", spanish: spanish)
        case .groceries: CuadraoCopy.text("copy.cuadraoAccountsPreview.34164df7c7", spanish: spanish)
        case .dining: CuadraoCopy.text("copy.guestMovementPresentation.ef1338cbc8", spanish: spanish)
        case .transport: CuadraoCopy.text("copy.guestMovementPresentation.f74da3b9d7", spanish: spanish)
        case .housing: CuadraoCopy.text("copy.guestMovementPresentation.22bf59e2ad", spanish: spanish)
        case .health: CuadraoCopy.text("copy.guestMovementPresentation.3a0e5f831d", spanish: spanish)
        case .shopping: CuadraoCopy.text("copy.guestMovementPresentation.5f2fe9268b", spanish: spanish)
        case .interestFees: CuadraoCopy.text("copy.guestMovementPresentation.f0080ec33b", spanish: spanish)
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
        guard let id, let account = book.account(id) else { return CuadraoCopy.text("copy.connectedAccountPresentation.f9d32ca2e5", spanish: spanish) }
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
