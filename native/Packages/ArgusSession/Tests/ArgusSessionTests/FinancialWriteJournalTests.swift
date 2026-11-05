import Foundation
import XCTest
@testable import ArgusSession

final class FinancialWriteJournalTests: XCTestCase {
    func testRelaunchKeepsExactConfirmedBytesAndKeyUntilExplicitClear() throws {
        let storage = MemoryStore()
        let owner = UUID()
        let identity = snapshot(owner)
        let body = Data(#"{"expected_revision":3,"expected_versions":{"first":7,"second":4},"preview_token":"reviewed","coverage":[{"included":false}]}"#.utf8)
        let write = PendingFinancialConfirmation(ownerId: owner, originAccountId: UUID(), route: "financial-activities",
            path: "/", method: "POST", body: body, key: UUID())
        let firstLaunch = FinancialWriteJournal(storage: storage, prefix: "test")
        try firstLaunch.begin(write, for: identity)

        let reopened = FinancialWriteJournal(storage: storage, prefix: "test")
        XCTAssertEqual(try reopened.pending(for: identity), write)
        XCTAssertEqual(try reopened.pending(for: identity)?.body, body)
        XCTAssertEqual(try reopened.pending(for: identity)?.key, write.key)
        try reopened.begin(write, for: identity)
        try reopened.clear(write, for: identity)
        XCTAssertNil(try reopened.pending(for: identity))
    }

    func testAnotherOwnerCannotReadClearOrReplacePendingConfirmation() throws {
        let storage = MemoryStore()
        let journal = FinancialWriteJournal(storage: storage, prefix: "test")
        let alice = UUID()
        let bob = UUID()
        let original = write(owner: alice)
        try journal.begin(original, for: snapshot(alice))
        XCTAssertNil(try journal.pending(for: snapshot(bob)))
        XCTAssertThrowsError(try journal.clear(original, for: snapshot(bob)))
        XCTAssertThrowsError(try journal.begin(original, for: snapshot(bob)))
        XCTAssertEqual(try journal.pending(for: snapshot(alice)), original)
        XCTAssertThrowsError(try journal.pending(for: .init(phase: .signedOut, profile: nil, revision: 2)))
    }

    func testDifferentSecondWriteCannotReplaceUnknownResult() throws {
        let owner = UUID()
        let journal = FinancialWriteJournal(storage: MemoryStore(), prefix: "test")
        let original = write(owner: owner)
        try journal.begin(original, for: snapshot(owner))
        var changed = write(owner: owner)
        XCTAssertThrowsError(try journal.begin(changed, for: snapshot(owner))) { error in
            XCTAssertEqual(error as? FinancialWriteJournalError, .pendingConfirmation)
        }
        changed = PendingFinancialConfirmation(ownerId: owner, originAccountId: original.originAccountId,
            route: original.route, path: original.path, method: original.method,
            body: Data(#"{"preview_token":"different"}"#.utf8), key: original.key)
        XCTAssertThrowsError(try journal.begin(changed, for: snapshot(owner)))
        XCTAssertEqual(try journal.pending(for: snapshot(owner)), original)
    }

    func testUnavailableStorageFailsBeforeAnyDispatchCanBeAttempted() throws {
        let storage = MemoryStore()
        storage.failWrites = true
        let owner = UUID()
        let journal = FinancialWriteJournal(storage: storage, prefix: "test")
        XCTAssertThrowsError(try journal.begin(write(owner: owner), for: snapshot(owner))) { error in
            XCTAssertEqual(error as? FinancialWriteJournalError, .storageUnavailable)
        }
        XCTAssertNil(try journal.pending(for: snapshot(owner)))
    }

    private func snapshot(_ owner: UUID) -> SessionSnapshot {
        .init(phase: .authenticated,
              profile: .init(id: owner.uuidString, email: nil, displayName: nil, language: nil), revision: 1)
    }

    private func write(owner: UUID) -> PendingFinancialConfirmation {
        .init(ownerId: owner, originAccountId: UUID(), route: "financial-activities", path: "",
              method: "POST", body: Data(#"{"preview_token":"reviewed"}"#.utf8), key: UUID())
    }
}
