import SwiftUI
import ArgusSession

struct FinancialBudgetNavigation: Codable, Equatable {
    enum Origin: String, Codable { case home, plan, planOverview, search }
    var budgetID: UUID
    var origin: Origin
    var activityID: UUID?
    var anchor: UUID?
    var anchorOffset: Double?
}

@MainActor
final class FinancialBudgetModel: ObservableObject {
    @Published private(set) var navigation: FinancialBudgetNavigation?
    @Published private(set) var detail: FinancialBudgetProgress?
    @Published private(set) var loading = false
    @Published private(set) var saving = false
    @Published private(set) var errorKey: String?
    @Published private(set) var options: FinancialActivityOptions?
    @Published var draft: FinancialBudgetDraft?
    private let controller: SessionController
    private unowned let loop: FinancialLoopModel
    private var identity: SessionSnapshot?
    private var request = UUID()
    private var generation = UUID()
    private let defaults: UserDefaults
    private let prefix = "financial.budget.navigation."

    init(controller: SessionController, loop: FinancialLoopModel, defaults: UserDefaults = .standard) {
        self.controller = controller; self.loop = loop; self.defaults = defaults
    }
    func bind(_ snapshot: SessionSnapshot?) {
        let next = snapshot?.phase == .authenticated ? snapshot : nil
        if let previous = identity?.profile?.id, previous != next?.profile?.id { defaults.removeObject(forKey: prefix + previous) }
        generation = UUID(); request = UUID(); identity = next
        detail = nil; options = nil; draft = nil; errorKey = nil; loading = false; saving = false; navigation = nil
        if let owner = next?.profile?.id, let bytes = defaults.data(forKey: prefix + owner) {
            navigation = try? JSONDecoder().decode(FinancialBudgetNavigation.self, from: bytes)
        }
    }
    func open(_ id: UUID, origin: FinancialBudgetNavigation.Origin) async {
        navigation = .init(budgetID: id, origin: origin); detail = nil; persist()
        await refreshIfOpen()
    }
    func refreshIfOpen() async {
        guard let identity, let navigation else { return }
        let ticket = UUID(); request = ticket; loading = true; errorKey = nil
        defer { if request == ticket { loading = false } }
        do {
            let next = try await controller.financialBudget(navigation.budgetID, expectedIdentity: identity)
            guard request == ticket, self.identity == identity else { return }
            detail = next
        } catch {
            guard request == ticket, self.identity == identity else { return }
            detail = nil; errorKey = FinancialActivityEditor.message(error)
        }
    }
    func close() { request = UUID(); navigation = nil; detail = nil; errorKey = nil; persist() }
    func activity(_ id: UUID?, preservingScrollPosition: Bool = false) {
        navigation?.activityID = id
        if let id, !preservingScrollPosition { navigation?.anchor = id; navigation?.anchorOffset = nil }
        persist()
    }
    var scrollContext: FinancialScrollContext? {
        guard let navigation else { return nil }
        let ticket = generation
        return .init(id: ticket.uuidString + navigation.budgetID.uuidString + navigation.origin.rawValue,
            anchor: navigation.anchor?.uuidString, offset: navigation.anchorOffset,
            availableAnchors: !loading && detail?.budget.id == navigation.budgetID ? detail?.contributors.map { $0.activityId.uuidString } : nil,
            active: navigation.activityID == nil,
            remember: { [weak self] anchor, offset in
                guard let self, self.generation == ticket, !self.loading, let anchor = UUID(uuidString: anchor), offset.isFinite,
                      self.navigation?.budgetID == navigation.budgetID, self.navigation?.origin == navigation.origin,
                      self.navigation?.activityID == nil, self.detail?.contributors.contains(where: { $0.activityId == anchor }) == true,
                      self.navigation?.anchor != anchor || self.navigation?.anchorOffset != offset else { return }
                self.navigation?.anchor = anchor; self.navigation?.anchorOffset = offset; self.persist()
            })
    }
    func create() async {
        guard loop.pendingConfirmation == nil, let projection = loop.plan.projection else { return }
        draft = FinancialBudgetDraft(month: projection.home.period?.month ?? String(projection.startDate.prefix(7)), currency: projection.accounts.first?.currency ?? "DOP")
        await loadOptions()
    }
    func edit() async {
        guard let budget = detail?.budget else { return }
        await edit(budget)
    }
    func edit(_ budget: FinancialBudget) async {
        guard loop.pendingConfirmation == nil else { return }
        draft = FinancialBudgetDraft(budget: budget)
        await loadOptions()
    }
    func loadOptions() async {
        guard let identity else { return }
        let ticket = generation
        do {
            let next = try await controller.financialActivityOptions(expectedIdentity: identity)
            guard generation == ticket else { return }
            options = next
        } catch { if generation == ticket { errorKey = FinancialActivityEditor.message(error) } }
    }
    func save(locale: Locale) async {
        guard let draft else { return }
        await save(draft, locale: locale)
    }
    func save(_ draft: FinancialBudgetDraft, locale: Locale) async {
        guard !saving else { return }
        let ticket = generation; saving = true; errorKey = nil
        defer { if generation == ticket { saving = false } }
        do {
            let operation: FinancialPlanOperation = draft.existing.map { .editBudget(id: $0.id, version: $0.version) } ?? .createBudget
            try await loop.confirmPlan(operation, command: draft.command(locale: locale), originAccountId: nil)
            guard generation == ticket else { return }
            if self.draft === draft { self.draft = nil }
        } catch { if generation == ticket { errorKey = FinancialActivityEditor.message(error) } }
    }
    func archive(_ archived: Bool) async {
        guard let budget = detail?.budget else { return }
        await archive(budget, archived: archived)
    }
    func archive(_ budget: FinancialBudget, archived: Bool) async {
        guard !saving else { return }
        let ticket = generation; saving = true; errorKey = nil
        defer { if generation == ticket { saving = false } }
        do {
            try await loop.confirmPlan(.editBudget(id: budget.id, version: budget.version),
                command: FinancialBudgetLifecycleCommand(expectedVersion: budget.version, archived: archived), originAccountId: nil)
        } catch { if generation == ticket { errorKey = FinancialActivityEditor.message(error) } }
    }
    func confirmed(_ operation: FinancialPlanOperation) {
        switch operation { case .createBudget, .editBudget: draft = nil; default: break }
    }
    private func persist() {
        guard let owner = identity?.profile?.id else { return }
        if let navigation, let bytes = try? JSONEncoder().encode(navigation) { defaults.set(bytes, forKey: prefix + owner) }
        else { defaults.removeObject(forKey: prefix + owner) }
    }
}

@MainActor
final class FinancialBudgetDraft: ObservableObject, Identifiable {
    let id = UUID()
    let existing: FinancialBudget?
    @Published var name = ""
    @Published var limit = ""
    @Published var currency: String
    @Published var date: Date
    @Published var accountIDs: Set<UUID> = []
    @Published var categoryIDs: Set<String> = []
    @Published var includeUncategorized = false
    init(month: String, currency: String) {
        existing = nil; self.currency = currency; date = PlanPresentation.date(month + "-01")
    }
    init(budget: FinancialBudget) {
        existing = budget; name = budget.name; limit = AccountPresentation.amount(budget.limit, locale: .current)
        currency = budget.currency; date = PlanPresentation.date(budget.month + "-01")
        accountIDs = Set(budget.accountIds); categoryIDs = Set(budget.categoryIds); includeUncategorized = budget.includeUncategorized
    }
    var ready: Bool { missing == nil }
    /// The first thing this budget still needs; the save check and the editor's hint both read it.
    var missing: ConnectedPlanMissing? {
        if let problem = ConnectedPlanMissing.name(name) { return problem }
        if limit.isEmpty { return .amount }
        if accountIDs.isEmpty { return .accounts }
        return categoryIDs.isEmpty && !includeUncategorized ? .categories : nil
    }
    func command(locale: Locale) throws -> FinancialBudgetCommand {
        guard ready, let amount = try AccountEntry.amount(limit, locale: locale) else { throw AccountEntry.Failure.amount }
        return .init(name: name, limit: amount, currency: currency, month: String(PlanPresentation.day(date).prefix(7)),
            accountIds: Array(accountIDs), categoryIds: Array(categoryIDs), includeUncategorized: includeUncategorized, expectedVersion: existing?.version)
    }
}
