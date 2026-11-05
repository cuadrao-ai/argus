import Foundation

public struct FinancialPlanSchedule: Codable, Equatable, Sendable {
    public enum Cadence: String, Codable, CaseIterable, Sendable {
        case once, weekly, everyTwoWeeks = "every_two_weeks", monthly, twiceMonthly = "twice_monthly"
    }
    public var cadence: Cadence
    public var startDate: String
    public var endDate: String?
    public var monthDays: [Int]
    public init(cadence: Cadence, startDate: String, endDate: String? = nil, monthDays: [Int] = []) {
        self.cadence = cadence; self.startDate = startDate; self.endDate = endDate; self.monthDays = monthDays
    }
    enum CodingKeys: String, CodingKey { case cadence, startDate = "start_date", endDate = "end_date", monthDays = "month_days" }
}

public enum FinancialExpectationKind: String, Codable, CaseIterable, Sendable { case income, bill }

public struct FinancialExpectation: Codable, Equatable, Sendable, Identifiable {
    public let id: UUID
    public let version: Int
    public let kind: FinancialExpectationKind
    public let title: String
    public let currency: String
    public let currencyFractionDigits: Int
    public let amountMinor: Int64
    public let amount: String
    public let accountId: UUID?
    public let schedule: FinancialPlanSchedule
    public let archived: Bool
    public let earliestEffectiveDate: String
    enum CodingKeys: String, CodingKey {
        case id, version, kind, title, currency, amount, schedule, archived
        case currencyFractionDigits = "currency_fraction_digits", amountMinor = "amount_minor"
        case accountId = "account_id", earliestEffectiveDate = "earliest_effective_date"
    }
}

public struct FinancialPlanSelection: Codable, Equatable, Sendable {
    public let version: Int
    public let accountIds: [UUID]
    public let timeZone: String
    enum CodingKeys: String, CodingKey { case version, accountIds = "account_ids", timeZone = "time_zone" }
}

public enum FinancialOccurrenceKind: String, Codable, Sendable { case income, bill, goalTransfer = "goal_transfer", debtPayment = "debt_payment" }

public struct FinancialPlanOccurrence: Codable, Equatable, Sendable, Identifiable {
    public enum Status: String, Codable, Sendable { case planned, fulfilled, needsReview = "needs_review" }
    public let id: String
    public let expectationId: UUID?
    public let debtPlanId: UUID?
    public let paidMinor: Int64?
    public let remainingMinor: Int64?
    public let goalId: UUID?
    public let sourceAccountId: UUID?
    public let destinationAccountId: UUID?
    public let expectationVersion: Int
    public let kind: FinancialOccurrenceKind
    public let title: String
    public let currency: String
    public let currencyFractionDigits: Int
    public let amountMinor: Int64
    public let amount: String
    public let accountId: UUID?
    public let dueDate: String
    public let projectionDate: String
    public let status: Status
    public let activityId: UUID?
    public let activityRevision: Int?
    public let exclusionReason: String?
    public let overdue: Bool
    enum CodingKeys: String, CodingKey {
        case id, kind, title, currency, amount, status, overdue
        case debtPlanId = "debt_plan_id", paidMinor = "paid_minor", remainingMinor = "remaining_minor"
        case goalId = "goal_id", sourceAccountId = "source_account_id", destinationAccountId = "destination_account_id"
        case expectationId = "expectation_id", expectationVersion = "expectation_version"
        case currencyFractionDigits = "currency_fraction_digits", amountMinor = "amount_minor"
        case accountId = "account_id", dueDate = "due_date", projectionDate = "projection_date"
        case activityId = "activity_id", activityRevision = "activity_revision", exclusionReason = "exclusion_reason"
    }
}

public struct FinancialForecastCurrency: Decodable, Sendable, Identifiable {
    public let currency: String
    public let currencyFractionDigits: Int
    public let accountIds: [UUID]
    public let unknownAccountIds: [UUID]
    public let knownStartingMinor: String
    public let startingMinor: String?
    public let expectedIncomeMinor: String
    public let expectedBillsMinor: String
    public let transferEffectMinor: String?
    public let netCashChangeMinor: String
    public let endingMinor: String?
    public let firstShortfallDate: String?
    public let asOf: String?
    public let points: [Point]
    public let order: String
    public var id: String { currency }
    public struct Point: Decodable, Sendable {
        public let date: String
        public let occurrenceId: String?
        public let changeMinor: String
        public let knownBalanceMinor: String
        public let balanceMinor: String?
        enum CodingKeys: String, CodingKey {
            case date, occurrenceId = "occurrence_id", changeMinor = "change_minor"
            case knownBalanceMinor = "known_balance_minor", balanceMinor = "balance_minor"
        }
    }
    enum CodingKeys: String, CodingKey {
        case currency, points, order, asOf = "as_of", currencyFractionDigits = "currency_fraction_digits"
        case accountIds = "account_ids", unknownAccountIds = "unknown_account_ids"
        case knownStartingMinor = "known_starting_minor", startingMinor = "starting_minor"
        case expectedIncomeMinor = "expected_income_minor", expectedBillsMinor = "expected_bills_minor"
        case transferEffectMinor = "transfer_effect_minor"
        case netCashChangeMinor = "net_cash_change_minor", endingMinor = "ending_minor", firstShortfallDate = "first_shortfall_date"
    }
}

public struct FinancialPlanProjection: Decodable, Sendable {
    public let home: FinancialHome
    public let selection: FinancialPlanSelection
    public let accounts: [FinancialAccount]
    public let expectations: [FinancialExpectation]
    public let occurrences: [FinancialPlanOccurrence]
    public let currencies: [FinancialForecastCurrency]
    public let startDate: String
    public let endDate: String
    public let coverage: String
    public let hasExpectations: Bool
    public let budgets: [FinancialBudgetProgress]
    public let debts: [FinancialDebtProgress]?
    public let goals: [FinancialGoalProgress]?
    public let goalPools: [FinancialGoalPool]?
    enum CodingKeys: String, CodingKey {
        case home, selection, accounts, expectations, occurrences, currencies, coverage, budgets, goals, debts
        case goalPools = "goal_pools"
        case startDate = "start_date", endDate = "end_date", hasExpectations = "has_expectations"
    }
}

public struct FinancialExpectationCommand: Encodable, Sendable {
    public var kind: FinancialExpectationKind?
    public var title: String
    public var currency: String?
    public var amount: String
    public var accountId: UUID?
    public var includesAccount: Bool
    public var schedule: FinancialPlanSchedule?
    public var expectedVersion: Int?
    public var effectiveDate: String?
    public init(kind: FinancialExpectationKind? = nil, title: String, currency: String? = nil, amount: String,
                accountId: UUID?, includesAccount: Bool = true, schedule: FinancialPlanSchedule?, expectedVersion: Int? = nil, effectiveDate: String? = nil) {
        self.kind = kind; self.title = title; self.currency = currency; self.amount = amount
        self.accountId = accountId; self.includesAccount = includesAccount; self.schedule = schedule; self.expectedVersion = expectedVersion; self.effectiveDate = effectiveDate
    }
    enum CodingKeys: String, CodingKey {
        case kind, title, currency, amount, schedule, accountId = "account_id"
        case expectedVersion = "expected_version", effectiveDate = "effective_date"
    }
    public func encode(to encoder: any Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encodeIfPresent(kind, forKey: .kind); try values.encode(title, forKey: .title)
        try values.encodeIfPresent(currency, forKey: .currency); try values.encode(amount, forKey: .amount)
        if includesAccount { try values.encode(accountId, forKey: .accountId) }
        try values.encodeIfPresent(schedule, forKey: .schedule)
        try values.encodeIfPresent(expectedVersion, forKey: .expectedVersion)
        try values.encodeIfPresent(effectiveDate, forKey: .effectiveDate)
    }
}

public struct FinancialPlanSelectionCommand: Encodable, Sendable {
    public let expectedVersion: Int
    public let accountIds: [UUID]
    public let timeZone: String
    public init(expectedVersion: Int, accountIds: [UUID], timeZone: String) {
        self.expectedVersion = expectedVersion; self.accountIds = accountIds; self.timeZone = timeZone
    }
    enum CodingKeys: String, CodingKey { case expectedVersion = "expected_version", accountIds = "account_ids", timeZone = "time_zone" }
}

public struct FinancialPlanFulfillmentCommand: Codable, Sendable {
    public let expectedVersion: Int
    public let activity: FinancialActivityCommand
    public init(expectedVersion: Int, activity: FinancialActivityCommand) { self.expectedVersion = expectedVersion; self.activity = activity }
    enum CodingKeys: String, CodingKey { case expectedVersion = "expected_version", activity }
}

public struct FinancialPlanLinkCommand: Encodable, Sendable {
    public let expectedVersion: Int
    public let activityId: UUID
    public let activityRevision: Int
    public init(expectedVersion: Int, activityId: UUID, activityRevision: Int) {
        self.expectedVersion = expectedVersion; self.activityId = activityId; self.activityRevision = activityRevision
    }
    enum CodingKeys: String, CodingKey { case expectedVersion = "expected_version", activityId = "activity_id", activityRevision = "activity_revision" }
}

public struct FinancialPlanFulfillmentPreview: Decodable, Sendable {
    public let occurrence: FinancialPlanOccurrence
    public let money: FinancialActivityPreview
}

public enum FinancialPlanOperation: Codable, Equatable, Sendable {
    case createDebt
    case editDebt(id: UUID, version: Int)
    case linkDebt(id: UUID, version: Int)
    case recordDebt(id: UUID, version: Int)
    case createGoal
    case editGoal(id: UUID, version: Int)
    case allocateGoals
    case linkGoal(id: UUID, version: Int)
    case recordGoal(id: UUID, version: Int)
    case releaseGoal(id: UUID, claimId: UUID, version: Int)
    case createExpectation
    case createBudget
    case editBudget(id: UUID, version: Int)
    case editExpectation(id: UUID, version: Int)
    case selection(version: Int)
    case fulfill(occurrenceId: String, version: Int)
    case link(occurrenceId: String, version: Int)

    public var path: String {
        switch self {
        case .createDebt: "/debts"
        case .editDebt(let id, _): "/debts/" + id.uuidString
        case .linkDebt(let id, _): "/debts/" + id.uuidString + "/payments/link"
        case .recordDebt(let id, _): "/debts/" + id.uuidString + "/payments"
        case .createGoal: "/goals"
        case .editGoal(let id, _): "/goals/" + id.uuidString
        case .allocateGoals: "/goals/allocations"
        case .linkGoal(let id, _): "/goals/" + id.uuidString + "/contributions/link"
        case .recordGoal(let id, _): "/goals/" + id.uuidString + "/contributions"
        case .releaseGoal(let id, let claimId, _): "/goals/" + id.uuidString + "/contributions/" + claimId.uuidString + "/release"
        case .createBudget: "/budgets"
        case .editBudget(let id, _): "/budgets/" + id.uuidString
        case .createExpectation: "/expectations"
        case .editExpectation(let id, _): "/expectations/" + id.uuidString
        case .selection: "/selection"
        case .fulfill(let id, _): "/occurrences/" + id + "/fulfillment"
        case .link(let id, _): "/occurrences/" + id + "/link"
        }
    }
    public var recordsActivity: Bool {
        switch self { case .fulfill, .recordGoal, .recordDebt: true; default: false }
    }
    public var method: String {
        switch self { case .editExpectation, .editBudget, .editGoal, .editDebt: "PATCH"; case .selection, .allocateGoals: "PUT"; default: "POST" }
    }
}

struct FinancialExpectationReceipt: Decodable { let expectation: FinancialExpectation; let replayed: Bool }
struct FinancialPlanSelectionReceipt: Decodable { let selection: FinancialPlanSelection; let replayed: Bool }
struct FinancialPlanLinkReceipt: Decodable { let occurrence: FinancialPlanOccurrence; let replayed: Bool }
