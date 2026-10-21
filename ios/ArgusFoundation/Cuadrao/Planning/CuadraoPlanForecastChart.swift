import SwiftUI
import Charts

struct CuadraoPlanChartPoint: Identifiable {
    let id: Int
    let position: Double
    let balance: Double
}

struct CuadraoPlanChartTick: Identifiable {
    let position: Double
    let title: String
    var id: Double { position }
}

struct CuadraoPlanForecastChart: View {
    let spanish: Bool
    let recorded: [CuadraoPlanChartPoint]
    let projected: [CuadraoPlanChartPoint]
    var comparison: [CuadraoPlanChartPoint] = []
    let xRange: ClosedRange<Double>
    let yRange: ClosedRange<Double>
    let ticks: [CuadraoPlanChartTick]
    var today: Double? = nil
    var selected: CuadraoPlanChartPoint? = nil
    @Binding var selection: Double?
    var detailed = false
    var compact = false
    /// A schedule-based projection holds each balance until the next scheduled date.
    var stepped = false
    let identifier: String
    let accessibilityTitle: String
    let accessibilityAmount: String

    var body: some View {
        Chart {
            ForEach(recorded) { point in
                AreaMark(x: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.9e3d3b41ed", spanish: spanish), point.position), y: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.02e2073456", spanish: spanish), point.balance))
                    .foregroundStyle(LinearGradient(colors: [WelcomePalette.pine.opacity(0.13), .clear], startPoint: .top, endPoint: .bottom))
                LineMark(x: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.9e3d3b41ed", spanish: spanish), point.position), y: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.02e2073456", spanish: spanish), point.balance), series: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.ec94e4cbf1", spanish: spanish), "actual"))
                    .foregroundStyle(WelcomePalette.pine).lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round))
                    .interpolationMethod(.linear)
            }
            ForEach(comparison) { point in
                LineMark(x: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.9e3d3b41ed", spanish: spanish), point.position), y: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.02e2073456", spanish: spanish), point.balance), series: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.ec94e4cbf1", spanish: spanish), "baseline"))
                    .foregroundStyle(Color.secondary.opacity(0.3)).lineStyle(StrokeStyle(lineWidth: 1.5, dash: [3, 5]))
            }
            ForEach(projected) { point in
                LineMark(x: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.9e3d3b41ed", spanish: spanish), point.position), y: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.02e2073456", spanish: spanish), point.balance), series: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.ec94e4cbf1", spanish: spanish), "forecast"))
                    .foregroundStyle(WelcomePalette.pine).lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, dash: [5, 5]))
                    .interpolationMethod(stepped ? .stepEnd : .linear)
                if projected.count == 1 {
                    PointMark(x: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.9e3d3b41ed", spanish: spanish), point.position), y: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.02e2073456", spanish: spanish), point.balance))
                        .foregroundStyle(WelcomePalette.pine).symbolSize(30)
                }
            }
            if let today {
                RuleMark(x: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.ebdcdc2bda", spanish: spanish), today))
                    .foregroundStyle(Color.secondary.opacity(0.25)).lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 4]))
            }
            if detailed {
                RuleMark(y: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.babd5a1631", spanish: spanish), 0)).foregroundStyle(Color.secondary.opacity(0.18))
            }
            if let point = selected {
                RuleMark(x: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.0d86e026ac", spanish: spanish), point.position)).foregroundStyle(WelcomePalette.pine.opacity(0.4))
                PointMark(x: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.9e3d3b41ed", spanish: spanish), point.position), y: .value(CuadraoCopy.text("copy.cuadraoPlanForecastChart.02e2073456", spanish: spanish), point.balance))
                    .foregroundStyle(WelcomePalette.pine).symbolSize(45)
            }
        }
        .chartXScale(domain: xRange)
        .chartYScale(domain: yRange)
        .chartYAxis(.hidden)
        .chartXAxis {
            AxisMarks(values: ticks.map(\.position)) { value in
                AxisValueLabel(anchor: value.as(Double.self) == ticks.last?.position ? .topTrailing : value.as(Double.self) == ticks.first?.position ? .topLeading : .top, collisionResolution: .disabled) {
                    if let position = value.as(Double.self), let tick = ticks.first(where: { $0.position == position }) {
                        Text(tick.title).font(.caption2)
                    }
                }
            }
        }
        .chartXSelection(value: $selection)
        .accessibilityIdentifier(identifier)
        .frame(height: compact ? 95 : detailed ? 170 : 150)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityTitle)
        .accessibilityValue(accessibilityAmount)
    }
}
