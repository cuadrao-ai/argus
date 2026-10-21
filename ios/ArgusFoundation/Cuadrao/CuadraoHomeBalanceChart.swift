import SwiftUI
import Charts

/// Builds the balance history when its inputs change; scrubbing only re-evaluates the chart below it.
struct CuadraoHomeBalanceChart: View {
    let accounts: [CanvasAccount]
    let observations: [CanvasBalanceObservation]
    let currency: String
    let currencies: [String]
    let spanish: Bool
    let shared: Bool
    let chooseCurrency: (String) -> Void
    var expanded = false
    var expand: () -> Void = {}
    var controls: CuadraoInsightControls?
    /// Built by the owner from the same accounts and observations, when it already has one.
    var history: CanvasBuiltBalanceHistory?
    /// An owner that totals its own history also says whether any account is unknown.
    var partial: Bool?
    var amountIdentifier = "home-chart-amount"
    @Binding var range: CanvasHistoryRange
    @Binding var periodOffset: Int
    init(accounts: [CanvasAccount], observations: [CanvasBalanceObservation], currency: String,
         currencies: [String], spanish: Bool, shared: Bool, chooseCurrency: @escaping (String) -> Void,
         expanded: Bool = false, expand: @escaping () -> Void = {}, controls: CuadraoInsightControls? = nil,
         history: CanvasBuiltBalanceHistory? = nil, partial: Bool? = nil, amountIdentifier: String = "home-chart-amount",
         range: Binding<CanvasHistoryRange> = .constant(.month), periodOffset: Binding<Int> = .constant(0)) {
        self.accounts = accounts; self.observations = observations; self.currency = currency
        self.currencies = currencies; self.spanish = spanish; self.shared = shared; self.chooseCurrency = chooseCurrency
        self.expanded = expanded; self.expand = expand; self.controls = controls; self.history = history
        self.partial = partial; self.amountIdentifier = amountIdentifier
        _range = range; _periodOffset = periodOffset
    }
    var body: some View {
        CuadraoHomeBalanceChartContent(accounts: accounts, observations: observations, currency: currency,
            currencies: currencies, spanish: spanish, shared: shared, chooseCurrency: chooseCurrency,
            expanded: expanded, expand: expand, controls: controls,
            built: history ?? CanvasBuiltBalanceHistory(accounts: accounts, observations: observations, now: .now),
            partialOverride: partial, amountIdentifier: amountIdentifier, range: $range, periodOffset: $periodOffset)
    }
}

private struct CuadraoHomeBalanceChartContent: View {
    let accounts: [CanvasAccount]
    let observations: [CanvasBalanceObservation]
    let currency: String
    let currencies: [String]
    let spanish: Bool
    let shared: Bool
    let chooseCurrency: (String) -> Void
    let expanded: Bool
    let expand: () -> Void
    let controls: CuadraoInsightControls?
    let built: CanvasBuiltBalanceHistory
    let partialOverride: Bool?
    let amountIdentifier: String
    @Environment(\.dynamicTypeSize) var typeSize
    @Environment(\.cuadraoCurrencyRules) var rules
    @State var compactRange: CanvasHomeRange = .month
    @Binding var range: CanvasHistoryRange
    @Binding var periodOffset: Int
    @State var selectedDate: Date?
    /// The history depends on the clock only through its day, so the built one holds until the day changes.
    private func history(_ now: Date) -> [CanvasBalancePoint] {
        built.points(on: now) ?? CanvasBalanceHistory.points(accounts: accounts, observations: observations, now: now)
    }
    /// Everything drawn from the history, derived once per body pass: the marks read it per point.
    private struct Reading {
        let availableRanges: [CanvasHomeRange]
        let effectiveRange: CanvasHomeRange
        let points: [CanvasBalancePoint]
        let xDomain: ClosedRange<Date>
        let selected: CanvasBalancePoint?
        let shown: CanvasBalancePoint?
        let bounds: ClosedRange<Double>
        let period: CanvasBalancePeriod?
    }
    private var reading: Reading {
        let now = Date.now
        let history = history(now)
        let availableRanges = CanvasHomeRange.available(history)
        let effectiveRange = availableRanges.contains(compactRange) ? compactRange : .all
        let points = expanded ? range.points(history, offset: periodOffset) : effectiveRange.points(history)
        let xDomain: ClosedRange<Date>
        if expanded {
            let interval = range.interval(offset: periodOffset)
            xDomain = interval.start...interval.end
        } else {
            let first = points.first?.date ?? Date.now
            xDomain = first...max(points.last?.date ?? first, first.addingTimeInterval(86400))
        }
        let selected = selectedDate.flatMap { selectedDate in
            points.min { abs($0.date.timeIntervalSince(selectedDate)) < abs($1.date.timeIntervalSince(selectedDate)) }
        }
        let period = expanded ? CanvasBalancePeriod(accounts: accounts, observations: observations, range: range,
            offset: periodOffset, now: now, history: history) : nil
        let values = points.map(\.value)
        let low = values.min() ?? 0, high = values.max() ?? 1
        let step = pow(10, floor(log10(max(high - low, max(abs(high) * 0.01, 1)))))
        return Reading(availableRanges: availableRanges, effectiveRange: effectiveRange, points: points, xDomain: xDomain,
            selected: selected, shown: selected ?? (expanded ? period?.closing : points.last),
            bounds: (floor((low - step * 0.2) / step) * step)...(ceil((high + step * 0.2) / step) * step), period: period)
    }
    private var partial: Bool { partialOverride ?? accounts.contains { $0.balance == nil } }
    var body: some View {
        let reading = reading
        let points = reading.points, xDomain = reading.xDomain, selected = reading.selected, shown = reading.shown
        let availableRanges = reading.availableRanges, effectiveRange = reading.effectiveRange
        VStack(alignment: .leading, spacing: 12) {
            amountRow(shown)
            Text((expanded ? shown.map { (partial ? (CuadraoCopy.text("copy.cuadraoHomeBalanceChart.56fbe2f22c", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoHomeBalanceChart.b19a96422a", spanish: spanish))) + dateLabel($0.date) } : selected.map { dateLabel($0.date) }) ?? (partial
                ? (CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.bbfd3e0f4b", spanish: spanish))
                : (CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.a3299351f5", spanish: spanish))))
                .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                .accessibilityIdentifier("home-chart-date")
            if expanded, let point = shown {
                Text(takeaway(point, period: reading.period)).font(CuadraoTypography.supporting)
                    .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("home-chart-takeaway")
            }
            if let controls { controls.padding(.vertical, 8) }
            if !points.isEmpty {
                periodCanvas(reading)
                HStack {
                    Text(dateLabel(expanded ? xDomain.lowerBound : points.first!.date))
                    Spacer()
                    if selectedDate != nil && !expanded {
                        Button(CuadraoCopy.text("copy.cuadraoChatPreview.ebdcdc2bda", spanish: spanish)) { selectedDate = nil }
                            .frame(minHeight: 44).accessibilityIdentifier("home-chart-today")
                    } else { Text(dateLabel(expanded ? xDomain.upperBound.addingTimeInterval(-1) : points.last!.date)) }
                }.font(CuadraoTypography.caption).foregroundStyle(.secondary)
            } else {
                CuadraoChartState(title: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.0d3f251ca9", spanish: spanish),
                    detail: shown == nil
                        ? (CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.efa154fffd", spanish: spanish))
                        : (CuadraoCopy.text("copy.cuadraoHomeBalanceChart.82a4465af1", spanish: spanish)))
                    .accessibilityIdentifier("home-chart-empty")
            }
            if expanded, let period = reading.period, period.closing != nil, !period.changes.isEmpty {
                CuadraoBalanceBreakdown(period: period, currency: currency, spanish: spanish)
            }
            if !expanded && availableRanges.count > 1 {
                HStack(spacing: 2) {
                    ForEach(availableRanges) { option in
                        Button {
                            compactRange = option; selectedDate = nil
                        } label: {
                            Text(option.title(spanish)).font(CuadraoTypography.caption)
                                .frame(maxWidth: .infinity, minHeight: 44)
                                .background(effectiveRange == option ? WelcomePalette.sage : .clear, in: Capsule())
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain).accessibilityIdentifier("home-range-" + option.rawValue)
                            .accessibilityAddTraits(effectiveRange == option ? .isSelected : [])
                    }
                }
            }
        }.onChange(of: range) { _, _ in selectedDate = nil }
            .onChange(of: periodOffset) { _, _ in selectedDate = nil }
            .onAppear { periodOffset = max(range.oldestOffset(history(.now)), min(0, periodOffset)) }
            .sensoryFeedback(.selection, trigger: selected?.date)
            .sensoryFeedback(.selection, trigger: periodOffset)
    }
    private func amountRow(_ shown: CanvasBalancePoint?) -> some View {
        CuadraoBalanceAmount(amount: shown.map { rules.format($0.balance, currency) } ?? "—",
            currency: currency, currencies: currencies, spanish: spanish, expanded: expanded, amountIdentifier: amountIdentifier,
            chooseCurrency: { selectedDate = nil; chooseCurrency($0) }, expand: expand)
    }
    private func periodCanvas(_ reading: Reading) -> some View {
        chart(reading).padding(expanded ? 14 : 0)
            .background {
                if expanded { RoundedRectangle(cornerRadius: 22).fill(WelcomePalette.surface.opacity(0.5)) }
            }
    }
    private var periodTitle: String {
        let interval = range.interval(offset: periodOffset)
        let format = Date.FormatStyle.dateTime.locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))
        switch range {
        case .month: return interval.start.formatted(format.month(.wide).year())
        case .year: return interval.start.formatted(format.year())
        case .week:
            let end = Calendar.current.date(byAdding: .day, value: -1, to: interval.end)!
            return dateLabel(interval.start) + " – " + dateLabel(end)
        }
    }
    private func takeaway(_ point: CanvasBalancePoint, period: CanvasBalancePeriod?) -> String {
        guard let baseline = period?.opening, baseline.date < point.date else {
            return CuadraoCopy.text("copy.cuadraoHomeBalanceChart.7e641861f4", spanish: spanish)
        }
        let change = point.balance - baseline.balance
        if change == 0 { return CuadraoCopy.text("copy.cuadraoHomeBalanceChart.ed7cd0a8e0", spanish: spanish, String(describing: dateLabel(baseline.date))) }
        let amount = currency + " " + rules.format(abs(change), currency)
        return change > 0 ? CuadraoCopy.text("copy.cuadraoHomeBalanceChart.f64698094d", spanish: spanish, String(describing: amount), String(describing: dateLabel(baseline.date)))
            : CuadraoCopy.text("copy.cuadraoHomeBalanceChart.003109c873", spanish: spanish, String(describing: amount), String(describing: dateLabel(baseline.date)))
    }
    private func chartBase(_ reading: Reading) -> some View {
        let points = reading.points, bounds = reading.bounds, xDomain = reading.xDomain
        let selected = reading.selected, shown = reading.shown
        return Chart {
            ForEach(points) { point in
                AreaMark(x: .value(CuadraoCopy.text("copy.cuadraoHomeBalanceChart.9e3d3b41ed", spanish: spanish), point.date), yStart: .value(CuadraoCopy.text("copy.cuadraoHomeBalanceChart.e2fe2c786e", spanish: spanish), bounds.lowerBound), yEnd: .value(CuadraoCopy.text("copy.cuadraoHomeBalanceChart.02e2073456", spanish: spanish), point.value))
                    .foregroundStyle(LinearGradient(colors: [WelcomePalette.pine.opacity(0.16), WelcomePalette.pine.opacity(0)], startPoint: .top, endPoint: .bottom))
                    .accessibilityHidden(true)
                LineMark(x: .value(CuadraoCopy.text("copy.connectedTransactionSheet.9e3d3b41ed", spanish: spanish), point.date), y: .value(CuadraoCopy.text("copy.cuadraoHomeBalanceChart.02e2073456", spanish: spanish), point.value))
                    .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round)).foregroundStyle(WelcomePalette.pine)
                    .accessibilityLabel(dateLabel(point.date)).accessibilityValue(currency + " " + rules.format(point.balance, currency))
            }
            if let point = shown {
                if selected != nil {
                    RuleMark(x: .value(CuadraoCopy.text("copy.cuadraoHomeBalanceChart.9e3d3b41ed", spanish: spanish), point.date)).lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 4]))
                        .foregroundStyle(WelcomePalette.ink.opacity(0.22)).accessibilityHidden(true)
                }
                PointMark(x: .value(CuadraoCopy.text("copy.cuadraoHomeBalanceChart.9e3d3b41ed", spanish: spanish), point.date), y: .value(CuadraoCopy.text("copy.cuadraoHomeBalanceChart.02e2073456", spanish: spanish), point.value))
                    .symbolSize(selected == nil ? 32 : 65).foregroundStyle(WelcomePalette.pine).accessibilityHidden(true)
            }
        }.chartYScale(domain: bounds)
            .chartXScale(domain: xDomain)
            .chartXAxis(.hidden)
            .chartYAxis {
                AxisMarks(position: .trailing, values: [bounds.lowerBound, bounds.upperBound]) { value in
                    AxisValueLabel {
                        if let amount = value.as(Double.self) {
                            Text(amount.formatted(.number.precision(.fractionLength(0)).locale(Locale(identifier: "en_US"))))
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .frame(height: expanded ? 270 : 125).accessibilityIdentifier("home-balance-chart")
            .accessibilityValue(periodTitle)
    }
    @ViewBuilder private func chart(_ reading: Reading) -> some View {
        if expanded {
            chartBase(reading)
            .chartOverlay { proxy in
                GeometryReader { geometry in
                    CuadraoChartTouchSurface { location in
                        guard let frame = proxy.plotFrame else { return }
                        let plot = geometry[frame]
                        selectedDate = proxy.value(atX: min(max(0, location.x - plot.minX), plot.width), as: Date.self)
                    }
                }
            }
        } else {
            chartBase(reading).chartXSelection(value: $selectedDate)
                .chartGesture { proxy in
                    LongPressGesture(minimumDuration: 0.2)
                        .sequenced(before: DragGesture(minimumDistance: 0))
                        .onChanged { value in
                            if case .second(true, let drag?) = value { proxy.selectXValue(at: drag.location.x) }
                        }
                        .simultaneously(with: SpatialTapGesture().onEnded { proxy.selectXValue(at: $0.location.x) })
                }
        }
    }
    private func dateLabel(_ date: Date) -> String {
        date.formatted(expanded
            ? .dateTime.day().month(.abbreviated).year().locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))
            : .dateTime.day().month(.abbreviated).locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish))))
    }
}
