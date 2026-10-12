import Foundation
import XCTest
import ArgusSession
@testable import FinancialModels

private func decode<T: Decodable>(_ value: [String: Any]) -> T {
    try! JSONDecoder().decode(T.self, from: JSONSerialization.data(withJSONObject: value))
}

private let accountID = "6a1f0b8e-3c55-4c2e-9a7d-2f1b4c6d8e90"
private let activityID = "0b9c8d7e-6f5a-4b3c-8d2e-1f0a9b8c7d6e"

private func fixtureDocument(_ status: String, receipt: [String: Any]? = nil) -> FinancialDocumentDetail {
    var preparation: Any = NSNull()
    if let receipt { preparation = ["complete": true, "readable": true, "receipt": receipt] }
    return decode(["connection_id": "doc-1", "filename": "Ticket.jpg", "media_type": "image/jpeg", "source_available": true,
                   "status": status, "consent": true, "version": 1, "error_code": NSNull(),
                   "created_at": "2026-10-11T12:00:00Z", "preparation": preparation])
}

nonisolated(unsafe) private let laSirena: [String: Any] = ["merchant": "La Sirena", "occurred_on": "2026-10-10", "currency": "DOP",
    "items": [["id": "1", "description": "Arroz", "quantity": "1", "unit_price": "150.00", "total": "150.00"]],
    "subtotal": "150.00", "tax": NSNull(), "service": NSNull(), "tip": NSNull(), "total": "250.50", "suggested_category": "groceries"]

private func fixtureEvent(_ id: String = "evt-1", version: Int = 1, state: String = "open", account: String? = nil,
                   kind: String? = "expense", matches: [String] = [], activity: String? = nil) -> FinancialImportEvent {
    decode(["id": id, "state": state, "evidence": "receipt", "version": version, "attention": NSNull(), "attention_detail": NSNull(),
            "possible_duplicates": [], "existing_activity_matches": matches, "recorded_duplicates": [],
            "activity_id": activity as Any? ?? NSNull(),
            "facts": ["amount": "250.50", "currency": "DOP", "direction": "outflow", "occurred_on": "2026-10-10",
                      "account_id": account as Any? ?? NSNull(), "kind": kind as Any? ?? NSNull()],
            "resolution": [:], "unresolved": account == nil ? ["account_id"] : [], "account_shared_with_household": NSNull(),
            "observations": [["id": "obs-1", "source": "statement", "connection_id": "doc-1", "external_id": "x", "evidence": "receipt",
                              "status": "posted", "live": true, "revisions": 1, "observed_at": NSNull(), "occurred_on": "2026-10-10",
                              "posted_on": NSNull(), "due_on": NSNull(), "amount": "250.50", "currency": "DOP", "direction": "outflow",
                              "merchant": "La Sirena", "description": NSNull(), "excerpt": NSNull(), "balance_scope": NSNull(),
                              "institution": NSNull(), "account_name": NSNull(), "account_mask": NSNull(), "attachments": [],
                              "redacted": false]],
            "created_at": "2026-10-11T12:00:00Z", "updated_at": "2026-10-11T12:00:00Z"])
}

nonisolated(unsafe) private let command: [String: Any] = ["kind": "expense", "account_id": accountID, "source_account_id": NSNull(),
    "destination_account_id": NSNull(), "amount": "250.50", "occurred_at": "2026-10-10T12:00:00-04:00",
    "time_zone": "America/Santo_Domingo", "note": "La Sirena", "category_id": "groceries", "source_id": NSNull(),
    "purchase_activity_id": NSNull(), "expected_revision": NSNull(), "reason": NSNull(), "expected_versions": [accountID: 3],
    "coverage": [], "preview_token": NSNull(), "principal": NSNull(), "interest": NSNull(), "fees": NSNull(), "reversal_of_activity_id": NSNull()]

private func fixturePreview(ready: Bool = true) -> FinancialImportPreview {
    decode(["event": eventJSON(account: accountID),
            "preview": ["ready": ready, "expected_versions": [accountID: 3], "affected_accounts": [],
                        "reviewed_request": ready ? command : NSNull(), "preview_token": ready ? "token-1" : NSNull()]])
}

private func eventJSON(account: String?) -> [String: Any] {
    let value = fixtureEvent(account: account)
    return ["id": value.id, "state": value.state, "evidence": "receipt", "version": 2, "attention": NSNull(), "attention_detail": NSNull(),
            "possible_duplicates": [], "existing_activity_matches": [], "recorded_duplicates": [], "activity_id": NSNull(),
            "facts": ["amount": "250.50", "currency": "DOP", "direction": "outflow", "occurred_on": "2026-10-10",
                      "account_id": account as Any? ?? NSNull(), "kind": "expense"],
            "resolution": [:], "unresolved": [], "account_shared_with_household": false, "observations": [],
            "created_at": "2026-10-11T12:00:00Z", "updated_at": "2026-10-11T12:00:00Z"]
}

private func fixtureActivity() -> FinancialActivityDetail {
    decode(["activity_id": activityID, "revision": 1, "kind": "expense", "amount_minor": 25050, "amount": "250.50", "currency": "DOP",
            "currency_fraction_digits": 2, "occurred_at": "2026-10-10T12:00:00-04:00", "time_zone": "America/Santo_Domingo",
            "note": "La Sirena", "category_id": "groceries", "source_id": NSNull(), "purchase_activity_id": NSNull(),
            "purchase_revision": NSNull(), "reason": NSNull(), "recorded_at": "2026-10-11T12:00:00Z", "recorded_by": NSNull(),
            "legs": []])
}

actor ScriptedReceiptServer: ReceiptJourneyTransport {
    var statuses: [String]
    var withReceipt: Bool
    var open: [FinancialImportEvent]
    var accepted: [FinancialImportEvent] = []
    var previewReady = true
    var acceptFailures = 0
    var uploadFailure: Error?
    private(set) var uploads: [(filename: String, consent: Bool)] = []
    private(set) var resolved: [FinancialImportChanges] = []
    private(set) var acceptKeys: [UUID] = []
    private(set) var acceptedRequests: [FinancialActivityCommand] = []
    private(set) var prepares = 0
    private(set) var links: [UUID] = []

    init(statuses: [String] = ["queued", "preparing", "review_ready"], withReceipt: Bool = true,
         open: [FinancialImportEvent] = [fixtureEvent()]) {
        self.statuses = statuses; self.withReceipt = withReceipt; self.open = open
    }
    func set(statuses: [String]) { self.statuses = statuses }
    func set(previewReady: Bool) { self.previewReady = previewReady }
    func set(acceptFailures: Int) { self.acceptFailures = acceptFailures }
    func set(uploadFailure: Error?) { self.uploadFailure = uploadFailure }
    func set(accepted: [FinancialImportEvent], open: [FinancialImportEvent]) { self.accepted = accepted; self.open = open }

    func upload(_ bytes: Data, mediaType: String, filename: String, consent: Bool, identity: SessionSnapshot) async throws -> SavedDocumentCapture {
        if let uploadFailure { throw uploadFailure }
        uploads.append((filename, consent))
        return SavedDocumentCapture(connectionID: "doc-1", status: consent ? "queued" : "saved", replayed: false)
    }
    func document(_ connectionID: String, identity: SessionSnapshot) async throws -> FinancialDocumentDetail {
        let status = statuses.count > 1 ? statuses.removeFirst() : statuses[0]
        return fixtureDocument(status, receipt: withReceipt ? laSirena : nil)
    }
    func prepare(_ connectionID: String, identity: SessionSnapshot) async throws -> SavedDocumentCapture {
        prepares += 1
        statuses = ["preparing", "review_ready"]
        return SavedDocumentCapture(connectionID: connectionID, status: "queued", replayed: false)
    }
    func openImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent] { open }
    func acceptedImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent] { accepted }
    func resolve(_ event: FinancialImportEvent, changes: FinancialImportChanges, identity: SessionSnapshot) async throws -> FinancialImportEvent {
        resolved.append(changes)
        return fixtureEvent(version: event.version + 1, account: accountID)
    }
    func preview(_ eventID: String, identity: SessionSnapshot) async throws -> FinancialImportPreview {
        fixturePreview(ready: previewReady)
    }
    func accept(_ event: FinancialImportEvent, request: FinancialActivityCommand, key: UUID, identity: SessionSnapshot) async throws -> FinancialImportAcceptance {
        acceptKeys.append(key)
        acceptedRequests.append(request)
        if acceptFailures > 0 { acceptFailures -= 1; throw URLError(.networkConnectionLost) }
        return FinancialImportAcceptance(event: event, activity: fixtureActivity(), replayed: acceptKeys.count > 1)
    }
    func link(_ event: FinancialImportEvent, activityID: UUID, identity: SessionSnapshot) async throws -> FinancialImportEvent {
        links.append(activityID)
        return event
    }
}

extension FinancialImportAcceptance {
    init(event: FinancialImportEvent, activity: FinancialActivityDetail, replayed: Bool) {
        self = decode(["event": eventJSON(account: accountID),
                       "activity": try! JSONSerialization.jsonObject(with: JSONEncoder().encode(activity)), "replayed": replayed])
    }
}

@MainActor
final class ReceiptJourneyModelTests: XCTestCase {
    private let alice = SessionSnapshot(phase: .authenticated, profile: nil, revision: 1)
    private let file = (data: Data([0xFF, 0xD8, 0xFF]), name: "Ticket.jpg", pdf: false)

    private func model(_ server: ScriptedReceiptServer, pollLimit: Int = 10) -> ReceiptJourneyModel {
        let model = ReceiptJourneyModel(transport: server, currentSession: { SessionSnapshot(phase: .authenticated, profile: nil, revision: 1) },
                                        pause: { _ in }, pollLimit: pollLimit, timeZone: TimeZone(identifier: "America/Santo_Domingo")!)
        model.bind(alice)
        return model
    }

    private func review(_ model: ReceiptJourneyModel) -> ReceiptReviewDraft? {
        if case .review(let draft) = model.phase { draft } else { nil }
    }

    func testACapturedFileWaitsForConsentAndNothingIsSentBeforeTheAnswer() async {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin(file)
        XCTAssertEqual(model.phase, .consent)
        let sent = await server.uploads
        XCTAssertTrue(sent.isEmpty)
    }

    func testDecliningSavesTheFileWithoutReadingAndStops() async {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin(file)
        await model.answerConsent(false)
        XCTAssertEqual(model.phase, .savedOnly)
        let sent = await server.uploads
        XCTAssertEqual(sent.map(\.consent), [false])
    }

    func testConsentSendsWithItFollowsTheReadingAndOpensTheReviewFilledFromTheReceipt() async throws {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin(file)
        await model.answerConsent(true)
        let sent = await server.uploads
        XCTAssertEqual(sent.map(\.consent), [true])
        let draft = try XCTUnwrap(review(model))
        XCTAssertEqual(draft.merchant, "La Sirena")
        XCTAssertEqual(draft.amount, "250.50")
        XCTAssertEqual(draft.currency, "DOP")
        XCTAssertEqual(draft.occurredOn.map(ReceiptReviewDraft.dayText), "2026-10-10")
        XCTAssertEqual(draft.categoryID, "groceries")
        XCTAssertNil(draft.accountID, "the server could not tell which account paid")
        XCTAssertFalse(draft.isComplete, "an account is needed before confirming")
        XCTAssertEqual(draft.receipt?.items.map(\.description), ["Arroz"])
    }

    func testConfirmingSendsOnlyTheAnswersThenRecordsThePreviewedRequestWithItsToken() async throws {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin(file)
        await model.answerConsent(true)
        var draft = try XCTUnwrap(review(model))
        draft.accountID = UUID(uuidString: accountID)
        draft.amount = "250.00"
        model.update(draft)
        await model.confirm()
        guard case .recorded(let recorded) = model.phase else { return XCTFail("\(model.phase)") }
        XCTAssertEqual(recorded.activityId, UUID(uuidString: activityID))
        let changes = await server.resolved
        XCTAssertEqual(changes.count, 1)
        XCTAssertEqual(changes[0].accountID, UUID(uuidString: accountID))
        XCTAssertEqual(changes[0].amount, "250.00")
        XCTAssertNil(changes[0].currency, "an unchanged currency is not sent")
        XCTAssertNil(changes[0].kind, "an expense stays an expense")
        XCTAssertEqual(changes[0].note, "La Sirena")
        let requests = await server.acceptedRequests
        XCTAssertEqual(requests.first?.previewToken, "token-1")
    }

    func testARetryAfterALostReplyReusesTheSameKeySoTheExpenseIsRecordedOnce() async throws {
        let server = ScriptedReceiptServer()
        await server.set(acceptFailures: 1)
        let model = model(server)
        model.begin(file)
        await model.answerConsent(true)
        var draft = try XCTUnwrap(review(model))
        draft.accountID = UUID(uuidString: accountID)
        model.update(draft)
        await model.confirm()
        XCTAssertEqual(model.phase, .failed(.couldNotRecord(nil)))
        await model.backToReview()
        var again = try XCTUnwrap(review(model))
        again.accountID = UUID(uuidString: accountID)
        model.update(again)
        await model.confirm()
        guard case .recorded = model.phase else { return XCTFail("\(model.phase)") }
        let keys = await server.acceptKeys
        XCTAssertEqual(keys.count, 2)
        XCTAssertEqual(keys[0], keys[1], "the retry replays the first recording")
    }

    func testNothingIsRecordedWhenThePreviewIsNotReady() async throws {
        let server = ScriptedReceiptServer()
        await server.set(previewReady: false)
        let model = model(server)
        model.begin(file)
        await model.answerConsent(true)
        var draft = try XCTUnwrap(review(model))
        draft.accountID = UUID(uuidString: accountID)
        model.update(draft)
        await model.confirm()
        XCTAssertEqual(model.phase, .failed(.couldNotRecord("balance_coverage_required")))
        let keys = await server.acceptKeys
        XCTAssertTrue(keys.isEmpty)
    }

    func testAnIncompleteReviewCannotBeConfirmed() async throws {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin(file)
        await model.answerConsent(true)
        await model.confirm()
        XCTAssertNotNil(review(model), "no account chosen, nothing happens")
        let changes = await server.resolved
        XCTAssertTrue(changes.isEmpty)
    }

    func testAnAlreadyRecordedPurchaseTakesTheReceiptInsteadOfANewExpense() async throws {
        let server = ScriptedReceiptServer(open: [fixtureEvent(account: accountID, matches: [activityID])])
        let model = model(server)
        model.begin(file)
        await model.answerConsent(true)
        let draft = try XCTUnwrap(review(model))
        XCTAssertEqual(draft.existingMatch, UUID(uuidString: activityID))
        await model.linkExisting()
        XCTAssertEqual(model.phase, .linked(UUID(uuidString: activityID)!.uuidString))
        let links = await server.links
        XCTAssertEqual(links, [UUID(uuidString: activityID)!])
        let keys = await server.acceptKeys
        XCTAssertTrue(keys.isEmpty, "linking records nothing new")
    }

    func testAFailedReadingWaitsForThePersonToAskAgain() async throws {
        let server = ScriptedReceiptServer(statuses: ["preparing", "needs_attention"])
        let model = model(server)
        model.begin(file)
        await model.answerConsent(true)
        XCTAssertEqual(model.phase, .failed(.couldNotRead))
        let before = await server.prepares
        XCTAssertEqual(before, 0, "a failed reading is never retried by itself")
        await model.readAgain()
        let after = await server.prepares
        XCTAssertEqual(after, 1)
        XCTAssertNotNil(review(model))
    }

    func testALongReadingStopsWaitingAndAReopenPicksItUp() async throws {
        let server = ScriptedReceiptServer(statuses: ["preparing"])
        let model = model(server, pollLimit: 3)
        model.begin(file)
        await model.answerConsent(true)
        XCTAssertEqual(model.phase, .stillPreparing("doc-1"))
        await server.set(statuses: ["review_ready"])
        await model.open("doc-1")
        XCTAssertNotNil(review(model))
    }

    func testAReadingWithNoMovementSaysSoAndARecordedOneOpensItsExpense() async {
        let empty = ScriptedReceiptServer(open: [])
        let model = model(empty)
        await model.open("doc-1")
        XCTAssertEqual(model.phase, .failed(.nothingToRecord))
        await empty.set(accepted: [fixtureEvent(state: "accepted", account: accountID, activity: activityID)], open: [])
        await model.open("doc-1")
        XCTAssertEqual(model.phase, .linked(activityID))
    }

    func testASendFailureKeepsTheFileForAnotherTry() async {
        let server = ScriptedReceiptServer()
        await server.set(uploadFailure: SessionFailure.unavailable)
        let model = model(server)
        model.begin(file)
        await model.answerConsent(true)
        XCTAssertEqual(model.phase, .failed(.couldNotSend(.couldNotSave)))
        await server.set(uploadFailure: nil)
        await model.answerConsent(true)
        XCTAssertNotNil(review(model))
    }

    func testChangesCarryOnlyWhatDiffers() {
        var draft = ReceiptReviewDraft(connectionID: "doc-1", event: fixtureEvent(account: accountID), receipt: nil)
        draft.merchant = ""
        XCTAssertEqual(draft.changes(timeZone: .current), FinancialImportChanges(), "nothing differs, nothing is sent")
        draft.occurredOn = ReceiptReviewDraft.day("2026-10-09")
        let changes = draft.changes(timeZone: TimeZone(identifier: "America/Santo_Domingo")!)
        XCTAssertEqual(changes.occurredOn, "2026-10-09")
        XCTAssertEqual(changes.timeZone, "America/Santo_Domingo")
    }
}
