import SwiftUI
import ArgusSession

@MainActor
final class HouseholdActivityEditor: ObservableObject, Identifiable {
    let id = UUID()
    let household: Household
    let snapshot: HouseholdSnapshot
    let origin: HouseholdAccount
    let correcting: HouseholdActivity?
    @Published var kind: FinancialActivityKind = .expense { didSet { preview = nil; if kind != oldValue { category = nil; incomeSource = nil; purchase = nil; principal = ""; interest = ""; fees = "" } } }
    @Published var accountId: UUID? { didSet { preview = nil } }
    @Published var sourceId: UUID? { didSet { preview = nil } }
    @Published var destinationId: UUID? { didSet { preview = nil } }
    @Published var amount = "" { didSet { preview = nil } }
    @Published var principal = "" { didSet { preview = nil } }
    @Published var interest = "" { didSet { preview = nil } }
    @Published var fees = "" { didSet { preview = nil } }
    @Published var note = "" { didSet { preview = nil } }
    @Published var reason = "" { didSet { preview = nil } }
    @Published var category: String? { didSet { preview = nil } }
    @Published var incomeSource: String? { didSet { preview = nil } }
    @Published var purchase: UUID? { didSet { preview = nil } }
    @Published var date = Date() { didSet { preview = nil } }
    @Published var options: HouseholdActivityOptions?
    @Published private(set) var preview: FinancialActivityPreview?
    @Published private(set) var errorKey: String?
    @Published private(set) var busy = false
    private var coverage: [FinancialAccountCoverage] = []
    private let identity: SessionSnapshot
    private weak var model: HouseholdModel?
    init(model: HouseholdModel, identity: SessionSnapshot, household: Household, snapshot: HouseholdSnapshot, account: HouseholdAccount, correction: HouseholdActivity?) {
        self.model = model; self.identity = identity; self.household = household; self.snapshot = snapshot; origin = account; correcting = correction
        accountId = account.id; sourceId = account.id
        if let value = correction?.activity {
            kind = value.kind; amount = value.amount ?? ""; note = value.note ?? ""; category = value.categoryId; incomeSource = value.sourceId; purchase = value.purchaseActivityId
            accountId = value.legs.first(where: { $0.role == "single" })?.accountId
            sourceId = value.legs.first(where: { $0.role == "source" })?.accountId
            destinationId = value.legs.first(where: { $0.role == "destination" })?.accountId
            date = AccountPresentation.parseDate(value.occurredAt) ?? Date()
            let divisor = pow(Decimal(10), account.account.currencyFractionDigits)
            principal = value.principalMinor.map { (Decimal($0) / divisor).description } ?? ""
            interest = value.interestMinor.map { (Decimal($0) / divisor).description } ?? ""
            fees = value.feesMinor.map { (Decimal($0) / divisor).description } ?? ""
            coverage = value.legs.flatMap { leg in leg.coverage.map { FinancialAccountCoverage(accountId: leg.accountId, observationId: $0.observationId, included: $0.included) } }
        }
    }
    var current: Bool { model?.isAvailable == true && model?.selectedId == household.id && model?.household?.membershipId == household.membershipId && model?.identity?.revision == identity.revision && model?.editor?.id == id }
    var choices: [HouseholdFinancialAccount] { options?.accounts ?? [] }
    var kinds: [FinancialActivityKind] { FinancialActivityKind.allCases.filter { options?.eligibility[$0.rawValue]?.contains(origin.account.type) == true && $0 != .paymentReversal } }
    func load() async {
        guard let model, current else { return }
        do {
            let value = try await model.controller.householdResponse(HouseholdActivityOptions.self, path: model.path(household.id, "/activity-options"), expectedIdentity: identity)
            guard current else { return }; options = value
            if correcting == nil, !kinds.contains(kind), let first = kinds.first { kind = first }
        } catch {
            guard current else { return }
            if !(await model.resolveAccessFailure(error, householdId: household.id)), current { errorKey = "household.loadError" }
        }
    }
    func answer(_ accountId: UUID, _ observationId: UUID, _ included: Bool) {
        coverage.removeAll { $0.accountId == accountId && $0.observationId == observationId }
        coverage.append(FinancialAccountCoverage(accountId: accountId, observationId: observationId, included: included)); preview = nil
    }
    func review(_ locale: Locale) async {
        guard let model, current else { return }
        busy = true; errorKey = nil; defer { busy = false }
        do {
            let command = FinancialActivityCommand(kind: kind, accountId: kind.isPaired ? nil : accountId, sourceAccountId: kind.isPaired ? sourceId : nil, destinationAccountId: kind.isPaired ? destinationId : nil, amount: try AccountEntry.amount(amount, locale: locale) ?? "", occurredAt: ISO8601DateFormatter().string(from: date), timeZone: correcting?.activity.timeZone ?? TimeZone.current.identifier, note: note.isEmpty ? nil : note, categoryId: category, sourceId: incomeSource, purchaseActivityId: purchase, expectedRevision: correcting?.activity.revision, reason: reason.isEmpty ? nil : reason, coverage: coverage, principal: principal.isEmpty ? nil : try AccountEntry.amount(principal, locale: locale), interest: interest.isEmpty ? nil : try AccountEntry.amount(interest, locale: locale), fees: fees.isEmpty ? nil : try AccountEntry.amount(fees, locale: locale), reversalOfActivityId: correcting?.activity.reversalOfActivityId)
            let value = try await model.controller.householdResponse(FinancialActivityPreview.self, path: model.path(household.id, "/activities" + (correcting.map { "/" + $0.id.uuidString } ?? "") + "/preview"), method: "POST", body: JSONEncoder().encode(HouseholdFinancialCommand(membershipId: household.membershipId, expectedVersion: household.version, activity: command)), expectedIdentity: identity)
            guard current else { return }; preview = value
        } catch {
            guard current else { return }
            if !(await model.resolveAccessFailure(error, householdId: household.id)), current { errorKey = "household.reviewError" }
        }
    }
    func confirm() async {
        guard let model, current, let preview, preview.ready, var command = preview.reviewedRequest else { return }
        command.previewToken = preview.previewToken
        await model.confirmActivity(command, activityId: correcting?.id, membership: household.membershipId, version: household.version)
    }
}
