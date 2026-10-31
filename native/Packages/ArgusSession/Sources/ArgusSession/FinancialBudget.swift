import Foundation

public struct FinancialBudget: Codable, Equatable, Sendable, Identifiable {
    public let id: UUID
    public let version: Int
    public let name: String
    public let limitMinor: Int64
    public let limit: String
    public let currency: String
    public let currencyFractionDigits: Int
    public let month: String
    public let accountIds: [UUID]
    public let categoryIds: [String]
    public let includeUncategorized: Bool
    public let archived: Bool
    enum CodingKeys: String, CodingKey {
        case id, version, name, limit, currency, month, archived
        case limitMinor = "limit_minor", currencyFractionDigits = "currency_fraction_digits"
        case accountIds = "account_ids", categoryIds = "category_ids", includeUncategorized = "include_uncategorized"
    }
}

public struct FinancialBudgetProgress: Codable, Equatable, Sendable, Identifiable {
    public let budget: FinancialBudget
    public let period: FinancialHomePeriod
    public let grossPurchasesMinor: String
    public let refundsMinor: String
    public let spentMinor: String
    public let remainingMinor: String
    public let overBudgetMinor: String
    public let contributors: [FinancialActivityDetail]
    public var id: UUID { budget.id }
    public var isOverBudget: Bool { Decimal(string: overBudgetMinor).map { $0 > 0 } ?? false }
    public var meterFraction: Double {
        guard let spent = Double(spentMinor), budget.limitMinor > 0 else { return 0 }
        return max(0, min(1, spent / Double(budget.limitMinor)))
    }
    enum CodingKeys: String, CodingKey {
        case budget, period, contributors
        case grossPurchasesMinor = "gross_purchases_minor", refundsMinor = "refunds_minor"
        case spentMinor = "spent_minor", remainingMinor = "remaining_minor", overBudgetMinor = "over_budget_minor"
    }
}

public struct FinancialBudgetCommand: Encodable, Sendable {
    public let name: String
    public let limit: String
    public let currency: String
    public let month: String
    public let accountIds: [UUID]
    public let categoryIds: [String]
    public let includeUncategorized: Bool
    public let expectedVersion: Int?
    public init(name: String, limit: String, currency: String, month: String, accountIds: [UUID],
                categoryIds: [String], includeUncategorized: Bool, expectedVersion: Int? = nil) {
        self.name = name; self.limit = limit; self.currency = currency; self.month = month
        self.accountIds = accountIds.sorted { $0.uuidString < $1.uuidString }; self.categoryIds = categoryIds.sorted()
        self.includeUncategorized = includeUncategorized; self.expectedVersion = expectedVersion
    }
    enum CodingKeys: String, CodingKey {
        case name, limit, currency, month, accountIds = "account_ids", categoryIds = "category_ids"
        case includeUncategorized = "include_uncategorized", expectedVersion = "expected_version"
    }
}

public struct FinancialBudgetLifecycleCommand: Encodable, Sendable {
    public let expectedVersion: Int
    public let archived: Bool
    public init(expectedVersion: Int, archived: Bool) { self.expectedVersion = expectedVersion; self.archived = archived }
    enum CodingKeys: String, CodingKey { case expectedVersion = "expected_version", archived }
}

struct FinancialBudgetReceipt: Decodable { let budget: FinancialBudget; let replayed: Bool }

extension SessionController {
    public func financialBudget(_ id: UUID, expectedIdentity: SessionSnapshot) async throws -> FinancialBudgetProgress {
        let data = try await financialRequest(route: "financial-plan", path: "/budgets/" + id.uuidString, expectedIdentity: expectedIdentity)
        do { return try JSONDecoder().decode(FinancialBudgetProgress.self, from: data) }
        catch { throw SessionFailure.invalidResponse }
    }
}
