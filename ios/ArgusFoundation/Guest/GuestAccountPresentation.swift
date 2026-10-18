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
            (CuadraoCopy.text("copy.guestAccountPresentation.b4d1df7fcf", spanish: spanish)) + MoneyFormatter.grouped(Limits.maximumMinor, digits: CurrencyTable.digits(code) ?? 2)
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
        guard let balance = book.balance(of: account.id) else { return CuadraoCopy.text("copy.connectedAccountPresentation.f91a22e211", spanish: spanish) }
        return MoneyFormatter.grouped(balance.minor, digits: balance.digits,
                                      grouping: locale.groupingSeparator ?? ",", decimal: locale.decimalSeparator ?? ".")
    }

    private static func qualifier(_ account: BookAccount, in book: DeviceBook, spanish: Bool) -> String {
        guard let minor = book.balance(of: account.id)?.minor else { return "" }
        if account.kind == .creditCard, minor > 0 { return CuadraoCopy.text("copy.connectedAccountPresentation.aed94b1b21", spanish: spanish) }
        return minor < 0 ? (CuadraoCopy.text("copy.connectedAccountPresentation.0a5b992f57", spanish: spanish)) : ""
    }

    static func share(_ account: BookAccount, spanish: Bool) -> String? {
        guard account.kind.isOptionalAsset, account.ownershipShareBps != Ownership.fullShareBps else { return nil }
        let whole = account.ownershipShareBps / 100, part = account.ownershipShareBps % 100
        let text = part == 0 ? "\(whole)" : "\(whole).\(part < 10 ? "0" : "")\(part)"
        return (CuadraoCopy.text("copy.connectedAccountPresentation.78b28cc9ef", spanish: spanish)) + text + "%"
    }

    static func row(_ account: BookAccount, in book: DeviceBook, spanish: Bool, locale: Locale) -> CanvasAccountRowValue {
        var notes: [String] = []
        if let share = share(account, spanish: spanish) { notes.append(share) }
        if account.archived { notes.append(CuadraoCopy.text("copy.connectedAccountPresentation.7268bbe2c2", spanish: spanish)) }
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
            freshness = (CuadraoCopy.text("copy.guestAccountPresentation.1013e187f0", spanish: spanish)) + formatter.string(from: opening.asOf)
        } else {
            freshness = CuadraoCopy.text("copy.connectedAccountPresentation.13cc4cd5c1", spanish: spanish)
        }
        var notes: [String] = []
        if let share = share(account, spanish: spanish) { notes.append(share) }
        if account.kind.isLiability {
            notes.append(CuadraoCopy.text("copy.connectedAccountPresentation.16dda57178", spanish: spanish))
        }
        if book.hasRecords(account.id) {
            notes.append(CuadraoCopy.text("copy.guestAccountPresentation.acf561eab5", spanish: spanish))
        }
        if account.archived { notes.append(CuadraoCopy.text("copy.connectedAccountPresentation.130abf6051", spanish: spanish)) }
        let label: String
        if account.kind.isLiability { label = CuadraoCopy.text("copy.cuadraoFirstAccountSheet.3bf64e270f", spanish: spanish) }
        else if account.kind.isOptionalAsset { label = CuadraoCopy.text("copy.guestAccountPresentation.d7a2d9accc", spanish: spanish) }
        else { label = CuadraoCopy.text("copy.guestAccountPresentation.02e2073456", spanish: CuadraoCopy.isSpanish()) }
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
        case .currencyUnsupported: CuadraoCopy.text("copy.guestAccountPresentation.4176befe0e", spanish: spanish)
        case .nicknameTooLong: CuadraoCopy.text("copy.guestAccountPresentation.40b1f4b87f", spanish: spanish, String(describing: Limits.nickname))
        case .amount(.invalid): CuadraoCopy.text("copy.guestAccountPresentation.159584f850", spanish: spanish)
        case .amount(.precision(let digits)):
            CuadraoCopy.text("copy.guestAccountPresentation.1aea4f003a", spanish: spanish, String(describing: currency), String(describing: digits))
        case .amount(.outOfRange), .amountTooLarge: CuadraoCopy.text("copy.guestAccountPresentation.7971778570", spanish: spanish)
        case .negativeAmount: CuadraoCopy.text("copy.guestAccountPresentation.977ba4587c", spanish: spanish)
        case .shareInvalid: CuadraoCopy.text("copy.cuadraoFirstAccountSheet.d99eaf19c2", spanish: spanish)
        case .accountLimit: CuadraoCopy.text("copy.guestAccountPresentation.c5b7ffa0e2", spanish: spanish)
        case .currencyLocked: CuadraoCopy.text("copy.guestAccountPresentation.a68f50c3a1", spanish: spanish)
        case .kindLocked: CuadraoCopy.text("copy.guestAccountPresentation.62cdfd697a", spanish: spanish)
        case .amountNotPositive: CuadraoCopy.text("copy.guestAccountPresentation.5e3ea1738d", spanish: spanish)
        case .futureDate: CuadraoCopy.text("copy.guestAccountPresentation.92f564ce61", spanish: spanish)
        case .beforeTracking:
            CuadraoCopy.text("copy.guestAccountPresentation.6b7ffed64b", spanish: spanish)
        case .accountArchived: CuadraoCopy.text("copy.guestAccountPresentation.e9f1f89f52", spanish: spanish)
        case .transferCurrencyMismatch: CuadraoCopy.text("copy.guestAccountPresentation.7329e7f2b2", spanish: spanish)
        case .transferSameAccount: CuadraoCopy.text("copy.guestAccountPresentation.80ed4244c4", spanish: spanish)
        case .movementLimit: CuadraoCopy.text("copy.guestAccountPresentation.90c3c20725", spanish: spanish)
        case .noteTooLong: CuadraoCopy.text("copy.guestAccountPresentation.f7a1962aa0", spanish: spanish, String(describing: Limits.note))
        case .accountNotFound, .orderInvalid, .movementNotFound, .planNameEmpty, .planLimit, .planNotFound, .planKindLocked, .planArchived, .scopeInvalid: CuadraoCopy.text("copy.guestAccountPresentation.c7aaa1eb33", spanish: spanish)
        }
    }
}
