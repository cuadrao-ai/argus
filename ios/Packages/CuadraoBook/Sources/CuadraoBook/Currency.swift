import Foundation

/// One currency the book accepts and the minor-unit digits it is read with.
public struct Currency: Hashable, Codable, Sendable {
    public let code: String
    public let digits: Int

    public init(code: String, digits: Int) {
        self.code = code
        self.digits = digits
    }
}

/// The currencies the server accepts, generated from its tender set (see `generate_book_currencies.py`).
/// An account snapshots its digits when it is created, so a later table change cannot reread stored amounts.
public enum CurrencyTable {
    public static let all: [Currency] = generatedCurrencyRows.map { Currency(code: $0.code, digits: $0.digits) }

    /// Offered first by pickers, in this order; the rest follow alphabetically.
    public static let priority = ["DOP", "USD", "EUR"]

    private static let byCode: [String: Currency] = Dictionary(uniqueKeysWithValues: all.map { ($0.code, $0) })

    /// The currency for a code after trimming and uppercasing, or nil when the server would refuse it.
    public static func currency(_ code: String) -> Currency? {
        byCode[code.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()]
    }

    public static func digits(_ code: String) -> Int? { currency(code)?.digits }

    /// Codes in picker order: the priority currencies, then every other one alphabetically.
    public static var pickerCodes: [String] {
        let rest = all.map(\.code).filter { !priority.contains($0) }.sorted()
        return priority.filter { byCode[$0] != nil } + rest
    }
}
