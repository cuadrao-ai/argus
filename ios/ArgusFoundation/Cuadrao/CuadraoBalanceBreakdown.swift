import SwiftUI

struct CuadraoBalanceBreakdown: View {
    let period: CanvasBalancePeriod
    let currency: String
    let spanish: Bool
    /// Rows push the account only where the host stack has an account destination.
    var linksToAccounts = true
    /// Connected data has periods with no recorded opening; the Preview's fixtures never do.
    var missingCoverage = false
    @Environment(\.dynamicTypeSize) private var typeSize
    private func money(_ value: Decimal) -> String { CanvasMoney.format(value, currency: currency) }
    private func signed(_ value: Decimal) -> String { (value > 0 ? "+" : "") + money(value) }
    private func date(_ value: Date) -> String {
        value.formatted(.dateTime.day().month(.abbreviated).year().locale(Locale(identifier: CuadraoCopy.text("copy.receiptJourneySheet.57139f7c9f", spanish: spanish))))
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text(period.change == nil ? (CuadraoCopy.text("copy.cuadraoBalanceBreakdown.81d154c4ef", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoBalanceBreakdown.ab384258cf", spanish: spanish)))
                .font(CuadraoTypography.section).accessibilityAddTraits(.isHeader)
            if let opening = period.opening, let closing = period.closing {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 20) {
                        snapshot(opening, title: CuadraoCopy.text("copy.cuadraoBalanceBreakdown.33e2af4e9c", spanish: spanish))
                        Image(systemName: "arrow.right").font(CuadraoTypography.supporting).foregroundStyle(.secondary).accessibilityHidden(true)
                        snapshot(closing, title: CuadraoCopy.text("copy.cuadraoBalanceBreakdown.9a5e853dda", spanish: spanish))
                    }
                    VStack(alignment: .leading, spacing: 16) {
                        snapshot(opening, title: CuadraoCopy.text("copy.cuadraoBalanceBreakdown.33e2af4e9c", spanish: spanish))
                        snapshot(closing, title: CuadraoCopy.text("copy.cuadraoBalanceBreakdown.9a5e853dda", spanish: spanish))
                    }
                }.accessibilityIdentifier("home-balance-comparison")
            } else {
                Text(CuadraoCopy.text("copy.cuadraoBalanceBreakdown.094154545b", spanish: spanish))
                    .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
            }
            VStack(spacing: 0) {
                ForEach(period.changes) { row in
                    if linksToAccounts {
                        NavigationLink(value: row.id) { rowContent(row) }
                            .buttonStyle(.plain).accessibilityIdentifier("home-balance-change-" + row.id.uuidString)
                    } else {
                        rowContent(row).accessibilityElement(children: .combine)
                            .accessibilityIdentifier("home-balance-change-" + row.id.uuidString)
                    }
                }
            }
            if let change = period.change {
                Divider()
                HStack {
                    Text(CuadraoCopy.text("copy.cuadraoBalanceBreakdown.ba753e1499", spanish: spanish)).font(CuadraoTypography.supporting)
                    Spacer(minLength: 12)
                    Text(signed(change)).font(CuadraoTypography.rowAmount).accessibilityIdentifier("home-balance-net-change")
                }
            }
            if period.isPartial {
                Text(CuadraoCopy.text("copy.cuadraoBalanceBreakdown.6d250ddcd8", spanish: spanish))
                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
        }.padding(.top, 20).accessibilityElement(children: .contain).accessibilityIdentifier("home-balance-breakdown")
    }
    private func snapshot(_ point: CanvasBalancePoint, title: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(CuadraoTypography.caption).foregroundStyle(.secondary)
            Text(money(point.balance)).font(CuadraoTypography.secondaryAmount)
            Text(date(point.date)).font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }.fixedSize(horizontal: false, vertical: true)
    }
    private func rowContent(_ row: CanvasBalanceChange) -> some View {
        HStack(spacing: 12) {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    accountLabel(row)
                    accountValue(row, alignment: .leading)
                }
                Spacer(minLength: 0)
            } else {
                accountLabel(row)
                Spacer(minLength: 8)
                accountValue(row, alignment: .trailing)
            }
            if linksToAccounts { Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary) }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 14).contentShape(Rectangle())
    }
    private func accountLabel(_ row: CanvasBalanceChange) -> some View {
        HStack(spacing: 10) {
            CanvasAccountIcon(kind: row.account.kind)
            Text(row.account.displayName(spanish)).font(CuadraoTypography.supporting)
        }
    }
    private func accountValue(_ row: CanvasBalanceChange, alignment: HorizontalAlignment) -> some View {
        VStack(alignment: alignment, spacing: 4) {
            Text(row.change.map(signed) ?? startingBalance(row) ?? missingAmount).font(CuadraoTypography.rowAmount)
            if let caption = caption(row) {
                Text(caption).font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
        }
    }
    private var missingAmount: String { missingCoverage ? CuadraoMissingCoverage.amount(spanish) : "—" }
    /// With no opening anywhere, the rows list each account's starting balance. Once a connected period has
    /// an opening, an account missing either end shows no data rather than a balance read as a change.
    private func startingBalance(_ row: CanvasBalanceChange) -> String? {
        missingCoverage && period.change != nil ? nil : row.closing.map(money)
    }
    private func caption(_ row: CanvasBalanceChange) -> String? {
        if let change = row.change {
            return change == 0 ? (CuadraoCopy.text("copy.cuadraoBalanceBreakdown.d7bc67be8b", spanish: spanish)) : change > 0 ? (CuadraoCopy.text("copy.cuadraoBalanceBreakdown.2fee63b543", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoBalanceBreakdown.02659db112", spanish: spanish))
        }
        if row.closing == nil { return CuadraoCopy.text("copy.cuadraoBalanceBreakdown.51a5a24fed", spanish: spanish) }
        return missingCoverage && period.change != nil ? (CuadraoCopy.text("copy.cuadraoBalanceBreakdown.7b8ca04530", spanish: spanish)) : nil
    }
}
