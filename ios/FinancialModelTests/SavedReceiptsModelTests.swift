import Foundation
import XCTest
import ArgusSession
@testable import FinancialModels

@MainActor
final class SavedReceiptsModelTests: XCTestCase {
    private let alice = SessionSnapshot(phase: .authenticated, profile: nil, revision: 1)
    private let signedOut = SessionSnapshot(phase: .signedOut, profile: nil, revision: 2)

    private func document(_ id: String, name: String = "Receipt.pdf") -> SavedDocument {
        SavedDocument(connectionID: id, filename: name, mediaType: "application/pdf", sizeBytes: 100, sourceAvailable: true,
                      status: "saved", createdAt: "2026-10-08T12:00:00Z", updatedAt: "2026-10-08T12:00:00Z")
    }

    private func model(_ transport: ScriptedTransport, session: @escaping @Sendable () async -> SessionSnapshot = { SessionSnapshot(phase: .authenticated, profile: nil, revision: 1) }) -> SavedReceiptsModel {
        let model = SavedReceiptsModel(transport: transport, currentSession: session)
        model.bind(alice)
        return model
    }

    func testSavingAFileListsItAndAnswersSaved() async {
        let transport = ScriptedTransport(listed: [document("a")])
        let model = model(transport)
        await model.save([(Data([0x89, 0x50, 0x4E, 0x47]), "Scan.png", false)])
        XCTAssertEqual(model.outcome, .saved)
        XCTAssertEqual(model.items.map(\.id), ["a"])
        let sent = await transport.saved
        XCTAssertEqual(sent.map(\.mediaType), ["image/png"])
        XCTAssertEqual(sent.map(\.filename), ["Scan.png"])
    }

    func testTheSameFileAgainAnswersAlreadySaved() async {
        let model = model(ScriptedTransport(replayed: true))
        await model.save([(Data([0xFF, 0xD8]), "Photo.jpg", false)])
        XCTAssertEqual(model.outcome, .alreadySaved)
    }

    func testTheServersCodesBecomeTheApprovedMessages() async {
        let cases: [(String, SavedReceiptFailure)] = [
            ("document_too_large", .tooLarge), ("document_media_type_unsupported", .wrongType),
            ("document_rate_limited", .limitReached), ("document_storage_unavailable", .couldNotSave), ("invalid_document", .wrongType),
        ]
        for (code, expected) in cases {
            let model = model(ScriptedTransport(saveFailure: SessionFailure.rejected(status: 400, code: code)))
            await model.save([(Data([1]), "a.pdf", true)])
            XCTAssertEqual(model.outcome, .failed(expected), code)
        }
        let unknown = model(ScriptedTransport(saveFailure: URLError(.notConnectedToInternet)))
        await unknown.save([(Data([1]), "a.pdf", true)])
        XCTAssertEqual(unknown.outcome, .failed(.offline), "no connection says so; the receipt is still on the iPhone")
        let server = model(ScriptedTransport(saveFailure: SessionFailure.unavailable))
        await server.save([(Data([1]), "a.pdf", true)])
        XCTAssertEqual(server.outcome, .failed(.couldNotSave), "a server failure is not called a lost connection")
    }

    func testRetryResendsTheSameFilesAfterACouldNotSaveAndOnlyThen() async {
        let transport = ScriptedTransport(saveFailure: SessionFailure.unavailable)
        let model = model(transport)
        await model.save([(Data([1, 2]), "Ticket.pdf", true)])
        XCTAssertEqual(model.outcome, .failed(.couldNotSave))
        await transport.stopFailing()
        await model.retry()
        XCTAssertEqual(model.outcome, .saved)
        let sent = await transport.saved
        XCTAssertEqual(sent.map(\.filename), ["Ticket.pdf"])

        let tooBig = ScriptedTransport(saveFailure: SessionFailure.rejected(status: 413, code: "document_too_large"))
        let other = self.model(tooBig)
        await other.save([(Data([1]), "big.pdf", true)])
        await other.retry()
        let none = await tooBig.attempts
        XCTAssertEqual(none, 1, "a file that is too large is never retried")
    }

    func testDeleteRemovesTheRowAndAFailureKeepsIt() async {
        let transport = ScriptedTransport(listed: [document("a"), document("b")])
        let model = model(transport)
        await model.load()
        await model.remove(model.items[0])
        XCTAssertEqual(model.items.map(\.id), ["b"])
        await transport.failDeletes()
        await model.remove(model.items[0])
        XCTAssertEqual(model.items.map(\.id), ["b"], "a failed delete keeps the receipt")
        XCTAssertEqual(model.outcome, .failed(.couldNotDelete))
        XCTAssertFalse(model.canRetry, "a failed delete never offers Try again, which would resend an old file")
    }

    func testAFileCapturedDuringASaveWaitsItsTurnAndIsNotLost() async {
        let transport = ScriptedTransport(saveDelayNanoseconds: 60_000_000)
        let model = model(transport)
        let first = Task { await model.save([(Data([1]), "one.pdf", true)]) }
        try? await Task.sleep(nanoseconds: 15_000_000)
        await model.save([(Data([2]), "two.pdf", true)])
        await first.value
        let sent = await transport.saved
        XCTAssertEqual(sent.map(\.filename), ["one.pdf", "two.pdf"])
        XCTAssertEqual(model.outcome, .saved)
        XCTAssertFalse(model.saving)
    }

    func testCancellingAFailedSaveDropsTheHeldFiles() async {
        let transport = ScriptedTransport(saveFailure: SessionFailure.unavailable)
        let model = model(transport)
        await model.save([(Data([1]), "a.pdf", true)])
        XCTAssertTrue(model.canRetry)
        model.discardFailedFiles()
        XCTAssertFalse(model.canRetry)
        model.fail(.unusableFile)
        XCTAssertEqual(model.outcome, .failed(.unusableFile))
        XCTAssertFalse(model.canRetry)
    }

    func testASaveFailingAfterSignOutLeavesNothingHeld() async {
        let transport = ScriptedTransport(saveFailure: SessionFailure.unavailable, saveDelayNanoseconds: 60_000_000)
        let model = model(transport)
        let saving = Task { await model.save([(Data(count: 1_000), "a.pdf", true)]) }
        try? await Task.sleep(nanoseconds: 15_000_000)
        model.bind(signedOut)
        await saving.value
        XCTAssertNil(model.outcome)
        XCTAssertFalse(model.canRetry, "the earlier person's file is not kept")
    }

    func testALateAnswerAfterSignOutIsIgnored() async {
        let transport = ScriptedTransport(listed: [document("a")], delayNanoseconds: 80_000_000)
        let model = model(transport)
        let loading = Task { await model.load() }
        try? await Task.sleep(nanoseconds: 10_000_000)
        model.bind(signedOut)
        await loading.value
        XCTAssertTrue(model.items.isEmpty, "nothing from the earlier person's list appears")
    }

    func testAFailureAfterTheSessionChangedStartsCleanAndTellsTheOwner() async {
        let transport = ScriptedTransport(listFailure: SessionFailure.unauthorized)
        let signedOutSnapshot = signedOut
        let model = model(transport, session: { signedOutSnapshot })
        var told: SessionSnapshot?
        model.sessionChanged = { told = $0 }
        await model.load()
        XCTAssertEqual(told, signedOutSnapshot)
        XCTAssertFalse(model.loadFailed, "a changed session is not shown as a load failure")
    }

    func testALoadFailureIsShownAndNothingIsInvented() async {
        let model = model(ScriptedTransport(listFailure: URLError(.timedOut)))
        await model.load()
        XCTAssertTrue(model.loadFailed)
        XCTAssertTrue(model.items.isEmpty)
    }

    func testTheCopyIsTheApprovedWordsWithoutAnEmDash() {
        for spanish in [true, false] {
            let copy = SavedReceiptCopy(spanish: spanish)
            let all = [copy.title, copy.empty, copy.saving, copy.savedTitle, copy.savedDetail, copy.alreadySaved, copy.tooLarge, copy.wrongType,
                       copy.limitReached, copy.couldNotSave, copy.retry, copy.view, copy.delete, copy.cancel, copy.deleteTitle, copy.deleteMessage,
                       copy.couldNotOpen, copy.couldNotLoad, copy.couldNotDelete, copy.unusableFile, copy.scannerUnavailable]
            XCTAssertTrue(all.allSatisfy { !$0.isEmpty && !$0.contains("\u{2014}") }, spanish ? "es" : "en")
        }
        XCTAssertEqual(SavedReceiptCopy(spanish: true).tooLarge, "El archivo pesa más de 10 MB. Elige uno más pequeño.")
        XCTAssertEqual(SavedReceiptCopy(spanish: false).deleteMessage, "It is deleted from your account and our servers. Your activity does not change.")
    }
}

actor ScriptedTransport: SavedReceiptsTransport {
    struct Sent { let mediaType: String; let filename: String }
    private var listed: [SavedDocument]
    private var replayed: Bool
    private var saveFailure: Error?
    private var listFailure: Error?
    private var deletesFail = false
    private let delay: UInt64
    private let saveDelay: UInt64
    private(set) var saved: [Sent] = []
    private(set) var attempts = 0

    init(listed: [SavedDocument] = [], replayed: Bool = false, saveFailure: Error? = nil, listFailure: Error? = nil, delayNanoseconds: UInt64 = 0, saveDelayNanoseconds: UInt64 = 0) {
        self.listed = listed; self.replayed = replayed; self.saveFailure = saveFailure; self.listFailure = listFailure; self.delay = delayNanoseconds; self.saveDelay = saveDelayNanoseconds
    }
    func stopFailing() { saveFailure = nil }
    func failDeletes() { deletesFail = true }

    func list(limit: Int, offset: Int, identity: SessionSnapshot) async throws -> SavedDocumentPage {
        if delay > 0 { try? await Task.sleep(nanoseconds: delay) }
        if let listFailure { throw listFailure }
        return try JSONDecoder().decode(SavedDocumentPage.self, from: JSONSerialization.data(withJSONObject: [
            "items": listed.map { ["connection_id": $0.connectionID, "filename": $0.filename, "media_type": $0.mediaType, "size_bytes": $0.sizeBytes,
                                    "source_available": $0.sourceAvailable, "status": $0.status, "created_at": $0.createdAt, "updated_at": $0.updatedAt] as [String: Any] },
            "next_offset": NSNull(),
        ]))
    }
    func save(_ bytes: Data, mediaType: String, filename: String, identity: SessionSnapshot) async throws -> SavedDocumentCapture {
        attempts += 1
        if saveDelay > 0 { try? await Task.sleep(nanoseconds: saveDelay) }
        if let saveFailure { throw saveFailure }
        saved.append(Sent(mediaType: mediaType, filename: filename))
        return try JSONDecoder().decode(SavedDocumentCapture.self, from: JSONSerialization.data(withJSONObject: [
            "connection_id": "new", "status": "saved", "replayed": replayed,
        ]))
    }
    func source(_ id: String, identity: SessionSnapshot) async throws -> Data { Data("%PDF".utf8) }
    func delete(_ id: String, identity: SessionSnapshot) async throws {
        if deletesFail { throw SessionFailure.unavailable }
        listed.removeAll { $0.connectionID == id }
    }
}
