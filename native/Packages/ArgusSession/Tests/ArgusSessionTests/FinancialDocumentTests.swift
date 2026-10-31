import Foundation
import XCTest
@testable import ArgusSession

final class FinancialDocumentTests: XCTestCase {
    private func document(_ id: String = "doc-1", created: String = "2026-10-08T12:00:00.123456+00:00") -> [String: Any] {
        ["connection_id": id, "filename": "Ticket.pdf", "media_type": "application/pdf", "sha256": "abc", "size_bytes": 2048,
         "source_available": true, "status": "saved", "consent": false, "version": 1, "created_at": created,
         "updated_at": created, "error_code": NSNull(), "proposal": [String: Any]()]
    }

    func testListDecodesTheServersDraftMetadataAndPaging() throws {
        let raw: [String: Any] = ["items": [document("a"), document("b", created: "2026-10-08T12:00:00Z")], "next_offset": 2]
        let page = try JSONDecoder().decode(SavedDocumentPage.self, from: JSONSerialization.data(withJSONObject: raw))
        XCTAssertEqual(page.items.map(\.id), ["a", "b"])
        XCTAssertEqual(page.nextOffset, 2)
        XCTAssertEqual(page.items[0].sizeBytes, 2048)
        XCTAssertTrue(page.items[0].sourceAvailable)
        XCTAssertNotNil(page.items[0].created, "fractional seconds parse")
        XCTAssertNotNil(page.items[1].created, "plain seconds parse")
        let last = try JSONDecoder().decode(SavedDocumentPage.self, from: JSONSerialization.data(withJSONObject: ["items": [], "next_offset": NSNull()]))
        XCTAssertNil(last.nextOffset)
    }

    func testSaveSendsTheBytesTheirTypeAndAnEncodedNameAndNoExtractionConsent() async throws {
        let fixture = try DocumentFixture()
        let identity = try await fixture.login()
        let bytes = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x01])
        let capture = try await fixture.client.saveDocument(bytes, mediaType: "image/jpeg", filename: "Café ticket.jpg", expectedIdentity: identity)
        XCTAssertEqual(capture.connectionID, "doc-new")
        XCTAssertFalse(capture.replayed)
        let sent = await fixture.server.captured()
        let request = try XCTUnwrap(sent.last)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.path, "/api/v1/financial-documents")
        XCTAssertEqual(request.httpBody, bytes)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "image/jpeg")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Document-Filename"), "Caf%C3%A9%20ticket.jpg")
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Extraction-Consent"), "saving a file never asks a model to read it")
        XCTAssertNil(request.value(forHTTPHeaderField: "Cookie"))
    }

    func testAFileOfTheWrongTypeOrTooLargeIsRefusedBeforeAnyRequest() async throws {
        let fixture = try DocumentFixture()
        let identity = try await fixture.login()
        let before = await fixture.server.captured().count
        do { _ = try await fixture.client.saveDocument(Data([1]), mediaType: "text/plain", filename: "a.txt", expectedIdentity: identity); XCTFail("type") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 415, code: "document_media_type_unsupported")) }
        let big = Data(count: SavedDocumentRules.maxBytes + 1)
        do { _ = try await fixture.client.saveDocument(big, mediaType: "application/pdf", filename: "a.pdf", expectedIdentity: identity); XCTFail("size") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 413, code: "document_too_large")) }
        let exactly = Data(count: SavedDocumentRules.maxBytes)
        _ = try await fixture.client.saveDocument(exactly, mediaType: "application/pdf", filename: "a.pdf", expectedIdentity: identity)
        let after = await fixture.server.captured().count
        XCTAssertEqual(after - before, 1, "only the file at the cap was sent")
    }

    func testDeleteUsesTheConnectionDisconnectRoute() async throws {
        let fixture = try DocumentFixture()
        let identity = try await fixture.login()
        try await fixture.client.deleteSavedDocument("doc-9", expectedIdentity: identity)
        let sent = await fixture.server.captured()
        let request = try XCTUnwrap(sent.last)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.path, "/api/v1/financial-connections/doc-9/disconnect")
    }

    func testTheListAndSourceReadsAndAServerProblemKeepsItsCode() async throws {
        let fixture = try DocumentFixture()
        let identity = try await fixture.login()
        let page = try await fixture.client.savedDocuments(limit: 25, offset: 50, expectedIdentity: identity)
        XCTAssertEqual(page.items.count, 1)
        let sentList = await fixture.server.captured()
        let listRequest = try XCTUnwrap(sentList.last)
        XCTAssertEqual(URLComponents(url: listRequest.url!, resolvingAgainstBaseURL: false)?.queryItems?.map { "\($0.name)=\($0.value ?? "")" }, ["limit=25", "offset=50"])
        let source = try await fixture.client.savedDocumentSource("doc-1", expectedIdentity: identity)
        XCTAssertEqual(source, Data("%PDF-1.7".utf8))
        await fixture.server.fail(status: 503, code: "document_storage_unavailable")
        do { _ = try await fixture.client.savedDocumentSource("doc-1", expectedIdentity: identity); XCTFail("503") }
        catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 503, code: "document_storage_unavailable")) }
    }

    func testConsentIsSentOnlyWhenThePersonAllowsReading() async throws {
        let fixture = try DocumentFixture()
        let identity = try await fixture.login()
        _ = try await fixture.client.saveDocument(Data([0xFF, 0xD8]), mediaType: "image/jpeg", filename: "a.jpg", consent: true, expectedIdentity: identity)
        let sent = await fixture.server.captured()
        XCTAssertEqual(sent.last?.value(forHTTPHeaderField: "X-Extraction-Consent"), "true")
        _ = try await fixture.client.prepareDocument("doc-1", expectedIdentity: identity)
        let prepared = await fixture.server.captured()
        let request = try XCTUnwrap(prepared.last)
        XCTAssertEqual(request.url?.path, "/api/v1/financial-documents/doc-1/prepare")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Extraction-Consent"), "true")
    }

    func testTheDocumentDetailDecodesItsReceiptAndTheImportsFindIt() async throws {
        let fixture = try DocumentFixture()
        let identity = try await fixture.login()
        let detail = try await fixture.client.financialDocument("doc-1", expectedIdentity: identity)
        XCTAssertEqual(detail.status, "review_ready")
        XCTAssertFalse(detail.isPreparing)
        XCTAssertEqual(detail.preparation?.receipt?.total, "250.50")
        XCTAssertEqual(detail.preparation?.receipt?.items.map(\.unitPrice), ["150.00"])
        let events = try await fixture.client.financialImports(expectedIdentity: identity)
        XCTAssertEqual(events.map(\.id), ["evt-1"])
        XCTAssertEqual(events.first?.connectionIDs, ["doc-1"])
        XCTAssertEqual(events.first?.unresolved, ["account_id"])
        let sent = await fixture.server.captured()
        XCTAssertEqual(sent.last?.url?.query, "state=open")
    }

    func testResolveSendsOnlyTheAnswersAndAcceptCarriesTheReviewedRequestAndKey() async throws {
        let fixture = try DocumentFixture()
        let identity = try await fixture.login()
        let event = try await fixture.client.financialImport("evt-1", expectedIdentity: identity)
        let account = UUID(uuidString: "6A1F0B8E-3C55-4C2E-9A7D-2F1B4C6D8E90")!
        _ = try await fixture.client.resolveFinancialImport(event, changes: FinancialImportChanges(accountID: account, categoryID: "groceries"),
                                                            expectedIdentity: identity)
        let resolved = await fixture.server.captured()
        let patch = try XCTUnwrap(resolved.last)
        XCTAssertEqual(patch.httpMethod, "PATCH")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(patch.httpBody)) as? [String: Any])
        XCTAssertEqual(body["version"] as? Int, 4)
        XCTAssertEqual(body["changes"] as? [String: String], ["account_id": "6a1f0b8e-3c55-4c2e-9a7d-2f1b4c6d8e90", "category_id": "groceries"])

        let key = UUID()
        let request = FinancialActivityCommand(kind: .expense, accountId: account, amount: "250.50", occurredAt: "2026-10-10T12:00:00-04:00",
                                               timeZone: "America/Santo_Domingo", previewToken: "token-1")
        _ = try? await fixture.client.acceptFinancialImport(event, request: request, key: key, expectedIdentity: identity)
        let accepted = await fixture.server.captured()
        let post = try XCTUnwrap(accepted.last)
        XCTAssertEqual(post.url?.path, "/api/v1/financial-imports/evt-1/accept")
        XCTAssertEqual(post.value(forHTTPHeaderField: "Idempotency-Key"), key.uuidString)
        let acceptBody = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(post.httpBody)) as? [String: Any])
        XCTAssertEqual(acceptBody["version"] as? Int, 4)
        XCTAssertEqual((acceptBody["request"] as? [String: Any])?["preview_token"] as? String, "token-1")

        _ = try await fixture.client.linkFinancialImport(event, activityID: account, expectedIdentity: identity)
        let linked = await fixture.server.captured()
        let link = try XCTUnwrap(linked.last)
        XCTAssertEqual(link.url?.path, "/api/v1/financial-imports/evt-1/link-activity")
        let linkBody = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(link.httpBody)) as? [String: Any])
        XCTAssertEqual(linkBody["activity_id"] as? String, "6a1f0b8e-3c55-4c2e-9a7d-2f1b4c6d8e90")
    }
}

nonisolated(unsafe) private let documentDetail: [String: Any] = ["connection_id": "doc-1", "filename": "Ticket.jpg", "media_type": "image/jpeg",
    "sha256": "abc", "size_bytes": 10, "source_available": true, "status": "review_ready", "consent": true, "version": 3,
    "created_at": "2026-10-11T12:00:00Z", "updated_at": "2026-10-11T12:00:00Z", "error_code": NSNull(), "proposal": [String: Any](),
    "preparation": ["complete": true, "readable": true, "pages_read": [1], "candidates": [], "observations": [], "issues": [],
                    "receipt": ["merchant": "La Sirena", "occurred_on": "2026-10-10", "currency": "DOP", "subtotal": "150.00",
                                "tax": NSNull(), "service": NSNull(), "tip": NSNull(), "total": "250.50", "suggested_category": NSNull(),
                                "rnc": NSNull(), "ncf": NSNull(), "ecf": NSNull(), "itbis": NSNull(),
                                "items": [["id": "1", "description": "Arroz", "quantity": "1", "unit_price": "150.00", "total": "150.00",
                                           "suggested_category": NSNull()]]]]]

nonisolated(unsafe) private let importEvent: [String: Any] = ["id": "evt-1", "state": "open", "evidence": "receipt", "version": 4, "attention": NSNull(),
    "attention_detail": NSNull(), "possible_duplicates": [], "existing_activity_matches": [], "recorded_duplicates": [],
    "activity_id": NSNull(), "facts": ["amount": "250.50", "currency": "DOP", "direction": "outflow", "occurred_on": "2026-10-10",
                                       "account_id": NSNull(), "kind": "expense"],
    "resolution": [String: Any](), "unresolved": ["account_id"], "account_shared_with_household": NSNull(),
    "observations": [["id": "obs-1", "source": "statement", "connection_id": "doc-1", "external_id": "x", "evidence": "receipt",
                      "status": "posted", "live": true, "revisions": 1, "observed_at": NSNull(), "occurred_on": "2026-10-10",
                      "posted_on": NSNull(), "due_on": NSNull(), "amount": "250.50", "currency": "DOP", "direction": "outflow",
                      "merchant": "La Sirena", "description": NSNull(), "excerpt": NSNull(), "balance_scope": NSNull(),
                      "institution": NSNull(), "account_name": NSNull(), "account_mask": NSNull(), "attachments": [], "redacted": false]],
    "created_at": "2026-10-11T12:00:00Z", "updated_at": "2026-10-11T12:00:00Z"]

struct DocumentFixture {
    let server: DocumentServer
    let client: SessionController
    init() throws {
        let server = DocumentServer()
        self.server = server
        let config = try SessionConfiguration(argusAPIURL: URL(string: "https://api.example.test")!, supabaseURL: URL(string: "https://auth.example.test")!, publicAnonKey: "sb_publishable_test", keychainService: UUID().uuidString)
        client = try SessionController(configuration: config, storage: MemoryStore(), fetch: { try await server.send($0) })
    }
    func login() async throws -> SessionSnapshot {
        try await client.login(email: "alice@example.test", password: "synthetic-password", captchaToken: "synthetic-captcha")
    }
}

actor DocumentServer {
    let auth = AuthServer()
    private var requests: [URLRequest] = []
    private var failure: (status: Int, code: String)?
    func captured() -> [URLRequest] { requests }
    func fail(status: Int, code: String) { failure = (status, code) }
    func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
        let path = request.url!.path
        guard path.contains("/financial-documents") || path.contains("/financial-connections") || path.contains("/financial-imports")
        else { return try await auth.send(request) }
        requests.append(request)
        func reply(_ status: Int, _ body: Data) -> (Data, URLResponse) {
            (body, HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!)
        }
        if let failure { return reply(failure.status, try JSONSerialization.data(withJSONObject: ["code": failure.code])) }
        if request.httpMethod == "POST" && path.hasSuffix("/financial-documents") {
            return reply(200, try JSONSerialization.data(withJSONObject: ["connection_id": "doc-new", "status": "saved", "replayed": false, "candidate_count": 0]))
        }
        if request.httpMethod == "POST" && path.hasSuffix("/disconnect") { return reply(200, Data("{}".utf8)) }
        if path.hasSuffix("/prepare") {
            return reply(200, try JSONSerialization.data(withJSONObject: ["connection_id": "doc-1", "status": "queued", "replayed": false, "candidate_count": 0]))
        }
        if path.contains("/financial-imports") {
            if path.hasSuffix("/accept") { return reply(200, Data("{}".utf8)) }
            if path.hasSuffix("/financial-imports") { return reply(200, try JSONSerialization.data(withJSONObject: ["items": [importEvent]])) }
            return reply(200, try JSONSerialization.data(withJSONObject: importEvent))
        }
        if request.httpMethod == "GET" && path.hasSuffix("/financial-documents/doc-1") {
            return reply(200, try JSONSerialization.data(withJSONObject: documentDetail))
        }
        if path.hasSuffix("/source") { return reply(200, Data("%PDF-1.7".utf8)) }
        let item: [String: Any] = ["connection_id": "doc-1", "filename": "Ticket.pdf", "media_type": "application/pdf", "sha256": "abc",
            "size_bytes": 10, "source_available": true, "status": "saved", "consent": false, "version": 1,
            "created_at": "2026-10-08T12:00:00Z", "updated_at": "2026-10-08T12:00:00Z", "error_code": NSNull(), "proposal": [String: Any]()]
        return reply(200, try JSONSerialization.data(withJSONObject: ["items": [item], "next_offset": NSNull()]))
    }
}
