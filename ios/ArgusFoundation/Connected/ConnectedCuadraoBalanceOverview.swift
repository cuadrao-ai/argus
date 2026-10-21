import SwiftUI
import ArgusSession

struct ConnectedCuadraoBalanceOverview: View {
    let home: FinancialHome
    let spanish: Bool
    var space = "Personal"
    @ObservedObject var loop: FinancialLoopModel
    let accounts: [FinancialAccount]
    @EnvironmentObject private var auth: ProfileAuthModel
    @State private var chosenCurrency: String?
    @State private var expanded = false
    @State private var history: ConnectedBalanceHistory.Reading?
    private var currencies: [FinancialCurrencySummary] {
        CurrencyPresentation.ordered(home.currencies, primary: auth.profile?.currency, currency: { $0.currency })
    }
    private var summary: FinancialCurrencySummary? {
        currencies.first { $0.currency == chosenCurrency } ?? currencies.first
    }
    private var timeZone: String { home.period?.timeZone ?? TimeZone.current.identifier }

    /// The reads restart when the hero, the listed accounts, the period or the day changes.
    private struct HistoryKey: Equatable {
        let summary: FinancialCurrencySummary
        let period: FinancialHomePeriod?
        let accounts: [UUID: Int]
        let day: Date
    }
    private func key(_ summary: FinancialCurrencySummary) -> HistoryKey {
        HistoryKey(summary: summary, period: home.period,
            accounts: Dictionary(uniqueKeysWithValues: accounts.filter { $0.currency == summary.currency }.map { ($0.id, $0.version) }),
            day: Calendar.current.startOfDay(for: .now))
    }

    var body: some View {
        if let summary {
            ConnectedBalanceReading(summary: summary, currencies: currencies.map(\.currency), spanish: spanish,
                history: history, chooseCurrency: { chosenCurrency = $0 }, expand: { expanded = true })
                .fullScreenCover(isPresented: $expanded) {
                    ConnectedCuadraoInsights(summary: summary, period: home.period, spanish: spanish, space: space,
                        timeZone: timeZone, history: history)
                }
                .task(id: key(summary)) { await load(summary) }
        }
    }

    /// Reads every known account of the currency through the bounded observation reader, one after another.
    /// A stale or cancelled read publishes nothing; the key change that caused it starts a fresh read.
    private func load(_ summary: FinancialCurrencySummary) async {
        history = nil
        var reads: [ConnectedBalanceHistory.AccountRead] = []
        if let period = home.period {
            for account in accounts where account.currency == summary.currency && account.balance.amountMinor != nil {
                let read = await loop.observations(accountID: account.id, period: period)
                reads.append(ConnectedBalanceHistory.AccountRead(account: account, read: read))
            }
        }
        guard !Task.isCancelled, let reading = ConnectedBalanceHistory.reading(summary: summary, reads: reads, now: .now) else { return }
        history = reading
    }
}

/// The approved balance chart over the hero and its recorded history; the hero stays readable while history loads.
private struct ConnectedBalanceReading: View {
    let summary: FinancialCurrencySummary
    let currencies: [String]
    let spanish: Bool
    var expanded = false
    let history: ConnectedBalanceHistory.Reading?
    var chooseCurrency: (String) -> Void = { _ in }
    var expand: () -> Void = {}
    var range: Binding<CanvasHistoryRange> = .constant(.month)
    var periodOffset: Binding<Int> = .constant(0)
    @Environment(\.locale) private var locale
    private var amountIdentifier: String { expanded ? "home-chart-amount" : "home.netWorth." + summary.currency }
    private var partial: Bool { summary.unknownAccounts > 0 }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            switch history {
            case .recorded(let points, let unavailableAccounts, let accounts)
                where Set(points.map { Calendar.current.startOfDay(for: $0.date) }).count > 1:
                CuadraoHomeBalanceChart(accounts: [], observations: [], currency: summary.currency, currencies: currencies,
                    spanish: spanish, shared: false, chooseCurrency: chooseCurrency, expanded: expanded, expand: expand,
                    history: CanvasBuiltBalanceHistory(points: points, now: .now), partial: partial,
                    amountIdentifier: amountIdentifier, range: range, periodOffset: periodOffset)
                if unavailableAccounts > 0 {
                    Text(unavailableHistory(unavailableAccounts))
                        .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                        .accessibilityIdentifier("home-chart-unavailable-history")
                }
                if expanded, !accounts.isEmpty {
                    let period = breakdown(points: points, accounts: accounts)
                    if period.closing != nil {
                        CuadraoBalanceBreakdown(period: period, currency: summary.currency, spanish: spanish, linksToAccounts: false, missingCoverage: true)
                    }
                }
            case .recorded:
                balanceOnly(chart: CuadraoChartState(title: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.ec3df4110c", spanish: spanish),
                    detail: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.32fe20d7d3", spanish: spanish))
                    .accessibilityIdentifier("home-chart-history-starts"))
            case .unknown, nil:
                if history == nil, ConnectedBalanceSummary(summary: summary).known {
                    balanceOnly(chart: CuadraoChartState(title: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.596f48e364", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.57179cea1b", spanish: spanish),
                        loading: true)
                        .accessibilityIdentifier("home-chart-loading"))
                } else {
                    balanceOnly(chart: CuadraoChartState(title: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.0d3f251ca9", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.efa154fffd", spanish: spanish))
                        .accessibilityIdentifier("home-chart-empty"))
                }
            }
            if partial {
                Text(verbatim: String(format: NSLocalizedString("loop.home.unknownCount", comment: ""), summary.unknownAccounts))
                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
        }
    }

    /// The hero amount over the approved cold-start art; used while the recorded history cannot yet draw a line.
    private func balanceOnly(chart: some View) -> some View {
        let value = ConnectedBalanceSummary(summary: summary)
        return VStack(alignment: .leading, spacing: 12) {
            CuadraoBalanceAmount(amount: value.balance(locale: locale) ?? "—", currency: summary.currency,
                currencies: currencies, spanish: spanish, expanded: expanded, amountIdentifier: amountIdentifier,
                chooseCurrency: chooseCurrency, expand: expand)
            Text(partial ? (CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.bbfd3e0f4b", spanish: spanish)) : (CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.a3299351f5", spanish: spanish)))
                .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                .accessibilityIdentifier("home-chart-date")
            chart
        }
    }

    /// The approved breakdown over the hero series: the period's opening and closing are its recorded days,
    /// each row an account's contribution on those days. Unknown-balance accounts stay counted, never listed.
    private func breakdown(points: [CanvasBalancePoint], accounts: [ConnectedBalanceHistory.AccountSeries]) -> CanvasBalancePeriod {
        let window = CanvasBalancePeriod(accounts: [], observations: [], range: range.wrappedValue,
            offset: periodOffset.wrappedValue, now: .now, history: points)
        let digits = summary.currencyFractionDigits
        func money(_ minor: Int64?) -> Decimal? { minor.map { ConnectedBalanceHistory.amount(Decimal($0), digits: digits) } }
        let rows = ConnectedBalanceHistory.changes(accounts, opening: window.opening?.date, closing: window.closing?.date).map { row in
            let account = CanvasAccount(id: row.account.id, name: ConnectedAccountPresentation.title(row.account, spanish: spanish),
                kind: ConnectedAccountPresentation.artwork(row.account.type) ?? .asset, currency: row.account.currency,
                balance: money(row.closing), archived: row.account.archived)
            return CanvasBalanceChange(account: account, opening: money(row.opening), closing: money(row.closing))
        }
        return CanvasBalancePeriod(interval: window.interval, opening: window.opening, closing: window.closing,
            closingAccounts: rows.map(\.account), changes: rows, isPartial: partial)
    }

    private func unavailableHistory(_ count: Int) -> String {
        return count == 1 ? CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.2c50f14e2a", spanish: spanish) : CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.7d72633328", spanish: spanish, String(describing: count))
    }
}

private struct ConnectedCuadraoInsights: View {
    let summary: FinancialCurrencySummary
    let period: FinancialHomePeriod?
    let spanish: Bool
    let space: String
    let timeZone: String
    let history: ConnectedBalanceHistory.Reading?
    @State private var range: CanvasHistoryRange = .month
    @State private var periodOffset = 0
    @State private var distribution = false
    @State private var activity = false
    @State private var selectedGroup: String?
    @Environment(\.locale) private var locale
    private var points: [CanvasBalancePoint] {
        if case .recorded(let points, _, _) = history { return points }
        return []
    }

    var body: some View {
        NavigationStack {
            CuadraoHomeInsightsLayout(spanish: spanish, range: $range, periodOffset: $periodOffset,
                distribution: $distribution, activity: $activity, distributionOnPastPeriods: false, oldestOffset: { showingActivity in
                    showingActivity ? 0 : range.oldestOffset(points)
                }) { offset in
                    if activity {
                        spending(range.interval(offset: offset))
                    } else if distribution && offset == 0 {
                        allocation
                    } else {
                        ConnectedBalanceReading(summary: summary, currencies: [summary.currency], spanish: spanish,
                            expanded: true, history: history, range: $range, periodOffset: .constant(offset))
                    }
                }.modifier(CuadraoHomeInsightsChrome(title: space, spanish: spanish))
                .onChange(of: periodOffset) { _, offset in if offset < 0 { distribution = false } }
        }.foregroundStyle(WelcomePalette.ink).tint(WelcomePalette.pine)
    }

    @ViewBuilder private func spending(_ page: DateInterval) -> some View {
        let value = ConnectedBalanceSummary(summary: summary)
        VStack(alignment: .leading, spacing: 20) {
            switch ConnectedSpendingPeriod.reading(summary: summary, period: period, page: page) {
            case .recorded(let minor):
                CuadraoSpendingReading(currency: summary.currency, amount: value.amount(minor, locale: locale),
                    caption: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.f5d8dd5e1a", spanish: spanish))
                CuadraoChartState(title: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.7718421512", spanish: spanish),
                    detail: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.11c6809730", spanish: spanish))
                    .accessibilityElement(children: .contain).accessibilityIdentifier("home-spending-chart")
            case .noData:
                CuadraoSpendingReading(currency: summary.currency, amount: CuadraoMissingCoverage.amount(spanish),
                    caption: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.f5d8dd5e1a", spanish: spanish))
                CuadraoChartState(title: CuadraoMissingCoverage.title(spanish), detail: CuadraoMissingCoverage.detail(spanish))
                    .accessibilityElement(children: .contain).accessibilityIdentifier("home-spending-chart")
            }
        }
    }

    private var allocation: some View {
        let value = ConnectedBalanceSummary(summary: summary)
        let groups = value.components.map { component in
            let fraction = value.fraction(component)
            return CuadraoDistributionGroup(id: component.rawValue,
                title: String(localized: String.LocalizationValue(component.titleKey), locale: locale),
                amount: value.amount(value.minor(component), locale: locale),
                percentage: fraction.formatted(.percent.precision(.fractionLength(1)).locale(locale)),
                fraction: fraction, color: component == .cash ? WelcomePalette.sunshine : WelcomePalette.overlap)
        }
        return CuadraoDistributionContent(currency: summary.currency, spanish: spanish,
            balanceTitle: balanceTitle, balance: value.balance(locale: locale) ?? "—",
            partial: summary.unknownAccounts > 0, assets: value.amount(summary.assetsMinor, locale: locale),
            groups: groups, deductions: value.deductions.map { value.amount($0, locale: locale) },
            selectedGroup: $selectedGroup) { _ in EmptyView() } deductionRows: { EmptyView() }
    }

    private var balanceTitle: String {
        let title = CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.012458b538", spanish: spanish)
        guard let asOf = summary.asOf else { return title }
        return title + " · " + AccountPresentation.date(asOf, zone: timeZone, locale: locale)
    }
}
