import SwiftUI
import ArgusSession

struct FinancialActivityDetailView: View {
    @ObservedObject var loop: FinancialLoopModel
    let activityID: UUID
    var accounts: [FinancialAccount] = []
    var openAccount: ((UUID) -> Void)? = nil
    var returnPayment: ((FinancialActivityDetail) -> Void)? = nil
    /// Sheet hosts defer the plan form until this sheet closes; pushed hosts open it directly.
    var setUpRecurring: ((FinancialActivityDetail) -> Void)? = nil
    let correct: (FinancialActivityDetail) -> Void
    @State private var detail: FinancialActivityDetail?
    @State private var revisions: [FinancialActivityDetail] = []
    @State private var errorKey: String?
    @Environment(\.locale) private var locale
    @Environment(\.receiptJourney) private var receipts
    @State private var receipt: FinancialDocumentDetail?
    @State private var viewingReceipt: ViewedReceipt?

    private var spanish: Bool { CuadraoCopy.isSpanish() }

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            if let detail {
                CanvasActivityDetailContent(value: display(detail), spanish: spanish) {
                    if let source = detail.sourceId {
                        LabeledContent("loop.activity.source", value: NSLocalizedString("loop.source." + source, comment: ""))
                    }
                    ForEach(detail.legs) { leg in accountRow(leg, detail: detail) }
                    if let principal = detail.principalMinor { PlanValueRow(title: "debt.principal", value: minor(principal, detail)) }
                    if let interest = detail.interestMinor { PlanValueRow(title: "debt.interest", value: minor(interest, detail)) }
                    if let fees = detail.feesMinor { PlanValueRow(title: "debt.fees", value: minor(fees, detail)) }
                    if detail.kind == .paymentReversal { Text("debt.return.disclosure").font(.subheadline).foregroundStyle(.secondary) }
                    if detail.kind == .refund {
                        Text(detail.purchaseActivityId == nil ? "loop.activity.purchaseNone" : "loop.activity.linkedPurchase")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                    if let reason = detail.reason { LabeledContent("accounts.reason", value: reason) }
                    if let receipt { receiptRow(receipt) }
                    if detail.originalAmountAvailable {
                        actions(detail)
                    } else {
                        Label(CuadraoCopy.text("copy.financialActivityDetailView.151c37f24b", spanish: spanish), systemImage: "lock")
                            .font(.subheadline).foregroundStyle(.secondary)
                            .accessibilityIdentifier("activity.readOnly")
                    }
                    if revisions.count > 1 { history }
                }
            } else if errorKey == nil { ProgressView("accounts.loading") }
            if let errorKey {
                Text(LocalizedStringKey(errorKey)).accessibilityIdentifier("activity.detail.error")
                Button("accounts.retry") { Task { await load() } }.frame(minHeight: 44)
            }
        }.foregroundStyle(WelcomePalette.ink)
            .task(id: activityID) { await load() }
            .sheet(item: $viewingReceipt) { SavedReceiptViewer(receipt: $0, copy: SavedReceiptCopy(spanish: spanish)) }
            .onChange(of: loop.activityEditor == nil) { _, closed in if closed { Task { await load() } } }
    }

    private func display(_ detail: FinancialActivityDetail) -> CanvasActivityDetailValue {
        let category = detail.categoryId.map {
            CanvasActivityCategoryValue(title: NSLocalizedString("loop.category." + $0, comment: ""), artwork: CanvasExpenseCategory.fromRecordedCategory($0))
        }
        let amount = detail.originalAmountAvailable
            ? detail.currency + " " + AccountPresentation.amount(detail.amount, locale: locale)
            : (CuadraoCopy.text("copy.financialActivityDetailView.fe5a1f51c9", spanish: spanish))
        return CanvasActivityDetailValue(
            title: detail.note.flatMap { $0.isEmpty ? nil : $0 } ?? NSLocalizedString("loop.kind." + detail.kind.rawValue, comment: ""),
            amount: amount, kind: NSLocalizedString("loop.kind." + detail.kind.rawValue, comment: ""),
            date: AccountPresentation.date(detail.occurredAt, zone: detail.timeZone, locale: locale), category: category)
    }

    @ViewBuilder private func accountRow(_ leg: FinancialActivityLeg, detail: FinancialActivityDetail) -> some View {
        let account = accounts.first { $0.id == leg.accountId }
        let role = NSLocalizedString(leg.role == "source" ? "loop.activity.from" : leg.role == "destination" ? "loop.activity.to" : "loop.activity.account", comment: "")
        let label = CanvasActivityAccountRowContent(title: loop.accountName(leg.accountId), detail: role + " · " + detail.currency,
            artwork: account.flatMap { ConnectedAccountPresentation.artwork($0.type) }, showsDisclosure: openAccount != nil && account != nil,
            amount: FinancialActivityPresentation.signedAmount(leg.balanceMovementMinor, digits: detail.currencyFractionDigits, locale: locale))
        if let openAccount, account != nil {
            Button { openAccount(leg.accountId) } label: { label }.buttonStyle(.plain)
                .accessibilityIdentifier("activity-detail-account." + leg.accountId.uuidString)
        } else { label }
    }

    private func actions(_ detail: FinancialActivityDetail) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            RegistrationButton(title: NSLocalizedString("loop.correction.title", comment: ""), enabled: loop.pendingConfirmation == nil) {
                correct(detail)
            }.accessibilityIdentifier("activity.correct")
            if FinancialExpectationSeed.eligible(detail) {
                CanvasActionRow(title: NSLocalizedString("loop.activity.repeat", comment: ""), symbol: "repeat") {
                    if let setUpRecurring { setUpRecurring(detail) } else { loop.plan.prepareRecurring(from: detail) }
                }.disabled(loop.pendingConfirmation != nil).accessibilityIdentifier("activity.repeat")
                Text("loop.activity.repeat.hint").font(.caption).foregroundStyle(.secondary)
            }
            if detail.kind == .cardPayment || detail.kind == .debtPayment {
                CanvasActionRow(title: NSLocalizedString("debt.return", comment: ""), symbol: "arrow.uturn.backward") {
                    if let returnPayment { returnPayment(detail) } else { loop.returnPayment(detail) }
                }.disabled(loop.pendingConfirmation != nil).accessibilityIdentifier("activity.return")
            }
        }
    }

    /// The receipt this movement was recorded from or attached to.
    private func receiptRow(_ document: FinancialDocumentDetail) -> some View {
        CanvasActionRow(title: ReceiptJourneyCopy(spanish: spanish).viewReceipt, symbol: "doc.text.magnifyingglass") {
            Task {
                guard let data = await receipts?.source(document) else { return }
                viewingReceipt = ViewedReceipt(document: SavedDocument(connectionID: document.connectionID, filename: document.filename,
                    mediaType: document.mediaType, sizeBytes: data.count, sourceAvailable: true, status: document.status,
                    createdAt: document.createdAt, updatedAt: document.createdAt), data: data)
            }
        }.accessibilityIdentifier("activity.receipt")
    }

    private var history: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("loop.revisions").font(CuadraoTypography.section).accessibilityAddTraits(.isHeader)
            ForEach(revisions, id: \.revision) { revision in
                VStack(alignment: .leading, spacing: 8) {
                    Text(verbatim: revision.originalAmountAvailable
                         ? revision.currency + " " + AccountPresentation.amount(revision.amount, locale: locale)
                         : (CuadraoCopy.text("copy.financialActivityDetailView.fe5a1f51c9", spanish: spanish)))
                        .font(CuadraoTypography.rowAmount)
                    Text(verbatim: AccountPresentation.date(revision.occurredAt, zone: revision.timeZone, locale: locale))
                        .font(.caption).foregroundStyle(.secondary)
                    if let reason = revision.reason { Text(verbatim: reason) }
                }
            }
        }
    }

    private func minor(_ value: Int64, _ detail: FinancialActivityDetail) -> String {
        PlanPresentation.money(String(value), currency: detail.currency, digits: detail.currencyFractionDigits, locale: locale)
    }

    private func load() async {
        errorKey = nil
        do {
            let current = try await loop.detail(id: activityID)
            detail = current
            revisions = try await loop.detailHistory(current)
            receipt = await receipts?.receipt(for: activityID)
        } catch {
            if case SessionFailure.rejected(let status, _) = error, status == 404 || status == 403 {
                detail = nil; errorKey = "search.destination.unavailable"
            } else { errorKey = "loop.error.connection" }
        }
    }
}
