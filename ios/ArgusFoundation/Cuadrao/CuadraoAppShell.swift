import SwiftUI

enum CuadraoAppShellMetrics {
    static let navigationHeight: CGFloat = 72
}

struct CuadraoAppShell<Content: View>: View {
    @Binding var selection: CuadraoTab
    let chat: CuadraoChatPreview
    let spanish: Bool
    let showsNavigation: Bool
    let compact: Bool
    let avatar: CuadraoAvatarSelection
    let profileName: String
    var showProposal: (() -> Void)? = nil
    var addItems: [CuadraoAddItem] = []
    /// Whether the third slot is the assistant tab or the add action. A host that never has an assistant says so
    /// here instead of inheriting the build-wide setting.
    var hasAssistant: Bool = CuadraoFirstRelease.hasAssistant
    @ViewBuilder let content: (Binding<CuadraoTab>) -> Content
    @State private var pendingTab: CuadraoTab?
    @State private var addOpen = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TabView(selection: tabSelection) { content(tabSelection) }
            .cuadraoScrollBar(edge: .bottom) {
                VStack(spacing: 0) {
                    if chat.voiceContextOwner == nil && selection != .assistant && chat.voice.active && chat.voice.presentation != .expanded {
                        CuadraoVoiceBar(voice: chat.voice, spanish: spanish)
                    }
                    if showsNavigation {
                        ZStack {
                            if chat.voiceMessage.state != .recording {
                                CuadraoNavigationBar(selection: tabSelection, compact: compact, spanish: spanish,
                                    avatar: avatar, profileName: profileName,
                                    addOpen: addOpen, hasAssistant: hasAssistant, add: toggleAdd)
                                    .padding(.horizontal, 20)
                                    .frame(height: 64, alignment: .bottom)
                                    .padding(.bottom, 8)
                                    .transition(.opacity)
                            }
                        }.frame(height: CuadraoAppShellMetrics.navigationHeight)
                            .animation(reduceMotion ? nil : .easeOut(duration: 0.18), value: chat.voiceMessage.state == .recording)
                    }
                }
            }
            .overlay { addLayer }
            .onChange(of: showsNavigation) { _, shown in if !shown { closeAdd() } }
            .onChange(of: selection) { _, _ in closeAdd() }
            .cuadraoSoftScrollEdges()
            .cuadraoVoicePresentation(chat: chat, spanish: spanish, ownsPresentation: chat.voiceContextOwner == nil,
                keyboard: {
                    if hasAssistant { selection = .assistant }
                    chat.voice.presentation = .keyboard
                }, showProposal: showProposal.map { show in {
                    show()
                    selection = .plan
                    chat.voice.presentation = .compact
                } })
            .confirmationDialog(spanish ? "¿Terminar el chat temporal?" : "End temporary chat?",
                isPresented: Binding(get: { pendingTab != nil }, set: { if !$0 { pendingTab = nil } }), titleVisibility: .visible) {
                Button(spanish ? "Terminar y salir" : "End and leave", role: .destructive) {
                    let destination = pendingTab
                    chat.leaveTemporary(for: .returnToRegular)
                    pendingTab = nil
                    if let destination { selection = destination }
                }
                Button(spanish ? "Seguir aquí" : "Stay here", role: .cancel) { pendingTab = nil }
            } message: {
                Text(spanish ? "Se descartará el contenido temporal. Tu chat anterior quedará intacto." : "Temporary content will be discarded. Your previous chat stays intact.")
            }
            .tint(WelcomePalette.pine)
            .foregroundStyle(WelcomePalette.ink)
            .environment(\.cuadraoChat, chat)
    }

    /// The add tray is a bubble that pops out of the + over a light dim. Tapping the dim or swiping down closes it.
    @ViewBuilder private var addLayer: some View {
        if addOpen && showsNavigation && !addItems.isEmpty {
            GeometryReader { proxy in
                let barBottom = proxy.safeAreaInsets.bottom + CuadraoAppShellMetrics.navigationHeight
                let atRight = compact && CuadraoNavigationSlot.slots(hasAssistant: hasAssistant).contains(.add)
                ZStack(alignment: .bottom) {
                    // The dim covers the whole screen, bar included, so no bright band is left behind the tray.
                    Color.black.opacity(0.16).allowsHitTesting(false).accessibilityHidden(true)
                    // Taps above the bar close the tray; the bar itself stays live for the X.
                    Color.clear.contentShape(Rectangle())
                        .padding(.bottom, barBottom)
                        .onTapGesture { closeAdd() }
                        .gesture(DragGesture(minimumDistance: 20).onEnded { value in
                            if value.translation.height > 30 { closeAdd() }
                        })
                        .accessibilityHidden(true)
                        .accessibilityIdentifier("add.scrim")
                    CuadraoAddTray(items: addItems, spanish: spanish, layout: atRight ? .stack : .card,
                                   maxHeight: proxy.size.height - CuadraoAppShellMetrics.navigationHeight - 12) { item in
                        closeAdd()
                        item.perform()
                    }
                    .frame(maxWidth: atRight ? .infinity : 300, alignment: atRight ? .trailing : .center)
                    .frame(maxWidth: .infinity, alignment: atRight ? .trailing : .center)
                    // The collapsed + sits 48pt in from the edge, which is the centre of a 48pt round button.
                    .padding(.trailing, atRight ? 24 : 0)
                    .padding(.bottom, atRight ? barBottom - 10 : barBottom - 2)
                    .transition(reduceMotion ? .opacity
                        : .scale(scale: 0.3, anchor: atRight ? .bottomTrailing : .bottom).combined(with: .opacity))
                    .accessibilityAction(.escape) { closeAdd() }
                }
                // The proxy above still reports the safe area; only the layer itself runs under it.
                .ignoresSafeArea()
            }
        }
    }

    private func toggleAdd() {
        guard !addItems.isEmpty else { return }
        withAnimation(reduceMotion ? nil : .spring(response: 0.34, dampingFraction: 0.72)) { addOpen.toggle() }
    }

    private func closeAdd() {
        guard addOpen else { return }
        withAnimation(reduceMotion ? nil : .spring(response: 0.3, dampingFraction: 0.85)) { addOpen = false }
    }

    private var tabSelection: Binding<CuadraoTab> {
        Binding(get: { selection }, set: { next in
            if next == .assistant && !hasAssistant { return }
            closeAdd()
            if selection == .assistant && next != .assistant && chat.hasTemporaryContent {
                pendingTab = next
            } else {
                if selection == .assistant && next != .assistant && chat.temporary {
                    chat.leaveTemporary(for: .returnToRegular)
                }
                selection = next
            }
        })
    }
}
