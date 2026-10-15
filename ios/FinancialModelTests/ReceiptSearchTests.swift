import Foundation
import XCTest
import ArgusSession
@testable import FinancialModels

@MainActor
final class ReceiptSearchTests: XCTestCase {
    private func document(_ id: String, _ name: String, status: String = "review_ready") -> SavedDocument {
        SavedDocument(connectionID: id, filename: name, mediaType: "image/jpeg", sizeBytes: 10, sourceAvailable: true,
                      status: status, createdAt: "2026-10-12T15:00:00Z", updatedAt: "2026-10-12T15:00:00Z")
    }

    private func reading(merchant: String, total: String, on day: String) -> DocumentReceipt {
        try! JSONDecoder().decode(DocumentReceipt.self, from: JSONSerialization.data(withJSONObject: [
            "merchant": merchant, "occurred_on": day, "currency": "DOP", "total": total, "subtotal": NSNull(), "tax": NSNull(),
            "service": NSNull(), "tip": NSNull(), "suggested_category": NSNull(),
            "items": [["id": "1", "description": "Plátanos", "quantity": "1", "unit_price": total, "total": total]]]))
    }

    func testAReadReceiptIsFoundByMerchantDateAmountAndItemWithoutCaseOrAccents() {
        let docs = [document("a", "IMG_0001.jpg"), document("b", "Factura luz.pdf", status: "saved")]
        let readings = ["a": reading(merchant: "Supermercado La Sirena", total: "1250.50", on: "2026-10-10")]
        XCTAssertEqual(ReceiptSearch.matches(docs, readings: readings, query: "sirena").map(\.id), ["a"])
        XCTAssertEqual(ReceiptSearch.matches(docs, readings: readings, query: "2026-10-10").map(\.id), ["a"])
        XCTAssertEqual(ReceiptSearch.matches(docs, readings: readings, query: "1,250.50").map(\.id), ["a"], "grouped amount")
        XCTAssertEqual(ReceiptSearch.matches(docs, readings: readings, query: "1250.50").map(\.id), ["a"])
        XCTAssertEqual(ReceiptSearch.matches(docs, readings: readings, query: "platanos").map(\.id), ["a"], "items, accents folded")
        XCTAssertEqual(ReceiptSearch.matches(docs, readings: readings, query: "sirena dop").map(\.id), ["a"], "every word must match")
        XCTAssertTrue(ReceiptSearch.matches(docs, readings: readings, query: "sirena usd").isEmpty)
    }

    func testAnUnreadReceiptIsFoundByItsFileNameAndAnEmptyQueryFindsNothing() {
        let docs = [document("b", "Factura luz.pdf", status: "saved")]
        XCTAssertEqual(ReceiptSearch.matches(docs, readings: [:], query: "FACTURA").map(\.id), ["b"])
        XCTAssertTrue(ReceiptSearch.matches(docs, readings: [:], query: "  ").isEmpty)
    }

    func testReadingsLoadOncePerVersionAndOnlyForReadReceipts() async {
        let transport = ScriptedTransport(listed: [document("a", "IMG.jpg"), document("b", "Luz.pdf", status: "saved")])
        let model = SavedReceiptsModel(transport: transport, currentSession: { SessionSnapshot(phase: .authenticated, profile: nil, revision: 1) })
        model.bind(SessionSnapshot(phase: .authenticated, profile: nil, revision: 1))
        let calls = Counter()
        let sirena = reading(merchant: "La Sirena", total: "250.50", on: "2026-10-10")
        model.reading = { id, _ in await calls.add(id); return sirena }
        await model.load()
        await model.loadReadings()
        await model.loadReadings()
        let asked = await calls.ids
        XCTAssertEqual(asked, ["a"], "only the read receipt, once")
        XCTAssertEqual(model.matching("sirena").map(\.id), ["a"])
    }
}

actor Counter {
    private(set) var ids: [String] = []
    func add(_ id: String) { ids.append(id) }
}
