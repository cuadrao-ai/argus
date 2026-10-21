import SwiftUI
import ArgusSession

@MainActor
final class HouseholdContributionEditor: ObservableObject {
    let plan: HouseholdPlan
    let correcting: HouseholdPlanContribution?
    @Published var kind = FinancialActivityKind.expense { didSet { changed() } }
    @Published var accountId: UUID? { didSet { changed() } }
    @Published var sourceId: UUID? { didSet { changed() } }
    @Published var destinationId: UUID? { didSet { changed() } }
    @Published var purpose = HouseholdContributionPurpose.spending { didSet { changed() } }
    @Published var occurrenceId: UUID? { didSet { changed() } }
    @Published var amount = "" { didSet { changed() } }
    @Published var principal = "" { didSet { changed() } }
    @Published var interest = "" { didSet { changed() } }
    @Published var fees = "" { didSet { changed() } }
    @Published var note = "" { didSet { changed() } }
    @Published var reason = "" { didSet { changed() } }
    @Published var category: String? { didSet { changed() } }
    @Published var incomeSource: String? { didSet { changed() } }
    @Published var date = Date() { didSet { changed() } }
    @Published private(set) var options: HouseholdPlanOptions?
    @Published private(set) var preview: FinancialActivityPreview?
    @Published private(set) var original: FinancialActivityDetail?
    @Published private(set) var sharedOriginal: HouseholdActivityValue?
    private var sharedOptions: HouseholdActivityOptions?
    @Published private(set) var errorKey: String?
    @Published private(set) var busy = false
    private var coverage: [FinancialAccountCoverage] = []
    private weak var model: HouseholdPlanModel?
    private let identity: SessionSnapshot?
    init(model: HouseholdPlanModel, plan: HouseholdPlan, correcting: HouseholdPlanContribution?) {
        self.model = model; self.plan = plan; self.correcting = correcting; identity = model.identity
        occurrenceId = correcting?.occurrenceId; purpose = correcting?.purpose ?? .spending
    }
    var current: Bool {
        guard let model, let identity else { return false }
        return model.isCurrent(plan, identity) && model.sheet?.id == HouseholdPlanModel.Sheet.record(plan, correcting).id
    }
    struct AccountChoice: Identifiable {
        let id: UUID; let type: String; let currency: String; let nickname: String?
    }
    var accounts: [AccountChoice] {
        let own = options?.money.accounts.map { AccountChoice(id: $0.id, type: $0.type, currency: $0.currency, nickname: $0.nickname) } ?? []
        let shared = sharedOptions?.accounts.map { AccountChoice(id: $0.id, type: $0.type, currency: $0.currency, nickname: $0.nickname) } ?? []
        return (own + shared.filter { value in !own.contains { $0.id == value.id } }).filter { $0.currency == plan.definition.common.currency }
    }
    var purposes: [HouseholdContributionPurpose] { options?.purposes[plan.ref.kind.rawValue] ?? [] }
    var kinds: [FinancialActivityKind] { FinancialActivityKind.allCases.filter { kind in kind != .paymentReversal && accounts.contains { options?.money.eligibility[kind.rawValue]?.contains($0.type) == true } } }
    func choices(destination: Bool = false) -> [AccountChoice] {
        let types = destination ? options?.money.destinationEligibility[kind.rawValue] : options?.money.eligibility[kind.rawValue]
        return accounts.filter { types?.contains($0.type) == true }
    }
    private func changed() { preview = nil }
    func load() async {
        guard let model, current else { return }; busy = true; defer { busy = false }
        do {
            let value = try await model.options(); guard current else { return }; options = value
            if let correcting {
                guard correcting.canCorrect, let ref = correcting.original, let identity, let controller = model.controller else { throw SessionFailure.unauthorized }
                if let householdId = ref.householdId {
                    let detail = try await controller.householdResponse(HouseholdAccountDetail.self, path: "/" + householdId.uuidString + "/accounts/" + ref.accountId.uuidString, expectedIdentity: identity)
                    guard current, let activity = detail.activities.first(where: { $0.id == ref.activityId && $0.canEdit }), activity.activity.amount != nil else { throw SessionFailure.unauthorized }
                    let choices = try await controller.householdResponse(HouseholdActivityOptions.self, path: "/" + householdId.uuidString + "/activity-options", expectedIdentity: identity)
                    guard current else { return }; sharedOptions = choices; sharedOriginal = activity.activity
                    let a = activity.activity
                    fill(kind: a.kind, amount: a.amount!, note: a.note, category: a.categoryId, source: a.sourceId, occurredAt: a.occurredAt, digits: a.currencyFractionDigits, principal: a.principalMinor, interest: a.interestMinor, fees: a.feesMinor, legs: a.legs)
                } else {
                    let activity = try await controller.financialActivityDetail(ref.activityId, expectedIdentity: identity)
                    guard current else { return }
                    guard activity.originalAmountAvailable, let amount = activity.amount else { throw SessionFailure.unauthorized }; original = activity
                    fill(kind: activity.kind, amount: amount, note: activity.note, category: activity.categoryId, source: activity.sourceId, occurredAt: activity.occurredAt, digits: activity.currencyFractionDigits, principal: activity.principalMinor, interest: activity.interestMinor, fees: activity.feesMinor, legs: activity.legs)
                }
            } else {
                if let first = purposes.first { purpose = first }
                switch purpose { case .goalSaving, .funding: kind = .transfer; case .debtPayment: kind = .debtPayment; default: kind = .expense }
                if !kinds.contains(kind), let first = kinds.first { kind = first }
            }
            errorKey = nil
        } catch { if current { errorKey = HouseholdPlanModel.message(error) } }
    }
    private func fill(kind: FinancialActivityKind, amount: String, note: String?, category: String?, source: String?, occurredAt: String, digits: Int, principal: Int64?, interest: Int64?, fees: Int64?, legs: [FinancialActivityLeg]) {
        self.kind = kind; self.amount = amount; self.note = note ?? ""; self.category = category; incomeSource = source
        accountId = legs.first { $0.role == "single" }?.accountId
        sourceId = legs.first { $0.role == "source" }?.accountId; destinationId = legs.first { $0.role == "destination" }?.accountId
        date = AccountPresentation.parseDate(occurredAt) ?? date
        self.principal = principal.map { HouseholdPlanPresentation.decimal(String($0), digits: digits) } ?? ""
        self.interest = interest.map { HouseholdPlanPresentation.decimal(String($0), digits: digits) } ?? ""
        self.fees = fees.map { HouseholdPlanPresentation.decimal(String($0), digits: digits) } ?? ""
        coverage = legs.flatMap { leg in leg.coverage.map { .init(accountId: leg.accountId, observationId: $0.observationId, included: $0.included) } }
    }
    func answer(_ account: UUID, _ observation: UUID, _ included: Bool) {
        guard current, !busy else { return }
        coverage.removeAll { $0.accountId == account && $0.observationId == observation }
        coverage.append(.init(accountId: account, observationId: observation, included: included)); preview = nil
    }
    func review(_ locale: Locale) async {
        guard let model, current, !busy else { return }; busy = true; errorKey = nil; defer { busy = false }
        do {
            let activity = FinancialActivityCommand(kind: kind, accountId: kind.isPaired ? nil : accountId, sourceAccountId: kind.isPaired ? sourceId : nil, destinationAccountId: kind.isPaired ? destinationId : nil, amount: try AccountEntry.amount(amount, locale: locale) ?? "", occurredAt: ISO8601DateFormatter().string(from: date), timeZone: original?.timeZone ?? sharedOriginal?.timeZone ?? TimeZone.current.identifier, note: note.isEmpty ? nil : note, categoryId: category, sourceId: incomeSource, purchaseActivityId: original?.purchaseActivityId ?? sharedOriginal?.purchaseActivityId, expectedRevision: original?.revision ?? sharedOriginal?.revision, reason: reason.isEmpty ? nil : reason, coverage: coverage, principal: principal.isEmpty ? nil : try AccountEntry.amount(principal, locale: locale), interest: interest.isEmpty ? nil : try AccountEntry.amount(interest, locale: locale), fees: fees.isEmpty ? nil : try AccountEntry.amount(fees, locale: locale), reversalOfActivityId: original?.reversalOfActivityId ?? sharedOriginal?.reversalOfActivityId)
            let result: HouseholdContributionPreview
            if let correcting {
                guard correcting.canCorrect, original != nil || sharedOriginal != nil else { throw SessionFailure.unauthorized }
                result = try await model.review(HouseholdContributionCorrectionCommand(scope: model.scope(plan), activity: activity), plan: plan, claim: correcting.id)
            } else { result = try await model.review(HouseholdContributionRecordCommand(scope: model.scope(plan), activity: activity, purpose: purpose, occurrenceId: occurrenceId), plan: plan) }
            guard current else { return }; preview = result.money
        } catch { if current { errorKey = HouseholdPlanModel.message(error) } }
    }
    func confirm() async {
        guard let model, current, !busy, let preview, preview.ready, var activity = preview.reviewedRequest, let token = preview.previewToken else { return }
        activity.previewToken = token; busy = true; defer { busy = false }
        if let correcting { await model.submit(HouseholdContributionCorrectionCommand(scope: model.scope(plan), activity: activity), action: .correct(plan.ref, claim: correcting.id)) }
        else { await model.submit(HouseholdContributionRecordCommand(scope: model.scope(plan), activity: activity, purpose: purpose, occurrenceId: occurrenceId), action: .record(plan.ref)) }
    }
}
