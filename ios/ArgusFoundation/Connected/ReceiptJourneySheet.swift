import SwiftUI
import ArgusSession

/// One receipt from consent to a saved expense. Built from the approved sheet parts: plain Cancel or Later on the
/// leading side, Done on the trailing side, and the sheet's own button at the bottom.
struct ReceiptJourneySheet: View {
    @ObservedObject var model: ReceiptJourneyModel
    let spanish: Bool
    let finished: () -> Void
    @State private var correcting = false
    @State private var amountError = ""

    private var copy: ReceiptJourneyCopy { ReceiptJourneyCopy(spanish: spanish) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) { content }
                    .padding(24).frame(maxWidth: .infinity, alignment: .leading)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(WelcomePalette.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { toolbar }
            .safeAreaInset(edge: .bottom, spacing: 0) { primary }
        }
        .tint(WelcomePalette.pine)
        .interactiveDismissDisabled(isBusy)
        .accessibilityIdentifier("receipt.journey")
    }

    private var isBusy: Bool {
        switch model.phase {
        case .sending, .recording: true
        default: false
        }
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        switch model.phase {
        case .consent:
            CuadraoCancelToolbar(title: copy.cancel, identifier: "receipt.journey.cancel") { close() }
        case .preparing, .stillPreparing, .review, .failed(.couldNotRead), .failed(.couldNotRecord):
            CuadraoCancelToolbar(title: copy.later, identifier: "receipt.journey.later") { close() }
        case .recorded, .linked, .savedOnly, .failed:
            CuadraoDoneToolbar(title: copy.done, identifier: "receipt.journey.done") { close() }
        case .idle, .sending, .recording:
            CuadraoCancelToolbar(title: copy.cancel, disabled: true) {}
        }
    }

    @ViewBuilder private var content: some View {
        switch model.phase {
        case .idle:
            EmptyView()
        case .consent:
            RegistrationHeading(title: copy.consentTitle, detail: copy.consentDetail)
            Text(copy.consentSaveOnlyDetail).font(CuadraoTypography.caption).foregroundStyle(.secondary)
        case .sending:
            progress(copy.sending, detail: nil)
        case .preparing:
            progress(copy.reading, detail: copy.readingDetail)
        case .stillPreparing:
            notice(copy.stillReading, identifier: "receipt.journey.still")
        case .review(let draft):
            review(draft)
        case .recording(let draft):
            summary(draft)
            progress(copy.recording, detail: nil)
        case .recorded:
            outcome(copy.recorded, detail: copy.recordedDetail, identifier: "receipt.journey.recorded")
        case .linked:
            outcome(copy.linked, detail: copy.recordedDetail, identifier: "receipt.journey.linked")
        case .savedOnly(let alreadySaved):
            let saved = SavedReceiptCopy(spanish: spanish)
            outcome(alreadySaved ? saved.alreadySaved : saved.savedTitle, detail: saved.savedDetail, identifier: "receipt.journey.saved")
        case .failed(let failure):
            notice(message(failure), identifier: "receipt.journey.failed")
        }
    }

    @ViewBuilder private var primary: some View {
        switch model.phase {
        case .consent:
            buttons {
                RegistrationButton(title: copy.consentRead) { Task { await model.answerConsent(true) } }
                    .accessibilityIdentifier("receipt.journey.read")
                Button(copy.consentSaveOnly) { Task { await model.answerConsent(false) } }
                    .frame(maxWidth: .infinity, minHeight: 44).accessibilityIdentifier("receipt.journey.saveOnly")
            }
        case .review(let draft):
            buttons {
                RegistrationButton(title: copy.confirm, enabled: draft.isComplete) { Task { await model.confirm() } }
                    .accessibilityIdentifier("receipt.journey.confirm")
            }
        case .recording:
            buttons { RegistrationButton(title: copy.confirm, busy: true) {} }
        case .failed(.couldNotSend):
            buttons {
                RegistrationButton(title: copy.retry) { Task { await model.answerConsent(true) } }
                    .accessibilityIdentifier("receipt.journey.retry")
            }
        case .failed(.couldNotRead):
            buttons {
                RegistrationButton(title: copy.readAgain) { Task { await model.readAgain() } }
                    .accessibilityIdentifier("receipt.journey.readAgain")
            }
        case .failed(.couldNotRecord):
            buttons {
                RegistrationButton(title: copy.backToReview) { Task { await model.backToReview() } }
                    .accessibilityIdentifier("receipt.journey.backToReview")
            }
        default:
            EmptyView()
        }
    }

    private func buttons<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        VStack(spacing: 8) { content() }
            .padding(.horizontal, 24).padding(.top, 12).padding(.bottom, 16)
            .background(WelcomePalette.background)
    }

    // MARK: Review

    @ViewBuilder private func review(_ draft: ReceiptReviewDraft) -> some View {
        Text(copy.reviewTitle).font(CuadraoTypography.screen).accessibilityAddTraits(.isHeader)
        summary(draft)
        DisclosureGroup(isExpanded: $correcting) { corrections(draft) } label: {
            Text(copy.correct).accessibilityIdentifier("receipt.review.correct")
        }
        accountChoice(draft)
        if let receipt = draft.receipt, !receipt.items.isEmpty { items(receipt) }
        if draft.existingMatch != nil {
            VStack(alignment: .leading, spacing: 8) {
                Text(copy.alreadyRecordedDetail).font(CuadraoTypography.caption).foregroundStyle(.secondary)
                Button(copy.alreadyRecorded) { Task { await model.linkExisting() } }
                    .frame(minHeight: 44).accessibilityIdentifier("receipt.review.link")
            }
        }
    }

    /// Merchant, date, category and total stay readable before any editing.
    private func summary(_ draft: ReceiptReviewDraft) -> some View {
        VStack(spacing: 0) {
            row(copy.merchant, draft.merchant.isEmpty ? copy.unknown : draft.merchant, id: "receipt.review.merchant")
            row(copy.date, draft.occurredOn.map(dayText) ?? copy.unknown, id: "receipt.review.date")
            row(copy.category, draft.categoryID.map(categoryTitle) ?? copy.noCategory, id: "receipt.review.category")
            row(copy.total, money(draft.amount, draft.currency), id: "receipt.review.total")
        }
    }

    @ViewBuilder private func corrections(_ draft: ReceiptReviewDraft) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            TextField(copy.merchant, text: binding(draft, \.merchant))
                .modifier(RegistrationField()).accessibilityIdentifier("receipt.review.merchant.edit")
            DatePicker(copy.date, selection: Binding(get: { draft.occurredOn ?? .now }, set: { value in
                var next = draft; next.occurredOn = value; model.update(next)
            }), in: ...Date.now, displayedComponents: .date)
                .accessibilityIdentifier("receipt.review.date.edit")
            CuadraoAmountField(raw: binding(draft, \.amount), currency: .constant(draft.currency), error: $amountError,
                               spanish: spanish, currencySelectable: false, identifier: "receipt.review.amount")
            if let categories = model.options?.categories {
                HStack {
                    Text(copy.category)
                    Spacer()
                    CuadraoChoiceMenu(title: copy.category, selection: binding(draft, \.categoryID),
                                      values: [nil] + categories.map(Optional.some),
                                      valueTitle: { $0.map(categoryTitle) ?? copy.noCategory })
                        .accessibilityIdentifier("receipt.review.category.edit")
                }
            }
        }.padding(.top, 12)
    }

    @ViewBuilder private func accountChoice(_ draft: ReceiptReviewDraft) -> some View {
        let accounts = model.accounts(for: draft)
        VStack(alignment: .leading, spacing: 8) {
            Text(copy.account).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
            if accounts.isEmpty {
                Text(copy.noAccount).font(CuadraoTypography.body).accessibilityIdentifier("receipt.review.noAccount")
            } else {
                CuadraoChoiceMenu(title: copy.account, selection: binding(draft, \.accountID),
                                  values: [nil] + accounts.map { Optional.some($0.id) },
                                  valueTitle: { id in
                                      accounts.first { $0.id == id }.map { ConnectedAccountPresentation.title($0, spanish: spanish) } ?? copy.chooseAccount
                                  })
                    .accessibilityIdentifier("receipt.review.account")
            }
        }
    }

    private func items(_ receipt: DocumentReceipt) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(copy.items).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
            ForEach(receipt.items) { item in
                HStack(alignment: .firstTextBaseline) {
                    Text([item.quantity.map { $0 + " × " }, item.description].compactMap { $0 }.joined())
                    Spacer()
                    Text(item.total ?? copy.unknown).monospacedDigit()
                }.font(CuadraoTypography.body)
            }
            Text(copy.itemsNote).font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }.accessibilityElement(children: .contain).accessibilityIdentifier("receipt.review.items")
    }

    // MARK: Parts

    private func row(_ title: String, _ value: String, id: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).foregroundStyle(.secondary)
            Spacer(minLength: 12)
            Text(value).multilineTextAlignment(.trailing)
        }
        .font(CuadraoTypography.body).frame(minHeight: 44)
        .accessibilityElement(children: .combine).accessibilityIdentifier(id)
    }

    private func progress(_ title: String, detail: String?) -> some View {
        VStack(spacing: 12) {
            ProgressView()
            Text(title).font(CuadraoTypography.body)
            if let detail { Text(detail).font(CuadraoTypography.caption).foregroundStyle(.secondary).multilineTextAlignment(.center) }
        }
        .frame(maxWidth: .infinity).padding(.vertical, 32)
        .accessibilityElement(children: .combine).accessibilityIdentifier("receipt.journey.progress")
    }

    private func outcome(_ title: String, detail: String, identifier: String) -> some View {
        RegistrationHeading(title: title, detail: detail).accessibilityIdentifier(identifier)
    }

    private func notice(_ text: String, identifier: String) -> some View {
        Text(text).font(CuadraoTypography.body).fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier(identifier)
    }

    private func message(_ failure: ReceiptJourneyFailure) -> String {
        switch failure {
        case .couldNotSend(let reason): SavedReceiptCopy(spanish: spanish).failure(reason)
        case .couldNotRead: copy.couldNotRead
        case .nothingToRecord: copy.nothingToRecord
        case .couldNotRecord(let code): copy.recordFailure(code)
        }
    }

    private func binding<Value>(_ draft: ReceiptReviewDraft, _ path: WritableKeyPath<ReceiptReviewDraft, Value>) -> Binding<Value> {
        Binding(get: { draft[keyPath: path] }, set: { value in
            var next = draft; next[keyPath: path] = value; model.update(next)
        })
    }

    private func categoryTitle(_ id: String) -> String { NSLocalizedString("loop.category." + id, comment: "") }

    private func dayText(_ date: Date) -> String {
        date.formatted(.dateTime.day().month(.abbreviated).year().locale(Locale(identifier: spanish ? "es_DO" : "en_US")))
    }

    private func money(_ amount: String, _ currency: String) -> String {
        guard let value = Decimal(string: amount), !currency.isEmpty else { return copy.unknown }
        return currency + " " + CanvasMoney.format(value, currency: currency)
    }

    private func close() {
        model.reset()
        finished()
    }
}

extension View {
    /// Shows the receipt journey whenever it is under way. `finished` runs after the sheet closes.
    func receiptJourney(_ model: ReceiptJourneyModel?, spanish: Bool, finished: @escaping () -> Void) -> some View {
        modifier(ReceiptJourneyPresentation(model: model, spanish: spanish, finished: finished))
    }
}

private struct ReceiptJourneyPresentation: ViewModifier {
    let model: ReceiptJourneyModel?
    let spanish: Bool
    let finished: () -> Void
    func body(content: Content) -> some View {
        if let model { content.modifier(Presented(model: model, spanish: spanish, finished: finished)) } else { content }
    }

    private struct Presented: ViewModifier {
        @ObservedObject var model: ReceiptJourneyModel
        let spanish: Bool
        let finished: () -> Void
        func body(content: Content) -> some View {
            content.sheet(isPresented: Binding(get: { model.phase != .idle }, set: { if !$0 { model.reset() } }),
                          onDismiss: finished) {
                ReceiptJourneySheet(model: model, spanish: spanish, finished: {})
            }
        }
    }
}
