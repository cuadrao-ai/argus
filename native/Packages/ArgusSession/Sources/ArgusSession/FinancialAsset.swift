import Foundation

public typealias FinancialAsset = FinancialAssetValue<UUID>

public struct FinancialAssetValue<Author: Codable & Equatable & Sendable>: Codable, Equatable, Sendable {
    public let personalPositionMinor: Int64?
    public let currentEstimate: FinancialAssetEstimate?
    public let estimates: [FinancialAssetEstimate]
    public let relatedDebtAccountId: UUID?
    public let changes: [FinancialAssetChangeValue<Author>]
    enum CodingKeys: String, CodingKey {
        case estimates, changes, personalPositionMinor = "personal_position_minor", currentEstimate = "current_estimate", relatedDebtAccountId = "related_debt_account_id"
    }
}

public struct FinancialAssetEstimate: Codable, Equatable, Sendable, Identifiable {
    public let recordId: UUID
    public let revision: Int
    public let kind: String
    public let amountMinor: Int64
    public let amount: String
    public let asOf: String
    public let timeZone: String
    public let estimateBasis: String?
    public let reason: String?
    public let recordedBy: UUID?
    public let recordedAt: String
    public let revisions: [FinancialAssetRevision]
    public var id: UUID { recordId }
    enum CodingKeys: String, CodingKey {
        case revision, kind, amount, reason, revisions, recordId = "record_id", amountMinor = "amount_minor", asOf = "as_of", timeZone = "time_zone", estimateBasis = "estimate_basis", recordedBy = "recorded_by", recordedAt = "recorded_at"
    }
}

public struct FinancialAssetRevision: Codable, Equatable, Sendable {
    public let revision: Int
    public let amountMinor: Int64
    public let amount: String
    public let asOf: String
    public let timeZone: String
    public let estimateBasis: String?
    public let reason: String?
    public let recordedBy: UUID?
    public let recordedAt: String
    enum CodingKeys: String, CodingKey {
        case revision, amount, reason, amountMinor = "amount_minor", asOf = "as_of", timeZone = "time_zone", estimateBasis = "estimate_basis", recordedBy = "recorded_by", recordedAt = "recorded_at"
    }
}

public typealias FinancialAssetChange = FinancialAssetChangeValue<UUID>

public struct FinancialAssetChangeValue<Author: Codable & Equatable & Sendable>: Codable, Equatable, Sendable {
    public let version: Int
    public let previousShareBps: Int
    public let ownershipShareBps: Int
    public let previousDebtAccountId: UUID?
    public let relatedDebtAccountId: UUID?
    public let recordedBy: Author
    public let recordedAt: String
    enum CodingKeys: String, CodingKey {
        case version, previousShareBps = "previous_share_bps", ownershipShareBps = "ownership_share_bps", previousDebtAccountId = "previous_debt_account_id", relatedDebtAccountId = "related_debt_account_id", recordedBy = "recorded_by", recordedAt = "recorded_at"
    }
}

public struct FinancialAssetEstimateCommand: Codable, Equatable, Sendable {
    public let expectedVersion: Int
    public let amount: String
    public let asOf: String
    public let timeZone: String
    public let estimateBasis: String?
    public let reason: String?
    public let recordId: UUID?
    public let expectedRevision: Int?
    public var previewToken: String?
    public init(expectedVersion: Int, amount: String, asOf: String, timeZone: String, estimateBasis: String?, reason: String?, recordId: UUID?, expectedRevision: Int?, previewToken: String? = nil) {
        self.expectedVersion = expectedVersion; self.amount = amount; self.asOf = asOf; self.timeZone = timeZone
        self.estimateBasis = estimateBasis; self.reason = reason; self.recordId = recordId
        self.expectedRevision = expectedRevision; self.previewToken = previewToken
    }
    enum CodingKeys: String, CodingKey {
        case amount, reason, expectedVersion = "expected_version", asOf = "as_of", timeZone = "time_zone", estimateBasis = "estimate_basis", recordId = "record_id", expectedRevision = "expected_revision", previewToken = "preview_token"
    }
}

public struct FinancialAssetDetailsCommand: Codable, Equatable, Sendable {
    public let expectedVersion: Int
    public let ownershipShareBps: Int
    public let relatedDebtAccountId: UUID?
    public init(expectedVersion: Int, ownershipShareBps: Int, relatedDebtAccountId: UUID?) {
        self.expectedVersion = expectedVersion; self.ownershipShareBps = ownershipShareBps; self.relatedDebtAccountId = relatedDebtAccountId
    }
    enum CodingKeys: String, CodingKey { case expectedVersion = "expected_version", ownershipShareBps = "ownership_share_bps", relatedDebtAccountId = "related_debt_account_id" }
    public func encode(to encoder: any Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(expectedVersion, forKey: .expectedVersion)
        try c.encode(ownershipShareBps, forKey: .ownershipShareBps)
        try c.encode(relatedDebtAccountId, forKey: .relatedDebtAccountId)
    }
}

public struct FinancialAssetPreview: Decodable, Sendable {
    public let account: FinancialAccount
    public let previewToken: String
    enum CodingKeys: String, CodingKey { case account, previewToken = "preview_token" }
}

extension SessionController {
    public func assetEstimatePreview(accountId: UUID, command: FinancialAssetEstimateCommand, expectedIdentity: SessionSnapshot) async throws -> FinancialAssetPreview {
        let data = try await financialRequest(path: "/" + accountId.uuidString + "/asset-estimates/preview", method: "POST", body: encoded(command), expectedIdentity: expectedIdentity)
        return try JSONDecoder().decode(FinancialAssetPreview.self, from: data)
    }

    public func sendAccountConfirmation(_ write: PendingFinancialConfirmation, expectedIdentity: SessionSnapshot) async throws -> FinancialAccount {
        guard expectedIdentity.profile.flatMap({ UUID(uuidString: $0.id) }) == write.ownerId,
              write.route == "financial-accounts" else { throw SessionFailure.invalidResponse }
        if write.path.isEmpty {
            guard write.method == "POST", write.originAccountId == nil else { throw SessionFailure.invalidResponse }
        } else {
            guard let id = write.originAccountId,
                  (write.path == "/" + id.uuidString + "/asset-estimates" && write.method == "POST") ||
                  (write.path == "/" + id.uuidString + "/asset-details" && write.method == "PUT")
            else { throw SessionFailure.invalidResponse }
        }
        let data = try await financialRequest(path: write.path, method: write.method, body: write.body, key: write.key.uuidString, expectedIdentity: expectedIdentity)
        do {
            if write.path.isEmpty { return try JSONDecoder().decode(FinancialAccount.self, from: data) }
            struct Receipt: Decodable { let account: FinancialAccount }
            return try JSONDecoder().decode(Receipt.self, from: data).account
        } catch { throw SessionFailure.invalidResponse }
    }
}
