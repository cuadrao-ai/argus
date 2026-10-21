import SwiftUI
import Observation

// Navigation artwork and destination names have one owner across the canvas.
extension CuadraoTab {
    func title(spanish: Bool) -> String {
        switch self {
        case .home: spanish ? "Inicio" : "Home"
        case .plan: "Plan"
        case .assistant: spanish ? "Asistente" : "Assistant"
        case .search: spanish ? "Buscar" : "Search"
        case .profile: spanish ? "Perfil" : "Profile"
        }
    }

    var symbol: String {
        switch self {
        case .home: "house"
        case .plan: "calendar"
        case .assistant: "sparkle"
        case .search: "magnifyingglass"
        case .profile: "person"
        }
    }

    func image(selected: Bool) -> Image {
        switch self {
        case .home: Image(selected ? "CuadraoHomeSelected" : "CuadraoHomeOutline")
        case .plan: Image("CuadraoPlan")
        case .profile: Image("CuadraoProfile")
        default: Image(systemName: symbol)
        }
    }

    /// Maps onto tip `tab.*` / `header.profile` identifiers (no Accounts tab).
    var tipAccessibilityID: String {
        switch self {
        case .home: "tab.home"
        case .plan: "tab.plan"
        case .assistant: "tab.argus"
        case .search: "tab.search"
        case .profile: "header.profile"
        }
    }
}

struct CuadraoNavigationBar: View {
    @Binding var selection: CuadraoTab
    let compact: Bool
    let spanish: Bool
    var avatar: CuadraoAvatarSelection = .none
    var profileName: String = ""
    var addOpen = false
    var hasAssistant: Bool = CuadraoFirstRelease.hasAssistant
    let add: () -> Void
    @GestureState private var scrubbing: CuadraoNavigationSlot?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private let padding: CGFloat = 4
    private let slotHeight: CGFloat = 48

    private var slots: [CuadraoNavigationSlot] { CuadraoNavigationSlot.slots(hasAssistant: hasAssistant) }
    /// With an add slot, a collapsed bar folds into the + alone at the right; otherwise it only narrows.
    private var collapsesToAdd: Bool { compact && slots.contains(.add) }

    /// One bar whose slots change width, so collapsing is a resize and never a swap of views.
    var body: some View {
        GeometryReader { proxy in
            let full = proxy.size.width
            let barWidth = collapsesToAdd ? slotHeight + padding * 2 : (compact ? min(full, 270) : full)
            let inner = max(0, barWidth - padding * 2)
            let slotWidth = collapsesToAdd ? slotHeight : inner / CGFloat(max(slots.count, 1))
            HStack(spacing: 0) {
                ForEach(slots) { slot in
                    let folded = collapsesToAdd && slot != .add
                    slotView(slot)
                        .frame(width: folded ? 0 : slotWidth, height: slotHeight)
                        .opacity(folded ? 0 : 1)
                        .clipped()
                        .accessibilityHidden(folded)
                }
            }
            .frame(width: inner, height: slotHeight)
            .gesture(slide(width: inner))
            .padding(padding)
            .modifier(CuadraoNavigationMaterial())
            .frame(width: full, height: slotHeight + padding * 2, alignment: collapsesToAdd ? .trailing : .center)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.2), value: compact)
        }.frame(height: slotHeight + padding * 2)
    }

    /// Sliding a finger across the bar follows it and chooses the slot it lifts on; a tap is a slide of no distance.
    private func slide(width: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .updating($scrubbing) { value, state, _ in state = slot(at: value.location, width: width) }
            .onEnded { value in
                if let chosen = slot(at: value.location, width: width) { activate(chosen) }
            }
    }

    private func slot(at location: CGPoint, width: CGFloat) -> CuadraoNavigationSlot? {
        guard location.y > -40, location.y < 96, location.x > -40, location.x < width + 40, !slots.isEmpty else { return nil }
        if collapsesToAdd { return .add }
        return slots[CuadraoNavigationSlot.index(forX: location.x, width: width, count: slots.count)]
    }

    private func activate(_ slot: CuadraoNavigationSlot) {
        switch slot {
        case .tab(let tab): selection = tab
        case .add: add()
        }
    }

    private var addLabel: String {
        addOpen ? (spanish ? "Cerrar" : "Close") : (spanish ? "Añadir" : "Add")
    }

    private var addGlyph: some View {
        Image(systemName: addOpen ? "xmark" : "plus")
            .font(.system(size: 25, weight: .regular))
            .foregroundStyle(WelcomePalette.pine)
    }

    @ViewBuilder private func slotView(_ slot: CuadraoNavigationSlot) -> some View {
        switch slot {
        case .tab(let tab):
            let highlighted = (scrubbing ?? .tab(selection)) == .tab(tab)
            Group {
                if tab == .profile, avatar != .none {
                    CuadraoIdentityAvatar(selection: avatar, name: profileName, size: 28, presentation: .navigation)
                } else {
                    tab.image(selected: highlighted)
                }
            }
                .environment(\.symbolVariants, .none)
                .font(.system(size: 25, weight: .regular))
                .frame(maxWidth: .infinity)
                .frame(height: 48)
                .foregroundStyle(highlighted ? WelcomePalette.pine : Color.secondary)
                .background {
                    if highlighted { Capsule().fill(WelcomePalette.pine.opacity(0.09)) }
                }
                .contentShape(Capsule())
                // Tip-compatible ids keep UITests working; Cuadrao ordinal remains for design evidence.
                .modifier(SlotAccessibility(label: tab.title(spanish: spanish), identifier: tab.tipAccessibilityID,
                                            selected: selection == tab) { activate(slot) })
        case .add:
            addGlyph
                .frame(maxWidth: .infinity)
                .frame(height: 48)
                .background {
                    if scrubbing == .add { Capsule().fill(WelcomePalette.pine.opacity(0.09)) }
                }
                .contentShape(Capsule())
                .modifier(SlotAccessibility(label: addLabel, identifier: "nav.add", selected: false) { activate(slot) })
        }
    }
}

/// One accessible button per slot. Touches belong to the bar's slide gesture, so the action is also exposed here.
private struct SlotAccessibility: ViewModifier {
    let label: String
    let identifier: String
    let selected: Bool
    let activate: () -> Void

    func body(content: Content) -> some View {
        content
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(label)
            .accessibilityIdentifier(identifier)
            .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
            .accessibilityAction { activate() }
    }
}

private struct CuadraoNavigationMaterial: ViewModifier {
    @ViewBuilder
    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content.glassEffect(.regular.tint(WelcomePalette.background.opacity(0.75)), in: .capsule)
        } else {
            content.background(.regularMaterial, in: Capsule())
                .overlay { Capsule().strokeBorder(.primary.opacity(0.08), lineWidth: 0.5) }
        }
    }
}

// Preserves the approved HTML thresholds; bounce cannot collapse the bar.
// The inset stays the same height in both states, avoiding scroll/layout feedback.
@Observable
final class CuadraoNavigationScroll {
    private(set) var compact = false
    @ObservationIgnored private var lastOffset: CGFloat = 0
    @ObservationIgnored private var travel: CGFloat = 0

    @ObservationIgnored private var interacting = false

    func setInteracting(_ value: Bool) {
        interacting = value
        travel = 0
    }

    func update(_ rawOffset: CGFloat) {
        let offset = max(0, rawOffset)
        let change = offset - lastOffset
        defer { lastOffset = offset }
        guard interacting else { return }
        guard change != 0 else { return }
        travel = (change.sign == travel.sign ? travel : 0) + change
        if offset < 50 || travel < -12 {
            compact = false
        } else if travel > 30 && offset > 100 {
            compact = true
        }
    }
}

struct CuadraoNavigationScrollObserver: ViewModifier {
    let scroll: CuadraoNavigationScroll
    let enabled: Bool

    @ViewBuilder
    func body(content: Content) -> some View {
        if #available(iOS 18.0, *) {
            content.onScrollGeometryChange(for: CGFloat.self) { geometry in
                let maximum = max(0, geometry.contentSize.height + geometry.contentInsets.top
                    + geometry.contentInsets.bottom - geometry.containerSize.height)
                return min(maximum, max(0, geometry.contentOffset.y + geometry.contentInsets.top))
            } action: { _, offset in
                if enabled { scroll.update(offset) }
            }
            .onScrollPhaseChange { _, phase in
                scroll.setInteracting(phase == .interacting)
            }
        } else {
            content
        }
    }
}
