import Foundation
import XCTest
@testable import ArgusSession

/// Copy only into the exact #875 baseline test target for independent gap proof.
/// This intentionally uses that historical callback-free API; it is not a current caller.
final class BaselineDeletionCleanupGapTests: XCTestCase {
    func testExternalCleanupRemovesAWhileBOwnsSessionBeforeAcknowledgementRejects() async throws {
        let server = AuthServer()
        let storage = MemoryStore()
        let configuration = try SessionConfiguration(argusAPIURL: URL(string: "https://api.example.test")!,
            supabaseURL: URL(string: "https://auth.example.test")!, publicAnonKey: "sb_publishable_test", keychainService: UUID().uuidString)
        let controller = try SessionController(configuration: configuration, storage: storage, fetch: { request in
            guard request.url!.path.hasSuffix("/account/delete") else { return try await server.send(request) }
            let data = try JSONSerialization.data(withJSONObject: ["status": "done", "pending": []])
            return (data, HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!)
        })
        let alice = try await controller.login(email: "alice@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha")
        guard case .completed(let receipt) = try await controller.deleteAccount(expectedIdentity: alice) else {
            return XCTFail("Synthetic completed deletion required")
        }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("argus-baseline-gap-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let aliceDirectory = root.appendingPathComponent(receipt.userID.uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: aliceDirectory, withIntermediateDirectories: true)
        try Data("synthetic A draft".utf8).write(to: aliceDirectory.appendingPathComponent("draft.txt"))
        let bob = try await controller.login(email: "bob@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha")
        let bobDirectory = root.appendingPathComponent(bob.profile!.id, isDirectory: true)
        try FileManager.default.createDirectory(at: bobDirectory, withIntermediateDirectories: true)
        try Data("synthetic B draft".utf8).write(to: bobDirectory.appendingPathComponent("draft.txt"))

        // The historical caller performs the effect before the actor can reject ownership.
        try FileManager.default.removeItem(at: aliceDirectory)
        do {
            try await controller.acknowledgeConfirmedAccountDeletion(receipt)
            XCTFail("B owns the session; stale A acknowledgement must reject")
        } catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
        XCTAssertFalse(FileManager.default.fileExists(atPath: aliceDirectory.path), "The rejection occurred after A's files were already removed")
        XCTAssertTrue(FileManager.default.fileExists(atPath: bobDirectory.appendingPathComponent("draft.txt").path))
        let current = await controller.snapshot(); XCTAssertEqual(current, bob)
    }
}
