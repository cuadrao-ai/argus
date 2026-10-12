import SwiftUI
import ArgusSession

@MainActor
final class FinancialLoopModel: ObservableObject {
    @Published private(set) var home: FinancialHome?
    struct AccountReadState {
        var activity: [FinancialActivity] = []
        var checks: [FinancialCheck] = []
        var activityCursor: String?
        var checksCursor: String?
        var loading = false
        var loadingMore = false
        var errorKey: String?
        var request = UUID()
    }
    @Published private(set) var accountReads: [UUID: AccountReadState] = [:]
    func read(_ accountID: UUID) -> AccountReadState { accountReads[accountID] ?? AccountReadState() }
    @Published var assetEditor: FinancialAssetEditor?
    @Published var editor: FinancialEditor?
    @Published var activityEditor: FinancialActivityEditor?
    /// The newest save the server accepted, for the Home notice. A new value is a new save.
    struct SaveNotice: Equatable { let token = UUID(); let activityID: UUID?; let corrected: Bool }
    @Published private(set) var saveNotice: SaveNotice?
    @Published private(set) var pendingConfirmation: PendingFinancialConfirmation?
    @Published private(set) var recovering = false
    @Published private(set) var recoveryErrorKey: String?
    private let controller: SessionController
    let accounts: AccountsModel
    private let journal: FinancialWriteJournal
    private var identity: SessionSnapshot?
    private var generation = UUID()
    var financialChanged: (() -> Void)?
    var sessionChanged: ((SessionSnapshot) -> Void)?
    lazy var debts = FinancialDebtModel(controller: controller, loop: self)
    lazy var goals = FinancialGoalModel(controller: controller, loop: self)
    lazy var budgets = FinancialBudgetModel(controller: controller, loop: self)
    lazy var plan = FinancialPlanModel(controller: controller, accounts: accounts, loop: self)

    init(controller: SessionController, accounts: AccountsModel, journal: FinancialWriteJournal) {
        self.controller = controller; self.accounts = accounts; self.journal = journal
        accounts.confirmCreate = { [weak self] command in
            guard let self else { throw SessionFailure.staleOperation }
            return try await self.confirmAccount(command, accountID: nil, suffix: "", method: "POST", key: command.idempotencyKey)
        }
    }

    func bind(_ snapshot: SessionSnapshot?) {
        guard identity?.revision != snapshot?.revision || identity?.profile?.id != snapshot?.profile?.id || identity?.phase != snapshot?.phase else { return }
        generation = UUID(); identity = snapshot?.phase == .authenticated ? snapshot : nil
        home = nil; accountReads = [:]
        assetEditor = nil; editor = nil; activityEditor = nil; recovering = false; recoveryErrorKey = nil
        if let identity {
            do { pendingConfirmation = try journal.pending(for: identity) }
            catch { pendingConfirmation = nil; recoveryErrorKey = "auth.error.storage" }
        } else { pendingConfirmation = nil }
        plan.bind(snapshot)
        budgets.bind(snapshot)
        goals.bind(snapshot)
        debts.bind(snapshot)
    }

    func refresh() async {
        guard identity != nil else { return }
        await plan.refresh()
        financialChanged?()
    }

    func acceptPlanHome(_ home: FinancialHome) { self.home = home }

    /// Use a task keyed by identity, account and period. Check cancellation before assigning its result.
    func observations(accountID: UUID, period: FinancialHomePeriod) async -> PersonalObservationRead {
        guard !Task.isCancelled else { return .cancelled }
        guard let identity else { return .unavailable }
        let ticket = generation
        let pageLimit = 64
        var readAccount = false; var verifying = false
        func checkCurrent() throws {
            try Task.checkCancellation()
            guard generation == ticket, self.identity == identity else { throw SessionFailure.staleOperation }
        }
        do {
            try checkCurrent()
            let before = try await controller.financialAccount(id: accountID, expectedIdentity: identity)
            try checkCurrent()
            guard before.id == accountID else { return .stale }
            readAccount = true
            var checks: [FinancialCheck] = []; var cursor: String?
            var seen = Set<String>()
            for index in 0..<pageLimit {
                try checkCurrent()
                let page = try await controller.financialChecks(accountId: accountID, cursor: cursor, expectedIdentity: identity)
                try checkCurrent()
                checks += page.items
                guard let next = page.nextCursor else { break }
                guard seen.insert(next).inserted else { return .incomplete(.repeatedCursor) }
                guard index + 1 < pageLimit else { return .incomplete(.pageLimit) }
                cursor = next
            }
            verifying = true
            try checkCurrent()
            let after = try await controller.financialAccount(id: accountID, expectedIdentity: identity)
            try checkCurrent()
            let current = await controller.snapshot()
            try checkCurrent()
            guard current == identity else { throw SessionFailure.staleOperation }
            return PersonalAccountObservations.accepted(requestedID: accountID, before: before,
                checksInServerOrder: checks, after: after, period: period)
        } catch {
            await handle(error, ticket: ticket)
            if Task.isCancelled || error is CancellationError { return .cancelled }
            guard generation == ticket, self.identity == identity else { return .stale }
            if case SessionFailure.staleOperation = error { return .stale }
            if case SessionFailure.rejected(status: 409, code: _) = error { return .stale }
            return readAccount ? .incomplete(verifying ? .verificationFailure : .pageFailure) : .unavailable
        }
    }

    func open(_ account: FinancialAccount) async {
        guard let identity else { return }
        let ticket = generation
        let request = UUID()
        // Keep prior activity/checks visible while refreshing. Clearing them made
        // post-confirm UITests lose "DOP 7,000.00" from check history for the
        // whole reload window (AccountSummary balance is a11y-combined).
        var loading = accountReads[account.id] ?? AccountReadState()
        loading.loading = true
        loading.errorKey = nil
        loading.request = request
        accountReads[account.id] = loading
        defer {
            if generation == ticket, accountReads[account.id]?.request == request { accountReads[account.id]?.loading = false }
        }
        do {
            let entries = try await controller.financialActivity(accountId: account.id, expectedIdentity: identity)
            let observations = try await controller.financialChecks(accountId: account.id, expectedIdentity: identity)
            guard generation == ticket, accountReads[account.id]?.request == request else { return }
            accountReads[account.id] = AccountReadState(activity: entries.items, checks: observations.items,
                activityCursor: entries.nextCursor, checksCursor: observations.nextCursor, request: request)
        } catch { await handle(error, ticket: ticket, accountID: account.id, request: request) }
    }

    func more(_ account: FinancialAccount, checks: Bool) async {
        guard let identity, let state = accountReads[account.id], !state.loading, !state.loadingMore,
              let cursor = checks ? state.checksCursor : state.activityCursor else { return }
        let ticket = generation; let request = state.request
        accountReads[account.id]?.loadingMore = true
        defer {
            if generation == ticket, accountReads[account.id]?.request == request { accountReads[account.id]?.loadingMore = false }
        }
        do {
            if checks {
                let page = try await controller.financialChecks(accountId: account.id, cursor: cursor, expectedIdentity: identity)
                guard generation == ticket, accountReads[account.id]?.request == request else { return }
                accountReads[account.id]?.checks += page.items
                accountReads[account.id]?.checksCursor = page.nextCursor
            } else {
                let page = try await controller.financialActivity(accountId: account.id, cursor: cursor, expectedIdentity: identity)
                guard generation == ticket, accountReads[account.id]?.request == request else { return }
                accountReads[account.id]?.activity += page.items
                accountReads[account.id]?.activityCursor = page.nextCursor
            }
        } catch { await handle(error, ticket: ticket, accountID: account.id, request: request) }
    }

    func history(_ account: FinancialAccount, activity: FinancialActivity) async throws -> [FinancialActivity] {
        guard let identity else { throw SessionFailure.unauthorized }
        let ticket = generation
        var entries: [FinancialActivity] = []; var cursor: String?
        repeat {
            let page = try await controller.financialActivityHistory(accountId: account.id, recordId: activity.recordId, cursor: cursor, expectedIdentity: identity)
            guard generation == ticket else { throw SessionFailure.staleOperation }
            entries += page.items; cursor = page.nextCursor
        } while cursor != nil
        return entries
    }

    func detail(_ activity: FinancialActivity) async throws -> FinancialActivityDetail {
        try await detail(id: activity.activityId ?? activity.recordId)
    }

    func detail(id: UUID) async throws -> FinancialActivityDetail {
        guard let identity else { throw SessionFailure.unauthorized }
        let ticket = generation
        do {
            let value = try await controller.financialActivityDetail(id, expectedIdentity: identity)
            guard generation == ticket else { throw SessionFailure.staleOperation }
            return value
        } catch {
            await handle(error, ticket: ticket)
            throw error
        }
    }

    func detailHistory(_ activity: FinancialActivityDetail) async throws -> [FinancialActivityDetail] {
        guard let identity else { throw SessionFailure.unauthorized }
        let ticket = generation
        do {
            let page = try await controller.financialActivityDetailHistory(activity.activityId, expectedIdentity: identity)
            guard generation == ticket else { throw SessionFailure.staleOperation }
            return page.items
        } catch {
            await handle(error, ticket: ticket)
            throw error
        }
    }

    func accountName(_ id: UUID) -> String {
        guard let account = accounts.accounts.first(where: { $0.id == id }) else { return id.uuidString }
        return account.nickname ?? NSLocalizedString("accounts.type." + account.type, comment: "")
    }

    func canCorrect(_ activity: FinancialActivityDetail) -> Bool { correctionAccount(activity) != nil }

    func correct(_ activity: FinancialActivityDetail, focusCategory: Bool = false) {
        guard let account = correctionAccount(activity) else { return }
        record(account, correcting: activity, focusCategory: focusCategory)
    }

    private func correctionAccount(_ activity: FinancialActivityDetail) -> FinancialAccount? {
        guard activity.originalAmountAvailable, let id = activity.legs.first?.accountId else { return nil }
        return accounts.accounts.first { $0.id == id }
    }

    func record(_ account: FinancialAccount, correcting activity: FinancialActivityDetail? = nil, occurrence: FinancialPlanOccurrence? = nil, goal: FinancialGoal? = nil, goalOccurrenceId: String? = nil, debt: FinancialDebt? = nil, debtOccurrenceId: String? = nil, returning: FinancialActivityDetail? = nil, focusCategory: Bool = false) {
        guard let identity, pendingConfirmation == nil, correctingAmountAvailable(activity), correctingAmountAvailable(returning) else { return }
        let ticket = generation
        activityEditor = FinancialActivityEditor(origin: account, correcting: activity, planOccurrence: occurrence, goal: goal, goalOccurrenceId: goalOccurrenceId, debt: debt, debtOccurrenceId: debtOccurrenceId, returning: returning, focusCategory: focusCategory, controller: controller,
            journal: journal, identity: identity, started: { [weak self] write in
                guard let self, self.generation == ticket else { return }
                self.pendingConfirmation = write
            }, resolved: { [weak self] in
                guard let self, self.generation == ticket else { return }
                self.pendingConfirmation = nil
            }, retired: { [weak self] snapshot in
                guard let self, self.generation == ticket else { return }
                self.bind(snapshot); self.sessionChanged?(snapshot)
            }) { [weak self] receipt in
                await self?.accepted(receipt, ticket: ticket)
            }
    }

    func returnPayment(_ activity: FinancialActivityDetail) {
        guard activity.originalAmountAvailable, let source = activity.legs.first(where: { $0.role == "source" })?.accountId, let account = accounts.accounts.first(where: { $0.id == source }) else { return }
        record(account, returning: activity)
    }
    private func correctingAmountAvailable(_ activity: FinancialActivityDetail?) -> Bool { activity?.originalAmountAvailable ?? true }

    func retryPending() async {
        guard let identity, let write = pendingConfirmation, !recovering else { return }
        let ticket = generation
        recovering = true; recoveryErrorKey = nil
        defer { if generation == ticket { recovering = false } }
        do {
            let current = await controller.snapshot()
            guard generation == ticket, current == identity else { throw SessionFailure.staleOperation }
            if let operation = write.planOperation {
                if operation.recordsActivity {
                    let receipt = try await controller.sendPlanFulfillment(write, expectedIdentity: identity)
                    guard generation == ticket else { return }
                    try journal.clear(write, for: identity); pendingConfirmation = nil
                    await accepted(receipt, ticket: ticket)
                } else {
                    try await controller.sendPlanConfirmation(write, expectedIdentity: identity)
                    guard generation == ticket else { return }
                    try journal.clear(write, for: identity); pendingConfirmation = nil
                    await accounts.load(); await refresh()
                    guard generation == ticket else { return }
                    plan.confirmed(operation)
                    budgets.confirmed(operation)
                    goals.confirmed(operation)
                    debts.confirmed(operation)
                }
            } else if write.route == "financial-accounts" {
                let account = try await controller.sendAccountConfirmation(write, expectedIdentity: identity)
                guard generation == ticket else { return }
                try journal.clear(write, for: identity); pendingConfirmation = nil
                assetEditor = nil; accounts.discard(); accounts.accept(account)
                if write.path.isEmpty { accounts.select(account) }
                await refresh()
            } else {
                let receipt = try await controller.sendFinancialConfirmation(write, expectedIdentity: identity)
                guard generation == ticket else { return }
                try journal.clear(write, for: identity); pendingConfirmation = nil
                await accepted(receipt, ticket: ticket)
            }
        } catch {
            guard generation == ticket else { return }
            let current = await controller.snapshot()
            guard generation == ticket else { return }
            if current != identity { bind(current); sessionChanged?(current); return }
            if case SessionFailure.rejected(let status, _) = error, (400..<500).contains(status), status != 408 {
                do { try journal.clear(write, for: identity); pendingConfirmation = nil }
                catch { recoveryErrorKey = "auth.error.storage"; return }
                await accounts.load(); await refresh()
            }
            recoveryErrorKey = FinancialActivityEditor.message(error)
        }
    }

    func confirmPlan<Command: Encodable>(_ operation: FinancialPlanOperation, command: Command, originAccountId: UUID?) async throws {
        guard let identity, let owner = identity.profile.flatMap({ UUID(uuidString: $0.id) }), pendingConfirmation == nil else {
            throw FinancialWriteJournalError.pendingConfirmation
        }
        let ticket = generation
        let encoder = JSONEncoder(); encoder.outputFormatting = .sortedKeys
        let write = PendingFinancialConfirmation(ownerId: owner, originAccountId: originAccountId,
            route: "financial-plan", path: operation.path, method: operation.method,
            body: try encoder.encode(command), key: UUID(), planOperation: operation)
        try journal.begin(write, for: identity)
        pendingConfirmation = write
        do {
            try await controller.sendPlanConfirmation(write, expectedIdentity: identity)
            guard generation == ticket else { throw SessionFailure.staleOperation }
            try journal.clear(write, for: identity); pendingConfirmation = nil
            await accounts.load(); await refresh()
        } catch {
            guard generation == ticket else { throw SessionFailure.staleOperation }
            let current = await controller.snapshot()
            guard generation == ticket else { throw SessionFailure.staleOperation }
            if current != identity { bind(current); sessionChanged?(current); throw error }
            if case SessionFailure.rejected(let status, _) = error, (400..<500).contains(status), status != 408 {
                try journal.clear(write, for: identity); pendingConfirmation = nil
                await refresh()
            }
            throw error
        }
    }

    func asset(_ account: FinancialAccount, correcting: FinancialAssetEstimate? = nil, details: Bool = false) {
        guard identity != nil, pendingConfirmation == nil else { return }
        assetEditor = FinancialAssetEditor(account: account, correcting: correcting, details: details, loop: self)
    }

    func previewAsset(_ accountID: UUID, command: FinancialAssetEstimateCommand) async throws -> FinancialAssetPreview {
        guard let identity else { throw SessionFailure.unauthorized }
        return try await controller.assetEstimatePreview(accountId: accountID, command: command, expectedIdentity: identity)
    }

    func confirmAccount<Command: Encodable>(_ command: Command, accountID: UUID?, suffix: String, method: String, key: UUID) async throws -> FinancialAccount {
        guard let identity, let owner = identity.profile.flatMap({ UUID(uuidString: $0.id) }) else { throw SessionFailure.unauthorized }
        let ticket = generation
        let encoder = JSONEncoder(); encoder.outputFormatting = .sortedKeys
        let write = PendingFinancialConfirmation(ownerId: owner, originAccountId: accountID, route: "financial-accounts",
            path: accountID.map { "/" + $0.uuidString + suffix } ?? "", method: method, body: try encoder.encode(command), key: key)
        try journal.begin(write, for: identity)
        pendingConfirmation = write
        do {
            let account = try await controller.sendAccountConfirmation(write, expectedIdentity: identity)
            guard generation == ticket else { throw SessionFailure.staleOperation }
            try journal.clear(write, for: identity); pendingConfirmation = nil
            accounts.accept(account); await refresh()
            return account
        } catch {
            guard generation == ticket else { throw SessionFailure.staleOperation }
            let current = await controller.snapshot()
            guard generation == ticket else { throw SessionFailure.staleOperation }
            if current != identity { bind(current); sessionChanged?(current); throw error }
            if case SessionFailure.rejected(let status, _) = error, (400..<500).contains(status), status != 408 {
                try journal.clear(write, for: identity); pendingConfirmation = nil
                if let accountID { await accounts.refresh(accountID) }
            }
            throw error
        }
    }

    var pendingTitle: String {
        if pendingConfirmation?.route == "financial-accounts" { return "assets.pending" }
        guard let operation = pendingConfirmation?.planOperation else { return "loop.pending.title" }
        switch operation {
        case .createGoal, .editGoal, .allocateGoals, .linkGoal, .recordGoal, .releaseGoal: return "goal.pending"
        case .createDebt, .editDebt, .linkDebt, .recordDebt: return "debt.pending"
        case .createBudget, .editBudget: return "budget.pending"
        case .createExpectation, .editExpectation: return "plan.pending.expectation"
        case .selection: return "plan.pending.selection"
        case .link: return "plan.pending.link"
        case .fulfill: return "plan.pending.fulfillment"
        }
    }

    private func accepted(_ receipt: FinancialActivityReceipt, ticket: UUID) async {
        guard generation == ticket, identity != nil else { return }
        pendingConfirmation = nil
        accounts.accept(receipt.accounts)
        let corrected = activityEditor?.correcting != nil
        activityEditor = nil
        saveNotice = SaveNotice(activityID: receipt.activity.activityId, corrected: corrected)
        await refresh()
        for account in receipt.accounts where accountReads[account.id] != nil { await open(account) }
    }

    func expense(_ account: FinancialAccount, correcting activity: FinancialActivity? = nil) {
        guard let identity else { return }
        let ticket = generation
        editor = FinancialEditor(account: account, kind: .expense(activity), controller: controller, identity: identity, retired: { [weak self] snapshot in
            guard let self, self.generation == ticket else { return }
            self.bind(snapshot); self.sessionChanged?(snapshot)
        }) { [weak self] account in
            await self?.accepted(account, ticket: ticket)
        }
    }

    func check(_ account: FinancialAccount) {
        guard let identity else { return }
        let ticket = generation
        editor = FinancialEditor(account: account, kind: .check, controller: controller, identity: identity, retired: { [weak self] snapshot in
            guard let self, self.generation == ticket else { return }
            self.bind(snapshot); self.sessionChanged?(snapshot)
        }) { [weak self] account in
            await self?.accepted(account, ticket: ticket)
        }
    }

    private func accepted(_ account: FinancialAccount, ticket: UUID) async {
        guard generation == ticket, identity != nil else { return }
        accounts.accept(account)
        editor = nil
        saveNotice = SaveNotice(activityID: nil, corrected: false)
        await refresh()
        await open(account)
    }

    private func handle(_ error: Error, ticket: UUID, accountID: UUID? = nil, request: UUID? = nil) async {
        guard generation == ticket else { return }
        let snapshot = await controller.snapshot()
        guard generation == ticket else { return }
        if snapshot.revision != identity?.revision || snapshot.phase != .authenticated {
            bind(snapshot); sessionChanged?(snapshot)
        } else if let accountID, accountReads[accountID]?.request == request {
            accountReads[accountID]?.errorKey = FinancialEditor.message(error)
            CuadraoHaptics.warning()
        }
    }
}

@MainActor
final class FinancialEditor: ObservableObject, Identifiable {
    enum Kind { case expense(FinancialActivity?), check }
    enum Phase { case editing, loading, review, saving, uncertain, conflict, retired, saved }
    let id = UUID()
    let account: FinancialAccount
    let kind: Kind
    @Published var amount = "" { didSet { if amount != oldValue { invalidatePlacement() } } }
    @Published var note = ""
    @Published var reason = ""
    @Published var date = Date() { didSet { if date != oldValue { invalidatePlacement() } } }
    @Published private(set) var categories: [FinancialCategory] = []
    @Published var categoryId: String?
    @Published private(set) var phase = Phase.editing
    @Published private(set) var expensePreview: ExpensePreview?
    @Published private(set) var checkPreview: BalanceCheckPreview?
    @Published private(set) var errorKey: String?
    private var coverage: [FinancialCoverage] = []
    private var expenseRequest: ExpenseRequest?
    private var checkRequest: BalanceCheckRequest?
    private var key = UUID()
    private let controller: SessionController
    private let identity: SessionSnapshot
    private let retired: (SessionSnapshot) -> Void
    private let completed: (FinancialAccount) async -> Void
    private let timeZone: String

    init(account: FinancialAccount, kind: Kind, controller: SessionController, identity: SessionSnapshot, retired: @escaping (SessionSnapshot) -> Void = { _ in },
         completed: @escaping (FinancialAccount) async -> Void) {
        self.account = account; self.kind = kind; self.controller = controller
        self.identity = identity; self.retired = retired; self.completed = completed
        if case .expense(let activity) = kind, let activity {
            amount = AccountPresentation.amount(activity.amount, locale: .current)
            note = activity.note ?? ""; categoryId = activity.categoryId; coverage = activity.coverage
            date = AccountPresentation.parseDate(activity.occurredAt) ?? Date()
            timeZone = activity.timeZone
        } else { timeZone = TimeZone.current.identifier }
    }

    var isCorrection: Bool { if case .expense(let value) = kind { return value != nil }; return false }
    var isCheck: Bool { if case .check = kind { return true }; return false }
    var busy: Bool { phase == .loading || phase == .saving }
    /// Entry fields only while editing. Coverage review must not remount amount/date
    /// controls — field didSet invalidate wiped coverage answers before confirm.
    var canEdit: Bool { phase == .editing }
    var canConfirm: Bool { phase == .uncertain || (phase == .review && (checkPreview != nil || expensePreview?.ready == true)) }
    var readyToReview: Bool { !amount.isEmpty && (!isCorrection || !reason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }

    func loadCategories() async {
        guard !isCheck else { return }
        do { categories = try await controller.financialCategories(expectedIdentity: identity).categories }
        catch { /* Optional categorization must not block recording. */ }
    }

    private func invalidatePlacement() {
        guard canEdit, !busy else { return }
        coverage = []; expensePreview = nil; expenseRequest = nil
    }

    func edit() {
        guard phase == .review else { return }
        phase = .editing; expensePreview = nil; checkPreview = nil; expenseRequest = nil; checkRequest = nil
    }

    func answer(_ observation: UUID, included: Bool) {
        guard !busy, phase != .uncertain else { return }
        coverage.removeAll { $0.observationId == observation }
        coverage.append(.init(observationId: observation, included: included))
        // Stay in review while coverage is answered so entry remount + didSet
        // invalidate does not wipe the coverage answers just recorded.
        expensePreview = nil
    }

    func review(locale: Locale) async {
        guard !busy, phase != .uncertain else { return }
        phase = .loading; errorKey = nil
        do {
            guard let exact = try AccountEntry.amount(amount, locale: locale) else { throw AccountEntry.Failure.amount }
            let formatter = ISO8601DateFormatter()
            formatter.timeZone = TimeZone(identifier: timeZone)
            switch kind {
            case .expense(let activity):
                var request = ExpenseRequest(expectedVersion: account.version, amount: exact, occurredAt: formatter.string(from: date),
                                             timeZone: timeZone, note: note, categoryId: categoryId, coverage: coverage,
                                             expectedRevision: activity?.revision, reason: isCorrection ? reason : nil)
                let preview = try await controller.expensePreview(accountId: account.id, recordId: activity?.recordId,
                                                                  request: request, expectedIdentity: identity)
                request.previewToken = preview.previewToken
                expenseRequest = request; expensePreview = preview
            case .check:
                var request = BalanceCheckRequest(expectedVersion: account.version, amount: exact, asOf: formatter.string(from: date),
                                                  timeZone: timeZone, note: note)
                let preview = try await controller.balanceCheckPreview(accountId: account.id, request: request, expectedIdentity: identity)
                request.previewToken = preview.previewToken
                checkRequest = request; checkPreview = preview
            }
            phase = .review
        } catch {
            if await retireIfNeeded() { return }
            resetRejectedPlacement(error)
            errorKey = Self.message(error)
            phase = Self.isConflict(error) ? .conflict : .editing
        }
    }

    func confirm() async {
        guard canConfirm else { return }
        phase = .saving; errorKey = nil
        do {
            let account: FinancialAccount
            switch kind {
            case .expense(let activity):
                guard let request = expenseRequest else { phase = .editing; return }
                account = try await controller.saveExpense(accountId: self.account.id, recordId: activity?.recordId,
                                                            request: request, key: key, expectedIdentity: identity).account
            case .check:
                guard let request = checkRequest else { phase = .editing; return }
                account = try await controller.saveBalanceCheck(accountId: self.account.id, request: request,
                                                                 key: key, expectedIdentity: identity).account
            }
            phase = .saved
            await completed(account)
        } catch {
            if await retireIfNeeded() { return }
            resetRejectedPlacement(error)
            errorKey = Self.message(error)
            if Self.isConflict(error) { phase = .conflict }
            else if case SessionFailure.rejected(let status, _) = error, (400..<500).contains(status), status != 408 { phase = .editing }
            else { phase = .uncertain }
        }
    }

    private func resetRejectedPlacement(_ error: Error) {
        guard case SessionFailure.rejected(_, let code) = error,
              code == "coverage_invalid" || code == "coverage_conflict" else { return }
        coverage = []; expensePreview = nil; expenseRequest = nil
    }

    private func retireIfNeeded() async -> Bool {
        let current = await controller.snapshot()
        guard current.phase != .authenticated || current.revision != identity.revision || current.profile?.id != identity.profile?.id else { return false }
        phase = .retired
        retired(current)
        return true
    }

    private static func isConflict(_ error: Error) -> Bool {
        if case SessionFailure.rejected(let status, _) = error { return status == 409 }
        return false
    }
    static func message(_ error: Error) -> String {
        if error is AccountEntry.Failure { return "accounts.error.amount_invalid" }
        guard case SessionFailure.rejected(let status, let code) = error, status < 500 else { return "loop.error.connection" }
        let supported = ["stale_version", "amount_precision", "amount_invalid", "amount_out_of_range", "date_in_future", "reason_required", "reason_invalid"]
        if let code, supported.contains(code) { return "accounts.error." + code }
        if code == "check_before_latest_observation" { return "loop.error.checkDate" }
        if code == "coverage_conflict" { return "loop.error.coverage" }
        return "loop.error.validation"
    }
}
