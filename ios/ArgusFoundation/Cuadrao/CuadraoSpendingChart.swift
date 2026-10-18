import Charts
import SwiftUI

/// One wording for a period whose coverage is missing, so no surface reads it as zero.
enum CuadraoMissingCoverage {
    static func amount(_ spanish: Bool) -> String { CuadraoCopy.text("copy.cuadraoSpendingChart.064971dc1c", spanish: spanish) }
    static func title(_ spanish: Bool) -> String { CuadraoCopy.text("copy.cuadraoDesignGallery.a090e20844", spanish: spanish) }
    static func detail(_ spanish: Bool) -> String {
        CuadraoCopy.text("copy.cuadraoSpendingChart.2e2c36a717", spanish: spanish)
    }
}

struct CuadraoSpendingChart: View {
    let expenses: [CanvasActivity]
    let coverageStart: Date?
    let currency: String
    let spanish: Bool
    let distribution: Bool
    let range: CanvasHistoryRange
    @Binding var periodOffset: Int
    var record: (() -> Void)?
    var controls: CuadraoInsightControls?
    var context: CanvasChartFocus?
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var selectedPosition: String?
    @State private var selectedCategory: CanvasExpenseCategory?
    private var story: CanvasSpendingStory { CanvasSpendingStory(expenses: expenses, range: range, offset: periodOffset, coverageStart: coverageStart) }
    private var interval: DateInterval { story.interval }
    private var entries: [CanvasActivity] { story.entries }
    private var total: Decimal { story.total }
    private var slots: [DateInterval] { CanvasSpendingHistory.slots(in: interval, range: range) }
    private var selectedSlot: DateInterval? {
        guard let selectedPosition, let index = slots.firstIndex(where: { tick($0) == selectedPosition }), slots[index].start <= story.now else { return nil }
        return slots[index]
    }
    private var buckets: [CanvasSpendingBucket] { CanvasSpendingHistory.buckets(entries, range: range) }
    private var categories: [CanvasExpenseCategory] { CanvasExpenseCategory.allCases.filter { categoryTotal($0) > 0 } }
    private var inspected: [CanvasActivity]? {
        guard let span = selectedSlot else { return nil }
        return CanvasSpendingHistory.entries(entries, in: span)
    }
    private func categoryTotal(_ category: CanvasExpenseCategory) -> Decimal {
        CanvasSpendingHistory.total(entries.filter { $0.category == category })
    }
    private func money(_ amount: Decimal) -> String { CanvasMoney.format(amount, currency: currency) }
    private var insight: String {
        guard story.covered else {
            return CuadraoCopy.text("copy.cuadraoSpendingChart.6a945d72e9", spanish: spanish)
        }

        if let prior = story.previousTotal {
            let difference = total - prior
            if difference == 0 { return CuadraoCopy.text("copy.cuadraoSpendingChart.02b2264bf1", spanish: spanish) }
            let reference = periodOffset == 0 ? (CuadraoCopy.text("copy.cuadraoSpendingChart.8aef524835", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoSpendingChart.75aecad63d", spanish: spanish))
            return CuadraoCopy.text("copy.cuadraoSpendingChart.107f945395", spanish: spanish, String(describing: currency), String(describing: money(abs(difference))), String(describing: ((difference > 0 ? CuadraoCopy.text("copy.cuadraoSpendingChart.14178c1062", spanish: spanish) : CuadraoCopy.text("copy.cuadraoSpendingChart.d08611ffa1", spanish: spanish)))), String(describing: reference))
        }
        guard let largest = categories.max(by: { categoryTotal($0) < categoryTotal($1) }) else {
            return CuadraoCopy.text("copy.cuadraoSpendingChart.2a0b65c993", spanish: spanish)
        }
        return CuadraoCopy.text("copy.cuadraoSpendingChart.bb160c1c11", spanish: spanish, String(describing: (spanish ? (largest.title(true)) : (largest.title(false)))))
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            CuadraoSpendingReading(currency: currency,
                amount: (inspected ?? entries).isEmpty && !story.covered ? CuadraoMissingCoverage.amount(spanish)
                    : money(inspected.map(CanvasSpendingHistory.total) ?? total),
                caption: selectedSlot.map { range == .year
                    ? $0.start.formatted(.dateTime.month(.wide).year().locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish))))
                    : story.periodText($0, spanish: spanish) } ?? (CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.f5d8dd5e1a", spanish: spanish)),
                insight: story.state == .populated || story.state == .emptyPeriod ? insight : nil)
            if let controls { controls }
            if story.state == .populated {
                if distribution { allocation } else { chart }
            } else { emptyState }
            ForEach(categories) { category in categoryRow(category) }
            CuadraoSpendingHighlights(story: story, currency: currency, spanish: spanish)
            if let context {
                CanvasChartAsk(context: selectedContext(context), spanish: spanish)
            }
        }.onChange(of: range) { _, _ in clearSelection() }
            .onChange(of: periodOffset) { _, _ in clearSelection() }
            .onChange(of: distribution) { _, _ in clearSelection() }
            .sensoryFeedback(.selection, trigger: selectedSlot?.start)
            .sensoryFeedback(.selection, trigger: periodOffset)
    }
    private func selectedContext(_ context: CanvasChartFocus) -> CanvasChartFocus {
        var selected = context
        selected.selection = selectedCategory.map { .expenseCategory(id: $0.rawValue, title: $0.title(spanish)) }
        selected.inspectedInterval = selectedSlot
        selected.inspectedTitle = selectedSlot.map { story.periodText($0, spanish: spanish) }
        return selected
    }
    private var emptyState: some View {
        CuadraoChartState(title: emptyTitle, detail: emptyDetail,
            actionTitle: recordsHere && record != nil ? (CuadraoCopy.text("copy.cuadraoSpendingChart.fcca57c73a", spanish: spanish)) : nil,
            action: recordsHere ? record : nil)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("home-spending-chart")
            .accessibilityValue(String(periodOffset))
    }
    /// First use and the current period with no records offer one record-entry action.
    private var recordsHere: Bool { story.state == .firstUse || (story.state == .emptyPeriod && periodOffset == 0) }
    private var emptyTitle: String {
        switch story.state {
        case .firstUse: return CuadraoCopy.text("copy.cuadraoDesignGallery.4fec8a8355", spanish: spanish)
        case .unavailable: return CuadraoMissingCoverage.title(spanish)
        case .emptyPeriod: return CuadraoCopy.text("copy.cuadraoDesignGallery.d9ec23ea81", spanish: spanish)
        case .populated: return ""
        }
    }
    private var emptyDetail: String {
        switch story.state {
        case .firstUse: return CuadraoCopy.text("copy.cuadraoSpendingChart.d92c2b06f9", spanish: spanish)
        case .unavailable: return CuadraoMissingCoverage.detail(spanish)
        case .emptyPeriod:
            return periodOffset == 0
                ? (CuadraoCopy.text("copy.cuadraoDesignGallery.25ab80246f", spanish: spanish))
                : (CuadraoCopy.text("copy.cuadraoSpendingChart.6a76acb5a3", spanish: spanish))
        case .populated: return ""
        }
    }
    private var chart: some View {
        Chart {
            ForEach(buckets) { bucket in
                BarMark(x: .value(CuadraoCopy.text("copy.cuadraoSpendingChart.296b533cc7", spanish: spanish), tick(CanvasSpendingHistory.bucketInterval(containing: bucket.date, range: range))), y: .value(CuadraoCopy.text("copy.cuadraoSpendingChart.8752de5bdb", spanish: spanish), bucket.value), width: .ratio(0.65))
                    .foregroundStyle(by: .value(CuadraoCopy.text("copy.cuadraoSpendingChart.67c7ee0c0f", spanish: spanish), bucket.category.title(spanish)))
                    .accessibilityLabel(bucket.date.formatted(date: .abbreviated, time: .omitted) + ", " + bucket.category.title(spanish))
                    .accessibilityValue(currency + " " + money(bucket.amount))
            }
            if let selectedSlot {
                RuleMark(x: .value(CuadraoCopy.text("copy.cuadraoSpendingChart.296b533cc7", spanish: spanish), tick(selectedSlot))).foregroundStyle(WelcomePalette.ink.opacity(0.25))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 4])).accessibilityHidden(true)
            }
        }.chartForegroundStyleScale(domain: CanvasExpenseCategory.allCases.map { $0.title(spanish) }, range: CanvasExpenseCategory.allCases.map(\.color))
            .chartLegend(.hidden).chartXScale(domain: slots.map(tick))
            .chartYScale(domain: 0...max(1, peak * 1.15))
            .chartXAxis {
                AxisMarks(values: axisPositions) { value in
                    AxisTick()
                    AxisValueLabel {
                        if let position = value.as(String.self) { Text(position).font(.caption2).fixedSize(horizontal: true, vertical: true) }
                    }
                }
            }
            .chartXAxisLabel(position: .bottom, alignment: .leading) {
                Text(axisContext).font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
            .chartYAxis { AxisMarks(position: .trailing, values: .automatic(desiredCount: 3)) }
            .chartOverlay { proxy in
                GeometryReader { geometry in
                    CuadraoChartTouchSurface(inspect: { inspect($0, proxy: proxy, geometry: geometry) })
                }
            }
            .frame(height: 270).padding(14)
            .background(WelcomePalette.surface.opacity(0.5), in: RoundedRectangle(cornerRadius: 22))
            .accessibilityIdentifier("home-spending-chart")
            .accessibilityValue(String(periodOffset))
            .accessibilityLabel(CuadraoCopy.text("copy.cuadraoSpendingChart.dcf355d2ae", spanish: spanish))
    }
    private func inspect(_ location: CGPoint, proxy: ChartProxy, geometry: GeometryProxy) {
        guard let frame = proxy.plotFrame else { return }
        let plot = geometry[frame]
        selectedPosition = proxy.value(atX: min(max(0, location.x - plot.minX), plot.width), as: String.self)
    }
    private var peak: Double {
        Dictionary(grouping: buckets, by: \.date).values.map { $0.reduce(0) { $0 + $1.value } }.max() ?? 0
    }
    private var axisContext: String {
        let format = Date.FormatStyle.dateTime.locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))
        if range == .year { return interval.start.formatted(format.year()) }
        let start = interval.start.formatted(format.month(.abbreviated).year())
        let end = interval.end.addingTimeInterval(-1).formatted(format.month(.abbreviated).year())
        return start == end ? start : start + " – " + end
    }
    private var axisPositions: [String] {
        let step = range == .year ? (typeSize.isAccessibilitySize ? 3 : 2) : (range == .month && typeSize.isAccessibilitySize ? 2 : 1)
        return stride(from: 0, to: slots.count, by: step).map { tick(slots[$0]) }
    }
    private func tick(_ span: DateInterval) -> String {
        let format = Date.FormatStyle.dateTime.locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))
        switch range {
        case .week: return span.start.formatted(format.weekday(.narrow)) + "\n" + span.start.formatted(format.day())
        case .month:
            let first = span.start.formatted(format.day())
            let last = span.end.addingTimeInterval(-1).formatted(format.day())
            return first == last ? first : first + "–" + last
        case .year: return span.start.formatted(format.month(.abbreviated))
        }
    }
    private var allocation: some View {
        VStack(alignment: .leading, spacing: 12) {
            CuadraoAllocationBar(segments: categories.map {
                CuadraoAllocationSegment(id: $0.rawValue, title: $0.title(spanish), fraction: fraction(categoryTotal($0)), color: $0.color)
            }, selection: Binding(get: { selectedCategory?.rawValue }, set: { selectedCategory = $0.flatMap(CanvasExpenseCategory.init(rawValue:)) }),
                identifier: "home-spending-segment-")
            HStack(spacing: 8) {
                Button { selectedCategory = nil } label: { Text(CuadraoCopy.text("copy.cuadraoDistributionContent.64c04b1430", spanish: spanish)).frame(minHeight: 44).contentShape(Rectangle()) }
                    .buttonStyle(.plain)
                    .foregroundStyle(selectedCategory == nil ? WelcomePalette.ink : .secondary)
                    .accessibilityIdentifier("home-spending-all")
                if let selectedCategory {
                    Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                    Text(selectedCategory.title(spanish)).foregroundStyle(selectedCategory.color)
                }
                Spacer()
            }.font(CuadraoTypography.supporting)
        }.padding(.vertical, 20)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("home-spending-distribution")
    }
    private func categoryRow(_ category: CanvasExpenseCategory) -> some View {
        DisclosureGroup(isExpanded: Binding(get: { selectedCategory == category }, set: { selectedCategory = $0 ? category : nil })) {
            LazyVStack(spacing: 0) {
            ForEach(entries.filter { $0.category == category }.sorted { $0.date > $1.date }) { entry in
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(entry.title).font(CuadraoTypography.supporting)
                        Text(entry.date.formatted(.dateTime.day().month(.abbreviated).locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish))))).font(CuadraoTypography.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(money(entry.amount)).font(CuadraoTypography.rowAmount)
                }.padding(.vertical, 8)
            }
            }
        } label: {
            HStack(spacing: 12) {
                CuadraoExpenseCategoryIcon(category: category)
                Text(category.title(spanish)).font(CuadraoTypography.supporting)
                Spacer(minLength: 8)
                VStack(alignment: .trailing, spacing: 4) {
                    Text(money(categoryTotal(category))).font(CuadraoTypography.rowAmount)
                    Text(fraction(categoryTotal(category)), format: .percent.precision(.fractionLength(1)))
                        .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                }
            }.frame(minHeight: 44)
        }.accessibilityIdentifier("home-spending-category-" + category.rawValue)
    }
    private func fraction(_ value: Decimal) -> Double { total > 0 ? NSDecimalNumber(decimal: value / total).doubleValue : 0 }
    private func clearSelection() { selectedPosition = nil; selectedCategory = nil }
}

struct CuadraoSpendingReading: View {
    let currency: String
    let amount: String
    let caption: String
    var insight: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(currency).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                Text(amount).font(CuadraoTypography.amount).lineLimit(1).minimumScaleFactor(0.5)
                    .accessibilityIdentifier("home-spending-total")
            }
            Text(caption).font(CuadraoTypography.caption).foregroundStyle(.secondary)
            if let insight {
                Text(insight).font(CuadraoTypography.supporting).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("home-spending-insight")
            }
        }
    }
}
