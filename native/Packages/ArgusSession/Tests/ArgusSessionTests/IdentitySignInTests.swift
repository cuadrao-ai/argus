import Auth
import CryptoKit
import Foundation
import XCTest
@testable import ArgusSession

final class IdentitySignInTests: XCTestCase, @unchecked Sendable {
    private func body(_ request: URLRequest) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(request.httpBody)) as? [String: Any])
    }
    private func idTokenRequests(_ fixture: SessionFixture) async -> [URLRequest] {
        await fixture.server.captured().filter { $0.url?.query?.contains("grant_type=id_token") == true }
    }

    func testNonceSendsHashToProviderAndRawToSupabase() {
        let nonce = SignInNonce(raw: "fixed-raw-nonce")
        let expected = SHA256.hash(data: Data("fixed-raw-nonce".utf8)).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(nonce.hashed, expected)
        XCTAssertEqual(nonce.hashed.count, 64)
        let first = SignInNonce(), second = SignInNonce()
        XCTAssertNotEqual(first.raw, second.raw)
        XCTAssertEqual(first.raw.count, 43)
        XCTAssertTrue(first.raw.allSatisfy { $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" })
        XCTAssertNotEqual(first.raw, first.hashed)
    }

    func testAppleIdTokenLandsInTheJournaledConnectedSession() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let nonce = SignInNonce()
        let outcome = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: nonce))
        let snapshot = outcome.session
        XCTAssertEqual(snapshot.phase, .authenticated)
        XCTAssertEqual(snapshot.profile?.id, fixture.server.alice.uuidString)

        let exchanges = await idTokenRequests(fixture)
        let exchange = try XCTUnwrap(exchanges.first)
        XCTAssertEqual(exchange.httpMethod, "POST")
        XCTAssertEqual(exchange.url?.host, "auth.example.test")
        XCTAssertEqual(exchange.value(forHTTPHeaderField: "apikey"), "sb_publishable_test")
        let sent = try body(exchange)
        XCTAssertEqual(sent["provider"] as? String, "apple")
        XCTAssertEqual(sent["id_token"] as? String, AuthServer.aliceIdToken)
        XCTAssertEqual(sent["nonce"] as? String, nonce.raw, "Supabase gets the raw nonce; Apple got the hash")
        XCTAssertNil(sent["access_token"] as? String)

        // Same path as email: the session survives relaunch and /me is the identity.
        let relaunched = try fixture.controller()
        let restored = try await relaunched.restore()
        XCTAssertEqual(restored.profile, snapshot.profile)
        let requests = await fixture.server.captured()
        XCTAssertTrue(requests.allSatisfy { $0.value(forHTTPHeaderField: "Cookie") == nil })
        let pending = try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending")
        XCTAssertNil(pending, "Adoption clears the pending journal only after /me succeeds")
    }

    func testGoogleSendsAccessTokenForAtHash() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let outcome = try await client.signIn(with: .init(provider: .google, idToken: AuthServer.bobIdToken,
                                                           nonce: SignInNonce(), accessToken: "ya29.synthetic"))
        XCTAssertEqual(outcome.session.profile?.id, fixture.server.bob.uuidString)
        let exchanges = await idTokenRequests(fixture)
        let sent = try body(XCTUnwrap(exchanges.first))
        XCTAssertEqual(sent["provider"] as? String, "google")
        XCTAssertEqual(sent["access_token"] as? String, "ya29.synthetic")
    }

    func testRejectedIdTokenStoresNothingAndMapsToBoundedCode() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        await fixture.server.configureIdToken(status: 400, errorCode: "bad_jwt")
        do { _ = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce())); XCTFail("Expected rejection") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 400, code: "bad_jwt")) }
        let snapshot = await client.snapshot()
        XCTAssertEqual(snapshot.phase, .signedOut)
        let meCount = await fixture.server.count("/me")
        XCTAssertEqual(meCount, 0)
        XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".session"))
        XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"))
    }

    func testAuthServerOutageIsUnavailable() async throws {
        let fixture = try SessionFixture()
        await fixture.server.configureIdToken(status: 503, errorCode: "unexpected_failure")
        do { _ = try await fixture.controller().signIn(with: .init(provider: .google, idToken: AuthServer.aliceIdToken, nonce: SignInNonce())); XCTFail("Expected outage") }
        catch { XCTAssertEqual(error as? SessionFailure, .unavailable) }
    }

    func testMalformedTokenNeverLeavesTheDevice() async throws {
        let fixture = try SessionFixture()
        do { _ = try await fixture.controller().signIn(with: .init(provider: .apple, idToken: "not-a-jwt", nonce: SignInNonce())); XCTFail("Expected local refusal") }
        catch { XCTAssertEqual(error as? SessionFailure, .invalidResponse) }
        let requests = await fixture.server.captured()
        XCTAssertTrue(requests.isEmpty)
    }

    func testArgusRefusalRevokesTheIssuedSession() async throws {
        // The allowlist is enforced at /me. A refused provider account is signed out at
        // Supabase right away instead of parking on the pending sign-out screen.
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        await fixture.server.configure(meStatuses: [403])
        do { _ = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce())); XCTFail("Expected refusal") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 403, code: "unauthorized")) }
        let snapshot = await client.snapshot()
        XCTAssertEqual(snapshot.phase, .signedOut)
        let logoutCount = await fixture.server.count("/logout")
        XCTAssertEqual(logoutCount, 1)
        XCTAssertNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"))
    }

    func testFailedRevokeAfterRefusalKeepsThePendingJournal() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        await fixture.server.configure(meStatuses: [403], logoutStatus: 503)
        do { _ = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce())); XCTFail("Expected refusal") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 403, code: "unauthorized")) }
        let snapshot = await client.snapshot()
        XCTAssertEqual(snapshot.phase, .signOutPending)
        XCTAssertNotNil(try fixture.storage.retrieve(key: fixture.configuration.storagePrefix + ".pending"))
    }

    func testAnonymousIdTokenSessionIsRefused() async throws {
        let fixture = try SessionFixture()
        await fixture.server.configureIdToken(anonymous: true)
        do { _ = try await fixture.controller().signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce())); XCTFail("Expected refusal") }
        catch { XCTAssertEqual(error as? SessionFailure, .unsupportedAnonymousTransfer) }
        let meCount = await fixture.server.count("/me")
        XCTAssertEqual(meCount, 0)
    }

    func testProviderSignInWhileSignedInIsRefused() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        do { _ = try await client.signIn(with: .init(provider: .google, idToken: AuthServer.bobIdToken, nonce: SignInNonce())); XCTFail("Expected refusal") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 409, code: "already_authenticated")) }
        let exchanges = await idTokenRequests(fixture)
        XCTAssertTrue(exchanges.isEmpty)
    }

    func testAppleCodeCaptureUsesTheSessionBearer() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let outcome = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()))
        let snapshot = outcome.session
        try await client.captureAppleAuthorizationCode("c0de.synthetic", expectedIdentity: snapshot)
        let captured = await fixture.server.captured()
        let capture = try XCTUnwrap(captured.last)
        XCTAssertEqual(capture.url?.absoluteString, "https://api.example.test/api/v1/auth/apple/authorization-code")
        XCTAssertEqual(capture.httpMethod, "POST")
        XCTAssertEqual(capture.value(forHTTPHeaderField: "Authorization")?.hasPrefix("Bearer "), true)
        XCTAssertEqual(try body(capture) as? [String: String], ["authorization_code": "c0de.synthetic"])

        await fixture.server.configureCapture(status: 404)
        do { try await client.captureAppleAuthorizationCode("c0de.synthetic", expectedIdentity: snapshot); XCTFail("Expected off") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 404, code: nil)) }
        let still = await client.snapshot()
        XCTAssertEqual(still.phase, .authenticated, "A capture failure never ends the session")
    }

    func testAppleCodeCaptureRefusesStaleIdentity() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let outcome = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()))
        let snapshot = outcome.session
        _ = try await client.signOut()
        do { try await client.captureAppleAuthorizationCode("c0de.synthetic", expectedIdentity: snapshot); XCTFail("Expected stale") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
    }
    func testCapturePreservesSafeServerFailureAndBoundsCode() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        let snapshot = try await fixture.login(client)
        await fixture.server.configureCapture(status: 503, code: "apple_sign_in_unavailable")
        do { try await client.captureAppleAuthorizationCode("fresh-code", expectedIdentity: snapshot); XCTFail("Expected unavailable") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 503, code: "apple_sign_in_unavailable")) }
        for code in ["", String(repeating: "a", count: 513), "á"] {
            do { try await client.captureAppleAuthorizationCode(code, expectedIdentity: snapshot); XCTFail("Expected local bounds refusal") }
            catch { XCTAssertEqual(error as? SessionFailure, .invalidResponse) }
        }
        let count = await fixture.server.count("/authorization-code")
        XCTAssertEqual(count, 1)
    }

    func testProviderSignInAwaitsOneCaptureAndKeepsSessionOnCaptureFailure() async throws {
        for (status, code) in [(404, Optional<String>.none), (409, "apple_identity_mismatch"), (503, "apple_sign_in_unavailable")] {
            let fixture = try SessionFixture()
            let client = try fixture.controller()
            let gate = RequestGate()
            await fixture.server.configureCapture(status: status, code: code)
            await fixture.server.holdCapture(gate)
            let signIn = Task { try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()), appleAuthorizationCode: "one-time-code") }
            await gate.waitUntilStarted()
            do { _ = try await client.restore(); XCTFail("Composite sign-in must still own mutation") }
            catch { XCTAssertEqual(error as? SessionFailure, .busy) }
            await gate.release()
            let result = try await signIn.value
            XCTAssertEqual(result.session.phase, .authenticated)
            XCTAssertEqual(result.appleCapture, .failed(.rejected(status: status, code: code)))
            let requests = await fixture.server.captured()
            XCTAssertEqual(requests.filter { $0.url?.path.hasSuffix("/authorization-code") == true }.count, 1)
            XCTAssertFalse(requests.contains { $0.url?.path.hasSuffix("/logout") == true })
        }
    }

    func testCaptureUnauthorizedNeverReplaysConsumedCode() async throws {
        let fixture = try SessionFixture()
        let client = try fixture.controller()
        _ = try await fixture.login(client)
        await fixture.server.configureCapture(status: 401, code: "unauthorized")
        let identity = await client.snapshot()
        do { try await client.captureAppleAuthorizationCode("one-time-code", expectedIdentity: identity); XCTFail("Expected invalid session") }
        catch { XCTAssertEqual(error as? SessionFailure, .unauthorized) }
        let captured = await fixture.server.captured()
        XCTAssertEqual(captured.filter { $0.url?.path.hasSuffix("/authorization-code") == true }.count, 1)
    }

    func testCaptureErrorCodesAreSafeAndAnExpiredCodeNeedsFreshAuthorization() async throws {
        for (status, code, expected) in [
            (400, "apple_authorization_invalid", AppleCaptureOutcome.freshAuthorizationRequired),
            (503, "private detail with spaces", .failed(.unavailable)),
            (503, "", .failed(.unavailable)),
            (204, "", .saved)
        ] {
            let fixture = try SessionFixture()
            await fixture.server.configureCapture(status: status, code: code)
            let result = try await fixture.controller().signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()), appleAuthorizationCode: String(repeating: "a", count: 512))
            XCTAssertEqual(result.appleCapture, expected)
            XCTAssertEqual(result.session.phase, .authenticated)
        }
    }

}
