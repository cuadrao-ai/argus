import SwiftUI
import ArgusSession

struct AccountActivityView: View {
    @ObservedObject var loop: FinancialLoopModel
    let account: FinancialAccount
    var debtOrigin: FinancialDebtNavigation.Origin = .account
    @State private var pendingCorrection: FinancialActivityDetail?
    @State private var pendingReturn: FinancialActivityDetail?
    @State private var pendingRecurring: FinancialActivityDetail?
    @State private var inspected: FinancialActivity?
    @Environment(\.locale) private var locale

    private var page: FinancialLoopModel.AccountReadState { loop.read(account.id) }
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    var body: some View {
        LazyVStack(alignment: .leading, spacing: 16) {
            if ["credit_card", "other_debt"].contains(account.type) {
                if let progress = loop.plan.projection?.debts?.first(where: { !$0.debt.archived && $0.debt.debtAccountId == account.id }) {
                    Button("debt.view") { Task { await loop.debts.open(progress.id, origin: debtOrigin) } }.frame(minHeight: 44).accessibilityIdentifier("accounts.debt")
                } else { Button("debt.add") { loop.debts.create(account) }.frame(minHeight: 44).accessibilityIdentifier("accounts.debt") }
            }
            Text(spanish ? "Movimientos" : "Activity").font(CuadraoTypography.section).accessibilityAddTraits(.isHeader)
            if page.loading && page.activity.isEmpty { CuadraoSkeleton(layout: .rows(3), identifier: "accounts.activity.loading") }
            if let error = page.errorKey {
                CuadraoRetryState(message: LocalizedStringKey(error), identifier: "accounts.activity.error",
                                  retryIdentifier: "accounts.activity.retry") { Task { await loop.open(account) } }
                    .disabled(page.loading)
            }
            if page.activity.isEmpty, loop.accountReads[account.id] != nil, !page.loading, page.errorKey == nil {
                VStack(alignment: .leading, spacing: 8) {
                    Text(spanish ? "Aún no hay movimientos." : "No activity yet.").font(.body)
                    Text(spanish ? "Añade el primero cuando lo necesites." : "Add the first when you need to.")
                        .font(.subheadline).foregroundStyle(.secondary)
                }.padding(.vertical, 18)
            }
            ForEach(page.activity, id: \.recordId) { activity in
                Button { inspected = activity } label: {
                    FinancialActivityRow(activity: activity, currency: account.currency)
                }.buttonStyle(.plain).accessibilityIdentifier("activity.row." + activity.recordId.uuidString)
            }
            if page.activityCursor != nil {
                Button("loop.more") { Task { await loop.more(account, checks: false) } }.frame(minHeight: 44)
                    .disabled(page.loading || page.loadingMore).accessibilityIdentifier("accounts.activity.more")
            }
            if !page.checks.isEmpty {
                Text("loop.check.history").font(CuadraoTypography.section).accessibilityAddTraits(.isHeader)
                ForEach(page.checks, id: \.recordId) { check in
                    VStack(alignment: .leading, spacing: 8) {
                        Label(check.kind == "value_update" ? "loop.check.value" : "loop.check.title", systemImage: "checkmark.circle")
                        Text(verbatim: account.currency + " " + AccountPresentation.amount(AccountPresentation.decimal(check.observedAmountMinor, digits: account.currencyFractionDigits), locale: locale))
                            .font(CuadraoTypography.rowAmount)
                        Text(verbatim: AccountPresentation.date(check.asOf, zone: check.timeZone, locale: locale))
                            .font(.caption).foregroundStyle(.secondary)
                        if let difference = check.differenceMinor {
                            Text("loop.difference") + Text(verbatim: " " + account.currency + " " + AccountPresentation.amount(AccountPresentation.decimal(difference, digits: account.currencyFractionDigits), locale: locale))
                        }
                        if let remaining = check.unexplainedMinor {
                            Text("loop.check.unexplained") + Text(verbatim: " " + account.currency + " " + AccountPresentation.amount(AccountPresentation.decimal(remaining, digits: account.currencyFractionDigits), locale: locale))
                        }
                        if let note = check.note, !note.isEmpty { Text(verbatim: note) }
                    }.font(.subheadline).padding(.vertical, 12)
                }
            }
            if page.checksCursor != nil {
                Button("loop.more") { Task { await loop.more(account, checks: true) } }.frame(minHeight: 44)
                    .disabled(page.loading || page.loadingMore).accessibilityIdentifier("accounts.checks.more")
            }
            if page.loadingMore { ProgressView("accounts.loading") }
        }
        .task(id: account.version) { await loop.open(account) }
        .sheet(item: $inspected, onDismiss: {
            if let activity = pendingCorrection { pendingCorrection = nil; loop.record(account, correcting: activity) }
            else if let activity = pendingReturn { pendingReturn = nil; loop.returnPayment(activity) }
            else if let activity = pendingRecurring { pendingRecurring = nil; loop.plan.prepareRecurring(from: activity) }
        }) { activity in
            NavigationStack {
                ScrollView {
                    FinancialActivityDetailView(loop: loop, activityID: activity.activityId ?? activity.recordId, accounts: [account],
                                                returnPayment: { current in pendingReturn = current; inspected = nil },
                                                setUpRecurring: { current in pendingRecurring = current; inspected = nil }) { current in
                        pendingCorrection = current; inspected = nil
                    }.padding(24)
                }.background(WelcomePalette.background)
                    .navigationTitle("loop.activity.title").navigationBarTitleDisplayMode(.inline)
                    .toolbar { CuadraoCancelToolbar(title: "action.close") { inspected = nil } }
            }.tint(WelcomePalette.pine).foregroundStyle(WelcomePalette.ink)
        }
    }
}

extension FinancialActivity: @retroactive Identifiable {
    public var id: UUID { recordId }
}

struct FinancialActivityRow: View {
    let activity: FinancialActivity
    let currency: String
    @Environment(\.locale) private var locale

    var body: some View {
        VStack(spacing: 0) {
            CanvasAccountActivityRowContent(value: CanvasAccountActivityRowValue(
                title: activity.note.flatMap { $0.isEmpty ? nil : $0 } ?? NSLocalizedString("loop.kind." + activity.kind, comment: ""),
                detail: AccountPresentation.date(activity.occurredAt, zone: activity.timeZone, locale: locale),
                amount: FinancialActivityPresentation.sign(for: activity.balanceMovementMinor) + currency + " " + AccountPresentation.amount(activity.amount, locale: locale),
                symbol: FinancialActivityPresentation.symbol(for: activity.kind),
                status: activity.active == false ? NSLocalizedString("loop.activity.moved", comment: "") : nil))
            Divider()
        }.accessibilityElement(children: .combine)
    }
}

struct FinancialEditorPresenter: View {
    @ObservedObject var loop: FinancialLoopModel
    let appearance: AppearancePreference
    var body: some View {
        Color.clear.frame(width: 0, height: 0)
            .sheet(item: $loop.activityEditor) { editor in
                ConnectedTransactionSheet(model: editor)
                    .preferredColorScheme(appearance.colorScheme).tint(WelcomePalette.pine).foregroundStyle(WelcomePalette.ink)
            }
            .sheet(item: $loop.editor) { editor in
                FinancialEditorView(model: editor)
                    .preferredColorScheme(appearance.colorScheme).tint(WelcomePalette.pine).foregroundStyle(WelcomePalette.ink)
            }
    }
}
