import SwiftUI
import ArgusSession

/// The approved Preview editor over the connected drafts; every save goes through the kind model's save seam.
struct ConnectedPlanEditor: View {
    enum Seed {
        case create(kind: CanvasPlanKind?)
        case goal(FinancialGoalDraft)
        case budget(FinancialBudgetDraft)
        case debt(FinancialDebtDraft)
    }
    @ObservedObject private var loop: FinancialLoopModel
    @ObservedObject private var goals: FinancialGoalModel
    @ObservedObject private var budgets: FinancialBudgetModel
    @ObservedObject private var debts: FinancialDebtModel
    private let seed: Seed
    private let initial: CanvasPlan
    @State private var kind: CanvasPlanKind
    @State private var details: ConnectedPlanDetails
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss

    init(loop: FinancialLoopModel, seed: Seed) {
        _loop = ObservedObject(wrappedValue: loop)
        _goals = ObservedObject(wrappedValue: loop.goals)
        _budgets = ObservedObject(wrappedValue: loop.budgets)
        _debts = ObservedObject(wrappedValue: loop.debts)
        self.seed = seed
        let seeded: (CanvasPlan, ConnectedPlanDetails) = switch seed {
        case .create(let kind): (CanvasPlan(name: "", kind: kind ?? .goal, currency: loop.plan.projection?.accounts.first?.currency ?? "DOP"), .init())
        case .goal(let draft): ConnectedPlanMapping.seed(draft, locale: .current)
        case .budget(let draft): ConnectedPlanMapping.seed(draft, locale: .current)
        case .debt(let draft): ConnectedPlanMapping.seed(draft, locale: .current)
        }
        initial = seeded.0
        _kind = State(initialValue: seeded.0.kind)
        _details = State(initialValue: seeded.1)
    }

    var body: some View {
        CuadraoPlanEditor(host: host, initial: initial, spanish: spanish, details: { plan in detailsView(plan) }, footer: { footerView })
    }

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    private var accounts: [FinancialAccount] { loop.plan.projection?.accounts ?? [] }
    private var editing: Bool {
        switch seed {
        case .create: false
        case .goal(let draft): draft.existing != nil
        case .budget(let draft): draft.existing != nil
        case .debt(let draft): draft.existing != nil
        }
    }
    private var kindLocked: Bool {
        if case .create(let kind) = seed { return kind != nil }
        return true
    }
    private var saving: Bool {
        switch kind { case .goal: goals.saving; case .budget: budgets.saving; case .debt: debts.saving }
    }
    private var errorKey: String? {
        switch kind { case .goal: goals.errorKey; case .budget: budgets.errorKey; case .debt: debts.errorKey }
    }
    private var monthlyTitle: String? {
        switch seed {
        case .goal(let draft): draft.hasPlan ? ConnectedPlanMapping.cadenceTitle(draft.cadence) : nil
        case .debt(let draft): ConnectedPlanMapping.cadenceTitle(draft.cadence)
        default: nil
        }
    }
    private var identifiers: CuadraoPlanEditorIdentifiers {
        var ids = CuadraoPlanEditorIdentifiers()
        switch kind {
        case .goal: ids.name = "goal.name"; ids.target = "goal.target"; ids.monthly = "goal.contributionAmount"; ids.currency = "goal.currency"; ids.save = "goal.save"
        case .budget: ids.name = "budget.name"; ids.target = "budget.limit"; ids.monthly = "budget.monthly"; ids.currency = "budget.currency"; ids.save = "budget.save"
        case .debt: ids.name = "debt.name"; ids.target = "debt.target"; ids.monthly = "debt.amount"; ids.rate = "debt.rate"; ids.currency = "debt.currency"; ids.save = "debt.save"
        }
        return ids
    }
    private var host: CuadraoPlanEditorHost {
        var host = CuadraoPlanEditorHost(spaces: [.init(id: "personal", title: NSLocalizedString("context.personal", comment: ""))],
                                         editing: editing, save: { plan in Task { await save(plan) } })
        host.kindLocked = kindLocked
        host.currencyLocked = kind == .debt
        host.showsTarget = kind != .debt
        host.showsRecorded = false
        host.showsRate = kind == .debt
        host.showsLook = false
        host.monthlyRequired = kind == .debt
        host.monthlyTitle = monthlyTitle
        host.identifiers = identifiers
        host.canSave = { plan in loop.pendingConfirmation == nil && ready(plan) }
        host.missing = { plan in
            ConnectedPlanReadiness.missing(plan, details, creatingDebt: { if case .create = seed { return true }; return false }(),
                                           optionsLoaded: budgets.options != nil)?.hint(spanish: spanish)
        }
        host.saving = saving
        host.dismissesOnSave = false
        return host
    }

    private func digits(_ currency: String) -> Int {
        switch seed {
        case .goal(let draft): if let existing = draft.existing { return existing.currencyFractionDigits }
        case .budget(let draft): if let existing = draft.existing { return existing.currencyFractionDigits }
        case .debt(let draft): if let existing = draft.existing { return existing.currencyFractionDigits }
        case .create: break
        }
        return accounts.first { $0.currency == currency }?.currencyFractionDigits ?? 2
    }
    private func goalDraft(_ plan: CanvasPlan, seeded: Bool) -> FinancialGoalDraft? {
        let draft: FinancialGoalDraft
        if case .goal(let current) = seed, seeded { draft = current }
        else if case .goal(let current) = seed, let existing = current.existing { draft = FinancialGoalDraft(goal: existing) }
        else if let projection = loop.plan.projection { draft = FinancialGoalDraft(start: projection.startDate, currency: plan.currency) }
        else { return nil }
        ConnectedPlanMapping.apply(plan, details, to: draft, digits: digits(plan.currency), locale: locale)
        return draft
    }
    private func budgetDraft(_ plan: CanvasPlan, seeded: Bool) -> FinancialBudgetDraft? {
        let draft: FinancialBudgetDraft
        if case .budget(let current) = seed, seeded { draft = current }
        else if case .budget(let current) = seed, let existing = current.existing { draft = FinancialBudgetDraft(budget: existing) }
        else if let projection = loop.plan.projection {
            draft = FinancialBudgetDraft(month: projection.home.period?.month ?? String(projection.startDate.prefix(7)), currency: plan.currency)
        } else { return nil }
        ConnectedPlanMapping.apply(plan, details, to: draft, digits: digits(plan.currency), locale: locale)
        return draft
    }
    private func debtDraft(_ plan: CanvasPlan, seeded: Bool) -> FinancialDebtDraft? {
        let draft: FinancialDebtDraft
        if case .debt(let current) = seed, seeded { draft = current }
        else if case .debt(let current) = seed, let existing = current.existing { draft = FinancialDebtDraft(debt: existing) }
        else if let projection = loop.plan.projection, let account = accounts.first(where: { $0.id == details.debtAccountID }) {
            draft = FinancialDebtDraft(account: account, start: projection.startDate)
        } else { return nil }
        ConnectedPlanMapping.apply(plan, details, to: draft, digits: digits(plan.currency), locale: locale)
        return draft
    }
    private func ready(_ plan: CanvasPlan) -> Bool {
        switch plan.kind {
        case .goal: goalDraft(plan, seeded: false)?.ready ?? false
        case .budget: budgets.options != nil && (budgetDraft(plan, seeded: false)?.ready ?? false)
        case .debt: debtDraft(plan, seeded: false)?.ready ?? false
        }
    }
    private func save(_ plan: CanvasPlan) async {
        switch plan.kind {
        case .goal:
            guard let draft = goalDraft(plan, seeded: true) else { return }
            await goals.save(draft, locale: locale); finish(goals.errorKey)
        case .budget:
            guard let draft = budgetDraft(plan, seeded: true) else { return }
            await budgets.save(draft, locale: locale); finish(budgets.errorKey)
        case .debt:
            guard let draft = debtDraft(plan, seeded: true) else { return }
            await debts.save(draft, locale: locale); finish(debts.errorKey)
        }
    }
    private func finish(_ error: String?) {
        if case .create = seed, error == nil, loop.pendingConfirmation == nil { dismiss() }
    }

    private func detailsView(_ plan: Binding<CanvasPlan>) -> some View {
        let current = plan.wrappedValue
        return VStack(alignment: .leading, spacing: 0) {
            switch current.kind {
            case .goal: goalDetails(current)
            case .budget: budgetDetails(current)
            case .debt: debtDetails(plan)
            }
        }
        .onChange(of: current.kind) { _, next in kind = next }
        .onChange(of: current.currency) { _, _ in details.destinationID = nil; details.sourceID = nil; details.accountIDs = [] }
        .task(id: current.kind) { if current.kind == .budget, budgets.options == nil { await budgets.loadOptions() } }
    }
    private func goalDetails(_ plan: CanvasPlan) -> some View {
        ConnectedPlanDetailsCard {
            choice("goal.destination", id: "goal.destination", selection: $details.destinationID,
                   accounts: funding(plan.currency, includeArchived: true), empty: plan.monthly > 0 ? "plan.account.required" : "plan.account.unassigned")
            if plan.monthly > 0 {
                Divider()
                choice("goal.source", id: "goal.source", selection: $details.sourceID, accounts: funding(plan.currency), empty: "plan.account.required")
            }
            Text("goal.plan.disclosure").font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }
    }
    private func budgetDetails(_ plan: CanvasPlan) -> some View {
        ConnectedPlanDetailsCard {
            Text("plan.includedAccounts").font(CuadraoTypography.section)
            if budgets.options == nil {
                ProgressView("accounts.loading")
                Button("accounts.retry") { Task { await budgets.loadOptions() } }.frame(minHeight: 44)
            }
            ForEach(budgetAccounts(plan.currency)) { account in
                Toggle(isOn: member($details.accountIDs, account.id)) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(loop.accountName(account.id)).font(CuadraoTypography.body)
                        if account.archived { Text("accounts.archived").font(CuadraoTypography.caption).foregroundStyle(.secondary) }
                    }
                }.accessibilityIdentifier("budget.account." + account.id.uuidString)
            }
            Text("budget.categories").font(CuadraoTypography.section)
            ForEach(budgets.options?.categories ?? [], id: \.self) { category in
                Toggle(isOn: member($details.categoryIDs, category)) { Text(LocalizedStringKey("loop.category." + category)).font(CuadraoTypography.body) }
                    .accessibilityIdentifier("budget.category." + category)
            }
            Toggle(isOn: $details.includeUncategorized) { Text("budget.uncategorized").font(CuadraoTypography.body) }
                .accessibilityIdentifier("budget.uncategorized")
            Text("budget.disclosure").font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }.tint(WelcomePalette.pine)
    }
    private func debtDetails(_ plan: Binding<CanvasPlan>) -> some View {
        let current = plan.wrappedValue
        return ConnectedPlanDetailsCard {
            if case .create = seed {
                choice("debt.chooseAccount", id: "debt.account", selection: Binding(get: { details.debtAccountID }, set: { id in
                    details.debtAccountID = id
                    guard let account = accounts.first(where: { $0.id == id }) else { return }
                    plan.wrappedValue.currency = account.currency
                    if current.name.isEmpty { plan.wrappedValue.name = loop.accountName(account.id) }
                }), accounts: debtCandidates, empty: "debt.chooseAccount")
                Divider()
            }
            choice("debt.source", id: "debt.source", selection: $details.sourceID, accounts: funding(current.currency), empty: "plan.account.required")
            Text("debt.plan.disclosure").font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }
    }
    private func choice(_ title: String, id: String, selection: Binding<UUID?>, accounts: [FinancialAccount], empty: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(LocalizedStringKey(title)).font(.caption).foregroundStyle(.secondary)
            CuadraoChoiceMenu(title: NSLocalizedString(title, comment: ""), selection: selection, values: [nil] + accounts.map(\.id),
                              valueTitle: { $0.map(loop.accountName) ?? NSLocalizedString(empty, comment: "") })
                .accessibilityIdentifier(id)
        }
    }
    private func member<Element: Hashable>(_ set: Binding<Set<Element>>, _ element: Element) -> Binding<Bool> {
        Binding(get: { set.wrappedValue.contains(element) },
                set: { if $0 { set.wrappedValue.insert(element) } else { set.wrappedValue.remove(element) } })
    }
    private func funding(_ currency: String, includeArchived: Bool = false) -> [FinancialAccount] {
        accounts.filter { (includeArchived || !$0.archived) && $0.currency == currency && ["cash", "checking", "savings"].contains($0.type) }
    }
    private func budgetAccounts(_ currency: String) -> [FinancialAccount] {
        (budgets.options?.accounts ?? []).filter { $0.currency == currency && (budgets.options?.eligibility["expense"] ?? []).contains($0.type) }
    }
    private var debtCandidates: [FinancialAccount] {
        let planned = loop.plan.projection?.debts ?? []
        return accounts.filter { account in
            !account.archived && ["credit_card", "other_debt"].contains(account.type)
                && !planned.contains { !$0.debt.archived && $0.debt.debtAccountId == account.id }
        }
    }
    private var footerView: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let errorKey { Text(LocalizedStringKey(errorKey)).accessibilityIdentifier(kind.rawValue + ".error") }
            if loop.pendingConfirmation != nil { PlanPendingView(loop: loop) }
        }
    }
}

private struct ConnectedPlanDetailsCard<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 14) { content }
            .padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 20))
    }
}
