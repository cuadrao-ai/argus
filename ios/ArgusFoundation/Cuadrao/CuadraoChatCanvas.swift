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
                    .toolbar { CuadraoDoneToolbar(title: es ? "Listo" : "Done") { savedReceipts = false } }
                }
            }
        }
        .confirmationDialog(es ? "Guardar fuera del chat temporal" : "Save outside temporary chat", isPresented: $temporaryReceipt, titleVisibility: .visible) {
            Button(es ? "Guardar recibo" : "Save receipt") { receiptWorkspace?.capture(ReceiptOrigin(groupID: nil, threadID: nil), .scan) }
        } message: { Text(es ? "El recibo se guardará en este dispositivo aunque cierres este chat temporal." : "The receipt will stay on this device even after this temporary chat closes.") }
        .confirmationDialog(es ? "¿Terminar el chat temporal?" : "End temporary chat?", isPresented: $ending, titleVisibility: .visible) {
            Button(es ? "Terminar y crear chat" : "End and create chat", role: .destructive) { store.leaveTemporary(for: .newRegular) }
            Button(es ? "Seguir aquí" : "Stay here", role: .cancel) {}
        } message: {
            Text(es ? "Se descartará esta conversación. Tu chat anterior quedará intacto." : "This conversation will be discarded. Your previous chat stays intact.")
        }
    }

    private var header: some View {
        HStack(spacing: 0) {
            if let close {
                control("xmark", es ? "Cerrar Cuadrao" : "Close Cuadrao", id: "chat-context-close", action: close)
            }
            control("clock.arrow.circlepath", es ? "Chats recientes" : "Recent chats", id: "chat-history") { sheet = .history }
            if active || store.temporary {
                Button {
                    if store.hasTemporaryContent { ending = true }
                    else { store.leaveTemporary(for: .newRegular) }
                } label: {
                    Image("CuadraoNewChat").resizable().scaledToFit().frame(width: 20, height: 20)
                        .frame(width: 44, height: 44).contentShape(Rectangle())
                }.buttonStyle(.plain)
                    .accessibilityLabel(store.temporary ? (es ? "Nuevo chat normal" : "New regular chat") : (es ? "Nuevo chat" : "New chat"))
                    .accessibilityIdentifier("chat-new")
            } else { Color.clear.frame(width: 44, height: 44) }
            if focused {
                control("keyboard.chevron.compact.down", es ? "Ocultar teclado" : "Hide keyboard", id: "chat-dismiss-keyboard") {
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
                    .accessibilityLabel(es ? "Compartir chat" : "Share chat")
                    .accessibilityIdentifier("chat-share")
                Menu {
                    Button(es ? "Cambiar nombre" : "Rename", systemImage: "pencil") { sheet = .rename }
                    Button(es ? (store.current.pinned ? "Desfijar" : "Fijar") : (store.current.pinned ? "Unpin" : "Pin"), systemImage: "pin") { store.current.pinned.toggle() }
                    Button(es ? "Marcar como no leído" : "Mark unread", systemImage: "envelope.badge") { store.current.unread = true }
                    Button(es ? "Archivar" : "Archive", systemImage: "archivebox") { store.archive(store.current) }
                    Button(es ? "Eliminar" : "Delete", systemImage: "trash", role: .destructive) { store.delete(store.current) }
                    Divider()
                    Button(es ? "Estados de vista previa" : "Preview states", systemImage: "slider.horizontal.3") { sheet = .states }
                } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                    .accessibilityLabel(es ? "Opciones del chat" : "Chat options")
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
                }.accessibilityLabel(store.temporary ? (es ? "Opciones del chat temporal" : "Temporary chat settings") : (es ? "Iniciar chat temporal" : "Start temporary chat"))
                    .accessibilityValue(store.temporary ? (es ? "Activo" : "Active") : "")
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
                        Text(es ? "Chat temporal" : "Temporary chat").font(CuadraoTypography.feature)
                        Text(CuadraoFirstRelease.shows(.memory)
                            ? (es ? "Fuera de tu historial.\nSin nuevas memorias." : "Outside your history.\nNo new memories.")
                            : (es ? "Fuera de tu historial." : "Outside your history."))
                            .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                        Button { sheet = .temporary } label: {
                            HStack(spacing: 6) {
                                Text(store.useContext ? (es ? "Con mi contexto" : "Using my context") : (es ? "Sin mi contexto" : "Without my context"))
                                Image(systemName: "chevron.down").font(.caption2)
                            }.font(.subheadline).frame(minHeight: 44)
                        }
                    } else {
                        CuadraoBrand().scaleEffect(0.85).accessibilityLabel("Cuadrao")
                        Text(store.current.focus?.groupID.flatMap { receiptWorkspace?.groups.group($0)?.name } ?? (es ? "¿Qué vemos hoy?" : "What shall we look at?"))
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
                            Label { Text((es ? "Temporal · " : "Temporary · ") + (store.useContext ? (es ? "Con mi contexto" : "Using my context") : (es ? "Sin mi contexto" : "Without my context"))) } icon: {
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
                    }.accessibilityLabel(es ? "Ir al último mensaje" : "Go to latest message").padding(.trailing, 24)
                }
            }
        }
    }

    private var responseState: some View {
        VStack(alignment: .leading, spacing: 12) {
            if store.responseState == .waiting {
                HStack { ProgressView(); Text(es ? "Preparando respuesta…" : "Preparing a response…") }
            } else {
                Label(es ? "No se pudo cargar la respuesta" : "The response could not load", systemImage: "wifi.slash")
            }
            Text(es ? "Estado de ejemplo. No hay una solicitud en curso." : "Example state. No request is running.")
                .font(.caption).foregroundStyle(.secondary)
            Button(es ? "Ver respuesta de ejemplo" : "Show example response") { store.responseState = .complete }
        }.font(.subheadline)
    }

    private var previewNotice: some View {
        Text(es ? "Vista previa del chat. Puedes probar ejemplos; no se envían mensajes ni se cambian tus cuentas."
             : "Chat preview. Try the examples; no messages are sent and your accounts stay unchanged.")
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
                TextField(holdOnComposer ? "" : (es ? "Escribe un mensaje" : "Write a message"), text: thread, axis: .vertical)
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
                    control(tray ? "xmark" : "plus", tray ? (es ? "Cerrar adjuntos" : "Close attachments") : (es ? "Adjuntar" : "Attach"), id: "chat-attach") {
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
                        }.accessibilityLabel(es ? "Enviar" : "Send").accessibilityIdentifier("chat-send")
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
                            Label(es ? "Recibos guardados" : "Saved receipts", systemImage: "receipt").frame(minHeight: 44)
                        }.accessibilityIdentifier("chat-saved-receipts")
                    }
                    HStack(spacing: 8) {
                        attachmentButton("doc.viewfinder", es ? "Escanear" : "Scan")
                        attachmentButton("photo", es ? "Foto" : "Photo")
                        attachmentButton("doc", es ? "Archivo" : "File")
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
                Text(es ? "Mantén un poco más para grabar." : "Hold a little longer to record.")
                    .font(.caption).foregroundStyle(.secondary)
            } else if !voiceEntryLearned && !store.voice.active && !ready {
                Text(es ? "Toca para conversar · Mantén para grabar" : "Tap to converse · Hold to record")
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
