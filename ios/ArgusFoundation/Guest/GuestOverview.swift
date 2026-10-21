import SwiftUI
import CuadraoBook

/// Home's overview: one currency at a time, the net balance and its daily history, drawn by the shared chart from points
/// the book derived. Unknown balances stay out of the total and are counted beside it.
struct GuestOverview: View {
    @ObservedObject var model: GuestBookModel
    let spanish: Bool
    @State private var chosen: String?
    @State private var expanded = false
    @Environment(\.locale) private var locale

    private var currencies: [String] { model.book.currencies }
    private var currency: String? { currencies.first { $0 == chosen } ?? currencies.first }

    var body: some View {
        if let currency, let net = model.book.netBalance(currency: currency) {
            GuestBalanceReading(book: model.book, net: net, currencies: currencies, spanish: spanish,
                                chooseCurrency: { chosen = $0 }, expand: { expanded = true })
                .fullScreenCover(isPresented: $expanded) {
                    GuestInsights(model: model, currency: currency, spanish: spanish)
                }
        }
    }
}

struct GuestBalanceReading: View {
    let book: DeviceBook
    let net: NetBalance
    let currencies: [String]
    let spanish: Bool
    var expanded = false
    var range: Binding<CanvasHistoryRange> = .constant(.month)
    var periodOffset: Binding<Int> = .constant(0)
    var chooseCurrency: (String) -> Void = { _ in }
    var expand: () -> Void = {}
    @Environment(\.locale) private var locale

    private var points: [CanvasBalancePoint] {
        (book.dailyBalances(currency: net.currency, zone: .current, now: .now) ?? []).map {
            CanvasBalancePoint(date: $0.day, balance: MinorUnits.decimal($0.minor, digits: net.digits))
        }
    }

    private var amountIdentifier: String { expanded ? "home-chart-amount" : "guest.netBalance." + net.currency }

    private var amountText: String {
        net.minor.map { MoneyFormatter.grouped($0, digits: net.digits, grouping: locale.groupingSeparator ?? ",",
                                                decimal: locale.decimalSeparator ?? ".") } ?? ""
    }

    var body: some View {
        let points = points
        VStack(alignment: .leading, spacing: 12) {
            if Set(points.map { Calendar.current.startOfDay(for: $0.date) }).count > 1 {
                CuadraoHomeBalanceChart(accounts: [], observations: [], currency: net.currency, currencies: currencies,
                    spanish: spanish, shared: false, chooseCurrency: chooseCurrency, expanded: expanded, expand: expand,
                    history: CanvasBuiltBalanceHistory(points: points, now: .now), partial: net.isPartial,
                    amountIdentifier: amountIdentifier, range: range, periodOffset: periodOffset)
            } else if net.knownAccounts > 0 {
                VStack(alignment: .leading, spacing: 12) {
                    CuadraoBalanceAmount(amount: amountText, currency: net.currency, currencies: currencies, spanish: spanish,
                        expanded: expanded, amountIdentifier: amountIdentifier, chooseCurrency: chooseCurrency, expand: expand)
                    Text(net.isPartial ? (CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.bbfd3e0f4b", spanish: spanish)) : (CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.a3299351f5", spanish: spanish)))
                        .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                    CuadraoChartState(title: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.ec3df4110c", spanish: spanish),
                        detail: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.32fe20d7d3", spanish: spanish))
                        .accessibilityElement(children: .contain).accessibilityIdentifier("guest.chart.starts")
                }
            } else {
                CuadraoChartState(title: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.0d3f251ca9", spanish: spanish),
                    detail: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.efa154fffd", spanish: spanish))
                    .accessibilityElement(children: .contain).accessibilityIdentifier("guest.chart.empty")
            }
            if net.isPartial {
                Text(unknown(net.unknownAccounts)).font(CuadraoTypography.caption).foregroundStyle(.secondary)
                    .accessibilityIdentifier("guest.chart.unknown")
            }
        }
    }

    private func unknown(_ count: Int) -> String {
        return count == 1 ? CuadraoCopy.text("copy.guestOverview.7b5763e333", spanish: spanish) : CuadraoCopy.text("copy.guestOverview.e24bb788c0", spanish: spanish, String(describing: count))
    }
}

/// The full-screen look at one currency: the balance over a month at a time, and what was spent in it. Spending never
/// claims a month it has no coverage for.
struct GuestInsights: View {
    @ObservedObject var model: GuestBookModel
    let currency: String
    let spanish: Bool
    @State private var offset = 0
    @Environment(\.dismiss) private var dismiss
    @Environment(\.locale) private var locale

    private var calendar: Calendar { Calendar.current }

    private var month: DateInterval {
        let start = calendar.date(from: calendar.dateComponents([.year, .month], from: .now)) ?? .now
        let first = calendar.date(byAdding: .month, value: offset, to: start) ?? start
        let end = calendar.date(byAdding: .month, value: 1, to: first) ?? first
        return DateInterval(start: first, end: end)
    }

    /// The oldest month with anything to show, so paging back stops where the history does.
    private var oldest: Int {
        let first = [model.book.accounts.filter { $0.currency == currency }.compactMap { $0.opening?.asOf }.min(),
                     model.book.movements.map(\.occurredAt).min()].compactMap { $0 }.min() ?? .now
        let from = calendar.dateComponents([.year, .month], from: first)
        let to = calendar.dateComponents([.year, .month], from: .now)
        return min(0, ((from.year ?? 0) - (to.year ?? 0)) * 12 + ((from.month ?? 0) - (to.month ?? 0)))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    HStack {
                        Button { offset = max(oldest, offset - 1) } label: { Image(systemName: "chevron.left").frame(width: 44, height: 44) }
                            .disabled(offset <= oldest).accessibilityLabel(CuadraoCopy.text("copy.guestOverview.3a75da6980", spanish: spanish))
                            .accessibilityIdentifier("guest.insights.previous")
                        Spacer()
                        Text(month.start.formatted(.dateTime.month(.wide).year().locale(locale))).font(CuadraoTypography.feature)
                            .accessibilityIdentifier("guest.insights.month")
                        Spacer()
                        Button { offset = min(0, offset + 1) } label: { Image(systemName: "chevron.right").frame(width: 44, height: 44) }
                            .disabled(offset >= 0).accessibilityLabel(CuadraoCopy.text("copy.guestOverview.4cc2c3734f", spanish: spanish))
                            .accessibilityIdentifier("guest.insights.next")
                    }
                    if let net = model.book.netBalance(currency: currency) {
                        GuestBalanceReading(book: model.book, net: net, currencies: [currency], spanish: spanish, expanded: true,
                                            range: .constant(.month), periodOffset: .constant(offset))
                    }
                    GuestSpending(book: model.book, currency: currency, interval: month, spanish: spanish)
                    GuestTotals(book: model.book, currency: currency, spanish: spanish)
                }.padding(24)
            }
            .accessibilityIdentifier("guest.insights")
            .background(WelcomePalette.background)
            .navigationTitle(CuadraoCopy.text("copy.guestAccountSheet.736ea2040f", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
            .toolbar { CuadraoDoneToolbar(title: CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish)) { dismiss() } }
        }.tint(WelcomePalette.pine).foregroundStyle(WelcomePalette.ink)
    }
}

struct GuestSpending: View {
    let book: DeviceBook
    let currency: String
    let interval: DateInterval
    let spanish: Bool
    @Environment(\.locale) private var locale

    private func text(_ minor: Int64, digits: Int) -> String {
        MoneyFormatter.grouped(minor, digits: digits, grouping: locale.groupingSeparator ?? ",", decimal: locale.decimalSeparator ?? ".")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            switch book.spending(currency: currency, in: interval) {
            case .recorded(let summary)?:
                CuadraoSpendingReading(currency: currency, amount: text(summary.totalMinor, digits: summary.digits),
                                       caption: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.f5d8dd5e1a", spanish: spanish))
                if let start = summary.coverageStart {
                    Text((CuadraoCopy.text("copy.guestOverview.45cb671575", spanish: spanish)) + start.formatted(.dateTime.day().month(.wide).locale(locale))
                         + (CuadraoCopy.text("copy.guestOverview.c4c4420fb3", spanish: spanish)))
                        .font(CuadraoTypography.caption).foregroundStyle(.secondary).accessibilityIdentifier("guest.spending.coverage")
                }
                if summary.byCategory.isEmpty {
                    Text(CuadraoCopy.text("copy.guestOverview.41e109f55e", spanish: spanish))
                        .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("guest.spending.none")
                }
                VStack(spacing: 14) {
                    ForEach(summary.byCategory, id: \.category) { row in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(GuestMovementPresentation.categoryTitle(row.category, spanish: spanish))
                                Spacer()
                                Text(text(row.minor, digits: summary.digits)).font(CuadraoTypography.rowAmount)
                            }
                            GeometryReader { proxy in
                                Capsule().fill(GuestMovementPresentation.categoryColor(row.category))
                                    .frame(width: proxy.size.width * share(row.minor, of: summary.totalMinor))
                            }.frame(height: 6).accessibilityHidden(true)
                        }.accessibilityElement(children: .combine)
                            .accessibilityIdentifier("guest.spending.category." + row.category.rawValue)
                    }
                }
            case .noData?, nil:
                CuadraoSpendingReading(currency: currency, amount: CuadraoMissingCoverage.amount(spanish),
                                       caption: CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.f5d8dd5e1a", spanish: spanish))
                CuadraoChartState(title: CuadraoMissingCoverage.title(spanish), detail: CuadraoMissingCoverage.detail(spanish))
                    .accessibilityElement(children: .contain).accessibilityIdentifier("guest.spending.noData")
            }
        }.accessibilityElement(children: .contain).accessibilityIdentifier("guest.spending")
    }

    /// A bar's share of the month, as a fraction of its width. Presentation only; no amount is derived from it.
    private func share(_ part: Int64, of whole: Int64) -> CGFloat {
        guard whole > 0 else { return 0 }
        return CGFloat(NSDecimalNumber(decimal: MinorUnits.decimal(part, digits: 0) / MinorUnits.decimal(whole, digits: 0)).doubleValue)
    }
}

/// The currency's accounts added up: what is held, what is owed, and what is left. Shares are applied; unknown balances are
/// counted beside the totals, never guessed.
struct GuestTotals: View {
    let book: DeviceBook
    let currency: String
    let spanish: Bool
    @Environment(\.locale) private var locale

    private func text(_ minor: Int64, _ digits: Int) -> String {
        MoneyFormatter.grouped(minor, digits: digits, grouping: locale.groupingSeparator ?? ",", decimal: locale.decimalSeparator ?? ".")
    }

    var body: some View {
        if let totals = book.totals(currency: currency) {
            VStack(alignment: .leading, spacing: 12) {
                Text(CuadraoCopy.text("copy.guestOverview.74597825aa", spanish: spanish, String(describing: currency))).font(CuadraoTypography.section)
                    .accessibilityAddTraits(.isHeader)
                row(CuadraoCopy.text("copy.guestOverview.d203e8be71", spanish: spanish), text(totals.assetsMinor, totals.digits), "guest.totals.assets")
                row(CuadraoCopy.text("copy.guestOverview.3d759411af", spanish: spanish), text(totals.owedMinor, totals.digits), "guest.totals.owed")
                row(CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.a3299351f5", spanish: spanish), text(totals.netMinor, totals.digits), "guest.totals.net", strong: true)
                if totals.unknownAccounts > 0 {
                    Text(CuadraoCopy.text("copy.guestOverview.8c5a9c5058", spanish: spanish, String(describing: totals.unknownAccounts)))
                        .font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("guest.totals.unknown")
                }
            }.accessibilityElement(children: .contain).accessibilityIdentifier("guest.totals")
        }
    }

    private func row(_ title: String, _ value: String, _ identifier: String, strong: Bool = false) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(strong ? .body.weight(.semibold) : .body)
            Spacer(minLength: 12)
            Text(value).font(CuadraoTypography.rowAmount).monospacedDigit().accessibilityIdentifier(identifier)
        }.padding(.vertical, 4)
    }
}
