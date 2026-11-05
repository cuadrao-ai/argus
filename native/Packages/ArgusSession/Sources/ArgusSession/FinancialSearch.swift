import Foundation

public enum FinancialSearchKind: String, Codable, CaseIterable, Sendable {
    case account, activity, expectation, budget, goal, debt
}

public enum FinancialSearchHit: Decodable, Sendable, Identifiable {
    case account(FinancialAccount)
    case activity(FinancialActivityDetail, archived: Bool)
    case expectation(FinancialExpectation)
    case budget(FinancialBudget)
    case goal(FinancialGoalProgress)
    case debt(FinancialDebtProgress)

    enum CodingKeys: String, CodingKey { case kind, account, activity, expectation, archived, budget, goal, debt }
    public init(from decoder: any Decoder) throws {
        let value = try decoder.container(keyedBy: CodingKeys.self)
        switch try value.decode(FinancialSearchKind.self, forKey: .kind) {
        case .account: self = .account(try value.decode(FinancialAccount.self, forKey: .account))
        case .activity: self = .activity(try value.decode(FinancialActivityDetail.self, forKey: .activity), archived: try value.decode(Bool.self, forKey: .archived))
        case .debt: self = .debt(try value.decode(FinancialDebtProgress.self, forKey: .debt))
        case .goal: self = .goal(try value.decode(FinancialGoalProgress.self, forKey: .goal))
        case .budget: self = .budget(try value.decode(FinancialBudget.self, forKey: .budget))
        case .expectation: self = .expectation(try value.decode(FinancialExpectation.self, forKey: .expectation))
        }
    }
    public var kind: FinancialSearchKind {
        switch self { case .account: .account; case .activity: .activity; case .expectation: .expectation; case .budget: .budget; case .goal: .goal; case .debt: .debt }
    }
    public var recordID: UUID {
        switch self { case .account(let value): value.id; case .activity(let value, _): value.activityId; case .expectation(let value): value.id; case .budget(let value): value.id; case .goal(let value): value.id; case .debt(let value): value.id }
    }
    public var id: String { kind.rawValue + "." + recordID.uuidString }
    public var currency: String {
        switch self { case .account(let value): value.currency; case .activity(let value, _): value.currency; case .expectation(let value): value.currency; case .budget(let value): value.currency; case .goal(let value): value.goal.currency; case .debt(let value): value.debt.currency }
    }
    public var amount: String? {
        switch self { case .account(let value): value.balance.amount; case .activity(let value, _): value.amount; case .expectation(let value): value.amount; case .budget(let value): value.limit; case .goal(let value): value.goal.target; case .debt(let value): value.balance.amount }
    }
    public var archived: Bool {
        switch self { case .account(let value): value.archived; case .activity(_, let archived): archived; case .expectation(let value): value.archived; case .budget(let value): value.archived; case .goal(let value): value.goal.archived; case .debt(let value): value.debt.archived }
    }
}

public struct FinancialSearchPage: Decodable, Sendable {
    public let items: [FinancialSearchHit]
    public let nextCursor: String?
    enum CodingKeys: String, CodingKey { case items, nextCursor = "next_cursor" }
}

extension SessionController {
    public func financialSearch(query: String, kind: FinancialSearchKind?, currency: String?, cursor: String?, expectedIdentity: SessionSnapshot) async throws -> FinancialSearchPage {
        var parameters = [URLQueryItem(name: "q", value: query)]
        if let kind { parameters.append(URLQueryItem(name: "kind", value: kind.rawValue)) }
        if let currency { parameters.append(URLQueryItem(name: "currency", value: currency)) }
        if let cursor { parameters.append(URLQueryItem(name: "cursor", value: cursor)) }
        let data = try await financialRequest(route: "financial-search", query: parameters, expectedIdentity: expectedIdentity)
        do { return try JSONDecoder().decode(FinancialSearchPage.self, from: data) }
        catch { throw SessionFailure.invalidResponse }
    }

    public func financialExpectation(_ id: UUID, expectedIdentity: SessionSnapshot) async throws -> FinancialExpectation {
        let data = try await financialRequest(route: "financial-plan", path: "/expectations/" + id.uuidString, expectedIdentity: expectedIdentity)
        do { return try JSONDecoder().decode(FinancialExpectation.self, from: data) }
        catch { throw SessionFailure.invalidResponse }
    }
}
