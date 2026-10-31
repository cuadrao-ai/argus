import Foundation

public struct FinancialDebtAssumptions: Codable, Equatable, Sendable {
    public let annualRatePercent: String
    public let recurringFees: String
    public let firstPeriodStart: String
    public let noNewBorrowing: Bool
    public init(annualRatePercent: String, recurringFees: String, firstPeriodStart: String) {
        self.annualRatePercent = annualRatePercent; self.recurringFees = recurringFees
        self.firstPeriodStart = firstPeriodStart; self.noNewBorrowing = true
    }
    enum CodingKeys: String, CodingKey { case annualRatePercent = "annual_rate_percent", recurringFees = "recurring_fees", firstPeriodStart = "first_period_start", noNewBorrowing = "no_new_borrowing" }
}

public struct FinancialDebt: Codable, Equatable, Sendable, Identifiable {
    public let id: UUID
    public let version: Int
    public let debtAccountId: UUID
    public let name: String
    public let currency: String
    public let currencyFractionDigits: Int
    public let sourceAccountId: UUID
    public let amountMinor: Int64
    public let amount: String
    public let schedule: FinancialPlanSchedule
    public let assumptions: FinancialDebtAssumptions?
    public let archived: Bool
    public let earliestEffectiveDate: String
    enum CodingKeys: String, CodingKey {
        case id, version, name, currency, amount, schedule, assumptions, archived
        case debtAccountId = "debt_account_id", currencyFractionDigits = "currency_fraction_digits", sourceAccountId = "source_account_id", amountMinor = "amount_minor", earliestEffectiveDate = "earliest_effective_date"
    }
}

public struct FinancialDebtPayoff: Codable, Equatable, Sendable {
    public let state: String
    public let reason: String?
    public let payoffDate: String?
    public let payments: Int?
    public let totalInterestMinor: String?
    public let totalFeesMinor: String?
    public let assumptions: FinancialDebtAssumptions?
    enum CodingKeys: String, CodingKey {
        case state, reason, payments, assumptions, payoffDate = "payoff_date", totalInterestMinor = "total_interest_minor", totalFeesMinor = "total_fees_minor"
    }
}

public struct FinancialDebtPayment: Codable, Equatable, Sendable, Identifiable {
    public let id: UUID
    public let activityId: UUID
    public let occurrenceId: String?
    public let status: String
    public let netPaidMinor: Int64?
    public let activity: FinancialActivityDetail?
    enum CodingKeys: String, CodingKey { case id, status, activity, activityId = "activity_id", occurrenceId = "occurrence_id", netPaidMinor = "net_paid_minor" }
}

public struct FinancialDebtProgress: Codable, Equatable, Sendable, Identifiable {
    public let debt: FinancialDebt
    public let balance: FinancialBalance
    public let state: String
    public let payoff: FinancialDebtPayoff
    public let payments: [FinancialDebtPayment]
    public let occurrences: [FinancialPlanOccurrence]
    public let fundingPool: FinancialGoalPool?
    public var id: UUID { debt.id }
    enum CodingKeys: String, CodingKey { case debt, balance, state, payoff, payments, occurrences, fundingPool = "funding_pool" }
}

public struct FinancialDebtCommand: Encodable, Sendable {
    public let name: String
    public let debtAccountId: UUID?
    public let sourceAccountId: UUID?
    public let amount: String?
    public let schedule: FinancialPlanSchedule?
    public let assumptions: FinancialDebtAssumptions?
    public let expectedVersion: Int?
    public let effectiveDate: String?
    public init(name: String, debtAccountId: UUID?, sourceAccountId: UUID?, amount: String?, schedule: FinancialPlanSchedule?, assumptions: FinancialDebtAssumptions?, expectedVersion: Int?, effectiveDate: String?) {
        self.name = name; self.debtAccountId = debtAccountId; self.sourceAccountId = sourceAccountId
        self.amount = amount; self.schedule = schedule; self.assumptions = assumptions
        self.expectedVersion = expectedVersion; self.effectiveDate = effectiveDate
    }
    enum CodingKeys: String, CodingKey { case name, amount, schedule, assumptions, debtAccountId = "debt_account_id", sourceAccountId = "source_account_id", expectedVersion = "expected_version", effectiveDate = "effective_date" }
    public func encode(to encoder: any Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(name, forKey: .name); try c.encode(assumptions, forKey: .assumptions)
        try c.encodeIfPresent(debtAccountId, forKey: .debtAccountId); try c.encodeIfPresent(sourceAccountId, forKey: .sourceAccountId)
        try c.encodeIfPresent(amount, forKey: .amount); try c.encodeIfPresent(schedule, forKey: .schedule)
        try c.encodeIfPresent(expectedVersion, forKey: .expectedVersion); try c.encodeIfPresent(effectiveDate, forKey: .effectiveDate)
    }
}

public struct FinancialDebtRecordCommand: Codable, Sendable {
    public let expectedVersion: Int
    public let activity: FinancialActivityCommand
    public let occurrenceId: String?
    public init(expectedVersion: Int, activity: FinancialActivityCommand, occurrenceId: String?) {
        self.expectedVersion = expectedVersion; self.activity = activity; self.occurrenceId = occurrenceId
    }
    enum CodingKeys: String, CodingKey { case expectedVersion = "expected_version", activity, occurrenceId = "occurrence_id" }
}

public struct FinancialDebtLinkCommand: Encodable, Sendable {
    public let expectedVersion: Int
    public let activityId: UUID
    public let activityRevision: Int
    public let occurrenceId: String?
    public let expectedAccountVersions: [String: Int]
    public init(expectedVersion: Int, activityId: UUID, activityRevision: Int, occurrenceId: String?, expectedAccountVersions: [String: Int]) {
        self.expectedVersion = expectedVersion; self.activityId = activityId; self.activityRevision = activityRevision
        self.occurrenceId = occurrenceId; self.expectedAccountVersions = expectedAccountVersions
    }
    enum CodingKeys: String, CodingKey { case expectedVersion = "expected_version", activityId = "activity_id", activityRevision = "activity_revision", occurrenceId = "occurrence_id", expectedAccountVersions = "expected_account_versions" }
}
public struct FinancialDebtPreview: Decodable, Sendable { public let debt: FinancialDebtProgress; public let money: FinancialActivityPreview }
struct FinancialDebtReceipt: Decodable { let debt: FinancialDebtProgress; let replayed: Bool }

extension SessionController {
    public func financialDebt(_ id: UUID, expectedIdentity: SessionSnapshot) async throws -> FinancialDebtProgress {
        try await planResponse(path: "/debts/" + id.uuidString, identity: expectedIdentity)
    }
    public func financialDebtCandidates(_ id: UUID, expectedIdentity: SessionSnapshot) async throws -> FinancialPurchaseCatalog {
        try await planResponse(path: "/debts/" + id.uuidString + "/payments/candidates", identity: expectedIdentity)
    }
    public func financialDebtPreview(_ id: UUID, command: FinancialDebtRecordCommand, expectedIdentity: SessionSnapshot) async throws -> FinancialDebtPreview {
        try await planResponse(path: "/debts/" + id.uuidString + "/payments/preview", method: "POST", body: encoded(command), identity: expectedIdentity)
    }
}
