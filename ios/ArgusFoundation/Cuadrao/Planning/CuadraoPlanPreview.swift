import Foundation
import Observation
import CuadraoBook

// Local UI scenarios only. Nothing in this file reads or writes a financial service.
enum CanvasPlanKind: String, Codable, CaseIterable, Identifiable {
    case goal, budget, debt
    var id: String { rawValue }
    func title(_ es: Bool) -> String {
        switch self {
        case .goal: CuadraoCopy.text("copy.cuadraoPlanPreview.cabba9bc9e", spanish: es)
        case .budget: CuadraoCopy.text("copy.cuadraoPlanPreview.7736181f54", spanish: es)
        case .debt: CuadraoCopy.text("copy.cuadraoPlanPreview.90cb2868da", spanish: es)
        }
    }
    func amountTitle(_ es: Bool) -> String {
        switch self {
        case .goal: CuadraoCopy.text("copy.cuadraoPlanPreview.e778771fc8", spanish: es)
        case .budget: CuadraoCopy.text("copy.cuadraoPlanPreview.d1b440c179", spanish: es)
        case .debt: CuadraoCopy.text("copy.cuadraoPlanPreview.f3f72bfd68", spanish: es)
        }
    }
    func recordedTitle(_ es: Bool) -> String {
        switch self {
        case .goal: CuadraoCopy.text("copy.cuadraoPlanPreview.cbd0c31fa0", spanish: es)
        case .budget: CuadraoCopy.text("copy.cuadraoPlanPreview.eb4dc40337", spanish: es)
        case .debt: CuadraoCopy.text("copy.cuadraoPlanPreview.6208769a5c", spanish: es)
        }
    }
}

enum CanvasPlanLook: String, Codable, CaseIterable, Identifiable {
    case coast, sunshine, bloom, clay
    var id: String { rawValue }
    var symbol: String {
        switch self { case .coast: "water.waves"; case .sunshine: "sun.max"; case .bloom: "leaf"; case .clay: "mountain.2" }
    }
    func title(_ es: Bool) -> String {
        switch self { case .coast: CuadraoCopy.text("copy.cuadraoPlanPreview.29bf91d53d", spanish: es); case .sunshine: CuadraoCopy.text("copy.cuadraoPlanPreview.d7d3325840", spanish: es); case .bloom: CuadraoCopy.text("copy.cuadraoPlanPreview.c7007b4160", spanish: es); case .clay: CuadraoCopy.text("copy.cuadraoPlanPreview.ac0374d65e", spanish: es) }
    }
}

enum PlanCurrency {
    /// The app's currencies, owned by the book's table so every picker and check shares one list.
    static let supported = CurrencyTable.offered
}

struct CanvasPlan: Identifiable, Codable, Equatable {
    var id = UUID()
    var name: String
    var kind: CanvasPlanKind = .goal
    var spaceID = "personal"
    var currency = "DOP"
    var target: Double = 0
    var recorded: Double = 0
    var monthly: Double = 0
    var annualRate: Double = 0
    var look: CanvasPlanLook = .coast
    var archived = false
    var scenario: PlanScenario {
        PlanScenario(kind: kind, currency: currency, target: target, recorded: recorded, monthly: monthly, annualRate: annualRate, look: look)
    }
    var remaining: Double { scenario.remaining }
    var progress: Double { scenario.progress }
    func months(at amount: Double) -> Int? { scenario.months(at: amount) }
    func projectedValue(at step: Int, monthly amount: Double) -> Double { scenario.projectedValue(at: step, monthly: amount) }
    func monthlyAmount(finishingIn months: Int) -> Double { scenario.monthlyAmount(finishingIn: months) }
}

struct CanvasForecastPoint: Identifiable {
    let day: Int
    let balance: Double
    var id: Int { day }
}

struct CanvasForecastEvent: Identifiable {
    let day: Int
    let titleKey: String
    let amount: Double
    var id: Int { day }
    func title(_ es: Bool) -> String { CuadraoCopy.text(titleKey, spanish: es) }
}

struct CanvasForecast {
    static let today = PlanScenarioDays.preview.elapsed
    static let lastDay = PlanScenarioDays.preview.total
    let household: Bool
    var daily: Double { household ? 600 : 1150 }
    var current: Double { household ? 18500 : 38200 }
    var events: [CanvasForecastEvent] {
        household ? [
            .init(day: 18, titleKey: "copy.cuadraoPlanPreview.75e5e16f06", amount: -6500),
            .init(day: 26, titleKey: "copy.cuadraoPlanPreview.d1465f77f9", amount: 16500)
        ] : [
            .init(day: 18, titleKey: "copy.cuadraoPlanPreview.3005ccb01b", amount: -8000),
            .init(day: 25, titleKey: "copy.cuadraoPlanPreview.8a260385d8", amount: 28000)
        ]
    }
    var actual: [CanvasForecastPoint] {
        let offsets: [Double] = [13800, 12100, 11400, 8800, 8450, 6500, 5900, 4200, 3000, 2400, 650, 0]
        return offsets.enumerated().map { .init(day: $0.offset + 1, balance: current + $0.element * (household ? 0.45 : 1)) }
    }
    func projection(daily: Double) -> [CanvasForecastPoint] {
        var balance = current
        return (Self.today...Self.lastDay).map { day in
            if day > Self.today {
                balance -= daily
                balance += events.filter { $0.day == day }.reduce(0) { $0 + $1.amount }
            }
            return .init(day: day, balance: balance)
        }
    }
    func ending(daily: Double) -> Double { projection(daily: daily).last!.balance }
    func lowest(daily: Double) -> CanvasForecastPoint { projection(daily: daily).min { $0.balance < $1.balance }! }
}

@Observable final class CuadraoPlanPreview {
    private static let storageKey = "cuadrao.design.plans.v1"
    var plans: [CanvasPlan] = []
    var dailyAssumptions: [String: Double] = [:]
    var hasForecast = true
    private let defaults: UserDefaults?
    private struct Snapshot: Codable {
        var plans: [CanvasPlan]
        var dailyAssumptions: [String: Double]
        var hasForecast: Bool
    }
    init(spanish: Bool, defaults: UserDefaults? = .standard, reset: Bool = false, empty: Bool = false) {
        // Standard defaults persist only in the design preview.
        self.defaults = defaults === UserDefaults.standard && !CuadraoDesignPreview.isActive ? nil : defaults
        if !reset, !empty, let bytes = self.defaults?.data(forKey: Self.storageKey),
           let saved = try? JSONDecoder().decode(Snapshot.self, from: bytes) {
            plans = saved.plans; dailyAssumptions = saved.dailyAssumptions; hasForecast = saved.hasForecast
        } else { resetExamples(spanish: spanish, empty: empty) }
    }
    func plan(_ id: UUID) -> CanvasPlan? { plans.first { $0.id == id } }
    func save(_ plan: CanvasPlan) {
        guard PlanCurrency.supported.contains(plan.currency),
              self.plan(plan.id).map({ $0.currency == plan.currency }) ?? true,
              !plan.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              plan.target.isFinite, plan.target > 0, plan.recorded.isFinite, plan.recorded >= 0,
              plan.monthly.isFinite, plan.monthly > 0,
              plan.annualRate.isFinite, (0...100).contains(plan.annualRate) else { return }
        if let i = plans.firstIndex(where: { $0.id == plan.id }) { plans[i] = plan } else { plans.append(plan) }
        persist()
    }
    func reorder(_ ids: [UUID]) {
        guard Set(ids) == Set(plans.filter { !$0.archived }.map(\.id)) else { return }
        plans = CuadraoCollectionOrder.applying(ids, to: plans); persist()
    }
    func archive(_ id: UUID, _ archived: Bool) {
        guard let i = plans.firstIndex(where: { $0.id == id }) else { return }
        plans[i].archived = archived; persist()
    }
    func daily(for scope: String) -> Double {
        dailyAssumptions[scope] ?? CanvasForecast(household: scope == "household").daily
    }
    func applyDaily(_ amount: Double, scope: String) {
        guard amount.isFinite, (0...10000).contains(amount) else { return }
        dailyAssumptions[scope] = amount; persist()
    }
    func enableForecastExample() { hasForecast = true; persist() }
    func resetExamples(spanish es: Bool, empty: Bool = false) {
        hasForecast = !empty; dailyAssumptions = [:]
        plans = empty ? [] : [
            CanvasPlan(name: CuadraoCopy.text("copy.cuadraoPlanPreview.6f714ea860", spanish: es), target: 60000, recorded: 24000, monthly: 6000, look: .coast),
            CanvasPlan(name: CuadraoCopy.text("copy.cuadraoPlanPreview.e211be6ff4", spanish: es), spaceID: "household", target: 90000, recorded: 35000, monthly: 10000, look: .clay),
            CanvasPlan(name: CuadraoCopy.text("copy.cuadraoPlanPreview.6e65f7bcc6", spanish: es), kind: .budget, target: 35000, recorded: 14200, monthly: 35000, look: .sunshine),
            CanvasPlan(name: CuadraoCopy.text("copy.cuadraoPlanPreview.11dba30e0c", spanish: es), kind: .debt, target: 45000, recorded: 12000, monthly: 5000, annualRate: 24, look: .bloom)
        ]
        persist()
    }
    private func persist() {
        if let bytes = try? JSONEncoder().encode(Snapshot(plans: plans, dailyAssumptions: dailyAssumptions, hasForecast: hasForecast)) {
            defaults?.set(bytes, forKey: Self.storageKey)
        }
    }
}
