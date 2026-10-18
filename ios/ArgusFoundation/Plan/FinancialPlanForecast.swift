import SwiftUI
import ArgusSession

struct FinancialPlanForecast<Details: View>: View {
    let projection: FinancialPlanProjection
    var primaryCurrency: String? = nil
    let chooseAccounts: () -> Void
    var canChooseAccounts = true
    var bottomSpace: CGFloat = 90
    @ViewBuilder let details: (FinancialForecastCurrency?) -> Details
    @State private var selectedCurrency: String?
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    private var currency: FinancialForecastCurrency? {
        let code = CurrencyPresentation.selectedCode(available: projection.currencies.map(\.currency),
            explicit: selectedCurrency, primary: primaryCurrency)
        return projection.currencies.first { $0.currency == code }
    }
    private var start: ConnectedForecastStart? { .reading(projection.currencies, hasAccounts: !projection.accounts.isEmpty) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            CuadraoPlanForecastSection(period: CuadraoCopy.text("copy.financialPlanForecast.dd3f66acc1", spanish: spanish)) {
                if projection.currencies.count > 1 {
                    Menu {
                        ForEach(projection.currencies) { option in
                            Button { selectedCurrency = option.currency } label: {
                                if currency?.currency == option.currency {
                                    Label(option.currency, systemImage: "checkmark")
                                } else { Text(option.currency) }
                            }
                        }
                    } label: {
                        CuadraoChoiceLabel(title: currency?.currency ?? NSLocalizedString("accounts.currency", comment: ""))
                    }
                        .accessibilityIdentifier("plan.forecast.currency")
                } else {
                    CuadraoChoiceLabel(title: currency?.currency ?? NSLocalizedString("context.personal", comment: ""), selectable: false)
                }
            } content: {
                if let start {
                    coldStart(start)
                } else if let currency {
                    FinancialPlanForecastCurrency(currency: currency, start: projection.startDate, end: projection.endDate)
                        .id(currency.currency)
                        .id(projection.selection.accountIds)
                        .id(projection.selection.timeZone)
                        .id(currency.accountIds)
                    Text(CuadraoCopy.text("copy.financialPlanForecast.f864256f44", spanish: spanish))
                        .font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("plan.coverage")
                } else {
                    Text(CuadraoCopy.text("copy.financialPlanForecast.0851f51522", spanish: spanish))
                        .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                        .accessibilityIdentifier("plan.forecast.chooseCurrency")
                }
            } explore: {
                #if DEBUG
                CuadraoPlanExploreLink(spanish: spanish, example: true) {
                    FinancialPlanScenarioExample(spanish: spanish, bottomSpace: bottomSpace)
                }
                #endif
            }
            if start != .noAccounts { behind }
        }
        .onChange(of: projection.currencies.map(\.currency)) { _, available in
            if let selectedCurrency, !available.contains(selectedCurrency) { self.selectedCurrency = nil }
        }
    }

    private func coldStart(_ start: ConnectedForecastStart) -> some View {
        CuadraoPlanColdStart(spanish: spanish, detail: coldStartDetail(start)) {
            if start != .noAccounts {
                Button("plan.chooseMoney", action: chooseAccounts).disabled(!canChooseAccounts)
                    .accessibilityIdentifier("plan.chooseAccounts")
            }
        }
    }

    private func coldStartDetail(_ start: ConnectedForecastStart) -> String {
        switch start {
        case .noAccounts:
            CuadraoCopy.text("copy.financialPlanForecast.aed83b432e", spanish: spanish)
        case .noAccountsIncluded:
            CuadraoCopy.text("copy.financialPlanForecast.8dc744f1e1", spanish: spanish)
        case .noKnownBalance:
            CuadraoCopy.text("copy.financialPlanForecast.cc14aa9fc3", spanish: spanish)
        }
    }

    private var behind: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 16) {
                if let currency {
                    PlanValueRow(title: "plan.income", value: amount(currency.expectedIncomeMinor, in: currency))
                    PlanValueRow(title: "plan.bills", value: amount(currency.expectedBillsMinor, in: currency))
                    if let effect = currency.transferEffectMinor {
                        PlanValueRow(title: "goal.transferEffect", value: amount(effect, in: currency))
                    }
                    PlanValueRow(title: "plan.netChange", value: amount(currency.netCashChangeMinor, in: currency))
                    if let asOf = currency.asOf {
                        Text(NSLocalizedString("plan.asOf", comment: "") + " " + AccountPresentation.date(asOf, zone: projection.selection.timeZone, locale: locale))
                            .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                    }
                }
                details(currency)
                Text("plan.assumptions").font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }.padding(.top, 16)
        } label: {
            Text(CuadraoCopy.text("copy.cuadraoForecastPlayground.d71bd096f1", spanish: spanish)).font(.subheadline.weight(.medium))
                .accessibilityIdentifier("plan.forecast.details")
        }.padding(.top, 8)
    }
    private func amount(_ minor: String, in currency: FinancialForecastCurrency) -> String {
        PlanPresentation.money(minor, currency: currency.currency, digits: currency.currencyFractionDigits, locale: locale)
    }
}

#if DEBUG
private struct FinancialPlanScenarioExample: View {
    let spanish: Bool
    let bottomSpace: CGFloat
    @State private var example: CuadraoPlanPreview

    init(spanish: Bool, bottomSpace: CGFloat) {
        self.spanish = spanish; self.bottomSpace = bottomSpace
        _example = State(initialValue: CuadraoPlanPreview(spanish: spanish, defaults: nil, reset: true))
    }

    var body: some View {
        CuadraoForecastPlayground(store: example, scope: CanvasSpace.personalID,
            scopeName: CuadraoCopy.text("copy.financialPlanForecast.43d5c155ac", spanish: spanish), spanish: spanish,
            bottomSpace: bottomSpace, isolatedExample: true)
    }
}
#endif

private struct FinancialPlanForecastCurrency: View {
    let currency: FinancialForecastCurrency
    let start: String
    let end: String
    @State private var selected: Int?
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    private var series: ConnectedForecastSeries { .reading(currency, end: end) }
    private var selectedPoint: ConnectedForecastSeries.Point? {
        guard let selected, case .series(let points, _) = series, points.indices.contains(selected) else { return nil }
        return points[selected]
    }
    private var displayedMinor: String? {
        if let selectedPoint { return selectedPoint.balanceMinor }
        return currency.endingMinor
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            CuadraoPlanForecastValue(
                title: selectedPoint.map { PlanPresentation.dateLabel($0.date, locale: locale) + " · " + NSLocalizedString("plan.projectedBalance", comment: "") } ?? NSLocalizedString("plan.projectedBalance", comment: ""),
                amount: displayedMinor.map(amount) ?? currency.currency + " · " + NSLocalizedString("accounts.unknown", comment: ""),
                identifier: (displayedMinor == nil ? "plan.unknown." : "plan.projected.") + currency.currency)
            if !currency.unknownAccountIds.isEmpty {
                if currency.accountIds.contains(where: { !currency.unknownAccountIds.contains($0) }) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(CuadraoCopy.text("copy.financialPlanForecast.79b26bb53f", spanish: CuadraoCopy.isSpanish()))
                        Text(amount(currency.knownStartingMinor)).monospacedDigit()
                            .accessibilityIdentifier("plan.knownStarting." + currency.currency)
                    }.font(CuadraoTypography.supporting)
                }
                Text("\(currency.unknownAccountIds.count) · " + NSLocalizedString("accounts.unknown", comment: ""))
                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
            if case .series(let points, let scheduled) = series {
                FinancialForecastChart(currency: currency, points: points, start: start, end: end, selected: $selected)
                if !scheduled {
                    Text(CuadraoCopy.text("copy.financialPlanForecast.ba54768f5e", spanish: spanish))
                        .font(CuadraoTypography.caption).foregroundStyle(.secondary).accessibilityIdentifier("plan.forecast.flat")
                }
            } else {
                Text(PlanPresentation.dateLabel(start, locale: locale) + " · " + PlanPresentation.dateLabel(end, locale: locale))
                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                CuadraoChartState(title: NSLocalizedString("accounts.unknown", comment: ""),
                    detail: NSLocalizedString("plan.unknown", comment: ""))
            }
            if let shortfall = currency.firstShortfallDate {
                Label { Text("plan.shortfall") + Text(verbatim: " · " + PlanPresentation.dateLabel(shortfall, locale: locale)) }
                    icon: { Image(systemName: "exclamationmark.circle") }
                    .font(CuadraoTypography.supporting).accessibilityIdentifier("plan.shortfall." + currency.currency)
            }
        }
        .onChange(of: start) { _, _ in selected = nil }
        .onChange(of: end) { _, _ in selected = nil }
        .onChange(of: currency.points.map { $0.date + ":" + ($0.balanceMinor ?? "unknown") }) { _, _ in selected = nil }
    }
    private func amount(_ minor: String) -> String {
        PlanPresentation.money(minor, currency: currency.currency, digits: currency.currencyFractionDigits, locale: locale)
    }
}

struct FinancialForecastChart: View {
    let currency: FinancialForecastCurrency
    let points: [ConnectedForecastSeries.Point]
    let start: String
    let end: String
    @Binding var selected: Int?
    @Environment(\.locale) private var locale
    private var marks: [CuadraoPlanChartPoint] {
        points.enumerated().compactMap { index, point in
            guard let value = Double(point.balanceMinor) else { return nil }
            return .init(id: index, position: PlanPresentation.date(point.date).timeIntervalSince1970, balance: value)
        }
    }
    private var yRange: ClosedRange<Double> {
        let values = marks.map(\.balance)
        let low = values.min() ?? 0, high = values.max() ?? 0
        let padding = max((high - low) * 0.1, max(abs(low), abs(high)) * 0.02, 1)
        return (low - padding)...(high + padding)
    }
    private var xRange: ClosedRange<Double> {
        let first = PlanPresentation.date(start).timeIntervalSince1970
        let last = PlanPresentation.date(end).timeIntervalSince1970
        return first == last ? (first - 43200)...(last + 43200) : first...last
    }
    private var ticks: [CuadraoPlanChartTick] {
        Array(Set([start, end])).sorted().map {
            .init(position: PlanPresentation.date($0).timeIntervalSince1970, title: PlanPresentation.dateLabel($0, locale: locale))
        }
    }
    private var readout: String? {
        guard let selected, points.indices.contains(selected) else { return nil }
        return PlanPresentation.dateLabel(points[selected].date, locale: locale) + " · " +
            PlanPresentation.money(points[selected].balanceMinor, currency: currency.currency, digits: currency.currencyFractionDigits, locale: locale)
    }

    var body: some View {
        CuadraoPlanForecastChart(spanish: CuadraoCopy.isSpanish(), recorded: [], projected: marks, xRange: xRange, yRange: yRange,
            ticks: ticks, selected: marks.first { $0.id == selected },
            selection: Binding(get: { marks.first { $0.id == selected }?.position }, set: { position in
                selected = position.flatMap { value in marks.reversed().min { abs($0.position - value) < abs($1.position - value) }?.id }
            }), compact: true, stepped: true, identifier: "plan.chart",
            accessibilityTitle: NSLocalizedString("plan.chart.title", comment: ""),
            accessibilityAmount: readout ?? currency.endingMinor.map { PlanPresentation.money($0, currency: currency.currency, digits: currency.currencyFractionDigits, locale: locale) } ?? "")
            .accessibilityHint(Text("plan.chart.accessibility"))
            .accessibilityAdjustableAction { direction in
                switch direction {
                case .increment: selected = min((selected ?? 0) + 1, max(0, points.count - 1))
                case .decrement: selected = max((selected ?? 0) - 1, 0)
                @unknown default: break
                }
            }
    }
}
