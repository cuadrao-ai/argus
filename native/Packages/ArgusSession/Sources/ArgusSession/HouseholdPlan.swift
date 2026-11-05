import Foundation

public enum HouseholdPlanKind: String, Codable, CaseIterable, Sendable { case budget, bill, goal, debt }
public enum HouseholdPlanPermission: String, Codable, Sendable { case view, edit }
public enum HouseholdContributionPurpose: String, Codable, CaseIterable, Sendable {
    case funding, spending, billPayment = "bill_payment", goalSaving = "goal_saving", debtPayment = "debt_payment"
}
public struct HouseholdPlanRef: Codable, Hashable, Sendable {
    public let kind: HouseholdPlanKind
    public let id: UUID
    public init(kind: HouseholdPlanKind, id: UUID) { self.kind = kind; self.id = id }
    public var path: String { "/" + kind.rawValue + "/" + id.uuidString }
}
public struct HouseholdPlanPerson: Codable, Identifiable, Sendable {
    public let membershipId: UUID
    public let displayName: String
    public var id: UUID { membershipId }
    enum CodingKeys: String, CodingKey { case membershipId = "membership_id", displayName = "display_name" }
}
public struct HouseholdPlanParticipant: Decodable, Identifiable, Sendable {
    public let membershipId: UUID
    public let displayName: String
    public let permission: HouseholdPlanPermission
    public let isSelf: Bool
    public var id: UUID { membershipId }
    enum CodingKeys: String, CodingKey { case membershipId = "membership_id", displayName = "display_name", permission, isSelf = "is_self" }
}
public struct HouseholdPlanResponsibility: Decodable, Sendable {
    public let person: HouseholdPlanPerson
    public let amountMinor: String?
    public let period: String?
    public let occurrenceId: UUID?
    public let scheduleId: UUID?
    public let agreedDate: String?
    enum CodingKeys: String, CodingKey {
        case person, amountMinor = "amount_minor", period, occurrenceId = "occurrence_id", scheduleId = "schedule_id", agreedDate = "agreed_date"
    }
}
public struct HouseholdPlanOccurrence: Decodable, Identifiable, Sendable {
    public enum Status: String, Decodable, Sendable { case pending, partial, fulfilled, needsReview = "needs_review", archived }
    public let id: UUID
    public let date: String
    public let amountMinor: String
    public let appliedMinor: String?
    public let remainingMinor: String?
    public let status: Status
    enum CodingKeys: String, CodingKey { case id, date, amountMinor = "amount_minor", appliedMinor = "applied_minor", remainingMinor = "remaining_minor", status }
}
public struct HouseholdAuthorizedOriginal: Decodable, Sendable {
    public let activityId: UUID
    public let accountId: UUID
    public let householdId: UUID?
    enum CodingKeys: String, CodingKey { case activityId = "activity_id", accountId = "account_id", householdId = "household_id" }
}
public struct HouseholdPlanContribution: Decodable, Identifiable, Sendable {
    public enum Status: String, Decodable, Sendable { case current, released, needsReview = "needs_review" }
    public let id: UUID
    public let person: HouseholdPlanPerson
    public let amountMinor: String?
    public let appliedMinor: String?
    public let currency: String
    public let currencyFractionDigits: Int
    public let date: String
    public let status: Status
    public let original: HouseholdAuthorizedOriginal?
    public let purpose: HouseholdContributionPurpose
    public let occurrenceId: UUID?
    public let canCorrect: Bool
    public let canRelease: Bool
    enum CodingKeys: String, CodingKey {
        case id, person, amountMinor = "amount_minor", appliedMinor = "applied_minor", currency, currencyFractionDigits = "currency_fraction_digits", date, status, original, purpose, occurrenceId = "occurrence_id", canCorrect = "can_correct", canRelease = "can_release"
    }
}
public struct HouseholdPlanAllocation: Decodable, Sendable {
    public let id: UUID
    public let person: HouseholdPlanPerson
    public let assignedMinor: String?
    public let supportedMinor: String?
    public let status: String
    public let canEdit: Bool
    enum CodingKeys: String, CodingKey { case id, person, assignedMinor = "assigned_minor", supportedMinor = "supported_minor", status, canEdit = "can_edit" }
}

/// A disclosed projection of one canonical definition. Private financial DTOs
/// never enter this type; kind-specific values come from the shared service.
public struct HouseholdPlan: Decodable, Identifiable, Sendable {
    public let ref: HouseholdPlanRef
    public let version: Int
    public let householdId: UUID
    public let membershipId: UUID
    public let authorizationVersion: Int
    public let owner: HouseholdPlanPerson
    public let permission: HouseholdPlanPermission
    public let isOwner: Bool
    public let participants: [HouseholdPlanParticipant]
    public let responsibilities: [HouseholdPlanResponsibility]
    public let occurrences: [HouseholdPlanOccurrence]
    public let contributions: [HouseholdPlanContribution]
    public let archived: Bool
    public let readOnly: Bool
    public let canRestore: Bool
    public let archiveReason: String?
    public let definition: HouseholdPlanDefinition
    public let progress: HouseholdPlanProgress
    public let allocations: [HouseholdPlanAllocation]
    public var id: UUID { ref.id }
    public var canEdit: Bool { permission == .edit && !readOnly }
    public var canManagePeople: Bool { isOwner && !readOnly }
    public var canContribute: Bool { !archived && !readOnly }

    enum CodingKeys: String, CodingKey {
        case ref, version, householdId = "household_id", membershipId = "membership_id", authorizationVersion = "authorization_version", owner, permission, isOwner = "is_owner", participants, responsibilities, occurrences, contributions, archived, readOnly = "read_only", canRestore = "can_restore", archiveReason = "archive_reason", definition, progress, allocations
    }
    public init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ref = try c.decode(HouseholdPlanRef.self, forKey: .ref); version = try c.decode(Int.self, forKey: .version)
        householdId = try c.decode(UUID.self, forKey: .householdId); membershipId = try c.decode(UUID.self, forKey: .membershipId)
        authorizationVersion = try c.decode(Int.self, forKey: .authorizationVersion)
        owner = try c.decode(HouseholdPlanPerson.self, forKey: .owner); permission = try c.decode(HouseholdPlanPermission.self, forKey: .permission)
        isOwner = try c.decode(Bool.self, forKey: .isOwner); participants = try c.decode([HouseholdPlanParticipant].self, forKey: .participants)
        responsibilities = try c.decode([HouseholdPlanResponsibility].self, forKey: .responsibilities)
        occurrences = try c.decode([HouseholdPlanOccurrence].self, forKey: .occurrences); contributions = try c.decode([HouseholdPlanContribution].self, forKey: .contributions)
        archived = try c.decode(Bool.self, forKey: .archived); readOnly = try c.decode(Bool.self, forKey: .readOnly)
        canRestore = try c.decode(Bool.self, forKey: .canRestore)
        archiveReason = try c.decodeIfPresent(String.self, forKey: .archiveReason)
        definition = try HouseholdPlanDefinition(kind: ref.kind, decoder: c.superDecoder(forKey: .definition))
        progress = try HouseholdPlanProgress(kind: ref.kind, decoder: c.superDecoder(forKey: .progress))
        allocations = ref.kind == .goal ? try c.decode([HouseholdPlanAllocation].self, forKey: .allocations) : []
    }
}
public struct HouseholdPlanSnapshot: Decodable, Sendable {
    public let householdId: UUID
    public let membershipId: UUID
    public let authorizationVersion: Int
    public let plans: [HouseholdPlan]
    enum CodingKeys: String, CodingKey { case householdId = "household_id", membershipId = "membership_id", authorizationVersion = "authorization_version", plans }
}
public struct HouseholdPlanReceipt: Decodable, Sendable { public let plan: HouseholdPlan; public let replayed: Bool }
public struct HouseholdPlanHistory: Decodable, Sendable { public let items: [HouseholdPlan] }
public struct HouseholdContributionPreview: Decodable, Sendable { public let plan: HouseholdPlan; public let money: FinancialActivityPreview }
public struct HouseholdContributionCandidates: Decodable, Sendable { public let items: [FinancialActivityDetail] }
public struct HouseholdPlanOptions: Decodable, Sendable {
    public struct Existing: Decodable, Identifiable, Sendable {
        public let ref: HouseholdPlanRef; public let name: String; public let version: Int; public let currency: String
        public var id: UUID { ref.id }
    }
    public let membershipId: UUID
    public let authorizationVersion: Int
    public let people: [HouseholdPlanPerson]
    public let money: FinancialActivityOptions
    public let ownedAccountIds: [UUID]
    public let existingDefinitions: [Existing]
    public let purposes: [String: [HouseholdContributionPurpose]]
    enum CodingKeys: String, CodingKey { case membershipId = "membership_id", authorizationVersion = "authorization_version", people, money, ownedAccountIds = "owned_account_ids", existingDefinitions = "existing_definitions", purposes }
}
