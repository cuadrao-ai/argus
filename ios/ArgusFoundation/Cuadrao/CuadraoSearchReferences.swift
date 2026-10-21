import SwiftUI

/// Presentation fixtures from the locked search study, not stored chats/files/memory.
enum CanvasSearchKind: CaseIterable {
    case all, accounts, activity, plans, chats, files, memory
    func title(_ es: Bool) -> String {
        switch self {
        case .all: CuadraoCopy.text("copy.cuadraoSearchReferences.64c04b1430", spanish: es)
        case .accounts: CuadraoCopy.text("copy.cuadraoSearchReferences.8cce5d02a3", spanish: es)
        case .activity: CuadraoCopy.text("copy.cuadraoSearchReferences.f7d6ac01ad", spanish: es)
        case .plans: CuadraoCopy.text("copy.cuadraoSearchReferences.5132fbb42e", spanish: es)
        case .chats: CuadraoCopy.text("copy.search.chats", spanish: es)
        case .files: CuadraoCopy.text("copy.cuadraoSearchReferences.2cec6f3871", spanish: es)
        case .memory: CuadraoCopy.text("copy.cuadraoSearchReferences.7fa6d06e03", spanish: es)
        }
    }
}

extension CanvasSearchKind {
    /// What the connected Search offers. With no assistant there are no AI chats, and no files or memory
    /// either, so those chips (each an "unavailable" dead end) are not shown.
    static func connected(hasAssistant: Bool) -> [CanvasSearchKind] {
        let withoutAssistant: Set<CanvasSearchKind> = [.chats, .files, .memory]
        return allCases.filter { hasAssistant ? $0 != .memory : !withoutAssistant.contains($0) }
    }
}

struct CanvasSearchReference: Identifiable {
    let id: String
    let kind: CanvasSearchKind
    let title: String
    let detail: String
    let content: String
    let source: String

    static func examples(_ es: Bool) -> [Self] { [
        Self(id: "plan-savings", kind: .plans,
             title: CuadraoCopy.text("copy.cuadraoSearchReferences.9057658f68", spanish: es),
             detail: CuadraoCopy.text("copy.cuadraoSearchReferences.0dabbf3e45", spanish: es),
             content: CuadraoCopy.text("copy.cuadraoSearchReferences.a6410d9e5f", spanish: es),
             source: CuadraoCopy.text("copy.cuadraoSearchReferences.a916e26bec", spanish: es)),
        Self(id: "chat-cd", kind: .chats,
             title: CuadraoCopy.text("copy.cuadraoSearchReferences.42f52e9b03", spanish: es),
             detail: CuadraoCopy.text("copy.cuadraoSearchReferences.964e5a1937", spanish: es),
             content: CuadraoCopy.text("copy.cuadraoSearchReferences.4f6497e9da", spanish: es),
             source: CuadraoCopy.text("copy.cuadraoSearchReferences.f4a7f50645", spanish: es)),
        Self(id: "chat-spending", kind: .chats,
             title: CuadraoCopy.text("copy.cuadraoSearchReferences.06d353e9b1", spanish: es),
             detail: CuadraoCopy.text("copy.cuadraoSearchReferences.964e5a1937", spanish: es),
             content: CuadraoCopy.text("copy.cuadraoSearchReferences.36e2933137", spanish: es),
             source: CuadraoCopy.text("copy.cuadraoSearchReferences.f4a7f50645", spanish: es)),
        Self(id: "file-statement", kind: .files,
             title: CuadraoCopy.text("copy.cuadraoSearchReferences.f710802f95", spanish: es),
             detail: CuadraoCopy.text("copy.cuadraoSearchReferences.0c528f7086", spanish: es),
             content: CuadraoCopy.text("copy.cuadraoSearchReferences.9e77fe0e95", spanish: es),
             source: CuadraoCopy.text("copy.cuadraoSearchReferences.2990c63b3f", spanish: es)),
        Self(id: "memory-learning", kind: .memory,
             title: CuadraoCopy.text("copy.cuadraoSearchReferences.c3439dafce", spanish: es),
             detail: CuadraoCopy.text("copy.cuadraoSearchReferences.caaa2be2ed", spanish: es),
             content: CuadraoCopy.text("copy.cuadraoSearchReferences.4f6497e9da", spanish: es),
             source: CuadraoCopy.text("copy.cuadraoSearchReferences.d8d6649952", spanish: es))
    ] }
}

struct CuadraoSearchReferenceDetail: View {
    let item: CanvasSearchReference
    let spanish: Bool
    let source: CanvasSearchReference?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text(item.title).font(CuadraoTypography.section)
                Text(item.detail).font(.subheadline).foregroundStyle(.secondary)
                Divider()
                Text(item.content).font(.body).textSelection(.enabled)
                Text(item.source).font(.footnote).foregroundStyle(.secondary)
                if let source {
                    NavigationLink {
                        CuadraoSearchReferenceDetail(item: source, spanish: spanish, source: nil)
                    } label: {
                        Label(CuadraoCopy.text("copy.cuadraoSearchReferences.83ce3236ce", spanish: spanish), systemImage: "bubble.left")
                            .frame(minHeight: 44)
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(24)
        }.background(WelcomePalette.background)
            .navigationTitle(item.kind.title(spanish)).navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar)
    }
}
