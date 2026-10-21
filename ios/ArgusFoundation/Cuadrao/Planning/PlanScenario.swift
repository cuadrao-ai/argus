import Foundation

struct PlanScenarioDays: Equatable {
    static let preview = PlanScenarioDays(elapsed: 12, total: 31)
    var elapsed: Int
    var total: Int
}

// Local what-if projection with explicit fixed monthly assumptions, never an actual balance.
struct PlanScenario: Equatable {
    static let previewToday = Calendar.current.date(from: DateComponents(year: 2026, month: 10, day: 12))!
    var kind: CanvasPlanKind
    var currency: String
    var target: Double
    var recorded: Double
    var monthly: Double
    var annualRate: Double = 0
    var look: CanvasPlanLook
    var budgetDays = PlanScenarioDays.preview
    var today = PlanScenario.previewToday
    var timeZone = TimeZone.current
    var remaining: Double { max(0, target - recorded) }
    var progress: Double { min(1, max(0, recorded / max(target, 1))) }

    func months(at amount: Double) -> Int? {
        guard remaining > 0 else { return 0 }
        guard amount > 0 else { return nil }
        var balance = remaining
        for month in 1...600 {
            let interest = kind == .debt ? balance * annualRate / 1200 : 0
            guard amount > interest else { return nil }
            balance = outstanding(after: balance, payment: amount)
            if balance <= 0.01 { return month }
        }
        return nil
    }
    private func outstanding(after balance: Double, payment: Double) -> Double {
        max(0, balance * (1 + (kind == .debt ? annualRate / 1200 : 0)) - payment)
    }
    func projectedValue(at step: Int, monthly amount: Double) -> Double {
        if kind == .budget { return recorded / Double(budgetDays.elapsed) * Double(step) }
        if kind == .goal { return min(target, recorded + amount * Double(step)) }
        var balance = remaining
        for _ in 0..<max(0, step) { balance = outstanding(after: balance, payment: amount) }
        return balance
    }
    func monthlyAmount(finishingIn months: Int) -> Double {
        let count = Double(max(1, months))
        let rate = kind == .debt ? annualRate / 1200 : 0
        let payment = rate == 0 ? remaining / count : remaining * rate / (1 - pow(1 + rate, -count))
        return max(1, ceil(payment))
    }

    func disclosure(spanish: Bool) -> String {
        if kind == .budget {
            let elapsed = budgetDays.elapsed, total = budgetDays.total
            return CuadraoCopy.text("copy.planScenario.c0ab2032ba", spanish: spanish, String(describing: elapsed), String(describing: ((elapsed == 1 ? CuadraoCopy.text("copy.planScenario.a965f93e10", spanish: spanish) : CuadraoCopy.text("copy.planScenario.1cca1d7c78", spanish: spanish)))), String(describing: total))
        }
        let formatter = DateFormatter()
        formatter.locale = Self.locale(spanish); formatter.timeZone = timeZone; formatter.dateStyle = .long
        let date = formatter.string(from: today)
        return CuadraoCopy.text("copy.planScenario.29ba16aeba", spanish: spanish, String(describing: date))
    }

    func budgetEdges(spanish: Bool) -> (first: String, last: String) {
        var calendar = Calendar.current; calendar.timeZone = timeZone
        let start = calendar.dateInterval(of: .month, for: today)?.start ?? today
        let last = calendar.date(byAdding: .day, value: max(0, budgetDays.total - 1), to: start) ?? start
        return (dayLabel(start, calendar: calendar, spanish: spanish), dayLabel(last, calendar: calendar, spanish: spanish))
    }
    private func dayLabel(_ date: Date, calendar: Calendar, spanish: Bool) -> String {
        let formatter = DateFormatter()
        formatter.locale = Self.locale(spanish); formatter.timeZone = timeZone
        guard spanish else { formatter.setLocalizedDateFormatFromTemplate("MMM d"); return formatter.string(from: date) }
        formatter.dateFormat = "MMM"
        let month = formatter.string(from: date).trimmingCharacters(in: CharacterSet(charactersIn: "."))
        return "\(calendar.component(.day, from: date)) \(month)."
    }
    private static func locale(_ spanish: Bool) -> Locale { Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)) }
}
