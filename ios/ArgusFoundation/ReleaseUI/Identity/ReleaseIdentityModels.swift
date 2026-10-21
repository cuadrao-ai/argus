import Foundation

public struct ReleaseDeletionConsequences: Equatable {
    public enum Household: Equatable {
        case member(name: String)
        case admin(name: String, successor: String)
        case soleMember(name: String)
    }
    public let households: [Household]
    public let hasSharedPlans: Bool
    public let hasLockedHistory: Bool

    public init(households: [Household] = [], hasSharedPlans: Bool = false, hasLockedHistory: Bool = false) {
        self.households = households
        self.hasSharedPlans = hasSharedPlans
        self.hasLockedHistory = hasLockedHistory
    }
}

public enum ReleaseDeletionVerification: Equatable {
    case typedDelete
    case code

    public func accepts(_ value: String) -> Bool {
        switch self {
        case .typedDelete: value.trimmingCharacters(in: .whitespacesAndNewlines) == "DELETE"
        case .code: !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
    }
}

/// POST /account/delete outcomes: `completed` is 200 done, `pending` is 202 in_progress, `failed` is a
/// failure where nothing happened, and `uncertain` is a sent command without a usable answer (lost response
/// or 503 account_deletion_incomplete). The owner signs out before presenting `pending` or `completed`, and
/// `pending` never turns into `completed` on this device. The support cases are the flag-off ticket fallback.
public enum ReleaseDeletionState: Equatable {
    case ready, verificationRejected, verificationResending, submitting, pending, failed, completed
    case appleAuthorizationRequired, uncertain(canRetry: Bool), supportRequested, supportUnavailable

    public var allowsVerificationInput: Bool {
        switch self { case .ready, .verificationRejected: true; default: false }
    }
}

public enum ReleaseSocialProvider: String, CaseIterable, Identifiable {
    case apple, google
    public var id: String { rawValue }
    public var title: String { self == .apple ? CuadraoCopy.text("copy.releaseIdentityModels.b18e276ec9", spanish: CuadraoCopy.isSpanish()) : CuadraoCopy.text("copy.releaseIdentityModels.d35302cf6f", spanish: CuadraoCopy.isSpanish()) }
}

public struct ReleasePendingInvite: Equatable {
    public let id: String
    public let title: String
    public init(id: String, title: String) { self.id = id; self.title = title }
}

public enum ReleaseSocialSignInState: Equatable {
    case idle, loading(ReleaseSocialProvider), cancelled, failed, missingName, savingName, nameFailed, complete
    public var isBusy: Bool {
        switch self { case .loading, .savingName: true; default: false }
    }
}

public struct ReleaseAIConsentDisclosure: Equatable {
    public let providerName: String
    public let purpose: String
    public let dataItems: [String]
    public let privacyURL: URL
    public init(providerName: String, purpose: String, dataItems: [String], privacyURL: URL) {
        self.providerName = providerName
        self.purpose = purpose
        self.dataItems = dataItems
        self.privacyURL = privacyURL
    }
}

public enum ReleaseAIConsentState: Equatable {
    case required, submitting, failed, accepted
}

public struct ReleaseConnectedSource: Identifiable, Equatable {
    public enum State: Equatable { case connected, disconnecting, pending, failed, disconnected }
    public let id: String
    public let name: String
    public let detail: String
    public let state: State
    public init(id: String, name: String, detail: String, state: State) {
        self.id = id; self.name = name; self.detail = detail; self.state = state
    }
}

public enum ReleaseMemoryState: Equatable {
    case off, on, updating(isEnabled: Bool), failed(isEnabled: Bool), resetting(isEnabled: Bool), resetComplete(isEnabled: Bool)
    public var isEnabled: Bool {
        switch self {
        case .on: true
        case .updating(let value), .failed(let value), .resetting(let value), .resetComplete(let value): value
        default: false
        }
    }
    public var isBusy: Bool {
        switch self { case .updating, .resetting: true; default: false }
    }
}
