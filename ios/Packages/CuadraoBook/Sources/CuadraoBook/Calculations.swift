import Foundation

/// What-if arithmetic for plans, in `Decimal` and whole minor units, with no sample date and no floating point. It states
/// plain assumptions (constant monthly contributions, no returns, no fees) and moves no money.
public enum PlanCalculator {
    /// Longest horizon the book will state: a hundred years.
    public static let maximumMonths = 1_200

    /// Whole months until a goal is reached at a constant monthly amount. 0 when nothing remains; nil when it never is.
    public static func monthsToGoal(remainingMinor: Int64, monthlyMinor: Int64) -> Int? {
        guard remainingMinor > 0 else { return 0 }
        guard monthlyMinor > 0 else { return nil }
        let months = (remainingMinor / monthlyMinor) + (remainingMinor % monthlyMinor == 0 ? 0 : 1)
        return months <= Int64(maximumMonths) ? Int(months) : nil
    }

    /// The smallest monthly amount that finishes a goal in the given months, rounded up to a whole minor unit.
    public static func monthlyNeeded(remainingMinor: Int64, months: Int) -> Int64? {
        guard months > 0, remainingMinor > 0 else { return nil }
        let count = Int64(months)
        return (remainingMinor / count) + (remainingMinor % count == 0 ? 0 : 1)
    }

    /// Where this month's spending lands at the pace so far: spent over the days elapsed, times the days in the month,
    /// rounded half to even to a whole minor unit. An estimate, never confirmed spending. Nil with no day elapsed or on overflow.
    public static func monthEndPace(spentMinor: Int64, elapsedDays: Int, totalDays: Int) -> Int64? {
        guard elapsedDays > 0, totalDays >= elapsedDays, spentMinor >= 0 else { return nil }
        let exact = Decimal(spentMinor) * Decimal(totalDays) / Decimal(elapsedDays)
        var source = exact
        var rounded = Decimal()
        NSDecimalRound(&rounded, &source, 0, .bankers)
        guard rounded <= Decimal(Int64.max) else { return nil }
        return (rounded as NSDecimalNumber).int64Value
    }

    /// The month the goal lands in: whole calendar months after `start`, read in the given zone.
    public static func completionMonth(after months: Int, from start: Date, zone: TimeZone) -> Date? {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = zone
        return calendar.date(byAdding: .month, value: months, to: start)
    }
}

/// A currency's accounts added up the way the book reads them: each balance after the person's ownership share, assets
/// and what is owed kept apart. Accounts with an unknown balance are counted, not guessed.
public struct CurrencyTotals: Equatable, Sendable {
    public let currency: String
    public let digits: Int
    public let assetsMinor: Int64
    /// A positive amount: the sum of what is owed.
    public let owedMinor: Int64
    public let netMinor: Int64
    public let knownAccounts: Int
    public let unknownAccounts: Int
}

extension DeviceBook {
    /// Nil when the currency has no account or the sums would overflow.
    public func totals(currency: String) -> CurrencyTotals? {
        let held = accounts.filter { $0.currency == currency }
        guard let digits = held.first?.digits else { return nil }
        var assets: Int64 = 0, owed: Int64 = 0
        var known = 0, unknown = 0
        for account in held {
            guard let balance = self.balance(of: account.id) else { unknown += 1; continue }
            known += 1
            guard let share = Ownership.share(of: balance.minor, bps: account.ownershipShareBps) else { return nil }
            if share >= 0 {
                let (sum, overflow) = assets.addingReportingOverflow(share)
                guard !overflow else { return nil }
                assets = sum
            } else {
                let (sum, overflow) = owed.addingReportingOverflow(-share)
                guard !overflow else { return nil }
                owed = sum
            }
        }
        let (net, overflow) = assets.subtractingReportingOverflow(owed)
        guard !overflow else { return nil }
        return CurrencyTotals(currency: currency, digits: digits, assetsMinor: assets, owedMinor: owed, netMinor: net,
                              knownAccounts: known, unknownAccounts: unknown)
    }
}
