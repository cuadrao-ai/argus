import Foundation
import ArgusSession

/// What the person reviews before a receipt becomes an expense. The server's reading fills it; every field stays editable.
struct ReceiptReviewDraft: Equatable {
    let connectionID: String
    var event: FinancialImportEvent
    let receipt: DocumentReceipt?
    var merchant: String
    var amount: String
    var currency: String
    var occurredOn: Date?
    var categoryID: String?
    var accountID: UUID?

    init(connectionID: String, event: FinancialImportEvent, receipt: DocumentReceipt?) {
        self.connectionID = connectionID; self.event = event; self.receipt = receipt
        let observation = event.observations.first { $0.connectionID == connectionID }
        merchant = receipt?.merchant ?? observation?.merchant ?? observation?.description ?? ""
        amount = event.facts.amount ?? receipt?.total ?? ""
        currency = event.facts.currency ?? receipt?.currency ?? ""
        occurredOn = (event.facts.occurredOn ?? receipt?.occurredOn).flatMap(Self.day)
        categoryID = receipt?.suggestedCategory
        accountID = event.facts.accountID.flatMap(UUID.init(uuidString:))
    }

    /// An already recorded movement this receipt may belong to.
    var existingMatch: UUID? { event.existingActivityMatches.first.flatMap(UUID.init(uuidString:)) }

    var isComplete: Bool {
        accountID != nil && occurredOn != nil && !currency.isEmpty
            && (Decimal(string: amount).map { $0 > 0 } ?? false)
    }

    /// Only what differs from the server's facts, plus the person's answers the server still needs.
    func changes(timeZone: TimeZone) -> FinancialImportChanges {
        var changes = FinancialImportChanges()
        let facts = event.facts
        if facts.kind != FinancialActivityKind.expense.rawValue { changes.kind = .expense }
        if let accountID, facts.accountID.flatMap(UUID.init(uuidString:)) != accountID { changes.accountID = accountID }
        if amount != facts.amount { changes.amount = amount }
        if currency != facts.currency { changes.currency = currency }
        if let occurredOn {
            let text = Self.dayText(occurredOn)
            if text != facts.occurredOn { changes.occurredOn = text; changes.timeZone = timeZone.identifier }
        }
        if let categoryID { changes.categoryID = categoryID }
        let note = merchant.trimmingCharacters(in: .whitespacesAndNewlines)
        if !note.isEmpty { changes.note = String(note.prefix(200)) }
        return changes
    }

    static func day(_ text: String) -> Date? { dayFormatter.date(from: text) }
    static func dayText(_ date: Date) -> String { dayFormatter.string(from: date) }
    private static let dayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}

/// What the sheet shows of a capture: the first image, or a document symbol for a PDF, and how many files came.
struct ReceiptPreview: Equatable {
    let image: Data?
    let count: Int

    init?(_ files: [(data: Data, name: String, pdf: Bool)]) {
        guard let first = files.first else { return nil }
        image = first.pdf ? nil : first.data
        count = files.count
    }

    /// A saved receipt reopened later: its file, which shows as a photo or, for a PDF, as the document symbol.
    init(image: Data) {
        self.image = image
        count = 1
    }
}

/// What a receipt hands to the movement sheet when the person writes it by hand. Each field is what the reading
/// found, if anything; the movement sheet still asks for the rest.
struct ReceiptHandoff: Equatable {
    let connectionID: String
    let merchant: String?
    let amount: String?
    let currency: String?
    let occurredOn: Date?

    init(connectionID: String, receipt: DocumentReceipt?) {
        self.connectionID = connectionID
        merchant = receipt?.merchant.flatMap { $0.isEmpty ? nil : $0 }
        amount = receipt?.total
        currency = receipt?.currency
        occurredOn = receipt?.occurredOn.flatMap(ReceiptReviewDraft.day)
    }
}
