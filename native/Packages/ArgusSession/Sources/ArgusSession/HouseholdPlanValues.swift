import Foundation

public struct HouseholdPlanCommonDefinition: Decodable, Sendable {
    public let name: String
    public let currency: String
    public let currencyFractionDigits: Int
    public let earliestEffectiveDate: String
    enum CodingKeys: String, CodingKey { case name, currency, currencyFractionDigits = "currency_fraction_digits", earliestEffectiveDate = "earliest_effective_date" }
}
public enum HouseholdPlanDefinition: Sendable {
    case budget(HouseholdPlanCommonDefinition, limit: String, month: String, categories: [String], uncategorized: Bool, published: Bool)
    case bill(HouseholdPlanCommonDefinition, amount: String, schedule: FinancialPlanSchedule)
    case goal(HouseholdPlanCommonDefinition, target: String, date: String?, schedule: FinancialPlanSchedule?, plannedContribution: String?)
    case debt(HouseholdPlanCommonDefinition, amount: String, schedule: FinancialPlanSchedule)
    public var common: HouseholdPlanCommonDefinition {
        switch self { case .budget(let c, _, _, _, _, _), .bill(let c, _, _), .goal(let c, _, _, _, _), .debt(let c, _, _): c }
    }
    public var amountMinor: String {
        switch self { case .budget(_, let v, _, _, _, _), .bill(_, let v, _), .goal(_, let v, _, _, _), .debt(_, let v, _): v }
    }
    public var schedule: FinancialPlanSchedule? {
        switch self { case .bill(_, _, let s), .debt(_, _, let s): s; case .goal(_, _, _, let s, _): s; case .budget: nil }
    }
    enum Keys: String, CodingKey {
        case limit = "limit_minor", month, categories = "category_ids", uncategorized = "include_uncategorized", published = "publish_budget_scope", amount = "amount_minor", schedule, target = "target_minor", date = "target_date", plannedContribution = "planned_contribution_minor"
    }
    init(kind: HouseholdPlanKind, decoder: any Decoder) throws {
        let common = try HouseholdPlanCommonDefinition(from: decoder)
        let c = try decoder.container(keyedBy: Keys.self)
        switch kind {
        case .budget: self = .budget(common, limit: try c.decode(String.self, forKey: .limit), month: try c.decode(String.self, forKey: .month), categories: try c.decode([String].self, forKey: .categories), uncategorized: try c.decode(Bool.self, forKey: .uncategorized), published: try c.decode(Bool.self, forKey: .published))
        case .bill: self = .bill(common, amount: try c.decode(String.self, forKey: .amount), schedule: try c.decode(FinancialPlanSchedule.self, forKey: .schedule))
        case .goal: self = .goal(common, target: try c.decode(String.self, forKey: .target), date: try c.decodeIfPresent(String.self, forKey: .date), schedule: try c.decodeIfPresent(FinancialPlanSchedule.self, forKey: .schedule), plannedContribution: try c.decodeIfPresent(String.self, forKey: .plannedContribution))
        case .debt: self = .debt(common, amount: try c.decode(String.self, forKey: .amount), schedule: try c.decode(FinancialPlanSchedule.self, forKey: .schedule))
        }
    }
}
public struct HouseholdPlanCommonProgress: Decodable, Sendable {
    public enum State: String, Decodable, Sendable { case active, reached, needsReview = "needs_review", unknown, archived }
    public let actualMinor: String?
    public let appliedMinor: String?
    public let remainingMinor: String?
    public let state: State
    public let debtBalanceMinor: String?
    public let debtState: String?
    enum CodingKeys: String, CodingKey {
        case actualMinor = "actual_minor", appliedMinor = "applied_minor", remainingMinor = "remaining_minor", state, debtBalanceMinor = "debt_balance_minor", debtState = "debt_state"
    }
}
public enum HouseholdPlanProgress: Sendable {
    case budget(HouseholdPlanCommonProgress, gross: String?, refunds: String?, spent: String?, overBudget: Bool?)
    case goal(HouseholdPlanCommonProgress, planned: String?, projected: String?)
    case bill(HouseholdPlanCommonProgress)
    case debt(HouseholdPlanCommonProgress)
    public var common: HouseholdPlanCommonProgress {
        switch self { case .budget(let c, _, _, _, _), .goal(let c, _, _), .bill(let c), .debt(let c): c }
    }
    enum Keys: String, CodingKey { case gross = "gross_minor", refunds = "refunds_minor", spent = "spent_minor", overBudget = "over_budget", planned = "planned_minor", projected = "projected_minor" }
    init(kind: HouseholdPlanKind, decoder: any Decoder) throws {
        let common = try HouseholdPlanCommonProgress(from: decoder)
        let c = try decoder.container(keyedBy: Keys.self)
        switch kind {
        case .budget: self = .budget(common, gross: try c.decode(String?.self, forKey: .gross), refunds: try c.decode(String?.self, forKey: .refunds), spent: try c.decode(String?.self, forKey: .spent), overBudget: try c.decode(Bool?.self, forKey: .overBudget))
        case .goal: self = .goal(common, planned: try c.decodeIfPresent(String.self, forKey: .planned), projected: try c.decodeIfPresent(String.self, forKey: .projected))
        case .bill: self = .bill(common)
        case .debt: self = .debt(common)
        }
    }
}

/// Typed dispatch is stored beside the exact confirmed bytes. Scope and identity
/// validation happens before a request can be sent, including after relaunch.
public enum HouseholdWriteOperation: Codable, Equatable, Sendable {
    case management
    case activity(householdId: UUID, activityId: UUID?)
    case plan(householdId: UUID, action: HouseholdPlanAction)
    public var householdId: UUID? {
        switch self { case .management: nil; case .activity(let id, _), .plan(let id, _): id }
    }
}
public enum HouseholdPlanAction: Codable, Equatable, Sendable {
    case create(HouseholdPlanKind)
    case share(HouseholdPlanRef)
    case edit(HouseholdPlanRef)
    case people(HouseholdPlanRef)
    case record(HouseholdPlanRef)
    case link(HouseholdPlanRef)
    case correct(HouseholdPlanRef, claim: UUID)
    case release(HouseholdPlanRef, claim: UUID)
    case allocation(HouseholdPlanRef)
    public var ref: HouseholdPlanRef? {
        switch self {
        case .create: nil
        case .share(let r), .edit(let r), .people(let r), .record(let r), .link(let r), .correct(let r, _), .release(let r, _), .allocation(let r): r
        }
    }
    public var path: String {
        switch self {
        case .create(let kind): "/" + kind.rawValue
        case .share(let r): r.path + "/share"
        case .edit(let r): r.path
        case .people(let r): r.path + "/participants"
        case .record(let r): r.path + "/contributions"
        case .link(let r): r.path + "/contributions/link"
        case .correct(let r, let id): r.path + "/contributions/" + id.uuidString
        case .release(let r, let id): r.path + "/contributions/" + id.uuidString + "/release"
        case .allocation(let r): r.path + "/allocations"
        }
    }
    public var method: String { switch self { case .edit, .correct: "PATCH"; case .people, .allocation: "PUT"; default: "POST" } }
}
