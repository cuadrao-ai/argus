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

private func fixtureAccount(_ id: String, type: String, currency: String = "DOP", archived: Bool = false) -> [String: Any] {
    ["id": id, "type": type, "nature": "asset", "currency": currency, "currency_fraction_digits": 2, "nickname": type,
     "archived": archived, "ownership_share_bps": 10000, "version": 3, "created_at": "2026-10-01T00:00:00Z",
     "updated_at": "2026-10-01T00:00:00Z", "opening": NSNull(), "asset": NSNull(),
     "balance": ["state": "unknown", "amount_minor": NSNull(), "amount": NSNull(), "as_of": NSNull(), "basis": NSNull(),
                 "activity_since_tracking_minor": 0]]
}

private func fixtureOptions() -> FinancialActivityOptions {
    decode(["accounts": [fixtureAccount(accountID, type: "checking"),
                         fixtureAccount("11111111-1111-4111-8111-111111111111", type: "checking", currency: "USD"),
                         fixtureAccount("22222222-2222-4222-8222-222222222222", type: "property"),
                         fixtureAccount("33333333-3333-4333-8333-333333333333", type: "cash", archived: true)],
            "eligibility": ["expense": ["checking", "cash", "card"]], "destination_eligibility": [:],
            "categories": ["groceries", "food", "transport"], "sources": []])
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
    var receiptCategory: String
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

    init(statuses: [String] = ["queued", "preparing", "review_ready"], withReceipt: Bool = true, receiptCategory: String = "groceries",
         open: [FinancialImportEvent] = [fixtureEvent()]) {
        self.statuses = statuses; self.withReceipt = withReceipt; self.receiptCategory = receiptCategory; self.open = open
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
        var receipt = laSirena
        receipt["suggested_category"] = receiptCategory
        return fixtureDocument(status, receipt: withReceipt ? receipt : nil)
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
    func options(identity: SessionSnapshot) async throws -> FinancialActivityOptions { fixtureOptions() }
    func source(_ connectionID: String, identity: SessionSnapshot) async throws -> Data { Data("%PDF".utf8) }
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

    private func signedIn(_ id: String, defaults: UserDefaults, server: ScriptedReceiptServer) throws -> ReceiptJourneyModel {
        let profile = try JSONDecoder().decode(SessionProfile.self, from: Data(#"{"id":"\#(id)"}"#.utf8))
        let snapshot = SessionSnapshot(phase: .authenticated, profile: profile, revision: 1)
        let model = ReceiptJourneyModel(transport: server, currentSession: { snapshot }, pause: { _ in }, pollLimit: 10,
                                        timeZone: TimeZone(identifier: "America/Santo_Domingo")!, defaults: defaults)
        model.bind(snapshot)
        return model
    }

    func testReadingIsAskedOnceRememberedPerAccountAndTurnedOffInSettings() async throws {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "receipt-reading-" + UUID().uuidString))
        let server = ScriptedReceiptServer()
        let alice = try signedIn("alice", defaults: defaults, server: server)
        XCTAssertFalse(alice.readingAllowed, "the first receipt carries the disclosure")
        alice.begin([file])
        XCTAssertEqual(alice.preview, ReceiptPreview([file]), "the captured photo is shown while choosing")
        await alice.answerConsent(true)
        XCTAssertTrue(alice.readingAllowed)
        XCTAssertNil(ReceiptPreview([]))

        let again = try signedIn("alice", defaults: defaults, server: server)
        XCTAssertTrue(again.readingAllowed, "the answer survives a relaunch")
        XCTAssertFalse(try signedIn("bruno", defaults: defaults, server: server).readingAllowed, "another account is asked itself")

        again.setReadingAllowed(false)
        XCTAssertFalse(try signedIn("alice", defaults: defaults, server: server).readingAllowed, "Settings turns it off")
    }

    func testSavingOnlyLeavesTheQuestionForNextTime() async throws {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "receipt-reading-" + UUID().uuidString))
        let model = try signedIn("alice", defaults: defaults, server: ScriptedReceiptServer())
        model.begin([file])
        await model.answerConsent(false)
        XCTAssertFalse(model.readingAllowed, "one saved-only receipt is not a lasting answer")
        model.reset()
        XCTAssertNil(model.preview)
    }

    func testACapturedFileWaitsForConsentAndNothingIsSentBeforeTheAnswer() async {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin([file])
        XCTAssertEqual(model.phase, .consent)
        let sent = await server.uploads
        XCTAssertTrue(sent.isEmpty)
    }

    func testDecliningSavesTheFileWithoutReadingAndStops() async {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin([file])
        await model.answerConsent(false)
        XCTAssertEqual(model.phase, .savedOnly(alreadySaved: false))
        let sent = await server.uploads
        XCTAssertEqual(sent.map(\.consent), [false])
    }

    func testConsentSendsWithItFollowsTheReadingAndOpensTheReviewFilledFromTheReceipt() async throws {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin([file])
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
        XCTAssertEqual(model.accounts(for: draft).map(\.id), [UUID(uuidString: accountID)!],
                       "only open expense accounts in the receipt's currency")
    }

    func testACategoryTheServerDoesNotKnowIsNotPrefilled() async throws {
        let server = ScriptedReceiptServer(receiptCategory: "Supermercado y hogar")
        let model = model(server)
        await model.open("doc-1")
        XCTAssertNil(try XCTUnwrap(review(model)).categoryID)
    }

    func testConfirmingSendsOnlyTheAnswersThenRecordsThePreviewedRequestWithItsToken() async throws {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin([file])
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
        model.begin([file])
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
        model.begin([file])
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
        model.begin([file])
        await model.answerConsent(true)
        await model.confirm()
        XCTAssertNotNil(review(model), "no account chosen, nothing happens")
        let changes = await server.resolved
        XCTAssertTrue(changes.isEmpty)
    }

    func testAnAlreadyRecordedPurchaseTakesTheReceiptInsteadOfANewExpense() async throws {
        let server = ScriptedReceiptServer(open: [fixtureEvent(account: accountID, matches: [activityID])])
        let model = model(server)
        model.begin([file])
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

    func testAnUnreadableReceiptIsHandedOverToBeWrittenByHand() async throws {
        let server = ScriptedReceiptServer(statuses: ["preparing", "needs_attention"])
        let model = model(server)
        model.begin([file])
        await model.answerConsent(true)
        XCTAssertEqual(model.phase, .failed(.couldNotRead))
        XCTAssertFalse(model.canWriteByHand, "only offered where the movement sheet can take it")
        var handed: [ReceiptHandoff] = []
        model.writeByHand = { handed.append($0) }
        XCTAssertTrue(model.canWriteByHand)
        model.handWrite()
        let handoff = try XCTUnwrap(handed.first)
        XCTAssertEqual(handoff.connectionID, "doc-1")
        XCTAssertEqual(handoff.merchant, "La Sirena", "what the reading found comes along")
        XCTAssertEqual(handoff.amount, "250.50")
        XCTAssertEqual(handoff.currency, "DOP")
        XCTAssertEqual(handoff.occurredOn.map(ReceiptReviewDraft.dayText), "2026-10-10")
        XCTAssertEqual(model.phase, .idle, "the journey closes; nothing is recorded")
        let keys = await server.acceptKeys
        XCTAssertTrue(keys.isEmpty)
    }

    func testAMissingDateIsNeitherShownAsTodayNorSaved() async throws {
        let model = model(ScriptedReceiptServer())
        model.begin([file])
        await model.answerConsent(true)
        var draft = try XCTUnwrap(review(model))
        draft.accountID = UUID()
        draft.occurredOn = nil
        model.update(draft)
        XCTAssertFalse(try XCTUnwrap(review(model)).isComplete, "no expense without a date the person chose")
        XCTAssertNil(draft.changes(timeZone: .current).occurredOn, "nothing invents a date")
        await model.confirm()
        XCTAssertNotNil(review(model), "confirming waits for the date")
    }

    func testWritingByHandIsNotOfferedOnAReadableReceipt() async throws {
        let model = model(ScriptedReceiptServer())
        model.writeByHand = { _ in XCTFail("not handed over") }
        model.begin([file])
        await model.answerConsent(true)
        XCTAssertNotNil(review(model))
        XCTAssertFalse(model.canWriteByHand)
        model.handWrite()
        XCTAssertNotNil(review(model), "the review stays")
    }

    func testAReopenedReceiptShowsItsFileBesideTheReview() async throws {
        let model = model(ScriptedReceiptServer(statuses: ["review_ready"]))
        await model.open("doc-1")
        for _ in 0..<100 where model.preview == nil { await Task.yield() }
        XCTAssertEqual(model.preview?.image, Data("%PDF".utf8))
        XCTAssertNotNil(review(model))
    }

    func testAFailedReadingWaitsForThePersonToAskAgain() async throws {
        let server = ScriptedReceiptServer(statuses: ["preparing", "needs_attention"])
        let model = model(server)
        model.begin([file])
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
        model.begin([file])
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
        model.begin([file])
        await model.answerConsent(true)
        XCTAssertEqual(model.phase, .failed(.couldNotSend(.couldNotSave)))
        await server.set(uploadFailure: nil)
        await model.answerConsent(true)
        XCTAssertNotNil(review(model))
    }

    func testARecordedMovementFindsTheReceiptItCameFrom() async throws {
        let server = ScriptedReceiptServer(open: [])
        await server.set(accepted: [fixtureEvent(state: "accepted", account: accountID, activity: activityID)], open: [])
        let model = model(server)
        let found = await model.receipt(for: UUID(uuidString: activityID)!)
        let document = try XCTUnwrap(found)
        XCTAssertEqual(document.connectionID, "doc-1")
        let other = await model.receipt(for: UUID())
        XCTAssertNil(other, "a movement typed by hand has no receipt")
        let data = await model.source(document)
        XCTAssertEqual(data, Data("%PDF".utf8))
    }

    func testSeveralFilesShareOneAnswerAndAreReviewedOneAfterAnother() async throws {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin([file, (data: Data([0x89, 0x50, 0x4E, 0x47]), name: "Segundo.png", pdf: false)])
        XCTAssertEqual(model.phase, .consent, "one question for the whole capture")
        await model.answerConsent(true)
        let sent = await server.uploads
        XCTAssertEqual(sent.map(\.filename), ["Ticket.jpg", "Segundo.png"])
        XCTAssertEqual(sent.map(\.consent), [true, true], "the answer covers every file")
        XCTAssertNotNil(review(model), "the first receipt opens for review")
        XCTAssertEqual(model.waiting.count, 1)
        await model.next()
        XCTAssertNotNil(review(model), "the second receipt follows")
        XCTAssertTrue(model.waiting.isEmpty)
    }

    func testDecliningSavesEveryFileWithoutReading() async {
        let server = ScriptedReceiptServer()
        let model = model(server)
        model.begin([file, file])
        await model.answerConsent(false)
        XCTAssertEqual(model.phase, .savedOnly(alreadySaved: false))
        let sent = await server.uploads
        XCTAssertEqual(sent.map(\.consent), [false, false])
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
