import Foundation
import ArgusSession
import CuadraoBook

/// Recorded positions of one currency, totalled the way the server hero totals them: every owner account,
/// archived included, the owner-signed amount and the account's current ownership share rounded half to even.
/// Today's point is the hero itself. Dated points exist only on days an account recorded a balance.
enum ConnectedBalanceHistory {
    struct AccountRead: Equatable {
        let account: FinancialAccount
        let read: PersonalObservationRead
    }

    /// One account's owner-share contribution on each local day it recorded a balance, today's being its
    /// current balance. A later day without a record keeps the last recorded contribution.
    struct AccountSeries: Equatable {
        let account: FinancialAccount
        let byDay: [Date: Int64]
        func contribution(on day: Date) -> Int64? {
            byDay.filter { $0.key <= day }.max { $0.key < $1.key }?.value
        }
    }

    /// One row of "What changed": the account's contributions on the period's recorded opening and closing days.
    struct AccountChange: Equatable {
        let account: FinancialAccount
        let opening: Int64?
        let closing: Int64?
    }

    enum Reading: Equatable {
        /// No account in this currency has a known balance.
        case unknown
        /// Dated positions ending on the hero today, and the per-account series they total. Accounts whose
        /// history could not be read are counted, and while any is missing only the hero point is drawn.
        case recorded(points: [CanvasBalancePoint], unavailableAccounts: Int, accounts: [AccountSeries])
    }

    /// The server's `personal_share`; the package owns the rounding so the device book and this agree by construction.
    static func personalShare(_ amount: Int64, bps: Int) -> Int64? { Ownership.share(of: amount, bps: bps) }

    /// The hero recomputed from the listed accounts; nil when a share or the total overflows.
    static func derivedPosition(_ accounts: [FinancialAccount]) -> Int64? {
        var total: Int64 = 0
        for account in accounts {
            guard let amount = account.balance.amountMinor,
                  let share = personalShare(amount, bps: account.ownershipShareBps) else { return nil }
            let (sum, overflow) = total.addingReportingOverflow(share)
            guard !overflow else { return nil }
            total = sum
        }
        return total
    }

    static func amount(_ minor: Decimal, digits: Int) -> Decimal {
        Decimal(sign: minor < 0 ? .minus : .plus, exponent: -digits, significand: abs(minor))
    }

    /// `reads` covers every account with a known balance; other currencies are ignored here.
    /// Returns nil when a read belongs to another identity or was cancelled: nothing of it may be shown.
    static func reading(summary: FinancialCurrencySummary, reads: [AccountRead], now: Date,
                        calendar: Calendar = .current) -> Reading? {
        guard summary.knownAccounts > 0, let hero = Decimal(string: summary.netWorthMinor) else { return .unknown }
        let reads = reads.filter { $0.account.currency == summary.currency }
        let today = calendar.startOfDay(for: now)
        let heroPoint = CanvasBalancePoint(date: today, balance: amount(hero, digits: summary.currencyFractionDigits))
        let heroOnly = Reading.recorded(points: [heroPoint], unavailableAccounts: 0, accounts: [])
        var complete: [(account: FinancialAccount, facts: PersonalAccountObservations)] = []
        var unavailable = 0
        for entry in reads {
            switch entry.read {
            case .stale, .cancelled: return nil
            case .incomplete, .unavailable: unavailable += 1
            case .complete(let facts): complete.append((entry.account, facts))
            }
        }
        guard unavailable == 0 else { return .recorded(points: [heroPoint], unavailableAccounts: unavailable, accounts: []) }
        let listed = reads.map(\.account)
        let consistent = Int64(summary.netWorthMinor) == derivedPosition(listed)
            && listed.count == summary.knownAccounts
            && complete.allSatisfy { $0.facts.accountVersion == $0.account.version }
        guard consistent, let accounts = series(complete, today: today, calendar: calendar) else { return heroOnly }
        let days = Set(accounts.flatMap { $0.byDay.keys }).filter { $0 < today }.sorted()
        var points: [CanvasBalancePoint] = []
        for day in days {
            guard let total = total(accounts, on: day) else { return heroOnly }
            points.append(CanvasBalancePoint(date: day, balance: amount(Decimal(total), digits: summary.currencyFractionDigits)))
        }
        points.append(heroPoint)
        return .recorded(points: points, unavailableAccounts: 0, accounts: accounts)
    }

    /// The rows between two recorded days of the series, in the order the accounts were read.
    static func changes(_ accounts: [AccountSeries], opening: Date?, closing: Date?) -> [AccountChange] {
        accounts.map { series in
            AccountChange(account: series.account, opening: opening.flatMap(series.contribution(on:)),
                          closing: closing.flatMap(series.contribution(on:)))
        }
    }

    /// Per account, the last balance recorded on each day before today, keyed by that day's local midnight,
    /// and the current balance under today. Nil when an ownership share overflows.
    private static func series(_ complete: [(account: FinancialAccount, facts: PersonalAccountObservations)],
                               today: Date, calendar: Calendar) -> [AccountSeries]? {
        var result: [AccountSeries] = []
        for (account, facts) in complete {
            var byDay: [Date: Int64] = [:]
            for observation in facts.observations {
                var zoned = calendar
                zoned.timeZone = TimeZone(identifier: observation.timeZone) ?? calendar.timeZone
                let parts = zoned.dateComponents([.year, .month, .day], from: observation.instant)
                guard let day = calendar.date(from: parts), day < today else { continue }
                guard let share = personalShare(observation.amountMinor, bps: account.ownershipShareBps) else { return nil }
                byDay[day] = share
            }
            guard let current = account.balance.amountMinor,
                  let share = personalShare(current, bps: account.ownershipShareBps) else { return nil }
            byDay[today] = share
            result.append(AccountSeries(account: account, byDay: byDay))
        }
        return result
    }

    private static func total(_ accounts: [AccountSeries], on day: Date) -> Int64? {
        var total: Int64 = 0
        for series in accounts {
            guard let share = series.contribution(on: day) else { continue }
            let (sum, overflow) = total.addingReportingOverflow(share)
            guard !overflow else { return nil }
            total = sum
        }
        return total
    }
}
