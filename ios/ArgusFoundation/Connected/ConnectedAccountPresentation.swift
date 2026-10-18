import SwiftUI
import ArgusSession

struct ConnectedAccountRow: View {
    let account: FinancialAccount
    let spanish: Bool
    @Environment(\.locale) private var locale

    var body: some View {
        CanvasAccountRowContent(value: ConnectedAccountPresentation.row(account, spanish: spanish, locale: locale))
    }
}

@MainActor
enum ConnectedAccountPresentation {
    static func artwork(_ type: String) -> CanvasAccountKind? {
        switch type {
        case "cash": .cash
        case "checking": .checking
        case "savings": .savings
        case "investment": .investment
        case "credit_card": .card
        case "other_debt": .loan
        case "property": .property
        case "vehicle": .vehicle
        case "other_asset": .asset
        default: nil
        }
    }

    nonisolated static func type(_ kind: CanvasAccountKind) -> String {
        switch kind {
        case .cash: "cash"
        case .checking: "checking"
        case .savings: "savings"
        case .investment: "investment"
        case .card: "credit_card"
        case .loan: "other_debt"
        case .property: "property"
        case .vehicle: "vehicle"
        case .asset: "other_asset"
        }
    }

    static func title(_ account: FinancialAccount, spanish: Bool) -> String {
        account.nickname ?? artwork(account.type)?.title(spanish) ?? (CuadraoCopy.text("copy.connectedAccountPresentation.f9d32ca2e5", spanish: spanish))
    }

    static func row(_ account: FinancialAccount, spanish: Bool, locale: Locale) -> CanvasAccountRowValue {
        var notes: [String] = []
        if account.isOptionalAsset { notes.append(NSLocalizedString("assets.whole", comment: "")) }
        if account.ownershipShareBps != 10000 { notes.append(share(account, spanish: spanish, locale: locale)) }
        if account.archived { notes.append(CuadraoCopy.text("copy.connectedAccountPresentation.7268bbe2c2", spanish: spanish)) }
        let qualifier: String
        if account.balance.state == .known, account.type == "credit_card", (account.balance.creditMinor ?? 0) > 0 {
            qualifier = CuadraoCopy.text("copy.connectedAccountPresentation.aed94b1b21", spanish: spanish)
        } else if account.balance.state == .known, (account.balance.amountMinor ?? 0) < 0 {
            qualifier = CuadraoCopy.text("copy.connectedAccountPresentation.0a5b992f57", spanish: spanish)
        } else { qualifier = "" }
        return CanvasAccountRowValue(
            title: title(account, spanish: spanish),
            subtitle: artwork(account.type)?.title(spanish) ?? account.type,
            artwork: artwork(account.type), amount: amount(account, spanish: spanish, locale: locale),
            amountCaption: account.currency + qualifier, note: notes.isEmpty ? nil : notes.joined(separator: " · "))
    }

    static func detail(_ account: FinancialAccount, spanish: Bool, locale: Locale) -> CanvasAccountDetailValue {
        let known = account.balance.state == .known
        let formatted = amount(account, spanish: spanish, locale: locale)
        let freshness: String
        if known, let asOf = account.balance.asOf {
            freshness = (CuadraoCopy.text("copy.connectedAccountPresentation.9fe77c6cda", spanish: spanish)) + AccountPresentation.date(asOf, zone: TimeZone.current.identifier, locale: locale)
        } else if known {
            freshness = CuadraoCopy.text("copy.connectedAccountPresentation.dc8a424b53", spanish: spanish)
        } else {
            freshness = CuadraoCopy.text("copy.connectedAccountPresentation.13cc4cd5c1", spanish: spanish)
        }
        var notes = [share(account, spanish: spanish, locale: locale)]
        if known, account.type == "credit_card", (account.balance.creditMinor ?? 0) > 0 {
            notes.append(CuadraoCopy.text("copy.connectedAccountPresentation.08362a6f74", spanish: spanish))
        } else if account.nature == "liability" {
            notes.append(CuadraoCopy.text("copy.connectedAccountPresentation.16dda57178", spanish: spanish))
        }
        if account.archived { notes.append(CuadraoCopy.text("copy.connectedAccountPresentation.130abf6051", spanish: spanish)) }
        return CanvasAccountDetailValue(title: title(account, spanish: spanish), artwork: artwork(account.type),
            balanceLabel: CuadraoCopy.text("copy.connectedAccountPresentation.02e2073456", spanish: CuadraoCopy.isSpanish()), currency: account.currency, amount: formatted,
            freshness: freshness, notes: notes, amountIdentifier: "accounts.balance." + account.currency,
            amountAccessibilityLabel: account.currency + " " + formatted)
    }

    private static func amount(_ account: FinancialAccount, spanish: Bool, locale: Locale) -> String {
        guard account.balance.state == .known, let amount = account.balance.amount else {
            return CuadraoCopy.text("copy.connectedAccountPresentation.f91a22e211", spanish: spanish)
        }
        return AccountPresentation.amount(amount, locale: locale)
    }

    private static func share(_ account: FinancialAccount, spanish: Bool, locale: Locale) -> String {
        (CuadraoCopy.text("copy.connectedAccountPresentation.78b28cc9ef", spanish: spanish))
            + AccountPresentation.amount(AssetShareControl.percent(account.ownershipShareBps), locale: locale) + "%"
    }
}

extension AccountDraft {
    /// The canvas entry holds a plain "1234.56" amount, so the create saves with a POSIX locale.
    mutating func apply(_ entry: CanvasAccountEntry) {
        guard let kind = entry.kind else { return }
        type = ConnectedAccountPresentation.type(kind)
        nickname = entry.trimmedName
        currency = entry.currency
        amount = entry.amount
        share = kind.isAsset ? String(entry.sharePercent) : "100"
    }
}
