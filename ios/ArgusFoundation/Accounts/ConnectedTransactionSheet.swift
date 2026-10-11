import SwiftUI
import ArgusSession

/// Hosts FinancialActivityEditor in the Preview's record-movement sheet. The model owns every phase,
/// the review preview and the confirm command; this view only binds fields and the two actions.
struct ConnectedTransactionSheet: View {
    @ObservedObject var model: FinancialActivityEditor
    @Environment(\.dismiss) private var dismiss
    @Environment(\.locale) private var locale
    @FocusState private var focused: Bool
    @State private var amountError = ""
    @State private var currency = ""

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    private var reviewing: Bool { model.phase != .editing }
    private var closed: Bool { model.phase == .conflict || model.phase == .retired }
    private var locked: Bool { model.busy || model.phase == .uncertain }
    /// Until every coverage question is answered the primary action re-runs the review, as the loop.* contract expects.
    private var confirmable: Bool { model.canConfirm || model.phase == .uncertain }

    var body: some View {
        CuadraoTransactionSheet(
            account: CuadraoTransactionAccount(title: name(model.origin), artwork: ConnectedAccountPresentation.artwork(model.origin.type),
                                               symbol: AccountPresentation.symbol(model.origin.type)),
            spanish: spanish, reviewing: reviewing, title: title, primaryTitle: primaryTitle,
            primaryEnabled: primaryEnabled, primaryBusy: model.busy,
            primaryIdentifier: closed ? nil : reviewing && confirmable ? "loop.confirm" : "loop.review",
            cancelDisabled: locked, dismissDisabled: locked,
            scrollTarget: model.focusCategory && model.options != nil && !reviewing ? "loop.category" : nil,
            back: { model.edit() }, primary: primaryAction) {
            if reviewing { review } else { entry }
            if let error = model.errorKey {
                Text(LocalizedStringKey(error)).font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("loop.error")
            }
            if model.phase == .uncertain { Text("loop.retry.same").font(.caption).foregroundStyle(.secondary) }
            if closed { Text(model.phase == .retired ? "auth.error.unauthorized" : "loop.conflict.review").font(.subheadline) }
            if reviewing, !locked, !closed, model.canConfirm || model.preview?.ready == false {
                Button("loop.edit") { model.edit() }.font(.subheadline)
                    .frame(maxWidth: .infinity, minHeight: 44).accessibilityIdentifier("loop.edit")
            }
        }
        .task { await model.load() }
        .onAppear { currency = model.origin.currency }
    }

    private var title: String? {
        model.isCorrection ? NSLocalizedString("loop.correction.title", comment: "") : nil
    }
    private var primaryTitle: String? {
        if closed { return NSLocalizedString("action.close", comment: "") }
        if model.phase == .uncertain { return NSLocalizedString("accounts.retry", comment: "") }
        if reviewing, !confirmable { return NSLocalizedString("loop.review", comment: "") }
        if reviewing, model.isCorrection { return NSLocalizedString("loop.activity.saveCorrection", comment: "") }
        return nil
    }
    private var primaryEnabled: Bool {
        if closed || model.phase == .uncertain { return true }
        if reviewing { return confirmable || (model.phase == .review && !model.busy) }
        return model.readyToReview && !model.busy && model.options != nil && amountError.isEmpty
    }
    private func primaryAction() {
        focused = false
        if closed { dismiss(); return }
        Task {
            if reviewing, confirmable {
                await model.confirm()
                if model.phase == .saved { dismiss() }
            } else {
                await model.review(locale: locale)
            }
        }
    }

    // MARK: Entry

    @ViewBuilder private var entry: some View {
        if let occurrence = model.planOccurrence {
            VStack(alignment: .leading, spacing: 6) {
                Text(occurrence.title).font(CuadraoTypography.section)
                Text("plan.record.disclosure").font(.subheadline).foregroundStyle(.secondary)
            }
        }
        if model.options == nil && model.phase == .editing {
            if model.errorKey == nil { ProgressView("accounts.loading") }
            else { Button("accounts.retry") { Task { await model.load() } }.frame(minHeight: 44) }
        } else if model.canEdit {
            kindRow
            accountRows
            CuadraoAmountField(raw: $model.amount, currency: $currency, error: $amountError, spanish: spanish,
                               currencySelectable: false, identifier: "loop.amount")
            if model.needsLoanSplit {
                field(NSLocalizedString("debt.principal", comment: ""), text: $model.principal, id: "loop.principal", decimal: true)
                field(NSLocalizedString("debt.interest", comment: ""), text: $model.interest, id: "loop.interest", decimal: true)
                field(NSLocalizedString("debt.fees", comment: ""), text: $model.fees, id: "loop.fees", decimal: true)
                Text("debt.split.disclosure").font(.caption).foregroundStyle(.secondary)
            }
            if model.returning != nil { Text("debt.return.disclosure").font(.caption).foregroundStyle(.secondary) }
            DatePicker(spanish ? "Fecha" : "Date", selection: $model.date, in: ...Date(), displayedComponents: .date)
                .accessibilityIdentifier("loop.date")
            if model.kind == .income {
                choice(NSLocalizedString("loop.activity.source", comment: ""), selection: $model.sourceId,
                       values: model.options?.sources ?? [], id: "loop.sourceType",
                       none: NSLocalizedString("loop.category.none", comment: "")) { NSLocalizedString("loop.source." + $0, comment: "") }
            }
            if model.kind == .refund {
                choice(NSLocalizedString("loop.activity.purchase", comment: ""), selection: $model.purchaseActivityId,
                       values: model.purchases.map(\.activityId), id: "loop.purchase",
                       none: NSLocalizedString("loop.activity.purchaseNone", comment: "")) { id in
                    model.purchases.first { $0.activityId == id }.map(purchaseLabel) ?? ""
                }
                if model.purchaseActivityId != nil { Text("loop.activity.linkedCategory").font(.caption).foregroundStyle(.secondary) }
            }
            if model.kind == .expense || (model.kind == .refund && model.purchaseActivityId == nil) {
                choice(NSLocalizedString("loop.category", comment: ""), selection: $model.categoryId,
                       values: model.options?.categories ?? [], id: "loop.category",
                       none: NSLocalizedString("loop.category.none", comment: "")) { NSLocalizedString("loop.category." + $0, comment: "") }
                    .id("loop.category")
            }
            VStack(alignment: .leading, spacing: 8) {
                TextField(spanish ? "Concepto (opcional)" : "Description (optional)", text: $model.note, axis: .vertical)
                    .focused($focused).lineLimit(1...4).modifier(RegistrationField())
                    .accessibilityIdentifier("loop.note")
                Text("\(model.note.unicodeScalars.count)/200").font(.caption)
                    .foregroundStyle(model.note.unicodeScalars.count > 200 ? .red : .secondary)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            if model.isCorrection {
                field(NSLocalizedString("accounts.reason", comment: ""), text: $model.reason, id: "loop.reason")
            }
        }
    }

    @ViewBuilder private var kindRow: some View {
        if !model.isCorrection && model.planOccurrence == nil && model.goal == nil && model.debt == nil && model.returning == nil {
            ScrollView(.horizontal) {
                HStack(spacing: 8) {
                    ForEach(model.availableKinds, id: \.self) { kind in
                        Button { model.setKind(kind) } label: {
                            Text(LocalizedStringKey("loop.kind." + kind.rawValue)).font(.subheadline)
                                .padding(.horizontal, 14).frame(minHeight: 44)
                                .foregroundStyle(model.kind == kind ? WelcomePalette.onAccent : WelcomePalette.ink)
                                .background(model.kind == kind ? WelcomePalette.pine : WelcomePalette.surface, in: Capsule())
                        }.accessibilityIdentifier("loop.kind." + kind.rawValue)
                            .accessibilityAddTraits(model.kind == kind ? .isSelected : [])
                    }
                }
            }.scrollIndicators(.hidden)
        } else {
            Label(LocalizedStringKey("loop.kind." + model.kind.rawValue), systemImage: FinancialActivityPresentation.symbol(for: model.kind.rawValue))
                .font(.subheadline)
        }
    }

    @ViewBuilder private var accountRows: some View {
        if model.kind == .paymentReversal {
            accountChoice("loop.activity.from", selection: $model.destinationAccountId, choices: model.destinationChoices, id: "loop.destination")
            accountChoice("loop.activity.to", selection: $model.sourceAccountId, choices: model.sourceChoices, id: "loop.source")
        } else if model.kind.isPaired {
            accountChoice("loop.activity.from", selection: $model.sourceAccountId, choices: model.sourceChoices, id: "loop.source")
            accountChoice(model.kind == .cardPayment ? "loop.activity.card" : "loop.activity.to",
                          selection: $model.destinationAccountId, choices: model.destinationChoices, id: "loop.destination")
        } else {
            accountChoice(model.kind == .refund ? "loop.activity.refundTo" : "loop.activity.account",
                          selection: $model.accountId, choices: model.singleChoices, id: "loop.account")
        }
    }

    private func accountChoice(_ key: String, selection: Binding<UUID?>, choices: [FinancialAccount], id: String) -> some View {
        choice(NSLocalizedString(key, comment: ""), selection: selection, values: choices.map(\.id), id: id,
               none: NSLocalizedString("loop.activity.chooseAccount", comment: "")) { value in
            choices.first { $0.id == value }.map(name) ?? ""
        }
    }

    private func choice<Value: Hashable>(_ caption: String, selection: Binding<Value?>, values: [Value], id: String,
                                         none: String, title: @escaping (Value) -> String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(caption).font(.caption).foregroundStyle(.secondary).accessibilityIdentifier(id + ".label")
            CuadraoChoiceMenu(title: caption, selection: selection, values: [nil] + values.map(Optional.some),
                              valueTitle: { $0.map(title) ?? none })
                .accessibilityIdentifier(id)
        }
    }

    private func field(_ caption: String, text: Binding<String>, id: String, decimal: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(caption).font(.caption).foregroundStyle(.secondary)
            TextField(decimal ? "0.00" : caption, text: text)
                .keyboardType(decimal ? .decimalPad : .default).focused($focused)
                .modifier(RegistrationField()).accessibilityIdentifier(id)
        }
    }

    // MARK: Review

    @ViewBuilder private var review: some View {
        let amount = Decimal(string: model.amount) ?? 0
        Text(sign + CanvasMoney.format(amount, currency: model.origin.currency))
            .font(CuadraoTypography.amount).monospacedDigit()
        LabeledContent(spanish ? "Moneda" : "Currency", value: model.origin.currency)
        LabeledContent(spanish ? "Tipo" : "Type", value: NSLocalizedString("loop.kind." + model.kind.rawValue, comment: ""))
        ForEach(reviewAccounts, id: \.0) { row in LabeledContent(row.0, value: row.1) }
        if let category = model.categoryId, model.kind == .expense || model.linkedPurchase == nil {
            LabeledContent(NSLocalizedString("loop.category", comment: ""), value: NSLocalizedString("loop.category." + category, comment: ""))
        }
        if !model.note.isEmpty { LabeledContent(spanish ? "Concepto" : "Description", value: model.note) }
        LabeledContent(spanish ? "Fecha" : "Date") { Text(model.date, format: .dateTime.day().month().year()) }
        if let preview = model.preview { impact(preview) }
    }

    private var sign: String {
        switch model.kind {
        case .income, .refund: "+"
        case .expense: "−"
        default: ""
        }
    }

    private var reviewAccounts: [(String, String)] {
        let from = NSLocalizedString("loop.activity.from", comment: ""), to = NSLocalizedString("loop.activity.to", comment: "")
        if model.kind == .paymentReversal {
            return [(from, name(model.destinationAccountId)), (to, name(model.sourceAccountId))]
        }
        if model.kind.isPaired {
            return [(from, name(model.sourceAccountId)),
                    (NSLocalizedString(model.kind == .cardPayment ? "loop.activity.card" : "loop.activity.to", comment: ""), name(model.destinationAccountId))]
        }
        return [(NSLocalizedString("loop.activity.account", comment: ""), name(model.accountId))]
    }

    @ViewBuilder private func impact(_ preview: FinancialActivityPreview) -> some View {
        Text(preview.ready ? "loop.activity.impact" : "loop.coverage.question").font(CuadraoTypography.section)
        ForEach(preview.affectedAccounts) { affected in
            VStack(alignment: .leading, spacing: 12) {
                Text(name(affected.accountId)).font(CuadraoTypography.supporting)
                balance("loop.recorded", value: affected.before, currency: affected.currency)
                if let after = affected.after { balance("loop.after", value: after, currency: affected.currency) }
                ForEach(affected.observations, id: \.observationId) { observation in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(observation.kind == "opening" || observation.kind == "opening_balance" ? "loop.coverage.opening" : "loop.coverage.check")
                        Text(verbatim: observation.timeZone.map { AccountPresentation.date(observation.asOf, zone: $0, locale: locale) } ?? observation.asOf)
                            .font(.caption).foregroundStyle(.secondary)
                        if model.phase != .uncertain {
                            HStack(spacing: 8) {
                                coverageButton("loop.coverage.yes", selected: observation.included == true,
                                               id: "loop.coverage.yes." + affected.accountId.uuidString + "." + observation.observationId.uuidString) {
                                    await model.answerAndReview(accountId: affected.accountId, observationId: observation.observationId, included: true, locale: locale)
                                }
                                coverageButton("loop.coverage.no", selected: observation.included == false,
                                               id: "loop.coverage.no." + affected.accountId.uuidString + "." + observation.observationId.uuidString) {
                                    await model.answerAndReview(accountId: affected.accountId, observationId: observation.observationId, included: false, locale: locale)
                                }
                            }
                        }
                    }.font(.subheadline)
                }
            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 20))
        }
        if let result = model.goalPreview, preview.ready {
            Text("goal.afterContribution").font(CuadraoTypography.section)
            FinancialGoalSummary(progress: result.goal, compact: true)
            ForEach(result.pools.filter { $0.state == "shortfall" && !$0.affectedGoalIds.isEmpty && ($0.accountId == model.sourceAccountId || $0.accountId == model.destinationAccountId) }) { pool in
                VStack(alignment: .leading, spacing: 8) {
                    Text(name(pool.accountId))
                    Text("goal.reason.pool_shortfall").foregroundStyle(WelcomePalette.owedNegative)
                    Text(pool.affectedGoalNames.joined(separator: " · "))
                    Text(PlanPresentation.money(pool.shortfallMinor ?? "0", currency: pool.currency, digits: result.goal.goal.currencyFractionDigits, locale: locale))
                }.font(.subheadline)
            }
        }
        if let result = model.debtPreview, preview.ready, let pool = result.debt.fundingPool {
            FinancialDebtFunding(pool: pool, digits: result.debt.debt.currencyFractionDigits)
        }
        if model.kind == .debtPayment { Text("debt.cost.disclosure").font(.caption).foregroundStyle(.secondary) }
        if model.kind == .transfer || model.kind == .cardPayment { Text("loop.activity.pairNote").font(.caption).foregroundStyle(.secondary) }
        if model.kind == .refund { Text("loop.activity.refundNote").font(.caption).foregroundStyle(.secondary) }
    }

    private func coverageButton(_ key: LocalizedStringKey, selected: Bool, id: String, action: @escaping () async -> Void) -> some View {
        Button { Task { await action() } } label: {
            Text(key).font(.subheadline).padding(.horizontal, 14).frame(minHeight: 44)
                .foregroundStyle(selected ? WelcomePalette.onAccent : WelcomePalette.ink)
                .background(selected ? WelcomePalette.pine : WelcomePalette.background, in: Capsule())
                .overlay { Capsule().stroke(selected ? WelcomePalette.pine : WelcomePalette.border) }
        }.accessibilityIdentifier(id).accessibilityAddTraits(selected ? .isSelected : [])
    }

    private func balance(_ label: LocalizedStringKey, value: FinancialBalance, currency: String) -> some View {
        LabeledContent(label) {
            if let amount = value.amount {
                Text(verbatim: currency + " " + AccountPresentation.amount(amount, locale: locale)).monospacedDigit()
            } else { Text("accounts.unknown") }
        }.font(.subheadline)
    }

    private func name(_ account: FinancialAccount) -> String {
        account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: "")
    }
    private func name(_ id: UUID?) -> String {
        guard let account = model.options?.accounts.first(where: { $0.id == id }) else { return name(model.origin) }
        return name(account)
    }
    private func purchaseLabel(_ purchase: FinancialActivityDetail) -> String {
        let title = purchase.note ?? purchase.categoryId.map { NSLocalizedString("loop.category." + $0, comment: "") }
            ?? NSLocalizedString("loop.kind.expense", comment: "")
        return title + " · " + purchase.currency + " " + AccountPresentation.amount(purchase.amount, locale: locale)
    }
}
