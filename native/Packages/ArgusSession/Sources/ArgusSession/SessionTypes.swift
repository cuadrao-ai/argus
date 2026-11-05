import Foundation

/// Safe, bounded failures. Never includes server prose, passwords, tokens or SDK errors.
public enum SessionFailure: Error, Equatable, Sendable {
    case accountDeletionInProgress
    case busy, invalidConfiguration, invalidResponse, unauthorized, unavailable
    case storageUnavailable, pendingSignOut, unsupportedAnonymousTransfer, staleOperation, credentialValidationRequired
    case rejected(status: Int, code: String?)
}

public struct SessionProfile: Equatable, Sendable, Decodable {
    public let id: String
    public let email: String?
    public let displayName: String?
    /// What greetings call the person; nil means they are greeted without a name.
    public let preferredName: String?
    public let language: String?
    public let currency: String?
    public let currencyOverride: String?
    init(id: String, email: String?, displayName: String?, preferredName: String? = nil, language: String?,
         currency: String? = nil, currencyOverride: String? = nil) {
        self.id = id; self.email = email; self.displayName = displayName; self.preferredName = preferredName; self.language = language
        self.currency = currency; self.currencyOverride = currencyOverride
    }
    enum CodingKeys: String, CodingKey {
        case id, email, language; case displayName = "display_name"; case preferredName = "preferred_name"
        case currency; case currencyOverride = "currency_override"
    }
}

public struct AppleIdentity: Equatable, Sendable, Decodable {
    public let subject: String
}

public enum AppleCredentialState: Sendable {
    case authorized, revoked, notFound, transferred
}

public protocol AppleCredentialChecking: Sendable {
    func state(for subject: String) async throws -> AppleCredentialState
}

struct UnavailableAppleCredentialChecker: AppleCredentialChecking {
    func state(for subject: String) async throws -> AppleCredentialState { throw SessionFailure.unavailable }
}

public struct SessionSnapshot: Equatable, Sendable {
    public enum Phase: Equatable, Sendable {
        case accountDeletionUncertain, accountDeletionPending
        case signedOut, authenticated, signOutPending, unsupportedAnonymousSession, credentialValidationRequired, reauthenticationRequired
    }
    public let phase: Phase
    public let profile: SessionProfile?
    public let revision: UInt64
    public let appleIdentity: AppleIdentity?
    /// A snapshot names an identity; only `SessionController` can make one usable for requests.
    public init(phase: Phase, profile: SessionProfile?, revision: UInt64, appleIdentity: AppleIdentity? = nil) {
        self.phase = phase; self.profile = profile; self.revision = revision; self.appleIdentity = appleIdentity
    }
}

public enum SignupOutcome: Equatable, Sendable {
    case confirmationRequired
    case authenticated(SessionSnapshot)
}
