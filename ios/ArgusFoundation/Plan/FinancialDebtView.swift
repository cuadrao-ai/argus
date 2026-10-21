import SwiftUI
import ArgusSession

struct FinancialDebtList: View {
    @ObservedObject var plan: FinancialPlanModel
    @ObservedObject var model: FinancialDebtModel
    let origin: FinancialDebtNavigation.Origin
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("plan.debts").font(ArgusStyle.display(23))
            let items = plan.projection?.debts ?? []
            if items.filter({ !$0.debt.archived }).isEmpty { Text("debt.empty").foregroundStyle(ArgusStyle.secondary) }
            ForEach(items.filter { !$0.debt.archived }) { progress in row(progress) }
        }
    }
    private func row(_ progress: FinancialDebtProgress) -> some View {
        Button { Task { await model.open(progress.id, origin: origin) } } label: {
            VStack(alignment: .leading, spacing: 10) {
                HStack { Text(verbatim: progress.debt.name); Spacer(); Image(systemName: "chevron.right") }
                FinancialDebtSummary(progress: progress)
            }.padding(.vertical, 14).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier("debt.row." + origin.rawValue + "." + progress.id.uuidString)
    }
}

struct FinancialDebtSummary: View {
    let progress: FinancialDebtProgress
    @Environment(\.locale) private var locale
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(progress.balance.creditMinor != nil && progress.balance.creditMinor != 0 ? "debt.credit" : "debt.recorded")
            Text(verbatim: money(progress.balance.creditMinor != nil && progress.balance.creditMinor != 0 ? progress.balance.creditMinor.map(String.init) : progress.balance.amountMinor.map(String.init)))
                .font(ArgusStyle.display(28)).monospacedDigit().accessibilityIdentifier("debt.recorded")
            Text(LocalizedStringKey("debt.state." + progress.state)).foregroundStyle(progress.state == "needs_review" ? ArgusStyle.negative : ArgusStyle.secondary).accessibilityIdentifier("debt.state")
        }
    }
    private func money(_ minor: String?) -> String { minor.map { PlanPresentation.money($0, currency: progress.debt.currency, digits: progress.debt.currencyFractionDigits, locale: locale) } ?? NSLocalizedString("accounts.unknown", comment: "") }
}

struct FinancialDebtFunding: View {
    let pool: FinancialGoalPool
    let digits: Int
    @Environment(\.locale) private var locale
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            DisclosureGroup("debt.funding") {
                VStack(alignment: .leading, spacing: 10) {
                    PlanValueRow(title: "debt.funding.recorded", value: money(pool.backingMinor))
                    PlanValueRow(title: "debt.funding.assigned", value: money(pool.assignedMinor))
                    PlanValueRow(title: "debt.funding.available", value: money(pool.availableMinor)).accessibilityIdentifier("debt.funding.available")
                    if pool.state == "shortfall" {
                        PlanValueRow(title: "goal.shortfall", value: money(pool.shortfallMinor))
                        Text(pool.affectedGoalNames.joined(separator: " · "))
                    }
                }.padding(.top, 12)
            }
            if pool.state == "shortfall" {
                Text("goal.reason.pool_shortfall").foregroundStyle(ArgusStyle.negative).accessibilityIdentifier("debt.funding.shortfall")
            }
        }
    }
    private func money(_ value: String?) -> String { value.map { PlanPresentation.money($0, currency: pool.currency, digits: digits, locale: locale) } ?? NSLocalizedString("accounts.unknown", comment: "") }
}

struct FinancialDebtPresenter: View {
    @ObservedObject var model: FinancialDebtModel
    @ObservedObject var loop: FinancialLoopModel
    @Binding var destination: AppDestination
    let search: FinancialSearchModel?
    var body: some View {
        ZStack {
            if model.navigation != nil {
                NavigationStack {
                    FinancialDebtDetail(model: model, loop: loop) {
                        switch model.navigation?.origin { case .home: destination = .home; case .plan, .planOverview: destination = .plan; case .search, .searchAccount: destination = .search; case .account: destination = .accounts; case nil: break }
                        model.close(); Task { await search?.refresh() }
                    }
                }.tint(WelcomePalette.pine).foregroundStyle(WelcomePalette.ink)
                    .accessibilityElement(children: .contain).accessibilityIdentifier("debt.detail")
            } else { Color.clear.allowsHitTesting(false) }
        }
        .background { FinancialDebtSheets(model: model, loop: loop, search: search) }
    }
}

struct FinancialDebtSheets: View {
    @ObservedObject var model: FinancialDebtModel
    @ObservedObject var loop: FinancialLoopModel
    let search: FinancialSearchModel?
    var body: some View {
        Color.clear.frame(width: 0, height: 0)
            .sheet(item: $model.draft, onDismiss: { Task { await search?.refresh() } }) { draft in ConnectedPlanEditor(loop: loop, seed: .debt(draft)) }
            .sheet(isPresented: $model.choosingAccount, onDismiss: model.accountChooserDismissed) {
                NavigationStack {
                    List((loop.plan.projection?.accounts ?? []).filter { account in !account.archived && ["credit_card", "other_debt"].contains(account.type) && !(loop.plan.projection?.debts ?? []).contains(where: { !$0.debt.archived && $0.debt.debtAccountId == account.id }) }) { account in
                        Button(loop.accountName(account.id)) { model.chooseAccount(account) }.accessibilityIdentifier("debt.account." + account.id.uuidString)
                    }.navigationTitle("debt.chooseAccount").toolbar { CuadraoCancelToolbar(title: "accounts.cancel") { model.choosingAccount = false } }
                }
            }
            .sheet(isPresented: $model.linking) { FinancialDebtLinkView(model: model, loop: loop) }
    }
}

struct FinancialDebtDetail: View {
    @ObservedObject var model: FinancialDebtModel
    @ObservedObject var loop: FinancialLoopModel
    var nativeNavigation = false
    let close: () -> Void
    @State private var archiving = false
    @Environment(\.locale) private var locale
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    var body: some View {
        ScrollViewReader { reader in
            CuadraoPlanDetailPage(scroll: nativeNavigation ? model.scrollContext : nil) {
                if !nativeNavigation, let id = model.navigation?.activityID { FinancialActivityDetailView(loop: loop, activityID: id) { loop.correct($0) } }
                else if let progress = model.detail {
                    heading(progress)
                    if progress.state == "recorded_clear" {
                        PlanLandscape(look: .bloom).frame(height: 135)
                    }
                    if let scenario = ConnectedPlanScenario.debt(progress, now: Date()) {
                        CuadraoPlanWhatIf(scenario: scenario, spanish: spanish, apply: applyMonthly(progress), showsDisclosure: true)
                    }
                    if let pool = progress.fundingPool { FinancialDebtFunding(pool: pool, digits: progress.debt.currencyFractionDigits) }
                    if !progress.debt.archived {
                        occurrencePicker(progress)
                        Button { model.record() } label: {
                            Label("debt.record", systemImage: "plus.circle").frame(minHeight: 44)
                        }.accessibilityIdentifier("debt.record")
                        Button("debt.extra") { model.record(extra: true) }.frame(minHeight: 44).accessibilityIdentifier("debt.extra")
                        Button("debt.link") { Task { await model.loadCandidates() } }.frame(minHeight: 44).accessibilityIdentifier("debt.link")
                    }
                    CuadraoPlanDetailFacts(spanish: spanish) {
                        PlanValueRow(title: "debt.source", value: loop.accountName(progress.debt.sourceAccountId))
                        PlanValueRow(title: "debt.amount", value: money(String(progress.debt.amountMinor), progress))
                        Text(LocalizedStringKey("plan.repeat." + progress.debt.schedule.cadence.rawValue))
                        Text("debt.plan.disclosure").foregroundStyle(.secondary)
                        Text("debt.estimate").font(CuadraoTypography.section)
                        payoff(progress)
                    }
                    Text("debt.payments").font(CuadraoTypography.section)
                    if progress.payments.isEmpty { Text("debt.noPayments").foregroundStyle(ArgusStyle.secondary) }
                    ForEach(progress.payments) { payment in
                        Button { model.activity(payment.activityId, preservingScrollPosition: nativeNavigation) } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack { Text(payment.activity?.note ?? NSLocalizedString("debt.payment", comment: "")); Spacer(); Text(verbatim: money(payment.netPaidMinor.map(String.init), progress)); Image(systemName: "chevron.right") }
                                Text(LocalizedStringKey("debt.payment." + payment.status)).foregroundStyle(ArgusStyle.secondary)
                            }.frame(minHeight: 48).contentShape(Rectangle())
                        }.buttonStyle(.plain).id(payment.activityId).accessibilityIdentifier("debt.activity." + payment.activityId.uuidString)
                            .financialScrollAnchor(payment.activityId.uuidString)
                    }
                    if progress.debt.archived {
                        PlanPrimaryButton(title: NSLocalizedString("debt.restore", comment: "")) { Task { await model.archive(false) } }
                            .accessibilityIdentifier("debt.restore")
                    }
                }
                if model.loading { ProgressView("accounts.loading") }
                if let key = model.errorKey { Text(LocalizedStringKey(key)).accessibilityIdentifier("debt.error"); Button("accounts.retry") { Task { await model.refreshIfOpen() } } }
                if loop.pendingConfirmation != nil { PlanPendingView(loop: loop) }
            }.disabled(model.saving).task(id: model.detail?.payments.map(\.activityId)) {
                guard !nativeNavigation, let anchor = model.navigation?.anchor else { return }
                await Task.yield()
                guard !Task.isCancelled else { return }
                reader.scrollTo(anchor, anchor: .top)
            }
        }
        .navigationDestination(isPresented: activityPresented) {
            if let id = model.navigation?.activityID {
                ScrollView {
                    FinancialActivityDetailView(loop: loop, activityID: id) { loop.correct($0) }.padding(24)
                }
                .background(WelcomePalette.background)
                .navigationTitle("loop.activity.title").navigationBarTitleDisplayMode(.inline)
                .toolbar(.visible, for: .navigationBar)
            }
        }
        .navigationTitle("").navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
        .toolbar {
            if !nativeNavigation {
                ToolbarItem(placement: .topBarLeading) {
                    if model.navigation?.activityID != nil {
                        Button { model.activity(nil); Task { await model.refreshIfOpen() } } label: { Label("debt.back", systemImage: "chevron.left") }
                            .accessibilityIdentifier("debt.activity.back")
                    } else {
                        Button(action: close) { Image(systemName: "chevron.left").frame(width: 44, height: 44) }
                            .accessibilityLabel("action.close").accessibilityIdentifier("debt.close")
                    }
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                if model.navigation?.activityID == nil, let progress = model.detail, !progress.debt.archived {
                    CuadraoPlanDetailOptions(spanish: spanish) {
                        Button { model.edit() } label: { Label("debt.edit", systemImage: "pencil") }.accessibilityIdentifier("debt.edit")
                        Button { archiving = true } label: { Label("debt.archive", systemImage: "archivebox") }.accessibilityIdentifier("debt.archive")
                    }.disabled(model.saving)
                } else if !nativeNavigation, model.navigation?.activityID != nil {
                    Button(action: close) { Image(systemName: "xmark").frame(width: 44, height: 44) }
                        .accessibilityLabel("action.close").accessibilityIdentifier("debt.close")
                }
            }
        }
        .confirmationDialog("debt.archive", isPresented: $archiving, titleVisibility: .visible) {
            Button("debt.archive") { Task { await model.archive(true) } }.accessibilityIdentifier("debt.archive.confirm")
            Button("accounts.cancel", role: .cancel) { }
        } message: { Text("debt.archive.disclosure") }
    }
    private var activityPresented: Binding<Bool> {
        let captured = model.navigation
        return Binding(get: { nativeNavigation && model.navigation?.activityID != nil }, set: { presented in
            guard nativeNavigation, !presented, let captured, let activityID = captured.activityID,
                  let current = model.navigation, current.debtID == captured.debtID,
                  current.origin == captured.origin, current.activityID == activityID else { return }
            model.activity(nil)
            Task { await model.refreshIfOpen() }
        })
    }
    private func heading(_ progress: FinancialDebtProgress) -> some View {
        let credit = progress.balance.creditMinor != nil && progress.balance.creditMinor != 0
        return CuadraoPlanDetailHeading(display: .init(
            name: progress.debt.name, space: NSLocalizedString("context.personal", comment: ""), look: .bloom,
            amount: money((credit ? progress.balance.creditMinor : progress.balance.amountMinor).map(String.init), progress),
            annotation: NSLocalizedString(credit ? "debt.credit" : "debt.recorded", comment: ""), amountIdentifier: "debt.recorded")) {
            Text(LocalizedStringKey("debt.state." + progress.state)).font(.subheadline)
                .foregroundStyle(progress.state == "needs_review" ? ArgusStyle.negative : ArgusStyle.secondary)
                .accessibilityIdentifier("debt.state")
        }
    }
    private func occurrencePicker(_ progress: FinancialDebtProgress) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Picker("debt.occurrence", selection: Binding(get: { model.occurrenceID }, set: { model.chooseOccurrence($0) })) {
                Text("debt.extra").tag(nil as String?)
                ForEach(progress.occurrences) { occurrence in Text(PlanPresentation.dateLabel(occurrence.dueDate, locale: locale)).tag(Optional(occurrence.id)) }
            }.accessibilityIdentifier("debt.occurrence")
            if let occurrence = progress.occurrences.first(where: { $0.id == model.occurrenceID }) {
                PlanValueRow(title: "debt.paid", value: money(occurrence.paidMinor.map(String.init), progress))
                PlanValueRow(title: "debt.remaining", value: money(occurrence.remainingMinor.map(String.init), progress)).accessibilityIdentifier("debt.remaining")
                Text(LocalizedStringKey("plan.status." + occurrence.status.rawValue))
                if occurrence.overdue { Text("plan.overdue").foregroundStyle(ArgusStyle.secondary) }
            }
        }
    }
    private func payoff(_ progress: FinancialDebtProgress) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if let date = progress.payoff.payoffDate {
                Text("debt.estimate.conditional"); Text(PlanPresentation.dateLabel(date, locale: locale)).accessibilityIdentifier("debt.payoff")
                if let count = progress.payoff.payments { PlanValueRow(title: "debt.estimate.payments", value: String(count)) }
                PlanValueRow(title: "debt.interest", value: money(progress.payoff.totalInterestMinor, progress))
                PlanValueRow(title: "debt.fees", value: money(progress.payoff.totalFeesMinor, progress))
            } else { Text(LocalizedStringKey("debt.payoff." + (progress.payoff.reason ?? "terms_missing"))) }
            if let assumptions = progress.payoff.assumptions {
                PlanValueRow(title: "debt.rate", value: assumptions.annualRatePercent + "%")
                PlanValueRow(title: "debt.fees", value: progress.debt.currency + " " + AccountPresentation.amount(assumptions.recurringFees, locale: locale))
            }
            Text("debt.estimate.assumptions").font(ArgusStyle.body(12, relativeTo: .caption)).foregroundStyle(ArgusStyle.secondary)
        }
    }
    private func applyMonthly(_ progress: FinancialDebtProgress) -> ((Double) -> Void)? {
        guard progress.debt.schedule.cadence == .monthly, !progress.debt.archived, loop.pendingConfirmation == nil else { return nil }
        return { monthly in
            let draft = FinancialDebtDraft(debt: progress.debt)
            draft.amount = ConnectedPlanScenario.draftAmount(monthly, digits: progress.debt.currencyFractionDigits, locale: locale)
            Task { await model.save(draft, locale: locale) }
        }
    }
    private func money(_ value: String?, _ progress: FinancialDebtProgress) -> String { value.map { PlanPresentation.money($0, currency: progress.debt.currency, digits: progress.debt.currencyFractionDigits, locale: locale) } ?? NSLocalizedString("accounts.unknown", comment: "") }
}

struct FinancialDebtLinkView: View {
    @ObservedObject var model: FinancialDebtModel
    @ObservedObject var loop: FinancialLoopModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.locale) private var locale
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("debt.link.disclosure").foregroundStyle(ArgusStyle.secondary)
                    if model.loading { ProgressView("accounts.loading") }
                    if model.candidates.isEmpty && !model.loading { Text("debt.link.empty").accessibilityIdentifier("debt.link.empty") }
                    ForEach(model.candidates) { entry in
                        Button { Task { await model.link(entry) } } label: {
                            HStack { Text(entry.note ?? NSLocalizedString("debt.payment", comment: "")); Spacer(); Text(verbatim: entry.currency + " " + AccountPresentation.amount(entry.amount, locale: locale)) }.frame(minHeight: 48).contentShape(Rectangle())
                        }.buttonStyle(.plain).disabled(model.saving || loop.pendingConfirmation != nil).accessibilityIdentifier("debt.candidate." + entry.activityId.uuidString)
                    }
                    if let key = model.errorKey { Text(LocalizedStringKey(key)).accessibilityIdentifier("debt.error") }
                    if loop.pendingConfirmation != nil { PlanPendingView(loop: loop) }
                }.padding(24)
            }.navigationTitle("debt.link").toolbar { CuadraoCancelToolbar(title: "accounts.cancel", disabled: model.saving, identifier: "debt.action.cancel") { dismiss() }}
        }
    }
}

private struct FinancialDebtOcclusion: ViewModifier {
    @ObservedObject var model: FinancialDebtModel
    func body(content: Content) -> some View { content.accessibilityHidden(model.navigation != nil).allowsHitTesting(model.navigation == nil) }
}
extension View {
    @ViewBuilder func financialDebtBackground(_ model: FinancialDebtModel?) -> some View { if let model { modifier(FinancialDebtOcclusion(model: model)) } else { self } }
}
