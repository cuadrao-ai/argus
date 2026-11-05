import XCTest
@testable import ArgusSession
final class LiveCurrencyTests: XCTestCase, @unchecked Sendable {
 func testLivePrimaryCurrencyWriteReadbackAndRelaunch() async throws {
  let fixture = try LocalSessionFixture.load()
  let client = try fixture.controller()
  do {
   let identity = try await fixture.login(client, user: 0)
   let saved = try await client.setPrimaryCurrency("USD", expectedIdentity: identity)
   XCTAssertEqual(saved.profile?.currency, "USD")
   XCTAssertEqual(saved.profile?.currencyOverride, "USD")
   let read = try await client.profile()
   XCTAssertEqual(read.profile, saved.profile)
   let resumed = try fixture.controller()
   let restored = try await resumed.restore()
   XCTAssertEqual(restored.profile, saved.profile)
   do { _ = try await resumed.setPrimaryCurrency("INVALID", expectedIdentity: restored); XCTFail("Invalid currency must fail") }
   catch { guard case .rejected(status: 422, code: _) = error as? SessionFailure else { throw error } }
   let unchanged = try await resumed.profile()
   XCTAssertEqual(unchanged.profile, saved.profile)
   _ = try await resumed.signOut()
  } catch { _ = try? await client.signOut(); throw error }
 }
}
