import Foundation

public struct Household: Decodable, Identifiable, Sendable {
    public let id: UUID
    public let name: String?
    public let version: Int
    public let membershipId: UUID
    public let adminMembershipId: UUID
    public let members: [HouseholdMember]
    public let invitations: [HouseholdInvitation]
    public let shares: [HouseholdShare]
    public var isAdmin: Bool { membershipId == adminMembershipId }
    enum CodingKeys: String, CodingKey {
        case id, name, version, members, invitations, shares
        case membershipId = "membership_id", adminMembershipId = "admin_membership_id"
    }
}
public struct HouseholdList: Decodable, Sendable { public let households: [Household] }
public struct HouseholdMember: Decodable, Identifiable, Sendable {
    public let userId: UUID
    public let membershipId: UUID
    public let displayName: String
    public let isSelf: Bool
    public let isAdmin: Bool
    public var id: UUID { membershipId }
    enum CodingKeys: String, CodingKey { case userId = "user_id", membershipId = "membership_id", displayName = "display_name", isSelf = "is_self", isAdmin = "is_admin" }
}
public struct HouseholdInvitation: Decodable, Identifiable, Sendable {
    public let id: UUID
    public let expiresAt: String
    public let state: String
    public let token: String?
    public let code: String?
    public let link: String?
    enum CodingKeys: String, CodingKey { case id, state, token, code, link, expiresAt = "expires_at" }
}
public struct HouseholdShare: Decodable, Sendable {
    public let accountId: UUID
    public let recipients: [HouseholdRecipient]
    enum CodingKeys: String, CodingKey { case accountId = "account_id", recipients }
}
public struct HouseholdRecipient: Codable, Sendable {
    public var membershipId: UUID
    public var permission: String
    public init(membershipId: UUID, permission: String = "view") { self.membershipId = membershipId; self.permission = permission }
    enum CodingKeys: String, CodingKey { case membershipId = "membership_id", permission }
}
public struct HouseholdInvitationPreview: Decodable, Sendable {
    public let name: String?
    public let expiresAt: String
    public let available: Bool
    enum CodingKeys: String, CodingKey { case name, available, expiresAt = "expires_at" }
}
public struct HouseholdAcceptance: Decodable, Sendable {
    public let householdId: UUID
    public let membershipId: UUID
    public let state: String
    enum CodingKeys: String, CodingKey { case householdId = "household_id", membershipId = "membership_id", state }
}
public struct HouseholdMutation: Decodable, Sendable {
    public let householdId: UUID
    public let membershipId: UUID?
    public let state: String
    public let replayed: Bool
    public let invitation: HouseholdInvitation?
    enum CodingKeys: String, CodingKey { case householdId = "household_id", membershipId = "membership_id", state, replayed, invitation }
}
public struct HouseholdFinancialCommand: Encodable, Sendable {
    public let membershipId: UUID
    public let expectedVersion: Int
    public let activity: FinancialActivityCommand
    public init(membershipId: UUID, expectedVersion: Int, activity: FinancialActivityCommand) {
        self.membershipId = membershipId; self.expectedVersion = expectedVersion; self.activity = activity
    }
    enum CodingKeys: String, CodingKey { case membershipId = "membership_id", expectedVersion = "expected_version", activity }
}
public typealias HouseholdFinancialAccount = FinancialAccountValue<UUID?>
public typealias HouseholdActivityOptions = FinancialActivityOptionsValue<UUID?>

public struct HouseholdAccount: Decodable, Identifiable, Sendable {
    public let account: HouseholdFinancialAccount
    public let ownerName: String
    public let permission: String
    public let isOwner: Bool
    public var id: UUID { account.id }
    enum CodingKeys: String, CodingKey { case account, ownerName = "owner_name", permission, isOwner = "is_owner" }
}
public struct HouseholdActivity: Decodable, Identifiable, Sendable {
    public let activity: HouseholdActivityValue
    public let authorName: String
    public let canEdit: Bool
    public let privateCounterpart: Bool
    public var id: UUID { activity.activityId }
    enum CodingKeys: String, CodingKey { case activity, authorName = "author_name", canEdit = "can_edit", privateCounterpart = "private_counterpart" }
}
public struct HouseholdActivityValue: Decodable, Sendable {
    public let activityId: UUID
    public let revision: Int
    public let kind: FinancialActivityKind
    public let amount: String?
    public let amountMinor: Int64?
    public let currencyFractionDigits: Int
    public let currency: String
    public let occurredAt: String
    public let timeZone: String
    public let note: String?
    public let categoryId: String?
    public let sourceId: String?
    public let purchaseActivityId: UUID?
    public let reversalOfActivityId: UUID?
    public let principalMinor: Int64?
    public let interestMinor: Int64?
    public let feesMinor: Int64?
    public let legs: [FinancialActivityLeg]
    enum CodingKeys: String, CodingKey {
        case revision, kind, amount, currency, note, legs
        case activityId = "activity_id", amountMinor = "amount_minor", currencyFractionDigits = "currency_fraction_digits", occurredAt = "occurred_at", timeZone = "time_zone"
        case categoryId = "category_id", sourceId = "source_id", purchaseActivityId = "purchase_activity_id", reversalOfActivityId = "reversal_of_activity_id"
        case principalMinor = "principal_minor", interestMinor = "interest_minor", feesMinor = "fees_minor"
    }
}
public struct HouseholdPosition: Decodable, Identifiable, Sendable {
    public let currency: String
    public let amountMinor: Int64
    public let currencyFractionDigits: Int
    public let unknownCount: Int
    public var id: String { currency }
    enum CodingKeys: String, CodingKey { case currency, amountMinor = "amount_minor", currencyFractionDigits = "currency_fraction_digits", unknownCount = "unknown_count" }
}
public struct HouseholdSnapshot: Decodable, Sendable {
    public let householdId: UUID
    public let membershipId: UUID
    public let authorizationVersion: Int
    public let accounts: [HouseholdAccount]
    public let activities: [HouseholdActivity]
    public let positions: [HouseholdPosition]
    enum CodingKeys: String, CodingKey {
        case householdId = "household_id", membershipId = "membership_id", authorizationVersion = "authorization_version", accounts, activities, positions
    }
}
public struct HouseholdAccountDetail: Decodable, Sendable { public let account: HouseholdAccount; public let activities: [HouseholdActivity] }
public struct HouseholdHistory: Decodable, Sendable { public let items: [HouseholdActivity] }
public struct HouseholdSearchHit: Decodable, Identifiable, Sendable {
    public enum Kind: String, Decodable, Sendable { case account, activity, plan }
    public let id: UUID
    public let kind: Kind
    public let title: String
    public let accountId: UUID?
    public let activityId: UUID?
    public let planRef: HouseholdPlanRef?
    enum CodingKeys: String, CodingKey { case id, kind, title, accountId = "account_id", activityId = "activity_id", planRef = "plan_ref" }
    public init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(UUID.self, forKey: .id); kind = try c.decode(Kind.self, forKey: .kind); title = try c.decode(String.self, forKey: .title)
        accountId = try c.decodeIfPresent(UUID.self, forKey: .accountId); activityId = try c.decodeIfPresent(UUID.self, forKey: .activityId)
        planRef = try c.decodeIfPresent(HouseholdPlanRef.self, forKey: .planRef)
        if kind == .plan, planRef == nil { throw DecodingError.dataCorruptedError(forKey: .planRef, in: c, debugDescription: "A plan search hit requires its typed destination.") }
    }
}
public struct HouseholdSearchPage: Decodable, Sendable {
    public let items: [HouseholdSearchHit]
    public let nextCursor: String?
    enum CodingKeys: String, CodingKey { case items, nextCursor = "next_cursor" }
}
public struct HouseholdReceipt: Decodable, Sendable { public let activity: HouseholdActivity; public let accounts: [HouseholdAccount]; public let replayed: Bool }

public struct HouseholdCommand: Encodable, Sendable {
    public var name: String?
    public var displayName: String?
    public var expectedVersion: Int?
    public var userId: UUID?
    public var token: String?
    public var code: String?
    public var recipients: [HouseholdRecipient]?
    public init(name: String? = nil, displayName: String? = nil, expectedVersion: Int? = nil, userId: UUID? = nil, token: String? = nil, recipients: [HouseholdRecipient]? = nil) {
        self.name = name; self.displayName = displayName; self.expectedVersion = expectedVersion; self.userId = userId; self.token = token; self.recipients = recipients
    }
    /// Preview or accept by exactly one secret, as the contract requires.
    public init(secret: InviteSecret, displayName: String? = nil) {
        self.displayName = displayName
        switch secret { case .token(let value): token = value; case .code(let value): code = value }
    }
    enum CodingKeys: String, CodingKey { case name, displayName = "display_name", expectedVersion = "expected_version", userId = "user_id", token, code, recipients }
}

extension SessionController {
    public func householdResponse<Value: Decodable & Sendable>(_ type: Value.Type, path: String = "", method: String = "GET", body: Data? = nil, key: UUID? = nil, query: [URLQueryItem] = [], expectedIdentity: SessionSnapshot) async throws -> Value {
        let route = path.hasPrefix("/invitations/") ? "household-invitations" : "households"
        let target = path.hasPrefix("/invitations/") ? String(path.dropFirst("/invitations".count)) : path
        let data = try await financialRequest(route: route, path: target, method: method, body: body, key: key?.uuidString, query: query, expectedIdentity: expectedIdentity)
        do { return try JSONDecoder().decode(Value.self, from: data) }
        catch { throw SessionFailure.invalidResponse }
    }
}
