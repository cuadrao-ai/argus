import Auth
import Foundation
import XCTest
@testable import ArgusSession

final class AppleNameInitializationTests: XCTestCase, @unchecked Sendable {
    private let subject = "canonical-apple-subject"
    private let seedName = "María del Carmen 王"

    private func prepare(_ client: SessionController, name: String? = nil, subject: String? = nil) throws -> AppleNameAuthorization {
        try client.prepareAppleName(displayName: name, subject: subject ?? self.subject)
    }
    private func signIn(_ client: SessionController, authorization: AppleNameAuthorization) async throws -> ProviderSignInOutcome {
        try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()),
                                appleAuthorizationCode: "one-time-code", appleNameAuthorization: authorization)
    }
    private func journal(_ fixture: SessionFixture) throws -> StoredSession? {
        try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session").map(StoredSession.decode)
    }
    private func names(_ fixture: SessionFixture) async -> [URLRequest] {
        await fixture.server.captured().filter { $0.url?.path.hasSuffix("/apple-name") == true }
    }

    func testCallbackIsDurableBeforeProviderGrantAndCanonicalNameIsAwaited() async throws {
        let fixture = try SessionFixture(), gate = RequestGate()
        await fixture.server.configureAppleName()
        await fixture.server.holdIdToken(gate)
        let client = try fixture.controller()
        let authorization = try prepare(client, name: "  " + seedName + "  ")
        let callback = try XCTUnwrap(fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".apple-name"))
        let intent = try JSONDecoder().decode(AppleNameIntent.self, from: callback)
        XCTAssertEqual(intent.displayName, seedName)
        let fields = try XCTUnwrap(JSONSerialization.jsonObject(with: callback) as? [String: Any])
        XCTAssertEqual(Set(fields.keys), Set(["id", "subject", "displayName", "createdAt"]))
        let task = Task { try await self.signIn(client, authorization: authorization) }
        await gate.waitUntilStarted()
        XCTAssertNil(try journal(fixture))
        await gate.release()
        let result = try await task.value
        XCTAssertEqual(result.session.profile?.displayName, seedName)
        XCTAssertEqual(result.appleName, .saved)
        XCTAssertEqual(result.appleCapture, .saved)
        XCTAssertNil(try journal(fixture)?.appleName)
        XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".apple-name"))
        let requests = await names(fixture)
        XCTAssertEqual(requests.count, 1)
        let sent = try JSONSerialization.jsonObject(with: XCTUnwrap(requests.first?.httpBody)) as? [String: String]
        XCTAssertEqual(sent, ["display_name": seedName])
    }

    func testLostGrantResponseKeepsOnlyCallbackIntentForFreshSameSubjectGrant() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller()
        await fixture.server.configureAppleName()
        await fixture.server.configureIdToken(status: 503)
        do { _ = try await signIn(client, authorization: prepare(client, name: seedName)); XCTFail("Expected outage") }
        catch { XCTAssertEqual(error as? SessionFailure, .unavailable) }
        XCTAssertNil(try journal(fixture))
        XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"))
        let relaunched = try fixture.controller()
        let restored = try await relaunched.restore()
        XCTAssertEqual(restored.phase, .signedOut)
        let before = await names(fixture)
        XCTAssertTrue(before.isEmpty)
        await fixture.server.configureIdToken()
        let result = try await signIn(relaunched, authorization: prepare(relaunched))
        XCTAssertEqual(result.session.profile?.displayName, seedName)
    }

    func testLostNameResponseRetriesAfterRelaunchWithoutCodeReplay() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller()
        await fixture.server.configureAppleName(loseResponse: true)
        let result = try await signIn(client, authorization: prepare(client, name: seedName))
        XCTAssertEqual(result.session.phase, .authenticated)
        XCTAssertEqual(result.appleName, .pending(.unavailable))
        XCTAssertEqual(try journal(fixture)?.appleName?.intent.displayName, seedName)
        let restored = try await fixture.controller().restore()
        XCTAssertEqual(restored.profile?.displayName, seedName)
        XCTAssertNil(try journal(fixture)?.appleName)
        let requests = await fixture.server.captured()
        XCTAssertEqual(requests.filter { $0.url?.path.hasSuffix("/apple-name") == true }.count, 2)
        XCTAssertEqual(requests.filter { $0.url?.path.hasSuffix("/authorization-code") == true }.count, 1)
        XCTAssertEqual(requests.filter { $0.url?.query?.contains("grant_type=id_token") == true }.count, 1)
    }

    func testUnavailableNameDoesNotFailSignInAndExplicitRetryUsesStoredIntent() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller()
        await fixture.server.configureAppleName(statuses: [503])
        let result = try await signIn(client, authorization: prepare(client, name: seedName))
        XCTAssertEqual(result.session.phase, .authenticated)
        XCTAssertEqual(result.appleName, .pending(.rejected(status: 503, code: "apple_name_unavailable")))
        let recovered = try await client.retryAppleNameInitialization(expectedIdentity: result.session)
        XCTAssertEqual(recovered.profile?.displayName, seedName)
        XCTAssertNil(try journal(fixture)?.appleName)
    }

    func testExistingNameAndExplicitClearAreCanonicalNoOps() async throws {
        for chosen in [Optional("User chosen name"), nil] {
            let fixture = try SessionFixture(), client = try fixture.controller()
            await fixture.server.configureAppleName(displayName: chosen, closed: true)
            let result = try await signIn(client, authorization: prepare(client, name: seedName))
            XCTAssertEqual(result.session.profile?.displayName, chosen)
            XCTAssertEqual(result.appleName, .saved)
            XCTAssertNil(try journal(fixture)?.appleName)
        }
    }

    func testDifferentCallbackAndDifferentCanonicalSubjectCannotReceiveOldName() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller()
        _ = try prepare(client, name: seedName)
        let other = try prepare(client, subject: "another-apple-subject")
        XCTAssertNil(other.intentID)
        await fixture.server.configureAppleName()
        let result = try await signIn(client, authorization: other)
        XCTAssertNil(result.appleName)
        let sent = await names(fixture)
        XCTAssertTrue(sent.isEmpty)

        let mismatch = try SessionFixture(), otherClient = try mismatch.controller()
        await mismatch.server.configureAppleName()
        await mismatch.server.configureApple(subject: "different-server-subject")
        let different = try await signIn(otherClient, authorization: prepare(otherClient, name: seedName))
        XCTAssertNil(different.session.profile?.displayName)
        XCTAssertNil(try journal(mismatch)?.appleName)
        let mismatchRequests = await names(mismatch)
        XCTAssertTrue(mismatchRequests.isEmpty)
    }

    func testSignOutClearsPendingNameAndRejectsOldIdentityRetry() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller()
        await fixture.server.configureAppleName(statuses: [503])
        let result = try await signIn(client, authorization: prepare(client, name: seedName))
        _ = try await client.signOut()
        do { _ = try await client.retryAppleNameInitialization(expectedIdentity: result.session); XCTFail("Expected stale identity") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        XCTAssertNil(try journal(fixture))
        XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".apple-name"))
    }

    func testDeniedAdoptionNeverDispatchesNameAndClearsCallback() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller()
        await fixture.server.configure(meStatuses: [403])
        do { _ = try await signIn(client, authorization: prepare(client, name: seedName)); XCTFail("Expected denial") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 403, code: "unauthorized")) }
        let sent = await names(fixture)
        XCTAssertTrue(sent.isEmpty)
        XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".apple-name"))
    }

    func testRefreshKeepsExactBoundIntentAndUnknownGrantCannotPromoteIt() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller()
        await fixture.server.configureAppleName(statuses: [503])
        _ = try await signIn(client, authorization: prepare(client, name: seedName))
        let before = try XCTUnwrap(journal(fixture)?.appleName)
        let owner = CredentialVault(backing: fixture.storage, prefix: fixture.configuration.storagePrefix)
        let rotated = try await fixture.server.sessionData()
        try owner.sdkWrite(key: "argus.session", value: rotated, epoch: owner.epoch())
        XCTAssertEqual(try owner.pendingAppleName(), before)
        try owner.sdkWrite(key: "argus.session", value: rotated, epoch: owner.epoch(), adoptingMethod: .email, adoptingName: before)
        XCTAssertEqual(try owner.signInMethod(), .apple)
        let empty = CredentialVault(backing: MemoryStore(), prefix: "new")
        XCTAssertThrowsError(try empty.sdkWrite(key: "argus.session", value: rotated, epoch: empty.epoch(), adoptingMethod: .email, adoptingName: before))
    }

    func testExpiredCallbackAndEmptyNameDoNotBecomeCommands() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller()
        let expired = AppleNameIntent(id: UUID(), subject: subject, displayName: seedName,
                                      createdAt: Date().addingTimeInterval(-AppleNameIntent.retention - 1))
        try fixture.storage.store(key: fixture.configuration.storagePrefix + ".apple-name", value: JSONEncoder().encode(expired))
        let authorization = try prepare(client, name: "  \n  ")
        XCTAssertNil(authorization.intentID)
        await fixture.server.configureAppleName()
        _ = try await signIn(client, authorization: authorization)
        let sent = await names(fixture)
        XCTAssertTrue(sent.isEmpty)
    }
    func testNameCommandIsAwaitedAndLateRevalidationCannotAdoptItsResponse() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller(), gate = RequestGate()
        await fixture.server.configureAppleName()
        await fixture.server.holdAppleName(gate)
        let authorization = try prepare(client, name: seedName)
        let task = Task { try await self.signIn(client, authorization: authorization) }
        await gate.waitUntilStarted()
        XCTAssertNotNil(try journal(fixture)?.appleName)
        do { _ = try await client.restore(); XCTFail("Sign-in owns the composite mutation") }
        catch { XCTAssertEqual(error as? SessionFailure, .busy) }
        _ = try await client.requestCredentialRevalidation()
        await gate.release()
        let outcome = try await task.value
        XCTAssertEqual(outcome.session.phase, .credentialValidationRequired)
        XCTAssertNil(outcome.session.profile?.displayName)
        XCTAssertNotNil(try journal(fixture)?.appleName)
        let restored = try await client.restore()
        XCTAssertEqual(restored.profile?.displayName, seedName)
        XCTAssertNil(try journal(fixture)?.appleName)
    }

    func testUncertainAppleValidationRetainsNameWithoutDispatchUntilAuthorized() async throws {
        let fixture = try SessionFixture(), checker = AppleChecker()
        await fixture.server.configureAppleName()
        await checker.configure(.transferred)
        let client = try fixture.controller(appleChecker: checker)
        let outcome = try await signIn(client, authorization: prepare(client, name: seedName))
        XCTAssertEqual(outcome.session.phase, .credentialValidationRequired)
        XCTAssertNotNil(try journal(fixture)?.appleName)
        let before = await names(fixture)
        XCTAssertTrue(before.isEmpty)
        await checker.configure(.authorized)
        let restored = try await fixture.controller(appleChecker: checker).restore()
        XCTAssertEqual(restored.profile?.displayName, seedName)
        let requests = await fixture.server.captured()
        XCTAssertEqual(requests.filter { $0.url?.path.hasSuffix("/authorization-code") == true }.count, 0)
    }

    func testCallbackStorageFailureAndSupersededCallbackNeverStartGrant() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller()
        fixture.storage.failedWriteSuffix = ".apple-name"
        XCTAssertThrowsError(try prepare(client, name: seedName)) { XCTAssertEqual($0 as? SessionFailure, .storageUnavailable) }
        fixture.storage.failedWriteSuffix = nil
        let old = try prepare(client, name: seedName)
        _ = try prepare(client, name: "Second callback")
        do { _ = try await signIn(client, authorization: old); XCTFail("Expected stale callback") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        let requests = await fixture.server.captured()
        XCTAssertTrue(requests.isEmpty)
    }

    func testDurableAcknowledgementFailureNeverReportsNameSaved() async throws {
        let fixture = try SessionFixture(), client = try fixture.controller(), gate = RequestGate()
        await fixture.server.configureAppleName()
        await fixture.server.holdAppleName(gate)
        let authorization = try prepare(client, name: seedName)
        let task = Task { try await self.signIn(client, authorization: authorization) }
        await gate.waitUntilStarted()
        fixture.storage.failedWriteSuffix = ".session"
        await gate.release()
        let outcome = try await task.value
        XCTAssertEqual(outcome.appleName, .pending(.storageUnavailable))
        XCTAssertEqual(outcome.session.phase, .credentialValidationRequired)
        fixture.storage.failedWriteSuffix = nil
        XCTAssertNotNil(try journal(fixture)?.appleName)
        let restored = try await fixture.controller().restore()
        XCTAssertEqual(restored.profile?.displayName, seedName)
        XCTAssertNil(try journal(fixture)?.appleName)
    }

    func testRecoverableAdoptionFailuresPreserveFirstCallbackForFreshGrant() async throws {
        for storageFailure in [false, true] {
            let fixture = try SessionFixture(), client = try fixture.controller()
            await fixture.server.configureAppleName()
            if storageFailure { fixture.storage.failedWriteSuffix = ".session" }
            else { await fixture.server.configure(meStatuses: [503]) }
            do { _ = try await signIn(client, authorization: prepare(client, name: seedName)); XCTFail("Expected incomplete adoption") }
            catch {
                let expected: SessionFailure = storageFailure ? .storageUnavailable : .rejected(status: 503, code: "unauthorized")
                XCTAssertEqual(error as? SessionFailure, expected)
            }
            fixture.storage.failedWriteSuffix = nil
            XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".apple-name"))
            let relaunched = try fixture.controller()
            _ = try await relaunched.restore()
            let result = try await signIn(relaunched, authorization: prepare(relaunched))
            XCTAssertEqual(result.session.profile?.displayName, seedName)
        }
    }

}
