import Foundation

/// One period owns the hero, takeaway, highlights and their supporting records.
struct CanvasSpendingStory {
    let expenses: [CanvasActivity]
    let range: CanvasHistoryRange
    let offset: Int
    let coverageStart: Date?
    var now: Date = .now
    var interval: DateInterval { range.interval(now: now, offset: offset) }
    var entries: [CanvasActivity] {
        CanvasSpendingHistory.entries(expenses.filter { $0.date <= now }, in: interval)
    }
    var total: Decimal { CanvasSpendingHistory.total(entries) }
    enum State { case populated, emptyPeriod, firstUse, unavailable }
    var state: State {
        if !entries.isEmpty { return .populated }
        if expenses.isEmpty && coverageStart == nil { return .firstUse }
        return covered ? .emptyPeriod : .unavailable
    }
    var covered: Bool { coverageStart.map { $0 <= interval.start } ?? false }
    var comparison: DateInterval? {
        let prior = CanvasSpendingHistory.comparisonInterval(range: range, offset: offset, now: now)
        guard covered, let coverageStart, coverageStart <= prior.start else { return nil }
        // The 31st of a month has no equivalent point in a 30-day previous month.
        if offset == 0 {
            let calendar = Calendar.current
            let elapsed = calendar.dateComponents([.day, .hour, .minute, .second], from: interval.start, to: now)
            let priorElapsed = calendar.dateComponents([.day, .hour, .minute, .second], from: prior.start, to: prior.end)
            guard elapsed == priorElapsed else { return nil }
        }
        return prior
    }
    /// Coverage confirms whether an empty period is a known zero.
    var previousEntries: [CanvasActivity]? {
        comparison.map { CanvasSpendingHistory.entries(expenses, in: $0) }
    }
    var previousTotal: Decimal? { previousEntries.map(CanvasSpendingHistory.total) }
    func total(for category: CanvasExpenseCategory, previous: Bool = false) -> Decimal {
        CanvasSpendingHistory.total((previous ? previousEntries ?? [] : entries).filter { $0.category == category })
    }
    var changedCategory: CanvasExpenseCategory? {
        guard previousEntries != nil, total > 0 else { return nil }
        return CanvasExpenseCategory.allCases.filter { total(for: $0) != total(for: $0, previous: true) }
            .max { abs(total(for: $0) - total(for: $0, previous: true)) < abs(total(for: $1) - total(for: $1, previous: true)) }
    }
    var largestExpense: CanvasActivity? {
        guard entries.count > 1 else { return nil }
        return entries.max { $0.amount < $1.amount }
    }
    func periodText(_ interval: DateInterval, spanish: Bool) -> String {
        let style = Date.FormatStyle.dateTime.locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))
        if range == .year && offset < 0 { return interval.start.formatted(style.year()) }
        let end = max(interval.start, interval.end.addingTimeInterval(-1))
        return interval.start.formatted(style.month(.abbreviated).day()) + " – " + end.formatted(style.month(.abbreviated).day())
    }
    var observedInterval: DateInterval { DateInterval(start: interval.start, end: min(interval.end, max(interval.start, now))) }
}

struct CanvasSpendingMonth: Identifiable {
    let interval: DateInterval
    let amount: Decimal
    var id: Date { interval.start }
}

struct CanvasSpendingInsight: Identifiable {
    enum Kind { case average, trend }
    let kind: Kind
    let category: CanvasExpenseCategory?
    let months: [CanvasSpendingMonth]
    var id: String { "\(category?.rawValue ?? "all")-\(kind)-\(months.count)" }
    var interval: DateInterval { DateInterval(start: months.first!.interval.start, end: months.last!.interval.end) }
    var average: Decimal { months.reduce(0) { $0 + $1.amount } / Decimal(months.count) }
    var priorAverage: Decimal { months.prefix(9).reduce(0) { $0 + $1.amount } / 9 }
    var recentAverage: Decimal { months.suffix(3).reduce(0) { $0 + $1.amount } / 3 }
    var difference: Decimal { recentAverage - priorAverage }
}

extension CanvasSpendingStory {
    func completedMonths(count: Int, category: CanvasExpenseCategory? = nil) -> [CanvasSpendingMonth]? {
        guard count == 6 || count == 12 else { return nil }
        let calendar = Calendar.current
        let cutoff = min(interval.end, now)
        let end = calendar.dateInterval(of: .month, for: cutoff)!.start
        let start = calendar.date(byAdding: .month, value: -count, to: end)!
        guard let coverageStart, coverageStart <= start else { return nil }
        return (0..<count).map { index in
            let first = calendar.date(byAdding: .month, value: index, to: start)!
            let span = calendar.dateInterval(of: .month, for: first)!
            let records = CanvasSpendingHistory.entries(expenses, in: span).filter { category == nil || $0.category == category }
            return CanvasSpendingMonth(interval: span, amount: CanvasSpendingHistory.total(records))
        }
    }
    var longitudinalInsights: [CanvasSpendingInsight] {
        var result: [CanvasSpendingInsight] = []
        for count in [6, 12] {
            if let months = completedMonths(count: count), months.contains(where: { $0.amount > 0 }) {
                result.append(CanvasSpendingInsight(kind: .average, category: nil, months: months))
            }
        }
        var trends: [CanvasSpendingInsight] = []
        for category in CanvasExpenseCategory.allCases {
            if let months = completedMonths(count: 6, category: category), months.contains(where: { $0.amount > 0 }) {
                result.append(CanvasSpendingInsight(kind: .average, category: category, months: months))
            }
            if let months = completedMonths(count: 12, category: category) {
                let insight = CanvasSpendingInsight(kind: .trend, category: category, months: months)
                if months.prefix(9).filter({ $0.amount > 0 }).count >= 6,
                   months.suffix(3).allSatisfy({ $0.amount > 0 }), insight.difference != 0 {
                    trends.append(insight)
                }
            }
        }
        return trends.sorted { abs($0.difference) > abs($1.difference) } + result
    }
}
