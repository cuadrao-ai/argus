import SwiftUI

struct CuadraoDistributionGroup: Identifiable {
    let id: String
    let title: String
    let amount: String
    let percentage: String
    let fraction: Double
    let color: Color
    var accountCount: Int?
}

struct CuadraoDistributionContent<AccountRows: View, DeductionRows: View>: View {
    let currency: String
    let spanish: Bool
    let balanceTitle: String
    let balance: String
    let partial: Bool
    let assets: String
    let groups: [CuadraoDistributionGroup]
    let deductions: String?
    var hasDeductionRows = false
    var controls: CuadraoInsightControls?
    @Binding var selectedGroup: String?
    @ViewBuilder let accountRows: (String) -> AccountRows
    @ViewBuilder let deductionRows: () -> DeductionRows
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private func select(_ group: String?) {
        withAnimation(reduceMotion ? .easeInOut(duration: 0.15) : .spring(response: 0.42, dampingFraction: 0.85)) {
            selectedGroup = selectedGroup == group ? nil : group
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            VStack(alignment: .leading, spacing: 8) {
                Text(balanceTitle).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(currency).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                    Text(balance).font(CuadraoTypography.amount).lineLimit(1).minimumScaleFactor(0.5)
                        .accessibilityIdentifier("home-distribution-total")
                }
                if partial {
                    Text(CuadraoCopy.text("copy.cuadraoDistributionContent.0a57d3d74b", spanish: spanish))
                        .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                }
            }
            if let controls { controls }
            if !groups.isEmpty {
                HStack {
                    Text(CuadraoCopy.text("copy.cuadraoDistributionContent.7558ff10d9", spanish: spanish))
                    Spacer()
                    Text(assets).font(CuadraoTypography.rowAmount)
                }.font(CuadraoTypography.supporting)
                CuadraoAllocationBar(segments: groups.map {
                    CuadraoAllocationSegment(id: $0.id, title: $0.title, fraction: $0.fraction, color: $0.color)
                }, selection: $selectedGroup, identifier: "home-distribution-segment-")
                HStack(spacing: 8) {
                    Button { select(nil) } label: {
                        Text(CuadraoCopy.text("copy.cuadraoDistributionContent.64c04b1430", spanish: spanish)).frame(minHeight: 44).contentShape(Rectangle())
                    }.foregroundStyle(selectedGroup == nil ? WelcomePalette.ink : .secondary)
                        .accessibilityIdentifier("home-distribution-all")
                    if let selected = groups.first(where: { $0.id == selectedGroup }) {
                        Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                        Text(selected.title).foregroundStyle(selected.color)
                    }
                    Spacer()
                }.font(CuadraoTypography.supporting).frame(minHeight: 44)
                VStack(spacing: 0) {
                    ForEach(groups) { group in categoryRow(group) }
                }
            } else {
                Text(CuadraoCopy.text("copy.cuadraoDistributionContent.437f65fb9f", spanish: spanish))
                    .font(CuadraoTypography.supporting).foregroundStyle(.secondary).padding(.vertical, 32)
            }
            if let deductions {
                Divider()
                if hasDeductionRows {
                    DisclosureGroup { deductionRows() } label: { deductionLabel(deductions) }
                } else {
                    deductionLabel(deductions)
                }
                HStack {
                    Text(CuadraoCopy.text("copy.connectedCuadraoBalanceOverview.a3299351f5", spanish: spanish))
                    Spacer()
                    Text(balance).font(CuadraoTypography.rowAmount)
                }.font(CuadraoTypography.supporting)
            }
        }.sensoryFeedback(.selection, trigger: selectedGroup)
            .onChange(of: groups.map(\.id)) { _, available in
                if let selectedGroup, !available.contains(selectedGroup) { self.selectedGroup = nil }
            }
    }
    private func deductionLabel(_ amount: String) -> some View {
        HStack {
            Text(CuadraoCopy.text("copy.cuadraoDistributionContent.4a2266fa10", spanish: spanish))
            Spacer()
            Text(amount).font(CuadraoTypography.rowAmount)
        }.font(CuadraoTypography.supporting).frame(minHeight: 44)
    }
    private func categoryRow(_ group: CuadraoDistributionGroup) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { select(group.id) } label: {
                VStack(spacing: 12) {
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 6) {
                                Text(group.title).font(CuadraoTypography.supporting)
                                if group.accountCount != nil {
                                    Image(systemName: selectedGroup == group.id ? "chevron.up" : "chevron.down")
                                        .font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                            if let count = group.accountCount {
                                Text(CuadraoCopy.text("copy.cuadraoDistributionContent.0cea7fab0e", spanish: spanish, String(describing: count), String(describing: ((count == 1 ? CuadraoCopy.text("copy.cuadraoDistributionContent.f08da4f153", spanish: spanish) : CuadraoCopy.text("copy.cuadraoDistributionContent.596ed8b9e3", spanish: spanish))))))
                                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                            }
                        }
                        Spacer(minLength: 8)
                        VStack(alignment: .trailing, spacing: 6) {
                            Text(group.percentage).font(CuadraoTypography.rowAmount)
                            Text(group.amount).font(CuadraoTypography.rowAmount).foregroundStyle(.secondary)
                        }
                    }
                    GeometryReader { proxy in
                        Rectangle().fill(WelcomePalette.ink.opacity(0.04))
                        Rectangle().fill(group.color).frame(width: max(0, proxy.size.width) * group.fraction)
                    }.frame(height: 3).accessibilityHidden(true)
                }.padding(.vertical, 18).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityIdentifier("home-distribution-" + group.id)
                .accessibilityValue(selectionLabel(group))
            if selectedGroup == group.id { accountRows(group.id) }
        }
    }
    private func selectionLabel(_ group: CuadraoDistributionGroup) -> String {
        if group.accountCount == nil {
            return selectedGroup == group.id ? (CuadraoCopy.text("copy.cuadraoDistributionContent.7dcec00d23", spanish: spanish)) : ""
        }
        return selectedGroup == group.id ? (CuadraoCopy.text("copy.cuadraoDistributionContent.9224088f94", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoDistributionContent.5b51c07868", spanish: spanish))
    }
}
