import Foundation

/// A currency's position across accounts, with the person's ownership share applied to each.
public struct NetBalance: Equatable, Sendable {
    public let currency: String
    public let digits: Int
    /// The total over accounts with a known balance; nil only if the arithmetic would overflow.
    public let minor: Int64?
    public let knownAccounts: Int
    /// Accounts whose balance is unknown stay counted here and out of the total.
    public let unknownAccounts: Int

    public var money: Money? { minor.map { Money(minor: $0, currency: currency, digits: digits) } }
    public var isPartial: Bool { unknownAccounts > 0 }
}

public struct DailyBalance: Equatable, Sendable {
    /// The start of the day in the zone the series was built for.
    public let day: Date
    public let minor: Int64
}

public enum SpendingReading: Equatable, Sendable {
    /// Coverage does not reach this month, so nothing is claimed about it: not zero, unknown.
    case noData
    case recorded(SpendingSummary)
}

public struct SpendingSummary: Equatable, Sendable {
    public let currency: String
    public let digits: Int
    public let totalMinor: Int64
    /// Largest first. Only categories with spending appear.
    public let byCategory: [CategoryTotal]
    /// Set when coverage begins inside the month, so the total is only for the days since.
    public let coverageStart: Date?

    public struct CategoryTotal: Equatable, Sendable {
        public let category: ExpenseCategory
        public let minor: Int64
    }
}

extension DeviceBook {
    /// The balance the person would read now: the stated balance plus movements since tracking began. Nil while
    /// unknown, or if the sum would overflow.
    public func balance(of id: UUID) -> Money? {
        guard let account = account(id), let opening = account.opening else { return nil }
        var total = opening.amountMinor
        for movement in movements where !movement.deleted && movement.occurredAt >= opening.asOf {
            guard let effect = movement.effect(on: id) else { continue }
            let (sum, overflow) = total.addingReportingOverflow(effect)
            guard !overflow else { return nil }
            total = sum
        }
        return Money(minor: total, currency: account.currency, digits: account.digits)
    }

    public func netBalance(currency: String) -> NetBalance? {
        let accounts = self.accounts.filter { $0.currency == currency }
        guard let digits = accounts.first?.digits else { return nil }
        var total: Int64? = 0
        var known = 0, unknown = 0
        for account in accounts {
            guard let balance = self.balance(of: account.id) else { unknown += 1; continue }
            known += 1
            guard let current = total, let share = Ownership.share(of: balance.minor, bps: account.ownershipShareBps) else { total = nil; continue }
            let (sum, overflow) = current.addingReportingOverflow(share)
            total = overflow ? nil : sum
        }
        return NetBalance(currency: currency, digits: digits, minor: total, knownAccounts: known, unknownAccounts: unknown)
    }

    /// Currencies the book holds in the order the person met them, the preferred one first.
    public var currencies: [String] {
        var seen: [String] = []
        for account in accounts where !seen.contains(account.currency) { seen.append(account.currency) }
        guard let primary = settings.primaryCurrency, let index = seen.firstIndex(of: primary) else { return seen }
        seen.remove(at: index)
        return [primary] + seen
    }

    /// The net balance at the end of each day that had a stated balance or a movement, and today. A day keeps the last
    /// balance until the next one. Nil if the arithmetic would overflow.
    public func dailyBalances(currency: String, zone: TimeZone, now: Date) -> [DailyBalance]? {
        let tracked = accounts.filter { $0.currency == currency && $0.opening != nil }
        guard !tracked.isEmpty else { return [] }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = zone
        let ids = Set(tracked.map(\.id))
        var days = Set<Date>([calendar.startOfDay(for: now)])
        for account in tracked { if let start = account.opening?.asOf { days.insert(calendar.startOfDay(for: start)) } }
        for movement in movements where !movement.deleted {
            let touches = ids.contains(movement.accountID) || (movement.counterpartID.map(ids.contains) ?? false)
            if touches { days.insert(calendar.startOfDay(for: movement.occurredAt)) }
        }
        var series: [DailyBalance] = []
        for day in days.sorted() {
            guard let end = calendar.date(byAdding: .day, value: 1, to: day) else { continue }
            var total: Int64 = 0
            for account in tracked {
                guard let opening = account.opening, opening.asOf < end else { continue }
                var balance = opening.amountMinor
                for movement in movements where !movement.deleted && movement.occurredAt >= opening.asOf && movement.occurredAt < end {
                    guard let effect = movement.effect(on: account.id) else { continue }
                    let (sum, overflow) = balance.addingReportingOverflow(effect)
                    guard !overflow else { return nil }
                    balance = sum
                }
                guard let share = Ownership.share(of: balance, bps: account.ownershipShareBps) else { return nil }
                let (sum, overflow) = total.addingReportingOverflow(share)
                guard !overflow else { return nil }
                total = sum
            }
            series.append(DailyBalance(day: day, minor: total))
        }
        return series
    }

    /// Where the book can speak about spending in a currency: the latest of its accounts' starts. An account starts
    /// when its balance was stated or its first movement happened, whichever is earlier; an untracked account
    /// means the currency has no coverage yet.
    public func spendingCoverageStart(currency: String) -> Date? {
        let accounts = activeAccounts.filter { $0.currency == currency }
        var starts: [Date] = []
        for account in accounts {
            let first = movements.filter { !$0.deleted && $0.effect(on: account.id) != nil }.map(\.occurredAt).min()
            guard let start = [account.opening?.asOf, first].compactMap({ $0 }).min() else { return nil }
            starts.append(start)
        }
        return starts.max()
    }

    /// Expenses in a currency over one interval (a calendar month in the device zone, say).
    public func spending(currency: String, in interval: DateInterval) -> SpendingReading? {
        guard let digits = accounts.first(where: { $0.currency == currency })?.digits else { return nil }
        guard let coverage = spendingCoverageStart(currency: currency), coverage < interval.end else { return .noData }
        let ids = Set(accounts.filter { $0.currency == currency }.map(\.id))
        var total: Int64 = 0
        var byCategory: [ExpenseCategory: Int64] = [:]
        for movement in movements where !movement.deleted && movement.kind == .expense && ids.contains(movement.accountID)
            && interval.contains(movement.occurredAt) && movement.occurredAt >= coverage {
            let (sum, overflow) = total.addingReportingOverflow(movement.amountMinor)
            guard !overflow else { return nil }
            total = sum
            byCategory[movement.category ?? .other, default: 0] += movement.amountMinor
        }
        let rows = byCategory.map { SpendingSummary.CategoryTotal(category: $0.key, minor: $0.value) }
            .sorted { $0.minor != $1.minor ? $0.minor > $1.minor : $0.category.rawValue < $1.category.rawValue }
        return .recorded(SpendingSummary(currency: currency, digits: digits, totalMinor: total, byCategory: rows,
                                         coverageStart: coverage > interval.start ? coverage : nil))
    }
}
