import SwiftUI
import ArgusSession

struct FinancialPlanCards: View {
    @ObservedObject var model: FinancialPlanModel
    @ObservedObject var loop: FinancialLoopModel
    let projection: FinancialPlanProjection
    let create: () -> Void
    var bottomSpace: CGFloat = 90
    @State private var archiving: FinancialPlanCardItem?
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    private var items: [FinancialPlanCardItem] { FinancialPlanCardItem.items(in: projection).filter { !$0.archived } }

    var body: some View {
        CuadraoPlanCollection(spanish: spanish, isEmpty: items.isEmpty,
            canCreate: loop.pendingConfirmation == nil && !model.saving, create: create) {
            VStack(spacing: 18) {
                ForEach(items) { item in
                    ConnectedSwipeRow(leading: actions(item, edge: .leading), trailing: actions(item, edge: .trailing)) {
                        Button { Task { await item.open(in: loop) } } label: {
                            CuadraoPlanCard(display: item.display(locale: locale))
                        }.buttonStyle(.plain).accessibilityIdentifier("plan.card." + item.id)
                    }
                }
            }.connectedSwipeContainer()
        } archives: {
            CuadraoPlanArchiveLink(spanish: spanish) {
                FinancialArchivedPlans(model: model, loop: loop, bottomSpace: bottomSpace)
            }
        }
        .confirmationDialog(archiving?.archiveCopy.title ?? "", isPresented: Binding(get: { archiving != nil }, set: { if !$0 { archiving = nil } }),
            titleVisibility: .visible, presenting: archiving) { item in
            Button(item.archiveCopy.confirm, role: item.archiveCopy.role) { Task { await item.archive(in: loop) } }
            Button("accounts.cancel", role: .cancel) {}
        } message: { item in Text(item.archiveCopy.message) }
    }

    private func actions(_ item: FinancialPlanCardItem, edge: HorizontalEdge) -> [ConnectedSwipeAction] {
        guard loop.pendingConfirmation == nil, !model.saving else { return [] }
        switch edge {
        case .leading:
            return [.init(id: "plan.swipe.edit", title: CuadraoCopy.text("copy.connectedCuadraoHome.2ddd4a589f", spanish: spanish), symbol: "pencil", tint: .blue) { Task { await item.edit(in: loop) } }]
        case .trailing:
            return [.init(id: "plan.swipe.archive", title: CuadraoCopy.text("copy.connectedCuadraoHome.0960027352", spanish: spanish), symbol: "archivebox", tint: .orange) { archiving = item }]
        }
    }
}

private struct FinancialArchivedPlans: View {
    @ObservedObject var model: FinancialPlanModel
    @ObservedObject var loop: FinancialLoopModel
    let bottomSpace: CGFloat
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    private var items: [FinancialPlanCardItem] {
        model.projection.map(FinancialPlanCardItem.items)?.filter(\.archived) ?? []
    }

    var body: some View {
        List {
            if items.isEmpty {
                ContentUnavailableView(CuadraoCopy.text("copy.cuadraoGroupCollection.e07523e83a", spanish: spanish), systemImage: "archivebox",
                    description: Text(CuadraoCopy.text("copy.cuadraoPlanCanvas.ebcdf81c28", spanish: spanish)))
                    .listRowSeparator(.hidden)
            }
            ForEach(items) { item in
                Button { Task { await item.open(in: loop) } } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.name)
                            Text("context.personal").font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").font(.caption2).accessibilityHidden(true)
                    }.frame(minHeight: 48).contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityIdentifier("plan.archived." + item.id)
            }
        }.navigationTitle(CuadraoCopy.text("copy.cuadraoSpacesSheet.e95aacbabf", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar).safeAreaPadding(.bottom, bottomSpace)
    }
}

private enum FinancialPlanCardItem: Identifiable {
    case goal(FinancialGoalProgress)
    case budget(FinancialBudgetProgress)
    case debt(FinancialDebtProgress)

    static func items(in projection: FinancialPlanProjection) -> [Self] {
        (projection.goals ?? []).map(Self.goal) + projection.budgets.map(Self.budget) + (projection.debts ?? []).map(Self.debt)
    }
    var id: String {
        switch self {
        case .goal(let item): "goal." + item.id.uuidString
        case .budget(let item): "budget." + item.id.uuidString
        case .debt(let item): "debt." + item.id.uuidString
        }
    }
    var name: String {
        switch self {
        case .goal(let item): item.goal.name
        case .budget(let item): item.budget.name
        case .debt(let item): item.debt.name
        }
    }
    var archived: Bool {
        switch self {
        case .goal(let item): item.goal.archived
        case .budget(let item): item.budget.archived
        case .debt(let item): item.debt.archived
        }
    }
    @MainActor func open(in loop: FinancialLoopModel) async {
        switch self {
        case .goal(let item): await loop.goals.open(item.id, origin: .planOverview)
        case .budget(let item): await loop.budgets.open(item.id, origin: .planOverview)
        case .debt(let item): await loop.debts.open(item.id, origin: .planOverview)
        }
    }
    @MainActor func edit(in loop: FinancialLoopModel) async {
        switch self {
        case .goal(let item): loop.goals.edit(item.goal)
        case .budget(let item): await loop.budgets.edit(item.budget)
        case .debt(let item): loop.debts.edit(item.debt)
        }
    }
    @MainActor func archive(in loop: FinancialLoopModel) async {
        switch self {
        case .goal(let item): await loop.goals.archive(item.goal, archived: true)
        case .budget(let item): await loop.budgets.archive(item.budget, archived: true)
        case .debt(let item): await loop.debts.archive(item.debt, archived: true)
        }
    }
    var archiveCopy: (title: LocalizedStringKey, confirm: LocalizedStringKey, message: LocalizedStringKey, role: ButtonRole?) {
        switch self {
        case .goal: ("goal.archive", "goal.archive", "goal.archive.disclosure", nil)
        case .budget: ("budget.remove.confirm", "budget.remove", "budget.remove.body", .destructive)
        case .debt: ("debt.archive", "debt.archive", "debt.archive.disclosure", nil)
        }
    }
    func display(locale: Locale) -> CuadraoPlanCardDisplay {
        let personal = NSLocalizedString("context.personal", comment: "")
        func money(_ minor: String?, _ currency: String, _ digits: Int) -> String {
            minor.map { PlanPresentation.money($0, currency: currency, digits: digits, locale: locale) }
                ?? currency + " · " + NSLocalizedString("accounts.unknown", comment: "")
        }
        switch self {
        case .goal(let progress):
            let currency = progress.goal.currency, digits = progress.goal.currencyFractionDigits
            return .init(name: name, space: personal, look: .coast,
                amount: money(progress.supportedMinor, currency, digits), annotation: NSLocalizedString("goal.supported", comment: ""),
                progress: progress.meterFraction,
                detail: NSLocalizedString("goal.target", comment: "") + ": " + money(String(progress.goal.targetMinor), currency, digits),
                notice: NSLocalizedString("goal.state." + progress.state, comment: ""))
        case .budget(let progress):
            let currency = progress.budget.currency, digits = progress.budget.currencyFractionDigits
            return .init(name: name, space: personal, look: .sunshine,
                amount: money(progress.spentMinor, currency, digits),
                annotation: NSLocalizedString(progress.isOverBudget ? "budget.over" : "budget.remaining", comment: "") + " " +
                    money(progress.isOverBudget ? progress.overBudgetMinor : progress.remainingMinor, currency, digits),
                progress: progress.meterFraction,
                detail: NSLocalizedString("budget.of", comment: "") + " " + money(String(progress.budget.limitMinor), currency, digits) + " · " + progress.budget.month)
        case .debt(let progress):
            let credit = progress.balance.creditMinor != nil && progress.balance.creditMinor != 0
            return .init(name: name, space: personal, look: .bloom,
                amount: money((credit ? progress.balance.creditMinor : progress.balance.amountMinor).map(String.init), progress.debt.currency, progress.debt.currencyFractionDigits),
                annotation: NSLocalizedString(credit ? "debt.credit" : "debt.recorded", comment: ""),
                detail: NSLocalizedString("debt.state." + progress.state, comment: ""))
        }
    }
}
