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
}
