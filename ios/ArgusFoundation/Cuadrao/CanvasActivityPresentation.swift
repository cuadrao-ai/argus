import SwiftUI

struct CanvasActivityCategoryValue {
    let title: String
    let artwork: CanvasExpenseCategory?
}

struct CanvasActivityDetailValue {
    let title: String
    let amount: String
    let kind: String
    let date: String
    let category: CanvasActivityCategoryValue?
}

struct CanvasActivityDetailContent<Details: View>: View {
    let value: CanvasActivityDetailValue
    let spanish: Bool
    @ViewBuilder let details: () -> Details

    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            Text(value.title).font(CuadraoTypography.feature)
                .accessibilityIdentifier("activity-detail-title")
            Text(value.amount).font(CuadraoTypography.amount).monospacedDigit()
                .accessibilityIdentifier("activity-detail-amount")
            LabeledContent(CuadraoCopy.text("copy.connectedTransactionSheet.36a6ac68b2", spanish: spanish), value: value.kind)
            if let category = value.category {
                LabeledContent(CuadraoCopy.text("copy.connectedCuadraoHome.67c7ee0c0f", spanish: spanish)) {
                    HStack {
                        if let artwork = category.artwork { CuadraoExpenseCategoryIcon(category: artwork) }
                        Text(category.title)
                    }
                }
            }
            LabeledContent(CuadraoCopy.text("copy.connectedTransactionSheet.9e3d3b41ed", spanish: spanish), value: value.date)
            details()
        }
    }
}

struct CanvasActivityAccountRowContent: View {
    let title: String
    let detail: String
    let artwork: CanvasAccountKind?
    var showsDisclosure = true
    var amount: String? = nil

    var body: some View {
        HStack(spacing: 16) {
            CanvasAccountArtwork(kind: artwork)
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(CuadraoTypography.action)
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if let amount { Text(amount).font(CuadraoTypography.rowAmount) }
            if showsDisclosure {
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary).accessibilityHidden(true)
            }
        }.frame(minHeight: 62).contentShape(Rectangle())
    }
}
