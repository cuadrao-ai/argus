import SwiftUI

/// Every percentage uses the same positive-assets total, including account rows.
struct CuadraoHomeDistribution: View {
    let accounts: [CanvasAccount]
    let currency: String
    let spanish: Bool
    var controls: CuadraoInsightControls?
    var historical = false
    var asOf: Date?
    var context: CanvasChartFocus?
    @State private var selectedKind: CanvasAccountKind?
    private var known: [CanvasAccount] { accounts.filter { $0.balance != nil } }
    private func value(_ account: CanvasAccount) -> Decimal {
        CanvasBalanceHistory.contribution(account.balance ?? 0, account: account)
    }
    private var positive: [CanvasAccount] { known.filter { value($0) > 0 } }
    private var deductions: [CanvasAccount] { known.filter { value($0) < 0 } }
    private var total: Decimal { amount(positive) }
    private var kinds: [CanvasAccountKind] { CanvasAccountKind.allCases.filter { kind in positive.contains { $0.kind == kind } } }
    private var palette: [Color] { [WelcomePalette.sunshine, WelcomePalette.pine, WelcomePalette.clay, WelcomePalette.overlap, WelcomePalette.bloom, WelcomePalette.sage, WelcomePalette.clay.opacity(0.7), WelcomePalette.pine.opacity(0.65), WelcomePalette.ink.opacity(0.5)] }
    private func color(_ kind: CanvasAccountKind) -> Color { palette[CanvasAccountKind.allCases.firstIndex(of: kind)!] }
    private func rows(_ kind: CanvasAccountKind) -> [CanvasAccount] { positive.filter { $0.kind == kind } }
    private func amount(_ rows: [CanvasAccount]) -> Decimal { rows.reduce(0) { $0 + value($1) } }
    private func fraction(_ amount: Decimal) -> Double { total > 0 ? NSDecimalNumber(decimal: amount / total).doubleValue : 0 }
    private func percent(_ amount: Decimal) -> String {
        fraction(amount).formatted(.percent.precision(.fractionLength(1)).locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish))))
    }
    private var balanceTitle: String {
        asOf.map { (CuadraoCopy.text("copy.cuadraoHomeBalanceChart.b19a96422a", spanish: spanish))
            + $0.formatted(.dateTime.day().month(.abbreviated).year().locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish)))) }
            ?? (historical ? (CuadraoCopy.text("copy.cuadraoHomeDistribution.4bfec87b7d", spanish: spanish))
                : (CuadraoCopy.text("copy.cuadraoHomeDistribution.7934df8746", spanish: spanish)))
    }
    private var groups: [CuadraoDistributionGroup] {
        kinds.map { kind in
            CuadraoDistributionGroup(id: kind.rawValue, title: kind.title(spanish),
                amount: CanvasMoney.format(amount(rows(kind)), currency: currency),
                percentage: percent(amount(rows(kind))), fraction: fraction(amount(rows(kind))),
                color: color(kind), accountCount: rows(kind).count)
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            CuadraoDistributionContent(currency: currency, spanish: spanish, balanceTitle: balanceTitle,
                balance: known.isEmpty ? "—" : CanvasMoney.format(total + amount(deductions), currency: currency),
                partial: accounts.count != known.count, assets: CanvasMoney.format(total, currency: currency),
                groups: groups, deductions: deductions.isEmpty ? nil : CanvasMoney.format(-amount(deductions), currency: currency),
                hasDeductionRows: !deductions.isEmpty, controls: controls,
                selectedGroup: Binding(get: { selectedKind?.rawValue }, set: { selectedKind = $0.flatMap(CanvasAccountKind.init(rawValue:)) })) { id in
                    if let kind = CanvasAccountKind(rawValue: id) {
                        ForEach(rows(kind)) { account in accountRow(account, showPercent: true) }
                    }
                } deductionRows: {
                    ForEach(deductions) { account in accountRow(account, showPercent: false) }
                }
            if let context { CanvasChartAsk(context: selectedContext(context), spanish: spanish) }
        }
    }
    private func selectedContext(_ context: CanvasChartFocus) -> CanvasChartFocus {
        var selected = context
        selected.selection = selectedKind.map { .accountKind(id: $0.rawValue, title: $0.title(spanish)) }
        return selected
    }
    private func accountRow(_ account: CanvasAccount, showPercent: Bool) -> some View {
        NavigationLink(value: account.id) {
            HStack(alignment: .firstTextBaseline) {
                Text(account.displayName(spanish)).font(CuadraoTypography.supporting)
                Spacer(minLength: 12)
                VStack(alignment: .trailing, spacing: 5) {
                    if showPercent { Text(percent(value(account))).font(CuadraoTypography.rowAmount) }
                    Text(CanvasMoney.format(value(account), currency: currency)).font(CuadraoTypography.rowAmount).foregroundStyle(.secondary)
                }
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
            }.padding(.vertical, 15).padding(.leading, 12).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier("home-distribution-account-" + account.id.uuidString)
    }

}
