import SwiftUI

struct CanvasChartFocus: Equatable {
    enum Metric: String { case balance, activity }
    enum Presentation: String { case evolution, distribution }
    let spaceID: String
    let spaceTitle: String
    let currency: String
    let interval: DateInterval
    let periodTitle: String
    let metric: Metric
    let presentation: Presentation
    enum Selection: Equatable {
        case expenseCategory(id: String, title: String)
        case accountKind(id: String, title: String)
        var title: String { switch self { case .expenseCategory(_, let title), .accountKind(_, let title): title } }
    }
    var selection: Selection?
    var inspectedInterval: DateInterval?
    var inspectedTitle: String?
}

enum CanvasChatFocus: Equatable {
    case account(id: UUID, title: String)
    case activity(id: UUID, title: String)
    case plan(id: UUID, title: String)
    case group(id: UUID, title: String)
    case receipt(id: UUID, title: String)
    case chart(CanvasChartFocus)

    var groupID: UUID? { if case .group(let id, _) = self { id } else { nil } }
    var symbol: String {
        switch self {
        case .account: "creditcard"
        case .activity: "arrow.up.arrow.down"
        case .plan, .group: "square.stack"
        case .receipt: "receipt"
        case .chart(let chart): chart.presentation == .distribution ? "chart.bar.xaxis" : "chart.xyaxis.line"
        }
    }
    func title(_ spanish: Bool) -> String {
        switch self {
        case .account(_, let title), .activity(_, let title), .plan(_, let title),
             .group(_, let title), .receipt(_, let title): title
        case .chart(let chart):
            [chart.metric == .activity ? (CuadraoCopy.text("copy.cuadraoChatContext.fea64e51c2", spanish: spanish)) : CuadraoCopy.text("copy.cuadraoChatContext.02e2073456", spanish: spanish),
             chart.spaceTitle, chart.currency, chart.periodTitle,
             chart.presentation == .distribution ? (CuadraoCopy.text("copy.cuadraoChatContext.af34dc6583", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoChatContext.382a06960e", spanish: spanish)),
             chart.selection?.title, chart.inspectedTitle].compactMap { $0 }.joined(separator: " · ")
        }
    }
}

private struct CuadraoChatKey: EnvironmentKey {
    static let defaultValue: CuadraoChatPreview? = nil
}
extension EnvironmentValues {
    var cuadraoChat: CuadraoChatPreview? {
        get { self[CuadraoChatKey.self] }
        set { self[CuadraoChatKey.self] = newValue }
    }
}
extension View {
    func contextualCuadrao(focus: Binding<CanvasChatFocus?>, spanish: Bool) -> some View {
        modifier(CuadraoContextPresentation(focus: focus, spanish: spanish))
    }
}
private struct CuadraoContextPresentation: ViewModifier {
    @Environment(\.cuadraoChat) private var chat
    @Environment(\.receiptWorkspace) private var receipts
    @Binding var focus: CanvasChatFocus?
    let spanish: Bool
    @State private var presented = false
    @State private var presentationID = UUID()
    func body(content: Content) -> some View {
        content
            .onChange(of: focus) { _, value in
                guard let value, let chat else { return }
                chat.selectFocus(value)
                chat.presentContext(presentationID)
                presented = true
            }
            .sheet(isPresented: $presented, onDismiss: { chat?.dismissContext(presentationID); focus = nil }) {
                if let chat {
                    CuadraoContextConversation(chat: chat, receipts: receipts, spanish: spanish, presentationID: presentationID)
                        .presentationDetents([.large]).presentationDragIndicator(.visible)
                }
            }
    }
}
private struct CuadraoContextConversation: View {
    let chat: CuadraoChatPreview
    let receipts: ReceiptWorkspace?
    let spanish: Bool
    let presentationID: UUID
    @State private var editing = false
    @State private var receiptRoute: ReceiptRoute?
    @Environment(\.dismiss) private var dismiss
    private var workspace: ReceiptWorkspace? {
        guard let receipts else { return nil }
        return ReceiptWorkspace(receipts: receipts.receipts, groups: receipts.groups, accounts: receipts.accounts,
            chat: chat, capture: { receiptRoute = .capture($0, $1) }, open: { receiptRoute = .review($0) })
    }
    var body: some View {
        CuadraoChatCanvas(store: chat, spanish: spanish, editing: $editing, contextual: true, close: { dismiss() })
            .environment(\.receiptWorkspace, workspace)
            .receiptPresentation(route: $receiptRoute, workspace: workspace, spanish: spanish)
            .cuadraoVoicePresentation(chat: chat, spanish: spanish, ownsPresentation: chat.voiceContextOwner == presentationID,
                keyboard: { chat.voice.presentation = .keyboard })
            .interactiveDismissDisabled(chat.voiceMessage.state == .recording)
            .tint(WelcomePalette.pine)
    }
}
struct CanvasChatFocusChip: View {
    let focus: CanvasChatFocus
    let spanish: Bool
    var remove: (() -> Void)?
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: focus.symbol).accessibilityHidden(true)
            Text(focus.title(spanish)).font(CuadraoTypography.supporting).fixedSize(horizontal: false, vertical: true)
            if let remove {
                Spacer(minLength: 0)
                Button(action: remove) { Image(systemName: "xmark").frame(width: 44, height: 44).contentShape(Rectangle()) }
                    .buttonStyle(.plain)
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoChatContext.d7fd55178d", spanish: spanish))
                    .accessibilityIdentifier("chat-focus-remove")
            }
        }.foregroundStyle(WelcomePalette.pine).padding(.leading, 12).padding(.trailing, remove == nil ? 12 : 0)
            .padding(.vertical, remove == nil ? 10 : 0)
            .background(WelcomePalette.pine.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))
            .accessibilityElement(children: .contain).accessibilityIdentifier("chat-focus-chip")
    }
}

struct CanvasChartAsk: View {
    let context: CanvasChartFocus
    let spanish: Bool
    @State private var focus: CanvasChatFocus?
    var body: some View {
        Button { focus = .chart(context) } label: {
            Label(CuadraoCopy.text("copy.cuadraoAccountCanvas.b44a9adeb4", spanish: spanish), systemImage: "bubble").frame(minHeight: 44)
        }.font(CuadraoTypography.supporting).accessibilityIdentifier("insight-open-chat")
            .contextualCuadrao(focus: $focus, spanish: spanish)
    }
}
