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
                        Text(spanish ? "Escenario de ejemplo" : "Example scenario").font(.subheadline.weight(.medium))
                        Text(spanish ? "Datos ficticios, separados de tus cuentas. Los cambios se quedan en este ejemplo." : "Fictional data, separate from your accounts. Changes stay in this example.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.accessibilityIdentifier("forecast-example-notice")
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text("\(spanish ? "Octubre" : "October") · \(scopeName)").font(.subheadline).foregroundStyle(.secondary)
                    Text(spanish ? "Tu mes tiene posibilidades." : "Your month has possibilities.")
                        .font(CuadraoTypography.feature)
                }
                VStack(alignment: .leading, spacing: 8) {
                    Text(point.map { "\($0.day) \(spanish ? "de octubre" : "October")\($0.day > CanvasForecast.today ? (spanish ? " · estimado" : " · estimated") : "")" }
                         ?? (spanish ? "Al cierre del mes" : "At month end"))
                        .font(.caption).foregroundStyle(.secondary)
                    Text(PlanFormat.amount(point?.balance ?? forecast.ending(daily: draft)))
                        .font(CuadraoTypography.amount)
                        .lineLimit(1).minimumScaleFactor(0.6).accessibilityIdentifier("forecast-ending")
                    PlanForecastChart(forecast: forecast, daily: draft, spanish: spanish, comparison: baseline, selectedDay: $selectedDay, detailed: true)
                    HStack(spacing: 16) {
                        Label(spanish ? "Registrado" : "Recorded", systemImage: "minus")
                        Label(spanish ? "Estimado" : "Estimated", systemImage: "ellipsis")
                        Spacer()
                    }.font(.caption2).foregroundStyle(.secondary)
                    if let event = forecast.events.first(where: { $0.day == selectedDay }) {
                        Text("\(event.title(spanish)) · \(PlanFormat.amount(event.amount))").font(.caption).foregroundStyle(WelcomePalette.pine)
                    }
                }
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Text(spanish ? "Gasto diario" : "Daily spending").font(.subheadline)
                        Spacer()
                        Button { exact = true } label: {
                            HStack(spacing: 6) { Text(PlanFormat.amount(draft)).font(CuadraoTypography.rowAmount); Image(systemName: "pencil").font(.caption) }
                        }.font(.subheadline.weight(.medium)).frame(minHeight: 44).accessibilityIdentifier("forecast-exact")
                    }
                    Slider(value: $draft, in: 0...3000, step: 50) { editing in
                        if editing { selectedDay = nil; saved = false }
                    }.tint(WelcomePalette.pine).accessibilityLabel(spanish ? "Gasto diario previsto" : "Expected daily spending")
                        .accessibilityValue(PlanFormat.amount(draft)).accessibilityIdentifier("forecast-slider")
                    Text(spanish ? "Mueve para probar. Toca el monto para ser más preciso." : "Slide to explore. Tap the amount to be more precise.")
                        .font(.caption).foregroundStyle(.secondary)
                    if changed {
                        let difference = forecast.ending(daily: draft) - forecast.ending(daily: baseline)
                        Text(spanish ? "\(PlanFormat.amount(abs(difference))) \(difference >= 0 ? "más" : "menos") al final del mes." : "\(PlanFormat.amount(abs(difference))) \(difference >= 0 ? "more" : "less") at month end.")
                            .font(.subheadline.weight(.medium)).foregroundStyle(WelcomePalette.pine)
                    }
                }.padding(22).background(WelcomePalette.sage.opacity(0.6), in: RoundedRectangle(cornerRadius: 26))
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: lowest.balance < 0 ? "exclamationmark.circle" : "calendar")
                        .foregroundStyle(lowest.balance < 0 ? Color.orange : WelcomePalette.pine)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(spanish ? "El día más ajustado: \(lowest.day) oct." : "Tightest day: Oct \(lowest.day)").font(.subheadline.weight(.medium))
                        Text(spanish ? "El balance estimado baja a \(PlanFormat.amount(lowest.balance))." : "The estimated balance dips to \(PlanFormat.amount(lowest.balance)).")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                assumptions
                VStack(spacing: 8) {
                    if changed {
                        PlanPrimaryButton(title: isolatedExample
                            ? (spanish ? "Aplicar al ejemplo" : "Apply to example")
                            : (spanish ? "Guardar este ritmo" : "Save this pace")) {
                            store.applyDaily(draft, scope: scope); saved = true
                        }.accessibilityIdentifier("forecast-apply")
                        Button(isolatedExample
                            ? (spanish ? "Restablecer ejemplo" : "Reset example")
                            : (spanish ? "Volver a mi plan" : "Reset to my plan")) { draft = baseline; selectedDay = nil }
                            .frame(minHeight: 44).accessibilityIdentifier("forecast-reset")
                    } else if saved {
                        Label(isolatedExample
                            ? (spanish ? "Ejemplo actualizado" : "Example updated")
                            : (spanish ? "Ritmo guardado" : "Pace saved"), systemImage: "checkmark.circle")
                            .foregroundStyle(WelcomePalette.pine).font(.subheadline).frame(minHeight: 44)
                    }
                    Text(isolatedExample
                        ? (spanish ? "No cambia tus cuentas ni tus planes." : "Your accounts and plans stay unchanged.")
                        : (spanish ? "Solo cambia tu previsión. No mueve dinero." : "Only changes your forecast. No money moves."))
                        .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }
                PlanPreviewFootnote(spanish: spanish)
            }.padding(24).padding(.bottom, bottomSpace)
        }
        .background(WelcomePalette.background).cuadraoSoftScrollEdges()
        .sensoryFeedback(.success, trigger: saved) { _, new in new }
        .navigationTitle(spanish ? "Explorar el mes" : "Explore the month").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .sheet(isPresented: $exact) {
            PlanExactAmount(amount: $draft, maximum: 3000, title: spanish ? "Gasto diario" : "Daily spending", currency: "DOP", spanish: spanish)
        }
    }
    private var assumptions: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 16) {
                Text(spanish ? "Escenario de ejemplo al 12 de octubre de 2026. El ritmo diario es un supuesto editable, no un límite." : "Example scenario as of October 12, 2026. Daily pace is an editable assumption, not a limit.")
                    .font(.subheadline).foregroundStyle(.secondary)
                ForEach(forecast.events) { event in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(event.title(spanish)).font(.subheadline)
                            Text("\(event.day) oct.").font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer(); Text(PlanFormat.amount(event.amount)).font(CuadraoTypography.rowAmount)
                    }
                }
                Text(spanish ? "Incluye estos pagos e ingresos previstos y el gasto diario del 13 al 31. No suma metas, ahorros ni cuentas privadas de otras personas." : "Includes these expected payments and income plus daily spending from the 13th to the 31st. Excludes goals, savings, and other people's private accounts.")
                    .font(.caption).foregroundStyle(.secondary)
            }.padding(.top, 14)
        } label: { Text(spanish ? "¿De dónde sale?" : "What's behind this?").font(.subheadline.weight(.medium)) }
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
                    Text(spanish ? "Usa un monto entre \(minimum.formatted()) y \(PlanFormat.amount(maximum, currency: currency))." : "Use an amount between \(minimum.formatted()) and \(PlanFormat.amount(maximum, currency: currency)).")
                        .font(.caption).foregroundStyle(.red)
                }
            }.navigationTitle(title).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel") { dismiss() }
                    CuadraoConfirmToolbar(title: spanish ? "Listo" : "Done",
                                          disabled: !error.isEmpty || !input.isFinite || input < minimum || input > maximum,
                                          identifier: "plan-exact-done") { amount = input; dismiss() }
                }
        }.presentationDetents([.medium]).presentationDragIndicator(.visible)
            .onAppear { input = amount }
    }
}
