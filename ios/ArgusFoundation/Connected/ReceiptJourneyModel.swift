import Foundation
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
    /// Files are held while the person decides whether the server may read them.
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
    /// Saved without reading, as the person chose.
    case savedOnly
    case failed(ReceiptJourneyFailure)
}

/// One receipt from capture to a saved expense: consent, send, the server's reading, review and correction,
/// then one explicit confirmation through the existing money service. Nothing is recorded without that confirmation.
@MainActor
final class ReceiptJourneyModel: ObservableObject {
    @Published private(set) var phase = ReceiptJourneyPhase.idle
    var sessionChanged: ((SessionSnapshot) -> Void)?

    private let transport: any ReceiptJourneyTransport
    private let currentSession: @Sendable () async -> SessionSnapshot
    private let pause: @Sendable (Duration) async -> Void
    private let pollLimit: Int
    private let timeZone: TimeZone
    private var identity: SessionSnapshot?
    private var ticket = UUID()
    private var held: (data: Data, name: String, pdf: Bool)?
    private var connectionID: String?
    private var acceptKey: (eventID: String, key: UUID)?

    init(transport: any ReceiptJourneyTransport, currentSession: @escaping @Sendable () async -> SessionSnapshot,
         pause: @escaping @Sendable (Duration) async -> Void = { try? await Task.sleep(for: $0) },
         pollLimit: Int = 40, timeZone: TimeZone = .current) {
        self.transport = transport; self.currentSession = currentSession
        self.pause = pause; self.pollLimit = pollLimit; self.timeZone = timeZone
    }

    convenience init(controller: SessionController) {
        self.init(transport: SessionReceiptJourneyTransport(controller: controller), currentSession: { await controller.snapshot() })
    }

    func bind(_ snapshot: SessionSnapshot?) {
        let next = snapshot?.phase == .authenticated ? snapshot : nil
        guard identity != next else { return }
        identity = next
        reset()
    }

    func reset() {
        ticket = UUID(); phase = .idle; held = nil; connectionID = nil; acceptKey = nil
    }

    /// A captured file waits for the person's answer about reading.
    func begin(_ file: (data: Data, name: String, pdf: Bool)) {
        reset()
        held = file
        phase = .consent
    }

    /// Yes sends the file with consent and follows the reading. No saves it privately and stops there.
    func answerConsent(_ allowed: Bool) async {
        guard phase == .consent || isSendFailure, let identity, let file = held else { return }
        let mine = ticket
        phase = .sending
        do {
            let capture = try await transport.upload(file.data, mediaType: SavedReceiptsModel.mediaType(file), filename: file.name,
                                                     consent: allowed, identity: identity)
            guard mine == ticket else { return }
            held = nil
            connectionID = capture.connectionID
            guard allowed else { phase = .savedOnly; return }
            await follow(capture.connectionID, mine: mine)
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
            case "saved": phase = .savedOnly; return
            default: break
            }
            let open = try await transport.openImports(identity: identity)
            guard mine == ticket else { return }
            if let event = open.first(where: { $0.connectionIDs.contains(connectionID) }) {
                phase = .review(ReceiptReviewDraft(connectionID: connectionID, event: event, receipt: document.preparation?.receipt))
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
