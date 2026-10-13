import SwiftUI
import ArgusSession

/// One receipt from consent to a saved expense. Built from the approved sheet parts: plain Cancel or Later on the
/// leading side, Done on the trailing side, and the sheet's own button at the bottom.
struct ReceiptJourneySheet: View {
    @ObservedObject var model: ReceiptJourneyModel
    let spanish: Bool
    let finished: () -> Void
    @State private var newPurchase = false
    @State private var choosingDay = false
    @State private var pickedDay = Date.now
    @State private var amountError = ""
    @State private var detent = PresentationDetent.medium

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
        .presentationDetents([.medium, .large], selection: $detent)
        .onChange(of: isLong, initial: true) { _, long in detent = long ? .large : .medium; if !long { newPurchase = false } }
        .interactiveDismissDisabled(isBusy)
        .accessibilityIdentifier("receipt.journey")
    }

    /// Review needs the whole screen; choosing, waiting and outcomes fit a half sheet.
    private var isLong: Bool {
        switch model.phase {
        case .review, .recording: true
        default: false
        }
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
        case .preparing, .stillPreparing, .review, .failed(.couldNotRead), .failed(.couldNotRecord), .failed(.couldNotSend):
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
            if model.readingAllowed {
                header(copy.choiceTitle(model.preview?.count ?? 1), identifier: "receipt.journey.choice")
            } else {
                header(copy.consentTitle, identifier: "receipt.journey.consent")
                Text(copy.consentDetail).font(CuadraoTypography.body).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("receipt.journey.disclosure")
            }
        case .sending:
            header(copy.sending, busy: true, identifier: "receipt.journey.progress")
        case .preparing:
            header(copy.reading, busy: true, identifier: "receipt.journey.progress")
            Text(copy.readingDetail).font(CuadraoTypography.caption).foregroundStyle(.secondary)
        case .stillPreparing:
            header(copy.stillReadingTitle, identifier: "receipt.journey.still")
            detail(copy.stillReading)
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
            let text = message(failure)
            header(text.title, identifier: "receipt.journey.failed")
            detail(text.detail)
        }
    }

    @ViewBuilder private var primary: some View {
        switch model.phase {
        case .consent:
            buttons {
                RegistrationButton(title: copy.read) { Task { await model.answerConsent(true) } }
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
        case .failed(.couldNotRead), .failed(.nothingToRecord):
            if model.canWriteByHand || model.phase == .failed(.couldNotRead) {
                buttons {
                    if model.canWriteByHand {
                        RegistrationButton(title: copy.writeByHand) { model.handWrite() }
                            .accessibilityIdentifier("receipt.journey.byHand")
                    }
                    if model.phase == .failed(.couldNotRead) {
                        if model.canWriteByHand {
                            Button(copy.readAgain) { Task { await model.readAgain() } }
                                .frame(maxWidth: .infinity, minHeight: 44).accessibilityIdentifier("receipt.journey.readAgain")
                        } else {
                            RegistrationButton(title: copy.readAgain) { Task { await model.readAgain() } }
                                .accessibilityIdentifier("receipt.journey.readAgain")
                        }
                    }
                }
            }
        case .failed(.couldNotRecord):
            buttons {
                RegistrationButton(title: copy.backToReview) { Task { await model.backToReview() } }
                    .accessibilityIdentifier("receipt.journey.backToReview")
            }
        case .recorded, .linked, .stillPreparing, .failed:
            if !model.waiting.isEmpty {
                buttons {
                    RegistrationButton(title: copy.nextReceipt(model.waiting.count)) { Task { await model.next() } }
                        .accessibilityIdentifier("receipt.journey.next")
                }
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

    /// The receipt beside its fields, each edited where it is shown. A possible duplicate is asked first, on top.
    @ViewBuilder private func review(_ draft: ReceiptReviewDraft) -> some View {
        if draft.existingMatch != nil, !newPurchase { duplicateBanner(draft) }
        HStack(alignment: .top, spacing: 16) {
            ReceiptThumbnail(preview: model.preview, size: CGSize(width: 88, height: 116))
            VStack(alignment: .leading, spacing: 12) {
                TextField(copy.merchant, text: binding(draft, \.merchant), axis: .vertical)
                    .font(CuadraoTypography.section).lineLimit(1...3)
                    .accessibilityLabel(copy.merchant).accessibilityIdentifier("receipt.review.merchant")
                if let day = draft.occurredOn {
                    DatePicker(copy.date, selection: Binding(get: { day }, set: { value in
                        var next = draft; next.occurredOn = value; model.update(next)
                    }), in: ...Date.now, displayedComponents: .date)
                        .labelsHidden().environment(\.locale, Locale(identifier: spanish ? "es_DO" : "en_US"))
                        .accessibilityLabel(copy.date).accessibilityIdentifier("receipt.review.date")
                } else {
                    missingDay(draft)
                }
            }
        }
        CuadraoAmountField(raw: binding(draft, \.amount), currency: .constant(draft.currency), error: $amountError,
                           spanish: spanish, currencySelectable: false, identifier: "receipt.review.total")
        VStack(spacing: 0) {
            if let categories = model.options?.categories {
                choiceRow(copy.category) {
                    CuadraoChoiceMenu(title: copy.category, selection: binding(draft, \.categoryID),
                                      values: [nil] + categories.map(Optional.some),
                                      valueTitle: { $0.map(categoryTitle) ?? copy.noCategory })
                        .accessibilityIdentifier("receipt.review.category")
                }
                Divider().foregroundStyle(WelcomePalette.separator)
            }
            accountChoice(draft)
        }
        if let receipt = draft.receipt, !receipt.items.isEmpty { items(receipt) }
    }

    /// The reading found no date: say so, and let the person pick one. No date is saved until they do.
    private func missingDay(_ draft: ReceiptReviewDraft) -> some View {
        Button { pickedDay = .now; choosingDay = true } label: {
            VStack(alignment: .leading, spacing: 2) {
                Text(copy.date + ": " + copy.unknown).foregroundStyle(.secondary)
                Text(copy.chooseDate)
            }
            .font(CuadraoTypography.body).frame(minHeight: 44, alignment: .leading)
        }
        .accessibilityIdentifier("receipt.review.date.missing")
        .popover(isPresented: $choosingDay) {
            VStack(spacing: 12) {
                DatePicker(copy.date, selection: $pickedDay, in: ...Date.now, displayedComponents: .date)
                    .datePickerStyle(.graphical).environment(\.locale, Locale(identifier: spanish ? "es_DO" : "en_US"))
                Button(copy.useDate) {
                    var next = draft; next.occurredOn = pickedDay; model.update(next); choosingDay = false
                }
                .buttonStyle(.borderedProminent).tint(WelcomePalette.pine).frame(minHeight: 44)
                .accessibilityIdentifier("receipt.review.date.use")
            }
            .padding(16).presentationCompactAdaptation(.popover)
        }
    }

    /// Asked before anything else: this purchase may already be recorded. Adding the receipt to it comes first.
    private func duplicateBanner(_ draft: ReceiptReviewDraft) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(copy.duplicateTitle).font(CuadraoTypography.body.weight(.semibold))
            Text(copy.duplicateDetail)
                .font(CuadraoTypography.supporting).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            // Side by side when both fit on one line each; otherwise stacked, adding to the movement first.
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 16) { addToMovement.fixedSize(); otherExpense.fixedSize() }
                VStack(alignment: .leading, spacing: 4) { addToMovement.frame(maxWidth: .infinity); otherExpense }
            }
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .contain).accessibilityIdentifier("receipt.review.duplicate")
    }

    private var addToMovement: some View {
        Button { Task { await model.linkExisting() } } label: {
            Text(copy.alreadyRecorded).frame(maxWidth: .infinity, minHeight: 44)
        }
        .buttonStyle(.borderedProminent).tint(WelcomePalette.pine).buttonBorderShape(.capsule)
        .accessibilityIdentifier("receipt.review.link")
    }

    private var otherExpense: some View {
        Button(copy.newPurchase) { newPurchase = true }
            .frame(minHeight: 44).accessibilityIdentifier("receipt.review.newPurchase")
    }

    private func choiceRow<Choice: View>(_ title: String, @ViewBuilder choice: () -> Choice) -> some View {
        HStack {
            Text(title).foregroundStyle(.secondary)
            Spacer(minLength: 12)
            choice()
        }
        .font(CuadraoTypography.body).frame(minHeight: 44)
    }

    /// Merchant, date, category and total while the expense is being saved.
    private func summary(_ draft: ReceiptReviewDraft) -> some View {
        VStack(spacing: 0) {
            row(copy.merchant, draft.merchant.isEmpty ? copy.unknown : draft.merchant, id: "receipt.summary.merchant")
            row(copy.date, draft.occurredOn.map(dayText) ?? copy.unknown, id: "receipt.summary.date")
            row(copy.category, draft.categoryID.map(categoryTitle) ?? copy.noCategory, id: "receipt.summary.category")
            row(copy.total, money(draft.amount, draft.currency), id: "receipt.summary.total")
        }
    }

    @ViewBuilder private func accountChoice(_ draft: ReceiptReviewDraft) -> some View {
        let accounts = model.accounts(for: draft)
        if accounts.isEmpty {
            Text(copy.noAccount).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).accessibilityIdentifier("receipt.review.noAccount")
        } else {
            choiceRow(copy.account) {
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

    /// The receipt's thumbnail beside one line of state, so the person always sees which receipt this is.
    private func header(_ title: String, busy: Bool = false, identifier: String) -> some View {
        HStack(alignment: .center, spacing: 16) {
            ReceiptThumbnail(preview: model.preview)
            VStack(alignment: .leading, spacing: 8) {
                Text(title).font(CuadraoTypography.section).fixedSize(horizontal: false, vertical: true)
                if busy { ProgressView().accessibilityHidden(true) }
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine).accessibilityIdentifier(identifier)
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

    /// A short title beside the receipt, and the plain explanation below it.
    private func message(_ failure: ReceiptJourneyFailure) -> (title: String, detail: String) {
        switch failure {
        case .couldNotSend(.offline): (copy.offlineTitle, copy.offlineDetail)
        case .couldNotSend(let reason): (copy.couldNotSendTitle, SavedReceiptCopy(spanish: spanish).failure(reason))
        case .couldNotRead: (copy.couldNotReadTitle, copy.stillSaved)
        case .nothingToRecord: (copy.nothingToRecordTitle, copy.stillSaved)
        case .couldNotRecord(let code): (copy.couldNotRecord, copy.recordFailure(code))
        }
    }

    private func detail(_ text: String) -> some View {
        Text(text).font(CuadraoTypography.body).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
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

/// The captured receipt as a small card: the photo itself, or the document symbol for a PDF, with a count for several.
struct ReceiptThumbnail: View {
    let preview: ReceiptPreview?
    var size = CGSize(width: 56, height: 72)

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10, style: .continuous).fill(WelcomePalette.surface)
            if let data = preview?.image, let image = UIImage(data: data) {
                Image(uiImage: image).resizable().scaledToFill()
            } else {
                Image(systemName: "doc.text").font(.title2).foregroundStyle(.secondary)
            }
        }
        .frame(width: size.width, height: size.height)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(WelcomePalette.separator, lineWidth: 0.5))
        .overlay(alignment: .topTrailing) {
            if let count = preview?.count, count > 1 {
                Text("\(count)").font(.caption2.weight(.semibold)).monospacedDigit()
                    .foregroundStyle(.white).padding(.horizontal, 6).frame(minWidth: 20, minHeight: 20)
                    .background(Capsule().fill(WelcomePalette.pine)).offset(x: 6, y: -6)
            }
        }
        .accessibilityHidden(true)
    }
}
