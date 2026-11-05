import Auth
import XCTest
@testable import ArgusSession
final class CombinedCurrencyAdmissionTests: XCTestCase, @unchecked Sendable {
 func testCurrencyHasZeroDispatchDuringValidationAndUnknownLinkedRestore() async throws {
  for unknown in [false, true] {
   let fixture = try SessionFixture(), checker = AppleChecker()
   await fixture.server.configureApple(subject: "synthetic-canonical-subject")
   let client: SessionController
   let identity: SessionSnapshot
   if unknown {
    let legacy = try await fixture.server.sessionData()
    try fixture.storage.store(key: fixture.configuration.storagePrefix + ".session", value: legacy)
    client = try fixture.controller(appleChecker: checker)
    identity = try await client.restore()
    XCTAssertEqual(identity.phase, .reauthenticationRequired)
   } else {
    client = try fixture.controller(appleChecker: checker)
    identity = try await client.signIn(with: .init(provider: .apple, idToken: AuthServer.aliceIdToken, nonce: SignInNonce()), appleAuthorizationCode: "fresh-code").session
    _ = try await client.requestCredentialRevalidation()
   }
   let before = await fixture.server.captured().count
   do { _ = try await client.setPrimaryCurrency("USD", expectedIdentity: identity); XCTFail("Denied currency write") }
   catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
   let after = await fixture.server.captured().count
   XCTAssertEqual(after, before)
  }
 }
}
