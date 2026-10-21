import Foundation
import ArgusSession

/// Connected choices the Preview plan does not carry; the seeded draft keeps every other server field.
struct ConnectedPlanDetails: Equatable {
    var destinationID: UUID?
    var sourceID: UUID?
    var debtAccountID: UUID?
    var accountIDs: Set<UUID> = []
    var categoryIDs: Set<String> = []
    var includeUncategorized = false
}

/// Drafts hold locale-formatted amount text; the Preview editor edits a Double.
enum ConnectedPlanAmount {
    static func text(_ value: Double, digits: Int, locale: Locale) -> String {
        guard value.isFinite, value > 0 else { return "" }
        let plain = String(format: "%.\(max(0, digits))f", locale: Locale(identifier: "en_US_POSIX"), value)
        return AccountPresentation.amount(plain, locale: locale)
    }
    static func value(_ text: String, locale: Locale) -> Double {
        guard let exact = (try? AccountEntry.amount(text, locale: locale)) ?? nil, let value = Double(exact) else { return 0 }
        return value
    }
}

@MainActor
enum ConnectedPlanMapping {
    static func seed(_ draft: FinancialGoalDraft, locale: Locale) -> (CanvasPlan, ConnectedPlanDetails) {
        var plan = CanvasPlan(name: draft.name, kind: .goal, currency: draft.currency, look: .coast)
        if let existing = draft.existing { plan.id = existing.id }
        plan.target = ConnectedPlanAmount.value(draft.target, locale: locale)
        plan.monthly = draft.hasPlan ? ConnectedPlanAmount.value(draft.amount, locale: locale) : 0
        return (plan, .init(destinationID: draft.destinationID, sourceID: draft.sourceID))
    }
    static func seed(_ draft: FinancialBudgetDraft, locale: Locale) -> (CanvasPlan, ConnectedPlanDetails) {
        var plan = CanvasPlan(name: draft.name, kind: .budget, currency: draft.currency, look: .sunshine)
        if let existing = draft.existing { plan.id = existing.id }
        plan.target = ConnectedPlanAmount.value(draft.limit, locale: locale); plan.monthly = plan.target
        return (plan, .init(accountIDs: draft.accountIDs, categoryIDs: draft.categoryIDs, includeUncategorized: draft.includeUncategorized))
    }
    static func seed(_ draft: FinancialDebtDraft, locale: Locale) -> (CanvasPlan, ConnectedPlanDetails) {
        var plan = CanvasPlan(name: draft.name, kind: .debt, currency: draft.currency, look: .bloom)
        if let existing = draft.existing { plan.id = existing.id }
        plan.monthly = ConnectedPlanAmount.value(draft.amount, locale: locale)
        plan.annualRate = draft.estimate ? ConnectedPlanAmount.value(draft.rate, locale: locale) : 0
        return (plan, .init(sourceID: draft.sourceID, debtAccountID: draft.debtAccountID))
    }

    static func apply(_ plan: CanvasPlan, _ details: ConnectedPlanDetails, to draft: FinancialGoalDraft, digits: Int, locale: Locale) {
        draft.name = plan.name
        if draft.existing == nil { draft.currency = plan.currency }
        draft.target = ConnectedPlanAmount.text(plan.target, digits: digits, locale: locale)
        draft.destinationID = details.destinationID
        draft.hasPlan = plan.monthly > 0
        draft.sourceID = details.sourceID
        draft.amount = ConnectedPlanAmount.text(plan.monthly, digits: digits, locale: locale)
    }
    static func apply(_ plan: CanvasPlan, _ details: ConnectedPlanDetails, to draft: FinancialBudgetDraft, digits: Int, locale: Locale) {
        draft.name = plan.name
        if draft.existing == nil { draft.currency = plan.currency }
        draft.limit = ConnectedPlanAmount.text(plan.target, digits: digits, locale: locale)
        draft.accountIDs = details.accountIDs
        draft.categoryIDs = details.categoryIDs
        draft.includeUncategorized = details.includeUncategorized
    }
    static func apply(_ plan: CanvasPlan, _ details: ConnectedPlanDetails, to draft: FinancialDebtDraft, digits: Int, locale: Locale) {
        draft.name = plan.name
        draft.sourceID = details.sourceID
        draft.amount = ConnectedPlanAmount.text(plan.monthly, digits: digits, locale: locale)
        draft.estimate = plan.annualRate > 0
        draft.rate = ConnectedPlanAmount.text(plan.annualRate, digits: 2, locale: locale)
        if draft.estimate && draft.fees.isEmpty { draft.fees = AccountPresentation.amount("0", locale: locale) }
    }

    static func cadenceTitle(_ cadence: FinancialPlanSchedule.Cadence) -> String? {
        cadence == .monthly ? nil : NSLocalizedString("plan.repeat." + cadence.rawValue, comment: "")
    }
}

/// The first field a new or edited plan still needs; the kind drafts own the rules, the editor names the result.
enum ConnectedPlanMissing: String, Equatable {
    case name, nameTooLong, amount, monthly, debtAccount, accounts, categories, destination, source, sameAccount, rate, fees, loading, planUnavailable

    static func name(_ text: String) -> ConnectedPlanMissing? {
        if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return .name }
        return text.count > 100 ? .nameTooLong : nil
    }

    func hint(spanish: Bool) -> String {
        switch self {
        case .name: CuadraoCopy.text("copy.connectedPlanMapping.033bc41e55", spanish: spanish)
        case .nameTooLong: CuadraoCopy.text("copy.connectedPlanMapping.a774c84053", spanish: spanish)
        case .amount: CuadraoCopy.text("copy.connectedPlanMapping.ccc6c1cd1c", spanish: spanish)
        case .monthly: CuadraoCopy.text("copy.connectedPlanMapping.89df02c9d4", spanish: spanish)
        case .debtAccount: CuadraoCopy.text("copy.connectedPlanMapping.a041a2e97b", spanish: spanish)
        case .accounts: CuadraoCopy.text("copy.connectedPlanMapping.3d09876227", spanish: spanish)
        case .categories: CuadraoCopy.text("copy.connectedPlanMapping.1556f112c5", spanish: spanish)
        case .destination: CuadraoCopy.text("copy.connectedPlanMapping.7534fa77de", spanish: spanish)
        case .source: CuadraoCopy.text("copy.connectedPlanMapping.7d1f6018e2", spanish: spanish)
        case .sameAccount: CuadraoCopy.text("copy.connectedPlanMapping.e99ac90dd4", spanish: spanish)
        case .rate: CuadraoCopy.text("copy.connectedPlanMapping.cefebc9acf", spanish: spanish)
        case .fees: CuadraoCopy.text("copy.connectedPlanMapping.b1c85a9067", spanish: spanish)
        case .loading: CuadraoCopy.text("copy.connectedPlanMapping.722075f221", spanish: spanish)
        case .planUnavailable: CuadraoCopy.text("copy.connectedPlanMapping.85dc68fb43", spanish: spanish)
        }
    }
}
