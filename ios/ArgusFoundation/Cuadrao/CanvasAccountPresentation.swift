import SwiftUI

struct CanvasAccountRowValue {
    let title: String
    let subtitle: String
    let artwork: CanvasAccountKind?
    let amount: String
    let amountCaption: String
    let note: String?

    init(title: String, subtitle: String, artwork: CanvasAccountKind?, amount: String, amountCaption: String, note: String? = nil) {
        self.title = title; self.subtitle = subtitle; self.artwork = artwork
        self.amount = amount; self.amountCaption = amountCaption; self.note = note
    }
}

struct CanvasAccountRowContent: View {
    let value: CanvasAccountRowValue
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        HStack(alignment: typeSize.isAccessibilitySize ? .top : .center, spacing: 12) {
            CanvasAccountArtwork(kind: value.artwork)
                .frame(width: 42, height: 42)
                .background(WelcomePalette.sage.opacity(0.65), in: RoundedRectangle(cornerRadius: 13))
            VStack(alignment: .leading, spacing: 5) {
                Text(value.title).font(CuadraoTypography.action)
                    .fixedSize(horizontal: false, vertical: true)
                Text(value.subtitle).font(.caption).foregroundStyle(.secondary)
                if let note = value.note { Text(note).font(.caption).foregroundStyle(.secondary) }
                if typeSize.isAccessibilitySize { balance.padding(.top, 6) }
            }.frame(maxWidth: .infinity, alignment: .leading)
            if !typeSize.isAccessibilitySize { balance.fixedSize(horizontal: true, vertical: false) }
        }.padding(.vertical, 12).contentShape(Rectangle())
    }

    private var balance: some View {
        VStack(alignment: typeSize.isAccessibilitySize ? .leading : .trailing, spacing: 5) {
            Text(value.amount).font(CuadraoTypography.rowAmount)
                .lineLimit(1).minimumScaleFactor(0.6)
            Text(value.amountCaption).font(.caption).foregroundStyle(.secondary)
        }
    }
}

struct CanvasAccountArtwork: View {
    let kind: CanvasAccountKind?
    var size: CGFloat = 23

    var body: some View {
        if let kind { CanvasAccountIcon(kind: kind, size: size) }
        else {
            Image(systemName: "square.stack").font(.system(size: size))
                .foregroundStyle(WelcomePalette.pine).accessibilityHidden(true)
        }
    }
}

struct CanvasAccountDetailValue {
    let title: String
    let artwork: CanvasAccountKind?
    let balanceLabel: String
    let currency: String
    let amount: String
    let freshness: String
    let notes: [String]
    let amountIdentifier: String
    let amountAccessibilityLabel: String?

    init(title: String, artwork: CanvasAccountKind?, balanceLabel: String, currency: String, amount: String, freshness: String,
         notes: [String] = [], amountIdentifier: String = "account-detail-amount", amountAccessibilityLabel: String? = nil) {
        self.title = title; self.artwork = artwork; self.balanceLabel = balanceLabel; self.currency = currency
        self.amount = amount; self.freshness = freshness; self.notes = notes
        self.amountIdentifier = amountIdentifier; self.amountAccessibilityLabel = amountAccessibilityLabel
    }
}

struct CanvasAccountDetailHeader: View {
    let value: CanvasAccountDetailValue

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            CanvasAccountArtwork(kind: value.artwork, size: 30)
                .frame(width: 58, height: 58)
                .background(WelcomePalette.sage, in: RoundedRectangle(cornerRadius: 18))
            Text(value.title).font(CuadraoTypography.screen)
                .accessibilityIdentifier("account-detail-title")
                .fixedSize(horizontal: false, vertical: true)
            VStack(alignment: .leading, spacing: 9) {
                Text(value.balanceLabel).font(.subheadline).foregroundStyle(.secondary)
                HStack(alignment: .firstTextBaseline, spacing: 9) {
                    Text(value.currency).font(.subheadline).foregroundStyle(.secondary)
                    Text(value.amount).font(CuadraoTypography.amount)
                        .monospacedDigit().lineLimit(1).minimumScaleFactor(0.6)
                        .accessibilityLabel(value.amountAccessibilityLabel ?? value.amount)
                        .accessibilityIdentifier(value.amountIdentifier)
                }
                Text(value.freshness).font(.footnote).foregroundStyle(.secondary)
                ForEach(value.notes, id: \.self) { note in
                    Text(note).font(.footnote).foregroundStyle(.secondary)
                }
            }
        }
    }
}

struct CanvasAccountDetailContent<History: View>: View {
    let value: CanvasAccountDetailValue
    let spanish: Bool
    var recordEnabled = true
    var checkEnabled = true
    var recordIdentifier = "account-detail-record"
    var checkIdentifier = "account-detail-check"
    let record: () -> Void
    let check: () -> Void
    @ViewBuilder let history: () -> History

    var body: some View {
        LazyVStack(alignment: .leading, spacing: 30) {
            CanvasAccountDetailHeader(value: value)
            VStack(spacing: 12) {
                RegistrationButton(title: CuadraoCopy.text("copy.canvasAccountPresentation.ef0cf39904", spanish: spanish), enabled: recordEnabled, action: record)
                    .accessibilityIdentifier(recordIdentifier)
                Button(CuadraoCopy.text("copy.canvasAccountPresentation.96327e1801", spanish: spanish), action: check)
                    .font(.system(size: 13, weight: .medium)).padding(.horizontal, 16).frame(minHeight: 44)
                    .overlay { Capsule().stroke(WelcomePalette.border, lineWidth: 1) }
                    .disabled(!checkEnabled).accessibilityIdentifier(checkIdentifier)
            }
            history()
        }
    }
}

struct CanvasAccountActivityRowValue {
    let title: String
    let detail: String
    let amount: String
    let symbol: String
    let status: String?

    init(title: String, detail: String, amount: String, symbol: String, status: String? = nil) {
        self.title = title; self.detail = detail; self.amount = amount; self.symbol = symbol; self.status = status
    }
}

struct CanvasAccountActivityRowContent: View {
    let value: CanvasAccountActivityRowValue

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: value.symbol).frame(width: 38, height: 38)
                .background(WelcomePalette.surface, in: Circle()).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 5) {
                Text(value.title).font(.body)
                Text(value.detail).font(.caption).foregroundStyle(.secondary)
                if let status = value.status {
                    Text(status).font(.caption).foregroundStyle(.secondary)
                        .accessibilityIdentifier("activity.moved")
                }
            }
            Spacer()
            Text(value.amount).font(CuadraoTypography.rowAmount)
        }.padding(.vertical, 10).contentShape(Rectangle())
    }
}
