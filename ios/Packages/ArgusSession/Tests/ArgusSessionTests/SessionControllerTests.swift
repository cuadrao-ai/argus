import Auth
import XCTest
@testable import ArgusSession

final class SessionControllerTests: XCTestCase, @unchecked Sendable {
    func testRegisteredLoginRestoresCanonicalProfile() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let signedIn = try await fixture.login(client)
        XCTAssertEqual(signedIn.phase, .authenticated)
        XCTAssertEqual(signedIn.profile?.id, fixture.server.alice.uuidString)
        let relaunched = try fixture.controller()
        let restored = try await relaunched.restore()
        XCTAssertEqual(restored.profile, signedIn.profile)
        let requests = await fixture.server.captured()
        XCTAssertTrue(requests.allSatisfy { $0.value(forHTTPHeaderField: "Cookie") == nil })
        XCTAssertTrue(requests.filter { $0.url!.path.hasSuffix("/me") }.allSatisfy { $0.value(forHTTPHeaderField: "Authorization")?.hasPrefix("Bearer ") == true })
    }

    func testPrimaryCurrencyReadsServerTruthAndSurvivesRelaunch() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let identity = try await fixture.login(client)
        XCTAssertEqual(identity.profile?.currency, "DOP")
        let saved = try await client.setPrimaryCurrency("USD", expectedIdentity: identity)
        XCTAssertEqual(saved.profile?.currency, "USD")
        XCTAssertEqual(saved.profile?.currencyOverride, "USD")
        let restored = try await fixture.controller().restore()
        XCTAssertEqual(restored.profile, saved.profile)
        let writes = await fixture.server.captured().filter { $0.httpMethod == "PATCH" }
        XCTAssertEqual(writes.count, 1)
        let body = try XCTUnwrap(writes.first?.httpBody)
        XCTAssertEqual(try JSONSerialization.jsonObject(with: body) as? [String: String], ["currency_override": "USD"])
    }

    func testNamesWriteReadsServerTruthAndClearsPreferredName() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let identity = try await fixture.login(client)
        XCTAssertEqual(identity.profile?.displayName, "Sample")
        XCTAssertNil(identity.profile?.preferredName)
        let saved = try await client.setNames(displayName: "Alexandra Rivera", preferredName: "Alex", expectedIdentity: identity)
        XCTAssertEqual(saved.profile?.displayName, "Alexandra Rivera")
        XCTAssertEqual(saved.profile?.preferredName, "Alex")
        let restored = try await fixture.controller().restore()
        XCTAssertEqual(restored.profile, saved.profile)
        let cleared = try await client.setNames(displayName: "Alexandra Rivera", preferredName: "", expectedIdentity: saved)
        XCTAssertNil(cleared.profile?.preferredName)
        let writes = await fixture.server.captured().filter { $0.httpMethod == "PATCH" }
        let bodies = try writes.map { try JSONSerialization.jsonObject(with: XCTUnwrap($0.httpBody)) as? [String: String] }
        XCTAssertEqual(bodies, [["display_name": "Alexandra Rivera", "preferred_name": "Alex"],
                                ["display_name": "Alexandra Rivera", "preferred_name": ""]])
    }

    func testRefusedNamesWriteLeavesProfileUnchangedAndStaleIdentityHasNoDispatch() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let identity = try await fixture.login(client)
        await fixture.server.configure(meStatuses: [422])
        do { _ = try await client.setNames(displayName: "Sample", preferredName: String(repeating: "a", count: 41), expectedIdentity: identity); XCTFail("Expected rejection") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 422, code: "unauthorized")) }
        let unchanged = await client.snapshot()
        XCTAssertEqual(unchanged.profile, identity.profile)
        _ = try await client.signOut()
        let before = await fixture.server.captured().count
        do { _ = try await client.setNames(displayName: "Other", preferredName: "", expectedIdentity: identity); XCTFail("Expected stale operation") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        let after = await fixture.server.captured().count
        XCTAssertEqual(after, before)
    }

    func testRefusedCurrencyWriteLeavesProfileAndRelaunchUnchanged() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let identity = try await fixture.login(client)
        await fixture.server.configure(meStatuses: [422])
        do { _ = try await client.setPrimaryCurrency("INVALID", expectedIdentity: identity); XCTFail("Expected rejection") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 422, code: "unauthorized")) }
        let unchanged = await client.snapshot()
        XCTAssertEqual(unchanged.profile, identity.profile)
        let restored = try await fixture.controller().restore()
        XCTAssertEqual(restored.profile, identity.profile)
    }

    func testLegacyProfileHasUnknownCurrencyAndSignedOutWriteHasNoDispatch() async throws {
        let legacy = try JSONDecoder().decode(SessionProfile.self, from: Data("{\"id\":\"synthetic\",\"language\":\"en\"}".utf8))
        XCTAssertNil(legacy.currency)
        XCTAssertNil(legacy.currencyOverride)
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let identity = try await fixture.login(client)
        _ = try await client.signOut()
        let before = await fixture.server.captured().count
        do { _ = try await client.setPrimaryCurrency("USD", expectedIdentity: identity); XCTFail("Expected stale operation") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        let after = await fixture.server.captured().count
        XCTAssertEqual(after, before)
    }

    func testSignupWithoutAgeConfirmationDispatchesNormalRequest() async throws {
        let fixture = try SessionFixture()
        let result = try await fixture.controller().signup(email: "new@example.test", password: "synthetic-password",
            captchaToken: "synthetic-captcha", language: "es-419")
        XCTAssertEqual(result, .confirmationRequired)
        let requests = await fixture.server.captured()
        let request = try XCTUnwrap(requests.first)
        XCTAssertEqual(request.url?.path, "/api/v1/auth/signup")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(request.httpBody)) as? [String: String])
        XCTAssertEqual(body, ["email": "new@example.test", "password": "synthetic-password",
                              "captcha_token": "synthetic-captcha", "language": "es-419"])
    }

    func testSignupWithoutSessionRequiresConfirmationWithoutAutomaticLogin() async throws {
        let fixture = try SessionFixture()
        let result = try await fixture.controller().signup(email: "new@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha", language: "es-419")
        XCTAssertEqual(result, .confirmationRequired)
        let requests = await fixture.server.captured()
        XCTAssertEqual(requests.count, 1)
        let body = try XCTUnwrap(requests.first?.httpBody)
        XCTAssertEqual((try JSONSerialization.jsonObject(with: body) as? [String: String])?["language"], "es-419")
    }

    func testOne401RefreshAndRetryBut503RetainsSession() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        await fixture.server.configure(meStatuses: [401, 200])
        let refreshed = try await client.profile()
        XCTAssertEqual(refreshed.phase, .authenticated)
        let refreshCount = await fixture.server.count("/token")
        XCTAssertEqual(refreshCount, 1)
        await fixture.server.configure(meStatuses: [503])
        do { _ = try await client.profile(); XCTFail("Expected retryable server failure") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 503, code: "unauthorized")) }
        let stillSignedIn = await client.snapshot()
        XCTAssertEqual(stillSignedIn.phase, .authenticated)
    }

    func testAStoredSessionTheServerCannotConfirmStaysStoredAndSignedOutDoesNot() async throws {
        let fixture = try SessionFixture()
        let fresh = try fixture.controller()
        let noSession = await fresh.hasStoredSession()
        XCTAssertFalse(noSession)
        _ = try await fixture.login(fresh)
        await fixture.server.configure(meStatuses: [503])
        let relaunched = try fixture.controller()
        do { _ = try await relaunched.restore(); XCTFail("Expected the unavailable server to fail the restore") }
        catch {}
        let phase = await relaunched.snapshot().phase
        let stored = await relaunched.hasStoredSession()
        XCTAssertNotEqual(phase, .authenticated)
        XCTAssertTrue(stored, "the keychain still holds the session, so launch must not show sign-in")
        let signedOut = try fixture.controller()
        _ = try await signedOut.signOut()
        let afterSignOut = await signedOut.hasStoredSession()
        XCTAssertFalse(afterSignOut)
    }

    func testSecond401EndsUsableSession() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        await fixture.server.configure(meStatuses: [401, 401])
        do { _ = try await client.profile(); XCTFail("Expected unauthorized") }
        catch { XCTAssertEqual(error as? SessionFailure, .unauthorized) }
        let result = await client.snapshot()
        XCTAssertNotEqual(result.phase, .authenticated)
        XCTAssertNil(result.profile)
    }

    func testFailedRevokePersistsPendingAndBlocksNewEntryAcrossRelaunch() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        await fixture.server.configure(logoutStatus: 503)
        let pending = try await client.signOut()
        XCTAssertEqual(pending.phase, .signOutPending)
        let relaunched = try fixture.controller()
        let restored = try await relaunched.restore()
        XCTAssertEqual(restored.phase, .signOutPending)
        do { _ = try await fixture.login(relaunched, email: "bob@example.test"); XCTFail("Pending revoke must block entry") }
        catch { XCTAssertEqual(error as? SessionFailure, .pendingSignOut) }
        await fixture.server.configure()
        let cleared = try await relaunched.retryPendingSignOut()
        XCTAssertEqual(cleared.phase, .signedOut)
        let bob = try await fixture.login(relaunched, email: "bob@example.test")
        XCTAssertEqual(bob.profile?.id, fixture.server.bob.uuidString)
    }

    func testSDKSuppressedLogout401DoesNotClaimRevoked() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        await fixture.server.configure(logoutStatus: 401)
        let pending = try await client.signOut()
        XCTAssertEqual(pending.phase, .signOutPending)
        await fixture.server.configure(refreshStatus: 400)
        let cleared = try await client.retryPendingSignOut()
        XCTAssertEqual(cleared.phase, .signedOut)
    }

    func testWriteFailureNeverClaimsAuthenticated() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        fixture.storage.failWrites = true
        do { _ = try await fixture.login(client); XCTFail("Storage must fail closed") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        let snapshot = await client.snapshot()
        XCTAssertNotEqual(snapshot.phase, .authenticated)
    }

    func testProfileMustMatchSDKIdentity() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        await fixture.server.configure(mismatch: true)
        do { _ = try await fixture.login(client); XCTFail("Identity mismatch must not render") }
        catch { XCTAssertEqual(error as? SessionFailure, .invalidResponse) }
        let snapshot = await client.snapshot()
        XCTAssertNil(snapshot.profile)
    }

    func testAnonymousSessionIsPreservedWithoutAnyNetworkOrAccountReplacement() async throws {
        let fixture = try SessionFixture()
        let data = try await fixture.server.sessionData(anonymous: true)
        try fixture.storage.store(key: fixture.configuration.storagePrefix + ".session", value: data)
        let client = try fixture.controller()
        let snapshot = try await client.restore()
        XCTAssertEqual(snapshot.phase, .unsupportedAnonymousSession)
        do { _ = try await fixture.login(client); XCTFail("Guest transfer is unsupported") }
        catch { XCTAssertEqual(error as? SessionFailure, .unsupportedAnonymousTransfer) }
        XCTAssertEqual(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"), data)
        let requests = await fixture.server.captured()
        XCTAssertTrue(requests.isEmpty)
    }

    func testLateProfileCannotReplaceNewAccount() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        let gate = RequestGate()
        await fixture.server.holdMe(gate)
        let old = Task { try await client.profile() }
        await gate.waitUntilStarted()
        _ = try await client.signOut()
        await gate.release()
        do { _ = try await old.value; XCTFail("Old request must be rejected") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        let bob = try await fixture.login(client, email: "bob@example.test")
        XCTAssertEqual(bob.profile?.id, fixture.server.bob.uuidString)
    }
    func testJournalFailureRetainsVisiblePendingStateAndBlocksEntry() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        fixture.storage.failedWriteSuffix = ".pending"
        do { _ = try await fixture.login(client); XCTFail("Expected storage failure") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        let pending = await client.snapshot()
        XCTAssertEqual(pending.phase, .signOutPending)
        do { _ = try await fixture.login(client); XCTFail("Issued session must not be forgotten") }
        catch { XCTAssertEqual(error as? SessionFailure, .pendingSignOut) }
        fixture.storage.failedWriteSuffix = nil
        let signedOut = try await client.retryPendingSignOut()
        XCTAssertEqual(signedOut.phase, .signedOut)
    }

    func testSDKSwallowedWriteFailureNeverReportsSuccessfulAdoption() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        fixture.storage.failedWriteSuffix = ".session"
        do { _ = try await fixture.login(client); XCTFail("Expected SDK persistence failure") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        let pending = await client.snapshot()
        XCTAssertEqual(pending.phase, .signOutPending)
        fixture.storage.failedWriteSuffix = nil
        let signedOut = try await client.retryPendingSignOut()
        XCTAssertEqual(signedOut.phase, .signedOut)
    }

    func testDeleteFailureRemainsPendingUntilLocalCleanupSucceeds() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        fixture.storage.failRemoves = true
        do { _ = try await client.signOut(); XCTFail("Expected Keychain deletion failure") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        let pending = await client.snapshot()
        XCTAssertEqual(pending.phase, .signOutPending)
        fixture.storage.failRemoves = false
        let signedOut = try await client.retryPendingSignOut()
        XCTAssertEqual(signedOut.phase, .signedOut)
    }

    func testConcurrentExpiredRequestsUseOneRefreshAndPersistRotation() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        let key = fixture.configuration.storagePrefix + ".session"
        let initial = try XCTUnwrap(fixture.storage.retrieve(key: key))
        var session = try StoredSession.decode(initial).session
        let originalRefresh = session.refreshToken
        session.expiresAt = Date().timeIntervalSince1970 - 1
        try fixture.storage.store(key: key, value: JSONEncoder().encode(StoredSession(session: session, signInMethod: .email)))
        let results = try await withThrowingTaskGroup(of: SessionSnapshot.self) { group in
            for _ in 0..<8 { group.addTask { try await client.profile() } }
            return try await group.reduce(into: [SessionSnapshot]()) { $0.append($1) }
        }
        XCTAssertTrue(results.allSatisfy { $0.phase == .authenticated })
        let count = await fixture.server.count("/token")
        XCTAssertEqual(count, 1)
        let saved = try StoredSession.decode(XCTUnwrap(fixture.storage.retrieve(key: key))).session
        XCTAssertFalse(saved.refreshToken == originalRefresh)
    }

    func testLateRefreshCannotResurrectSignedOutCredentials() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        await fixture.server.configure(meStatuses: [401])
        let gate = RequestGate()
        await fixture.server.holdRefresh(gate)
        let old = Task { try await client.profile() }
        await gate.waitUntilStarted()
        let signOut = Task { try await client.signOut() }
        for _ in 0..<1000 {
            if await client.snapshot().phase == .signOutPending { break }
            await Task.yield()
        }
        let during = await client.snapshot()
        XCTAssertEqual(during.phase, .signOutPending)
        await gate.release()
        do { _ = try await old.value; XCTFail("Retired refresh must not deliver") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        let result = try await signOut.value
        XCTAssertEqual(result.phase, .signedOut)
        XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
    }

    func testFailedRotationPersistenceEndsUsableSessionAndRetainsRevocation() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        fixture.storage.failedWriteSuffix = ".session"
        await fixture.server.configure(meStatuses: [401])
        do { _ = try await client.profile(); XCTFail("Rotation was not persisted") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        let snapshot = await client.snapshot()
        XCTAssertEqual(snapshot.phase, .signOutPending)
        XCTAssertNil(snapshot.profile)
        fixture.storage.failedWriteSuffix = nil
        let result = try await client.retryPendingSignOut()
        XCTAssertEqual(result.phase, .signedOut)
    }

    func testSignOutWithoutStoredCredentialStillInvalidatesInFlightProfile() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        let gate = RequestGate()
        await fixture.server.holdMe(gate)
        let old = Task { try await client.profile() }
        await gate.waitUntilStarted()
        // The SDK can clear storage on a refused refresh before its error reaches
        // the actor. Sign-out must still invalidate requests in that interval.
        try fixture.storage.remove(key: fixture.configuration.storagePrefix + ".session")
        let signedOut = try await client.signOut()
        XCTAssertEqual(signedOut.phase, .signedOut)
        await gate.release()
        do { _ = try await old.value; XCTFail("Sign-out always ends the account epoch") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        let after = await client.snapshot()
        XCTAssertEqual(after.phase, .signedOut)
    }

    func testSignOutJournalFailureIsVisibleAndInvalidatesOldProfile() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        let gate = RequestGate()
        await fixture.server.holdMe(gate)
        let old = Task { try await client.profile() }
        await gate.waitUntilStarted()
        fixture.storage.failedWriteSuffix = ".pending"
        do { _ = try await client.signOut(); XCTFail("Expected journal storage failure") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        let pending = await client.snapshot()
        XCTAssertEqual(pending.phase, .signOutPending)
        XCTAssertNil(pending.profile)
        await gate.release()
        do { _ = try await old.value; XCTFail("Failed sign-out still invalidates old profile delivery") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        do { _ = try await client.retryPendingSignOut(); XCTFail("Retry must persist the pending journal before removing saved credentials") }
        catch { XCTAssertEqual(error as? SessionFailure, .storageUnavailable) }
        XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
        fixture.storage.failedWriteSuffix = nil
        let done = try await client.retryPendingSignOut()
        XCTAssertEqual(done.phase, .signedOut)
    }

    func testRejectedRefreshEndsUsableSessionForBothSDKErrorShapes() async throws {
        for triggeredByExpiry in [false, true] {
            for code in ["refresh_token_not_found", "invalid_refresh_token"] {
                let fixture = try SessionFixture()
                let client = try fixture.controller()
                _ = try await fixture.login(client)
                if triggeredByExpiry {
                    let key = fixture.configuration.storagePrefix + ".session"
                    var session = try StoredSession.decode(XCTUnwrap(fixture.storage.retrieve(key: key))).session
                    session.expiresAt = Date().timeIntervalSince1970 - 1
                    try fixture.storage.store(key: key, value: JSONEncoder().encode(StoredSession(session: session, signInMethod: .email)))
                }
                await fixture.server.configure(meStatuses: triggeredByExpiry ? [] : [401], refreshStatus: 400, refreshErrorCode: code)
                do { _ = try await client.profile(); XCTFail("Rejected refresh must end usable auth") }
                catch { XCTAssertEqual(error as? SessionFailure, .unauthorized) }
                let stopped = await client.snapshot()
                XCTAssertNil(stopped.profile)
                XCTAssertEqual(stopped.phase, code == "refresh_token_not_found" ? .signedOut : .signOutPending)
                if code == "invalid_refresh_token" {
                    // An unrecognized 400 proves refresh refusal, not durable server
                    // revocation. It must not unlock another account prematurely.
                    let retried = try await client.retryPendingSignOut()
                    XCTAssertEqual(retried.phase, .signOutPending)
                }
            }
        }
    }

    func testTransientRefreshFailureKeepsSessionRetryable() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        await fixture.server.configure(meStatuses: [401], refreshStatus: 503)
        do { _ = try await client.profile(); XCTFail("Expected retryable refresh failure") }
        catch { XCTAssertEqual(error as? SessionFailure, .unavailable) }
        let retained = await client.snapshot()
        XCTAssertEqual(retained.phase, .authenticated)
        await fixture.server.configure()
        let recovered = try await client.profile()
        XCTAssertEqual(recovered.phase, .authenticated)
    }

}
