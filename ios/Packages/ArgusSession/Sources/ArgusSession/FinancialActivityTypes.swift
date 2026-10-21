import Foundation

public enum FinancialActivityKind: String, Codable, CaseIterable, Sendable {
    case expense, income, transfer, cardPayment = "card_payment", refund, debtPayment = "debt_payment", paymentReversal = "payment_reversal"

    public var isPaired: Bool { self == .transfer || self == .cardPayment || self == .debtPayment || self == .paymentReversal }
}

public struct FinancialAccountCoverage: Codable, Equatable, Sendable {
    public var accountId: UUID
    public var observationId: UUID
    public var included: Bool
    public init(accountId: UUID, observationId: UUID, included: Bool) {
        self.accountId = accountId; self.observationId = observationId; self.included = included
    }
    enum CodingKeys: String, CodingKey {
        case accountId = "account_id", observationId = "observation_id", included
    }
}

/// The server returns this entire normalized command in a preview. Confirmation
/// changes only previewToken, then journals and sends the encoded bytes unchanged.
public struct FinancialActivityCommand: Codable, Equatable, Sendable {
    public var kind: FinancialActivityKind
    public var accountId: UUID?
    public var sourceAccountId: UUID?
    public var destinationAccountId: UUID?
    public var amount: String
    public var principal: String?
    public var interest: String?
    public var fees: String?
    public var reversalOfActivityId: UUID?
    public var occurredAt: String
    public var timeZone: String
    public var note: String?
    public var categoryId: String?
    public var sourceId: String?
    public var purchaseActivityId: UUID?
    public var expectedRevision: Int?
    public var reason: String?
    public var expectedVersions: [String: Int]
    public var coverage: [FinancialAccountCoverage]
    public var previewToken: String?
    /// The entry day the preview decided; sent back so confirm keeps it across midnight.
    public var enteredOn: String?

    public init(kind: FinancialActivityKind, accountId: UUID? = nil, sourceAccountId: UUID? = nil,
                destinationAccountId: UUID? = nil, amount: String, occurredAt: String,
                timeZone: String, note: String? = nil, categoryId: String? = nil,
                sourceId: String? = nil, purchaseActivityId: UUID? = nil,
                expectedRevision: Int? = nil, reason: String? = nil,
                expectedVersions: [String: Int] = [:], coverage: [FinancialAccountCoverage] = [],
                previewToken: String? = nil, principal: String? = nil, interest: String? = nil, fees: String? = nil, reversalOfActivityId: UUID? = nil) {
        self.principal = principal; self.interest = interest; self.fees = fees; self.reversalOfActivityId = reversalOfActivityId
        self.kind = kind; self.accountId = accountId; self.sourceAccountId = sourceAccountId
        self.destinationAccountId = destinationAccountId; self.amount = amount
        self.occurredAt = occurredAt; self.timeZone = timeZone; self.note = note
        self.categoryId = categoryId; self.sourceId = sourceId
        self.purchaseActivityId = purchaseActivityId; self.expectedRevision = expectedRevision
        self.reason = reason; self.expectedVersions = expectedVersions
        self.coverage = coverage; self.previewToken = previewToken
    }

    enum CodingKeys: String, CodingKey {
        case kind, amount, note, reason, coverage, principal, interest, fees
        case reversalOfActivityId = "reversal_of_activity_id"
        case accountId = "account_id", sourceAccountId = "source_account_id"
        case destinationAccountId = "destination_account_id", occurredAt = "occurred_at"
        case timeZone = "time_zone", categoryId = "category_id", sourceId = "source_id"
        case purchaseActivityId = "purchase_activity_id", expectedRevision = "expected_revision"
        case expectedVersions = "expected_versions", previewToken = "preview_token"
        case enteredOn = "entered_on"
    }

    public func encode(to encoder: any Encoder) throws {
        var value = encoder.container(keyedBy: CodingKeys.self)
        try value.encode(kind, forKey: .kind)
        try value.encode(accountId, forKey: .accountId)
        try value.encode(sourceAccountId, forKey: .sourceAccountId)
        try value.encode(destinationAccountId, forKey: .destinationAccountId)
        try value.encode(amount, forKey: .amount)
        try value.encode(principal, forKey: .principal); try value.encode(interest, forKey: .interest); try value.encode(fees, forKey: .fees)
        try value.encode(reversalOfActivityId, forKey: .reversalOfActivityId)
        try value.encode(occurredAt, forKey: .occurredAt)
        try value.encode(timeZone, forKey: .timeZone)
        try value.encode(note, forKey: .note)
        try value.encode(categoryId, forKey: .categoryId)
        try value.encode(sourceId, forKey: .sourceId)
        try value.encode(purchaseActivityId, forKey: .purchaseActivityId)
        try value.encode(expectedRevision, forKey: .expectedRevision)
        try value.encode(reason, forKey: .reason)
        try value.encode(expectedVersions, forKey: .expectedVersions)
        try value.encode(coverage, forKey: .coverage)
        try value.encode(previewToken, forKey: .previewToken)
        try value.encodeIfPresent(enteredOn, forKey: .enteredOn)
    }
}

public typealias FinancialActivityOptions = FinancialActivityOptionsValue<UUID>

public struct FinancialActivityOptionsValue<Author: Codable & Equatable & Sendable>: Decodable, Sendable {
    public let accounts: [FinancialAccountValue<Author>]
    public let eligibility: [String: [String]]
    public let destinationEligibility: [String: [String]]
    public let categories: [String]
    public let sources: [String]
    enum CodingKeys: String, CodingKey {
        case accounts, eligibility, categories, sources
        case destinationEligibility = "destination_eligibility"
    }
}

public struct FinancialAffectedAccount: Decodable, Sendable, Identifiable {
    public let accountId: UUID
    public let currency: String
    public let currencyFractionDigits: Int
    public let before: FinancialBalance
    public let after: FinancialBalance?
    public let observations: [FinancialObservation]
    public let unexplainedBefore: [String: Int64?]
    public let unexplainedAfter: [String: Int64?]?
    public var id: UUID { accountId }
    enum CodingKeys: String, CodingKey {
        case accountId = "account_id", currency, before, after, observations
        case currencyFractionDigits = "currency_fraction_digits"
        case unexplainedBefore = "unexplained_before", unexplainedAfter = "unexplained_after"
    }
}

public struct FinancialActivityPreview: Decodable, Sendable {
    public let ready: Bool
    public let expectedVersions: [String: Int]
    public let affectedAccounts: [FinancialAffectedAccount]
    public let reviewedRequest: FinancialActivityCommand?
    public let previewToken: String?
    enum CodingKeys: String, CodingKey {
        case ready
        case expectedVersions = "expected_versions"
        case affectedAccounts = "affected_accounts"
        case reviewedRequest = "reviewed_request", previewToken = "preview_token"
    }
}

public struct FinancialActivityLeg: Codable, Equatable, Sendable, Identifiable {
    public let recordId: UUID
    public let recordRevision: Int
    public let accountId: UUID
    public let role: String
    public let balanceMovementMinor: Int64
    public let coverage: [FinancialCoverage]
    public var id: UUID { recordId }
    enum CodingKeys: String, CodingKey {
        case recordId = "record_id", recordRevision = "record_revision"
        case accountId = "account_id", role, balanceMovementMinor = "balance_movement_minor", coverage
    }
}

/// Group identity stays stable when a correction changes either account leg.
public struct FinancialActivityDetail: Codable, Equatable, Sendable, Identifiable {
    public let activityId: UUID
    public let revision: Int
    public let kind: FinancialActivityKind
    public let amountMinor: Int64?
    public let amount: String?
    public let currency: String
    public let currencyFractionDigits: Int
    public let occurredAt: String
    public let timeZone: String
    public let note: String?
    public let categoryId: String?
    public let sourceId: String?
    public let purchaseActivityId: UUID?
    public let purchaseRevision: Int?
    public let reason: String?
    public let recordedAt: String
    public let recordedBy: String?
    public let legs: [FinancialActivityLeg]
    public let principalMinor: Int64?
    public let interestMinor: Int64?
    public let feesMinor: Int64?
    public let reversalOfActivityId: UUID?
    public let reversalOfRevision: Int?
    public let countedSpendingMinor: Int64?
    public let refundedMinor: Int64?
    public let refundableMinor: Int64?
    public var id: UUID { activityId }
    /// A destination-only projection has visible account legs but no authority
    /// to disclose or change the original source amount.
    public var originalAmountAvailable: Bool { amountMinor != nil && amount != nil }
    enum CodingKeys: String, CodingKey {
        case revision, kind, amount, currency, note, reason, legs
        case activityId = "activity_id", amountMinor = "amount_minor"
        case currencyFractionDigits = "currency_fraction_digits"
        case occurredAt = "occurred_at", timeZone = "time_zone"
        case categoryId = "category_id", sourceId = "source_id"
        case purchaseActivityId = "purchase_activity_id", purchaseRevision = "purchase_revision"
        case recordedAt = "recorded_at", recordedBy = "recorded_by"
        case principalMinor = "principal_minor", interestMinor = "interest_minor", feesMinor = "fees_minor"
        case reversalOfActivityId = "reversal_of_activity_id", reversalOfRevision = "reversal_of_revision", countedSpendingMinor = "counted_spending_minor"
        case refundedMinor = "refunded_minor", refundableMinor = "refundable_minor"
    }
}

public struct FinancialActivityReceipt: Decodable, Sendable {
    public let activity: FinancialActivityDetail
    public let accounts: [FinancialAccount]
    public let replayed: Bool
}

public struct FinancialPurchaseCatalog: Decodable, Sendable {
    public let items: [FinancialActivityDetail]
}
