import SwiftUI
import Charts

// Local exploration only: the slider never writes money. `apply` is the plan's own edit command.
struct CuadraoPlanWhatIf: View {
    let scenario: PlanScenario
    let spanish: Bool
    /// The Preview drops a pending draft on any plan edit, not only when the scenario moves.
    var resetsOn: CanvasPlan? = nil
    var apply: ((Double) -> Void)? = nil
    var showsDisclosure = false
    @State private var draftAmount: Double?
    @State private var sliderCeiling: Double = 0
    @State private var saved = false
    @State private var applying = false
    @State private var exact = false
    private var baseline: Double { scenario.kind == .budget ? scenario.target : scenario.monthly }
    private var amount: Double { draftAmount ?? baseline }
    private var changed: Bool { abs(amount - baseline) > 0.01 }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text(scenario.kind == .budget ? (CuadraoCopy.text("copy.cuadraoPlanWhatIf.92ed11541e", spanish: spanish)) : scenario.kind == .debt ? (CuadraoCopy.text("copy.cuadraoPlanWhatIf.fbc1085402", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoPlanWhatIf.ea444e4450", spanish: spanish)))
                    .font(CuadraoTypography.section)
                if scenario.kind == .budget && scenario.recorded > 0 {
                    let estimate = scenario.projectedValue(at: scenario.budgetDays.total, monthly: amount)
                    Text(CuadraoCopy.text("copy.cuadraoPlanWhatIf.e805e50e8c", spanish: spanish, String(describing: PlanFormat.amount(estimate, currency: scenario.currency))))
                        .font(.subheadline).foregroundStyle(.secondary)
                } else if scenario.kind != .budget {
                    Text(scenario.months(at: amount).map { PlanFormat.month(after: $0, spanish: spanish, from: scenario.today) }
                        ?? (CuadraoCopy.text("copy.cuadraoPlanWhatIf.bf08094eee", spanish: spanish)))
                        .font(.system(.title, design: .rounded)).foregroundStyle(scenario.look.color).contentTransition(.numericText()).accessibilityIdentifier("plan-estimated-date")
                    if changed, let original = scenario.months(at: scenario.monthly), let proposed = scenario.months(at: amount), original != proposed {
                        Text(CuadraoCopy.text("copy.cuadraoPlanWhatIf.b20a7805a6", spanish: spanish, String(describing: abs(original - proposed)), String(describing: ((proposed < original ? CuadraoCopy.text("copy.cuadraoPlanWhatIf.a72a71b9cb", spanish: spanish) : CuadraoCopy.text("copy.cuadraoPlanWhatIf.497dfb6c3d", spanish: spanish))))))
                            .font(.subheadline.weight(.medium)).foregroundStyle(scenario.look.color)
                    }
                }
            }
            if scenario.kind != .budget || scenario.recorded > 0 {
                PlanDetailChart(scenario: scenario, amount: amount, spanish: spanish, scenarioCeiling: sliderCeiling)
            }
            VStack(spacing: 6) {
                HStack {
                    Text(scenario.kind == .budget ? (CuadraoCopy.text("copy.cuadraoPlanWhatIf.8d5b7791b3", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoPlanEditor.90ae4ff82c", spanish: spanish))).font(.subheadline)
                    Spacer()
                    Button { exact = true } label: {
                        HStack(spacing: 6) { Text(PlanFormat.amount(amount, currency: scenario.currency)).font(CuadraoTypography.rowAmount); Image(systemName: "pencil").font(.caption) }
                            .font(.subheadline.weight(.medium)).frame(minHeight: 44)
                    }.accessibilityIdentifier("plan-detail-exact")
                }
                Slider(value: Binding(get: { amount }, set: { draftAmount = $0; saved = false; applying = false }),
                    in: 1...max(1000, baseline * 3, sliderCeiling), step: 1)
                    .tint(scenario.look.color).accessibilityLabel(CuadraoCopy.text("copy.cuadraoPlanWhatIf.154fa94cbb", spanish: spanish))
                    .accessibilityIdentifier("plan-detail-slider")
            }.padding(16).background(scenario.look.color.opacity(0.065), in: RoundedRectangle(cornerRadius: 24))
            if scenario.kind != .budget {
                ScrollView(.horizontal) {
                    HStack(spacing: 8) {
                        ForEach([3, 6, 12], id: \.self) { months in
                            Button {
                                draftAmount = scenario.monthlyAmount(finishingIn: months); sliderCeiling = max(sliderCeiling, draftAmount ?? 0); saved = false; applying = false
                            } label: {
                                Text(CuadraoCopy.text("copy.cuadraoPlanWhatIf.2e5a9e4729", spanish: spanish, String(describing: months)))
                                    .font(.caption).padding(.horizontal, 14).frame(minHeight: 44)
                                    .background(WelcomePalette.surface, in: Capsule())
                            }.accessibilityIdentifier("plan-in-\(months)-months")
                        }
                    }
                }.scrollIndicators(.hidden)
            }
            if changed {
                if let apply {
                    PlanPrimaryButton(title: CuadraoCopy.text("copy.cuadraoPlanWhatIf.a6debfe200", spanish: spanish)) {
                        applying = true; apply(amount)
                    }.accessibilityIdentifier("plan-detail-apply")
                }
                Button(CuadraoCopy.text("copy.cuadraoPlanWhatIf.1acfa48fa0", spanish: spanish)) { draftAmount = nil; applying = false }
                    .font(.subheadline).frame(maxWidth: .infinity, minHeight: 44).accessibilityIdentifier("plan-detail-reset")
            } else if saved {
                Label(CuadraoCopy.text("copy.cuadraoPlanWhatIf.c924b7508b", spanish: spanish), systemImage: "checkmark.circle")
                    .font(.subheadline).foregroundStyle(WelcomePalette.pine)
            }
            if showsDisclosure {
                Text(scenario.disclosure(spanish: spanish)).font(.caption).foregroundStyle(.secondary)
            }
        }
        .sheet(isPresented: $exact) {
            PlanExactAmount(amount: Binding(get: { amount }, set: { draftAmount = $0; sliderCeiling = max(sliderCeiling, $0); saved = false; applying = false }), maximum: CanvasMoney.maximumValue, minimum: 1,
                title: scenario.kind == .budget ? (CuadraoCopy.text("copy.cuadraoPlanWhatIf.adfe058ad4", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoPlanEditor.90ae4ff82c", spanish: spanish)), currency: scenario.currency, spanish: spanish)
        }
        .onChange(of: scenario) { _, _ in reset() }
        .onChange(of: resetsOn) { _, _ in reset() }
        .sensoryFeedback(.success, trigger: saved) { _, new in new }
    }

    private func reset() {
        draftAmount = nil; sliderCeiling = 0
        if applying { applying = false; saved = true }
    }
}

private struct PlanDetailChart: View {
    let scenario: PlanScenario
    let amount: Double
    let spanish: Bool
    var scenarioCeiling: Double = 0
    private var horizon: Int { scenario.kind == .budget ? scenario.budgetDays.total : min(24, max(6, scenario.months(at: scenario.monthly) ?? 12)) }
    private func value(_ month: Int, monthly: Double) -> Double {
        scenario.projectedValue(at: month, monthly: monthly)
    }
    private var upperBound: Double {
        if scenario.kind == .debt { return max(scenario.target, scenario.remaining * pow(1 + scenario.annualRate / 1200, Double(horizon))) * 1.15 }
        if scenario.kind == .budget { return max(scenario.target * 3, scenarioCeiling, value(horizon, monthly: amount)) * 1.15 }
        return scenario.target * 1.15
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Chart {
                RuleMark(y: .value(CuadraoCopy.text("copy.cuadraoPlanWhatIf.728a6d7a37", spanish: spanish), scenario.kind == .budget ? amount : scenario.kind == .goal ? scenario.target : 0))
                    .foregroundStyle(scenario.look.color.opacity(0.3)).lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 4]))
                ForEach(0...horizon, id: \.self) { step in
                    LineMark(x: .value(CuadraoCopy.text("copy.cuadraoPlanWhatIf.c0d1241cc1", spanish: spanish), step), y: .value(CuadraoCopy.text("copy.cuadraoPlanWhatIf.18232145da", spanish: spanish), value(step, monthly: scenario.monthly)), series: .value(CuadraoCopy.text("copy.cuadraoPlanWhatIf.ec94e4cbf1", spanish: spanish), "saved"))
                        .foregroundStyle(Color.secondary.opacity(0.3)).lineStyle(StrokeStyle(lineWidth: 2))
                    LineMark(x: .value(CuadraoCopy.text("copy.cuadraoPlanWhatIf.c0d1241cc1", spanish: spanish), step), y: .value(CuadraoCopy.text("copy.cuadraoPlanWhatIf.18232145da", spanish: spanish), value(step, monthly: amount)), series: .value(CuadraoCopy.text("copy.cuadraoPlanWhatIf.ec94e4cbf1", spanish: spanish), "preview"))
                        .foregroundStyle(scenario.look.color).lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, dash: [5, 4]))
                }
            }
            .chartYScale(domain: 0...upperBound)
            .chartYAxis(.hidden).chartXAxis(.hidden).frame(height: 110)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(CuadraoCopy.text("copy.cuadraoPlanWhatIf.79e152df0b", spanish: spanish))
            HStack {
                Text(scenario.kind == .budget ? scenario.budgetEdges(spanish: spanish).first : (CuadraoCopy.text("copy.cuadraoChatPreview.ebdcdc2bda", spanish: spanish)))
                Spacer()
                Text(scenario.kind == .budget ? scenario.budgetEdges(spanish: spanish).last : (CuadraoCopy.text("copy.cuadraoPlanWhatIf.d6e04e41b3", spanish: spanish, String(describing: horizon))))
            }.font(.caption2).foregroundStyle(.secondary)
            Text(CuadraoCopy.text("copy.cuadraoPlanWhatIf.a4bca8f6d8", spanish: spanish)).font(.caption2).foregroundStyle(.secondary)
        }
    }
}
