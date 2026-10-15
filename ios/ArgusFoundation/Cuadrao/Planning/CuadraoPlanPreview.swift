import Foundation
import Observation
import CuadraoBook

// Local UI scenarios only. Nothing in this file reads or writes a financial service.
enum CanvasPlanKind: String, Codable, CaseIterable, Identifiable {
    case goal, budget, debt
    var id: String { rawValue }
    func title(_ es: Bool) -> String {
        switch self {
        case .goal: es ? "Una meta" : "A goal"
        case .budget: es ? "Mi mes" : "My month"
        case .debt: es ? "Salir de una deuda" : "Pay off a debt"
        }
    }
    func amountTitle(_ es: Bool) -> String {
        switch self {
        case .goal: es ? "Quiero reunir" : "I want to save"
        case .budget: es ? "Quiero gastar hasta" : "I want to spend up to"
        case .debt: es ? "Deuda inicial" : "Starting debt"
        }
    }
    func recordedTitle(_ es: Bool) -> String {
        switch self {
        case .goal: es ? "Ya reunido" : "Already saved"
        case .budget: es ? "Gastado este mes" : "Spent this month"
        case .debt: es ? "Capital pagado" : "Principal repaid"
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
        switch self { case .coast: es ? "Mar" : "Sea"; case .sunshine: es ? "Sol" : "Sun"; case .bloom: es ? "Crecer" : "Grow"; case .clay: es ? "Tierra" : "Earth" }
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
    let spanish: String
    let english: String
    let amount: Double
    var id: Int { day }
    func title(_ es: Bool) -> String { es ? spanish : english }
}

struct CanvasForecast {
    static let today = PlanScenarioDays.preview.elapsed
    static let lastDay = PlanScenarioDays.preview.total
    let household: Bool
    var daily: Double { household ? 600 : 1150 }
    var current: Double { household ? 18500 : 38200 }
    var events: [CanvasForecastEvent] {
        household ? [
            .init(day: 18, spanish: "Servicios de casa", english: "Household bills", amount: -6500),
            .init(day: 26, spanish: "Aportes al hogar", english: "Household contributions", amount: 16500)
        ] : [
            .init(day: 18, spanish: "Pagos previstos", english: "Planned payments", amount: -8000),
            .init(day: 25, spanish: "Próximo ingreso", english: "Next income", amount: 28000)
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
            CanvasPlan(name: es ? "Un finde en Samaná" : "A weekend in Samaná", target: 60000, recorded: 24000, monthly: 6000, look: .coast),
            CanvasPlan(name: es ? "Casa a nuestro gusto" : "A home that feels like us", spaceID: "household", target: 90000, recorded: 35000, monthly: 10000, look: .clay),
            CanvasPlan(name: es ? "Mi mes, a mi ritmo" : "My month, my pace", kind: .budget, target: 35000, recorded: 14200, monthly: 35000, look: .sunshine),
            CanvasPlan(name: es ? "Adiós a la tarjeta" : "Goodbye, card balance", kind: .debt, target: 45000, recorded: 12000, monthly: 5000, annualRate: 24, look: .bloom)
        ]
        persist()
    }
    private func persist() {
        if let bytes = try? JSONEncoder().encode(Snapshot(plans: plans, dailyAssumptions: dailyAssumptions, hasForecast: hasForecast)) {
            defaults?.set(bytes, forKey: Self.storageKey)
        }
    }
}
