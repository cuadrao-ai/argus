import SwiftUI

struct CuadraoHomeInsights: View {
    let data: CuadraoAccountsPreview
    private var accounts: [CanvasAccount] { data.active.filter { $0.currency == currency } }
    let currency: String
    let spanish: Bool
    let space: String
    let shared: Bool
    @State private var range: CanvasHistoryRange = .month
    @State private var periodOffset = 0
    @State private var distribution = false
    @State private var activity = false
    @State private var accountPath: [UUID] = []
    @State private var accountSheet: CanvasAccountSheet?
    @State private var chooseRecordingAccount = false
    private var expenses: [CanvasActivity] {
        CanvasSpendingHistory.expenses(data.visibleActivity, accounts: data.scopedAccounts, currency: currency)
    }
    private var history: [CanvasBalancePoint] { CanvasBalanceHistory.points(accounts: accounts, observations: data.balanceObservations, now: .now) }
    private func balancePeriod(_ offset: Int, built: CanvasBuiltBalanceHistory?) -> CanvasBalancePeriod {
        let now = Date.now
        guard let history = built?.points(on: now) else {
            return CanvasBalancePeriod(accounts: accounts, observations: data.balanceObservations, range: range, offset: offset, now: now)
        }
        return CanvasBalancePeriod(accounts: accounts, observations: data.balanceObservations, range: range, offset: offset, now: now, history: history)
    }
    private func recordFirstExpense() {
        if accounts.count == 1, let account = accounts.first { accountSheet = .record(account.id) }
        else { chooseRecordingAccount = true }
    }
    private func chartContext(_ offset: Int) -> CanvasChartFocus {
        CanvasChartFocus(spaceID: data.selectedSpaceID, spaceTitle: space, currency: currency,
            interval: range.interval(offset: offset), periodTitle: range.periodLabel(spanish: spanish, offset: offset),
            metric: activity ? .activity : .balance, presentation: distribution ? .distribution : .evolution)
    }
    @ViewBuilder private func periodContent(_ offset: Int, built: CanvasBuiltBalanceHistory?) -> some View {
        if activity {
            CuadraoSpendingChart(expenses: expenses, coverageStart: data.spendingCoverageStart(currency: currency), currency: currency,
                spanish: spanish, distribution: distribution, range: range, periodOffset: .constant(offset), record: accounts.isEmpty ? nil : recordFirstExpense, context: chartContext(offset))
        } else if distribution {
            let period = balancePeriod(offset, built: built)
            CuadraoHomeDistribution(accounts: period.closingAccounts, currency: currency, spanish: spanish, historical: offset < 0,
                asOf: period.closing?.date, context: chartContext(offset))
        } else {
            CuadraoHomeBalanceChart(accounts: accounts, observations: data.balanceObservations, currency: currency,
                currencies: [currency], spanish: spanish, shared: shared, chooseCurrency: { _ in }, expanded: true,
                history: built, range: $range, periodOffset: .constant(offset))
            CanvasChartAsk(context: chartContext(offset), spanish: spanish)
        }
    }
    var body: some View {
        // One history per pass feeds the page range, every live page and its period.
        let built = activity ? nil : CanvasBuiltBalanceHistory(accounts: accounts, observations: data.balanceObservations, now: .now)
        NavigationStack(path: $accountPath) {
            CuadraoHomeInsightsLayout(spanish: spanish, range: $range, periodOffset: $periodOffset,
                distribution: $distribution, activity: $activity, oldestOffset: { showingActivity in
                    showingActivity ? CanvasSpendingHistory.oldestOffset(expenses, range: range)
                        : range.oldestOffset(built?.points ?? history)
                }) { offset in
                    periodContent(offset, built: built)
                }
                .modifier(CuadraoHomeInsightsChrome(title: space, spanish: spanish))
                .navigationDestination(for: UUID.self) { id in
                    CuadraoAccountCanvas(data: data, accountID: id, spanish: spanish,
                        actions: { accountSheet = $0 }, record: { accountSheet = .record($0) })
                }
        }.confirmationDialog(CuadraoCopy.text("copy.cuadraoHomeInsights.483c453a6a", spanish: spanish), isPresented: $chooseRecordingAccount, titleVisibility: .visible) {
            ForEach(accounts) { account in
                Button(account.displayName(spanish)) { accountSheet = .record(account.id) }
            }
        }.sheet(item: $accountSheet) { selection in
            CuadraoAccountModal(data: data, selection: selection, spanish: spanish,
                show: { accountSheet = $0 }, archived: { _ in
                    accountSheet = nil; accountPath = []
                })
        }.tint(WelcomePalette.pine).foregroundStyle(WelcomePalette.ink)
    }
}
