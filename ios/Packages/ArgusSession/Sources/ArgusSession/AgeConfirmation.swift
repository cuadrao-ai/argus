import Foundation

/// A person's 18+ attestation, not a verified age. The original timestamp survives guest conversion.
public struct AgeConfirmation: Equatable, Sendable {
    public let timestamp: String

    public init?(timestamp: String, now: Date = Date()) {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = formatter.date(from: timestamp)
        if date == nil {
            formatter.formatOptions = [.withInternetDateTime]
            date = formatter.date(from: timestamp)
        }
        guard let date, date <= now.addingTimeInterval(300) else { return nil }
        self.timestamp = timestamp
    }

    public static func recorded(at date: Date = Date()) -> Self {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return Self(timestamp: formatter.string(from: date), now: date)!
    }
}
