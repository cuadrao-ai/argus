import SwiftUI

/// One row of the + menu: what it is called, and what choosing it does.
struct CuadraoAddItem: Identifiable {
    let action: CuadraoAddAction
    let perform: () -> Void
    var id: String { action.id }
}

extension CuadraoAddAction {
    func title(spanish: Bool) -> String {
        switch self {
        case .account: spanish ? "Cuenta" : "Account"
        case .transaction: spanish ? "Transacción" : "Transaction"
        case .plan: "Plan"
        case .group: spanish ? "Grupo" : "Group"
        case .invite: spanish ? "Invitar" : "Invite"
        case .scanCamera: spanish ? "Escanear con la cámara" : "Scan with camera"
        case .choosePhoto: spanish ? "Elegir una foto" : "Choose a photo"
        case .chooseFile: spanish ? "Elegir un archivo" : "Choose a file"
        }
    }

    var symbol: String {
        switch self {
        case .account: "creditcard"
        case .transaction: "arrow.left.arrow.right"
        case .plan: "calendar.badge.plus"
        case .group: "person.2"
        case .invite: "person.badge.plus"
        case .scanCamera: "doc.viewfinder"
        case .choosePhoto: "photo"
        case .chooseFile: "folder"
        }
    }
}

/// The + menu is one list in two layouts. A card with a nub grows out of the + on the open bar; labeled round
/// buttons stack up from the + once the bar has folded into it. Both come from the same items, in the same order.
struct CuadraoAddTray: View {
    enum Layout { case card, stack }

    let items: [CuadraoAddItem]
    let spanish: Bool
    let layout: Layout
    /// The room above the bar. At default sizes the rows fit; large text makes the menu scroll instead of leaving the screen.
    var maxHeight: CGFloat = .infinity
    let choose: (CuadraoAddItem) -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ScaledMetric(relativeTo: .body) private var glyphSize: CGFloat = 17
    @AccessibilityFocusState private var focusedRow: String?
    @State private var contentHeight: CGFloat?
    @State private var appeared = false

    private var groups: [[CuadraoAddItem]] {
        [items.filter { !$0.action.isFileAction }, items.filter { $0.action.isFileAction }].filter { !$0.isEmpty }
    }

    var body: some View {
        Group {
            switch layout {
            case .card: card
            case .stack: stack
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("add.tray")
        .onAppear {
            focusedRow = items.first?.id
            appeared = true
        }
    }

    // MARK: Card

    private var card: some View {
        VStack(spacing: 0) {
            // The card is as tall as its rows, up to a cap; it scrolls only when large text leaves no room.
            ScrollView {
                cardRows.onGeometryChange(for: CGFloat.self) { $0.size.height } action: { contentHeight = $0 }
            }
            .scrollBounceBehavior(.basedOnSize)
            .frame(height: contentHeight.map { min($0, 420, max(120, maxHeight - 40)) } ?? CGFloat(items.count) * 52)
            .padding(.vertical, 6).padding(.horizontal, 12)
            .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 28))
            CuadraoAddNub()
                .fill(WelcomePalette.surface)
                .frame(width: 22, height: 9)
                .accessibilityHidden(true)
        }
        .shadow(color: .black.opacity(0.14), radius: 20, y: 6)
    }

    private var cardRows: some View {
        VStack(spacing: 0) {
            ForEach(Array(groups.enumerated()), id: \.offset) { groupIndex, group in
                if groupIndex > 0 {
                    Divider().padding(.vertical, 4).padding(.horizontal, 6)
                }
                ForEach(group) { item in
                    cardRow(item)
                    if item.id != group.last?.id { Divider().padding(.leading, 52) }
                }
            }
        }
    }

    private func cardRow(_ item: CuadraoAddItem) -> some View {
        Button { choose(item) } label: {
            HStack(spacing: 14) {
                Image(systemName: item.action.symbol)
                    .font(.system(size: min(glyphSize, 24), weight: .regular))
                    .foregroundStyle(WelcomePalette.pine)
                    .frame(width: 34, height: 34)
                    .background(WelcomePalette.pine.opacity(0.1), in: Circle())
                    .accessibilityHidden(true)
                Text(item.action.title(spanish: spanish)).font(.body)
                Spacer(minLength: 8)
            }
            .padding(.horizontal, 6).frame(minHeight: 52).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("add.tray." + item.action.rawValue)
        .accessibilityFocused($focusedRow, equals: item.id)
        .modifier(CuadraoAddStagger(index: index(of: item), count: items.count, appeared: appeared, reduceMotion: reduceMotion, fromBottom: false))
    }

    // MARK: Stack

    private var stack: some View {
        // Rows nearest the + stay in view when the stack is taller than the room above the bar.
        ScrollView {
            VStack(alignment: .trailing, spacing: 12) {
                ForEach(Array(groups.enumerated()), id: \.offset) { groupIndex, group in
                    if groupIndex > 0 { Color.clear.frame(height: 6) }
                    ForEach(group) { item in stackRow(item) }
                }
            }
            .padding(.vertical, 14)
            .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { contentHeight = $0 }
        }
        .scrollBounceBehavior(.basedOnSize)
        .scrollClipDisabled()
        .defaultScrollAnchor(.bottom)
        .frame(height: contentHeight.map { min($0, max(120, maxHeight)) })
    }

    private func stackRow(_ item: CuadraoAddItem) -> some View {
        Button { choose(item) } label: {
            HStack(spacing: 12) {
                Text(item.action.title(spanish: spanish))
                    .font(.subheadline.weight(.medium))
                    .padding(.horizontal, 12).padding(.vertical, 7)
                    .background(WelcomePalette.surface, in: Capsule())
                    .shadow(color: .black.opacity(0.1), radius: 6, y: 2)
                Image(systemName: item.action.symbol)
                    .font(.system(size: min(glyphSize + 2, 30), weight: .regular))
                    .foregroundStyle(WelcomePalette.pine)
                    .frame(width: 48, height: 48)
                    .background(WelcomePalette.surface, in: Circle())
                    .shadow(color: .black.opacity(0.14), radius: 10, y: 3)
                    .accessibilityHidden(true)
            }
            .frame(minHeight: 48).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("add.tray." + item.action.rawValue)
        .accessibilityFocused($focusedRow, equals: item.id)
        .modifier(CuadraoAddStagger(index: index(of: item), count: items.count, appeared: appeared, reduceMotion: reduceMotion, fromBottom: true))
    }

    private func index(of item: CuadraoAddItem) -> Int { items.firstIndex { $0.id == item.id } ?? 0 }
}

/// Rows settle in one after another so the menu reads as growing out of the +: the card from the top down,
/// the stack from the + upward.
private struct CuadraoAddStagger: ViewModifier {
    let index: Int
    let count: Int
    let appeared: Bool
    let reduceMotion: Bool
    let fromBottom: Bool

    func body(content: Content) -> some View {
        let order = fromBottom ? count - 1 - index : index
        content
            .opacity(reduceMotion || appeared ? 1 : 0)
            .offset(y: reduceMotion || appeared ? 0 : (fromBottom ? 14 : 10))
            .animation(reduceMotion ? nil : .spring(response: 0.34, dampingFraction: 0.8).delay(0.05 + Double(order) * 0.035), value: appeared)
    }
}

/// The small point under the card that aims it at the +.
private struct CuadraoAddNub: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.minY))
        path.addQuadCurve(to: CGPoint(x: rect.midX, y: rect.maxY), control: CGPoint(x: rect.midX - rect.width * 0.12, y: rect.minY + rect.height * 0.15))
        path.addQuadCurve(to: CGPoint(x: rect.maxX, y: rect.minY), control: CGPoint(x: rect.midX + rect.width * 0.12, y: rect.minY + rect.height * 0.15))
        path.closeSubpath()
        return path
    }
}
