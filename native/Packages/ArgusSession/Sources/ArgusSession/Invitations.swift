import Foundation

/// A typed code, or the token a link or QR carries. Exactly one reaches the server.
public enum InviteSecret: Equatable, Sendable {
    case token(String)
    case code(String)

    /// The API contract caps a code at 32 characters, so longer bare text is a token.
    public init?(input: String) {
        let value = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return nil }
        if let url = URL(string: value), url.scheme != nil {
            guard let token = InvitationLink.token(in: url) else { return nil }
            self = .token(token)
        } else if value.count > 32 {
            self = .token(value)
        } else {
            self = .code(value)
        }
    }
}

extension InviteSecret: Encodable {
    private enum CodingKeys: String, CodingKey { case token, code }
    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case .token(let value): try container.encode(value, forKey: .token)
        case .code(let value): try container.encode(value, forKey: .code)
        }
    }
}

/// The two link shapes the server builds: `https://cuadrao.ai/invite#<token>` and `argus-household://invite#<token>`.
public enum InvitationLink {
    public static func token(in url: URL) -> String? {
        guard let fragment = url.fragment, !fragment.isEmpty, url.query == nil else { return nil }
        switch url.scheme?.lowercased() {
        case "https":
            guard url.host?.lowercased() == "cuadrao.ai", url.path == "/invite", url.port == nil else { return nil }
        case "argus-household":
            guard url.host?.lowercased() == "invite", url.path.isEmpty || url.path == "/" else { return nil }
        default:
            return nil
        }
        return fragment
    }

    public static func isUniversal(_ url: URL) -> Bool { url.scheme?.lowercased() == "https" }
}

/// Beta admission only. Household membership and account access are separate facts with separate owners.
public struct BetaAccess: Decodable, Equatable, Sendable {
    public let gateEnabled: Bool
    public let admitted: Bool
    public let waitlistURL: URL?
    public let testFlightURL: URL?
    enum CodingKeys: String, CodingKey {
        case admitted, gateEnabled = "gate_enabled", waitlistURL = "waitlist_url", testFlightURL = "testflight_url"
    }
}

public struct InviteQuota: Decodable, Equatable, Sendable {
    public let limit: Int
    public let used: Int
    public let remaining: Int
}

public enum InviteState: String, Decodable, Sendable { case pending, accepted, revoked, expired }

public struct SentInvite: Decodable, Identifiable, Equatable, Sendable {
    public enum Kind: String, Decodable, Sendable { case beta, household }
    public let id: UUID
    public let kind: Kind
    public let invitationId: UUID?
    public let state: InviteState
    public let sentAt: Date
    public let expiresAt: Date?
    public let acceptedAt: Date?
    enum CodingKeys: String, CodingKey {
        case id, kind, state
        case invitationId = "invitation_id", sentAt = "sent_at", expiresAt = "expires_at", acceptedAt = "accepted_at"
    }
}

public struct SentInvites: Decodable, Equatable, Sendable {
    public let quota: InviteQuota
    public let invitations: [SentInvite]
    public init(quota: InviteQuota, invitations: [SentInvite]) { self.quota = quota; self.invitations = invitations }
}

/// Secrets arrive once. A replayed create carries none of them.
public struct CreatedInvite: Decodable, Equatable, Sendable {
    public enum Kind: String, Decodable, Sendable { case beta, groupLink = "group_link" }
    public let id: UUID
    public let kind: Kind
    public let expiresAt: Date
    public let token: String?
    public let code: String?
    public let link: URL?
    public let sourceLabel: String?
    public let cap: Int?
    public let replayed: Bool
    enum CodingKeys: String, CodingKey {
        case id, kind, token, code, link, cap, replayed
        case expiresAt = "expires_at", sourceLabel = "source_label"
    }
    public init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(UUID.self, forKey: .id); kind = try c.decode(Kind.self, forKey: .kind)
        expiresAt = try c.decode(Date.self, forKey: .expiresAt)
        token = try c.decodeIfPresent(String.self, forKey: .token); code = try c.decodeIfPresent(String.self, forKey: .code)
        link = try c.decodeIfPresent(String.self, forKey: .link).flatMap(URL.init(string:))
        sourceLabel = try c.decodeIfPresent(String.self, forKey: .sourceLabel); cap = try c.decodeIfPresent(Int.self, forKey: .cap)
        replayed = try c.decodeIfPresent(Bool.self, forKey: .replayed) ?? false
    }
    public var hasSecrets: Bool { code != nil || link != nil }
}

public struct CreatedInviteResponse: Decodable, Equatable, Sendable {
    public let invitation: CreatedInvite
    public let quota: InviteQuota?
}

public struct InvitePreview: Decodable, Equatable, Sendable {
    public enum Kind: String, Decodable, Sendable { case beta, household, groupLink = "group_link" }
    public let kind: Kind
    public let available: Bool
    public let expiresAt: Date
    public let householdName: String?
    enum CodingKeys: String, CodingKey { case kind, available, expiresAt = "expires_at", householdName = "household_name" }
}

public struct RedeemResult: Decodable, Equatable, Sendable {
    public enum Outcome: String, Decodable, Sendable { case admitted, alreadyAdmitted = "already_admitted" }
    public let admitted: Bool
    public let outcome: Outcome
    public let kind: CreatedInvite.Kind
    public let replayed: Bool
}

public struct GroupLink: Decodable, Identifiable, Equatable, Sendable {
    public enum State: String, Decodable, Sendable { case open, full, expired, revoked }
    public let id: UUID
    public let sourceLabel: String
    public let cap: Int
    public let redeemed: Int
    public let overflow: Int
    public let expiresAt: Date
    public let revokedAt: Date?
    public let state: State
    enum CodingKeys: String, CodingKey {
        case id, cap, redeemed, overflow, state
        case sourceLabel = "source_label", expiresAt = "expires_at", revokedAt = "revoked_at"
    }
}

struct GroupLinkList: Decodable { let links: [GroupLink] }

/// The founder's group-link form, held to the server's limits before any request.
public struct GroupLinkDraft: Equatable, Sendable {
    public enum Invalid: Error, Equatable, Sendable { case label, cap, expiry }
    /// Counted in Unicode scalars, as the server's `max_length` counts code points.
    public static let labelLimit = 80
    public static let capLimit = 10_000
    public static let longestLifetime: TimeInterval = 365 * 86_400

    public let label: String
    public let cap: Int
    public let expires: String

    public init(label: String, cap: Int, expiresAt: Date, now: Date = Date()) throws {
        let name = label.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, name.unicodeScalars.count <= Self.labelLimit else { throw Invalid.label }
        guard (1...Self.capLimit).contains(cap) else { throw Invalid.cap }
        guard expiresAt > now, expiresAt <= now.addingTimeInterval(Self.longestLifetime) else { throw Invalid.expiry }
        self.label = name; self.cap = cap; expires = InvitationDates.string(expiresAt)
    }
}

/// Every invite lookup and command failure the screens can explain, from the server's problem code.
/// `unavailable` means no answer arrived; every other case is the server's answer.
public enum InvitationProblem: Error, Equatable, Sendable {
    case invalid, expired, revoked, used, full, rateLimited
    case householdInvitation, quotaExhausted, founderOnly, invitationRequired
    case surfaceUnavailable, signedOut, refused, unavailable

    public init(_ error: any Error) {
        if let problem = error as? InvitationProblem { self = problem; return }
        guard let failure = error as? SessionFailure else { self = .unavailable; return }
        switch failure {
        case .unauthorized, .staleOperation, .pendingSignOut, .unsupportedAnonymousTransfer: self = .signedOut
        case .rejected(let status, let code): self = Self.problem(status: status, code: code)
        default: self = .unavailable
        }
    }

    static func problem(status: Int, code: String?) -> InvitationProblem {
        switch code {
        case "invitation_not_found", "validation_error": .invalid
        case "invitation_expired": .expired
        case "invitation_revoked": .revoked
        case "invitation_consumed": .used
        case "group_link_full": .full
        case "invite_rate_limited": .rateLimited
        case "household_invitation_requires_accept": .householdInvitation
        case "beta_invite_quota_exhausted": .quotaExhausted
        case "founder_required": .founderOnly
        case "beta_invite_required": .invitationRequired
        case "invites_unavailable", "households_unavailable": .surfaceUnavailable
        case "account_conversion_required", "verified_user_required": .signedOut
        case "invite_request_invalid", "household_admin_required", "idempotency_conflict", "idempotency_key_required": .refused
        default: status == 429 ? .rateLimited : status >= 500 ? .unavailable : .refused
        }
    }
}

public protocol InvitesTransport: Sendable {
    func send(route: String, path: String, method: String, body: Data?, key: String?) async throws -> Data
}

public struct SessionInvitesTransport: InvitesTransport {
    private let controller: SessionController
    private let identity: SessionSnapshot
    public init(controller: SessionController, identity: SessionSnapshot) {
        self.controller = controller; self.identity = identity
    }
    public func send(route: String, path: String, method: String, body: Data?, key: String?) async throws -> Data {
        try await controller.financialRequest(route: route, path: path, method: method, body: body, key: key, expectedIdentity: identity)
    }
}

/// The `/api/v1/invites` surface. Every failure surfaces as an `InvitationProblem`.
public struct InvitesClient: Sendable {
    private let transport: any InvitesTransport
    public init(transport: any InvitesTransport) { self.transport = transport }

    public func access() async throws -> BetaAccess { try await get("/access") }
    public func sent() async throws -> SentInvites { try await get("") }
    public func groupLinks() async throws -> [GroupLink] { (try await get("/group-links") as GroupLinkList).links }

    public func createInvite(key: UUID) async throws -> CreatedInviteResponse {
        try await call("", method: "POST", body: Data("{}".utf8), key: key)
    }
    public func preview(_ secret: InviteSecret) async throws -> InvitePreview {
        try await call("/preview", method: "POST", body: try JSONEncoder().encode(secret))
    }
    public func redeem(_ secret: InviteSecret) async throws -> RedeemResult {
        try await call("/redeem", method: "POST", body: try JSONEncoder().encode(secret))
    }
    public func createGroupLink(_ draft: GroupLinkDraft, key: UUID) async throws -> CreatedInviteResponse {
        let body: [String: Any] = ["source_label": draft.label, "cap": draft.cap, "expires_at": draft.expires]
        return try await call("/group-links", method: "POST", body: try JSONSerialization.data(withJSONObject: body), key: key)
    }
    public func revokeGroupLink(_ id: UUID) async throws {
        _ = try await raw("/group-links/" + id.uuidString.lowercased() + "/revoke", method: "POST", body: nil, key: nil)
    }

    private func get<Value: Decodable>(_ path: String) async throws -> Value { try await call(path, method: "GET") }
    private func call<Value: Decodable>(_ path: String, method: String, body: Data? = nil, key: UUID? = nil) async throws -> Value {
        let data = try await raw(path, method: method, body: body, key: key?.uuidString)
        do { return try InvitationDates.decoder().decode(Value.self, from: data) }
        catch { throw InvitationProblem.unavailable }
    }
    private func raw(_ path: String, method: String, body: Data?, key: String?) async throws -> Data {
        do { return try await transport.send(route: "invites", path: path, method: method, body: body, key: key) }
        catch { throw InvitationProblem(error) }
    }
}

/// Server datetimes are ISO 8601 with or without fractional seconds.
public enum InvitationDates {
    public static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            guard let date = date(value) else {
                throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Not an ISO 8601 date."))
            }
            return date
        }
        return decoder
    }
    public static func date(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
    }
    public static func string(_ date: Date) -> String { ISO8601DateFormatter().string(from: date) }
}
