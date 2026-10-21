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
                        freshness: account.balance == nil ? (spanish ? "Sin balance registrado" : "No balance recorded")
                            : (spanish ? "Actualizado hoy" : "Updated today")),
                    spanish: spanish, record: { record(accountID) }, check: { showingBalanceInfo = true }) {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        Text(spanish ? "Movimientos" : "Activity").font(CuadraoTypography.section)
                        let entries = data.activity.filter { $0.accountID == accountID }.sorted { $0.date > $1.date }
                        if entries.isEmpty {
                            CuadraoEmptyView(title: spanish ? "Aún no hay movimientos" : "No activity yet",
                                detail: spanish ? "Añade el primero cuando lo necesites." : "Add the first when you need to.",
                                actionTitle: spanish ? "Añadir movimiento" : "Add transaction", action: { record(accountID) },
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
                .alert(spanish ? "Comprobar balance" : "Check balance", isPresented: $showingBalanceInfo) {
                    Button(spanish ? "Entendido" : "Got it", role: .cancel) { }
                } message: {
                    Text(spanish ? "La conciliación sigue en la app conectada. Esta vista permite revisar el diseño de la cuenta."
                         : "Reconciliation remains in the connected app. This canvas previews the account design.")
                }
        }
    }
    private var moreButton: some View {
        Menu {
            if let account = data.account(accountID) {
                Button(spanish ? "Preguntar a Cuadrao" : "Ask Cuadrao", systemImage: "bubble") {
                    chatFocus = .account(id: accountID, title: account.displayName(spanish))
                }.accessibilityIdentifier("account-detail-ask")
            }
            Button(spanish ? "Cambiar nombre" : "Rename account", systemImage: "pencil") { actions(.rename(accountID)) }
            Button(spanish ? "Añadir movimiento" : "Add transaction", systemImage: "plus") { record(accountID) }
            Button(spanish ? "Archivar" : "Archive", systemImage: "archivebox") { actions(.archive(accountID)) }
        } label: {
            Image(systemName: "ellipsis").frame(width: 44, height: 44).contentShape(Rectangle())
        }.buttonStyle(.plain)
            .accessibilityLabel(spanish ? "Opciones de cuenta" : "Account actions")
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
                        title: title.isEmpty ? (income ? (spanish ? "Ingreso" : "Income") : (spanish ? "Gasto" : "Expense")) : title,
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
                LabeledContent(spanish ? "Moneda" : "Currency", value: account.currency)
                LabeledContent(spanish ? "Tipo" : "Type", value: income ? (spanish ? "Ingreso" : "Income") : (spanish ? "Gasto" : "Expense"))
                if !title.isEmpty { LabeledContent(spanish ? "Concepto" : "Description", value: title) }
                LabeledContent(spanish ? "Fecha" : "Date") { Text(date, format: .dateTime.day().month().year()) }
            } else {
                Picker(spanish ? "Tipo" : "Type", selection: $income) {
                    Text(spanish ? "Gasto" : "Expense").tag(false)
                    Text(spanish ? "Ingreso" : "Income").tag(true)
                }.pickerStyle(.segmented)
                CuadraoAmountField(raw: $amount, currency: $currency, error: $error, spanish: spanish, currencySelectable: false)
                TextField(spanish ? "Concepto (opcional)" : "Description (optional)", text: $title)
                    .modifier(RegistrationField())
                DatePicker(spanish ? "Fecha" : "Date", selection: $date, in: ...Date.now, displayedComponents: .date)
            }
        }.onAppear { currency = account.currency }
    }
}
