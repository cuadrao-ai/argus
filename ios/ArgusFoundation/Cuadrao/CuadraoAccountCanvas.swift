import SwiftUI

struct CuadraoAccountCanvas: View {
    let data: CuadraoAccountsPreview
    let accountID: UUID
    let spanish: Bool
    let actions: (CanvasAccountSheet) -> Void
    let record: (UUID) -> Void
    @State private var showingBalanceInfo = false
    @State private var refreshedAt: Date?
    @State private var chatFocus: CanvasChatFocus?
    @Environment(\.locale) private var locale

    var body: some View {
        if let account = data.account(accountID) {
            ScrollView {
                CuadraoLastUpdated(date: refreshedAt, spanish: spanish).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 24)
                CanvasAccountDetailContent(
                    value: CanvasAccountDetailValue(title: account.displayName(spanish), artwork: account.kind,
                        balanceLabel: account.balanceLabel(spanish), currency: account.currency,
                        amount: account.balance.map { CanvasMoney.format($0, currency: account.currency) } ?? "—",
                        freshness: account.balance == nil ? (CuadraoCopy.text("copy.connectedAccountPresentation.13cc4cd5c1", spanish: spanish))
                            : (CuadraoCopy.text("copy.cuadraoAccountCanvas.cd64f83c7e", spanish: spanish))),
                    spanish: spanish, record: { record(accountID) }, check: { showingBalanceInfo = true }) {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        Text(CuadraoCopy.text("copy.accountActivityView.f7d6ac01ad", spanish: spanish)).font(CuadraoTypography.section)
                        let entries = data.activity.filter { $0.accountID == accountID }.sorted { $0.date > $1.date }
                        if entries.isEmpty {
                            CuadraoEmptyView(title: CuadraoCopy.text("copy.accountActivityView.8e6c47416d", spanish: spanish),
                                detail: CuadraoCopy.text("copy.accountActivityView.051603fc06", spanish: spanish),
                                actionTitle: CuadraoCopy.text("copy.canvasAccountPresentation.ef0cf39904", spanish: spanish), action: { record(accountID) },
                                identifier: "account-detail.empty", actionIdentifier: "account-detail.empty.record")
                        } else {
                            ForEach(entries) { entry in
                                NavigationLink {
                                    CuadraoActivityDetail(data: data, activityID: entry.id, spanish: spanish, actions: actions, record: record)
                                } label: {
                                    CanvasAccountActivityRowContent(value: CanvasAccountActivityRowValue(
                                        title: entry.title,
                                        detail: entry.date.formatted(.dateTime.day().month(.abbreviated).locale(locale)),
                                        amount: (entry.income ? "+" : "−") + CanvasMoney.format(entry.amount, currency: account.currency),
                                        symbol: entry.income ? "arrow.down.left" : "arrow.up.right"))
                                }.buttonStyle(.plain).accessibilityIdentifier("account-detail-activity.\(entry.id)")
                                Divider()
                            }
                        }
                    }
                }.padding(24).padding(.bottom, 32)
            // Design preview only: the data is in memory, so there is no load behind this stamp. Connected detail uses AccountsModel.refreshedAt.
            }.refreshable { try? await Task.sleep(for: .milliseconds(400)); refreshedAt = Date() }
                .background(WelcomePalette.background)
                .navigationTitle("").navigationBarTitleDisplayMode(.inline)
                .toolbar(.visible, for: .navigationBar)
                .toolbar {
                    if #available(iOS 26.0, *) {
                        ToolbarItem(placement: .topBarTrailing) { moreButton }
                            .sharedBackgroundVisibility(.hidden)
                    } else {
                        ToolbarItem(placement: .topBarTrailing) { moreButton }
                    }
                }
                .contextualCuadrao(focus: $chatFocus, spanish: spanish)
                .alert(CuadraoCopy.text("copy.canvasAccountPresentation.96327e1801", spanish: spanish), isPresented: $showingBalanceInfo) {
                    Button(CuadraoCopy.text("copy.cuadraoAccountCanvas.43385c465a", spanish: spanish), role: .cancel) { }
                } message: {
                    Text(CuadraoCopy.text("copy.cuadraoAccountCanvas.9d566dd31f", spanish: spanish))
                }
        }
    }
    private var moreButton: some View {
        Menu {
            if let account = data.account(accountID) {
                Button(CuadraoCopy.text("copy.cuadraoAccountCanvas.b44a9adeb4", spanish: spanish), systemImage: "bubble") {
                    chatFocus = .account(id: accountID, title: account.displayName(spanish))
                }.accessibilityIdentifier("account-detail-ask")
            }
            Button(CuadraoCopy.text("copy.cuadraoAccountCanvas.e59e534133", spanish: spanish), systemImage: "pencil") { actions(.rename(accountID)) }
            Button(CuadraoCopy.text("copy.canvasAccountPresentation.ef0cf39904", spanish: spanish), systemImage: "plus") { record(accountID) }
            Button(CuadraoCopy.text("copy.connectedCuadraoHome.0960027352", spanish: spanish), systemImage: "archivebox") { actions(.archive(accountID)) }
        } label: {
            Image(systemName: "ellipsis").frame(width: 44, height: 44).contentShape(Rectangle())
        }.buttonStyle(.plain)
            .accessibilityLabel(CuadraoCopy.text("copy.accountDetailView.f3398370dd", spanish: spanish))
            .accessibilityIdentifier("account-detail-options")
    }

}

/// Visual entry/review only. Saving stages a sample row, never a financial command.
struct CuadraoTransactionCanvas: View {
    let data: CuadraoAccountsPreview
    let account: CanvasAccount
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var amount = ""
    @State private var currency = ""
    @State private var error = ""
    @State private var title = ""
    @State private var income = false
    @State private var date = Date.now
    @State private var reviewing = false
    private var valid: Bool { error.isEmpty && (Decimal(string: amount) ?? 0) > 0 }
    var body: some View {
        CuadraoTransactionSheet(account: CuadraoTransactionAccount(title: account.displayName(spanish), artwork: account.kind),
            spanish: spanish, reviewing: reviewing, primaryEnabled: valid, back: { reviewing = false }, primary: {
                if reviewing {
                    data.activity.insert(CanvasActivity(accountID: account.id,
                        title: title.isEmpty ? (income ? (CuadraoCopy.text("copy.cuadraoAccountCanvas.68048ec6e6", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoAccountCanvas.705df72a66", spanish: spanish))) : title,
                        amount: Decimal(string: amount) ?? 0, date: date, income: income), at: 0)
                    dismiss()
                } else {
                    UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                    reviewing = true
                }
            }) {
            if reviewing {
                Text((income ? "+" : "−") + CanvasMoney.format(Decimal(string: amount) ?? 0, currency: account.currency))
                    .font(CuadraoTypography.amount).monospacedDigit()
                LabeledContent(CuadraoCopy.text("copy.connectedTransactionSheet.9b96ad5816", spanish: spanish), value: account.currency)
                LabeledContent(CuadraoCopy.text("copy.connectedTransactionSheet.36a6ac68b2", spanish: spanish), value: income ? (CuadraoCopy.text("copy.cuadraoAccountCanvas.68048ec6e6", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoAccountCanvas.705df72a66", spanish: spanish)))
                if !title.isEmpty { LabeledContent(CuadraoCopy.text("copy.connectedTransactionSheet.387cf3bb68", spanish: spanish), value: title) }
                LabeledContent(CuadraoCopy.text("copy.connectedTransactionSheet.9e3d3b41ed", spanish: spanish)) { Text(date, format: .dateTime.day().month().year()) }
            } else {
                Picker(CuadraoCopy.text("copy.connectedTransactionSheet.36a6ac68b2", spanish: spanish), selection: $income) {
                    Text(CuadraoCopy.text("copy.cuadraoAccountCanvas.705df72a66", spanish: spanish)).tag(false)
                    Text(CuadraoCopy.text("copy.cuadraoAccountCanvas.68048ec6e6", spanish: spanish)).tag(true)
                }.pickerStyle(.segmented)
                CuadraoAmountField(raw: $amount, currency: $currency, error: $error, spanish: spanish, currencySelectable: false)
                TextField(CuadraoCopy.text("copy.connectedTransactionSheet.b6d70b2c10", spanish: spanish), text: $title)
                    .modifier(RegistrationField())
                DatePicker(CuadraoCopy.text("copy.connectedTransactionSheet.9e3d3b41ed", spanish: spanish), selection: $date, in: ...Date.now, displayedComponents: .date)
            }
        }.onAppear { currency = account.currency }
    }
}
