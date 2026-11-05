import Foundation

public struct FinancialGoalPlan: Codable, Equatable, Sendable {
    public let sourceAccountId: UUID
    public let amount: String
    public let schedule: FinancialPlanSchedule
    public init(sourceAccountId: UUID, amount: String, schedule: FinancialPlanSchedule) {
        self.sourceAccountId = sourceAccountId; self.amount = amount; self.schedule = schedule
    }
    enum CodingKeys: String, CodingKey { case sourceAccountId = "source_account_id", amount, schedule }
}

public struct FinancialGoal: Codable, Equatable, Sendable, Identifiable {
    public let id: UUID
    public let version: Int
    public let name: String
    public let currency: String
    public let currencyFractionDigits: Int
    public let targetMinor: Int64
    public let target: String
    public let targetDate: String?
    public let destinationAccountId: UUID?
    public let contributionPlan: FinancialGoalPlan?
    public let allocations: [Allocation]
    public let archived: Bool
    public let earliestEffectiveDate: String
    public struct Allocation: Codable, Equatable, Sendable {
        public let accountId: UUID
        public let unlinkedMinor: Int64
        enum CodingKeys: String, CodingKey { case accountId = "account_id", unlinkedMinor = "unlinked_minor" }
    }
    enum CodingKeys: String, CodingKey {
        case id, version, name, currency, target, allocations, archived
        case currencyFractionDigits = "currency_fraction_digits", targetMinor = "target_minor", targetDate = "target_date"
        case destinationAccountId = "destination_account_id", contributionPlan = "contribution_plan", earliestEffectiveDate = "earliest_effective_date"
    }
}

public struct FinancialGoalPool: Codable, Equatable, Sendable, Identifiable {
    public let accountId: UUID
    public let accountName: String?
    public let currency: String
    public let accountVersion: Int
    public let ownershipShareBps: Int
    public let asOf: String?
    public let backingMinor: String?
    public let assignedMinor: String
    public let availableMinor: String?
    public let shortfallMinor: String?
    public let state: String
    public let affectedGoalIds: [UUID]
    public let affectedGoalNames: [String]
    public var id: UUID { accountId }
    enum CodingKeys: String, CodingKey {
        case currency, state, accountId = "account_id", accountName = "account_name", accountVersion = "account_version"
        case ownershipShareBps = "ownership_share_bps", asOf = "as_of", backingMinor = "backing_minor", assignedMinor = "assigned_minor"
        case availableMinor = "available_minor", shortfallMinor = "shortfall_minor", affectedGoalIds = "affected_goal_ids", affectedGoalNames = "affected_goal_names"
    }
}

public struct FinancialGoalContribution: Codable, Equatable, Sendable, Identifiable {
    public let id: UUID
    public let activityId: UUID
    public let activityRevision: Int?
    public let occurrenceId: String?
    public let sourceAccountId: UUID
    public let destinationAccountId: UUID
    public let treatment: String
    public let reviewedPersonalMinor: String
    public let currentPersonalMinor: String?
    public let counting: Bool
    public let status: String
    public let reason: String?
    public let activity: FinancialActivityDetail?
    enum CodingKeys: String, CodingKey {
        case id, treatment, counting, status, reason, activity
        case activityId = "activity_id", activityRevision = "activity_revision", occurrenceId = "occurrence_id"
        case sourceAccountId = "source_account_id", destinationAccountId = "destination_account_id"
        case reviewedPersonalMinor = "reviewed_personal_minor", currentPersonalMinor = "current_personal_minor"
    }
}

public struct FinancialGoalComponent: Codable, Equatable, Sendable {
    public let accountId: UUID
    public let assignedMinor: String
    public let supportedMinor: String?
    enum CodingKeys: String, CodingKey { case accountId = "account_id", assignedMinor = "assigned_minor", supportedMinor = "supported_minor" }
}

public struct FinancialGoalProgress: Codable, Equatable, Sendable, Identifiable {
    public let goal: FinancialGoal
    public let assignedMinor: String
    public let supportedMinor: String?
    public let independentlyBackedMinor: String
    public let remainingMinor: String?
    public let state: String
    public let reasons: [String]
    public let pools: [FinancialGoalPool]
    public let contributions: [FinancialGoalContribution]
    public let components: [FinancialGoalComponent]
    public let plannedMinor: String
    public let projectedMinor: String?
    public let projectionEndDate: String
    public var id: UUID { goal.id }
    public var meterFraction: Double? {
        guard let supportedMinor, let amount = Double(supportedMinor), goal.targetMinor > 0 else { return nil }
        return max(0, min(1, amount / Double(goal.targetMinor)))
    }
    enum CodingKeys: String, CodingKey {
        case goal, state, reasons, pools, contributions, components
        case assignedMinor = "assigned_minor", supportedMinor = "supported_minor", independentlyBackedMinor = "independently_backed_minor"
        case remainingMinor = "remaining_minor", plannedMinor = "planned_minor", projectedMinor = "projected_minor", projectionEndDate = "projection_end_date"
    }
}

public struct FinancialGoalCommand: Encodable, Sendable {
    public let name: String
    public let currency: String?
    public let target: String
    public let targetDate: String?
    public let destinationAccountId: UUID?
    public let contributionPlan: FinancialGoalPlan?
    public let includesSetup: Bool
    public let expectedVersion: Int?
    public let effectiveDate: String?
    public init(name: String, currency: String?, target: String, targetDate: String?, destinationAccountId: UUID?,
                contributionPlan: FinancialGoalPlan?, includesSetup: Bool = true, expectedVersion: Int? = nil, effectiveDate: String? = nil) {
        self.name = name; self.currency = currency; self.target = target; self.targetDate = targetDate
        self.destinationAccountId = destinationAccountId; self.contributionPlan = contributionPlan
        self.includesSetup = includesSetup; self.expectedVersion = expectedVersion; self.effectiveDate = effectiveDate
    }
    enum CodingKeys: String, CodingKey {
        case name, currency, target, targetDate = "target_date", destinationAccountId = "destination_account_id"
        case contributionPlan = "contribution_plan", expectedVersion = "expected_version", effectiveDate = "effective_date"
    }
    public func encode(to encoder: any Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(name, forKey: .name); try c.encodeIfPresent(currency, forKey: .currency)
        try c.encode(target, forKey: .target); try c.encode(targetDate, forKey: .targetDate)
        if includesSetup { try c.encode(destinationAccountId, forKey: .destinationAccountId); try c.encode(contributionPlan, forKey: .contributionPlan) }
        try c.encodeIfPresent(expectedVersion, forKey: .expectedVersion); try c.encodeIfPresent(effectiveDate, forKey: .effectiveDate)
    }
}

public struct FinancialGoalAllocationCommand: Encodable, Sendable {
    public struct Change: Encodable, Sendable {
        public let goalId: UUID
        public let expectedVersion: Int
        public let accountId: UUID
        public let amount: String
        public let releaseClaimIds: [UUID]
        public init(goalId: UUID, expectedVersion: Int, accountId: UUID, amount: String, releaseClaimIds: [UUID] = []) {
            self.goalId = goalId; self.expectedVersion = expectedVersion; self.accountId = accountId; self.amount = amount; self.releaseClaimIds = releaseClaimIds
        }
        enum CodingKeys: String, CodingKey { case goalId = "goal_id", expectedVersion = "expected_version", accountId = "account_id", amount, releaseClaimIds = "release_claim_ids" }
    }
    public let changes: [Change]
    public let expectedAccountVersions: [String: Int]
    public init(changes: [Change], expectedAccountVersions: [String: Int]) { self.changes = changes; self.expectedAccountVersions = expectedAccountVersions }
    enum CodingKeys: String, CodingKey { case changes, expectedAccountVersions = "expected_account_versions" }
}

public struct FinancialGoalLinkCommand: Encodable, Sendable {
    public let expectedVersion: Int
    public let activityId: UUID
    public let activityRevision: Int
    public let treatment: String
    public let occurrenceId: String?
    public let expectedAccountVersions: [String: Int]
    public init(expectedVersion: Int, activityId: UUID, activityRevision: Int, treatment: String, occurrenceId: String?, expectedAccountVersions: [String: Int]) {
        self.expectedVersion = expectedVersion; self.activityId = activityId; self.activityRevision = activityRevision
        self.treatment = treatment; self.occurrenceId = occurrenceId; self.expectedAccountVersions = expectedAccountVersions
    }
    enum CodingKeys: String, CodingKey { case expectedVersion = "expected_version", activityId = "activity_id", activityRevision = "activity_revision", treatment, occurrenceId = "occurrence_id", expectedAccountVersions = "expected_account_versions" }
}

public struct FinancialGoalRecordCommand: Codable, Sendable {
    public let expectedVersion: Int
    public let activity: FinancialActivityCommand
    public let occurrenceId: String?
    public init(expectedVersion: Int, activity: FinancialActivityCommand, occurrenceId: String? = nil) {
        self.expectedVersion = expectedVersion; self.activity = activity; self.occurrenceId = occurrenceId
    }
    enum CodingKeys: String, CodingKey { case expectedVersion = "expected_version", activity, occurrenceId = "occurrence_id" }
}

public struct FinancialGoalReleaseCommand: Encodable, Sendable {
    public let expectedVersion: Int
    public init(expectedVersion: Int) { self.expectedVersion = expectedVersion }
    enum CodingKeys: String, CodingKey { case expectedVersion = "expected_version" }
}

public struct FinancialGoalPreview: Decodable, Sendable { public let goal: FinancialGoalProgress; public let pools: [FinancialGoalPool]; public let money: FinancialActivityPreview }
struct FinancialGoalReceipt: Decodable { let goal: FinancialGoalProgress; let replayed: Bool }
struct FinancialGoalAllocationReceipt: Decodable { let goals: [FinancialGoalProgress]; let pools: [FinancialGoalPool]; let replayed: Bool }

extension SessionController {
    public func financialGoal(_ id: UUID, expectedIdentity: SessionSnapshot) async throws -> FinancialGoalProgress {
        try await planResponse(path: "/goals/" + id.uuidString, identity: expectedIdentity)
    }
    public func financialGoalCandidates(_ id: UUID, expectedIdentity: SessionSnapshot) async throws -> FinancialPurchaseCatalog {
        try await planResponse(path: "/goals/" + id.uuidString + "/contributions/candidates", identity: expectedIdentity)
    }
    public func financialGoalPreview(_ id: UUID, command: FinancialGoalRecordCommand, expectedIdentity: SessionSnapshot) async throws -> FinancialGoalPreview {
        try await planResponse(path: "/goals/" + id.uuidString + "/contributions/preview", method: "POST", body: encoded(command), identity: expectedIdentity)
    }
}
