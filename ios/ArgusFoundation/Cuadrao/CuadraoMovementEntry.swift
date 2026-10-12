import SwiftUI

/// Words for the amount-first movement entry. Kept here until the approved strings land in the catalog.
struct MovementEntryCopy {
    let spanish: Bool
    var from: String { spanish ? "De" : "From" }
    var to: String { spanish ? "A" : "To" }
    var account: String { spanish ? "Cuenta" : "Account" }
    var swap: String { spanish ? "Cambiar origen y destino" : "Swap from and to" }
}

/// Wraps its children onto new lines, so chips stay above the keyboard at every text size.
struct MovementChipFlow: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(width: proposal.width ?? .infinity, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrange(width: bounds.width, subviews: subviews)
        for (index, origin) in result.origins.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + origin.x, y: bounds.minY + origin.y), proposal: .unspecified)
        }
    }

    private func arrange(width: CGFloat, subviews: Subviews) -> (size: CGSize, origins: [CGPoint]) {
        var origins: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, maxX: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > width { x = 0; y += rowHeight + spacing; rowHeight = 0 }
            origins.append(CGPoint(x: x, y: y))
            x += size.width + spacing; rowHeight = max(rowHeight, size.height); maxX = max(maxX, x - spacing)
        }
        return (CGSize(width: maxX, height: y + rowHeight), origins)
    }
}

/// The chip look shared by pickers and the date control.
struct MovementChipLabel: View {
    let symbol: String
    let title: String
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: symbol).font(.caption.weight(.semibold)).accessibilityHidden(true)
            Text(title).font(CuadraoTypography.supporting).lineLimit(1)
            Image(systemName: "chevron.down").font(.caption2.weight(.semibold)).accessibilityHidden(true)
        }
        .foregroundStyle(WelcomePalette.ink).padding(.horizontal, 14).frame(minHeight: 44)
        .background(WelcomePalette.surface, in: Capsule()).contentShape(Capsule())
    }
}

/// One single-choice chip. The menu keeps the native checkmark list.
struct MovementChoiceChip<Value: Hashable>: View {
    let caption: String
    let symbol: String
    @Binding var selection: Value
    let values: [Value]
    let valueTitle: (Value) -> String
    var body: some View {
        Menu {
            Picker(caption, selection: $selection) {
                ForEach(values, id: \.self) { Text(valueTitle($0)).tag($0) }
            }
        } label: { MovementChipLabel(symbol: symbol, title: valueTitle(selection)) }
            .accessibilityLabel(caption + ", " + valueTitle(selection))
    }
}

/// The date as a chip: the system compact picker already draws its own pill.
struct MovementDateChip: View {
    let caption: String
    @Binding var date: Date
    let range: ClosedRange<Date>
    let identifier: String
    var body: some View {
        DatePicker(caption, selection: $date, in: range, displayedComponents: .date)
            .labelsHidden().datePickerStyle(.compact).tint(WelcomePalette.pine)
            .fixedSize().frame(minHeight: 44)
            .accessibilityLabel(caption).accessibilityIdentifier(identifier)
    }
}

/// "De" and "A" side by side with a swap button between them.
struct MovementTransferCards<Value: Hashable>: View {
    let copy: MovementEntryCopy
    @Binding var from: Value
    @Binding var to: Value
    let fromValues: [Value]
    let toValues: [Value]
    let valueTitle: (Value) -> String
    let swap: () -> Void
    let canSwap: Bool
    let fromIdentifier: String
    let toIdentifier: String
    let swapIdentifier: String

    var body: some View {
        VStack(spacing: -10) {
            card(copy.from, selection: $from, values: fromValues, identifier: fromIdentifier)
            Button(action: swap) {
                Image(systemName: "arrow.up.arrow.down").font(.subheadline.weight(.semibold))
                    .foregroundStyle(WelcomePalette.onAccent).frame(width: 44, height: 44)
                    .background(WelcomePalette.pine, in: Circle())
                    .overlay { Circle().stroke(WelcomePalette.background, lineWidth: 4) }
            }.disabled(!canSwap).opacity(canSwap ? 1 : 0.4).zIndex(1)
                .accessibilityLabel(copy.swap).accessibilityIdentifier(swapIdentifier)
            card(copy.to, selection: $to, values: toValues, identifier: toIdentifier)
        }
    }

    private func card(_ caption: String, selection: Binding<Value>, values: [Value], identifier: String) -> some View {
        Menu {
            Picker(caption, selection: selection) {
                ForEach(values, id: \.self) { Text(valueTitle($0)).tag($0) }
            }
        } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(caption).font(.caption).foregroundStyle(.secondary)
                    Text(valueTitle(selection.wrappedValue)).font(CuadraoTypography.action).foregroundStyle(WelcomePalette.ink).lineLimit(1)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.down").font(.caption.weight(.semibold)).foregroundStyle(WelcomePalette.pine).accessibilityHidden(true)
            }.padding(.horizontal, 16).padding(.vertical, 12).frame(maxWidth: .infinity, minHeight: 56)
                .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 18))
        }.accessibilityLabel(caption + ", " + valueTitle(selection.wrappedValue)).accessibilityIdentifier(identifier)
    }
}
