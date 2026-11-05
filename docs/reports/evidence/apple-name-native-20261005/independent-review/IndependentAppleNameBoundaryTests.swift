import XCTest
@testable import ArgusSession
final class IndependentAppleNameBoundaryTests: XCTestCase, @unchecked Sendable {
 func testCaptureOutageStillSavesCanonicalNameAndNeverReplaysCode() async throws {
  let fixture = try SessionFixture(), client = try fixture.controller()
  await fixture.server.configureAppleName()
  await fixture.server.configureCapture(status: 503, code: "apple_sign_in_unavailable")
  let authorization = try client.prepareAppleName(displayName: "María 王", subject: "canonical-apple-subject")
  let outcome = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()), appleAuthorizationCode: "one-time-code", appleNameAuthorization: authorization)
  XCTAssertEqual(outcome.session.phase, .authenticated)
  XCTAssertEqual(outcome.session.profile?.displayName, "María 王")
  XCTAssertEqual(outcome.appleCapture, .failed(.rejected(status: 503, code: "apple_sign_in_unavailable")))
  XCTAssertEqual(outcome.appleName, .saved)
  _ = try await fixture.controller().restore()
  let requests = await fixture.server.captured()
  XCTAssertEqual(requests.filter { $0.url?.path.hasSuffix("/apple-name") == true }.count, 1)
  XCTAssertEqual(requests.filter { $0.url?.path.hasSuffix("/authorization-code") == true }.count, 1)
 }
 func testAccountSwitchRefusesStaleNameRetryAndDoesNotSeedNewOwner() async throws {
  let fixture = try SessionFixture(), client = try fixture.controller()
  await fixture.server.configureAppleName(statuses: [503])
  let authorization = try client.prepareAppleName(displayName: "Alice only", subject: "canonical-apple-subject")
  let alice = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()), appleAuthorizationCode: "one-time-code", appleNameAuthorization: authorization)
  _ = try await client.signOut()
  let bob = try await fixture.login(client, email: "bob@example.test")
  XCTAssertEqual(bob.profile?.id, fixture.server.bob.uuidString)
  XCTAssertNil(bob.profile?.displayName)
  let before = await fixture.server.captured().count
  do { _ = try await client.retryAppleNameInitialization(expectedIdentity: alice.session); XCTFail("Stale account retry must fail") }
  catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
  let after = await fixture.server.captured().count
  XCTAssertEqual(before, after)
  let reopened = try await fixture.controller().restore()
  XCTAssertEqual(reopened.profile?.id, fixture.server.bob.uuidString)
  XCTAssertNil(reopened.profile?.displayName)
  let requests = await fixture.server.captured()
  XCTAssertEqual(requests.filter { $0.url?.path.hasSuffix("/apple-name") == true }.count, 1)
 }
 func testSubsequentGrantWithoutFullNameDoesNotReseedCanonicalName() async throws {
  let fixture = try SessionFixture(), client = try fixture.controller()
  await fixture.server.configureAppleName()
  let first = try client.prepareAppleName(displayName: "María 王", subject: "canonical-apple-subject")
  _ = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()), appleAuthorizationCode: "first-fresh-code", appleNameAuthorization: first)
  _ = try await client.signOut()
  let second = try client.prepareAppleName(displayName: nil, subject: "canonical-apple-subject")
  let outcome = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()), appleAuthorizationCode: "second-fresh-code", appleNameAuthorization: second)
  XCTAssertEqual(outcome.session.profile?.displayName, "María 王")
  XCTAssertNil(outcome.appleName)
  let requests = await fixture.server.captured()
  XCTAssertEqual(requests.filter { $0.url?.path.hasSuffix("/apple-name") == true }.count, 1)
 }

}
