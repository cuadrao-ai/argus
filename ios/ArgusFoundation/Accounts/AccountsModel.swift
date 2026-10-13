import SwiftUI
import ArgusSession

/// Memory-only presentation state. The session owns identity; the API owns records.
@MainActor
final class AccountsModel: ObservableObject {
    @Published private(set) var accounts: [FinancialAccount] = []
    @Published private(set) var selectedID: UUID?
    var selected: FinancialAccount? { accounts.first { $0.id == selectedID } }
    @Published var draft: AccountDraft?
    @Published private(set) var hasLoaded = false
    @Published private(set) var busy = false
    @Published private(set) var errorKey: String?
    @Published private(set) var latest: FinancialAccount?
    @Published private(set) var needsReview = false
    @Published private(set) var identity: SessionSnapshot?
    /// When each account's detail last loaded successfully, on the device clock.
    @Published private(set) var refreshedAt: [UUID: Date] = [:]
    var confirmCreate: ((CreateFinancialAccountRequest) async throws -> FinancialAccount)?
    var financialChanged: (() -> Void)?
    var sessionChanged: ((SessionSnapshot) -> Void)?
    private let controller: SessionController
    private var generation = UUID()
    @Published private(set) var openingPreview: OpeningPreview?
    @Published private(set) var openingUncertain = false
    private var pendingOpening: WriteOpeningRequest?
    private var openingCoverage: [OpeningCoverage] = []
    private var openingKey = UUID()
    private var pendingCreate: CreateFinancialAccountRequest?

    init(controller: SessionController) { self.controller = controller }

    func bind(_ snapshot: SessionSnapshot?) {
        guard snapshot?.revision != identity?.revision || snapshot?.profile?.id != identity?.profile?.id || snapshot?.phase != identity?.phase else { return }
        generation = UUID()
        identity = snapshot?.phase == .authenticated ? snapshot : nil
        accounts = []; refreshedAt = [:]; hasLoaded = false; selectedID = nil; draft = nil; latest = nil
        clearOpening(); pendingCreate = nil; busy = false; errorKey = nil; needsReview = false
    }

    func load() async {
        await run { identity in let values = try await self.controller.financialAccounts(expectedIdentity: identity)
            if self.current(identity) {
                self.accounts = values
                self.hasLoaded = true
                let now = Date()
                for value in values { self.refreshedAt[value.id] = now }
                if !values.contains(where: { $0.id == self.selectedID }) { self.selectedID = nil }
            } }
    }

    func open(_ account: FinancialAccount) async {
        guard !busy else { return }
        select(account)
        await refresh(account.id)
    }

    func refresh(_ accountID: UUID) async {
        await run(targetAccountID: accountID) { identity in let value = try await self.controller.financialAccount(id: accountID, expectedIdentity: identity)
            if self.current(identity) { self.upsert(value); self.refreshedAt[accountID] = Date() } }
    }

    func back() { guard !busy else { return }; selectedID = nil; errorKey = nil }
    func create() { begin(AccountDraft()) }
    func edit(_ account: FinancialAccount) { begin(AccountDraft(account: account, mode: .metadata)) }
    func rename(_ account: FinancialAccount) { begin(AccountDraft(account: account, mode: .rename)) }
    func opening(_ account: FinancialAccount) { begin(AccountDraft(account: account, mode: .opening)) }
    func discard() { clearOpening(); draft = nil; pendingCreate = nil; latest = nil; needsReview = false; errorKey = nil }
    func editLatest() {
        guard let latest, let mode = draft?.mode else { return }
        begin(AccountDraft(account: latest, mode: mode))
    }

    private func begin(_ draft: AccountDraft) {
        clearOpening(); self.draft = draft; pendingCreate = nil; errorKey = nil; latest = nil; needsReview = false
    }

    func save(locale: Locale = .current) async {
        guard let draft, !needsReview else { return }
        await run { identity in
            let amount = try AccountEntry.amount(draft.amount, locale: locale)
            let share = try AccountEntry.share(draft.share)
            let saved: FinancialAccount
            switch draft.mode {
            case .create:
                if self.pendingCreate == nil {
                    let opening = try AccountEntry.amount(draft.createOpening, locale: locale)
                    self.pendingCreate = CreateFinancialAccountRequest(type: draft.type, currency: draft.currency,
                        nickname: draft.nickname, amount: opening,
                        asOf: opening == nil ? nil : draft.asOf, timeZone: draft.timeZone, ownershipShareBps: share)
                }
                guard let confirm = self.confirmCreate else { throw FinancialWriteJournalError.storageUnavailable }
                saved = try await confirm(self.pendingCreate!)
            case .metadata, .rename:
                guard let base = draft.base else { return }
                saved = try await self.controller.updateFinancialAccount(id: base.id,
                    request: EditFinancialAccountRequest(expectedVersion: base.version, nickname: draft.nickname,
                        type: draft.type == base.type ? nil : draft.type,
                        currency: draft.currency == base.currency ? nil : draft.currency, ownershipShareBps: base.isOptionalAsset || share == base.ownershipShareBps ? nil : share), expectedIdentity: identity)
            case .opening:
                guard let base = draft.base else { return }
                guard let request = self.pendingOpening else {
                    var request = WriteOpeningRequest(expectedVersion: base.version, expectedRevision: base.opening?.revision,
                        amount: amount, asOf: draft.asOf == base.opening?.asOf ? nil : draft.asOf,
                        timeZone: draft.timeZone == base.opening?.timeZone ? nil : draft.timeZone, reason: draft.reason)
                    request.coverage = self.openingCoverage
                    let preview = try await self.controller.openingPreview(accountId: base.id, request: request, expectedIdentity: identity)
                    guard self.current(identity) else { return }
                    self.openingPreview = preview
                    if preview.ready { request.previewToken = preview.previewToken; self.pendingOpening = request }
                    return
                }
                self.openingUncertain = true
                saved = try await self.controller.writeOpening(id: base.id, request: request, key: self.openingKey, expectedIdentity: identity)
            }
            guard self.current(identity) else { return }
            self.accept(saved)
            if draft.mode == .create { self.select(saved) }
            self.discard()
        }
    }

    var openingIsReviewed: Bool { pendingOpening != nil }
    func changedOpeningInput() { if draft?.mode == .opening && !openingUncertain { clearOpening() } }
    func editOpening() { guard !openingUncertain else { return }; clearOpening() }
    func answerOpening(_ id: UUID, included: Bool, locale: Locale) async {
        guard !busy, !openingUncertain else { return }
        openingCoverage.removeAll { $0.activityId == id }
        openingCoverage.append(.init(activityId: id, included: included))
        pendingOpening = nil
        await save(locale: locale)
    }
    private func clearOpening() {
        openingPreview = nil; pendingOpening = nil; openingCoverage = []; openingKey = UUID(); openingUncertain = false
    }

    var createIsFrozen: Bool { pendingCreate != nil }

    func archive(_ account: FinancialAccount) async {
        await run(targetAccountID: account.id) { identity in
            let saved = try await self.controller.updateFinancialAccount(id: account.id,
                request: EditFinancialAccountRequest(expectedVersion: account.version, archived: !account.archived), expectedIdentity: identity)
            if self.current(identity) { self.accept(saved) }
        }
    }

    private func current(_ captured: SessionSnapshot) -> Bool {
        identity?.revision == captured.revision && identity?.profile?.id == captured.profile?.id
    }

    func select(_ account: FinancialAccount) { upsert(account); selectedID = account.id }

    func upsert(_ account: FinancialAccount) {
        if let index = accounts.firstIndex(where: { $0.id == account.id }) { accounts[index] = account }
        else { accounts.append(account) }
    }

    func accept(_ account: FinancialAccount) {
        upsert(account)
        financialChanged?()
    }

    func accept(_ updated: [FinancialAccount]) {
        for account in updated { upsert(account) }
        financialChanged?()
    }

    private func run(targetAccountID: UUID? = nil, _ operation: (SessionSnapshot) async throws -> Void) async {
        guard let identity, !busy else { return }
        let ticket = generation
        busy = true; errorKey = nil
        defer { if generation == ticket { busy = false } }
        do { try await operation(identity) }
        catch {
            guard generation == ticket else { return }
            let snapshot = await controller.snapshot()
            guard generation == ticket else { return }
            if snapshot.revision != identity.revision || snapshot.phase != .authenticated {
                bind(snapshot); sessionChanged?(snapshot); return
            }
            errorKey = Self.message(error)
            if case SessionFailure.rejected(_, let code) = error, code == "coverage_invalid" || code == "coverage_conflict" { clearOpening() }
            if pendingOpening != nil {
                if case SessionFailure.rejected(let status, _) = error, (400..<500).contains(status), status != 408 {
                    clearOpening()
                } else { return }
            }
            if case SessionFailure.rejected(let status, _) = error, status == 422 || status == 400 { pendingCreate = nil }
            if draft?.base != nil && Self.requiresReview(error) {
                needsReview = true
                if let id = draft?.base?.id {
                    let value = try? await controller.financialAccount(id: id, expectedIdentity: identity)
                    guard generation == ticket else { return }
                    guard await synchronize(identity, ticket: ticket) else { return }
                    latest = value
                }
            } else if draft == nil, let targetAccountID, Self.requiresReview(error) {
                let value = try? await controller.financialAccount(id: targetAccountID, expectedIdentity: identity)
                if await synchronize(identity, ticket: ticket), let value { self.upsert(value) }
            }
        }
    }

    private func synchronize(_ identity: SessionSnapshot, ticket: UUID) async -> Bool {
        let snapshot = await controller.snapshot()
        guard generation == ticket else { return false }
        if snapshot.revision != identity.revision || snapshot.phase != .authenticated {
            bind(snapshot); sessionChanged?(snapshot); return false
        }
        return true
    }

    private static func requiresReview(_ error: Error) -> Bool {
        if case SessionFailure.rejected(let status, _) = error { return status == 409 || status >= 500 }
        return true
    }

    private static func message(_ error: Error) -> String {
        if let entry = error as? AccountEntry.Failure { return entry == .share ? "accounts.error.share" : "accounts.error.amount_invalid" }
        guard case SessionFailure.rejected(let status, let code) = error else { return "accounts.error.connection" }
        let supported = ["amount_precision", "amount_invalid", "amount_out_of_range", "currency_unsupported", "currency_locked",
                         "date_in_future", "date_invalid", "time_zone_invalid", "nickname_invalid", "reason_required", "reason_invalid",
                         "field_missing", "type_locked", "nature_change_requires_empty_account", "stale_version", "idempotency_conflict",
                         "financial_accounts_unavailable", "financial_account_not_found", "account_conversion_required", "validation_error"]
        if let code, supported.contains(code) { return "accounts.error." + code }
        return status == 401 ? "auth.error.unauthorized" : "accounts.error.connection"
    }
}

struct AccountDraft: Identifiable {
    /// Rename edits only the nickname; metadata also edits type, currency and ownership.
    enum Mode { case create, metadata, rename, opening }
    let id = UUID()
    var mode: Mode = .create
    var base: FinancialAccount?
    var nickname = ""
    var type = "checking"
    var currency = "DOP"
    var amount = ""
    var asOf = ISO8601DateFormatter().string(from: Date())
    var timeZone = "America/Santo_Domingo"
    var reason = ""
    var share = "100"
    /// Cash starts tracking what is in hand, so a blank wallet is a recorded zero.
    /// Every other type keeps a blank balance unknown.
    var createOpening: String { amount.isEmpty && type == "cash" ? "0" : amount }

    init() {}
    init(account: FinancialAccount, mode: Mode) {
        self.mode = mode; base = account; nickname = account.nickname ?? ""
        type = account.type; currency = account.currency
        share = String(account.ownershipShareBps / 100) + "." + String(format: "%02d", account.ownershipShareBps % 100)
        // Empty correction amount means carry forward. Never submit signed read money as user input.
        asOf = account.opening?.asOf ?? ISO8601DateFormatter().string(from: Date())
        timeZone = account.opening?.timeZone ?? "America/Santo_Domingo"
    }
}
