import Foundation

public struct FinancialCoverage: Codable, Equatable, Sendable {
    public var observationId: UUID
    public var included: Bool
    public init(observationId: UUID, included: Bool) { self.observationId = observationId; self.included = included }
    enum CodingKeys: String, CodingKey {
        case observationId = "observation_id"
        case included
    }
}

public struct FinancialActivity: Codable, Equatable, Sendable {
    public var recordId: UUID
    public var revision: Int
    public var kind: String
    public var amountMinor: Int64
    public var amount: String
    public var balanceMovementMinor: Int64
    public var occurredAt: String
    public var timeZone: String
    public var note: String?
    public var categoryId: String?
    public var reason: String?
    public var recordedAt: String
    public var recordedBy: String?
    public var coverage: [FinancialCoverage]
    public var accountId: UUID?
    public var currency: String?
    public var activityId: UUID?
    public var role: String?
    public var active: Bool?
    enum CodingKeys: String, CodingKey {
        case recordId = "record_id"
        case revision
        case kind
        case amountMinor = "amount_minor"
        case amount
        case balanceMovementMinor = "balance_movement_minor"
        case occurredAt = "occurred_at"
        case timeZone = "time_zone"
        case note
        case categoryId = "category_id"
        case reason
        case recordedAt = "recorded_at"
        case recordedBy = "recorded_by"
        case coverage
        case accountId = "account_id"
        case currency
        case activityId = "activity_id"
        case role, active
    }
}

public struct FinancialObservation: Codable, Equatable, Sendable {
    public var observationId: UUID
    public var kind: String
    public var asOf: String
    public var amountMinor: Int64
    public var amount: String
    public var included: Bool?
    public var timeZone: String?
    enum CodingKeys: String, CodingKey {
        case observationId = "observation_id"
        case kind
        case asOf = "as_of"
        case amountMinor = "amount_minor"
        case amount
        case included
        case timeZone = "time_zone"
    }
}

public struct ExpensePreview: Codable, Equatable, Sendable {
    public var accountVersion: Int
    public var ready: Bool
    public var observations: [FinancialObservation]
    public var before: FinancialBalance
    public var after: FinancialBalance?
    public var previewToken: String?
    enum CodingKeys: String, CodingKey {
        case accountVersion = "account_version"
        case ready
        case observations
        case before
        case after
        case previewToken = "preview_token"
    }
}

public struct ExpenseRequest: Codable, Equatable, Sendable {
    public var expectedVersion: Int
    public var amount: String
    public var occurredAt: String
    public var timeZone: String
    public var note: String?
    public var categoryId: String?
    public var coverage: [FinancialCoverage]
    public var expectedRevision: Int?
    public var reason: String?
    public var previewToken: String?
    public init(expectedVersion: Int, amount: String, occurredAt: String, timeZone: String, note: String? = nil,
                categoryId: String? = nil, coverage: [FinancialCoverage] = [], expectedRevision: Int? = nil,
                reason: String? = nil, previewToken: String? = nil) {
        self.expectedVersion = expectedVersion; self.amount = amount; self.occurredAt = occurredAt
        self.timeZone = timeZone; self.note = note; self.categoryId = categoryId; self.coverage = coverage
        self.expectedRevision = expectedRevision; self.reason = reason; self.previewToken = previewToken
    }
    enum CodingKeys: String, CodingKey {
        case expectedVersion = "expected_version"
        case amount
        case occurredAt = "occurred_at"
        case timeZone = "time_zone"
        case note
        case categoryId = "category_id"
        case coverage
        case expectedRevision = "expected_revision"
        case reason
        case previewToken = "preview_token"
    }
}

public struct ExpenseReceipt: Codable, Equatable, Sendable {
    public var account: FinancialAccount
    public var activity: FinancialActivity
    public var replayed: Bool
    enum CodingKeys: String, CodingKey {
        case account
        case activity
        case replayed
    }
}

public struct BalanceCheckRequest: Codable, Equatable, Sendable {
    public var expectedVersion: Int
    public var amount: String
    public var asOf: String
    public var timeZone: String
    public var source: String
    public var note: String?
    public var previewToken: String?
    public init(expectedVersion: Int, amount: String, asOf: String, timeZone: String, note: String? = nil, previewToken: String? = nil) {
        self.expectedVersion = expectedVersion; self.amount = amount; self.asOf = asOf
        self.timeZone = timeZone; self.source = "manual"; self.note = note; self.previewToken = previewToken
    }
    enum CodingKeys: String, CodingKey {
        case expectedVersion = "expected_version"
        case amount
        case asOf = "as_of"
        case timeZone = "time_zone"
        case source
        case note
        case previewToken = "preview_token"
    }
}

public struct BalanceCheckPreview: Codable, Equatable, Sendable {
    public var accountVersion: Int
    public var currency: String
    public var currencyFractionDigits: Int
    public var expectedAmountMinor: Int64?
    public var observedAmountMinor: Int64
    public var differenceMinor: Int64?
    public var asOf: String
    public var timeZone: String
    public var previewToken: String
    enum CodingKeys: String, CodingKey {
        case accountVersion = "account_version"
        case currency
        case currencyFractionDigits = "currency_fraction_digits"
        case expectedAmountMinor = "expected_amount_minor"
        case observedAmountMinor = "observed_amount_minor"
        case differenceMinor = "difference_minor"
        case asOf = "as_of"
        case timeZone = "time_zone"
        case previewToken = "preview_token"
    }
}

public struct FinancialCheck: Codable, Equatable, Sendable {
    public var recordId: UUID
    public var revision: Int
    public var kind: String
    public var asOf: String
    public var timeZone: String
    public var source: String
    public var note: String?
    public var expectedAmountMinor: Int64?
    public var observedAmountMinor: Int64
    public var differenceMinor: Int64?
    public var unexplainedMinor: Int64?
    public var recordedAt: String
    public var recordedBy: String?
    enum CodingKeys: String, CodingKey {
        case recordId = "record_id"
        case revision
        case kind
        case asOf = "as_of"
        case timeZone = "time_zone"
        case source
        case note
        case expectedAmountMinor = "expected_amount_minor"
        case observedAmountMinor = "observed_amount_minor"
        case differenceMinor = "difference_minor"
        case unexplainedMinor = "unexplained_minor"
        case recordedAt = "recorded_at"
        case recordedBy = "recorded_by"
    }
}

public struct BalanceCheckReceipt: Codable, Equatable, Sendable {
    public var account: FinancialAccount
    public var check: FinancialCheck
    public var replayed: Bool
    enum CodingKeys: String, CodingKey {
        case account
        case check
        case replayed
    }
}

public struct FinancialCurrencySummary: Codable, Equatable, Sendable {
    public var currency: String
    public var currencyFractionDigits: Int
    public var cashMinor: String
    public var otherAssetsMinor: String
    public var asOf: String?
    public var assetsMinor: String
    public var debtsMinor: String
    public var netWorthMinor: String
    public var knownAccounts: Int
    public var unknownAccounts: Int
    public var recordedSpendingMinor: String
    public var grossIncomeMinor: String?
    public var grossPurchasesMinor: String?
    public var refundsMinor: String?
    public var netSpendingMinor: String?
    enum CodingKeys: String, CodingKey {
        case currency
        case currencyFractionDigits = "currency_fraction_digits"
        case cashMinor = "cash_minor"
        case otherAssetsMinor = "other_assets_minor"
        case asOf = "as_of"
        case assetsMinor = "assets_minor"
        case debtsMinor = "debts_minor"
        case netWorthMinor = "net_worth_minor"
        case knownAccounts = "known_accounts"
        case unknownAccounts = "unknown_accounts"
        case recordedSpendingMinor = "recorded_spending_minor"
        case grossIncomeMinor = "gross_income_minor", grossPurchasesMinor = "gross_purchases_minor"
        case refundsMinor = "refunds_minor", netSpendingMinor = "net_spending_minor"
    }
}

public struct FinancialHomePeriod: Codable, Equatable, Sendable {
    public var month: String
    public var timeZone: String
    public var startAt: String
    public var endAtExclusive: String
    enum CodingKeys: String, CodingKey {
        case month, timeZone = "time_zone", startAt = "start_at", endAtExclusive = "end_at_exclusive"
    }
}

public struct FinancialHome: Codable, Equatable, Sendable {
    public var currencies: [FinancialCurrencySummary]
    public var recentActivity: [FinancialActivity]
    public var recordedAt: String
    public var period: FinancialHomePeriod?
    public var coverage: String?
    enum CodingKeys: String, CodingKey {
        case currencies
        case recentActivity = "recent_activity"
        case recordedAt = "recorded_at"
        case period, coverage
    }
}

public struct FinancialPage<Item: Codable & Equatable & Sendable>: Codable, Equatable, Sendable {
    public var items: [Item]
    public var nextCursor: String?
    enum CodingKeys: String, CodingKey {
        case items
        case nextCursor = "next_cursor"
    }
}

public struct OpeningCoverage: Codable, Equatable, Sendable {
    public let activityId: UUID
    public let included: Bool
    public init(activityId: UUID, included: Bool) { self.activityId = activityId; self.included = included }
    enum CodingKeys: String, CodingKey { case activityId = "activity_id", included }
}
public struct OpeningActivity: Decodable, Sendable {
    public let activityId: UUID
    public let amount: String
    public let occurredAt: String
    public let note: String?
    public let included: Bool?
    enum CodingKeys: String, CodingKey { case activityId = "activity_id", amount, occurredAt = "occurred_at", note, included }
}
public struct OpeningPreview: Decodable, Sendable {
    public let ready: Bool
    public let activities: [OpeningActivity]
    public let before: FinancialBalance
    public let after: FinancialBalance?
    public let previewToken: String?
    enum CodingKeys: String, CodingKey { case ready, activities, before, after, previewToken = "preview_token" }
}
public struct FinancialCategory: Decodable, Sendable, Identifiable {
    public let id: String
    public let kind: String
}
public struct FinancialCategoryCatalog: Decodable, Sendable { public let categories: [FinancialCategory] }
