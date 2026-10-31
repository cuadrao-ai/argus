import Foundation

/// A handle to the vault's callback intent. It contains no provider credentials.
public struct AppleNameAuthorization: Sendable {
    let subject: String
    let intentID: UUID?
    let epoch: UInt64
}

struct AppleNameIntent: Codable, Equatable, Sendable {
    let id: UUID
    let subject: String
    let displayName: String
    let createdAt: Date

    static let retention: TimeInterval = 24 * 60 * 60
    func isCurrent(at date: Date = Date()) -> Bool {
        date >= createdAt && date.timeIntervalSince(createdAt) < Self.retention
    }
}

struct BoundAppleNameIntent: Codable, Equatable, Sendable {
    let intent: AppleNameIntent
    let userID: UUID
    let grantID: UUID
}

public enum AppleNameSaveOutcome: Equatable, Sendable {
    case saved
    case pending(SessionFailure)
}
