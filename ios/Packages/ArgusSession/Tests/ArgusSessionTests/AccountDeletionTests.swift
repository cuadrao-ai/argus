import Auth
import Foundation
import XCTest
@testable import ArgusSession

private actor DeletionServer {
    let auth = AuthServer()
    var status = 200
    var body: [String: Any] = ["status": "done", "pending": []]
    var retry: String?
    var loseResponse = false
    var requests: [URLRequest] = []
    var tickets: [URLRequest] = []
    var gate: RequestGate?
    var sdkUserGate: RequestGate?
    func configure(_ status: Int, _ body: [String: Any], retry: String? = nil, lose: Bool = false) {
        self.status = status; self.body = body; self.retry = retry; loseResponse = lose
    }
    func hold(_ gate: RequestGate) { self.gate = gate }
    func holdSDKUser(_ gate: RequestGate) { sdkUserGate = gate }
    func captured() -> [URLRequest] { requests }
    func supportTickets() -> [URLRequest] { tickets }
    func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
        if request.url!.path.hasSuffix("/api/v1/feedback") {
            tickets.append(request)
            return (Data(#"{"success":true}"#.utf8),
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!)
        }
        guard request.url!.path.hasSuffix("/account/delete") else {
            if request.url!.path.hasSuffix("/user"), let sdkUserGate { await sdkUserGate.enter() }
            return try await auth.send(request)
        }
        requests.append(request)
        if let gate { await gate.enter() }
        if loseResponse { throw URLError(.networkConnectionLost) }
        var headers = ["Content-Type": "application/json"]
        if let retry { headers["Retry-After"] = retry }
        return (try JSONSerialization.data(withJSONObject: body),
            HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: headers)!)
    }
}

private struct DeletionFixture {
    let server = DeletionServer()
    let storage = MemoryStore()
    let configuration = try! SessionConfiguration(argusAPIURL: URL(string: "https://api.example.test")!,
        supabaseURL: URL(string: "https://auth.example.test")!, publicAnonKey: "sb_publishable_test", keychainService: UUID().uuidString)
    func controller(appleChecker: any AppleCredentialChecking = AuthorizedAppleChecker()) throws -> SessionController {
        try SessionController(configuration: configuration, storage: storage, appleChecker: appleChecker, fetch: { [server] in try await server.send($0) })
    }
    func login(_ controller: SessionController) async throws -> SessionSnapshot {
        try await controller.login(email: "alice@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha")
    }
    func journal() throws -> AccountDeletionJournal? {
        try CredentialVault(backing: storage, prefix: configuration.storagePrefix).deletionJournal()
    }
}

private struct DeletionCleanupFiles: Sendable {
    let root: URL
    init() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent("argus-cleanup-test-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }
    private func directory(_ userID: UUID) -> URL { root.appendingPathComponent(userID.uuidString, isDirectory: true) }
    func create(_ userID: UUID) throws {
        let owner = directory(userID)
        try FileManager.default.createDirectory(at: owner, withIntermediateDirectories: true)
        try Data("synthetic draft".utf8).write(to: owner.appendingPathComponent("draft.txt"))
    }
    func contains(_ userID: UUID) -> Bool { FileManager.default.fileExists(atPath: directory(userID).appendingPathComponent("draft.txt").path) }
    func remove(_ userID: UUID) throws {
        do { try FileManager.default.removeItem(at: directory(userID)) }
        catch let error as CocoaError where error.code == .fileNoSuchFile { }
    }
    func removeAll() throws { try FileManager.default.removeItem(at: root) }
}

private enum DeletionCleanupTestFailure: Error, Sendable { case callbackFailed, expectedCompletion }

final class AccountDeletionTests: XCTestCase {
    func testDoneIssuesOwnerReceiptAndRetiresWithoutRefreshOrCapture() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        let beforeRefresh = await fixture.server.auth.count("/token")
        let result = try await controller.deleteAccount(expectedIdentity: identity, freshAppleAuthorizationCode: "fresh-code")
        guard case .completed(let receipt) = result else { return XCTFail("Expected server completion") }
        XCTAssertEqual(receipt.userID.uuidString.lowercased(), identity.profile!.id.lowercased())
        XCTAssertEqual(receipt.initiatingRevision, identity.revision)
        let snapshot = await controller.snapshot(); XCTAssertEqual(snapshot.phase, .signedOut)
        XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
        let requests = await fixture.server.captured(); XCTAssertEqual(requests.count, 1)
        let body = try JSONSerialization.jsonObject(with: requests[0].httpBody!) as! [String: Any]
        XCTAssertEqual(body["confirm"] as? Bool, true)
        XCTAssertEqual(body["apple_authorization_code"] as? String, "fresh-code")
        XCTAssertNil(body["user_id"])
        let afterRefresh = await fixture.server.auth.count("/token"); XCTAssertEqual(afterRefresh, beforeRefresh)
        let captures = await fixture.server.auth.count("/authorization-code"); XCTAssertEqual(captures, 0)
        let journalData = try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".deletion")!
        XCTAssertFalse(String(decoding: journalData, as: UTF8.self).contains("fresh-code"))
    }

    func testAcceptedRetiresProofAndRelaunchCannotRetry() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        await fixture.server.configure(202, ["status": "in_progress", "pending": ["apple"]])
        let result = try await controller.deleteAccount(expectedIdentity: identity)
        XCTAssertEqual(result, .pending(userID: UUID(uuidString: identity.profile!.id)!))
        let restored = try fixture.controller(); let snapshot = try await restored.restore()
        XCTAssertEqual(snapshot.phase, .signedOut)
        XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
        do { _ = try await restored.resumePendingAccountDeletion(); XCTFail("Accepted deletion has no interactive proof") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        let commands = await fixture.server.captured(); XCTAssertEqual(commands.count, 1)
    }

    func testAcceptedDeletionRelaunchesSignedOutWithNothingStoredAfterTheServerFinishes() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        await fixture.server.configure(202, ["status": "in_progress", "pending": ["analytics"]])
        let result = try await controller.deleteAccount(expectedIdentity: identity)
        XCTAssertEqual(result, .pending(userID: UUID(uuidString: identity.profile!.id)!))
        let accepted = await controller.snapshot(); XCTAssertEqual(accepted.phase, .accountDeletionPending)
        XCTAssertEqual(try fixture.journal()?.phase, .pending)

        await fixture.server.auth.configure(meStatuses: [401, 401, 401], refreshStatus: 400, refreshErrorCode: "user_not_found")
        let requestsBefore = await fixture.server.auth.captured().count
        for _ in 0..<2 {
            let relaunched = try fixture.controller()
            let snapshot = try await relaunched.restore()
            XCTAssertEqual(snapshot.phase, .signedOut, "relaunch after an accepted deletion lands signed out")
            XCTAssertNil(snapshot.profile)
            let statuses = try await relaunched.accountDeletionStatuses(); XCTAssertEqual(statuses, [])
        }
        for key in [".session", ".pending", ".deletion"] {
            XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + key), key)
        }
        let requestsAfter = await fixture.server.auth.captured().count
        XCTAssertEqual(requestsAfter, requestsBefore, "the signed-out relaunch needs no network")
        let commands = await fixture.server.captured(); XCTAssertEqual(commands.count, 1)
    }

    func testTransientNetworkErrorKeepsDeletionStateAndSessionAcrossRelaunch() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        await fixture.server.configure(202, ["status": "in_progress", "pending": []], lose: true)
        let result = try await controller.deleteAccount(expectedIdentity: identity)
        guard case .uncertain = result else { return XCTFail("A lost response is uncertain") }
        for _ in 0..<2 {
            let relaunched = try fixture.controller()
            let snapshot = try await relaunched.restore()
            XCTAssertEqual(snapshot.phase, .accountDeletionUncertain, "a network error never signs out")
        }
        XCTAssertEqual(try fixture.journal()?.phase, .uncertain)
        XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"), "proof kept for Check again")
        let userID = try XCTUnwrap(UUID(uuidString: identity.profile!.id))
        let status = try await fixture.controller().accountDeletionStatus(userID: userID)
        XCTAssertEqual(status, .uncertain(userID: userID, retryAfter: nil, canRetry: true, recovery: nil))
    }

    func testLostResponseSurvivesRelaunchAndBlocksProtectedDispatchBeforeSameCommandResolution() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        await fixture.server.configure(200, ["status": "done", "pending": []], lose: true)
        let result = try await controller.deleteAccount(expectedIdentity: identity, freshAppleAuthorizationCode: "one-use-code")
        guard case .uncertain = result else { return XCTFail("Lost response is uncertain") }
        XCTAssertEqual(try fixture.journal()?.phase, .uncertain)
        XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
        do { _ = try await controller.financialAccounts(expectedIdentity: identity); XCTFail("Quarantined") } catch {}
        do { _ = try await controller.signOut(); XCTFail("Cannot discard recovery proof") }
        catch { XCTAssertEqual(error as? SessionFailure, .accountDeletionInProgress) }
        let restored = try fixture.controller(); let snapshot = try await restored.restore()
        XCTAssertEqual(snapshot.phase, .accountDeletionUncertain)
        await fixture.server.configure(200, ["status": "done", "pending": []])
        _ = try await restored.resumePendingAccountDeletion()
        let commands = await fixture.server.captured(); XCTAssertEqual(commands.count, 2)
        let body = try JSONSerialization.jsonObject(with: commands[1].httpBody!) as! [String: Any]
        XCTAssertNil(body["apple_authorization_code"], "Never replay one-time code")
        XCTAssertEqual(commands[0].value(forHTTPHeaderField: "Authorization"), commands[1].value(forHTTPHeaderField: "Authorization"))
    }

    func testUnauthorizedNeverRefreshesAndKeepsUncertaintyForSupport() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        let before = await fixture.server.auth.count("/token")
        await fixture.server.configure(401, ["code": "unauthorized"])
        let result = try await controller.deleteAccount(expectedIdentity: identity)
        guard case .uncertain(_, _, let canRetry, _) = result else { return XCTFail("Unauthorized does not prove intact account") }
        XCTAssertFalse(canRetry)
        _ = try await controller.resumePendingAccountDeletion()
        let after = await fixture.server.auth.count("/token"); XCTAssertEqual(after, before)
        let commands = await fixture.server.captured(); XCTAssertEqual(commands.count, 1)
    }

    func testNoAdmissionRefusalsRestoreCurrentIdentityAndNeverClearCredentials() async throws {
        let cases: [(Int, String, AccountDeletionRefusal)] = [
            (409, "apple_reauthorization_required", .freshAppleAuthorizationRequired),
            (409, "apple_identity_mismatch", .freshAppleAuthorizationRequired),
            (400, "apple_authorization_invalid", .freshAppleAuthorizationRequired),
            (503, "account_deletion_unavailable", .unavailable),
            (403, "account_deletion_not_allowed", .forbidden), (404, "not_found", .disabled)]
        for (status, code, expected) in cases {
            let fixture = DeletionFixture(); let controller = try fixture.controller()
            let identity = try await fixture.login(controller)
            await fixture.server.configure(status, ["code": code])
            let result = try await controller.deleteAccount(expectedIdentity: identity)
            XCTAssertEqual(result, .refused(expected))
            let snapshot = await controller.snapshot(); XCTAssertEqual(snapshot, identity)
            XCTAssertNil(try fixture.journal())
            XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
        }
    }

    func testDeletionOffFilesOneSupportTicketForTheSignedInOwnerOnly() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        await fixture.server.configure(404, ["code": "not_found"])
        let refused = try await controller.deleteAccount(expectedIdentity: identity)
        XCTAssertEqual(refused, .refused(.disabled))
        try await controller.requestAccountDeletionSupport(expectedIdentity: identity)
        let tickets = await fixture.server.supportTickets()
        XCTAssertEqual(tickets.count, 1)
        XCTAssertEqual(tickets[0].httpMethod, "POST")
        XCTAssertEqual(tickets[0].value(forHTTPHeaderField: "Authorization")?.hasPrefix("Bearer header."), true)
        let body = try JSONSerialization.jsonObject(with: tickets[0].httpBody!) as! [String: Any]
        XCTAssertEqual(body["type"] as? String, "account_deletion_request")
        XCTAssertEqual((body["context"] as? [String: String])?["source"], "ios_profile")
        XCTAssertNil(body["user_id"], "the server attaches the session's own account")
        let snapshot = await controller.snapshot(); XCTAssertEqual(snapshot, identity)
        XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))

        _ = try await controller.signOut()
        do { try await controller.requestAccountDeletionSupport(expectedIdentity: identity); XCTFail("A retired identity cannot file a ticket") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        let after = await fixture.server.supportTickets(); XCTAssertEqual(after.count, 1)
    }

    func testIncompleteHonorsRetryAfterAndMalformedDoneCannotIssueReceipt() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        await fixture.server.configure(503, ["code": "account_deletion_incomplete"], retry: "5")
        let result = try await controller.deleteAccount(expectedIdentity: identity)
        guard case .uncertain(_, let retry, _, _) = result else { return XCTFail("Incomplete") }
        XCTAssertNotNil(retry)
        do { _ = try await controller.resumePendingAccountDeletion(); XCTFail("Retry too soon") }
        catch { XCTAssertEqual(error as? SessionFailure, .busy) }
        let commands = await fixture.server.captured(); XCTAssertEqual(commands.count, 1)
        let data = try JSONSerialization.data(withJSONObject: ["status": "done", "pending": ["apple"]])
        let response = HTTPURLResponse(url: URL(string: "https://api.example.test")!, statusCode: 200, httpVersion: nil, headerFields: nil)!
        if case .uncertain = AccountDeletionResponse.parse(data, response: response) {} else { XCTFail("Malformed done cannot complete") }
    }

    func testJournalFailureHasNoCommandEffects() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        fixture.storage.failedWriteSuffix = ".deletion"
        do { _ = try await controller.deleteAccount(expectedIdentity: identity); XCTFail("No durable intent") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        let commands = await fixture.server.captured(); XCTAssertTrue(commands.isEmpty)
    }

    func testInterruptedCompletedCleanupReceiptCanBeRecoveredAndAcknowledged() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        fixture.storage.failRemoves = true
        do { _ = try await controller.deleteAccount(expectedIdentity: identity); XCTFail("Credential removal failed") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        XCTAssertEqual(try fixture.journal()?.phase, .completed)
        fixture.storage.failRemoves = false
        let restored = try fixture.controller(); _ = try await restored.restore()
        let status = try await restored.accountDeletionStatus(userID: UUID(uuidString: identity.profile!.id)!)
        guard case .completed(let receipt) = status else { return XCTFail("Durable cleanup obligation") }
        try await restored.acknowledgeConfirmedAccountDeletion(receipt, cleanup: { _ in })
        XCTAssertNil(try fixture.journal())
        let commands = await fixture.server.captured(); XCTAssertEqual(commands.count, 1)
    }

    func testAcceptedAcknowledgementAllowsAnotherAccountWithoutRetiringIt() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let alice = try await fixture.login(controller)
        await fixture.server.configure(202, ["status": "in_progress", "pending": []])
        _ = try await controller.deleteAccount(expectedIdentity: alice)
        let bob = try await controller.login(email: "bob@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha")
        XCTAssertNotEqual(alice.profile?.id, bob.profile?.id)
        let restored = try fixture.controller(); let snapshot = try await restored.restore()
        XCTAssertEqual(snapshot.profile?.id, bob.profile?.id)
        let acknowledgement = try await restored.accountDeletionStatus(userID: UUID(uuidString: alice.profile!.id)!)
        XCTAssertEqual(acknowledgement, .pending(userID: UUID(uuidString: alice.profile!.id)!))
        do { _ = try await controller.deleteAccount(expectedIdentity: alice); XCTFail("Stale owner") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        let commands = await fixture.server.captured(); XCTAssertEqual(commands.count, 1)
    }

    func testRecoveryRefusalCannotTurnLostResponseIntoNoAdmission() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        await fixture.server.configure(503, ["code": "account_deletion_incomplete"])
        _ = try await controller.deleteAccount(expectedIdentity: identity)
        await fixture.server.configure(409, ["code": "apple_reauthorization_required"])
        let result = try await controller.resumePendingAccountDeletion()
        guard case .uncertain(_, _, _, let recovery) = result else { return XCTFail("Earlier uncertainty survives") }
        XCTAssertEqual(recovery, .freshAppleAuthorizationRequired)
        XCTAssertEqual(try fixture.journal()?.phase, .uncertain)
        let snapshot = await controller.snapshot(); XCTAssertEqual(snapshot.phase, .accountDeletionUncertain)
    }

    func testConcurrentDuplicateIsDeniedWhileJournalAlreadyQuarantinesProtectedWork() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        let gate = RequestGate(); await fixture.server.hold(gate)
        let command = Task { try await controller.deleteAccount(expectedIdentity: identity) }
        await gate.waitUntilStarted()
        XCTAssertEqual(try fixture.journal()?.phase, .uncertain)
        let notification = try await controller.requestCredentialRevalidation()
        XCTAssertEqual(notification.phase, .accountDeletionUncertain)
        XCTAssertEqual(notification.revision, identity.revision)
        do { _ = try await controller.deleteAccount(expectedIdentity: identity); XCTFail("Duplicate") } catch {}
        do { _ = try await controller.financialAccounts(expectedIdentity: identity); XCTFail("Protected dispatch") } catch {}
        await gate.release(); _ = try await command.value
        let commands = await fixture.server.captured(); XCTAssertEqual(commands.count, 1)
        let financial = await fixture.server.auth.count("/financial-accounts"); XCTAssertEqual(financial, 0)
    }

    func testExpiredProofUsesSupportWithoutRefreshOrDispatch() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        await fixture.server.configure(503, ["code": "account_deletion_incomplete"])
        _ = try await controller.deleteAccount(expectedIdentity: identity)
        await fixture.server.auth.configure(expired: true)
        let expired = try await fixture.server.auth.sessionData()
        try fixture.storage.store(key: fixture.configuration.storagePrefix + ".session", value: expired)
        let before = await fixture.server.auth.count("/token")
        let restored = try fixture.controller(); _ = try await restored.restore()
        let result = try await restored.resumePendingAccountDeletion()
        guard case .uncertain(_, _, let canRetry, _) = result else { return XCTFail("Expired proof remains uncertain") }
        XCTAssertFalse(canRetry)
        let after = await fixture.server.auth.count("/token"); XCTAssertEqual(after, before)
        let commands = await fixture.server.captured(); XCTAssertEqual(commands.count, 1)
    }


    func testAcceptedAJournalCannotRetireBDuringSDKAdoption() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let alice = try await fixture.login(controller)
        await fixture.server.configure(202, ["status": "in_progress", "pending": []])
        _ = try await controller.deleteAccount(expectedIdentity: alice)
        let gate = RequestGate(); await fixture.server.holdSDKUser(gate)
        let login = Task { try await controller.login(email: "bob@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha") }
        await gate.waitUntilStarted()
        XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"))
        do { _ = try await controller.signOut(); XCTFail("Cannot interrupt B adoption") }
        catch { XCTAssertEqual(error as? SessionFailure, .busy) }
        do { _ = try await controller.retryPendingSignOut(); XCTFail("Cannot retire B issued proof") }
        catch { XCTAssertEqual(error as? SessionFailure, .busy) }
        let adopting = await controller.snapshot()
        let pendingProof = try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending")
        let notification = try await controller.requestCredentialRevalidation()
        XCTAssertEqual(notification.phase, .signOutPending, "Notification must be admitted during adoption")
        XCTAssertEqual(notification.revision, adopting.revision, "A's deletion acknowledgement must not retire B's epoch")
        XCTAssertEqual(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"), pendingProof)
        await gate.release(); let bob = try await login.value
        XCTAssertNotEqual(bob.profile?.id, alice.profile?.id)
        let snapshot = await controller.snapshot(); XCTAssertEqual(snapshot, bob)
    }


    func testAppleNotificationDuringRefusedDeletionDoesNotRestoreStaleAuthenticatedAccess() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let identity = try await controller.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce())).session
        XCTAssertEqual(identity.phase, .authenticated)
        await fixture.server.configure(409, ["code": "apple_reauthorization_required"])
        let gate = RequestGate(); await fixture.server.hold(gate)
        let command = Task { try await controller.deleteAccount(expectedIdentity: identity) }
        await gate.waitUntilStarted()
        let notification = try await controller.requestCredentialRevalidation()
        XCTAssertEqual(notification.phase, .accountDeletionUncertain)
        await gate.release(); let result = try await command.value
        XCTAssertEqual(result, .refused(.freshAppleAuthorizationRequired))
        let snapshot = await controller.snapshot()
        XCTAssertEqual(snapshot.phase, .credentialValidationRequired)
        XCTAssertEqual(snapshot.revision, identity.revision)
        XCTAssertNil(try fixture.journal())
        XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
        do { _ = try await controller.financialAccounts(expectedIdentity: identity); XCTFail("Notification requires fresh Apple validation") } catch {}
        let reads = await fixture.server.auth.count("/financial-accounts"); XCTAssertEqual(reads, 0)
    }


    private func completedReceipt(_ fixture: DeletionFixture, _ controller: SessionController) async throws -> ConfirmedAccountDeletion {
        let identity = try await fixture.login(controller)
        guard case .completed(let receipt) = try await controller.deleteAccount(expectedIdentity: identity) else {
            throw DeletionCleanupTestFailure.expectedCompletion
        }
        return receipt
    }

    func testStaleCompletedCleanupHasNoFilesystemEffectsWhileBOwnsSession() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let receipt = try await completedReceipt(fixture, controller)
        let files = try DeletionCleanupFiles(); defer { try? files.removeAll() }
        try files.create(receipt.userID)
        let bob = try await controller.login(email: "bob@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha")
        let bobID = try XCTUnwrap(UUID(uuidString: bob.profile!.id)); try files.create(bobID)
        do {
            try await controller.acknowledgeConfirmedAccountDeletion(receipt) { try files.remove($0) }
            XCTFail("A's stale receipt must not authorize filesystem cleanup")
        } catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        XCTAssertTrue(files.contains(receipt.userID)); XCTAssertTrue(files.contains(bobID))
        XCTAssertEqual(try fixture.journal()?.phase, .completed)
        let current = await controller.snapshot(); XCTAssertEqual(current, bob)
    }

    func testCompletedCleanupUsesValidatedOwnerAndMissingDirectoryIsIdempotent() async throws {
        for exists in [true, false] {
            let fixture = DeletionFixture(); let controller = try fixture.controller()
            let receipt = try await completedReceipt(fixture, controller)
            let files = try DeletionCleanupFiles(); defer { try? files.removeAll() }
            if exists { try files.create(receipt.userID) }
            let unrelated = UUID(); try files.create(unrelated)
            try await controller.acknowledgeConfirmedAccountDeletion(receipt) { try files.remove($0) }
            XCTAssertFalse(files.contains(receipt.userID)); XCTAssertTrue(files.contains(unrelated))
            XCTAssertNil(try fixture.journal())
            let requests = await fixture.server.captured(); XCTAssertEqual(requests.count, 1)
        }
    }

    func testCleanupCallbackFailureRetainsJournalAndRelaunchRetriesCleanupOnly() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let receipt = try await completedReceipt(fixture, controller)
        let files = try DeletionCleanupFiles(); defer { try? files.removeAll() }
        try files.create(receipt.userID)
        do {
            try await controller.acknowledgeConfirmedAccountDeletion(receipt) { _ in throw DeletionCleanupTestFailure.callbackFailed }
            XCTFail("Cleanup did not succeed")
        } catch { XCTAssertEqual(error as? DeletionCleanupTestFailure, .callbackFailed) }
        XCTAssertTrue(files.contains(receipt.userID)); XCTAssertEqual(try fixture.journal()?.phase, .completed)
        let restored = try fixture.controller(); _ = try await restored.restore()
        let status = try await restored.accountDeletionStatus(userID: receipt.userID)
        guard case .completed(let recovered) = status else { return XCTFail("Existing journal owns retry") }
        try await restored.acknowledgeConfirmedAccountDeletion(recovered) { try files.remove($0) }
        XCTAssertFalse(files.contains(receipt.userID)); XCTAssertNil(try fixture.journal())
        let requests = await fixture.server.captured(); XCTAssertEqual(requests.count, 1)
    }

    func testAcknowledgementStorageFailureAfterCleanupRetainsIdempotentRetryObligation() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let receipt = try await completedReceipt(fixture, controller)
        let files = try DeletionCleanupFiles(); defer { try? files.removeAll() }
        try files.create(receipt.userID); fixture.storage.failRemoves = true
        do {
            try await controller.acknowledgeConfirmedAccountDeletion(receipt) { try files.remove($0) }
            XCTFail("Journal removal must fail")
        } catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        XCTAssertFalse(files.contains(receipt.userID)); XCTAssertEqual(try fixture.journal()?.phase, .completed)
        fixture.storage.failRemoves = false
        try await controller.acknowledgeConfirmedAccountDeletion(receipt) { try files.remove($0) }
        XCTAssertNil(try fixture.journal())
        let requests = await fixture.server.captured(); XCTAssertEqual(requests.count, 1)
    }

    func testCleanupCannotInterruptBAdoptionBeforeSDKProofIsStored() async throws {
        let fixture = DeletionFixture(); let controller = try fixture.controller()
        let receipt = try await completedReceipt(fixture, controller)
        let files = try DeletionCleanupFiles(); defer { try? files.removeAll() }
        try files.create(receipt.userID)
        let gate = RequestGate(); await fixture.server.holdSDKUser(gate)
        let login = Task { try await controller.login(email: "bob@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha") }
        await gate.waitUntilStarted()
        let pending = try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending")
        do {
            try await controller.acknowledgeConfirmedAccountDeletion(receipt) { try files.remove($0) }
            XCTFail("B adoption already owns the actor mutation")
        } catch { XCTAssertEqual(error as? SessionFailure, .busy) }
        XCTAssertTrue(files.contains(receipt.userID))
        XCTAssertEqual(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"), pending)
        await gate.release(); _ = try await login.value
    }

    func testPendingUncertaintyAndOrdinarySignOutCannotAuthorizeCleanup() async throws {
        for status in [202, 503, 0] {
            let fixture = DeletionFixture(); let controller = try fixture.controller()
            let identity = try await fixture.login(controller); let userID = try XCTUnwrap(UUID(uuidString: identity.profile!.id))
            let files = try DeletionCleanupFiles(); defer { try? files.removeAll() }
            try files.create(userID)
            let receipt: ConfirmedAccountDeletion
            if status == 0 {
                _ = try await controller.signOut()
                receipt = .init(userID: userID, initiatingRevision: identity.revision, commandID: UUID())
            } else {
                if status == 202 {
                    await fixture.server.configure(status, ["status": "in_progress", "pending": []])
                } else {
                    await fixture.server.configure(status, ["code": "account_deletion_incomplete"])
                }
                _ = try await controller.deleteAccount(expectedIdentity: identity)
                let journal = try XCTUnwrap(fixture.journal())
                receipt = .init(userID: journal.userID, initiatingRevision: journal.initiatingRevision, commandID: journal.id)
            }
            let before = try fixture.journal()
            do {
                try await controller.acknowledgeConfirmedAccountDeletion(receipt) { try files.remove($0) }
                XCTFail("Only a completed journal authorizes cleanup")
            } catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
            XCTAssertTrue(files.contains(userID)); XCTAssertEqual(try fixture.journal(), before)
        }
    }

}
