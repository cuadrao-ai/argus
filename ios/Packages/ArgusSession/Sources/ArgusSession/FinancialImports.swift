import Foundation

/// One saved document with its preparation (`GET /financial-documents/{id}`). The status is preparation state only;
/// approval lives on the import events that carry this connection ID.
public struct FinancialDocumentDetail: Decodable, Sendable, Equatable, Identifiable {
    public let connectionID: String
    public let filename: String
    public let mediaType: String
    public let sourceAvailable: Bool
    public let status: String
    public let consent: Bool
    public let version: Int
    public let errorCode: String?
    public let createdAt: String
    public let preparation: DocumentPreparation?
    public var id: String { connectionID }

    /// The server is still reading the file; poll again.
    public var isPreparing: Bool { status == "queued" || status == "preparing" }

    enum CodingKeys: String, CodingKey {
        case filename, status, consent, version, preparation
        case connectionID = "connection_id", mediaType = "media_type", sourceAvailable = "source_available"
        case errorCode = "error_code", createdAt = "created_at"
    }
}

/// What the server read from the file. Missing fields stay unknown; receipt lines are review detail, not purchases.
public struct DocumentPreparation: Decodable, Sendable, Equatable {
    public let complete: Bool?
    public let readable: Bool?
    public let receipt: DocumentReceipt?
}

public struct DocumentReceipt: Decodable, Sendable, Equatable {
    public let merchant: String?
    public let occurredOn: String?
    public let currency: String?
    public let items: [DocumentReceiptItem]
    public let subtotal: String?
    public let tax: String?
    public let service: String?
    public let tip: String?
    public let total: String?
    public let suggestedCategory: String?
    enum CodingKeys: String, CodingKey {
        case merchant, currency, items, subtotal, tax, service, tip, total
        case occurredOn = "occurred_on", suggestedCategory = "suggested_category"
    }
}

public struct DocumentReceiptItem: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let description: String?
    public let quantity: String?
    public let unitPrice: String?
    public let total: String?
    enum CodingKeys: String, CodingKey { case id, description, quantity, total; case unitPrice = "unit_price" }
}

/// A draft movement the reconciliation queue holds until the person records it (`/financial-imports`).
/// Open events affect no balance, budget, goal, Home or Search.
public struct FinancialImportEvent: Decodable, Sendable, Equatable, Identifiable {
    public let id: String
    public let state: String
    public let version: Int
    public let attention: String?
    public let activityID: String?
    public let facts: FinancialImportFacts
    public let unresolved: [String]
    public let possibleDuplicates: [String]
    public let existingActivityMatches: [String]
    public let recordedDuplicates: [String]
    public let observations: [FinancialImportObservation]

    /// The documents this event was read from.
    public var connectionIDs: Set<String> { Set(observations.map(\.connectionID)) }

    enum CodingKeys: String, CodingKey {
        case id, state, version, attention, facts, unresolved, observations
        case activityID = "activity_id", possibleDuplicates = "possible_duplicates"
        case existingActivityMatches = "existing_activity_matches", recordedDuplicates = "recorded_duplicates"
    }
}

public struct FinancialImportFacts: Decodable, Sendable, Equatable {
    public let amount: String?
    public let currency: String?
    public let direction: String?
    public let occurredOn: String?
    public let accountID: String?
    public let kind: String?
    enum CodingKeys: String, CodingKey {
        case amount, currency, direction, kind
        case occurredOn = "occurred_on", accountID = "account_id"
    }
}

public struct FinancialImportObservation: Decodable, Sendable, Equatable {
    public let source: String
    public let connectionID: String
    public let merchant: String?
    public let description: String?
    public let amount: String?
    public let currency: String?
    public let occurredOn: String?
    enum CodingKeys: String, CodingKey {
        case source, merchant, description, amount, currency
        case connectionID = "connection_id", occurredOn = "occurred_on"
    }
}

/// The person's answers for an import. Only the fields set here are sent; the server keeps the rest.
public struct FinancialImportChanges: Encodable, Sendable, Equatable {
    public var kind: FinancialActivityKind?
    public var accountID: UUID?
    public var amount: String?
    public var currency: String?
    public var occurredOn: String?
    public var categoryID: String?
    public var note: String?
    public var timeZone: String?

    public init(kind: FinancialActivityKind? = nil, accountID: UUID? = nil, amount: String? = nil, currency: String? = nil,
                occurredOn: String? = nil, categoryID: String? = nil, note: String? = nil, timeZone: String? = nil) {
        self.kind = kind; self.accountID = accountID; self.amount = amount; self.currency = currency
        self.occurredOn = occurredOn; self.categoryID = categoryID; self.note = note; self.timeZone = timeZone
    }

    enum CodingKeys: String, CodingKey {
        case kind, amount, currency, note
        case accountID = "account_id", occurredOn = "occurred_on", categoryID = "category_id", timeZone = "time_zone"
    }

    public func encode(to encoder: any Encoder) throws {
        var value = encoder.container(keyedBy: CodingKeys.self)
        try value.encodeIfPresent(kind, forKey: .kind)
        try value.encodeIfPresent(accountID?.uuidString.lowercased(), forKey: .accountID)
        try value.encodeIfPresent(amount, forKey: .amount)
        try value.encodeIfPresent(currency, forKey: .currency)
        try value.encodeIfPresent(occurredOn, forKey: .occurredOn)
        try value.encodeIfPresent(categoryID, forKey: .categoryID)
        try value.encodeIfPresent(note, forKey: .note)
        try value.encodeIfPresent(timeZone, forKey: .timeZone)
    }
}

public struct FinancialImportPreview: Decodable, Sendable {
    public let event: FinancialImportEvent
    public let preview: FinancialActivityPreview
}

public struct FinancialImportAcceptance: Decodable, Sendable {
    public let event: FinancialImportEvent
    public let activity: FinancialActivityDetail
    public let replayed: Bool
}

private struct ImportList: Decodable { let items: [FinancialImportEvent] }
private struct VersionBody: Encodable { let version: Int }
private struct ResolveBody: Encodable { let version: Int; let changes: FinancialImportChanges }
private struct LinkBody: Encodable {
    let version: Int; let activityID: String
    enum CodingKeys: String, CodingKey { case version; case activityID = "activity_id" }
}
private struct AcceptBody: Encodable { let version: Int; let request: FinancialActivityCommand }
private struct PreviewBody: Encodable { let overrides: [String: String] }

extension SessionController {
    public func financialDocument(_ connectionID: String, expectedIdentity: SessionSnapshot) async throws -> FinancialDocumentDetail {
        try await importResponse(route: "financial-documents", path: "/" + connectionID, identity: expectedIdentity)
    }

    /// Asks the server to read a saved file again. Sent only with the person's consent; a saved reading replays without a model.
    public func prepareDocument(_ connectionID: String, expectedIdentity: SessionSnapshot) async throws -> SavedDocumentCapture {
        try await importResponse(route: "financial-documents", path: "/" + connectionID + "/prepare", method: "POST",
                                 body: Data("{}".utf8), headers: ["X-Extraction-Consent": "true"], identity: expectedIdentity)
    }

    public func financialImports(state: String = "open", expectedIdentity: SessionSnapshot) async throws -> [FinancialImportEvent] {
        let list: ImportList = try await importResponse(query: [URLQueryItem(name: "state", value: state)], identity: expectedIdentity)
        return list.items
    }

    public func financialImport(_ id: String, expectedIdentity: SessionSnapshot) async throws -> FinancialImportEvent {
        try await importResponse(path: "/" + id, identity: expectedIdentity)
    }

    public func resolveFinancialImport(_ event: FinancialImportEvent, changes: FinancialImportChanges,
                                       expectedIdentity: SessionSnapshot) async throws -> FinancialImportEvent {
        try await importResponse(path: "/" + event.id, method: "PATCH",
                                 body: encoded(ResolveBody(version: event.version, changes: changes)), identity: expectedIdentity)
    }

    public func previewFinancialImport(_ id: String, expectedIdentity: SessionSnapshot) async throws -> FinancialImportPreview {
        try await importResponse(path: "/" + id + "/preview", method: "POST",
                                 body: encoded(PreviewBody(overrides: [:])), identity: expectedIdentity)
    }

    /// Records the reviewed request. A retry with the same key replays the first recording, so it never records twice.
    public func acceptFinancialImport(_ event: FinancialImportEvent, request: FinancialActivityCommand, key: UUID,
                                      expectedIdentity: SessionSnapshot) async throws -> FinancialImportAcceptance {
        try await importResponse(path: "/" + event.id + "/accept", method: "POST",
                                 body: encoded(AcceptBody(version: event.version, request: request)), key: key.uuidString,
                                 identity: expectedIdentity)
    }

    /// The purchase is already recorded: the receipt joins that movement instead of creating another.
    public func linkFinancialImport(_ event: FinancialImportEvent, activityID: UUID,
                                    expectedIdentity: SessionSnapshot) async throws -> FinancialImportEvent {
        try await importResponse(path: "/" + event.id + "/link-activity", method: "POST",
                                 body: encoded(LinkBody(version: event.version, activityID: activityID.uuidString.lowercased())),
                                 identity: expectedIdentity)
    }

    public func dismissFinancialImport(_ event: FinancialImportEvent, expectedIdentity: SessionSnapshot) async throws -> FinancialImportEvent {
        try await importResponse(path: "/" + event.id + "/dismiss", method: "POST",
                                 body: encoded(VersionBody(version: event.version)), identity: expectedIdentity)
    }

    private func importResponse<Value: Decodable>(route: String = "financial-imports", path: String = "", method: String = "GET",
                                                  body: Data? = nil, key: String? = nil, query: [URLQueryItem] = [],
                                                  headers: [String: String] = [:], identity: SessionSnapshot) async throws -> Value {
        let data = try await financialRequest(route: route, path: path, method: method, body: body, key: key, query: query,
                                              headers: headers, expectedIdentity: identity)
        do { return try JSONDecoder().decode(Value.self, from: data) }
        catch { throw SessionFailure.invalidResponse }
    }
}
