import Foundation
import XCTest
@testable import ArgusSession
@testable import FinancialModels

/// The movement sheet opened from Home starts on the first money account. These tests pin which account
/// the sheet names, and that Transfer can pay a credit card by becoming a card payment.
@MainActor
final class MovementAccountChoiceTests: XCTestCase {
    func testHeaderNamesTheChosenExpenseAccountNotTheOrigin() async throws {
        let fixture = try MovementFixture(); let editor = try await fixture.editor()
        XCTAssertEqual(editor.headerAccount.id, MovementServer.bank)
        editor.accountId = MovementServer.card
        XCTAssertEqual(editor.headerAccount.id, MovementServer.card)
        XCTAssertEqual(editor.headerAccount.nickname, "BoFa")
    }

    func testHeaderNamesTheChosenTransferSource() async throws {
        let fixture = try MovementFixture(); let editor = try await fixture.editor()
        editor.setKind(.transfer)
        editor.sourceAccountId = MovementServer.cash
        XCTAssertEqual(editor.headerAccount.id, MovementServer.cash)
        XCTAssertEqual(editor.headerAccount.nickname, "Efectivo")
    }

    func testTransferOffersTheCardAndChoosingItBecomesACardPayment() async throws {
        let fixture = try MovementFixture(); let editor = try await fixture.editor()
        editor.setKind(.transfer)
        let date = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-10-10T12:00:00Z"))
        editor.amount = "300.00"; editor.note = "Pago BoFa"; editor.date = date
        XCTAssertEqual(editor.sourceAccountId, MovementServer.bank)
        XCTAssertTrue(editor.destinationChoices.map(\.id).contains(MovementServer.card))
        editor.destinationAccountId = MovementServer.card
        XCTAssertEqual(editor.kind, .cardPayment)
        XCTAssertEqual(editor.amount, "300.00")
        XCTAssertEqual(editor.note, "Pago BoFa")
        XCTAssertEqual(editor.date, date)
        XCTAssertEqual(editor.sourceAccountId, MovementServer.bank)
        XCTAssertEqual(editor.destinationAccountId, MovementServer.card)
        XCTAssertEqual(editor.headerAccount.id, MovementServer.bank)
    }

    func testCardPaymentFromTransferReviewsBankToCard() async throws {
        let fixture = try MovementFixture(); let editor = try await fixture.editor()
        editor.setKind(.transfer)
        editor.amount = "300.00"
        editor.destinationAccountId = MovementServer.card
        await editor.review(locale: Locale(identifier: "en_US"))
        XCTAssertEqual(editor.phase, .review)
        let previews = await fixture.server.previews
        let sent = try XCTUnwrap(previews.last)
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(sent.httpBody)) as? [String: Any])
        XCTAssertEqual(payload["kind"] as? String, "card_payment")
        XCTAssertEqual(payload["source_account_id"] as? String, MovementServer.bank.uuidString)
        XCTAssertEqual(payload["destination_account_id"] as? String, MovementServer.card.uuidString)
        XCTAssertEqual(payload["amount"] as? String, "300.00")
        XCTAssertTrue(payload["account_id"] is NSNull)
    }
}

private struct MovementFixture {
    let server = MovementServer()
    let client: SessionController
    let journal: FinancialWriteJournal
    init() throws {
        let config = try SessionConfiguration(argusAPIURL: URL(string: "https://api.example.test")!, supabaseURL: URL(string: "https://auth.example.test")!,
                                              publicAnonKey: "sb_publishable_test", keychainService: UUID().uuidString)
        let server = self.server, storage = MemoryStore()
        client = try SessionController(configuration: config, storage: storage, fetch: { try await server.send($0) })
        journal = FinancialWriteJournal(storage: storage, prefix: config.storagePrefix)
    }
    /// Opened the way Home opens it: on the first money account, Banco prueba.
    @MainActor func editor() async throws -> FinancialActivityEditor {
        let identity = try await client.login(email: "alice@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha")
        let origin = try JSONDecoder().decode(FinancialAccount.self, from: Data(MovementServer.account(MovementServer.bank, type: "checking", nature: "asset", name: "Banco prueba").utf8))
        let editor = FinancialActivityEditor(origin: origin, controller: client, journal: journal, identity: identity) { _ in }
        await editor.load()
        XCTAssertEqual(editor.kind, .expense)
        return editor
    }
}

private actor MovementServer {
    static let bank = UUID(), card = UUID(), cash = UUID()
    let auth = AuthServer()
    private(set) var previews: [URLRequest] = []

    static func account(_ id: UUID, type: String, nature: String, name: String) -> String {
        #"{"id":"\#(id)","type":"\#(type)","nature":"\#(nature)","currency":"DOP","currency_fraction_digits":2,"nickname":"\#(name)","archived":false,"ownership_share_bps":10000,"version":1,"created_at":"2026-10-01T12:00:00Z","updated_at":"2026-10-01T12:00:00Z","balance":{"state":"known","amount_minor":100000,"amount":"1000.00","as_of":"2026-10-01T12:00:00Z","basis":"opening","activity_since_tracking_minor":0},"opening":null}"#
    }

    func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
        let path = request.url!.path
        guard path.contains("/financial-") else { return try await auth.send(request) }
        let body: String
        if path.hasSuffix("/options") {
            let accounts = [Self.account(Self.bank, type: "checking", nature: "asset", name: "Banco prueba"),
                            Self.account(Self.card, type: "credit_card", nature: "liability", name: "BoFa"),
                            Self.account(Self.cash, type: "cash", nature: "asset", name: "Efectivo")].joined(separator: ",")
            let liquid = #"["cash","checking","savings"]"#
            body = #"{"accounts":[\#(accounts)],"eligibility":{"expense":["cash","checking","savings","credit_card"],"income":\#(liquid),"transfer":\#(liquid),"card_payment":\#(liquid),"refund":["cash","checking","savings","credit_card"]},"destination_eligibility":{"transfer":\#(liquid),"card_payment":["credit_card"]},"categories":["groceries"],"sources":["salary"]}"#
        } else if path.hasSuffix("/preview") {
            previews.append(request)
            let payload = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
            let reviewed = String(data: try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]), encoding: .utf8)!
            body = #"{"ready":true,"expected_versions":{},"affected_accounts":[],"reviewed_request":\#(reviewed),"preview_token":"reviewed"}"#
        } else {
            body = #"{"items":[],"next_cursor":null}"#
        }
        return (Data(body.utf8), HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!)
    }
}
