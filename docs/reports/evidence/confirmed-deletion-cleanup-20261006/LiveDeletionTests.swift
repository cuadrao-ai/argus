import Foundation
import XCTest
@testable import ArgusSession
final class LiveDeletionTests: XCTestCase, @unchecked Sendable {
 func testLocalDeletionCommandRetiresOnlyAAndPreservesB() async throws {
  let fixture = try LocalSessionFixture.load()
  let client = try fixture.controller()
  let alice = try await fixture.login(client, user: 0)
  let refreshBefore = fixture.counter.refreshCount
  let result = try await client.deleteAccount(expectedIdentity: alice)
  let retired = await client.snapshot()
  XCTAssertNil(try fixture.vault.session())
  var receipt: ConfirmedAccountDeletion?
  switch result {
  case .completed(let done):
   receipt = done
   XCTAssertEqual(done.userID.uuidString.lowercased(),fixture.users[0].id.lowercased())
   XCTAssertEqual(done.initiatingRevision,alice.revision)
   XCTAssertEqual(retired.phase,.signedOut)
   print("ACTUAL_DELETION_OUTCOME completed200")
  case .pending(let userID):
   XCTAssertEqual(userID.uuidString.lowercased(),fixture.users[0].id.lowercased())
   XCTAssertEqual(retired.phase,.accountDeletionPending)
   print("ACTUAL_DELETION_OUTCOME accepted202")
  default: XCTFail("Actual local API must resolve own synthetic deletion");return
  }
  XCTAssertEqual(fixture.counter.refreshCount,refreshBefore)
  let bob = try await fixture.login(client,user:1)
  XCTAssertEqual(bob.profile?.id.lowercased(),fixture.users[1].id.lowercased())
  if let receipt {
   let hidden = try await client.accountDeletionStatus(userID:receipt.userID)
   XCTAssertNil(hidden)
   do { try await client.acknowledgeConfirmedAccountDeletion(receipt, cleanup: { _ in });XCTFail("B ownership must deny stale A cleanup acknowledgement") }
   catch { XCTAssertEqual(error as? SessionFailure,.staleOperation) }
  }
  let relaunched = try fixture.controller()
  let restored = try await relaunched.restore()
  XCTAssertEqual(restored.profile?.id,bob.profile?.id)
  let signedOut = try await relaunched.signOut()
  XCTAssertEqual(signedOut.phase,.signedOut)
 }
}
