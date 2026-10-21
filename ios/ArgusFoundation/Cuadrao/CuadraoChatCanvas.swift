import SwiftUI

struct CuadraoChatCanvas: View {
    @Environment(\.receiptWorkspace) private var receiptWorkspace
    @State private var savedReceipts = false
    @State private var pendingReceipt: ReceiptRoute?
    @State private var temporaryReceipt = false
    let store: CuadraoChatPreview
    let spanish: Bool
    @Binding var editing: Bool
    var contextual = false
    var close: (() -> Void)?
    var showsPreviewNotice = false
    @State private var sheet: CanvasChatSheet?
    @State private var tray = false
    @State private var ending = false
    private var voiceMessage: CuadraoVoiceMessagePreview { store.voiceMessage }
    @AppStorage("cuadrao.design.voice-entry-learned") private var voiceEntryLearned = false
    @Environment(\.scenePhase) private var scenePhase
    @FocusState private var focused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var es: Bool { spanish }
    private var active: Bool { !store.current.turns.isEmpty || !store.current.receiptIDs.isEmpty }
    private var ready: Bool { !store.current.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !store.current.attachments.isEmpty }

    private var holdOnComposer: Bool {
        !focused && !ready && !store.voice.active && voiceMessage.state != .review
            && !(voiceMessage.state == .recording && !voiceMessage.held)
    }

    var body: some View {
        @Bindable var thread = store.current
        Group {
            if active { conversation } else { welcome }
        }
        .cuadraoScrollBar(edge: .top) {
            header.disabled(voiceMessage.state == .recording)
        }
        .cuadraoScrollBar(edge: .bottom) {
            composer(thread: $thread.draft)
        }
        .cuadraoSoftScrollEdges()
        .safeAreaPadding(.bottom, focused || contextual ? 0 : 80)
        .background(WelcomePalette.background)
        .foregroundStyle(WelcomePalette.ink)
        .toolbar(.hidden, for: .tabBar)
        .onChange(of: focused) { _, value in editing = value; if value { tray = false } }
        .onDisappear { focused = false; editing = false
            if voiceMessage.state == .recording { voiceMessage.cancel() } }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active && voiceMessage.state == .recording { voiceMessage.cancel() }
        }
        .onAppear { if store.voice.active && store.voice.presentation == .keyboard { focused = true } }
        .onChange(of: store.voice.presentation) { _, value in
            focused = store.voice.active && value == .keyboard
        }
        .sheet(item: $sheet) { destination in
            CuadraoChatSheet(destination: destination, store: store, spanish: es)
                .tint(WelcomePalette.pine)
        }
        .sheet(isPresented: $savedReceipts, onDismiss: {
            if let pendingReceipt {
                self.pendingReceipt = nil
                switch pendingReceipt {
                case .review(let id): receiptWorkspace?.open(id)
                case .capture(let origin, let source): receiptWorkspace?.capture(origin, source)
                }
            }
        }) {
            if let workspace = receiptWorkspace {
                NavigationStack {
                    ReceiptSavedList(workspace: ReceiptWorkspace(receipts: workspace.receipts, groups: workspace.groups,
                        accounts: workspace.accounts, chat: workspace.chat,
                        capture: { origin, source in
                            pendingReceipt = .capture(ReceiptOrigin(groupID: origin.groupID, threadID: store.current.id), source)
                            savedReceipts = false
                        },
                        open: { id in savedReceipts = false; pendingReceipt = .review(id) }), groupID: store.current.focus?.groupID, spanish: es)
                    .toolbar { CuadraoDoneToolbar(title: CuadraoCopy.text("copy.cuadraoChatCanvas.bd6b05a681", spanish: es)) { savedReceipts = false } }
                }
            }
        }
        .confirmationDialog(CuadraoCopy.text("copy.cuadraoChatCanvas.54ef0f042b", spanish: es), isPresented: $temporaryReceipt, titleVisibility: .visible) {
            Button(CuadraoCopy.text("copy.cuadraoChatCanvas.63c4385004", spanish: es)) { receiptWorkspace?.capture(ReceiptOrigin(groupID: nil, threadID: nil), .scan) }
        } message: { Text(CuadraoCopy.text("copy.cuadraoChatCanvas.bc17ee3d75", spanish: es)) }
        .confirmationDialog(CuadraoCopy.text("copy.cuadraoChatCanvas.b5ea512511", spanish: es), isPresented: $ending, titleVisibility: .visible) {
            Button(CuadraoCopy.text("copy.cuadraoChatCanvas.b259e84c21", spanish: es), role: .destructive) { store.leaveTemporary(for: .newRegular) }
            Button(CuadraoCopy.text("copy.cuadraoChatCanvas.32a630a211", spanish: es), role: .cancel) {}
        } message: {
            Text(CuadraoCopy.text("copy.cuadraoChatCanvas.10504814c5", spanish: es))
        }
    }

    private var header: some View {
        HStack(spacing: 0) {
            if let close {
                control("xmark", CuadraoCopy.text("copy.cuadraoChatCanvas.f72fb61754", spanish: es), id: "chat-context-close", action: close)
            }
            control("clock.arrow.circlepath", CuadraoCopy.text("copy.cuadraoChatCanvas.3541995ad0", spanish: es), id: "chat-history") { sheet = .history }
            if active || store.temporary {
                Button {
                    if store.hasTemporaryContent { ending = true }
                    else { store.leaveTemporary(for: .newRegular) }
                } label: {
                    Image("CuadraoNewChat").resizable().scaledToFit().frame(width: 20, height: 20)
                        .frame(width: 44, height: 44).contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .accessibilityLabel(store.temporary ? (CuadraoCopy.text("copy.cuadraoChatCanvas.bc000ebb7a", spanish: es)) : (CuadraoCopy.text("copy.cuadraoChatCanvas.284b0cf53b", spanish: es)))
                    .accessibilityIdentifier("chat-new")
            } else { Color.clear.frame(width: 44, height: 44) }
            if focused {
                control("keyboard.chevron.compact.down", CuadraoCopy.text("copy.cuadraoChatCanvas.9fa94c6056", spanish: es), id: "chat-dismiss-keyboard") {
                    focused = false
                    if store.voice.active && store.voice.presentation == .keyboard {
                        store.voice.presentation = .compact
                    }
                }
            }
            Spacer(minLength: 8)
            if active && !store.temporary {
                Button { sheet = .share } label: {
                    Image("CuadraoShare").resizable().scaledToFit().frame(width: 20, height: 20)
                        .frame(width: 44, height: 44).contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoChatCanvas.ebf2baf694", spanish: es))
                    .accessibilityIdentifier("chat-share")
                Menu {
                    Button(CuadraoCopy.text("copy.cuadraoChatCanvas.be04335b17", spanish: es), systemImage: "pencil") { sheet = .rename }
                    Button((store.current.pinned ? CuadraoCopy.text("copy.cuadraoChatCanvas.beaa2b609a", spanish: es) : CuadraoCopy.text("copy.cuadraoChatCanvas.a470d7a873", spanish: es)), systemImage: "pin") { store.current.pinned.toggle() }
                    Button(CuadraoCopy.text("copy.cuadraoChatCanvas.d11165f313", spanish: es), systemImage: "envelope.badge") { store.current.unread = true }
                    Button(CuadraoCopy.text("copy.cuadraoChatCanvas.0960027352", spanish: es), systemImage: "archivebox") { store.archive(store.current) }
                    Button(CuadraoCopy.text("copy.cuadraoChatCanvas.534547cf82", spanish: es), systemImage: "trash", role: .destructive) { store.delete(store.current) }
                    Divider()
                    Button(CuadraoCopy.text("copy.cuadraoChatCanvas.799fddcdd7", spanish: es), systemImage: "slider.horizontal.3") { sheet = .states }
                } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoChatCanvas.52acedcbe7", spanish: es))
            } else {
                Button {
                    if store.temporary { sheet = .temporary } else {
                        focused = false; tray = false
                        withAnimation(reduceMotion ? nil : .easeOut(duration: 0.15)) { store.startTemporary() }
                    }
                } label: {
                    Image("CuadraoTemporaryChat").resizable().scaledToFit().frame(width: 24, height: 24)
                        .frame(width: 44, height: 44)
                        .background(store.temporary ? WelcomePalette.surface : .clear, in: Circle())
                }.accessibilityLabel(store.temporary ? (CuadraoCopy.text("copy.cuadraoChatCanvas.329661bcf4", spanish: es)) : (CuadraoCopy.text("copy.cuadraoChatCanvas.d2370f5f03", spanish: es)))
                    .accessibilityValue(store.temporary ? (CuadraoCopy.text("copy.cuadraoChatCanvas.dc337aae84", spanish: es)) : "")
                    .accessibilityIdentifier("chat-temporary")
            }
        }.foregroundStyle(WelcomePalette.ink).padding(.horizontal, 18).padding(.top, 6)
    }

    private var welcome: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 18) {
                    Spacer(minLength: 24)
                    if store.temporary {
                        Image("CuadraoTemporaryChat").resizable().scaledToFit().frame(width: 36, height: 36).foregroundStyle(.secondary)
                        Text(CuadraoCopy.text("copy.cuadraoChatCanvas.9d6f2322f8", spanish: es)).font(CuadraoTypography.feature)
                        Text(CuadraoFirstRelease.shows(.memory)
                            ? (CuadraoCopy.text("copy.cuadraoChatCanvas.b134cd8062", spanish: es))
                            : (CuadraoCopy.text("copy.cuadraoChatCanvas.9654f7c17c", spanish: es)))
                            .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                        Button { sheet = .temporary } label: {
                            HStack(spacing: 6) {
                                Text(store.useContext ? (CuadraoCopy.text("copy.cuadraoChatCanvas.684e6bc34a", spanish: es)) : (CuadraoCopy.text("copy.cuadraoChatCanvas.c862a25b83", spanish: es)))
                                Image(systemName: "chevron.down").font(.caption2)
                            }.font(.subheadline).frame(minHeight: 44)
                        }
                    } else {
                        CuadraoBrand().scaleEffect(0.85).accessibilityLabel(CuadraoCopy.text("copy.cuadraoChatCanvas.d6c2cf736d", spanish: CuadraoCopy.isSpanish()))
                        Text(store.current.focus?.groupID.flatMap { receiptWorkspace?.groups.group($0)?.name } ?? (CuadraoCopy.text("copy.cuadraoChatCanvas.e0a733e485", spanish: es)))
                            .font(CuadraoTypography.screen).multilineTextAlignment(.center)
                        if showsPreviewNotice { previewNotice }
                    }
                    Spacer(minLength: 32)
                }.frame(maxWidth: .infinity, minHeight: geometry.size.height).padding(.horizontal, 24)
            }.scrollDismissesKeyboard(.interactively)
        }
    }

    private var conversation: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 32) {
                    if showsPreviewNotice { previewNotice.frame(maxWidth: .infinity) }
                    if store.temporary {
                        Button { sheet = .temporary } label: {
                            Label { Text((CuadraoCopy.text("copy.cuadraoChatCanvas.385ef6d2aa", spanish: es)) + (store.useContext ? (CuadraoCopy.text("copy.cuadraoChatCanvas.684e6bc34a", spanish: es)) : (CuadraoCopy.text("copy.cuadraoChatCanvas.c862a25b83", spanish: es)))) } icon: {
                                Image("CuadraoTemporaryChat").resizable().scaledToFit().frame(width: 16, height: 16)
                            }
                                .font(.caption).foregroundStyle(.secondary)
                        }.frame(maxWidth: .infinity, minHeight: 44)
                    }
                    if let workspace = receiptWorkspace {
                        if let groupID = store.current.focus?.groupID, let group = workspace.groups.group(groupID) {
                            Text(group.name).font(CuadraoTypography.section)
                        }
                        ForEach(store.current.receiptIDs, id: \.self) { id in
                            if let draft = workspace.receipts.receipt(id) {
                                ReceiptCard(draft: draft, spanish: es) { workspace.open(id) }
                            }
                        }
                    }
                    ForEach(store.current.turns) { turn in
                        VStack(alignment: .leading, spacing: 24) {
                            VStack(alignment: .trailing, spacing: 8) {
                                if let focus = turn.focus { CanvasChatFocusChip(focus: focus, spanish: es) }
                                ForEach(turn.attachments) { item in CanvasChatAttachmentChip(item: item, spanish: es) }
                                if !turn.question.isEmpty {
                                    Text(turn.question).font(.body).textSelection(.enabled)
                                        .padding(.horizontal, 17).padding(.vertical, 13)
                                        .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 22))
                                }
                            }.frame(maxWidth: .infinity, alignment: .trailing).padding(.leading, 28)
                            if turn.id == store.current.turns.last?.id && store.responseState != .complete {
                                responseState
                            } else {
                                CuadraoChatAnswer(turn: turn, spanish: es, showSources: { sheet = .sources }, showDetails: { sheet = .calculation })
                            }
                        }.id(turn.id)
                    }
                    Color.clear.frame(height: 1).id("chat-bottom")
                }.padding(.horizontal, 24).padding(.vertical, 24)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: store.current.turns.count) { _, _ in proxy.scrollTo("chat-bottom", anchor: .bottom) }
            .onChange(of: focused) { _, value in if value { proxy.scrollTo("chat-bottom", anchor: .bottom) } }
            .overlay(alignment: .bottomTrailing) {
                if store.current.turns.count > 1 {
                    Button { withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) { proxy.scrollTo("chat-bottom", anchor: .bottom) } } label: {
                        Image(systemName: "arrow.down").frame(width: 44, height: 44).background(.regularMaterial, in: Circle())
                    }.accessibilityLabel(CuadraoCopy.text("copy.cuadraoChatCanvas.9da0ce92b1", spanish: es)).padding(.trailing, 24)
                }
            }
        }
    }

    private var responseState: some View {
        VStack(alignment: .leading, spacing: 12) {
            if store.responseState == .waiting {
                HStack { ProgressView(); Text(CuadraoCopy.text("copy.cuadraoChatCanvas.5cacb9b5ac", spanish: es)) }
            } else {
                Label(CuadraoCopy.text("copy.cuadraoChatCanvas.3e35bd41d9", spanish: es), systemImage: "wifi.slash")
            }
            Text(CuadraoCopy.text("copy.cuadraoChatCanvas.c8ad78ec7b", spanish: es))
                .font(.caption).foregroundStyle(.secondary)
            Button(CuadraoCopy.text("copy.cuadraoChatCanvas.afd08c6d07", spanish: es)) { store.responseState = .complete }
        }.font(.subheadline)
    }

    private var previewNotice: some View {
        Text(CuadraoCopy.text("copy.cuadraoChatCanvas.85ea414e1f", spanish: es))
            .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            .multilineTextAlignment(.center).accessibilityIdentifier("chat.preview.notice")
    }

    private func composer(thread: Binding<String>) -> some View {
        VStack(spacing: 10) {
            if !active && store.current.focus == nil && !store.temporary && !focused && !tray && !store.voice.active && voiceMessage.state == .idle {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(CanvasChatExample.allCases) { sample in
                            Button { if sample == .document { sheet = .attachment("doc") } else { store.send(example: sample, spanish: es) } } label: {
                                Text(sample.title(es)).font(.subheadline).padding(.horizontal, 16).frame(minHeight: 44)
                                    .overlay { Capsule().stroke(WelcomePalette.separator, lineWidth: 1) }.contentShape(Rectangle())
                            }.buttonStyle(.plain)
                        }
                    }.padding(.horizontal, 20)
                }
            }
            VStack(alignment: .leading, spacing: 12) {
                if let focus = store.current.focus {
                    CanvasChatFocusChip(focus: focus, spanish: es) { store.current.focus = nil }
                }
                if store.voice.active {
                    CuadraoVoiceBar(voice: store.voice, spanish: es, embedded: true)
                    Divider().overlay(WelcomePalette.pine.opacity(0.12))
                }
                if voiceMessage.state == .review || voiceMessage.state == .submitted {
                    CuadraoVoiceMessagePanel(message: voiceMessage, spanish: es)
                }
                if !store.current.attachments.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            ForEach(store.current.attachments) { item in
                                CanvasChatAttachmentChip(item: item, spanish: es) { store.current.attachments.removeAll { $0.id == item.id } }
                            }
                        }
                    }
                }
                TextField(holdOnComposer ? "" : (CuadraoCopy.text("copy.cuadraoChatCanvas.ea17dd71c5", spanish: es)), text: thread, axis: .vertical)
                    .font(.body).lineLimit(1...6).focused($focused)
                    .padding(.horizontal, 6).padding(.top, 4).frame(minHeight: 44)
                    .accessibilityIdentifier("chat-composer")
                    .accessibilityHidden(holdOnComposer)
                    .disabled(voiceMessage.state == .recording || voiceMessage.state == .review)
                    .overlay {
                        if holdOnComposer {
                            CuadraoVoiceEntry(spanish: es, cancelArmed: voiceMessage.cancelArmed, composer: true,
                                tap: { focused = true }, beginHold: { beginVoiceMessage(held: true) },
                                drag: { voiceMessage.drag(leftwardDistance: $0, upwardDistance: $1) },
                                release: { voiceMessage.release(); voiceEntryLearned = true },
                                cancel: { voiceMessage.cancel() }, accessibleRecord: { beginVoiceMessage(held: false) })
                        }
                    }
                HStack {
                    control(tray ? "xmark" : "plus", tray ? (CuadraoCopy.text("copy.cuadraoChatCanvas.898ae61c3b", spanish: es)) : (CuadraoCopy.text("copy.cuadraoChatCanvas.cd9f7a1192", spanish: es)), id: "chat-attach") {
                        guard voiceMessage.state != .recording else { return }
                        focused = false
                        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { tray.toggle() }
                    }
                    Spacer()
                    if ready {
                        Button { focused = false; tray = false; store.send(spanish: es) } label: {
                            Image(systemName: "arrow.up").font(.system(size: 19, weight: .semibold))
                                .foregroundStyle(WelcomePalette.onAccent).frame(width: 44, height: 44)
                                .background(WelcomePalette.pine, in: Circle())
                        }.accessibilityLabel(CuadraoCopy.text("copy.cuadraoChatCanvas.9318acd61f", spanish: es)).accessibilityIdentifier("chat-send")
                            .disabled(voiceMessage.state == .recording || voiceMessage.state == .review)
                    } else if !store.voice.active {
                        CuadraoVoiceEntry(spanish: es, cancelArmed: voiceMessage.cancelArmed, tap: {
                            guard voiceMessage.state != .recording, voiceMessage.state != .review else { return }
                            focused = false; tray = false; voiceMessage.cancel(); voiceEntryLearned = true
                            store.voice.start()
                        }, beginHold: { beginVoiceMessage(held: true) }, drag: { voiceMessage.drag(leftwardDistance: $0, upwardDistance: $1) },
                           release: { voiceMessage.release(); voiceEntryLearned = true }, cancel: { voiceMessage.cancel() },
                           accessibleRecord: { beginVoiceMessage(held: false) })
                            .frame(width: 44, height: 44)
                    }
                }
                if tray && voiceMessage.state != .recording {
                    Divider()
                    if receiptWorkspace != nil, !store.temporary {
                        Button { tray = false; savedReceipts = true } label: {
                            Label(CuadraoCopy.text("copy.cuadraoChatCanvas.d4f38a690a", spanish: es), systemImage: "receipt").frame(minHeight: 44)
                        }.accessibilityIdentifier("chat-saved-receipts")
                    }
                    HStack(spacing: 8) {
                        attachmentButton("doc.viewfinder", CuadraoCopy.text("copy.cuadraoChatCanvas.61350196c6", spanish: es))
                        attachmentButton("photo", CuadraoCopy.text("copy.cuadraoChatCanvas.6ac14f4075", spanish: es))
                        attachmentButton("doc", CuadraoCopy.text("copy.cuadraoChatCanvas.cc29162bd2", spanish: es))
                    }.padding(.bottom, 4)
                }
            }.padding(12).background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 26))
                .overlay {
                    if store.voice.active {
                        RoundedRectangle(cornerRadius: 26).stroke(WelcomePalette.pine.opacity(0.16), lineWidth: 1)
                    }
                }
                .padding(.horizontal, 16)
            if voiceMessage.tooShort {
                Text(CuadraoCopy.text("copy.cuadraoChatCanvas.4d7e9e8e2d", spanish: es))
                    .font(.caption).foregroundStyle(.secondary)
            } else if !voiceEntryLearned && !store.voice.active && !ready {
                Text(CuadraoCopy.text("copy.cuadraoChatCanvas.915ed9f9c1", spanish: es))
                    .font(.caption).foregroundStyle(.secondary).padding(.horizontal, 20)
            }
        }.padding(.top, 8).padding(.bottom, 8)
            .accessibilityHidden(voiceMessage.state == .recording)
    }

    private func beginVoiceMessage(held: Bool) {
        guard !store.voice.active else { return }
        focused = false; tray = false
        voiceMessage.begin(liveVoiceActive: store.voice.active, held: held)
    }

    private func attachmentButton(_ symbol: String, _ title: String) -> some View {
        Button {
            tray = false
            if symbol == "doc.viewfinder", let workspace = receiptWorkspace {
                if store.temporary { temporaryReceipt = true }
                else { workspace.capture(ReceiptOrigin(groupID: store.current.focus?.groupID, threadID: store.current.id), .scan) }
            } else { sheet = .attachment(symbol) }
        } label: {
            VStack(spacing: 9) { Image(systemName: symbol).font(.title3); Text(title).font(.caption) }
                .frame(maxWidth: .infinity, minHeight: 70).contentShape(Rectangle())
        }.buttonStyle(.plain)
    }
    private func control(_ symbol: String, _ label: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { Image(systemName: symbol).font(.system(size: 19)).frame(width: 44, height: 44).contentShape(Rectangle()) }
            .buttonStyle(.plain).accessibilityLabel(label).accessibilityIdentifier(id)
    }
}
