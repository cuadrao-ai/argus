import Foundation
import SwiftUI
import ArgusSession

/// The server calls the receipt journey needs. The real one talks to the API; tests stub it.
protocol ReceiptJourneyTransport: Sendable {
    func upload(_ bytes: Data, mediaType: String, filename: String, consent: Bool, identity: SessionSnapshot) async throws -> SavedDocumentCapture
    func document(_ connectionID: String, identity: SessionSnapshot) async throws -> FinancialDocumentDetail
    func prepare(_ connectionID: String, identity: SessionSnapshot) async throws -> SavedDocumentCapture
    func openImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent]
    func acceptedImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent]
    func resolve(_ event: FinancialImportEvent, changes: FinancialImportChanges, identity: SessionSnapshot) async throws -> FinancialImportEvent
    func preview(_ eventID: String, identity: SessionSnapshot) async throws -> FinancialImportPreview
    func accept(_ event: FinancialImportEvent, request: FinancialActivityCommand, key: UUID, identity: SessionSnapshot) async throws -> FinancialImportAcceptance
    func link(_ event: FinancialImportEvent, activityID: UUID, identity: SessionSnapshot) async throws -> FinancialImportEvent
    func options(identity: SessionSnapshot) async throws -> FinancialActivityOptions
    func source(_ connectionID: String, identity: SessionSnapshot) async throws -> Data
}

struct SessionReceiptJourneyTransport: ReceiptJourneyTransport {
    let controller: SessionController
    func upload(_ bytes: Data, mediaType: String, filename: String, consent: Bool, identity: SessionSnapshot) async throws -> SavedDocumentCapture {
        try await controller.saveDocument(bytes, mediaType: mediaType, filename: filename, consent: consent, expectedIdentity: identity)
    }
    func document(_ connectionID: String, identity: SessionSnapshot) async throws -> FinancialDocumentDetail {
        try await controller.financialDocument(connectionID, expectedIdentity: identity)
    }
    func prepare(_ connectionID: String, identity: SessionSnapshot) async throws -> SavedDocumentCapture {
        try await controller.prepareDocument(connectionID, expectedIdentity: identity)
    }
    func openImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent] {
        try await controller.financialImports(state: "open", expectedIdentity: identity)
    }
    func acceptedImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent] {
        try await controller.financialImports(state: "accepted", expectedIdentity: identity)
    }
    func resolve(_ event: FinancialImportEvent, changes: FinancialImportChanges, identity: SessionSnapshot) async throws -> FinancialImportEvent {
        try await controller.resolveFinancialImport(event, changes: changes, expectedIdentity: identity)
    }
    func preview(_ eventID: String, identity: SessionSnapshot) async throws -> FinancialImportPreview {
        try await controller.previewFinancialImport(eventID, expectedIdentity: identity)
    }
    func accept(_ event: FinancialImportEvent, request: FinancialActivityCommand, key: UUID, identity: SessionSnapshot) async throws -> FinancialImportAcceptance {
        try await controller.acceptFinancialImport(event, request: request, key: key, expectedIdentity: identity)
    }
    func link(_ event: FinancialImportEvent, activityID: UUID, identity: SessionSnapshot) async throws -> FinancialImportEvent {
        try await controller.linkFinancialImport(event, activityID: activityID, expectedIdentity: identity)
    }
    func options(identity: SessionSnapshot) async throws -> FinancialActivityOptions {
        try await controller.financialActivityOptions(expectedIdentity: identity)
    }
    func source(_ connectionID: String, identity: SessionSnapshot) async throws -> Data {
        try await controller.savedDocumentSource(connectionID, expectedIdentity: identity)
    }
}

/// What the person reviews before a receipt becomes an expense. The server's reading fills it; every field stays editable.
struct ReceiptReviewDraft: Equatable {
    let connectionID: String
    var event: FinancialImportEvent
    let receipt: DocumentReceipt?
    var merchant: String
    var amount: String
    var currency: String
    var occurredOn: Date?
    var categoryID: String?
    var accountID: UUID?

    init(connectionID: String, event: FinancialImportEvent, receipt: DocumentReceipt?) {
        self.connectionID = connectionID; self.event = event; self.receipt = receipt
        let observation = event.observations.first { $0.connectionID == connectionID }
        merchant = receipt?.merchant ?? observation?.merchant ?? observation?.description ?? ""
        amount = event.facts.amount ?? receipt?.total ?? ""
        currency = event.facts.currency ?? receipt?.currency ?? ""
        occurredOn = (event.facts.occurredOn ?? receipt?.occurredOn).flatMap(Self.day)
        categoryID = receipt?.suggestedCategory
        accountID = event.facts.accountID.flatMap(UUID.init(uuidString:))
    }

    /// An already recorded movement this receipt may belong to.
    var existingMatch: UUID? { event.existingActivityMatches.first.flatMap(UUID.init(uuidString:)) }

    var isComplete: Bool {
        accountID != nil && occurredOn != nil && !currency.isEmpty
            && (Decimal(string: amount).map { $0 > 0 } ?? false)
    }

    /// Only what differs from the server's facts, plus the person's answers the server still needs.
    func changes(timeZone: TimeZone) -> FinancialImportChanges {
        var changes = FinancialImportChanges()
        let facts = event.facts
        if facts.kind != FinancialActivityKind.expense.rawValue { changes.kind = .expense }
        if let accountID, facts.accountID.flatMap(UUID.init(uuidString:)) != accountID { changes.accountID = accountID }
        if amount != facts.amount { changes.amount = amount }
        if currency != facts.currency { changes.currency = currency }
        if let occurredOn {
            let text = Self.dayText(occurredOn)
            if text != facts.occurredOn { changes.occurredOn = text; changes.timeZone = timeZone.identifier }
        }
        if let categoryID { changes.categoryID = categoryID }
        let note = merchant.trimmingCharacters(in: .whitespacesAndNewlines)
        if !note.isEmpty { changes.note = String(note.prefix(200)) }
        return changes
    }

    static func day(_ text: String) -> Date? { dayFormatter.date(from: text) }
    static func dayText(_ date: Date) -> String { dayFormatter.string(from: date) }
    private static let dayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}

enum ReceiptJourneyFailure: Equatable {
    /// The file did not reach the server; the held file can be sent again.
    case couldNotSend(SavedReceiptFailure)
    /// The server could not read the file. A new reading needs the person to ask for it.
    case couldNotRead
    /// The reading found no movement to record. The file stays saved.
    case nothingToRecord
    /// The server refused to record; the code says why.
    case couldNotRecord(String?)
}

enum ReceiptJourneyPhase: Equatable {
    case idle
    /// Files are held while the person chooses to read them or only save them. The first time, and whenever
    /// reading is off, the choice carries the AI disclosure.
    case consent
    case sending
    /// The server is reading the file. The person may close this; the receipt stays in Files.
    case preparing(String)
    /// Reading takes longer than this screen waits. It continues on the server.
    case stillPreparing(String)
    case review(ReceiptReviewDraft)
    case recording(ReceiptReviewDraft)
    case recorded(FinancialActivityDetail)
    /// The receipt joined a movement that was already recorded.
    case linked(String)
    /// Saved without reading, as the person chose. The same file may already have been saved.
    case savedOnly(alreadySaved: Bool)
    case failed(ReceiptJourneyFailure)
}

/// One receipt from capture to a saved expense: consent, send, the server's reading, review and correction,
/// then one explicit confirmation through the existing money service. Nothing is recorded without that confirmation.
@MainActor
final class ReceiptJourneyModel: ObservableObject {
    @Published private(set) var phase = ReceiptJourneyPhase.idle
    /// The same accounts and categories the movement editor offers.
    @Published private(set) var options: FinancialActivityOptions?
    /// Receipts from the same capture still to review, in order.
    @Published private(set) var waiting: [String] = []
    /// The person's one answer about AI reading, kept per account on this iPhone and changed in Settings.
    @Published private(set) var readingAllowed = false
    /// The first captured file, shown while the person chooses and while it is read.
    @Published private(set) var preview: ReceiptPreview?
    var sessionChanged: ((SessionSnapshot) -> Void)?

    private let transport: any ReceiptJourneyTransport
    private let currentSession: @Sendable () async -> SessionSnapshot
    private let pause: @Sendable (Duration) async -> Void
    private let pollLimit: Int
    private let timeZone: TimeZone
    private let defaults: UserDefaults
    private var identity: SessionSnapshot?
    private var ticket = UUID()
    private var held: [(data: Data, name: String, pdf: Bool)] = []
    private var sent: [String] = []
    private var consented = false
    private var connectionID: String?
    private var acceptKey: (eventID: String, key: UUID)?

    init(transport: any ReceiptJourneyTransport, currentSession: @escaping @Sendable () async -> SessionSnapshot,
         pause: @escaping @Sendable (Duration) async -> Void = { try? await Task.sleep(for: $0) },
         pollLimit: Int = 40, timeZone: TimeZone = .current, defaults: UserDefaults = .standard) {
        self.transport = transport; self.currentSession = currentSession
        self.pause = pause; self.pollLimit = pollLimit; self.timeZone = timeZone; self.defaults = defaults
    }

    convenience init(controller: SessionController) {
        self.init(transport: SessionReceiptJourneyTransport(controller: controller), currentSession: { await controller.snapshot() })
    }

    func bind(_ snapshot: SessionSnapshot?) {
        let next = snapshot?.phase == .authenticated ? snapshot : nil
        guard identity != next else { return }
        identity = next
        readingAllowed = permissionKey.map { defaults.bool(forKey: $0) } ?? false
        reset()
    }

    private var permissionKey: String? { identity?.profile.map { "cuadrao.receiptReading." + $0.id } }

    /// Settings turns AI reading on or off. Off brings the disclosure back before the next reading.
    func setReadingAllowed(_ allowed: Bool) {
        guard let key = permissionKey else { return }
        readingAllowed = allowed
        defaults.set(allowed, forKey: key)
    }

    func reset() {
        ticket = UUID(); phase = .idle; held = []; sent = []; waiting = []; connectionID = nil; acceptKey = nil; options = nil; preview = nil
    }

    /// Captured files wait for the person's answer about reading. One answer covers every file of the capture.
    func begin(_ files: [(data: Data, name: String, pdf: Bool)]) {
        reset()
        guard !files.isEmpty else { return }
        held = files
        preview = ReceiptPreview(files)
        phase = .consent
        ScanTrace.mark("consent asked")
    }

    /// Yes sends every file with consent and follows the first reading; the rest wait their turn. No saves them
    /// privately and stops there. After a failure, only the files not yet sent are sent again.
    func answerConsent(_ allowed: Bool) async {
        guard phase == .consent || isSendFailure, let identity, !held.isEmpty else { return }
        let mine = ticket
        if phase == .consent {
            consented = allowed
            if allowed, !readingAllowed { setReadingAllowed(true) }
        }
        let allowed = consented
        phase = .sending
        do {
            var replayed = true
            while let file = held.first {
                let capture = try await transport.upload(file.data, mediaType: SavedReceiptsModel.mediaType(file), filename: file.name,
                                                         consent: allowed, identity: identity)
                guard mine == ticket else { return }
                held.removeFirst()
                sent.append(capture.connectionID)
                replayed = replayed && capture.replayed
            }
            guard allowed else { phase = .savedOnly(alreadySaved: replayed); return }
            let first = sent.removeFirst()
            waiting = sent
            sent = []
            connectionID = first
            await follow(first, mine: mine)
        } catch {
            guard mine == ticket, !(await identityChanged(mine)) else { return }
            phase = .failed(.couldNotSend(SavedReceiptFailure(error)))
        }
    }

    /// Reopens a saved receipt where it stands: still reading, ready to review, or already recorded.
    func open(_ connectionID: String) async {
        reset()
        self.connectionID = connectionID
        await follow(connectionID, mine: ticket)
    }

    /// Moves to the next receipt of the same capture.
    func next() async {
        guard !waiting.isEmpty else { return }
        var rest = waiting
        let id = rest.removeFirst()
        await open(id)
        waiting = rest
    }

    /// A new reading after a failed one. It is a fresh provider attempt, so it happens only when the person asks.
    func readAgain() async {
        guard let identity, let connectionID, phase == .failed(.couldNotRead) else { return }
        let mine = ticket
        phase = .preparing(connectionID)
        do {
            _ = try await transport.prepare(connectionID, identity: identity)
            await follow(connectionID, mine: mine)
        } catch {
            guard mine == ticket, !(await identityChanged(mine)) else { return }
            phase = .failed(.couldNotRead)
        }
    }

    /// The saved receipt behind a recorded movement, found through the import that recorded or took it.
    func receipt(for activityID: UUID) async -> FinancialDocumentDetail? {
        guard let identity else { return nil }
        do {
            let recorded = try await transport.acceptedImports(identity: identity)
            guard let event = recorded.first(where: { $0.activityID.flatMap(UUID.init(uuidString:)) == activityID }),
                  let connectionID = event.observations.first(where: { $0.source == "statement" })?.connectionID else { return nil }
            return try await transport.document(connectionID, identity: identity)
        } catch { return nil }
    }

    /// The receipt file's bytes, or nil when they cannot be read.
    func source(_ document: FinancialDocumentDetail) async -> Data? {
        guard let identity, document.sourceAvailable else { return nil }
        return try? await transport.source(document.connectionID, identity: identity)
    }

    /// Open accounts that can pay this expense, in the receipt's currency.
    func accounts(for draft: ReceiptReviewDraft) -> [FinancialAccount] {
        guard let options else { return [] }
        let types = Set(options.eligibility[FinancialActivityKind.expense.rawValue] ?? [])
        return options.accounts.filter { !$0.archived && $0.currency == draft.currency && types.contains($0.type) }
    }

    func update(_ draft: ReceiptReviewDraft) {
        guard case .review(let current) = phase, current.event.id == draft.event.id else { return }
        phase = .review(draft)
    }

    /// The one explicit confirmation: save the answers, preview through the money service, then record with a key that
    /// survives a retry, so a repeated tap or a lost reply never records the expense twice.
    func confirm() async {
        guard let identity, case .review(var draft) = phase, draft.isComplete else { return }
        let mine = ticket
        phase = .recording(draft)
        do {
            let changes = draft.changes(timeZone: timeZone)
            if changes != FinancialImportChanges() {
                draft.event = try await transport.resolve(draft.event, changes: changes, identity: identity)
            }
            let result = try await transport.preview(draft.event.id, identity: identity)
            guard mine == ticket else { return }
            draft.event = result.event
            guard result.preview.ready, var request = result.preview.reviewedRequest else {
                phase = .failed(.couldNotRecord(result.preview.ready ? nil : "balance_coverage_required"))
                return
            }
            request.previewToken = result.preview.previewToken
            let key = acceptKey?.eventID == draft.event.id ? acceptKey!.key : UUID()
            acceptKey = (draft.event.id, key)
            let accepted = try await transport.accept(draft.event, request: request, key: key, identity: identity)
            guard mine == ticket else { return }
            acceptKey = nil
            phase = .recorded(accepted.activity)
        } catch {
            guard mine == ticket, !(await identityChanged(mine)) else { return }
            phase = .failed(.couldNotRecord(Self.code(error)))
        }
    }

    /// The purchase is already recorded: attach this receipt to it instead of recording it again.
    func linkExisting() async {
        guard let identity, case .review(let draft) = phase, let activityID = draft.existingMatch else { return }
        let mine = ticket
        phase = .recording(draft)
        do {
            _ = try await transport.link(draft.event, activityID: activityID, identity: identity)
            guard mine == ticket else { return }
            phase = .linked(activityID.uuidString)
        } catch {
            guard mine == ticket, !(await identityChanged(mine)) else { return }
            phase = .failed(.couldNotRecord(Self.code(error)))
        }
    }

    /// After a recording failure, return to the same review with the person's answers kept.
    func backToReview() async {
        guard case .failed(.couldNotRecord) = phase, let connectionID else { return }
        await follow(connectionID, mine: ticket)
    }

    private var isSendFailure: Bool { if case .failed(.couldNotSend) = phase { true } else { false } }

    /// Polls the saved document until its reading settles, then finds the movement the reading produced.
    private func follow(_ connectionID: String, mine: UUID) async {
        guard let identity else { return }
        phase = .preparing(connectionID)
        do {
            var document = try await transport.document(connectionID, identity: identity)
            var polls = 0
            while document.isPreparing {
                guard polls < pollLimit else { if mine == ticket { phase = .stillPreparing(connectionID) }; return }
                polls += 1
                await pause(.milliseconds(1500))
                guard mine == ticket else { return }
                document = try await transport.document(connectionID, identity: identity)
            }
            guard mine == ticket else { return }
            switch document.status {
            case "needs_attention": phase = .failed(.couldNotRead); return
            case "saved": phase = .savedOnly(alreadySaved: true); return
            default: break
            }
            let open = try await transport.openImports(identity: identity)
            guard mine == ticket else { return }
            if let event = open.first(where: { $0.connectionIDs.contains(connectionID) }) {
                let options = try await transport.options(identity: identity)
                guard mine == ticket else { return }
                self.options = options
                var draft = ReceiptReviewDraft(connectionID: connectionID, event: event, receipt: document.preparation?.receipt)
                // The reading's category is free text; only a category the server knows is kept.
                if let category = draft.categoryID, !options.categories.contains(category) { draft.categoryID = nil }
                phase = .review(draft)
                return
            }
            let recorded = try await transport.acceptedImports(identity: identity)
            guard mine == ticket else { return }
            if let event = recorded.first(where: { $0.connectionIDs.contains(connectionID) }), let activity = event.activityID {
                phase = .linked(activity)
            } else {
                phase = .failed(.nothingToRecord)
            }
        } catch {
            guard mine == ticket, !(await identityChanged(mine)) else { return }
            phase = .failed(.couldNotRead)
        }
    }

    private static func code(_ error: Error) -> String? {
        if case .rejected(_, let code)? = error as? SessionFailure { return code }
        return nil
    }

    private func identityChanged(_ mine: UUID) async -> Bool {
        guard let identity else { return true }
        let snapshot = await currentSession()
        guard mine == ticket else { return true }
        guard snapshot != identity else { return false }
        bind(snapshot)
        sessionChanged?(snapshot)
        return true
    }
}

private struct ReceiptJourneyKey: EnvironmentKey {
    static let defaultValue: ReceiptJourneyModel? = nil
}

extension EnvironmentValues {
    /// Set by the signed-in shell, so a recorded movement can show the receipt it came from.
    var receiptJourney: ReceiptJourneyModel? {
        get { self[ReceiptJourneyKey.self] }
        set { self[ReceiptJourneyKey.self] = newValue }
    }
}

/// What the sheet shows of a capture: the first image, or a document symbol for a PDF, and how many files came.
struct ReceiptPreview: Equatable {
    let image: Data?
    let count: Int

    init?(_ files: [(data: Data, name: String, pdf: Bool)]) {
        guard let first = files.first else { return nil }
        image = first.pdf ? nil : first.data
        count = files.count
    }
}
