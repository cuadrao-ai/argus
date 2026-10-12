import Foundation
import XCTest
@testable import FinancialModels

@MainActor
final class GuestReceiptStoreTests: XCTestCase {
    private var book: URL!

    override func setUp() async throws {
        book = FileManager.default.temporaryDirectory.appendingPathComponent("guest-receipts-" + UUID().uuidString, isDirectory: true)
    }

    override func tearDown() async throws { try? FileManager.default.removeItem(at: book) }

    func testSavedReceiptsLiveInsideTheBookAndSurviveReopening() throws {
        let store = GuestReceiptStore(bookDirectory: book)
        let saved = try store.save([(Data([1, 2]), "Ticket.jpg", false), (Data("%PDF".utf8), "Factura.pdf", true)])
        XCTAssertEqual(saved.count, 2)
        XCTAssertEqual(store.receipts.map(\.name), ["Factura.pdf", "Ticket.jpg"], "newest first")
        XCTAssertTrue(store.directory.path.hasPrefix(book.path), "deleting the book deletes its receipts")
        XCTAssertEqual(store.data(saved[1]), Data("%PDF".utf8))
        let reopened = GuestReceiptStore(bookDirectory: book)
        XCTAssertEqual(reopened.receipts, store.receipts)
    }

    func testAMovementHoldsOneReceiptAndRemovingKeepsTheFile() throws {
        let store = GuestReceiptStore(bookDirectory: book)
        let saved = try store.save([(Data([1]), "a.jpg", false), (Data([2]), "b.jpg", false)])
        let movement = UUID()
        try store.attach(saved[0].id, to: movement)
        XCTAssertEqual(store.receipt(for: movement)?.id, saved[0].id)
        try store.attach(saved[1].id, to: movement)
        XCTAssertEqual(store.receipt(for: movement)?.id, saved[1].id, "the newer choice replaces the first")
        XCTAssertNil(store.receipts.first { $0.id == saved[0].id }?.movementID, "the first stays saved, unattached")
        try store.attach(saved[1].id, to: nil)
        XCTAssertNil(store.receipt(for: movement))
        XCTAssertNotNil(store.data(saved[1]), "removing from a movement keeps the file")
    }

    func testUnattachedIncludesReceiptsWhoseMovementWasDeleted() throws {
        let store = GuestReceiptStore(bookDirectory: book)
        let saved = try store.save([(Data([1]), "a.jpg", false), (Data([2]), "b.jpg", false), (Data([3]), "c.jpg", false)])
        let live = UUID(), gone = UUID()
        try store.attach(saved[0].id, to: live)
        try store.attach(saved[1].id, to: gone)
        XCTAssertEqual(Set(store.unattached(liveMovements: [live]).map(\.id)), [saved[1].id, saved[2].id])
    }

    func testDeleteRemovesTheFileAndTheEntry() throws {
        let store = GuestReceiptStore(bookDirectory: book)
        let saved = try store.save([(Data([1]), "a.jpg", false)])
        try store.delete(saved[0].id)
        XCTAssertTrue(store.receipts.isEmpty)
        XCTAssertNil(store.data(saved[0]))
        XCTAssertTrue(GuestReceiptStore(bookDirectory: book).receipts.isEmpty)
    }

    func testSearchFindsAReceiptByNameDateOrItsMovement() throws {
        let store = GuestReceiptStore(bookDirectory: book)
        let day = ISO8601DateFormatter().date(from: "2026-10-10T15:00:00Z")!
        let saved = try store.save([(Data([1]), "Ticket Sirena.jpg", false), (Data([2]), "IMG_0002.jpg", false)], now: day)
        let movement = UUID()
        try store.attach(saved[1].id, to: movement)
        let describe: (GuestReceipt) -> String = { $0.movementID == movement ? "Farmacia Carol DOP 1,250.00" : "" }
        XCTAssertEqual(store.matching("SIRENA", describe: describe).map(\.id), [saved[0].id])
        XCTAssertEqual(store.matching("carol 1250", describe: describe).map(\.id), [saved[1].id], "the movement's words and amount")
        XCTAssertEqual(Set(store.matching("2026-10-10", describe: describe).map(\.id)), Set(saved.map(\.id)))
        XCTAssertTrue(store.matching(" ", describe: describe).isEmpty)
    }
}
