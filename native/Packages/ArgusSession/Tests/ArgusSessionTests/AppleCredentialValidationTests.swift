import Auth
import Foundation
import XCTest
@testable import ArgusSession

actor AppleChecker: AppleCredentialChecking {
    var answer: AppleCredentialState = .authorized
    var failure = false
    var subjects: [String] = []
    var gate: RequestGate?
    func configure(_ answer: AppleCredentialState = .authorized, failure: Bool = false, gate: RequestGate? = nil) {
        self.answer = answer; self.failure = failure; self.gate = gate
    }
    func state(for subject: String) async throws -> AppleCredentialState {
        subjects.append(subject)
        if let gate { await gate.enter() }
        if failure { throw SessionFailure.unavailable }
        return answer
    }
    func checked() -> [String] { subjects }
}

final class AppleCredentialValidationTests: XCTestCase, @unchecked Sendable {
    private func signIn(_ client: SessionController) async throws -> SessionSnapshot {
        try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()), appleAuthorizationCode: "fresh-code").session
    }

    func testAppleUsesCanonicalSubjectAndRevalidatesOnRelaunch() async throws {
        let fixture = try SessionFixture(), checker = AppleChecker()
        await fixture.server.configureApple(subject: "canonical-subject")
        let client = try fixture.controller(appleChecker: checker)
        let snapshot = try await signIn(client)
        XCTAssertEqual(snapshot.appleIdentity?.subject, "canonical-subject")
        XCTAssertEqual(snapshot.phase, .authenticated)
        let relaunched = try fixture.controller(appleChecker: checker)
        let restored = try await relaunched.restore()
        XCTAssertEqual(restored.phase, .authenticated)
        let subjects = await checker.checked()
        XCTAssertEqual(subjects, ["canonical-subject", "canonical-subject"])
    }

    func testKnownEmailAndGoogleIgnoreAppleLinkAcrossRelaunch() async throws {
        for google in [false, true] {
            let fixture = try SessionFixture(), checker = AppleChecker()
            await fixture.server.configureApple(subject: "canonical-subject")
            await checker.configure(.revoked)
            let client = try fixture.controller(appleChecker: checker)
            if google { _ = try await client.signIn(with: .init(provider: .google, idToken: AuthServer.aliceIdToken, nonce: SignInNonce())) }
            else { _ = try await fixture.login(client) }
            let restored = try await fixture.controller(appleChecker: checker).restore()
            XCTAssertEqual(restored.phase, .authenticated)
            let subjects = await checker.checked()
            XCTAssertTrue(subjects.isEmpty)
        }
    }

    func testUnknownLinkedSessionRequiresExplicitSignIn() async throws {
        let fixture = try SessionFixture(), checker = AppleChecker()
        await fixture.server.configureApple(subject: "canonical-subject")
        let legacy = try await fixture.server.sessionData()
        try fixture.storage.store(key: fixture.configuration.storagePrefix + ".session", value: legacy)
        let client = try fixture.controller(appleChecker: checker)
        let restored = try await client.restore()
        XCTAssertEqual(restored.phase, .reauthenticationRequired)
        do { _ = try await client.financialAccounts(expectedIdentity: restored); XCTFail("Unknown method must block product reads") }
        catch { XCTAssertEqual(error as? SessionFailure, .unauthorized) }
        let subjects = await checker.checked()
        XCTAssertTrue(subjects.isEmpty)
        _ = try await client.signOut()
        let loggedIn = try await fixture.login(client)
        XCTAssertEqual(loggedIn.phase, .authenticated)
    }

    func testUncertainAppleStateKeepsCredentialsAndCanRetry() async throws {
        for transferred in [false, true] {
            let fixture = try SessionFixture(), checker = AppleChecker()
            await fixture.server.configureApple(subject: "canonical-subject")
            await checker.configure(transferred ? .transferred : .authorized, failure: !transferred)
            let client = try fixture.controller(appleChecker: checker)
            let result = try await signIn(client)
            XCTAssertEqual(result.phase, .credentialValidationRequired)
            XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
            XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"))
            let count = await fixture.server.count("/logout")
            XCTAssertEqual(count, 0)
            await checker.configure()
            let relaunched = try fixture.controller(appleChecker: checker)
            let restored = try await relaunched.restore()
            XCTAssertEqual(restored.phase, .authenticated)
        }
    }

    func testRevocationAndNotFoundRetireThroughPendingJournal() async throws {
        for answer in [AppleCredentialState.revoked, .notFound] {
            let fixture = try SessionFixture(), checker = AppleChecker()
            await fixture.server.configureApple(subject: "canonical-subject")
            let client = try fixture.controller(appleChecker: checker)
            let before = try await signIn(client)
            await checker.configure(answer)
            await fixture.server.configure(logoutStatus: 503)
            let stopped = try await client.restore()
            XCTAssertEqual(stopped.phase, .signOutPending)
            XCTAssertGreaterThan(stopped.revision, before.revision)
            XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
            XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"))
            await fixture.server.configure()
            let restored = try await fixture.controller(appleChecker: checker).restore()
            XCTAssertEqual(restored.phase, .signedOut)
        }
    }

    func testValidationBlocksSavedSnapshotAndPublishesPendingBeforeCheckCompletes() async throws {
        let fixture = try SessionFixture(), checker = AppleChecker()
        await fixture.server.configureApple(subject: "canonical-subject")
        let client = try fixture.controller(appleChecker: checker)
        let before = try await signIn(client)
        let gate = RequestGate()
        await checker.configure(gate: gate)
        let restore = Task { try await client.restore() }
        await gate.waitUntilStarted()
        let pending = await client.snapshot()
        XCTAssertEqual(pending.phase, .credentialValidationRequired)
        XCTAssertEqual(pending.revision, before.revision)
        do { _ = try await client.financialAccounts(expectedIdentity: before); XCTFail("Old snapshot bypassed validation") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        await gate.release()
        let restored = try await restore.value
        XCTAssertEqual(restored.phase, .authenticated)
    }
    func testNewGrantForSameAccountReplacesMethodAndCanonicalMismatchSkipsChecker() async throws {
        let fixture = try SessionFixture(), checker = AppleChecker()
        await fixture.server.configureApple(subject: "canonical-subject")
        let client = try fixture.controller(appleChecker: checker)
        _ = try await signIn(client)
        _ = try await client.signOut()
        await checker.configure(.revoked)
        let email = try await fixture.login(client)
        XCTAssertEqual(email.phase, .authenticated)
        XCTAssertEqual(try StoredSession.decode(XCTUnwrap(fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))).signInMethod, .email)
        _ = try await client.signOut()
        await fixture.server.configure(mismatch: true)
        do { _ = try await signIn(client); XCTFail("Mismatched canonical owner") }
        catch { XCTAssertEqual(error as? SessionFailure, .invalidResponse) }
        let subjects = await checker.checked()
        XCTAssertEqual(subjects.count, 1)
    }

    func testRevocationStorageFailureRemainsPendingAndCannotSwitchAccountsDuringCheck() async throws {
        let fixture = try SessionFixture(), checker = AppleChecker()
        let client = try fixture.controller(appleChecker: checker)
        _ = try await signIn(client)
        let gate = RequestGate()
        await checker.configure(.revoked, gate: gate)
        let checking = Task { try await client.restore() }
        await gate.waitUntilStarted()
        do { _ = try await client.signOut(); XCTFail("Validation owns mutation") }
        catch { XCTAssertEqual(error as? SessionFailure, .busy) }
        fixture.storage.failedWriteSuffix = ".pending"
        await gate.release()
        do { _ = try await checking.value; XCTFail("Journal write must fail closed") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        let pending = await client.snapshot()
        XCTAssertEqual(pending.phase, .signOutPending)
        fixture.storage.failedWriteSuffix = nil
        _ = try await client.retryPendingSignOut()
        let bob = try await fixture.login(client, email: "bob@example.test")
        XCTAssertEqual(bob.profile?.id, fixture.server.bob.uuidString)
    }

    func testLostMethodSessionWriteHasPendingCredentialsForRelaunch() async throws {
        let fixture = try SessionFixture(), checker = AppleChecker()
        fixture.storage.failedWriteSuffix = ".session"
        let client = try fixture.controller(appleChecker: checker)
        await fixture.server.configure(logoutStatus: 503)
        do { _ = try await signIn(client); XCTFail("Failed durable method/session write") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"))
        fixture.storage.failedWriteSuffix = nil
        await fixture.server.configure()
        let restored = try await fixture.controller(appleChecker: checker).restore()
        XCTAssertEqual(restored.phase, .signedOut)
    }

    func testForegroundUnreadableMethodOrPendingJournalBlocksCachedSDKDispatch() async throws {
        for suffix in [".session", ".pending"] {
            let fixture = try SessionFixture(), checker = AppleChecker()
            let client = try fixture.controller(appleChecker: checker)
            let before = try await signIn(client)
            fixture.storage.failedReadSuffix = suffix
            do { _ = try await client.restore(); XCTFail("Unreadable journal must fail closed") }
            catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
            let pending = await client.snapshot()
            XCTAssertEqual(pending.phase, .credentialValidationRequired)
            do { _ = try await client.financialAccounts(expectedIdentity: before); XCTFail("Cached SDK bypass") }
            catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
            fixture.storage.failedReadSuffix = nil
            let recovered = try await client.restore()
            XCTAssertEqual(recovered.phase, .authenticated)
        }
    }

    func testPendingValidationReportsDiscardedCaptureAndNeverReplaysOnRetry() async throws {
        let fixture = try SessionFixture(), checker = AppleChecker()
        await checker.configure(.transferred)
        let client = try fixture.controller(appleChecker: checker)
        let result = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()), appleAuthorizationCode: "one-time-code")
        XCTAssertEqual(result.session.phase, .credentialValidationRequired)
        XCTAssertEqual(result.appleCapture, .freshAuthorizationRequired)
        await checker.configure()
        _ = try await client.restore()
        let captured = await fixture.server.count("/authorization-code")
        XCTAssertEqual(captured, 0)
    }

    func testPendingRevocationTakesPriorityOverMalformedOrUnreadableOrdinarySession() async throws {
        for unreadable in [false, true] {
            let fixture = try SessionFixture()
            let client = try fixture.controller()
            _ = try await fixture.login(client)
            await fixture.server.configure(logoutStatus: 503)
            _ = try await client.signOut()
            try fixture.storage.store(key: fixture.configuration.storagePrefix + ".session", value: Data("malformed".utf8))
            if unreadable { fixture.storage.failedReadSuffix = ".session" }
            await fixture.server.configure()
            let relaunched = try fixture.controller()
            let admitted = try await relaunched.requestCredentialRevalidation()
            XCTAssertEqual(admitted.phase, .signOutPending)
            let restored = try await relaunched.restore()
            XCTAssertEqual(restored.phase, .signedOut)
            XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"))
        }
    }

    func testNotificationInvalidatesInFlightAppleAnswersBeforeQueuedRestore() async throws {
        for answer in [AppleCredentialState.authorized, .revoked] {
            let fixture = try SessionFixture(), checker = AppleChecker()
            let client = try fixture.controller(appleChecker: checker)
            let before = try await signIn(client)
            let gate = RequestGate()
            await checker.configure(answer, gate: gate)
            let checking = Task { try await client.restore() }
            await gate.waitUntilStarted()
            let admitted = try await client.requestCredentialRevalidation()
            XCTAssertEqual(admitted.phase, .credentialValidationRequired)
            await gate.release()
            let stale = try await checking.value
            XCTAssertEqual(stale.phase, .credentialValidationRequired)
            XCTAssertEqual(stale.revision, before.revision)
            do {
                _ = try await client.financialAccounts(expectedIdentity: before)
                XCTFail("A superseded checker answer reopened protected dispatch")
            } catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
            let reads = await fixture.server.count("/financial-accounts")
            let logouts = await fixture.server.count("/logout")
            XCTAssertEqual(reads, 0)
            XCTAssertEqual(logouts, 0)
            XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
            await checker.configure(answer)
            let fresh = try await client.restore()
            XCTAssertEqual(fresh.phase, answer == .authorized ? .authenticated : .signedOut)
        }
    }

    func testNotificationHoldsAppleAccessButLeavesKnownEmailAndGoogleUsable() async throws {
        for method in [SessionSignInMethod.apple, .email, .google] {
            let fixture = try SessionFixture(), checker = AppleChecker()
            await fixture.server.configureApple(subject: "linked-subject")
            let client = try fixture.controller(appleChecker: checker)
            let before: SessionSnapshot
            switch method {
            case .apple: before = try await signIn(client)
            case .email: before = try await fixture.login(client)
            case .google:
                before = try await client.signIn(with: .init(provider: .google, idToken: AuthServer.aliceIdToken, nonce: SignInNonce())).session
            }
            let admitted = try await client.requestCredentialRevalidation()
            XCTAssertEqual(admitted.phase, method == .apple ? .credentialValidationRequired : .authenticated)
            do {
                _ = try await client.financialAccounts(expectedIdentity: before)
                XCTFail("Synthetic endpoint returns 404")
            } catch {
                XCTAssertEqual(error as? SessionFailure, method == .apple ? .staleOperation : .rejected(status: 404, code: nil))
            }
            let reads = await fixture.server.count("/financial-accounts")
            XCTAssertEqual(reads, method == .apple ? 0 : 1)
        }
    }

    func testNotificationDuringCaptureHoldsSessionWithoutReplayingCode() async throws {
        let fixture = try SessionFixture(), checker = AppleChecker()
        let gate = RequestGate()
        await fixture.server.holdCapture(gate)
        let client = try fixture.controller(appleChecker: checker)
        let signingIn = Task {
            try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()), appleAuthorizationCode: "one-time-code")
        }
        await gate.waitUntilStarted()
        let admitted = try await client.requestCredentialRevalidation()
        XCTAssertEqual(admitted.phase, .credentialValidationRequired)
        await gate.release()
        let outcome = try await signingIn.value
        XCTAssertEqual(outcome.session.phase, .credentialValidationRequired)
        XCTAssertEqual(outcome.appleCapture, .failed(.credentialValidationRequired))
        let restored = try await client.restore()
        XCTAssertEqual(restored.phase, .authenticated)
        let captures = await fixture.server.count("/authorization-code")
        XCTAssertEqual(captures, 1)
    }

    func testNotificationDuringAdoptionKeepsJournalAndRequiresFreshCheck() async throws {
        let fixture = try SessionFixture(), checker = AppleChecker()
        let gate = RequestGate()
        await fixture.server.holdMe(gate)
        let client = try fixture.controller(appleChecker: checker)
        let signingIn = Task { try await self.signIn(client) }
        await gate.waitUntilStarted()
        let admitted = try await client.requestCredentialRevalidation()
        XCTAssertEqual(admitted.phase, .signOutPending)
        XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"))
        await checker.configure(.revoked)
        await gate.release()
        let outcome = try await signingIn.value
        XCTAssertEqual(outcome.phase, .signedOut)
        let captures = await fixture.server.count("/authorization-code")
        XCTAssertEqual(captures, 0)
    }

    func testUnreadableNotificationAdmissionInvalidatesInFlightCheckerAnswer() async throws {
        for suffix in [".session", ".pending"] {
            let fixture = try SessionFixture(), checker = AppleChecker()
            let client = try fixture.controller(appleChecker: checker)
            let before = try await signIn(client)
            let gate = RequestGate()
            await checker.configure(gate: gate)
            let checking = Task { try await client.restore() }
            await gate.waitUntilStarted()
            fixture.storage.failedReadSuffix = suffix
            do {
                _ = try await client.requestCredentialRevalidation()
                XCTFail("Unreadable admission must fail closed")
            } catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
            await gate.release()
            let stale = try await checking.value
            XCTAssertEqual(stale.phase, .credentialValidationRequired)
            do {
                _ = try await client.financialAccounts(expectedIdentity: before)
                XCTFail("Unreadable journal permitted protected access")
            } catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
            fixture.storage.failedReadSuffix = nil
            await checker.configure()
            let restored = try await client.restore()
            XCTAssertEqual(restored.phase, .authenticated)
        }
    }

}
