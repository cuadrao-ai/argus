import Foundation
import XCTest
@testable import ArgusSession
@testable import FinancialModels

private struct DeletionCall: Equatable, Sendable { let confirm: Bool?; let appleCode: String? }

private actor DeletionModelServer {
    let auth = AuthServer()
    private var replies: [(Int, [String: Any])] = []
    private var loseNext = false
    private var ticketStatuses: [Int] = []
    private(set) var deletions: [DeletionCall] = []
    private(set) var tickets: [String?] = []
    func reply(_ status: Int, _ body: [String: Any]) { replies.append((status, body)) }
    func loseNextResponse() { loseNext = true }
    func failNextTicket(_ status: Int) { ticketStatuses.append(status) }
    func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
        let body = (try? JSONSerialization.jsonObject(with: request.httpBody ?? Data())) as? [String: Any] ?? [:]
        let path = request.url!.path
        if path.hasSuffix("/api/v1/account/delete") {
            deletions.append(DeletionCall(confirm: body["confirm"] as? Bool, appleCode: body["apple_authorization_code"] as? String))
            if loseNext { loseNext = false; throw URLError(.networkConnectionLost) }
            let (status, json) = replies.isEmpty ? (200, ["status": "done", "pending": []]) : replies.removeFirst()
            return respond(request, status, json)
        }
        if path.hasSuffix("/api/v1/feedback") {
            let status = ticketStatuses.isEmpty ? 200 : ticketStatuses.removeFirst()
            if status == 200 { tickets.append(body["type"] as? String) }
            return respond(request, status, status == 200 ? ["success": true] : ["code": "feedback_unavailable"])
        }
        return try await auth.send(request)
    }
    private func respond(_ request: URLRequest, _ status: Int, _ json: [String: Any]) -> (Data, URLResponse) {
        (try! JSONSerialization.data(withJSONObject: json),
         HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!)
    }
}

/// Stands in for the per-owner receipt draft directories the production cleanup removes.
private final class DraftFolders: @unchecked Sendable {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("argus-deletion-model-" + UUID().uuidString, isDirectory: true)
    private let lock = NSLock()
    private var failures = 0
    private(set) var attempts: [UUID] = []
    func create(_ owner: UUID) throws {
        let folder = root.appendingPathComponent(owner.uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try Data("synthetic draft".utf8).write(to: folder.appendingPathComponent("draft.pdf"))
    }
    func exists(_ owner: UUID) -> Bool {
        FileManager.default.fileExists(atPath: root.appendingPathComponent(owner.uuidString).appendingPathComponent("draft.pdf").path)
    }
    func failNext() { lock.withLock { failures += 1 } }
    func remove(_ owner: UUID) throws {
        try lock.withLock {
            attempts.append(owner)
            if failures > 0 { failures -= 1; throw CocoaError(.fileWriteNoPermission) }
        }
        do { try FileManager.default.removeItem(at: root.appendingPathComponent(owner.uuidString, isDirectory: true)) }
        catch let error as CocoaError where error.code == .fileNoSuchFile { }
    }
    deinit { try? FileManager.default.removeItem(at: root) }
}

@MainActor
private struct DeletionModelFixture {
    let server = DeletionModelServer()
    let storage = MemoryStore()
    let folders = DraftFolders()
    let configuration = try! SessionConfiguration(argusAPIURL: URL(string: "https://api.example.test")!,
        supabaseURL: URL(string: "https://auth.example.test")!, publicAnonKey: "sb_publishable_test", keychainService: UUID().uuidString)
    func controller() throws -> SessionController {
        try SessionController(configuration: configuration, storage: storage, fetch: { [server] in try await server.send($0) })
    }
    func model(_ controller: SessionController, appleAvailable: Bool = false) -> AccountDeletionModel {
        let folders = self.folders
        return AccountDeletionModel(controller: controller, appleAvailable: appleAvailable, cleanup: { try folders.remove($0) })
    }
    func login(_ controller: SessionController, email: String = "alice@example.test") async throws -> SessionSnapshot {
        try await controller.login(email: email, password: "synthetic-password", captchaToken: "synthetic-captcha")
    }
    var alice: UUID { get async { server.auth.alice } }
    var bob: UUID { get async { server.auth.bob } }
}

@MainActor
final class AccountDeletionModelTests: XCTestCase {
    func testAcceptedDeletionIsPendingRemovesThatAccountsDraftsAndRelaunchesSignedOut() async throws {
        let fixture = DeletionModelFixture(); let controller = try fixture.controller()
        _ = try await fixture.login(controller)
        let alice = await fixture.alice; let bob = await fixture.bob
        try fixture.folders.create(alice); try fixture.folders.create(bob)
        let model = fixture.model(controller)
        var published: [SessionSnapshot.Phase] = []
        model.sessionChanged = { published.append($0.phase) }
        await fixture.server.reply(202, ["status": "in_progress", "pending": ["apple"]])
        await model.submit()
        XCTAssertEqual(model.state, .pending, "202 is accepted work, never a claimed completion")
        XCTAssertEqual(published, [.accountDeletionPending], "the shell leaves the signed-in surface on acceptance")
        XCTAssertEqual(fixture.folders.attempts, [alice])
        XCTAssertFalse(fixture.folders.exists(alice), "the signed-out account's drafts leave the iPhone")
        XCTAssertTrue(fixture.folders.exists(bob), "cleanup is keyed by the accepted owner only")
        model.finish()
        XCTAssertEqual(model.state, .ready, "Done leaves the signed-out destination without claiming completion")

        let relaunched = try fixture.controller()
        let restored = try await relaunched.restore()
        XCTAssertEqual(restored.phase, .signedOut)
        let reopened = fixture.model(relaunched)
        await reopened.load()
        XCTAssertEqual(reopened.state, .ready, "the next launch is the signed-out entry, never a claimed completion")
        XCTAssertEqual(fixture.folders.attempts, [alice], "a finished cleanup never repeats")
        XCTAssertTrue(fixture.folders.exists(bob))
    }

    func testAcceptedDeletionCleanupThatFailedFinishesOnTheNextLaunch() async throws {
        let fixture = DeletionModelFixture(); let controller = try fixture.controller()
        _ = try await fixture.login(controller)
        let alice = await fixture.alice; let bob = await fixture.bob
        try fixture.folders.create(alice); try fixture.folders.create(bob)
        let model = fixture.model(controller)
        fixture.folders.failNext()
        await fixture.server.reply(202, ["status": "in_progress", "pending": []])
        await model.submit()
        XCTAssertEqual(model.state, .pending)
        XCTAssertTrue(fixture.folders.exists(alice))

        let relaunched = try fixture.controller()
        let restored = try await relaunched.restore()
        XCTAssertEqual(restored.phase, .signedOut)
        let reopened = fixture.model(relaunched)
        await reopened.load()
        XCTAssertEqual(reopened.state, .ready)
        XCTAssertEqual(fixture.folders.attempts, [alice, alice])
        XCTAssertFalse(fixture.folders.exists(alice))
        XCTAssertTrue(fixture.folders.exists(bob))
        let again = fixture.model(try fixture.controller()); await again.load()
        XCTAssertEqual(fixture.folders.attempts, [alice, alice], "nothing is owed after the cleanup finished")
        let deletions = await fixture.server.deletions; XCTAssertEqual(deletions.count, 1)
    }

    func testAcceptedDeletionInterruptedBeforeItsCleanupFinishesOnTheNextLaunch() async throws {
        let fixture = DeletionModelFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        let alice = await fixture.alice; let bob = await fixture.bob
        try fixture.folders.create(alice); try fixture.folders.create(bob)
        await fixture.server.reply(202, ["status": "in_progress", "pending": []])
        _ = try await controller.deleteAccount(expectedIdentity: identity)

        let relaunched = try fixture.controller()
        _ = try await relaunched.restore()
        let reopened = fixture.model(relaunched)
        await reopened.load()
        XCTAssertEqual(reopened.state, .ready)
        XCTAssertEqual(fixture.folders.attempts, [alice])
        XCTAssertFalse(fixture.folders.exists(alice))
        XCTAssertTrue(fixture.folders.exists(bob))
    }

    func testInterruptedResponseThenRetryCompletesAndCleansExactlyOnce() async throws {
        let fixture = DeletionModelFixture(); let controller = try fixture.controller()
        _ = try await fixture.login(controller)
        let alice = await fixture.alice; let bob = await fixture.bob
        try fixture.folders.create(alice); try fixture.folders.create(bob)
        let model = fixture.model(controller)
        await fixture.server.loseNextResponse()
        await model.submit()
        XCTAssertEqual(model.state, .uncertain(canRetry: true))
        let uncertain = await controller.snapshot(); XCTAssertEqual(uncertain.phase, .accountDeletionUncertain)
        XCTAssertTrue(fixture.folders.exists(alice), "an unanswered command cannot clean up")

        await model.retry()
        XCTAssertEqual(model.state, .completed)
        let finished = await controller.snapshot(); XCTAssertEqual(finished.phase, .signedOut)
        XCTAssertEqual(fixture.folders.attempts, [alice])
        XCTAssertFalse(fixture.folders.exists(alice))
        XCTAssertTrue(fixture.folders.exists(bob), "cleanup is keyed by the confirmed owner only")
        let deletions = await fixture.server.deletions
        XCTAssertEqual(deletions.map(\.confirm), [true, true])

        await model.load()
        let again = fixture.model(try fixture.controller()); await again.load()
        XCTAssertEqual(fixture.folders.attempts, [alice], "a finished cleanup never repeats")
    }

    func testRelaunchDuringUnconfirmedDeletionResumesTheSameCommand() async throws {
        let fixture = DeletionModelFixture(); let controller = try fixture.controller()
        _ = try await fixture.login(controller)
        let alice = await fixture.alice; try fixture.folders.create(alice)
        await fixture.server.loseNextResponse()
        await fixture.model(controller).submit()

        let relaunched = try fixture.controller()
        let restored = try await relaunched.restore()
        XCTAssertEqual(restored.phase, .accountDeletionUncertain)
        let model = fixture.model(relaunched)
        await model.load()
        XCTAssertEqual(model.state, .uncertain(canRetry: true))
        XCTAssertEqual(fixture.folders.attempts, [], "an unanswered command never cleans")
        XCTAssertTrue(fixture.folders.exists(alice))
        await fixture.server.reply(202, ["status": "in_progress", "pending": []])
        await model.retry()
        XCTAssertEqual(model.state, .pending)
        XCTAssertEqual(fixture.folders.attempts, [alice])
        XCTAssertFalse(fixture.folders.exists(alice), "the resumed command's acceptance cleans like the first")
        let deletions = await fixture.server.deletions; XCTAssertEqual(deletions.count, 2)
    }

    func testIdentityChangeBeforeCleanupNeverClearsAnotherPersonsDrafts() async throws {
        let fixture = DeletionModelFixture(); let controller = try fixture.controller()
        _ = try await fixture.login(controller)
        let alice = await fixture.alice; let bob = await fixture.bob
        try fixture.folders.create(alice); try fixture.folders.create(bob)
        let model = fixture.model(controller)
        fixture.folders.failNext()
        await model.submit()
        XCTAssertEqual(model.state, .completed, "server completion stands even when local cleanup must retry")
        XCTAssertTrue(fixture.folders.exists(alice))

        let signedInBob = try await fixture.login(controller, email: "bob@example.test")
        XCTAssertEqual(signedInBob.profile?.id.lowercased(), bob.uuidString.lowercased())
        await model.load()
        XCTAssertEqual(fixture.folders.attempts, [alice], "no cleanup runs while another person is signed in")
        XCTAssertTrue(fixture.folders.exists(alice) && fixture.folders.exists(bob))

        _ = try await controller.signOut()
        await model.load()
        XCTAssertEqual(fixture.folders.attempts, [alice, alice])
        XCTAssertFalse(fixture.folders.exists(alice))
        XCTAssertTrue(fixture.folders.exists(bob))
        await model.load()
        XCTAssertEqual(fixture.folders.attempts, [alice, alice])
    }

    func testOrdinarySignOutKeepsDraftsUntilAConfirmedDeletion() async throws {
        let fixture = DeletionModelFixture(); let controller = try fixture.controller()
        _ = try await fixture.login(controller)
        let alice = await fixture.alice; try fixture.folders.create(alice)
        let model = fixture.model(controller)
        _ = try await controller.signOut()
        await model.load()
        XCTAssertEqual(model.state, .ready)
        XCTAssertTrue(fixture.folders.exists(alice))

        _ = try await fixture.login(controller)
        await model.submit()
        XCTAssertEqual(model.state, .completed)
        XCTAssertFalse(fixture.folders.exists(alice))
    }

    func testDeletionOffFilesTheSupportRequestAndKeepsTheSession() async throws {
        let fixture = DeletionModelFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        let alice = await fixture.alice; try fixture.folders.create(alice)
        let model = fixture.model(controller)
        await fixture.server.reply(404, ["code": "not_found"])
        await fixture.server.failNextTicket(503)
        await model.submit()
        XCTAssertEqual(model.state, .supportUnavailable)
        var tickets = await fixture.server.tickets; XCTAssertEqual(tickets.count, 0)

        await model.retry()
        XCTAssertEqual(model.state, .supportRequested)
        tickets = await fixture.server.tickets
        XCTAssertEqual(tickets, ["account_deletion_request"])
        let deletions = await fixture.server.deletions; XCTAssertEqual(deletions.count, 1, "retrying the ticket does not resend deletion")
        let snapshot = await controller.snapshot(); XCTAssertEqual(snapshot, identity)
        XCTAssertTrue(fixture.folders.exists(alice), "a support request deletes nothing on the device")
    }

    func testFreshAppleAuthorizationIsRequestedAndSentOnlyWithTheNextCommand() async throws {
        let fixture = DeletionModelFixture(); let controller = try fixture.controller()
        _ = try await fixture.login(controller)
        let model = fixture.model(controller, appleAvailable: true)
        await fixture.server.reply(409, ["code": "apple_reauthorization_required"])
        await model.submit()
        XCTAssertEqual(model.state, .appleAuthorizationRequired)
        await model.submit(appleAuthorizationCode: "fresh-apple-code")
        XCTAssertEqual(model.state, .completed)
        let deletions = await fixture.server.deletions
        XCTAssertEqual(deletions.map(\.appleCode), [nil, "fresh-apple-code"])

        let unavailable = DeletionModelFixture(); let other = try unavailable.controller()
        _ = try await unavailable.login(other)
        let withoutApple = unavailable.model(other, appleAvailable: false)
        await unavailable.server.reply(409, ["code": "apple_reauthorization_required"])
        await withoutApple.submit()
        XCTAssertEqual(withoutApple.state, .supportRequested, "a build without Apple sign-in offers the support path")
        let tickets = await unavailable.server.tickets; XCTAssertEqual(tickets.count, 1)
    }
}
