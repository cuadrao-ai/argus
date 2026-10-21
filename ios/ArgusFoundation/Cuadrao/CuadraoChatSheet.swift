import SwiftUI

enum CanvasChatSheet: Identifiable {
    case history, rename, temporary, sources, calculation, share, states
    case attachment(String)
    var id: String { String(describing: self) }
}

struct CuadraoChatSheet: View {
    let destination: CanvasChatSheet
    let store: CuadraoChatPreview
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var endTemporary = false
    @State private var pendingExit = CuadraoChatPreview.Exit.returnToRegular
    private var es: Bool { spanish }
    private var heading: String {
        switch destination {
        case .history: "Chats"
        case .rename: CuadraoCopy.text("copy.cuadraoChatSheet.be04335b17", spanish: es)
        case .temporary: CuadraoCopy.text("copy.cuadraoChatSheet.9d6f2322f8", spanish: es)
        case .sources: CuadraoCopy.text("copy.cuadraoChatSheet.98180ee4aa", spanish: es)
        case .calculation: CuadraoCopy.text("copy.cuadraoChatSheet.cf5a9b0030", spanish: es)
        case .share: CuadraoCopy.text("copy.cuadraoChatSheet.ebf2baf694", spanish: es)
        case .states: CuadraoCopy.text("copy.cuadraoChatSheet.50a58652a9", spanish: es)
        case .attachment: CuadraoCopy.text("copy.cuadraoChatSheet.dd02d37730", spanish: es)
        }
    }
    var body: some View {
        NavigationStack {
            Group {
                if case .history = destination {
                    CuadraoChatHistory(store: store, spanish: es, open: { requestExit(.open($0)) }, newChat: { requestExit(.newRegular) })
                }
                else { ScrollView { content.padding(24).frame(maxWidth: .infinity, alignment: .leading) } }
            }
            .background(WelcomePalette.background).foregroundStyle(WelcomePalette.ink)
            .navigationTitle(heading).navigationBarTitleDisplayMode(.inline)
            .toolbar { CuadraoDoneToolbar(title: CuadraoCopy.text("copy.cuadraoChatSheet.bd6b05a681", spanish: es)) { dismiss() } }
        }
        .presentationDragIndicator(.visible)
        .onAppear { title = store.current.title }
        .confirmationDialog(CuadraoCopy.text("copy.cuadraoChatSheet.b5ea512511", spanish: es), isPresented: $endTemporary, titleVisibility: .visible) {
            Button(CuadraoCopy.text("copy.cuadraoChatSheet.adbbfa6b0f", spanish: es), role: .destructive) { finishExit() }
            Button(CuadraoCopy.text("copy.cuadraoChatSheet.32a630a211", spanish: es), role: .cancel) {}
        } message: { Text(CuadraoCopy.text("copy.cuadraoChatSheet.4017ca0336", spanish: es)) }
    }

    @ViewBuilder private var content: some View {
        @Bindable var store = store
        VStack(alignment: .leading, spacing: 24) {
            switch destination {
            case .history: EmptyView()
            case .rename:
                TextField(CuadraoCopy.text("copy.cuadraoChatSheet.d48f4627c6", spanish: es), text: $title).textFieldStyle(.roundedBorder)
                action(CuadraoCopy.text("copy.cuadraoChatSheet.553ab1bf1a", spanish: es)) { store.current.title = String(title.trimmingCharacters(in: .whitespacesAndNewlines).prefix(80)); dismiss() }
                    .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            case .temporary:
                CuadraoTemporaryChatSettings(store: store, spanish: es) { requestExit(.returnToRegular) }
            case .calculation:
                Text("DOP " + CanvasChatCalculation.amount(CanvasChatCalculation.total)).font(CuadraoTypography.amount)
                detail(CuadraoCopy.text("copy.cuadraoChatSheet.db4c3e00e8", spanish: es), "DOP " + CanvasChatCalculation.amount(CanvasChatCalculation.monthly))
                detail(CuadraoCopy.text("copy.cuadraoChatSheet.e4558bee29", spanish: es), String(CanvasChatCalculation.months))
                Divider()
                Text(CuadraoCopy.text("copy.cuadraoChatSheet.dd9303bf15", spanish: es))
                previewNote
            case .sources:
                Label(CuadraoCopy.text("copy.cuadraoChatSheet.5e4a5a023f", spanish: es), systemImage: "book")
                Text(CuadraoCopy.text("copy.cuadraoChatSheet.2712c66473", spanish: es))
                Text(CuadraoCopy.text("copy.cuadraoChatSheet.36de23a94b", spanish: es)).foregroundStyle(.secondary)
            case .share:
                Text(store.current.title).font(.title3)
                Text(CuadraoCopy.text("copy.cuadraoChatSheet.22acf8b60e", spanish: es))
                previewNote
            case .states:
                Text(CuadraoCopy.text("copy.cuadraoChatSheet.f454963e45", spanish: es))
                ForEach(CanvasChatResponseState.allCases, id: \.self) { value in
                    Button { store.responseState = value; dismiss() } label: {
                        HStack {
                            Text(stateTitle(value)); Spacer()
                            if store.responseState == value { Image(systemName: "checkmark") }
                        }.frame(minHeight: 44)
                    }
                }
            case .attachment(let symbol):
                Image(systemName: symbol).font(.system(size: 36)).foregroundStyle(WelcomePalette.pine)
                let name = symbol == "doc" ? (CuadraoCopy.text("copy.cuadraoChatSheet.ca2f2bd73f", spanish: es)) : (CuadraoCopy.text("copy.cuadraoChatSheet.941cb12fc5", spanish: es))
                Text(name).font(.title3)
                Text(CuadraoCopy.text("copy.cuadraoChatSheet.e3548be203", spanish: es))
                action(CuadraoCopy.text("copy.cuadraoChatSheet.6fd1ba1633", spanish: es)) {
                    store.current.attachments.append(CanvasChatAttachment(name: name, symbol: symbol))
                    dismiss()
                }
                Text(CuadraoCopy.text("copy.cuadraoChatSheet.9b1aac232a", spanish: es)).font(.footnote).foregroundStyle(.secondary)
            }
        }
    }

    private func requestExit(_ destination: CuadraoChatPreview.Exit) {
        pendingExit = destination
        if store.hasTemporaryContent { endTemporary = true } else { finishExit() }
    }
    private func finishExit() { store.leaveTemporary(for: pendingExit); dismiss() }
    private var previewNote: some View {
        Text(CuadraoCopy.text("copy.cuadraoChatSheet.d331ecc43f", spanish: es))
            .font(.footnote).foregroundStyle(.secondary)
    }
    private func detail(_ label: String, _ value: String) -> some View {
        HStack { Text(label).foregroundStyle(.secondary); Spacer(); Text(value).monospacedDigit() }
    }
    private func action(_ title: String, _ perform: @escaping () -> Void) -> some View {
        Button(action: perform) { Text(title).font(.body.weight(.semibold)).frame(maxWidth: .infinity, minHeight: 52)
            .foregroundStyle(WelcomePalette.onAccent).background(WelcomePalette.pine, in: RoundedRectangle(cornerRadius: 16)) }
    }
    private func stateTitle(_ value: CanvasChatResponseState) -> String {
        switch value {
        case .complete: CuadraoCopy.text("copy.cuadraoChatSheet.a2728a2e9f", spanish: es)
        case .waiting: CuadraoCopy.text("copy.cuadraoChatSheet.95846cdde3", spanish: es)
        case .failed: CuadraoCopy.text("copy.cuadraoChatSheet.b165cd53c9", spanish: es)
        }
    }
}
