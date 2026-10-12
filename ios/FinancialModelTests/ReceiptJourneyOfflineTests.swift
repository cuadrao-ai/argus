import XCTest
import ArgusSession
@testable import FinancialModels

/// A receipt that cannot be sent for lack of a connection is kept on this iPhone and sent when the network returns.
@MainActor
final class ReceiptJourneyOfflineTests: XCTestCase {
    private let file = (data: Data([0xFF, 0xD8, 0xFF]), name: "Ticket.jpg", pdf: false)

    private func signedIn(_ id: String, defaults: UserDefaults, server: ScriptedReceiptServer,
                          pending: ReceiptPendingStore?) throws -> ReceiptJourneyModel {
        let profile = try JSONDecoder().decode(SessionProfile.self, from: Data(#"{"id":"\#(id)"}"#.utf8))
        let snapshot = SessionSnapshot(phase: .authenticated, profile: profile, revision: 1)
        let model = ReceiptJourneyModel(transport: server, currentSession: { snapshot }, pause: { _ in }, pollLimit: 10,
                                        timeZone: TimeZone(identifier: "America/Santo_Domingo")!, defaults: defaults,
                                        pendingStore: { _ in pending })
        model.bind(snapshot)
        return model
    }

    private func pendingFolder() -> ReceiptPendingStore {
        ReceiptPendingStore(directory: FileManager.default.temporaryDirectory.appendingPathComponent("pending-" + UUID().uuidString))
    }

    func testOfflineKeepsTheReceiptForLaterAndSendsItWhenTheNetworkReturns() async throws {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "receipt-offline-" + UUID().uuidString))
        let server = ScriptedReceiptServer()
        await server.set(uploadFailure: URLError(.notConnectedToInternet))
        let pending = pendingFolder()
        let model = try signedIn("alice", defaults: defaults, server: server, pending: pending)
        model.begin([file])
        await model.answerConsent(true)
        XCTAssertEqual(model.phase, .failed(.couldNotSend(.offline)))
        XCTAssertEqual(pending.entries.count, 1, "kept on this iPhone as soon as the send fails, as the sheet says")
        XCTAssertTrue(model.canSaveForLater)
        model.saveForLater()
        XCTAssertEqual(model.phase, .idle, "the sheet closes")
        XCTAssertEqual(pending.entries.map(\.consent), [true], "kept on this iPhone with the answer about reading")
        XCTAssertEqual(pending.entries.first.flatMap(pending.data), file.data)

        await model.networkReturned()
        XCTAssertEqual(pending.entries.count, 1, "still offline: kept for the next return")
        await server.set(uploadFailure: nil)
        await model.networkReturned()
        XCTAssertTrue(pending.entries.isEmpty, "sent once the network is back")
        let sent = await server.uploads
        XCTAssertEqual(sent.last?.filename, "Ticket.jpg")
        XCTAssertEqual(sent.last?.consent, true)
    }

    func testKeptReceiptsAreSentOnTheNextLaunchAndANoStaysANo() async throws {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "receipt-offline-" + UUID().uuidString))
        let pending = pendingFolder()
        try pending.keep([file], consent: false)
        let server = ScriptedReceiptServer()
        _ = try signedIn("alice", defaults: defaults, server: server, pending: pending)
        for _ in 0..<100 where !pending.entries.isEmpty { await Task.yield() }
        XCTAssertTrue(pending.entries.isEmpty, "signing in sends what was kept")
        let sent = await server.uploads
        XCTAssertEqual(sent.map(\.consent), [false], "a receipt kept without reading is never read")
    }

    func testAServerFailureIsNotOfferedAsSaveForLater() async throws {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "receipt-offline-" + UUID().uuidString))
        let server = ScriptedReceiptServer()
        await server.set(uploadFailure: SessionFailure.unavailable)
        let model = try signedIn("alice", defaults: defaults, server: server, pending: pendingFolder())
        model.begin([file])
        await model.answerConsent(true)
        XCTAssertEqual(model.phase, .failed(.couldNotSend(.couldNotSave)))
        XCTAssertFalse(model.canSaveForLater)
    }

    private func offlineModel(_ pending: ReceiptPendingStore, server: ScriptedReceiptServer, account: String = "alice") async throws -> ReceiptJourneyModel {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "receipt-offline-" + UUID().uuidString))
        await server.set(uploadFailure: URLError(.notConnectedToInternet))
        let model = try signedIn(account, defaults: defaults, server: server, pending: pending)
        model.begin([file])
        await model.answerConsent(true)
        return model
    }

    func testCancellingAnOfflineReceiptDiscardsTheKeptCopy() async throws {
        let pending = pendingFolder()
        let model = try await offlineModel(pending, server: ScriptedReceiptServer())
        XCTAssertEqual(pending.entries.count, 1)
        model.reset()
        XCTAssertTrue(pending.entries.isEmpty, "Cancelar leaves nothing on the iPhone")
    }

    func testARetryThatGoesThroughRemovesTheKeptCopy() async throws {
        let pending = pendingFolder()
        let server = ScriptedReceiptServer()
        let model = try await offlineModel(pending, server: server)
        await server.set(uploadFailure: nil)
        await model.answerConsent(true)
        XCTAssertTrue(pending.entries.isEmpty, "sent from the sheet, so nothing is sent twice later")
        XCTAssertNotEqual(model.phase, .failed(.couldNotSend(.offline)), "the reading goes on")
    }

    func testSigningOutOrSwitchingAccountsClearsThatAccountsKeptReceipts() async throws {
        let pending = pendingFolder()
        let model = try await offlineModel(pending, server: ScriptedReceiptServer())
        model.saveForLater()
        XCTAssertEqual(pending.entries.count, 1)
        model.bind(nil)
        XCTAssertTrue(pending.entries.isEmpty, "signing out or deleting the account takes the photos off the iPhone")
        XCTAssertFalse(FileManager.default.fileExists(atPath: pending.directory.path))

        let other = try await offlineModel(pending, server: ScriptedReceiptServer())
        other.saveForLater()
        let bruno = try JSONDecoder().decode(SessionProfile.self, from: Data(#"{"id":"bruno"}"#.utf8))
        other.bind(SessionSnapshot(phase: .authenticated, profile: bruno, revision: 2))
        XCTAssertTrue(pending.entries.isEmpty, "another account never sends or sees them")
    }

    func testAFileThatCannotBeReadNowIsKeptAndARejectedOneDoesNotBlockTheRest() async throws {
        let pending = pendingFolder()
        let ids = try pending.keep([file, (Data([1, 2]), "Segundo.jpg", false)], consent: false)
        // The first file cannot be read right now (as while the phone is locked) but is still there.
        let first = pending.directory.appendingPathComponent(ids[0].uuidString)
        try FileManager.default.removeItem(at: first)
        try FileManager.default.createDirectory(at: first, withIntermediateDirectories: false)
        let server = ScriptedReceiptServer()
        await server.set(uploadFailure: SessionFailure.rejected(status: 415, code: "document_media_type_unsupported"))
        let model = try signedIn("alice", defaults: try XCTUnwrap(UserDefaults(suiteName: "receipt-offline-" + UUID().uuidString)),
                                 server: server, pending: pending)
        await model.networkReturned()
        XCTAssertEqual(pending.entries.count, 2, "an unreadable file is never deleted")
        XCTAssertEqual(pending.entries.first { $0.id == ids[1] }?.rejected, true, "a refused file is marked")
        await server.set(uploadFailure: nil)
        await model.networkReturned()
        let sent = await server.uploads
        XCTAssertTrue(sent.isEmpty, "the refused file is skipped and the unreadable one waits")
        try FileManager.default.removeItem(at: first)
        await model.networkReturned()
        XCTAssertEqual(pending.entries.map(\.id), [ids[1]], "a file that is truly gone is forgotten")
    }
}
