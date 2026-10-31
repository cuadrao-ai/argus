import Foundation

/// Client default for a prepared start date only. `src/argus/domain/planning/recurrence.py`
/// owns the calendar rule (keep the anchor day, clamp to shorter months); the server
/// re-validates the schedule and generates every occurrence.
public enum FinancialRecurrence {
    public static func calendarDay(of instant: String, timeZone: String) -> String? {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = parser.date(from: instant)
        if date == nil { parser.formatOptions = [.withInternetDateTime]; date = parser.date(from: instant) }
        guard let date, let zone = TimeZone(identifier: timeZone) else { return nil }
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = zone
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        guard let year = parts.year, let month = parts.month, let day = parts.day else { return nil }
        return format(year: year, month: month, day: day)
    }

    /// The first monthly date strictly after `movement` that is on or after `today`.
    public static func nextMonthlyDate(after movement: String, onOrAfter today: String) -> (date: String, monthDay: Int)? {
        guard let start = components(movement), components(today) != nil else { return nil }
        var year = start.year, month = start.month
        for _ in 0..<2400 {
            let candidate = format(year: year, month: month, day: min(start.day, lastDay(year: year, month: month)))
            if candidate > movement, candidate >= today { return (candidate, start.day) }
            (year, month) = month == 12 ? (year + 1, 1) : (year, month + 1)
        }
        return nil
    }

    private static func components(_ day: String) -> (year: Int, month: Int, day: Int)? {
        let parts = day.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3, (1...12).contains(parts[1]), (1...lastDay(year: parts[0], month: parts[1])).contains(parts[2]) else { return nil }
        return (parts[0], parts[1], parts[2])
    }
    private static func lastDay(year: Int, month: Int) -> Int {
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let first = calendar.date(from: DateComponents(year: year, month: month, day: 1))!
        return calendar.range(of: .day, in: .month, for: first)!.count
    }
    private static func format(year: Int, month: Int, day: Int) -> String {
        String(format: "%04d-%02d-%02d", year, month, day)
    }
}

/// A recurring expectation prepared from one recorded income or expense. The
/// movement is never changed and nothing links back to it; the seed only
/// prefills the review form.
public struct FinancialExpectationSeed: Equatable, Sendable {
    public static let titleLimit = 100
    public static let eligibleAccountTypes: Set<String> = ["cash", "checking", "savings"]

    public let kind: FinancialExpectationKind
    public let title: String
    public let currency: String
    public let amount: String
    public let accountId: UUID?
    public let cadence: FinancialPlanSchedule.Cadence
    public let monthDay: Int
    public let startDate: String

    public static func kind(for activity: FinancialActivityKind) -> FinancialExpectationKind? {
        switch activity {
        case .income: .income
        case .expense: .bill
        default: nil
        }
    }

    public static func eligible(_ activity: FinancialActivityDetail) -> Bool {
        kind(for: activity.kind) != nil && activity.originalAmountAvailable
    }

    public init?(activity: FinancialActivityDetail, accounts: [FinancialAccount], today: String, fallbackTitle: String) {
        guard let kind = Self.kind(for: activity.kind), let amount = activity.amount,
              let movementDay = FinancialRecurrence.calendarDay(of: activity.occurredAt, timeZone: activity.timeZone),
              let next = FinancialRecurrence.nextMonthlyDate(after: movementDay, onOrAfter: today) else { return nil }
        let note = activity.note?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        self.kind = kind
        // The server limit counts code points, so truncate by scalar, not by grapheme.
        title = String(String.UnicodeScalarView((note.isEmpty ? fallbackTitle : note).unicodeScalars.prefix(Self.titleLimit)))
        currency = activity.currency
        self.amount = amount
        let legAccount = activity.legs.first { $0.role == "single" }?.accountId
        accountId = accounts.first {
            $0.id == legAccount && !$0.archived && $0.currency == activity.currency && Self.eligibleAccountTypes.contains($0.type)
        }?.id
        cadence = .monthly
        monthDay = next.monthDay
        startDate = next.date
    }
}
