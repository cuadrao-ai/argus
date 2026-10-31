import Foundation

public struct HouseholdPlanScope: Encodable, Sendable {
    public let membershipId: UUID
    public let authorizationVersion: Int
    public let planVersion: Int?
    public init(membershipId: UUID, authorizationVersion: Int, planVersion: Int? = nil) {
        self.membershipId = membershipId; self.authorizationVersion = authorizationVersion; self.planVersion = planVersion
    }
    enum CodingKeys: String, CodingKey { case membershipId = "membership_id", authorizationVersion = "expected_authorization_version", planVersion = "expected_plan_version" }
}
public struct HouseholdPlanParticipantWrite: Encodable, Sendable {
    public let membershipId: UUID
    public let permission: HouseholdPlanPermission
    public init(membershipId: UUID, permission: HouseholdPlanPermission) { self.membershipId = membershipId; self.permission = permission }
    enum CodingKeys: String, CodingKey { case membershipId = "membership_id", permission }
}
public enum HouseholdResponsibilityPeriod: Sendable {
    case month(String), occurrence(UUID), schedule(UUID), agreedDate(String)
}
public struct HouseholdPlanResponsibilityWrite: Encodable, Sendable {
    public let membershipId: UUID
    public let amount: String?
    public let period: HouseholdResponsibilityPeriod
    public init(membershipId: UUID, amount: String?, period: HouseholdResponsibilityPeriod) { self.membershipId = membershipId; self.amount = amount; self.period = period }
    enum Keys: String, CodingKey { case membershipId = "membership_id", amount, period, occurrenceId = "occurrence_id", scheduleId = "schedule_id", agreedDate = "agreed_date" }
    public func encode(to encoder: any Encoder) throws {
        var c = encoder.container(keyedBy: Keys.self)
        try c.encode(membershipId, forKey: .membershipId); try c.encode(amount, forKey: .amount)
        switch period {
        case .month(let p): try c.encode(p, forKey: .period)
        case .occurrence(let id): try c.encode(id, forKey: .occurrenceId)
        case .schedule(let id): try c.encode(id, forKey: .scheduleId)
        case .agreedDate(let date): try c.encode(date, forKey: .agreedDate)
        }
    }
}
public struct HouseholdPlanPeopleCommand: Encodable, Sendable {
    public let kind: HouseholdPlanKind
    public let scope: HouseholdPlanScope
    public let participants: [HouseholdPlanParticipantWrite]
    public let responsibilities: [HouseholdPlanResponsibilityWrite]
    public let publishBudgetScope: Bool
    public init(kind: HouseholdPlanKind, scope: HouseholdPlanScope, participants: [HouseholdPlanParticipantWrite], responsibilities: [HouseholdPlanResponsibilityWrite], publishBudgetScope: Bool) {
        self.kind = kind; self.scope = scope; self.participants = participants; self.responsibilities = responsibilities; self.publishBudgetScope = publishBudgetScope
    }
    enum Keys: String, CodingKey { case participants, responsibilities, publishBudgetScope = "publish_budget_scope" }
    public func encode(to encoder: any Encoder) throws {
        try scope.encode(to: encoder)
        var c = encoder.container(keyedBy: Keys.self)
        try c.encode(participants, forKey: .participants); try c.encode(responsibilities, forKey: .responsibilities)
        if kind == .budget { try c.encode(publishBudgetScope, forKey: .publishBudgetScope) }
    }
}
public struct HouseholdPlanCreateCommand<Definition: Encodable & Sendable>: Encodable, Sendable {
    public let people: HouseholdPlanPeopleCommand
    public let definition: Definition
    public init(people: HouseholdPlanPeopleCommand, definition: Definition) { self.people = people; self.definition = definition }
    enum Keys: String, CodingKey { case definition }
    public func encode(to encoder: any Encoder) throws {
        try people.encode(to: encoder); var c = encoder.container(keyedBy: Keys.self); try c.encode(definition, forKey: .definition)
    }
}
/// Add the discriminator to the existing canonical create DTO. Its private
/// account controls belong only to the authenticated actor's creation sheet.
public struct HouseholdPlanDefinitionInput<Value: Encodable & Sendable>: Encodable, Sendable {
    public let kind: HouseholdPlanKind
    public let value: Value
    public init(kind: HouseholdPlanKind, value: Value) { self.kind = kind; self.value = value }
    enum Keys: String, CodingKey { case kind }
    public func encode(to encoder: any Encoder) throws {
        try value.encode(to: encoder); var c = encoder.container(keyedBy: Keys.self); try c.encode(kind, forKey: .kind)
    }
}
public struct HouseholdPlanDefinitionPatch: Encodable, Sendable {
    public var name: String?
    public var amount: String?
    public var plannedContributionAmount: String?
    public var targetDate: String?
    public var includesTargetDate: Bool
    public var month: String?
    public var categoryIds: [String]?
    public var includeUncategorized: Bool?
    public var schedule: FinancialPlanSchedule?
    public var effectiveDate: String?
    public var archived: Bool?
    public init(name: String? = nil, amount: String? = nil, plannedContributionAmount: String? = nil, targetDate: String? = nil, includesTargetDate: Bool = false, month: String? = nil, categoryIds: [String]? = nil, includeUncategorized: Bool? = nil, schedule: FinancialPlanSchedule? = nil, effectiveDate: String? = nil, archived: Bool? = nil) {
        self.name = name; self.amount = amount; self.plannedContributionAmount = plannedContributionAmount; self.targetDate = targetDate; self.includesTargetDate = includesTargetDate; self.month = month; self.categoryIds = categoryIds; self.includeUncategorized = includeUncategorized; self.schedule = schedule; self.effectiveDate = effectiveDate; self.archived = archived
    }
    enum CodingKeys: String, CodingKey { case name, amount, plannedContributionAmount = "planned_contribution_amount", targetDate = "target_date", month, categoryIds = "category_ids", includeUncategorized = "include_uncategorized", schedule, effectiveDate = "effective_date", archived }
    public func encode(to encoder: any Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(name, forKey: .name); try c.encodeIfPresent(amount, forKey: .amount)
        try c.encodeIfPresent(plannedContributionAmount, forKey: .plannedContributionAmount)
        if includesTargetDate { try c.encode(targetDate, forKey: .targetDate) }
        try c.encodeIfPresent(month, forKey: .month); try c.encodeIfPresent(categoryIds, forKey: .categoryIds)
        try c.encodeIfPresent(includeUncategorized, forKey: .includeUncategorized); try c.encodeIfPresent(schedule, forKey: .schedule)
        try c.encodeIfPresent(effectiveDate, forKey: .effectiveDate); try c.encodeIfPresent(archived, forKey: .archived)
    }
}
public struct HouseholdPlanEditCommand: Encodable, Sendable {
    public let scope: HouseholdPlanScope
    public let definition: HouseholdPlanDefinitionPatch?
    public let responsibilities: [HouseholdPlanResponsibilityWrite]?
    public init(scope: HouseholdPlanScope, definition: HouseholdPlanDefinitionPatch? = nil, responsibilities: [HouseholdPlanResponsibilityWrite]? = nil) { self.scope = scope; self.definition = definition; self.responsibilities = responsibilities }
    enum Keys: String, CodingKey { case definition, responsibilities }
    public func encode(to encoder: any Encoder) throws {
        try scope.encode(to: encoder); var c = encoder.container(keyedBy: Keys.self); try c.encodeIfPresent(definition, forKey: .definition); try c.encodeIfPresent(responsibilities, forKey: .responsibilities)
    }
}
public struct HouseholdContributionRecordCommand: Encodable, Sendable {
    public let scope: HouseholdPlanScope
    public let activity: FinancialActivityCommand
    public let purpose: HouseholdContributionPurpose
    public let occurrenceId: UUID?
    public init(scope: HouseholdPlanScope, activity: FinancialActivityCommand, purpose: HouseholdContributionPurpose, occurrenceId: UUID?) { self.scope = scope; self.activity = activity; self.purpose = purpose; self.occurrenceId = occurrenceId }
    enum Keys: String, CodingKey { case activity, purpose, occurrenceId = "occurrence_id" }
    public func encode(to encoder: any Encoder) throws {
        try scope.encode(to: encoder); var c = encoder.container(keyedBy: Keys.self); try c.encode(activity, forKey: .activity); try c.encode(purpose, forKey: .purpose); try c.encode(occurrenceId, forKey: .occurrenceId)
    }
}
public struct HouseholdContributionCorrectionCommand: Encodable, Sendable {
    public let scope: HouseholdPlanScope
    public let activity: FinancialActivityCommand
    public init(scope: HouseholdPlanScope, activity: FinancialActivityCommand) { self.scope = scope; self.activity = activity }
    enum Keys: String, CodingKey { case activity }
    public func encode(to encoder: any Encoder) throws { try scope.encode(to: encoder); var c = encoder.container(keyedBy: Keys.self); try c.encode(activity, forKey: .activity) }
}
public struct HouseholdContributionLinkCommand: Encodable, Sendable {
    public let scope: HouseholdPlanScope
    public let activityId: UUID
    public let activityRevision: Int
    public let expectedAccountVersions: [String: Int]
    public let purpose: HouseholdContributionPurpose
    public let occurrenceId: UUID?
    public let treatment: String
    public init(scope: HouseholdPlanScope, activityId: UUID, activityRevision: Int, expectedAccountVersions: [String: Int], purpose: HouseholdContributionPurpose, occurrenceId: UUID?, treatment: String) {
        self.scope = scope; self.activityId = activityId; self.activityRevision = activityRevision; self.expectedAccountVersions = expectedAccountVersions; self.purpose = purpose; self.occurrenceId = occurrenceId; self.treatment = treatment
    }
    enum Keys: String, CodingKey { case activityId = "activity_id", activityRevision = "activity_revision", expectedAccountVersions = "expected_account_versions", purpose, occurrenceId = "occurrence_id", treatment }
    public func encode(to encoder: any Encoder) throws {
        try scope.encode(to: encoder); var c = encoder.container(keyedBy: Keys.self); try c.encode(activityId, forKey: .activityId); try c.encode(activityRevision, forKey: .activityRevision); try c.encode(expectedAccountVersions, forKey: .expectedAccountVersions); try c.encode(purpose, forKey: .purpose); try c.encode(occurrenceId, forKey: .occurrenceId); try c.encode(treatment, forKey: .treatment)
    }
}
public struct HouseholdPlanAllocationCommand: Encodable, Sendable {
    public let scope: HouseholdPlanScope
    public let accountId: UUID
    public let amount: String
    public let expectedAccountVersions: [String: Int]
    public init(scope: HouseholdPlanScope, accountId: UUID, amount: String, expectedAccountVersions: [String: Int]) { self.scope = scope; self.accountId = accountId; self.amount = amount; self.expectedAccountVersions = expectedAccountVersions }
    enum Keys: String, CodingKey { case accountId = "account_id", amount, expectedAccountVersions = "expected_account_versions" }
    public func encode(to encoder: any Encoder) throws {
        try scope.encode(to: encoder); var c = encoder.container(keyedBy: Keys.self); try c.encode(accountId, forKey: .accountId); try c.encode(amount, forKey: .amount); try c.encode(expectedAccountVersions, forKey: .expectedAccountVersions)
    }
}

extension SessionController {
    public func householdPlanResponse<Value: Decodable & Sendable>(_ type: Value.Type, householdId: UUID, path: String = "", method: String = "GET", body: Data? = nil, expectedIdentity: SessionSnapshot) async throws -> Value {
        try await householdResponse(type, path: "/" + householdId.uuidString + "/plan" + path, method: method, body: body, expectedIdentity: expectedIdentity)
    }
    public func sendHouseholdPlanConfirmation(_ write: PendingFinancialConfirmation, expectedIdentity: SessionSnapshot) async throws -> HouseholdPlanReceipt {
        guard write.ownerId == expectedIdentity.profile.flatMap({ UUID(uuidString: $0.id) }),
              case .plan(let id, let action) = write.householdOperation,
              write.route == "households", write.path == "/" + id.uuidString + "/plan" + action.path,
              write.method == action.method, write.householdMembershipId != nil, write.householdAuthorizationVersion != nil else { throw SessionFailure.invalidResponse }
        let current = try await householdResponse(Household.self, path: "/" + id.uuidString, expectedIdentity: expectedIdentity)
        guard current.membershipId == write.householdMembershipId else { throw SessionFailure.rejected(status: 409, code: "shared_plan_scope_changed") }
        // Consent writes advance authorization themselves. The server checks the
        // exact receipt before CAS while still enforcing current access.
        return try await householdResponse(HouseholdPlanReceipt.self, path: write.path, method: write.method, body: write.body, key: write.key, expectedIdentity: expectedIdentity)
    }
}
