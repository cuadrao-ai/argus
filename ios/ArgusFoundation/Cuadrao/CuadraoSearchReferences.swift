import SwiftUI

/// Presentation fixtures from the locked search study, not stored chats/files/memory.
enum CanvasSearchKind: CaseIterable {
    case all, accounts, activity, plans, chats, files, memory
    func title(_ es: Bool) -> String {
        switch self {
        case .all: es ? "Todo" : "All"
        case .accounts: es ? "Cuentas" : "Accounts"
        case .activity: es ? "Movimientos" : "Activity"
        case .plans: es ? "Planes" : "Plans"
        case .chats: "Chats"
        case .files: es ? "Archivos" : "Files"
        case .memory: es ? "Memoria" : "Memory"
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
             title: es ? "Fondo de emergencia" : "Emergency fund",
             detail: es ? "Meta de ahorro · Solo yo" : "Savings goal · Only me",
             content: es ? "Un fondo para gastos inesperados." : "A fund for unexpected expenses.",
             source: es ? "Plan de ejemplo" : "Example plan"),
        Self(id: "chat-cd", kind: .chats,
             title: es ? "Entender los certificados de depósito" : "Understanding certificates of deposit",
             detail: es ? "Conversación · Solo yo" : "Conversation · Only me",
             content: es ? "Estoy aprendiendo cómo funcionan los certificados de depósito." : "I am learning how certificates of deposit work.",
             source: es ? "Mensaje de ejemplo" : "Example message"),
        Self(id: "chat-spending", kind: .chats,
             title: es ? "Mis gastos de septiembre" : "My September spending",
             detail: es ? "Conversación · Solo yo" : "Conversation · Only me",
             content: es ? "Quiero entender en qué se fue mi dinero este mes." : "I want to understand where my money went this month.",
             source: es ? "Mensaje de ejemplo" : "Example message"),
        Self(id: "file-statement", kind: .files,
             title: es ? "Estado de cuenta · Septiembre.pdf" : "Statement · September.pdf",
             detail: es ? "PDF · Solo yo" : "PDF · Only me",
             content: es ? "La vista del documento y sus movimientos revisados se conectarán aquí. Este ejemplo no contiene un PDF real." : "The document and its reviewed activity will connect here. This example does not contain a real PDF.",
             source: es ? "Archivo de ejemplo" : "Example file"),
        Self(id: "memory-learning", kind: .memory,
             title: es ? "Interés de aprendizaje" : "Learning interest",
             detail: es ? "Contexto confirmado · Solo yo" : "Confirmed context · Only me",
             content: es ? "Estoy aprendiendo cómo funcionan los certificados de depósito." : "I am learning how certificates of deposit work.",
             source: es ? "Confirmado en una conversación de ejemplo" : "Confirmed in an example conversation")
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
                        Label(spanish ? "Ver conversación de origen" : "View source conversation", systemImage: "bubble.left")
                            .frame(minHeight: 44)
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(24)
        }.background(WelcomePalette.background)
            .navigationTitle(item.kind.title(spanish)).navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar)
    }
}
