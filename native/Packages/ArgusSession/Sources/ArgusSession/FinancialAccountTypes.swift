import Foundation

/// Wire values only. The server owns amount precision, currency validity and nature.
/// Date strings preserve the recorded offset; no client normalization changes an instant.
public typealias FinancialAccount = FinancialAccountValue<UUID>

public struct FinancialAccountValue<Author: Codable & Equatable & Sendable>: Codable, Equatable, Sendable, Identifiable {
    public let id: UUID
    public let type: String
    public let nature: String
    public let currency: String
    public let currencyFractionDigits: Int
    public let nickname: String?
    public let archived: Bool
    public let ownershipShareBps: Int
    public let version: Int
    public let createdAt: String
    public let updatedAt: String
    public let balance: FinancialBalance
    public let opening: FinancialOpening?
    public let asset: FinancialAssetValue<Author>?
    public var isOptionalAsset: Bool { ["property", "vehicle", "other_asset"].contains(type) }
    enum CodingKeys: String, CodingKey {
        case id, type, nature, currency, nickname, archived, version, balance, opening, asset
        case currencyFractionDigits = "currency_fraction_digits", ownershipShareBps = "ownership_share_bps"
        case createdAt = "created_at", updatedAt = "updated_at"
    }
}

public struct FinancialBalance: Codable, Equatable, Sendable {
    public enum State: String, Codable, Sendable { case known, unknown }
    public let state: State
    public let amountMinor: Int64?
    public let amount: String?
    public let asOf: String?
    public let basis: String?
    public let activitySinceTrackingMinor: Int64
    public let creditMinor: Int64?
    enum CodingKeys: String, CodingKey {
        case state, amount, basis
        case amountMinor = "amount_minor", asOf = "as_of", activitySinceTrackingMinor = "activity_since_tracking_minor"
        case creditMinor = "credit_minor"
    }
}

public struct FinancialOpening: Codable, Equatable, Sendable {
    public let recordId: UUID
    public let revision: Int
    public let amountMinor: Int64
    public let amount: String
    public let asOf: String
    public let timeZone: String
    public let reason: String?
    public let recordedAt: String
    public let revisions: [FinancialOpeningRevision]
    enum CodingKeys: String, CodingKey {
        case revision, amount, reason, revisions
        case recordId = "record_id", amountMinor = "amount_minor", asOf = "as_of", timeZone = "time_zone", recordedAt = "recorded_at"
    }
}

public struct FinancialOpeningRevision: Codable, Equatable, Sendable {
    public let revision: Int
    public let amountMinor: Int64
    public let amount: String
    public let asOf: String
    public let timeZone: String
    public let reason: String?
    public let recordedBy: String?
    public let recordedAt: String
    enum CodingKeys: String, CodingKey {
        case revision, amount, reason
        case amountMinor = "amount_minor", asOf = "as_of", timeZone = "time_zone", recordedAt = "recorded_at", recordedBy = "recorded_by"
    }
}

/// Keep this immutable value for retries after uncertain delivery. Its UUID is
/// a header, never part of the body. Creating a new value means a new operation.
public struct CreateFinancialAccountRequest: Encodable, Equatable, Sendable {
    public let idempotencyKey: UUID
    public let type: String
    public let currency: String
    public let nickname: String?
    public let amount: String?
    public let asOf: String?
    public let timeZone: String?
    public let ownershipShareBps: Int
    public init(type: String, currency: String, nickname: String? = nil, amount: String? = nil,
                asOf: String? = nil, timeZone: String? = nil, ownershipShareBps: Int = 10000,
                idempotencyKey: UUID = UUID()) {
        self.type = type; self.currency = currency; self.nickname = nickname; self.amount = amount
        self.asOf = asOf; self.timeZone = timeZone; self.ownershipShareBps = ownershipShareBps; self.idempotencyKey = idempotencyKey
    }
    enum CodingKeys: String, CodingKey {
        case type, currency, nickname, amount
        case asOf = "as_of", timeZone = "time_zone", ownershipShareBps = "ownership_share_bps"
    }
}

public struct EditFinancialAccountRequest: Encodable, Equatable, Sendable {
    public let expectedVersion: Int
    /// nil leaves the nickname unchanged; an empty string explicitly clears it.
    public let nickname: String?
    public let type: String?
    public let currency: String?
    public let archived: Bool?
    public let ownershipShareBps: Int?
    public init(expectedVersion: Int, nickname: String? = nil, type: String? = nil,
                currency: String? = nil, archived: Bool? = nil, ownershipShareBps: Int? = nil) {
        self.expectedVersion = expectedVersion; self.nickname = nickname; self.type = type
        self.currency = currency; self.archived = archived; self.ownershipShareBps = ownershipShareBps
    }
    enum CodingKeys: String, CodingKey {
        case nickname, type, currency, archived
        case expectedVersion = "expected_version", ownershipShareBps = "ownership_share_bps"
    }
}

public struct WriteOpeningRequest: Encodable, Equatable, Sendable {
    public let expectedVersion: Int
    public let expectedRevision: Int?
    /// User-entered convention (positive owed for liabilities), not signed GET truth.
    /// Omit unchanged amounts, especially for date-only corrections.
    public let amount: String?
    public let asOf: String?
    public let timeZone: String?
    public let reason: String?
    public var coverage: [OpeningCoverage]? = nil
    public var previewToken: String? = nil
    public init(expectedVersion: Int, expectedRevision: Int?, amount: String? = nil,
                asOf: String? = nil, timeZone: String? = nil, reason: String? = nil) {
        self.expectedVersion = expectedVersion; self.expectedRevision = expectedRevision
        self.amount = amount; self.asOf = asOf; self.timeZone = timeZone; self.reason = reason
    }
    enum CodingKeys: String, CodingKey {
        case amount, reason, coverage
        case previewToken = "preview_token"
        case expectedVersion = "expected_version", expectedRevision = "expected_revision", asOf = "as_of", timeZone = "time_zone"
    }
    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(expectedVersion, forKey: .expectedVersion)
        try container.encode(expectedRevision, forKey: .expectedRevision)
        try container.encodeIfPresent(amount, forKey: .amount)
        try container.encodeIfPresent(asOf, forKey: .asOf)
        try container.encodeIfPresent(timeZone, forKey: .timeZone)
        try container.encodeIfPresent(reason, forKey: .reason)
        try container.encodeIfPresent(coverage, forKey: .coverage)
        try container.encodeIfPresent(previewToken, forKey: .previewToken)
    }
}
