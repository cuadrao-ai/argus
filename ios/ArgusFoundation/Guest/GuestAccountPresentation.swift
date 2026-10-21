import Foundation
import CuadraoBook

/// The currency rules the shared money fields use inside the book: the server's set, each currency's exact digits,
/// and a ceiling that keeps totals inside Int64. The device's own currency data is never consulted.
enum GuestCurrencyRules {
    static let rules = make()

    /// The picker lists the whole table unless the host narrows it, as the plan form does to the currencies of the book's accounts.
    static func make(pickerCodes: [String]? = nil) -> CuadraoCurrencyRules { CuadraoCurrencyRules(
        digits: { CurrencyTable.digits($0) ?? 2 },
        maximum: { MinorUnits.decimal(Limits.maximumMinor, digits: CurrencyTable.digits($0) ?? 2) },
        maximumMessage: { code, spanish in
            (spanish ? "Máximo: " : "Maximum: ") + MoneyFormatter.grouped(Limits.maximumMinor, digits: CurrencyTable.digits(code) ?? 2)
        },
        format: { value, code in
            let digits = CurrencyTable.digits(code) ?? 2
            return MinorUnits.exactMinor(value, digits: digits).map { MoneyFormatter.grouped($0, digits: digits) } ?? ""
        },
        pickerCodes: { pickerCodes ?? CurrencyTable.pickerCodes }) }
}

/// How book accounts read on screen, and how a form's values become a draft. Pure; no view and no server model.
enum GuestAccountPresentation {
    static func artwork(_ kind: AccountKind) -> CanvasAccountKind {
        switch kind {
        case .cash: .cash
        case .checking: .checking
        case .savings: .savings
        case .investment: .investment
        case .creditCard: .card
        case .otherDebt: .loan
        case .property: .property
        case .vehicle: .vehicle
        case .otherAsset: .asset
        }
    }

    static func kind(_ canvas: CanvasAccountKind) -> AccountKind {
        switch canvas {
        case .cash: .cash
        case .checking: .checking
        case .savings: .savings
        case .investment: .investment
        case .card: .creditCard
        case .loan: .otherDebt
        case .property: .property
        case .vehicle: .vehicle
        case .asset: .otherAsset
        }
    }

    static func title(_ account: BookAccount, spanish: Bool) -> String {
        account.nickname ?? artwork(account.kind).title(spanish)
    }

    static func amount(_ account: BookAccount, in book: DeviceBook, spanish: Bool, locale: Locale) -> String {
        guard let balance = book.balance(of: account.id) else { return spanish ? "Saldo desconocido" : "Balance unknown" }
        return MoneyFormatter.grouped(balance.minor, digits: balance.digits,
                                      grouping: locale.groupingSeparator ?? ",", decimal: locale.decimalSeparator ?? ".")
    }

    private static func qualifier(_ account: BookAccount, in book: DeviceBook, spanish: Bool) -> String {
        guard let minor = book.balance(of: account.id)?.minor else { return "" }
        if account.kind == .creditCard, minor > 0 { return spanish ? " · a favor" : " · credit" }
        return minor < 0 ? (spanish ? " · pendiente" : " · owed") : ""
    }

    static func share(_ account: BookAccount, spanish: Bool) -> String? {
        guard account.kind.isOptionalAsset, account.ownershipShareBps != Ownership.fullShareBps else { return nil }
        let whole = account.ownershipShareBps / 100, part = account.ownershipShareBps % 100
        let text = part == 0 ? "\(whole)" : "\(whole).\(part < 10 ? "0" : "")\(part)"
        return (spanish ? "Tu parte: " : "Your share: ") + text + "%"
    }

    static func row(_ account: BookAccount, in book: DeviceBook, spanish: Bool, locale: Locale) -> CanvasAccountRowValue {
        var notes: [String] = []
        if let share = share(account, spanish: spanish) { notes.append(share) }
        if account.archived { notes.append(spanish ? "Archivada" : "Archived") }
        return CanvasAccountRowValue(title: title(account, spanish: spanish), subtitle: artwork(account.kind).title(spanish),
            artwork: artwork(account.kind), amount: amount(account, in: book, spanish: spanish, locale: locale),
            amountCaption: account.currency + qualifier(account, in: book, spanish: spanish),
            note: notes.isEmpty ? nil : notes.joined(separator: " · "))
    }

    static func detail(_ account: BookAccount, in book: DeviceBook, spanish: Bool, locale: Locale) -> CanvasAccountDetailValue {
        let shown = amount(account, in: book, spanish: spanish, locale: locale)
        let freshness: String
        if let opening = account.opening {
            let formatter = DateFormatter()
            formatter.locale = locale
            formatter.timeZone = TimeZone(identifier: opening.timeZone) ?? .current
            formatter.dateStyle = .medium
            freshness = (spanish ? "Seguimiento desde el " : "Tracked since ") + formatter.string(from: opening.asOf)
        } else {
            freshness = spanish ? "Sin balance registrado" : "No balance recorded"
        }
        var notes: [String] = []
        if let share = share(account, spanish: spanish) { notes.append(share) }
        if account.kind.isLiability {
            notes.append(spanish ? "Saldo con signo: un monto negativo indica dinero que debes."
                : "Signed balance: a negative amount means money owed.")
        }
        if book.hasRecords(account.id) {
            notes.append(spanish ? "La moneda y el tipo se conservan con el balance registrado."
                : "The currency and type are kept with the recorded balance.")
        }
        if account.archived { notes.append(spanish ? "Archivada. Se conservan el balance y el historial." : "Archived. Balance and history are kept.") }
        let label: String
        if account.kind.isLiability { label = spanish ? "Monto pendiente" : "Amount owed" }
        else if account.kind.isOptionalAsset { label = spanish ? "Valor estimado" : "Estimated value" }
        else { label = "Balance" }
        return CanvasAccountDetailValue(title: title(account, spanish: spanish), artwork: artwork(account.kind), balanceLabel: label,
            currency: account.currency, amount: shown, freshness: freshness, notes: notes,
            amountIdentifier: "guest.account.balance." + account.currency, amountAccessibilityLabel: account.currency + " " + shown)
    }

    // MARK: Form values

    static func draft(_ entry: CanvasAccountEntry) -> BookAccountDraft? {
        guard let canvas = entry.kind else { return nil }
        return BookAccountDraft(kind: kind(canvas), currency: entry.currency, nickname: entry.trimmedName,
                            amountText: entry.amount, shareBps: entry.sharePercent * 100)
    }

    /// What the form shows for an existing account: the typed form of its balance (a debt as a positive amount owed).
    static func entry(_ account: BookAccount, in book: DeviceBook) -> CanvasAccountEntry {
        var entry = CanvasAccountEntry()
        entry.kind = artwork(account.kind)
        entry.name = account.nickname ?? ""
        entry.currency = account.currency
        if let balance = book.balance(of: account.id) {
            entry.amount = MoneyFormatter.plain(account.kind.isLiability ? -balance.minor : balance.minor, digits: balance.digits)
        }
        let percent = account.ownershipShareBps / 100
        if account.ownershipShareBps % 100 == 0, [50, 100].contains(percent) {
            entry.share = percent
        } else {
            entry.sharingCustom = true
            entry.customShare = String(percent)
        }
        return entry
    }

    static func message(_ error: BookRuleError, currency: String, spanish: Bool) -> String {
        switch error {
        case .currencyUnsupported: spanish ? "Esa moneda no está disponible." : "That currency isn't available."
        case .nicknameTooLong: spanish ? "El nombre puede tener hasta \(Limits.nickname) caracteres." : "The name can have up to \(Limits.nickname) characters."
        case .amount(.invalid): spanish ? "Revisa el monto." : "Check the amount."
        case .amount(.precision(let digits)):
            spanish ? "\(currency) usa \(digits) decimales." : "\(currency) uses \(digits) decimal places."
        case .amount(.outOfRange), .amountTooLarge: spanish ? "El monto es demasiado grande." : "That amount is too large."
        case .negativeAmount: spanish ? "Escribe un monto positivo." : "Enter a positive amount."
        case .shareInvalid: spanish ? "Introduce tu parte, de 1 a 100%." : "Enter your share, from 1 to 100%."
        case .accountLimit: spanish ? "Llegaste al máximo de cuentas en este iPhone." : "You've reached the most accounts this iPhone can hold."
        case .currencyLocked: spanish ? "La moneda se conserva con el balance registrado." : "The currency is kept with the recorded balance."
        case .kindLocked: spanish ? "El tipo se conserva con el balance registrado." : "The type is kept with the recorded balance."
        case .amountNotPositive: spanish ? "Escribe un monto mayor que cero." : "Enter an amount above zero."
        case .futureDate: spanish ? "La fecha no puede ser futura." : "The date can't be in the future."
        case .beforeTracking:
            spanish ? "Esa fecha es anterior al inicio del seguimiento de la cuenta." : "That date is before the account's tracking began."
        case .accountArchived: spanish ? "Una cuenta archivada no recibe movimientos nuevos." : "An archived account takes no new activity."
        case .transferCurrencyMismatch: spanish ? "Las transferencias son entre cuentas de la misma moneda." : "Transfers are between accounts in the same currency."
        case .transferSameAccount: spanish ? "Elige una cuenta distinta para recibir." : "Choose a different account to receive it."
        case .movementLimit: spanish ? "Llegaste al máximo de movimientos en este iPhone." : "You've reached the most activity this iPhone can hold."
        case .noteTooLong: spanish ? "El concepto puede tener hasta \(Limits.note) caracteres." : "The description can have up to \(Limits.note) characters."
        case .accountNotFound, .orderInvalid, .movementNotFound, .planNameEmpty, .planLimit, .planNotFound, .planKindLocked, .planArchived, .scopeInvalid: spanish ? "No se pudo guardar. Inténtalo de nuevo." : "Couldn't save. Try again."
        }
    }
}
