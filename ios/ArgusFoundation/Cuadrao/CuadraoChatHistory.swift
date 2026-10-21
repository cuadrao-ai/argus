import SwiftUI

/// Local design rows share their conversation objects with Chat and Search.
struct CuadraoChatHistory: View {
    let store: CuadraoChatPreview
    let spanish: Bool
    let open: (CanvasChatThread) -> Void
    let newChat: () -> Void
    @State private var query = ""
    @State private var scope = Scope.recent
    @State private var renaming: CanvasChatThread?
    @State private var renameDraft = ""
    @State private var showRename = false
    @State private var showDelete = false
    @State private var deleting: CanvasChatThread?
    private var es: Bool { spanish }
    private enum Scope: Int, CaseIterable { case recent, archived, deleted }

    private var rows: [CanvasChatThread] {
        let search = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return store.visibleThreads.filter {
            (scope == .deleted ? $0.deleted : !$0.deleted && $0.archived == (scope == .archived))
                && (search.isEmpty || $0.title.localizedStandardContains(search))
        }.sorted { ($0.lastMessageDate ?? .distantPast) > ($1.lastMessageDate ?? .distantPast) }
    }
    var body: some View {
        VStack(spacing: 12) {
            Picker(CuadraoCopy.text("copy.cuadraoChatHistory.94e3ec4d94", spanish: es), selection: $scope) {
                Text(CuadraoCopy.text("copy.cuadraoChatHistory.a75f08cffc", spanish: es)).tag(Scope.recent)
                Text(CuadraoCopy.text("copy.cuadraoChatHistory.e95aacbabf", spanish: es)).tag(Scope.archived)
                Text(CuadraoCopy.text("copy.cuadraoChatHistory.343f039743", spanish: es)).tag(Scope.deleted)
            }.pickerStyle(.segmented).padding(.horizontal, 24)
            List {
                if rows.isEmpty { empty }
                else if scope == .recent {
                    group(rows.filter(\.pinned), title: CuadraoCopy.text("copy.cuadraoChatHistory.5c9356bc6a", spanish: es))
                    group(rows.filter { !$0.pinned }, title: CuadraoCopy.text("copy.cuadraoChatHistory.a75f08cffc", spanish: es))
                } else { ForEach(rows) { row($0) } }
            }.listStyle(.plain).scrollContentBackground(.hidden)
                .searchable(text: $query, prompt: CuadraoCopy.text("copy.cuadraoChatHistory.8ee94305ef", spanish: es))
            Button(action: newChat) {
                Label { Text(CuadraoCopy.text("copy.cuadraoChatHistory.284b0cf53b", spanish: es)) } icon: {
                    Image("CuadraoNewChat").resizable().scaledToFit().frame(width: 20, height: 20)
                }.frame(minHeight: 44)
            }.accessibilityIdentifier("history-new")
            Text(CuadraoCopy.text("copy.cuadraoChatHistory.ae95f7287f", spanish: es))
                .font(.caption).foregroundStyle(.secondary).padding(.bottom, 16)
        }
        .alert(CuadraoCopy.text("copy.cuadraoChatHistory.be04335b17", spanish: es), isPresented: $showRename) {
            TextField(CuadraoCopy.text("copy.cuadraoChatHistory.d48f4627c6", spanish: es), text: $renameDraft)
            Button(CuadraoCopy.text("copy.cuadraoChatHistory.62a128b722", spanish: es), role: .cancel) { renaming = nil }
            Button(CuadraoCopy.text("copy.cuadraoChatHistory.553ab1bf1a", spanish: es)) {
                renaming?.title = String(renameDraft.trimmingCharacters(in: .whitespacesAndNewlines).prefix(80))
                renaming = nil
            }.disabled(renameDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .confirmationDialog(CuadraoCopy.text("copy.cuadraoChatHistory.49e8eab1d4", spanish: es), isPresented: $showDelete, titleVisibility: .visible) {
            Button(CuadraoCopy.text("copy.cuadraoChatHistory.63edcd617b", spanish: es), role: .destructive) {
                if let deleting { store.delete(deleting) }; deleting = nil
            }
        } message: { Text(CuadraoCopy.text("copy.cuadraoChatHistory.394d87c8ef", spanish: es)) }
    }

    @ViewBuilder private func group(_ items: [CanvasChatThread], title: String) -> some View {
        if !items.isEmpty {
            Section { ForEach(items) { row($0) } } header: {
                Text(title).font(.caption.weight(.medium)).textCase(nil).foregroundStyle(.secondary)
            }
        }
    }

    private func row(_ thread: CanvasChatThread) -> some View {
        Button { open(thread) } label: {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(thread.title.isEmpty ? (CuadraoCopy.text("copy.cuadraoChatHistory.284b0cf53b", spanish: es)) : thread.title)
                    .font(.body.weight(thread.unread ? .semibold : .regular)).lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 6) {
                    if thread.unread { Circle().fill(WelcomePalette.pine).frame(width: 6, height: 6) }
                    else if store.current.id == thread.id && !store.temporary {
                        Image(systemName: "checkmark").font(.caption2).foregroundStyle(WelcomePalette.pine)
                    }
                    if let date = thread.lastMessageDate { CuadraoChatDate(date: date, spanish: es) }
                }.accessibilityHidden(true)
            }.frame(minHeight: 52).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier("history-row-" + thread.id)
            .accessibilityLabel(thread.title.isEmpty ? (CuadraoCopy.text("copy.cuadraoChatHistory.284b0cf53b", spanish: es)) : thread.title)
            .accessibilityValue(accessibilityValue(thread))
            .accessibilityActions { actions(thread) }
            .padding(.vertical, 4)
            .listRowInsets(EdgeInsets(top: 0, leading: 24, bottom: 0, trailing: 24))
            .listRowBackground(WelcomePalette.background).foregroundStyle(WelcomePalette.ink)
            .contextMenu { actions(thread) }
            .swipeActions(edge: .leading, allowsFullSwipe: true) {
                if scope == .recent {
                    Button { thread.pinned.toggle() } label: {
                        Label(thread.pinned ? (CuadraoCopy.text("copy.cuadraoChatHistory.beaa2b609a", spanish: es)) : (CuadraoCopy.text("copy.cuadraoChatHistory.a470d7a873", spanish: es)), systemImage: thread.pinned ? "pin.slash" : "pin")
                    }.tint(Color(red: 0.62, green: 0.36, blue: 0.08))
                }
            }
            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                if scope == .recent {
                    Button { store.archive(thread) } label: { Label(CuadraoCopy.text("copy.cuadraoChatHistory.0960027352", spanish: es), systemImage: "archivebox") }
                        .tint(Color(red: 0.34, green: 0.41, blue: 0.47))
                } else {
                    Button { store.restore(thread) } label: { Label(CuadraoCopy.text("copy.cuadraoChatHistory.e203d01b16", spanish: es), systemImage: "arrow.uturn.backward") }
                        .tint(WelcomePalette.pine)
                }
            }
    }

    private func accessibilityValue(_ thread: CanvasChatThread) -> String {
        let state = thread.deleted ? (CuadraoCopy.text("copy.cuadraoChatHistory.f6831c7566", spanish: es))
            : thread.unread ? (CuadraoCopy.text("copy.cuadraoChatHistory.d2e70c1b3e", spanish: es))
            : store.current.id == thread.id && !store.temporary ? (CuadraoCopy.text("copy.cuadraoChatHistory.cf81fc1799", spanish: es)) : nil
        return [state, thread.lastMessageDate.map { CanvasChatRecency.label($0, spanish: es) }]
            .compactMap { $0 }.joined(separator: ", ")
    }

    @ViewBuilder private func actions(_ thread: CanvasChatThread) -> some View {
        if thread.deleted {
            Button(CuadraoCopy.text("copy.cuadraoChatHistory.e203d01b16", spanish: es), systemImage: "arrow.uturn.backward") { store.restore(thread) }
        } else {
            Button(thread.unread ? (CuadraoCopy.text("copy.cuadraoChatHistory.7f84db9dae", spanish: es)) : (CuadraoCopy.text("copy.cuadraoChatHistory.1194ea54ec", spanish: es)), systemImage: thread.unread ? "envelope.open" : "envelope") { thread.unread.toggle() }
            Button(thread.pinned ? (CuadraoCopy.text("copy.cuadraoChatHistory.beaa2b609a", spanish: es)) : (CuadraoCopy.text("copy.cuadraoChatHistory.a470d7a873", spanish: es)), systemImage: thread.pinned ? "pin.slash" : "pin") { thread.pinned.toggle() }
            Button(CuadraoCopy.text("copy.cuadraoChatHistory.be04335b17", spanish: es), systemImage: "pencil") { renameDraft = thread.title; renaming = thread; showRename = true }
            if thread.archived {
                Button(CuadraoCopy.text("copy.cuadraoChatHistory.e203d01b16", spanish: es), systemImage: "arrow.uturn.backward") { store.restore(thread) }
            } else {
                Button(CuadraoCopy.text("copy.cuadraoChatHistory.0960027352", spanish: es), systemImage: "archivebox") { store.archive(thread) }
            }
            Divider()
            Button(CuadraoCopy.text("copy.cuadraoChatHistory.534547cf82", spanish: es), systemImage: "trash", role: .destructive) { deleting = thread; showDelete = true }
        }
    }

    private var empty: some View {
        let searching = !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return ContentUnavailableView(searching ? (CuadraoCopy.text("copy.cuadraoChatHistory.2448aace19", spanish: es)) : (CuadraoCopy.text("copy.cuadraoChatHistory.8b0c465c43", spanish: es)),
            systemImage: searching ? "magnifyingglass" : "bubble.left.and.bubble.right",
            description: Text(searching ? (CuadraoCopy.text("copy.cuadraoChatHistory.647ea08be0", spanish: es))
                : (CuadraoCopy.text("copy.cuadraoChatHistory.7d25bb23b0", spanish: es))))
    }
}
