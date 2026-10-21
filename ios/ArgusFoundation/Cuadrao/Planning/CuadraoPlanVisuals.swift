import SwiftUI

extension CanvasPlanLook {
    var color: Color {
        switch self {
        case .coast: WelcomePalette.pine
        case .sunshine: WelcomePalette.sunshine
        case .bloom: WelcomePalette.bloom
        case .clay: WelcomePalette.clay
        }
    }
}

enum PlanFormat {
    static func amount(_ value: Double, currency: String = "DOP") -> String {
        let number = value.formatted(.number.precision(.fractionLength(0...2)).locale(Locale(identifier: "en_US")))
        return "\(currency) \(number)"
    }
    static func month(after count: Int, spanish: Bool, from start: Date = PlanScenario.previewToday) -> String {
        let date = Calendar.current.date(byAdding: .month, value: count, to: start) ?? start
        let text = date.formatted(.dateTime.month(.wide).year().locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish))))
        return text.prefix(1).uppercased() + text.dropFirst()
    }
    static func space(_ id: String, accounts: CuadraoAccountsPreview, spanish: Bool) -> String {
        accounts.spaces.first { $0.id == id }?.title(spanish) ?? (CuadraoCopy.text("copy.cuadraoPlanEditor.577a4529ed", spanish: spanish))
    }
}

struct PlanPrimaryButton: View {
    let title: String
    var symbol: String? = nil
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Text(title)
                if let symbol { Image(systemName: symbol) }
            }.font(CuadraoTypography.action).frame(maxWidth: .infinity, minHeight: 52)
                .foregroundStyle(WelcomePalette.onAccent)
                .background(WelcomePalette.pine, in: Capsule())
        }.buttonStyle(.plain)
    }
}

/// Quiet, scalable cover art, drawn natively instead of decorative stock imagery.
struct PlanLandscape: View {
    let look: CanvasPlanLook
    var body: some View {
        GeometryReader { g in
            ZStack {
                Circle().fill(look.color.opacity(0.10)).frame(width: g.size.width * 0.8)
                Circle().fill(look.color.opacity(0.24))
                    .frame(width: g.size.width * 0.29, height: g.size.width * 0.29)
                    .offset(x: g.size.width * 0.16, y: -g.size.height * 0.19)
                ForEach(0..<3) { index in
                    PlanWave(crest: CGFloat(index) * 0.12)
                        .fill(look.color.opacity(0.12 + Double(index) * 0.09))
                        .frame(height: g.size.height * 0.5)
                        .offset(y: g.size.height * 0.15 + CGFloat(index) * 9)
                }
                Image(systemName: look.symbol).font(.system(size: 27, weight: .light))
                    .foregroundStyle(look.color).offset(x: -g.size.width * 0.13, y: g.size.height * 0.02)
            }.clipShape(RoundedRectangle(cornerRadius: 30))
        }.accessibilityHidden(true)
    }
}

private struct PlanWave: Shape {
    let crest: CGFloat
    func path(in rect: CGRect) -> Path {
        Path { path in
            path.move(to: CGPoint(x: 0, y: rect.height * (0.4 + crest)))
            path.addCurve(to: CGPoint(x: rect.maxX, y: rect.height * 0.3),
                control1: CGPoint(x: rect.width * 0.4, y: -rect.height * 0.7),
                control2: CGPoint(x: rect.width * 0.7, y: rect.height))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
            path.addLine(to: CGPoint(x: 0, y: rect.maxY)); path.closeSubpath()
        }
    }
}

struct PlanCard: View {
    let plan: CanvasPlan
    let space: String
    let spanish: Bool
    var body: some View {
        CuadraoPlanCard(display: .init(
            name: plan.name, space: space, look: plan.look,
            amount: PlanFormat.amount(plan.kind == .debt ? plan.remaining : plan.recorded, currency: plan.currency),
            annotation: plan.kind == .debt ? (CuadraoCopy.text("copy.cuadraoPlanVisuals.9cf2abcade", spanish: spanish)) : "\(Int(plan.recorded / max(plan.target, 1) * 100))%",
            progress: plan.progress,
            detail: plan.kind == .budget
                ? (CuadraoCopy.text("copy.cuadraoPlanVisuals.d16b6c2fa4", spanish: spanish, String(describing: PlanFormat.amount(plan.target, currency: plan.currency))))
                : (CuadraoCopy.text("copy.cuadraoPlanVisuals.dc74adf3f8", spanish: spanish, String(describing: ((plan.kind == .debt ? CuadraoCopy.text("copy.cuadraoPlanVisuals.f3f72bfd68", spanish: spanish) : CuadraoCopy.text("copy.cuadraoPlanVisuals.a666a311f9", spanish: spanish)))), String(describing: PlanFormat.amount(plan.target, currency: plan.currency))))))
    }
}

struct PlanForecastChart: View {
    let forecast: CanvasForecast
    let daily: Double
    let spanish: Bool
    var comparison: Double? = nil
    @Binding var selectedDay: Int?
    var detailed = false
    var compact = false
    private var selected: CanvasForecastPoint? {
        guard let selectedDay else { return nil }
        return (forecast.actual + forecast.projection(daily: daily).dropFirst()).first { $0.day == selectedDay }
    }
    var body: some View {
        CuadraoPlanForecastChart(
            spanish: spanish,             recorded: forecast.actual.map(point), projected: forecast.projection(daily: daily).map(point),
            comparison: comparison.flatMap { $0 != daily ? forecast.projection(daily: $0).map(point) : nil } ?? [],
            xRange: 1...31, yRange: -30000...65000,
            ticks: [1, 12, 31].map { .init(position: Double($0), title: $0 == 12 ? (CuadraoCopy.text("copy.cuadraoPlanVisuals.2d2ab461e3", spanish: spanish)) : "\($0) oct.") },
            today: Double(CanvasForecast.today), selected: selected.map(point),
            selection: Binding(get: { selectedDay.map(Double.init) }, set: { selectedDay = $0.map { Int($0.rounded()) } }),
            detailed: detailed, compact: compact, identifier: "plan-forecast-chart",
            accessibilityTitle: CuadraoCopy.text("copy.cuadraoPlanVisuals.74c98abe9d", spanish: spanish),
            accessibilityAmount: PlanFormat.amount(forecast.ending(daily: daily)))
    }
    private func point(_ value: CanvasForecastPoint) -> CuadraoPlanChartPoint {
        .init(id: value.day, position: Double(value.day), balance: value.balance)
    }
}

struct PlanPreviewFootnote: View {
    let spanish: Bool
    var body: some View {
        Text(CuadraoCopy.text("copy.cuadraoPlanVisuals.c512360fe4", spanish: spanish))
            .font(.caption2).foregroundStyle(.secondary).frame(maxWidth: .infinity).padding(.vertical, 12)
    }
}
