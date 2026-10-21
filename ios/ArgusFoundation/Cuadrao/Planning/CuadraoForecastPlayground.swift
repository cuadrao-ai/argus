import SwiftUI

struct CuadraoForecastPlayground: View {
    let store: CuadraoPlanPreview
    let scope: String
    let scopeName: String
    let spanish: Bool
    var bottomSpace: CGFloat = 90
    let isolatedExample: Bool
    @State private var draft: Double
    @State private var selectedDay: Int?
    @State private var exact = false
    @State private var saved = false
    private var forecast: CanvasForecast { CanvasForecast(household: scope == "household") }
    private var baseline: Double { store.daily(for: scope) }
    private var changed: Bool { abs(draft - baseline) > 0.01 }
    private var lowest: CanvasForecastPoint { forecast.lowest(daily: draft) }
    private var point: CanvasForecastPoint? {
        guard let selectedDay else { return nil }
        return (forecast.actual + forecast.projection(daily: draft).dropFirst()).first { $0.day == selectedDay }
    }
    init(store: CuadraoPlanPreview, scope: String, scopeName: String, spanish: Bool, bottomSpace: CGFloat = 90, isolatedExample: Bool = false) {
        self.store = store; self.scope = scope; self.scopeName = scopeName; self.spanish = spanish; self.bottomSpace = bottomSpace
        self.isolatedExample = isolatedExample
        _draft = State(initialValue: store.daily(for: scope))
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                if isolatedExample {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.1b8f6f8538", spanish: spanish)).font(.subheadline.weight(.medium))
                        Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.d8afb57180", spanish: spanish))
                            .font(.caption).foregroundStyle(.secondary)
                    }.accessibilityIdentifier("forecast-example-notice")
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text("\(CuadraoCopy.text("copy.cuadraoForecastPlayground.1489ef5402", spanish: spanish)) · \(scopeName)").font(.subheadline).foregroundStyle(.secondary)
                    Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.4f6e2dfaa9", spanish: spanish))
                        .font(CuadraoTypography.feature)
                }
                VStack(alignment: .leading, spacing: 8) {
                    Text(point.map { "\($0.day) \(CuadraoCopy.text("copy.cuadraoForecastPlayground.651df10909", spanish: spanish))\($0.day > CanvasForecast.today ? (CuadraoCopy.text("copy.cuadraoForecastPlayground.201fd9701c", spanish: spanish)) : "")" }
                         ?? (CuadraoCopy.text("copy.cuadraoForecastPlayground.00f88d36ae", spanish: spanish)))
                        .font(.caption).foregroundStyle(.secondary)
                    Text(PlanFormat.amount(point?.balance ?? forecast.ending(daily: draft)))
                        .font(CuadraoTypography.amount)
                        .lineLimit(1).minimumScaleFactor(0.6).accessibilityIdentifier("forecast-ending")
                    PlanForecastChart(forecast: forecast, daily: draft, spanish: spanish, comparison: baseline, selectedDay: $selectedDay, detailed: true)
                    HStack(spacing: 16) {
                        Label(CuadraoCopy.text("copy.cuadraoForecastPlayground.f370568882", spanish: spanish), systemImage: "minus")
                        Label(CuadraoCopy.text("copy.cuadraoForecastPlayground.eb1bf8d2fe", spanish: spanish), systemImage: "ellipsis")
                        Spacer()
                    }.font(.caption2).foregroundStyle(.secondary)
                    if let event = forecast.events.first(where: { $0.day == selectedDay }) {
                        Text("\(event.title(spanish)) · \(PlanFormat.amount(event.amount))").font(.caption).foregroundStyle(WelcomePalette.pine)
                    }
                }
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.7cd7472e1f", spanish: spanish)).font(.subheadline)
                        Spacer()
                        Button { exact = true } label: {
                            HStack(spacing: 6) { Text(PlanFormat.amount(draft)).font(CuadraoTypography.rowAmount); Image(systemName: "pencil").font(.caption) }
                        }.font(.subheadline.weight(.medium)).frame(minHeight: 44).accessibilityIdentifier("forecast-exact")
                    }
                    Slider(value: $draft, in: 0...3000, step: 50) { editing in
                        if editing { selectedDay = nil; saved = false }
                    }.tint(WelcomePalette.pine).accessibilityLabel(CuadraoCopy.text("copy.cuadraoForecastPlayground.5d3db19ffe", spanish: spanish))
                        .accessibilityValue(PlanFormat.amount(draft)).accessibilityIdentifier("forecast-slider")
                    Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.e077e39624", spanish: spanish))
                        .font(.caption).foregroundStyle(.secondary)
                    if changed {
                        let difference = forecast.ending(daily: draft) - forecast.ending(daily: baseline)
                        Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.25f9d2e580", spanish: spanish, String(describing: PlanFormat.amount(abs(difference))), String(describing: ((difference >= 0 ? CuadraoCopy.text("copy.cuadraoForecastPlayground.14178c1062", spanish: spanish) : CuadraoCopy.text("copy.cuadraoForecastPlayground.d08611ffa1", spanish: spanish))))))
                            .font(.subheadline.weight(.medium)).foregroundStyle(WelcomePalette.pine)
                    }
                }.padding(22).background(WelcomePalette.sage.opacity(0.6), in: RoundedRectangle(cornerRadius: 26))
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: lowest.balance < 0 ? "exclamationmark.circle" : "calendar")
                        .foregroundStyle(lowest.balance < 0 ? Color.orange : WelcomePalette.pine)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.b2b85634f8", spanish: spanish, String(describing: lowest.day))).font(.subheadline.weight(.medium))
                        Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.632938220c", spanish: spanish, String(describing: PlanFormat.amount(lowest.balance))))
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                assumptions
                VStack(spacing: 8) {
                    if changed {
                        PlanPrimaryButton(title: isolatedExample
                            ? (CuadraoCopy.text("copy.cuadraoForecastPlayground.9834537ff8", spanish: spanish))
                            : (CuadraoCopy.text("copy.cuadraoForecastPlayground.547d4a05af", spanish: spanish))) {
                            store.applyDaily(draft, scope: scope); saved = true
                        }.accessibilityIdentifier("forecast-apply")
                        Button(isolatedExample
                            ? (CuadraoCopy.text("copy.cuadraoForecastPlayground.39ffbb4a04", spanish: spanish))
                            : (CuadraoCopy.text("copy.cuadraoForecastPlayground.2b7777515c", spanish: spanish))) { draft = baseline; selectedDay = nil }
                            .frame(minHeight: 44).accessibilityIdentifier("forecast-reset")
                    } else if saved {
                        Label(isolatedExample
                            ? (CuadraoCopy.text("copy.cuadraoForecastPlayground.101ee9e1ce", spanish: spanish))
                            : (CuadraoCopy.text("copy.cuadraoForecastPlayground.9a8b6ad035", spanish: spanish)), systemImage: "checkmark.circle")
                            .foregroundStyle(WelcomePalette.pine).font(.subheadline).frame(minHeight: 44)
                    }
                    Text(isolatedExample
                        ? (CuadraoCopy.text("copy.cuadraoForecastPlayground.2e92b0e65b", spanish: spanish))
                        : (CuadraoCopy.text("copy.cuadraoForecastPlayground.6731f7fa58", spanish: spanish)))
                        .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }
                PlanPreviewFootnote(spanish: spanish)
            }.padding(24).padding(.bottom, bottomSpace)
        }
        .background(WelcomePalette.background).cuadraoSoftScrollEdges()
        .sensoryFeedback(.success, trigger: saved) { _, new in new }
        .navigationTitle(CuadraoCopy.text("copy.cuadraoForecastPlayground.07455db089", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .sheet(isPresented: $exact) {
            PlanExactAmount(amount: $draft, maximum: 3000, title: CuadraoCopy.text("copy.cuadraoForecastPlayground.7cd7472e1f", spanish: spanish), currency: "DOP", spanish: spanish)
        }
    }
    private var assumptions: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 16) {
                Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.12c0a17fe5", spanish: spanish))
                    .font(.subheadline).foregroundStyle(.secondary)
                ForEach(forecast.events) { event in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(event.title(spanish)).font(.subheadline)
                            Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.d527fc60bc", spanish: spanish, String(describing: event.day))).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer(); Text(PlanFormat.amount(event.amount)).font(CuadraoTypography.rowAmount)
                    }
                }
                Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.0233490002", spanish: spanish))
                    .font(.caption).foregroundStyle(.secondary)
            }.padding(.top, 14)
        } label: { Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.d71bd096f1", spanish: spanish)).font(.subheadline.weight(.medium)) }
    }
}

struct PlanExactAmount: View {
    @Binding var amount: Double
    let maximum: Double
    var minimum: Double = 0
    let title: String
    let currency: String
    let spanish: Bool
    @State private var input: Double = 0
    @State private var error = ""
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            Form {
                PlanAmountInput(value: $input, currency: .constant(currency), error: $error,
                                title: title, identifier: "plan-exact-input", spanish: spanish)
                if !input.isFinite || input < minimum || input > maximum {
                    Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.ee61be4e1f", spanish: spanish, String(describing: minimum.formatted()), String(describing: PlanFormat.amount(maximum, currency: currency))))
                        .font(.caption).foregroundStyle(.red)
                }
            }.navigationTitle(title).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish)) { dismiss() }
                    CuadraoConfirmToolbar(title: CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish),
                                          disabled: !error.isEmpty || !input.isFinite || input < minimum || input > maximum,
                                          identifier: "plan-exact-done") { amount = input; dismiss() }
                }
        }.presentationDetents([.medium]).presentationDragIndicator(.visible)
            .onAppear { input = amount }
    }
}
