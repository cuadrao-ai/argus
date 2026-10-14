import SwiftUI
import ArgusSession

@MainActor
final class FinancialGoalDraft: ObservableObject, Identifiable {
    let id = UUID()
    let existing: FinancialGoal?
    @Published var name = ""
    @Published var target = ""
    @Published var currency: String
    @Published var hasTargetDate = false
    @Published var targetDate: Date
    @Published var destinationID: UUID?
    @Published var hasPlan = false
    @Published var sourceID: UUID?
    @Published var amount = ""
    @Published var start: Date
    @Published var cadence = FinancialPlanSchedule.Cadence.monthly
    @Published var firstDay = 15
    @Published var secondDay = 31
    @Published var hasEnd = false
    @Published var end: Date
    @Published var effective: Date
    init(start: String, currency: String) {
        existing = nil; self.currency = currency
        let date = PlanPresentation.date(start); self.start = date; targetDate = date; end = date; effective = date
        firstDay = PlanPresentation.monthDay(start)
    }
    init(goal: FinancialGoal) {
        existing = goal; name = goal.name; currency = goal.currency; target = AccountPresentation.amount(goal.target, locale: .current)
        hasTargetDate = goal.targetDate != nil; targetDate = PlanPresentation.date(goal.targetDate ?? goal.earliestEffectiveDate)
        destinationID = goal.destinationAccountId; hasPlan = goal.contributionPlan != nil
        sourceID = goal.contributionPlan?.sourceAccountId
        amount = goal.contributionPlan.map { AccountPresentation.amount($0.amount, locale: .current) } ?? ""
        let schedule = goal.contributionPlan?.schedule
        start = PlanPresentation.date(schedule?.startDate ?? goal.earliestEffectiveDate)
        cadence = schedule?.cadence ?? .monthly
        firstDay = schedule?.monthDays.first ?? PlanPresentation.monthDay(schedule?.startDate ?? goal.earliestEffectiveDate)
        secondDay = schedule?.monthDays.last ?? 31
        hasEnd = schedule?.endDate != nil; end = PlanPresentation.date(schedule?.endDate ?? goal.earliestEffectiveDate)
        effective = PlanPresentation.date(goal.earliestEffectiveDate)
    }
    var ready: Bool { missing == nil }
    /// The first thing this goal still needs; the save check and the editor's hint both read it.
    var missing: ConnectedPlanMissing? {
        if let problem = ConnectedPlanMissing.name(name) { return problem }
        if target.isEmpty { return .amount }
        guard hasPlan else { return nil }
        if destinationID == nil { return .destination }
        if sourceID == nil { return .source }
        if destinationID == sourceID { return .sameAccount }
        return amount.isEmpty ? .monthly : nil
    }
    func command(locale: Locale) throws -> FinancialGoalCommand {
        guard ready, let exact = try AccountEntry.amount(target, locale: locale) else { throw AccountEntry.Failure.amount }
        let plan: FinancialGoalPlan?
        if hasPlan, let sourceID, let amount = try AccountEntry.amount(amount, locale: locale) {
            let previous = existing?.contributionPlan?.schedule
            let unchangedAnchor = previous?.cadence == .monthly && previous?.monthDays.isEmpty == true &&
                previous?.startDate == PlanPresentation.day(start) && firstDay == PlanPresentation.monthDay(PlanPresentation.day(start))
            let monthDays = cadence == .twiceMonthly ? [firstDay, secondDay] : cadence == .monthly && !unchangedAnchor ? [firstDay] : []
            plan = .init(sourceAccountId: sourceID, amount: amount, schedule: .init(cadence: cadence,
                startDate: PlanPresentation.day(start), endDate: hasEnd ? PlanPresentation.day(end) : nil, monthDays: monthDays))
        } else { plan = nil }
        let changed = existing.map { $0.destinationAccountId != destinationID || $0.contributionPlan != plan } ?? true
        return .init(name: name, currency: existing == nil ? currency : nil, target: exact,
            targetDate: hasTargetDate ? PlanPresentation.day(targetDate) : nil, destinationAccountId: destinationID,
            contributionPlan: plan, includesSetup: changed, expectedVersion: existing?.version,
            effectiveDate: existing != nil && changed ? PlanPresentation.day(effective) : nil)
    }
}
