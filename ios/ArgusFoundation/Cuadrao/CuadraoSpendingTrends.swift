import SwiftUI
import Charts

struct CuadraoSpendingTrendCard: View {
    let insight: CanvasSpendingInsight
    let story: CanvasSpendingStory
    let currency: String
    let spanish: Bool
    private var color: Color { insight.category?.color ?? WelcomePalette.pine }
    private func money(_ amount: Decimal) -> String { currency + " " + CanvasMoney.format(amount, currency: currency) }
    private var statement: String {
        if insight.kind == .trend {
            return CuadraoCopy.text("copy.cuadraoSpendingTrends.7ed0d4b722", spanish: spanish, String(describing: ((insight.difference > 0 ? CuadraoCopy.text("copy.cuadraoSpendingTrends.9ccf938126", spanish: spanish) : CuadraoCopy.text("copy.cuadraoSpendingTrends.00cdef7854", spanish: spanish)))), String(describing: money(abs(insight.difference))))
        }
        return CuadraoCopy.text("copy.cuadraoSpendingTrends.4f45922a2c", spanish: spanish, String(describing: money(insight.average)), String(describing: insight.months.count))
    }
    var body: some View {
        NavigationLink {
            CuadraoSpendingTrendEvidence(insight: insight, story: story, currency: currency, spanish: spanish)
        } label: {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 12) {
                    if let category = insight.category { CuadraoExpenseCategoryIcon(category: category) }
                    else { Image(systemName: "chart.bar.xaxis").font(.title3).foregroundStyle(color).frame(width: 42, height: 42).background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 13)) }
                    Text(insight.category?.title(spanish) ?? (CuadraoCopy.text("copy.cuadraoSpendingTrends.795ca2344f", spanish: spanish, String(describing: insight.months.count))))
                        .font(CuadraoTypography.supporting).foregroundStyle(color)
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(.secondary)
                }
                Text(statement).font(CuadraoTypography.body).fixedSize(horizontal: false, vertical: true)
                Divider()
                chart
                if insight.kind == .trend {
                    HStack(alignment: .top, spacing: 16) {
                        reference(insight.priorAverage, title: CuadraoCopy.text("copy.cuadraoSpendingTrends.cd017f7732", spanish: spanish), color: .secondary)
                        Spacer(minLength: 0)
                        reference(insight.recentAverage, title: CuadraoCopy.text("copy.cuadraoSpendingTrends.fb769b524a", spanish: spanish), color: color)
                    }
                } else { reference(insight.average, title: CuadraoCopy.text("copy.cuadraoSpendingTrends.f562465264", spanish: spanish), color: color) }
                Text(windowLabel).font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
                .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 24))
        }.buttonStyle(.plain).accessibilityIdentifier("home-highlight-" + insight.id)
    }
    private var windowLabel: String {
        let style = Date.FormatStyle.dateTime.month(.abbreviated).year().locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))
        return insight.interval.start.formatted(style) + " – " + insight.interval.end.addingTimeInterval(-1).formatted(style)
    }
    private func reference(_ value: Decimal, title: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(money(value)).font(CuadraoTypography.rowAmount).foregroundStyle(color)
            Text(title).font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }
    }
    private var chart: some View {
        Chart {
            ForEach(insight.months) { month in
                BarMark(x: .value(CuadraoCopy.text("copy.cuadraoSpendingTrends.c0d1241cc1", spanish: spanish), month.interval.start, unit: .month), y: .value(CuadraoCopy.text("copy.cuadraoSpendingTrends.8752de5bdb", spanish: spanish), NSDecimalNumber(decimal: month.amount).doubleValue))
                    .foregroundStyle(WelcomePalette.ink.opacity(0.16)).cornerRadius(3)
                    .accessibilityLabel(month.interval.start.formatted(.dateTime.month().year().locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))))
                    .accessibilityValue(money(month.amount))
            }
            if insight.kind == .trend {
                RuleMark(xStart: .value(CuadraoCopy.text("copy.cuadraoSpendingTrends.87eb0c0972", spanish: spanish), insight.interval.start), xEnd: .value(CuadraoCopy.text("copy.cuadraoSpendingTrends.4f1e585adf", spanish: spanish), insight.months[9].interval.start), y: .value(CuadraoCopy.text("copy.cuadraoSpendingTrends.aee00efaba", spanish: spanish), NSDecimalNumber(decimal: insight.priorAverage).doubleValue))
                    .foregroundStyle(WelcomePalette.ink.opacity(0.45)).lineStyle(StrokeStyle(lineWidth: 4, lineCap: .round))
                RuleMark(xStart: .value(CuadraoCopy.text("copy.cuadraoSpendingTrends.87eb0c0972", spanish: spanish), insight.months[9].interval.start), xEnd: .value(CuadraoCopy.text("copy.cuadraoSpendingTrends.4f1e585adf", spanish: spanish), insight.interval.end), y: .value(CuadraoCopy.text("copy.cuadraoSpendingTrends.aee00efaba", spanish: spanish), NSDecimalNumber(decimal: insight.recentAverage).doubleValue))
                    .foregroundStyle(color).lineStyle(StrokeStyle(lineWidth: 4, lineCap: .round))
            } else {
                RuleMark(y: .value(CuadraoCopy.text("copy.cuadraoSpendingTrends.aee00efaba", spanish: spanish), NSDecimalNumber(decimal: insight.average).doubleValue))
                    .foregroundStyle(color).lineStyle(StrokeStyle(lineWidth: 4, lineCap: .round))
            }
        }.chartXScale(domain: insight.interval.start...insight.interval.end).chartYAxis(.hidden)
            .chartXAxis { AxisMarks(values: .stride(by: .month, count: insight.months.count == 12 ? 3 : 1)) { value in
                AxisValueLabel {
                    if let date = value.as(Date.self) { Text(date.formatted(.dateTime.month(.abbreviated).locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish))))) }
                }
            } }.frame(height: 160).allowsHitTesting(false)
    }
}

private struct CuadraoSpendingTrendEvidence: View {
    let insight: CanvasSpendingInsight
    let story: CanvasSpendingStory
    let currency: String
    let spanish: Bool
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 24) {
                ForEach(insight.months.reversed()) { month in
                    VStack(alignment: .leading, spacing: 12) {
                        Text(month.interval.start.formatted(.dateTime.month(.wide).year().locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))))
                            .font(CuadraoTypography.feature)
                        Text(currency + " " + CanvasMoney.format(month.amount, currency: currency)).font(CuadraoTypography.secondaryAmount)
                        let records = CanvasSpendingHistory.entries(story.expenses, in: month.interval).filter { insight.category == nil || $0.category == insight.category }
                        if records.isEmpty { Text(CuadraoCopy.text("copy.cuadraoSpendingHighlights.ae1f889e38", spanish: spanish)).foregroundStyle(.secondary) }
                        ForEach(records.sorted { $0.date > $1.date }) { entry in
                            HStack(alignment: .top) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(entry.title)
                                    Text(entry.date.formatted(.dateTime.day().month(.abbreviated).locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish))))).font(CuadraoTypography.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text(CanvasMoney.format(entry.amount, currency: currency)).font(CuadraoTypography.rowAmount)
                            }.padding(.vertical, 6)
                        }
                    }
                }
            }.padding(24)
        }.background(WelcomePalette.background).navigationTitle(insight.category?.title(spanish) ?? (CuadraoCopy.text("copy.cuadraoSpendingHighlights.e21847e80d", spanish: spanish)))
            .navigationBarTitleDisplayMode(.inline).accessibilityIdentifier("home-highlight-records")
    }
}
