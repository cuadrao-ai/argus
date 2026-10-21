import SwiftUI

extension View {
    @ViewBuilder
    func connectedReceiptDrafts(userID: UUID?, chat: CuadraoChatPreview, spanish: Bool) -> some View {
        #if DEBUG
        if let userID, CuadraoFirstRelease.showsReceiptCapture {
            modifier(ConnectedReceiptDrafts(userID: userID, chat: chat, spanish: spanish))
                .id(userID)
        } else {
            self
        }
        #else
        self
        #endif
    }
}

#if DEBUG
private struct ConnectedReceiptDrafts: ViewModifier {
    let chat: CuadraoChatPreview
    let spanish: Bool
    @State private var receipts: CuadraoReceiptStore
    @State private var groups: CuadraoGroupPreview
    @State private var accounts: CuadraoAccountsPreview
    @State private var route: ReceiptRoute?

    init(userID: UUID, chat: CuadraoChatPreview, spanish: Bool) {
        self.chat = chat
        self.spanish = spanish
        _receipts = State(initialValue: CuadraoReceiptStore.connectedDrafts(userID: userID))
        _groups = State(initialValue: CuadraoGroupPreview(spanish: spanish, defaults: nil, empty: true))
        _accounts = State(initialValue: CuadraoAccountsPreview(populated: false, spanish: spanish))
    }

    private var workspace: ReceiptWorkspace {
        ReceiptWorkspace(receipts: receipts, groups: groups, accounts: accounts, chat: chat,
            capture: { route = .capture($0, $1) }, open: { route = .review($0) })
    }

    func body(content: Content) -> some View {
        content
            .receiptPresentation(route: $route, workspace: workspace, spanish: spanish)
            .environment(\.receiptWorkspace, workspace)
            .environment(\.cuadraoChat, chat)
    }
}
#endif
