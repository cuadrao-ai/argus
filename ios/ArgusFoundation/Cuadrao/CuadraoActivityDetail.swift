import SwiftUI

struct CuadraoActivityDetail: View {
    let data: CuadraoAccountsPreview
    let activityID: UUID
    let spanish: Bool
    let actions: (CanvasAccountSheet) -> Void
    let record: (UUID) -> Void
    @State private var chatFocus: CanvasChatFocus?
    @Environment(\.locale) private var locale

    var body: some View {
        Group {
            if let entry = data.activity.first(where: { $0.id == activityID }),
               let account = data.account(entry.accountID),
               !data.spaces.contains(where: { $0.id == account.spaceID && $0.deleted }) {
                ScrollView {
                    CanvasActivityDetailContent(value: CanvasActivityDetailValue(
                        title: entry.title,
                        amount: account.currency + " " + (entry.income ? "+" : "−") + CanvasMoney.format(entry.amount, currency: account.currency),
                        kind: entry.income ? (CuadraoCopy.text("copy.cuadraoAccountCanvas.68048ec6e6", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoAccountCanvas.705df72a66", spanish: spanish)),
                        date: entry.date.formatted(.dateTime.day().month(.wide).year().locale(locale)),
                        category: entry.income ? nil : CanvasActivityCategoryValue(title: entry.category.title(spanish), artwork: entry.category)),
                        spanish: spanish) {
                        NavigationLink {
                            CuadraoAccountCanvas(data: data, accountID: account.id, spanish: spanish, actions: actions, record: record)
                        } label: {
                            CanvasActivityAccountRowContent(title: account.displayName(spanish), detail: account.currency, artwork: account.kind)
                        }.buttonStyle(.plain).accessibilityIdentifier("activity-detail-account")
                        Button {
                            chatFocus = .activity(id: entry.id, title: entry.title)
                        } label: {
                            Label(CuadraoCopy.text("copy.cuadraoAccountCanvas.b44a9adeb4", spanish: spanish), systemImage: "bubble")
                                .font(.subheadline).frame(minHeight: 44).contentShape(Rectangle())
                        }.buttonStyle(.plain).foregroundStyle(WelcomePalette.pine)
                            .accessibilityIdentifier("activity-detail-ask")
                    }.padding(24)
                }.background(WelcomePalette.background)
            } else {
                ContentUnavailableView(CuadraoCopy.text("copy.cuadraoActivityDetail.1a8ab825c4", spanish: spanish), systemImage: "doc.text.magnifyingglass")
            }
        }.navigationTitle(CuadraoCopy.text("copy.cuadraoActivityDetail.4a9fb37375", spanish: spanish))
            .navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
            .contextualCuadrao(focus: $chatFocus, spanish: spanish)
    }
}
