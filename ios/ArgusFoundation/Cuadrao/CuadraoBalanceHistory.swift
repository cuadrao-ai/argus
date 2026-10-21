import Foundation

/// Recorded-position projection for the UI preview, never a spendable-cash forecast.
struct CanvasBalanceObservation {
    let accountID: UUID
    let currency: String
    let kind: CanvasAccountKind
    let share: Int
    let date: Date
    let balance: Decimal
}

struct CanvasBalancePoint: Identifiable, Equatable {
    let date: Date
    let balance: Decimal
    var id: Date { date }
    var value: Double { NSDecimalNumber(decimal: balance).doubleValue }
}

enum CanvasBalanceHistory {
    static func position(_ accounts: [CanvasAccount]) -> Decimal? {
        let known = accounts.filter { $0.balance != nil }
        guard !known.isEmpty else { return nil }
        return known.reduce(Decimal.zero) { $0 + contribution($1.balance!, account: $1) }
    }

    static func points(accounts: [CanvasAccount], observations: [CanvasBalanceObservation], now: Date) -> [CanvasBalancePoint] {
        guard let current = position(accounts) else { return [] }
        let known = accounts.filter { $0.balance != nil }
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: now)
        // Never invent earlier balances for a new account or reinterpret another currency/share.
        let matched = known.map { account in
            observations.filter {
                $0.accountID == account.id && $0.currency == account.currency && $0.kind == account.kind
                    && $0.share == account.share && $0.date < today
            }.reduce(into: [Date: Decimal]()) { indexed, observation in
                if indexed[observation.date] == nil { indexed[observation.date] = observation.balance }
            }
        }
        let dates = Set(matched.flatMap { $0.keys }).sorted()
        var result: [CanvasBalancePoint] = []
        for date in dates {
            let values = matched.map { $0[date] }
            guard values.allSatisfy({ $0 != nil }) else { continue }
            let total = zip(known, values).reduce(Decimal.zero) { $0 + contribution($1.1!, account: $1.0) }
            result.append(CanvasBalancePoint(date: date, balance: total))
        }
        result.append(CanvasBalancePoint(date: today, balance: current))
        return result
    }

    static func snapshot(accounts: [CanvasAccount], observations: [CanvasBalanceObservation], at date: Date) -> [CanvasAccount] {
        accounts.map { account in
            var copy = account
            guard account.balance != nil else { return copy }
            copy.balance = observations.first {
                $0.accountID == account.id && $0.currency == account.currency && $0.kind == account.kind
                    && $0.share == account.share && $0.date == date
            }?.balance
            return copy
        }
    }

    static func contribution(_ balance: Decimal, account: CanvasAccount) -> Decimal {
        balance * (account.kind.isDebt ? -1 : 1) * Decimal(account.kind.isAsset ? account.share : 100) / 100
    }

    /// Explicit example observations, separate from activity and never backfilled for created accounts.
    static func examples(accounts: [CanvasAccount], now: Date) -> [CanvasBalanceObservation] {
        let calendar = Calendar.current
        let days = CanvasPreviewHistory.days(now: now).filter {
            let weekday = calendar.component(.weekday, from: $0)
            return weekday == 2 || weekday == 5 || calendar.component(.day, from: $0) == 1
        }
        return accounts.enumerated().flatMap { index, account in
            guard let balance = account.balance else { return [CanvasBalanceObservation]() }
            return days.enumerated().map { day, date in
                let progress = Double(day) / Double(max(1, days.count - 1))
                let month = calendar.component(.month, from: date)
                let dayOfMonth = calendar.component(.day, from: date)
                let seed = CanvasPreviewHistory.variation(date, salt: index)
                let seasonal = [0, -4, -1, 3, -2, -7, -3, 2, 4, 1, -5, -8][month - 1]
                let payCycle = account.kind == .checking ? (dayOfMonth < 6 || dayOfMonth > 25 ? 7 : -3) : 0
                let percentage = Int(70 + progress * 30) + seasonal + payCycle + seed % 7 - 3
                return CanvasBalanceObservation(accountID: account.id, currency: account.currency, kind: account.kind,
                    share: account.share, date: date, balance: balance * Decimal(percentage) / 100)
            }
        }
    }
}

/// A history and the day it was built for; the projection reads the clock only through that day.
struct CanvasBuiltBalanceHistory {
    let points: [CanvasBalancePoint]
    let day: Date
    init(accounts: [CanvasAccount], observations: [CanvasBalanceObservation], now: Date) {
        points = CanvasBalanceHistory.points(accounts: accounts, observations: observations, now: now)
        day = Calendar.current.startOfDay(for: now)
    }
    /// Points already totalled by their owner, such as the connected hero series.
    init(points: [CanvasBalancePoint], now: Date) {
        self.points = points
        day = Calendar.current.startOfDay(for: now)
    }
    func points(on now: Date) -> [CanvasBalancePoint]? {
        Calendar.current.startOfDay(for: now) == day ? points : nil
    }
}

/// A shared preview window; each fixture chooses plausible events within it.
enum CanvasPreviewHistory {
    static func variation(_ date: Date, salt: Int) -> Int {
        let parts = Calendar.current.dateComponents([.year, .month, .day], from: date)
        var seed = UInt64(parts.year! * 10000 + parts.month! * 100 + parts.day! + salt * 7919)
        seed = (seed ^ (seed >> 16)) &* 0x45d9f3b
        seed = (seed ^ (seed >> 16)) &* 0x45d9f3b
        return Int((seed ^ (seed >> 16)) % 10000)
    }
    static func days(now: Date) -> [Date] {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: now)
        let year = calendar.dateInterval(of: .year, for: today)!.start
        let start = calendar.date(byAdding: .year, value: -1, to: year)!
        let count = calendar.dateComponents([.day], from: start, to: today).day!
        return (0..<count).map { calendar.date(byAdding: .day, value: $0, to: start)! }
    }

}

/// Calendar periods own filtering, paging bounds and the balance comparison.
enum CanvasHistoryRange: String, CaseIterable, Identifiable {
    case week, month, year
    var id: String { rawValue }
    var component: Calendar.Component {
        switch self { case .week: .weekOfYear; case .month: .month; case .year: .year }
    }
    func title(_ es: Bool) -> String {
        switch self {
        case .week: CuadraoCopy.text("copy.cuadraoBalanceHistory.24d0da91ad", spanish: es)
        case .month: CuadraoCopy.text("copy.cuadraoBalanceHistory.c0d1241cc1", spanish: es)
        case .year: CuadraoCopy.text("copy.cuadraoBalanceHistory.7d3eb2c53b", spanish: es)
        }
    }
    func interval(now: Date = .now, offset: Int = 0) -> DateInterval {
        let calendar = Calendar.current
        let current = calendar.dateInterval(of: component, for: now)!.start
        return calendar.dateInterval(of: component, for: calendar.date(byAdding: component, value: min(offset, 0), to: current)!)!
    }
    func periodLabel(spanish: Bool, now: Date = .now, offset: Int = 0) -> String {
        let period = interval(now: now, offset: offset)
        let format = Date.FormatStyle.dateTime.locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))
        if self == .year { return period.start.formatted(format.year()) }
        let end = period.end.addingTimeInterval(-1)
        return period.start.formatted(format.month(.abbreviated).day()) + " – " + end.formatted(format.month(.abbreviated).day())
    }
    func points(_ points: [CanvasBalancePoint], now: Date = .now, offset: Int = 0) -> [CanvasBalancePoint] {
        let window = interval(now: now, offset: offset)
        return points.filter { $0.date >= window.start && $0.date < window.end && $0.date <= now }
    }
    func oldestOffset(_ points: [CanvasBalancePoint], now: Date = .now) -> Int {
        guard let first = points.first else { return 0 }
        let start = Calendar.current.dateInterval(of: component, for: first.date)!.start
        return min(0, Calendar.current.dateComponents([component], from: interval(now: now).start, to: start).value(for: component) ?? 0)
    }
    func baseline(_ history: [CanvasBalancePoint], now: Date = .now, offset: Int = 0) -> CanvasBalancePoint? {
        let start = interval(now: now, offset: offset).start
        return history.last { $0.date < start } ?? points(history, now: now, offset: offset).first
    }
}

/// Quiet Home offers only windows covered by recorded history.
enum CanvasHomeRange: String, CaseIterable, Identifiable {
    case month, twoMonths, quarter, halfYear, year, all
    var id: String { rawValue }
    var months: Int? {
        switch self {
        case .month: 1; case .twoMonths: 2; case .quarter: 3
        case .halfYear: 6; case .year: 12; case .all: nil
        }
    }
    func title(_ es: Bool) -> String {
        guard let months else { return CuadraoCopy.text("copy.cuadraoBalanceHistory.64c04b1430", spanish: es) }
        if months == 12 { return CuadraoCopy.text("copy.cuadraoBalanceHistory.c822ff9a14", spanish: es) }
        return months == 1 ? CuadraoCopy.text("copy.cuadraoBalanceHistory.86bf5f312f", spanish: es, String(describing: months)) : CuadraoCopy.text("copy.cuadraoBalanceHistory.3347ced10f", spanish: es, String(describing: months))
    }
    func start(now: Date) -> Date? {
        months.map { Calendar.current.date(byAdding: .month, value: -$0, to: Calendar.current.startOfDay(for: now))! }
    }
    static func available(_ points: [CanvasBalancePoint], now: Date = .now) -> [Self] {
        guard let first = points.first, points.count > 1 else { return [.all] }
        return allCases.filter { option in option.start(now: now).map { first.date <= $0 } ?? true }
    }
    func points(_ points: [CanvasBalancePoint], now: Date = .now) -> [CanvasBalancePoint] {
        guard let start = start(now: now) else { return points }
        return points.filter { $0.date >= start && $0.date <= now }
    }
}
