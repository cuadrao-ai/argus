import SwiftUI
import Charts

@main
struct ChartPrototypeApp: App {
    init() { ChartStyle.registerFonts() }
    var body: some Scene { WindowGroup { PrototypeView() } }
}

struct PrototypeView: View {
    private let bundle = Result { try FixtureBundle.load() }
    var body: some View {
        switch bundle {
        case .success(let fixtures): ChartPage(scenarios: fixtures.cases)
        case .failure(let error): Text("Fixture could not load: \(error.localizedDescription)")
        }
    }
}

struct ChartPage: View {
    let scenarios: [Scenario]
    private let plots: [String: PlotData]
    init(scenarios: [Scenario]) {
        self.scenarios = scenarios
        self.plots = Dictionary(uniqueKeysWithValues: scenarios.map { ($0.id, PlotData($0)) })
    }
    @State private var scenarioID = ProcessInfo.processInfo.environment["CHART_CASE"] ?? "stress"
    @State private var spanish = ProcessInfo.processInfo.environment["CHART_LOCALE"] == "es-419"
    @State private var theme = ProcessInfo.processInfo.environment["CHART_THEME"] ?? "system"
    @State private var selection = Selection()
    @Environment(\.scenePhase) private var phase
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var amountHeight = 40
    private var scenario: Scenario { scenarios.first { $0.id == scenarioID } ?? scenarios[0] }
    private var presentation: Presentation { Presentation(spanish: spanish) }
    private var selected: Sample? { selection.index.flatMap { scenario.points.indices.contains($0) ? scenario.points[$0] : nil } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(presentation.text("Explore the picture", "Explora el panorama")).font(ChartStyle.display())
                    Text(presentation.text("Synthetic data · chart prototype", "Datos sintéticos · prototipo de gráfico"))
                        .font(ChartStyle.body(13, relativeTo: .caption)).foregroundStyle(ChartStyle.secondary)
                }
                VStack(alignment: .leading, spacing: 20) {
                    Text(scenario.title[spanish ? "es-419" : "en"] ?? scenario.id)
                        .font(ChartStyle.display(20, relativeTo: .headline))
                    readout
                    FinancialChart(scenario: scenario, selection: $selection, presentation: presentation, data: plots[scenario.id]!)
                        .equatable().frame(height: 220)
                        .accessibilityIdentifier("financialChart")
                    HStack(spacing: 20) {
                        legend(presentation.text("Actual", "Real"), color: ChartStyle.actual, dashed: false)
                        legend(presentation.text("Projected", "Proyectada"), color: ChartStyle.projected, dashed: true)
                    }
                    buttonLayout {
                        Button(presentation.text("Previous", "Anterior")) { selection.step(-1, count: scenario.points.count) }
                            .accessibilityIdentifier("previous").disabled(scenario.points.isEmpty)
                        Button(presentation.text("Next", "Siguiente")) { selection.step(1, count: scenario.points.count) }
                            .accessibilityIdentifier("next").disabled(scenario.points.isEmpty)
                        Button(presentation.text("Reset", "Restablecer")) { selection.reset() }
                            .accessibilityIdentifier("reset")
                    }.buttonStyle(ChartPillStyle())
                    Text(presentation.text("Drag sideways to explore, or use the buttons. Swipe up to scroll.", "Arrastra de lado para explorar o usa los botones. Desliza arriba para desplazar."))
                        .font(ChartStyle.body(13, relativeTo: .caption)).foregroundStyle(ChartStyle.secondary)
                }
                Divider().overlay(ChartStyle.grid)
                VStack(alignment: .leading, spacing: 16) {
                    Text(presentation.text("Chart lab", "Laboratorio de gráficos")).font(ChartStyle.display(20, relativeTo: .headline))
                    Text(presentation.text("Change the sample, language and appearance below.", "Cambia el ejemplo, el idioma y la apariencia aquí."))
                        .font(ChartStyle.body(14, relativeTo: .subheadline)).foregroundStyle(ChartStyle.secondary)
                    controls
                    Text("\(scenario.currency) · UTC · \(presentation.text("major currency units", "unidades monetarias mayores"))")
                        .font(ChartStyle.body(13, relativeTo: .caption)).foregroundStyle(ChartStyle.secondary)
                    Text(presentation.text("Every amount comes from the shared synthetic fixture. Dashed lines are authored projections, not forecasts. Missing samples remain missing; no line connects across a missing interval.", "Cada importe proviene del conjunto sintético compartido. Las líneas discontinuas son proyecciones de ejemplo, no pronósticos. Los datos faltantes siguen faltando; ninguna línea conecta a través de esos intervalos."))
                    Text(presentation.text("Contributions are dated facts, not returns. USD and DOP stay separate. Dates are civil days shown in UTC.", "Los aportes son datos fechados, no rendimientos. USD y DOP permanecen separados. Las fechas son días civiles mostrados en UTC."))
                    Text(presentation.text("End of scroll proof", "Fin de prueba de desplazamiento"))
                        .font(ChartStyle.body(13, relativeTo: .caption)).foregroundStyle(ChartStyle.secondary)
                        .accessibilityIdentifier("scrollEnd")
                }.font(ChartStyle.body(14, relativeTo: .subheadline))
            }.padding(24)
        }
        .font(ChartStyle.body()).foregroundStyle(ChartStyle.ink)
        .background(ChartStyle.background).tint(ChartStyle.ink)
        .environment(\.locale, presentation.locale)
        .preferredColorScheme(theme == "system" ? nil : (theme == "dark" ? .dark : .light))
        .onChange(of: scenarioID) { _, _ in selection.reset() }
        .onChange(of: phase) { _, value in if value != .active { selection.cancel() } }
    }
    private var buttonLayout: AnyLayout {
        typeSize.isAccessibilitySize ? AnyLayout(VStackLayout(spacing: 8)) : AnyLayout(HStackLayout(spacing: 8))
    }
    private func legend(_ label: String, color: Color, dashed: Bool) -> some View {
        HStack(spacing: 6) {
            Path { path in path.move(to: .zero); path.addLine(to: CGPoint(x: 24, y: 0)) }
                .stroke(color, style: StrokeStyle(lineWidth: 2.5, dash: dashed ? [5, 3] : []))
                .frame(width: 24, height: 2)
            Text(label).font(ChartStyle.body(13, relativeTo: .caption))
        }.accessibilityElement(children: .combine)
    }
    private var controls: some View {
        VStack(alignment: .leading, spacing: 16) {
            Picker(presentation.text("Scenario", "Escenario"), selection: $scenarioID) {
                ForEach(scenarios) { scenario in
                    Text(scenario.title[spanish ? "es-419" : "en"] ?? scenario.id)
                        .tag(scenario.id).accessibilityIdentifier("scenario-option-" + scenario.id)
                }
            }.accessibilityIdentifier("scenario").frame(minHeight: 44)
            Toggle("Español (Latinoamérica)", isOn: $spanish).accessibilityIdentifier("locale")
            Picker(presentation.text("Appearance", "Apariencia"), selection: $theme) {
                Text(presentation.text("System", "Sistema")).tag("system")
                Text(presentation.text("Light", "Claro")).tag("light")
                Text(presentation.text("Dark", "Oscuro")).tag("dark")
            }.pickerStyle(.segmented).accessibilityIdentifier("theme").frame(minHeight: 44)
        }
    }
    private var readout: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(selected.map { presentation.date($0.date) } ?? presentation.text("Select a date", "Elige una fecha"))
                .font(ChartStyle.body(14, relativeTo: .subheadline)).foregroundStyle(ChartStyle.secondary)
                .accessibilityIdentifier("selectedDate")
            Text(presentation.amount(selected?.actual, currency: scenario.currency))
                .font(ChartStyle.display(30, relativeTo: .title)).monospacedDigit()
                .lineLimit(1).minimumScaleFactor(0.65).frame(height: amountHeight, alignment: .leading)
                .accessibilityLabel("\(presentation.text("Actual", "Real")): \(presentation.amount(selected?.actual, currency: scenario.currency))")
                .accessibilityIdentifier("actualValue")
            HStack {
                Text(presentation.text("Actual", "Real")).foregroundStyle(ChartStyle.secondary)
                Spacer()
            }.font(ChartStyle.body(13, relativeTo: .caption))
            Text("\(presentation.text("Projected", "Proyectada")): \(presentation.amount(selected?.projected, currency: scenario.currency))")
                .accessibilityIdentifier("projectedValue")
            Text("\(presentation.text("Contribution", "Aporte")): \(presentation.amount(selected?.contribution, currency: scenario.currency))")
                .accessibilityIdentifier("contributionValue")
        }.font(ChartStyle.body(14, relativeTo: .subheadline).monospacedDigit())
            .frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading)
    }
}

struct FinancialChart: View, Equatable {
    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.scenario.id == rhs.scenario.id && lhs.presentation.spanish == rhs.presentation.spanish
    }
    let scenario: Scenario
    @Binding var selection: Selection
    let presentation: Presentation
    let data: PlotData
    @ScaledMetric(relativeTo: .caption2) private var axisEdgePadding = 18
    var body: some View {
        Chart {
            ForEach(data.actual) { point in
                LineMark(x: .value("Date", point.date), y: .value("Actual", point.value), series: .value("Segment", point.segment))
                    .interpolationMethod(.linear).foregroundStyle(ChartStyle.actual).lineStyle(StrokeStyle(lineWidth: 2.5))
            }
            ForEach(data.projected) { point in
                LineMark(x: .value("Date", point.date), y: .value("Projected", point.value), series: .value("Segment", point.segment))
                    .interpolationMethod(.linear).foregroundStyle(ChartStyle.projected).lineStyle(StrokeStyle(lineWidth: 2.5, dash: [6, 4]))
            }
            ForEach(data.actual) { point in
                PointMark(x: .value("Date", point.date), y: .value("Actual", point.value))
                    .foregroundStyle(ChartStyle.actual).symbolSize(data.actual.count > 100 ? 2 : 16)
            }
            ForEach(data.projected) { point in
                PointMark(x: .value("Date", point.date), y: .value("Projected", point.value))
                    .foregroundStyle(ChartStyle.projected).symbol(.diamond).symbolSize(data.projected.count > 100 ? 2 : 20)
            }
        }
        .chartXScale(domain: data.domain)
        .chartXScale(range: .plotDimension(padding: axisEdgePadding))
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 3)) { value in
                AxisValueLabel(collisionResolution: .greedy) {
                    if let date = value.as(Date.self) {
                        Text(presentation.date(date, compact: true))
                            .font(ChartStyle.body(11, relativeTo: .caption2)).fixedSize()
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) {
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5)).foregroundStyle(ChartStyle.grid)
                AxisValueLabel().font(ChartStyle.body(11, relativeTo: .caption2))
            }
        }
        .chartXAxis(scenario.points.isEmpty ? .hidden : .automatic)
        .chartYAxis(scenario.points.isEmpty ? .hidden : .automatic)
        .chartOverlay { proxy in
            ChartInteraction(proxy: proxy, data: data, selection: $selection)
        }
        .overlay { if scenario.points.isEmpty { Text(presentation.text("No data", "Sin datos")) } }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(presentation.text("Financial chart. Use Previous and Next for every sample.", "Gráfico financiero. Usa Anterior y Siguiente para cada dato."))
    }
}


private struct ChartInteraction: View {
    let proxy: ChartProxy
    let data: PlotData
    @Binding var selection: Selection
    var body: some View {
        GeometryReader { geometry in
            if let anchor = proxy.plotFrame {
                let frame = geometry[anchor]
                if let index = selection.index, data.dates.indices.contains(index),
                   let x = proxy.position(forX: data.dates[index]) {
                    Rectangle().fill(.secondary).frame(width: 1, height: frame.height)
                        .position(x: frame.minX + x, y: frame.midY).allowsHitTesting(false)
                }
                HorizontalScrubber { state, x in
                    switch state {
                    case .began: selection.begin(); fallthrough
                    case .changed:
                        if let date: Date = proxy.value(atX: min(max(x, 0), frame.width)) { selection.select(data.nearest(date)) }
                    case .ended: selection.end()
                    case .cancelled, .failed: selection.cancel()
                    default: break
                    }
                }.frame(width: frame.width, height: frame.height).position(x: frame.midX, y: frame.midY)
            }
        }
    }
}
