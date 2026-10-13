import SwiftUI
import ArgusSession

@MainActor
final class FinancialDebtDraft: ObservableObject, Identifiable {
    let id = UUID()
    let existing: FinancialDebt?
    let debtAccountID: UUID
    let currency: String
    @Published var name: String
    @Published var sourceID: UUID?
    @Published var amount = ""
    @Published var start: Date
    @Published var cadence = FinancialPlanSchedule.Cadence.monthly
    @Published var firstDay: Int
    @Published var secondDay = 31
    @Published var hasEnd = false
    @Published var end: Date
    @Published var effective: Date
    @Published var estimate = false
    @Published var rate = ""
    @Published var fees = ""
    @Published var periodStart: Date
    init(account: FinancialAccount, start: String) {
        existing = nil; debtAccountID = account.id; currency = account.currency
        name = account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: "")
        let date = PlanPresentation.date(start)
        self.start = date; end = date; effective = date; periodStart = date
        firstDay = PlanPresentation.monthDay(start)
    }
    init(debt: FinancialDebt) {
        existing = debt; debtAccountID = debt.debtAccountId; currency = debt.currency; name = debt.name
        sourceID = debt.sourceAccountId; amount = AccountPresentation.amount(debt.amount, locale: .current)
        start = PlanPresentation.date(debt.schedule.startDate); cadence = debt.schedule.cadence
        firstDay = debt.schedule.monthDays.first ?? PlanPresentation.monthDay(debt.schedule.startDate)
        secondDay = debt.schedule.monthDays.last ?? 31
        hasEnd = debt.schedule.endDate != nil; end = PlanPresentation.date(debt.schedule.endDate ?? debt.earliestEffectiveDate)
        effective = PlanPresentation.date(debt.earliestEffectiveDate)
        estimate = debt.assumptions != nil
        rate = debt.assumptions.map { AccountPresentation.amount($0.annualRatePercent, locale: .current) } ?? ""
        fees = debt.assumptions.map { AccountPresentation.amount($0.recurringFees, locale: .current) } ?? ""
        periodStart = PlanPresentation.date(debt.assumptions?.firstPeriodStart ?? debt.earliestEffectiveDate)
    }
    var ready: Bool { missing == nil }
    /// The first thing this debt plan still needs; the save check and the editor's hint both read it.
    var missing: ConnectedPlanMissing? {
        if let problem = ConnectedPlanMissing.name(name) { return problem }
        if amount.isEmpty { return .monthly }
        if sourceID == nil { return .source }
        if estimate && rate.isEmpty { return .rate }
        return estimate && fees.isEmpty ? .fees : nil
    }
    func command(locale: Locale) throws -> FinancialDebtCommand {
        guard ready, let exact = try AccountEntry.amount(amount, locale: locale) else { throw AccountEntry.Failure.amount }
        let old = existing?.schedule
        let unchangedAnchor = old?.cadence == .monthly && old?.monthDays.isEmpty == true && old?.startDate == PlanPresentation.day(start) && firstDay == PlanPresentation.monthDay(PlanPresentation.day(start))
        let days = cadence == .twiceMonthly ? [firstDay, secondDay] : cadence == .monthly && !unchangedAnchor ? [firstDay] : []
        let schedule = FinancialPlanSchedule(cadence: cadence, startDate: PlanPresentation.day(start), endDate: hasEnd ? PlanPresentation.day(end) : nil, monthDays: days)
        let sourceChanged = existing.map { $0.sourceAccountId != sourceID } ?? true
        let amountChanged = existing.map { $0.amount != exact } ?? true
        let scheduleChanged = existing.map { $0.schedule != schedule } ?? true
        let changed = sourceChanged || amountChanged || scheduleChanged
        let assumptions: FinancialDebtAssumptions?
        if estimate, let rate = try AccountEntry.amount(rate, locale: locale), let fees = try AccountEntry.amount(fees, locale: locale) {
            assumptions = .init(annualRatePercent: rate, recurringFees: fees, firstPeriodStart: PlanPresentation.day(periodStart))
        } else { assumptions = nil }
        return .init(name: name, debtAccountId: existing == nil ? debtAccountID : nil, sourceAccountId: sourceChanged ? sourceID : nil,
                     amount: amountChanged ? exact : nil, schedule: scheduleChanged ? schedule : nil, assumptions: assumptions,
                     expectedVersion: existing?.version, effectiveDate: existing != nil && changed ? PlanPresentation.day(effective) : nil)
    }
}
