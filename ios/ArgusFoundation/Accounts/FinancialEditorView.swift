import SwiftUI
import ArgusSession

struct FinancialEditorView: View {
    @ObservedObject var model: FinancialEditor
    @Environment(\.dismiss) private var dismiss
    @Environment(\.locale) private var locale
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    HStack(spacing: 12) {
                        Image(systemName: AccountPresentation.symbol(model.account.type))
                        Text(model.account.nickname ?? NSLocalizedString("accounts.type." + model.account.type, comment: ""))
                        Spacer()
                        Text(verbatim: model.account.currency).foregroundStyle(ArgusStyle.secondary)
                    }
                    if model.canEdit {
                        // Keep entry off-screen during loading/coverage review so field
                        // remounts cannot invalidate in-flight coverage answers.
                        entry
                    }
                    if let preview = model.expensePreview { expenseReview(preview) }
                    if let preview = model.checkPreview { checkReview(preview) }
                    if let key = model.errorKey {
                        Text(LocalizedStringKey(key)).foregroundStyle(ArgusStyle.secondary)
                            .accessibilityIdentifier("loop.error")
                    }
                    if model.phase == .uncertain {
                        Text("loop.retry.same").font(ArgusStyle.body(13, relativeTo: .caption))
                    }
                    if model.phase == .conflict || model.phase == .retired {
                        Text(model.phase == .retired ? "auth.error.unauthorized" : "loop.conflict.review")
                        Button("action.close") { dismiss() }.buttonStyle(PillButtonStyle())
                    } else if model.canConfirm {
                        Button {
                            focused = false
                            Task { await model.confirm() }
                        } label: {
                            Text(model.phase == .uncertain ? "accounts.retry" : model.isCheck ? "loop.check.confirm" : "loop.expense.confirm")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(PillButtonStyle()).accessibilityIdentifier("loop.confirm")
                        if model.phase != .uncertain {
                            Button("loop.edit") { model.edit() }.frame(minHeight: 44)
                                .accessibilityIdentifier("loop.edit")
                        }
                    } else {
                        Button {
                            focused = false
                            Task { await model.review(locale: locale) }
                        } label: { Text("loop.review").frame(maxWidth: .infinity) }
                        .buttonStyle(PillButtonStyle()).disabled(!model.readyToReview || model.busy)
                        .accessibilityIdentifier("loop.review")
                        if model.phase == .review, model.expensePreview?.ready == false {
                            Button("loop.edit") { model.edit() }.frame(minHeight: 44)
                                .accessibilityIdentifier("loop.edit")
                        }
                    }
                    if model.busy { ProgressView("accounts.loading") }
                }.padding(24)
            }
            .background(ArgusStyle.background)
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle(model.isCheck ? "loop.check.title" : model.isCorrection ? "loop.correction.title" : "loop.expense.title")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                CuadraoCancelToolbar(title: NSLocalizedString("accounts.cancel", comment: ""),
                                     disabled: model.busy || model.phase == .uncertain) { dismiss() }
            }
            .interactiveDismissDisabled(model.busy || model.phase == .uncertain)
            .task { await model.loadCategories() }
        }
    }

    private var entry: some View {
        VStack(alignment: .leading, spacing: 22) {
            VStack(alignment: .leading, spacing: 8) {
                Text(model.isCheck && model.account.nature == "liability" ? "accounts.amount.owed" : "loop.amount")
                HStack {
                    TextField("0.00", text: $model.amount).keyboardType(.decimalPad).focused($focused)
                        .monospacedDigit().accessibilityIdentifier("loop.amount")
                    if model.isCheck {
                        Button {
                            model.amount = model.amount.hasPrefix("-") ? String(model.amount.dropFirst()) : "-" + model.amount
                        } label: { Image(systemName: "plus.forwardslash.minus").frame(width: 44, height: 44) }
                        .accessibilityLabel("accounts.amount.sign")
                    }
                }.padding(.horizontal, 14).frame(minHeight: 52)
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line))
            }
            DatePicker("loop.date", selection: $model.date, in: ...Date(), displayedComponents: .date)
                .accessibilityIdentifier("loop.date")
            VStack(alignment: .leading, spacing: 8) {
                Text("loop.note")
                TextField("loop.note.placeholder", text: $model.note, axis: .vertical)
                    .focused($focused).lineLimit(2...4).padding(14)
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line))
                    .accessibilityIdentifier("loop.note")
                Text("\(model.note.unicodeScalars.count)/200").font(ArgusStyle.body(11, relativeTo: .caption))
                    .foregroundStyle(ArgusStyle.secondary).frame(maxWidth: .infinity, alignment: .trailing)
            }
            if !model.isCheck && !model.categories.isEmpty {
                Picker("loop.category", selection: $model.categoryId) {
                    Text("loop.category.none").tag(nil as String?)
                    ForEach(model.categories) { category in
                        Text(LocalizedStringKey("loop.category." + category.id)).tag(Optional(category.id))
                    }
                }.accessibilityIdentifier("loop.category")
            }
            if model.isCorrection {
                VStack(alignment: .leading, spacing: 8) {
                    Text("accounts.reason")
                    TextField("accounts.reason", text: $model.reason, axis: .vertical).focused($focused)
                        .padding(14).overlay(RoundedRectangle(cornerRadius: 14).stroke(ArgusStyle.line))
                        .accessibilityIdentifier("loop.reason")
                }
            }
        }.disabled(model.busy)
    }

    private func expenseReview(_ preview: ExpensePreview) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            if preview.ready {
                value("loop.recorded", amount: preview.before.amount)
                value("loop.after", amount: preview.after?.amount)
                Text(model.note).font(ArgusStyle.body(14, relativeTo: .subheadline))
            } else {
                Text("loop.coverage.question").font(ArgusStyle.display(22))
            }
            ForEach(preview.observations, id: \.observationId) { observation in
                VStack(alignment: .leading, spacing: 10) {
                    Text(observation.kind == "opening" ? "loop.coverage.opening" : "loop.coverage.check")
                    Text(verbatim: AccountPresentation.date(observation.asOf, zone: model.account.opening?.timeZone ?? TimeZone.current.identifier, locale: locale))
                        .font(ArgusStyle.body(13, relativeTo: .caption))
                    Text(verbatim: model.account.currency + " " + AccountPresentation.amount(observation.amount, locale: locale)).monospacedDigit()
                    if model.phase != .uncertain {
                        HStack {
                            Button("loop.coverage.yes") {
                                model.answer(observation.observationId, included: true)
                                Task { await model.review(locale: locale) }
                            }.buttonStyle(PillButtonStyle(primary: observation.included == true)).accessibilityIdentifier((observation.included == nil ? "loop.coverage.yes." : "loop.coverage.change.yes.") + observation.kind + "." + observation.observationId.uuidString)
                            Button("loop.coverage.no") {
                                model.answer(observation.observationId, included: false)
                                Task { await model.review(locale: locale) }
                            }.buttonStyle(PillButtonStyle(primary: observation.included == false)).accessibilityIdentifier((observation.included == nil ? "loop.coverage.no." : "loop.coverage.change.no.") + observation.kind + "." + observation.observationId.uuidString)
                        }.disabled(model.busy)
                    } else {
                        Text(observation.included == true ? "loop.coverage.included" : "loop.coverage.excluded")
                            .font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
                    }
                }
            }
        }
    }

    private func checkReview(_ preview: BalanceCheckPreview) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            minorValue("loop.recorded", amount: preview.expectedAmountMinor, digits: preview.currencyFractionDigits)
            minorValue("loop.observed", amount: preview.observedAmountMinor, digits: preview.currencyFractionDigits)
            minorValue("loop.difference", amount: preview.differenceMinor, digits: preview.currencyFractionDigits)
            Text(verbatim: AccountPresentation.date(preview.asOf, zone: preview.timeZone, locale: locale))
                .font(ArgusStyle.body(13, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
            Text(preview.differenceMinor == nil ? "loop.check.unknown" : preview.differenceMinor == 0 ? "loop.check.matches" : "loop.check.adjustment")
                .font(ArgusStyle.body(14, relativeTo: .subheadline))
            if preview.differenceMinor != nil && preview.differenceMinor != 0 {
                Text("loop.check.missing").font(ArgusStyle.body(13, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
            }
        }
    }

    private func minorValue(_ label: LocalizedStringKey, amount: Int64?, digits: Int) -> some View {
        value(label, amount: amount.map { AccountPresentation.decimal($0, digits: digits) })
    }
    private func value(_ label: LocalizedStringKey, amount: String?) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).foregroundStyle(ArgusStyle.secondary)
            Spacer()
            if let amount { Text(verbatim: model.account.currency + " " + AccountPresentation.amount(amount, locale: locale)).monospacedDigit() }
            else { Text("accounts.unknown") }
        }.font(ArgusStyle.body(14, relativeTo: .subheadline))
    }
}
