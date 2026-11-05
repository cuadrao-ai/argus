import Foundation

/// A receipt or other file the person saved, as the server lists it (`GET /financial-documents`).
/// Saving a document stores the file privately and creates no expense, balance change or amount owed.
public struct SavedDocument: Decodable, Sendable, Identifiable, Equatable {
    public let connectionID: String
    public let filename: String
    public let mediaType: String
    public let sizeBytes: Int
    /// False when the stored file is gone, so it can be listed but not opened.
    public let sourceAvailable: Bool
    public let status: String
    public let createdAt: String
    public let updatedAt: String
    public var id: String { connectionID }

    enum CodingKeys: String, CodingKey {
        case filename, status
        case connectionID = "connection_id"
        case mediaType = "media_type"
        case sizeBytes = "size_bytes"
        case sourceAvailable = "source_available"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    public init(connectionID: String, filename: String, mediaType: String, sizeBytes: Int, sourceAvailable: Bool,
                status: String, createdAt: String, updatedAt: String) {
        self.connectionID = connectionID; self.filename = filename; self.mediaType = mediaType; self.sizeBytes = sizeBytes
        self.sourceAvailable = sourceAvailable; self.status = status; self.createdAt = createdAt; self.updatedAt = updatedAt
    }

    /// The server's timestamp, which may or may not carry fractional seconds.
    public var created: Date? { Self.date(createdAt) }

    static func date(_ text: String) -> Date? {
        let plain = ISO8601DateFormatter()
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return plain.date(from: text) ?? fractional.date(from: text)
    }
}

public struct SavedDocumentPage: Decodable, Sendable, Equatable {
    public let items: [SavedDocument]
    public let nextOffset: Int?
    enum CodingKeys: String, CodingKey { case items; case nextOffset = "next_offset" }
}

/// What saving a file answered (`POST /financial-documents`).
public struct SavedDocumentCapture: Decodable, Sendable, Equatable {
    public let connectionID: String
    /// Preparation state (`saved|queued|preparing|review_ready|needs_attention`), never an approval.
    public let status: String
    /// True when the same file was already saved, so nothing new was stored.
    public let replayed: Bool
    public let candidateCount: Int
    enum CodingKeys: String, CodingKey { case status, replayed; case connectionID = "connection_id"; case candidateCount = "candidate_count" }

    public init(connectionID: String, status: String, replayed: Bool, candidateCount: Int = 0) {
        self.connectionID = connectionID; self.status = status; self.replayed = replayed; self.candidateCount = candidateCount
    }

    public init(from decoder: any Decoder) throws {
        let value = try decoder.container(keyedBy: CodingKeys.self)
        connectionID = try value.decode(String.self, forKey: .connectionID)
        status = try value.decode(String.self, forKey: .status)
        replayed = try value.decode(Bool.self, forKey: .replayed)
        candidateCount = try value.decodeIfPresent(Int.self, forKey: .candidateCount) ?? 0
    }
}

/// The media types the server accepts for a saved document, and their size cap.
public enum SavedDocumentRules {
    public static let mediaTypes: Set<String> = ["application/pdf", "image/jpeg", "image/png"]
    public static let maxBytes = 10 * 1024 * 1024
}

extension SessionController {
    public func savedDocuments(limit: Int = 50, offset: Int = 0, expectedIdentity: SessionSnapshot) async throws -> SavedDocumentPage {
        let query = [URLQueryItem(name: "limit", value: String(limit)), URLQueryItem(name: "offset", value: String(offset))]
        let data = try await financialRequest(route: "financial-documents", query: query, expectedIdentity: expectedIdentity)
        do { return try JSONDecoder().decode(SavedDocumentPage.self, from: data) }
        catch { throw SessionFailure.invalidResponse }
    }

    /// Saves a file privately. Only an explicit `consent` lets the server ask a model to read it.
    public func saveDocument(_ bytes: Data, mediaType: String, filename: String, consent: Bool = false,
                             expectedIdentity: SessionSnapshot) async throws -> SavedDocumentCapture {
        guard SavedDocumentRules.mediaTypes.contains(mediaType) else { throw SessionFailure.rejected(status: 415, code: "document_media_type_unsupported") }
        guard bytes.count <= SavedDocumentRules.maxBytes else { throw SessionFailure.rejected(status: 413, code: "document_too_large") }
        let encodedName = filename.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(CharacterSet(charactersIn: "-_.!~*'()"))) ?? "document"
        var headers = ["X-Document-Filename": encodedName]
        if consent { headers["X-Extraction-Consent"] = "true" }
        let data = try await financialRequest(route: "financial-documents", method: "POST", body: bytes,
                                              contentType: mediaType, headers: headers, expectedIdentity: expectedIdentity)
        do { return try JSONDecoder().decode(SavedDocumentCapture.self, from: data) }
        catch { throw SessionFailure.invalidResponse }
    }

    /// The stored file's bytes. The server proxies them; no link leaves the server.
    public func savedDocumentSource(_ connectionID: String, expectedIdentity: SessionSnapshot) async throws -> Data {
        try await financialRequest(route: "financial-documents", path: "/" + connectionID + "/source", expectedIdentity: expectedIdentity)
    }

    /// Deletes a saved document and erases its stored file. Confirmed activity is never touched.
    public func deleteSavedDocument(_ connectionID: String, expectedIdentity: SessionSnapshot) async throws {
        _ = try await financialRequest(route: "financial-connections", path: "/" + connectionID + "/disconnect", method: "POST",
                                       body: Data("{}".utf8), expectedIdentity: expectedIdentity)
    }
}
