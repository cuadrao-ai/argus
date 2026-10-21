import Foundation
import ArgusSession

/// The one rule for adding a movement, and it never asks first: no account starts the first-account sheet;
/// otherwise the editor opens straight away on the first money account in the person's primary currency (or
/// the first money account in their own order when that currency has none), and the editor's account row
/// changes it within that currency. An account in another currency is recorded from its own row, which
/// opens the editor on it. Home's Activity "+" and the navigation "+" share this rule.
/// Until the accounts have loaded the list says nothing, so the answer is to load first.
enum ConnectedAddMovement {
    enum Target {
        case loadAccounts
        case createAccount
        case record(FinancialAccount)
    }

    static func target(for activeAccounts: [FinancialAccount], loaded: Bool, preferredCurrency: String? = nil) -> Target {
        guard loaded else { return .loadAccounts }
        let money = activeAccounts.filter { $0.nature == "asset" }
        let inPreferred = preferredCurrency.flatMap { code in
            money.first { $0.currency.caseInsensitiveCompare(code) == .orderedSame }
        }
        guard let account = inPreferred ?? money.first ?? activeAccounts.first else { return .createAccount }
        return .record(account)
    }
}
