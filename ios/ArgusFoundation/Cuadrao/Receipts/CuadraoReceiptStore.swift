import Foundation
import Observation

enum ReceiptPostingCapability {
    case preview, draftOnly
    enum Failure: Error { case unavailable }
    var allowsPosting: Bool { self == .preview }
    func requirePosting() throws {
        guard allowsPosting else { throw Failure.unavailable }
    }
}

@Observable final class CuadraoReceiptStore {
    private(set) var receipts: [ReceiptDraft] = []
    private(set) var loadFailed = false
    let directory: URL
    let postingCapability: ReceiptPostingCapability
    private var indexURL: URL { directory.appendingPathComponent("receipts.json") }
    init(directory: URL? = nil, reset: Bool = false, postingCapability: ReceiptPostingCapability = .preview) {
        self.directory = directory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("CuadraoReceipts")
        self.postingCapability = postingCapability
        // Default on-device storage exists only in the design preview; checks inject a directory.
        guard directory != nil || CuadraoDesignPreview.isActive else { loadFailed = true; return }
        do {
            try FileManager.default.createDirectory(at: self.directory, withIntermediateDirectories: true)
            if reset, FileManager.default.fileExists(atPath: indexURL.path) { try Data("[]".utf8).write(to: indexURL, options: .atomic) }
            if FileManager.default.fileExists(atPath: indexURL.path) {
                receipts = try JSONDecoder().decode([ReceiptDraft].self, from: Data(contentsOf: indexURL))
            }
        } catch { loadFailed = true }
    }
    static func connectedDrafts(userID: UUID, applicationSupport: URL? = nil) -> CuadraoReceiptStore {
        CuadraoReceiptStore(directory: connectedDirectory(userID: userID, applicationSupport: applicationSupport), postingCapability: .draftOnly)
    }
    /// Account deletion only (confirmed or accepted): the session owner passes the validated owner after its identity fence.
    /// A missing directory is already clean, so a retried cleanup converges.
    static func removeConnectedDrafts(userID: UUID, applicationSupport: URL? = nil) throws {
        do { try FileManager.default.removeItem(at: connectedDirectory(userID: userID, applicationSupport: applicationSupport)) }
        catch let error as CocoaError where error.code == .fileNoSuchFile { }
    }
    private static func connectedDirectory(userID: UUID, applicationSupport: URL?) -> URL {
        let root = applicationSupport ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return root.appendingPathComponent("CuadraoConnectedReceiptDrafts", isDirectory: true)
            .appendingPathComponent(userID.uuidString, isDirectory: true)
    }
    func receipt(_ id: UUID) -> ReceiptDraft? { receipts.first { $0.id == id } }
    func url(_ source: ReceiptSource) -> URL { directory.appendingPathComponent(source.filename) }
    func capture(files: [(data: Data, name: String, pdf: Bool)], currency: String?, origin: ReceiptOrigin,
                 group: PlanGroup?, example: Bool, spanish: Bool, id: UUID = UUID()) throws -> UUID {
        guard !loadFailed, !files.isEmpty, files.count <= 10,
              files.allSatisfy({ !$0.data.isEmpty }), files.reduce(0, { $0 + $1.data.count }) <= 20_000_000 else { throw ReceiptError.source }
        guard origin.groupID == group?.id else { throw ReceiptError.destination }
        if let currency, !PlanCurrency.supported.contains(currency) { throw ReceiptError.currency }
        if receipt(id) != nil { return id }
        var sources: [ReceiptSource] = []
        var indexed = false
        defer {
            if !indexed { for source in sources { try? FileManager.default.removeItem(at: url(source)) } }
        }
        for (offset, file) in files.enumerated() {
            let source = ReceiptSource(filename: "\(id.uuidString)-\(offset).\(file.pdf ? "pdf" : "jpg")", name: file.name, pdf: file.pdf)
            try file.data.write(to: url(source), options: .atomic)
            sources.append(source)
        }
        var draft = ReceiptDraft(id: id, currency: group?.currency ?? currency, origin: origin, source: sources,
                                 example: example, destination: group.map { .group($0.id) } ?? .personal(accountID: nil))
        if let group { draft.payer = group.me; draft.participants = Set(group.activeMembers.map(\.id)) }
        if example {
            let sample = ReceiptSample(spanish: spanish)
            draft.merchant = sample.merchant; draft.category = sample.category; draft.lines = sample.lines
            draft.taxCents = sample.taxCents; draft.serviceCents = sample.serviceCents
        }
        try persist(receipts + [draft])
        indexed = true
        return id
    }
    func update(_ draft: ReceiptDraft) throws {
        guard let old = receipt(draft.id) else { throw ReceiptError.missing }
        guard old.prepared else { throw ReceiptError.confirmed }
        guard draft.currency == old.currency, draft.source == old.source, draft.origin == old.origin,
              draft.lifecycle == old.lifecycle else { throw ReceiptError.destination }
        if old.currency == nil {
            guard draft.destination == old.destination, draft.lines == old.lines,
                  draft.taxCents == old.taxCents, draft.serviceCents == old.serviceCents,
                  draft.addedTipCents == old.addedTipCents else { throw ReceiptError.currency }
        }
        var revised = draft; revised.updatedAt = .now
        try persist(receipts.map { $0.id == revised.id ? revised : $0 })
    }
    func setCurrency(_ currency: String, for id: UUID) throws {
        guard var draft = receipt(id) else { throw ReceiptError.missing }
        guard draft.prepared, draft.currency == nil, draft.origin.groupID == nil,
              case .personal = draft.destination, PlanCurrency.supported.contains(currency) else { throw ReceiptError.currency }
        draft.currency = currency
        draft.updatedAt = .now
        try persist(receipts.map { $0.id == id ? draft : $0 })
    }
    func discard(_ id: UUID, groups: CuadraoGroupPreview) throws {
        guard let draft = receipt(id) else { return }
        guard draft.prepared, !groups.groups.contains(where: { $0.expenses.contains { $0.receiptID == id } }) else { throw ReceiptError.confirmed }
        try persist(receipts.filter { $0.id != id })
        for source in draft.source { try? FileManager.default.removeItem(at: url(source)) }
    }
    func confirm(_ id: UUID, groups: CuadraoGroupPreview, accounts: CuadraoAccountsPreview) throws {
        try postingCapability.requirePosting()
        guard var draft = receipt(id) else { throw ReceiptError.missing }
        guard draft.prepared else { return }
        try draft.validate()
        if let owner = groups.groups.first(where: { $0.expenses.contains { $0.receiptID == id } }), draft.groupID != owner.id {
            throw ReceiptError.confirmed
        }
        switch draft.destination {
        case .group(let groupID):
            try groups.confirmReceipt(draft, groupID: groupID)
        case .personal(let accountID):
            guard let accountID, let account = accounts.account(accountID), !account.archived,
                  account.spaceID == CanvasSpace.personalID, account.currency == draft.currency,
                  [.cash, .checking, .savings, .card].contains(account.kind) else { throw ReceiptError.destination }
        }
        draft.lifecycle = .confirmed
        draft.updatedAt = .now
        try persist(receipts.map { $0.id == id ? draft : $0 })
        projectPersonal(into: accounts)
    }
    func reconcile(groups: CuadraoGroupPreview, accounts: CuadraoAccountsPreview) throws {
        try postingCapability.requirePosting()
        var repaired = receipts
        for index in repaired.indices where repaired[index].prepared {
            let draft = repaired[index]
            if let groupID = draft.groupID, let expense = groups.group(groupID)?.expenses.first(where: { $0.id == draft.id }),
               expense.receiptID == draft.id, !expense.draft {
                repaired[index].lifecycle = .confirmed
            }
        }
        if repaired != receipts { try persist(repaired) }
        projectPersonal(into: accounts)
    }
    func projectPersonal(into accounts: CuadraoAccountsPreview) {
        guard postingCapability.allowsPosting else { return }
        for draft in receipts where !draft.prepared {
            if case .personal(let accountID) = draft.destination, let accountID {
                accounts.projectReceipt(draft, accountID: accountID)
            }
        }
    }
    private func persist(_ values: [ReceiptDraft]) throws {
        guard !loadFailed else { throw ReceiptError.source }
        try JSONEncoder().encode(values).write(to: indexURL, options: .atomic)
        receipts = values
    }
}

extension CuadraoAccountsPreview {
    func projectReceipt(_ draft: ReceiptDraft, accountID: UUID) {
        guard let account = account(accountID), account.currency == draft.currency,
              !activity.contains(where: { $0.id == draft.id }) else { return }
        let amount = Decimal(draft.total) / 100
        activity.append(CanvasActivity(id: draft.id, accountID: accountID, title: draft.merchant,
                                       amount: amount, date: draft.date, income: false,
                                       category: CanvasExpenseCategory(rawValue: draft.category) ?? .other))
        if let index = accounts.firstIndex(where: { $0.id == accountID }), let balance = accounts[index].balance {
            accounts[index].balance = balance + (account.kind.isDebt ? amount : -amount)
        }
    }
}
